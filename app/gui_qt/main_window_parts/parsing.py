"""Parsing and progress-estimation helpers for FFmpeg output."""

from __future__ import annotations

import re
import time
from typing import Any

from app.shared.i18n import trs

_DURATION_RE = re.compile(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)")
_TIME_RE = re.compile(r"time=(\d{2}:\d{2}:\d{2}(?:\.\d+)?)")
_OUT_TIME_RE = re.compile(r"out_time=(\d{2}:\d{2}:\d{2}(?:\.\d+)?)")
_OUT_TIME_MS_RE = re.compile(r"out_time_ms=(\d+)")
_OUT_TIME_US_RE = re.compile(r"out_time_us=(\d+)")
_SPEED_RE = re.compile(r"speed=\s*([\d.]+)x")


def parse_ffmpeg_duration_seconds(text: str) -> float | None:
    match = _DURATION_RE.search(text)
    if not match:
        return None
    hh, mm, ss = match.groups()
    return int(hh) * 3600 + int(mm) * 60 + float(ss)


def parse_ffmpeg_time_seconds(text: str) -> float | None:
    matches = _TIME_RE.findall(text)
    if matches:
        hh, mm, ss = matches[-1].split(":")
        return int(hh) * 3600 + int(mm) * 60 + float(ss)

    out_time_matches = _OUT_TIME_RE.findall(text)
    if out_time_matches:
        hh, mm, ss = out_time_matches[-1].split(":")
        return int(hh) * 3600 + int(mm) * 60 + float(ss)

    out_time_ms_matches = _OUT_TIME_MS_RE.findall(text)
    if out_time_ms_matches:
        try:
            # FFmpeg -progress outputs out_time_ms in microseconds.
            return float(out_time_ms_matches[-1]) / 1_000_000.0
        except Exception:
            return None

    out_time_us_matches = _OUT_TIME_US_RE.findall(text)
    if out_time_us_matches:
        try:
            return float(out_time_us_matches[-1]) / 1_000_000.0
        except Exception:
            return None

    return None


def parse_ffmpeg_speed(text: str) -> str | None:
    matches = _SPEED_RE.findall(text)
    return matches[-1] if matches else None


def fmt_seconds(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def fmt_eta_hu(seconds: float) -> str:
    s = int(max(0, seconds))
    m, sec = divmod(s, 60)
    h, m = divmod(m, 60)
    _h, _m, _s = trs("h"), trs("m"), trs("s")
    if h:
        return f"{h}{_h} {m}{_m} {sec}{_s}"
    if m:
        return f"{m}{_m} {sec}{_s}"
    return f"{sec}{_s}"


def build_run_status_text(
    pct: int,
    seconds: float,
    total_seconds: float,
    speed: str | None,
    eta_sec: float,
) -> str:
    parts = [
        f"{pct:5.1f}%",
        f"{fmt_seconds(seconds)} / {fmt_seconds(total_seconds)}",
    ]
    if speed:
        parts.append(f"{speed}x")
    if eta_sec > 0:
        parts.append(f"ETA: {fmt_eta_hu(eta_sec)}")
    return " | ".join(parts)


def build_run_status_text_partial(
    seconds: float,
    speed: str | None,
) -> str:
    parts = [f"{trs('Running:')} {fmt_seconds(seconds)}"]
    if speed:
        parts.append(f"{speed}x")
    return " | ".join(parts)


def append_capped_text(existing: str, new_text: str, max_chars: int) -> str:
    return (existing + new_text)[-max_chars:]


def resolve_stderr_progress_update(
    data: str,
    run_duration_seconds: float,
    eta_estimator: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "run_duration_seconds": run_duration_seconds,
        "should_reset_progress": False,
        "progress_percent": None,
        "status_text": None,
    }

    seconds = parse_ffmpeg_time_seconds(data)
    speed = parse_ffmpeg_speed(data)

    if run_duration_seconds <= 0:
        duration_seconds = parse_ffmpeg_duration_seconds(data)
        if duration_seconds is not None:
            run_duration_seconds = duration_seconds
            result["run_duration_seconds"] = run_duration_seconds
            result["should_reset_progress"] = True
        elif seconds is not None:
            result["status_text"] = build_run_status_text_partial(seconds, speed)

    if run_duration_seconds <= 0:
        return result

    if seconds is None:
        return result

    pct = max(0, min(100, int((seconds / run_duration_seconds) * 100)))
    eta_sec = eta_estimator.update(float(pct))
    result["progress_percent"] = pct
    result["status_text"] = build_run_status_text(pct, seconds, run_duration_seconds, speed, eta_sec)
    return result


class _EtaEstimator:
    """Sliding-window ETA estimator to avoid noisy/incorrect ETA values."""

    _WINDOW = 20.0
    _MIN_SAMPLES = 3
    _SMOOTH = 0.70

    def __init__(self) -> None:
        self._history: list[tuple[float, float]] = []
        self._eta = 0.0
        self._start = time.time()

    def reset(self) -> None:
        self._history.clear()
        self._eta = 0.0
        self._start = time.time()

    def update(self, percent: float) -> float:
        now = time.time()
        if percent < 0.5 or percent >= 99.9:
            return 0.0

        self._history.append((now, percent))
        cutoff = now - self._WINDOW
        self._history = [(t, p) for t, p in self._history if t >= cutoff]

        if len(self._history) < self._MIN_SAMPLES:
            elapsed = now - self._start
            if elapsed > 2 and percent > 0.1:
                rate = percent / elapsed
                self._eta = (100.0 - percent) / max(rate, 1e-6)
            return self._eta

        oldest_t, oldest_p = self._history[0]
        newest_t, newest_p = self._history[-1]
        dt = newest_t - oldest_t
        dp = newest_p - oldest_p
        if dt < 1.0 or dp < 0.1:
            return self._eta

        speed = dp / dt
        raw = (100.0 - percent) / max(speed, 1e-6)

        elapsed = now - self._start
        if percent > 5:
            max_eta = elapsed * (100.0 / percent) * 1.5
            raw = min(raw, max_eta)

        if self._eta > 0:
            self._eta = raw * self._SMOOTH + self._eta * (1.0 - self._SMOOTH)
        else:
            self._eta = raw

        self._eta = max(1.0, min(self._eta, 86400.0))
        return self._eta
