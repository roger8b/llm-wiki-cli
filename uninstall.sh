#!/usr/bin/env bash
# Uninstaller for llm-wiki.
#
# Removes the venv and the llmwiki binary symlink created by install.sh.
# Brain directories (your knowledge bases) are NEVER touched.
#
# Usage:
#   ./uninstall.sh
#   LLMWIKI_HOME=~/.llmwiki LLMWIKI_BIN=~/.local/bin ./uninstall.sh
#   ./uninstall.sh --yes     # skip confirmation prompt
set -euo pipefail

HOME_DIR="${LLMWIKI_HOME:-$HOME/.llmwiki}"
BIN_DIR="${LLMWIKI_BIN:-$HOME/.local/bin}"
BINARY="$BIN_DIR/llmwiki"
VENV="$HOME_DIR/venv"
SKIP_CONFIRM=0

for arg in "$@"; do
  case "$arg" in
    --yes|-y) SKIP_CONFIRM=1 ;;
  esac
done

# --- summary of what will be removed ------------------------------------
echo ""
echo "llm-wiki uninstaller"
echo "===================="
echo ""
echo "Will remove:"
[ -d "$VENV" ]   && echo "  venv      $VENV" || echo "  venv      $VENV  (not found — already removed)"
[ -e "$BINARY" ] && echo "  binary    $BINARY" || echo "  binary    $BINARY  (not found — already removed)"
echo ""
echo "Will NOT touch:"
echo "  brain directories (your Markdown knowledge bases)"
echo "  shell config files (~/.zshrc, ~/.bashrc)"
echo ""

# --- nothing to do? -----------------------------------------------------
if [ ! -d "$VENV" ] && [ ! -e "$BINARY" ]; then
  echo "Nothing to remove. llm-wiki is not installed."
  exit 0
fi

# --- confirmation -------------------------------------------------------
if [ "$SKIP_CONFIRM" -eq 0 ]; then
  printf "Proceed? [y/N] "
  read -r answer
  case "$answer" in
    [yY][eE][sS]|[yY]) : ;;
    *) echo "Aborted."; exit 0 ;;
  esac
fi

# --- remove binary ------------------------------------------------------
if [ -e "$BINARY" ] || [ -L "$BINARY" ]; then
  echo "==> Removing binary $BINARY"
  rm -f "$BINARY"
fi

# --- remove venv --------------------------------------------------------
if [ -d "$VENV" ]; then
  echo "==> Removing venv $VENV"
  rm -rf "$VENV"
fi

# --- remove HOME_DIR if now empty ---------------------------------------
if [ -d "$HOME_DIR" ] && [ -z "$(ls -A "$HOME_DIR" 2>/dev/null)" ]; then
  echo "==> Removing empty directory $HOME_DIR"
  rmdir "$HOME_DIR"
fi

echo ""
echo "OK. llm-wiki uninstalled."

# --- PATH hint ----------------------------------------------------------
case ":$PATH:" in
  *":$BIN_DIR:"*)
    echo ""
    echo "Note: $BIN_DIR is still in your PATH."
    echo "Remove it from ~/.zshrc or ~/.bashrc if you no longer need it."
    ;;
esac
echo ""
