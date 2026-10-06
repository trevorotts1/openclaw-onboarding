#!/usr/bin/env bash
# tests/unit/cc-company-id-registry-repair.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# THE DEFECT THIS LOCKS — the installer repaired the copy nobody reads.
#
# 32-command-center-setup/scripts/run-full-install.sh detects that the mirrored
# company id disagrees with the company owning the Command Center's workspaces,
# and repairs it. It repaired ONE copy: the MC_COMPANY_ID scalar in .env.local.
#
# The Command Center resolves a request's tenant through tenantRegistration()
# (src/lib/auth/tenant-context.ts), which reads the per-host `companyId` inside
# MC_TENANT_REGISTRY_JSON — NOT the scalar. interview-launch.py stamps that
# registry once from the launch state and then REFUSES to rebind a registered
# host, so the wrong value is sticky. Measured on a client box: six registered
# hosts all still carried `companyId: default` after an install that reported
# success, and the client's board rendered zero of their 40 departments.
#
# The second half of the defect: the repair ran on FULL installs only.
# --update-only warned and changed nothing, and a code-only roll is frequently
# the only thing that ever runs on a provisioned box again.
#
# ASSERTED HERE, against the SHIPPING function extracted VERBATIM from the real
# installer (no reimplementation):
#   1. both copies are repaired — scalar AND every registry host
#   2. it repairs on the --update-only path too (UPDATE_ONLY=true)
#   3. every OTHER assignment in .env.local survives byte-for-byte, including
#      the API token and session secret (never rotated, never echoed)
#   4. already-correct input produces NO write at all (idempotent)
#   5. an unparseable registry rewrites NOTHING and says so (fail closed, never
#      a half-repair that leaves the two copies disagreeing)
#   6. the file keeps mode 0600
#   7. MUTATION PROOF — a repair that writes only the scalar (the pre-fix
#      behaviour) must FAIL case 1, so a green run here is not vacuous
#
# Hermetic: stdlib python3 + bash only. No network, no box, no real credentials.
# bash 3.2-safe. Exit 0 = pass, 1 = fail.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RFI="$REPO_ROOT/32-command-center-setup/scripts/run-full-install.sh"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
eq()   { if [ "$1" = "$2" ]; then pass "$3"; else fail "$3 (got '$1' want '$2')"; fi; }

echo "=== cc-company-id-registry-repair.test.sh ==="
[ -f "$RFI" ] || { echo "  FAIL: installer not found: $RFI"; exit 1; }
[ -f "$REPO_ROOT/shared-utils/service_env.py" ] || { echo "  FAIL: service_env.py not found"; exit 1; }

WORK="$(mktemp -d -t cc-company-id-test-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

# ── verbatim extraction of the shipping function (brace-matched, col-0 "}") ──
extract_function() {
  awk -v fn="$1() {" '
    $0 == fn { p=1 }
    p { print }
    p && $0 == "}" { exit }
  ' "$RFI"
}

REPAIR="$(extract_function cc_repair_company_id)"
if [ -z "$REPAIR" ]; then
  echo "FATAL: 'cc_repair_company_id() {' not found verbatim in $RFI (drift?)"
  exit 2
fi
printf '%s\n' "$REPAIR" > "$WORK/repair.inc"
echo "Extracted cc_repair_company_id verbatim ($(grep -c '' "$WORK/repair.inc") lines) from $RFI"

# Minimal harness the extracted function expects: SKILL_DIR (for the shared
# service_env import), log(), and UPDATE_ONLY.
# SKILL_DIR is the SKILL directory (installer line 113: dirname/..), so the
# function's own "$SKILL_DIR/../shared-utils" resolves to the repo-root helper.
SKILL_DIR="$REPO_ROOT/32-command-center-setup"
log() { LOG_LINES="${LOG_LINES:-}$2"$'\n'; }
# shellcheck source=/dev/null
. "$WORK/repair.inc"

# ── fixture: the shape measured on the box, plus neighbours that must survive ─
TOKEN='tok-never-rotated-and-never-echoed'
SECRET='sess-never-rotated-and-never-echoed'
new_env() {
  local f="$1" scalar="$2" reg="$3"
  cat > "$f" <<ENVEOF
DATABASE_PATH=/opt/mission-control/mission-control.db
MC_API_TOKEN=$TOKEN
MC_TENANT_SESSION_SECRET=$SECRET
MC_COMPANY_ID=$scalar
MC_INSTALLATION_ID=install-abc
MC_TENANT_REGISTRY_JSON=$reg
MC_TENANT_PUBLIC_URL=https://board.example.test
ENVEOF
  chmod 600 "$f"
}

