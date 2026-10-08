#!/usr/bin/env bash
# Folded from .github/workflows/u116-comms-audience-trigger-guard.yml (job "Communication trigger + audience-confirmation prompt — page/blog/email/SMS/social"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
export OPENCLAW_PLATFORM='mac'
( # step: Compile the seam + the comms trigger + persona_blend.py
set -e
python3 -m py_compile shared-utils/persona_for_job.py
python3 -m py_compile shared-utils/comms_audience_trigger.py
python3 -m py_compile 23-ai-workforce-blueprint/scripts/persona_blend.py
)
( # step: U1/A-U1 — persona_for_job.py self-test
set -e
python3 shared-utils/persona_for_job.py --self-test
)
( # step: comms_audience_trigger.py self-test
set -e
python3 shared-utils/comms_audience_trigger.py --self-test
)
( # step: persona_blend.py regression suite (T1-T13, must stay green)
set -e
python3 23-ai-workforce-blueprint/scripts/test-persona-blend-matcher.py
)
( # step: A-U5 scoped-bundle regression suite (force_content_task must not disturb scope_hint)
set -e
python3 23-ai-workforce-blueprint/scripts/test-a-u5-scoped-bundle.py
)
( # step: U116 — communication trigger + audience-confirmation proof
set -e
python3 tests/unit/u116-comms-audience-trigger-proof.test.py
)
