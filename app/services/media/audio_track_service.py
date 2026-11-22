#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ffprobe based audio-track discovery for the audio swap workflow."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioTrackInfo:
    """One audio stream inside a media file."""

    path: str
    stream_index: int
    audio_index: int
    codec: str
    channels: int
    channel_layout: str
    sample_rate: int
    bit_rate: int
    language: str
    title: str
    duration: float

    def short_label(self) -> str:
        parts: list[str] = []
        if self.language and self.language not in ("und", ""):
            parts.append(self.language)
        if self.codec:
            parts.append(self.codec.upper())
        if self.channels:
            parts.append(self.channel_layout or f"{self.channels}ch")
        if self.title:
            parts.append(self.title)
        return " · ".join(parts) or f"Track {self.audio_index + 1}"


@dataclass(frozen=True)
class MediaProbeResult:
    duration: float
    audio_tracks: tuple[AudioTrackInfo, ...]
    has_video: bool = False


def _safe_int(value, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def probe_media(path: str, ffprobe_bin: str = "") -> MediaProbeResult:
    """Return duration and all audio streams of *path* (empty result on error)."""
    if not path:
        return MediaProbeResult(duration=0.0, audio_tracks=())

    try:
        result = subprocess.run(
            [
                ffprobe_bin or "ffprobe",
                "-v", "error",
                "-show_streams",
                "-show_format",
                "-of", "json",
                path,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if result.returncode != 0:
            return MediaProbeResult(duration=0.0, audio_tracks=())
        payload = json.loads(result.stdout or "{}")
    except Exception:
        return MediaProbeResult(duration=0.0, audio_tracks=())

    fmt = payload.get("format", {}) or {}
    duration = _safe_float(fmt.get("duration"), 0.0)

    tracks: list[AudioTrackInfo] = []
    audio_index = 0
    has_video = False
    for stream in payload.get("streams", []) or []:
        codec_type = str(stream.get("codec_type", ""))
        if codec_type == "video":
            disposition = stream.get("disposition", {}) or {}
            if _safe_int(disposition.get("attached_pic"), 0) != 1:
                has_video = True
            continue
        if codec_type != "audio":
            continue
        tags = stream.get("tags", {}) or {}
        tracks.append(
            AudioTrackInfo(
                path=path,
                stream_index=_safe_int(stream.get("index")),
                audio_index=audio_index,
                codec=str(stream.get("codec_name", "") or "").strip().lower(),
                channels=_safe_int(stream.get("channels"), 0),
                channel_layout=str(stream.get("channel_layout", "") or "").strip(),
                sample_rate=_safe_int(stream.get("sample_rate"), 0),
                bit_rate=_safe_int(stream.get("bit_rate"), 0),
                language=str(tags.get("language", "") or "").strip(),
                title=str(tags.get("title", "") or "").strip(),
                duration=_safe_float(stream.get("duration"), duration),
            )
        )
        audio_index += 1

    return MediaProbeResult(duration=duration, audio_tracks=tuple(tracks), has_video=has_video)
