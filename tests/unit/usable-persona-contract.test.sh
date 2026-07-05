#!/usr/bin/env bash
# tests/unit/usable-persona-contract.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Hermetic tests for the F1.1 inbox-watcher false-success fix.
#
# Part A — the shared usable-persona contract (pipeline/usable-persona-contract.sh):
#   asserts blueprint + categories key + >=1 index row, with a DISTINCT exit
#   code per missing leg, and prefix-slug safety (slug `foo` is not satisfied by
#   a `foo-bar` index row).
#
# Part B — the inbox-watcher (scripts/persona-inbox-watcher.sh) end-to-end, in a
#   sandboxed HOME with a STUB converter. This is the adversarial headline
#   assertion: the watcher NEVER moves a source to processed/ unless all three
#   contract legs are present. Covers:
#     B1 all three legs present, exit 0        -> moved to processed/
#     B2 exit 0 but NO legs (false-success)    -> stays in inbox (retry), NOT processed/
#     B3 blueprint+categories but NO index row -> stays in inbox, NOT processed/
#     B4 converter exit 7 (ORCHESTRATOR_MISSING) -> NOT processed/
#
# No network, no Gemini key, no openclaw CLI. sqlite via python3 stdlib.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILL="$REPO_ROOT/22-book-to-persona-coaching-leadership-system"
CONTRACT="$SKILL/pipeline/usable-persona-contract.sh"
WATCHER="$SKILL/scripts/persona-inbox-watcher.sh"

