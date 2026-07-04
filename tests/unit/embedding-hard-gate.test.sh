#!/usr/bin/env bash
# tests/unit/embedding-hard-gate.test.sh — embedding-subsystem hardening gates
#
# Proves the EMBED-1..3 invariants that killed the historical silent failures:
#
#   T1  NO KEY => FAIL LOUD: gemini-section-indexer.py with no resolvable
#       Gemini key exits non-zero and writes NOTHING (the old code silently
#       wrote fake hash-derived 768-dim vectors stamped as gemini/3072).
#   T2  FAKE MODE IS EXPLICIT + TRUTHFUL: --allow-fake-embeddings writes rows
#       stamped provider='fake' model='deterministic-hash-768' dim=768 — never
#       a lying gemini stamp — and only into an explicit --db target.
#   T3  VERIFY GATE CATCHES FAKES: embedding_engine --verify fails (rc 4) on
#       a fake-mode DB AND on a row with a LYING gemini/3072 stamp over a
#       768-dim blob; passes (rc 0) on a well-formed gemini/3072 DB.
#   T4  SANDBOX WRITE-GUARD: a run against the DEFAULT live DB under an
#       overridden $HOME (sandbox) without OPENCLAW_SANDBOX=1 exits 4 before
#       touching anything.
#   T5  ONE DB PATH: detect_platform paths["gemini_index"] ==
#       embedding_engine.DB_PATH == .../data/coaching-personas/gemini-index.sqlite
#       in BOTH detect_platform copies (shared-utils + 23-.../lib).
#
# Offline: never calls any embedding API; needs python3 + sqlite3 (stdlib) only.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INDEXER="$REPO_ROOT/23-ai-workforce-blueprint/scripts/gemini-section-indexer.py"
ENGINE="$REPO_ROOT/shared-utils/embedding_engine.py"
PASS=0
FAIL=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== embedding-hard-gate.test.sh ==="

[ -f "$INDEXER" ] || { echo "FAIL: indexer not found: $INDEXER"; exit 1; }
[ -f "$ENGINE" ]  || { echo "FAIL: engine not found: $ENGINE"; exit 1; }

# ── Fixtures ──────────────────────────────────────────────────────────────────
# Sandbox HOME (makes detect_platform resolve mac under $TMP, and makes
# home_is_overridden() true on any runner).
SBHOME="$TMP/sbhome"
mkdir -p "$SBHOME/.openclaw/workspace/data"

# A minimal persona blueprint with a coaching (3) and leadership (4) section,
# each over the 30-word floor.
FIXTURE="$TMP/fixture/personas"
mkdir -p "$FIXTURE/testauthor-testbook"
cat > "$FIXTURE/testauthor-testbook/persona-blueprint.md" <<'MD'
# Test Persona Blueprint

## Section 3: Coaching Framework
This is the coaching framework section of the fixture persona. It contains
enough words to clear the minimum section word floor used by the section
parser so that the indexer emits a row for it during the plumbing test run.

## Section 4: Agent Governance Framework
This is the leadership governance section of the fixture persona. It also
contains enough words to clear the minimum section word floor used by the
section parser so the indexer emits a second row for the leadership mode.
MD

run_indexer() {
    # Clean provider env: no Gemini key can leak in from the operator box.
    env -u GOOGLE_API_KEY -u GEMINI_API_KEY -u OPENAI_API_KEY \
        HOME="$SBHOME" OPENCLAW_SANDBOX=1 \
        python3 "$INDEXER" "$@" 2>&1
}

# ── T1: no key => fail loud, write nothing ───────────────────────────────────
T1_DB="$TMP/t1.sqlite"
T1_OUT="$(run_indexer --db "$T1_DB" --personas-root "$FIXTURE" --reindex-all)"
T1_RC=$?
if [ "$T1_RC" -ne 0 ]; then
    pass "T1a: keyless indexer run exits non-zero (rc=$T1_RC)"
else
    fail "T1a: keyless indexer run exited 0 — silent-fake regression! Output: $(echo "$T1_OUT" | tail -3)"
fi
if echo "$T1_OUT" | grep -qi "REFUSING to index"; then
    pass "T1b: refusal message names the hard gate"
