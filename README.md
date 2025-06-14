# mpv Jellyfin dmenu

A simple [Jellyfin] media browser using [dmenu] or alternative ([rofi] [wofi]
etc.). Opens [mpv] to play videos.

- Browse "Continue Watching", "Next-up", "Latest", and "Collections"

- Resume playback position and report watch progress to Jellyfin

- No server-side transcoding (thanks to mpv)

Other characteristics:

- Uses Jellyfin Quick Connect to authenticate the first time

- Launches *your* mpv with minimal interference

- Can use [dmenu alternatives][alt] (see `--help`)

- Follows [Jellyfin watched/resume rules][rules], *or not* (see `--help`)

[Jellyfin]: https://jellyfin.org/
[mpv]: https://mpv.io/
[dmenu]: https://tools.suckless.org/dmenu
[rofi]: https://davatorium.github.io/rofi
[wofi]: https://hg.sr.ht/~scoopta/wofi
[alt]: #dmenu-alternative-command
[rules]: https://jellyfin.josmind.com/web/#/dashboard/playback/resume

## Installation

Dependencies: `python3`, `mpv`, `dmenu` (or `rofi`, `wofi`, etc.), optional python module
`platformdirs`.

You can use `./mpv-jellyfin-dmenu` directly.

You can copy or symlink `mpv-jellyfin-dmenu` somewhere in your `$PATH` (`~/.local/bin`).

## Usage

**First, authenticate from a terminal with Jellyfin Quick Connect:**

```console
$ mpv-jellyfin-dmenu --auth
```

Then you are ready to run:

```console
$ mpv-jellyfin-dmenu
```

### Configuration

The configuration is located at `~/.config/mpv-jellyfin-dmenu/config.ini`.

Default configuration values can be seen from `--help`:

```console
$ mpv-jellyfin-dmenu --help
```

#### dmenu alternative command

```ini
# ~/.config/mpv-jellyfin-dmenu/config.ini
[mpv-jellyfin-dmenu]
dmenu_command = rofi -dmenu -i
```

## Development

```sh
make
```

### Todo

- Add Latest count configuration
- Add option to quit after watching for movies or shows
- Use dmenu for authentication instead of terminal
- Add the total number of episode in the season in shows titles
- Add mpv args configuration
- Collection Folder sort order
- Maybe follow [Jellyfin's Home](https://jellyfin.josmind.com/web/#/mypreferenceshome.html) [display preference](https://api.jellyfin.org/#tag/DisplayPreferences) ?
- Allow other players (VLC ? is there a VLC IPC remote control ?)
- write more tests

## Yet another mpv Jellyfin

- https://jellyfin.org/downloads/clients/
- https://github.com/EmperorPenguin18/mpv-jellyfin
- https://github.com/jellyfin/jellyfin-mpv-shim
- https://github.com/nonomal/jellyfin-desktop
- https://github.com/Aanok/jftui
