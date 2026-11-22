#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bump APP_VERSION in app/shared/version.py using semantic versioning."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


VERSION_FILE = Path(__file__).resolve().parents[1] / "app" / "shared" / "version.py"
VERSION_RE = re.compile(r'^APP_VERSION\s*=\s*"([^"]+)"\s*$', re.MULTILINE)
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc)\.(\d+))?$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bump application version")
    parser.add_argument(
        "--part",
        choices=("patch", "minor", "major"),
        default="patch",
        help="Which semantic version part to bump (default: patch)",
    )
    parser.add_argument(
        "--channel",
        choices=("stable", "alpha", "beta", "rc"),
        default="stable",
        help="Release channel for the new version (default: stable)",
    )
    return parser.parse_args()


def bump_core(major: int, minor: int, patch: int, part: str) -> tuple[int, int, int]:
    if part == "major":
        return major + 1, 0, 0
    if part == "minor":
        return major, minor + 1, 0
    return major, minor, patch + 1


def next_version(
    current_major: int,
    current_minor: int,
    current_patch: int,
    current_channel: str | None,
    current_pre_num: int,
    part: str,
    target_channel: str,
) -> str:
    """Compute next version according to semver + prerelease conventions."""
    if target_channel == "stable":
        # Promote prerelease to stable on same core by default for patch.
        if part == "patch" and current_channel is not None:
            return f"{current_major}.{current_minor}.{current_patch}"

        n_major, n_minor, n_patch = bump_core(current_major, current_minor, current_patch, part)
        return f"{n_major}.{n_minor}.{n_patch}"

    # Keep incrementing prerelease number for the same channel/core when patch.
    if part == "patch" and current_channel == target_channel:
        return f"{current_major}.{current_minor}.{current_patch}-{target_channel}.{current_pre_num + 1}"

    n_major, n_minor, n_patch = bump_core(current_major, current_minor, current_patch, part)
    return f"{n_major}.{n_minor}.{n_patch}-{target_channel}.1"


def main() -> int:
    args = parse_args()

    if not VERSION_FILE.exists():
        print(f"Version file not found: {VERSION_FILE}", file=sys.stderr)
        return 1

    content = VERSION_FILE.read_text(encoding="utf-8")
    match = VERSION_RE.search(content)
    if not match:
        print("APP_VERSION assignment not found in version.py", file=sys.stderr)
        return 1

    current = match.group(1)
    sem = SEMVER_RE.match(current)
    if not sem:
        print(f"Current APP_VERSION is not semver-compatible: {current}", file=sys.stderr)
        return 1

    major = int(sem.group(1))
    minor = int(sem.group(2))
    patch = int(sem.group(3))
    current_channel = sem.group(4)
    current_pre_num = int(sem.group(5) or 0)

    new_version = next_version(
        current_major=major,
        current_minor=minor,
        current_patch=patch,
        current_channel=current_channel,
        current_pre_num=current_pre_num,
        part=args.part,
        target_channel=args.channel,
    )

    new_content = (
        content[: match.start(1)]
        + new_version
        + content[match.end(1) :]
    )
    VERSION_FILE.write_text(new_content, encoding="utf-8")
    print(new_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
