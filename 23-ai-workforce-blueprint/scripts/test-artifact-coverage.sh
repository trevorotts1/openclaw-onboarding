#!/usr/bin/env bash
# test-artifact-coverage.sh — adversarial fixture tests for the ARTIFACT COVERAGE
# gate (the 7 new dimensions in qc-assert-repo-consistency.py, v12.25.0).
#
# A green gate that never fails is worthless. These tests plant ONE drift per new
# dimension in an isolated sandbox copy of the repo and confirm the gate exits
# NON-ZERO (rc=6, ARTIFACT DRIFT) with a clear message — and that the CLEAN repo
# PASSES (rc=0).
#
#   A0. CLEAN REPO PASSES (artifact gate rc=0)
#   A1. ORG-CHART        — neuter generate_org_chart to drop a dept  -> FAIL
#   A2. ROUTING          — neuter write_universal_routing_map row     -> FAIL
#   A3. COMMAND-CENTER   — neuter generate_departments_json entry     -> FAIL
#   A4. DREAMING         — unwire create_department_workspace from the
#                          selected_departments loop                  -> FAIL
#   A5. GENERATOR-WIRING — remove a generator call site               -> FAIL
#   A6. BOOTSTRAP        — delete a shipped core template (SOUL.md)    -> FAIL
#   A7. SKILLS-COUNT     — corrupt the README skill count             -> FAIL
#   A8. VERSION-MARKERS  — drift one version marker (install.sh)      -> FAIL
#
# Each negative test breaks exactly ONE invariant so the gate is proven to bite on
# THAT specific drift. Exit 0 = all fixture tests pass; non-zero = a test failed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"
GATE="$SCRIPT_DIR/qc-assert-repo-consistency.py"

PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

# Run ONLY the artifact gate against a sandbox skill dir; echo rc.
run_artifact() {  # run_artifact <skill-dir> -> rc
  python3 "$GATE" --skill-dir "$1" --only artifact >/dev/null 2>&1
  echo $?
}

# A sandbox the artifact gate can read fully needs the repo-root files it scans
# (version, install.sh, README.md, cc-compat.json, the 6 core templates,
# Start Here.md) PLUS the skill dir and the PA sibling library. We copy the
# repo-root scalar files + the skill + PA lib into <tmp>/repo/.
SANDBOXES_FILE="$(mktemp)"
make_sandbox() {  # make_sandbox -> echoes the sandbox skill dir on the FIRST line
  local tmp; tmp="$(mktemp -d)"
  local sbroot="$tmp/repo"
  mkdir -p "$sbroot"
  cp -R "$SKILL_DIR" "$sbroot/23-ai-workforce-blueprint"
  [ -d "$REPO_ROOT/42-personal-assistant-library" ] && \
    cp -R "$REPO_ROOT/42-personal-assistant-library" "$sbroot/42-personal-assistant-library"
  # Repo-root files the artifact gate reads (BOOTSTRAP / SKILLS-COUNT / VERSION).
  for f in version install.sh update-skills.sh README.md cc-compat.json \
           DIRECT-TO-AGENT-UPDATE-MESSAGE.md "Start Here.md" \
           IDENTITY.md SOUL.md AGENTS.md USER.md TOOLS.md HEARTBEAT.md; do
    [ -e "$REPO_ROOT/$f" ] && cp "$REPO_ROOT/$f" "$sbroot/$f"
  done
  # Also bring the ACTIVE + ARCHIVED skill dir NAMES across so the tree-count is
  # identical to the real repo (empty stand-ins are enough — only dir names count).
  for d in "$REPO_ROOT"/[0-9]*/; do
    base="$(basename "$d")"
    [ "$base" = "23-ai-workforce-blueprint" ] && continue
    [ "$base" = "42-personal-assistant-library" ] && continue
    mkdir -p "$sbroot/$base"
  done
  find "$sbroot/23-ai-workforce-blueprint" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
  echo "$sbroot/23-ai-workforce-blueprint"
  echo "$tmp" >> "$SANDBOXES_FILE"
}

cleanup() {
  while IFS= read -r d; do [ -n "$d" ] && rm -rf "$d"; done < "$SANDBOXES_FILE" 2>/dev/null
  rm -f "$SANDBOXES_FILE"
}
trap cleanup EXIT

