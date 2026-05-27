#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="${APP_NAME:-FFBuilder}"
VERSION="${VERSION:-$(date +%Y.%m.%d)}"
RELEASE_AUTOMATION="${RELEASE_AUTOMATION:-ask}"  # ask|on|off
BUMP_PART="${BUMP_PART:-}"
RELEASE_CHANNEL="${RELEASE_CHANNEL:-}"
PUSH_RELEASE="${PUSH_RELEASE:-}"  # 1|0; empty means prompt in ask mode
MIN_MACOS="${MIN_MACOS:-10.13}"
HOST_ARCH="$(uname -m)"
if [[ "$HOST_ARCH" == "arm64" ]]; then
  DEFAULT_TARGET_ARCH="arm64"
elif [[ "$HOST_ARCH" == "x86_64" ]]; then
  DEFAULT_TARGET_ARCH="x86_64"
else
  DEFAULT_TARGET_ARCH="arm64"
fi
TARGET_ARCH="${TARGET_ARCH:-$DEFAULT_TARGET_ARCH}"
LEGACY_MACOS="${LEGACY_MACOS:-0}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script must be run on macOS."
  exit 1
fi

is_tty=0
if [[ -t 0 ]]; then
  is_tty=1
fi

_ask_yes_no() {
  local prompt="$1"
  local default="${2:-N}"
  local answer=""
  local answer_lc=""
  if [[ "$is_tty" != "1" ]]; then
    [[ "$default" == "Y" ]]
    return
  fi
  read -r -p "$prompt" answer
  answer="${answer:-$default}"
  answer_lc="$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')"
  case "$answer_lc" in
    y|yes|i|igen) return 0 ;;
    *) return 1 ;;
  esac
}

_pick_bump_part() {
  local part="${BUMP_PART:-patch}"
  if [[ "$is_tty" == "1" && -z "$BUMP_PART" ]]; then
    read -r -p "Verzió emelés típusa [patch/minor/major] (alapértelmezett: patch): " part
    part="${part:-patch}"
  fi
  case "$part" in
    patch|minor|major)
      BUMP_PART="$part"
      ;;
    *)
      echo "Invalid BUMP_PART: $part"
      exit 1
      ;;
  esac
}

_pick_release_channel() {
  local channel="${RELEASE_CHANNEL:-alpha}"
  if [[ "$is_tty" == "1" && -z "$RELEASE_CHANNEL" ]]; then
    read -r -p "Release csatorna [stable/alpha/beta/rc] (alapértelmezett: alpha): " channel
    channel="${channel:-alpha}"
  fi
  case "$channel" in
    stable|alpha|beta|rc)
      RELEASE_CHANNEL="$channel"
      ;;
    *)
      echo "Invalid RELEASE_CHANNEL: $channel"
      exit 1
      ;;
  esac
}

_require_clean_git_worktree() {
  if ! git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Release automation requires a git repository."
    exit 1
  fi

  if [[ -n "$(git -C "$ROOT_DIR" status --porcelain)" ]]; then
    echo "Working tree is not clean. Commit/stash changes before release automation."
    exit 1
  fi
}

if [[ "$LEGACY_MACOS" == "1" ]]; then
  # Legacy profile targets older Intel macOS releases.
  MIN_MACOS="${MIN_MACOS:-10.12}"
  TARGET_ARCH="${TARGET_ARCH:-x86_64}"
fi

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "python3 not found."
  exit 1
fi

# Verify assets folder exists
if [[ ! -d "$ROOT_DIR/assets" ]]; then
  echo "Error: assets folder not found at $ROOT_DIR/assets"
  exit 1
fi

# Check for icon file
ICON_PATH=""
if [[ -f "$ROOT_DIR/assets/icons/app.icns" ]]; then
  ICON_PATH="$ROOT_DIR/assets/icons/app.icns"
fi

if [[ -z "$ICON_PATH" && -f "$ROOT_DIR/installers/generate_macos_icon.py" ]]; then
  echo "Icon not found, generating app.icns from SVG..."
  if "$PYTHON_BIN" "$ROOT_DIR/installers/generate_macos_icon.py"; then
    if [[ -f "$ROOT_DIR/assets/icons/app.icns" ]]; then
      ICON_PATH="$ROOT_DIR/assets/icons/app.icns"
    fi
  else
    echo "Warning: icon generation failed. Continuing without app icon."
  fi
fi

echo "Using python: $PYTHON_BIN"
echo "Minimum macOS target: $MIN_MACOS"
echo "Target architecture: $TARGET_ARCH"
if [[ -n "$ICON_PATH" ]]; then
  echo "Using icon: $ICON_PATH"
fi

if [[ "$MIN_MACOS" == "10.12" ]]; then
  echo "Legacy note: Sierra-compatible builds are only reliable when built with Sierra-era Python/dependencies."
