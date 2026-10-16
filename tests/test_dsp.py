import numpy as np

from aquascope.dsp import analyze, dbfs, logarithmic_bands


def sine(frequency: float, sample_rate: int = 48_000, seconds: float = 0.25):
    t = np.arange(int(sample_rate * seconds)) / sample_rate
    signal = 0.5 * np.sin(2 * np.pi * frequency * t)
    return np.column_stack((signal, signal)).astype(np.float32)


def test_dbfs_reference_values():
    assert dbfs(1.0) == 0.0
    assert -6.1 < dbfs(0.5) < -6.0
    assert dbfs(0.0) == -120.0


def test_detects_dominant_frequency():
    result = analyze(sine(1_000), 48_000)
    assert abs(result.metrics.dominant_hz - 1_000) < 15
    assert -6.2 < result.metrics.peak_dbfs < -5.9
    assert result.metrics.correlation > 0.99


def test_stereo_balance_points_right():
    frames = sine(440)
    frames[:, 0] *= 0.1
    result = analyze(frames, 48_000)
    assert result.metrics.stereo_balance > 0.7


def test_log_bands_have_requested_width():
    result = analyze(sine(440), 48_000)
    bands = logarithmic_bands(result.spectrum, result.frequencies, 80)
    assert bands.shape == (80,)
    assert np.max(bands) > 0.9


def test_log_bands_interpolate_narrow_low_frequency_bands():
    frequencies = np.linspace(0, 24_000, 2049)
    spectrum = np.ones(2049, dtype=np.float32) * 0.5
    bands = logarithmic_bands(spectrum, frequencies, 120)
    assert np.all(bands > 0)


def test_silence_is_stable():
    result = analyze(np.zeros((2048, 2), dtype=np.float32), 48_000)
    assert result.metrics.rms_dbfs == -120.0
    assert result.metrics.clipped_samples == 0
    assert np.all(np.isfinite(result.spectrum))
