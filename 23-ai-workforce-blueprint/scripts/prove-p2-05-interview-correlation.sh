#!/usr/bin/env bash
# prove-p2-05-interview-correlation.sh — the ONE standing gate for P2-05
# (AI Workforce Interview → departments correlation, SUPER-SPEC-2026-07-11 §P2-05).
#
# WHY THIS EXISTS:
# P2-05's three parts (opt-out loss warnings, the net-new department path, and
# sub-floor verification) each ship their own fail-first suite. Sibling units
# P2-06/07/08 each contribute a single named gate the P6-01 per-box rollout probe
# runs to confirm the fix is LIVE (not merely merged). P2-05 had no such single
# aggregate gate. This is it: one command that
#   (1) runs all three P2-05 fail-first suites and requires each to pass, AND
#   (2) re-runs the part-(e) BREAK-IT battery as deterministic probes with the
#       exit codes quoted, so a regression in the sovereign-but-never-silent
#       opt-out contract, the force-a-floor-dept-as-net-new guard, or the
#       can't-silently-shrink-the-floor rule is caught at the gate.
#
# It exercises the REAL modules (record-dept-decision.sh, net-new-department.py,
# department-loss-warning.py, canonical_decline.py) end to end — no mocks — so if
# any P2-05 component regresses, this gate FAILS. Suitable both as a repo CI gate
# and as a per-box P6-01 probe (add-only; read-only against a temp workspace).
#
# EXIT 0 = every suite passed and every break-it probe held. Non-zero = a
# regression (the failing check is printed).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECORDER="$SCRIPT_DIR/record-dept-decision.sh"
NETNEW="$SCRIPT_DIR/net-new-department.py"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

command -v jq >/dev/null 2>&1 || { echo "SKIP: jq not on PATH (P2-05 gate needs jq for the recorder)"; exit 0; }

echo "═════════════════════════════════════════════════════════════════════"
echo "P2-05 GATE — interview → departments correlation"
echo "═════════════════════════════════════════════════════════════════════"

# ── PART 1: the three P2-05 fail-first suites must each pass ──────────────────
echo ""
echo "── Part 1: P2-05 component suites ──"
for suite in test-opt-out-loss-warning.sh test-net-new-department.sh test-sub-floor-build.sh; do
  sp="$SCRIPT_DIR/$suite"
  if [ ! -f "$sp" ]; then bad "$suite MISSING (P2-05 component suite not present)"; continue; fi
  if bash "$sp" >/dev/null 2>&1; then
    ok "$suite passed (rc=0)"
  else
    bad "$suite FAILED — run it directly for the failing case: bash $sp"
  fi
done

# ── PART 2: the part-(e) break-it battery (deterministic, exit codes quoted) ──
echo ""
echo "── Part 2: P2-05 break-it battery ──"

# E1 — FORCE a floor/vertical department as a net-new department must be
# structurally impossible. Minting 'listings' (the real-estate vertical dept) as
# a brand-new department is exactly the "don't force real estate" violation in
# reverse: the guard must REJECT it (exit 2), routing the need to the existing
# department instead of a phantom twin. Quote the exit code (part (e) requires it).
if [ -f "$NETNEW" ]; then
  set +e
  msg="$(python3 "$NETNEW" --name listings --check-only 2>&1 >/dev/null)"; e1=$?
  set -e
  if [ "$e1" -eq 2 ]; then
    ok "force-net-new 'listings' rejected — RULE 1 canonical/known duplicate (exit 2)"
  else
    bad "force-net-new 'listings' expected exit 2, got $e1 :: $msg"
  fi
  # And a genuinely new need is still accepted (exit 0) — the guard is not a blanket deny.
  set +e
  python3 "$NETNEW" --name "Investor Relations" --check-only >/dev/null 2>&1; e1b=$?
  set -e
  [ "$e1b" -eq 0 ] && ok "genuine net-new 'Investor Relations' still accepted (exit 0)" \
                    || bad "genuine net-new expected exit 0, got $e1b"
else
  bad "net-new-department.py MISSING at $NETNEW"
fi

# Shared temp workspace for the state-file probes (E2/E3).
TMPD="$(mktemp -d)"
trap 'rm -rf "$TMPD"' EXIT
STATE="$TMPD/.workforce-build-state.json"