fi

if [[ "$TARGET_ARCH" == "universal2" ]]; then
  echo "Note: universal2 requires universal/fat binaries for all native dependencies."
  echo "If build fails with IncompatibleBinaryArchError, use TARGET_ARCH=$DEFAULT_TARGET_ARCH."
fi

DO_RELEASE_AUTOMATION=0
case "$RELEASE_AUTOMATION" in
  on)
    DO_RELEASE_AUTOMATION=1
    ;;
  off)
    DO_RELEASE_AUTOMATION=0
    ;;
  ask)
    if _ask_yes_no "Build után automatikus release (verzió bump + tag + push)? [y/N]: " "N"; then
      DO_RELEASE_AUTOMATION=1
    fi
    ;;
  *)
    echo "Invalid RELEASE_AUTOMATION: $RELEASE_AUTOMATION (use ask|on|off)"
    exit 1
    ;;
esac

RELEASE_TAG=""
if [[ "$DO_RELEASE_AUTOMATION" == "1" ]]; then
  _require_clean_git_worktree
  _pick_bump_part
  _pick_release_channel

  if [[ ! -f "$ROOT_DIR/tools/bump_version.py" ]]; then
    echo "Missing bump tool: $ROOT_DIR/tools/bump_version.py"
    exit 1
  fi

  echo "Bumping version: part=$BUMP_PART channel=$RELEASE_CHANNEL"
  VERSION="$($PYTHON_BIN "$ROOT_DIR/tools/bump_version.py" --part "$BUMP_PART" --channel "$RELEASE_CHANNEL")"
  RELEASE_TAG="v$VERSION"
  echo "New version: $VERSION"
fi

"$PYTHON_BIN" -m pip install --upgrade pip "pyinstaller>=6.0"

cd "$ROOT_DIR"

if [[ -f "main.py" ]]; then
  ENTRYPOINT="main.py"
elif [[ -f "__main__.py" ]]; then
  ENTRYPOINT="__main__.py"
else
  echo "Build failed: neither main.py nor __main__.py was found in project root."
  exit 1
fi

rm -rf build dist "$APP_NAME.spec"

export MACOSX_DEPLOYMENT_TARGET="$MIN_MACOS"

PYINSTALLER_ARGS=(
  "--noconfirm"
  "--clean"
  "--windowed"
  "--strip"
  "--target-arch" "$TARGET_ARCH"
  "--name" "$APP_NAME"
  "--add-data" "assets:assets"
  "--add-data" "app/gui_qt/ui:app/gui_qt/ui"
  "--add-data" "app/templates/default_templates:app/templates/default_templates"
  # QML / Quick stack – not used
  "--exclude-module" "PySide6.QtQuick"
  "--exclude-module" "PySide6.QtQml"
  "--exclude-module" "PySide6.QtQmlModels"
  "--exclude-module" "PySide6.QtQmlWorkerScript"
  "--exclude-module" "PySide6.QtQmlMeta"
  # Large optional Qt modules – not used
  "--exclude-module" "PySide6.QtPdf"
  "--exclude-module" "PySide6.QtVirtualKeyboard"
  "--exclude-module" "PySide6.QtBluetooth"
  "--exclude-module" "PySide6.QtMultimedia"
  "--exclude-module" "PySide6.QtMultimediaWidgets"
  "--exclude-module" "PySide6.QtWebEngine"
  "--exclude-module" "PySide6.QtWebEngineCore"
  "--exclude-module" "PySide6.QtWebEngineWidgets"
  "--exclude-module" "PySide6.QtCharts"
  "--exclude-module" "PySide6.QtDataVisualization"
  "--exclude-module" "PySide6.QtSql"
  "--exclude-module" "PySide6.QtTest"
  "--exclude-module" "PySide6.QtSerialPort"
  "--exclude-module" "PySide6.QtSerialBus"
  "--exclude-module" "PySide6.QtTextToSpeech"
  "--exclude-module" "PySide6.QtSensors"
  "--exclude-module" "PySide6.Qt3DCore"
  "--exclude-module" "PySide6.Qt3DRender"
  "--exclude-module" "PySide6.Qt3DInput"
  "--exclude-module" "PySide6.Qt3DLogic"
  "--exclude-module" "PySide6.Qt3DAnimation"
  "--exclude-module" "PySide6.Qt3DExtras"
  "--exclude-module" "PySide6.QtRemoteObjects"
  "--exclude-module" "PySide6.QtStateMachine"
  "--exclude-module" "PySide6.QtConcurrent"
  # Unused stdlib heavyweights
  "--exclude-module" "tkinter"
  "--exclude-module" "unittest"
  "--exclude-module" "xmlrpc"
  "--exclude-module" "pydoc"
  "--exclude-module" "doctest"
  # Removed dependencies (replaced by native Qt drawing)
  "--exclude-module" "matplotlib"
  "--exclude-module" "numpy"
  "--exclude-module" "PIL"
  "--exclude-module" "contourpy"
  "--exclude-module" "cycler"
  "--exclude-module" "kiwisolver"
)

