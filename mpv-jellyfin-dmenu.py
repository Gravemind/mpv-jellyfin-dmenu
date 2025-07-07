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
import secrets
import time
from contextlib import contextmanager
from functools import partial
from textwrap import dedent
from types import SimpleNamespace


try:
    import platformdirs

    CONFIG_DIR = platformdirs.user_config_dir()
except ImportError:
    CONFIG_DIR = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.environ["HOME"], ".config"))


DEFAULT_CONFIG_INI = """
[mpv-jellyfin-dmenu]

# Alternative dmenu command. Leave empty to auto select.
dmenu_command =

# Jellyfin > Dashboard > Playback > Resume
jellyfin_watched_rules = true

# Interval between playback position reporting
playback_report_interval = 4.0

# MPV command line argument. For example:
#   Open window immediately: --force-window=immediate
#   Keep window open after end of video: --idle=yes
#   Start fullscreen: --fullscreen
mpv_args = --force-window=immediate

icon_watched = ✅
icon_not_watched = ❎
icon_in_progress = ⏳
icon_continue = ▶️
icon_play_next = ⏭️️
icon_parent_folder = 🔙
icon_collection_folder = 📂
icon_movie = 🎥
icon_show = 📺
icon_season = 📺
icon_video = 🎬
"""

DEFAULT_AUTH_INI = """
[jellyfin_authentication]
url =
token =
device_id =
"""

DMENUS = [
    ["rofi", "-dmenu", "-i"],
    ["wofi", "--dmenu", "-i"],
    ["dmenu", "-i"],
]

YESES = ["true", "yes", "1", "on"]


