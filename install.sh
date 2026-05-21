#!/usr/bin/env bash
# Instalador do llm-wiki (v2, Python).
#
# Cria um venv dedicado, instala o pacote (com extras) e expõe o binário
# `wiki` no PATH via symlink.
#
# Uso:
#   ./install.sh                  # instala do diretório atual
#   LLMWIKI_EXTRAS=api,mcp ./install.sh
#   LLMWIKI_HOME=~/.wiki LLMWIKI_BIN=~/.local/bin ./install.sh
set -euo pipefail

HOME_DIR="${LLMWIKI_HOME:-$HOME/.wiki}"
BIN_DIR="${LLMWIKI_BIN:-$HOME/.local/bin}"
EXTRAS="${LLMWIKI_EXTRAS:-api,mcp,agent,ollama}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- pré-requisito: Python 3.12+ ---------------------------------------
PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "Erro: python3 não encontrado." >&2
  exit 1
fi
PYVER="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,12) else 1)'; then
  echo "Erro: Python >=3.12 exigido (encontrado $PYVER)." >&2
  exit 1
fi

echo "==> Criando venv em $HOME_DIR/venv (Python $PYVER)"
"$PY" -m venv --clear "$HOME_DIR/venv"

echo "==> Instalando llm-wiki[$EXTRAS] de $SRC_DIR"
"$HOME_DIR/venv/bin/pip" install --quiet --upgrade pip
if [ -n "$EXTRAS" ]; then
  "$HOME_DIR/venv/bin/pip" install --quiet "$SRC_DIR[$EXTRAS]"
else
  "$HOME_DIR/venv/bin/pip" install --quiet "$SRC_DIR"
fi

echo "==> Expondo binário em $BIN_DIR/wiki"
mkdir -p "$BIN_DIR"
ln -sf "$HOME_DIR/venv/bin/wiki" "$BIN_DIR/wiki"

echo ""
echo "OK. llm-wiki instalado."
"$HOME_DIR/venv/bin/wiki" version
case ":$PATH:" in
  *":$BIN_DIR:"*) : ;;
  *) echo ""; echo "ATENÇÃO: adicione $BIN_DIR ao PATH:"; echo "  export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac
echo ""
echo "Próximo passo:  wiki init meu-brain && cd meu-brain"
