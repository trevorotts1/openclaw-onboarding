#!/usr/bin/env bash
# Folded from .github/workflows/persona-task-mode-wiring-guard.yml (job "Leadership / Task-Mode fires at task time"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
export OPENCLAW_PLATFORM='mac'
( # step: Run persona-task-mode-wiring tests
set -e
chmod +x tests/unit/persona-task-mode-wiring.test.sh
bash tests/unit/persona-task-mode-wiring.test.sh
)
( # step: Section tagger / indexer agreement (coaching=Section3, leadership=Section4)
set -e
chmod +x tests/unit/section-tagger-indexer-agreement.test.sh
bash tests/unit/section-tagger-indexer-agreement.test.sh
)
( # step: move-task.py compiles + probe syntax-checks
set -e
python3 -m py_compile 32-command-center-setup/scripts/move-task.py
bash -n shared-utils/fleet-heartbeat-persona-probe.sh
)
( # step: move-task persona lifecycle gate
set -e
chmod +x tests/unit/move-task-persona-lifecycle.test.sh
bash tests/unit/move-task-persona-lifecycle.test.sh
)
( # step: no-naked-dispatch contract (FDN-2)
set -e
if [ -f tests/unit/no-naked-dispatch.test.sh ]; then
  echo "FDN-2 contract test present — enforcing."
  chmod +x tests/unit/no-naked-dispatch.test.sh
  bash tests/unit/no-naked-dispatch.test.sh
else
  echo "::warning::FDN-2 no-naked-dispatch contract test (tests/unit/no-naked-dispatch.test.sh) not present yet — this gate self-activates when FDN-2 merges."
fi
)
