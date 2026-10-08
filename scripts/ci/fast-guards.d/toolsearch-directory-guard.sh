#!/usr/bin/env bash
# Folded from .github/workflows/toolsearch-directory-guard.yml (job "tools.toolSearch directory-mode shape + drift guard"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Run toolsearch-directory-shape tests
set -e
chmod +x tests/unit/toolsearch-directory-shape.test.sh
bash tests/unit/toolsearch-directory-shape.test.sh
)
