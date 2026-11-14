#!/usr/bin/env bash
# test-retire-without-database.sh — BU-56 acceptance test.
#
# Proves "Remove this department" is carried out with NO Command Center
# database variable present, and that the agent-roster step runs before
# anything is moved:
#
#   A1  the retirement exits 0 with no DASHBOARD_DB_PATH / DATABASE_PATH
#   A2  the declined tree is under <company>/.retired/ (never deleted)
#   A3  the settle receipt carries ccLanePending == true
#   A4  the declined entry is gone from departments[]
#   A5  a roster-step failure exits 1 and NO tree was moved
#
# Exit 0 = every guard passes; non-zero = a guard failed.
# Hermetic: sandboxed $HOME, scratch build-state under $TMPDIR. Nothing may
# escape the sandbox.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RETIRE="$SCRIPT_DIR/retire-confirmed-decline.sh"

PASS=0
FAIL=0
good() { PASS=$((PASS + 1)); echo "PASS: $1"; }
bad()  { FAIL=$((FAIL + 1)); echo "FAIL: $1" >&2; }

[ -f "$RETIRE" ] || { echo "FAIL: missing $RETIRE" >&2; exit 1; }

TMP="$(mktemp -d -p "${TMPDIR:-/tmp}")"
trap 'chmod -R u+rwX "$TMP" 2>/dev/null; rm -rf "$TMP"' EXIT
SANDBOX_HOME="$TMP/home"
mkdir -p "$SANDBOX_HOME"

# ── fixture: one company, three prebuilt departments, one provenanced decline
make_fixture() {  # $1 = company folder, $2 = state file, $3 = company slug
  local company="$1" state="$2" slug="$3"
  mkdir -p "$company/departments/audio" "$company/departments/marketing" "$company/departments/sales"
  for d in audio marketing sales; do echo "SENTINEL-$d" > "$company/departments/$d/SENTINEL.md"; done
  python3 - "$state" "$slug" <<'PY'
import json, sys
state_path, slug = sys.argv[1], sys.argv[2]
state = {
    "companySlug": slug,
    "buildType": "standard-first",
    "standardPrebuild": {"prebuiltDepartments": ["audio", "marketing", "sales"]},
    "departments": [
        {"slug": "audio", "status": "prebuilt"},
        {"slug": "marketing", "status": "prebuilt"},
        {"slug": "sales", "status": "prebuilt"},
    ],
    "canonicalReconciliation": {"decisions": {"audio": {
        "decision": "no",
        "source": "owner-interview",
        "decidedAt": "2026-11-12T12:00:00Z",
        "decidedBy": "owner",
    }}},
}
with open(state_path, "w", encoding="utf-8") as f:
    json.dump(state, f, indent=2)
PY
}

# ── CASE 1: no database variable at all ────────────────────────────────────
COMPANY1="$TMP/acme-one"
STATE1="$TMP/state-one.json"
make_fixture "$COMPANY1" "$STATE1" "acme-one"
env -u DASHBOARD_DB_PATH -u DATABASE_PATH HOME="$SANDBOX_HOME" \
  bash "$RETIRE" --dept __declined__ --build-state-file "$STATE1" --company-dir "$COMPANY1" \
  >"$TMP/case1.out" 2>"$TMP/case1.err"
RC=$?
if [ "$RC" -eq 0 ]; then good "A1: retirement exits 0 with no database variable"; else
  bad "A1: expected rc=0, got $RC"; tail -8 "$TMP/case1.err" >&2; fi

if [ ! -d "$COMPANY1/departments/audio" ] \
   && [ -n "$(find "$COMPANY1/.retired" -maxdepth 2 -type f -name SENTINEL.md 2>/dev/null)" ]; then
  good "A2: declined tree archived under .retired/ (never deleted)"
else
  bad "A2: 'audio' not archived correctly (dir present=$( [ -d "$COMPANY1/departments/audio" ] && echo yes || echo no ))"
fi

python3 - "$STATE1" <<'PY'
import json, sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
receipts = state.get("departmentRetirementReceipts") or []
last = receipts[-1] if receipts else {}
assert last.get("ccLanePending") is True, "ccLanePending=%r" % (last.get("ccLanePending"),)
slugs = {str(d.get("slug") or d.get("id")) for d in state.get("departments") or [] if isinstance(d, dict)}
assert "audio" not in slugs, "declined entry still present: %r" % (sorted(slugs),)
PY
if [ $? -eq 0 ]; then good "A3/A4: receipt ccLanePending=true; declined entry removed from departments[]"; else
  bad "A3/A4: receipt or departments[] wrong"; fi

# ── CASE 2: the roster step fails first; nothing may move ──────────────────
COMPANY2="$TMP/acme-two"
STATE2="$TMP/state-two.json"
make_fixture "$COMPANY2" "$STATE2" "acme-two"
BAD_CONFIG="$TMP/openclaw-unreadable.json"
printf '{not valid json' > "$BAD_CONFIG"
chmod 000 "$BAD_CONFIG"
env -u DASHBOARD_DB_PATH -u DATABASE_PATH HOME="$SANDBOX_HOME" \
  bash "$RETIRE" --dept __declined__ --build-state-file "$STATE2" --company-dir "$COMPANY2" \
  --oc-config "$BAD_CONFIG" >"$TMP/case2.out" 2>"$TMP/case2.err"
RC=$?
if [ "$RC" -eq 1 ]; then good "A5: roster-step failure exits 1"; else
  bad "A5: expected rc=1, got $RC"; tail -8 "$TMP/case2.err" >&2; fi
if [ -d "$COMPANY2/departments/audio" ] && [ ! -d "$COMPANY2/.retired" ]; then
  good "A5: no tree was moved before the failure"
else
  bad "A5: a tree moved despite the roster-step failure"
fi

echo "── $PASS passed, $FAIL failed ──"
[ "$FAIL" -eq 0 ]
