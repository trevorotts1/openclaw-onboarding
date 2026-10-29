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
# dry-run finds 2 offenders (an Anthropic primary is NOT one: no vendor rule) and
# (correctly) exits 3 because the gate still sees them unfixed — that nonzero exit is EXPECTED in dry mode.
# We assert on the receipt content below, not the exit code.
bash scripts/repair-model-sovereignty.sh \
  --config "$WORK/openclaw.json" --box ci --receipt-dir "$WORK/sweep" || true
python3 - "$WORK/sweep/ci.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert len(d["openclaw_fixes_planned"]) == 2, d["openclaw_fixes_planned"]
g = {f["agent"]: f for f in d["openclaw_fixes_planned"]}
assert g["dept-graphics"]["required_modality"] == "vision", g["dept-graphics"]
print("dry-run OK: 2 offenders, graphics->vision, Anthropic primary untouched")
PY
# apply -> gate must come back clean
bash scripts/repair-model-sovereignty.sh \
  --config "$WORK/openclaw.json" --box ci --receipt-dir "$WORK/sweep" --apply
python3 - "$WORK/sweep/ci.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["clean"] is True, d["gate_offenders_after"]
cfg = json.load(open(sys.argv[1].replace("sweep/ci.json", "openclaw.json")))
legal = [a for a in cfg["agents"]["list"] if a["id"] == "dept-legal"][0]
assert legal["model"]["primary"] == "anthropic/claude-opus", legal
print("apply OK: gate clean after repair; the Anthropic primary was kept")
PY
# gate must agree independently
python3 shared-utils/assert_model_sovereignty.py --scan-config "$WORK/openclaw.json"
echo "repair sweep smoke OK"
)
( # step: No vendor rule -- the selector forbids no Anthropic-family id
set -e
bash tests/unit/no-anthropic-rule.test.sh
echo "OK: no Anthropic rule"
)
