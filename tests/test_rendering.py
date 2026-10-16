import numpy as np

from aquascope.textual_ui import (
    braille_radial,
    braille_vectorscope,
    braille_waveform,
    persistence_trace,
    radial_scope,
    spectrum_chart,
    spectrum_curve_chart,
    spectrum_rows,
    waterfall_chart,
)


def test_braille_waveform_dimensions_and_resolution():
    samples = np.sin(np.linspace(0, 4 * np.pi, 1000))
    rows = braille_waveform(samples, width=40, height=8)
    assert len(rows) == 8
    assert all(len(row) == 40 for row in rows)
    assert any("\u2800" <= character <= "\u28ff" for row in rows for character in row)


def test_braille_waveform_handles_empty_input():
    rows = braille_waveform(np.array([]), width=10, height=3)
    assert len(rows) == 3
    assert all(len(row) == 10 for row in rows)


def test_spectrum_uses_partial_blocks():
    rows = spectrum_rows(np.array([0.05, 0.5, 1.0]), width=3, height=4)
    assert len(rows) == 4
    assert all(len(row) == 3 for row in rows)
    assert rows[-1][-1] == "█"


def test_complete_spectrum_has_axes_grid_and_peak_trace():
    values = np.linspace(0.1, 0.9, 40)
    chart = spectrum_chart(values, values + 0.08, width=64, height=10, show_peaks=True)
    plain = chart.plain
    assert "-90" in plain
    assert "1k" in plain
    assert "16k" in plain
    assert "•" in plain
    assert "─" in plain


def test_peak_hold_is_hidden_by_default():
    values = np.linspace(0.1, 0.9, 40)
    chart = spectrum_chart(values, values + 0.08, width=64, height=10)
    assert "•" not in chart.plain


def test_smooth_spectrum_curve_has_axes_and_braille_trace():
    values = np.linspace(0.2, 0.8, 40)
    chart = spectrum_curve_chart(values, values, width=64, height=10)
    plain = chart.plain
    assert "-90" in plain
    assert "30" in plain
    assert "16k" in plain
    assert any("\u2800" <= character <= "\u28ff" for character in plain)


def test_vectorscope_renders_stereo_signal():
    t = np.linspace(0, 2 * np.pi, 1000)
    stereo = np.column_stack((np.sin(t), np.sin(t + 0.5)))
    rows = braille_vectorscope(stereo, width=30, height=10)
    assert len(rows) == 10
    assert any("\u2800" <= character <= "\u28ff" for row in rows for character in row)


def test_radial_waveform_fills_requested_canvas():
    signal = np.sin(np.linspace(0, 8 * np.pi, 1000))
    rows = braille_radial(signal, np.array([0.7, 0.4, 0.2]), 40, 12)
    assert len(rows) == 12
    assert all(len(row) == 40 for row in rows)
    assert any("\u2800" <= character <= "\u28ff" for row in rows for character in row)


def test_polar_scope_includes_trace_and_graticule():
    signal = np.sin(np.linspace(0, 8 * np.pi, 1000))
    rendered = radial_scope(signal, np.array([0.7, 0.4, 0.2]), 40, 12)
    assert len(rendered.plain.splitlines()) == 12
    assert len(rendered.spans) > 1


def test_persistence_distinguishes_live_and_previous_traces():
    first = np.sin(np.linspace(0, 4 * np.pi, 500)) * 0.5
    second = np.sin(np.linspace(0, 4 * np.pi, 500) + 0.8) * 0.5
    rendered = persistence_trace([first, second], width=40, height=8)
    assert len(rendered.plain.splitlines()) == 8
    assert len(rendered.spans) > 1


def test_waterfall_fills_requested_canvas():
    history = [np.linspace(0, 1, 20) for _ in range(4)]
    rendered = waterfall_chart(history, width=20, height=6)
    lines = rendered.plain.splitlines()
    assert len(lines) == 6
    assert all(len(line) == 20 for line in lines)
