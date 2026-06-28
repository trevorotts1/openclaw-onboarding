#!/usr/bin/env bash
# tests/unit/provision-idempotency.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Acceptance test for the v14.27.2 canonical persona-index idempotency gate.
#
# Proves that provision_persona_index() RE-PROVISIONS a non-canonical partial
# index (the 6260 / 7615 / 9456-row locally-re-embedded indexes the OLD
# "has section_number column ⇒ done" gate wrongly SKIPPED) while genuinely
# SKIPPING the canonical 4413-row v2.1.0 asset — and that the live-operator
# index (content-canonical but unstamped sentinel) self-heals instead of
# triggering a 90MB re-download (furnace guard).
#
# Also proves reconcile_persona_assets() converges a drifted 40-persona box to
# the canonical 54 personas + canonical persona-categories.json md5.
#
# Fully offline: PROVISION_DRY_RUN=1 stops the gate before any network I/O.
# Requires python3 with the stdlib sqlite3 module (present on ubuntu-latest).
#
# Exit 0 = all checks pass. Exit 1 = one or more failed.
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HELPER="$REPO_ROOT/shared-utils/provision-persona-index.sh"
MANIFEST="$REPO_ROOT/shared-utils/prebuilt-index/INDEX-MANIFEST.json"
SK22="$REPO_ROOT/22-book-to-persona-coaching-leadership-system"
CANON_CAT_MD5="c544561074e6e1d65aed1840b6f03b8c"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== provision-idempotency.test.sh ==="

if [ ! -f "$HELPER" ]; then
    echo "  FAIL: helper not found at $HELPER"; exit 1
fi
# shellcheck source=/dev/null
source "$HELPER"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Helper: write a sqlite index with section_number+mode columns and N rows.
_mk_index() {
    python3 - "$1" "$2" <<'PY'
import sqlite3, sys
p, n = sys.argv[1], int(sys.argv[2])
c = sqlite3.connect(p)
c.execute("CREATE TABLE embeddings(id INTEGER, file_path TEXT, section_number INTEGER, mode TEXT)")
c.executemany("INSERT INTO embeddings VALUES(?,?,?,?)",
              [(i, f"/x/personas/p{i % 54}/f.md", 3, "both") for i in range(n)])
c.commit(); c.close()
PY
}
_mk_54_dirs() {
    mkdir -p "$1/personas"
    for i in $(seq 1 54); do mkdir -p "$1/personas/persona-$i"; done
}

export PROVISION_DRY_RUN=1

# ─── (1) Non-canonical 6260-row index (sentinel v2.1.0, 54 dirs) → RE-PROVISION
echo "--- (1) non-canonical 6260-row index re-provisions ---"
D1="$WORK/box-6260"; mkdir -p "$D1"
_mk_index "$D1/gemini-index.sqlite" 6260
printf 'prebuilt-index-v2.1.0\n' > "$D1/.prebuilt-index-version"
_mk_54_dirs "$D1"
OUT1="$(provision_persona_index "$MANIFEST" "$D1" 2>&1)"
echo "$OUT1" | grep -q "NEEDS (re)provision" \
    && pass "1a: 6260-row index triggers NEEDS (re)provision" \
    || fail "1a: 6260-row index did NOT trigger re-provision (out: $OUT1)"
echo "$OUT1" | grep -q "chunk-count:6260!=4413" \
    && pass "1b: reason is chunk-count:6260!=4413" \
    || fail "1b: chunk-count mismatch reason missing (out: $OUT1)"
echo "$OUT1" | grep -q "skipping download" \
    && fail "1c: 6260-row index wrongly skipped" \
    || pass "1c: 6260-row index did NOT skip"

# ─── (2) Canonical 4413-row index + sentinel + 54 dirs → SKIP
echo "--- (2) canonical 4413-row index skips ---"
D2="$WORK/box-canon"; mkdir -p "$D2"
_mk_index "$D2/gemini-index.sqlite" 4413
printf 'prebuilt-index-v2.1.0\n' > "$D2/.prebuilt-index-version"
_mk_54_dirs "$D2"
OUT2="$(provision_persona_index "$MANIFEST" "$D2" 2>&1)"
echo "$OUT2" | grep -q "already canonical" \
    && pass "2a: canonical 4413-row index reports already canonical" \
    || fail "2a: canonical index not recognized (out: $OUT2)"
echo "$OUT2" | grep -q "NEEDS (re)provision" \
    && fail "2b: canonical index wrongly flagged for re-provision" \
    || pass "2b: canonical index NOT re-provisioned"

