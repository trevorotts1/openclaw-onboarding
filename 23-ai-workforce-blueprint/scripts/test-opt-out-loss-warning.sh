#!/usr/bin/env bash
# test-opt-out-loss-warning.sh — P2-05 step 1 CI guard: the interview's decline
# step ECHOES a floor department's loss_warning and REQUIRES confirmation before
# the opt-out is recorded.
#
# WHAT IT PROVES (fails 3-ways against the pre-P2-05 tree):
#   1. Every one of the 28 FLOOR departments (22 mandatory + 6 universal-primary)
#      carries a non-empty loss_warning in department-naming-map.json.
#      (FAILS pre-fix: loss_warning did not exist.)
#   2. department-loss-warning.py returns the text (rc0) for a floor dept and
#      NOTHING (rc3) for a non-floor dept (industry-gated 'listings', a custom).
#      (FAILS pre-fix: the reader did not exist.)
#   3. record-dept-decision.sh --decision no for a FLOOR dept WITHOUT
#      --confirm-loss ECHOES the warning and REFUSES to write (exit 2, decision
#      absent). WITH --confirm-loss it writes, stamps lossWarningAck=true, and
#      canonical_decline.py HONORS the decline. A NON-floor dept decline needs no
#      confirmation and writes directly.
#      (FAILS pre-fix: the writer had no --confirm-loss gate and wrote blindly.)
#
# Exit 0 = all pass; non-zero = a test failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
NAMING_MAP="$SKILL_DIR/department-naming-map.json"
RECORDER="$SCRIPT_DIR/record-dept-decision.sh"
LOSS_READER="$SCRIPT_DIR/department-loss-warning.py"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

command -v jq >/dev/null 2>&1 || { echo "SKIP: jq not on PATH"; exit 0; }

# ── Test 1: all 28 floor depts carry a loss_warning ──────────────────────────
python3 - "$NAMING_MAP" <<'PYEOF'
import json, sys
nm = json.load(open(sys.argv[1]))
missing = []
mand = nm.get("mandatory", {})
for did, d in mand.items():
    if not (isinstance(d, dict) and d.get("loss_warning", "").strip()):
        missing.append(("mandatory", did))
univ = 0
for pack in nm.get("vertical_packs", {}).values():
    for d in pack.get("auto_add_departments", []):
        if isinstance(d, dict) and d.get("universal_primary"):
            univ += 1
            if not str(d.get("loss_warning", "")).strip():
                missing.append(("universal-primary", d.get("id")))
count = len(mand) + univ
if missing:
    print(f"  FAIL: {len(missing)} floor dept(s) missing loss_warning: {missing}")
    sys.exit(1)
if count != 28:
    print(f"  FAIL: expected 28 floor depts, found {count} (mandatory={len(mand)} univ={univ})")
    sys.exit(1)
print(f"  PASS: all 28 floor departments carry a loss_warning ({len(mand)} mandatory + {univ} universal-primary)")
PYEOF
if [ $? -eq 0 ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); fi

# ── Test 2: the loss-warning reader ──────────────────────────────────────────
if [ -x "$LOSS_READER" ] || [ -f "$LOSS_READER" ]; then
  if out="$(python3 "$LOSS_READER" --dept billing-finance)" && [ -n "$out" ]; then
    ok "reader returns text for a floor dept (billing-finance): '$out'"
  else
    bad "reader did not return text for floor dept billing-finance"
  fi
  # normalization-insensitive
  if [ "$(python3 "$LOSS_READER" --dept Billing_Finance)" = "$out" ]; then
    ok "reader is normalization-insensitive (Billing_Finance == billing-finance)"
  else
    bad "reader not normalization-insensitive"
  fi
  # non-floor industry-gated dept -> rc3, no text
  if lo="$(python3 "$LOSS_READER" --dept listings)"; rc=$?; [ "$rc" -eq 3 ] && [ -z "$lo" ]; then
    ok "reader rc=3 + empty for industry-gated non-floor dept (listings)"
  else
    bad "reader should rc=3/empty for non-floor listings (got rc=$rc text='$lo')"
  fi
else
  bad "department-loss-warning.py not found at $LOSS_READER"
fi

# ── Test 3: record-dept-decision.sh confirmation gate ────────────────────────
TMPD="$(mktemp -d)"
trap 'rm -rf "$TMPD"' EXIT
STATE="$TMPD/.workforce-build-state.json"

