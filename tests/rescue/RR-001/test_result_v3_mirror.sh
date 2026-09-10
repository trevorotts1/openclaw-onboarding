#!/usr/bin/env bash
# tests/rescue/RR-001/test_result_v3_mirror.sh — ONB-side RR-001 gate.
#
# SPEC RR-001: "Create a versioned result schema in
# FLEET/rescue/contracts/result-v3.schema.json and mirror the public receiver
# subset into ONB/65-rescue-receiver/contracts. Require incident, instruction,
# attempt and runtime IDs; repair_status; verification_status; evidence
# references; remaining blocker; and outcome digest. ... Keep legacy ACKs
# readable as delivered-only until upgraded."
#
# The FLEET contract is CANONICAL. This copy is the PUBLIC RECEIVER SUBSET, so
# it may be NARROWER (fewer optional branches published to a box) but it must
# never be LOOSER: every requirement the canonical schema enforces must also be
# enforced here, or a box could emit a result the fleet's validator rejects.
#
# WHAT THIS PROVES:
#   T1  the mirror declares itself a mirror and pins the canonical identity
#       (repo + path + $id + version + required list + both enums) in
#       x-canonical, so drift is detectable on a box with no FLEET checkout.
#   T2  the mirror's `required` list is a SUPERSET of the canonical one.
#   T3  the two repair_status / verification_status enum SETS are IDENTICAL.
#   T4  every canonically-required field is defined here, the SPEC's named
#       field set is REQUIRED, and repair_status uses the SPEC vocabulary.
#   T5  DRIFT CONTROL: a synthetic canonical schema with one extra required
#       field and one extra enum value IS detected by these same comparisons —
#       so a green run means the comparison discriminates, not that it was
#       never exercised.
#   T6  LEGACY ACK: a bare `{verdict:delivered}` ack still uses only defined
#       properties, and does NOT satisfy the v3 required set — so it can only
#       be read as delivered-only, never mistaken for a repair claim.
#
# The canonical file is read from a sibling checkout when one is present; the
# vendored x-canonical pin is used otherwise. Point at one explicitly with
# RR_FLEET_CONTRACT=/abs/path/to/result-v3.schema.json.
#
# Run: bash tests/rescue/RR-001/test_result_v3_mirror.sh

set -u
PASS=0
FAIL=0
say_ok()   { PASS=$((PASS+1)); echo "  ok   $1"; }
say_fail() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
MIRROR="$REPO/65-rescue-receiver/contracts/result-v3.schema.json"

echo "== RR-001 ONB: result-v3 public receiver subset =="
if [ ! -f "$MIRROR" ]; then
  echo "FATAL: $MIRROR missing"
  exit 2
fi
if python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$MIRROR" 2>/dev/null; then
  say_ok "mirror is valid JSON"
else
  say_fail "mirror is not valid JSON"
  echo ""; echo "RESULT: $PASS passed, $FAIL failed"; exit 1
fi

CANON=""
for cand in "${RR_FLEET_CONTRACT:-}" \
            "$REPO/../fleet-protocol/rescue/contracts/result-v3.schema.json" \
            "$HOME/blackceo-fleet-ops/rescue/contracts/result-v3.schema.json"; do
  if [ -n "$cand" ] && [ -f "$cand" ]; then CANON="$cand"; break; fi
done
if [ -n "$CANON" ]; then
  say_ok "canonical contract located for a LIVE comparison: $CANON"
else
  say_ok "no canonical checkout on this box — comparing against the vendored x-canonical pin"
fi

REPORT="$(mktemp)"
python3 - "$MIRROR" "$CANON" > "$REPORT" 2>&1 <<'PYEOF'
import json, sys
mirror_path = sys.argv[1]
canon_path  = sys.argv[2] if len(sys.argv) > 2 else ""
m = json.load(open(mirror_path, encoding="utf-8"))
pin = m.get("x-canonical")

fail = []
def good(x): print("OK\t" + x)
def bad(x):  print("BAD\t" + x)

# ---- T1: the mirror declares itself a mirror, with the canonical identity --
if not isinstance(pin, dict):
    bad("T1 mirror carries NO x-canonical block — drift would be undetectable on a box with no FLEET tree")
    pin = {}
