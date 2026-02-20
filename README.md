# sidecar

A [Claude Code](https://github.com/anthropics/claude-code) plugin that manages on-demand Docker containers for local development infrastructure. Say "start postgres" and Claude starts it, learns the connection string, and injects it into every subsequent command that needs it — no config files, no hardcoded ports.

## What it does

- Starts Docker containers on demand: `postgres`, `redis`, `mongo`, `kafka`, `rabbitmq`
- Assigns random host ports (no collisions between projects or parallel sessions)
- Claude internalizes connection strings automatically and injects them into commands
- Cleans up containers when the session ends (unless `--keep` is set)
- Reconnects to kept containers on the next session

## Requirements

- [Claude Code](https://github.com/anthropics/claude-code) with plugin support
- Docker
- Python 3

## Installation

```bash
claude plugin install https://github.com/ma233/sidecar
```

Or install from a local clone:

```bash
claude plugin install /path/to/sidecar
```

The Stop hook is registered automatically on install — no manual setup needed.

## Usage

Just talk to Claude naturally:

```
"Start postgres"
"Spin up redis and keep it between sessions"
"Run the database migrations"
"Run integration tests"
"What's my DATABASE_URL?"
"Is postgres running?"
"/sidecar stop --all"
```

### Commands

| Command                             | Description                                 |
| ----------------------------------- | ------------------------------------------- |
| `/sidecar start <service> [--keep]` | Start a service container                   |
| `/sidecar status`                   | Show running containers and connection info |
| `/sidecar stop <service>`           | Stop and remove a specific container        |
| `/sidecar stop --all`               | Stop all non-kept containers                |
| `/sidecar stop --all --force`       | Stop everything including kept containers   |

### Services

| Service    | Aliases            | Primary env var           | Image                          |
| ---------- | ------------------ | ------------------------- | ------------------------------ |
| `postgres` | `pg`, `postgresql` | `DATABASE_URL`            | `postgres:18-alpine`           |
| `redis`    | —                  | `REDIS_URL`               | `redis:8-alpine`               |
| `mongo`    | `mongodb`          | `MONGODB_URL`             | `mongo:8`                      |
| `kafka`    | —                  | `KAFKA_BOOTSTRAP_SERVERS` | `confluentinc/cp-kafka:7.9.5`  |
| `rabbitmq` | `rabbit`           | `AMQP_URL`                | `rabbitmq:4-management-alpine` |

Default credentials for all services: user=`sidecar`, password=`sidecar`, db=`sidecar`.

RabbitMQ also exposes a management UI (`RABBITMQ_MGMT_URL`).

### The `--keep` flag

By default, containers are stopped when the Claude session ends. Pass `--keep` at start time to make a container persist across sessions:

```
"Start postgres --keep"
```

On the next session, Claude will detect the kept container and reconnect to it silently. The keep policy is set at creation and cannot be changed afterward.

## How it works

**State lives in Docker labels — nothing is written to disk.**

Each container gets four labels:

| Label             | Value                                           |
| ----------------- | ----------------------------------------------- |
| `sidecar.project` | 6-char MD5 of the project directory path        |
| `sidecar.service` | `postgres`, `redis`, etc.                       |
| `sidecar.keep`    | `true` or `false`                               |
| `sidecar.meta`    | base64-encoded JSON for service-specific extras |

**Ports are OS-assigned** (`-p 0:<container_port>`). Claude reads the actual assigned port from `docker port` output and never assumes defaults like 5432 or 6379.

**Connection injection** happens automatically. Once a service is running, Claude injects the correct env vars into any command that needs them:

```bash
DATABASE_URL=postgresql://sidecar:sidecar@localhost:54321/sidecar sqlx migrate run
DATABASE_URL=... REDIS_URL=redis://localhost:63791 cargo test
```

## Project structure

```
sidecar/
├── .claude-plugin/
│   └── plugin.json          # plugin manifest (skills + Stop hook)
├── skills/
│   └── sidecar/
│       └── SKILL.md         # Claude skill instructions
├── hooks/
│   └── hooks.json           # Stop → stop.sh --all
├── scripts/
│   ├── start.sh             # docker run per service, waits for healthy
│   ├── stop.sh              # stops containers; respects sidecar.keep
│   ├── detect.sh            # finds sidecar containers for this project
│   └── state.py             # reads labels, resolves ports, builds URIs
└── evals/
    └── cases.md             # behavioral eval test cases
```

## License

Apache-2.0
