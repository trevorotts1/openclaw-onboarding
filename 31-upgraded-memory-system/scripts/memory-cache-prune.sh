#!/usr/bin/env bash
# memory-cache-prune.sh — reclaim disk from dead rows in every agent's
# memory_embedding_cache. Pure maintenance: no LLM, no network, no re-embedding.
#
# WHY THIS EXISTS
# ---------------
# Each agent DB (<state>/agents/<id>/agent/openclaw-agent.sqlite) caches one
# embedding per chunk hash in memory_embedding_cache, keyed by
# (provider, model, provider_key, hash). A 3072-dim vector serialized as JSON is
# ~66 KB, and nothing in the runtime ever deletes a cache row. Two kinds pile up:
#
#   1. STALE KEY  — rows under a provider_key other than the one this agent's
#      index is stamped with (memory_index_meta.memory_index_meta_v1.providerKey).
#      An upgrade that changes the embedding identity strands every old row; the
#      runtime only looks up the current key, so they can never be read again.
#   2. ORPHANED   — rows under the current key whose hash matches no row in
#      memory_index_chunks: the chunk they were cached for was edited or deleted.
#      Measured on one box: 7,133 rows = 0.47 GB across 5 agents (one agent alone
#      held 6,205 rows / 410 MB). Only rows older than ORPHAN_GRACE_DAYS (default
#      7) are pruned, so a reindex in flight or a file restored within the week
#      still hits the cache. Worst case after that: one embed call for that text.
#
# Each agent is judged against ITS OWN index stamp, never another agent's: during
# an upgrade some agents are re-stamped before others, and a box-wide key would
# delete the fresh rows of whichever agents moved first.
#
# VACUUM runs after rows are deleted, or when a DB already holds at least
# VACUUM_FREE_MB (default 256) of free pages: an OpenClaw schema migration
# rebuilds tables and leaves the old pages behind (2026.9.6 left 2.6 GB free on
# one box, 0.9 GB in a single agent DB). VACUUM rewrites the whole file, so it is
# skipped when free disk is under twice the DB's size — it would fail anyway.
# A DB that stays locked past the busy timeout is skipped and retried next run.
#
# python3 stdlib sqlite3 does the work: the Docker base image ships no sqlite3
# CLI. Safe while the gateway runs (SQLite locking + WAL); schedule it off-hours.
#
# Usage:
#   memory-cache-prune.sh            # prune + vacuum
#   memory-cache-prune.sh --dry-run  # report reclaimable rows/bytes, write nothing
# Env: OPENCLAW_AGENTS_DIR, MEMORY_PRUNE_LOG_DIR, ORPHAN_GRACE_DAYS (default 7),
#      VACUUM_FREE_MB (default 256).
# Exit: 0 ok (including skipped-busy), 1 a DB errored, 2 python3 missing.

set -uo pipefail

command -v python3 >/dev/null 2>&1 || { echo "memory-cache-prune: python3 not found" >&2; exit 2; }

exec python3 - "$@" <<'PYEOF'
import glob, json, os, shutil, sqlite3, sys, time

dry = "--dry-run" in sys.argv[1:]
root = os.environ.get("OPENCLAW_STATE_DIR") or (
    "/data/.openclaw" if os.path.isdir("/data/.openclaw") else os.path.expanduser("~/.openclaw"))
agents_dir = os.environ.get("OPENCLAW_AGENTS_DIR") or os.path.join(root, "agents")
log_dir = os.environ.get("MEMORY_PRUNE_LOG_DIR") or os.path.join(root, "logs")
grace_days = int(os.environ.get("ORPHAN_GRACE_DAYS") or 7)
cutoff_ms = int((time.time() - grace_days * 86400) * 1000)
vacuum_free = int(os.environ.get("VACUUM_FREE_MB") or 256) * 1048576
os.makedirs(log_dir, exist_ok=True)
ledger = os.path.join(log_dir, "memory-cache-prune.jsonl")


def log(**row):
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **row}
    with open(ledger, "a") as fh:
        fh.write(json.dumps(row) + "\n")


def size(db):
    return sum(os.path.getsize(p) for p in (db, db + "-wal") if os.path.exists(p))


def own_key(con):
    row = con.execute(
        "select value from memory_index_meta where key='memory_index_meta_v1'").fetchone()
    try:
        return json.loads(row[0]).get("providerKey") if row else None
    except ValueError:
        return None


print("(dry run — no writes)" if dry else "pruning", f"grace={grace_days}d", agents_dir)
touched = rows_total = bytes_total = errors = 0
for db in sorted(glob.glob(os.path.join(agents_dir, "*", "agent", "openclaw-agent.sqlite"))):
    agent = db.split(os.sep)[-3]
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro" if dry else db, uri=True, timeout=15,
                              isolation_level=None)
        tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        if not {"memory_embedding_cache", "memory_index_chunks", "memory_index_meta"} <= tables:
            con.close()
            continue
        key = own_key(con)
        dead = "(updated_at < ? AND hash NOT IN (SELECT hash FROM memory_index_chunks))"
        args = [cutoff_ms]
        if key:
            dead, args = f"(provider_key <> ? OR {dead})", [key, cutoff_ms]
        n, nbytes = con.execute(
            f"select count(*), coalesce(sum(length(embedding)),0) from memory_embedding_cache where {dead}",
            args).fetchone()
        free = con.execute("pragma freelist_count").fetchone()[0] * \
            con.execute("pragma page_size").fetchone()[0]
        if n == 0 and free < vacuum_free:
            con.close()
            continue
        before = size(db)
        room = shutil.disk_usage(os.path.dirname(db)).free >= 2 * before
        if n == 0 and not room:
            print(f"  SKIP {agent}: {free // 1048576} MB free pages, not enough disk to vacuum")
            con.close()
            continue
        if dry:
            print(f"  would prune {agent}: {n} rows (~{nbytes // 1048576} MB), "
                  f"{free // 1048576} MB free pages{'' if room else ' (vacuum skipped: low disk)'}")
        else:
            if n:
                con.execute(f"delete from memory_embedding_cache where {dead}", args)
            if room:
                con.execute("vacuum")
                con.execute("pragma wal_checkpoint(TRUNCATE)")
            after = size(db)
            status = ("pruned" if n else "compacted") + ("" if room else "-no-vacuum-low-disk")
            print(f"  {status} {agent}: {n} rows, {before // 1048576} MB -> {after // 1048576} MB")
            log(agent=agent, rows=n, before_mb=before // 1048576, after_mb=after // 1048576,
                status=status)
        con.close()
        touched += 1; rows_total += n; bytes_total += nbytes
    except sqlite3.OperationalError as e:
        if "locked" in str(e) or "busy" in str(e):
            print(f"  SKIP {agent} (db busy)")
            log(agent=agent, status="busy")
        else:
            errors += 1
            print(f"  ERROR {agent}: {e}", file=sys.stderr)
            log(agent=agent, status="error", error=str(e)[:200])
    except sqlite3.Error as e:
        errors += 1
        print(f"  ERROR {agent}: {e}", file=sys.stderr)
        log(agent=agent, status="error", error=str(e)[:200])

print("----")
print(f"agents affected: {touched}   dead rows: {rows_total}   dead vector payload: ~{bytes_total // 1048576} MB")
log(event="summary", agents=touched, rows=rows_total, payload_mb=bytes_total // 1048576,
    dry_run=int(dry), errors=errors)
sys.exit(1 if errors else 0)
PYEOF
