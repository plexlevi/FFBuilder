"""cmd_macros – FFmpeg parancssablon helyőrzők feloldása.

Támogatott tokenek:
    {input}              → idézett bemeneti fájl elérési útja
    {output}             → idézett kimeneti fájl elérési útja
    {output}.ext         → {output} feloldása, az .ext felülírja a formátumot
    {map_channel: <params>}  → minden hangcsatorna külön mono WAV-ba
                               (modern: -filter_complex channelsplit + -map)
    {map_streams: <params>}   → minden hangsáv külön fájlba, kiosztás megőrzésével
                               (kiterjesztés a -c:a értékéből automatikusan)
    {recode_audio: <params>}  → a videó összes hangsávját átkonvertálja, a videó érintetlen marad
                               pl. {recode_audio: -c:a aac -b:a 256k -ar 48000}
                               minden sávhoz explicit -map 0:a:N, nincs -c:v
    {compat_audio}            → minden hangsáv Apple/Chromecast-kompatibilissé tétele
                               aac_at (mac) / aac + AC3 surround, explicit -ac, disposition
    {compat_subs}             → feliratok mov_text-ként, per-sáv title + language metaadat
"""

from __future__ import annotations

import json
import platform as _platform
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


# Csatornaszám → standard FFmpeg layout név fallback (ha ffprobe nem adja meg)
_CHANNEL_COUNT_TO_LAYOUT: dict[int, str] = {
    1: "mono",
    2: "stereo",
    3: "2.1",
    4: "4.0",
    5: "5.0",
    6: "5.1",
    7: "6.1",
    8: "7.1",
}


