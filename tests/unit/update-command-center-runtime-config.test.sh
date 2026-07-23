#!/usr/bin/env bash
# Local-fixture regression suite for the update-time Command Center runtime
# config reconciler. No real box, client record, network, or Command Center
# checkout is read or written.
set -uo pipefail

THIS_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPO_ROOT="${REPO_UNDER_TEST:-$THIS_REPO}"
RECONCILER="$REPO_ROOT/shared-utils/reconcile_command_center_runtime.py"
UPDATER="$REPO_ROOT/update-skills.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS + 1)); echo "  PASS: $1"; }
bad() { FAIL=$((FAIL + 1)); echo "  FAIL: $1"; }

TMP="$(mktemp -d -t cc-runtime-update-test-XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

make_fixture() {
  local root="$1" identity="${2:-yes}" correct="${3:-no}"
  mkdir -p "$root/workspace" "$root/master/zero-human-company/fixture-company" \
    "$root/command-center/config" "$root/command-center/public"

  cat > "$root/master/zero-human-company/fixture-company/departments.json" <<'JSON'
[
  {"id":"dept-ceo","slug":"ceo","emoji":"C","name":"CEO","headTitle":"Chief Executive Officer","workspacePath":"departments/master-orchestrator","isCeo":true},
  {"id":"dept-operations","slug":"operations","emoji":"O","name":"Operations","headTitle":"Head of Operations","workspacePath":"departments/operations"}
]
JSON

  if [ "$identity" = "yes" ]; then
    cat > "$root/workspace/.workforce-build-state.json" <<'JSON'
{"companyName":"Fixture Company","companySlug":"fixture-company","industry":"services","brandColor":"#123456"}
JSON
  else
    cat > "$root/workspace/.workforce-build-state.json" <<'JSON'
{"companySlug":"fixture-company"}
JSON
  fi

  if [ "$correct" = "yes" ]; then
    cat > "$root/command-center/config/company-config.json" <<'JSON'
{"companyName":"Established Fixture Brand","industry":"retained","custom":"keep-me"}
JSON
    cp "$root/master/zero-human-company/fixture-company/departments.json" \
      "$root/command-center/config/departments.json"
    cat > "$root/command-center/public/logo-config.json" <<'JSON'
{"logoUrl":"https://example.invalid/established-logo.png","custom":"keep-me"}
JSON
  else
    cat > "$root/command-center/config/company-config.json" <<'JSON'
{"companyName":"Your Company","industry":"","commandCenterName":"Command Center","custom":"keep-me"}
JSON
    printf '[]\n' > "$root/command-center/config/departments.json"
    printf '{}\n' > "$root/command-center/public/logo-config.json"
  fi
}

run_reconciler() {
  local root="$1"
  python3 "$RECONCILER" \
    --workspace "$root/workspace" \
    --master-files "$root/master" \
    --command-center-dir "$root/command-center" \
    >"$root/run.log" 2>&1
}

if [ ! -f "$RECONCILER" ]; then
  for scenario in \
    "empty departments populate" \
    "placeholder branding resolves" \
    "unknown identity fails loud" \
    "correct config stays unchanged" \
    "rerun is idempotent"; do
    bad "$scenario (reconciler missing)"
  done
  if grep -q 'Step U6d: Command Center runtime configuration reconciliation' "$UPDATER" 2>/dev/null; then
    ok "root updater wiring present"
  else
    bad "root updater wiring missing"
  fi
  echo "RESULT pass=$PASS fail=$FAIL"
  exit 1
fi

echo "Scenario A: empty departments are populated from the canonical ZHC artifact"
A="$TMP/a"; make_fixture "$A"
if run_reconciler "$A" && python3 - "$A/command-center/config/departments.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert len(d) == 2
assert len({x["slug"] for x in d}) == 2
PY
then
  ok "empty departments populate without duplicates"
else
  bad "empty departments did not populate"
fi

echo "Scenario B: exact placeholder branding uses the provisioning identity"
B="$TMP/b"; make_fixture "$B"
if run_reconciler "$B" && python3 - \
  "$B/command-center/config/company-config.json" \
  "$B/command-center/public/logo-config.json" <<'PY'
import json, sys
company = json.load(open(sys.argv[1]))
logo = json.load(open(sys.argv[2]))
assert company["companyName"] == "Fixture Company"
assert company["custom"] == "keep-me"
assert company["industry"] == "services"
assert logo["logoUrl"].startswith("data:image/svg+xml,")
assert "Your%20Company" not in logo["logoUrl"]
PY
then
  ok "placeholder name and empty logo receive real identity branding"
else
  bad "resolvable branding was not applied"
fi

echo "Scenario C: an undeterminable identity fails loudly and fabricates nothing"
C="$TMP/c"; make_fixture "$C" no
cp "$C/command-center/config/company-config.json" "$C/company.before"
cp "$C/command-center/public/logo-config.json" "$C/logo.before"
if run_reconciler "$C"; then
  bad "undeterminable identity unexpectedly succeeded"
