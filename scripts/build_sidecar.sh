#!/usr/bin/env bash
# Compile the llm-wiki backend into a standalone binary (Tauri sidecar).
#
# Output: ui/src-tauri/binaries/wiki-backend-<target-triple>
# The target-triple suffix is what Tauri's externalBin resolver expects.
#
# Usage:
#   ./scripts/build_sidecar.sh            # uses the active venv's python
#   PYTHON=/path/to/python ./scripts/build_sidecar.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
BIN_DIR="$ROOT/ui/src-tauri/binaries"
ENTRY="$ROOT/scripts/sidecar_entry.py"

# --- target triple (Tauri convention) ----------------------------------
TRIPLE="$("$PY" - <<'PYEOF'
import platform
m = platform.machine()
arch = "aarch64" if m in ("arm64", "aarch64") else "x86_64"
sysname = platform.system()
if sysname == "Darwin":
    print(f"{arch}-apple-darwin")
elif sysname == "Linux":
    print(f"{arch}-unknown-linux-gnu")
else:
    print(f"{arch}-pc-windows-msvc")
PYEOF
)"
echo "==> Target triple: $TRIPLE"

# --- ensure pyinstaller -------------------------------------------------
if ! "$PY" -c "import PyInstaller" 2>/dev/null; then
  echo "==> Installing pyinstaller"
  # On macOS/Homebrew and other PEP-668-compliant distros, pip refuses to
  # install into the system Python. Use --break-system-packages as a last
  # resort for local builds where no venv is available.
  PIP_FLAGS="--quiet"
  "$PY" -m pip install $PIP_FLAGS --break-system-packages pyinstaller || \
    "$PY" -m pip install $PIP_FLAGS pyinstaller
fi

# --- build --------------------------------------------------------------
WORK="$ROOT/.build-sidecar"
rm -rf "$WORK"
mkdir -p "$WORK" "$BIN_DIR"

# --onedir (NOT --onefile): a onefile bootloader re-extracts the entire ~57MB
# bundle to a temp dir on EVERY launch, costing ~7-8s of pure I/O before the
# CLI even runs. --onedir extracts once at build time; launch just execs the
# binary against the sibling _internal/ folder. Startup drops from ~9s to ~1-2s.
echo "==> Running PyInstaller (this can take a few minutes)"
"$PY" -m PyInstaller \
  --onedir \
  --name wiki-backend \
  --distpath "$WORK/dist" \
  --workpath "$WORK/build" \
  --specpath "$WORK" \
  --noconfirm \
  --collect-all langchain \
  --collect-all langchain_core \
  --collect-all langchain_ollama \
  --collect-all langgraph \
  --collect-all deepagents \
  --collect-submodules llmwiki \
  --collect-data llmwiki \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan.on \
  "$ENTRY"

# --onedir produces dist/wiki-backend/ (exe + _internal/). Tauri bundles this
# whole folder as a resource (see tauri.conf.json) and the Rust shell resolves
# the inner exe at runtime — exe and _internal/ must stay together.
SRC_DIR="$WORK/dist/wiki-backend"
DEST_DIR="$BIN_DIR/wiki-backend"

rm -rf "$DEST_DIR" "$BIN_DIR/_internal" "$BIN_DIR"/wiki-backend-*
cp -R "$SRC_DIR" "$DEST_DIR"

echo ""
echo "OK. Sidecar built as a onedir bundle (exe + _internal/) for triple $TRIPLE:"
echo "  $DEST_DIR/"
echo ""