# Six registered hosts, every one of them stamped with the sentinel.
SIX_DEFAULT='{"a.example.test":{"kind":"self","tenantId":"self","companyId":"default","installationId":"install-abc"},"b.example.test":{"kind":"self","tenantId":"self","companyId":"default","installationId":"install-abc"},"c.example.test":{"kind":"self","tenantId":"self","companyId":"default","installationId":"install-abc"},"d.example.test":{"kind":"self","tenantId":"self","companyId":"default","installationId":"install-abc"},"e.example.test":{"kind":"self","tenantId":"self","companyId":"default","installationId":"install-abc"},"f.example.test":{"kind":"self","tenantId":"self","companyId":"default","installationId":"install-abc"}}'
OWNER='riverside-media'

# Read a key back the way the installer does — through the shared reader.
env_get() {
  python3 - "$REPO_ROOT/shared-utils" "$1" "$2" <<'PYGET'
import sys
sys.path.insert(0, sys.argv[1])
from service_env import read_env
print(read_env(sys.argv[2]).get(sys.argv[3], ''), end='')
PYGET
}
# How many registrations name $2 as their companyId.
reg_count_for() {
  python3 - "$REPO_ROOT/shared-utils" "$1" "$2" <<'PYREG'
import json, sys
sys.path.insert(0, sys.argv[1])
from service_env import read_env
registry = json.loads(read_env(sys.argv[2]).get('MC_TENANT_REGISTRY_JSON') or '{}')
print(sum(1 for r in registry.values() if r.get('companyId') == sys.argv[3]))
PYREG
}

# ── 1. BOTH copies repaired, on a FULL install ───────────────────────────────
E="$WORK/full.env"; new_env "$E" default "$SIX_DEFAULT"
LOG_LINES=""; UPDATE_ONLY=false cc_repair_company_id "$E" "$OWNER" default
eq "$(env_get "$E" MC_COMPANY_ID)" "$OWNER"           "full install: MC_COMPANY_ID repaired"
eq "$(reg_count_for "$E" "$OWNER")" "6"               "full install: all 6 registry hosts repaired (the copy tenantRegistration reads)"
eq "$(reg_count_for "$E" default)"  "0"               "full install: no registration still names the sentinel"

# ── 3. every neighbour assignment survives, secrets untouched and unechoed ───
eq "$(env_get "$E" MC_API_TOKEN)"             "$TOKEN"  "API token preserved byte-for-byte (never rotated)"
eq "$(env_get "$E" MC_TENANT_SESSION_SECRET)" "$SECRET" "session secret preserved byte-for-byte"
eq "$(env_get "$E" DATABASE_PATH)" "/opt/mission-control/mission-control.db" "DATABASE_PATH preserved"
eq "$(env_get "$E" MC_INSTALLATION_ID)" "install-abc"  "MC_INSTALLATION_ID preserved"
eq "$(env_get "$E" MC_TENANT_PUBLIC_URL)" "https://board.example.test" "MC_TENANT_PUBLIC_URL preserved"
# the registry identity fields other than companyId are untouched
eq "$(python3 -c 'import json,sys;sys.path.insert(0,sys.argv[1]);from service_env import read_env;r=json.loads(read_env(sys.argv[2])["MC_TENANT_REGISTRY_JSON"]);print(r["a.example.test"]["installationId"]+"/"+r["a.example.test"]["tenantId"]+"/"+r["a.example.test"]["kind"])' "$REPO_ROOT/shared-utils" "$E")" \
   "install-abc/self/self" "registry identity fields other than companyId untouched"
case "${LOG_LINES:-}" in
  *"$TOKEN"*|*"$SECRET"*) fail "a secret VALUE reached the log" ;;
  *) pass "no secret value reached the log" ;;
esac

# ── 6. mode still 0600 ───────────────────────────────────────────────────────
eq "$(python3 -c 'import os,sys;print(oct(os.stat(sys.argv[1]).st_mode & 0o777))' "$E")" "0o600" "file mode still 0600"

