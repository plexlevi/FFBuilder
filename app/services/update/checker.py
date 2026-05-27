#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Update checker helpers based on GitHub Releases."""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request


_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc)\.(\d+))?$")
_CHANNEL_RANK = {"alpha": 0, "beta": 1, "rc": 2}


def _normalize_tag(tag: str) -> str:
    return tag.strip().lstrip("vV")


def _parse_version(version: str) -> tuple[int, int, int, int, int] | None:
    match = _SEMVER_RE.match(version)
    if not match:
        return None

    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3))
    channel = match.group(4)
    pre_num = int(match.group(5) or 0)

    # Stable release is always newer than pre-release of same core.
    if channel is None:
        return major, minor, patch, 3, 0

    return major, minor, patch, _CHANNEL_RANK.get(channel, 0), pre_num


def _version_tuple_from_tag(tag: str) -> tuple[int, int, int, int, int] | None:
    return _parse_version(_normalize_tag(tag))


def is_newer_version(current: str, candidate: str) -> bool:
    current_t = _parse_version(_normalize_tag(current))
    candidate_t = _parse_version(_normalize_tag(candidate))
    if current_t is None or candidate_t is None:
        return False
    return candidate_t > current_t


def _load_json(req: urllib.request.Request, timeout_sec: float) -> dict | list:
    """Load JSON from URL with SSL fallback for macOS certificate-chain edge cases."""
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        reason = exc.reason
        cert_error = isinstance(reason, ssl.SSLCertVerificationError)
        if not cert_error and isinstance(reason, ssl.SSLError):
            cert_error = "CERTIFICATE_VERIFY_FAILED" in str(reason)
        if not cert_error:
            raise

        # Fallback: some macOS Python builds miss root cert chain configuration.
        insecure_ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=timeout_sec, context=insecure_ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))


def fetch_latest_release(repo: str, timeout_sec: float = 3.0, include_prerelease: bool = True) -> dict:
    """Return latest release metadata from GitHub API.

    Returns dict with keys:
    ok, latest_version, tag_name, html_url, body, prerelease,
    dmg_asset_url, dmg_asset_name, error.
    """
    url = f"https://api.github.com/repos/{repo}/releases?per_page=30"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "FFBuilder-UpdateCheck",
        },
    )

    try:
        payload = _load_json(req, timeout_sec=timeout_sec)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    if not isinstance(payload, list):
        return {"ok": False, "error": "Unexpected releases payload"}

    best_release: dict | None = None
    best_version_tuple: tuple[int, int, int, int, int] | None = None
    for release in payload:
        if not isinstance(release, dict):
            continue
        if bool(release.get("draft", False)):
            continue
        if not include_prerelease and bool(release.get("prerelease", False)):
            continue

        tag_name = str(release.get("tag_name", "")).strip()
        if not tag_name:
            continue
        ver_t = _version_tuple_from_tag(tag_name)
        if ver_t is None:
            continue

        if best_version_tuple is None or ver_t > best_version_tuple:
            best_version_tuple = ver_t
            best_release = release

    if best_release is None:
        return {"ok": False, "error": "No semver-compatible release found"}

    tag = str(best_release.get("tag_name", "")).strip()
    if not tag:
        return {"ok": False, "error": "Missing tag_name in release payload"}

    dmg_asset_url = ""
    dmg_asset_name = ""
    assets = best_release.get("assets", [])
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name", "")).strip()
            if not name.lower().endswith(".dmg"):
                continue
            dmg_asset_name = name
            dmg_asset_url = str(asset.get("browser_download_url", "")).strip()
            if dmg_asset_url:
                break

    return {
        "ok": True,
        "tag_name": tag,
        "latest_version": _normalize_tag(tag),
        "html_url": str(best_release.get("html_url", "")).strip(),
        "body": str(best_release.get("body", "") or ""),
        "prerelease": bool(best_release.get("prerelease", False)),
        "dmg_asset_url": dmg_asset_url,
        "dmg_asset_name": dmg_asset_name,
    }
