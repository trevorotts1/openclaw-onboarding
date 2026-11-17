#!/usr/bin/env bash
# Folded from .github/workflows/silent-success-guards.yml (job "ONB-50-001: the impersonation guard covers every recipient-visible field"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Compile the prover
echo "--- step: Compile the prover"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards silent-success-guards--onb-50-001: step \"Compile the prover\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 -m py_compile 50-email-engine/tools/prove-email.py
echo "OK: prove-email.py compiles"
)
( # step: Run the prover self-test (includes the schema-vs-guard coverage gate)
echo "--- step: Run the prover self-test (includes the schema-vs-guard coverage gate)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards silent-success-guards--onb-50-001: step \"Run the prover self-test (includes the schema-vs-guard coverage gate)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 50-email-engine/tools/prove-email.py --self-test
)
( # step: The guard scans previews, and the schema drift gate really fails
echo "--- step: The guard scans previews, and the schema drift gate really fails"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards silent-success-guards--onb-50-001: step \"The guard scans previews, and the schema drift gate really fails\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 - <<'PY'
import importlib.util, json, pathlib, re, sys, tempfile

root = pathlib.Path("50-email-engine")
spec = importlib.util.spec_from_file_location("pe", root / "tools/prove-email.py")
pe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pe)

fail = 0

# 1. previews is in scope at all.
if "previews" not in pe.COPY_FIELDS:
    print("FAIL: previews is not in COPY_FIELDS"); fail = 1

# 2. The guard FIRES on a name in previews (synthetic sentinel; no real
#    public figure's name is committed anywhere in this repo's fixtures).
pe._PERSONA_NAME_RES.append(re.compile(r"\bfauxsimile\s+testpersona\b", re.I))
e = pe._valid_email()
e["previews"] = ["Why Fauxsimile Testpersona changed everything"]
codes = [c for c, _ in pe.evaluate(e)]
if pe.AF_PERSONA_NAMED not in codes:
    print("FAIL: a persona name in previews did NOT trip the guard:", codes); fail = 1

# 3. ANTI-FALSE-POSITIVE: clean copy still passes.
if pe.evaluate(pe._valid_email()):
    print("FAIL: clean copy tripped the guard"); fail = 1

# 4. The schema drift gate must REALLY fail on an unguarded new field --
#    a gate that cannot fail is the defect class this workflow exists for.
schema = json.loads((root / "schema/email.schema.json").read_text())
schema["properties"]["postscript"] = {"type": "string", "description": "synthetic"}
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
    json.dump(schema, fh); tmp = fh.name
ok, msg = pe._schema_copy_coverage(tmp)
if ok:
    print("FAIL: the coverage gate PASSED an unguarded free-text field"); fail = 1
else:
    print("OK: coverage gate fails on an unguarded field ->", msg)

# 5. A schema it cannot read REPORTS that; it never counts as a pass.
ok, msg = pe._schema_copy_coverage("/nonexistent/email.schema.json")
if ok:
    print("FAIL: the coverage gate PASSED with an unreadable schema"); fail = 1
else:
    print("OK: unreadable schema is reported, not passed ->", msg)

sys.exit(fail)
PY
)
( # step: Enforcement hash pin matches the pinned head
echo "--- step: Enforcement hash pin matches the pinned head"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards silent-success-guards--onb-50-001: step \"Enforcement hash pin matches the pinned head\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
cd 50-email-engine
computed="$(cat tools/prove-email.py run_email_engine.py EMAIL-MANIFEST.json \
  tools/launch_profiles.py tools/persona_canonical.py \
  profiles/launch-email-families.json schema/email.schema.json \
  intake/email-intake-questions.json | sha256sum | awk '{print $1}')"
pinned="$(tr -d ' \t\n' < ENGINE-PIN.sha256)"
if [ "$computed" != "$pinned" ]; then
  echo "FAIL: ENGINE-PIN.sha256 drift — computed $computed, pinned $pinned"
  echo "Fix: re-pin after any edit to prove-email.py / run_email_engine.py / EMAIL-MANIFEST.json"
  exit 1
fi
echo "OK: enforcement hash matches the pinned head ($pinned)"
)
