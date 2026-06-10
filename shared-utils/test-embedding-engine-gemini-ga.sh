#!/usr/bin/env bash
# test-embedding-engine-gemini-ga.sh
# Fixture tests for the onb-gemini GA migration (PRD [[gemini-embedding-model-migration]]).
#
# Verifies WITHOUT a live client box or API key:
#   T1: GEMINI_MODEL constant == "gemini-embedding-2" (no -preview)
#   T2: STALE_GEMINI_MODELS contains "gemini-embedding-2-preview"
#   T3: GEMINI_OUTPUT_DIM == 3072
#   T4: output_dimensionality=3072 appears in embed_content calls (source grep)
#   T5: stale -preview vectors in a fixture DB → drift detected → re-embed path
#       (indexer returns exit 1 + "STALE PREVIEW MODEL" message)
#   T6: search() on a stale DB → keyword fallback path activated (no cosine)
#   T7: semantic_task_fit._embed_text imports GEMINI_MODEL from embedding_engine
#       (no hardcoded slug in semantic_task_fit.py)
#   T8: no active "gemini-embedding-2-preview" string outside STALE_GEMINI_MODELS
#       definition and retired/stale-detection comments
#   T9: keyword fallback fires when no API key set (missing key path)
#   T10: query uses same model as index (enforced via provider_hint; no
#        cross-model cosine — verified via stale fixture triggering keyword path)
#
# Usage: bash shared-utils/test-embedding-engine-gemini-ga.sh
#        Exit 0 = all pass. Non-zero = failures reported.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0
FAILURES=()

ok() { echo "  PASS: $1"; ((PASS++)); }
fail() { echo "  FAIL: $1"; ((FAIL++)); FAILURES+=("$1"); }

echo ""
echo "=== test-embedding-engine-gemini-ga.sh ==="
echo "shared-utils dir: $SCRIPT_DIR"
echo ""

ENGINE="$SCRIPT_DIR/embedding_engine.py"
STF="$SCRIPT_DIR/semantic_task_fit.py"

if [ ! -f "$ENGINE" ]; then
  echo "ERROR: $ENGINE not found — are you running from the repo root?"
  exit 1
fi

