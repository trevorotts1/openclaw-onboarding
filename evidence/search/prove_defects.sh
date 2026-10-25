#!/usr/bin/env bash
# T-01 defect reproducers, run against the pinned commit's own code.
#
# Usage: bash evidence/search/prove_defects.sh <repo-root> <workdir>
#
# Writes nothing into the repository. All fixtures live under <workdir>.
# No removals: every fixture directory is created if absent and files are
# overwritten in place.

set -uo pipefail

ROOT="${1:?repo root required}"
WORK="${2:?workdir required}"
SKILL38="$ROOT/38-conversational-ai-system"
LIB="$SKILL38/scripts/lib-docker-tenant.sh"

mkdir -p "$WORK/d11/legacyroot" "$WORK/d12"

echo "=================================================================="
echo "D-11  existing hook mapping is migrated, not skipped"
echo "=================================================================="
cat > "$WORK/d11/legacyroot/openclaw.json" <<'JSON'
{
  "hooks": {
    "enabled": true,
    "mappings": [
      {
        "id": "ghl-inbound-sms",
        "match": { "path": "ghl-inbound-sms" },
        "action": "agent",
        "agentId": "main",
        "sessionKey": "hook:ghl:sms:{{contact.id}}",
        "messageTemplate": "legacy template with no directive",
        "deliver": false
      }
    ]
  },
  "gateway": { "trustedProxies": ["127.0.0.1"] },
  "agents": { "entries": { "main": {} } }
}
JSON

OPENCLAW_ROOT="$WORK/d11/legacyroot" \
PYTHONDONTWRITEBYTECODE=1 \
  python3 -I "$SKILL38/scripts/repair/repair-inbound-hooks.py" 2>&1
echo "repair_rc=$?"

echo "-- post-state (one JSON line) --"
jq -c '.hooks.mappings[0]
  | {id, sessionKey,
     has_model: has("model"),
     nested_session_token: (.sessionKey | test("\\{\\{contact\\.id\\}\\}")),
     template_has_send_directive: (.messageTemplate | test("MANDATORY")),
     template_has_conversation_log: (.messageTemplate | test("conversational-logs"))}' \
  "$WORK/d11/legacyroot/openclaw.json"

echo
echo "=================================================================="
echo "D-12  model is OPTIONAL in the one shared predicate"
echo "=================================================================="
# shellcheck disable=SC1090
. "$LIB"
s38_canonical_mapping ghl-inbound-sms ghl-inbound-sms main '{{session_key}}' > "$WORK/d12/one.json"

jq -n --slurpfile m "$WORK/d12/one.json" \
  '{hooks:{enabled:true,allowedAgentIds:["main"],mappings:[$m[0]]},agents:{entries:{main:{}}}}' \
  > "$WORK/d12/no-model.json"
jq -n --slurpfile m "$WORK/d12/one.json" \
  '{hooks:{enabled:true,allowedAgentIds:["main"],mappings:[($m[0]|.model="")]},agents:{entries:{main:{}}}}' \
  > "$WORK/d12/blank-model.json"
jq -n --slurpfile m "$WORK/d12/one.json" \
  '{hooks:{enabled:true,allowedAgentIds:["main"],mappings:[($m[0]|.model="client-chosen-model")]},agents:{entries:{main:{}}}}' \
  > "$WORK/d12/with-model.json"

for cfg in no-model blank-model with-model; do
  echo "-- $cfg --"
  HOOK_MAPPING_ID=ghl-inbound-sms hook_mapping_contract_eval "$WORK/d12/$cfg.json" \
    > "$WORK/d12/$cfg.out" 2>&1
  echo "eval_rc=$?"
  grep -E '^(MAPSELECT|MAPCONTRACT|GATEVERDICT)\|' "$WORK/d12/$cfg.out"
done

echo
echo "=================================================================="
echo "D-13  HTTP 200 admission versus a delivered reply"
echo "=================================================================="
echo "-- the self-test's completed-reply checks and their gates --"
grep -n 'CODE" = "200"' "$SKILL38/scripts/24-self-test-hook.sh"
grep -n 'CREATE_TEMP_CONTACT:-0' "$SKILL38/scripts/24-self-test-hook.sh"
grep -n 'GHL Conversations API send returned' "$SKILL38/scripts/24-self-test-hook.sh"
echo "-- the contracts layer labels admission honestly --"
grep -n 'never "delivered"' "$SKILL38/tools/direct_fulfillment.py"
echo
echo "reading: with CREATE_TEMP_CONTACT unset (the default) the block that can"
echo "prove a GHL messageId never runs, so HTTP 200 + {ok:true} is accepted as"
echo "the completed reply. The contracts layer states the correct rule; the"
echo "hook self-test does not yet enforce it."

echo
echo "=================================================================="
echo "D-15  the launch reply-owner gate is not invoked by any install path"
echo "=================================================================="
grep -rn 'qc-launch-conversation-ai' "$ROOT/install.sh" "$ROOT/update-skills.sh" "$ROOT/.github/workflows/" 2>/dev/null
echo "installer_workflow_hits_rc=$?"
grep -n 'qc-launch-conversation-ai' "$SKILL38/launch/qc-launch-conversation-ai.sh" | head -2
echo "gate_script_present_rc=$?"
