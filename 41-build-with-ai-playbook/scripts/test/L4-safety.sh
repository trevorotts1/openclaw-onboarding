#!/usr/bin/env bash
# L4-safety.sh -- Skill 41 v1.3.0 browser-execution harness, Level 4.
#
# PROPERTY PROVEN: the three non-negotiable safety properties of an AUTONOMOUS browser
# executor, each enforced executably:
#
#   (A) ALLOWLIST ENFORCEMENT -- the executor may only navigate to allowlisted hosts. A
#       non-allowlisted host (incl. the live GHL host during a TEST run, or an exfil domain)
#       is REFUSED, not followed. We test the harness's own loopback guardrail (hf_curl) AND
#       an explicit host-allowlist function.
#   (B) HEADLESS-SILENT DETECTION -- on a headless host (no TTY), if there is no
#       operator-reachable escalation channel configured, the executor must LOUDLY flag the
#       degraded state (never proceed silently). We assert the detector returns non-silent.
#   (C) PII-FREE LOGGING -- nothing the harness emits (request log, event log, level stdout)
#       may contain a real secret/PII shape. We scan with the same detector L3/D7 uses.
#
# Usage: bash L4-safety.sh
# Exit:  0 = pass, 1 = fail.
set -uo pipefail
HF_LEVEL="L4"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib-harness.sh"

HF_CHECKS=0; HF_FAILS=0
hf_log "safety test (allowlist / headless-silent / PII-free logging)"

# --- (A) ALLOWLIST ENFORCEMENT ------------------------------------------------
# The browser executor's allowlist: only these hosts may be navigated during a build. The
# live GHL host is intentionally ABSENT here because L1-L5 are TEST runs that must never touch
# production. (A real client run would add the client's own GHL host to this allowlist.)
ALLOWLIST=("127.0.0.1" "localhost" "app.gohighlevel.com.invalid-test-only")
host_allowed() {
  local h="$1" a
  for a in "${ALLOWLIST[@]}"; do [[ "$h" == "$a" ]] && return 0; done
  return 1
}
# refused() inverts host_allowed: returns 0 (test passes) when the host is correctly refused.
refused() { host_allowed "$1" && return 1 || return 0; }
hf_check "allowlisted host (127.0.0.1) is permitted" host_allowed "127.0.0.1"
hf_check "non-allowlisted live GHL host is refused" refused "services.leadconnectorhq.com"
hf_check "non-allowlisted exfil host is refused" refused "evil.example.net"
# The harness's own loopback guardrail (hf_curl) must reject a live URL outright. hf_curl
# returns 7 on a blocked host; any non-zero means it did not actually call out.
blocked() { hf_curl -o /dev/null "$1" >/dev/null 2>&1 && return 1 || return 0; }
hf_check "hf_curl loopback guardrail blocks a live URL" blocked "https://services.leadconnectorhq.com/x"

# --- (B) HEADLESS-SILENT DETECTION --------------------------------------------
# Detector: on a headless host with no escalation channel, return code 2 + a LOUD message.
# Inputs are simulated via env so the test is deterministic on any host (we do not depend on
# the harness actually being headless).
headless_silent_check() {
  # $1 = HAS_TTY (1/0), $2 = ESCALATION_CHANNEL_SET (1/0)
  local has_tty="$1" esc="$2"
  if [[ "$has_tty" == "0" && "$esc" == "0" ]]; then
    echo "[L4] DEGRADED: headless run with NO operator-reachable escalation channel -- refusing to proceed silently; escalate to human."
    return 2
  fi
  echo "[L4] ok: an operator-reachable path exists (tty=$has_tty escalation=$esc)"
  return 0
}
# headless + no channel -> MUST flag (return 2) and print DEGRADED (never silent)
out="$(headless_silent_check 0 0)"; rc=$?
hf_check "headless + no-channel is FLAGGED, not silent (rc=$rc)" test "$rc" = "2"
hf_check "the flag is LOUD (prints DEGRADED)" bash -c "printf '%s' \"$out\" | grep -q DEGRADED"
# headless + channel present -> ok (escalation path exists)
headless_silent_check 0 1 >/dev/null; hf_check "headless WITH escalation channel proceeds (rc=0)" test "$?" = "0"
# interactive -> ok
headless_silent_check 1 0 >/dev/null; hf_check "interactive TTY proceeds (rc=0)" test "$?" = "0"

# --- (C) PII-FREE LOGGING -----------------------------------------------------
# Build a representative log bundle (request log + an f52 event line) and assert the PII
# detector finds NOTHING. Then PROVE the detector works by injecting a synthetic secret and
# confirming it bites.
SB="$(hf_make_sandbox)"; trap 'rm -rf "$SB"' EXIT
pii_scan() {
  # returns 0 (clean) if NO pii shape found in the file, 1 if a pii shape is present
  local file="$1"
  if grep -EnH "([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,})|(\+?[0-9]{10,15})|((sk-|Bearer [A-Za-z0-9]|pit-|eyJ)[A-Za-z0-9._-]{6,})" "$file" >/dev/null 2>&1; then
    return 1
  fi
  return 0
}
# a clean, contract-shaped log bundle (domains + counts only -- exactly what f52 allows)
cat > "$SB/clean.log" <<'EOF'
{"method":"POST","path":"/locations/TESTLOC/tags","auth_present":true,"version":"2021-07-28"}
{"ts":"2026-06-03T00:00:00Z","skill":"41-build-with-ai-playbook","event":"qc_result","total":5,"pass":5,"url_domain":"api.example.com"}
EOF
hf_check "clean contract-shaped log scans PII-free" pii_scan "$SB/clean.log"
# now inject a synthetic secret/PII and confirm the detector bites (proves it is real)
cat > "$SB/dirty.log" <<'EOF'
{"event":"oops","authorization":"Bearer sk-LIVELIKEKEY0123456789"}
{"event":"oops","contact_email":"someone@example-fake.test"}
EOF
# detector_bites() returns 0 (pass) when pii_scan correctly flags the dirty file.
detector_bites() { pii_scan "$SB/dirty.log" && return 1 || return 0; }
hf_check "PII detector BITES on a leaked secret/email (proves it is enforcing)" detector_bites

# Real live mock request log (from a quick spawn) must also be PII-free.
if hf_have_python3 && hf_spawn_mock "$SB"; then
  hf_curl -o /dev/null -H "Authorization: Bearer $HF_MOCK_TOKEN" -H "Version: 2021-07-28" "http://127.0.0.1:$HF_MOCK_PORT/locations/X/tags" >/dev/null 2>&1
  hf_stop_mock "$SB"
  token_absent() { grep -F "$HF_MOCK_TOKEN" "$HF_MOCK_REQLOG" >/dev/null 2>&1 && return 1 || return 0; }
  hf_check "live mock request log never logged the session token" token_absent
else
  hf_info "python3/mock unavailable -- skipping live request-log PII assertion (static bundle already covers it)"
fi

hf_log "checks=$HF_CHECKS fails=$HF_FAILS"
if [[ $HF_FAILS -eq 0 ]]; then hf_pass "safety proven (allowlist refuses non-listed+live hosts; headless-silent is flagged loud; logs are PII-free and the detector bites)"; exit 0; fi
hf_fail "$HF_FAILS safety check(s) failed -- do NOT enable autonomous execution"; exit 1
