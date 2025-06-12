#!/usr/bin/env python3

import argparse
import configparser
import json
import os
import os.path
import socket
import subprocess
import sys
import urllib
import urllib.request
import datetime
import select
import shutil
import shlex
from contextlib import contextmanager
from functools import partial
from textwrap import dedent
from types import SimpleNamespace


try:
    import platformdirs

    CONFIG_DIR = platformdirs.user_config_dir()
except ImportError:
    CONFIG_DIR = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.environ["HOME"], ".config"))


DMENUS = [
    ["rofi", "-dmenu", "-i"],
    ["wofi", "--dmenu", "-i"],
    ["dmenu", "-i"],
]


def make_parser():
    parser = argparse.ArgumentParser(
        description="Select jellyfin media with dmenu and play them with mpv",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--auth", action="store_true", help="Force authenticate, use from a terminal."
    )
    parser.add_argument(
        "--auth-config",
        default=os.path.join(CONFIG_DIR, "mpv-jellyfin-dmenu/auth.ini"),
        help="Generated authentication data (%(default)s).",
    )
    avail = " or ".join(next(zip(*DMENUS)))
    parser.add_argument(
        "-d",
        "--dmenu",
        help=f"The dmenu command (by default, looks for $DMENU, {avail}).",
    )
    parser.add_argument("--debug", action="store_true", help="Debug print.")
    parser.add_argument("mpv_args", nargs="*", help="Additional mpv arguments")

    return parser


class Config:
    """Simplest ini config."""

    def __init__(self, section, attributes):
        self.path = None
        self.section = section
        self.attributes = attributes
        for k in self.attributes:
            setattr(self, k, None)

    def read(self):
        ini = configparser.ConfigParser()
        ini.read(self.path)
        if self.section in ini:
            for k in self.attributes:
                setattr(self, k, str(ini[self.section].get(k, "")))

    def write(self):
        ini = configparser.ConfigParser()
        ini[self.section] = {}
        for k in self.attributes:
            ini[self.section][k] = str(getattr(self, k, "") or "")
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w", encoding="utf-8") as f:
            ini.write(f)


AUTH_CONFIG = Config("jellyfin_authentication", ("url", "token", "user"))

GLOBAL = SimpleNamespace()


def jellyfin_api(method, uri, query=None, data=None):
    url = AUTH_CONFIG.url + "/" + uri
    req_data = None
    name = "mpv-jellyfin-dmenu"
    device = "mpv-jellyfin-dmenu"
    token = AUTH_CONFIG.token
    machine_id = 1
    version = "1"
    headers = {
        "Accept": "application/json;charset=utf-8",
        "Authorization": (
            f"MediaBrowser Client={name}, Device={device}, "
            f"DeviceId={machine_id}, Version={version}"
        ),
    }

    if query is not None:
        url = url + "?" + urllib.parse.urlencode(query)
    if data is not None:
        req_data = json.dumps(data).encode()
        headers["Content-type"] = "application/json;charset=utf-8"

    if GLOBAL.debug:
        debug("jellyfin_api REQ", method, url, json.dumps(headers), json.dumps(data))

    if token:
        headers["Authorization"] += f", Token={token}"

    req = urllib.request.Request(
        url=url,
        method=method,
        headers=headers,
        data=req_data,
    )

    with urllib.request.urlopen(req) as f:
        resp = json.load(f)
        if GLOBAL.debug:
            debug("jellyfin_api RESP", json.dumps(resp))
        return resp


def jellyfin_get(uri, query=None, data=None):
    return jellyfin_api("GET", uri, query=query, data=data)


def jellyfin_post(uri, query=None, data=None):
    return jellyfin_api("POST", uri, query=query, data=data)


def debug(*msg):
    if GLOBAL.debug:
        print("[DEBUG]", *msg, file=sys.stderr)


def info(*msg):
    print(*msg, file=sys.stderr)


def error(*msg):
    print("error:", *msg, file=sys.stderr)


def fatal(*msg):
    print("fatal error:", *msg, file=sys.stderr)
    sys.exit(1)


