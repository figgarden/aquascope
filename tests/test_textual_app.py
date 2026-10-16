import asyncio

from aquascope.audio import AudioEngine
from aquascope.textual_ui import AquaScopeApp, ScopeWidget, SpectrumWidget


def test_compact_app_layout_and_controls():
    async def exercise() -> None:
        app = AquaScopeApp(AudioEngine(), demo=True)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert app.screen.has_class("compact")
            scope = app.query_one(ScopeWidget)
            assert scope.auto_scale
            await pilot.press("a")
            assert not scope.auto_scale
            await pilot.press("up")
            assert scope.manual_gain > 1.0
            await pilot.press("v")
            assert scope.mode == "PERSIST"
            await pilot.press("v")
            assert scope.mode == "MID"
            await pilot.press("s")
            spectrum = app.query_one(SpectrumWidget)
            assert spectrum.mode == "BARS"
            await pilot.press("s")
            assert spectrum.mode == "WATERFALL"
            await pilot.press("s")
            assert spectrum.mode == "CURVE"
            await pilot.press("p")
            assert spectrum.peak_hold_enabled

    asyncio.run(exercise())


def test_mono_source_only_offers_functional_scope_modes():
    scope = ScopeWidget()
    scope.input_channels = 1
    assert scope.next_mode() == "PERSIST"
    assert scope.next_mode() == "RADIAL"
    assert scope.next_mode() == "WAVE"


def test_desktop_app_uses_full_layout():
    async def exercise() -> None:
        app = AquaScopeApp(AudioEngine(), demo=True)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            assert not app.screen.has_class("compact")

    asyncio.run(exercise())
