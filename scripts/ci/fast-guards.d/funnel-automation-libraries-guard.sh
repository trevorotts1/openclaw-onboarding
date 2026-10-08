#!/usr/bin/env bash
# Folded from .github/workflows/funnel-automation-libraries-guard.yml (job "Funnel/automation libraries + FAB-QC gate guard"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Install pytest
set -e
pip install pytest
)
( # step: Library drift gate (disk <-> index <-> link map; persona crosswalk; portable indexes)
set -e
python3 scripts/check-funnel-automation-library-drift.py
)
( # step: Persona crosswalk gate (0 unresolved persona refs; canonical targets)
set -e
python3 shared-utils/persona_crosswalk.py --validate
)
( # step: FAB-QC gate guard (rubric + scorer + producer + crosswalk + call-sites)
set -e
bash scripts/guard-fab-qc-gate.sh
)
( # step: Matcher selftests
set -e
python3 44-convert-and-flow-operator/automation-templates/_matcher/flex.py
python3 44-convert-and-flow-operator/automation-templates/_matcher/cli.py --selftest
python3 06-ghl-install-pages/tools/funnel_matcher_cli.py --selftest
)
( # step: Persona-bundle ladder + copy-stage blend-seam selftests (B-U1/B-U3/B-U6)
set -e
python3 06-ghl-install-pages/tools/persona_bundle_ladder.py
python3 49-signature-funnel/scripts/copy_persona_blend_seam.py --self-test
)
( # step: Matcher + FAB-QC + producer + crosswalk pytest suites
set -e
python3 -m pytest 06-ghl-install-pages/tests/test_funnel_matcher.py \
                  06-ghl-install-pages/tests/test_v2_dispatcher.py \
                  06-ghl-install-pages/tests/test_prove_skill6_block_u22.py \
                  06-ghl-install-pages/tests/test_a_u7_convergence.py \
                  06-ghl-install-pages/tests/test_a_u9_exemplar_injection.py \
                  44-convert-and-flow-operator/tests/test_automation_matcher.py \
                  49-signature-funnel/scripts/test_copy_persona_blend_seam.py -q
python3 tests/unit/fab-qc.test.py
python3 tests/unit/fab-artifact.test.py
python3 tests/unit/persona-crosswalk.test.py
)
( # step: Page-QC v2 (U25) + comms-conformance (U117) suites + mutation-proof guards
set -e
python3 tests/unit/page-qc.test.py
bash tests/unit/page-qc-gate-guard.test.sh
python3 tests/unit/u117-comms-qc-conformance.test.py
bash tests/unit/u117-comms-qc-guard.test.sh
)
( # step: Exemplar-injection selftest + acceptance suite (A-U9)
set -e
python3 shared-utils/exemplar_injection.py
python3 06-ghl-install-pages/tools/skill6_convergence.py
python3 -m pytest shared-utils/test_exemplar_injection.py -q
)
( # step: U22/B-U8 — Skill-6 persona-unification block operator-box proof run
set -e
python3 06-ghl-install-pages/scripts/prove_skill6_block_u22.py
)
