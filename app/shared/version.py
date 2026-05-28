#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Application version metadata."""

APP_NAME = "FFBuilder"
APP_VERSION = "0.4.11"
GITHUB_REPO = "plexlevi/FFBuilder"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"


def app_window_title() -> str:
    """Return the main window title with the current version."""
    return f"{APP_NAME} · v{APP_VERSION}"
