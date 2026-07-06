#!/usr/bin/env bash
# =============================================================================
# PODCAST PRODUCTION ENGINE :: WEBHOOK LAYER SELF-TEST RUNNER
# Runs every module's built-in --self-test. Fail-closed: any non-zero aborts.
# No network, no live gateway, no real ~/.openclaw state (temp dirs only), no
# secrets. This is the local gate the webhook slice runs before commit; the T1-T9
# onboarding verification (through the real public URL) is a separate executable.
# =============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"

echo "== Podcast Engine webhook layer self-tests =="
echo "-- python: $("$PY" --version 2>&1)"

fail=0
for mod in mapper.py job_key.py ledger.py flow_client.py intake_handler.py; do
  echo
  echo "== $mod =="
  if "$PY" "$HERE/$mod" --self-test; then
    echo "-- $mod: PASS"
  else
    echo "-- $mod: FAIL"
    fail=1
  fi
done

echo
echo "== byte-compile check (syntax) =="
"$PY" -m py_compile "$HERE"/*.py && echo "-- py_compile: PASS"

echo
echo "== aliases.json + route-template.json5 structure check =="
"$PY" - "$HERE" <<'PYEOF'
import json, sys
here = sys.argv[1]
with open(here + "/aliases.json", encoding="utf-8") as fh:
    tables = json.load(fh)
assert "field_aliases" in tables and "enum_normalization" in tables, "aliases.json missing sections"
print("-- aliases.json: valid JSON with required sections")
# route-template.json5 is JSON5 (unquoted keys, // comments) that Python's stdlib
# json cannot parse; validate brace/bracket balance and the live-verified path.
raw = open(here + "/route-template.json5", encoding="utf-8").read()
code = "\n".join(l for l in raw.splitlines() if not l.lstrip().startswith("//"))
assert code.count("{") == code.count("}"), "route-template.json5 brace imbalance"
assert code.count("[") == code.count("]"), "route-template.json5 bracket imbalance"
for token in ("plugins:", "entries:", "webhooks:", "routes:", "sessionKey:",
              "secret:", 'source: "env"', 'provider: "default"', 'id: "PODCAST_INTAKE_HOOK_SECRET"',
              "controllerId:"):
    assert token in code, "route-template.json5 missing %r" % token
print("-- route-template.json5: balanced, carries the live-verified schema")
PYEOF

echo
if [ "$fail" -eq 0 ]; then
  echo "== ALL WEBHOOK-LAYER SELF-TESTS PASSED =="
  exit 0
fi
echo "== WEBHOOK-LAYER SELF-TESTS FAILED =="
exit 1
