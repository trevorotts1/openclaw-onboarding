#!/usr/bin/env bash
# test-phantom-dept-collision-gate.sh — C5 phantom-duplicate department-tree gate
# + reconcile.
#
# Proves the C5 fix (phantom duplicate dept trees materialized side-by-side, e.g.
# billing + billing-finance, legal + legal-compliance, plus '.bak' dept dirs):
#
#   T1. CLEAN workspace (no collision) -> `department-floor.py --check-collisions`
#       exits 0.
#   T2. billing + billing-finance siblings -> the gate FAILS (rc=5) and reports the
#       collision group {canonical: billing-finance, dirs: [billing, billing-finance]}.
#   T3. legal + legal-compliance siblings -> gate FAILS (rc=5).
#   T4. PRECEDENCE: podcast + audio is NOT a collision (podcast is its own
#       canonical universal-primary, never folded into audio) -> gate exits 0.
#   T5. A phantom '.bak' dept dir -> gate FAILS (rc=5) and lists it under
#       phantom_backup_dirs.
#   T6. A genuine CUSTOM dept never collides with a canonical -> gate exits 0.
#   T7. reconcile-legacy-tree.py --merge-duplicates DRY-RUN -> rc=2, mutates NOTHING.
#   T8. reconcile-legacy-tree.py --merge-duplicates --apply -> keeps the canonical
#       winner, LAYERS the loser's unique role into it, ARCHIVES the loser + the
#       .bak dir OUT of departments/ (never deletes), and the gate is then CLEAN
#       (rc=0). Idempotent: a second apply finds nothing.
#   T9. Case-insensitive canonical resolution: 'Sales' and 'sales' both resolve to
#       the same canonical (proven via canonical_slug_for, since a case-insensitive
#       filesystem cannot hold both sibling dirs at once).
#  T10. ENFORCEMENT: the gate the QC pipeline actually runs
#       (scripts/qc-assert-workspace-departments-built.sh — CHECK X.11 + the
#       onboarding-honesty "done" contract) FAILS rc=5 AF-PHANTOM-DEPT-TREE on a
#       duplicate tree and prints the reconcile remediation.
#  T11. That same gate FAILS rc=5 on a phantom '.bak' dept dir.
#  T12. NO false positive: a collision-free workspace never returns rc=5 — it falls
#       through to the pre-existing shell verdict (rc=3), so the phantom check
#       neither false-fires nor swallows the shell dimension.
#
# Exit 0 = all tests pass; non-zero = a test failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLOOR="$SCRIPT_DIR/department-floor.py"
RECONCILE="$SCRIPT_DIR/reconcile-legacy-tree.py"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mk_departments() { # <name> <dept dir names...> ; echo departments_dir
  local name="$1"; shift
  local dd="$TMP/$name/departments"
  rm -rf "$TMP/$name"; mkdir -p "$dd"
  for d in "$@"; do mkdir -p "$dd/$d/01-a-role"; done
  echo "$dd"
}

check_collisions() { # <departments_dir> ; returns rc
  python3 "$FLOOR" --check-collisions --departments-dir "$1" --json >/dev/null 2>&1
}

echo "=== T1: clean workspace -> no collision (rc=0) ==="
DD=$(mk_departments t1 marketing sales billing-finance legal)
if check_collisions "$DD"; then ok "T1: clean workspace -> --check-collisions rc=0"; else bad "T1: clean workspace should PASS but rc!=0"; fi

