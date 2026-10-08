#!/usr/bin/env bash
# Folded from .github/workflows/rescue-rangers-rr015-gates.yml (job "RR-015 gates (shared admission client + EWS escalation paths)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Python syntax + import hygiene
set -e
python3 -m py_compile scripts/lib/rescue_admission.py
python3 -m py_compile 60-zhc-early-warning-system/scripts/ews_alert.py
python3 -m py_compile 60-zhc-early-warning-system/scripts/ews_common.py
python3 -m py_compile 60-zhc-early-warning-system/scripts/ews_fleet.py
python3 -m py_compile 60-zhc-early-warning-system/scripts/ews_ledger.py
)
( # step: Admission client self-test (offline, injected transport)
set -e
python3 scripts/lib/rescue_admission.py --self-test
)
( # step: RR-015 battery (stale P1 + dead-man, mocked admission endpoint)
set -e
python3 tests/rescue/RR-015/test_rescue_admission_client.py
)
( # step: EWS aggregate self-tests (escalate + dead-man rewiring)
set -e
python3 60-zhc-early-warning-system/scripts/ews_alert.py --self-test
python3 60-zhc-early-warning-system/scripts/ews_fleet.py --self-test
python3 60-zhc-early-warning-system/scripts/ews_ledger.py --self-test
)
( # step: Dependency regressions (RR-017 / RR-003 / RR-006 / RR-021 batteries)
set -e
python3 tests/unit/rescue-contract-rr017.test.py
python3 tests/unit/rescue-contract-rr003.test.py
python3 tests/rescue/RR-006/test_legacy_writer_retired.py
python3 tests/rescue/RR-021/test_receiver_work_preserved.py
bash tests/rescue/RR-004/test_receiver_additive_fields.sh
)