PASS=0; FAIL=0
pass() { echo "  PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

for f in "$CONTRACT" "$WATCHER"; do
    [ -f "$f" ] || { echo "FATAL: missing $f"; exit 2; }
done

SB="$(mktemp -d -t upc-test.XXXXXX)"
trap 'rm -rf "$SB"' EXIT

# Build a coaching-personas base with a chosen subset of legs.
#   mk_base <base> <slug> <blueprint:0|1> <catkey:0|1> <indexrow:0|1>
mk_base() {
    local base="$1" slug="$2" bp="$3" cat="$4" idx="$5"
    mkdir -p "$base/personas/$slug"
    [ "$bp" = "1" ] && printf '# %s\n\nblueprint body\n' "$slug" > "$base/personas/$slug/persona-blueprint.md"
    BASE="$base" SLUG="$slug" CAT="$cat" IDX="$idx" python3 - <<'PY'
import json, os, sqlite3
base=os.environ["BASE"]; slug=os.environ["SLUG"]
cat=os.environ["CAT"]=="1"; idx=os.environ["IDX"]=="1"
catpath=base+"/persona-categories.json"
data={"schemaVersion":"1.1","personas":{}}
if cat:
    data["personas"][slug]={"author":"A","book":"B","domain":["mindset"],"perspective":[]}
json.dump(data, open(catpath,"w"), indent=2)
db=base+"/gemini-index.sqlite"
c=sqlite3.connect(db)
c.execute("""CREATE TABLE IF NOT EXISTS embeddings(
  id TEXT PRIMARY KEY, file_path TEXT, chunk_index INTEGER, content TEXT,
  vector BLOB, last_updated REAL, provider TEXT, model TEXT, dim INTEGER)""")
if idx:
    fp="/home/x/.openclaw/workspace/data/coaching-personas/personas/%s/persona-blueprint.md"%slug
    c.execute("INSERT OR REPLACE INTO embeddings(id,file_path,chunk_index) VALUES(?,?,0)",(slug+"#0",fp))
c.commit(); c.close()
PY
}

echo "── Part A: usable-persona contract (per-leg exit codes) ──"

A="$SB/A"; mk_base "$A" "atomic-habits" 1 1 1
bash "$CONTRACT" "$A" "atomic-habits" >/dev/null 2>&1
[ $? -eq 0 ] && pass "all three legs present -> exit 0" || fail "all legs present should be 0"

B="$SB/B"; mk_base "$B" "deep-work" 0 1 1
bash "$CONTRACT" "$B" "deep-work" >/dev/null 2>&1
[ $? -eq 2 ] && pass "blueprint missing -> exit 2" || fail "blueprint missing should be 2 (got $?)"

C="$SB/C"; mk_base "$C" "grit" 1 0 1
bash "$CONTRACT" "$C" "grit" >/dev/null 2>&1
[ $? -eq 3 ] && pass "categories key missing -> exit 3" || fail "categories missing should be 3 (got $?)"

D="$SB/D"; mk_base "$D" "mindset-book" 1 1 0
bash "$CONTRACT" "$D" "mindset-book" >/dev/null 2>&1
[ $? -eq 4 ] && pass "zero index rows -> exit 4" || fail "no index row should be 4 (got $?)"

# Prefix-slug safety: an index row for `focus-book` must NOT satisfy `focus`.
E="$SB/E"; mk_base "$E" "focus-book" 1 1 1
mkdir -p "$E/personas/focus"; printf '# focus\nbody\n' > "$E/personas/focus/persona-blueprint.md"
python3 -c "import json;p='$E/persona-categories.json';d=json.load(open(p));d['personas']['focus']={'domain':['mindset']};json.dump(d,open(p,'w'))"
bash "$CONTRACT" "$E" "focus" >/dev/null 2>&1
[ $? -eq 4 ] && pass "prefix slug not satisfied by sibling's index row -> exit 4" || fail "prefix-slug leak: 'focus' wrongly matched 'focus-book' row (got $?)"

echo "── Part B: inbox-watcher never moves to processed/ without all three legs ──"

if [ -d /data/.openclaw/master-files ]; then
    echo "  SKIP Part B: /data/.openclaw/master-files exists (would resolve to a REAL VPS workspace; not sandboxable)."
else
    # Assemble a sandbox skill tree the watcher can resolve relative to itself.
    SKDIR="$SB/skill"
    mkdir -p "$SKDIR/scripts" "$SKDIR/pipeline"
    cp "$WATCHER" "$SKDIR/scripts/persona-inbox-watcher.sh"
    cp "$CONTRACT" "$SKDIR/pipeline/usable-persona-contract.sh"
    # Orchestrator only needs to EXIST (watcher self-disables otherwise).
    printf '#!/usr/bin/env python3\n' > "$SKDIR/pipeline/orchestrator.py"

    # STUB converter: computes the same slug the watcher does, then — per
    # STUB_MODE — writes some/all/none of the three legs and exits with a code.
    cat > "$SKDIR/scripts/add-persona-from-source.sh" <<'STUB'
#!/bin/bash
set -uo pipefail
SRC=""
while [ $# -gt 0 ]; do case "$1" in --source) SRC="$2"; shift 2;; --title|--author) shift 2;; *) shift;; esac; done
BASE="$HOME/.openclaw/workspace/data/coaching-personas"
bn="$(basename "$SRC")"; bn="${bn%.*}"
slug="$(echo "$bn" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g; s/-\{2,\}/-/g; s/^-//; s/-$//')"
mkdir -p "$BASE/personas/$slug"
case "${STUB_MODE:-full}" in
  full)
    printf '# %s\nbody\n' "$slug" > "$BASE/personas/$slug/persona-blueprint.md"
    BASE="$BASE" SLUG="$slug" python3 - <<'PY'
import json,os,sqlite3
base=os.environ["BASE"]; slug=os.environ["SLUG"]
p=base+"/persona-categories.json"
d=json.load(open(p)) if os.path.exists(p) else {"personas":{}}
d.setdefault("personas",{})[slug]={"domain":["mindset"],"perspective":[]}
json.dump(d,open(p,"w"))
c=sqlite3.connect(base+"/gemini-index.sqlite")
c.execute("CREATE TABLE IF NOT EXISTS embeddings(id TEXT PRIMARY KEY,file_path TEXT,chunk_index INTEGER,content TEXT,vector BLOB,last_updated REAL,provider TEXT,model TEXT,dim INTEGER)")
c.execute("INSERT OR REPLACE INTO embeddings(id,file_path,chunk_index) VALUES(?,?,0)",(slug+"#0",base+"/personas/"+slug+"/persona-blueprint.md"))
c.commit()
PY
    exit 0 ;;
  noindex)
    printf '# %s\nbody\n' "$slug" > "$BASE/personas/$slug/persona-blueprint.md"
    BASE="$BASE" SLUG="$slug" python3 - <<'PY'
