#!/usr/bin/env bash
# Folded from .github/workflows/content-pipeline-fail-closed-guard.yml (job "T0-61: the em-dash check is not satisfied by an em dash"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Syntax-check
echo "--- step: Syntax-check"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards content-pipeline-fail-closed-guard--humanizer-predicate: step \"Syntax-check\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash -n 19-humanizer/qc-humanizer.sh
bash -n 19-humanizer/test/test-humanizer-rule-check.sh
echo "OK: shell syntax"
)
( # step: The predicate is proven in BOTH directions
echo "--- step: The predicate is proven in BOTH directions"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards content-pipeline-fail-closed-guard--humanizer-predicate: step \"The predicate is proven in BOTH directions\" failed (exit $fg_rc)"' EXIT
bash 19-humanizer/test/test-humanizer-rule-check.sh
)
( # step: The banned character is not in the pattern
echo "--- step: The banned character is not in the pattern"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards content-pipeline-fail-closed-guard--humanizer-predicate: step \"The banned character is not in the pattern\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
# A directed check for the exact regression: reintroducing the literal
# em-dash character into a SEARCH PATTERN is what made the gate
# inverted. Two deliberate narrowings, because a guard that fires on
# anything else is the false-positive class this change set exists to
# remove:
#   1. comments are STRIPPED -- prose describing the defect is not the
#      defect, and a guard that fires on its own explanation is useless;
#   2. only lines that also invoke `grep` are measured -- the shared
#      assert/warn_only harness prints an em dash in its OUTPUT
#      formatting on every skill's QC script, and that is not a pattern.
sed 's/[[:space:]]*#.*$//' 19-humanizer/qc-humanizer.sh > /tmp/humanizer-code-only.sh
if grep -n 'grep' /tmp/humanizer-code-only.sh | grep $'—'; then
  echo "FAIL: the literal em-dash character is back inside a search pattern in"
  echo "      19-humanizer/qc-humanizer.sh -- see the line above (T0-61). The check"
  echo "      would then pass precisely when the character it bans is present."
  exit 1
fi
echo "OK: no em-dash character inside any search pattern; the check matches rule language only"
)
( # step: The stripper itself is proven able to fail
echo "--- step: The stripper itself is proven able to fail"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards content-pipeline-fail-closed-guard--humanizer-predicate: step \"The stripper itself is proven able to fail\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
# A check that has only ever been observed passing has not been
# observed. Reintroduce the defect into a COPY and require a catch.
cp 19-humanizer/qc-humanizer.sh /tmp/qc-humanizer-mutated.sh
printf '%s\n' "warn_only \"x\" \"grep -qE 'em dash|"$'—'"' /dev/null\"" >> /tmp/qc-humanizer-mutated.sh
sed 's/[[:space:]]*#.*$//' /tmp/qc-humanizer-mutated.sh > /tmp/mutated-code-only.sh
if grep -n 'grep' /tmp/mutated-code-only.sh | grep -q $'—'; then
  echo "OK: the guard catches a reintroduced em-dash character inside a search pattern"
else
  echo "FAIL: the guard cannot detect the very regression it exists for"
  exit 1
fi
)
