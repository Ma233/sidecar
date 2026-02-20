I want to create a Claude Code plugin called "sidecar".

**What it does:**
Manages on-demand Docker containers for local development infrastructure
(postgres, redis, mongo, kafka, rabbitmq). Each service is started
individually as needed during a conversation. Once a container is running,
Claude knows its connection strings and injects them into any command that
needs them — migrations, codegen, tests, ad-hoc queries, or anything else.

**Key behaviors:**

1. `/sidecar start <service> [--keep]` — runs `docker run -p 0:<port>` (random
   host port), waits for healthcheck, prints connection info for Claude to
   internalize. `--keep` must be decided at start time and cannot be changed.
2. `/sidecar status` — re-detects running containers, re-resolves ports,
   prints fresh connection info
3. `/sidecar stop <service|--all> [--force]` — stops and removes containers;
   respects `sidecar.keep` label unless `--force`
4. On session start: auto-run detect to find kept containers from previous
   sessions, reconnect silently if found, offer to restart stopped ones

**Port collision design:**
All services use `-p 0:<container_port>` so the OS assigns a random host port.
URIs are constructed from (service, actual port) — no hardcoded defaults anywhere.

**State design (labels only, no files):**
State lives entirely in 4 Docker container labels:

- `sidecar.project=<cwd-md5-6chars>`
- `sidecar.service=<name>`
- `sidecar.keep=<true|false>` — set at creation, immutable, single source of truth
- `sidecar.meta=<base64-json>` — service-specific extras (e.g. rabbitmq mgmt port)

Nothing is written to the project directory.

**Plugin structure:**
This is a Claude Code plugin. The Stop hook is declared in `hooks/hooks.json`
and registered automatically on plugin install — no manual setup needed.

```
sidecar/
├── .claude-plugin/
│   └── plugin.json          # declares skills + Stop hook
├── skills/
│   └── sidecar/
│       └── SKILL.md
├── hooks/
│   └── hooks.json           # Stop → stop.sh --all
└── scripts/
    ├── start.sh
    ├── stop.sh              # also used directly as the exit hook
    ├── detect.sh
    └── state.py
```

**Scripts:**

- `start.sh` — per-service `docker run` with 4 labels; calls `state.py connections` after start
- `detect.sh` — finds containers by label, delegates to `state.py connections`
- `state.py` — reads labels + resolves ports via `docker port`; commands: `connections`, `env`
- `stop.sh` — reads `sidecar.keep` label; respects it unless `--force`; also the exit hook

**I already have a working implementation.** Please use it as the starting
point, write eval test cases, then iterate to improve the skill description
(frontmatter) and instruction clarity.
