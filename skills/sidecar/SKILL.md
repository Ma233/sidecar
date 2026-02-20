---
name: sidecar
description: >
  Manages on-demand Docker containers for local development infrastructure
  (postgres, redis, mongo, kafka, rabbitmq). Each service is started
  individually as needed. Once a container is running, Claude internalizes
  its connection strings and injects them into any command that needs them
  — without being asked.
  Invoke when: user requests a service by name ("start postgres", "spin up
  redis", "bring up kafka", "I need a database", "I need a cache"), needs
  infrastructure for a task ("run migrations", "run integration tests",
  "seed the database", "run sqlx migrate", "run codegen", "run entity
  generation"), asks for connection info ("what's my DATABASE_URL", "what
  port is redis on", "connection string for mongo", "how do I connect to
  postgres"), checks status ("is postgres running?", "sidecar status",
  "what's running"), or at first skill invocation in a session to detect
  kept containers from a previous session.
---

# Sidecar — On-Demand Infrastructure Containers

Sidecar starts Docker containers on demand for local development. State lives
entirely in Docker container labels — no config files, no project-directory
pollution. Ports are randomly assigned by the OS to avoid conflicts.

---

## First Invocation (Session Reconnect Check)

**The very first time this skill is invoked in a session**, run:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/detect.sh
```

Interpret the output and act accordingly:

| detect.sh output              | Action                                                                                      |
| ----------------------------- | ------------------------------------------------------------------------------------------- |
| "No sidecar containers found" | Proceed normally; wait for user to request a service                                        |
| Running containers listed     | **Silently** internalize all connection URIs — no announcement                              |
| Stopped containers listed     | Offer to restart each: "I found a stopped \<service\> from a previous session. Restart it?" |
| "Docker is not running"       | Warn the user; do not attempt to start anything                                             |

After this initial detect, proceed to handle whatever the user requested.

---

## Commands

### `/sidecar start <service> [--keep]`

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/start.sh <service> [--keep]
```

- **Without `--keep`**: container is stopped automatically when the session ends
- **With `--keep`**: container survives session exit; detect.sh will reconnect next session
- `--keep` is **decided at start time** — it cannot be changed after creation

Services and accepted names:

| Canonical name | Aliases            |
| -------------- | ------------------ |
| `postgres`     | `pg`, `postgresql` |
| `redis`        | —                  |
| `mongo`        | `mongodb`          |
| `kafka`        | —                  |
| `rabbitmq`     | `rabbit`           |

**After running start.sh**: read all printed connection info and internalize
every URI and env var. Report to the user: which service started, the
host-port assigned, and the key env var(s).

### `/sidecar status`

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/detect.sh
```

Re-detects running containers, resolves current ports, prints fresh connection
info. **Update all internalized URIs** from this output — ports may have
changed if a container was restarted.

### `/sidecar stop <service|--all> [--force]`

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/stop.sh <service|--all> [--force]
```

- `stop.sh postgres` — stops and removes the postgres container
- `stop.sh --all` — stops containers where `sidecar.keep=false`; kept containers remain running
- `stop.sh --all --force` — stops everything including kept containers

**Before running `--force`**: confirm with the user, since kept containers are
intentionally persistent and this is irreversible.

**After stopping**: clear internalized URIs for the stopped service(s). They
are no longer valid.

---

## How to Use Connection Info

**Core rules:**

1. **Internalize immediately**: after any `start.sh` or `detect.sh`, store all connection URIs in memory
2. **Never hardcode ports**: ports are OS-assigned at random — the default ports (5432, 6379, 27017, 9092, 5672) will be wrong
3. **Inject proactively**: add connection env vars to commands automatically, without being asked
4. **Answer from memory**: if the user asks for a connection string you already have, answer immediately — no script needed
5. **Refresh on status**: after running `detect.sh`, replace old URIs with new output

**Example injections:**

```bash
# Database migrations
DATABASE_URL=postgresql://sidecar:sidecar@localhost:<PORT>/sidecar sqlx migrate run

# Tests with multiple services
DATABASE_URL=... REDIS_URL=... cargo test

# Direct SQL query
psql postgresql://sidecar:sidecar@localhost:<PORT>/sidecar -c "SELECT count(*) FROM users"

# Redis CLI
redis-cli -p <PORT> ping
```

---

## Lifecycle

```
/sidecar start postgres         → auto-stopped on session exit (default)
/sidecar start postgres --keep  → survives exit, reconnectable next session

Session exit (Stop hook, registered automatically on plugin install):
  └─ stop.sh --all
       └─ stops containers where sidecar.keep=false
       └─ leaves containers where sidecar.keep=true

Next session:
  └─ detect.sh finds kept containers → Claude reconnects silently
```

---

## State Storage

All state lives in Docker container labels — nothing written to the project directory:

| Label             | Value              | Notes                             |
| ----------------- | ------------------ | --------------------------------- |
| `sidecar.project` | `<cwd-md5-6chars>` | Scopes containers to this project |
| `sidecar.service` | `postgres` / etc.  | Used to build URIs                |
| `sidecar.keep`    | `true` / `false`   | Set at creation, immutable        |
| `sidecar.meta`    | base64(JSON)       | Service-specific extras           |

---

## Service Catalog

| Service           | Image                          | Container Port | Primary Env Var           |
| ----------------- | ------------------------------ | -------------- | ------------------------- |
| `postgres` / `pg` | `postgres:18-alpine`           | 5432           | `DATABASE_URL`            |
| `redis`           | `redis:8-alpine`               | 6379           | `REDIS_URL`               |
| `mongo`           | `mongo:8`                      | 27017          | `MONGODB_URL`             |
| `kafka`           | `confluentinc/cp-kafka:7.9.5`  | 9092           | `KAFKA_BOOTSTRAP_SERVERS` |
| `rabbitmq`        | `rabbitmq:4-management-alpine` | 5672           | `AMQP_URL`                |

**RabbitMQ**: also exposes a management UI on a random host port; printed as
`RABBITMQ_MGMT_URL` (credentials: sidecar / sidecar).

**Postgres credentials**: user=`sidecar`, password=`sidecar`, db=`sidecar`

---

## Anti-Patterns

- **Never assume a default port.** Use the port printed in connection info output, always.
- **Never ask for a connection string** once a service is running. You have it.
- **Never start a service the user hasn't requested** — if a task implicitly needs one (e.g. migrations), offer first.
- **Never run `--force`** without explicit user instruction and confirmation.
- **Never write connection info to files.** Inject inline; ports change across restarts.
