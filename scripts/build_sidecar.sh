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
  "$PY" -m pip install --quiet pyinstaller
fi

# --- build --------------------------------------------------------------
WORK="$ROOT/.build-sidecar"
rm -rf "$WORK"
mkdir -p "$WORK" "$BIN_DIR"

echo "==> Running PyInstaller (this can take a few minutes)"
"$PY" -m PyInstaller \
  --onefile \
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

# --onefile produces a single standalone executable.
SRC="$WORK/dist/wiki-backend"
DEST="$BIN_DIR/wiki-backend-$TRIPLE"

# Remove any old _internal folder and copy the standalone binary
rm -rf "$BIN_DIR/_internal"
cp "$SRC" "$DEST"

echo ""
echo "OK. Sidecar built as a single self-contained file:"
echo "  $DEST"
echo ""
