# mpv Jellyfin dmenu

A simple [Jellyfin] media selection program using [rofi], [wofi], or
[dmenu]. Launches [mpv] and reports playback progress to Jellyfin while playing.

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

[Jellyfin]: https://jellyfin.org/
[mpv]: https://mpv.io/
[dmenu]: https://tools.suckless.org/dmenu
[rofi]: https://davatorium.github.io/rofi
[wofi]: https://hg.sr.ht/~scoopta/wofi

## Development

```sh
make
```

### Todo

- Add Latest count configuration
- Add option to quit after watching for movies or shows
- Use dmenu for authentication instead of terminal
- Add the total number of episode in the season in shows titles
- Write more tests

## Yet another mpv Jellyfin

- https://github.com/EmperorPenguin18/mpv-jellyfin
- https://github.com/jellyfin/jellyfin-mpv-shim/tree/master/jellyfin_mpv_shim
- https://github.com/nonomal/jellyfin-desktop
- https://github.com/Aanok/jftui