echo "=== A0: CLEAN REPO PASSES (artifact gate) ==="
rc="$(run_artifact "$SKILL_DIR")"
if [ "$rc" -eq 0 ]; then ok "clean repo artifact gate exits 0 (rc=$rc)"; else bad "clean repo should exit 0, got rc=$rc"; fi

echo "=== A1: ORG-CHART drift FAILS ==="
sb="$(make_sandbox | head -1)"
# Make generate_org_chart skip the 'marketing' dept -> it vanishes from the chart.
python3 - "$sb/scripts/build-workforce.py" <<'PY'
import sys
p = sys.argv[1]; s = open(p, encoding="utf-8").read()
needle = "    for dept_id, dept_info in departments.items():\n        content += f\"### {dept_info['emoji']} {dept_info['name']} - {dept_info['head']}\\n\""
repl   = "    for dept_id, dept_info in departments.items():\n        if dept_id == 'marketing':\n            continue\n        content += f\"### {dept_info['emoji']} {dept_info['name']} - {dept_info['head']}\\n\""
assert needle in s, "org-chart loop anchor not found"
open(p, "w", encoding="utf-8").write(s.replace(needle, repl, 1))
PY
rc="$(run_artifact "$sb")"
if [ "$rc" -eq 6 ]; then ok "org-chart dropping a dept -> exit 6"; else bad "org-chart drift should exit 6, got rc=$rc"; fi

echo "=== A2: ROUTING drift FAILS ==="
sb="$(make_sandbox | head -1)"
# Make write_universal_routing_map skip 'sales' -> no routing row for it.
python3 - "$sb/scripts/build-workforce.py" <<'PY'
import sys
p = sys.argv[1]; s = open(p, encoding="utf-8").read()
needle = '        if dept_id in ("ceo", "master-orchestrator", "dept-ceo"):\n            continue'
repl   = '        if dept_id in ("ceo", "master-orchestrator", "dept-ceo", "sales"):\n            continue'
assert needle in s, "routing skip anchor not found"
open(p, "w", encoding="utf-8").write(s.replace(needle, repl, 1))
PY
rc="$(run_artifact "$sb")"
if [ "$rc" -eq 6 ]; then ok "routing dropping a dept -> exit 6"; else bad "routing drift should exit 6, got rc=$rc"; fi

echo "=== A3: COMMAND-CENTER drift FAILS ==="
sb="$(make_sandbox | head -1)"
# Make generate_departments_json skip 'research' -> no CC column/topic for it.
python3 - "$sb/scripts/build-workforce.py" <<'PY'
import sys
p = sys.argv[1]; s = open(p, encoding="utf-8").read()
needle = '        if dept_id in ("ceo", "master-orchestrator", "dept-ceo"):\n            continue'
# There are two such guards (routing + departments_json). Replace the LAST one
# (inside generate_departments_json, which appears after the def line).
idx = s.rfind(needle)
assert idx != -1, "departments_json skip anchor not found"
repl = '        if dept_id in ("ceo", "master-orchestrator", "dept-ceo", "research"):\n            continue'
s = s[:idx] + repl + s[idx + len(needle):]
open(p, "w", encoding="utf-8").write(s)
PY
rc="$(run_artifact "$sb")"
if [ "$rc" -eq 6 ]; then ok "command-center dropping a dept -> exit 6"; else bad "command-center drift should exit 6, got rc=$rc"; fi

echo "=== A4: DREAMING drift FAILS (dept-workspace unwired from floor loop) ==="
sb="$(make_sandbox | head -1)"
# Replace the selected_departments loop that drives create_department_workspace
# with a hardcoded 1-dept subset -> floor depts excluded from the dreaming substrate.
python3 - "$sb/scripts/build-workforce.py" <<'PY'
import sys, re
p = sys.argv[1]; lines = open(p, encoding="utf-8").read().splitlines(keepends=True)
# Find the call line, walk back to its governing `for ... in selected_departments` header.
call_i = next(i for i, ln in enumerate(lines)
              if "create_department_workspace(" in ln and not ln.lstrip().startswith("def "))
hdr = None
for j in range(call_i, max(0, call_i - 60), -1):
    if re.match(r"\s*for\s+\w+(?:\s*,\s*\w+)?\s+in\s+selected_departments", lines[j]):
        hdr = j; break
