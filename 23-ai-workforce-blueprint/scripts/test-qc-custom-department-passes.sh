#!/usr/bin/env bash
# test-qc-custom-department-passes.sh — BU-57 acceptance (WF-077, WF-052).
#
# Proves, against the SHIPPED qc-completeness.sh, that:
#   1. a department the role-library index does not know (custom / LLM-authored)
#      is PASS when every role folder carries a real how-to.md (>= LIBRARY_MIN_BYTES)
#      and IDENTITY.md coverage is >= 95% — a custom department no longer blocks
#      the whole company just because the library has no expected role count;
#   2. the same department is PARTIAL when one how-to.md is thinner than the floor
#      (the gate is not simply loosened);
#   3. the new --deps-only flag runs ONLY the presentation-dependency block and
#      exits 6 when a required dep is absent, 0 when present;
#   4. the normal run with QC_SKIP_PRESENTATION_DEPS=1 does not exit 6 — missing
#      presentation tools are recorded, never a required check.
#
# Every scenario runs against a sandboxed HOME with fixture trees; no box, fleet
# or live database is read or written.
#
# Exit 0 = every assertion passed.

set -uo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
QC="$SCRIPT_DIR/qc-completeness.sh"
FLOOR="$SCRIPT_DIR/department-floor.py"

[ -f "$QC" ] || { echo "FAIL: qc-completeness.sh missing at $QC" >&2; exit 1; }
[ -f "$FLOOR" ] || { echo "FAIL: department-floor.py missing at $FLOOR" >&2; exit 1; }
bash -n "$QC" || { echo "FAIL: qc-completeness.sh does not parse" >&2; exit 1; }
python3 -m py_compile "$SCRIPT_DIR/workforce_completion.py" \
  || { echo "FAIL: workforce_completion.py does not compile" >&2; exit 1; }

PASSED=0
FAILED=0
ok()   { echo "  PASS: $*"; PASSED=$((PASSED+1)); }
bad()  { echo "  FAIL: $*" >&2; FAILED=$((FAILED+1)); }

# Explicit template so TMPDIR is honoured on macOS (bare mktemp -d ignores it).
TMP="$(mktemp -d "${TMPDIR:-/tmp}/qc-custom-dept.XXXXXX")" || exit 1
trap 'rm -rf "$TMP"' EXIT
TMP="$(cd "$TMP" && pwd -P)"

# detect_platform aborts when it cannot tell the platform; the sandboxed HOME
# carries ~/.openclaw, and the documented override is set too.
export OPENCLAW_PLATFORM="${OPENCLAW_PLATFORM:-mac}"

FIX="$TMP/fixture"
HOME_DIR="$FIX/home"
WS="$HOME_DIR/.openclaw/workspace"
DEPTS="$WS/departments"

# Build the fixture: one library department that passes (ai-ceo, count 1 in the
# shipped index) and one department the index does not know, with two role
# folders, each carrying a 4 KB how-to.md and an IDENTITY.md.
build_fixture() {
  rm -rf "$WS"
  mkdir -p "$DEPTS"
  HOME="$HOME_DIR" python3 - "$WS" "$DEPTS" "$FLOOR" <<'PY'
import importlib.util, json, sys
from pathlib import Path

ws, depts, floor_py = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])

FILLED_HOWTO = (
    "<!-- workforce-provenance: source=role-library role-slug=ai-ceo-playbook content_sha=y -->\n"
    + ("How-to body content line.\n" * 200)
)
assert len(FILLED_HOWTO.encode()) >= 3072
SOP = (
    "## Define\n" + ("Define body line of real content.\n" * 80)
    + "## Measure\n" + ("Measure body line of real content.\n" * 80)
    + "## Analyze\n" + ("Analyze body line of real content.\n" * 80)
    + "## Improve\n" + ("Improve body line of real content.\n" * 80)
    + "## Control\n" + ("Control body line of real content.\n" * 80)
)
assert len(SOP.encode()) >= 7168

# Library department: ai-ceo (1 role in the shipped index), fully filled.
lib = depts / "ai-ceo"
role = lib / "01-ai-ceo-playbook"
role.mkdir(parents=True)
(role / "how-to.md").write_text(FILLED_HOWTO)
(role / "IDENTITY.md").write_text("# identity\n")
for n in range(1, 5):
    (role / f"0{n}-sop.md").write_text(SOP)
(lib / "governing-personas.md").write_text("# personas\n")

# Custom (not in the index) department: two roles, 4 KB how-to.md each.
custom = depts / "custom-research-lab"
custom.mkdir()
for slug in ("researcher-a", "researcher-b"):
    rd = custom / slug
    rd.mkdir()
    (rd / "how-to.md").write_text("# how-to\n" + ("Custom role content line.\n" * 200))
    (rd / "IDENTITY.md").write_text("# identity\n")