import json,os
base=os.environ["BASE"]; slug=os.environ["SLUG"]
p=base+"/persona-categories.json"
d=json.load(open(p)) if os.path.exists(p) else {"personas":{}}
d.setdefault("personas",{})[slug]={"domain":["mindset"],"perspective":[]}
json.dump(d,open(p,"w"))
import sqlite3
c=sqlite3.connect(base+"/gemini-index.sqlite")
c.execute("CREATE TABLE IF NOT EXISTS embeddings(id TEXT PRIMARY KEY,file_path TEXT,chunk_index INTEGER,content TEXT,vector BLOB,last_updated REAL,provider TEXT,model TEXT,dim INTEGER)")
c.commit()
PY
    exit 0 ;;
  empty)   exit 0 ;;
  missing) exit 7 ;;
esac
STUB
    chmod +x "$SKDIR/scripts/add-persona-from-source.sh" "$SKDIR/scripts/persona-inbox-watcher.sh" "$SKDIR/pipeline/usable-persona-contract.sh"

    run_watcher() {  # $1=STUB_MODE  $2=source basename ; echoes nothing, sets globals
        local mode="$1" fname="$2"
        HOME_SB="$SB/home-$mode"
        rm -rf "$HOME_SB"
        local pbase="$HOME_SB/.openclaw/workspace/data/coaching-personas"
        mkdir -p "$pbase/inbox"
        printf 'dummy source text\n' > "$pbase/inbox/$fname"
        STUB_MODE="$mode" HOME="$HOME_SB" bash "$SKDIR/scripts/persona-inbox-watcher.sh" >/dev/null 2>&1 || true
        INBOX="$pbase/inbox"; PROC="$pbase/inbox/processed"; FAILED="$pbase/inbox/failed"
    }

    # B1 — full success: all three legs -> processed/
    run_watcher full "b1-book.txt"
    if [ -f "$PROC/b1-book.txt" ] && [ ! -f "$INBOX/b1-book.txt" ]; then
        pass "B1 all legs present -> source moved to processed/"
    else
        fail "B1 expected processed/b1-book.txt and empty inbox"
    fi

    # B2 — false success: exit 0, NO legs -> must NOT be in processed/
    run_watcher empty "b2-book.txt"
    if [ ! -f "$PROC/b2-book.txt" ] && [ -f "$INBOX/b2-book.txt" ]; then
        pass "B2 exit 0 but no legs -> NOT processed/, left in inbox for retry"
    else
        fail "B2 false-success leaked to processed/ (or source vanished with no retry)"
    fi

    # B3 — blueprint+categories but NO index row -> must NOT be in processed/
    run_watcher noindex "b3-book.txt"
    if [ ! -f "$PROC/b3-book.txt" ] && [ -f "$INBOX/b3-book.txt" ]; then
        pass "B3 missing index row -> NOT processed/ (all three legs required)"
    else
        fail "B3 vector-less persona leaked to processed/"
    fi

    # B4 — converter exit 7 (ORCHESTRATOR_MISSING) -> must NOT be in processed/
    run_watcher missing "b4-book.txt"
    if [ ! -f "$PROC/b4-book.txt" ] && [ -f "$INBOX/b4-book.txt" ]; then
        pass "B4 orchestrator-missing (exit 7) -> NOT processed/, left for retry"
    else
        fail "B4 orchestrator-missing leaked to processed/"
    fi

    # B5 — idempotency-branch counter-example: a blueprint ALREADY exists for the
    # slug but the other two legs are absent. The old idempotency short-circuit
    # moved straight to processed/ on blueprint-only; with the contract gate it
    # must NOT. (Converter runs in `empty` mode so no legs get completed.)
    HOME_SB="$SB/home-b5"; rm -rf "$HOME_SB"
    pbase5="$HOME_SB/.openclaw/workspace/data/coaching-personas"
    mkdir -p "$pbase5/inbox" "$pbase5/personas/b5-book"
    printf '# b5-book\nstale half-built blueprint\n' > "$pbase5/personas/b5-book/persona-blueprint.md"
    printf 'dummy\n' > "$pbase5/inbox/b5-book.txt"
    STUB_MODE="empty" HOME="$HOME_SB" bash "$SKDIR/scripts/persona-inbox-watcher.sh" >/dev/null 2>&1 || true
    if [ ! -f "$pbase5/inbox/processed/b5-book.txt" ] && [ -f "$pbase5/inbox/b5-book.txt" ]; then
        pass "B5 pre-existing blueprint but missing categories/index -> NOT processed/ (idempotency gate holds)"
    else
        fail "B5 half-built persona (blueprint-only) leaked to processed/ via idempotency short-circuit"
    fi
fi

echo ""
echo "──────────────────────────────────────────────"
echo "usable-persona-contract.test.sh: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