# ─── (3) Live-operator-like: canonical 4413 + EMPTY sentinel + 54 dirs → self-heal+SKIP
echo "--- (3) operator-like index self-heals sentinel, skips download ---"
D3="$WORK/box-operator"; mkdir -p "$D3"
_mk_index "$D3/gemini-index.sqlite" 4413
: > "$D3/.prebuilt-index-version"   # empty sentinel (built locally, never stamped)
_mk_54_dirs "$D3"
OUT3="$(provision_persona_index "$MANIFEST" "$D3" 2>&1)"
echo "$OUT3" | grep -q "self-heal" \
    && pass "3a: empty-sentinel canonical index self-heals" \
    || fail "3a: self-heal not triggered (out: $OUT3)"
echo "$OUT3" | grep -q "would download" \
    && fail "3b: operator index wrongly scheduled a download (furnace)" \
    || pass "3b: operator index did NOT schedule a download"
STAMP="$(tr -d '[:space:]' < "$D3/.prebuilt-index-version")"
[ "$STAMP" = "prebuilt-index-v2.1.0" ] \
    && pass "3c: sentinel stamped to prebuilt-index-v2.1.0" \
    || fail "3c: sentinel not stamped (got '$STAMP')"

# ─── (4) Missing 'mode' column → RE-PROVISION
echo "--- (4) missing mode column re-provisions ---"
D4="$WORK/box-nomode"; mkdir -p "$D4"
python3 - "$D4/gemini-index.sqlite" <<'PY'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
c.execute("CREATE TABLE embeddings(id INTEGER, section_number INTEGER)")
c.executemany("INSERT INTO embeddings VALUES(?,?)", [(i, 3) for i in range(4413)])
c.commit(); c.close()
PY
_mk_54_dirs "$D4"
printf 'prebuilt-index-v2.1.0\n' > "$D4/.prebuilt-index-version"
OUT4="$(provision_persona_index "$MANIFEST" "$D4" 2>&1)"
echo "$OUT4" | grep -q "missing-column:mode" \
    && pass "4a: missing 'mode' column triggers re-provision" \
    || fail "4a: missing mode column not caught (out: $OUT4)"

# ─── (5) reconcile_persona_assets converges 40 → 54 + canonical categories md5
echo "--- (5) reconcile converges drifted 40-persona box to canonical 54 ---"
if [ ! -d "$SK22/personas" ] || [ ! -f "$SK22/persona-categories.json" ]; then
    fail "5: Skill-22 source missing — cannot test reconcile"
else
    WS="$WORK/ws"; CDB="$WS/data/coaching-personas"
    mkdir -p "$CDB/personas" "$WS/coaching-personas"
    # 40 stale persona dirs with placeholder blueprints
    # shellcheck disable=SC2012
    ls -d "$SK22"/personas/*/ | head -40 | while read -r p; do
        s="$(basename "$p")"; mkdir -p "$CDB/personas/$s"
        echo "STALE-PLACEHOLDER" > "$CDB/personas/$s/persona-blueprint.md"
    done
    echo '{"categories":"OLD-40-NON-CANONICAL"}' > "$WS/coaching-personas/persona-categories.json"

    reconcile_persona_assets "$SK22" "$CDB" "$WS" >/dev/null 2>&1

    DIRS="$(find "$CDB/personas" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')"
    NONEMPTY="$(find "$CDB/personas" -name persona-blueprint.md -size +0c 2>/dev/null | wc -l | tr -d ' ')"
    STALE="$(grep -rl 'STALE-PLACEHOLDER' "$CDB/personas" 2>/dev/null | wc -l | tr -d ' ')"
    DATA_MD5="$(_pidx_md5 "$CDB/persona-categories.json")"
    LEG_MD5="$(_pidx_md5 "$WS/coaching-personas/persona-categories.json")"

    [ "$DIRS" = "54" ] && pass "5a: persona dirs converged 40 → 54" || fail "5a: dirs=$DIRS (expected 54)"
    [ "$NONEMPTY" = "54" ] && pass "5b: 54 non-empty blueprints on disk" || fail "5b: non-empty=$NONEMPTY"
    [ "$STALE" = "0" ] && pass "5c: stale placeholder blueprints overwritten" || fail "5c: $STALE stale remain"
    [ "$DATA_MD5" = "$CANON_CAT_MD5" ] && pass "5d: data/ categories md5 == canonical" || fail "5d: data md5=$DATA_MD5"
    [ "$LEG_MD5" = "$CANON_CAT_MD5" ] && pass "5e: legacy categories md5 == canonical" || fail "5e: legacy md5=$LEG_MD5"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    echo "FAIL: $FAIL assertion(s) failed"
    exit 1
fi
echo "PASS: all assertions passed"
exit 0
