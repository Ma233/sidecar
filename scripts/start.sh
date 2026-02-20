#!/usr/bin/env bash
# sidecar plugin: scripts/start.sh <service> [--keep]
set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SERVICE="${1:-}"
KEEP=false
[[ "${2:-}" == "--keep" ]] && KEEP=true

if [[ -z "$SERVICE" ]]; then
  echo "Usage: start.sh <service> [--keep]"
  echo "Services: postgres/pg  redis  mongo  kafka  rabbitmq"
  exit 1
fi

PROJECT_HASH=$(echo "$PWD" | md5sum | cut -c1-6)

case "$SERVICE" in
  pg|postgres|postgresql) SERVICE="postgres" ;;
  redis)          SERVICE="redis" ;;
  mongo|mongodb)  SERVICE="mongo" ;;
  kafka)          SERVICE="kafka" ;;
  rabbit|rabbitmq) SERVICE="rabbitmq" ;;
  *)
    echo "[sidecar] Unknown service: $SERVICE"
    echo "Supported: postgres/pg, redis, mongo, kafka, rabbitmq"
    exit 1 ;;
esac

CONTAINER_NAME="sidecar-${SERVICE}-${PROJECT_HASH}"

# Already running
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "[sidecar] ${SERVICE} already running as ${CONTAINER_NAME}"
  python3 "$PLUGIN_ROOT/scripts/state.py" connections
  exit 0
fi

# Stopped — restart
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "[sidecar] Restarting stopped container ${CONTAINER_NAME}..."
  docker start "$CONTAINER_NAME"
  python3 "$PLUGIN_ROOT/scripts/state.py" connections
  exit 0
fi

echo "[sidecar] Starting ${SERVICE}..."

META_JSON="{}"

pick_free_port() {
  python3 -c "import socket; s=socket.socket(); s.bind(('',0)); p=s.getsockname()[1]; s.close(); print(p)"
}

COMMON=(
  "--label" "sidecar.project=${PROJECT_HASH}"
  "--label" "sidecar.service=${SERVICE}"
  "--label" "sidecar.keep=${KEEP}"
)

case "$SERVICE" in
  postgres)
    docker run -d --name "$CONTAINER_NAME" "${COMMON[@]}" \
      --label "sidecar.meta=$(echo "${META_JSON}" | base64 -w0)" \
      -e POSTGRES_USER=sidecar -e POSTGRES_PASSWORD=sidecar -e POSTGRES_DB=sidecar \
      -p 0:5432 \
      --health-cmd "pg_isready -U sidecar -d sidecar" \
      --health-interval 2s --health-retries 15 \
      postgres:16-alpine
    ;;

  redis)
    docker run -d --name "$CONTAINER_NAME" "${COMMON[@]}" \
      --label "sidecar.meta=$(echo "${META_JSON}" | base64 -w0)" \
      -p 0:6379 \
      --health-cmd "redis-cli ping" \
      --health-interval 2s --health-retries 10 \
      redis:7-alpine redis-server --save "" --appendonly no
    ;;

  mongo)
    docker run -d --name "$CONTAINER_NAME" "${COMMON[@]}" \
      --label "sidecar.meta=$(echo "${META_JSON}" | base64 -w0)" \
      -e MONGO_INITDB_ROOT_USERNAME=sidecar -e MONGO_INITDB_ROOT_PASSWORD=sidecar \
      -p 0:27017 \
      --health-cmd "mongosh --eval 'db.adminCommand(\"ping\")' --quiet" \
      --health-interval 3s --health-retries 15 \
      mongo:7
    ;;

  kafka)
    CLUSTER_ID=$(docker run --rm confluentinc/cp-kafka:7.6.0 \
      kafka-storage random-uuid 2>/dev/null || echo "sidecar-kafka-$(date +%s)")
    KAFKA_HOST_PORT=$(pick_free_port)
    CTRL_HOST_PORT=$(pick_free_port)
    META_JSON="{\"ctrl_port\":${CTRL_HOST_PORT}}"
    docker run -d --name "$CONTAINER_NAME" "${COMMON[@]}" \
      --label "sidecar.meta=$(echo "${META_JSON}" | base64 -w0)" \
      -e KAFKA_NODE_ID=1 -e KAFKA_PROCESS_ROLES=broker,controller \
      -e KAFKA_LISTENERS="PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093" \
      -e KAFKA_ADVERTISED_LISTENERS="PLAINTEXT://localhost:${KAFKA_HOST_PORT}" \
      -e KAFKA_CONTROLLER_QUORUM_VOTERS="1@localhost:9093" \
      -e KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER \
      -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 \
      -e KAFKA_LOG_DIRS=/tmp/kraft-combined-logs \
      -e CLUSTER_ID="$CLUSTER_ID" \
      -p "${KAFKA_HOST_PORT}:9092" -p "${CTRL_HOST_PORT}:9093" \
      confluentinc/cp-kafka:7.6.0
    ;;

  rabbitmq)
    docker run -d --name "$CONTAINER_NAME" "${COMMON[@]}" \
      -e RABBITMQ_DEFAULT_USER=sidecar -e RABBITMQ_DEFAULT_PASS=sidecar \
      -p 0:5672 -p 0:15672 \
      --health-cmd "rabbitmq-diagnostics -q ping" \
      --health-interval 5s --health-retries 10 \
      rabbitmq:3-management-alpine
    # mgmt_port resolved after container is up; store via meta override file
    ;;
esac

# Wait for healthy
echo -n "[sidecar] Waiting for ${SERVICE} to be ready"
MAX=40; COUNT=0
while :; do
  HEALTH=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "none")
  [[ "$HEALTH" == "healthy" ]] && break
  if [[ "$HEALTH" == "none" ]]; then
    RUNNING=$(docker inspect --format='{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null || echo "false")
    if [[ "$RUNNING" == "true" ]]; then
      [[ "$SERVICE" == "kafka" ]] && sleep 8
      break
    fi
  fi
  COUNT=$((COUNT+1))
  if [[ $COUNT -ge $MAX ]]; then
    echo ""; echo "[sidecar] ERROR: ${SERVICE} did not become healthy in ${MAX}s"
    docker logs "$CONTAINER_NAME" --tail 20; exit 1
  fi
  echo -n "."; sleep 1
done
echo " ready."

# Store rabbitmq mgmt_port in meta override file (label is immutable post-creation)
if [[ "$SERVICE" == "rabbitmq" ]]; then
  MGMT_PORT=$(docker port "$CONTAINER_NAME" 15672 2>/dev/null | head -1 | cut -d: -f2 || true)
  echo "{\"mgmt_port\":${MGMT_PORT:-0}}" > "/tmp/sidecar-meta-${PROJECT_HASH}-rabbitmq.json"
fi

python3 "$PLUGIN_ROOT/scripts/state.py" connections
