#!/usr/bin/env bash
# Folded from .github/workflows/kie-prompt-enforcer-guard.yml (job "KIE prompt enforcer guard (one enforcer, no separate band)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Enforcer behavior + declared gates import it and keep no band
set -e
python3 tests/unit/kie-prompt-enforcer-and-gates.test.py
)
( # step: Embedded enforcer copies are locked to the source and enforce the same rule without shared-utils
set -e
python3 tests/unit/kie-prompt-enforcer-embedded-lock.test.py
)
( # step: Every gate self-test passes rule 12 (79 percent rejected, 95 and 100 percent pass, 101 percent rejected)
set -e
export HOME="$(mktemp -d)"
python3 scripts/qc_gip_agnes_prompt_band.py --self-test
python3 66-kie-image/scripts/validate_prompt.py --self-test
python3 67-kie-video/scripts/validate_prompt.py --self-test
python3 68-kie-audio/scripts/validate_audio_request.py --self-test
python3 shared-utils/social_prompt_compiler.py --self-test
python3 35-social-media-planner/scripts/test_pregen_prompt_gate.py
python3 45-design-intelligence-library/scripts/prove_gip_prompt_floor.py --self-test
python3 45-design-intelligence-library/scripts/test_prompt_band_cli.py
python3 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/prove_pres_prompt_floor.py --self-test
)
