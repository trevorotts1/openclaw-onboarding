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


# ─────────────────────────────────────────────────────────────────────────────
# 2026-08-04 — DEFECT: an unrelated box-side CC runtime-config gap withheld
# the skills-content stamp entirely, with no path forward. Scenarios G-K.
# ─────────────────────────────────────────────────────────────────────────────
# Live: "DEPARTMENTS UNRESOLVED" (un-provisioned box, interview never
# completed -- a KNOWN VALID state) and "existing departments.json is
# non-empty but invalid; refusing to clobber operator/client data" (correct
# caution, but a dead end) each blocked 2 boxes fleet-wide. Fix: the
# reconciler now distinguishes case (a) UNPROVISIONED (rc=2, a plain
# advisory -- the caller must NOT withhold the stamp) from case (b) a
# genuine data problem (rc=1 -- the caller still writes the stamp but
# latches a non-zero FINAL exit and reports the exact remediation).

echo "Scenario G: an un-provisioned box (no ZHC artifact at all) is rc=2, UNPROVISIONED, WARN -- not FATAL"
G="$TMP/g"
mkdir -p "$G/workspace" "$G/master/zero-human-company" \
  "$G/command-center/config" "$G/command-center/public"
# No fixture-company under master/zero-human-company/ at all -- this box's
# workforce interview has never produced a ZHC departments.json artifact.
cat > "$G/workspace/.workforce-build-state.json" <<'JSON'
{}
JSON
printf '[]\n' > "$G/command-center/config/departments.json"
cat > "$G/command-center/config/company-config.json" <<'JSON'
{"companyName":"Your Company","industry":"","commandCenterName":"Command Center"}
JSON
printf '{}\n' > "$G/command-center/public/logo-config.json"
run_reconciler "$G"
RC_G=$?
if [ "$RC_G" -eq 2 ] && grep -q 'DEPARTMENTS UNRESOLVED' "$G/run.log" && grep -qi '^\[cc-runtime\] WARN' "$G/run.log"; then
  ok "un-provisioned box: rc=2 (distinct from genuine-failure rc=1), printed as WARN not FATAL"
else
  bad "un-provisioned box did not report rc=2/WARN as expected (rc=$RC_G): $(cat "$G/run.log")"
fi

echo "Scenario H: a genuine data problem (invalid existing departments.json) is rc=1, FATAL, WITH a remediation command"
H="$TMP/h"; make_fixture "$H"
# Corrupt the EXISTING departments.json into a non-empty, schema-invalid list
# (entries missing slug/name) -- the reconciler must refuse to clobber it.
printf '[{"nope":"not a valid department entry"}]\n' > "$H/command-center/config/departments.json"
cp "$H/command-center/config/departments.json" "$H/departments.before.h"
run_reconciler "$H"
RC_H=$?
if [ "$RC_H" -eq 1 ] \
  && cmp -s "$H/departments.before.h" "$H/command-center/config/departments.json" \
  && grep -q 'refusing to clobber operator/client data' "$H/run.log" \
  && grep -q 'REMEDIATION' "$H/run.log" \
  && grep -q "$H/command-center/config/departments.json" "$H/run.log"; then
  ok "invalid existing departments.json: rc=1, untouched, FATAL names the exact file + a remediation command"
else
  bad "invalid-data case did not report rc=1/remediation as expected (rc=$RC_H): $(cat "$H/run.log")"
fi

echo "Scenario I: root updater latches _U6D_CC_RUNTIME_FATAL for a genuine rc=1 (not the stamp-withholding _U6D_CC_CONFIG_FAIL)"
if grep -q '_U6D_CC_RUNTIME_FATAL' "$UPDATER" && grep -q '_U6D_CC_RUNTIME_DETAIL' "$UPDATER"; then
  ok "root updater declares the U6D-CC-RUNTIME final-verdict latch"
else
  bad "root updater is missing the U6D-CC-RUNTIME final-verdict latch"
fi
if grep -qE '_U6D_RC.*-eq 2' "$UPDATER" && grep -q 'UNPROVISIONED' "$UPDATER"; then
  ok "root updater special-cases rc=2 (UNPROVISIONED) separately from a genuine failure"
else
  bad "root updater does not distinguish rc=2 (UNPROVISIONED) from a genuine failure"
fi
if grep -q '_WORKFORCE_INCOMPLETE_NOTES.*Command Center runtime config' "$UPDATER"; then
  ok "an un-provisioned CC runtime config gap is routed to the workforce-provisioning advisory bucket (never stamp-gating)"
else
  bad "un-provisioned CC runtime config gap is not routed to the advisory bucket"
fi

echo "Scenario J: root updater's FINAL exit code goes non-zero (2) on a genuine U6d failure without withholding the stamp"
if grep -q '"\${_U6D_CC_RUNTIME_FATAL:-no}" = "yes"' "$UPDATER"; then
  ok "root updater's final verdict checks _U6D_CC_RUNTIME_FATAL"
else
  bad "root updater's final verdict does not check _U6D_CC_RUNTIME_FATAL"
fi
if grep -q '"\${GHL_MCP_RUNTIME_FATAL:-no}" = "yes" \] || \[ "\${_U6D_CC_RUNTIME_FATAL:-no}" = "yes"' "$UPDATER"; then
  ok "final exit code 2 fires when EITHER the GHL-MCP or the U6D-CC-RUNTIME latch is set"
else
  bad "final exit-code combination of the two runtime latches not found"
fi

echo "Scenario K: an UnprovisionedError never reaches the OLD undifferentiated 'FATAL' catch (exception ordering)"
python3 - "$RECONCILER" <<'PY'
import importlib.util, os, sys
path = sys.argv[1]
sys.path.insert(0, os.path.dirname(path))  # reconcile_command_center_runtime.py imports sibling detect_platform.py
spec = importlib.util.spec_from_file_location("cc_rt", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
assert issubclass(mod.UnprovisionedError, mod.ReconcileError), "UnprovisionedError must subclass ReconcileError"
try:
    raise mod.UnprovisionedError("probe")
except mod.UnprovisionedError:
    pass
else:
    raise SystemExit("UnprovisionedError was not raised/caught as itself")
print("OK")
PY
if [ $? -eq 0 ]; then
  ok "UnprovisionedError is a proper ReconcileError subclass with its own catchable identity"
else
  bad "UnprovisionedError class shape is wrong"
fi

echo "RESULT pass=$PASS fail=$FAIL"
[ "$FAIL" -eq 0 ]
