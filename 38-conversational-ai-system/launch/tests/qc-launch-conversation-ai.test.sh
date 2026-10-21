#!/usr/bin/env bash
# qc-launch-conversation-ai.test.sh — synthetic-local regression for the launch
# Conversation-AI completion gate.
#
# Every mutation below is derived from fixtures/pass-full.json in a temp folder.
# Nothing touches a provider, a tenant, a phone, a mailbox or the network.
#
# Exit 0 = all assertions pass; 1 = a failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$SCRIPT_DIR/../qc-launch-conversation-ai.sh"
BASE="$SCRIPT_DIR/../fixtures/pass-full.json"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/ulaudit-UL-016-qc.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

PASS=0
FAIL=0

ok()  { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }

# run_gate <bundle> -> sets OUT (json), VERDICT, CODES (newline list)
run_gate() {
  OUT="$(bash "$GATE" --bundle "$1" --json 2>/dev/null)"
  VERDICT="$(printf '%s' "$OUT" | python3 -c "
import json,sys
try:
    print(json.load(sys.stdin)['verdict'])
except Exception:
    print('PARSE_ERROR')
" 2>/dev/null)"
  CODES="$(printf '%s' "$OUT" | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    codes=sorted({p['code'] for b in d['bundles'] for p in b['problems']})
    print('\n'.join(codes))
except Exception:
    print('PARSE_ERROR')
" 2>/dev/null)"
}

assert_verdict() {
  local expected="$1" label="$2"
  if [ "$VERDICT" = "$expected" ]; then
    ok "$label: verdict $expected"
  else
    bad "$label: expected $expected, got ${VERDICT:-<empty>}"
    printf '%s\n' "$OUT" | sed 's/^/        /'
  fi
}

assert_code() {
  local code="$1" label="$2"
  if printf '%s\n' "$CODES" | grep -qx "$code"; then
    ok "$label: reported $code"
  else
    bad "$label: expected $code, got $(printf '%s' "$CODES" | tr '\n' ' ')"
    printf '%s\n' "$OUT" | sed 's/^/        /'
  fi
}

# mutant <name> <python-expression-operating-on-m> -> path
mutant() {
  local name="$1"
  local code="$2"
  local path="$TMP/$name.json"
  python3 - "$BASE" "$path" "$code" <<'PYEOF'
import json
import sys

source, dest, code = sys.argv[1], sys.argv[2], sys.argv[3]
m = json.load(open(source))
exec(code)
with open(dest, "w") as handle:
    json.dump(m, handle, indent=2)
PYEOF
  printf '%s' "$path"
}

printf '=== qc-launch-conversation-ai.test.sh ===\n'
printf 'base fixture: %s\n\n' "$BASE"

# 1. The unmodified fixture passes.
run_gate "$BASE"
assert_verdict PASS "pass-full"
[ "$CODES" = "" ] && ok "pass-full: no problem codes" || bad "pass-full: unexpected codes $CODES"

# 2. Global registry hygiene alone never satisfies a playbook.
p="$(mutant global-evidence '
for e in m["evidence"]:
    if e["playbook"] == "checkout-playbook.md":
        e["scope"] = "global"
        e["global_registry_hygiene"] = True
')"
run_gate "$p"; assert_verdict FAIL "global-evidence"; assert_code EVIDENCE_GLOBAL "global-evidence"

# 3. Evidence for a different launch revision is not this launch's evidence.
p="$(mutant wrong-revision '
for e in m["evidence"]:
    e["launch_revision"] = 3
')"
run_gate "$p"; assert_verdict FAIL "wrong-revision"; assert_code EVIDENCE_TARGET "wrong-revision"

# 4. Evidence for another tenant is rejected.
p="$(mutant wrong-tenant '
for e in m["evidence"]:
    e["tenant_id"] = "tenant-other"
')"
run_gate "$p"; assert_verdict FAIL "wrong-tenant"; assert_code EVIDENCE_TARGET "wrong-tenant"

# 5. Playbook with no evidence at all.
p="$(mutant missing-evidence '
m["evidence"] = [e for e in m["evidence"] if e["playbook"] != "booking-playbook.md"]
')"
run_gate "$p"; assert_verdict FAIL "missing-evidence"; assert_code EVIDENCE_MISSING "missing-evidence"

# 6. Enrollment is required.
p="$(mutant missing-enrollment '
m["enrollment"]["contact_enrolled"] = False
')"
run_gate "$p"; assert_verdict FAIL "missing-enrollment"; assert_code ENROLLMENT "missing-enrollment"

# 7. Consent is required per channel.
p="$(mutant consent-revoked '
m["consent"]["sms"]["granted"] = False
')"
run_gate "$p"; assert_verdict FAIL "consent-revoked"; assert_code CONSENT "consent-revoked"

# 8. Per-offer knowledge must be versioned and complete.
p="$(mutant knowledge-incomplete '
del m["knowledge"][0]["version"]
del m["knowledge"][0]["payment_schedule"]
')"
run_gate "$p"; assert_verdict FAIL "knowledge-incomplete"; assert_code KNOWLEDGE "knowledge-incomplete"

# 9. Unknown handling must escalate and forbid invention.
p="$(mutant knowledge-unknown '
m["knowledge"][0]["unknown_policy"] = "guess"
m["knowledge"][0]["invention_guard"] = False
')"
run_gate "$p"; assert_verdict FAIL "knowledge-unknown"
assert_code KNOWLEDGE_UNKNOWN "knowledge-unknown"
assert_code KNOWLEDGE_INVENTION "knowledge-unknown"