else
    fail "T1b: expected loud refusal message, got: $(echo "$T1_OUT" | tail -3)"
fi
T1_ROWS="$(python3 -c "
import sqlite3, os, sys
p = sys.argv[1]
if not os.path.exists(p):
    print(0); sys.exit()
try:
    print(sqlite3.connect(p).execute('SELECT COUNT(*) FROM embeddings').fetchone()[0])
except Exception:
    print(0)
" "$T1_DB")"
if [ "$T1_ROWS" = "0" ]; then
    pass "T1c: zero rows written on keyless run"
else
    fail "T1c: keyless run wrote $T1_ROWS rows"
fi

# ── T2: explicit fake mode writes TRUTHFUL metadata ──────────────────────────
T2_DB="$TMP/t2.sqlite"
T2_OUT="$(run_indexer --db "$T2_DB" --personas-root "$FIXTURE" --reindex-all --allow-fake-embeddings)"
T2_RC=$?
if [ "$T2_RC" -eq 0 ]; then
    pass "T2a: fake mode with explicit --db succeeds (rc=0)"
else
    fail "T2a: fake mode failed (rc=$T2_RC): $(echo "$T2_OUT" | tail -3)"
fi
T2_CHECK="$(python3 -c "
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
rows = c.execute('SELECT provider, model, dim, length(vector) FROM embeddings').fetchall()
if not rows:
    print('NO-ROWS'); sys.exit()
bad = [r for r in rows if r[0] != 'fake' or r[1] != 'deterministic-hash-768'
       or r[2] != 768 or r[3] != 768 * 4]
gemini_liars = [r for r in rows if r[0] == 'gemini']
print(f'rows={len(rows)} bad={len(bad)} liars={len(gemini_liars)}')
" "$T2_DB")"
if echo "$T2_CHECK" | grep -q "bad=0 liars=0" && ! echo "$T2_CHECK" | grep -q "NO-ROWS"; then
    pass "T2b: all fake rows truthfully stamped fake/deterministic-hash-768/768 ($T2_CHECK)"
else
    fail "T2b: fake rows mis-stamped: $T2_CHECK"
fi
# Fake mode against the DEFAULT DB (no --db) without sandbox opt-in must refuse.
T2C_OUT="$(env -u GOOGLE_API_KEY -u GEMINI_API_KEY -u OPENAI_API_KEY -u OPENCLAW_SANDBOX \
    HOME="$SBHOME" python3 "$INDEXER" --reindex-all --allow-fake-embeddings 2>&1)"
T2C_RC=$?
if [ "$T2C_RC" -ne 0 ]; then
    pass "T2c: fake mode against default live DB refused (rc=$T2C_RC)"
else
    fail "T2c: fake mode against default live DB was ALLOWED"
fi

# ── T3: --verify catches fake and lying-stamp DBs, passes clean ones ─────────
python3 "$ENGINE" --verify --db "$T2_DB" >/dev/null 2>&1
T3_RC=$?
if [ "$T3_RC" -eq 4 ]; then
    pass "T3a: --verify fails (rc=4) on fake-mode DB"
else
    fail "T3a: --verify rc=$T3_RC on fake-mode DB (want 4)"
fi
# Lying stamp: row claims gemini/gemini-embedding-2/3072 but blob is 768-dim.
T3_DB="$TMP/t3.sqlite"
python3 - "$T3_DB" <<'PY'
import sqlite3, struct, sys
conn = sqlite3.connect(sys.argv[1])
conn.execute("""CREATE TABLE embeddings (
    id TEXT PRIMARY KEY, file_path TEXT, chunk_index INTEGER, content TEXT,
    vector BLOB, last_updated REAL, provider TEXT, model TEXT, dim INTEGER)""")
fake = struct.pack("768f", *([0.5] * 768))
conn.execute("INSERT INTO embeddings VALUES (?,?,?,?,?,?,?,?,?)",
             ("liar__section_03", "x/coaching-personas/personas/liar/persona-blueprint.md",
              3, "text", fake, 0.0, "gemini", "gemini-embedding-2", 3072))
conn.commit()
PY
python3 "$ENGINE" --verify --db "$T3_DB" >/dev/null 2>&1
T3B_RC=$?
if [ "$T3B_RC" -eq 4 ]; then
    pass "T3b: --verify fails (rc=4) on LYING gemini/3072 stamp over a 768-dim blob"
