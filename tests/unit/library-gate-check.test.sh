#!/usr/bin/env bash
# tests/unit/library-gate-check.test.sh
#
# Proves scripts/health/library-gate-check.sh on throwaway fixture boxes.
# A good box must PASS; then every defect, one at a time, must flip the verdict
# (the check must not be a rubber stamp). Missing revenue goal must only WARN.
# Never touches a real box: every run points --departments-dir/--workspace/
# --company-config at a temp folder.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK="$HERE/../../scripts/health/library-gate-check.sh"
T="$(mktemp -d "${TMPDIR:-/tmp}/library-gate-check-test.XXXXXX")"
trap 'rm -rf "$T"' EXIT
fails=0
ok()  { echo "ok   - $1"; }
bad() { echo "FAIL - $1"; fails=$((fails + 1)); }

# a role playbook that clears the 3072-byte floor with real-looking text
body() { /usr/bin/python3 -c 'print("# Role playbook\n" + "Real authored guidance for this role, step by step.\n" * 90)'; }

build_box() {  # build_box <dir> : 2 departments, directors, roles, links, SOP, goal
  local b="$1"
  mkdir -p "$b/departments"
  echo "owner profile" > "$b/USER.md"
  for d in sales support; do
    local dd="$b/departments/$d"
    mkdir -p "$dd/00-director-of-$d" "$dd/01-specialist" "$dd/sops"
    body > "$dd/00-director-of-$d/how-to.md"
    body > "$dd/01-specialist/how-to.md"
    body > "$dd/sops/handle-request.md"
    echo "dept profile" > "$dd/USER.md"
    ln -s "$dd/USER.md" "$dd/01-specialist/USER.md"
    ln -s "$b/USER.md" "$dd/00-director-of-$d/USER.md"
  done
  echo '{"company":"Fixture Co","yearlyRevenueGoal":1000000}' > "$b/company-config.json"
}

run() {  # run <box> -> sets RC, OUT
  OUT="$(bash "$CHECK" --workspace "$1" --departments-dir "$1/departments" --company-config "$1/company-config.json" 2>&1)"
  RC=$?
}
expect() {  # expect <label> <rc> <grep-pattern>
  if [ "$RC" = "$2" ] && printf '%s' "$OUT" | /usr/bin/grep -q -E -- "$3"; then ok "$1"; else bad "$1 (rc=$RC, wanted $2 and /$3/)"; printf '%s\n' "$OUT" | sed 's/^/      /'; fi
}

# 1. control: good box passes
B="$T/good"; build_box "$B"; run "$B"
expect "good box passes with all four items PASS" 0 'RESULT: PASS \(0 warnings\)'
printf '%s' "$OUT" | /usr/bin/grep -q 'revenue-goal: PASS' || bad "good box revenue-goal should PASS"

# 2. placeholder text in a role playbook -> fail
B="$T/ph"; build_box "$B"; printf '# Role\n\n[PENDING — FILL FROM LIBRARY]\n' > "$B/departments/sales/01-specialist/how-to.md"; run "$B"
expect "placeholder playbook fails" 1 'sales/01-specialist/how-to.md \(placeholder text\)'

# 3. thin playbook -> fail
B="$T/thin"; build_box "$B"; echo "short" > "$B/departments/sales/01-specialist/how-to.md"; run "$B"
expect "thin playbook fails" 1 'thin \(6 bytes\)'

# 4. empty playbook -> fail
B="$T/empty"; build_box "$B"; : > "$B/departments/support/01-specialist/how-to.md"; run "$B"
expect "empty playbook fails" 1 'support/01-specialist/how-to.md \(empty\)'

# 5. placeholder SOP file -> fail
B="$T/sop"; build_box "$B"; echo "[Step 1 - to be personalized based on research]" > "$B/departments/sales/sops/handle-request.md"; run "$B"
expect "placeholder SOP fails" 1 'handle-request.md \(placeholder text\)'

# 6. role folder with no how-to.md -> fail
B="$T/nohowto"; build_box "$B"; rm "$B/departments/sales/01-specialist/how-to.md"; echo "id" > "$B/departments/sales/01-specialist/IDENTITY.md"; run "$B"
expect "role without how-to.md fails" 1 'missing how-to.md'

# 7. department without a director -> fail
B="$T/nodir"; build_box "$B"; rm -rf "$B/departments/support/00-director-of-support"; run "$B"
expect "department without director fails" 1 'directors: FAIL - 1 of 2 departments have no director'

# 8. broken USER.md link -> fail
B="$T/link"; build_box "$B"; rm "$B/departments/sales/USER.md"; run "$B"
expect "broken USER.md link fails" 1 'user-md-links: FAIL - 1 of 4 USER.md links are broken'

# 9. missing revenue goal -> WARN only, still exit 0
B="$T/goal"; build_box "$B"; echo '{"company":"Fixture Co"}' > "$B/company-config.json"; run "$B"
expect "missing revenue goal only warns" 0 'RESULT: PASS \(1 warning\)'
printf '%s' "$OUT" | /usr/bin/grep -q 'revenue-goal: WARN' || bad "revenue-goal should say WARN"

# 10. no company-config at all -> WARN only
B="$T/nocfg"; build_box "$B"; rm "$B/company-config.json"; run "$B"
expect "no company-config only warns" 0 'revenue-goal: WARN - no company-config.json found'

# 11. backup snapshot dir is not a department (mirrors qc-completeness)
B="$T/bak"; build_box "$B"; mkdir -p "$B/departments/sales.bak-20260101/x"; echo "junk" > "$B/departments/sales.bak-20260101/x/how-to.md"; run "$B"
expect "backup dir is ignored" 0 'RESULT: PASS'

# 12. placeholder quoted deep inside a real playbook is doctrine, not a stub
B="$T/quote"; build_box "$B"; { body; printf 'A good playbook never leaves [PENDING - FILL FROM LIBRARY] behind.\n'; } > "$B/departments/sales/01-specialist/how-to.md"; run "$B"
expect "quoted stub phrase deep in a real playbook passes" 0 'RESULT: PASS'

# 13. "cannot tell" is never a pass
B="$T/none"; mkdir -p "$B/departments"; run "$B"
expect "no departments is undetermined (exit 5), not a pass" 5 'UNDETERMINED'

# 14. read-only: running the check changes nothing in the box
B="$T/ro"; build_box "$B"; before="$(find "$B" -type f -o -type l | sort | xargs ls -ld 2>/dev/null | cksum)"; run "$B"
after="$(find "$B" -type f -o -type l | sort | xargs ls -ld 2>/dev/null | cksum)"
[ "$before" = "$after" ] && ok "check writes nothing" || bad "check modified the box"

echo
if [ "$fails" -eq 0 ]; then echo "library-gate-check: all tests passed"; exit 0; fi
echo "library-gate-check: $fails test(s) FAILED"; exit 1
