#!/usr/bin/env bash
# Folded from .github/workflows/silent-success-guards.yml (job "ONB-46-001: a run with zero deliverables is never marked done"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Run the Skill 46 security + outcome-rule suite
echo "--- step: Run the Skill 46 security + outcome-rule suite"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards silent-success-guards--onb-46-001: step \"Run the Skill 46 security + outcome-rule suite\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
node 46-kie-callback-relay/test/security.test.mjs
)
( # step: The outcome rule has exactly ONE implementation
echo "--- step: The outcome rule has exactly ONE implementation"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards silent-success-guards--onb-46-001: step \"The outcome rule has exactly ONE implementation\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
node - <<'NODE'
const fs = require('fs');
const f  = '46-kie-callback-relay/box-kv-poller.js';
// Strip comments so only executable code is measured.
const bare = fs.readFileSync(f, 'utf8')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/^[ \t]*\/\/.*$/gm, '');
const delegations = (bare.match(/this\._resolveOutcome\(/g) || []).length;
const literals    = (bare.match(/status:\s*'done'/g) || []).length;
if (delegations !== 2) {
  console.error(`FAIL: expected 2 delegations to _resolveOutcome, found ${delegations}`);
  process.exit(1);
}
if (literals !== 1) {
  console.error(`FAIL: expected exactly 1 executable status:'done' literal ` +
                `(inside _resolveOutcome), found ${literals} — a path re-inlined the rule`);
  process.exit(1);
}
console.log('OK: both resolution paths delegate; one status:\'done\' literal, inside the shared rule');
NODE
)