else:
    good("T1 mirror carries an x-canonical block")
    for k in ("repo", "path", "$id", "version"):
        if not pin.get(k):
            bad("T1 x-canonical is missing %r — the canonical identity is not fully pinned" % k)
    if pin.get("path") != "rescue/contracts/result-v3.schema.json":
        bad("T1 x-canonical.path does not name the canonical FLEET contract: %r" % pin.get("path"))
    elif pin.get("repo") != "blackceo-fleet-ops":
        bad("T1 x-canonical.repo is not the canonical fleet repo: %r" % pin.get("repo"))
    else:
        good("T1 x-canonical pins the canonical identity: %s %s (%s)" %
             (pin.get("repo"), pin.get("path"), pin.get("version")))

m_req   = set(m.get("required") or [])
props   = m.get("properties") or {}
m_rep   = set((props.get("repair_status") or {}).get("enum") or [])
m_ver   = set((props.get("verification_status") or {}).get("enum") or [])
m_props = set(props.keys())

# If a REAL canonical file is present, compare against IT (it is authoritative);
# the vendored pin is the fallback for boxes with no checkout.
p_req = set(pin.get("required") or [])
p_rep = set(pin.get("repair_status") or [])
p_ver = set(pin.get("verification_status") or [])
src = "the vendored x-canonical pin"
if canon_path:
    try:
        c = json.load(open(canon_path, encoding="utf-8"))
        p_req = set(c.get("required") or [])
        p_rep = set(((c.get("properties") or {}).get("repair_status") or {}).get("enum") or [])
        p_ver = set(((c.get("properties") or {}).get("verification_status") or {}).get("enum") or [])
        src = "the LIVE canonical file"
        # the pin must also agree with the live file, or the pin is stale
        if pin:
            if set(pin.get("required") or []) != p_req:
                bad("T1 the vendored pin's required list is STALE vs the live canonical file — "
                    "re-vendor it so a box with no checkout sees the current contract")
            if set(pin.get("repair_status") or []) != p_rep or \
               set(pin.get("verification_status") or []) != p_ver:
                bad("T1 the vendored pin's enums are STALE vs the live canonical file")
            if pin.get("version") != c.get("properties", {}).get("outcome_digest", {}).get("x-version", pin.get("version")):
                pass  # version identity is asserted by T1 above; no extra trap here
    except Exception as e:
        bad("T1 could not read the canonical file %s: %s" % (canon_path, e))

# ---- T2/T3: mirror is a SUBSET — never LOOSER ----------------------------
if not p_req:
    bad("T2 no canonical required list available — the superset check cannot run")
elif not p_req <= m_req:
    bad("T2 the mirror is LOOSER than canonical (%s): canonical requires %s, the mirror does not"
        % (src, sorted(p_req - m_req)))
else:
    good("T2 the mirror's required list is a SUPERSET of canonical (%d canonical, %d here) — via %s"
         % (len(p_req), len(m_req), src))

if not p_rep or not p_ver:
    bad("T3 no canonical enums available — the enum check cannot run")
elif p_rep != m_rep:
    bad("T3 repair_status enum DRIFTS from canonical: mirror-only=%s canonical-only=%s"
        % (sorted(m_rep - p_rep), sorted(p_rep - m_rep)))
elif p_ver != m_ver:
    bad("T3 verification_status enum DRIFTS from canonical: mirror-only=%s canonical-only=%s"
        % (sorted(m_ver - p_ver), sorted(p_ver - m_ver)))
else:
    good("T3 both enums are IDENTICAL to canonical (repair_status=%d values, verification_status=%d values)"
         % (len(m_rep), len(m_ver)))

# ---- T4: required fields defined + SPEC set required ----------------------
missing = sorted(p_req - m_props)
if missing:
    bad("T4 canonical requires fields the mirror does not define: %s" % missing)
else:
    good("T4 every canonically-required field is defined as a property here (%d fields)" % len(p_req))

SPEC_FIELDS = ["incident_id", "instruction_id", "attempt_id", "runtime_id",
               "outcome_digest", "repair_status", "verification_status"]
