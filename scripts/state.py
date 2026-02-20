#!/usr/bin/env python3
"""
sidecar/scripts/state.py

Reads sidecar state entirely from Docker container labels.
No files, no mutation — labels set at container creation are the source of truth.

Usage:
  state.py connections   # print active connection info (Claude reads this)
  state.py env           # print KEY=VALUE for shell sourcing / eval
"""

import sys, json, base64, subprocess, hashlib, os
from datetime import datetime, timezone

CONTAINER_PORTS = {
    "postgres": 5432, "redis": 6379,
    "mongo": 27017, "kafka": 9092, "rabbitmq": 5672,
}

def project_hash():
    d = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return hashlib.md5(d.encode()).hexdigest()[:6]

def resolve_port(name, cport):
    try:
        out = subprocess.check_output(
            ["docker", "port", name, str(cport)], stderr=subprocess.DEVNULL
        ).decode().strip()
        return int(out.split(":")[-1])
    except Exception:
        return None

def decode_meta(raw):
    try:
        return json.loads(base64.b64decode(raw).decode())
    except Exception:
        return {}

def load_meta_override(service, phash):
    """Read tmp file written by start.sh for service-specific extras set after container creation."""
    path = f"/tmp/sidecar-meta-{phash}-{service}.json"
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}

def list_containers(hash):
    try:
        out = subprocess.check_output(
            ["docker", "ps", "--filter", f"label=sidecar.project={hash}",
             "--format", "{{.Names}}\t{{.Labels}}"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return []
    results = []
    for line in (out.splitlines() if out else []):
        name, labels_str = line.split("\t", 1)
        labels = {}
        for part in labels_str.split(","):
            if "=" in part:
                k, _, v = part.partition("=")
                labels[k.strip()] = v.strip()
        service = labels.get("sidecar.service", "")
        meta = decode_meta(labels.get("sidecar.meta", "e30="))
        meta.update(load_meta_override(service, hash))
        results.append({
            "name":    name,
            "service": service,
            "keep":    labels.get("sidecar.keep", "false") == "true",
            "meta":    meta,
        })
    return results

def build_uri(service, port):
    return {
        "postgres": f"postgresql://sidecar:sidecar@localhost:{port}/sidecar",
        "redis":    f"redis://localhost:{port}",
        "mongo":    f"mongodb://sidecar:sidecar@localhost:{port}",
        "kafka":    f"localhost:{port}",
        "rabbitmq": f"amqp://sidecar:sidecar@localhost:{port}",
    }.get(service, f"localhost:{port}")

def build_env(service, port, meta):
    uri = build_uri(service, port)
    p = str(port)
    if service == "postgres":
        return {"DATABASE_URL": uri, "POSTGRES_HOST": "localhost", "POSTGRES_PORT": p,
                "POSTGRES_USER": "sidecar", "POSTGRES_PASSWORD": "sidecar", "POSTGRES_DB": "sidecar"}
    if service == "redis":
        return {"REDIS_URL": uri, "REDIS_HOST": "localhost", "REDIS_PORT": p}
    if service == "mongo":
        return {"MONGODB_URL": uri, "MONGODB_HOST": "localhost", "MONGODB_PORT": p}
    if service == "kafka":
        return {"KAFKA_BOOTSTRAP_SERVERS": uri}
    if service == "rabbitmq":
        ev = {"AMQP_URL": uri, "RABBITMQ_HOST": "localhost", "RABBITMQ_PORT": p}
        if meta.get("mgmt_port"):
            ev["RABBITMQ_MGMT_URL"] = f"http://localhost:{meta['mgmt_port']}"
        return ev
    return {"SERVICE_URI": uri}

def cmd_connections(_):
    hash = project_hash()
    containers = list_containers(hash)
    if not containers:
        print("[sidecar] No running containers found for this project.")
        print("Run: /sidecar start postgres  (or redis, mongo, kafka, rabbitmq)")
        return
    print("# Sidecar — Active Connections")
    print(f"# {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("# Claude: ports are randomly assigned — use values below, never assume defaults.")
    print()
    all_env = {}
    for c in containers:
        cport = CONTAINER_PORTS.get(c["service"])
        if not cport:
            continue
        port = resolve_port(c["name"], cport)
        if not port:
            print(f"# WARNING: could not resolve port for {c['name']}")
            continue
        env  = build_env(c["service"], port, c["meta"])
        flag = "kept" if c["keep"] else "cleanup-on-exit"
        print(f"## {c['service'].upper()}  host-port={port}  [{flag}]")
        for k, v in env.items():
            print(f"  {k}={v}")
        if c["service"] == "rabbitmq" and c["meta"].get("mgmt_port"):
            print(f"  MGMT_UI=http://localhost:{c['meta']['mgmt_port']}  (sidecar/sidecar)")
        print()
        all_env.update(env)
    print("# Shell export block:")
    for k, v in all_env.items():
        print(f"# export {k}={v}")

def cmd_env(_):
    for c in list_containers(project_hash()):
        cport = CONTAINER_PORTS.get(c["service"])
        if not cport:
            continue
        port = resolve_port(c["name"], cport)
        if not port:
            continue
        for k, v in build_env(c["service"], port, c["meta"]).items():
            print(f"{k}={v}")

CMDS = {"connections": cmd_connections, "env": cmd_env}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(f"Usage: state.py <{'|'.join(CMDS)}>")
        sys.exit(1)
    CMDS[sys.argv[1]](sys.argv[2:])
