#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ffmpeg_params.py — FFmpeg paraméter adatbázis (FFBuilder)
=======================================================
Nem-GUI modul: statikus adatok FFmpeg paraméterekhez, konténer
formátumokhoz és parancs-sablonokhoz.

Önállóan futtatható (JSON kimenet):
    python ffmpeg_params.py
    python ffmpeg_params.py sections
    python ffmpeg_params.py templates
    python ffmpeg_params.py formats

Importálható:
    from ffmpeg_params import PARAM_SECTIONS, CONTAINER_FORMATS, TEMPLATES
"""

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paraméter leírások betöltése külső JSON fájlból
# ---------------------------------------------------------------------------
_DESCRIPTIONS_DIR = Path(__file__).parent.parent.parent / "assets" / "locales"

def _load_descriptions(lang: str = "en") -> dict[str, str]:
    """Load param descriptions for the given language (en/hu).
    Falls back to 'en' if the language file is not found."""
    path = _DESCRIPTIONS_DIR / f"param_descriptions_{lang}.json"
    if not path.exists():
        path = _DESCRIPTIONS_DIR / "param_descriptions_en.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _normalize_lang(lang: str | None) -> str:
    raw = str(lang or "en").strip().lower()
    if not raw:
        return "en"
    return raw.split("_", 1)[0]


def refresh_param_descriptions(lang: str = "en") -> None:
    """Re-inject localised labels/descriptions into PARAM_SECTIONS.
    Call this whenever the application language changes."""
    chosen_lang = _normalize_lang(lang)
    descs = _load_descriptions(chosen_lang)
    for section in PARAM_SECTIONS:
        for param in section["params"]:
            key = param["key"]
            param["label"] = _get_param_label(key, chosen_lang)
            param["desc"] = descs.get(param["key"], "")

# ---------------------------------------------------------------------------
# Paraméter szekciók
# ---------------------------------------------------------------------------
# Minden param-nak van:
#   key             — ffmpeg flag (pl. "-c:v")
#   label           — megjelenítési neve
#   type            — "combo" | "entry" | "flag"
#   default         — alapértelmezett érték
#   options         — (csak combo) értékek listája
#   placeholder     — (csak entry) segítő szöveg
#   desc            — leíró szöveg (tooltip vagy help)
#   enabled_default — bool, alapból aktív-e

PARAM_SECTIONS = [
    {
        "id": "input",
        "title": "⬤  INPUT",
        "params": [
            {
                "key": "-hwaccel",
                "type": "combo",
                "default": "auto",
                "options": ["auto", "cuda", "videotoolbox", "vaapi", "qsv", "opencl", "d3d11va"],
                "enabled_default": False,
            },
            {
                "key": "-ss",
                "type": "entry",
                "default": "",
                "placeholder": "pl. 00:01:30  vagy  90",
                "examples": ["00:00:30", "00:01:00", "00:05:00", "00:10:00"],
                "enabled_default": False,
            },
            {
                "key": "-to",
                "type": "entry",
                "default": "",
                "placeholder": "pl. 00:02:00  vagy  120",
                "examples": ["00:01:00", "00:02:00", "00:05:00", "00:10:00"],
                "enabled_default": False,
            },
            {
                "key": "-t",
                "type": "entry",
                "default": "",
                "placeholder": "pl. 00:00:30  vagy  30",
                "examples": ["30", "00:00:30", "00:01:00", "00:05:00"],
                "enabled_default": False,
            },
            {
                "key": "-re",
                "type": "flag",
                "default": "",
                "enabled_default": False,
            },
            {
                "key": "-stream_loop",
                "type": "combo",
                "default": "-1",
                "options": ["-1", "0", "1", "2", "5", "10"],
                "enabled_default": False,
            },
            {
                "key": "-itsoffset",
                "type": "entry",
                "default": "",
                "placeholder": "pl. 1.5  (sec)",
                "enabled_default": False,
            },
        ],
    },
    {
        "id": "video",
        "title": "▶  VIDEO",
        "params": [
            {
                "key": "-c:v",
                "type": "combo",
                "default": "libx264",
                "options": [
                    "copy", "libx264", "libx265", "libvpx-vp9",
                    "libaom-av1", "prores_ks", "dnxhd",
                    "mpeg4", "libxvid", "huffyuv", "ffv1",
                    # macOS VideoToolbox
                    "h264_videotoolbox", "hevc_videotoolbox",
                    # NVIDIA NVENC
                    "h264_nvenc", "hevc_nvenc", "av1_nvenc",
                    # AMD AMF
                    "h264_amf", "hevc_amf",
                    # Intel QuickSync
                    "h264_qsv", "hevc_qsv", "av1_qsv",
                ],
                "enabled_default": True,
            },
            {
                "key": "-crf",
                "type": "combo",
                "default": "23",
                "options": ["0", "15", "18", "20", "22", "23", "24", "26", "28", "30", "35", "51"],
                "enabled_default": False,
            },
            {
                "key": "-preset",
                "type": "combo",
                "default": "medium",
                "options": [
                    "ultrafast", "superfast", "veryfast", "faster",
                    "fast", "medium", "slow", "slower", "veryslow",
                ],
                "enabled_default": False,
            },
            {
                "key": "-b:v",
                "type": "entry",
                "default": "",
                "placeholder": "pl. 5000k  vagy  8M",
                "examples": ["500k", "1000k", "3000k", "5000k", "8M", "15M"],
                "enabled_default": False,
            },
            {
                "key": "-maxrate",
                "type": "entry",
                "default": "",
                "placeholder": "pl. 10M",
                "examples": ["3M", "5M", "8M", "10M"],
                "enabled_default": False,
            },
            {
                "key": "-vf",
                "type": "entry",
                "default": "",
                "placeholder": "pl. scale=1920:1080,fps=30",
                "examples": [
                    "scale=1920:1080",
                    "scale=1280:720",
                    "scale=-1:720",
                    "fps=30",
                    "crop=1280:720:0:0",
                    "setpts=0.5*PTS",
                    "pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
                ],
                "enabled_default": False,
            },
            {
                "key": "-r",
                "type": "combo",
                "default": "",
                "options": ["23.976", "24", "25", "29.97", "30", "48", "50", "59.94", "60", "120"],
                "enabled_default": False,
            },
            {
                "key": "-pix_fmt",
                "type": "combo",
                "default": "yuv420p",
                "options": [
                    "yuv420p", "yuv422p", "yuv444p",
                    "yuv420p10le", "yuv422p10le", "yuv444p10le",
                    "nv12", "rgb24", "rgba", "gray",
                ],
                "enabled_default": False,
            },
            {
                "key": "-profile:v",
                "type": "combo",
                "default": "",
                "options": [
                    "baseline", "main", "high",
                    "high10", "high422", "high444",
                    "main10",
                ],
                "enabled_default": False,
            },
            {
                "key": "-refs",
                "type": "combo",
                "default": "",
                "options": ["1", "2", "3", "4", "5", "6", "8", "10", "12", "16"],
                "enabled_default": False,
            },
            {
                "key": "-bf",
                "type": "combo",
                "default": "",
                "options": ["0", "1", "2", "3", "4", "5", "6", "8", "10", "12", "16"],
                "enabled_default": False,
            },
            {
                "key": "-tune",
                "type": "combo",
                "default": "",
                "options": [
                    "film", "animation", "grain",
                    "stillimage", "fastdecode", "zerolatency",
                    "psnr", "ssim",
                ],
                "enabled_default": False,
            },
            {
                "key": "-g",
                "type": "entry",
                "default": "",
                "placeholder": "pl. 30  (=1 kulcskép/sec 30fps-nél)",
                "examples": ["24", "30", "60", "120"],
                "enabled_default": False,
            },
            {
                "key": "-bufsize",
                "type": "entry",
                "default": "",
                "placeholder": "pl. 10M  vagy  20000k",
                "examples": ["5M", "10M", "20M", "20000k"],
                "enabled_default": False,
            },
            {
                "key": "-vn",
                "type": "flag",
                "default": "",
                "enabled_default": False,
            },
            {
                "key": "-s",
                "type": "combo",
                "default": "",
                "options": [
                    "3840x2160", "2560x1440", "1920x1080",
                    "1280x720", "854x480", "640x360", "1080x1920", "720x1280",
                ],
                "enabled_default": False,
            },
            {
                "key": "-aspect",
                "type": "combo",
                "default": "",
                "options": ["16:9", "4:3", "1:1", "21:9", "2.35:1", "9:16"],
                "enabled_default": False,
            },
            {
                "key": "-vframes",
                "type": "entry",
                "default": "",
                "placeholder": "pl. 300  (=10s @ 30fps)",
                "enabled_default": False,
            },
            {
                "key": "-level",
                "type": "combo",
                "default": "",
                "options": ["3.0", "3.1", "4.0", "4.1", "4.2", "5.0", "5.1", "5.2"],
                "enabled_default": False,
            },
            {
                "key": "-minrate",
                "type": "entry",
                "default": "",
                "placeholder": "pl. 2M  vagy  1000k",
                "enabled_default": False,
            },
            {
                "key": "-pass",
                "type": "combo",
                "default": "",
                "options": ["1", "2"],
                "enabled_default": False,
            },
            {
                "key": "-qscale:v",
                "type": "entry",
                "default": "",
                "placeholder": "pl. 2  (alacsonyabb = jobb)",
                "enabled_default": False,
            },
            {
                "key": "-bsf:v",
                "type": "combo",
                "default": "",
                "options": [
                    "h264_mp4toannexb", "hevc_mp4toannexb",
                    "mpeg4_unpack_bframes", "extract_extradata", "null",
                ],
                "enabled_default": False,
            },
            {
                "key": "-tag:v",
                "type": "entry",
                "default": "",
                "placeholder": "pl. hvc1  (Apple HEVC)",
                "enabled_default": False,
            },
            {
                "key": "-vsync",
                "type": "combo",
                "default": "",
                "options": ["cfr", "vfr", "passthrough", "drop"],
                "enabled_default": False,
            },
        ],
    },
    {
        "id": "audio",
        "title": "♫  AUDIO",
        "params": [
            {
                "key": "-c:a",
                "type": "combo",
                "default": "aac",
                "options": [
                    "copy", "aac", "libmp3lame", "libopus", "libvorbis",
                    "flac", "pcm_s16le", "pcm_s24le", "ac3", "eac3",
                ],
                "enabled_default": True,
            },
            {
                "key": "-b:a",
                "type": "combo",
                "default": "192k",
                "options": ["64k", "96k", "128k", "160k", "192k", "256k", "320k"],
                "enabled_default": False,
            },
            {
                "key": "-ar",
                "type": "combo",
                "default": "",
                "options": ["22050", "44100", "48000", "88200", "96000"],
                "enabled_default": False,
            },
            {
                "key": "-ac",
                "type": "combo",
                "default": "",
                "options": ["1", "2", "6", "8"],
                "enabled_default": False,
            },
            {
                "key": "-af",
                "type": "entry",
                "default": "",
                "placeholder": "pl. loudnorm, volume=1.5",
                "examples": [
                    "loudnorm=I=-23:TP=-1.5:LRA=11",
                    "volume=1.5",
                    "volume=6dB",
                    "atempo=2.0",
                    "aresample=48000",
                ],
                "enabled_default": False,
            },
            {
                "key": "-an",
                "type": "flag",
                "default": "",
                "enabled_default": False,
            },
            {
                "key": "-vol",
                "type": "entry",
                "default": "",
                "placeholder": "pl. 256=eredeti, 512=dupla",
                "examples": ["256", "128", "384", "512"],
                "enabled_default": False,
            },            {
                "key": "-profile:a",
                "type": "combo",
                "default": "",
                "options": ["aac_low", "aac_he", "aac_he_v2", "aac_eld", "aac_xhe"],
                "enabled_default": False,
            },
            {
                "key": "-q:a",
                "type": "entry",
                "default": "",
                "placeholder": "pl. 2  (mp3: 0–9, alacsonyabb = jobb)",
                "enabled_default": False,
            },
            {
                "key": "-sample_fmt",
                "type": "combo",
                "default": "",
                "options": ["s16", "s32", "fltp", "s16p", "s32p", "u8", "dbl"],
                "enabled_default": False,
            },
            {
                "key": "-bsf:a",
                "type": "combo",
                "default": "",
                "options": ["aac_adtstoasc", "mp3decomp", "null"],
                "enabled_default": False,
            },
            {
                "key": "-shortest",
                "type": "flag",
                "default": "",
                "enabled_default": False,
            },        ],
    },
    {
        "id": "advanced",
        "title": "⚙  ADVANCED",
        "params": [
            {
                "key": "-map",
                "type": "entry",
                "default": "",
                "placeholder": "pl. 0:v:0 0:a:1",
                "examples": ["0:v:0", "0:a:0", "0:a:1", "0:s:0", "0:v:0 0:a:0"],
                "enabled_default": False,
            },
            {
                "key": "-movflags",
                "type": "combo",
                "default": "",
                "options": ["+faststart", "frag_keyframe+empty_moov", "disable"],
                "enabled_default": False,
            },
            {
                "key": "-metadata",
                "type": "entry",
                "default": "",
                "placeholder": "pl. title=Film neve",
                "examples": ["title=Film neve", "artist=Rendező", "year=2024", "comment=Megjegyzés"],
                "enabled_default": False,
            },
            {
                "key": "-threads",
                "type": "combo",
                "default": "",
                "options": ["0", "1", "2", "4", "8", "16"],
                "enabled_default": False,
            },
            {
                "key": "-loglevel",
                "type": "combo",
                "default": "",
                "options": ["quiet", "panic", "fatal", "error", "warning", "info", "verbose", "debug"],
                "enabled_default": False,
            },
            {
                "key": "-y",
                "type": "flag",
                "default": "",
                "enabled_default": True,
            },
            {
                "key": "-f",
                "type": "combo",
                "default": "",
                "options": [
                    "mp4", "matroska", "avi", "mov", "webm",
                    "mp3", "wav", "ogg", "flac", "aac",
                    "image2", "rawvideo", "null",
                ],
                "enabled_default": False,
            },
            {
                "key": "-c:s",
                "type": "combo",
                "default": "",
                "options": ["copy", "mov_text", "srt", "ass", "webvtt"],
                "enabled_default": False,
            },
            {
                "key": "-sn",
                "type": "flag",
                "default": "",
                "enabled_default": False,
            },
            {
                "key": "-map_metadata",
                "type": "combo",
                "default": "",
                "options": ["0", "-1"],
                "enabled_default": False,
            },
            {
                "key": "-fflags",
                "type": "combo",
                "default": "",
                "options": [
                    "+genpts", "+igndts", "+discardcorrupt",
                    "+sortdts", "+fastseek", "+nobuffer",
                ],
                "enabled_default": False,
            },
            {
                "key": "-avoid_negative_ts",
                "type": "combo",
                "default": "",
                "options": ["make_non_negative", "make_zero", "disabled", "auto"],
                "enabled_default": False,
            },
            {
                "key": "-probesize",
                "type": "entry",
                "default": "",
                "placeholder": "pl. 50M  (alapért. ~5MB)",
                "examples": ["10M", "50M", "100M"],
                "enabled_default": False,
            },
            {
                "key": "-max_muxing_queue_size",
                "type": "entry",
                "default": "",
                "placeholder": "pl. 9999  (alapért. 128)",
                "enabled_default": False,
            },
            {
                "key": "-copyts",
                "type": "flag",
                "default": "",
                "enabled_default": False,
            },
            {
                "key": "-start_at_zero",
                "type": "flag",
                "default": "",
                "enabled_default": False,
            },
            {
                "key": "-strict",
                "type": "combo",
                "default": "",
                "options": ["experimental", "-2", "-1", "0", "1", "2"],
                "enabled_default": False,
            },
            {
                "key": "-analyzeduration",
                "type": "entry",
                "default": "",
                "placeholder": "pl. 100M",
                "enabled_default": False,
            },
            {
                "key": "-tag:a",
                "type": "entry",
                "default": "",
                "placeholder": "pl. mp4a",
                "enabled_default": False,
            },
            {
                "key": "-dn",
                "type": "flag",
                "default": "",
                "enabled_default": False,
            },
        ],
    },
    {
        "id": "color",
        "title": "◈  COLOR & HDR",
        "params": [
            {
                "key": "-color_range",
                "type": "combo",
                "default": "",
                "options": ["tv", "pc", "limited", "full"],
                "enabled_default": False,
            },
            {
                "key": "-color_primaries",
                "type": "combo",
                "default": "",
                "options": [
                    "bt709", "bt2020", "smpte170m", "smpte240m",
                    "film", "smpte431", "smpte432", "jedec-p22",
                ],
                "enabled_default": False,
            },
            {
                "key": "-color_trc",
                "type": "combo",
                "default": "",
                "options": [
                    "bt709", "smpte2084", "arib-std-b67",
                    "linear", "log", "smpte240m", "bt2020-10", "bt2020-12",
                ],
                "enabled_default": False,
            },
            {
                "key": "-colorspace",
                "type": "combo",
                "default": "",
                "options": [
                    "bt709", "bt2020nc", "bt2020c",
                    "smpte170m", "smpte240m", "ycgco", "fcc",
                ],
                "enabled_default": False,
            },
            {
                "key": "-chroma_sample_location",
                "type": "combo",
                "default": "",
                "options": ["left", "center", "topleft", "top", "bottomleft", "bottom"],
                "enabled_default": False,
            },
            {
                "key": "-master_display",
                "type": "entry",
                "default": "",
                "placeholder": "pl. G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,1)",
                "enabled_default": False,
            },
            {
                "key": "-max_cll",
                "type": "entry",
                "default": "",
                "placeholder": "pl. 1000,300  (MaxCLL,MaxFALL nit)",
                "enabled_default": False,
            },
        ],
    },
]

# Fix, kézzel megadott paraméternevek a vizuális szerkesztő soraihoz (többnyelvűen).
_PARAM_LABELS_BY_LANG: dict[str, dict[str, str]] = {
    "en": {
        "-hwaccel": "Hardware decode",
        "-ss": "Start time",
        "-to": "End time",
        "-t": "Duration",
        "-re": "Read realtime",
        "-stream_loop": "Loop input",
        "-itsoffset": "Input offset",
        "-c:v": "Video codec",
        "-crf": "Quality (CRF)",
        "-preset": "Encode preset",
        "-b:v": "Video bitrate",
        "-maxrate": "Max bitrate",
        "-vf": "Video filters",
        "-r": "Frame rate",
        "-pix_fmt": "Pixel format",
        "-profile:v": "Video profile",
        "-refs": "Reference frames",
        "-bf": "B-frames",
        "-tune": "Encoder tune",
        "-g": "GOP size",
        "-bufsize": "VBV buffer",
        "-vn": "Disable video",
        "-s": "Resolution",
        "-aspect": "Aspect ratio",
        "-vframes": "Frame limit",
        "-level": "Codec level",
        "-minrate": "Min bitrate",
        "-pass": "Two-pass stage",
        "-qscale:v": "VBR quality",
        "-bsf:v": "Video bitstream filter",
        "-tag:v": "Video FourCC",
        "-vsync": "Sync mode",
        "-c:a": "Audio codec",
        "-b:a": "Audio bitrate",
        "-ar": "Sample rate",
        "-ac": "Channels",
        "-af": "Audio filters",
        "-an": "Disable audio",
        "-vol": "Legacy volume",
        "-profile:a": "Audio profile",
        "-q:a": "Audio quality",
        "-sample_fmt": "Sample format",
        "-bsf:a": "Audio bitstream filter",
        "-shortest": "Stop at shortest",
        "-map": "Stream mapping",
        "-movflags": "MP4/MOV flags",
        "-metadata": "Metadata",
        "-threads": "CPU threads",
        "-loglevel": "Log level",
        "-y": "Overwrite output",
        "-f": "Force format",
        "-c:s": "Subtitle codec",
        "-sn": "Disable subtitles",
        "-map_metadata": "Metadata mapping",
        "-fflags": "Format flags",
        "-avoid_negative_ts": "Timestamp policy",
        "-probesize": "Probe size",
        "-max_muxing_queue_size": "Mux queue size",
        "-copyts": "Copy timestamps",
        "-start_at_zero": "Start at zero",
        "-strict": "Compliance mode",
        "-analyzeduration": "Analyze duration",
        "-tag:a": "Audio FourCC",
        "-dn": "Disable data streams",
        "-color_range": "Color range",
        "-color_primaries": "Color primaries",
        "-color_trc": "Transfer characteristic",
        "-colorspace": "Color matrix",
        "-chroma_sample_location": "Chroma location",
        "-master_display": "HDR master display",
        "-max_cll": "HDR MaxCLL/MaxFALL",
    },
    "hu": {
        "-hwaccel": "Hardveres dekódolás",
        "-ss": "Kezdő idő",
        "-to": "Vég idő",
        "-t": "Időtartam",
        "-re": "Valós idejű olvasás",
        "-stream_loop": "Bemenet ismétlése",
        "-itsoffset": "Bemeneti eltolás",
        "-c:v": "Videó kodek",
        "-crf": "Minőség (CRF)",
        "-preset": "Kódolási preset",
        "-b:v": "Videó bitráta",
        "-maxrate": "Max bitráta",
        "-vf": "Videó filterek",
        "-r": "Képkockasebesség",
        "-pix_fmt": "Pixel formátum",
        "-profile:v": "Videó profil",
        "-refs": "Referencia frame-ek",
        "-bf": "B-frame-ek",
        "-tune": "Encoder hangolás",
        "-g": "GOP méret",
        "-bufsize": "VBV puffer",
        "-vn": "Videó tiltása",
        "-s": "Felbontás",
        "-aspect": "Képarány",
        "-vframes": "Frame limit",
        "-level": "Kodek szint",
        "-minrate": "Min bitráta",
        "-pass": "Kétmenetes lépés",
        "-qscale:v": "VBR minőség",
        "-bsf:v": "Videó bitstream filter",
        "-tag:v": "Videó FourCC",
        "-vsync": "Szinkron mód",
        "-c:a": "Audió kodek",
        "-b:a": "Audió bitráta",
        "-ar": "Mintavételi frekvencia",
        "-ac": "Csatornák",
        "-af": "Audió filterek",
        "-an": "Audió tiltása",
        "-vol": "Legacy hangerő",
        "-profile:a": "Audió profil",
        "-q:a": "Audió minőség",
        "-sample_fmt": "Mintaformátum",
        "-bsf:a": "Audió bitstream filter",
        "-shortest": "Legrövidebbnél áll meg",
        "-map": "Stream leképezés",
        "-movflags": "MP4/MOV jelzők",
        "-metadata": "Metaadatok",
        "-threads": "CPU szálak",
        "-loglevel": "Napló szint",
        "-y": "Felülírás",
        "-f": "Formátum kényszerítés",
        "-c:s": "Felirat kodek",
        "-sn": "Felirat tiltása",
        "-map_metadata": "Metaadat leképezés",
        "-fflags": "Formátum jelzők",
        "-avoid_negative_ts": "Timestamp szabály",
        "-probesize": "Probe méret",
        "-max_muxing_queue_size": "Mux sor méret",
        "-copyts": "Timestamp másolás",
        "-start_at_zero": "Indítás nulláról",
        "-strict": "Megfelelési mód",
        "-analyzeduration": "Elemzési idő",
        "-tag:a": "Audió FourCC",
        "-dn": "Adat stream tiltása",
        "-color_range": "Színtartomány",
        "-color_primaries": "Alapszínek",
        "-color_trc": "Transzfer karakterisztika",
        "-colorspace": "Színtér mátrix",
        "-chroma_sample_location": "Krómaminta hely",
        "-master_display": "HDR master display",
        "-max_cll": "HDR MaxCLL/MaxFALL",
    },
}


def _get_param_label(key: str, lang: str) -> str:
    chosen_lang = _normalize_lang(lang)
    localized = _PARAM_LABELS_BY_LANG.get(chosen_lang, {})
    if key in localized:
        return localized[key]
    return _PARAM_LABELS_BY_LANG["en"].get(key, key)


# Leírások és fix nevek betöltése és beillesztése a struktúrába (induláskor en alapértelmezett)
refresh_param_descriptions("en")

# ---------------------------------------------------------------------------
# Konténer / output formátumok
# ---------------------------------------------------------------------------

CONTAINER_FORMATS = [
    ("mp4",  "MP4  — H.264/HEVC + AAC  (legelterjedtebb)"),
    ("mkv",  "MKV  — Matroska  (univerzális, mindenre)"),
    ("mov",  "MOV  — QuickTime  (Apple, ProRes, Final Cut)"),
    ("avi",  "AVI  — klasszikus Windows formátum"),
    ("webm", "WebM  — VP9 / AV1 + Opus  (web streaming)"),
    ("ts",   "TS   — MPEG Transport Stream  (broadcast, HLS)"),
    ("mp3",  "MP3  — csak audió  (MPEG Layer 3)"),
    ("aac",  "AAC  — csak audió  (Advanced Audio Coding)"),
    ("flac", "FLAC — csak audió  (lossless tömörítés)"),
    ("wav",  "WAV  — csak audió  (tömörítetlen PCM)"),
    ("ogg",  "OGG  — csak audió  (Vorbis / Opus)"),
    ("mxf",  "MXF  — broadcast / XDCAM / DNxHD"),
    ("gif",  "GIF  — animált kép  (web)"),
]


# ---------------------------------------------------------------------------
# Önálló futtatás
# ---------------------------------------------------------------------------

def main():
    """
    Összefoglalót vagy teljes adatot ír stdout-ra JSON formátumban.

    Használat:
        python ffmpeg_params.py             → összefoglaló
        python ffmpeg_params.py sections    → PARAM_SECTIONS teljes JSON
        python ffmpeg_params.py formats     → CONTAINER_FORMATS JSON
    """
    mode = sys.argv[1] if len(sys.argv) > 1 else "summary"

    if mode == "sections":
        print(json.dumps(PARAM_SECTIONS, ensure_ascii=False, indent=2))
    elif mode == "formats":
        print(json.dumps(CONTAINER_FORMATS, ensure_ascii=False, indent=2))
    else:
        summary = {
            "sections": len(PARAM_SECTIONS),
            "total_params": sum(len(s["params"]) for s in PARAM_SECTIONS),
            "container_formats": len(CONTAINER_FORMATS),
            "section_ids": [s["id"] for s in PARAM_SECTIONS],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
