"""Textual interface with high-resolution Braille signal rendering."""

from __future__ import annotations

import math
import time
from collections.abc import Iterable
from typing import ClassVar

import numpy as np
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import Label, ListItem, ListView, Static

from . import __version__
from .audio import AudioEngine, Device, setup_hint
from .config import save_config
from .dsp import Analysis, analyze, logarithmic_bands

AQUA = "#58f5e7"
AQUA_DIM = "#248f88"
INK = "#071211"
PANEL = "#091918"
SPECTRUM_GRADIENT = ("#17605c", "#207f79", "#2ba39a", "#3acabe", "#58f5e7", "#9afff7")

BRAILLE_BITS = (
    (0x01, 0x08),
    (0x02, 0x10),
    (0x04, 0x20),
    (0x40, 0x80),
)
BLOCKS = " ▁▂▃▄▅▆▇█"


def braille_waveform(samples: np.ndarray, width: int, height: int) -> list[str]:
    """Render samples to a 2x4-dot-per-cell Braille canvas."""
    if width <= 0 or height <= 0:
        return []
    pixels_w, pixels_h = width * 2, height * 4
    canvas = np.zeros((height, width), dtype=np.uint8)
    signal = np.asarray(samples, dtype=np.float64)
    if signal.size == 0:
        signal = np.zeros(pixels_w)
    indexes = np.linspace(0, len(signal) - 1, pixels_w).astype(int)
    values = np.clip(signal[indexes], -1.0, 1.0)
    ys = np.rint((1.0 - values) * 0.5 * (pixels_h - 1)).astype(int)

    def light(px: int, py: int) -> None:
        if 0 <= px < pixels_w and 0 <= py < pixels_h:
            canvas[py // 4, px // 2] |= BRAILLE_BITS[py % 4][px % 2]

    previous_y = int(ys[0])
    for px, y_value in enumerate(ys):
        y = int(y_value)
        for py in range(min(previous_y, y), max(previous_y, y) + 1):
            light(px, py)
        previous_y = y

    return [
        "".join(chr(0x2800 + int(bits)) if bits else " " for bits in row)
        for row in canvas
    ]


def braille_vectorscope(channels: np.ndarray, width: int, height: int) -> list[str]:
    """Render a stereo goniometer with mono vertical and side horizontal."""
    if width <= 0 or height <= 0:
        return []
    pixels_w, pixels_h = width * 2, height * 4
    canvas = np.zeros((height, width), dtype=np.uint8)
    data = np.asarray(channels, dtype=np.float64)
    if data.ndim != 2 or data.shape[1] < 2 or len(data) == 0:
        data = np.zeros((1, 2))
    indexes = np.linspace(0, len(data) - 1, min(len(data), pixels_w * 3)).astype(int)
    left, right = data[indexes, 0], data[indexes, 1]
    mid = (left + right) / math.sqrt(2.0)
    side = (left - right) / math.sqrt(2.0)
    scale = max(float(np.max(np.abs(np.concatenate((mid, side))))), 1e-4)
    x_values = np.rint((side / scale * 0.46 + 0.5) * (pixels_w - 1)).astype(int)
    y_values = np.rint((0.5 - mid / scale * 0.46) * (pixels_h - 1)).astype(int)
    for px, py in zip(x_values, y_values, strict=True):
        if 0 <= px < pixels_w and 0 <= py < pixels_h:
            canvas[py // 4, px // 2] |= BRAILLE_BITS[py % 4][px % 2]
    return [
        "".join(chr(0x2800 + int(bits)) if bits else " " for bits in row)
        for row in canvas
    ]


def _draw_segment(
    canvas: np.ndarray, x0: float, y0: float, x1: float, y1: float
) -> None:
    """Draw a clipped line segment onto a Braille-dot canvas."""
    height, width = canvas.shape
    pixels_w, pixels_h = width * 2, height * 4
    steps = max(1, int(max(abs(x1 - x0), abs(y1 - y0))))
    for step in range(steps + 1):
        amount = step / steps
        px = round(x0 + (x1 - x0) * amount)
        py = round(y0 + (y1 - y0) * amount)
        if 0 <= px < pixels_w and 0 <= py < pixels_h:
            canvas[py // 4, px // 2] |= BRAILLE_BITS[py % 4][px % 2]


def _canvas_lines(canvas: np.ndarray) -> list[str]:
    return [
        "".join(chr(0x2800 + int(bits)) if bits else " " for bits in row)
        for row in canvas
    ]


def braille_radial(
    samples: np.ndarray,
    drive: np.ndarray,
    width: int,
    height: int,
) -> list[str]:
    """Render a polar oscilloscope where waveform amplitude controls radius."""
    if width <= 0 or height <= 0:
        return []
    pixels_w, pixels_h = width * 2, height * 4
    canvas = np.zeros((height, width), dtype=np.uint8)
    signal = np.asarray(samples, dtype=np.float64)
    if signal.size == 0:
        signal = np.zeros(256)
    indexes = np.linspace(0, len(signal) - 1, max(128, pixels_w * 2)).astype(int)
    signal = signal[indexes]
    peak = max(float(np.max(np.abs(signal))), 1e-4)
    signal = np.clip(signal / peak, -1.0, 1.0)
    energy = np.pad(np.asarray(drive, dtype=np.float64), (0, 3))[:3]
    _, _, highs = np.clip(energy, 0.0, 1.0)
    angles = np.linspace(0.0, 2.0 * math.pi, len(signal), endpoint=False)
    base = min(pixels_w, pixels_h) * 0.30
    radius = base * (1.0 + signal * (0.38 + highs * 0.10))
    radius = np.clip(radius, base * 0.48, base * 1.52)
    center_x, center_y = (pixels_w - 1) / 2, (pixels_h - 1) / 2
    x_values = center_x + radius * np.cos(angles)
    y_values = center_y + radius * np.sin(angles)
    for index in range(len(signal)):
        following = (index + 1) % len(signal)
        _draw_segment(
            canvas,
            x_values[index],
            y_values[index],
            x_values[following],
            y_values[following],
        )
    return _canvas_lines(canvas)


def radial_scope(
    samples: np.ndarray,
    drive: np.ndarray,
    width: int,
    height: int,
) -> Text:
    """Render a polar waveform over a dim amplitude graticule."""
    if width <= 0 or height <= 0:
        return Text()
    pixels_w, pixels_h = width * 2, height * 4
    grid = np.zeros((height, width), dtype=np.uint8)
    center_x, center_y = (pixels_w - 1) / 2, (pixels_h - 1) / 2
    radius = min(pixels_w, pixels_h) * 0.30
    _draw_segment(grid, center_x - radius * 1.55, center_y, center_x + radius * 1.55, center_y)
    _draw_segment(grid, center_x, center_y - radius * 1.55, center_x, center_y + radius * 1.55)
    for scale in (0.5, 1.0):
        points = 160
        ring = radius * scale
        for index in range(points):
            angle = index * 2.0 * math.pi / points
            following = (index + 1) * 2.0 * math.pi / points
            _draw_segment(
                grid,
                center_x + math.cos(angle) * ring,
                center_y + math.sin(angle) * ring,
                center_x + math.cos(following) * ring,
                center_y + math.sin(following) * ring,
            )
    trace = braille_radial(samples, drive, width, height)
    result = Text()
    for row in range(height):
        for column in range(width):
            trace_bits = ord(trace[row][column]) - 0x2800 if trace[row][column] != " " else 0
            bits = int(grid[row, column]) | trace_bits
            if trace_bits:
                result.append(chr(0x2800 + bits), style=f"bold {AQUA}")
            elif bits:
                result.append(chr(0x2800 + bits), style="#174642")
            else:
                result.append(" ")
        if row < height - 1:
            result.append("\n")
    return result


def persistence_trace(history: list[np.ndarray], width: int, height: int) -> Text:
    """Overlay recent waveforms with a bright live trace and dim persistence."""
    if width <= 0 or height <= 0:
        return Text()
    frames = history[-5:] or [np.zeros(1)]
    old = np.zeros((height, width), dtype=np.uint8)
    for frame in frames[:-1]:
        for row, line in enumerate(braille_waveform(frame, width, height)):
            for column, character in enumerate(line):
                if character != " ":
                    old[row, column] |= ord(character) - 0x2800
    current = braille_waveform(frames[-1], width, height)
    result = Text()
    for row in range(height):
        for column in range(width):
            current_bits = ord(current[row][column]) - 0x2800 if current[row][column] != " " else 0
            bits = int(old[row, column]) | current_bits
            if current_bits:
                result.append(chr(0x2800 + bits), style=f"bold {AQUA}")
            elif bits:
                result.append(chr(0x2800 + bits), style=AQUA_DIM)
            else:
                result.append(" ")
        if row < height - 1:
            result.append("\n")
    return result


def spectrum_rows(values: np.ndarray, width: int, height: int) -> list[str]:
    """Render a spectrum with one-eighth-cell vertical resolution."""
    if width <= 0 or height <= 0:
        return []
    source = np.asarray(values, dtype=np.float64)
    if source.size == 0:
        source = np.zeros(width)
    indexes = np.linspace(0, len(source) - 1, width).astype(int)
    units = np.rint(np.clip(source[indexes], 0.0, 1.0) * height * 8).astype(int)
    rows: list[str] = []
    for row in range(height):
        rows_below = height - row - 1
        glyphs = []
        for value in units:
            fill = int(np.clip(value - rows_below * 8, 0, 8))
            glyphs.append(BLOCKS[fill])
        rows.append("".join(glyphs))
    return rows


class ScopeWidget(Static):
    """High-resolution oscilloscope widget."""

    def __init__(self) -> None:
        super().__init__(id="scope")
        self.samples = np.zeros(256, dtype=np.float32)
        self.channels = np.zeros((256, 2), dtype=np.float32)
        self.auto_scale = True
        self.manual_gain = 1.0
        self.scope_scale = 1.0
        self.mode = "WAVE"
        self.input_channels = 1
        self.trace_history: list[np.ndarray] = []
        self.spectral_drive = np.zeros(3, dtype=np.float64)
        self.radial_samples = self.samples

    def set_analysis(self, analysis: Analysis, input_channels: int) -> None:
        self.samples = analysis.waveform
        self.channels = analysis.channels
        self.input_channels = input_channels
        self.trace_history.append(analysis.waveform.copy())
        if len(self.trace_history) > 5:
            self.trace_history.pop(0)
        regions = ((30, 180), (180, 2_000), (2_000, 16_000))
        drive = np.array(
            [
                np.mean(analysis.spectrum[(analysis.frequencies >= low) & (analysis.frequencies < high)])
                if np.any((analysis.frequencies >= low) & (analysis.frequencies < high))
                else 0.0
                for low, high in regions
            ]
        )
        drive = np.clip((drive - 0.12) / 0.78, 0.0, 1.0)
        self.spectral_drive = 0.86 * self.spectral_drive + 0.14 * drive
        sample_rate = float(analysis.frequencies[-1] * 2.0)
        fundamental = max(analysis.metrics.dominant_hz, 20.0)
        radial_window = int(np.clip(sample_rate / fundamental * 5.0, 192, 2_048))
        self.radial_samples = analysis.waveform[-radial_window:]
        if self.mode not in self._available_modes():
            self.mode = "WAVE"
            self.border_title = "OSCILLOSCOPE  |  WAVE"
        self.refresh()

    def next_mode(self) -> str:
        modes = self._available_modes()
        self.mode = modes[(modes.index(self.mode) + 1) % len(modes)]
        self.border_title = f"OSCILLOSCOPE  |  {self.mode}"
        self.refresh()
        return self.mode

    def on_click(self, event: events.Click) -> None:
        """Let mouse and touch users cycle the instrument view."""
        event.stop()
        mode = self.next_mode()
        self.app.notify(f"Scope: {mode}", timeout=2)

    def _available_modes(self) -> tuple[str, ...]:
        return (
            ("WAVE", "PERSIST", "MID", "SIDE", "VECTOR", "RADIAL")
            if self.input_channels >= 2
            else ("WAVE", "PERSIST", "RADIAL")
        )

    def render(self) -> Text:
        width = max(1, self.content_size.width)
        height = max(1, self.content_size.height)
        if self.mode == "VECTOR":
            lines = braille_vectorscope(self.channels, width, height)
            result = Text()
            for index, line in enumerate(lines):
                result.append(line, style=f"bold {AQUA}")
                if index < len(lines) - 1:
                    result.append("\n")
            return result

        if self.mode == "RADIAL":
            return radial_scope(
                self.radial_samples, self.spectral_drive, width, height
            )

        if self.channels.shape[1] >= 2 and self.mode in ("MID", "SIDE"):
            left, right = self.channels[:, 0], self.channels[:, 1]
            source = (left + right) * 0.5 if self.mode == "MID" else (left - right) * 0.5
        else:
            source = self.samples
        waveform = self._trigger(source, width * 12)
        peak = max(float(np.max(np.abs(waveform))), 1e-4)
        target = min(32.0, 0.86 / peak)
        if self.auto_scale:
            self.scope_scale = 0.90 * self.scope_scale + 0.10 * target
            gain = self.scope_scale
        else:
            gain = self.manual_gain
        if self.mode == "PERSIST":
            traces = [
                self._trigger(frame, width * 12) * gain for frame in self.trace_history
            ]
            return persistence_trace(traces, width, height)
        lines = braille_waveform(waveform * gain, width, height)
        result = Text()
        for index, line in enumerate(lines):
            result.append(line, style=f"bold {AQUA}")
            if index < len(lines) - 1:
                result.append("\n")
        return result

    @staticmethod
    def _trigger(waveform: np.ndarray, window_size: int) -> np.ndarray:
        if len(waveform) <= window_size:
            return waveform
        search = waveform[-min(len(waveform), window_size * 3) :]
        crossings = np.flatnonzero((search[:-1] <= 0.0) & (search[1:] > 0.0)) + 1
        valid = crossings[crossings + window_size <= len(search)]
        start = int(valid[-1]) if len(valid) else len(search) - window_size
        return search[start : start + window_size]


class SpectrumWidget(Static):
    """Smooth dBFS spectrum using partial-height block cells."""

    def __init__(self) -> None:
        super().__init__(id="spectrum")
        self.values = np.empty(0, dtype=np.float32)
        self.display_values = np.empty(0, dtype=np.float32)
        self.peak_values = np.empty(0, dtype=np.float32)
        self.history: list[np.ndarray] = []
        self.mode = "CURVE"
        self.peak_hold_enabled = False

    def set_values(self, values: np.ndarray) -> None:
        self.values = values
        if self.display_values.shape != values.shape:
            self.display_values = values.copy()
            self.peak_values = values.copy()
        else:
            rising = values > self.display_values
            self.display_values[rising] = (
                0.55 * self.display_values[rising] + 0.45 * values[rising]
            )
            self.display_values[~rising] = np.maximum(
                values[~rising], self.display_values[~rising] - 0.025
            )
            self.peak_values = np.maximum(values, self.peak_values - 0.014)
        self.history.append(values.copy())
        if len(self.history) > 120:
            self.history.pop(0)
        self.refresh()

    def next_mode(self) -> str:
        modes = ("CURVE", "BARS", "WATERFALL")
        self.mode = modes[(modes.index(self.mode) + 1) % len(modes)]
        self._update_title()
        self.refresh()
        return self.mode

    def on_click(self, event: events.Click) -> None:
        """Cycle analyzer modes directly from the graph panel."""
        event.stop()
        mode = self.next_mode()
        self.app.notify(f"Analyzer: {mode}", timeout=2)

    def toggle_peak_hold(self) -> bool:
        self.peak_hold_enabled = not self.peak_hold_enabled
        if self.peak_hold_enabled:
            self.peak_values = self.display_values.copy()
        self._update_title()
        self.refresh()
        return self.peak_hold_enabled

    def _update_title(self) -> None:
        if self.mode == "WATERFALL":
            self.border_title = "SPECTRUM  |  WATERFALL"
        else:
            suffix = "  |  PEAK HOLD" if self.peak_hold_enabled else ""
            name = "FFT TRACE" if self.mode == "CURVE" else "RTA BARS"
            window = "  |  HANN" if self.mode == "CURVE" else ""
            self.border_title = f"{name}  |  LOG Hz / dBFS{window}{suffix}"

    def render(self) -> Text:
        width = max(1, self.content_size.width)
        height = max(1, self.content_size.height)
        if self.mode == "WATERFALL":
            return waterfall_chart(self.history, width, height)
        if self.mode == "CURVE":
            return spectrum_curve_chart(
                self.display_values,
                self.peak_values,
                width,
                height,
                show_peaks=self.peak_hold_enabled,
            )
        return spectrum_chart(
            self.display_values,
            self.peak_values,
            width,
            height,
            show_peaks=self.peak_hold_enabled,
        )


def spectrum_chart(
    values: np.ndarray,
    peaks: np.ndarray,
    width: int,
    height: int,
    show_peaks: bool = False,
) -> Text:
    """Render a complete log-frequency analyzer with axes, grid, and peak trace."""
    result = Text()
    if width < 12 or height < 3:
        for index, line in enumerate(spectrum_rows(values, width, height)):
            result.append(line, style=AQUA)
            if index < height - 1:
                result.append("\n")
        return result

    axis_width = 5
    plot_width = width - axis_width
    plot_height = height - 1
    source = np.asarray(values, dtype=np.float64)
    peak_source = np.asarray(peaks, dtype=np.float64)
    if source.size == 0:
        source = np.zeros(plot_width)
    if peak_source.size == 0:
        peak_source = source
    indexes = np.linspace(0, len(source) - 1, plot_width).astype(int)
    levels = np.rint(np.clip(source[indexes], 0.0, 1.0) * plot_height * 8).astype(int)
    peak_levels = np.clip(peak_source[indexes], 0.0, 1.0)

    grid_rows = {
        0: "  0 ",
        round((plot_height - 1) / 3): "-30 ",
        round(2 * (plot_height - 1) / 3): "-60 ",
        plot_height - 1: "-90 ",
    }
    frequency_ticks = (
        (31.5, "31"),
        (63, "63"),
        (125, "125"),
        (250, "250"),
        (500, "500"),
        (1000, "1k"),
        (2000, "2k"),
        (4000, "4k"),
        (8000, "8k"),
        (16_000, "16k"),
    )
    tick_positions = {
        min(
            plot_width - 1,
            max(0, round(math.log(frequency / 30) / math.log(20_000 / 30) * (plot_width - 1))),
        ): label
        for frequency, label in frequency_ticks
    }

    for row in range(plot_height):
        label = grid_rows.get(row, "    ")
        result.append(label.ljust(axis_width), style=AQUA_DIM)
        for column, units in enumerate(levels):
            rows_below = plot_height - row - 1
            fill = int(np.clip(units - rows_below * 8, 0, 8))
            peak_row = round((1.0 - peak_levels[column]) * (plot_height - 1))
            separation = peak_levels[column] - float(units) / (plot_height * 8)
            is_local_peak = (
                column == 0
                or column == plot_width - 1
                or peak_levels[column] >= peak_levels[column - 1]
                and peak_levels[column] >= peak_levels[column + 1]
            )
            if (
                show_peaks
                and peak_levels[column] > 0.16
                and separation > 0.035
                and is_local_peak
                and row == peak_row
            ):
                result.append("•", style=f"bold {SPECTRUM_GRADIENT[-1]}")
            elif fill:
                gradient_position = 1.0 - row / max(1, plot_height - 1)
                color_index = min(
                    len(SPECTRUM_GRADIENT) - 1,
                    int(gradient_position * len(SPECTRUM_GRADIENT)),
                )
                result.append(BLOCKS[fill], style=f"bold {SPECTRUM_GRADIENT[color_index]}")
            elif row in grid_rows:
                result.append("─", style="#174642")
            elif column in tick_positions:
                result.append("┊", style="#123b38")
            else:
                result.append(" ")
        result.append("\n")

    axis = [" "] * width
    for position, label in tick_positions.items():
        start = min(width - len(label), axis_width + position - len(label) // 2)
        for offset, character in enumerate(label):
            axis[start + offset] = character
    result.append("".join(axis), style=AQUA_DIM)
    return result


def spectrum_curve_chart(
    values: np.ndarray,
    peaks: np.ndarray,
    width: int,
    height: int,
    show_peaks: bool = False,
) -> Text:
    """Render a continuous calibrated FFT trace on a scientific graticule."""
    result = Text()
    if width < 12 or height < 3:
        return result
    axis_width = 5
    plot_width = width - axis_width
    plot_height = height - 1
    pixels_w, pixels_h = plot_width * 2, plot_height * 4
    contour = np.zeros((plot_height, plot_width), dtype=np.uint8)

    source = np.asarray(values, dtype=np.float64)
    if source.size == 0:
        source = np.zeros(plot_width)
    if source.size >= 7:
        kernel = np.array([1, 2, 4, 6, 4, 2, 1], dtype=np.float64) / 20.0
        source = np.convolve(np.pad(source, (3, 3), mode="edge"), kernel, mode="valid")
    sample_x = np.linspace(0, len(source) - 1, pixels_w)
    curve = np.clip(np.interp(sample_x, np.arange(len(source)), source), 0.0, 1.0)
    ys = np.rint((1.0 - curve) * (pixels_h - 1)).astype(int)
    previous_y = int(ys[0])
    for px, y_value in enumerate(ys):
        y = int(y_value)
        for py in range(min(previous_y, y), max(previous_y, y) + 1):
            contour[py // 4, px // 2] |= BRAILLE_BITS[py % 4][px % 2]
        previous_y = y

    grid_rows = {
        0: "  0 ",
        round((plot_height - 1) / 3): "-30 ",
        round(2 * (plot_height - 1) / 3): "-60 ",
        plot_height - 1: "-90 ",
    }
    frequency_ticks = (
        (31.5, "31"),
        (63, "63"),
        (125, "125"),
        (250, "250"),
        (500, "500"),
        (1000, "1k"),
        (2000, "2k"),
        (4000, "4k"),
        (8000, "8k"),
        (16_000, "16k"),
    )
    tick_positions = {
        min(
            plot_width - 1,
            max(0, round(math.log(frequency / 30) / math.log(20_000 / 30) * (plot_width - 1))),
        ): label
        for frequency, label in frequency_ticks
    }

    peak_source = np.asarray(peaks, dtype=np.float64)
    if peak_source.size:
        peak_indexes = np.linspace(0, len(peak_source) - 1, plot_width).astype(int)
        peak_levels = np.clip(peak_source[peak_indexes], 0.0, 1.0)
    else:
        peak_levels = np.zeros(plot_width)

    for row in range(plot_height):
        result.append(grid_rows.get(row, "    ").ljust(axis_width), style=AQUA_DIM)
        for column in range(plot_width):
            bits = int(contour[row, column])
            peak_row = round((1.0 - peak_levels[column]) * (plot_height - 1))
            is_local_peak = (
                column == 0
                or column == plot_width - 1
                or peak_levels[column] >= peak_levels[column - 1]
                and peak_levels[column] >= peak_levels[column + 1]
            )
            if (
                show_peaks
                and peak_levels[column] > 0.16
                and is_local_peak
                and row == peak_row
            ):
                result.append("•", style=f"bold {SPECTRUM_GRADIENT[-1]}")
            elif bits:
                result.append(chr(0x2800 + bits), style=f"bold {AQUA}")
            elif row in grid_rows:
                result.append("─", style="#174642")
            elif column in tick_positions:
                result.append("┊", style="#123b38")
            else:
                result.append(" ")
        result.append("\n")

    axis = [" "] * width
    for position, label in tick_positions.items():
        start = min(width - len(label), axis_width + position - len(label) // 2)
        for offset, character in enumerate(label):
            axis[start + offset] = character
    result.append("".join(axis), style=AQUA_DIM)
    return result


def waterfall_chart(history: list[np.ndarray], width: int, height: int) -> Text:
    """Render recent spectra as a time-descending intensity waterfall."""
    result = Text()
    if width <= 0 or height <= 0:
        return result
    frames = history[-height:]
    missing = height - len(frames)
    frames = [np.zeros(width, dtype=np.float32)] * missing + frames
    for row, frame in enumerate(frames):
        source = np.asarray(frame, dtype=np.float64)
        indexes = np.linspace(0, max(0, len(source) - 1), width).astype(int)
        values = source[indexes] if len(source) else np.zeros(width)
        for value in values:
            intensity = float(np.clip(value, 0.0, 1.0))
            color_index = min(
                len(SPECTRUM_GRADIENT) - 1,
                int(intensity * len(SPECTRUM_GRADIENT)),
            )
            glyph = "█" if intensity > 0.16 else ("·" if intensity > 0.04 else " ")
            result.append(glyph, style=SPECTRUM_GRADIENT[color_index])
        if row < height - 1:
            result.append("\n")
    return result


class TelemetryWidget(Static):
    def __init__(self) -> None:
        super().__init__(id="telemetry")
        self.analysis: Analysis | None = None
        self.left_hold = -120.0
        self.right_hold = -120.0

    def set_analysis(self, analysis: Analysis, fall: float) -> None:
        self.analysis = analysis
        metrics = analysis.metrics
        self.left_hold = max(metrics.left_peak_dbfs, self.left_hold - fall)
        self.right_hold = max(metrics.right_peak_dbfs, self.right_hold - fall)
        self.refresh()

    @staticmethod
    def _meter(value: float, hold: float, width: int = 14) -> str:
        level = int(np.clip((value + 60.0) / 60.0, 0.0, 1.0) * width)
        marker = min(width - 1, max(0, int((hold + 60.0) / 60.0 * width)))
        cells = list("━" * level + "─" * (width - level))
        cells[marker] = "│"
        return "".join(cells)

    def render(self) -> Text:
        if self.analysis is None:
            return Text("ACQUIRING SIGNAL...", style=AQUA_DIM)
        m = self.analysis.metrics
        text = Text()

        def heading(value: str) -> None:
            text.append(value + "\n", style=f"bold {AQUA}")
            text.append("─" * 27 + "\n", style=AQUA_DIM)

        def row(label: str, value: str) -> None:
            text.append(f"{label:<12}", style=AQUA_DIM)
            text.append(value + "\n", style=f"bold {AQUA}")

        heading("LEVELS")
        row("PEAK L", f"{m.left_peak_dbfs:6.1f} dBFS")
        text.append(f"{self._meter(m.left_peak_dbfs, self.left_hold)}\n", style=AQUA)
        row("PEAK R", f"{m.right_peak_dbfs:6.1f} dBFS")
        text.append(f"{self._meter(m.right_peak_dbfs, self.right_hold)}\n\n", style=AQUA)
        heading("SPECTRAL")
        row("RMS", f"{m.rms_dbfs:6.1f} dBFS")
        row("CREST", f"{m.crest_db:6.1f} dB")
        row("FUNDAMENTAL", f"{m.dominant_hz:6.0f} Hz")
        row("CENTROID", f"{m.centroid_hz:6.0f} Hz")
        text.append("\n")
        heading("STEREO IMAGE")
        row("BALANCE", f"{m.stereo_balance:+6.2f}")
        row("CORRELATION", f"{m.correlation:+6.2f}")
        row("CLIPPED", f"{m.clipped_samples:6d}")
        return text


class HelpScreen(ModalScreen[None]):
    BINDINGS: ClassVar = [Binding("escape", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Label("AQUASCOPE QUICK REFERENCE", id="dialog-title")
            yield Static(
                "SPACE   Hold / resume\n"
                "D       Select audio source\n"
                "A       Toggle auto scale\n"
                "UP/DOWN Manual gain\n"
                "V       Wave / persistence / phase / polar\n"
                "S       Curve / bars / waterfall\n"
                "P       Toggle spectrum peak hold\n"
                "? / H   This guide\n"
                "Q       Quit\n\n"
                "SYSTEM = playback loopback\n"
                "INPUT  = microphone / line\n\n"
                "Created by Gabriel Moreno, N6OSB\n"
                "Assisted by Claude.ai Sonnet via Perplexity",
                id="dialog-body",
            )
            yield Label("Press ESC to close", id="dialog-hint")


class DeviceScreen(ModalScreen[int | None]):
    BINDINGS: ClassVar = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, devices: Iterable[Device]) -> None:
        super().__init__()
        self.devices = list(devices)

    def compose(self) -> ComposeResult:
        with Container(id="device-dialog"):
            yield Label("SELECT AUDIO SOURCE", id="dialog-title")
            yield ListView(
                *[
                    ListItem(
                        Label(
                            f"{device.source_kind:<6}  {device.name}  "
                            f"{device.channels}ch / {device.sample_rate / 1000:.1f}k"
                        ),
                        id=f"device-{device.index}",
                    )
                    for device in self.devices
                ],
                id="device-list",
            )
            yield Label("ENTER select   ESC cancel", id="dialog-hint")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        self.dismiss(int(item_id.removeprefix("device-")))

    def action_cancel(self) -> None:
        self.dismiss(None)


class AquaScopeApp(App[None]):
    """Responsive Textual audio analyzer."""

    TITLE = "AquaScope"
    ENABLE_COMMAND_PALETTE = False
    CSS = f"""
    Screen {{
        background: {INK};
        color: {AQUA};
    }}
    #header, #footer, #quick {{
        height: 1;
        background: {AQUA};
        color: {INK};
        text-style: bold;
        padding: 0 1;
    }}
    #source {{
        height: 2;
        color: {AQUA_DIM};
        padding: 0 1;
        content-align: left middle;
    }}
    #body {{
        height: 1fr;
    }}
    #graphs {{
        width: 1fr;
        height: 1fr;
    }}
    ScopeWidget, SpectrumWidget {{
        height: 1fr;
        border: round {AQUA_DIM};
        border-title-color: {AQUA};
        border-title-style: bold;
        padding: 0;
    }}
    ScopeWidget {{
        height: 3fr;
    }}
    SpectrumWidget {{
        height: 2fr;
    }}
    #telemetry {{
        width: 32;
        height: 1fr;
        border-left: solid {AQUA_DIM};
        padding: 1 1;
        background: {PANEL};
    }}
    #footer {{
        dock: bottom;
    }}
    .compact #telemetry {{
        display: none;
    }}
    .compact #source {{
        height: 1;
    }}
    .compact ScopeWidget {{
        height: 1fr;
    }}
    .compact SpectrumWidget {{
        height: 1fr;
    }}
    ModalScreen {{
        align: center middle;
        background: rgba(0, 0, 0, 0.72);
    }}
    #dialog {{
        width: 52;
        height: 22;
        border: tall {AQUA};
        background: {PANEL};
        padding: 1 2;
    }}
    #device-dialog {{
        width: 72;
        height: 70%;
        max-height: 24;
        border: tall {AQUA};
        background: {PANEL};
        padding: 1 2;
    }}
    #dialog-title {{
        height: 2;
        color: {AQUA};
        text-style: bold;
        content-align: center middle;
    }}
    #dialog-body {{
        height: 1fr;
        color: {AQUA};
    }}
    #dialog-hint {{
        height: 1;
        color: {AQUA_DIM};
        content-align: center middle;
    }}
    #device-list {{
        height: 1fr;
        background: {INK};
        border: none;
    }}
    ListItem {{
        padding: 0 1;
        color: {AQUA_DIM};
    }}
    ListItem.--highlight {{
        background: {AQUA};
        color: {INK};
        text-style: bold;
    }}
    """
    BINDINGS: ClassVar = [
        Binding("q", "quit", "Quit", show=False),
        Binding("space", "hold", "Hold", show=False),
        Binding("d", "device", "Source", show=False),
        Binding("a", "auto_scale", "Auto", show=False),
        Binding("up", "gain_up", "Gain +", show=False),
        Binding("down", "gain_down", "Gain -", show=False),
        Binding("v", "scope_view", "Scope view", show=False),
        Binding("s", "spectrum_view", "Spectrum view", show=False),
        Binding("p", "peak_hold", "Peak hold", show=False),
        Binding("question_mark", "help", "Help", show=False),
        Binding("h", "help", "Help", show=False),
    ]

    def __init__(
        self,
        engine: AudioEngine,
        fps: int = 30,
        demo: bool = False,
        layout: str = "auto",
    ) -> None:
        super().__init__()
        self.engine = engine
        self.fps = fps
        self.demo = demo
        self.layout_mode = layout
        self.paused = False
        self.analysis: Analysis | None = None
        self.started_at = time.monotonic()
        self.message = ""
        self._refresh_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Static(id="header")
        yield Static(id="source")
        yield Static(id="quick")
        with Horizontal(id="body"):
            with Vertical(id="graphs"):
                scope = ScopeWidget()
                scope.border_title = "OSCILLOSCOPE  |  WAVE"
                yield scope
                spectrum = SpectrumWidget()
                spectrum.border_title = "FFT TRACE  |  LOG Hz / dBFS  |  HANN"
                yield spectrum
            yield TelemetryWidget()
        yield Static(
            " Q QUIT  SPACE HOLD  D SOURCE  V SCOPE  S SPECTRUM  P PEAK  ? HELP",
            id="footer",
        )

    def on_mount(self) -> None:
        if not self.demo:
            try:
                self.engine.start()
            except Exception as exc:  # noqa: BLE001 - PortAudio errors vary by backend
                self.demo = True
                self.message = f"Audio unavailable; showing reference signal ({exc})"
        self._apply_layout()
        self._refresh_timer = self.set_interval(1.0 / self.fps, self._tick)
        self._tick()

    def on_unmount(self) -> None:
        if self._refresh_timer is not None:
            self._refresh_timer.stop()
        self.engine.close()

    def on_resize(self, event: events.Resize) -> None:
        del event
        self._apply_layout()

    def _apply_layout(self) -> None:
        compact = self.layout_mode == "compact" or (
            self.layout_mode == "auto" and (self.size.width < 120 or self.size.height < 34)
        )
        self.screen.set_class(compact, "compact")

    def _tick(self) -> None:
        try:
            self._refresh()
        except NoMatches:
            # A last timer tick can land while the app is shutting down and its
            # widgets are already gone; there is nothing left to draw.
            return

    def _refresh(self) -> None:
        if not self.paused:
            if self.demo:
                frames = self._demo_frames()
                self.analysis = analyze(frames, 48_000)
            elif self.engine.stream is not None:
                self.analysis = analyze(self.engine.snapshot(), self.engine.sample_rate)
        if self.analysis is not None:
            scope = self.query_one(ScopeWidget)
            input_channels = (
                min(2, self.engine.device.channels) if self.engine.device else 2
            )
            scope.set_analysis(self.analysis, input_channels)
            width = max(8, self.query_one(SpectrumWidget).content_size.width)
            bands = logarithmic_bands(
                self.analysis.spectrum, self.analysis.frequencies, width
            )
            self.query_one(SpectrumWidget).set_values(bands)
            self.query_one(TelemetryWidget).set_analysis(
                self.analysis, fall=18.0 / self.fps
            )
        self._update_chrome()

    def _update_chrome(self) -> None:
        if self.paused:
            state = "HOLD"
        elif self.demo:
            state = "DEMO"
        elif self.analysis and self.analysis.metrics.rms_dbfs < -75.0:
            state = "NO SIGNAL"
        else:
            state = "LIVE"
        self.query_one("#header", Static).update(
            f"AQUASCOPE  {__version__}    PRECISION AUDIO ANALYZER".ljust(
                max(1, self.size.width - len(state) - 3)
            )
            + state
        )
        device = self.engine.device
        name = device.name if device else "REFERENCE SIGNAL"
        kind = device.source_kind if device else "DEMO"
        rate = self.engine.sample_rate / 1000 if not self.demo else 48.0
        note = f"  {self.message}" if self.message else ""
        self.query_one("#source", Static).update(
            f"{kind:<6}  {name}   |   {rate:.1f} kHz / FLOAT32{note}"
        )
        if self.analysis is not None:
            m = self.analysis.metrics
            self.query_one("#quick", Static).update(
                f"PK {m.peak_dbfs:5.1f}   RMS {m.rms_dbfs:5.1f}   "
                f"CREST {m.crest_db:4.1f}   FUND {m.dominant_hz:5.0f} Hz   "
                f"CORR {m.correlation:+.2f}"
            )

    def _demo_frames(self) -> np.ndarray:
        sample_rate = 48_000
        count = 8192
        now = time.monotonic() - self.started_at
        t = np.arange(count, dtype=np.float64) / sample_rate + now
        pulse = 0.55 + 0.45 * max(0.0, math.sin(now * math.pi * 1.7)) ** 8
        left = pulse * (
            0.34 * np.sin(2 * np.pi * 110 * t)
            + 0.19 * np.sin(2 * np.pi * 220 * t)
            + 0.09 * np.sin(2 * np.pi * 1760 * t)
        )
        right = pulse * (
            0.31 * np.sin(2 * np.pi * 110 * t + 0.08)
            + 0.17 * np.sin(2 * np.pi * 330 * t)
            + 0.10 * np.sin(2 * np.pi * 1320 * t)
        )
        return np.column_stack((left, right)).astype(np.float32)

    def action_hold(self) -> None:
        self.paused = not self.paused

    def action_auto_scale(self) -> None:
        scope = self.query_one(ScopeWidget)
        scope.auto_scale = not scope.auto_scale

    def action_gain_up(self) -> None:
        scope = self.query_one(ScopeWidget)
        scope.auto_scale = False
        scope.manual_gain = min(8.0, scope.manual_gain * 1.25)

    def action_gain_down(self) -> None:
        scope = self.query_one(ScopeWidget)
        scope.auto_scale = False
        scope.manual_gain = max(0.125, scope.manual_gain / 1.25)

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_scope_view(self) -> None:
        mode = self.query_one(ScopeWidget).next_mode()
        self.notify(f"Scope: {mode}", timeout=2)

    def action_spectrum_view(self) -> None:
        mode = self.query_one(SpectrumWidget).next_mode()
        self.notify(f"Analyzer: {mode}", timeout=2)

    def action_peak_hold(self) -> None:
        enabled = self.query_one(SpectrumWidget).toggle_peak_hold()
        self.notify(f"Peak hold: {'ON' if enabled else 'OFF'}", timeout=2)

    def action_device(self) -> None:
        try:
            devices = AudioEngine.devices()
        except Exception as exc:  # noqa: BLE001 - audio driver boundary
            self.notify(f"{exc}. {setup_hint()}", severity="error", timeout=6)
            return
        if not devices:
            self.notify(setup_hint(), severity="warning", timeout=6)
            return
        self.push_screen(DeviceScreen(devices), self._select_device)

    def _select_device(self, index: int | None) -> None:
        if index is None:
            return
        devices = AudioEngine.devices()
        selected = next((item for item in devices if item.index == index), None)
        if selected is None:
            return
        self.engine.close()
        self.engine.requested_device = index
        try:
            self.engine.start()
        except Exception as exc:  # noqa: BLE001 - PortAudio backend boundary
            self.demo = True
            self.notify(str(exc), severity="error", timeout=6)
            return
        self.demo = False
        self.message = ""
        save_config({"device_name": selected.name})
        self.notify(f"Listening to {selected.name}", timeout=3)