else
    fail "T3b: --verify rc=$T3B_RC on lying-stamp DB (want 4)"
fi
# Clean DB: correctly-shaped 3072-dim rows stamped gemini => rc 0.
T3C_DB="$TMP/t3c.sqlite"
python3 - "$T3C_DB" <<'PY'
import sqlite3, struct, sys
conn = sqlite3.connect(sys.argv[1])
conn.execute("""CREATE TABLE embeddings (
    id TEXT PRIMARY KEY, file_path TEXT, chunk_index INTEGER, content TEXT,
    vector BLOB, last_updated REAL, provider TEXT, model TEXT, dim INTEGER)""")
good = struct.pack("3072f", *([0.25] * 3072))
for i in (3, 4):
    conn.execute("INSERT INTO embeddings VALUES (?,?,?,?,?,?,?,?,?)",
                 (f"good__section_{i:02d}",
                  "x/coaching-personas/personas/good/persona-blueprint.md",
                  i, "text", good, 0.0, "gemini", "gemini-embedding-2", 3072))
conn.commit()
PY
python3 "$ENGINE" --verify --db "$T3C_DB" >/dev/null 2>&1
T3C_RC=$?
if [ "$T3C_RC" -eq 0 ]; then
    pass "T3c: --verify passes (rc=0) on a well-formed gemini/3072 DB"
else
    fail "T3c: --verify rc=$T3C_RC on clean DB (want 0)"
fi

# ── T4: sandbox write-guard on the DEFAULT live DB ───────────────────────────
T4_OUT="$(env -u OPENCLAW_SANDBOX -u GOOGLE_API_KEY -u GEMINI_API_KEY \
    HOME="$SBHOME" python3 "$INDEXER" --reindex-all 2>&1)"
T4_RC=$?
if [ "$T4_RC" -eq 4 ]; then
    pass "T4a: default-DB run under overridden HOME exits 4 (sandbox guard)"
else
    fail "T4a: default-DB run under overridden HOME rc=$T4_RC (want 4): $(echo "$T4_OUT" | tail -3)"
fi
if echo "$T4_OUT" | grep -q "OPENCLAW_SANDBOX"; then
    pass "T4b: guard message names the OPENCLAW_SANDBOX opt-in"
else
    fail "T4b: guard message missing OPENCLAW_SANDBOX hint: $(echo "$T4_OUT" | tail -3)"
fi
if [ ! -f "$SBHOME/.openclaw/workspace/data/coaching-personas/gemini-index.sqlite" ] \
   && [ ! -f "$SBHOME/.openclaw/workspace/data/gemini-index.sqlite" ]; then
    pass "T4c: nothing was written into the sandbox workspace"
else
    fail "T4c: guard leaked a DB into the sandbox workspace"
fi

# ── T5: one DB path across both path authorities + the engine ────────────────
T5_OUT="$(HOME="$SBHOME" OPENCLAW_PLATFORM=mac python3 - "$REPO_ROOT" <<'PY'
import sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / "shared-utils"))
from detect_platform import get_openclaw_paths
import embedding_engine as E
p = get_openclaw_paths()
suffix = "data/coaching-personas/gemini-index.sqlite"
assert str(p["gemini_index"]).endswith(suffix), p["gemini_index"]
assert str(p["gemini_index"]) == E.DB_PATH, (p["gemini_index"], E.DB_PATH)
# The Skill-23 lib copy must agree.
import importlib.util
spec = importlib.util.spec_from_file_location(
    "lib_dp", root / "23-ai-workforce-blueprint" / "lib" / "detect_platform.py")
lib_dp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib_dp)
p2 = lib_dp.get_openclaw_paths()
assert str(p2["gemini_index"]).endswith(suffix), p2["gemini_index"]
print("UNIFIED")
PY
)"
if echo "$T5_OUT" | grep -q "UNIFIED"; then
    pass "T5: gemini_index unified across shared-utils, lib copy, and engine DB_PATH"
else
    fail "T5: DB path authorities disagree: $T5_OUT"
fi

echo ""
echo "=== embedding-hard-gate: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
exit 0
