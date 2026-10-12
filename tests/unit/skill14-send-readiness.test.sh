#!/usr/bin/env bash
# skill14-send-readiness.test.sh (RRS001) -- the skill 14 TOOLS.md block must teach the
# Google service-account + domain-wide-delegation send path and a send-readiness check.
#
# THE LIVE BUG: the block taught only `gws auth login`. An agent that checked gws OAuth,
# found nothing, told an operator the box had no way to send email, while the working
# service-account path sat in a different agent's MEMORY.md. INSTALL.md also claimed that
# path "is documented in TOOLS.md", which was false for the block the skill ships.
# Hermetic: mktemp HOME, no network, no real gws.
set -uo pipefail
P="[skill14-send-readiness]"; PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "$P PASS: $*"; }
fail() { FAIL=$((FAIL+1)); echo "$P FAIL: $*" >&2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
S="$ROOT/14-google-workspace-integration"
BLOCK="$(awk '/^## TOOLS.md - UPDATE REQUIRED/{f=1;next} /^## MEMORY.md/{f=0} f' "$S/CORE_UPDATES.md")"

for needle in GOOGLE_APPLICATION_CREDENTIALS GCP_IMPERSONATE_USER "domain-wide delegation" "SEND READINESS CHECK" "credentials.enc"; do
  printf '%s' "$BLOCK" | grep -qiF "$needle" && pass "TOOLS.md block names: $needle" || fail "TOOLS.md block missing: $needle"
done
printf '%s' "$BLOCK" | grep -q "Do NOT run a bare \"gws auth status\"" && pass "block warns against a bare headless gws auth status" || fail "block does not carry the credential-wipe warning"
printf '%s' "$BLOCK" | grep -E '^[0-9]\. .*gws auth status' >/dev/null && fail "block TELLS the agent to run gws auth status" || pass "block never tells the agent to run gws auth status"
grep -q "This path is documented in TOOLS.md and is what" "$S/INSTALL.md" && fail "INSTALL.md still carries the false 'documented in TOOLS.md' line" || pass "INSTALL.md false claim corrected"
grep -q "SEND READINESS CHECK" "$S/INSTALL.md" && pass "INSTALL.md points at the real TOOLS.md block" || fail "INSTALL.md does not point at the block"

# QC gate behavior
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT; mkdir -p "$T/h/.config/gws"; echo '{}' > "$T/key.json"
qc() { env -u GOOGLE_APPLICATION_CREDENTIALS -u GCP_IMPERSONATE_USER -u GWS_ACCOUNT -u GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE HOME="$T/h" "$@" bash "$S/qc-google-workspace-integration.sh" </dev/null 2>&1 | grep -i "send path" | head -1; }
L="$(qc)";                                        [[ "$L" == *WARN* ]] && pass "gate WARNs with neither path" || fail "gate neither: '$L'"
L="$(qc GOOGLE_APPLICATION_CREDENTIALS=$T/key.json GCP_IMPERSONATE_USER=a@b.c)"; [[ "$L" == *PASS* ]] && pass "gate PASSes on service-account key + impersonated user" || fail "gate SA: '$L'"
L="$(qc GOOGLE_APPLICATION_CREDENTIALS=$T/key.json)";   [[ "$L" == *WARN* ]] && pass "gate WARNs on a key with no impersonated user" || fail "gate key-only: '$L'"
echo x > "$T/h/.config/gws/credentials.enc"
L="$(qc)";                                        [[ "$L" == *PASS* ]] && pass "gate PASSes on gws OAuth credentials alone" || fail "gate oauth: '$L'"
echo "$P Results: $PASS passed, $FAIL failed"; [ "$FAIL" -eq 0 ]
