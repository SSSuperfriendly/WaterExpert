#!/usr/bin/env bash
# Sync the assembled Water AI agent tree (Mac -> ECS) and restart the agent.
#
# The agent deployment is NOT a git checkout on the server: the authoritative
# tree is the local assembled copy (collaborator source + data/outputs + our
# model-core swap), which rsyncs here with dev/binary junk excluded. The Linux
# venv (server-only; local dev uses .venv) and .env are created once by
# bootstrap_server.sh and MUST be excluded below — a `--delete` rsync without
# 'venv/' excluded wiped /srv/waterexpert-agent/venv on 2026-09-09 (agent down
# until rebuilt). Rollback = re-run with the previous tree checked out, then
# restart.
set -euo pipefail

HOST="${HOST:-waterexpert@47.84.185.231}"
# Agent tree now lives inside the platform repo as agent/ (single project path);
# --env AGENT_LOCAL=... still overrides when deploying from another checkout.
AGENT_LOCAL="${AGENT_LOCAL:-$(cd "$(dirname "$0")/../.." && pwd)/agent}"
AGENT_REMOTE="${AGENT_REMOTE:-/srv/waterexpert-agent}"

echo ">> Agent: rsync $AGENT_LOCAL -> $HOST:$AGENT_REMOTE"
rsync -az --delete \
  --exclude '.venv/' \
  --exclude 'venv/' \
  --exclude '.git/' \
  --exclude '__pycache__/' \
  --exclude '.env' \
  --exclude 'outputs/api_jobs/' \
  -e ssh "$AGENT_LOCAL/" "$HOST:$AGENT_REMOTE/"

echo ">> Agent: restart waterexpert-agent (if unit exists)"
ssh -o BatchMode=yes "$HOST" 'sudo systemctl restart waterexpert-agent 2>/dev/null || echo "(unit not present yet)"'

echo ">> Agent: smoke health (poll up to 60s for boot + model load)"
ssh -o BatchMode=yes "$HOST" 'for i in $(seq 1 30); do h=$(curl -s --max-time 3 http://127.0.0.1:8001/api/health 2>/dev/null); echo "$h" | grep -q "\"healthy\"" && break; sleep 2; done; echo "$h" | head -c 400; echo'
echo ">> Agent deploy done."
