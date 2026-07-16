#!/usr/bin/env bash
# test-department-optout-sync.sh — U108 (E5-3, closes G2b) CI guard.
#
# Proves department-optout-sync.py against all four BINARY acceptance items
# in the U108 slice (E5-3 / G2b — "Department opt-out + functionality
# WARNING"):
#
#   (a) opting a department out shows the functionality-loss warning naming
#       the lost capabilities.
#   (b) the opt-out is recorded and provisioning does NOT scaffold that
#       department (ONB-side half; the CC board-column half is U110's own
#       leg on the blackceo-command-center repo — see this unit's ledger
#       note for that cross-repo hand-off).
#   (c) re-opting-in restores the department (reversible).
#   (d) a guard proves no department is ever removed without the warning
#       being surfaced.
#
# Fails RED against the pre-U108 tree (department-optout-sync.py did not
# exist; there was no single `provisioning/department-optout.json` contract
# and no guard closing the lossWarningAck bypass gap — see the module
# docstring).
#
# Exit 0 = all pass; non-zero = a test failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
NAMING_MAP="$SKILL_DIR/department-naming-map.json"
RECORDER="$SCRIPT_DIR/record-dept-decision.sh"
SYNC="$SCRIPT_DIR/department-optout-sync.py"
MATERIALIZE="$SCRIPT_DIR/materialize-missing-departments.py"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

command -v jq >/dev/null 2>&1 || { echo "SKIP: jq not on PATH"; exit 0; }
python3 -c "import json" 2>/dev/null || { echo "SKIP: python3 not usable"; exit 0; }

[ -f "$SYNC" ] || { echo "FAIL: department-optout-sync.py not found at $SYNC"; exit 1; }

TMPD="$(mktemp -d)"
trap 'rm -rf "$TMPD"' EXIT

STATE="$TMPD/.workforce-build-state.json"
OUT="$TMPD/department-optout.json"

seed_state() {
  cat > "$STATE" <<'JSON'
{
  "canonicalReconciliation": {
    "decisions": {}
  }
}
JSON
}

# ── Test (a): opting out a FLOOR department shows the loss-warning, and the
#    sync artifact captures the exact text the owner was shown ─────────────
seed_state
bash "$RECORDER" --dept billing-finance --decision no --confirm-loss \
  --source owner-interview --by owner123 --session s1 --state "$STATE" >/dev/null 2>&1

rc=1
out="$(python3 "$SYNC" --state "$STATE" --out "$OUT" --json 2>/dev/null)"; rc=$?
if [ "$rc" -eq 0 ]; then ok "sync exits 0 for a fully-confirmed opt-out"; else bad "sync exited $rc for a confirmed opt-out"; fi

opted="$(echo "$out" | jq -r '.optedOut["billing-finance"].optedOut // "MISSING"')"
if [ "$opted" = "true" ]; then ok "billing-finance recorded as optedOut=true"; else bad "billing-finance not recorded as opted out (got $opted)"; fi

shown="$(echo "$out" | jq -r '.optedOut["billing-finance"].lossWarningShown // "MISSING"')"
if [ "$shown" = "true" ]; then ok "lossWarningShown=true"; else bad "lossWarningShown missing/false (got $shown)"; fi

text="$(echo "$out" | jq -r '.optedOut["billing-finance"].lossWarningText // ""')"
if echo "$text" | grep -q "invoices"; then ok "the functionality-loss text names the lost capability: '$text'"; else bad "loss warning text missing/wrong: '$text'"; fi

if [ -f "$OUT" ]; then ok "provisioning/department-optout.json (the U108-named artifact) was written to disk"; else bad "output file was not written"; fi

