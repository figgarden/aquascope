# Privacy

AquaScope is a local, offline tool. This document lists everything it touches.

## Network

None. AquaScope contains no networking code: no HTTP clients, sockets, analytics, crash
reporting, or update checks. You can run it with networking disabled.

## Audio

- AquaScope opens **one input stream** on the device you choose (or the loopback device it
  selects automatically).
- Captured samples go into a fixed 16,384-frame in-memory ring buffer (about 0.34 s at 48 kHz),
  which is continuously overwritten. They are used only to draw the display.
- Audio is **never written to disk** and never leaves the process.
- `--demo` mode opens no audio device at all.

## Files

AquaScope writes exactly one file, and only after you pick a device with `d`:

| Platform | Location |
| --- | --- |
| Linux / macOS | `$XDG_CONFIG_HOME/aquascope/config.json`, default `~/.config/aquascope/config.json` |
| Windows | `%APPDATA%\aquascope\config.json` |

Contents:

```json
{
  "device_name": "BlackHole 2ch"
}
```

Delete the file to forget the choice.

## Diagnostics output

`aquascope --doctor` and `aquascope --list-devices` print to your terminal only. They show your
OS and version, Python version, terminal name, the config path with your home folder shown as
`~`, and the names of your audio input devices. Device names can include personal labels (for
example "Jane's AirPods"), so check the output before sharing it in a bug report.

## Screenshots in this repository

The images in `docs/` were produced by `tools/render_preview.py` with the built-in demo signal,
so they contain no real device names or audio.
