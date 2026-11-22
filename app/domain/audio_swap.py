#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Audio swap job model and ffmpeg command builder.

The workflow replaces (or extends) the audio tracks of a video with tracks
coming from external audio files or from other media files, optionally
re-encoding the video in the same pass.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from app.domain import cmd_macros


AUDIO_CODEC_COPY = "copy"
AUDIO_CODEC_AAC = "aac"
AUDIO_CODEC_AC3 = "ac3"
AUDIO_CODEC_PCM = "pcm_s24le"
AUDIO_CODEC_MP3 = "libmp3lame"
AUDIO_CODEC_OPUS = "libopus"

# Lossless / uncompressed codecs that make no sense with -b:a.
_BITRATE_LESS_CODECS = {AUDIO_CODEC_PCM, "pcm_s16le", "pcm_s32le", "flac"}

# Codecs that are not safe to copy into an MP4/MOV container.
_MP4_UNSAFE_COPY_CODECS = {
    "pcm_s16le",
    "pcm_s24le",
    "pcm_s32le",
    "pcm_f32le",
    "pcm_f64le",
    "flac",
    "vorbis",
    "opus",
    "dts",
    "truehd",
}

# Encoded audio codecs that do not belong in an MP4/MOV container.
_MP4_UNSAFE_ENCODE_CODECS = {
    "pcm_s16le",
    "pcm_s24le",
    "pcm_s32le",
    "flac",
    "libvorbis",
    "libopus",
    "dts",
}

_MOV_UNSAFE_ENCODE_CODECS = {
    "flac",
    "libvorbis",
    "libopus",
    "dts",
}


@dataclass(frozen=True)
class VideoProfile:
    key: str
    label: str
    args: tuple[str, ...]


VIDEO_PROFILE_COPY = "copy"

VIDEO_PROFILES: dict[str, VideoProfile] = {
    VIDEO_PROFILE_COPY: VideoProfile(
        key=VIDEO_PROFILE_COPY,
        label="Copy video (no re-encode)",
        args=("-c:v", "copy"),
    ),
    "h264_source": VideoProfile(
        key="h264_source",
        label="H.264 (source resolution)",
        args=(
            "-c:v", "libx264", "-crf", "20", "-preset", "medium",
            "-pix_fmt", "yuv420p",
        ),
    ),
    "h264_1080p": VideoProfile(
        key="h264_1080p",
        label="H.264 1080p",
        args=(
            "-c:v", "libx264", "-crf", "20", "-preset", "medium",
            "-vf", "scale=-2:1080", "-pix_fmt", "yuv420p",
        ),
    ),
    "h264_720p": VideoProfile(
        key="h264_720p",
        label="H.264 720p",
        args=(
            "-c:v", "libx264", "-crf", "21", "-preset", "medium",
            "-vf", "scale=-2:720", "-pix_fmt", "yuv420p",
        ),
    ),
    "hevc_1080p": VideoProfile(
        key="hevc_1080p",
        label="HEVC 1080p",
        args=(
            "-c:v", "libx265", "-crf", "22", "-preset", "medium",
            "-vf", "scale=-2:1080", "-tag:v", "hvc1", "-pix_fmt", "yuv420p",
        ),
    ),
}


@dataclass
class AudioSlot:
    """One output audio track of a target video."""

    source_path: str
    source_audio_index: int = 0
    source_codec: str = ""
    source_label: str = ""
    is_original: bool = False
    codec: str = AUDIO_CODEC_AAC
    bitrate: str = "256k"
    channels: int | None = 2
    sample_rate: int | None = 48000
    normalize: bool = False
    language: str = ""
    title: str = ""
    is_default: bool = False

    def clone(self) -> "AudioSlot":
        return replace(self)

    def summary(self, index: int) -> str:
        name = self.source_label or Path(self.source_path).name or "?"
        if self.is_original:
            name = f"{name} (original)"
        details: list[str] = []
        if self.codec == AUDIO_CODEC_COPY:
            details.append("copy")
        else:
            details.append(self.codec.upper())
            if self.bitrate and self.codec not in _BITRATE_LESS_CODECS:
                details.append(self.bitrate)
        if self.normalize:
            details.append("R128")
        if self.language:
            details.append(self.language)
        if self.is_default:
            details.append("default")
        return f"{index}. {name} · " + " · ".join(details)


@dataclass
class AudioSwapJob:
    target_path: str
    output_path: str
    slots: list[AudioSlot]
    video_profile: str = VIDEO_PROFILE_COPY
    keep_subtitles: bool = False
    fit_duration: bool = True
    target_duration: float = 0.0
    output_format: str = "mp4"
    ffmpeg_bin: str = "ffmpeg"


def slot_for_track(
    track,
    *,
    is_original: bool,
    default_codec: str | None = None,
) -> AudioSlot:
    """Create a sensible default slot from an AudioTrackInfo object."""
    codec = default_codec or (AUDIO_CODEC_COPY if is_original else AUDIO_CODEC_AAC)
    if codec == AUDIO_CODEC_COPY:
        bitrate = ""
        sample_rate = None
        channels = None
    else:
        bitrate = "384k" if int(getattr(track, "channels", 0) or 0) > 2 else "256k"
        sample_rate = 48000
        channels = None
    label = Path(track.path).name
    if int(getattr(track, "audio_index", 0) or 0) > 0:
        label = f"{label} [{track.audio_index + 1}]"
    return AudioSlot(
        source_path=track.path,
        source_audio_index=int(track.audio_index),
        source_codec=str(getattr(track, "codec", "") or "").lower(),
        source_label=label,
        is_original=is_original,
        codec=codec,
        bitrate=bitrate,
        sample_rate=sample_rate,
        channels=channels,
        language=str(getattr(track, "language", "") or ""),
        title=str(getattr(track, "title", "") or ""),
    )


