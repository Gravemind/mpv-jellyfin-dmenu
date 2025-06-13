# mpv Jellyfin dmenu

A simple [Jellyfin] media selection program using [rofi], [wofi], or
[dmenu]. Launches [mpv] and reports playback progress to Jellyfin while playing.

## Usage

**First, authenticate from a terminal with Jellyfin Quick Connect:**

```console
$ mpv-jellyfin-dmenu --auth
```

Then you are ready to run:

```console
$ mpv-jellyfin-dmenu
```

### Use dmenu alternatives

```console
$ export DMENU="rofi -dmenu -i"
$ mpv-jellyfin-dmenu
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

- Add icons configuration
- Add playback reporting configuration (interval)
- Add Latest count configuration
- Add `mark-watched-at` (or something) to replace popup
- Add option to quit after watching for movies or shows
- Use dmenu for authentication instead of terminal
- Add the total number of episode in the season in shows titles
- Write more tests

## Yet another mpv Jellyfin

- https://github.com/EmperorPenguin18/mpv-jellyfin
- https://github.com/jellyfin/jellyfin-mpv-shim/tree/master/jellyfin_mpv_shim
- https://github.com/nonomal/jellyfin-desktop
- https://github.com/Aanok/jftui