def authenticate():
    info()

    if AUTH_CONFIG.url:
        url = input(f"Please enter your Jellyfin url (defaults to {AUTH_CONFIG.url}): ").strip()
        if url:
            AUTH_CONFIG.url = url
    else:
        AUTH_CONFIG.url = input("Please enter your Jellyfin url: ").strip()
    info()

    AUTH_CONFIG.url = AUTH_CONFIG.url.rstrip("/")
    if not AUTH_CONFIG.url:
        fatal("Invalid url.")
    AUTH_CONFIG.write()

    pubinfo = jellyfin_get("System/Info/Public")
    info(f"Connected to Jellyfin {pubinfo['ServerName']!r} v{pubinfo['Version']}")
    info()

    info("Initiating quick connect:")
    qc = jellyfin_post("QuickConnect/Initiate")
    code = qc["Code"]
    secret = qc["Secret"]

    msg = dedent(
        f"""
        Please, authorize via Jellyfin Quick Connect:

        1) Sign-in to {AUTH_CONFIG.url}

        2) Authorize code {code} in {AUTH_CONFIG.url}/#/quickconnect

        3) Then, press enter...
        """
    )
    info(msg)
    input()

    try:
        auth = jellyfin_post("Users/AuthenticateWithQuickConnect", {}, {"Secret": secret})
    except urllib.error.HTTPError as e:
        fatal(f"authentication failed ({e})")
    AUTH_CONFIG.token = auth["AccessToken"]

    me = jellyfin_get("Users/Me")
    info(f"Authenticated as {me['Name']!r}")

    AUTH_CONFIG.write()


def item_played_percent(item):
    tot = item.get("RunTimeTicks", None)
    ud = item.get("UserData", {})
    pl = ud.get("PlaybackPositionTicks", {})
    if pl and tot:
        return 100.0 * float(pl) / float(tot)
    return None


def item_title(item, menu=True):
    title = []

    if menu:
        typ = item["Type"]

        if typ in ["ParentFolder"]:
            icon = "🔙"
        elif typ in ["CollectionFolder"]:
            icon = "📂"
        elif item.get("MediaType") == "Video":
            icon = "🎬"
        elif typ in ["Series", "Season"]:
            icon = "📺"
        elif typ in ["Movie"]:
            icon = "🎬"
        else:
            icon = f"[{typ}]"

        title.append(icon)

        ud = item.get("UserData", {})
        watched = ud.get("Played", False)
        watched_pos = item_played_percent(item)
        if watched:
            title.append("✅")
        if watched_pos:
            title.append(f"⏳{watched_pos:.0f}%")

    y = item.get("ProductionYear")

    series = item.get("SeriesName")
    if series:
        title.append(series)
        if y:
            title.append(f"({y})")

        e = item.get("IndexNumber", None)
        s = item.get("ParentIndexNumber", None)
        if s is not None and e is not None:
            title.append(f"S{s:>02}E{e:>02}")

        title.append("-")

        name = item["Name"]
        title.append(name)
    else:
        name = item["Name"]
        title.append(name)
        if y:
            title.append(f"({y})")

    res = " ".join(title)
    return res


def json_load_multiple(data):
    """Yields multiple (json_object, remaining_data). Stops when data is not a valid json.

    while:
        data += ... get more data ...
        for (js, data) in json_load_multiple(data):
            ...

    """
    while data:
        try:
            data_str = data.decode()  # Is decode safe over partial data ?
            js, end = json.JSONDecoder().raw_decode(data_str)
            data = data_str[end:].lstrip(" \n").encode()
            yield (js, data)
        except json.decoder.JSONDecodeError:
            break


def test_json_load_multiple():
    assert list(json_load_multiple(b"[1]\n[2]\n")) == [([1], b"[2]\n"), ([2], b"")]
    assert not list(json_load_multiple(b"["))
    assert list(json_load_multiple(b"[1]\n[2")) == [([1], b"[2")]
    assert list(json_load_multiple(b"[1]\n[2]\n[")) == [([1], b"[2]\n["), ([2], b"[")]