elif cmp -s "$C/company.before" "$C/command-center/config/company-config.json" \
  && cmp -s "$C/logo.before" "$C/command-center/public/logo-config.json" \
  && grep -q 'IDENTITY UNRESOLVED' "$C/run.log" \
  && ! grep -Eq 'My Company|Client|Default' "$C/command-center/config/company-config.json"; then
  ok "undeterminable identity fails loud with branding files untouched"
else
  bad "identity failure was not loud or altered branding"
fi

echo "Scenario D: already-correct runtime config is byte-for-byte unchanged"
D="$TMP/d"; make_fixture "$D" yes yes
find "$D/command-center" -type f -print0 | sort -z | xargs -0 shasum -a 256 > "$D/before.sha"
if run_reconciler "$D"; then
  find "$D/command-center" -type f -print0 | sort -z | xargs -0 shasum -a 256 > "$D/after.sha"
  if cmp -s "$D/before.sha" "$D/after.sha"; then
    ok "correct departments and branding are not clobbered"
  else
    bad "correct runtime config changed"
  fi
else
  bad "correct runtime config did not pass"
fi

echo "Scenario E: a second reconciliation is a no-op"
E="$TMP/e"; make_fixture "$E"
if run_reconciler "$E"; then
  find "$E/command-center" -type f -print0 | sort -z | xargs -0 shasum -a 256 > "$E/first.sha"
  if run_reconciler "$E"; then
    find "$E/command-center" -type f -print0 | sort -z | xargs -0 shasum -a 256 > "$E/second.sha"
    if cmp -s "$E/first.sha" "$E/second.sha" && \
       [ "$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$E/command-center/config/departments.json")" = "2" ]; then
      ok "rerun is byte-idempotent and department count stays stable"
    else
      bad "rerun changed output or duplicated departments"
    fi
  else
    bad "second reconciliation failed"
  fi
else
  bad "first reconciliation failed"
fi

echo "Scenario F: an empty logo with no build-state identity NEVER blocks (stamp fix)"
# Real departments + a real, already-established company name, an EMPTY logo, and
# a build-state that carries ONLY a slug (no companyName). Pre-fix this raised
# IDENTITY UNRESOLVED (rc=1) purely because the logo could not be resolved from
# build-state — a BRANDING gap aborting the run one step before the stamp. The
# logo must instead be derived from the real company name already on disk, and
# the reconciler must SUCCEED (rc=0).
F="$TMP/f"
mkdir -p "$F/workspace" "$F/master/zero-human-company/fixture-company" \
  "$F/command-center/config" "$F/command-center/public"
cat > "$F/master/zero-human-company/fixture-company/departments.json" <<'JSON'
[
  {"id":"dept-ceo","slug":"ceo","name":"CEO"},
  {"id":"dept-operations","slug":"operations","name":"Operations"}
]
JSON
cp "$F/master/zero-human-company/fixture-company/departments.json" \
  "$F/command-center/config/departments.json"
cat > "$F/command-center/config/company-config.json" <<'JSON'
{"companyName":"Established Fixture Brand","industry":"retained","custom":"keep-me"}
JSON
printf '{}\n' > "$F/command-center/public/logo-config.json"
cat > "$F/workspace/.workforce-build-state.json" <<'JSON'
{"companySlug":"fixture-company"}
JSON
cp "$F/command-center/config/company-config.json" "$F/company.before.f"
if run_reconciler "$F" && python3 - \
  "$F/command-center/config/company-config.json" \
  "$F/command-center/public/logo-config.json" \
  "$F/company.before.f" <<'PY'
import json, sys
company = json.load(open(sys.argv[1]))
logo = json.load(open(sys.argv[2]))
before = json.load(open(sys.argv[3]))
# Real company name must be preserved byte-identical (never re-derived/clobbered).
assert company["companyName"] == before["companyName"]
assert company["custom"] == "keep-me"
# Logo derived from the on-disk real name (advisory branding population), not
# blocking, and NOT fabricating a company name.
assert logo["logoUrl"].startswith("data:image/svg+xml,")
assert "Your%20Company" not in logo["logoUrl"]
PY
then
  ok "empty logo + slug-only build-state succeeds (logo derived from real name; stamp not blocked)"
else
  bad "empty logo incorrectly blocked the reconciler or altered the company name"
fi

if grep -q 'Step U6d: Command Center runtime configuration reconciliation' "$UPDATER" \
  && grep -q '_U6D_CC_CONFIG_FAIL' "$UPDATER" \
  && grep -q 'reconcile_command_center_runtime.py' "$UPDATER"; then
  ok "root updater invokes and gates the reconciler"
else
  bad "root updater wiring/gate is incomplete"
fi

# The U6d content gate must assert departments + non-placeholder companyName,
# but must NOT hard-assert a non-empty logoUrl (that would let a branding gap
# withhold the version stamp — the bug this fix closes).
if grep -q 'ADVISORY branding gap' "$UPDATER"; then
  ok "U6d treats an empty logoUrl as advisory (does not block the stamp)"
else
  bad "U6d still hard-blocks on an empty logoUrl"
fi

echo "RESULT pass=$PASS fail=$FAIL"
[ "$FAIL" -eq 0 ]
