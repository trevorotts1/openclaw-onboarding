#!/usr/bin/env bash
# verify.sh - Skill 80 (Signature Upsell) verifier. READ-ONLY and IDEMPOTENT.
# Version lockstep (SKILL.md <-> skill-version.txt) plus the package's own verify.py.
# Exits nonzero on any failure. Used by the update gate (lib-onboarding-state.sh).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"
fails=0
echo "== Skill 80 (Signature Upsell) :: verify.sh =="
front_ver="$("$PY" -c "import re,pathlib,sys; m=re.search(r'^version:\s*(\S+)', pathlib.Path(sys.argv[1]).read_text(), re.M); print(m.group(1) if m else '')" "$ROOT/SKILL.md")"
file_ver="$(tr -d '[:space:]' < "$ROOT/skill-version.txt")"
if [ -n "$front_ver" ] && [ "$front_ver" = "$file_ver" ]; then printf '  [PASS] version lockstep %s\n' "$front_ver"; else printf '  [FAIL] version drift [%s] != [%s]\n' "$front_ver" "$file_ver"; fails=$((fails+1)); fi
if "$PY" "$ROOT/verify.py" >/dev/null 2>&1; then echo "  [PASS] verify.py"; else echo "  [FAIL] verify.py (run it directly for the log)"; fails=$((fails+1)); fi
echo "=================================================="
if [ "$fails" -eq 0 ]; then echo "RESULT: PASS"; exit 0; fi
echo "RESULT: FAIL - $fails check(s) failed."
exit 1
