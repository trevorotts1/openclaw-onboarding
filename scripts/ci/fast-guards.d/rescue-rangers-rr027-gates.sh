#!/usr/bin/env bash
# Folded from .github/workflows/rescue-rangers-rr027-gates.yml (job "RR-027 gates (parse + scrub + no-argv-key + regressions)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Shell syntax gates
set -e
bash -n shared-utils/rescue-env.sh
sh -n shared-utils/rescue-env.sh
bash -n 65-rescue-receiver/wire.sh
bash -n 65-rescue-receiver/rescue-poll.sh
sh -n 65-rescue-receiver/rescue-poll.sh
bash -n scripts/seed-rr-agent-map.sh
)
( # step: Helper contract (parse / get / scrub / header-file / private tmp)
set -e
bash tests/unit/rr027-rescue-env.test.sh
sh tests/unit/rr027-rescue-env.test.sh
)
( # step: Consumer leak gates (child env + argv + logs, sentinel-driven)
set -e
bash tests/unit/rr027-no-credential-in-child-env.test.sh
sh tests/unit/rr027-no-credential-in-child-env.test.sh
)
( # step: Receiver additive-fields regression (RR-004 pairing)
set -e
bash tests/rescue/RR-004/test_receiver_additive_fields.sh
)
( # step: Dependency regressions (RR-017 / RR-003 / RR-006 / RR-021 batteries)
set -e
python3 tests/unit/rescue-contract-rr017.test.py
python3 tests/unit/rescue-contract-rr003.test.py
python3 tests/rescue/RR-006/test_legacy_writer_retired.py
python3 tests/rescue/RR-021/test_receiver_work_preserved.py
)
