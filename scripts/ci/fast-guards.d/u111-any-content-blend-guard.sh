#!/usr/bin/env bash
# Folded from .github/workflows/u111-any-content-blend-guard.yml (job ""Any content" blend-governance proof — email/blog/newsletter/SMS-NOT-FOUND"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
export OPENCLAW_PLATFORM='mac'
( # step: Compile the U1 seam + both engine call sites
set -e
python3 -m py_compile shared-utils/persona_for_job.py
python3 -m py_compile 50-email-engine/tools/persona_canonical.py
python3 -m py_compile 57-social-media-in-a-box/scripts/persona_adapter.py
)
( # step: U1/A-U1 — persona_for_job.py self-test (18 cases, incl. blend mode)
set -e
python3 shared-utils/persona_for_job.py --self-test
)
( # step: Skill 57 persona_adapter.py self-test (9 cases, incl. U111 blend passthrough)
set -e
python3 57-social-media-in-a-box/scripts/persona_adapter.py --self-test
)
( # step: U111 — any-content blend-governance proof (email/blog/newsletter/SMS-NOT-FOUND)
set -e
python3 tests/unit/u111-any-content-blend-proof.test.py
)
