#!/usr/bin/env bash
# Folded from .github/workflows/skill-frontmatter-version-guard.yml (job "SKILL.md frontmatter vs skill-version.txt drift guard"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check the gate script
set -e
bash -n scripts/qc-assert-skill-frontmatter-version.sh
)
( # step: Self-test the gate (must fail on a mismatch fixture, pass on a match fixture)
set -e
chmod +x scripts/qc-assert-skill-frontmatter-version.sh
bash scripts/qc-assert-skill-frontmatter-version.sh --self-test
)
( # step: Run frontmatter/skill-version drift gate (must pass)
set -e
chmod +x scripts/qc-assert-skill-frontmatter-version.sh
bash scripts/qc-assert-skill-frontmatter-version.sh
)
