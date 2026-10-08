#!/usr/bin/env bash
# Folded from .github/workflows/phase-6i-reachability-guard.yml (job "reachability"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: _cc_mtime is an integer under GNU stat and survives set -u
set -e
bash tests/unit/cc-mtime-portable.test.sh
)
( # step: slug readers accept `slug`; role-library pin follows symlinks
set -e
bash tests/unit/phase-6i-slug-readers.test.sh
)
