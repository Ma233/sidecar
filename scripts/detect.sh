#!/usr/bin/env bash
# sidecar plugin: scripts/detect.sh
set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PROJECT_HASH=$(printf '%s' "${CLAUDE_PROJECT_DIR:-$PWD}" | md5sum | cut -c1-6)

echo "[sidecar/detect] Project: $(basename "$PWD") (hash: $PROJECT_HASH)"
echo ""

if ! docker info &>/dev/null; then
  echo "[sidecar/detect] Docker is not running."
  exit 1
fi

RUNNING=$(docker ps \
  --filter "label=sidecar.project=${PROJECT_HASH}" \
  --format '{{.Names}}' 2>/dev/null || true)

STOPPED=$(docker ps -a --filter "status=exited" \
  --filter "label=sidecar.project=${PROJECT_HASH}" \
  --format '{{.Names}}' 2>/dev/null || true)

if [[ -z "$RUNNING" && -z "$STOPPED" ]]; then
  echo "[sidecar/detect] No sidecar containers found for this project."
  echo "Run /sidecar start <service> to begin."
  exit 0
fi

if [[ -n "$RUNNING" ]]; then
  echo "[sidecar/detect] Running containers — connection info:"
  echo ""
  python3 "$PLUGIN_ROOT/scripts/state.py" connections
fi

if [[ -n "$STOPPED" ]]; then
  echo ""
  echo "[sidecar/detect] Stopped containers (keep=true, from a previous session):"
  echo "$STOPPED" | sed 's/^/  /'
  echo "  To restart: /sidecar start <service>"
  echo "  To remove:  /sidecar stop <service>"
fi

OTHER=$(docker ps \
  --filter "label=sidecar.project" \
  --format '{{.Names}}' 2>/dev/null \
  | grep -v "\-${PROJECT_HASH}$" || true)

if [[ -n "$OTHER" ]]; then
  echo ""
  echo "[sidecar/detect] Other sidecar containers on this machine (different projects):"
  echo "$OTHER" | sed 's/^/  /'
  echo "  (Using different random ports — no conflict.)"
fi
