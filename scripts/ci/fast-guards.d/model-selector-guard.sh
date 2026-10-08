#!/usr/bin/env bash
# Folded from .github/workflows/model-selector-guard.yml (job "Intelligent Model Selector + AF-MODEL-SOVEREIGNTY (v12.15.0)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Reject the retired DeepSeek V4 Pro model id (KEF001)
set -e
python3 tests/unit/no-retired-deepseek-pro-model.test.py
)
( # step: Run selector + gate unit tests
set -e
python3 tests/unit/model-selector.test.py
)
( # step: Smoke-test the repair sweep (dry-run + apply + idempotency)
set -e
set -euo pipefail
WORK=$(mktemp -d)
cat > "$WORK/openclaw.json" <<'JSON'
{
  "models": { "list": [
    {"id":"ollama/deepseek-v4.1-flash"},
    {"id":"ollama/qwen3-vl:235b-cloud"},
    {"id":"openrouter/deepseek/deepseek-v4.1-flash"}
  ]},
  "agents": { "list": [
    {"id":"dept-ceo","model":{"primary":"openrouter/free","fallbacks":[]}},
    {"id":"dept-graphics","model":null},
    {"id":"dept-legal","model":{"primary":"anthropic/claude-opus","fallbacks":[]}}
  ]}
}
JSON
# dry-run finds 3 offenders and (correctly) exits 3 because the gate
# still sees them unfixed — that nonzero exit is EXPECTED in dry mode.
# We assert on the receipt content below, not the exit code.
bash scripts/repair-model-sovereignty.sh \
  --config "$WORK/openclaw.json" --box ci --receipt-dir "$WORK/sweep" || true
python3 - "$WORK/sweep/ci.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert len(d["openclaw_fixes_planned"]) == 3, d["openclaw_fixes_planned"]
g = {f["agent"]: f for f in d["openclaw_fixes_planned"]}
assert g["dept-graphics"]["required_modality"] == "vision", g["dept-graphics"]
print("dry-run OK: 3 offenders, graphics->vision")
PY
# apply -> gate must come back clean
bash scripts/repair-model-sovereignty.sh \
  --config "$WORK/openclaw.json" --box ci --receipt-dir "$WORK/sweep" --apply
python3 - "$WORK/sweep/ci.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["clean"] is True, d["gate_offenders_after"]
print("apply OK: gate clean after repair")
PY
# gate must agree independently
python3 shared-utils/assert_model_sovereignty.py --scan-config "$WORK/openclaw.json"
echo "repair sweep smoke OK"
)
( # step: No Anthropic / free-default leakage in selector outputs
set -e
set -euo pipefail
# The selector and gate must never emit a forbidden or free-default model.
if grep -REn "'(claude-[a-z0-9-]+|anthropic/[a-z0-9-]+)'" \
  shared-utils/select_model.py shared-utils/assert_model_sovereignty.py 2>&1; then
  echo "FAIL: Anthropic model string in selector source"; exit 1
fi
echo "OK: no Anthropic strings in selector source"
)
