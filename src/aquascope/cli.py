"""Command-line entry point."""

from __future__ import annotations

import argparse
import os
import platform
import sys

from . import __version__
from .audio import AudioEngine, setup_hint
from .config import config_path, display_path, load_config
from .textual_ui import AquaScopeApp


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="aquascope",
        description="Monochrome aqua oscilloscope and spectrum analyzer.",
    )
    result.add_argument("-d", "--device", type=int, help="PortAudio input device index")
    result.add_argument("--list-devices", action="store_true", help="list audio inputs and exit")
    result.add_argument("--sample-rate", type=int, help="override the device sample rate")
    result.add_argument("--fps", type=int, default=30, choices=range(10, 61), metavar="10-60")
    result.add_argument("--demo", action="store_true", help="run with a built-in reference signal")
    result.add_argument(
        "--layout",
        choices=("auto", "compact", "full"),
        default="auto",
        help="interface layout (default: auto)",
    )
    result.add_argument("--doctor", action="store_true", help="check audio and terminal setup")
    result.add_argument(
        "--credits",
        action="version",
        version=(
            "AquaScope\n"
            "Created by Gabriel Moreno\n"
            "With assistance from Claude.ai Sonnet via Perplexity\n"
            "Licensed under GPL-3.0-or-later"
        ),
        help="show creator and project credits",
    )
    result.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return result


def terminal_name() -> str:
    if os.environ.get("WT_SESSION"):
        return "Windows Terminal"
    return os.environ.get("TERM_PROGRAM") or os.environ.get("TERM") or "unknown"


def doctor() -> int:
    print(f"AquaScope {__version__} diagnostics")
    print(f"  Platform:  {platform.platform()}")
    print(f"  Python:    {platform.python_version()}")
    print(f"  Terminal:  {terminal_name()}")
    print(f"  Color:     {os.environ.get('COLORTERM', 'standard')}")
    print(f"  Config:    {display_path(config_path())}")
    try:
        devices = AudioEngine.devices()
    except Exception as exc:  # noqa: BLE001 - driver errors vary by platform
        print(f"  Audio:     unavailable ({exc})")
        print(f"\n  Fix: {setup_hint()}")
        print("  AquaScope will still open in demo mode.")
        return 1
    loopbacks = [item for item in devices if item.is_loopback]
    print(f"  Audio:     ready ({len(devices)} input device(s))")
    print(f"  Loopback:  {loopbacks[0].name if loopbacks else 'not detected'}")
    if not loopbacks:
        print(f"\n  Tip: {setup_hint()}")
    else:
        print("\n  Ready for system-audio visualization.")
    return 0


def main() -> None:
    args = parser().parse_args()
    if args.doctor:
        raise SystemExit(doctor())
    if args.list_devices:
        try:
            devices = AudioEngine.devices()
        except Exception as exc:
            print(f"Could not query audio devices: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        if not devices:
            print("No input-capable audio devices found.")
            print(setup_hint())
            return
        default = AudioEngine.choose_default(devices)
        for device in devices:
            marker = "*" if default and device.index == default.index else " "
            print(f"{marker} {device.display_name} · {device.host_api}")
        print("\n* automatic selection")
        return

    config = load_config()
    engine = AudioEngine(
        device=args.device,
        sample_rate=args.sample_rate,
        preferred_name=config.get("device_name"),
    )
    AquaScopeApp(engine, fps=args.fps, demo=args.demo, layout=args.layout).run()


if __name__ == "__main__":
    main()
