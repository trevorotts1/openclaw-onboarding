#!/usr/bin/env bash
# Folded from .github/workflows/u98-blend-governs-product-voice-engines-guard.yml (job "Blend GOVERNS the product-voice engines — Skill 35/51/58/Anthology(54/59)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
export OPENCLAW_PLATFORM='mac'
( # step: Compile the U1/U5 seams + all four engine call sites
set -e
python3 -m py_compile 23-ai-workforce-blueprint/scripts/persona_blend.py
python3 -m py_compile shared-utils/persona_for_job.py
python3 -m py_compile shared-utils/tone-writing-core/tone_persona_autopick.py
python3 -m py_compile 35-social-media-planner/scripts/daily_blend_bundle.py
python3 -m py_compile 51-signature-presentation/scripts/blend_voice_governance.py
python3 -m py_compile 58-podcast-production-engine/scripts/blend_voice_governance.py
)
( # step: U1 — persona_for_job.py self-test (incl. blend mode)
set -e
python3 shared-utils/persona_for_job.py --self-test
)
( # step: Skill 35 — daily_blend_bundle.py self-test (7 distinct day scopes)
set -e
python3 35-social-media-planner/scripts/daily_blend_bundle.py --self-test
)
( # step: Skill 51 — blend_voice_governance.py self-test (4 phases, sacred structure pinned)
set -e
python3 51-signature-presentation/scripts/blend_voice_governance.py --self-test
)
( # step: Skill 58 — blend_voice_governance.py self-test (4 style engines, format pinned)
set -e
python3 58-podcast-production-engine/scripts/blend_voice_governance.py --self-test
)
( # step: Anthology — tone_persona_autopick.py self-test (N/A governed, client-named untouched)
set -e
python3 shared-utils/tone-writing-core/tone_persona_autopick.py --self-test
)
( # step: Anthology structure — tone-core sync (52/53/54, byte-for-byte)
set -e
python3 52-avatar-alchemist/scripts/verify_tone_core_sync.py
python3 53-book-writer/scripts/verify_tone_core_sync.py
python3 54-anthology-writer/scripts/verify_tone_core_sync.py
)
( # step: U98 — blend-GOVERNS product-voice-engines proof (all four legs)
set -e
python3 tests/unit/u98-blend-governs-product-voice-engines.test.py
)
