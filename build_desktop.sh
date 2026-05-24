#!/usr/bin/env bash
# Automation script to compile the Python sidecar and build the Tauri desktop app.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "==> 1. Compiling Python sidecar backend binary..."
PYTHON=.venv/bin/python ./scripts/build_sidecar.sh

echo "==> 2. Moving to frontend directory..."
cd ui

if [ ! -d "node_modules" ]; then
  echo "==> node_modules not found, installing frontend dependencies..."
  npm install
fi

echo "==> 3. Building Tauri macOS application..."
npx tauri build

echo ""
echo "=========================================================="
echo "SUCCESS: App built successfully!"
echo "=========================================================="
echo "Installer DMG: ui/src-tauri/target/release/bundle/dmg/llm-wiki_2.0.0_aarch64.dmg"
echo "App Bundle:    ui/src-tauri/target/release/bundle/macos/llm-wiki.app"
echo "=========================================================="
