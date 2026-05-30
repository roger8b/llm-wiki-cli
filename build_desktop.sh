#!/usr/bin/env bash
# Automation script to compile the Python sidecar and build the Tauri desktop app.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Build the SPA FIRST so the PyInstaller sidecar bundles the current frontend.
# (build_sidecar collects src/llmwiki/.../dist; building it after the sidecar
# would freeze a one-build-old SPA into the binary.)
echo "==> 1. Building frontend SPA..."
cd ui
if [ ! -d "node_modules" ]; then
  echo "==> node_modules not found, installing frontend dependencies..."
  npm install
fi
npm run build
cd "$ROOT"

echo "==> 2. Compiling Python sidecar backend binary..."
# Resolve Python: prefer .venv if it exists, otherwise fall back to system python3.
if [ -f ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="python3"
fi
echo "==> Using Python: $PYTHON"

PYTHON="$PYTHON" ./scripts/build_sidecar.sh

echo "==> 3. Building Tauri macOS application..."
# bundle_dmg.sh fails if a volume named "llm-wiki" from a previous DMG is still
# mounted — detach any stragglers and remove leftover temp DMGs first.
while [ -d "/Volumes/llm-wiki" ]; do
  echo "==> Detaching stale /Volumes/llm-wiki"
  hdiutil detach "/Volumes/llm-wiki" -force >/dev/null 2>&1 || break
done
rm -f ui/src-tauri/target/release/bundle/macos/rw.*.dmg 2>/dev/null || true

cd ui
npx tauri build

echo ""
echo "=========================================================="
echo "SUCCESS: App built successfully!"
echo "=========================================================="
echo "Installer DMG: ui/src-tauri/target/release/bundle/dmg/llm-wiki_2.0.0_aarch64.dmg"
echo "App Bundle:    ui/src-tauri/target/release/bundle/macos/llm-wiki.app"
echo "=========================================================="