# ── Test (b): the opt-out is HONORED — provisioning does not scaffold it ───
# department_floor.evaluate_floor() is the shared function both
# materialize-missing-departments.py and build-workforce.py consult to decide
# what to scaffold. Build a departments/ fixture missing TWO departments:
# billing-finance (opted out above — must NOT be flagged as needing
# materialization) and marketing (a POSITIVE CONTROL, never declined — must
# still be flagged missing, proving the test is not vacuously green).
DEPTS_DIR="$TMPD/departments"
mkdir -p "$DEPTS_DIR"
python3 - "$SCRIPT_DIR" "$DEPTS_DIR" <<'PYEOF'
import sys, importlib.util
scripts_dir, depts_dir = sys.argv[1], sys.argv[2]
import os
spec = importlib.util.spec_from_file_location("df_fixture", os.path.join(scripts_dir, "department-floor.py"))
df = importlib.util.module_from_spec(spec); spec.loader.exec_module(df)
nm = df.load_naming_map()
mand = df.mandatory_ids(nm)
univ = df.universal_primary_vertical_departments(nm)
skip = {"billing-finance", "marketing"}
for dept_id in mand + univ:
    if dept_id in skip:
        continue
    os.makedirs(os.path.join(depts_dir, dept_id), exist_ok=True)
PYEOF

mrc=1
mout="$(python3 "$MATERIALIZE" --departments-dir "$DEPTS_DIR" --build-state-file "$STATE" --json 2>/dev/null)"; mrc=$?
missing="$(echo "$mout" | jq -r '.missing_before // [] | join(",")')"
if echo ",$missing," | grep -q ",marketing,"; then
  ok "positive control: undeclared 'marketing' correctly flagged missing_before (test is not vacuous)"
else
  bad "positive control failed: 'marketing' should be missing_before, got: $missing"
fi
if echo ",$missing," | grep -q ",billing-finance,"; then
  bad "opted-out 'billing-finance' was still flagged for scaffolding: $missing"
else
  ok "opted-out 'billing-finance' is NOT flagged for scaffolding (provisioning honors the opt-out): $missing"
fi

# ── Test (c): REVERSIBLE — re-opting-in restores the department ────────────
bash "$RECORDER" --dept billing-finance --decision yes \
  --source owner-interview --by owner123 --session s2 --state "$STATE" >/dev/null 2>&1

rout="$(python3 "$SYNC" --state "$STATE" --out "$OUT" --json 2>/dev/null)"
still_opted="$(echo "$rout" | jq -r '.optedOut["billing-finance"] // "ABSENT"')"
if [ "$still_opted" = "ABSENT" ]; then ok "re-opt-in: billing-finance no longer in optedOut (reversed)"; else bad "re-opt-in did not clear the opt-out: $still_opted"; fi

mout2="$(python3 "$MATERIALIZE" --departments-dir "$DEPTS_DIR" --build-state-file "$STATE" --json 2>/dev/null)"
missing2="$(echo "$mout2" | jq -r '.missing_before // [] | join(",")')"
if echo ",$missing2," | grep -q ",billing-finance,"; then
  ok "reversibility proven end-to-end: after re-opt-in, provisioning now WOULD scaffold billing-finance again: $missing2"
else
  bad "after re-opt-in, billing-finance should be eligible for scaffolding again, got: $missing2"
fi

# ── Test (d): GUARD — no department is ever removed without the warning
#    being surfaced, even against a decision written OUTSIDE record-dept-
#    decision.sh's own gate (correct provenance, but no lossWarningAck) ────
seed_state
python3 - "$STATE" <<'PYEOF'
import json, sys
p = sys.argv[1]
s = json.load(open(p))
# Hand-craft a bypass: a FLOOR department declined with full provenance but
# WITHOUT ever going through record-dept-decision.sh's --confirm-loss gate
# (no lossWarningAck field at all) — exactly what a rogue/alternate writer
# could produce.
s["canonicalReconciliation"]["decisions"]["marketing"] = {
    "decision": "no", "source": "owner-interview",
    "decidedAt": "2026-07-16T00:00:00Z", "decidedBy": "owner123", "sessionId": "s1",
}
json.dump(s, open(p, "w"))
PYEOF

grc=1
gout="$(python3 "$SYNC" --state "$STATE" --out "$OUT" --json 2>/dev/null)"; grc=$?
if [ "$grc" -eq 1 ]; then ok "sync exits 1 (anomaly) when a floor decline bypasses the warning gate"; else bad "expected exit 1 for an unconfirmed floor decline, got $grc"; fi

