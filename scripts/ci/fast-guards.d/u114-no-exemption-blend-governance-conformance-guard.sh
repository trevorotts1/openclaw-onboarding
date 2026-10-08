#!/usr/bin/env bash
# Folded from .github/workflows/u114-no-exemption-blend-governance-conformance-guard.yml (job "No-exemption blend-governance conformance — Skill 51/58/Anthology(54/59)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
export OPENCLAW_PLATFORM='mac'
( # step: Compile the sanctioned governance seams
set -e
python3 -m py_compile shared-utils/persona_for_job.py
python3 -m py_compile shared-utils/tone-writing-core/tone_persona_autopick.py
python3 -m py_compile 51-signature-presentation/scripts/blend_voice_governance.py
python3 -m py_compile 58-podcast-production-engine/scripts/blend_voice_governance.py
)
( # step: U114 — no-exemption blend-governance conformance proof (static + behavioral + mutation + regression)
set -e
python3 tests/unit/u114-no-exemption-blend-governance-conformance.test.py
)
