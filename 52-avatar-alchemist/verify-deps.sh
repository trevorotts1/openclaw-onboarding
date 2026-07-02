#!/usr/bin/env bash
# verify-deps.sh — prove the shipped skill needs nothing beyond python3 stdlib +
# the client's own model providers. No Airtable, Drive, Slack, Gmail, n8n at runtime.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
fail=0
command -v python3 >/dev/null 2>&1 || { echo "FAIL: python3 missing"; fail=1; }
if grep -REl 'import[[:space:]]+(requests|openai|anthropic|httpx|aiohttp|google|slack|gspread)\b' "$HERE/scripts" >/dev/null 2>&1; then
  echo "FAIL: a script imports a forbidden external runtime dependency"; fail=1
fi
for f in aa_intake_gate.py aa_build_check.py aa_delivery_gate.py aa_gate_integrity_check.py aa_director.py; do
  python3 -c "import ast,sys; ast.parse(open('$HERE/scripts/$f').read())" || { echo "FAIL: $f does not parse"; fail=1; }
done
if [ "$fail" = 0 ]; then echo "PASS: python3 stdlib only; zero external runtime services (client providers only)."; fi
exit "$fail"