def copy_codec_compatible(source_codec: str, output_format: str) -> bool:
    fmt = (output_format or "").strip().lower().lstrip(".")
    codec = (source_codec or "").strip().lower()
    if fmt in ("mp4", "mov", "m4v"):
        return codec not in _MP4_UNSAFE_COPY_CODECS
    return True


def _quote(value: str) -> str:
    return cmd_macros.quote_if_needed(value)


def _audio_args(slot: AudioSlot, out_index: int, pad_audio: bool) -> list[str]:
    args: list[str] = []

    if slot.codec == AUDIO_CODEC_COPY:
        args += [f"-c:a:{out_index}", "copy"]
    else:
        args += [f"-c:a:{out_index}", slot.codec]
        if slot.bitrate and slot.codec not in _BITRATE_LESS_CODECS:
            args += [f"-b:a:{out_index}", slot.bitrate]
        if slot.sample_rate:
            args += [f"-ar:a:{out_index}", str(int(slot.sample_rate))]
        if slot.channels:
            args += [f"-ac:a:{out_index}", str(int(slot.channels))]

        filters: list[str] = []
        if slot.normalize:
            filters.append("loudnorm=I=-18:TP=-1.5:LRA=11")
        if pad_audio:
            filters.append("apad")
        if filters:
            args += [f"-filter:a:{out_index}", ",".join(filters)]

    if slot.language:
        language = slot.language.strip()
        if language and language.lower() != "und":
            args += [f"-metadata:s:a:{out_index}", f"language={language}"]
    if slot.title:
        args += [f"-metadata:s:a:{out_index}", f"title={_quote(slot.title.strip())}"]

    args += [f"-disposition:a:{out_index}", "default" if slot.is_default else "0"]
    return args


def build_audio_swap_command(job: AudioSwapJob) -> str:
    """Build a single ffmpeg command for one target video."""
    if not job.target_path:
        raise ValueError("Missing target video path.")
    if not job.output_path:
        raise ValueError("Missing output path.")
    if not job.slots:
        raise ValueError("No audio tracks assigned.")

    target_path = str(job.target_path)
    source_indices: dict[str, int] = {target_path: 0}

    args: list[str] = [
        _quote(job.ffmpeg_bin or "ffmpeg"),
        "-y",
        "-nostdin",
        "-i", _quote(target_path),
    ]

    # Register each unique external source only once.
    for slot in job.slots:
        path = str(slot.source_path or "")
        if not path or slot.is_original or path == target_path:
            continue
        if path in source_indices:
            continue
        source_indices[path] = len(source_indices)
        args += ["-i", _quote(path)]

    args += ["-map", "0:v:0"]

    profile = VIDEO_PROFILES.get(job.video_profile) or VIDEO_PROFILES[VIDEO_PROFILE_COPY]
    args += list(profile.args)

    pad_audio = bool(job.fit_duration and job.target_duration > 0)
    for out_index, slot in enumerate(job.slots):
        if slot.is_original or str(slot.source_path) == target_path:
            input_index = 0
        else:
            input_index = source_indices[str(slot.source_path)]
        args += ["-map", f"{input_index}:a:{int(slot.source_audio_index)}"]
        args += _audio_args(slot, out_index, pad_audio)

    output_format = (job.output_format or Path(job.output_path).suffix.lstrip(".")).lower()

    if job.keep_subtitles:
        subtitle_codec = "copy" if output_format == "mkv" else "mov_text"
        args += ["-map", "0:s?", "-c:s", subtitle_codec]

    args += ["-map_chapters", "0", "-map_metadata", "0"]

    if job.fit_duration:
        if job.target_duration > 0:
            args += ["-t", f"{float(job.target_duration):.3f}"]
        else:
            args += ["-shortest"]

    if output_format in ("mp4", "mov", "m4v"):
        args += ["-movflags", "+faststart"]

    args += ["-max_muxing_queue_size", "1024"]
    args += [_quote(str(job.output_path))]
    return " ".join(args)


def validate_audio_swap_job(job: AudioSwapJob) -> str | None:
    """Return a human readable error, or None when the job looks valid."""
    if not job.slots:
        return "No audio tracks assigned."
    if not job.output_path:
        return "Missing output path."
    if Path(job.output_path).resolve() == Path(job.target_path).resolve():
        return "The output path would overwrite the original video."
    fmt = (job.output_format or "").strip().lower().lstrip(".")
    for slot in job.slots:
        if slot.codec == AUDIO_CODEC_COPY:
            if not copy_codec_compatible(slot.source_codec, fmt):
                codec = (slot.source_codec or "unknown").upper()
                return (
                    f"{codec} audio cannot be copied into a {fmt.upper()} container. "
                    "Choose AAC for that track or use MKV output."
                )
            continue

        unsafe = (
            (fmt in ("mp4", "m4v") and slot.codec in _MP4_UNSAFE_ENCODE_CODECS)
            or (fmt == "mov" and slot.codec in _MOV_UNSAFE_ENCODE_CODECS)
        )
        if unsafe:
            return (
                f"{slot.codec.upper()} audio cannot be encoded into a {fmt.upper()} container. "
                "Choose AAC, AC3 or MP3, or use MKV output."
            )
    return None
