#!/usr/bin/env bash
# sidecar plugin: scripts/stop.sh <service|--all> [--force]
# Also used as the Claude Code Stop hook: stop.sh --all
set -euo pipefail

TARGET="${1:-}"
FORCE=false
[[ "${2:-}" == "--force" ]] && FORCE=true

PROJECT_HASH=$(printf '%s' "${CLAUDE_PROJECT_DIR:-$PWD}" | md5sum | cut -c1-6)

stop_one() {
  local name="$1"
  docker stop "$name" &>/dev/null && docker rm "$name" &>/dev/null \
    && echo "[sidecar] Stopped: $name" \
    || echo "[sidecar] $name not found"
}

if [[ "$TARGET" == "--all" ]]; then
  STOPPED=(); KEPT=()

  # Stop containers with keep=false (use --filter instead of template index,
  # which broke in Docker 28 where Labels is no longer indexable by string)
  while read -r name; do
    docker stop "$name" &>/dev/null && docker rm "$name" &>/dev/null
    STOPPED+=("$name")
  done < <(docker ps \
    --filter "label=sidecar.project=${PROJECT_HASH}" \
    --filter "label=sidecar.keep=false" \
    --format '{{.Names}}' 2>/dev/null)

  if [[ "$FORCE" == "true" ]]; then
    while read -r name; do
      docker stop "$name" &>/dev/null && docker rm "$name" &>/dev/null
      STOPPED+=("$name")
    done < <(docker ps \
      --filter "label=sidecar.project=${PROJECT_HASH}" \
      --filter "label=sidecar.keep=true" \
      --format '{{.Names}}' 2>/dev/null)
  else
    while read -r name; do
      KEPT+=("$name")
    done < <(docker ps \
      --filter "label=sidecar.project=${PROJECT_HASH}" \
      --filter "label=sidecar.keep=true" \
      --format '{{.Names}}' 2>/dev/null)
  fi

  [[ ${#STOPPED[@]} -gt 0 ]] && echo "[sidecar] Stopped: ${STOPPED[*]}" || true
  [[ ${#KEPT[@]} -gt 0 ]]    && echo "[sidecar] Kept running: ${KEPT[*]}" || true

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
