#!/usr/bin/env bash
# Semi-automatic production release (run from the maintainer machine).
#
# Releases whatever is checked out at HEAD (must be clean) to the ECS, then
# restarts the affected systemd service and smoke-checks it. The authoritative
# git source of truth is the `platform` remote (main); this script is the
# delivery mechanism (rsync, not server-side git).
#
# Usage:
#   ./scripts/deploy/release.sh                 # release platform + agent + frontend
#   ./scripts/deploy/release.sh --scope=platform
#   ./scripts/deploy/release.sh --scope=agent
#   ./scripts/deploy/release.sh --skip-checks   # don't run pytest / npm build
#   ./scripts/deploy/release.sh --tag=prod-20260909   # also tag+push this release
#
# Rollback: re-run with the previous tag/commit checked out (git stash/checkout
# the old ref, then `release.sh`). var/ and .env on the server are never
# touched by the rsync path list below, so state is preserved across releases.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

HOST="${HOST:-waterexpert@47.84.185.231}"
APP_REMOTE="${APP_REMOTE:-/srv/waterexpert/app}"
SCOPE="${SCOPE:-all}"          # overridden by --scope=
TAG=""
RUN_CHECKS=1

for arg in "$@"; do
  case "$arg" in
    --scope=platform|--scope=agent|--scope=all) SCOPE="${arg#--scope=}" ;;
    --scope) echo "use --scope=platform|agent|all"; exit 2 ;;
    --skip-checks) RUN_CHECKS=0 ;;
    --tag=*) TAG="${arg#--tag=}" ;;
    *) echo "unknown arg: $arg"; exit 2 ;;
  esac
done

echo ">> Release scope=$SCOPE host=$HOST"

# ---- preflight -------------------------------------------------------------
if [ -n "$(git status --porcelain)" ]; then
  echo "!! Working tree is dirty — commit or stash before releasing."; exit 1
fi
HEAD_SHA="$(git rev-parse HEAD)"
echo ">> Releasing HEAD $HEAD_SHA ($(git rev-parse --abbrev-ref HEAD))"

# ---- local checks ----------------------------------------------------------
if [ "$RUN_CHECKS" = 1 ]; then
  echo ">> Running backend tests..."
  (cd "$REPO_ROOT" && .ai4s/bin/python -m pytest -q) || { echo "!! tests failed"; exit 1; }
  echo ">> Building frontend..."
  (cd "$REPO_ROOT/frontend" && npm run build) || { echo "!! frontend build failed"; exit 1; }
else
  echo ">> --skip-checks: skipping pytest / npm build"
fi

# ---- platform files ---------------------------------------------------------
if [ "$SCOPE" = platform ] || [ "$SCOPE" = all ]; then
  echo ">> rsync platform code -> $HOST:$APP_REMOTE"
  rsync -az --delete -e ssh \
    backend configs scripts src data outputs docs \
    requirements.txt README.md .env.example \
    "$HOST:$APP_REMOTE/"
  echo ">> rsync frontend/out -> $HOST:$APP_REMOTE/frontend/out"
  rsync -az --delete -e ssh frontend/out "$HOST:$APP_REMOTE/frontend/"
  echo ">> restart waterexpert-platform"
  ssh -o BatchMode=yes "$HOST" 'sudo systemctl restart waterexpert-platform'
fi

# ---- agent files -----------------------------------------------------------
if [ "$SCOPE" = agent ] || [ "$SCOPE" = all ]; then
  "$REPO_ROOT/scripts/deploy/deploy_agent.sh"
fi

# ---- smoke -----------------------------------------------------------------
sleep 2
echo ">> Smoke checks"
ssh -o BatchMode=yes "$HOST" 'echo -n "platform healthz: "; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/healthz; echo -n "platform readyz:  "; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/readyz'
if [ "$SCOPE" = agent ] || [ "$SCOPE" = all ]; then
  ssh -o BatchMode=yes "$HOST" 'echo -n "agent health: "; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8001/api/health || true'
fi

# ---- tag & push provenance -------------------------------------------------
if [ -n "$TAG" ]; then
  echo ">> Tagging $TAG and pushing to platform remote"
  git tag -a "$TAG" -m "Production release $TAG ($HEAD_SHA)" && git push platform "$TAG"
fi

echo ">> Release done: $HEAD_SHA"
