#!/usr/bin/env bash
# Folded from .github/workflows/skill23-role-floor-guard.yml (job "Build meets the role-library floor; reconcile repairs a below-floor tree"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
export OPENCLAW_PLATFORM='mac'
( # step: Build role folders (canonical slugs, full library floor, idempotent)
set -e
python3 tests/unit/test_build_library_role_floor.py
)
( # step: reconcile-role-floor.py (rename keeps how-tos, fills floor, no other client's lanes)
set -e
python3 tests/unit/test_reconcile_role_floor.py
)
