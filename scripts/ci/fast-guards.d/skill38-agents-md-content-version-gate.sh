#!/usr/bin/env bash
# Folded from .github/workflows/skill38-agents-md-content-version-gate.yml (job "05-update-agents-md.sh is wired in; the 9 qc gates check the LIVE box, not the shipped source"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check every touched script
set -e -o pipefail
set -euo pipefail
for f in update-skills.sh scripts/onboarding-state.sh lib-onboarding-state.sh \
         38-conversational-ai-system/scripts/05-update-agents-md.sh \
         38-conversational-ai-system/scripts/11-run-qc-checklist.sh \
         38-conversational-ai-system/scripts/qc-segmentation.sh \
         38-conversational-ai-system/scripts/qc-multi-tenant.sh \
         38-conversational-ai-system/scripts/qc-client-test-mode.sh \
         38-conversational-ai-system/scripts/qc-zhc-tag-prefix.sh \
         38-conversational-ai-system/scripts/qc-ab-testing.sh \
         38-conversational-ai-system/scripts/qc-zhc-pixel.sh \
         38-conversational-ai-system/scripts/qc-webhook-chaining.sh \
         38-conversational-ai-system/scripts/qc-workflow-exits.sh \
         38-conversational-ai-system/scripts/qc-tool-gating.sh; do
  bash -n "$f"
done
echo "all touched scripts parse clean"
)
( # step: (i) 05-update-agents-md.sh is wired into the automated pipeline
set -e -o pipefail
set -euo pipefail
bash tests/unit/skill38-agents-md-wiring.test.sh
echo "skill38-agents-md-wiring.test.sh: PASS"
)
( # step: (ii) the 9 qc gates are content-version-aware (mutation-proven both directions)
set -e -o pipefail
set -euo pipefail
bash tests/unit/skill38-qc-gates-live-agentsmd-awareness.test.sh
echo "skill38-qc-gates-live-agentsmd-awareness.test.sh: PASS"
)
( # step: Existing per-gate negative-fixture tests still pass (no regression)
set -e -o pipefail
set -euo pipefail
cd 38-conversational-ai-system/scripts
for t in qc-segmentation.test.sh qc-multi-tenant.test.sh qc-client-test-mode.test.sh \
         qc-ab-testing.test.sh qc-zhc-pixel.test.sh qc-webhook-chaining.test.sh \
         qc-workflow-exits.test.sh qc-tool-gating.test.sh; do
  echo "--- $t ---"
  bash "$t"
done
)
( # step: obs_verify_skill / oc_gate_skill regression suites still pass
set -e -o pipefail
set -euo pipefail
bash tests/unit/onboarding-state-obs-api.test.sh
bash tests/unit/install-state-fail-open.test.sh
)
