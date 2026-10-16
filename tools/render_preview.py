"""Export deterministic AquaScope screenshots (demo signal only) for docs and visual QA.

Usage:
    python tools/render_preview.py                # every scope mode into docs/
    python tools/render_preview.py WAVE VECTOR    # selected modes
    AQUASCOPE_PREVIEW_DIR=/tmp python tools/render_preview.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from aquascope.audio import AudioEngine
from aquascope.textual_ui import AquaScopeApp, ScopeWidget, SpectrumWidget

OUTPUT_DIR = Path(
    os.environ.get("AQUASCOPE_PREVIEW_DIR") or Path(__file__).resolve().parent.parent / "docs"
)
SPECTRUM_FOR_MODE = {"WAVE": "CURVE", "PERSIST": "BARS", "VECTOR": "WATERFALL"}


async def render(preview_mode: str, size: tuple[int, int]) -> Path:
    # demo=True never opens an audio device, so no real device names leak into images.
    app = AquaScopeApp(AudioEngine(), demo=True)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(1.0)
        scope = app.query_one(ScopeWidget)
        if preview_mode in scope._available_modes():
            scope.mode = preview_mode
            scope.border_title = f"OSCILLOSCOPE  |  {preview_mode}"
        spectrum = app.query_one(SpectrumWidget)
        while spectrum.mode != SPECTRUM_FOR_MODE.get(preview_mode, "CURVE"):
            spectrum.next_mode()
        await pilot.pause(0.5)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        return Path(
            app.save_screenshot(
                filename=f"aquascope-{preview_mode.lower()}.svg",
                path=str(OUTPUT_DIR),
            )
        )


async def main() -> None:
    modes = [mode.upper() for mode in sys.argv[1:]] or [
        "WAVE",
        "PERSIST",
        "MID",
        "VECTOR",
        "RADIAL",
    ]
    for mode in modes:
        size = (140, 40) if mode == "WAVE" else (100, 30)
        print(await render(mode, size))


if __name__ == "__main__":
    asyncio.run(main())