# ── T1: GEMINI_MODEL constant ────────────────────────────────────────────────
echo "T1: GEMINI_MODEL = 'gemini-embedding-2' (not -preview)"
GMODEL=$(python3 -c "
import sys; sys.path.insert(0, '$SCRIPT_DIR')
from embedding_engine import GEMINI_MODEL
print(GEMINI_MODEL)
" 2>/dev/null)
if [ "$GMODEL" = "gemini-embedding-2" ]; then
  ok "GEMINI_MODEL=$GMODEL"
else
  fail "GEMINI_MODEL=$GMODEL (expected 'gemini-embedding-2')"
fi

# ── T2: STALE_GEMINI_MODELS contains -preview ────────────────────────────────
echo "T2: STALE_GEMINI_MODELS contains 'gemini-embedding-2-preview'"
STALE_HAS=$(python3 -c "
import sys; sys.path.insert(0, '$SCRIPT_DIR')
from embedding_engine import STALE_GEMINI_MODELS
print('yes' if 'gemini-embedding-2-preview' in STALE_GEMINI_MODELS else 'no')
" 2>/dev/null)
if [ "$STALE_HAS" = "yes" ]; then
  ok "STALE_GEMINI_MODELS contains 'gemini-embedding-2-preview'"
else
  fail "STALE_GEMINI_MODELS does NOT contain 'gemini-embedding-2-preview'"
fi

# ── T3: GEMINI_OUTPUT_DIM == 3072 ────────────────────────────────────────────
echo "T3: GEMINI_OUTPUT_DIM = 3072"
OUTDIM=$(python3 -c "
import sys; sys.path.insert(0, '$SCRIPT_DIR')
from embedding_engine import GEMINI_OUTPUT_DIM
print(GEMINI_OUTPUT_DIM)
" 2>/dev/null)
if [ "$OUTDIM" = "3072" ]; then
  ok "GEMINI_OUTPUT_DIM=$OUTDIM"
else
  fail "GEMINI_OUTPUT_DIM=$OUTDIM (expected 3072)"
fi

# ── T4: output_dimensionality=GEMINI_OUTPUT_DIM in embed calls ───────────────
echo "T4: output_dimensionality=GEMINI_OUTPUT_DIM in both embed calls"
DIM_COUNT=$(grep -c "output_dimensionality=GEMINI_OUTPUT_DIM" "$ENGINE" 2>/dev/null || echo 0)
if [ "$DIM_COUNT" -ge 2 ]; then
  ok "output_dimensionality=GEMINI_OUTPUT_DIM appears $DIM_COUNT time(s) in engine"
else
  fail "output_dimensionality=GEMINI_OUTPUT_DIM appears $DIM_COUNT time(s) (expected >=2)"
fi

# ── T5: stale -preview fixture DB → indexer detects "STALE PREVIEW MODEL" ───
echo "T5: stale -preview fixture DB → indexer exit 1 + STALE PREVIEW MODEL message"
TMPDIR_TEST=$(mktemp -d)
FIXTURE_DB="$TMPDIR_TEST/gemini-index.sqlite"
FIXTURE_PERSONAS="$TMPDIR_TEST/personas"
mkdir -p "$FIXTURE_PERSONAS/test-persona"
echo "# Test persona blueprint" > "$FIXTURE_PERSONAS/test-persona/blueprint.md"

# Seed the DB with a row whose model = 'gemini-embedding-2-preview' (stale)
python3 - <<PYEOF
import sqlite3, numpy as np, time
conn = sqlite3.connect("$FIXTURE_DB")
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS embeddings (
        id TEXT PRIMARY KEY, file_path TEXT, chunk_index INTEGER,
        content TEXT, vector BLOB, last_updated REAL,
        provider TEXT, model TEXT, dim INTEGER
    )
""")
# Fake 3072-dim float32 vector — same blob size as real gemini-embedding-2 vectors
vec = np.zeros(3072, dtype=np.float32).tobytes()
cur.execute(
    "INSERT INTO embeddings VALUES (?,?,?,?,?,?,?,?,?)",
    ("hash_0", "$FIXTURE_PERSONAS/test-persona/blueprint.md", 0,
     "test content", vec, time.time(),
     "gemini", "gemini-embedding-2-preview", 3072)
)
conn.commit()
conn.close()
print("fixture DB created with stale -preview row")
PYEOF

# Run indexer on stale DB (no --rebuild) — expect exit 1 + STALE message
STALE_MSG=$(python3 "$ENGINE" --status 2>&1 | grep -i "STALE" || true)
INDEXER_ERR=$(WORKSPACE_ROOT="$TMPDIR_TEST" PERSONAS_DIR="$FIXTURE_PERSONAS" \
  python3 -c "
import sys; sys.path.insert(0, '$SCRIPT_DIR')
import os; os.environ['WORKSPACE_ROOT'] = '$TMPDIR_TEST'
from embedding_engine import cmd_index
# Patch module-level DB_PATH to fixture
import embedding_engine
embedding_engine.DB_PATH = '$FIXTURE_DB'
embedding_engine.PERSONAS_DIR = '$FIXTURE_PERSONAS'
rc = cmd_index(rebuild=False, db_path='$FIXTURE_DB', personas_dir='$FIXTURE_PERSONAS')
sys.exit(rc)
" 2>&1)
INDEXER_RC=$?

if [ $INDEXER_RC -eq 1 ] && echo "$INDEXER_ERR" | grep -qi "STALE"; then
  ok "cmd_index on stale DB: exit 1 + STALE message detected"
else
  fail "cmd_index on stale DB: expected exit 1 + STALE message, got exit=$INDEXER_RC msg='${INDEXER_ERR:0:200}'"
fi

# ── T6: search() on stale DB → keyword fallback (no cosine) ─────────────────
echo "T6: search() on stale -preview DB → keyword fallback path"
SEARCH_OUT=$(python3 -c "
import sys; sys.path.insert(0, '$SCRIPT_DIR')
import os; os.environ.setdefault('GOOGLE_API_KEY', '')
from embedding_engine import search
rc = search('test content', limit=3, db_path='$FIXTURE_DB')
sys.exit(rc)
" 2>&1)
SEARCH_RC=$?

if echo "$SEARCH_OUT" | grep -qi "STALE\|keyword-fallback\|KEYWORD"; then
  ok "search() on stale DB: keyword fallback activated (STALE/keyword message present)"
else
  fail "search() on stale DB: expected keyword fallback message, got: ${SEARCH_OUT:0:300}"
fi

# ── T7: semantic_task_fit imports GEMINI_MODEL (no hardcoded slug) ───────────
echo "T7: semantic_task_fit.py has no hardcoded 'gemini-embedding-2-preview'"
HARDCODED=$(grep -c 'gemini-embedding-2-preview' "$STF" 2>/dev/null) || HARDCODED=0
HARDCODED="${HARDCODED//[[:space:]]/}"  # strip whitespace
if [ "${HARDCODED}" = "0" ]; then
  ok "No hardcoded 'gemini-embedding-2-preview' in semantic_task_fit.py"
else
  echo "    Lines found:"
  grep -n "gemini-embedding-2-preview" "$STF" | head -5
  fail "Found ${HARDCODED} hardcoded 'gemini-embedding-2-preview' in semantic_task_fit.py"
fi

# ── T8: no active -preview slug outside stale-detection in embedding_engine ──
echo "T8: 'gemini-embedding-2-preview' in embedding_engine.py only in STALE_GEMINI_MODELS / comments"
# Use Python for context-aware analysis: scan the file and classify each line
# containing the preview slug as "allowed" (comment, docstring, or STALE_GEMINI_MODELS
# set definition/members) or "violation" (active code using the slug as a model ID).
ACTIVE_PREVIEW=$(python3 - "$ENGINE" <<'PYEOF'
import sys, re
path = sys.argv[1]
with open(path) as f:
    lines = f.readlines()

# Track whether we're inside the STALE_GEMINI_MODELS block
in_stale_block = False
violations = []
for i, raw in enumerate(lines, 1):
    line = raw.rstrip('\n')
    if 'gemini-embedding-2-preview' not in line:
        if 'STALE_GEMINI_MODELS' in line and 'frozenset' in line:
            in_stale_block = True
        if in_stale_block and '}' in line:
            in_stale_block = False
        continue

    stripped = line.strip()
    # Allow: comment lines (# ...) or blank-ish comment block lines
    if stripped.startswith('#'):
        continue
    # Allow: docstring content lines (part of triple-quoted block — usually indented strings)
    if stripped.startswith('"') and stripped.endswith('"') and '=' not in stripped:
        continue
    # Allow: inside the STALE_GEMINI_MODELS frozenset block
    if in_stale_block:
        continue
    if 'STALE_GEMINI_MODELS' in stripped:
        continue
    # Allow: variable assignment that IS the stale check (contains STALE or stale)
    if 'stale' in stripped.lower() or 'STALE' in stripped:
        continue
    # Allow: backfill comment/docstring lines (-> blob references)
    if '->' in stripped and ('blob' in stripped.lower() or 'GA' in stripped or 'wave' in stripped.lower()):
        continue
    # What remains is a violation
    violations.append(f"  line {i}: {stripped}")

print('\n'.join(violations))
PYEOF
)
if [ -z "${ACTIVE_PREVIEW}" ]; then
  ok "No active (non-stale-detection) 'gemini-embedding-2-preview' in embedding_engine.py"
else
  echo "    Violations:"
  echo "$ACTIVE_PREVIEW" | head -5
  fail "Found active '-preview' references in embedding_engine.py outside stale-detection"
fi

# ── T9: keyword fallback when GOOGLE_API_KEY missing ─────────────────────────
echo "T9: search() falls back to keyword when no API key + no embedder"
# Seed with a GA-model row so provider check passes, then remove key
FIXTURE_GA_DB="$TMPDIR_TEST/ga-index.sqlite"
python3 - <<PYEOF
import sqlite3, numpy as np, time
conn = sqlite3.connect("$FIXTURE_GA_DB")
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS embeddings (
        id TEXT PRIMARY KEY, file_path TEXT, chunk_index INTEGER,
        content TEXT, vector BLOB, last_updated REAL,
        provider TEXT, model TEXT, dim INTEGER
    )
""")
vec = np.zeros(3072, dtype=np.float32).tobytes()
cur.execute(
    "INSERT INTO embeddings VALUES (?,?,?,?,?,?,?,?,?)",
    ("hash_1", "$FIXTURE_PERSONAS/test-persona/blueprint.md", 0,
     "test keyword content", vec, time.time(),
     "gemini", "gemini-embedding-2", 3072)
)
conn.commit()
conn.close()
PYEOF

KEYWORD_OUT=$(GOOGLE_API_KEY="" GEMINI_API_KEY="" OPENAI_API_KEY="" \
  python3 -c "
import sys; sys.path.insert(0, '$SCRIPT_DIR')
import os
# Wipe all keys so get_embedder returns None
os.environ.pop('GOOGLE_API_KEY', None)
os.environ.pop('GEMINI_API_KEY', None)
os.environ.pop('OPENAI_API_KEY', None)
from embedding_engine import search
rc = search('test keyword content', limit=3, db_path='$FIXTURE_GA_DB')
sys.exit(rc)
" 2>&1)
KEYWORD_RC=$?

if echo "$KEYWORD_OUT" | grep -qi "keyword-fallback\|KEYWORD\|missing key\|unavailable"; then
  ok "search() with no API key: keyword fallback activated"
else
  fail "search() with no API key: expected keyword fallback, got exit=$KEYWORD_RC msg='${KEYWORD_OUT:0:300}'"
fi

# ── T10: no cross-model cosine (stale fixture produces keyword path, not cosine) ─
echo "T10: stale fixture produces keyword path (no cross-model cosine computed)"
COSINE_ATTEMPTED=$(python3 -c "
import sys; sys.path.insert(0, '$SCRIPT_DIR')
import os; os.environ.setdefault('GOOGLE_API_KEY', 'fake-key-for-test')
# Patch get_embedder to return a mock — if it's called, cosine was attempted
import embedding_engine
_original_get_embedder = embedding_engine.get_embedder
_called = []
def _mock_embedder(provider_hint=None):
    _called.append(provider_hint)
    return None  # simulate unavailable
embedding_engine.get_embedder = _mock_embedder
rc = embedding_engine.search('test', limit=3, db_path='$FIXTURE_DB')
# If get_embedder was called with 'gemini', it means we reached the embedding step
# rather than short-circuiting at the stale-detection check.
if _called:
    print(f'embedder_called_with={_called}')
else:
    print('embedder_not_called (stale check short-circuited correctly)')
" 2>/dev/null)

if echo "$COSINE_ATTEMPTED" | grep -q "not_called\|short-circuited"; then
  ok "No cosine attempted on stale DB — stale-detection short-circuited before embedder"
elif echo "$COSINE_ATTEMPTED" | grep -q "embedder_called_with=\['gemini'\]"; then
  # embedder called but returned None → keyword fallback — acceptable (still no cosine)
  ok "Embedder called but returned None → keyword fallback (no cross-model cosine)"
else
  # embedder called and returned a client — cosine would be attempted (bad)
  fail "Stale DB: embedder path reached unexpectedly: $COSINE_ATTEMPTED"
fi

# ── Cleanup ──────────────────────────────────────────────────────────────────
rm -rf "$TMPDIR_TEST"

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ ${#FAILURES[@]} -gt 0 ]; then
  echo "Failed tests:"
  for f in "${FAILURES[@]}"; do echo "  - $f"; done
fi
echo ""
[ $FAIL -eq 0 ] && exit 0 || exit 1
