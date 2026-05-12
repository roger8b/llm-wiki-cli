#!/usr/bin/env bash
set -euo pipefail

# wiki CLI installer
# Usage: curl -fsSL <url>/install.sh | bash
#        bash install.sh [--brain <path>] [--no-brain] [--no-git]

REPO_URL="https://github.com/your-org/wiki-cli"  # update before publishing
INSTALL_DIR="${HOME}/.wiki-cli"
BRAIN_PATH="${HOME}/brain"
INIT_BRAIN=true
INIT_GIT=true

# ── parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --brain)   BRAIN_PATH="$2"; shift 2 ;;
    --no-brain) INIT_BRAIN=false; shift ;;
    --no-git)  INIT_GIT=false; shift ;;
    *) echo "unknown option: $1"; exit 1 ;;
  esac
done

# ── colors ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; DIM='\033[2m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*"; exit 1; }
dim()  { echo -e "${DIM}  $*${NC}"; }

echo ""
echo "  wiki CLI installer"
echo ""

# ── prerequisites ─────────────────────────────────────────────────────────────
command -v node >/dev/null 2>&1 || err "Node.js not found. Install from https://nodejs.org (>=18 required)."
command -v npm  >/dev/null 2>&1 || err "npm not found. Install from https://nodejs.org."

NODE_MAJOR=$(node -e "process.stdout.write(process.versions.node.split('.')[0])")
if [[ $NODE_MAJOR -lt 18 ]]; then
  err "Node.js >=18 required (found $NODE_MAJOR). Upgrade at https://nodejs.org."
fi
ok "Node.js $(node --version)"

# ── install ───────────────────────────────────────────────────────────────────
if [[ -d "$INSTALL_DIR" ]]; then
  warn "existing install found at $INSTALL_DIR — pulling latest"
  git -C "$INSTALL_DIR" pull --quiet
else
  dim "cloning to $INSTALL_DIR …"
  git clone --quiet "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"
dim "installing dependencies …"
npm install --silent
dim "building …"
npm run build --silent
npm link --silent

ok "wiki CLI installed ($(wiki --version 2>/dev/null || echo 'ok'))"

# ── bootstrap brain ───────────────────────────────────────────────────────────
if $INIT_BRAIN; then
  echo ""
  if [[ -f "${BRAIN_PATH}/wiki.config.yaml" ]]; then
    warn "brain already exists at ${BRAIN_PATH} — skipping bootstrap"
    wiki config set-root "$BRAIN_PATH"
  else
    dim "creating brain at ${BRAIN_PATH} …"
    WIKI_ARGS=("$BRAIN_PATH")
    if $INIT_GIT; then
      WIKI_ARGS+=("--git")
    fi
    wiki bootstrap "${WIKI_ARGS[@]}"
    ok "brain ready at ${BRAIN_PATH}"
  fi
fi

# ── done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}All done.${NC}"
echo ""
echo "  Next steps:"
echo "  1. wiki doctor                     — verify the brain"
echo "  2. cd ~/your-project && wiki init  — wire a project (interactive)"
echo "  3. wiki --help                     — full command reference"
echo ""