class MpvWatcher:
    """Handle for watched_mpv."""

    def __init__(self, fd, playback_pct):
        self.fd = fd
        self.playback_pct = playback_pct
        self.ask_playback_pct_id = 42
        self.ask_playback_pct_cmd = (
            json.dumps(
                {
                    "command": ["get_property", "percent-pos"],
                    "request_id": self.ask_playback_pct_id,
                }
            ).encode()
            + b"\n"
        )
        self.returncode = None
        self.data = b""

    def loop(self, interval):
        fd = self.fd
        data = self.data
        fds = (fd.fileno(),)
        r, _, x = select.select(fds, (), fds, interval)
        if x:
            return False
        if r:
            recv = fd.recv(1024 * 4)
            if not recv:  # (disconnected)
                return False
            data += recv
            for msg, data in json_load_multiple(data):
                debug("recv from mpv:", msg)
                if msg.get("request_id") == self.ask_playback_pct_id:
                    self.playback_pct = msg["data"]
            if data:
                debug("partial recv:", data)
        else:  # (timeout)
            fd.sendall(self.ask_playback_pct_cmd)
        return True


@contextmanager
def watched_mpv(url, title, playback_pct):
    myfd, mpvfd = socket.socketpair()

    mpv_cmd = ["mpv", f"--input-ipc-client=fd://{mpvfd.fileno()}"]
    if playback_pct:
        info(f"Resuming video at {playback_pct:.2f}%")
        mpv_cmd.append(f"--start={playback_pct:.2f}%")
    mpv_cmd.append("--force-media-title=" + title)
    mpv_cmd.extend(GLOBAL.mpv_args)
    mpv_cmd.append("--")
    mpv_cmd.append(url)

    watcher = MpvWatcher(myfd, playback_pct=playback_pct)
    with subprocess.Popen(mpv_cmd, pass_fds=(mpvfd.fileno(),)) as proc:
        mpvfd.close()
        try:
            yield watcher
        except Exception as e:
            error(e, "... waiting for mpv to quit")
            raise

    myfd.close()
    watcher.returncode = proc.returncode


def now_iso():
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def mpv_play_item(item):
    url = AUTH_CONFIG.url + f"/Videos/{item['Id']}/stream?static=true"
    title = item_title(item, menu=False)
    ud = item["UserData"]
    playback_ticks = ud["PlaybackPositionTicks"]
    play_count = ud["PlayCount"]
    played = ud["Played"]
    runtime_ticks = item["RunTimeTicks"]

    play_count += 1

    def ticks_to_pct(ticks):
        return 100.0 * (float(ticks) / float(runtime_ticks))

    def pct_to_ticks(pct):
        return int(runtime_ticks * (pct / 100.0))

    playback_pct = ticks_to_pct(playback_ticks)

    with watched_mpv(
        url=url, title=title + " (mpv-jellyfin-dmenu)", playback_pct=playback_pct
    ) as watcher:
        while watcher.loop(10.0):
            if playback_pct != watcher.playback_pct:
                playback_pct = watcher.playback_pct
                playback_ticks = pct_to_ticks(playback_pct)
                # TODO: support lost connection (or token change, etc.)
                res = jellyfin_post(
                    f"UserItems/{item['Id']}/UserData",
                    {"userId": GLOBAL.user_id},
                    {
                        "PlaybackPositionTicks": playback_ticks,
                        "LastPlayedDate": now_iso(),
                        "PlayCount": play_count,
                    },
                )
                played = res["Played"]

    if watcher.returncode != 0:
        fatal(f"mpv exit {watcher.returncode}")

    info("")
    menu = [
        f"⏳ In progress at {playback_pct:.0f}%",
        "✅ Watched",
        "❎ Not watched",
    ]
    ans = dmenu_ask(f"Mark: {title}", "\n".join(menu))
    if ans is None:
        fatal("abort.")
    ansid = menu.index(ans)
    if ansid == 0:
        played = False
    elif ansid == 1:
        played = True
        playback_ticks = 0
    elif ansid == 2:
        played = False
        playback_ticks = 0
    else:
        assert False
    playback_pct = ticks_to_pct(playback_ticks)
    info(f"Marking played={played} pos={playback_pct:.0f}%: {title}")
    jellyfin_post(
        f"UserItems/{item['Id']}/UserData",
        {"userId": GLOBAL.user_id},
        {"Played": played, "PlaybackPositionTicks": playback_ticks},
    )


def dmenu_ask(prompt, stdin):
    dmenu_cmd = GLOBAL.dmenu_cmd + ["-p", prompt]
    debug("dmenu_ask", dmenu_cmd)
    with subprocess.Popen(
        dmenu_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        encoding="utf-8",
    ) as proc:
        if stdin:
            proc.stdin.write(stdin)
            proc.stdin.close()
        stdout = proc.stdout.read()
    if proc.returncode != 0:
        return None
    if stdout[-1] == "\n":
        stdout = stdout[:-1]
    return stdout


