#!/usr/bin/env bash
# Folded from .github/workflows/updater-write-preflight-guard.yml (job "update-skills.sh refuses early on a root-owned workspace file"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: The updater still parses
set -e
bash -n update-skills.sh
)
( # step: The suite still parses
set -e
bash -n tests/unit/updater-write-preflight-permission-block.test.sh
)
( # step: Write pre-flight and PERMISSION BLOCK contract
set -e
bash tests/unit/updater-write-preflight-permission-block.test.sh
)
