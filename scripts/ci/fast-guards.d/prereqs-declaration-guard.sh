#!/usr/bin/env bash
# Folded from .github/workflows/prereqs-declaration-guard.yml (job "Declared-mandatory dependencies are present and resolvable (T0-40)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check
set -e -o pipefail
set -euo pipefail
bash -n shared-utils/check-skill-prereqs.sh
bash -n scripts/qc-prereqs-json.sh
bash -n tests/unit/prereqs-declared-mandatory-skills.test.sh
python3 -c "import json; json.load(open('05-ghl-setup/PREREQS.json')); json.load(open('06-ghl-install-pages/PREREQS.json'))"
echo "syntax OK"
)
( # step: Declared-mandatory dependency suite
set -e -o pipefail
bash tests/unit/prereqs-declared-mandatory-skills.test.sh
)
