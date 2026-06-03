#!/usr/bin/env bash
# llm-wiki macOS desktop installer.
#
# Downloads the latest release DMG, installs llm-wiki.app into /Applications,
# clears the Gatekeeper quarantine flag (the app is not Apple-notarized) and
# optionally launches it.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/roger8b/llm-wiki-cli/main/install-desktop.sh | bash
#
# Options (env):
#   VERSION=v2.1.0   install a specific tag instead of the latest release
#   NO_LAUNCH=1      install but do not open the app afterwards
#   ALLOW_ANY_ARCH=1 skip the Apple Silicon check (e.g. under a Rosetta shell
#                    where `uname -m` misreports an arm64 Mac as x86_64)
set -euo pipefail

REPO="roger8b/llm-wiki-cli"
APP_NAME="llm-wiki.app"
INSTALL_DIR="/Applications"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# ── sanity checks ───────────────────────────────────────────────────────────
[ "$(uname -s)" = "Darwin" ] || die "this installer is for macOS only"

arch="$(uname -m)"
if [ "$arch" != "arm64" ] && [ "${ALLOW_ANY_ARCH:-0}" != "1" ]; then
  die "this Mac is '$arch'; the release DMG targets Apple Silicon (arm64) only. \
If this is an Apple Silicon Mac running under a Rosetta shell, re-run with ALLOW_ANY_ARCH=1."
fi

for bin in curl hdiutil ditto; do
  command -v "$bin" >/dev/null 2>&1 || die "required tool '$bin' not found"
done

# ── resolve download URL ────────────────────────────────────────────────────
api="https://api.github.com/repos/$REPO/releases"
if [ -n "${VERSION:-}" ]; then
  info "Looking up release $VERSION"
  release_json="$(curl -fsSL "$api/tags/$VERSION")" || die "release $VERSION not found"
else
  info "Looking up latest release"
  release_json="$(curl -fsSL "$api/latest")" || die "could not query latest release"
fi

# Extract the first .dmg asset's browser_download_url without requiring jq.
dmg_url="$(printf '%s' "$release_json" \
  | grep -oE '"browser_download_url"[^"]*"[^"]*\.dmg"' \
  | head -1 \
  | sed -E 's/.*"(https[^"]+\.dmg)"$/\1/')"

[ -n "$dmg_url" ] || die "no .dmg asset found in the release"

# ── download ────────────────────────────────────────────────────────────────
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"; [ -n "${mount:-}" ] && hdiutil detach "$mount" -quiet 2>/dev/null || true' EXIT

dmg="$tmp/llm-wiki.dmg"
info "Downloading $(basename "$dmg_url")"
curl -fL --progress-bar "$dmg_url" -o "$dmg" || die "download failed"

# ── mount, copy, detach ─────────────────────────────────────────────────────
info "Mounting DMG"
mount="$(hdiutil attach "$dmg" -nobrowse -readonly -mountrandom /tmp \
  | grep -oE '/tmp/[^ ]+' | tail -1)"
[ -n "$mount" ] && [ -d "$mount" ] || die "could not mount DMG"

src="$mount/$APP_NAME"
[ -d "$src" ] || src="$(find "$mount" -maxdepth 1 -name '*.app' | head -1)"
[ -d "$src" ] || die "could not find an .app inside the DMG"

dest="$INSTALL_DIR/$(basename "$src")"
if [ -d "$dest" ]; then
  info "Removing previous install at $dest"
  rm -rf "$dest" 2>/dev/null || sudo rm -rf "$dest"
fi

info "Installing to $dest"
ditto "$src" "$dest" 2>/dev/null || sudo ditto "$src" "$dest"

hdiutil detach "$mount" -quiet 2>/dev/null || true
mount=""

# ── clear quarantine (unsigned app) ─────────────────────────────────────────
info "Clearing Gatekeeper quarantine flag"
xattr -cr "$dest" 2>/dev/null || sudo xattr -cr "$dest"

echo ""
info "Installed: $dest"

# ── launch ──────────────────────────────────────────────────────────────────
if [ "${NO_LAUNCH:-0}" = "1" ]; then
  echo "Open it from Applications when ready."
else
  info "Launching llm-wiki"
  open "$dest"
fi