def make_parser():
    default_auth_path = os.path.join(CONFIG_DIR, "mpv-jellyfin-dmenu/auth.ini")
    default_config_path = os.path.join(CONFIG_DIR, "mpv-jellyfin-dmenu/config.ini")

    parser = argparse.ArgumentParser(
        description="Select jellyfin media with dmenu and play them with mpv",
        epilog=(
            f"Default config values (when not specified in {default_config_path}):\n\n"
            f"```ini{DEFAULT_CONFIG_INI}```\n "
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--auth", action="store_true", help="Force authenticate, use from a terminal."
    )
    parser.add_argument(
        "--auth-config",
        default=default_auth_path,
        help="Generated authentication data.\ndefault: %(default)s",
    )
    parser.add_argument(
        "--config",
        default=default_config_path,
        help="Config file.\ndefault: %(default)s",
    )
    parser.add_argument(
        "--jellyfin-watched-rules",
        dest="jellyfin_watched_rules",
        action="store_true",
        default=None,
        help="Follow jellyfin rules to mark as watched/progress.\n"
        "See Jellyfin > Dashboard > Playback > Resume",
    )
    parser.add_argument(
        "--ask-watched",
        dest="jellyfin_watched_rules",
        action="store_false",
        default=None,
        help="Disable --jellyfin-watched-rules: ask watched/played state after playing.",
    )
    avail = " or ".join(next(zip(*DMENUS)))
    parser.add_argument(
        "-d",
        "--dmenu",
        help=f"The dmenu command.\ndefault: $DMENU or {avail}",
    )
    parser.add_argument("--debug", action="store_true", help="Debug print.")
    parser.add_argument("mpv_args", nargs="*", help="Additional mpv arguments")

    return parser


class Config:
    """Simplest ini config."""

    def __init__(self, default):
        ini = configparser.ConfigParser()
        ini.read_string(default)
        self.__dict__.update(
            {
                "_path": None,
                "_ini": ini,
                "_section": ini.sections()[0],
            }
        )

    def set_path(self, path):
        self._path = path

    def read(self):
        self._ini.read(self._path)

    def write(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            self._ini.write(f)

    def __getattr__(self, name):
        return self._ini[self._section][name]

    def __setattr__(self, name, value):
        if name in self.__dict__:
            self.__dict__[name] = value
        else:
            self._ini[self._section][name] = value


AUTH_CONFIG = Config(DEFAULT_AUTH_INI)

CONFIG = Config(DEFAULT_CONFIG_INI)

GLOBAL = SimpleNamespace()


def jellyfin_api(method, uri, query=None, data=None):
    url = AUTH_CONFIG.url + "/" + uri

    # Seen as Device AppName by Jellyfin
    client = "mpv-jellyfin-dmenu"
    # Seen as Device AppVersion by Jellyfin
    version = "1"
    # Seen as Device Name by Jellyfin
    device = "mpv-jellyfin-dmenu@" + socket.gethostname()
    # Seen as Device Id by Jellyfin
    device_id = AUTH_CONFIG.device_id or "1"

    headers = {
        "Accept": "application/json;charset=utf-8",
        "Authorization": (
            f"MediaBrowser Client={client}, Version={version}"
            f", Device={device}, DeviceId={device_id}"
        ),
    }

    if query is not None:
        url = url + "?" + urllib.parse.urlencode(query)

    content = None
    if data is not None:
        content = json.dumps(data).encode()
        headers["Content-type"] = "application/json;charset=utf-8"

    if GLOBAL.debug:
        debug("jellyfin_api REQ", method, url, json.dumps(headers), json.dumps(data))

    token = AUTH_CONFIG.token
    if token:
        headers["Authorization"] += f", Token={token}"

    req = urllib.request.Request(
        url=url,
        method=method,
        headers=headers,
        data=content,
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

    if not AUTH_CONFIG.device_id:
        AUTH_CONFIG.device_id = secrets.token_bytes(16).hex()

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

        if typ == "ParentFolder":
            icon = CONFIG.icon_parent_folder
        elif typ == "CollectionFolder":
            icon = CONFIG.icon_collection_folder
        elif typ == "Series":
            icon = CONFIG.icon_show
        elif typ == "Season":
            icon = CONFIG.icon_season
        elif typ == "Movie":
            icon = CONFIG.icon_movie
        elif item.get("MediaType") == "Video":
            icon = CONFIG.icon_video
        else:
            icon = f"[{typ}]"

        title.append(icon)

        ud = item.get("UserData", {})
        watched = ud.get("Played", False)
        watched_pos = item_played_percent(item)
        if watched:
            title.append(CONFIG.icon_watched)
        if watched_pos:
            title.append(f"{CONFIG.icon_in_progress}{watched_pos:.0f}%")

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

    Supports truncated json and utf-8 char sequence at the end. But if the json is invalid in the
    middle of data the function will never advance.

    """
    WS = b" \t\n"
    decoder = json.JSONDecoder()
    while data:
        data = data.lstrip(WS)
        try:
            data_str = data.decode()
            invalid_end = b""
        except UnicodeDecodeError as e:
            if e.end == len(data):
                data_str = data[: e.start].decode()
                invalid_end = data[e.start :]
            else:
                raise
        try:
            js, end = decoder.raw_decode(data_str)
        except json.decoder.JSONDecodeError:
            # (does not work: e.pos reports the beginning of truncated strings)
            # if e.pos < len(data_str) - 1:
            #     raise
            break
        data = data_str[end:].encode().lstrip(WS) + invalid_end
        yield (js, data)


def test_json_load_multiple():
    import pytest  # pylint: disable=import-outside-toplevel

    assert list(json_load_multiple(b"[1]\n[2]\n")) == [([1], b"[2]\n"), ([2], b"")]
    assert list(json_load_multiple(b" [1][2]")) == [([1], b"[2]"), ([2], b"")]
    assert list(json_load_multiple(b"[1]\n[2]\n")) == [([1], b"[2]\n"), ([2], b"")]
    assert not list(json_load_multiple(b"["))
    assert list(json_load_multiple(b"[1]\n[2")) == [([1], b"[2")]
    assert list(json_load_multiple(b"[1]\n[2]\n[")) == [([1], b"[2]\n["), ([2], b"[")]

    # Test utf-8
    assert list(json_load_multiple('[1]\n["☺"]\n['.encode())) == [
        ([1], '["☺"]\n['.encode()),
        (["☺"], b"["),
    ]

    # Test truncated utf-8 char
    utf = "☺".encode("utf-8")
    assert len(utf) > 2
    truncated_utf = utf[:-1]
    # sanity check
    with pytest.raises(UnicodeDecodeError):
        truncated_utf.decode()
    truncated_utf_json = b'{"truncated":"' + truncated_utf
    assert not list(json_load_multiple(truncated_utf_json))
    assert list(json_load_multiple(b'{"valid":1} ' + truncated_utf_json)) == [
        ({"valid": 1}, truncated_utf_json)
    ]

    invalid_utf = b'["invalid' + truncated_utf + b'char"]'
    with pytest.raises(UnicodeDecodeError):
        list(json_load_multiple(invalid_utf))


class MpvWatcher:
    """Handle for watched_mpv."""

    def __init__(self, fd, playback_pct, interval):
        self.fd = fd
        self.playback_pct = playback_pct
        self.interval = interval
        self.returncode = None
        self.loop_gen_it = self.loop_gen()

    def loop_gen(self):
        pb_req_id = 42
        pb_cmd = (
            json.dumps(
                {
                    "command": ["get_property", "percent-pos"],
                    "request_id": pb_req_id,
                }
            ).encode()
            + b"\n"
        )

        fd = self.fd
        fds = (fd.fileno(),)
        data = b""

        # Shorter delay after seek: doesn't change yield interval, but gets us a better last
        # position after seek and quit.
        fast_delay = 0.1

        now = time.monotonic()
        next_pb_update = now + self.interval
        next_yield = now + self.interval
        while True:
            r, _, x = select.select(fds, (), fds, max(0, min(next_pb_update, next_yield) - now))
            if x:
                return

            now = time.monotonic()
            if r:
                recv = fd.recv(1024 * 4)  # shouldn't block
                if not recv:  # (disconnected)
                    return
                data += recv
                for msg, data in json_load_multiple(data):
                    debug("recv from mpv:", msg)
                    if msg.get("request_id") == pb_req_id:
                        msg_data = msg.get("data")
                        if msg_data is not None:
                            self.playback_pct = msg_data
                        next_pb_update = now + self.interval
                    elif msg.get("event") in ["seek"]:
                        # "seek" event is when seeking begins
                        # "playback-restart" event is when playback restarts after seek
                        next_pb_update = now + fast_delay
                if data:
                    debug("partial recv:", data)

            if now >= next_yield:
                next_yield = now + self.interval
                yield

            if now >= next_pb_update:
                self.fd.sendall(pb_cmd)  # blocks
                now = time.monotonic()
                next_pb_update = now + self.interval

    def loop(self):
        try:
            next(self.loop_gen_it)
            return True
        except ConnectionResetError as e:
            info(f"mpv connection closed: {e}")
            return False
        except StopIteration:
            return False


@contextmanager
def watched_mpv(url, title, playback_pct, interval):
    myfd, mpvfd = socket.socketpair()

    mpv_cmd = ["mpv", f"--input-ipc-client=fd://{mpvfd.fileno()}"]
    if playback_pct:
        info(f"Resuming video at {playback_pct:.2f}%")
        mpv_cmd.append(f"--start={playback_pct:.2f}%")
    mpv_cmd.append("--force-media-title=" + title)
    mpv_cmd.extend(GLOBAL.mpv_args)
    mpv_cmd.append("--")
    mpv_cmd.append(url)

    watcher = MpvWatcher(myfd, playback_pct=playback_pct, interval=interval)
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

    # Should we get a fresh playcount ?
    play_count = item["UserData"]["PlayCount"]
    res = jellyfin_post(
        f"UserItems/{item['Id']}/UserData",
        {"userId": GLOBAL.user_id},
        {
            "PlayCount": play_count + 1,
            "LastPlayedDate": now_iso(),
        },
    )
    # Replace with fresh user data
    item["UserData"] = res

    url = AUTH_CONFIG.url + f"/Videos/{item['Id']}/stream?static=true"
    title = item_title(item, menu=False)
    ud = item["UserData"]
    playback_ticks = ud["PlaybackPositionTicks"]
    runtime_ticks = item["RunTimeTicks"]
    played = ud["Played"]

    def ticks_to_pct(ticks):
        return 100.0 * (float(ticks) / float(runtime_ticks))

    def pct_to_ticks(pct):
        return int(runtime_ticks * (pct / 100.0))

    playback_pct = ticks_to_pct(playback_ticks)

    with watched_mpv(
        url=url,
        title=title + " (mpv-jellyfin-dmenu)",
        playback_pct=playback_pct,
        interval=GLOBAL.playback_report_interval,
    ) as watcher:
        while watcher.loop():
            if watcher.playback_pct != playback_pct:
                playback_pct = watcher.playback_pct
                playback_ticks = pct_to_ticks(playback_pct)
                # TODO: support lost connection (or token change, etc.)
                jellyfin_post(
                    f"UserItems/{item['Id']}/UserData",
                    {"userId": GLOBAL.user_id},
                    {"PlaybackPositionTicks": playback_ticks, "Played": False},
                )

    # Get very last known position
    playback_pct = watcher.playback_pct
    playback_ticks = pct_to_ticks(playback_pct)

    if watcher.returncode != 0:
        fatal(f"mpv exit {watcher.returncode}")
    info("")

    # Get jellyfin watched/resume rules
    if GLOBAL.jellyfin_watched_rules:
        # Late fetch to get latest config
        res = jellyfin_get("System/Configuration", {}, {})
        min_duration = res["MinResumeDurationSeconds"]
        min_resume = res["MinResumePct"]
        max_resume = res["MaxResumePct"]

        # https://learn.microsoft.com/en-us/dotnet/api/system.timespan.tickspersecond?view=net-9.0#system-timespan-tickspersecond
        ticks_per_seconds = 10000000

        if runtime_ticks / ticks_per_seconds < min_duration:
            played = True
            playback_ticks = 0
        elif playback_pct < min_resume:
            played = False  # Played mark is removed in Jellyfin
            playback_ticks = 0
        elif playback_pct > max_resume:
            played = True
            playback_ticks = 0
        else:
            played = False

    else:
        menu = [
            f"{CONFIG.icon_in_progress} In progress at {playback_pct:.0f}%",
            f"{CONFIG.icon_watched} Watched",
            f"{CONFIG.icon_not_watched} Not watched",
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

    CONFIG.set_path(opts.config)
    CONFIG.read()

    GLOBAL.debug = opts.debug
    GLOBAL.playback_report_interval = float(CONFIG.playback_report_interval.strip() or 5.0)

    if opts.jellyfin_watched_rules is not None:
        GLOBAL.jellyfin_watched_rules = opts.jellyfin_watched_rules
    else:
        GLOBAL.jellyfin_watched_rules = CONFIG.jellyfin_watched_rules.lower().strip() in YESES

    AUTH_CONFIG.set_path(opts.auth_config)
    AUTH_CONFIG.read()

    dmenu_str = opts.dmenu or CONFIG.dmenu_command or os.environ.get("DMENU")
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

    if opts.mpv_args:
        GLOBAL.mpv_args = opts.mpv_args
    else:
        GLOBAL.mpv_args = shlex.split(CONFIG.mpv_args)

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
            push_items(resumes["Items"], prefix=f"{CONFIG.icon_continue} ")

            # Next-up
            nexts = jellyfin_get("Shows/NextUp", {"mediaTypes": "Video"})
            push_items(nexts["Items"], prefix=f"{CONFIG.icon_play_next} ")

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
                        # "limit": 5,  # Bug ? responds with less results than asked.
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
