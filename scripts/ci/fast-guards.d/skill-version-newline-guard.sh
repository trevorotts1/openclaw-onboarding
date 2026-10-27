#!/usr/bin/env bash
# Folded from .github/workflows/skill-version-newline-guard.yml (job "skill-version.txt trailing-newline lint"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check the gate script
set -e
bash -n scripts/qc-assert-skill-version-newline.sh
)
( # step: Self-test the gate (fails on a no-newline fixture, passes on a clean one)
set -e
chmod +x scripts/qc-assert-skill-version-newline.sh
bash scripts/qc-assert-skill-version-newline.sh --self-test
)
( # step: Run trailing-newline lint (must pass)
set -e
chmod +x scripts/qc-assert-skill-version-newline.sh
bash scripts/qc-assert-skill-version-newline.sh
)
( # step: A commit's message must name the Skill 38 version that commit contains (PBB-263 D1)
set -e
python3 -B scripts/qc-assert-commit-version-claim.py --self-test
python3 -B scripts/qc-assert-commit-version-claim.py --ci
)
