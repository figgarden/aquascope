# Contributing to AquaScope

Thanks for your interest! Bug reports, platform testing (especially Windows audio setups),
and new views are all welcome.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Before opening a pull request

```bash
ruff check .
pytest
```

The test suite runs headless and needs no audio hardware. CI runs it on Linux, macOS, and
Windows.

## Guidelines

- Keep AquaScope **offline**. Pull requests that add network access, analytics, or telemetry
  won't be accepted. See [PRIVACY.md](PRIVACY.md).
- Keep the aqua monochrome look. New colors should come from the palette in `textual_ui.py`.
- Rendering helpers (`braille_waveform`, `spectrum_chart`, …) are pure functions. Add a test
  in `tests/test_rendering.py` for any new one.
- If you change the UI, regenerate the screenshots with `python tools/render_preview.py`.

## Releasing (maintainers)

1. Bump the version in `pyproject.toml` and `src/aquascope/__init__.py`.
2. Add a `CHANGELOG.md` entry.
3. Tag and push: `git tag v2.5.0 && git push --tags`. The release workflow builds the
   wheel and sdist and attaches them to a GitHub release.

By contributing, you agree that your contributions are licensed under GPL-3.0-or-later.
