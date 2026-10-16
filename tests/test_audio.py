from aquascope.audio import AudioEngine, Device


def device(index: int, name: str) -> Device:
    return Device(index, name, 2, 48_000, "test")


def test_loopback_detection():
    assert device(1, "BlackHole 2ch").is_loopback
    assert device(2, "Monitor of Built-in Audio").is_loopback
    assert not device(3, "MacBook Microphone").is_loopback


def test_loopback_is_preferred_without_querying_default(monkeypatch):
    monitor = device(4, "Output Monitor")
    chosen = AudioEngine.choose_default([device(1, "Microphone"), monitor])
    assert chosen == monitor
    assert chosen.source_kind == "SYSTEM"


def test_windows_loopback_names_are_detected():
    assert device(1, "Stereo Mix (Realtek(R) Audio)").is_loopback
    assert device(2, "CABLE Output (VB-Audio Virtual Cable)").is_loopback
    assert device(3, "VoiceMeeter Output (VB-Audio VoiceMeeter VAIO)").is_loopback
    assert not device(4, "Microphone Array (Intel® Smart Sound)").is_loopback


def test_windows_prefers_wasapi_copy_of_loopback_device():
    mme = Device(1, "Stereo Mix (Realtek(R) Audio)", 2, 44_100, "MME")
    wdm = Device(7, "Stereo Mix (Realtek HD Audio Stereo input)", 2, 48_000, "Windows WDM-KS")
    wasapi = Device(12, "Stereo Mix (Realtek(R) Audio)", 2, 48_000, "Windows WASAPI")
    assert AudioEngine.choose_default([mme, wdm, wasapi]) == wasapi


def test_single_host_api_keeps_first_loopback():
    first = Device(2, "Monitor of Speakers", 2, 48_000, "ALSA")
    second = Device(5, "Monitor of HDMI", 2, 48_000, "ALSA")
    assert AudioEngine.choose_default([first, second]) == first