def get_audio_channels(input_path: str, ffprobe_bin: str) -> list[tuple[int, int, str, str]]:
    """Visszaadja a bemeneti fájl hangsávjait: (audio_idx, csatornaszám, channel_layout, codec_name)."""
    if not input_path or not ffprobe_bin:
        return []
    try:
        result = subprocess.run(
            [
                ffprobe_bin,
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=index,channels,channel_layout,codec_name",
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
        streams: list[tuple[int, int, str, str]] = []
        # audio_idx = audio-relatív sorrend (0, 1, 2, …) — ez kell a filter_complex [0:a:N]-hez,
        # NEM a globális stream index, amit ffprobe az "index" mezőben ad vissza.
        for audio_idx, stream in enumerate(payload.get("streams", [])):
            num_channels = int(stream.get("channels", 1) or 1)
            layout = str(stream.get("channel_layout", "") or "").strip()
            if not layout:
                layout = _CHANNEL_COUNT_TO_LAYOUT.get(num_channels, f"{num_channels}c")
            codec_name = str(stream.get("codec_name", "") or "").strip().lower()
            streams.append((audio_idx, num_channels, layout, codec_name))
        return streams
    except Exception:
        return []


def expand_map_channel(cmd: str, input_path: str, ffprobe_bin: str) -> str:
    """`{map_channel: <extra>}` → -filter_complex channelsplit + -map per csatorna.

    A deprecated -map_channel modern kiváltója.

    Példa: `{map_channel: -c:a pcm_s24le -ar 48000}` (1 stereo stream):
        -filter_complex "[0:a:0]channelsplit=channel_layout=stereo[a0c0][a0c1]"
        -map "[a0c0]" -c:a pcm_s24le -ar 48000 "audio1.wav"
        -map "[a0c1]" -c:a pcm_s24le -ar 48000 "audio2.wav"
    """
    def _replace(match: re.Match) -> str:
        extra_params = match.group(1).strip()
        if not input_path:
            return match.group(0)

        streams = get_audio_channels(input_path, ffprobe_bin)
        if not streams:
            return ""

        p = Path(input_path)
        stem = p.stem or "audio"
        directory = p.parent

        filter_parts: list[str] = []
        output_tags: list[str] = []
        for stream_idx, nb_channels, layout, _codec in streams:
            tags = [f"a{stream_idx}c{i}" for i in range(nb_channels)]
            tags_str = "".join(f"[{t}]" for t in tags)
            filter_parts.append(
                f"[0:a:{stream_idx}]channelsplit=channel_layout={layout}{tags_str}"
            )
            output_tags.extend(tags)

        filter_complex = ";".join(filter_parts)
        chunks: list[str] = [f'-filter_complex "{filter_complex}"']

        for n, tag in enumerate(output_tags, start=1):
            out_file = quote_if_needed(str(directory / f"{stem}_audio{n}.wav"))
            part = f'-map "[{tag}]"'
            if extra_params:
                part += f" {extra_params}"
            part += f" {out_file}"
            chunks.append(part)

        return " ".join(chunks)

    return re.sub(r"\{map_channel\s*:\s*([^}]+)\}", _replace, cmd)


# Codec neve → kimeneti fájlkiterjesztés
_CODEC_TO_EXT: dict[str, str] = {
    "aac": "aac",
    "libfdk_aac": "aac",
    "libmp3lame": "mp3",
    "mp3": "mp3",
    "ac3": "ac3",
    "eac3": "eac3",
    "flac": "flac",
    "libopus": "opus",
    "opus": "opus",
    "libvorbis": "ogg",
    "dts": "dts",
    "truehd": "thd",
    "copy": "mka",
}


def _ext_from_params(extra_params: str) -> str:
    """A -c:a értékéből meghatározza a kimeneti fájlkiterjesztést."""
    m = re.search(r'-c:a\s+(\S+)', extra_params)
    if m:
        codec = m.group(1).lower()
        if codec.startswith("pcm_"):
            return "wav"
        return _CODEC_TO_EXT.get(codec, "aac")
    return "aac"


def expand_map_streams(cmd: str, input_path: str, ffprobe_bin: str) -> str:
    """`{map_streams: <extra>}` → -map per audio streamenként, külön fájlba.

    A csatornakiosztást megőrzi; codec és egyéb paraméterek az extra részből.
    A kimeneti fájlkiterjesztést a -c:a értékéből automatikusan határozza meg.

    Példa: `{map_streams: -c:a aac -b:a 256k -ar 48000}` (2 stream esetén):
        -map 0:a:0 -c:a aac -b:a 256k -ar 48000 "film_audio1.aac"
        -map 0:a:1 -c:a aac -b:a 256k -ar 48000 "film_audio2.aac"
    """
    def _replace(match: re.Match) -> str:
        extra_params = match.group(1).strip()
        if not input_path:
            return match.group(0)

        streams = get_audio_channels(input_path, ffprobe_bin)
        if not streams:
            return ""

        p = Path(input_path)
        stem = p.stem or "audio"
        directory = p.parent
        ext = _ext_from_params(extra_params)

        chunks: list[str] = []
        for audio_idx, _nb_channels, _layout, _codec in streams:
            out_file = quote_if_needed(str(directory / f"{stem}_audio{audio_idx + 1}.{ext}"))
            part = f"-map 0:a:{audio_idx}"
            if extra_params:
                part += f" {extra_params}"
            part += f" {out_file}"
            chunks.append(part)

        return " ".join(chunks)

    return re.sub(r"\{map_streams\s*:\s*([^}]+)\}", _replace, cmd)


def expand_recode_audio(cmd: str, input_path: str, ffprobe_bin: str) -> str:
    """`{recode_audio: <extra>}` → minden hangsávhoz explicit -map 0:a:N + a megadott paraméterek.

    Nem ad hozzá videó-kódolót; a sablon kezeli a videót.

    Példa: `{recode_audio: -c:a aac -b:a 256k -ar 48000}` (2 hangsáv esetén):
        -map 0:a:0 -c:a:0 aac -b:a 256k -ar 48000 -map 0:a:1 -c:a:1 aac -b:a 256k -ar 48000
    """
    def _replace(match: re.Match) -> str:
        extra_params = match.group(1).strip()
        if not input_path:
            # Ha nincs input fájl (előnézet mód), egyszerű -map 0:a marad
            return f"-map 0:a {extra_params}".strip()

        streams = get_audio_channels(input_path, ffprobe_bin)
        if not streams:
            return f"-map 0:a {extra_params}".strip()

        # Extra paraméterekből a -c:a értéket kiemeljük, a többi paraméter közös marad
        # Minden sávhoz: -map 0:a:N -c:a:N <codec> <tobb_param>
        # A -c:a <codec> részt per-stream indexelésre alakítjuk, a többi átmarad.
        codec_match = re.search(r'-c:a\s+(\S+)', extra_params)
        if codec_match:
            codec = codec_match.group(1)
            other_params = re.sub(r'-c:a\s+\S+', '', extra_params).strip()
        else:
            codec = None
            other_params = extra_params

        chunks: list[str] = []
        for audio_idx, _nb_channels, _layout, _codec in streams:
            part = f"-map 0:a:{audio_idx}"
            if codec:
                part += f" -c:a:{audio_idx} {codec}"
            if other_params:
                part += f" {other_params}"
            chunks.append(part)

        return " ".join(chunks)

    return re.sub(r"\{recode_audio\s*:\s*([^}]+)\}", _replace, cmd)


# macOS: natív AudioToolbox AAC encoder (jobb Apple-kompatibilitás); egyéb: libavcodec aac
_AAC_CODEC = "aac_at" if _platform.system() == "Darwin" else "aac"

# Codecs that are natively compatible with Apple devices and Chromecast
_COMPAT_COPY_CODECS: frozenset[str] = frozenset({"aac", "ac3", "eac3", "mp3"})
# Surround codecs not Apple/Chromecast compatible → stereo downmix only
_SURROUND_DOWNMIX_ONLY_CODECS: frozenset[str] = frozenset({"dts", "dca", "truehd", "mlp"})
# Surround channel count → display label
_SURROUND_LABELS: dict[int, str] = {6: "5.1", 7: "6.1", 8: "7.1", 5: "5.0", 4: "4.0"}
# ISO 639-2/B language code → display name
_LANG_NAMES: dict[str, str] = {
    "hun": "Hungarian", "eng": "English", "ger": "German", "deu": "German",
    "fra": "French",   "fre": "French",  "spa": "Spanish", "ita": "Italian",
    "jpn": "Japanese", "kor": "Korean",  "rus": "Russian", "por": "Portuguese",
    "pol": "Polish",   "cze": "Czech",   "ces": "Czech",   "slk": "Slovak",
    "rom": "Romanian", "ron": "Romanian","hrv": "Croatian","srp": "Serbian",
    "bul": "Bulgarian","ukr": "Ukrainian","zho": "Chinese","chi": "Chinese",
    "ara": "Arabic",   "tur": "Turkish", "nld": "Dutch",   "swe": "Swedish",
    "nor": "Norwegian","dan": "Danish",  "fin": "Finnish", "gre": "Greek",
}


def _lang_display(code: str) -> str:
    return _LANG_NAMES.get(code.lower(), code) if code else ""


def _clean_stream_title(title: str) -> str:
    """Eltávolítja a codec/bitrate utótagot a stream-title-ből.
    Pl. 'Commentary with James Cameron DD 2.0 @ 224 kbps' → 'Commentary with James Cameron'
    """
    cleaned = re.sub(
        r'\s+(?:DD|DTS|AC3|AAC|MP3|EAC3|TrueHD|Atmos)\s+[\d.]+(?:\s*@\s*\d+\s*kbps)?$',
        "", title, flags=re.IGNORECASE
    ).strip()
    cleaned = re.sub(r'\s+@\s*\d+\s*kbps$', "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned if cleaned else title


def _compat_label(lang: str, title: str, suffix: str) -> str:
    """Generál egy emberi olvashatóságú stream-title-t.

    Prioritás: ha van language → nyelv neve + suffix
               ha van title de nincs lang → megtisztított title (suffix nélkül, már egyedi)
               különben → csak suffix
    """
    if lang and lang not in ("und", ""):
        base = _lang_display(lang)
        return f"{base} ({suffix})" if base else suffix
    if title:
        return _clean_stream_title(title)
    return suffix


def _get_compat_streams(input_path: str, ffprobe_bin: str) -> list[dict]:
    """ffprobe által lekérdezi az összes hangsáv részleteit a compat_audio tokenhez."""
    try:
        result = subprocess.run(
            [
                ffprobe_bin, "-v", "error",
                "-select_streams", "a",
                "-show_entries",
                "stream=codec_name,channels,channel_layout:stream_tags=language,title",
                "-of", "json",
                input_path,
            ],
            capture_output=True, text=True, check=False, timeout=20,
        )
        if result.returncode != 0:
            return []
        payload = json.loads(result.stdout or "{}")
        streams: list[dict] = []
        for audio_idx, s in enumerate(payload.get("streams", [])):
            tags = s.get("tags", {}) or {}
            lang = str(tags.get("language", "") or "").strip()
            title = str(tags.get("title", "") or "").strip()
            channels = int(s.get("channels", 2) or 2)
            layout = str(s.get("channel_layout", "") or "").strip()
            if not layout:
                layout = _CHANNEL_COUNT_TO_LAYOUT.get(channels, f"{channels}c")
            codec = str(s.get("codec_name", "") or "").strip().lower()
            streams.append({
                "audio_idx": audio_idx,
                "codec": codec,
                "channels": channels,
                "layout": layout,
                "lang": lang,
                "title": title,
            })
        return streams
    except Exception:
        return []


def expand_compat_audio(cmd: str, input_path: str, ffprobe_bin: str) -> str:
    """`{compat_audio}` → minden hangsáv Apple/Chromecast-kompatibilis formátumra.

    Surround stream:
      1. Szteó AAC downmix 256k — Dolby PLII mátrix filter (nincs fázishiba)
      2. Surround AC3 448k — minden surround sávhoz (DTS is → AC3)
    Szteó/mono: AAC 256k, -ac:a:N 2 (forrás már szteró, biztonságos)
    Nincs -map_metadata, nincs -ac 2 a surround downmixnél (helyette dplii filter).
    """
    def _replace(match: re.Match) -> str:
        if not input_path:
            return match.group(0)

        streams = _get_compat_streams(input_path, ffprobe_bin)
        if not streams:
            return ""

        # 1. pass: kimeneti sávok leírójának összeállítása
        out_streams: list[dict] = []
        for s in streams:
            in_idx = s["audio_idx"]
            codec = s["codec"]
            channels = s["channels"]
            lang = s["lang"]
            title = s["title"]
            is_surround = channels > 2

            if is_surround:
                surround_label = _SURROUND_LABELS.get(channels, f"{channels}ch")
                # Szteó AAC downmix — dplii filter a fázishibák elkerülésére
                out_streams.append({
                    "in_idx": in_idx, "codec": "aac",
                    "ac2": False, "dplii": True,
                    "bitrate": "256k",
                    "title": _compat_label(lang, title, "Stereo"),
                    "lang": lang,
                })
                # Surround AC3 (copy ha AC3, konvert ha DTS/egyéb)
                out_streams.append({
                    "in_idx": in_idx,
                    "codec": "copy" if codec in _COMPAT_COPY_CODECS else "ac3",
                    "ac2": False, "dplii": False,
                    "bitrate": None if codec in _COMPAT_COPY_CODECS else "448k",
                    "title": _compat_label(lang, title, surround_label),
                    "lang": lang,
                })
            else:
                out_streams.append({
                    "in_idx": in_idx, "codec": "aac",
                    "ac2": True, "dplii": False,
                    "bitrate": "256k",
                    "title": _compat_label(lang, title, "Stereo"),
                    "lang": lang,
                })

        # 2. pass: alternate group hozzárendelés (language szerint csoportosítás)
        # Ugyanolyan nyelvű sávok azonos group-ba kerülnek, különböző nyelvek külön csoportba.
        # Ez kell ahhoz, hogy a QuickTime minden sávot elkülönítetten lásson.
        lang_to_group: dict[str, int] = {}
        group_counter = 1
        for os_ in out_streams:
            lang = os_["lang"]
            if lang and lang not in ("und", ""):
                if lang not in lang_to_group:
                    lang_to_group[lang] = group_counter
                    group_counter += 1
                os_["alt_group"] = lang_to_group[lang]
            else:
                # Nyelv nélküli sávok (pl. kommentár): mindütt és külön csoport
                os_["alt_group"] = group_counter
                group_counter += 1

        # 3. pass: dup title-ök számozása
        title_seen: dict[str, int] = {}
        for os_ in out_streams:
            title_seen[os_["title"]] = title_seen.get(os_["title"], 0) + 1
        title_counter: dict[str, int] = {}
        for os_ in out_streams:
            t = os_["title"]
            if title_seen[t] > 1:
                title_counter[t] = title_counter.get(t, 0) + 1
                os_["title"] = f"{t} {title_counter[t]}"

        # 4. pass: ffmpeg chunk-ok generálása
        chunks: list[str] = []
        for out_idx, os_ in enumerate(out_streams):
            safe_title = os_["title"].replace('"', "'")
            lang = os_["lang"]
            part = f"-map 0:a:{os_['in_idx']} -c:a:{out_idx} {os_['codec']}"
            if os_["dplii"]:
                part += f' -filter:a:{out_idx} "aresample=matrix_encoding=dplii"'
            elif os_["ac2"]:
                part += f" -ac:a:{out_idx} 2"
            if os_["bitrate"]:
                part += f" -b:a:{out_idx} {os_['bitrate']}"
            # disposition: AAC = default (iOS elsődleges), AC3 = 0 (passthrough alternatíva)
            disp = "default" if os_["codec"] == "aac" else "0"
            part += f" -disposition:a:{out_idx} {disp}"
            # alternate_group: QuickTime minden csoportból csak egyet menne, külön group = mind látszó
            part += f' -metadata:s:a:{out_idx} alternate_group={os_["alt_group"]}'
            part += f' -metadata:s:a:{out_idx} title="{safe_title}"'
            if lang and lang not in ("und", ""):
                part += f" -metadata:s:a:{out_idx} language={lang}"
            chunks.append(part)

        return " ".join(chunks)

    return re.sub(r"\{compat_audio\}", _replace, cmd)


def expand_compat_subs(cmd: str, input_path: str, ffprobe_bin: str) -> str:
    """`{compat_subs}` → minden feliratsáv mov_text-ként, per-sáv title + language metaadat.

    Titanic példa (hun, eng felirat):
        -map 0:s:0 -c:s:0 mov_text -metadata:s:s:0 title="Hungarian" -metadata:s:s:0 language=hun
        -map 0:s:1 -c:s:1 mov_text -metadata:s:s:1 title="English"   -metadata:s:s:1 language=eng
    """
    def _replace(match: re.Match) -> str:
        if not input_path:
            return match.group(0)
        try:
            result = subprocess.run(
                [
                    ffprobe_bin, "-v", "error",
                    "-select_streams", "s",
                    "-show_entries", "stream=index:stream_tags=language,title",
                    "-of", "json",
                    input_path,
                ],
                capture_output=True, text=True, check=False, timeout=20,
            )
            if result.returncode != 0:
                return ""
            payload = json.loads(result.stdout or "{}")
            subs = payload.get("streams", [])
        except Exception:
            return ""

        if not subs:
            return ""

        chunks: list[str] = []
        for sub_idx, s in enumerate(subs):
            tags = s.get("tags", {}) or {}
            lang = str(tags.get("language", "") or "").strip()
            title = str(tags.get("title", "") or "").strip()
            if lang and lang not in ("und", ""):
                display = _lang_display(lang) or lang
            elif title:
                display = title
            else:
                display = f"Subtitle {sub_idx + 1}"
            safe = display.replace('"', "'")
            part = f"-map 0:s:{sub_idx} -c:s:{sub_idx} mov_text"
            part += f' -metadata:s:s:{sub_idx} title="{safe}"'
            if lang and lang not in ("und", ""):
                part += f" -metadata:s:s:{sub_idx} language={lang}"
            chunks.append(part)

        return " ".join(chunks)

    return re.sub(r"\{compat_subs\}", _replace, cmd)


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
    cmd = expand_map_channel(cmd, input_path, ffprobe_bin)
    cmd = expand_map_streams(cmd, input_path, ffprobe_bin)
    cmd = expand_recode_audio(cmd, input_path, ffprobe_bin)
    cmd = expand_compat_audio(cmd, input_path, ffprobe_bin)
    cmd = expand_compat_subs(cmd, input_path, ffprobe_bin)
    return cmd
