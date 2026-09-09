#!/usr/bin/env bash
# One-shot production health/status check (run from the maintainer machine).
# Reports systemd units, both services' health endpoints (local + public), and
# disk/memory/swap headroom.
set -uo pipefail

HOST="${HOST:-waterexpert@47.84.185.231}"
PUBLIC_IP="${PUBLIC_IP:-47.84.185.231}"

echo "== systemd units =="
ssh -o BatchMode=yes "$HOST" 'systemctl is-active waterexpert-platform waterexpert-agent 2>&1 || true; echo; systemctl --failed --no-legend | head -5 || true'

echo "== platform health (server-local) =="
ssh -o BatchMode=yes "$HOST" 'echo -n "healthz: "; curl -s --max-time 8 -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/healthz; echo -n "readyz: "; curl -s --max-time 8 -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/readyz'

echo "== agent health (server-local) =="
ssh -o BatchMode=yes "$HOST" 'curl -s --max-time 10 http://127.0.0.1:8001/api/health | head -c 300; echo'

echo "== public entrypoint =="
echo -n "public /healthz: "
curl -s --max-time 8 -o /dev/null -w "%{http_code}\n" "http://$PUBLIC_IP/healthz" || echo "UNREACHABLE (security group?)"

echo "== resources =="
ssh -o BatchMode=yes "$HOST" 'free -m | sed -n 1,2p; echo; df -h / | tail -1; echo; swapon --show || echo "(no swap)"'
echo "== status done =="
