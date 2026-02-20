# Sidecar Skill — Eval Test Cases

Each case specifies: context, input, required Claude behavior, and forbidden behavior.
All cases assume `${CLAUDE_PLUGIN_ROOT}` is the sidecar plugin root directory.

---

## E-01: Session start — no containers

**Context**: Fresh project, no sidecar containers exist, Docker is running.

**Trigger**: Anything that first invokes the sidecar skill in this session.

**Required**:

- Runs `detect.sh` before any other sidecar operation
- Output says "No sidecar containers found"
- Does NOT start any service unprompted
- Waits for user to request a service

**Forbidden**:

- Running `start.sh` without explicit user request
- Offering to start a specific service unprompted

---

## E-02: Session start — running containers found

**Context**: `detect.sh` prints postgres running at host-port 54123 with:

```
DATABASE_URL=postgresql://sidecar:sidecar@localhost:54123/sidecar
```

**Required**:

- Internalizes all URIs **silently** (no announcement to user like "I found postgres running")
- Stores port 54123 (not 5432) for all subsequent postgres interactions

**Forbidden**:

- Announcing internalized connection info unprompted
- Storing default port 5432 instead of the actual resolved port

---

## E-03: Session start — stopped kept containers found

**Context**: `detect.sh` shows `sidecar-postgres-abc123` is stopped (exited, keep=true from previous session).

**Required**:

- Offers to restart, e.g.: "I found a stopped postgres from a previous session. Restart it?"
- Waits for user confirmation before running `start.sh`

**Forbidden**:

- Auto-restarting without asking
- Silently ignoring the stopped container

---

## E-04: Session start — Docker not running

**Context**: `detect.sh` outputs "[sidecar/detect] Docker is not running."

**Required**:

- Reports to user that Docker is not available
- Suggests starting Docker Desktop / Docker daemon
- Does NOT attempt to call `start.sh`

**Forbidden**:

- Silently swallowing the error
- Running start.sh when Docker is unavailable

---

## E-05: Explicit start — new service

**Input**: "Start postgres"

**Context**: First invocation in session, no containers running.

**Required**:

1. Runs `detect.sh` (session reconnect check, first invocation only)
2. Runs `start.sh postgres`
3. Reads and internalizes all printed connection info
4. Reports to user: which service, host-port assigned, key env vars (e.g., `DATABASE_URL`)

**Forbidden**:

- Skipping the detect.sh step on first invocation
- Reporting a hardcoded port like 5432
- Not reporting connection info to user

---

## E-06: Start with --keep

**Input**: "Start redis and keep it running between sessions"

**Required**:

- Runs `start.sh redis --keep`
- Tells user the container will survive session exit and be reconnected next session
- Notes that the keep policy cannot be changed after creation

**Forbidden**:

- Starting without `--keep` and later trying to add it
- Not informing the user of the persistence behavior

---

## E-07: Start — service already running (same session)

**Context**: Claude already started postgres this session and has the URI internalized.

**Input**: "Start postgres again" or "I need postgres"

**Required**:

