#!/usr/bin/env bash
# sidecar plugin: scripts/stop.sh <service|--all> [--force]
# Also used as the Claude Code Stop hook: stop.sh --all
set -euo pipefail

TARGET="${1:-}"
FORCE=false
[[ "${2:-}" == "--force" ]] && FORCE=true

PROJECT_HASH=$(echo "$PWD" | md5sum | cut -c1-6)

stop_one() {
  local name="$1"
  docker stop "$name" &>/dev/null && docker rm "$name" &>/dev/null \
    && echo "[sidecar] Stopped: $name" \
    || echo "[sidecar] $name not found"
}

if [[ "$TARGET" == "--all" ]]; then
  STOPPED=(); KEPT=()
  while IFS=$'\t' read -r name keep; do
    if [[ "$FORCE" == "true" || "$keep" != "true" ]]; then
      docker stop "$name" &>/dev/null && docker rm "$name" &>/dev/null
      STOPPED+=("$name")
    else
      KEPT+=("$name")
    fi
  done < <(docker ps \
    --filter "label=sidecar.project=${PROJECT_HASH}" \
    --format '{{.Names}}\t{{index .Labels "sidecar.keep"}}' 2>/dev/null)

  [[ ${#STOPPED[@]} -gt 0 ]] && echo "[sidecar] Stopped: ${STOPPED[*]}"
  [[ ${#KEPT[@]} -gt 0 ]]    && echo "[sidecar] Kept running: ${KEPT[*]}"

elif [[ -n "$TARGET" ]]; then
  case "$TARGET" in
    pg|postgres|postgresql) TARGET="postgres" ;;
    redis)   TARGET="redis"    ;;
    mongo*)  TARGET="mongo"    ;;
    kafka)   TARGET="kafka"    ;;
    rabbit*) TARGET="rabbitmq" ;;
  esac
  stop_one "sidecar-${TARGET}-${PROJECT_HASH}"

else
  echo "Usage: stop.sh <service|--all> [--force]"
  exit 1
fi