# ── 2. the --update-only path repairs too (it used to warn and do nothing) ───
E2="$WORK/update-only.env"; new_env "$E2" default "$SIX_DEFAULT"
LOG_LINES=""; UPDATE_ONLY=true cc_repair_company_id "$E2" "$OWNER" default
eq "$(env_get "$E2" MC_COMPANY_ID)" "$OWNER"  "--update-only: MC_COMPANY_ID repaired (was: warn and change nothing)"
eq "$(reg_count_for "$E2" "$OWNER")" "6"      "--update-only: all 6 registry hosts repaired"

# ── 4. already correct → NO write at all ─────────────────────────────────────
GOOD_REG="${SIX_DEFAULT//\"companyId\":\"default\"/\"companyId\":\"$OWNER\"}"
E3="$WORK/noop.env"; new_env "$E3" "$OWNER" "$GOOD_REG"
BEFORE="$(python3 -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$E3")"
LOG_LINES=""; UPDATE_ONLY=false cc_repair_company_id "$E3" "$OWNER" "$OWNER"
AFTER="$(python3 -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$E3")"
eq "$AFTER" "$BEFORE" "already-correct input rewrites nothing (byte-identical file)"
case "${LOG_LINES:-}" in
  *"already name"*) pass "already-correct input says so in the log" ;;
  *) fail "already-correct input did not log the no-op (log: ${LOG_LINES:-<empty>})" ;;
esac

# ── 5. unparseable registry → rewrite NOTHING, say so (fail closed) ──────────
E4="$WORK/broken.env"; new_env "$E4" default '{not json at all'
BEFORE4="$(python3 -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$E4")"
LOG_LINES=""; UPDATE_ONLY=false cc_repair_company_id "$E4" "$OWNER" default
AFTER4="$(python3 -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$E4")"
eq "$AFTER4" "$BEFORE4" "unparseable registry: NOTHING rewritten, not even the scalar (no half-repair)"
case "${LOG_LINES:-}" in
  *"not parseable"*) pass "unparseable registry is reported, not swallowed" ;;
  *) fail "unparseable registry was silent (log: ${LOG_LINES:-<empty>})" ;;
esac

# ── 5b. absent .env.local → warn, never create ───────────────────────────────
E5="$WORK/absent.env"
LOG_LINES=""; UPDATE_ONLY=false cc_repair_company_id "$E5" "$OWNER" default
if [ -e "$E5" ]; then fail "absent .env.local was created"; else pass "absent .env.local is not created"; fi

# ── 7. MUTATION PROOF — the pre-fix behaviour must FAIL case 1 ───────────────
# A repair that writes only the scalar is exactly what shipped. If this suite
# stays green against it, the suite proves nothing.
cc_repair_company_id_scalar_only() {
  python3 - "$REPO_ROOT/shared-utils" "$1" "$2" <<'PYMUT'
import os, sys, tempfile
sys.path.insert(0, sys.argv[1])
from service_env import read_env, encode_assignment
path, owner = sys.argv[2], sys.argv[3]
values = read_env(path)
if values.get('MC_COMPANY_ID', '') == owner:
    raise SystemExit(0)
text = open(path, encoding='utf-8').read()
lines = [l for l in text.splitlines() if l.split('=', 1)[0].strip() != 'MC_COMPANY_ID']
lines.append(encode_assignment('MC_COMPANY_ID', owner))
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or '.', prefix='.mut-')
with os.fdopen(fd, 'w', encoding='utf-8') as h:
    h.write('\n'.join(lines) + '\n')
os.replace(tmp, path)
PYMUT
}
EM="$WORK/mutant.env"; new_env "$EM" default "$SIX_DEFAULT"
cc_repair_company_id_scalar_only "$EM" "$OWNER"
if [ "$(env_get "$EM" MC_COMPANY_ID)" = "$OWNER" ] && [ "$(reg_count_for "$EM" "$OWNER")" = "0" ]; then
  pass "mutation proof: a scalar-only repair leaves all 6 registry hosts wrong — this suite bites"
else
  fail "mutation proof DID NOT BITE — the suite would pass the original defect"
fi

echo
echo "=== cc-company-id-registry-repair: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
exit 0
