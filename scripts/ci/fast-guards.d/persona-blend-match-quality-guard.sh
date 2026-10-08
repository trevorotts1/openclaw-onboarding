#!/usr/bin/env bash
# Folded from .github/workflows/persona-blend-match-quality-guard.yml (job "Persona-blend matcher — contract + regression-corpus + logging + e2e selectability"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
export OPENCLAW_PLATFORM='mac'
( # step: persona_blend.py compiles
set -e
python3 -m py_compile 23-ai-workforce-blueprint/scripts/persona_blend.py
)
( # step: W7 blend-matcher contract suite (46 tests, hermetic fixtures)
set -e
python3 23-ai-workforce-blueprint/scripts/test-persona-blend-matcher.py
)
( # step: P4-01/A-U13 — 40-case match-quality regression corpus (>=90% gate, REAL catalog)
set -e
python3 23-ai-workforce-blueprint/scripts/test-persona-match-regression-corpus.py
)
( # step: P4-02 — four-slot SYNERGY directive contract (voice/audience/substance/task)
set -e
python3 23-ai-workforce-blueprint/scripts/test-p4-02-synergy-directive.py
)
( # step: A-U2 — Blend Directive v2 (structured voice-attribute block, byte-identical v1 degrade)
set -e
python3 23-ai-workforce-blueprint/scripts/test-a-u2-blend-directive-v2.py
)
( # step: A-U5 — per-page/scoped blends (scope_hint, fixture funnel, back-compat)
set -e
python3 23-ai-workforce-blueprint/scripts/test-a-u5-scoped-bundle.py
)
( # step: U115 — per-part/per-persona governance (ONB leg — decompose, per-part loop, part-persona-map, back-compat)
set -e
python3 23-ai-workforce-blueprint/scripts/test-u115-part-persona-governance.py
)
( # step: P4-01 — match-score-distribution logging (drift observability)
set -e
python3 tests/unit/persona-match-score-log.test.py
)
( # step: P4-01 — book-to-persona -> matcher-selectable end-to-end round trip
set -e
python3 tests/unit/p4-01-book-to-persona-matcher-selectable-e2e.test.py
)
( # step: D6 — Skill-22 duality-tag write-side contract (orchestrator)
set -e
chmod +x tests/unit/persona-duality-tags-pipeline.test.sh
bash tests/unit/persona-duality-tags-pipeline.test.sh
)
( # step: A-U3 — schema-1.4 enrichment complete (N/N coverage + extended-vocab gate)
set -e
python3 tests/unit/schema14-enrichment-complete.test.py
)
( # step: A-U3 — persona_fleet.py publish path carries the new fields (fail-first proven)
set -e
python3 tests/unit/persona-fleet-schema14-sync.test.py
)
( # step: persona-selector-v2.py compiles
set -e
python3 -m py_compile 23-ai-workforce-blueprint/scripts/persona-selector-v2.py
)
( # step: A-U4 — conversion_goal first-class input (source ladder, slot 5, decision receipt, no-contamination)
set -e
python3 23-ai-workforce-blueprint/scripts/test-a-u4-conversion-goal.py
)
( # step: persona_grounding_health_probe.py compiles
set -e
python3 -m py_compile shared-utils/persona_grounding_health_probe.py
)
( # step: fleet_refresh_runner.py compiles
set -e
python3 -m py_compile shared-utils/fleet_refresh_runner.py
)
( # step: A-U12 — blend observability probe (persona_match advisory, persona_grounding_degraded, non-gating)
set -e
python3 tests/unit/persona-grounding-health-probe.test.py
)