seed_state() {
  cat > "$STATE" <<'JSON'
{
  "canonicalReconciliation": {
    "customKeeps": ["my-custom-lab"],
    "decisions": {}
  }
}
JSON
}

# 3a: decline a FLOOR dept WITHOUT --confirm-loss => exit 2, warning echoed, NOT written
seed_state
set +e
werr="$(bash "$RECORDER" --dept billing-finance --decision no \
  --source owner-interview --by owner123 --session s1 --state "$STATE" 2>&1 >/dev/null)"
rc=$?
set -e
if [ "$rc" -eq 2 ]; then ok "floor decline without --confirm-loss exits 2"; else bad "expected exit 2, got $rc"; fi
if echo "$werr" | grep -q "OPT-OUT WARNING"; then ok "warning was echoed to the owner"; else bad "warning not echoed"; fi
if echo "$werr" | grep -q "invoices, collections"; then ok "the loss_warning text was shown"; else bad "loss_warning text not shown"; fi
written="$(jq -r '.canonicalReconciliation.decisions["billing-finance"] // "ABSENT"' "$STATE")"
if [ "$written" = "ABSENT" ]; then ok "decline NOT recorded without confirmation (dept stays in floor)"; else bad "decline was written without confirmation: $written"; fi

# 3b: decline a FLOOR dept WITH --confirm-loss => exit 0, written, ack stamped, honored
seed_state
set +e
bash "$RECORDER" --dept billing-finance --decision no --confirm-loss \
  --source owner-interview --by owner123 --session s1 --state "$STATE" >/dev/null 2>&1
rc=$?
set -e
if [ "$rc" -eq 0 ]; then ok "floor decline WITH --confirm-loss exits 0"; else bad "expected exit 0, got $rc"; fi
ack="$(jq -r '.canonicalReconciliation.decisions["billing-finance"].lossWarningAck // "MISSING"' "$STATE")"
if [ "$ack" = "true" ]; then ok "lossWarningAck=true stamped into the decision"; else bad "lossWarningAck not stamped (got $ack)"; fi
prov="$(jq -r '.canonicalReconciliation.decisions["billing-finance"] | [.decision,.source,.decidedAt,.decidedBy] | @tsv' "$STATE")"
if echo "$prov" | grep -q "no"; then ok "four provenance fields intact ($prov)"; else bad "provenance fields wrong: $prov"; fi

# canonical_decline.py must HONOR the confirmed decline
honored="$(python3 - "$SCRIPT_DIR" "$STATE" <<'PYEOF'
import sys, os, json, importlib.util
scripts_dir, state = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("cd", os.path.join(scripts_dir, "canonical_decline.py"))
cd = importlib.util.module_from_spec(spec); spec.loader.exec_module(cd)
bs = json.load(open(state))
declined = cd.canonical_decline_set(bs, quiet=True)
print("YES" if cd.norm("billing-finance") in declined else "NO")
PYEOF
)"
if [ "$honored" = "YES" ]; then ok "canonical_decline.py HONORS the confirmed floor decline"; else bad "confirmed decline not honored by canonical_decline.py"; fi

# 3c: decline a NON-floor custom dept => no confirmation needed, written directly
seed_state
set +e
bash "$RECORDER" --dept my-custom-lab --decision no \
  --source owner-interview --by owner123 --session s1 --state "$STATE" >/dev/null 2>&1
rc=$?
set -e
if [ "$rc" -eq 0 ]; then ok "non-floor custom decline needs no confirmation (exit 0)"; else bad "custom decline should exit 0, got $rc"; fi
cw="$(jq -r '.canonicalReconciliation.decisions["my-custom-lab"].decision // "ABSENT"' "$STATE")"
if [ "$cw" = "no" ]; then ok "custom decline written directly"; else bad "custom decline not written (got $cw)"; fi
cack="$(jq -r '.canonicalReconciliation.decisions["my-custom-lab"].lossWarningAck // "none"' "$STATE")"
if [ "$cack" = "none" ]; then ok "no lossWarningAck on a non-floor decline (nothing to lose)"; else bad "unexpected lossWarningAck on custom: $cack"; fi

echo ""
echo "── test-opt-out-loss-warning: $PASS passed, $FAIL failed ──"
[ "$FAIL" -eq 0 ] || exit 1
