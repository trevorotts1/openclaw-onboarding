#!/usr/bin/env bash
# Skill 74 - KIE Live Adapter - install QC. HERMETIC: offline unit tests only, no network, no key needed.
# Live checks live in scripts/live_smoke.sh (opt-in, never run here). Writes nothing inside the skill folder.
# Exit 0 = all checks pass. Exit 1 = at least one failed.
set -u
D="$(cd "$(dirname "$0")" && pwd)"
export PYTHONDONTWRITEBYTECODE=1
unset KIE_API_KEY KIE_LIVE_ADAPTER_MODE
PASS=0; FAIL=0
ok() { echo "  PASS - $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL - $1"; FAIL=$((FAIL+1)); }
chk() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }
snap() { (cd "$D" && find . -type f | LC_ALL=C sort | while read -r f; do printf '%s %s\n' "$(shasum -a 256 < "$f" | cut -d' ' -f1)" "$f"; done); }

echo "== Skill 74 KIE Live Adapter - QC (offline)"
BEFORE="$(snap)"
for f in SKILL.md INSTALL.md INSTRUCTIONS.md CORE_UPDATES.md QC.md CHANGELOG.md PREREQS.json skill-version.txt wire.sh \
         vendor-approval.json scripts/kie_live_adapter.py scripts/build_model_registry.py references/kie-model-registry.json scripts/vendor_skill_probe.sh scripts/live_smoke.sh \
         references/adapter-contract.md references/integration-policy.md references/vendor-research.md references/decision-log.md \
         tests/test_adapter_contract.py tests/test_shadow_mode.py tests/test_no_chat_agent_mutation.py tests/test_registry_commands.py; do
  chk "present: $f" "[ -f '$D/$f' ]"
done
chk "wire.sh executable" "[ -x '$D/wire.sh' ]"
chk "this script executable" "[ -x '$D/qc-74-kie-live-adapter.sh' ]"
chk "skill-version.txt is v1.1.0 plus newline" "[ \"\$(cat '$D/skill-version.txt')\" = v1.1.0 ] && [ \"\$(tail -c1 '$D/skill-version.txt' | od -An -c | tr -d ' ')\" = '\\n' ]"
chk "SKILL.md top-level version matches" "head -20 '$D/SKILL.md' | awk '/^version: 1.1.0\$/{f=1} END{exit !f}'"
chk "PREREQS.json valid JSON" "python3 -c \"import json;json.load(open('$D/PREREQS.json'))\""
chk "vendor-approval.json valid JSON" "python3 -c \"import json;json.load(open('$D/vendor-approval.json'))\""
chk "registry JSON valid, live-api or public-docs source, every model has limits fields" "python3 -c \"import json;d=json.load(open('$D/references/kie-model-registry.json'));assert d['source'] in ('live-api','public-docs') and d['models'] and all('input_fields' in m and 'prompt_field' in m and 'pricing' in m for m in d['models'])\""
chk "adapter parses (no bytecode written)" "python3 -c \"import ast;ast.parse(open('$D/scripts/kie_live_adapter.py').read());ast.parse(open('$D/scripts/build_model_registry.py').read())\""
chk "bash syntax: wire.sh" "bash -n '$D/wire.sh'"
chk "bash syntax: vendor_skill_probe.sh" "bash -n '$D/scripts/vendor_skill_probe.sh'"
chk "bash syntax: live_smoke.sh" "bash -n '$D/scripts/live_smoke.sh'"
chk "no file named model-map.json" "[ -z \"\$(find '$D' -name model-map.json)\" ]"
chk "no Authorization or key literal in fixtures" "! cat '$D'/tests/fixtures/* | tr 'A-Z' 'a-z' | awk '/bearer |authorization/{f=1} END{exit !f}'"

UT="$(mktemp)"
if (cd "$D/tests" && python3 -m unittest discover -s . 2>&1 | tail -4 | tee "$UT" | awk '/^OK/{f=1} END{exit !f}'); then
  ok "unit tests: $(awk '/^Ran/{print}' "$UT")"
else
  bad "unit tests"; cat "$UT"
fi
rm -f "$UT"
AFTER="$(snap)"
chk "skill folder unchanged by the run (no artifacts, no __pycache__)" "[ \"$BEFORE\" = \"$AFTER\" ]"
echo "== $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