marketing_honored="$(echo "$gout" | jq -r '.optedOut["marketing"] // "ABSENT"')"
if [ "$marketing_honored" = "ABSENT" ]; then ok "the bypassing decline is NEVER honored as an opt-out in the artifact"; else bad "bypass decline was wrongly honored: $marketing_honored"; fi

unconf_dept="$(echo "$gout" | jq -r '.unconfirmed[0].department // "NONE"')"
unconf_reason="$(echo "$gout" | jq -r '.unconfirmed[0].reason // ""')"
if [ "$unconf_dept" = "marketing" ]; then ok "the anomaly is NAMED (department=marketing), never silently dropped"; else bad "unconfirmed anomaly not surfaced for marketing (got '$unconf_dept')"; fi
if echo "$unconf_reason" | grep -qi "lossWarningAck"; then ok "the reason names the missing confirmation: '$unconf_reason'"; else bad "reason does not explain the missing confirmation: '$unconf_reason'"; fi

# SCOPE BOUNDARY (documented honestly, not swept under the rug): this guard
# protects the OPT-OUT ARTIFACT (department-optout.json) — the contract U110
# / any CC settings surface is meant to read — and that artifact never
# honors the bypass (the three checks just above). It does NOT retroactively
# change department-floor.py's own declined_set(), which is a separate,
# already-shipped, provenance-only mechanism this unit does not touch (out
# of scope; department-floor.py's floor semantics are U109's lane, not
# U108's). So a consumer reading department-floor.py DIRECTLY (bypassing the
# artifact this unit ships) still treats the bypass decline as declined —
# prove that this is the case, so the residual gap is documented by a
# passing assertion instead of silently assumed.
gmout="$(python3 "$MATERIALIZE" --departments-dir "$DEPTS_DIR" --build-state-file "$STATE" --json 2>/dev/null)"
gmissing="$(echo "$gmout" | jq -r '.missing_before // [] | join(",")')"
if echo ",$gmissing," | grep -q ",marketing,"; then
  bad "unexpected: department-floor.py should still honor the bypass decline (documented scope boundary), but flagged marketing missing: $gmissing"
else
  ok "documented scope boundary confirmed: department-floor.py (untouched by this unit) still honors the bypass by provenance alone ($gmissing) — exactly why department-optout.json (this unit's artifact) is the consumer contract U110/CC must read, never raw canonicalReconciliation.decisions"
fi

# ── Non-floor sanity: a custom / non-floor decline needs no confirmation ───
# (customKeeps registers 'my-custom-lab' as a known recorded-custom id so
# record-dept-decision.sh's own dept-id validation accepts it — mirrors
# test-opt-out-loss-warning.sh's identical seeding for the same scenario.)
cat > "$STATE" <<'JSON'
{
  "canonicalReconciliation": {
    "customKeeps": ["my-custom-lab"],
    "decisions": {}
  }
}
JSON
bash "$RECORDER" --dept my-custom-lab --decision no \
  --source owner-interview --by owner123 --session s1 --state "$STATE" >/dev/null 2>&1
nout="$(python3 "$SYNC" --state "$STATE" --out "$OUT" --json 2>/dev/null)"; nrc=$?
if [ "$nrc" -eq 0 ]; then ok "non-floor decline syncs cleanly with no unconfirmed anomaly (exit 0)"; else bad "non-floor decline unexpectedly produced rc=$nrc"; fi
# NOTE: jq's `//` alternative operator treats `false` as falsy too (not just
# null/absent) — using it on a boolean field would misreport a real `false`
# as "MISSING". Use `has` + explicit tostring instead.
ncust="$(echo "$nout" | jq -r 'if (.optedOut | has("my-custom-lab")) then (.optedOut["my-custom-lab"].lossWarningShown | tostring) else "MISSING" end')"
if [ "$ncust" = "false" ]; then ok "non-floor opt-out correctly shows lossWarningShown=false (nothing guaranteed to lose)"; else bad "non-floor lossWarningShown unexpected: $ncust"; fi

echo ""
echo "── test-department-optout-sync: $PASS passed, $FAIL failed ──"
[ "$FAIL" -eq 0 ] || exit 1