# 10. Human fallback must be bounded and owned.
p="$(mutant fallback-unbounded '
m["human_fallback"]["bounded"] = False
m["human_fallback"]["max_turns"] = 40
m["human_fallback"]["owner"] = ""
')"
run_gate "$p"; assert_verdict FAIL "fallback-unbounded"; assert_code FALLBACK "fallback-unbounded"

# 11. A native reply owner needs the approved prompt/knowledge translation.
p="$(mutant native-unapproved '
m["reply_owner"] = {"kind": "native_ghl"}
')"
run_gate "$p"; assert_verdict FAIL "native-unapproved"; assert_code REPLY_OWNER_TRANSLATION "native-unapproved"

# 12. Mode-specific adapters are required (full needs faq+booking+checkout).
p="$(mutant adapter-missing '
del m["adapters"]["booking"]
')"
run_gate "$p"; assert_verdict FAIL "adapter-missing"; assert_code ADAPTER_MISSING "adapter-missing"

# 13. The mode matrix is enforced.
p="$(mutant mode-none '
m["mode"] = "none"
')"
run_gate "$p"; assert_verdict FAIL "mode-none"; assert_code MODE "mode-none"

# 14. Thirty buyer questions are the floor.
p="$(mutant probes-short '
m["qa_probes"] = m["qa_probes"][:29]
')"
run_gate "$p"; assert_verdict FAIL "probes-short"; assert_code PROBES_COUNT "probes-short"

# 15. An injection probe may never be obeyed.
p="$(mutant injection-obeyed '
for p in m["qa_probes"]:
    if p["category"] == "injection":
        p["outcome"] = "grounded"
        p["grounded_ref"] = "system.prompt"
')"
run_gate "$p"; assert_verdict FAIL "injection-obeyed"; assert_code PROBE_INJECTION "injection-obeyed"

# 16. A divergent price must escalate.
p="$(mutant price-change-grounded '
for p in m["qa_probes"]:
    if p["category"] == "price_change" and p["reported_price_matches_plan"] is False:
        p["outcome"] = "grounded"
        p["grounded_ref"] = "offer.price_usd"
')"
run_gate "$p"; assert_verdict FAIL "price-change-grounded"; assert_code PROBE_PRICE_CHANGE "price-change-grounded"

# 17. State must stay namespaced to this tenant/location/launch.
p="$(mutant state-foreign '
m["state"]["namespace"] = "launch-ai/tenant-other/loc-other/launch-other/"
m["state"]["sample_key"] = "launch-ai/tenant-other/loc-other/launch-other/contact-001"
')"
run_gate "$p"; assert_verdict FAIL "state-foreign"; assert_code STATE_NAMESPACE "state-foreign"

# 18. Two launches plus unrelated support stay isolated.
p="$(mutant false-booking-success '
m["isolation"]["false_booking_success"] = True
')"
run_gate "$p"; assert_verdict FAIL "false-booking-success"; assert_code FALSE_BOOKING_SUCCESS "false-booking-success"

# 19. This lane never produces a live effect.
p="$(mutant live-effects '
m["live_effects"] = ["sms.send"]
')"
run_gate "$p"; assert_verdict FAIL "live-effects"; assert_code LIVE_EFFECTS "live-effects"

# 20. Staging without a separately authorized account is blocked, never faked.
p="$(mutant staging-bypass '
m["staging"]["result"] = "pass"
')"
run_gate "$p"; assert_verdict FAIL "staging-bypass"; assert_code STAGING_BYPASS "staging-bypass"

# 21. A failed booking outcome never passes — regression for the shipped defect.
p="$(mutant booking-failed '
m["scenarios"]["booking_success"]["outcome"] = "failed"
')"
run_gate "$p"; assert_verdict FAIL "booking-failed"; assert_code SCENARIO_OUTCOME "booking-failed"

# 22. Free-text outcomes are rejected even when nonempty.
p="$(mutant booking-prose '
m["scenarios"]["booking_success"]["outcome"] = "synthetic appointment created on a free slot"
')"
run_gate "$p"; assert_verdict FAIL "booking-prose"; assert_code SCENARIO_OUTCOME "booking-prose"

# 23. A scenario trace must point at this bundle's targeted evidence.
p="$(mutant scenario-dangling-ref '
m["scenarios"]["booking_success"]["evidence_ref"] = "sha256:no-such-digest"
')"
run_gate "$p"; assert_verdict FAIL "scenario-dangling-ref"; assert_code SCENARIO_EVIDENCE "scenario-dangling-ref"

# 24. --dir scans every bundle and fails if any one is incomplete.
mkdir -p "$TMP/dirscan"
cp "$BASE" "$TMP/dirscan/pass-a.json"
cp "$TMP/live-effects.json" "$TMP/dirscan/fail-b.json"
DIR_OUT="$(bash "$GATE" --dir "$TMP/dirscan" --json 2>/dev/null)"
DIR_VERDICT="$(printf '%s' "$DIR_OUT" | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])" 2>/dev/null)"
[ "$DIR_VERDICT" = "FAIL" ] && ok "--dir: any failing bundle fails the run" || bad "--dir: expected FAIL, got '${DIR_VERDICT:-<empty>}'"

# 25. A malformed bundle is a loud failure, not a pass.
printf '{not json' > "$TMP/malformed.json"
run_gate "$TMP/malformed.json"
assert_verdict FAIL "malformed"; assert_code IO "malformed"

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
