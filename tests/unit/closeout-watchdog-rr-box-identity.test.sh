#!/usr/bin/env bash
# tests/unit/closeout-watchdog-rr-box-identity.test.sh
#
# D17: closeout-readiness-watchdog.sh posted its Rescue Rangers escalation with no box
# identity, so the RR-01 intake rejected every one as invalid_payload "unresolvable box"
# (Lyric Hawkins, every weekly escalation since Sep 6). The post must carry the canonical
# fleet slug as boxName/box plus a non-empty message, and with no slug it must NOT post.
#
# HERMETIC: a COPY of the watchdog runs in a private sandbox with a fake `curl` that
# records the -d body. No network, no real ~/.openclaw.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WATCHDOG="$REPO_ROOT/23-ai-workforce-blueprint/scripts/closeout-readiness-watchdog.sh"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== closeout-watchdog-rr-box-identity.test.sh ==="
[[ -f "$WATCHDOG" ]] || { echo "FAIL: missing $WATCHDOG"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "FAIL: python3 required"; exit 1; }

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX" 2>/dev/null || true' EXIT

T48="$(python3 -c "
from datetime import datetime, timedelta, timezone
print((datetime.now(timezone.utc) - timedelta(hours=48)).strftime('%Y-%m-%dT%H:%M:%SZ'))")"

# All departments done, SOP library failed, buildCompletedAt empty -> a stuck class fires.
_run_box() {  # $1 = name, rest = extra env (e.g. FLEET_STANDING_BOX_SLUG=x)
  local name="$1"; shift
  local h="$SANDBOX/$name"
  local skill="$h/.openclaw/skills/23-ai-workforce-blueprint/scripts"
  mkdir -p "$skill" "$h/.openclaw/workspace" "$h/bin"
  cp "$WATCHDOG" "$skill/closeout-readiness-watchdog.sh"
  cat > "$h/bin/curl" <<'SHIM'
#!/usr/bin/env bash
# record the -d body; print nothing
while [[ $# -gt 0 ]]; do
  if [[ "$1" == "-d" ]]; then printf '%s' "$2" > "$FAKE_CURL_BODY"; fi
  shift
done
exit 0
SHIM
  chmod +x "$h/bin/curl"
  cat > "$h/.openclaw/workspace/.workforce-build-state.json" <<STATE
{"interviewComplete": true, "interviewQc": {"status": "pass"}, "companyName": "Fixture Co",
 "agentName": "FixtureOrchestrator", "closeoutStatus": "pending", "roleLibraryStatus": "done",
 "sopLibraryStatus": "failed", "commsAutomationStatus": "not-applicable", "resumeAttempts": 0,
 "maxResumeAttempts": 12, "interviewCompletedAt": "$T48",
 "interviewProgress": {"lastQuestionAt": "$T48"},
 "departments": [{"id": "alpha", "status": "done", "completedAt": "$T48"}]}
STATE
  env -i PATH="$h/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin" HOME="$h" \
    OC_ROOT="$h/.openclaw" ZHC_STATE_FILE="$h/.openclaw/workspace/.workforce-build-state.json" \
    RESCUE_RANGERS_WEBHOOK_URL="http://127.0.0.1:9/webhook/rr-v2-intake" \
    FAKE_CURL_BODY="$h/body.json" "$@" \
    bash "$skill/closeout-readiness-watchdog.sh" --local >"$h/run.out" 2>&1
  return 0
}

echo "--- with a fleet slug: the intake's required fields are present ---"
_run_box with-slug FLEET_STANDING_BOX_SLUG=lyric-hawkins
B="$SANDBOX/with-slug/body.json"
if [[ -s "$B" ]]; then
  pass "1a: an escalation was POSTed to the webhook"
  if python3 - "$B" <<'PY'
import json, sys
p = json.load(open(sys.argv[1]))
sys.exit(0 if p.get("action") == "escalate"
         and p.get("boxName") == "lyric-hawkins" and p.get("box") == "lyric-hawkins"
         and str(p.get("message") or "").strip() else 1)
PY
  then pass "1b: payload carries boxName/box=<slug> and a non-empty message"
  else fail "1b: payload is missing boxName/box or message: $(cat "$B")"; fi
else
  fail "1a: no POST captured: $(tail -5 "$SANDBOX/with-slug/run.out")"
fi

echo "--- with no slug: nothing the intake can accept is posted ---"
_run_box no-slug
if [[ -s "$SANDBOX/no-slug/body.json" ]]; then
  fail "2a: posted a payload with no box identity"
else
  pass "2a: no POST without a box slug"
fi
if grep -q "FLEET_STANDING_BOX_SLUG is not set" "$SANDBOX/no-slug/run.out" "$SANDBOX/no-slug/.openclaw/workspace/.closeout-watchdog.log" 2>/dev/null; then
  pass "2b: the skipped escalation is logged loudly"
else
  fail "2b: the skip was silent"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
(( FAIL == 0 )) || { echo "FAIL: $FAIL check(s) failed"; exit 1; }
echo "PASS: closeout-watchdog-rr-box-identity"
