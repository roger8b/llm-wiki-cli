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

# --- sqlite-vec loadability guard (#319) --------------------------------
# PyInstaller bundles $PY's own sqlite3. If that build lacks
# enable_load_extension (uv python-build-standalone, system python on macOS),
# the frozen sidecar can NEVER load sqlite-vec and semantic embeddings stay 0
# at runtime — silently degrading to FTS-only. Fail the build loudly here
# instead of shipping a sidecar that can't do hybrid search.
# Override with SKIP_VEC_CHECK=1 only if you knowingly want an FTS-only bundle.
if [ "${SKIP_VEC_CHECK:-0}" != "1" ]; then
  if ! "$PY" -c "import sqlite3,sys; sys.exit(0 if hasattr(sqlite3.connect(':memory:'),'enable_load_extension') else 1)"; then
    echo "ERROR: $PY's sqlite3 has no enable_load_extension — sqlite-vec can't load." >&2
    echo "       The sidecar would ship with semantic search dead (page_embeddings=0)." >&2
    echo "       Use a Python whose sqlite3 supports loadable extensions, e.g.:" >&2
    echo "         PYTHON=\$(brew --prefix python)/bin/python3 ./scripts/build_sidecar.sh" >&2
    echo "       Or set SKIP_VEC_CHECK=1 to build an FTS-only sidecar on purpose." >&2
    exit 1
  fi
fi

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

# --- ensure runtime extras --------------------------------------------
# PyInstaller only bundles what it can import, and the extractors/providers
# import their backends lazily inside functions — so EVERY optional dep must be
# installed in this build env or the frozen sidecar ships without it and fails
# at runtime with "install the [x] extra" (useless advice for a frozen binary).
# This installs the full feature set so the sidecar contemplates all of the app:
#   agent/ollama/anthropic/openai/google → all LLM + embedding providers
#   api/mcp                              → server + MCP interfaces
#   pdf/html                             → document extractors
#   semantic                             → sqlite-vec vector search (#169)
#   audio                                → faster-whisper transcription (#76)
# NOTE: `audio` drags in ctranslate2/onnxruntime/av and adds ~hundreds of MB to
# the bundle. Drop it from the list (and the audio --collect-all flags below) if
# transcription isn't needed and bundle size matters.
EXTRAS="agent,ollama,anthropic,openai,google,api,mcp,pdf,html,semantic,audio"
echo "==> Installing project + all feature extras ($EXTRAS)"
"$PY" -m pip install --quiet -e "$ROOT[$EXTRAS]"

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
  --collect-all langchain_anthropic \
  --collect-all langchain_openai \
  --collect-all langchain_google_genai \
  --collect-all langgraph \
  --collect-all deepagents \
  --collect-submodules llmwiki \
  --collect-data llmwiki \
  --collect-all pypdf \
  --collect-all trafilatura \
  --collect-all sqlite_vec \
  --collect-all faster_whisper \
  --collect-all ctranslate2 \
  --collect-all onnxruntime \
  --collect-all av \
  --collect-all tokenizers \
  --collect-all huggingface_hub \
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
