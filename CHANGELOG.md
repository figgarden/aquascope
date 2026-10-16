# Changelog

All notable changes to AquaScope are documented here. This project follows
[Semantic Versioning](https://semver.org/).

## [2.5.0] - 2026-10-16

### Added
- **Windows support.** Settings are stored in `%APPDATA%\aquascope`. Stereo Mix (including
  common localized names), VB-Audio Virtual Cable, and VoiceMeeter are detected as loopback
  sources. The WASAPI copy of a device is preferred over MME/DirectSound/WDM-KS duplicates.
  Windows-specific setup hints and Windows Terminal detection in `--doctor`.
- CI on Linux, macOS, and Windows across Python 3.11–3.14.
- Tests for config handling and Windows device selection.
- `PRIVACY.md`, `CONTRIBUTING.md`, issue templates, and a tag-driven release workflow.
- README screenshots of every view.

### Changed
- `--doctor` shows the config path with the home directory as `~`, so pasted diagnostics
  don't reveal your username.
- An empty `XDG_CONFIG_HOME` now falls back to `~/.config` instead of the current directory.
- `tools/render_preview.py` writes to `docs/` (or `$AQUASCOPE_PREVIEW_DIR`) and can render
  every mode, instead of a hard-coded path.

### Removed
- The unused legacy curses interface (`tui.py`). The `curses` module doesn't exist on Windows,
  and the Textual UI fully replaced it.

## [2.4.1] - 2026-08-25

- First packaged release: Textual UI with Braille oscilloscope, FFT trace / RTA bars /
  waterfall, persistence, mid/side, vectorscope and polar views, telemetry panel, device
  picker, compact layout, and `--doctor`.

[2.5.0]: https://github.com/figgarden/aquascope/releases/tag/v2.5.0
[2.4.1]: https://github.com/figgarden/aquascope/releases/tag/v2.4.1