(custom / "governing-personas.md").write_text("# personas\n")
for slug in ("researcher-a", "researcher-b"):
    assert (custom / slug / "how-to.md").stat().st_size >= 4096

# The hard department floor is not what this unit exercises. Simulate a client
# who declined every floor department so the floor check cannot mask the
# per-department verdict, using the provenance shape department-floor accepts.
spec = importlib.util.spec_from_file_location("department_floor", floor_py)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
verdict = mod.evaluate_floor(departments_dir=depts)
assert verdict["expected_floor"], "fixture floor came back empty"
decisions = {
    key: {"decision": "no", "source": "fixture", "decidedAt": "2026-01-01T00:00:00Z",
          "decidedBy": "test-qc-custom-department-passes"}
    for key in verdict["expected_floor"]
}
(ws / ".workforce-build-state.json").write_text(json.dumps({
    "companySlug": "fixture-co",
    "canonicalReconciliation": {"decisions": decisions},
}))
recheck = mod.evaluate_floor(departments_dir=depts)
assert recheck["floor_met"] and recheck["rc"] == 0, (
    "fixture floor still unmet after declines: %r" % (recheck.get("missing_mandatory"),))
PY
}

run_qc() {  # run_qc <expected-rc> <label> [env assignments...] -- [args...]
  local want="$1" label="$2"; shift 2
  local -a envs=() args=()
  while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do envs+=("$1"); shift; done
  [ "$#" -gt 0 ] && shift
  args=("$@")
  env -i HOME="$HOME_DIR" OPENCLAW_PLATFORM="$OPENCLAW_PLATFORM" \
      PATH="${QC_PATH_OVERRIDE:-$PATH}" ${envs[@]+"${envs[@]}"} \
      bash "$QC" ${args[@]+"${args[@]}"} > "$TMP/out.log" 2>&1
  local rc=$?
  echo "  ($label) exit $rc (want $want)"
  if [ "$rc" = "$want" ]; then ok "$label: exit $rc"; else
    bad "$label: exit $rc, expected $want"; sed -n '1,25p' "$TMP/out.log" | sed 's/^/    > /'
  fi
  return 0
}

echo "=== S1: a custom department with real content is PASS, whole gate exits 0 ==="
build_fixture
# The build's required run passes QC_SKIP_PRESENTATION_DEPS=1 (BU-57 Change 2),
# so the analysis verdict is exercised independently of this box's presentation
# runtime — the dep gate has its own scenario below.
run_qc 0 "custom department with 4 KB how-tos passes" QC_SKIP_PRESENTATION_DEPS=1 -- --quiet
if grep -q "custom-research-lab" "$TMP/out.log" && grep -q "PASS" "$TMP/out.log"; then
  ok "the run names the custom department"
else
  echo "  NOTE: custom department not named in the summary (quiet run)"
fi

echo "=== S2: a thin how-to.md in the custom department drops it to PARTIAL (exit 2) ==="
printf '# thin\n' > "$DEPTS/custom-research-lab/researcher-b/how-to.md"
run_qc 2 "one 1 KB how-to makes the custom department PARTIAL" QC_SKIP_PRESENTATION_DEPS=1 -- --quiet

echo "=== S3: --deps-only exits 6 when soffice/pdftoppm are absent ==="
build_fixture
STUB="$TMP/bin"
mkdir -p "$STUB"
for b in bash python3 date mkdir dirname tee sed cat printf grep env tail; do
  src="$(command -v "$b" 2>/dev/null || true)"
  [ -n "$src" ] && ln -sf "$src" "$STUB/$b"
done
QC_PATH_OVERRIDE="$STUB" run_qc 6 "--deps-only with no soffice/pdftoppm" -- --deps-only
if grep -q "PRESENTATION_DEPS_MISSING" "$TMP/out.log"; then
  ok "--deps-only logged PRESENTATION_DEPS_MISSING"
else
  bad "--deps-only did not log PRESENTATION_DEPS_MISSING"
fi

echo "=== S4: normal mode with QC_SKIP_PRESENTATION_DEPS=1 does not exit 6 ==="
run_qc 0 "normal mode with QC_SKIP_PRESENTATION_DEPS=1 is not 6" QC_SKIP_PRESENTATION_DEPS=1 -- --quiet
if grep -q "DEP_GATE_BYPASSED" "$TMP/out.log"; then
  ok "the bypass is still recorded, not silent"
else
  bad "the bypass was not recorded (DEP_GATE_BYPASSED line missing)"
fi

echo "============================================"
echo "test-qc-custom-department-passes: PASS=$PASSED FAIL=$FAILED"
echo "============================================"
[ "$FAILED" -eq 0 ] || exit 1
exit 0
