#!/usr/bin/env bash
# Batch pull requests (head branch batch/*) run ONLY the required checks: every pull_request
# workflow except the three that produce required checks must skip its jobs for batch/ heads.
set -e
cd "${GITHUB_WORKSPACE:-.}"
# This guard only fires when .github/workflows/** changes, and the folded-guards
# runner installs no third-party packages. Install the one dependency the check
# imports (PyYAML), the same way the other folded guards install theirs.
python3 -m pip install --quiet --disable-pip-version-check pyyaml
python3 scripts/ci/batch-required-only-check.py
python3 scripts/ci/batch-required-only-check.py --self-test