assert hdr is not None, "dept-workspace floor loop header not found"
indent = lines[hdr][:len(lines[hdr]) - len(lines[hdr].lstrip())]
lines[hdr] = f'{indent}for dept_id, dept_info in {{"marketing": selected_departments.get("marketing", {{}})}}.items():\n'
open(p, "w", encoding="utf-8").write("".join(lines))
PY
rc="$(run_artifact "$sb")"
if [ "$rc" -eq 6 ]; then ok "dept-workspace unwired from floor loop -> exit 6"; else bad "dreaming drift should exit 6, got rc=$rc"; fi

echo "=== A5: GENERATOR-WIRING drift FAILS (remove a generator call) ==="
sb="$(make_sandbox | head -1)"
# Remove the write_universal_routing_map CALL site (keep the def) -> unwired.
python3 - "$sb/scripts/build-workforce.py" <<'PY'
import sys
p = sys.argv[1]; lines = open(p, encoding="utf-8").read().splitlines(keepends=True)
out = [ln for ln in lines
       if not ("write_universal_routing_map(" in ln and not ln.lstrip().startswith("def "))]
assert len(out) < len(lines), "no routing call site removed"
open(p, "w", encoding="utf-8").write("".join(out))
PY
rc="$(run_artifact "$sb")"
if [ "$rc" -eq 6 ]; then ok "removed a generator call site -> exit 6"; else bad "generator-wiring drift should exit 6, got rc=$rc"; fi

echo "=== A6: BOOTSTRAP drift FAILS (delete a shipped core template) ==="
sb="$(make_sandbox | head -1)"
sbroot="$(dirname "$sb")"
rm -f "$sbroot/SOUL.md"
rc="$(run_artifact "$sb")"
if [ "$rc" -eq 6 ]; then ok "deleted SOUL.md core template -> exit 6"; else bad "bootstrap drift should exit 6, got rc=$rc"; fi

echo "=== A6b: BOOTSTRAP drift FAILS (a committed MEMORY.md template) ==="
sb="$(make_sandbox | head -1)"
sbroot="$(dirname "$sb")"
printf '# MEMORY\n- a committed memory file (should never ship)\n' > "$sbroot/MEMORY.md"
rc="$(run_artifact "$sb")"
if [ "$rc" -eq 6 ]; then ok "committed MEMORY.md template -> exit 6"; else bad "committed MEMORY.md should exit 6, got rc=$rc"; fi

echo "=== A7: SKILLS-COUNT drift FAILS (corrupt the README count) ==="
sb="$(make_sandbox | head -1)"
sbroot="$(dirname "$sb")"
python3 - "$sbroot/README.md" <<'PY'
import sys, re
p = sys.argv[1]; s = open(p, encoding="utf-8").read()
s2 = re.sub(r"\*\*(\d+) numbered skill folders", lambda m: f"**{int(m.group(1))+5} numbered skill folders", s, count=1)
assert s2 != s, "README skill-count line not found"
open(p, "w", encoding="utf-8").write(s2)
PY
rc="$(run_artifact "$sb")"
if [ "$rc" -eq 6 ]; then ok "corrupt README skill count -> exit 6"; else bad "skills-count drift should exit 6, got rc=$rc"; fi

echo "=== A8: VERSION-MARKERS drift FAILS (drift install.sh ONBOARDING_VERSION) ==="
sb="$(make_sandbox | head -1)"
sbroot="$(dirname "$sb")"
python3 - "$sbroot/install.sh" <<'PY'
import sys, re
p = sys.argv[1]; s = open(p, encoding="utf-8").read()
s2 = re.sub(r'^ONBOARDING_VERSION="?v?[0-9.]+"?', 'ONBOARDING_VERSION="v0.0.1"', s, count=1, flags=re.MULTILINE)
assert s2 != s, "ONBOARDING_VERSION line not found"
open(p, "w", encoding="utf-8").write(s2)
PY
rc="$(run_artifact "$sb")"
if [ "$rc" -eq 6 ]; then ok "drifted install.sh version -> exit 6"; else bad "version-markers drift should exit 6, got rc=$rc"; fi

echo
echo "--------------------------------------------"
echo "RESULT: $PASS passed, $FAIL failed"
if [ "$FAIL" -eq 0 ]; then
  echo "ALL ARTIFACT-COVERAGE FIXTURE TESTS PASSED"
  exit 0
else
  echo "ARTIFACT-COVERAGE FIXTURE TEST FAILURES"
  exit 1
fi