if [[ -n "$ICON_PATH" ]]; then
  PYINSTALLER_ARGS+=("--icon" "$ICON_PATH")
fi

"$PYTHON_BIN" -m PyInstaller "${PYINSTALLER_ARGS[@]}" "$ENTRYPOINT"

APP_PATH="dist/$APP_NAME.app"
DMG_PATH="dist/${APP_NAME}-${VERSION}-macos.dmg"
NOTARIZE="${NOTARIZE:-0}"
NOTARY_PROFILE="${NOTARY_PROFILE:-}"

if [[ ! -d "$APP_PATH" ]]; then
  echo "Build failed: app bundle not found at $APP_PATH"
  exit 1
fi

# Remove quarantine from the local build so it can be tested directly
# without running xattr manually. Downloaded copies still get quarantine
# applied by the browser — notarization is the only fix for distribution.
xattr -cr "$APP_PATH" 2>/dev/null || true

# Optional code signing (only if CODESIGN_IDENTITY is set)
if [[ -n "${CODESIGN_IDENTITY:-}" ]]; then
  echo "Signing app with identity: $CODESIGN_IDENTITY"
  if ! codesign --force --deep --sign "$CODESIGN_IDENTITY" "$APP_PATH"; then
    echo "Warning: Code signing failed, but continuing with DMG creation."
  fi
fi

DMG_STAGING="$(mktemp -d)"
ditto "$APP_PATH" "$DMG_STAGING/$(basename "$APP_PATH")"
ln -s /Applications "$DMG_STAGING/Applications"
hdiutil create -volname "$APP_NAME" -srcfolder "$DMG_STAGING" -ov -format UDZO "$DMG_PATH"
rm -rf "$DMG_STAGING"

if [[ ! -f "$DMG_PATH" ]]; then
  echo "Build failed: DMG file not created at $DMG_PATH"
  exit 1
fi

if [[ "$NOTARIZE" == "1" ]]; then
  if ! command -v xcrun >/dev/null 2>&1; then
    echo "Notarization failed: xcrun not found. Install Xcode command line tools."
    exit 1
  fi

  if [[ -z "$NOTARY_PROFILE" ]]; then
    echo "Notarization failed: set NOTARY_PROFILE to a notarytool keychain profile name."
    echo "Example: xcrun notarytool store-credentials my-profile --apple-id <id> --team-id <team> --password <app-specific-password>"
    exit 1
  fi

  echo "Submitting DMG for notarization with profile: $NOTARY_PROFILE"
  xcrun notarytool submit "$DMG_PATH" --keychain-profile "$NOTARY_PROFILE" --wait

  echo "Stapling notarization tickets..."
  xcrun stapler staple "$APP_PATH"
  xcrun stapler staple "$DMG_PATH"

  echo "Running Gatekeeper assessment..."
  spctl --assess --type open --verbose "$DMG_PATH"
fi

echo "Done."
echo "App: $APP_PATH"
echo "DMG: $DMG_PATH"

if [[ "$DO_RELEASE_AUTOMATION" == "1" ]]; then
  echo "Preparing git release..."
  git add app/shared/version.py

  if git diff --cached --quiet; then
    echo "No version change to commit; skipping release automation."
    exit 1
  fi

  git commit -m "chore(release): $RELEASE_TAG"

  if git rev-parse "$RELEASE_TAG" >/dev/null 2>&1; then
    echo "Tag already exists: $RELEASE_TAG"
    exit 1
  fi
  git tag "$RELEASE_TAG"

  DO_PUSH=1
  if [[ -n "$PUSH_RELEASE" ]]; then
    case "$PUSH_RELEASE" in
      1|0) DO_PUSH="$PUSH_RELEASE" ;;
      *)
        echo "Invalid PUSH_RELEASE: $PUSH_RELEASE (use 1 or 0)"
        exit 1
        ;;
    esac
  elif [[ "$is_tty" == "1" && "$RELEASE_AUTOMATION" == "ask" ]]; then
    if _ask_yes_no "Push commit + tag az origin remote-ra? [Y/n]: " "Y"; then
      DO_PUSH=1
    else
      DO_PUSH=0
    fi
  fi

  if [[ "$DO_PUSH" == "1" ]]; then
    git push origin HEAD
    git push origin "$RELEASE_TAG"
    echo "Release pushed. GitHub Actions will build and publish: $RELEASE_TAG"
  else
    echo "Push skipped. Push manually when ready:"
    echo "  git push origin HEAD"
    echo "  git push origin $RELEASE_TAG"
  fi
fi
