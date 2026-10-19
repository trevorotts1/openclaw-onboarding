#!/usr/bin/env bash
# tests/unit/gate-repair-empty-department.test.sh — CAN004 regression lock.
# repair-directors-doctrine.py deliberately skips a role-less department
# (skipped_empty) but library-gate-check.sh counted it as "no director", so
# repair-then-gate failed on every run (live: branding-dept, daily-briefing-dept)
# and the content update rolled back. Gate and repair must agree: a department
# with no role folders only WARNs. Scratch tree only; never the live ~/.openclaw.
# Exit: 0 green; 1 regressed.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPAIR="$REPO_ROOT/23-ai-workforce-blueprint/scripts/repair/repair-directors-doctrine.py"
T="$(mktemp -d "${TMPDIR:-/tmp}/gate-repair-empty-XXXXXX")"
trap 'rm -rf "$T"' EXIT
fail=0; ok() { echo "  ok   $1"; }; bad() { echo "  FAIL $1"; fail=1; }

# gate runs as a copy beside a stub general-task check (the real sibling is a different change)
mkdir -p "$T/gate"; cp "$REPO_ROOT/scripts/health/library-gate-check.sh" "$T/gate/"
printf '#!/usr/bin/env bash\nexit 0\n' > "$T/gate/general-task-check.sh"

D="$T/ws/departments"
mkdir -p "$D/sales/01-specialist" "$D/branding-dept"           # sales: roles, no director; branding: role-less
python3 -c 'print("# Role\n" + "Real authored guidance for this role, step by step.\n" * 90)' > "$D/sales/01-specialist/how-to.md"
echo "x" > "$D/branding-dept/AGENTS.md"; echo "x" > "$D/branding-dept/IDENTITY.md"
echo '{"company":"Fixture Co","yearlyRevenueGoal":1000000}' > "$T/ws/company-config.json"

rep="$(python3 "$REPAIR" --departments-dir "$D" --workspace-dir "$T/ws" --json 2>/dev/null)"
case "$rep" in *'"branding-dept"'*) ok "repair skips the role-less department";; *) bad "repair did not report skipped_empty: $rep";; esac
[ -d "$D/sales/00-director-of-sales" ] && ok "repair scaffolds a director where roles exist" || bad "no director created for sales"

out="$(bash "$T/gate/library-gate-check.sh" --workspace "$T/ws" --departments-dir "$D" --company-config "$T/ws/company-config.json" 2>&1)"; rc=$?
[ "$rc" = 0 ] && ok "repair-then-gate passes (rc=0)" || { bad "gate rc=$rc"; printf '%s\n' "$out" | sed 's/^/      /'; }
case "$out" in *'empty-departments: WARN'*branding*|*'empty-departments: WARN'*) ok "empty department is warned, not hidden";; *) bad "no empty-departments warning";; esac

# control: a department WITH roles and no director must still fail the gate
mkdir -p "$T/ws2/departments/ops/01-specialist"; cp "$D/sales/01-specialist/how-to.md" "$T/ws2/departments/ops/01-specialist/"
cp "$T/ws/company-config.json" "$T/ws2/"
bash "$T/gate/library-gate-check.sh" --workspace "$T/ws2" --departments-dir "$T/ws2/departments" --company-config "$T/ws2/company-config.json" >/dev/null 2>&1; rc=$?
[ "$rc" = 1 ] && ok "control: department with roles but no director still fails" || bad "control rc=$rc (wanted 1)"

[ "$fail" = 0 ] && echo "PASS" || { echo "REGRESSED"; exit 1; }
