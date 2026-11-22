#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Update checker helpers based on GitHub Releases."""

from __future__ import annotations

import concurrent.futures
import json
import logging
import re
import socket
import ssl
import urllib.error
import urllib.request

_log = logging.getLogger(__name__)


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
    """Fetch JSON with a guaranteed hard wall-clock timeout.

    On macOS in PyInstaller frozen apps, ``urllib.request.urlopen`` can hang
    indefinitely during DNS resolution or proxy negotiation because the socket
    ``timeout`` parameter only applies to socket I/O, NOT to ``getaddrinfo()``.
    Wrapping the call in a ``ThreadPoolExecutor`` future with ``result(timeout=…)``
    provides a true wall-clock limit that survives those stalls.

    SSL certificate fallback is retained for macOS builds that ship without a
    usable root-cert bundle.
    """

    def _fetch(ctx=None) -> dict | list:
        old_default = socket.getdefaulttimeout()
        # Belt-and-suspenders: setdefaulttimeout nudges getaddrinfo on some platforms.
        socket.setdefaulttimeout(timeout_sec)
        try:
            kw: dict = {"timeout": timeout_sec}
            if ctx is not None:
                kw["context"] = ctx
            _log.debug("[UpdateCheck] urlopen start (ctx=%s)", "insecure" if ctx is not None else "default")
            with urllib.request.urlopen(req, **kw) as r:
                data = r.read()
            _log.debug("[UpdateCheck] urlopen done, %d bytes", len(data))
            return json.loads(data.decode("utf-8"))
        finally:
            socket.setdefaulttimeout(old_default)

    hard_limit = timeout_sec + 3.0
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        fut = pool.submit(_fetch)
        try:
            return fut.result(timeout=hard_limit)
        except concurrent.futures.TimeoutError:
            _log.error("[UpdateCheck] Hard timeout (%.0fs) – DNS or proxy stall suspected", hard_limit)
            raise urllib.error.URLError(f"hard timeout after {hard_limit:.0f}s (DNS/proxy stall)")
        except urllib.error.URLError as url_exc:
            reason = url_exc.reason
            is_cert = isinstance(reason, ssl.SSLCertVerificationError) or (
                isinstance(reason, ssl.SSLError) and "CERTIFICATE_VERIFY_FAILED" in str(reason)
            )
            if not is_cert:
                raise
            # SSL cert fallback: some macOS frozen builds lack the root-cert bundle.
            _log.warning("[UpdateCheck] SSL cert error, retrying without verification")
            insecure_ctx = ssl._create_unverified_context()
            fut2 = pool.submit(_fetch, insecure_ctx)
            try:
                return fut2.result(timeout=hard_limit)
            except concurrent.futures.TimeoutError:
                _log.error("[UpdateCheck] Hard timeout (no-verify) (%.0fs)", hard_limit)
                raise urllib.error.URLError(f"hard timeout (no-verify) after {hard_limit:.0f}s")
    finally:
        pool.shutdown(wait=False)


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