# E2 — a MALFORMED decline must not silently shrink the floor. A bare,
# un-provenanced `decisions[<floor>] = "no"` (no decidedBy/source/decidedAt) is
# the exact shape that used to slip a floor department out silently. The shared
# reader canonical_decline.py must REJECT it: the dept stays in the floor and the
# drop is surfaced as a rejection, never honored.
cat > "$STATE" <<'JSON'
{
  "canonicalReconciliation": {
    "decisions": {
      "billing-finance": "no"
    }
  }
}
JSON
e2="$(python3 - "$SCRIPT_DIR" "$STATE" <<'PYEOF'
import sys, os, json, importlib.util
scripts_dir, state_path = sys.argv[1], sys.argv[2]
fp = os.path.join(scripts_dir, "canonical_decline.py")
spec = importlib.util.spec_from_file_location("canonical_decline", fp)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
bs = json.load(open(state_path))
res = mod.analyze(bs, quiet=True)
declined = res["declined"]
rejections = res["rejections"]
# billing-finance normalizes to 'billingfinance' — it must NOT be honored, and it
# MUST appear as a rejection (surfaced, never silent).
honored = mod.norm("billing-finance") in declined
was_rejected = any(mod.norm(r.get("id","")) == mod.norm("billing-finance") for r in rejections)
print("HONORED" if honored else ("REJECTED" if was_rejected else "DROPPED-SILENTLY"))
PYEOF
)"
case "$e2" in
  REJECTED) ok "malformed (un-provenanced) decline REJECTED — floor not shrunk, drop surfaced" ;;
  HONORED)  bad "malformed decline was HONORED — a floor dept can be silently dropped (regression)" ;;
  *)        bad "malformed decline neither honored nor surfaced ($e2) — silent drop (regression)" ;;
esac

# E3 — opt-out is SOVEREIGN but NEVER SILENT. Declining a floor department
# without --confirm-loss must exit 2 and write nothing (the owner must be shown
# the loss first); WITH --confirm-loss the confirmed decline is honored by
# canonical_decline.py. Both directions, quoted.
cat > "$STATE" <<'JSON'
{ "canonicalReconciliation": { "decisions": {} } }
JSON
set +e
e3msg="$(bash "$RECORDER" --dept billing-finance --decision no \
  --source owner-interview --by owner123 --session p2-05-gate --state "$STATE" 2>&1 >/dev/null)"; e3a=$?
set -e
written="$(jq -r '.canonicalReconciliation.decisions["billing-finance"] // "ABSENT"' "$STATE")"
if [ "$e3a" -eq 2 ] && [ "$written" = "ABSENT" ]; then
  ok "floor decline WITHOUT --confirm-loss refused (exit 2) and NOT written — never silent"
else
  bad "floor decline without --confirm-loss: expected exit 2 + no write, got exit $e3a written=$written"
fi
if echo "$e3msg" | grep -q "OPT-OUT WARNING"; then
  ok "the loss warning was echoed to the owner before the refusal"
else
  bad "loss warning not echoed on refusal"
fi

set +e
bash "$RECORDER" --dept billing-finance --decision no --confirm-loss \
  --source owner-interview --by owner123 --session p2-05-gate --state "$STATE" >/dev/null 2>&1; e3b=$?
set -e
honored="$(python3 - "$SCRIPT_DIR" "$STATE" <<'PYEOF'
import sys, os, json, importlib.util
scripts_dir, state_path = sys.argv[1], sys.argv[2]
fp = os.path.join(scripts_dir, "canonical_decline.py")
spec = importlib.util.spec_from_file_location("canonical_decline", fp)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
res = mod.analyze(json.load(open(state_path)), quiet=True)
print("HONORED" if mod.norm("billing-finance") in res["declined"] else "NOT-HONORED")
PYEOF
)"
if [ "$e3b" -eq 0 ] && [ "$honored" = "HONORED" ]; then
  ok "confirmed floor decline (--confirm-loss) exits 0 and is HONORED — opt-out is sovereign"
else
  bad "confirmed floor decline: expected exit 0 + honored, got exit $e3b honored=$honored"
fi

echo ""
echo "═════════════════════════════════════════════════════════════════════"
echo "── P2-05 gate: $PASS passed, $FAIL failed ──"
echo "═════════════════════════════════════════════════════════════════════"
[ "$FAIL" -eq 0 ] || exit 1
