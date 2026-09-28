#!/usr/bin/env bash
# memory-index-check.sh — READ-ONLY report of memory-index identity drift.
# It never reindexes, never re-embeds, never writes to an agent DB. Repair is an
# operator decision: `openclaw memory index --agent <id> --force` re-embeds that
# agent through the paid embedding provider.
#
# WHY THIS EXISTS
# ---------------
# OpenClaw stamps each agent's memory index with a providerKey: a sha256 of the
# embedding provider's cacheKeyData ({provider, baseUrl, model,
# outputDimensionality, headers}; the API key is NOT part of it). An upgrade can
# change the SHAPE of that object — on 2026.7.1 outputDimensionality started
# resolving for gemini-embedding-2 — so the hash moves. Any index still stamped
# with the old key gets "Vector search: paused until memory is rebuilt" and
# silently degrades to keyword search, with no error anywhere. One box had 96 of
# 137 agents in that state for weeks. This check makes that state visible.
#
# The live key is the one the default agent (main) carries, falling back to the
# most common key across agents when main has none.
#
# Usage:  memory-index-check.sh
# Env:    OPENCLAW_AGENTS_DIR, MEMORY_PRUNE_LOG_DIR
# Exit:   0 healthy, 1 drift found (the cron shows the run as failed), 2 cannot run.

set -uo pipefail

command -v python3 >/dev/null 2>&1 || { echo "memory-index-check: python3 not found" >&2; exit 2; }

exec python3 - "$@" <<'PYEOF'
import collections, glob, json, os, sqlite3, sys, time

root = os.environ.get("OPENCLAW_STATE_DIR") or (
    "/data/.openclaw" if os.path.isdir("/data/.openclaw") else os.path.expanduser("~/.openclaw"))
agents_dir = os.environ.get("OPENCLAW_AGENTS_DIR") or os.path.join(root, "agents")
log_dir = os.environ.get("MEMORY_PRUNE_LOG_DIR") or os.path.join(root, "logs")
os.makedirs(log_dir, exist_ok=True)

stores = {}
for db in sorted(glob.glob(os.path.join(agents_dir, "*", "agent", "openclaw-agent.sqlite"))):
    agent = db.split(os.sep)[-3]
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=15)
        row = con.execute(
            "select value from memory_index_meta where key='memory_index_meta_v1'").fetchone()
        chunks = con.execute("select count(*) from memory_index_chunks").fetchone()[0]
        con.close()
        meta = json.loads(row[0]) if row else {}
        stores[agent] = (meta, chunks)
    except (sqlite3.Error, ValueError):
        stores[agent] = (None, 0)  # unreadable store; reported below

if not stores:
    print("no agent stores found")
    sys.exit(0)

live = (stores.get("main", ({}, 0))[0] or {}).get("providerKey")
if not live:
    keys = [m.get("providerKey") for m, _ in stores.values() if m and m.get("providerKey")]
    live = collections.Counter(keys).most_common(1)[0][0] if keys else None
if not live:
    print("cannot determine the live providerKey (no agent has an index stamp)")
    sys.exit(2)

drift = []
for agent, (meta, chunks) in stores.items():
    if meta is None:
        drift.append((agent, "unreadable"))
    elif chunks == 0:
        continue  # an empty index legitimately carries no stamp and no vectors
    elif meta.get("providerKey") != live:
        drift.append((agent, f"providerKey-drift({str(meta.get('providerKey'))[:12]})"))
    elif "vectorDims" not in meta:
        drift.append((agent, "missing-vectorDims"))

print(f"live providerKey: {live[:12]}…   agent stores: {len(stores)}   drifted: {len(drift)}")
for agent, why in drift:
    print(f"  DRIFT {agent} — {why}   (vector search paused; repair: openclaw memory index --agent {agent} --force)")
with open(os.path.join(log_dir, "memory-index-check.jsonl"), "a") as fh:
    fh.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                         "total": len(stores), "drifted": len(drift),
                         "agents": [a for a, _ in drift]}) + "\n")
sys.exit(1 if drift else 0)
PYEOF
