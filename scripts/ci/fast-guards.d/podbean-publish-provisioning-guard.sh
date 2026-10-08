#!/usr/bin/env bash
# Folded from .github/workflows/podbean-publish-provisioning-guard.yml (job "Podbean publish-proxy + identity provisioning guard (S58-U15)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Run podbean-publish-provisioning tests (incl. mutation proof)
set -e
chmod +x tests/unit/podbean-publish-provisioning.test.sh
bash tests/unit/podbean-publish-provisioning.test.sh
)
