import sys
from pathlib import Path

from aquascope import config


def test_config_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "aquascope" / "config.json")
    config.save_config({"device_name": "BlackHole 2ch"})
    assert config.load_config() == {"device_name": "BlackHole 2ch"}


def test_corrupt_config_is_ignored(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(config, "config_path", lambda: path)
    assert config.load_config() == {}


def test_config_path_uses_platform_location(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    expected = "appdata" if sys.platform == "win32" else "xdg"
    assert config.config_path() == tmp_path / expected / "aquascope" / "config.json"


def test_display_path_hides_home_directory():
    shown = config.display_path(Path.home() / "secret-user-dir" / "config.json")
    assert shown.startswith("~")
    assert str(Path.home()) not in shown
