#!/usr/bin/env bash
# Folded from .github/workflows/ledger-truth-gate.yml (job "Reject ledger rows claiming verified/done that git + check-run history cannot prove"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Check out trevorotts1/blackceo-command-center (second repository, as the workflows own checkout step did)
echo "--- step: Check out trevorotts1/blackceo-command-center (second repository, as the workflows own checkout step did)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards ledger-truth-gate: step \"Check out trevorotts1/blackceo-command-center (second repository, as the workflows own checkout step did)\" failed (exit $fg_rc)"' EXIT
rm -rf blackceo-command-center
test -n "${GH_TOKEN:-}" || { echo "GH_TOKEN is not set: fast-guards.yml passes secrets.GITHUB_TOKEN"; exit 1; }
git -c http.extraheader="AUTHORIZATION: basic $(printf 'x-access-token:%s' "$GH_TOKEN" | base64 | tr -d '[:space:]')" clone --quiet https://github.com/trevorotts1/blackceo-command-center.git blackceo-command-center
)
( # step: Run the ledger-truth gate (every added verified/done row, re-derived from git + check-runs)
echo "--- step: Run the ledger-truth gate (every added verified/done row, re-derived from git + check-runs)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards ledger-truth-gate: step \"Run the ledger-truth gate (every added verified/done row, re-derived from git + check-runs)\" failed (exit $fg_rc)"' EXIT
export GH_TOKEN="${GH_TOKEN:-}"
export GATE_BASE="${FG_BASE_SHA:-}"
export GATE_HEAD="${FG_HEAD_SHA:-${GITHUB_SHA:-}}"
export GATE_CC_DIR=blackceo-command-center
set -euo pipefail
python3 scripts/ledger-truth-gate.py --base "$GATE_BASE" --head "$GATE_HEAD" --cc-dir "$GATE_CC_DIR"
)
