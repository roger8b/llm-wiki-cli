#!/usr/bin/env bash
# Cut a new llm-wiki release.
#
# Bumps the version in pyproject.toml and tauri.conf.json, commits the bump,
# creates a `v<version>` tag and pushes it. The CI workflow then builds the
# macOS DMG and publishes it to a public GitHub Release.
#
# Usage:
#   ./scripts/release.sh 2.1.0          # set explicit version
#   ./scripts/release.sh patch          # bump 2.0.0 -> 2.0.1
#   ./scripts/release.sh minor          # bump 2.0.0 -> 2.1.0
#   ./scripts/release.sh major          # bump 2.0.0 -> 3.0.0
#
# Options (env):
#   DRY_RUN=1   show what would happen without committing/tagging/pushing
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYPROJECT="pyproject.toml"
TAURI_CONF="ui/src-tauri/tauri.conf.json"
REMOTE="${REMOTE:-origin}"

die()  { echo "error: $*" >&2; exit 1; }
warn() { echo "warning: $*" >&2; }

[ $# -eq 1 ] || die "usage: $0 <major|minor|patch|X.Y.Z>"

# ── read current version (source of truth: pyproject.toml) ──────────────────
current="$(grep -E '^version *= *"' "$PYPROJECT" | head -1 | sed -E 's/.*"([^"]+)".*/\1/')"
[ -n "$current" ] || die "could not read current version from $PYPROJECT"

# ── resolve target version ──────────────────────────────────────────────────
arg="$1"
case "$arg" in
  major|minor|patch)
    IFS=. read -r MA MI PA <<<"$current"
    [[ "$MA" =~ ^[0-9]+$ && "$MI" =~ ^[0-9]+$ && "$PA" =~ ^[0-9]+$ ]] \
      || die "current version '$current' is not plain X.Y.Z; pass an explicit version"
    case "$arg" in
      major) MA=$((MA+1)); MI=0; PA=0 ;;
      minor) MI=$((MI+1)); PA=0 ;;
      patch) PA=$((PA+1)) ;;
    esac
    version="$MA.$MI.$PA"
    ;;
  *)
    [[ "$arg" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "version must be X.Y.Z, got '$arg'"
    version="$arg"
    ;;
esac

tag="v$version"
echo "==> Current version: $current"
echo "==> New version:     $version  (tag $tag)"

# ── safety checks ───────────────────────────────────────────────────────────
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not a git repository"

branch="$(git rev-parse --abbrev-ref HEAD)"
[ "$branch" != "HEAD" ] || die "detached HEAD — checkout main before releasing"
if [ "$branch" != "main" ]; then
  if [ "${ALLOW_BRANCH:-0}" = "1" ]; then
    warn "releasing from '$branch' (ALLOW_BRANCH=1)"
  else
    die "must release from main (on '$branch'); set ALLOW_BRANCH=1 to override"
  fi
fi

if [ -n "$(git status --porcelain)" ]; then
  if [ "${DRY_RUN:-0}" = "1" ]; then
    warn "working tree is dirty (ignored in dry-run)"
  else
    die "working tree is dirty — commit or stash changes before releasing"
  fi
fi

if git rev-parse "$tag" >/dev/null 2>&1; then
  die "tag $tag already exists locally"
fi
if [ -n "$(git ls-remote --tags "$REMOTE" "refs/tags/$tag" 2>/dev/null)" ]; then
  die "tag $tag already exists on $REMOTE"
fi

if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "[dry-run] would bump $PYPROJECT and $TAURI_CONF to $version"
  echo "[dry-run] would commit, tag $tag and push to $REMOTE"
  exit 0
fi

# ── bump versions ───────────────────────────────────────────────────────────
# pyproject.toml: first `version = "..."` line only
perl -0pi -e 'BEGIN{$c=0} s/^version *= *"[^"]+"/version = "'"$version"'"/m && $c++ unless $c' "$PYPROJECT"
# tauri.conf.json: top-level "version": "..."
perl -0pi -e 's/("version"\s*:\s*)"[^"]+"/${1}"'"$version"'"/' "$TAURI_CONF"

# verify
grep -q "\"version\": \"$version\"" "$TAURI_CONF" || die "failed to update $TAURI_CONF"
grep -q "^version = \"$version\"" "$PYPROJECT"     || die "failed to update $PYPROJECT"

echo "==> Bumped $PYPROJECT and $TAURI_CONF to $version"

# ── commit, tag, push ───────────────────────────────────────────────────────
git add "$PYPROJECT" "$TAURI_CONF"
git commit -m "release: $version"
git tag -a "$tag" -m "Release $version"

echo "==> Pushing commit and tag to $REMOTE"
# Push branch and tag together (atomic) so we never end up with the commit on
# the remote but no tag, or vice versa.
git push --atomic "$REMOTE" "$branch" "$tag"

echo ""
echo "=========================================================="
echo "Release $tag pushed. CI is now building the macOS DMG."
echo "Watch:    https://github.com/roger8b/llm-wiki-cli/actions"
echo "Release:  https://github.com/roger8b/llm-wiki-cli/releases/tag/$tag"
echo "=========================================================="
