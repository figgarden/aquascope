"""Signal analysis used by the live display."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

import numpy as np
from numpy.typing import NDArray

EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class AudioMetrics:
    peak_dbfs: float
    rms_dbfs: float
    left_peak_dbfs: float
    right_peak_dbfs: float
    left_rms_dbfs: float
    right_rms_dbfs: float
    crest_db: float
    dominant_hz: float
    centroid_hz: float
    stereo_balance: float
    correlation: float
    clipped_samples: int


@dataclass(frozen=True, slots=True)
class Analysis:
    waveform: NDArray[np.float32]
    channels: NDArray[np.float32]
    spectrum: NDArray[np.float32]
    frequencies: NDArray[np.float64]
    metrics: AudioMetrics


def dbfs(value: float) -> float:
    """Convert a linear full-scale amplitude to dBFS with a useful floor."""
    return max(-120.0, 20.0 * np.log10(max(abs(value), EPSILON)))


def analyze(
    frames: NDArray[np.float32],
    sample_rate: float,
    fft_size: int = 4096,
) -> Analysis:
    """Analyze interleaved audio frames and return display-ready data."""
    data = np.asarray(frames, dtype=np.float32)
    if data.ndim == 1:
        data = data[:, None]
    if data.size == 0:
        data = np.zeros((fft_size, 1), dtype=np.float32)

    mono = np.mean(data, axis=1)
    peak = float(np.max(np.abs(mono)))
    rms = float(np.sqrt(np.mean(np.square(mono, dtype=np.float64))))
    crest = dbfs(peak) - dbfs(rms) if rms > EPSILON else 0.0

    n = min(fft_size, len(mono))
    fft_input = np.zeros(fft_size, dtype=np.float64)
    if n:
        segment = mono[-n:].astype(np.float64)
        segment -= np.mean(segment)
        fft_input[-n:] = segment * np.hanning(n)

    magnitudes = np.abs(np.fft.rfft(fft_input))
    frequencies = np.fft.rfftfreq(fft_size, 1.0 / sample_rate)
    if len(magnitudes) > 1:
        magnitudes[0] = 0.0
        dominant_hz = float(frequencies[int(np.argmax(magnitudes))])
        centroid_hz = float(np.sum(frequencies * magnitudes) / max(np.sum(magnitudes), EPSILON))
    else:
        dominant_hz = centroid_hz = 0.0

    window_gain = max(float(np.sum(np.hanning(n))), EPSILON)
    amplitude = 2.0 * magnitudes / window_gain
    spectrum_db = 20.0 * np.log10(np.maximum(amplitude, EPSILON))
    spectrum = np.clip((spectrum_db + 90.0) / 90.0, 0.0, 1.0).astype(np.float32)

    if data.shape[1] >= 2:
        left, right = data[:, 0], data[:, 1]
        left_peak = float(np.max(np.abs(left)))
        right_peak = float(np.max(np.abs(right)))
        left_rms = float(np.sqrt(np.mean(np.square(left, dtype=np.float64))))
        right_rms = float(np.sqrt(np.mean(np.square(right, dtype=np.float64))))
        balance = (right_rms - left_rms) / max(right_rms + left_rms, EPSILON)
        if np.std(left) > EPSILON and np.std(right) > EPSILON:
            correlation = float(np.corrcoef(left, right)[0, 1])
        else:
            correlation = 1.0
    else:
        left_peak = right_peak = float(np.max(np.abs(data[:, 0])))
        left_rms = right_rms = float(
            np.sqrt(np.mean(np.square(data[:, 0], dtype=np.float64)))
        )
        balance, correlation = 0.0, 1.0

    metrics = AudioMetrics(
        peak_dbfs=dbfs(peak),
        rms_dbfs=dbfs(rms),
        left_peak_dbfs=dbfs(left_peak),
        right_peak_dbfs=dbfs(right_peak),
        left_rms_dbfs=dbfs(left_rms),
        right_rms_dbfs=dbfs(right_rms),
        crest_db=crest,
        dominant_hz=dominant_hz,
        centroid_hz=centroid_hz,
        stereo_balance=float(np.clip(balance, -1.0, 1.0)),
        correlation=float(np.clip(correlation, -1.0, 1.0)),
        clipped_samples=int(np.count_nonzero(np.abs(data) >= 0.999)),
    )
    return Analysis(mono.astype(np.float32), data[:, :2].copy(), spectrum, frequencies, metrics)


def logarithmic_bands(
    spectrum: NDArray[np.float32],
    frequencies: NDArray[np.float64],
    count: int,
    low_hz: float = 30.0,
    high_hz: float = 20_000.0,
) -> NDArray[np.float32]:
    """Reduce an FFT to logarithmically spaced display bands."""
    if count <= 0:
        return np.empty(0, dtype=np.float32)
    high_hz = min(high_hz, float(frequencies[-1]) if len(frequencies) else high_hz)
    if high_hz <= low_hz:
        return np.zeros(count, dtype=np.float32)
    edges = np.geomspace(low_hz, high_hz, count + 1)
    bands = np.zeros(count, dtype=np.float32)
    for index, (start, stop) in enumerate(pairwise(edges)):
        mask = (frequencies >= start) & (frequencies < stop)
        center = float(np.sqrt(start * stop))
        interpolated = float(np.interp(center, frequencies, spectrum))
        if np.any(mask):
            bands[index] = max(float(np.max(spectrum[mask])), interpolated)
        else:
            # At low frequencies a display band may be narrower than one FFT
            # bin. Interpolation prevents visible holes in the analyzer.
            bands[index] = interpolated
    return bands
