#!/usr/bin/env bash
# test-how-to-use-docs.sh - QC gate for the "How to Use This Department" guides.
#
# Enforces (per enforcement-not-description doctrine) that the owner-facing
# how-to-use-this-department.md artifact + its answer-wiring stay intact:
#   1. Every client-facing department in templates/role-library/ has a committed
#      how-to-use-this-department.md, and it is CURRENT vs the renderer.
#   2. No committed guide contains a client name, an em/en dash, or an unfilled
#      template token other than the two intended company tokens.
#   3. The build emits the guide per department (build-workforce.py is wired).
#   4. The answer mechanism is wired: the universal SOP exists, SOP-00 has the
#      Step 1.5 carve-out, and both operating protocols point at the guide.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILL="$ROOT/23-ai-workforce-blueprint"
LIB="$SKILL/templates/role-library"
PASS=0; FAIL=0
red(){ printf "\033[31m  X FAIL - %s\033[0m\n" "$1"; FAIL=$((FAIL+1)); }
ok(){ printf "\033[32m  ok - %s\033[0m\n" "$1"; PASS=$((PASS+1)); }

echo ""
echo "=== How-to-Use-This-Department QC ==="

# 1. All departments present + current vs the renderer.
if python3 "$SKILL/scripts/generate_how_to_use_docs.py" --check >/tmp/htu-check.out 2>&1; then
  ok "every department has a current how-to-use-this-department.md"
else
  red "missing or stale guides (run generate_how_to_use_docs.py)"
  cat /tmp/htu-check.out
fi

# 2. Content hygiene across every committed guide.
CLIENT_NAMES="corey|lyric|teresa|maria|kofi|beverly|evelyn|angeleen|monique|sheila|aurelia|karen|cassandra|barret|jill"
hygiene_fail=0
while IFS= read -r doc; do
  [ -f "$doc" ] || continue
  if grep -qE "—|–" "$doc"; then red "em/en dash in $doc"; hygiene_fail=1; fi
  if grep -qiE "\b($CLIENT_NAMES)\b" "$doc"; then red "client name in $doc"; hygiene_fail=1; fi
  # Any {{TOKEN}} other than the two intended company tokens is a fill failure.
  if grep -oE "\{\{[A-Z_]+\}\}" "$doc" | grep -vE "\{\{(COMPANY_NAME|GENERATION_DATE)\}\}" | grep -q .; then
    red "unfilled template token in $doc"; hygiene_fail=1
  fi
done < <(find "$LIB" -maxdepth 2 -name "how-to-use-this-department.md")
[ "$hygiene_fail" -eq 0 ] && ok "no client names, em dashes, or stray tokens in any committed guide"

# 3. Build is wired to emit the guide per department.
if grep -q "write_department_how_to_use" "$SKILL/scripts/build-workforce.py"; then
  ok "build-workforce.py calls write_department_how_to_use"
else
  red "build-workforce.py is NOT wired to emit the guide"
fi

# 4. Answer mechanism is wired.
[ -f "$ROOT/universal-sops/answering-how-to-use-questions.md" ] \
  && ok "universal-sops/answering-how-to-use-questions.md exists" \
  || red "missing universal-sops/answering-how-to-use-questions.md"

grep -q "how-to-use-this-department" "$SKILL/master-orchestrator-dept/SOP-00-Owner-Task-Routing.md" \
  && ok "SOP-00 references the guide (Step 1.5 carve-out)" \
  || red "SOP-00 does NOT reference the guide"

grep -q "how-to-use-this-department" "$SKILL/scripts/create_role_workspaces.py" \
  && ok "CEO operating protocol points at the guide" \
  || red "CEO operating protocol does NOT point at the guide"

grep -q "how-to-use-this-department" "$SKILL/scripts/build-workforce.py" \
  && ok "Director operating protocol points at the guide" \
  || red "Director operating protocol does NOT point at the guide"

echo ""
echo "=== Result: $PASS passed | $FAIL failed ==="
[ "$FAIL" -gt 0 ] && exit 1 || exit 0
