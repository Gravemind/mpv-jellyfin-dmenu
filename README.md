# mpv Jellyfin dmenu

A simple Jellyfin media selection program using [rofi], [wofi], or
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

[mpv]: https://mpv.io/
[dmenu]: https://tools.suckless.org/dmenu
[rofi]: https://davatorium.github.io/rofi
[wofi]: https://hg.sr.ht/~scoopta/wofi

## Development

```sh
make
```

### Todo

- Add ini config file for dmenu command and more
- Add icons configuration
- Add playback reporting configuration (interval)
- Add `mark-watched-at` (or something) to replace popup
- Use dmenu for authentication instead of terminal
- Write more tests
