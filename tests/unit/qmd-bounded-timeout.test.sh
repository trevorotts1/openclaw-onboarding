#!/usr/bin/env bash
# tests/unit/qmd-bounded-timeout.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# THE DEFECT THIS LOCKS (v20.0.81): every `qmd` invocation in
# shared-utils/provision-persona-index.sh was UNBOUNDED. On a box whose native
# better-sqlite3 ABI is broken, `qmd` falls through to `bunx @tobilu/qmd`, which
# takes ~17 MINUTES to download, start and then fail. Three sequential calls
# burned ~50 of one update run's 64 minutes.
#
# Worse than slow: the removes were written `qmd collection remove ... || true`,
# so a call that never completed was indistinguishable from one that succeeded.
# The updater printed "removing the collection" for a collection it had not
# removed, and the agent kept reading a store the log said was gone.
#
# THE CONTRACT LOCKED HERE:
#   1. every qmd call runs under a hard wall-clock bound
#   2. a call that hits the bound is REPORTED per-call, on stderr
#   3. a run with any timeout emits an end-of-block `STATUS: qmd-timeout`
#   4. a timed-out run NEVER claims the store was indexed or removed
#   5. the function still cannot abort its caller under `set -e`
#
# Hermetic: a stub `qmd` (and a stub `npm`, so the ABI-repair path cannot touch
# the runner's real npm) are placed on PATH inside a temp dir. No network, no
# real qmd, no fleet box.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$REPO_ROOT/shared-utils/provision-persona-index.sh"
[ -f "$SRC" ] || { echo "FATAL: not found: $SRC"; exit 1; }

TD="$(mktemp -d)"
trap 'rm -rf "$TD"' EXIT

# A qmd that never answers. 25s is long enough that FIVE unbounded calls blow
# past the 60s assertion below, and short enough that the suite stays quick.
STUB_SLEEP="${QMD_STUB_SLEEP:-25}"
mkdir -p "$TD/bin"
cat > "$TD/bin/qmd" <<EOF
#!/bin/sh
sleep ${STUB_SLEEP}
EOF
cat > "$TD/bin/npm" <<'EOF'
#!/bin/sh
exit 1
EOF
chmod +x "$TD/bin/qmd" "$TD/bin/npm"

mkdir -p "$TD/db/personas/example-slug"
echo "# blueprint" > "$TD/db/personas/example-slug/persona-blueprint.md"

export PATH="$TD/bin:$PATH"
# Short bounds keep the suite fast; the wrapper logic under test is identical.
export QMD_LIST_TIMEOUT=3
export QMD_INDEX_TIMEOUT=3

# shellcheck disable=SC1090
. "$SRC"

START=$(date +%s)
OUTPUT="$(reconcile_qmd_persona_index "$TD/db" 2>&1)"
RC=$?
ELAPSED=$(( $(date +%s) - START ))

echo "----- captured output -----"
echo "$OUTPUT"
echo "----- end output -----"
echo "elapsed=${ELAPSED}s rc=${RC} (stub qmd sleeps ${STUB_SLEEP}s per call)"
echo

FAILED=0
ok()   { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAILED=1; }

echo "[1] every qmd call is bounded"
if [ "$ELAPSED" -ge 60 ]; then
    fail "took ${ELAPSED}s — at least one qmd call ran unbounded"
else
    ok "completed in ${ELAPSED}s despite a ${STUB_SLEEP}s-per-call stub"
fi

echo "[2] a timed-out call is reported, not swallowed"
if echo "$OUTPUT" | grep -q "TIMED OUT"; then
    ok "per-call timeout notice present"
else
    fail "no 'TIMED OUT' notice — the timeout was swallowed"
fi

echo "[3] the run emits an end-of-block qmd-timeout STATUS"
if echo "$OUTPUT" | grep -q "STATUS: qmd-timeout"; then
    ok "STATUS: qmd-timeout emitted"
else
    fail "no 'STATUS: qmd-timeout' summary"
fi

echo "[4] a timed-out run never claims success"
if echo "$OUTPUT" | grep -qE "✓ qmd .*(indexed|already canonical)"; then
    fail "claimed the store was reconciled while every qmd call timed out"
else
    ok "no success claimed"
fi

echo "[5] the reconcile cannot abort its caller"
if [ "$RC" -eq 0 ]; then
    ok "returned 0 (additive)"
else
    fail "returned $RC — would abort the updater under set -e"
fi

# ── anti-false-positive control ──────────────────────────────────────────────
# A "fix" that simply always prints a timeout would pass everything above. So:
# with a FAST, WORKING qmd stub the run must NOT report a timeout at all.
echo
echo "[6] control: a fast, working qmd must NOT report a timeout"
cat > "$TD/bin/qmd" <<'EOF'
#!/bin/sh
case "$1 $2" in
  "collection list") printf 'coaching-personas (qmd://coaching-personas/)\n  Pattern: **/*.md\n  Files:   9\n  Updated: now\n' ;;
  *) : ;;
esac
exit 0
EOF
chmod +x "$TD/bin/qmd"
_QMD_TIMEOUTS=0
_QMD_TIMEOUT_CALLS=""
OUT2="$(reconcile_qmd_persona_index "$TD/db" 2>&1)"
RC2=$?
if echo "$OUT2" | grep -qE "TIMED OUT|STATUS: qmd-timeout"; then
    fail "reported a timeout for a qmd that answered immediately"
    echo "$OUT2"
else
    ok "no timeout reported for a healthy qmd (rc=${RC2})"
fi

echo
if [ "$FAILED" -eq 0 ]; then
    echo "QMD BOUNDED-TIMEOUT SUITE: ALL PASS"
else
    echo "QMD BOUNDED-TIMEOUT SUITE: FAILURES"
fi
exit "$FAILED"
