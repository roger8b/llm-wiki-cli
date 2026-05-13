#!/usr/bin/env bash
set -euo pipefail

# wiki CLI installer
# Usage: curl -fsSL <url>/install.sh | bash
#        bash install.sh [--brain <path>] [--no-brain] [--no-git] [--local]

REPO_URL="https://github.com/roger8b/llm-wiki-cli"
INSTALL_DIR="${HOME}/.wiki-cli"
BRAIN_PATH="${HOME}/brain"
INIT_BRAIN=true
INIT_GIT=true
USE_LOCAL=false
LOCAL_SOURCE=""

# ── parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --brain)    BRAIN_PATH="$2"; shift 2 ;;
    --no-brain) INIT_BRAIN=false; shift ;;
    --no-git)   INIT_GIT=false; shift ;;
    --local)    USE_LOCAL=true
                # if next arg exists and isn't a flag, treat as source path
                if [[ $# -gt 1 && "${2:0:2}" != "--" ]]; then
                  LOCAL_SOURCE="$2"; shift 2
                else
                  shift
                fi ;;
    --help|-h)  cat <<EOF
Usage: $0 [--brain <path>] [--no-brain] [--no-git] [--local [src]]

  --brain <path>   Brain location (default: ~/brain)
  --no-brain       Skip brain creation
  --no-git         Skip git init in brain
  --local [src]    Use local checkout instead of cloning. If 'src' given,
                   syncs from that path into ~/.wiki-cli/. Otherwise uses
                   existing ~/.wiki-cli/.
EOF
                exit 0 ;;
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
if $USE_LOCAL; then
  if [[ -n "$LOCAL_SOURCE" ]]; then
    [[ -d "$LOCAL_SOURCE" ]] || err "local source not found: $LOCAL_SOURCE"
    [[ -f "$LOCAL_SOURCE/package.json" ]] || err "no package.json at $LOCAL_SOURCE"
    dim "syncing $LOCAL_SOURCE → $INSTALL_DIR …"
    mkdir -p "$INSTALL_DIR"
    # use rsync if available, fall back to cp -R (excluding node_modules/dist)
    if command -v rsync >/dev/null 2>&1; then
      rsync -a --delete --exclude node_modules --exclude dist --exclude .git "$LOCAL_SOURCE/" "$INSTALL_DIR/"
    else
      (cd "$LOCAL_SOURCE" && tar --exclude=node_modules --exclude=dist --exclude=.git -cf - .) | (cd "$INSTALL_DIR" && tar -xf -)
    fi
  else
    [[ -d "$INSTALL_DIR" ]] || err "no local install found at $INSTALL_DIR. Run without --local first, or pass --local <src>."
    dim "using existing $INSTALL_DIR"
  fi
elif [[ -d "$INSTALL_DIR/.git" ]]; then
  warn "existing install found at $INSTALL_DIR — pulling latest"
  git -C "$INSTALL_DIR" pull --quiet || warn "git pull failed — continuing with current state"
elif [[ -d "$INSTALL_DIR" ]]; then
  warn "$INSTALL_DIR exists but is not a git checkout — leaving as-is"
else
  dim "cloning to $INSTALL_DIR …"
  git clone --quiet "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"
dim "installing dependencies …"
npm install --silent
dim "building …"
npm run build --silent
npm link --silent 2>/dev/null || warn "npm link failed — you may need to run it manually (sudo npm link)"

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