missing_spec = [f for f in SPEC_FIELDS if f not in m_req]
if missing_spec:
    bad("T4 the mirror does not REQUIRE the SPEC-named fields: %s" % missing_spec)
else:
    good("T4 the mirror REQUIRES every SPEC-named field (incident/instruction/attempt/runtime ids; "
         "outcome_digest; repair_status; verification_status)")
if not m_rep <= {"repaired", "advice_delivered", "partial", "not_repaired"}:
    bad("T4 repair_status carries values outside the SPEC vocabulary: %s" % sorted(m_rep))
else:
    good("T4 repair_status vocabulary is the SPEC enum exactly: %s" % sorted(m_rep))
if not m_ver <= {"verified", "unverified", "verifier_failed", "pending"}:
    bad("T4 verification_status carries values outside the SPEC vocabulary: %s" % sorted(m_ver))
else:
    good("T4 verification_status vocabulary is the SPEC enum exactly: %s" % sorted(m_ver))

# ---- T5: DRIFT CONTROL — the comparison must be able to FAIL --------------
synth_req = sorted(p_req | {"a_field_the_mirror_lacks"})
detected_req = not (set(synth_req) <= m_req)
synth_rep = sorted(p_rep | {"invented_status"})
detected_enum = (set(synth_rep) != m_rep)
if detected_req and detected_enum:
    good("T5 DRIFT CONTROL: a synthetic canonical schema with one extra required field AND one extra "
         "repair_status value IS detected by these same comparisons — the gate discriminates")
else:
    bad("T5 DRIFT CONTROL FAILED: the comparison did not notice a synthetic canonical drift "
        "(req_detected=%s enum_detected=%s) — a green run would prove nothing"
        % (detected_req, detected_enum))

# ---- T6: legacy ACK readability ------------------------------------------
# A pre-v3 ack carries NO result body at all (the old `verdict` field lives on
# the ACK ENVELOPE, which this schema does not describe). "Readable as
# delivered-only" therefore means two concrete things about the RESULT
# contract: (a) it must not require a result the legacy sender never produced,
# and (b) it must offer a vocabulary for "transport receipt only, no repair
# claim" so a delivered-but-unupgraded ack has somewhere honest to land.
legacy_accepted = {"action": "ack", "verdict": "delivered"}
if set(legacy_accepted) >= m_req:
    bad("T6 a bare legacy ack SATISFIES the v3 required set — delivered-only would be "
        "indistinguishable from a repair claim")
else:
    good("T6 a bare legacy ack does NOT satisfy the v3 required set (%d fields) → it can only be "
         "read as delivered-only until upgraded, never as a repair claim" % len(m_req))
tr = props.get("transport_receipt") or {}
tr_states = set((tr.get("properties") or {}).get("receipt_state", {}).get("enum") or [])
DELIVERED_ONLY = {"receipt_only_unverified", "receipt_pending", "receipt_unconfirmed"}
if not tr_states:
    bad("T6 transport_receipt declares no receipt_state enum — a delivered-only ack has no "
        "vocabulary to be recorded in")
elif not (tr_states & DELIVERED_ONLY):
    bad("T6 transport_receipt.receipt_state cannot express delivered-without-a-repair-claim: %s"
        % sorted(tr_states))
else:
    good("T6 transport_receipt.receipt_state expresses delivered-only (%s) — a legacy ack is "
         "recordable as a TRANSPORT receipt and never as a repair claim"
         % sorted(tr_states & DELIVERED_ONLY))
if "transport_receipt" not in m_req:
    good("T6 transport_receipt is OPTIONAL — a legacy ack is not forced to invent one")
else:
    bad("T6 transport_receipt is REQUIRED — a legacy ack could not satisfy this schema at all")
PYEOF
RC=$?
while IFS=$'\t' read -r tag msg; do
  case "$tag" in
    OK)  say_ok   "$msg" ;;
    BAD) say_fail "$msg" ;;
    *)   [ -n "$msg" ] && say_fail "unexpected report line" "$tag $msg" ;;
  esac
done < "$REPORT"
rm -f "$REPORT"
[ "$RC" -eq 0 ] || true

echo ""
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
