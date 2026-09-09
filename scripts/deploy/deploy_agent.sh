#!/usr/bin/env bash
# Sync the assembled Water AI agent tree (Mac -> ECS) and restart the agent.
#
# The agent deployment is NOT a git checkout on the server: the authoritative
# tree is the local assembled copy (collaborator source + data/outputs + our
# model-core swap), which rsyncs here with dev/binary junk excluded. The Linux
# venv and .env are created once by bootstrap_server.sh and are preserved
# (excluded below). Rollback = re-run with the previous tree checked out, then
# restart.
set -euo pipefail

HOST="${HOST:-waterexpert@47.84.185.231}"
AGENT_LOCAL="${AGENT_LOCAL:-/Users/mac/Project/agent-water-expert}"
AGENT_REMOTE="${AGENT_REMOTE:-/srv/waterexpert-agent}"

echo ">> Agent: rsync $AGENT_LOCAL -> $HOST:$AGENT_REMOTE"
rsync -az --delete \
  --exclude '.venv/' \
  --exclude '.git/' \
  --exclude '__pycache__/' \
  --exclude '.env' \
  --exclude 'outputs/api_jobs/' \
  -e ssh "$AGENT_LOCAL/" "$HOST:$AGENT_REMOTE/"

echo ">> Agent: restart waterexpert-agent (if unit exists)"
ssh -o BatchMode=yes "$HOST" 'sudo systemctl restart waterexpert-agent 2>/dev/null || echo "(unit not present yet)"'

echo ">> Agent: smoke health"
ssh -o BatchMode=yes "$HOST" 'sleep 1; curl -sS --max-time 10 http://127.0.0.1:8001/api/health | head -c 400; echo'
echo ">> Agent deploy done."
