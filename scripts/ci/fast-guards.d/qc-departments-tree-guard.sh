#!/usr/bin/env bash
# Folded from .github/workflows/qc-departments-tree-guard.yml (job "QC measures the tree the repairer writes to"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
export OPENCLAW_PLATFORM='mac'
( # step: Syntax-check the changed shell and Python
set -e -o pipefail
set -euo pipefail
bash -n 23-ai-workforce-blueprint/scripts/qc-completeness.sh
bash -n 23-ai-workforce-blueprint/scripts/migrate-existing-workforce.sh
bash -n tests/unit/qc-departments-tree-resolution.test.sh
python3 -m py_compile \
  23-ai-workforce-blueprint/scripts/_qc_paths.py \
  23-ai-workforce-blueprint/scripts/_qc_company_info.py \
  23-ai-workforce-blueprint/scripts/department-floor.py
echo "OK: syntax checks passed"
)
( # step: Run the departments-tree resolution suite (8 scenarios, 12 assertions)
set -e -o pipefail
set -uo pipefail
# The GitHub runner filesystem is case-SENSITIVE, so scenario 5
# (case-drifted 'Sales' vs 'sales') is a real test here. On a
# case-insensitive macOS volume it passes trivially.
chmod +x tests/unit/qc-departments-tree-resolution.test.sh
bash tests/unit/qc-departments-tree-resolution.test.sh
)
( # step: Company-root resolution per layout
set -e -o pipefail
set -euo pipefail
bash -n 32-command-center-setup/scripts/materialize-dept-agents.sh
python3 tests/unit/test_company_root_resolution.py
bash 23-ai-workforce-blueprint/scripts/test-gate-company-dir-resolution.sh
)
