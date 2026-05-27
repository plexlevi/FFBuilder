#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Detailed audio analysis dialog with legacy-style loudness graph."""

from __future__ import annotations

import os
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QFile, QObject, QPointF, QRectF, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QFileDialog,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.gui_qt.dialogs._modal_backdrop import exec_with_backdrop, apply_rounded_mask
from app.shared.i18n import trs


# ── Eredmény cache: (fájl_útvonal, mtime_ns) → LoudnessAnalysisResult ────────
# Ha a dialógus egyszer már elvégezte az elemzést, a következő nyitáskor
# azonnal megjelenítjük az eredményt, és a főablak LoudnessWorker-je is
# kihagyja az újabb ffmpeg futtatást.
_RESULT_CACHE: dict[tuple[str, int], "LoudnessAnalysisResult"] = {}

# Fájlok amelyekre jelenleg fut a háttér-elemzés (_LoudnessWorker)
_PENDING_PATHS: set[str] = set()


def _cache_key(file_path: str) -> tuple[str, int]:
    try:
        mtime = os.stat(file_path).st_mtime_ns
    except OSError:
        mtime = 0
    return (file_path, mtime)


def get_cached_result(file_path: str) -> "LoudnessAnalysisResult | None":
    """Visszaadja a file korábban mentett teljes elemzési eredményét, ha létezik."""
    return _RESULT_CACHE.get(_cache_key(file_path))


def build_file_info_patch(result: "LoudnessAnalysisResult") -> dict[str, str]:
    """Map full audio-analysis result to main-window file metadata keys."""
    return {
        "audio_sample_rate": result.sample_rate_hz,
        "audio_bit_depth": result.bit_depth,
        "audio_channels": result.channels,
        "audio_bitrate": result.bit_rate,
        "lufs": result.integrated,
        "lra": result.loudness_range,
        "true_peak": result.true_peak_max,
        "loudness_gate": result.loudness_gate,
    }


@dataclass
class LoudnessAnalysisResult:
    filename: str
    sample_rate_hz: str
    bit_depth: str
    codec: str
    channels: str
    bit_rate: str
    short_term: str
    integrated: str
    loudness_range: str
    loudness_gate: str
    momentary_max: str
    short_term_max: str
    true_peak_max: str
    momentary_data: list[tuple[float, float]]
    shortterm_data: list[tuple[float, float]]
    integrated_data: list[tuple[float, float]]


class _AudioAnalysisSignals(QObject):
    progress = Signal(int)
    finished = Signal(object)
    failed = Signal(str)


