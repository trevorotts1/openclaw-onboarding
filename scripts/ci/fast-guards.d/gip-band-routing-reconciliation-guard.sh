#!/usr/bin/env bash
# Folded from .github/workflows/gip-band-routing-reconciliation-guard.yml (job "GIP band<->routing reconciliation — prompt-bands.json v2 + Ideogram text-bearing band + no-nano-banana lock"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: prompt-bands.json is valid JSON, holds no length numbers, and has no Ideogram text-bearing band
set -e
python3 -c "
import json
d = json.load(open('45-design-intelligence-library/library/_system/prompt-bands.json'))
assert d['length_source']['enforcer'] == 'shared-utils/kie_prompt_enforcer.py'
bands = d['bands']
assert 'text_bearing_medium' not in bands, 'the Ideogram social band must not exist (owner order 2026-10-05)'
for bid, b in bands.items():
    for key in ('min', 'max'):
        assert key not in b, f'{bid} reintroduced a hard-coded {key}; length is KIE rule 12 via the shared enforcer'
    if b.get('text_bearing'):
        eps = [str(e).lower() for e in b.get('endpoints', [])]
        assert not any('nano-banana' in e for e in eps), f'{bid} lists a nano-banana endpoint'
        assert not any('ideogram' in e for e in eps), f'{bid} lists an Ideogram endpoint'
print('OK: prompt-bands.json v3 shape confirmed')
"
)
( # step: diu_validator.py / prove_gip_prompt_floor.py / test_prompt_band_cli.py compile
set -e
python3 -m py_compile 45-design-intelligence-library/scripts/diu_validator.py
python3 -m py_compile 45-design-intelligence-library/scripts/prove_gip_prompt_floor.py
python3 -m py_compile 45-design-intelligence-library/scripts/test_prompt_band_cli.py
)
( # step: GIP prompt-band self-test (fixture gate, incl. rule 12 boundaries + nano-banana/Ideogram assertions)
set -e
python3 45-design-intelligence-library/scripts/prove_gip_prompt_floor.py --self-test
)
( # step: GIP prompt-band CLI fail-first proof (real subprocess, incl. rule 12 boundary cases)
set -e
python3 45-design-intelligence-library/scripts/test_prompt_band_cli.py
)
( # step: pregen_prompt_gate.py compiles
set -e
python3 -m py_compile 35-social-media-planner/scripts/pregen_prompt_gate.py
)
( # step: Skill 35 pre-generation gate fail-first proof (real subprocess, incl. rule 12 boundary cases)
set -e
python3 35-social-media-planner/scripts/test_pregen_prompt_gate.py
)
( # step: Role-library content-manifest check (touched graphics role docs/SOPs re-stamped)
set -e
python3 23-ai-workforce-blueprint/scripts/hash-content-manifest.py --check
)
