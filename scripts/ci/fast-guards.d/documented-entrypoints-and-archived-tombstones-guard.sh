#!/usr/bin/env bash
# Folded from .github/workflows/documented-entrypoints-and-archived-tombstones-guard.yml (job "Documented entry points resolve + archived skills are tombstones"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check the checker, the suites and the archived installers
set -e -o pipefail
set -euo pipefail
python3 -m py_compile docs/tools/check_documented_entrypoints.py
python3 -m py_compile tests/unit/documented-entrypoint-paths.test.py
python3 -m py_compile tests/unit/archived-skill-tombstones.test.py
for f in ./*-ARCHIVED/install.sh; do
  [ -f "$f" ] || continue
  bash -n "$f"
done
python3 -c 'import json,sys; json.load(open("docs/archived-skill-tombstones.json"))'
echo "syntax OK"
)
( # step: T2-07 — every documented entry point resolves
set -e -o pipefail
set -euo pipefail
python3 docs/tools/check_documented_entrypoints.py --repo-root .
python3 tests/unit/documented-entrypoint-paths.test.py
)
( # step: T2-12 — archived skills are tombstones and their installers refuse
set -e -o pipefail
python3 tests/unit/archived-skill-tombstones.test.py
)
( # step: Assert the guards themselves can still go red
set -e -o pipefail
set -euo pipefail
# A guard that has only ever been observed passing has not been
# observed. Construct both defects in a scratch tree and require a
# non-zero exit from the checker.
tmp="$(mktemp -d)"
mkdir -p "$tmp/77-fixture-skill/scripts"
printf '# Fixture\n\n```bash\nbash do-the-thing.sh\n```\n' > "$tmp/77-fixture-skill/SKILL.md"
if python3 docs/tools/check_documented_entrypoints.py --repo-root "$tmp"; then
  echo "FAIL: the entry-point checker passed a script that does not exist." >&2
  exit 1
fi
echo "PASS: the entry-point checker goes red on a real defect."
rm -rf "$tmp"
)