class _AudioAnalysisWorker(QRunnable):
    def __init__(self, file_path: str, ffmpeg_bin: str, ffprobe_bin: str) -> None:
        super().__init__()
        self.file_path = file_path
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin
        self.signals = _AudioAnalysisSignals()

    def run(self) -> None:
        try:
            result = self._analyze()
        except Exception as exc:
            self.signals.failed.emit(str(exc))
            return
        self.signals.finished.emit(result)

    def _analyze(self) -> LoudnessAnalysisResult:
        probe_cmd = [
            self.ffprobe_bin,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            "-select_streams",
            "a:0",
            self.file_path,
        ]
        probe = subprocess.run(probe_cmd, capture_output=True, text=True, check=True, timeout=30)

        payload = json.loads(probe.stdout or "{}")
        streams = payload.get("streams", [])
        if not streams:
            raise RuntimeError("The file does not contain an audio stream.")
        audio_stream = streams[0]

        duration_seconds = 0.0
        try:
            duration_seconds = float((payload.get("format") or {}).get("duration") or 0.0)
        except Exception:
            duration_seconds = 0.0

        sample_rate_hz = "N/A"
        if audio_stream.get("sample_rate"):
            sr = int(audio_stream.get("sample_rate"))
            sample_rate_hz = f"{sr} Hz ({sr // 1000} kHz)"

        sample_fmt = str(audio_stream.get("sample_fmt") or "")
        bit_depth = "N/A"
        for field in ("bits_per_sample", "bits_per_raw_sample"):
            raw = audio_stream.get(field)
            if raw:
                try:
                    bit_depth = f"{int(raw)} bit"
                    break
                except Exception:
                    pass
        if bit_depth == "N/A" and sample_fmt:
            sample_fmt_l = sample_fmt.lower()
            if "s16" in sample_fmt_l:
                bit_depth = "16 bit"
            elif "s24" in sample_fmt_l:
                bit_depth = "24 bit"
            elif "s32" in sample_fmt_l or "flt" in sample_fmt_l:
                bit_depth = "32 bit"

        codec = str(audio_stream.get("codec_name") or "N/A").upper()
        channels = str(audio_stream.get("channels") or "N/A")
        bit_rate = "N/A"
        try:
            br = int(audio_stream.get("bit_rate") or 0)
            if br > 0:
                bit_rate = f"{br // 1000} kbps"
        except Exception:
            pass

        analysis_cmd = [
            self.ffmpeg_bin,
            "-hide_banner",
            "-i",
            self.file_path,
            "-map",
            "0:a:0",
            "-vn",
            "-sn",
            "-dn",
            "-af",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ]

        process = subprocess.Popen(
            analysis_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        stderr_lines: list[str] = []
        momentary_data: list[tuple[float, float]] = []
        shortterm_data: list[tuple[float, float]] = []
        integrated_data: list[tuple[float, float]] = []

        line_pattern = re.compile(r"t:\s*([\d.]+).*?M:\s*([-\d.]+)\s+S:\s*([-\d.]+).*?I:\s*([-\d.]+)")

        if process.stderr is None:
            raise RuntimeError("Could not open FFmpeg stderr channel.")

        _last_emitted_pct: int = -1

        for line in process.stderr:
            stderr_lines.append(line)

            tm = re.search(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", line)
            if tm and duration_seconds > 0:
                hh = int(tm.group(1))
                mm = int(tm.group(2))
                ss = float(tm.group(3))
                current = hh * 3600 + mm * 60 + ss
                pct = int(max(0.0, min(100.0, (current / duration_seconds) * 100.0)))
                if pct != _last_emitted_pct:
                    _last_emitted_pct = pct
                    self.signals.progress.emit(pct)

            m = line_pattern.search(line)
            if m:
                t = float(m.group(1))
                mv = float(m.group(2))
                sv = float(m.group(3))
                iv = float(m.group(4))
                if mv > -100:
                    momentary_data.append((t, mv))
                if sv > -100:
                    shortterm_data.append((t, sv))
                if iv > -100:
                    integrated_data.append((t, iv))

        process.wait(timeout=1200)
        if process.returncode not in (0,):
            raise RuntimeError("FFmpeg loudness analysis failed.")

        self.signals.progress.emit(100)

        stderr_text = "".join(stderr_lines)
        summary = stderr_text[stderr_text.rfind("Summary:") :] if "Summary:" in stderr_text else stderr_text

        def _fmt(match: re.Match | None, unit: str) -> str:
            if not match:
                return "N/A"
            return f"{float(match.group(1)):.1f} {unit}"

        integrated_match = re.search(r"I:\s*([-\d.]+)\s+LUFS", summary)
        lra_match = re.search(r"LRA:\s*([\d.]+)\s+LU", summary)
        tp_match = re.search(r"Peak:\s*([-\d.]+)\s+dBFS", summary)
        gate_match = re.search(
            r"Integrated loudness:\s*.*?Threshold:\s*([-\d.]+)\s+LUFS",
            summary,
            flags=re.S,
        )

        short_term = f"{shortterm_data[-1][1]:.1f} LUFS" if shortterm_data else "N/A"
        momentary_max = f"{max(v for _, v in momentary_data):.1f} LUFS" if momentary_data else "N/A"
        short_term_max = f"{max(v for _, v in shortterm_data):.1f} LUFS" if shortterm_data else "N/A"

        return LoudnessAnalysisResult(
            filename=os.path.basename(self.file_path),
            sample_rate_hz=sample_rate_hz,
            bit_depth=bit_depth,
            codec=codec,
            channels=channels,
            bit_rate=bit_rate,
            short_term=short_term,
            integrated=_fmt(integrated_match, "LUFS"),
            loudness_range=_fmt(lra_match, "LU"),
            loudness_gate=_fmt(gate_match, "LUFS"),
            momentary_max=momentary_max,
            short_term_max=short_term_max,
            true_peak_max=_fmt(tp_match, "dB"),
            momentary_data=momentary_data,
            shortterm_data=shortterm_data,
            integrated_data=integrated_data,
        )


# ── QPainter-alapú loudness grafikon widget ───────────────────────────────────

class LoudnessGraphWidget(QWidget):
    """Natív QPainter loudness időbeli grafikon – matplotlib / numpy / PIL nélkül."""

    _Y_MIN: float = -60.0
    _Y_MAX: float = 0.0
    _Y_TICKS: list[int] = [-60, -50, -40, -30, -20, -10, 0]
    # Margók: bal (y tengely), teteje, jobb, alap (x tengely)
    _ML, _MT, _MR, _MB = 52, 14, 14, 44

    def __init__(self, result: LoudnessAnalysisResult, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._result = result
        self._pixmap_cache: QPixmap | None = None
        self._cache_size: QSize = QSize()
        self.setMinimumSize(460, 260)

    def sizeHint(self) -> QSize:
        return QSize(700, 360)

    def render_to_pixmap(self, width: int = 3508, height: int = 2481) -> QPixmap:
        """Hi-res QPixmap renderelés PNG mentéshez (A4 @ 300 DPI)."""
        pix = QPixmap(width, height)
        pix.fill(QColor("white"))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint(p, QRectF(0.0, 0.0, width, height), scale=width / 700.0, dark=False)
        p.end()
        return pix

    def paintEvent(self, event) -> None:  # type: ignore[override]
        current_size = self.size()
        dark = self.palette().color(QPalette.ColorRole.Window).lightness() < 128
        if self._pixmap_cache is None or self._cache_size != current_size:
            pix = QPixmap(current_size)
            pix.fill(Qt.GlobalColor.transparent)
            p = QPainter(pix)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._paint(p, QRectF(pix.rect()), scale=1.0, dark=dark)
            p.end()
            self._pixmap_cache = pix
            self._cache_size = current_size
        p = QPainter(self)
        p.drawPixmap(0, 0, self._pixmap_cache)
        p.end()

    # ------------------------------------------------------------------

    def _paint(self, p: QPainter, r: QRectF, *, scale: float, dark: bool) -> None:
        L = self._ML * scale
        T = self._MT * scale
        R = self._MR * scale
        B = self._MB * scale
        px0 = r.x() + L
        py0 = r.y() + T
        pw = r.width() - L - R
        ph = r.height() - T - B
        if pw < 1 or ph < 1:
            return

        all_t: list[float] = []
        for series in (self._result.momentary_data, self._result.shortterm_data, self._result.integrated_data):
            all_t.extend(t for t, _ in series)
        x_min = min(all_t, default=0.0)
        x_max = max(all_t, default=1.0)
        if x_max <= x_min:
            x_max = x_min + 1.0

        def to_pt(t: float, lufs: float) -> QPointF:
            x = px0 + (t - x_min) / (x_max - x_min) * pw
            clamped = max(self._Y_MIN, min(self._Y_MAX, lufs))
            y = py0 + ph * (1.0 - (clamped - self._Y_MIN) / (self._Y_MAX - self._Y_MIN))
            return QPointF(x, y)

        # Háttér
        p.fillRect(r, QColor("#1b1b1b") if dark else QColor("#f9f9f9"))

        text_col = QColor("#b8b8b8") if dark else QColor("#444444")
        grid_col = QColor(180, 180, 180, 35) if dark else QColor(80, 80, 80, 35)

        # Y grid + feliratok
        font = QFont(p.font())
        font.setPointSizeF(7.5 * scale)
        p.setFont(font)

        # Fájlnév – grafikon teteje, középre igazítva
        fn_font = QFont(p.font())
        fn_font.setPointSizeF(8.0 * scale)
        fn_font.setBold(True)
        p.setFont(fn_font)
        p.setPen(text_col)
        raw_name = os.path.basename(self._result.filename)
        display_name = raw_name if len(raw_name) <= 80 else raw_name[:77] + "…"
        p.drawText(
            QRectF(px0, r.y(), pw, T),
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
            display_name,
        )
        p.setFont(font)
        for y_val in self._Y_TICKS:
            pt = to_pt(x_min, float(y_val))
            p.setPen(QPen(grid_col, 1.0 * scale))
            p.drawLine(QPointF(px0, pt.y()), QPointF(px0 + pw, pt.y()))
            p.setPen(text_col)
            p.drawText(
                QRectF(r.x(), pt.y() - 7 * scale, L - 4 * scale, 14 * scale),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                str(y_val),
            )

        # EBU-R128 −23 referenciavonal
        pt_ebu = to_pt(x_min, -23.0)
        pen_ebu = QPen(QColor(210, 70, 70, 200), 1.2 * scale, Qt.PenStyle.DashLine)
        p.setPen(pen_ebu)
        p.drawLine(QPointF(px0, pt_ebu.y()), QPointF(px0 + pw, pt_ebu.y()))

        # Downsample to pixel-width for performance (no redraws on cache hit)
        max_pts = max(2, int(pw))
        st_ds = self._downsample(self._result.shortterm_data, max_pts)
        m_ds  = self._downsample(self._result.momentary_data,  max_pts)
        i_ds  = self._downsample(self._result.integrated_data, max_pts)

        # Short-term kitöltés
        if st_ds:
            base_y = to_pt(x_min, self._Y_MIN).y()
            pts = [to_pt(t, v) for t, v in st_ds]
            fill = QPainterPath()
            fill.moveTo(pts[0])
            for pt in pts[1:]:
                fill.lineTo(pt)
            fill.lineTo(QPointF(pts[-1].x(), base_y))
            fill.lineTo(QPointF(pts[0].x(), base_y))
            fill.closeSubpath()
            p.fillPath(fill, QColor(50, 150, 240, 50))

        # Vonalak
        self._draw_series(p, st_ds, to_pt, QColor(70, 160, 255), 1.0 * scale)
        self._draw_series(p, m_ds,  to_pt, QColor(110, 215, 255), 0.9 * scale)
        self._draw_series(p, i_ds,  to_pt, QColor(255, 185, 45),  1.3 * scale)

        # X tengelycímkék
        n_x = min(8, max(4, int(pw / (55 * scale))))
        p.setPen(text_col)
        for i in range(n_x + 1):
            t = x_min + (x_max - x_min) * i / n_x
            pt = to_pt(t, self._Y_MIN)
            secs = int(t)
            h_v, rem = divmod(secs, 3600)
            m_v, s_v = divmod(rem, 60)
            label = f"{h_v:02d}:{m_v:02d}:{s_v:02d}" if h_v else f"{m_v:02d}:{s_v:02d}"
            p.drawText(
                QRectF(pt.x() - 28 * scale, pt.y() + 4 * scale, 56 * scale, 14 * scale),
                Qt.AlignmentFlag.AlignCenter,
                label,
            )

        # Keret
        border_col = QColor("#3a3a3a") if dark else QColor("#c0c0c0")
        p.setPen(QPen(border_col, 1.0 * scale))
        p.drawRect(QRectF(px0, py0, pw, ph))

        # Jelmagyarázat
        lx = px0 + pw - 130 * scale
        ly = py0 + 10 * scale
        for label, col in (
            ("Short-Term",   QColor(70, 160, 255)),
            ("Momentary",    QColor(110, 215, 255)),
            ("Integrated",   QColor(255, 185, 45)),
            ("EBU-R128 −23", QColor(210, 70, 70)),
        ):
            p.setPen(QPen(col, 2.0 * scale))
            p.drawLine(QPointF(lx, ly + 4 * scale), QPointF(lx + 18 * scale, ly + 4 * scale))
            p.setPen(text_col)
            p.drawText(
                QRectF(lx + 22 * scale, ly - 2 * scale, 110 * scale, 14 * scale),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label,
            )
            ly += 16 * scale

        # Loudness stat blokk – bal alsó sarok, a plot területén belül
        stats_rows = [
            ("Integrated",    self._result.integrated),
            ("True Peak",     self._result.true_peak_max),
            ("LRA",           self._result.loudness_range),
            ("Momentary max", self._result.momentary_max),
        ]
        row_h = 13.0 * scale
        sb_w  = 180.0 * scale
        sb_h  = len(stats_rows) * row_h + 4 * scale
        sb_x  = px0 + 6 * scale
        sb_y  = py0 + ph - sb_h - 4 * scale

        # Semi-transzparens háttér
        p.fillRect(
            QRectF(sb_x - 3 * scale, sb_y - 2 * scale, sb_w + 6 * scale, sb_h + 4 * scale),
            QColor(20, 20, 20, 110) if dark else QColor(250, 250, 250, 160),
        )

        stats_font = QFont(p.font())
        stats_font.setPointSizeF(7.0 * scale)
        p.setFont(stats_font)
        lbl_col = QColor("#888888")
        for s_label, s_value in stats_rows:
            p.setPen(lbl_col)
            p.drawText(
                QRectF(sb_x, sb_y, 96 * scale, row_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                s_label + ":",
            )
            p.setPen(text_col)
            p.drawText(
                QRectF(sb_x + 96 * scale, sb_y, 84 * scale, row_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                s_value,
            )
            sb_y += row_h

    @staticmethod
    def _downsample(
        data: list[tuple[float, float]], max_pts: int
    ) -> list[tuple[float, float]]:
        """Average-bucket downsample – preserves shape, limits QPainterPath nodes."""
        n = len(data)
        if n <= max_pts:
            return data
        result: list[tuple[float, float]] = []
        bucket_size = n / max_pts
        i = 0.0
        while len(result) < max_pts:
            start = int(i)
            end = min(n, max(start + 1, int(i + bucket_size)))
            bucket = data[start:end]
            if not bucket:
                break
            avg_t = sum(t for t, _ in bucket) / len(bucket)
            avg_v = sum(v for _, v in bucket) / len(bucket)
            result.append((avg_t, avg_v))
            i += bucket_size
        return result

    @staticmethod
    def _draw_series(
        p: QPainter,
        data: list[tuple[float, float]],
        to_pt,
        color: QColor,
        width: float,
    ) -> None:
        if not data:
            return
        p.setPen(QPen(color, width))
        path = QPainterPath()
        path.moveTo(to_pt(data[0][0], data[0][1]))
        for t, v in data[1:]:
            path.lineTo(to_pt(t, v))
        p.drawPath(path)


class AudioAnalysisDialog(QDialog):
    def __init__(self, file_path: str, ffmpeg_bin: str, ffprobe_bin: str, parent=None):
        super().__init__(parent)
        self.ready = False
        self._file_path = file_path
        self._ffmpeg_bin = ffmpeg_bin
        self._ffprobe_bin = ffprobe_bin
        self._thread_pool = QThreadPool.globalInstance()
        self._result: LoudnessAnalysisResult | None = None
        self._graph_widget: LoudnessGraphWidget | None = None

        self.setWindowTitle(trs("Audio analysis"))
        self.resize(760, 780)
        self.setMinimumSize(680, 560)

        self._wait_timer: QTimer | None = None
        self._build_ui()

        cached = get_cached_result(self._file_path)
        if cached is not None:
            QTimer.singleShot(0, lambda: self._on_finished(cached))
        elif self._file_path in _PENDING_PATHS:
            self.status_label.setText(trs("Background analysis in progress, waiting..."))
            self._wait_timer = QTimer(self)
            self._wait_timer.timeout.connect(self._wait_for_background_result)
            self._wait_timer.start(400)
        else:
            self._start_analysis()

    def exec(self) -> int:
        return exec_with_backdrop(self)

    def get_file_info_patch(self) -> dict[str, str]:
        if self._result is None:
            return {}
        return build_file_info_patch(self._result)

    def _build_ui(self) -> None:
        _ui_path = Path(__file__).parent.parent / "ui" / "audio_analysis_dialog.ui"
        loader = QUiLoader()
        f = QFile(str(_ui_path))
        f.open(QFile.ReadOnly)
        w = loader.load(f, self)
        f.close()
        w.setStyleSheet("")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(w)

        self.file_label = w.findChild(QLabel, "fileLabel")
        self.file_label.setStyleSheet("font-size: 13pt; font-weight: 600;")
        self.file_label.setText(os.path.basename(self._file_path))
        self.status_label = w.findChild(QLabel, "statusLabel")
        self.status_label.setStyleSheet("font-size: 13pt;")
        self.scroll_area = w.findChild(QScrollArea, "scrollArea")
        self.results_widget = w.findChild(QWidget, "resultsWidget")
        self.results_layout = self.results_widget.layout()
        self.save_button = w.findChild(QPushButton, "saveButton")
        self.save_button.clicked.connect(self._save_graph)

    def _wait_for_background_result(self) -> None:
        """Megvárja, hogy a főablak háttér-elemzése végezzen, majd megjeleníti az eredményt."""
        cached = get_cached_result(self._file_path)
        if cached is not None:
            self._wait_timer.stop()
            self._on_finished(cached)
            return
        if self._file_path not in _PENDING_PATHS:
            # Worker már nem fut, de nincs cache (hiba lehetett) → saját worker
            self._wait_timer.stop()
            self.status_label.setText("0%")
            self._start_analysis()

    def _start_analysis(self) -> None:
        worker = _AudioAnalysisWorker(self._file_path, self._ffmpeg_bin, self._ffprobe_bin)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.failed.connect(self._on_failed)
        self._thread_pool.start(worker)

    def _on_progress(self, value: int) -> None:
        pct = max(0, min(100, int(value)))
        self.status_label.setText(f"{pct}%")

    def _on_finished(self, result: LoudnessAnalysisResult) -> None:
        _RESULT_CACHE[_cache_key(self._file_path)] = result  # cache for next open / main window
        self._result = result
        self.status_label.setVisible(False)
        self._render_results(result)
        self.scroll_area.setVisible(True)
        self.save_button.setEnabled(True)
        self.ready = True
        QTimer.singleShot(0, self._adjust_and_center)

    def _on_failed(self, message: str) -> None:
        QMessageBox.critical(self, trs("Audio analysis error"), message)
        self.reject()

    def _adjust_and_center(self) -> None:
        self.adjustSize()
        parent = self.parentWidget()
        if parent is not None:
            x = (parent.width() - self.width()) // 2
            y = (parent.height() - self.height()) // 2
            self.move(x, y)
        apply_rounded_mask(self)

    def _render_results(self, result: LoudnessAnalysisResult) -> None:
        file_info = {
            "Sample Rate": result.sample_rate_hz,
            "Bit Depth": result.bit_depth,
            "Codec": result.codec,
            "Channels": result.channels,
            "Bit Rate": result.bit_rate,
        }
        loudness_info = {
            "Integrated": result.integrated,
            "Loudness gate": result.loudness_gate,
            "True peak max": result.true_peak_max,
            "Momentary max": result.momentary_max,
            "Short term max": result.short_term_max,
            "Short term": result.short_term,
            "Loudness range": result.loudness_range,
        }

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.addWidget(self._create_info_group(trs("File Information"), file_info), 1)
        top_row.addWidget(self._create_info_group(trs("Loudness Analysis"), loudness_info), 1)
        self.results_layout.addLayout(top_row)
        self.results_layout.addWidget(self._create_graph_group(result))
        self.results_layout.addStretch(1)

    def _create_info_group(self, title: str, items: dict[str, str]) -> QGroupBox:
        group = QGroupBox(title)
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignLeft)
        for key, value in items.items():
            k = QLabel(f"{key}:")
            k.setStyleSheet("font-size: 11pt;")
            v = QLabel(str(value))
            v.setStyleSheet("font-size: 11pt; font-weight: 600;")
            form.addRow(k, v)
        return group

    def _create_graph_group(self, result: LoudnessAnalysisResult) -> QGroupBox:
        group = QGroupBox(trs("Loudness over time"))
        layout = QVBoxLayout(group)
        self._graph_widget = LoudnessGraphWidget(result, parent=group)
        layout.addWidget(self._graph_widget)
        return group

    def _save_graph(self) -> None:
        if self._result is None or self._graph_widget is None:
            return
        base_name = f"{Path(self._file_path).stem}_loudnessGraph.png"
        desktop = str(Path.home() / "Desktop" / base_name)
        out_path, _ = QFileDialog.getSaveFileName(self, "Grafikon mentése", desktop, "PNG files (*.png)")
        if not out_path:
            return
        # A4 landscape @ 300 DPI = 3508 × 2481 px
        pix = self._graph_widget.render_to_pixmap(3508, 2481)
        if pix.save(out_path, "PNG"):
            QMessageBox.information(self, "Mentés kész", f"Grafikon mentve (3508×2481 px):\n{out_path}")
        else:
            QMessageBox.critical(self, "Mentési hiba", "Nem sikerült a fájl mentése.")
