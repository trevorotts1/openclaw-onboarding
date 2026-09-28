#!/usr/bin/env bash
# tests/unit/memory-cache-prune.test.sh — Skill 31 memory maintenance.
# Drives the real scripts against throwaway agent DBs and a fake `openclaw` CLI.
# No gateway, no network, never touches ~/.openclaw.
#
#   A. memory-cache-prune.sh deletes stale-key rows and old orphans, keeps live
#      rows and orphans inside the grace period, and judges each agent against
#      ITS OWN index stamp (an agent re-stamped first keeps its fresh rows).
#   B. --dry-run writes nothing.
#   C. a DB holding free pages but no dead rows is compacted.
#   D. memory-index-check.sh is read-only and exits 1 on drift, 0 when healthy.
#   E. install.sh schedules both jobs as silent command crons, is idempotent,
#      and honors a tombstone.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
S="$REPO/31-upgraded-memory-system"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
export OPENCLAW_AGENTS_DIR="$T/agents" MEMORY_PRUNE_LOG_DIR="$T/logs"
fail=0
check() { if [ "$2" = "$3" ]; then echo "PASS $1"; else echo "FAIL $1: got '$2' want '$3'"; fail=1; fi; }

# seed <agent> <index-key> — cache rows: live, stale key, old orphan, fresh orphan
seed() {
  mkdir -p "$T/agents/$1/agent"
  python3 - "$T/agents/$1/agent/openclaw-agent.sqlite" "$2" <<'PY'
import sqlite3, sys, time
db, key = sys.argv[1:]
now = int(time.time() * 1000); old = now - 30 * 86400000
c = sqlite3.connect(db)
c.executescript("""
CREATE TABLE memory_index_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE memory_index_chunks(id TEXT PRIMARY KEY, hash TEXT NOT NULL);
CREATE TABLE memory_embedding_cache(provider TEXT, model TEXT, provider_key TEXT, hash TEXT,
  embedding BLOB, dims INTEGER, updated_at INTEGER, PRIMARY KEY(provider, model, provider_key, hash));
INSERT INTO memory_index_chunks VALUES('c1', 'h-live');""")
c.execute("INSERT INTO memory_index_meta VALUES('memory_index_meta_v1', ?)",
          ('{"provider":"gemini","providerKey":"%s","vectorDims":3072}' % key,))
for k, h, t in ((key, "h-live", old), ("stalekey", "h-live", old),
                (key, "h-gone-old", old), (key, "h-gone-new", now)):
    c.execute("INSERT INTO memory_embedding_cache VALUES('gemini','m',?,?,x'00',1,?)", (k, h, t))
c.commit()
PY
}
left() { python3 -c "import sqlite3,sys;print(','.join(k+':'+h for k,h in sqlite3.connect(sys.argv[1]).execute('select provider_key,hash from memory_embedding_cache order by 1,2')))" "$T/agents/$1/agent/openclaw-agent.sqlite"; }
sha() { shasum "$T/agents/$1/agent/openclaw-agent.sqlite" | cut -d' ' -f1; }

seed main keyA; seed dept-x keyB

# ---- B. dry run ----
bash "$S/scripts/memory-cache-prune.sh" --dry-run >/dev/null
check "B dry-run leaves rows" "$(left main)" "keyA:h-gone-new,keyA:h-gone-old,keyA:h-live,stalekey:h-live"

# ---- A. prune ----
bash "$S/scripts/memory-cache-prune.sh" >/dev/null; rc=$?
check "A exit code" "$rc" "0"
check "A main pruned" "$(left main)" "keyA:h-gone-new,keyA:h-live"
check "A dept-x judged by its own key" "$(left dept-x)" "keyB:h-gone-new,keyB:h-live"
check "A ledger summary" "$(tail -1 "$T/logs/memory-cache-prune.jsonl" | python3 -c 'import json,sys;print(json.load(sys.stdin)["rows"])')" "4"

# ---- C. compaction of free pages with nothing to delete ----
python3 - "$T/agents/main/agent/openclaw-agent.sqlite" <<'PY'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
c.execute("CREATE TABLE junk(b BLOB)"); c.executemany("INSERT INTO junk VALUES(zeroblob(4096))", [()] * 600)
c.commit(); c.execute("DROP TABLE junk"); c.commit()
PY
free() { python3 -c "import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute('pragma freelist_count').fetchone()[0] > 0)" "$T/agents/main/agent/openclaw-agent.sqlite"; }
check "C free pages seeded" "$(free)" "True"
VACUUM_FREE_MB=1 bash "$S/scripts/memory-cache-prune.sh" >/dev/null
check "C compacted" "$(free)" "False"
check "C rows untouched" "$(left main)" "keyA:h-gone-new,keyA:h-live"

# ---- D. index check ----
before="$(sha dept-x)"
bash "$S/scripts/memory-index-check.sh" >/dev/null; rc=$?
check "D drift detected (dept-x keyB vs main keyA)" "$rc" "1"
check "D read-only" "$(sha dept-x)" "$before"
python3 -c "import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);c.execute(\"update memory_index_meta set value=replace(value,'keyB','keyA')\");c.commit()" "$T/agents/dept-x/agent/openclaw-agent.sqlite"
bash "$S/scripts/memory-index-check.sh" >/dev/null; rc=$?
check "D healthy" "$rc" "0"

# ---- E. installer against a fake openclaw CLI ----
mkdir -p "$T/bin" "$T/home"
cat > "$T/bin/openclaw" <<'SH'
#!/usr/bin/env bash
# fake: `cron list --json` serves $FAKE_JOBS; `cron add` appends a job and logs argv
[ "$1 $2" = "cron list" ] || [ "$1 $2" = "cron add" ] || exit 0
if [ "$2" = "list" ]; then [ "${3:-}" = "--help" ] && exit 0; cat "$FAKE_JOBS"; exit 0; fi
printf '%s\n' "$*" >> "$FAKE_LOG"
python3 - "$FAKE_JOBS" "$@" <<'PY'
import json, sys
path, args = sys.argv[1], sys.argv[2:]
jobs = json.load(open(path)); jobs["jobs"].append({"name": args[args.index("--name") + 1]})
json.dump(jobs, open(path, "w"))
PY
SH
chmod +x "$T/bin/openclaw"
export FAKE_JOBS="$T/jobs.json" FAKE_LOG="$T/cron-add.log"
echo '{"jobs":[]}' > "$FAKE_JOBS"; : > "$FAKE_LOG"
run_install() { HOME="$T/home" PATH="$T/bin:$PATH" bash "$S/install.sh" --idempotent >/dev/null; }
run_install; rc=$?
check "E install exit" "$rc" "0"
check "E two jobs added" "$(wc -l < "$FAKE_LOG" | tr -d ' ')" "2"
check "E all silent command crons" "$(grep -c -- '--no-deliver --command bash ' "$FAKE_LOG")" "2"
check "E check job is the read-only script" "$(grep -c 'memory-index-check.sh' "$FAKE_LOG")" "1"
check "E nothing re-embeds" "$(grep -c -E 'memory index|--force' "$FAKE_LOG")" "0"
run_install
check "E idempotent re-run" "$(wc -l < "$FAKE_LOG" | tr -d ' ')" "2"
echo '{"jobs":[]}' > "$FAKE_JOBS"; : > "$FAKE_LOG"
mkdir -p "$T/home/.openclaw/workspace/.cron-tombstones"
touch "$T/home/.openclaw/workspace/.cron-tombstones/memory-cache-prune"
run_install
check "E tombstone honored" "$(grep -c 'name memory-cache-prune' "$FAKE_LOG")" "0"

exit $fail
