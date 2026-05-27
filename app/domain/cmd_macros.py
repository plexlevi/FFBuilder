"""cmd_macros – FFmpeg parancssablon helyőrzők feloldása.

Támogatott tokenek:
    {input}              → idézett bemeneti fájl elérési útja
    {output}             → idézett kimeneti fájl elérési útja
    {output}.ext         → {output} feloldása, az .ext felülírja a formátumot
    {map_all: <params>}  → minden hangcsatorna külön mono WAV-ba (-map_channel)
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def quote_if_needed(value: str) -> str:
    """Idézőjelbe teszi az értéket, ha szóközt, idézőjelet vagy backslash-t tartalmaz."""
    if re.search(r'[\s"\'\\]', value):
        return '"' + value.replace('"', '\\"') + '"'
    return value


def expand_input(cmd: str, input_path: str) -> str:
    """`{input}` → idézett bemeneti útvonal. Ha üres, a token marad."""
    if input_path:
        return cmd.replace("{input}", quote_if_needed(input_path))
    return cmd


def expand_output(cmd: str, output_path: str, fallback_fmt: str = "mp4") -> str:
    """`{output}[.ext]` → idézett kimeneti útvonal, vagy `{output}.<fallback_fmt>`.

    Ha az output_path üres, a token megmarad a fallback formátummal kiegészítve,
    hogy a parancs-előnézetben látható legyen a várható kiterjesztés.
    """
    if output_path:
        return re.sub(r"\{output\}(\.\w+)?", quote_if_needed(output_path), cmd)
    return re.sub(r"\{output\}(\.\w+)?", f"{{output}}.{fallback_fmt}", cmd)


def get_audio_channels(input_path: str, ffprobe_bin: str) -> list[tuple[int, int]]:
    """Visszaadja a bemeneti fájl összes hangcsatornáját (stream_idx, ch_idx) párokban."""
    if not input_path or not ffprobe_bin:
        return []
    try:
        result = subprocess.run(
            [
                ffprobe_bin,
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=index,channels",
                "-of", "json",
                input_path,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        if result.returncode != 0:
            return []
        payload = json.loads(result.stdout or "{}")
        channels: list[tuple[int, int]] = []
        for stream in payload.get("streams", []):
            stream_idx = int(stream.get("index", 0) or 0)
            num_channels = int(stream.get("channels", 1) or 1)
            for ch_idx in range(num_channels):
                channels.append((stream_idx, ch_idx))
        return channels
    except Exception:
        return []


def expand_map_all(cmd: str, input_path: str, ffprobe_bin: str) -> str:
    """`{map_all: <extra>}` → `-map_channel` sor minden hangcsatornához.

    Példa: `{map_all: -c:a pcm_s24le -ar 48000}`
    Eredmény (3 csatorna esetén):
        -map_channel 0.0.0 -c:a pcm_s24le -ar 48000 "audio1.wav"
        -map_channel 0.0.1 -c:a pcm_s24le -ar 48000 "audio2.wav"
        -map_channel 0.0.2 -c:a pcm_s24le -ar 48000 "audio3.wav"
    """
    def _replace(match: re.Match) -> str:
        extra_params = match.group(1).strip()
        if not input_path:
            return match.group(0)

        channels = get_audio_channels(input_path, ffprobe_bin)
        if not channels:
            return ""

        p = Path(input_path)
        stem = p.stem or "audio"
        directory = p.parent

        chunks: list[str] = []
        for n, (stream_idx, ch_idx) in enumerate(channels, start=1):
            out_file = quote_if_needed(str(directory / f"{stem}_audio{n}.wav"))
            part = f"-map_channel 0.{stream_idx}.{ch_idx}"
            if extra_params:
                part += f" {extra_params}"
            part += f" {out_file}"
            chunks.append(part)
        return " ".join(chunks)

    return re.sub(r"\{map_all\s*:\s*([^}]+)\}", _replace, cmd)


def expand_all(
    cmd: str,
    *,
    input_path: str = "",
    output_path: str = "",
    fallback_fmt: str = "mp4",
    ffprobe_bin: str = "",
) -> str:
    """Minden sablon-tokent felold a helyes sorrendben."""
    cmd = expand_input(cmd, input_path)
    cmd = expand_output(cmd, output_path, fallback_fmt)
    cmd = expand_map_all(cmd, input_path, ffprobe_bin)
    return cmd