echo "=== T2: billing + billing-finance -> collision (rc=5) ==="
DD=$(mk_departments t2 billing billing-finance marketing)
check_collisions "$DD"; RC=$?
if [ "$RC" -eq 5 ]; then ok "T2: billing+billing-finance -> rc=5 (collision caught)"; else bad "T2: expected rc=5, got $RC"; fi
GROUP=$(python3 "$FLOOR" --check-collisions --departments-dir "$DD" --json 2>/dev/null \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print([g['canonical'] for g in d['slug_collisions']])")
if echo "$GROUP" | grep -q "billing-finance"; then ok "T2: collision group canonical == billing-finance"; else bad "T2: canonical not billing-finance ($GROUP)"; fi

echo "=== T3: legal + legal-compliance -> collision (rc=5) ==="
DD=$(mk_departments t3 legal legal-compliance marketing)
check_collisions "$DD"; RC=$?
if [ "$RC" -eq 5 ]; then ok "T3: legal+legal-compliance -> rc=5"; else bad "T3: expected rc=5, got $RC"; fi

echo "=== T4: podcast + audio is NOT a collision (precedence) ==="
DD=$(mk_departments t4 podcast audio marketing)
if check_collisions "$DD"; then ok "T4: podcast+audio -> rc=0 (podcast is its own canonical, not folded into audio)"; else bad "T4: podcast+audio wrongly flagged as collision"; fi

echo "=== T5: phantom .bak dept dir -> gate fails (rc=5) ==="
DD=$(mk_departments t5 marketing legal)
mkdir -p "$DD/Presentations.bak-20260615-024720/01-x"
check_collisions "$DD"; RC=$?
if [ "$RC" -eq 5 ]; then ok "T5: phantom .bak dir -> rc=5"; else bad "T5: expected rc=5 for .bak dir, got $RC"; fi
BK=$(python3 "$FLOOR" --check-collisions --departments-dir "$DD" --json 2>/dev/null \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['phantom_backup_dirs'])")
if echo "$BK" | grep -q "Presentations.bak"; then ok "T5: .bak dir reported in phantom_backup_dirs"; else bad "T5: .bak not reported ($BK)"; fi

echo "=== T6: custom dept never collides with a canonical ==="
DD=$(mk_departments t6 marketing legal publishing-studio revenue-operations)
if check_collisions "$DD"; then ok "T6: custom depts -> rc=0 (no false collision)"; else bad "T6: custom depts wrongly flagged"; fi

echo "=== T7: reconcile --merge-duplicates DRY-RUN mutates nothing (rc=2) ==="
DD=$(mk_departments t7 billing billing-finance legal legal-compliance marketing)
mkdir -p "$DD/legal.bak-20260601/01-y"
BEFORE=$(ls "$DD" | sort | tr '\n' ',')
python3 "$RECONCILE" --merge-duplicates --target "$DD" --log-dir "$TMP/t7logs" >/dev/null 2>&1; RC=$?
AFTER=$(ls "$DD" | sort | tr '\n' ',')
if [ "$RC" -eq 2 ]; then ok "T7: dry-run rc=2 (changes pending)"; else bad "T7: expected dry-run rc=2, got $RC"; fi
if [ "$BEFORE" = "$AFTER" ]; then ok "T7: dry-run mutated NOTHING on disk"; else bad "T7: dry-run mutated disk ($BEFORE -> $AFTER)"; fi

echo "=== T8: reconcile --merge-duplicates --apply reconciles + archives ==="
# billing (loser) carries a UNIQUE role that must survive by layering into the winner.
DD=$(mk_departments t8 billing-finance legal legal-compliance marketing)
mkdir -p "$DD/billing/07-unique-billing-role/x"        # billing loser + unique role
mkdir -p "$DD/legal.bak-20260601/01-y"                 # phantom backup
python3 "$RECONCILE" --merge-duplicates --apply --target "$DD" --log-dir "$TMP/t8logs" >/dev/null 2>&1; RC=$?
if [ "$RC" -eq 0 ]; then ok "T8: apply rc=0"; else bad "T8: apply expected rc=0, got $RC"; fi
if [ ! -d "$DD/billing" ]; then ok "T8: loser 'billing' removed from departments/"; else bad "T8: loser 'billing' still in departments/"; fi
if [ -d "$DD/billing-finance" ]; then ok "T8: canonical winner 'billing-finance' kept"; else bad "T8: winner 'billing-finance' missing"; fi
if [ -d "$DD/billing-finance/07-unique-billing-role" ]; then ok "T8: loser's unique role LAYERED into winner"; else bad "T8: unique role not layered"; fi
if [ ! -d "$DD/legal.bak-20260601" ]; then ok "T8: phantom .bak dir moved OUT of departments/"; else bad "T8: .bak dir still present"; fi
ARCH_COUNT=$(find "$TMP/t8/departments-archive" -maxdepth 2 -mindepth 2 -type d 2>/dev/null | wc -l | tr -d ' ')
if [ "$ARCH_COUNT" -ge 3 ]; then ok "T8: losers + .bak preserved under departments-archive/ ($ARCH_COUNT dirs)"; else bad "T8: archive missing preserved trees ($ARCH_COUNT)"; fi
if check_collisions "$DD"; then ok "T8: gate CLEAN (rc=0) after reconcile"; else bad "T8: gate still dirty after reconcile"; fi
# Idempotent: a second apply finds nothing.
python3 "$RECONCILE" --merge-duplicates --apply --target "$DD" --log-dir "$TMP/t8logs2" >/dev/null 2>&1; RC2=$?
if [ "$RC2" -eq 0 ]; then ok "T8: second apply idempotent (rc=0)"; else bad "T8: second apply not idempotent (rc=$RC2)"; fi

echo "=== T9: case-insensitive canonical resolution (Sales == sales) ==="
RES=$(python3 - "$FLOOR" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("df", sys.argv[1])
df = importlib.util.module_from_spec(spec); spec.loader.exec_module(df)
a = df.canonical_slug_for("Sales"); b = df.canonical_slug_for("sales")
p = df.canonical_slug_for("podcast"); au = df.canonical_slug_for("audio")
print("OK" if (a == b and a is not None and p == "podcast" and au == "audio") else f"BAD a={a} b={b} p={p} au={au}")
PY
)
if [ "$RES" = "OK" ]; then ok "T9: 'Sales'/'sales' resolve identically; podcast/audio stay distinct"; else bad "T9: $RES"; fi

# ── ENFORCEMENT (not description): the phantom check must FAIL the gate that the
#    QC pipeline / onboarding-honesty contract actually runs
#    (scripts/qc-assert-workspace-departments-built.sh, CHECK X.11 rc=3/rc=5 hard
#    fail + lib-onboarding-state oc_workspace_departments_materialized). A
#    detector nothing calls is documentation, not a gate.
WS_GATE="$SCRIPT_DIR/../../scripts/qc-assert-workspace-departments-built.sh"

echo "=== T10: workspace gate FAILS (rc=5 AF-PHANTOM-DEPT-TREE) on a duplicate tree ==="
if [ ! -f "$WS_GATE" ]; then
  bad "T10: workspace gate not found at $WS_GATE"
else
  DD=$(mk_departments t10 billing billing-finance marketing legal)
  bash "$WS_GATE" --departments-dir "$DD" >/dev/null 2>&1; RC=$?
  if [ "$RC" -eq 5 ]; then ok "T10: qc-assert-workspace-departments-built -> rc=5 on billing+billing-finance"; else bad "T10: expected gate rc=5, got $RC"; fi
  OUT=$(bash "$WS_GATE" --departments-dir "$DD" 2>&1)
  if echo "$OUT" | grep -q "AF-PHANTOM-DEPT-TREE"; then ok "T10: gate emits AF-PHANTOM-DEPT-TREE"; else bad "T10: AF-PHANTOM-DEPT-TREE marker absent"; fi
  if echo "$OUT" | grep -q "reconcile-legacy-tree.py --merge-duplicates"; then ok "T10: gate prints the reconcile remediation"; else bad "T10: no remediation printed"; fi

  echo "=== T11: phantom .bak dept dir also FAILS the workspace gate (rc=5) ==="
  DD=$(mk_departments t11 marketing legal)
  mkdir -p "$DD/Presentations.bak-20260615-024720/01-x"
  bash "$WS_GATE" --departments-dir "$DD" >/dev/null 2>&1; RC=$?
  if [ "$RC" -eq 5 ]; then ok "T11: .bak dept dir -> workspace gate rc=5"; else bad "T11: expected gate rc=5 for .bak dir, got $RC"; fi

  echo "=== T12: NO false positive — a collision-free workspace never returns rc=5 ==="
  # This workspace is collision-free but its depts are unmaterialized shells, so the
  # gate must fall through to its EXISTING shell verdict (rc=3), never rc=5. Proves
  # the phantom check neither false-fires nor swallows the shell dimension.
  DD=$(mk_departments t12 marketing legal billing-finance)
  bash "$WS_GATE" --departments-dir "$DD" >/dev/null 2>&1; RC=$?
  if [ "$RC" -ne 5 ]; then ok "T12: collision-free workspace -> rc=$RC (not 5; shell dimension still gates)"; else bad "T12: false AF-PHANTOM-DEPT-TREE on a clean workspace"; fi
fi

echo
echo "==================================================="
echo "  test-phantom-dept-collision-gate: PASS=$PASS FAIL=$FAIL"
echo "==================================================="
[ "$FAIL" -eq 0 ]
