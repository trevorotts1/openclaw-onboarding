#!/usr/bin/env bash
# tests/unit/u105-fallback-provider-selection.test.sh
#
# Verifies that all fallback examples in the Summarize-YouTube documentation
# name the fallback provider explicitly via --provider <name>.
#
# The bug documented in U105: the fallback command was byte-identical to the
# primary command — a self-chained retry that re-runs the same provider that
# just failed. Every retry command must select a different provider.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed.
#
# Mutation proof: change the provider flag on any fallback line and this
# test catches it (assertion (A) or (B)).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXAMPLES="$REPO_ROOT/16-summarize-youtube/EXAMPLES.md"
FULL_GUIDE="$REPO_ROOT/16-summarize-youtube/summarize-youtube-full.md"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== u105-fallback-provider-selection.test.sh ==="
echo ""

# Helper: test if a string contains a pattern without grep flag collision
contains() { printf '%s' "$1" | grep -qFe "$2"; }
not_contains() { printf '%s' "$1" | grep -vqFe "$2"; }

# ── (A) EXAMPLES.md: The Gemini fallback block must include --provider gemini ──
echo "--- (A) EXAMPLES.md — Gemini fallback selects --provider gemini ---"

# Extract the command inside the "Gemini fallback" example code block
FALLBACK_LINE_A=$(sed -n '/## Example 3 - Gemini fallback/,/^```$/p' "$EXAMPLES" \
  | grep -E '^\s*summarize ' \
  | head -1)

if contains "$FALLBACK_LINE_A" '--provider gemini'; then
  pass "(A) EXAMPLES.md fallback line includes --provider gemini"
else
  fail "(A) EXAMPLES.md fallback line is missing --provider gemini (got: $FALLBACK_LINE_A)"
fi

# ── (B) summarize-youtube-full.md — API Key Fallback Chain section ──────────────
echo ""
echo "--- (B) summarize-youtube-full.md — Fallback chain selects --provider gemini ---"

# Extract the fallback command from the "API Key Fallback Chain" section
FALLBACK_LINE_B=$(sed -n '/API Key Fallback Chain/,/## Practical Examples/p' "$FULL_GUIDE" \
  | grep -E '^\s+.*\|\|' \
  | grep -E 'summarize' \
  | head -1)

if contains "$FALLBACK_LINE_B" '--provider gemini'; then
  pass "(B) summarize-youtube-full.md fallback line includes --provider gemini"
else
  fail "(B) summarize-youtube-full.md fallback line is missing --provider gemini (got: $FALLBACK_LINE_B)"
fi

# ── (C) EXAMPLES.md: Primary command (Example 2) does NOT have --provider ───────
echo ""
echo "--- (C) EXAMPLES.md — Primary command (Example 2) has NO --provider flag ---"

PRIMARY_LINE_C=$(sed -n '/## Example 2 - OpenAI first/,/^```$/p' "$EXAMPLES" \
  | grep -E '^\s*summarize ' \
  | head -1)

if not_contains "$PRIMARY_LINE_C" '--provider'; then
  pass "(C) EXAMPLES.md primary command does not specify provider (uses default)"
else
  fail "(C) EXAMPLES.md primary command should NOT have --provider (got: $PRIMARY_LINE_C)"
fi

# ── (D) full guide: primary command has NO --provider ──────────────────────────
echo ""
echo "--- (D) summarize-youtube-full.md — Primary command has NO --provider flag ---"

# Find the first || chain; the left side is the primary command
PRIMARY_LINE_D=$(sed -n '/API Key Fallback Chain/,/## Practical Examples/p' "$FULL_GUIDE" \
  | grep -E '^\s+.*\|\|' \
  | grep -E 'summarize' \
  | head -1 \
  | sed 's/||.*//')

if not_contains "$PRIMARY_LINE_D" '--provider'; then
  pass "(D) summarize-youtube-full.md primary command does not specify provider"
else
  fail "(D) summarize-youtube-full.md primary command should NOT have --provider (got: $PRIMARY_LINE_D)"
fi

# ── (E) Edge case: --provider flag format consistency ──────────────────────────
echo ""
echo "--- (E) All --provider references in these files have a named value ---"

# Check that every --provider appearance has a value after it
MISSING_VALUE=0
while IFS= read -r line; do
  if ! printf '%s' "$line" | grep -qFe '--provider'; then
    continue
  fi
  rest="${line#*--provider}"
  rest="${rest# }"  # strip leading space
  rest="${rest#=}"  # strip leading =
  val="${rest%% *}"
  if [ -z "$val" ]; then
    fail "(E) --provider has no value on line: $line"
    MISSING_VALUE=$((MISSING_VALUE+1))
  fi
done < <(grep -rnFe '--provider' "$EXAMPLES" "$FULL_GUIDE" 2>/dev/null || true)

if [ "$MISSING_VALUE" -eq 0 ]; then
  pass "(E) All --provider references have a value"
fi

# ── Final summary ──────────────────────────────────────────────────────────────
echo ""
echo "================================================="
echo "Results: $PASS passed, $FAIL failed"
echo "================================================="

if [ "$FAIL" -eq 0 ]; then
  echo "ALL TESTS PASSED"
  exit 0
else
  echo "TESTS FAILED"
  exit 1
fi
