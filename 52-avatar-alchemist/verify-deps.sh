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
# single-sourced egress ban (AST import walk, catches `from X import Y` the
# regex above misses): aa_egress_gate.py is the one authoritative scanner for
# n8n/Airtable/Slack/Drive/Gmail/urllib/requests-POST egress; called here too
# so this script and entry.sh/aa_director.py never diverge on the banlist.
python3 "$HERE/scripts/aa_egress_gate.py" --scripts-dir "$HERE/scripts" >/dev/null \
  || { echo "FAIL: AF-AV-EGRESS — an ungoverned egress path was found (see aa_egress_gate.py)"; fail=1; }
if [ "$fail" = 0 ]; then echo "PASS: python3 stdlib only; zero external runtime services (client providers only); egress-clean."; fi
exit "$fail"
