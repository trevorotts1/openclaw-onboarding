#!/usr/bin/env bash
# verify.sh - Skill 78 (Signature Product Selection) build-checkpoint verifier.
# READ-ONLY and IDEMPOTENT. Runs script self-tests, the unit suite, and JSON
# sanity on the shipped schemas. Exits nonzero on any failure.
# This is a build/maintenance check, not a runtime page-build step.
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
echo "== Skill 78 (Signature Product Selection) :: verify.sh =="
for f in SKILL.md skill-version.txt runtime-manifest.json schema/selection.schema.json schema/selection-request.schema.json schema/selection-result.schema.json schema/page-result.schema.json scripts/selection_core.py scripts/selection_session.py scripts/selection_session_store.py scripts/selection_runtime.py scripts/build_selection_plan.py scripts/validate_selection_content.py scripts/validate_selection_binding.py scripts/render_selection_preview.py scripts/emit_binding_plan.py scripts/emit_page_result.py components/selection-ui/selection.css references/selection-copy-profile.md references/selection-ui-contract.md references/binding-plan-contract.md references/asset-integration.md references/session-storage-contract.md references/runtime-adapter-contract.md tests/test_selection_core.py tests/test_selection_ui_session.py tests/test_selection_runtime_storage.py tests/test_broken_fixtures.py tests/test_emit_page_result.py fixtures/broken/unknown-price.json fixtures/broken/unapproved-price.json fixtures/broken/negative-amount.json fixtures/broken/installment-mismatch.json fixtures/broken/duplicate-offer.json fixtures/broken/offer-without-prices.json fixtures/broken/recurring-no-interval.json fixtures/broken/trial-no-terms.json fixtures/broken/missing-native-mapping.json fixtures/broken/single-offer.json; do
  if [ -f "$ROOT/$f" ]; then printf '  [PASS] %s\n' "$f"; else printf '  [FAIL] missing %s\n' "$f"; fails=$((fails+1)); fi
done
front_ver="$("$PY" -c "import re,pathlib; t=pathlib.Path('$ROOT/SKILL.md').read_text(); print(re.search(r'^version:\s*(\S+)', t, re.M).group(1))")"
file_ver="$(tr -d '[:space:]' < "$ROOT/skill-version.txt")"
if [ "$front_ver" = "$file_ver" ]; then printf '  [PASS] version lockstep %s\n' "$front_ver"; else printf '  [FAIL] version drift %s != %s\n' "$front_ver" "$file_ver"; fails=$((fails+1)); fi
run "build_selection_plan.py --self-test" "$PY" "$ROOT/scripts/build_selection_plan.py" --self-test
run "validate_selection_content.py --self-test" "$PY" "$ROOT/scripts/validate_selection_content.py" --self-test
run "validate_selection_binding.py --self-test" "$PY" "$ROOT/scripts/validate_selection_binding.py" --self-test
run "render_selection_preview.py --self-test" "$PY" "$ROOT/scripts/render_selection_preview.py" --self-test
run "emit_binding_plan.py --self-test" "$PY" "$ROOT/scripts/emit_binding_plan.py" --self-test
run "emit_page_result.py --self-test" "$PY" "$ROOT/scripts/emit_page_result.py" --self-test
run "selection_runtime.py --self-test" "$PY" "$ROOT/scripts/selection_runtime.py" --self-test
run "unit tests (unittest discover, all test files)" "$PY" -m unittest discover -s "$ROOT/tests" -v
run "schema JSON parse" "$PY" -c "import json,glob; [json.load(open(f)) for f in glob.glob('$ROOT/schema/*.json')]"
# Golden fixture freshness: the committed plan must equal a fresh rebuild
# (canonical JSON comparison) and the committed previews must match a fresh
# render byte for byte. This is the check whose absence let the first
# checkpoint ship stale renders.
run "golden fixture freshness (plan + previews rebuild identical)" "$PY" - "$ROOT" <<'PYEOF'
import json, subprocess, sys, tempfile
from pathlib import Path
root = Path(sys.argv[1])
fx = root / "fixtures" / "golden-three-option"
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    plan = subprocess.run([sys.executable, str(root / "scripts" / "build_selection_plan.py"), str(fx / "launch.json"),
                           "--recommendation", str(fx / "recommendation.json")], capture_output=True, text=True)
    assert plan.returncode == 0, plan.stderr
    rebuilt_plan = json.dumps(json.loads(plan.stdout), indent=2, sort_keys=True) + "\n"
    committed_plan = json.dumps(json.loads((fx / "plan.json").read_text()), indent=2, sort_keys=True) + "\n"
    assert rebuilt_plan == committed_plan, "plan.json differs from a fresh rebuild"
    (td / "plan.json").write_text((fx / "plan.json").read_text())
    for state, name in [("default", "preview-default.html"), ("selected", "preview-selected.html"),
                        ("error", "preview-error.html"), ("reconfirm", "preview-reconfirm.html")]:
        r = subprocess.run([sys.executable, str(root / "scripts" / "render_selection_preview.py"),
                            str(td / "plan.json"), str(td / name), "--state", state], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert (td / name).read_text() == (fx / name).read_text(), f"{name} differs from a fresh rebuild"
print("golden fixtures fresh")
PYEOF
# Schema validation of a built selection and a page result, when the
# optional jsonschema package is available; otherwise a named, honest skip.
run "schema validation of built artifacts (or named skip)" "$PY" - "$ROOT" <<'PYEOF'
import sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / "scripts"))
try:
    import jsonschema
except ImportError:
    print("SKIP-NAMED: jsonschema package not installed; parse-only check above stands")
    raise SystemExit(0)
import json
from build_selection_plan import SELF_TEST_LAUNCH, build_plan
from selection_core import build_selection
from emit_page_result import emit, emit_selection_result
sel = build_selection(SELF_TEST_LAUNCH, offer_id="MAIN-A", price_choice_id="MAIN-A-USD",
                      selected_at="2026-10-15T20:00:00Z", source_page_id="P", session_ref="opaque")
jsonschema.validate(sel, json.loads((root / "schema" / "selection.schema.json").read_text()))
req = {"request_id": "verify-request", "page_id": "VERIFY-SELECTION-PAGE",
       "input_hash": "d" * 64, "test_only": True}
res = emit(build_plan(SELF_TEST_LAUNCH), author_session="verify", request=req)
assert "outcome" not in res, "page-result document must not carry outcome"
jsonschema.validate(res, json.loads((root / "schema" / "page-result.schema.json").read_text()))
profile = emit_selection_result(build_plan(SELF_TEST_LAUNCH), author_session="verify", request=req)
jsonschema.validate(profile, json.loads((root / "schema" / "selection-result.schema.json").read_text()))
print("  [PASS] built selection, page result (no outcome), and selection-result profile validate against shipped schemas")
PYEOF
echo "=================================================="
if [ "$fails" -eq 0 ]; then echo "RESULT: PASS"; exit 0; fi
echo "RESULT: FAIL - $fails check(s) failed."
exit 1
