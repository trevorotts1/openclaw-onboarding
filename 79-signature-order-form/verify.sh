#!/usr/bin/env bash
# verify.sh - Skill 79 (Signature Order Form) verifier. READ-ONLY and IDEMPOTENT.
# Checks required files, version lockstep (SKILL.md <-> skill-version.txt),
# schema JSON parse and the unit suite. Exits nonzero on any failure.
# Build/maintenance and update-gate check, not a runtime page-build step.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"
fails=0
run() {
  local label="$1"; shift
  local log rc
  log="$("$@" 2>&1)"; rc=$?
  if [ "$rc" -eq 0 ]; then printf '  [PASS] %s\n' "$label"; else printf '  [FAIL] %s (rc=%s)\n%s\n' "$label" "$rc" "$log"; fails=$((fails+1)); fi
}
echo "== Skill 79 (Signature Order Form) :: verify.sh =="
for f in SKILL.md skill-version.txt references/checkout.schema.json references/extra_offer_interface.md scripts/validate_checkout.py scripts/purchase_event.py scripts/purchase_state.py scripts/order_bumps.py scripts/selection_flow.py scripts/quote_display.py scripts/capability_matrix.py scripts/attempt_recovery.py scripts/bump_fixture_model.py; do
  if [ -f "$ROOT/$f" ]; then printf '  [PASS] %s\n' "$f"; else printf '  [FAIL] missing %s\n' "$f"; fails=$((fails+1)); fi
done
front_ver="$("$PY" -c "import re,pathlib,sys; m=re.search(r'^version:\s*(\S+)', pathlib.Path(sys.argv[1]).read_text(), re.M); print(m.group(1) if m else '')" "$ROOT/SKILL.md")"
file_ver="$(tr -d '[:space:]' < "$ROOT/skill-version.txt")"
if [ -n "$front_ver" ] && [ "$front_ver" = "$file_ver" ]; then printf '  [PASS] version lockstep %s\n' "$front_ver"; else printf '  [FAIL] version drift [%s] != [%s]\n' "$front_ver" "$file_ver"; fails=$((fails+1)); fi
run "schema JSON parse" "$PY" -c "import json,sys; json.load(open(sys.argv[1]))" "$ROOT/references/checkout.schema.json"
# The validator imports jsonschema; name the fix instead of ten import errors.
run "jsonschema importable (python3 -m launcher_core.cli dependencies --install from 83-black-friday-launcher)" "$PY" -c "
import sys; sys.path.insert(0, sys.argv[1] + '/scripts')
import validate_checkout" "$ROOT"
run "unit tests (unittest discover, all test files)" "$PY" -m unittest discover -s "$ROOT/tests"
echo "=================================================="
if [ "$fails" -eq 0 ]; then echo "RESULT: PASS"; exit 0; fi
echo "RESULT: FAIL - $fails check(s) failed."
exit 1
