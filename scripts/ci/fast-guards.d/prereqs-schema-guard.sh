#!/usr/bin/env bash
# Folded from .github/workflows/prereqs-schema-guard.yml (job "PREREQS.json schema lint + runtime enforcement test"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check the gate scripts
set -e
bash -n scripts/qc-prereqs-json.sh
bash -n scripts/test-prereqs-schema-enforcement.sh
bash -n shared-utils/check-skill-prereqs.sh
)
( # step: Compile-check the embedded Python (compile, not ast.parse)
set -e
python3 - <<'PY'
import re, sys
for path in ("scripts/qc-prereqs-json.sh", "shared-utils/check-skill-prereqs.sh"):
    src = open(path).read()
    blocks = re.findall(r"<<'PYEOF'\n(.*?)\nPYEOF", src, re.S)
    if not blocks:
        sys.exit(f"{path}: no embedded python block found")
    for block in blocks:
        compile(block, path, "exec")
    print(f"OK {path} ({len(blocks)} python block(s) compiled)")
PY
)
( # step: Runtime enforcement test (dependency present AND absent)
set -e
bash scripts/test-prereqs-schema-enforcement.sh
)
( # step: PREREQS.json schema lint (must pass)
set -e
bash scripts/qc-prereqs-json.sh --verbose
)
