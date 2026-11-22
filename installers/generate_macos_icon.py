#!/usr/bin/env python3
"""Generate assets/icons/app.icns from SVG source for macOS builds."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    icons_dir = root / "assets" / "icons"
    svg_candidates = [
        icons_dir / "light" / "app.svg",
        icons_dir / "dark" / "app.svg",
    ]

    svg_path = next((p for p in svg_candidates if p.is_file()), None)
    if svg_path is None:
        print("No source SVG found (expected assets/icons/light/app.svg or dark/app.svg).", file=sys.stderr)
        return 1

    iconutil = shutil.which("iconutil")
    if not iconutil:
        print("iconutil not found. This script must run on macOS.", file=sys.stderr)
        return 1

    try:
        from PySide6.QtCore import QSize, Qt
        from PySide6.QtGui import QColor, QImage, QPainter
        from PySide6.QtSvg import QSvgRenderer
    except Exception as exc:  # pragma: no cover
        print(f"Failed to import PySide6 SVG modules: {exc}", file=sys.stderr)
        return 1

    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        print(f"Invalid SVG: {svg_path}", file=sys.stderr)
        return 1

    iconset_dir = icons_dir / "app.iconset"
    if iconset_dir.exists():
        shutil.rmtree(iconset_dir)
    iconset_dir.mkdir(parents=True, exist_ok=True)

    sizes = [16, 32, 128, 256, 512]
    for size in sizes:
        for scale in [1, 2]:
            px = size * scale
            image = QImage(QSize(px, px), QImage.Format_ARGB32)
            image.fill(QColor(0, 0, 0, 0))

            painter = QPainter(image)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            renderer.render(painter)
            painter.end()

            suffix = "" if scale == 1 else "@2x"
            out_name = f"icon_{size}x{size}{suffix}.png"
            out_file = iconset_dir / out_name
            if not image.save(str(out_file), "PNG"):
                print(f"Failed to write {out_file}", file=sys.stderr)
                return 1

    icns_path = icons_dir / "app.icns"
    if icns_path.exists():
        icns_path.unlink()

    proc = subprocess.run(
        [iconutil, "-c", "icns", str(iconset_dir), "-o", str(icns_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print("iconutil failed:", file=sys.stderr)
        print(proc.stderr.strip(), file=sys.stderr)
        return proc.returncode

    print(f"Generated {icns_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