def main():
    GLOBAL.debug = False

    parser = make_parser()
    opts = parser.parse_args()

    GLOBAL.debug = opts.debug

    AUTH_CONFIG.path = opts.auth_config
    AUTH_CONFIG.read()

    dmenu_str = opts.dmenu or os.environ.get("DMENU")
    if dmenu_str:
        dmenu_cmd = shlex.split(dmenu_str)
        if not shutil.which(dmenu_cmd[0]):
            fatal(f"Could not find executable {dmenu_cmd[0]!r}")
    else:
        for dmenu_cmd in DMENUS:
            if shutil.which(dmenu_cmd[0]):
                break
        else:
            avail = " or ".join(next(zip(*DMENUS)))
            fatal(f"Could not find a suitable $DMENUS or {avail}.")
    GLOBAL.dmenu_cmd = dmenu_cmd

    GLOBAL.mpv_args = opts.mpv_args

    # --auth options
    if opts.auth:
        authenticate()
        info("\nmpv-jellyfin-dmenu is ready.\n")
        return

    # Test authentication
    if not (AUTH_CONFIG.url and AUTH_CONFIG.token):
        dmenu_ask(
            "mpv-jellyfin-dmenu auth required",
            dedent(
                """
                ERROR: missing Jellyfin authentication

                Please, open a terminal to authenticate:

                  $ mpv-jellyfin-dmenu --auth

                """
            ),
        )
        fatal("missing authentication")

    try:
        me = jellyfin_get("Users/Me")
    except urllib.error.HTTPError as e:
        msg = dedent(
            f"""
            Authentication failed ({e})

            You can re-setup authentication with

              $ mpv-jellyfin-dmenu --auth

            """
        )
        dmenu_ask("Error", msg)
        fatal(msg)

    GLOBAL.user_id = me["Id"]
    info(f"Authenticated on {AUTH_CONFIG.url!r} as {me['Name']!r}")

    # Main loop

    next_item = None
    parents = []

    while True:
        lines_item = []
        lines_id = set()
        lines = []

        def push_item(item, prefix=None):
            item_id = item.get("Id", None)
            if item_id is not None and item_id in lines_id:
                return
            lines_id.add(item_id)
            title = (prefix or "") + item_title(item).strip()
            lines.append(title)
            lines_item.append(item)

        def push_items(items, prefix=None):
            list(map(partial(push_item, prefix=prefix), items))

        if next_item is None:
            # Root menu

            # Continue watching
            resumes = jellyfin_get("UserItems/Resume", {"mediaTypes": "Video"})
            push_items(resumes["Items"], prefix="▶️ ")

            # Next-up
            nexts = jellyfin_get("Shows/NextUp", {"mediaTypes": "Video"})
            push_items(nexts["Items"], prefix="⏭️ ")

            # Root folders and their latest items
            roots = jellyfin_get("UserViews", {"userId": GLOBAL.user_id})
            for root in roots["Items"]:
                push_item(root)
                latests = jellyfin_get(
                    "Items/Latest",
                    {
                        "mediaTypes": "Video",
                        "parentId": root["Id"],
                        "userId": GLOBAL.user_id,
                        "limit": 5,
                    },
                )
                push_items(latests[:5])  # (no Items)

        else:
            # Folder-like menu (e.g. Folder, Series, Season)

            # Fake ParentFolder
            push_item({"Name": "..", "Type": "ParentFolder"})

            # Folder items
            its = jellyfin_get("Items", {"userId": GLOBAL.user_id, "parentId": next_item["Id"]})
            push_items(its["Items"])

        ans = dmenu_ask("mpv-jellyfin-dmenu", "\n".join(lines))
        if ans is None:
            fatal("abort.")

        i = lines.index(ans)
        item = lines_item[i]
        info("Selected:", item_title(item))

        if item["Type"] == "ParentFolder":  # Fake ParentFolder
            next_item = parents.pop()
        elif item["IsFolder"]:
            parents.append(next_item)
            next_item = item
        elif item["MediaType"] == "Video":
            mpv_play_item(item)
        else:
            fatal(f"unknown item type {item['Type']!r}")

    return


if __name__ == "__main__":
    main()
