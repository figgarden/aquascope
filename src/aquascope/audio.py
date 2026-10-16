"""Cross-platform PortAudio capture and a thread-safe rolling buffer."""

from __future__ import annotations

import platform
import threading
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

LOOPBACK_KEYWORDS = (
    "monitor",  # PipeWire / PulseAudio
    "loopback",  # ALSA snd-aloop, Rogue Amoeba Loopback
    "blackhole",  # macOS
    "soundflower",  # macOS (legacy)
    "stereo mix",  # Windows, plus a few localized spellings
    "stereomix",
    "mixage stéréo",
    "mezcla estéreo",
    "what u hear",  # Creative Sound Blaster
    "cable output",  # VB-Audio Virtual Cable (Windows / macOS)
    "voicemeeter",  # VB-Audio VoiceMeeter
)

# Windows lists every device once per host API. WASAPI is the most accurate;
# MME is the most forgiving fallback. Other platforms have a single API.
HOST_API_PREFERENCE = ("Windows WASAPI", "MME", "Windows DirectSound")


@dataclass(frozen=True, slots=True)
class Device:
    index: int
    name: str
    channels: int
    sample_rate: int
    host_api: str

    @property
    def display_name(self) -> str:
        return f"{self.index:>2}  {self.name}  [{self.channels}ch · {self.sample_rate} Hz]"

    @property
    def is_loopback(self) -> bool:
        name = self.name.casefold()
        return any(word in name for word in LOOPBACK_KEYWORDS)

    @property
    def host_api_rank(self) -> int:
        try:
            return HOST_API_PREFERENCE.index(self.host_api)
        except ValueError:
            return len(HOST_API_PREFERENCE)

    @property
    def source_kind(self) -> str:
        return "SYSTEM" if self.is_loopback else "INPUT"


class AudioEngine:
    """Capture input audio into a bounded circular-style buffer."""

    def __init__(
        self,
        device: int | None = None,
        sample_rate: int | None = None,
        preferred_name: str | None = None,
    ) -> None:
        self.requested_device = device
        self.requested_sample_rate = sample_rate
        self.preferred_name = preferred_name
        self.device: Device | None = None
        self.stream: Any = None
        self.status = "idle"
        self.last_error = ""
        self._lock = threading.Lock()
        self._buffer = np.zeros((16384, 2), dtype=np.float32)
        self._channels = 2

    @staticmethod
    def devices() -> list[Device]:
        import sounddevice as sd

        raw_devices = sd.query_devices()
        host_apis = sd.query_hostapis()
        result = []
        for index, item in enumerate(raw_devices):
            channels = int(item["max_input_channels"])
            if channels <= 0:
                continue
            api_name = str(host_apis[item["hostapi"]]["name"])
            result.append(
                Device(
                    index=index,
                    name=str(item["name"]),
                    channels=channels,
                    sample_rate=int(item["default_samplerate"]),
                    host_api=api_name,
                )
            )
        return result

    @classmethod
    def choose_default(cls, devices: list[Device]) -> Device | None:
        """Prefer virtual monitor devices, then the default input."""
        if not devices:
            return None
        loopbacks = [device for device in devices if device.is_loopback]
        if loopbacks:
            return min(loopbacks, key=lambda device: device.host_api_rank)
        try:
            import sounddevice as sd

            default_input = int(sd.default.device[0])
            return next((item for item in devices if item.index == default_input), devices[0])
        except Exception:  # noqa: BLE001 - audio backends expose inconsistent exception types
            return devices[0]

    def start(self) -> None:
        import sounddevice as sd

        devices = self.devices()
        selected = (
            next((item for item in devices if item.index == self.requested_device), None)
            if self.requested_device is not None
            else next(
                (
                    item
                    for item in devices
                    if self.preferred_name
                    and item.name.casefold() == self.preferred_name.casefold()
                ),
                None,
            )
        )
        selected = selected or self.choose_default(devices)
        if selected is None:
            raise RuntimeError("No input-capable audio device was found.")
        self.device = selected
        self._channels = min(2, selected.channels)
        sample_rate = self.requested_sample_rate or selected.sample_rate

        def callback(indata: NDArray[np.float32], frames: int, time: Any, status: Any) -> None:
            del frames, time
            if status:
                self.last_error = str(status)
            block = np.asarray(indata, dtype=np.float32)
            with self._lock:
                if block.shape[1] == 1:
                    block = np.repeat(block, 2, axis=1)
                length = min(len(block), len(self._buffer))
                self._buffer = np.roll(self._buffer, -length, axis=0)
                self._buffer[-length:] = block[-length:, :2]

        self.stream = sd.InputStream(
            device=selected.index,
            channels=self._channels,
            samplerate=sample_rate,
            dtype="float32",
            blocksize=1024,
            latency="low",
            callback=callback,
        )
        self.stream.start()
        self.status = "listening"

    def snapshot(self, frames: int = 8192) -> NDArray[np.float32]:
        with self._lock:
            return self._buffer[-frames:].copy()

    @property
    def sample_rate(self) -> float:
        return float(self.stream.samplerate) if self.stream is not None else 48_000.0

    @property
    def latency_ms(self) -> float:
        if self.stream is None:
            return 0.0
        latency = self.stream.latency
        return float(max(latency) if isinstance(latency, tuple) else latency) * 1000.0

    def close(self) -> None:
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.status = "stopped"


def setup_hint() -> str:
    system = platform.system()
    if system == "Darwin":
        return "Install BlackHole 2ch, then create a Multi-Output Device in Audio MIDI Setup."
    if system == "Linux":
        return "Select a PipeWire/PulseAudio device whose name contains 'Monitor'."
    if system == "Windows":
        return (
            "Enable 'Stereo Mix' under Sound settings > Recording, "
            "or install VB-Audio Virtual Cable."
        )
    return "Choose a loopback or stereo-mix input device."
