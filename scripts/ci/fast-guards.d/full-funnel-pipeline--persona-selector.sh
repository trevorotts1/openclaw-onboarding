#!/usr/bin/env bash
# Folded from .github/workflows/full-funnel-pipeline.yml (job "persona-selector (web-dev funnel surface + A7)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
export RUNNER_TEMP="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
export GITHUB_ENV="$(mktemp)"
export PYTHONUNBUFFERED=1
( # step: Seed minimal persona fixture (clean CI has no OpenClaw install)
echo "--- step: Seed minimal persona fixture (clean CI has no OpenClaw install)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards full-funnel-pipeline--persona-selector: step \"Seed minimal persona fixture (clean CI has no OpenClaw install)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
# The canonical selector loads its persona pool from
# ~/.openclaw/workspace/data/coaching-personas, which only exists on an
# installed box. A clean CI checkout has none, so every task returns no
# persona. Seed a small leak-clean public-author fixture (committed at
# full-funnel-pipeline/ci-fixtures/coaching-personas) into a throwaway
# HOME so the test exercises the REAL selector against a real pool.
OC_HOME="${RUNNER_TEMP}/oc-home"
mkdir -p "${OC_HOME}/.openclaw/workspace/data"
cp -R 23-ai-workforce-blueprint/full-funnel-pipeline/ci-fixtures/coaching-personas \
      "${OC_HOME}/.openclaw/workspace/data/coaching-personas"
{
  echo "OC_TEST_HOME=${OC_HOME}"
  echo "OPENCLAW_PLATFORM=mac"
  echo "SCORING_MODE=heuristic"
  echo "PERSONA_CATEGORIES_PATH=${OC_HOME}/.openclaw/workspace/data/coaching-personas/persona-categories.json"
} >> "$GITHUB_ENV"
)
[ -s "$GITHUB_ENV" ] && { set -a; . "$GITHUB_ENV"; set +a; }
( # step: test-persona-selector.sh exits 0 with A7 PASS
echo "--- step: test-persona-selector.sh exits 0 with A7 PASS"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards full-funnel-pipeline--persona-selector: step \"test-persona-selector.sh exits 0 with A7 PASS\" failed (exit $fg_rc)"' EXIT
export HOME="${OC_TEST_HOME:-}"
set -euo pipefail
cd 23-ai-workforce-blueprint/scripts
bash test-persona-selector.sh | tee /tmp/tps.log
# Strip ANSI color codes before matching so the assertion is robust to
# terminal coloring. A7 = the web-dev funnel-surface tag-overlap check.
sed -E 's/\x1b\[[0-9;]*m//g' /tmp/tps.log > /tmp/tps.clean
grep -Eq "A7 Web-dev funnel-surface tags: +PASS" /tmp/tps.clean
echo "✓ persona selector functional; A7 web-dev funnel persona PASS"
)
[ -s "$GITHUB_ENV" ] && { set -a; . "$GITHUB_ENV"; set +a; }
( # step: specialist routing is department-agnostic (network-marketing->brunson, sketchnote->rohde)
echo "--- step: specialist routing is department-agnostic (network-marketing->brunson, sketchnote->rohde)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards full-funnel-pipeline--persona-selector: step \"specialist routing is department-agnostic (network-marketing->brunson, sketchnote->rohde)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
# Hermetic: seeds the canonical 54-persona persona-categories.json into its own
# temp HOME and runs the heuristic path. Proves a clearly-named specialist is
# reachable regardless of department (the v14.22.0 routing fix).
bash 23-ai-workforce-blueprint/scripts/test-persona-selector-specialist-routing.sh
)
[ -s "$GITHUB_ENV" ] && { set -a; . "$GITHUB_ENV"; set +a; }
( # step: sticky-cache staleness is enforced (needs_review busts; craft survives variety)
echo "--- step: sticky-cache staleness is enforced (needs_review busts; craft survives variety)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards full-funnel-pipeline--persona-selector: step \"sticky-cache staleness is enforced (needs_review busts; craft survives variety)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
# Hermetic: temp HOME + temp sqlite DB, heuristic path. Regression guard for the
# v14.23.3 fix — a flagged-stale (needs_review=1) sticky row must bust the cache
# and re-score (so a (operations, design) row cannot stay locked on sinek after
# the craft fix made rohde the winner), the craft specialist must survive
# anti-repetition variety, and trusted rows must still be honored.
bash 23-ai-workforce-blueprint/scripts/test-persona-selector-stickiness-staleness.sh
)
[ -s "$GITHUB_ENV" ] && { set -a; . "$GITHUB_ENV"; set +a; }
