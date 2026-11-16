#!/usr/bin/env bash
# Folded from .github/workflows/lean-bootstrap-guard.yml (job "compact core + pointer stamping contracts"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
# The old job ran on Python 3.9 (the interpreter client Macs run). fast-guards runs 3.11 and ubuntu-latest has no
# setup-python 3.9 build, so install 3.9 here with uv and put it first on PATH as python3 for every step below.
command -v uv >/dev/null 2>&1 || python3 -m pip install --quiet --disable-pip-version-check uv || { echo "::error::fast-guards lean-bootstrap-guard: could not install uv"; exit 1; }
uv python install 3.9 || { echo "::error::fast-guards lean-bootstrap-guard: could not install Python 3.9"; exit 1; }
FG_PY39="$(uv python find 3.9)" && FG_SHIM="$(mktemp -d)" && ln -s "$FG_PY39" "$FG_SHIM/python3" && ln -s "$FG_PY39" "$FG_SHIM/python" || { echo "::error::fast-guards lean-bootstrap-guard: no Python 3.9"; exit 1; }
export PATH="$FG_SHIM:$PATH"
python3 --version | grep -q '^Python 3\.9\.' || { echo "::error::fast-guards lean-bootstrap-guard: python3 is not 3.9"; exit 1; }
( # step: compact-bootstrap contract tests
echo "--- step: compact-bootstrap contract tests"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards lean-bootstrap-guard: step \"compact-bootstrap contract tests\" failed (exit $fg_rc)"' EXIT
chmod +x tests/unit/compact-bootstrap.test.sh
bash tests/unit/compact-bootstrap.test.sh
)
( # step: bootstrap-pointerize contract tests
echo "--- step: bootstrap-pointerize contract tests"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards lean-bootstrap-guard: step \"bootstrap-pointerize contract tests\" failed (exit $fg_rc)"' EXIT
chmod +x tests/unit/bootstrap-pointerize.test.sh
bash tests/unit/bootstrap-pointerize.test.sh
)
( # step: BEGIN/END marker pairs match; Skill 38 heals orphaned END-only stanzas
echo "--- step: BEGIN/END marker pairs match; Skill 38 heals orphaned END-only stanzas"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards lean-bootstrap-guard: step \"BEGIN/END marker pairs match; Skill 38 heals orphaned END-only stanzas\" failed (exit $fg_rc)"' EXIT
python3 tests/unit/test_bootstrap_marker_pairs.py
)
( # step: Scheduled jobs are COMMAND kind and name no model
echo "--- step: Scheduled jobs are COMMAND kind and name no model"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards lean-bootstrap-guard: step \"Scheduled jobs are COMMAND kind and name no model\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
for f in scripts/bootstrap-compact-weekly.sh scripts/bootstrap-validate-daily.sh; do
  if grep -nE '(agnes|claude-|gpt-|gemini-[0-9]|deepseek|kimi|glm-)' "$f"; then
    echo "FAIL: $f names a model. It must read the box default from config." >&2
    exit 1
  fi
done
# The registrations must go through _ensure_health_cron, which always
# builds a command-kind cron.
grep -q '_ensure_health_cron "bootstrap-validate-daily"' scripts/ensure-pipeline-crons.sh
grep -q '_ensure_health_cron "bootstrap-compact-weekly"' scripts/ensure-pipeline-crons.sh
# And the weekly one must carry its timezone, or it can land BEFORE the
# 03:00 America/New_York skill update it is supposed to follow.
grep -q '"bootstrap-compact-weekly" "30 4 \* \* 0"  "bootstrap-compact-weekly.sh" "America/New_York"' \
  scripts/ensure-pipeline-crons.sh
echo "OK: both crons are command-kind, model-free, and the weekly job is zone-pinned."
)
( # step: The weekly switch defaults to report
echo "--- step: The weekly switch defaults to report"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards lean-bootstrap-guard: step \"The weekly switch defaults to report\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
test -f config/bootstrap-compact.conf.example
grep -q '^report$' config/bootstrap-compact.conf.example
grep -q 'MODE="report"' scripts/bootstrap-compact-weekly.sh
echo "OK: the shipped default is report (writes nothing)."
)
