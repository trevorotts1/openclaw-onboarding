#!/usr/bin/env bash
# prove-handover.sh — receipt-backed HANDOVER gate (Bulletproofing d).
#
# WHY THIS EXISTS: before a box is handed to a client it must be PROVABLY
# complete-and-correct — not merely "at least the floor". Every existing gate
# checks the floor is present (under-provision guard) but NONE fails on
# OVER-provisioning (a provenance-declined department that was built anyway — the
# residual over-provision bug). This gate composes the receipt-backed equality invariant
# with the on-disk floor prover into ONE fail-closed handover check.
#
# It asserts, in order, and FAILS (non-zero) on the first that does not hold:
#   1. department-floor.py rc==0        — the mandatory + universal-primary floor
#                                          (minus declines) is present ON DISK.
#   2. provisioning-receipt.json exists — a receipt-less box is NOT handover-ready
#                                          (fail-closed; older boxes must rebuild).
#   3. receipt.equalityOk == true       — built set == expected set at build time
#                                          (no over- or under-provision).
#   4. receipt.declinedButBuilt empty   — no declined dept was built.
#   5. receipt.missingFromBuilt empty   — no expected dept was dropped.
#   6. no declined dept present ON DISK  — re-verified live (catches drift since build).
#
# Optional: with `--local <oc-root>` it ALSO runs prove-zhe.py --local (the four
# ZHE wrappings + the receipt-equality check) so the handover verdict is the full
# picture. Absent prove-zhe is a WARN, not a failure of this gate.
#
# USAGE
#   prove-handover.sh                       # gate the active company on this box
#   prove-handover.sh --receipt <path>      # gate a specific receipt file
#   prove-handover.sh --local <oc-root>     # also run prove-zhe.py --local <oc-root>
#
# EXIT CODES
#   0  handover-ready (all assertions hold)
#   3  NOT handover-ready (an assertion failed — see stderr)
#   7  cannot resolve the box (no departments dir / no receipt to gate)
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECEIPT_OVERRIDE=""
LOCAL_OC_ROOT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --receipt) RECEIPT_OVERRIDE="$2"; shift 2 ;;
    --local)   LOCAL_OC_ROOT="$2"; shift 2 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 1 ;;
  esac
done

fail() { echo "HANDOVER: NOT READY — $*" >&2; exit 3; }

# ── 1. On-disk floor prover (department-floor.py rc==0) ───────────────────────
FLOOR_JSON="$(python3 "$SCRIPT_DIR/department-floor.py" --json 2>/dev/null || true)"
FLOOR_RC=$(printf '%s' "$FLOOR_JSON" | python3 -c 'import sys,json;
try: print(json.load(sys.stdin).get("rc", 99))
except Exception: print(99)' 2>/dev/null || echo 99)
if [ "$FLOOR_RC" = "7" ]; then
  echo "HANDOVER: cannot resolve departments dir on disk (department-floor rc=7)" >&2
  exit 7
fi
if [ "$FLOOR_RC" != "0" ]; then
  fail "on-disk floor NOT met (department-floor.py rc=$FLOOR_RC). Run the build to completion first."
fi
DEPTS_DIR="$(printf '%s' "$FLOOR_JSON" | python3 -c 'import sys,json;
print(json.load(sys.stdin).get("departments_dir") or "")' 2>/dev/null || echo "")"
echo "HANDOVER: [1/6] on-disk floor MET (department-floor.py rc=0)"

# ── 2. Locate the provisioning receipt (fail-closed if absent) ────────────────
RECEIPT=""
if [ -n "$RECEIPT_OVERRIDE" ]; then
  RECEIPT="$RECEIPT_OVERRIDE"
else
  CANDIDATES=()
  [ -n "$DEPTS_DIR" ] && CANDIDATES+=("$(dirname "$DEPTS_DIR")/provisioning-receipt.json")
  if [ -d /data/.openclaw/workspace ]; then
    CANDIDATES+=("/data/.openclaw/workspace/provisioning-receipt.json")
  fi
  CANDIDATES+=("$HOME/.openclaw/workspace/provisioning-receipt.json")
  for c in "${CANDIDATES[@]}"; do
    if [ -f "$c" ]; then RECEIPT="$c"; break; fi
  done
fi
if [ -z "$RECEIPT" ] || [ ! -f "$RECEIPT" ]; then
  echo "HANDOVER: NOT READY — no provisioning-receipt.json found (searched near the" >&2
  echo "          departments dir + workspace roots). A box without a receipt is not" >&2
  echo "          provably complete; re-run build-workforce to emit one." >&2
  exit 7
fi
echo "HANDOVER: [2/6] provisioning receipt found -> $RECEIPT"

# ── 3-6. Assert the receipt's equality invariant + live over-build re-verify ──
VERDICT="$(python3 - "$RECEIPT" "$DEPTS_DIR" <<'PYV'
import sys, os, json, re
receipt_path, depts_dir = sys.argv[1], sys.argv[2]
norm = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())
try:
    rec = json.load(open(receipt_path))
except Exception as e:
    print("RECEIPT_UNPARSEABLE " + str(e)); sys.exit(0)
problems = []
if not bool(rec.get("equalityOk")):
    problems.append("equalityOk=false (" + str(rec.get("reason")) + ")")
if rec.get("declinedButBuilt"):
    problems.append("declined depts built: " + ", ".join(rec["declinedButBuilt"]))
if rec.get("missingFromBuilt"):
    problems.append("expected depts missing: " + ", ".join(rec["missingFromBuilt"]))
# Live re-verify: no provenance-declined dept may be present on disk right now.
declined = {norm(x) for x in (rec.get("declined") or [])}
if depts_dir and os.path.isdir(depts_dir) and declined:
    on_disk = {norm(n) for n in os.listdir(depts_dir)
               if os.path.isdir(os.path.join(depts_dir, n))
               and not n.startswith((".", "_"))}
    over = sorted(on_disk & declined)
    if over:
        problems.append("declined dept(s) present on disk NOW: " + ", ".join(over))
if problems:
    print("FAIL " + " | ".join(problems))
else:
    print("OK expected=%s built=%s" % (rec.get("expectedCount"), rec.get("builtCount")))
PYV
)"
case "$VERDICT" in
  OK*)  echo "HANDOVER: [3-6/6] receipt equality invariant holds ($VERDICT)" ;;
  *)    fail "receipt equality invariant broken -> ${VERDICT#FAIL }" ;;
esac

# ── Optional: full ZHE prover ─────────────────────────────────────────────────
if [ -n "$LOCAL_OC_ROOT" ]; then
  if [ -f "$SCRIPT_DIR/prove-zhe.py" ]; then
    echo "HANDOVER: running prove-zhe.py --local $LOCAL_OC_ROOT ..."
    if python3 "$SCRIPT_DIR/prove-zhe.py" --local "$LOCAL_OC_ROOT"; then
      echo "HANDOVER: prove-zhe PASS"
    else
      fail "prove-zhe.py reported the box is not ZHE-complete (see its output above)."
    fi
  else
    echo "HANDOVER: WARN prove-zhe.py not present; skipping full ZHE prover." >&2
  fi
fi

echo "HANDOVER: READY — box is provably complete-and-correct (floor met + expected-set equality + no over-build)."
exit 0
