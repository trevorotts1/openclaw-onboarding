#!/usr/bin/env bash
# Folded from .github/workflows/u14-blueprint-section-map-guard.yml (job "Blueprint section-map crosswalk — 100% coverage + Section-4 hazard fix, both generations"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
export OPENCLAW_PLATFORM='mac'
( # step: persona_for_job.py compiles
set -e
python3 -m py_compile shared-utils/persona_for_job.py
)
( # step: persona_for_job.py self-test (never-naked contract, incl. blend mode)
set -e
python3 shared-utils/persona_for_job.py --self-test
)
( # step: _section-map.json is current (drift lock vs. the 99 on-disk blueprints)
set -e
python3 22-book-to-persona-coaching-leadership-system/scripts/build-section-map.py --check
)
( # step: U14 — 100% coverage + Section-4 load-contract hazard fix (both generations) + CHANGELOG backfill
set -e
python3 tests/unit/u14-blueprint-section-map.test.py
)
