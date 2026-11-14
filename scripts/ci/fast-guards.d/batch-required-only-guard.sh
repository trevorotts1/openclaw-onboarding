#!/usr/bin/env bash
# Batch pull requests (head branch batch/*) run ONLY the required checks: every pull_request
# workflow except the three that produce required checks must skip its jobs for batch/ heads.
set -e
cd "${GITHUB_WORKSPACE:-.}"
python3 scripts/ci/batch-required-only-check.py
python3 scripts/ci/batch-required-only-check.py --self-test
