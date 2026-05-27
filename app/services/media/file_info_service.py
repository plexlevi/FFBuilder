#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
file_info_service.py — FFmpeg/ffprobe alapú fájl metaadat kinyerő
==================================================================
Publikus API:
    extract_info(file_path, ffprobe, ffmpeg, include_loudness) → dict
    enrich_info_with_loudness(info, file_path, ffmpeg, progress_callback) → dict
"""

import json
import os
import re
import subprocess

from app.services.ffmpeg.manager import find_binaries


# Cache loudness results per unchanged file: (path, mtime_ns, size) -> metrics dict
_LOUDNESS_CACHE: dict[tuple[str, int, int], dict] = {}


def _parse_loudnorm_json(stderr_text: str) -> dict:
    """Extract loudnorm JSON block from ffmpeg stderr and return parsed dict."""
    m = re.search(r"\{\s*\"input_i\".*?\}", stderr_text, flags=re.S)
    if not m:
        return {}
    block = m.group(0)
    try:
        return json.loads(block)
    except Exception:
        return {}


def _parse_ffmpeg_timestamp(timestamp: str) -> float:
    """Convert HH:MM:SS.mmm timestamp into seconds."""
    try:
        hh, mm, ss = timestamp.split(":", 2)
        return (int(hh) * 3600) + (int(mm) * 60) + float(ss)
    except Exception:
        return 0.0


def _measure_loudness(
    file_path: str,
    ffmpeg: str,
    progress_callback=None,
    duration_seconds: float | None = None,
) -> dict:
    """
    Fast loudness analysis for file-info display using ebur128 summary.
    Returns keys: lufs, lra, true_peak, loudness_gate, loudnorm_offset.
    """
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-i", file_path,
        "-map", "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-af", "ebur128=peak=true",
        "-f", "null",
        "-",
    ]
    try:
        if callable(progress_callback):
            progress_callback(0.0)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        duration = float(duration_seconds or 0.0)
        stderr_parts: list[str] = []
        last_reported = 0.0

        if proc.stderr is not None:
            while True:
                line = proc.stderr.readline()
                if not line:
                    if proc.poll() is not None:
                        break
                    continue

                stderr_parts.append(line)

                if duration <= 0:
                    continue

                progress_seconds = 0.0
                m_time = re.search(r"time=(\d{2}:\d{2}:\d{2}(?:\.\d+)?)", line)
                if m_time:
                    progress_seconds = _parse_ffmpeg_timestamp(m_time.group(1))
                else:
                    m_t = re.search(r"\bt:\s*([\d.]+)", line)
                    if m_t:
                        try:
                            progress_seconds = float(m_t.group(1))
                        except Exception:
                            progress_seconds = 0.0

                if progress_seconds > 0 and callable(progress_callback):
                    frac = max(0.0, min(0.99, progress_seconds / duration))
                    if frac - last_reported >= 0.005:
                        last_reported = frac
                        progress_callback(frac)

        proc.wait(timeout=1800)
        stderr_text = "".join(stderr_parts)
        if "Summary:" not in stderr_text:
            return {}

        summary = stderr_text[stderr_text.rfind("Summary:"):]

        i_m = re.search(r"\bI:\s*([\-\d.]+)\s+LUFS", summary)
        lra_m = re.search(r"\bLRA:\s*([\d.]+)\s+LU", summary)
        tp_m = re.search(r"\bPeak:\s*([\-\d.]+)\s+dBFS", summary)
        thr_m = re.search(r"Integrated loudness:\s*.*?Threshold:\s*([\-\d.]+)\s+LUFS", summary, flags=re.S)

        if not (i_m or lra_m or tp_m or thr_m):
            return {}

        def _m(group_match) -> str:
            if not group_match:
                return "unknown"
            try:
                return f"{float(group_match.group(1)):.1f}"
            except Exception:
                return str(group_match.group(1)).strip()

        return {
            "lufs": _m(i_m),
            "lra": _m(lra_m),
            "true_peak": _m(tp_m),
            "loudness_gate": _m(thr_m),
            "loudnorm_offset": "unknown",
        }
    except Exception:
        return {}
    finally:
        if callable(progress_callback):
            progress_callback(1.0)


def _get_loudness_cached(
    file_path: str,
    ffmpeg: str,
    progress_callback=None,
    duration_seconds: float | None = None,
) -> dict:
    """Return cached loudness metrics for unchanged file, otherwise measure and cache."""
    try:
        st = os.stat(file_path)
        key = (file_path, int(st.st_mtime_ns), int(st.st_size))
    except Exception:
        return _measure_loudness(
            file_path,
            ffmpeg,
            progress_callback=progress_callback,
            duration_seconds=duration_seconds,
        )

    cached = _LOUDNESS_CACHE.get(key)
    if cached is not None:
        if callable(progress_callback):
            progress_callback(1.0)
        return cached

    measured = _measure_loudness(
        file_path,
        ffmpeg,
        progress_callback=progress_callback,
        duration_seconds=duration_seconds,
    )
    _LOUDNESS_CACHE[key] = measured

    # Simple cap to avoid unbounded memory usage in long sessions.
    if len(_LOUDNESS_CACHE) > 256:
        try:
            first_key = next(iter(_LOUDNESS_CACHE.keys()))
            _LOUDNESS_CACHE.pop(first_key, None)
        except Exception:
            pass

    return measured


# ---------------------------------------------------------------------------
# Step 3 — extract metadata with ffprobe
# ---------------------------------------------------------------------------

def _apply_no_audio_state(info: dict) -> None:
    """Set explicit metadata values for files without audio streams."""
    no_audio_msg = "N/A (nincs audio stream)"
    info["audio_bitrate"] = no_audio_msg
    info["audio_sample_rate"] = no_audio_msg
    info["audio_bit_depth"] = no_audio_msg
    info["audio_channels"] = no_audio_msg
    info["audio_channel_layout"] = no_audio_msg
    info["lufs"] = no_audio_msg
    info["lra"] = no_audio_msg
    info["true_peak"] = no_audio_msg
    info["loudness_gate"] = no_audio_msg
    info["loudnorm_ready"] = "no (nincs audio stream)"
    info["error"] = "Nincs audio stream, loudnorm nem futtatható"


def _extract_hdr_metadata(stream: dict) -> dict:
    """Extract HDR-related metadata from ffprobe video stream fields."""
    out = {
        "hdr": "SDR",
        "color_primaries": "unknown",
        "hdr_max_cll": "unknown",
        "hdr_max_fall": "unknown",
        "hdr_mastering_display": "unknown",
    }

    color_primaries = str(stream.get("color_primaries", "") or "").strip()
    color_transfer = str(stream.get("color_transfer", "") or "").strip().lower()
    pix_fmt = str(stream.get("pix_fmt", "") or "").strip().lower()

    if color_primaries:
        out["color_primaries"] = color_primaries

    side_data = stream.get("side_data_list", [])
    has_mastering = False
    has_content_light = False

    if isinstance(side_data, list):
        for entry in side_data:
            if not isinstance(entry, dict):
                continue

            side_type = str(entry.get("side_data_type", "") or "").lower()

            if "mastering display metadata" in side_type:
                has_mastering = True
                out["hdr_mastering_display"] = "present"

            if "content light level metadata" in side_type:
                has_content_light = True
                max_cll = entry.get("max_content")
                max_fall = entry.get("max_average")
                if max_cll not in (None, ""):
                    out["hdr_max_cll"] = str(max_cll)
                if max_fall not in (None, ""):
                    out["hdr_max_fall"] = str(max_fall)

            if "dolby vision" in side_type or "dovi" in side_type:
                out["hdr"] = "Dolby Vision"
            elif "smpte2094" in side_type or "dynamic hdr" in side_type:
                out["hdr"] = "HDR10+"

    if out["hdr"] == "SDR":
        if color_transfer in {"smpte2084", "pq"}:
            out["hdr"] = "HDR10"
        elif color_transfer == "arib-std-b67":
            out["hdr"] = "HLG"
        elif has_mastering or has_content_light:
            out["hdr"] = "HDR"
        elif "2020" in color_primaries.lower() and ("10" in pix_fmt or "12" in pix_fmt):
            out["hdr"] = "HDR"

    return out


def enrich_info_with_loudness(
    info: dict,
    file_path: str,
    ffmpeg: str | None = None,
    progress_callback=None,
) -> dict:
    """Adds loudness metrics to an already extracted metadata dict."""
    out = dict(info)

    if out.get("audio") == "no audio":
        _apply_no_audio_state(out)
        return out

    ffmpeg_bin = ffmpeg or find_binaries()[0]
    if ffmpeg_bin:
        loud = _get_loudness_cached(
            file_path,
            ffmpeg_bin,
            progress_callback=progress_callback,
            duration_seconds=float(out.get("__duration_seconds", 0.0) or 0.0),
        )
        if loud:
            out["lufs"] = loud.get("lufs", "unknown")
            out["lra"] = loud.get("lra", "unknown")
            out["true_peak"] = loud.get("true_peak", "unknown")
            out["loudness_gate"] = loud.get("loudness_gate", "unknown")
            out["loudnorm_offset"] = loud.get("loudnorm_offset", "unknown")

    return out


def extract_info(
    file_path: str,
    ffprobe: str,
    ffmpeg: str | None = None,
    include_loudness: bool = True,
) -> dict:
    """Runs ffprobe on a single file and returns a metadata dict."""
    info = {
        "path":             file_path,
        "filename":         os.path.basename(file_path),
        "size":             "unknown",
        "duration":         "unknown",
        "resolution":       "unknown",
        "codec":            "unknown",
        "profile":          "unknown",
        "level":            "unknown",
        "bit_depth":        "unknown",
        "fps":              "unknown",
        "aspect_ratio":     "unknown",
        "color":            "unknown",
        "color_space":      "unknown",
        "color_transfer":   "unknown",
        "color_primaries":  "unknown",
        "hdr":              "SDR",
        "hdr_max_cll":      "unknown",
        "hdr_max_fall":     "unknown",
        "hdr_mastering_display": "unknown",
        "field_order":      "unknown",
        "nb_frames":        "unknown",
        "format":           "unknown",
        "video_bitrate":    "unknown",
        "audio":            "no audio",
        "audio_bitrate":    "unknown",
        "audio_sample_rate": "unknown",
        "audio_channels":    "unknown",
        "audio_channel_layout": "unknown",
        "audio_sample_fmt":  "unknown",
        "audio_bit_depth":   "unknown",
        "audio_profile":     "unknown",
        "audio_language":    "unknown",
        "loudnorm_ready":    "no",
        "lufs":             "unknown",
        "lra":              "unknown",
        "true_peak":        "unknown",
        "loudness_gate":    "unknown",
        "loudnorm_offset":  "unknown",
        "container_format": "unknown",
        "bitrate":          "unknown",
        "__duration_seconds": 0.0,
    }

    # File size (no ffprobe needed)
    try:
        size_bytes = os.path.getsize(file_path)
        if size_bytes < 1024 ** 3:
            info["size"] = f"{size_bytes / 1024 ** 2:.1f} MB"
        else:
            info["size"] = f"{size_bytes / 1024 ** 3:.2f} GB"
    except OSError:
        pass

    # Run ffprobe
    cmd = [
        ffprobe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        file_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        probe = json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        info["error"] = "ffprobe timed out"
        return info
    except subprocess.CalledProcessError as e:
        info["error"] = f"ffprobe failed: {e}"
        return info
    except json.JSONDecodeError as e:
        info["error"] = f"ffprobe output parse error: {e}"
        return info

    # --- Format / container ---
    fmt = probe.get("format", {})
    fmt_name = fmt.get("format_name", "")
    _fmt_map = {
        "matroska": "Matroska", "webm": "Matroska", "mkv": "Matroska",
        "mp4": "MP4", "avi": "AVI", "mov": "QuickTime",
    }
    info["container_format"] = next(
        (v for k, v in _fmt_map.items() if k in fmt_name),
        fmt_name.upper() or "unknown"
    )

    # Duration
    try:
        dur = float(fmt.get("duration", 0))
        m, s = int(dur // 60), int(dur % 60)
        info["duration"] = f"{m} min {s} s"
        info["__duration_seconds"] = dur
    except (ValueError, TypeError):
        pass

    # Bitrate
    try:
        br = int(fmt.get("bit_rate", 0))
        info["bitrate"] = f"{br // 1000} kb/s"
    except (ValueError, TypeError):
        pass

    # --- Streams ---
    for stream in probe.get("streams", []):
        codec_type = stream.get("codec_type", "")

        if codec_type == "video" and info["codec"] == "unknown":
            info["codec"] = stream.get("codec_name", "unknown").upper()

            w = stream.get("width", 0)
            h = stream.get("height", 0)
            if w and h:
                info["resolution"] = f"{w}x{h}"

            # FPS
            fps_raw = stream.get("r_frame_rate", "")
            if fps_raw and "/" in fps_raw:
                try:
                    num, den = fps_raw.split("/")
                    fps_val = float(num) / float(den)
                    info["fps"] = f"{fps_val:.3f}".rstrip("0").rstrip(".")
                except (ValueError, ZeroDivisionError):
                    pass

            # Display aspect ratio
            dar = stream.get("display_aspect_ratio", "")
            info["aspect_ratio"] = dar if dar and dar != "0:1" else "unknown"

            # Pixel format
            pix = stream.get("pix_fmt", "")
            if pix:
                info["color"] = pix

            info["format"] = stream.get("codec_long_name", info["codec"])

            # Profile
            profile = stream.get("profile", "")
            if profile and profile.lower() != "unknown":
                info["profile"] = profile

            # Level
            level_raw = stream.get("level", -1)
            if isinstance(level_raw, int) and level_raw > 0:
                codec_lower = stream.get("codec_name", "").lower()
                if codec_lower in ("h264", "avc"):
                    info["level"] = f"{level_raw / 10:.1f}"
                elif codec_lower in ("hevc", "h265"):
                    info["level"] = f"{level_raw / 30:.1f}"
                else:
                    info["level"] = str(level_raw)

            # Bit depth
            bits = stream.get("bits_per_raw_sample") or stream.get("bits_per_coded_sample")
            if bits and str(bits) not in ("0", ""):
                info["bit_depth"] = f"{bits} bit"

            # Video stream bitrate
            vbr = stream.get("bit_rate", "")
            if vbr:
                try:
                    info["video_bitrate"] = f"{int(vbr) // 1000} kb/s"
                except (ValueError, TypeError):
                    pass

            # Color space
            cs = stream.get("color_space", "")
            if cs:
                info["color_space"] = cs

            # Color transfer
            ct = stream.get("color_transfer", "")
            if ct:
                info["color_transfer"] = ct

            # Color primaries
            cp = stream.get("color_primaries", "")
            if cp:
                info["color_primaries"] = cp

            # HDR metadata (side data + transfer/primaries heuristics)
            info.update(_extract_hdr_metadata(stream))

            # Field order
            fo = stream.get("field_order", "")
            if fo:
                info["field_order"] = fo

            # Frame count
            nb = stream.get("nb_frames", "")
            if nb:
                info["nb_frames"] = nb

        elif codec_type == "audio" and info["audio"] == "no audio":
            acodec      = stream.get("codec_name", "").upper()
            sample_rate = stream.get("sample_rate", "")
            ch_layout   = stream.get("channel_layout", "")
            channels    = str(stream.get("channels", ""))
            sample_fmt  = stream.get("sample_fmt", "")
            a_profile   = stream.get("profile", "")

            tags = stream.get("tags", {}) if isinstance(stream.get("tags", {}), dict) else {}
            language = tags.get("language", "")

            # Audio bit depth (ha expliciten elérhető)
            a_bits = stream.get("bits_per_raw_sample") or stream.get("bits_per_coded_sample")
            if (not a_bits or str(a_bits) in ("", "0")) and sample_fmt:
                fmt_lower = str(sample_fmt).lower()
                if "s16" in fmt_lower:
                    a_bits = "16"
                elif "s24" in fmt_lower:
                    a_bits = "24"
                elif "s32" in fmt_lower or "flt" in fmt_lower:
                    a_bits = "32"

            audio_parts = [x for x in [
                acodec,
                f"{sample_rate} Hz" if sample_rate else "",
                ch_layout or channels,
            ] if x]
            info["audio"] = ", ".join(audio_parts) if audio_parts else "unknown"

            if sample_rate:
                info["audio_sample_rate"] = f"{sample_rate} Hz"
            if channels:
                info["audio_channels"] = channels
            if ch_layout:
                info["audio_channel_layout"] = ch_layout
            if sample_fmt:
                info["audio_sample_fmt"] = sample_fmt
            if a_bits and str(a_bits) not in ("", "0"):
                info["audio_bit_depth"] = f"{a_bits} bit"
            if a_profile and a_profile.lower() != "unknown":
                info["audio_profile"] = a_profile
            if language:
                info["audio_language"] = language

            # Audio stream bitrate
            abr = stream.get("bit_rate", "")
            if abr:
                try:
                    info["audio_bitrate"] = f"{int(abr) // 1000} kb/s"
                except (ValueError, TypeError):
                    pass

            # Loudnorm előkészítéshez legfontosabb input paraméterek megléte
            if sample_rate and channels:
                info["loudnorm_ready"] = "yes"
            else:
                info["loudnorm_ready"] = "partial"

    if include_loudness:
        info = enrich_info_with_loudness(info, file_path, ffmpeg=ffmpeg)
    elif info["audio"] == "no audio":
        _apply_no_audio_state(info)

    return info



