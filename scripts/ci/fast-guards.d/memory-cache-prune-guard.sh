#!/usr/bin/env bash
# Folded from .github/workflows/memory-cache-prune-guard.yml (job "memory maintenance prunes dead cache rows and never re-embeds"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check the scripts
set -e -o pipefail
set -euo pipefail
for f in 31-upgraded-memory-system/install.sh \
         31-upgraded-memory-system/scripts/memory-cache-prune.sh \
         31-upgraded-memory-system/scripts/memory-index-check.sh \
         tests/unit/memory-cache-prune.test.sh; do
  bash -n "$f"
done
echo "bash -n: PASS"
)
( # step: Run the memory maintenance suite
set -e -o pipefail
set -euo pipefail
bash tests/unit/memory-cache-prune.test.sh
echo "memory-cache-prune-guard: PASS"
)
