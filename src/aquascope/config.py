"""Small, failure-tolerant user configuration.

The only thing AquaScope ever stores is the name of the last audio device you
picked, in a local JSON file. Nothing is sent anywhere.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def config_path() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return root / "aquascope" / "config.json"


def display_path(path: Path) -> str:
    """Show a path with the home directory collapsed to ``~``.

    Keeps the local username out of diagnostics people paste into bug reports.
    """
    try:
        return str(Path("~") / path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def load_config() -> dict[str, Any]:
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_config(data: dict[str, Any]) -> None:
    path = config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    except OSError:
        # A read-only home directory should never stop the visualizer.
        return