- Either: tells user postgres is already running (using internalized state)
- Or: runs `start.sh postgres` (script detects it's running and returns existing info)

**Forbidden**:

- Creating a duplicate container
- Losing track of the existing connection info

---

## E-08: Start — unknown service name

**Input**: "/sidecar start mysql"

**Required**:

- Runs `start.sh mysql` (script will return an error)
- Reports the error clearly to the user
- Lists supported services (postgres, redis, mongo, kafka, rabbitmq)

**Forbidden**:

- Silently failing without reporting the error
- Substituting a different service without asking

---

## E-09: Implicit start — migration request

**Input**: "Run the database migrations"

**Context**: No postgres running, detect.sh shows nothing.

**Required**:

- Recognizes that migrations need a database
- Either asks user "Should I start postgres first?" or starts it proactively with explanation
- Once postgres is running, runs the migration command with `DATABASE_URL` injected automatically

**Forbidden**:

- Running migrations without a database
- Using a hardcoded `DATABASE_URL=postgresql://localhost:5432/...`
- Asking the user "what is your DATABASE_URL?"

---

## E-10: Connection injection — integration tests

**Context**: Postgres is running at host-port 54123. Claude has internalized:

```
DATABASE_URL=postgresql://sidecar:sidecar@localhost:54123/sidecar
```

**Input**: "Run the integration tests"

**Required**:

- Runs tests with DATABASE_URL injected, e.g.:
  `DATABASE_URL=postgresql://sidecar:sidecar@localhost:54123/sidecar cargo test`
- Does NOT ask the user for a connection string

**Forbidden**:

- Using `localhost:5432` (hardcoded default port)
- Asking "what DATABASE_URL should I use?"

---

## E-11: Multiple services — correct URI routing

**Context**: Both running:

- postgres at host-port 54321 → `DATABASE_URL=postgresql://sidecar:sidecar@localhost:54321/sidecar`
- redis at host-port 63791 → `REDIS_URL=redis://localhost:63791`

**Input**: "Run the cache warmup script, then run the full test suite"

**Required**:

- Cache warmup: injects `REDIS_URL=redis://localhost:63791`
- Test suite: injects both `DATABASE_URL` and `REDIS_URL` with correct ports for each

**Forbidden**:

- Using default ports (5432, 6379)
- Mixing up which URI belongs to which service

---

## E-12: Status refresh

**Input**: "/sidecar status"

**Required**:

- Runs `detect.sh`
- Updates internalized URIs with fresh info from output
- Reports current running containers and their connection info to user

---

## E-13: Answer from memory — connection string query

**Context**: Claude internalized postgres connection info earlier in the session.

**Input**: "What's the connection string for postgres?"

**Required**:

- Answers immediately from memory without running any script
- Provides complete URI with the correct (random) host port

**Forbidden**:

- Running a script unnecessarily when info is already known
- Providing a connection string with the default port 5432

---

## E-14: Stop specific service

**Input**: "/sidecar stop postgres"

**Required**:

- Runs `stop.sh postgres`
- Confirms to user that postgres was stopped
- Clears internalized postgres URIs (they are now invalid)

**Forbidden**:

- Keeping stale postgres URIs after the container is stopped
- Running stop with `--force` when not requested

---

## E-15: Stop all — respects keep label

**Input**: "/sidecar stop --all"

**Context**: Postgres running (keep=false), Redis running (keep=true).

**Required**:

- Runs `stop.sh --all`
- Reports: postgres was stopped, redis was kept running
- Clears internalized postgres URIs; retains redis URIs (still valid)

**Forbidden**:

- Stopping redis (a kept container) without `--force`
- Clearing redis URIs when it's still running

---

## E-16: Stop all --force — confirm first

**Input**: "/sidecar stop --all --force"

**Context**: Redis is running with keep=true.

**Required**:

- Confirms with user before running (destroying a kept container is irreversible)
- After confirmation: runs `stop.sh --all --force`
- All containers stopped; clears all internalized URIs

**Forbidden**:

- Running `--force` without user confirmation
- Silently proceeding without warning about the kept container

---

## E-17: RabbitMQ — management UI

**Context**: RabbitMQ running. `detect.sh` output includes:

```
AMQP_URL=amqp://sidecar:sidecar@localhost:56789
RABBITMQ_MGMT_URL=http://localhost:15673
```

**Required**:

- Internalizes both `AMQP_URL` and `RABBITMQ_MGMT_URL`
- If user asks how to access the management UI, provides: `http://localhost:15673` (credentials: sidecar/sidecar)

**Forbidden**:

- Assuming management UI is at port 15672 (hardcoded default)

---

## E-18: Skill not triggered for unrelated tasks

**Input**: "Can you refactor this function to use iterators?"

**Required**:

- Does NOT invoke sidecar skill
- Focuses on the code refactoring task

---

## E-19: Proactive infrastructure offer

**Input**: "I want to run `sqlx migrate run` but I don't have a database set up"

**Required**:

- Offers to start postgres
- Once started, runs: `DATABASE_URL=<resolved-uri> sqlx migrate run`

**Forbidden**:

- Running the migration command without a database
- Asking the user to provide the DATABASE_URL

---

## E-20: Keep policy immutability

**Context**: Postgres was started without `--keep`.

**Input**: "Actually, I want to keep postgres running after we're done"

**Required**:

- Explains that keep policy is set at creation time and cannot be changed
- Offers alternatives: stop and restart with `--keep`, or leave it as-is

**Forbidden**:

- Running any command that claims to change `sidecar.keep` on the existing container
- Silently ignoring the request

---

## E-21: Port collisions — awareness

**Context**: User is working on two projects simultaneously, each has a postgres sidecar.

**Required**:

- Understands that each project's containers have a different 6-char hash in their name
- Does not assume containers from one project conflict with another
- `detect.sh` output shows "Other sidecar containers on this machine (different projects)" — Claude notes these are non-conflicting

---

## E-22: No .env file creation

**Context**: Postgres is running. Claude is about to run a command that needs DATABASE_URL.

**Input**: "Set up the environment for running tests"

**Required**:

- Injects env vars inline in commands (e.g., `DATABASE_URL=... cargo test`)
- Does NOT write connection strings to `.env`, `.envrc`, or any config file

**Forbidden**:

- Writing `DATABASE_URL=...` to a `.env` file or similar
- Persisting connection strings to disk (containers' ports change across restarts)
