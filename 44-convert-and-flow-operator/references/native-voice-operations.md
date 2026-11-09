# Native Voice AI Operations (WF27, revision 3.0 section 24)

Interface checkpoint: **WF27-CP01**. This file and
`tools/engine/cli_anything/gohighlevel/public/voice_ai.py` are the frozen
interface. A consumer reads this checkpoint record instead of re-deriving the
shapes.

## Two providers, one explicit choice

| Provider id | What it is | Owner |
|---|---|---|
| `ghl_native_voice` | HighLevel's own Voice AI agents, actions and call-log dashboard, reached through the frozen public adapter | Skill 44 / shared public adapter (WF27 adapter) |
| `self_hosted_skill38` | The existing STT -> brain -> TTS pipeline over Twilio Media Streams, documented in `38-conversational-ai-system/protocols/voice-phone-protocol.md` | Skill 38 |

`select_provider(provider, reason=...)` refuses an empty or unknown id. There is
no default and no cost claim: `VoiceProviderChoice.price_evidence_ref` is `None`
until client-specific usage/price evidence exists, so nothing in this lane says
one provider is cheaper.

Native provisioning is not proof that a number is routed to the agent, and the
self-hosted route is not proof that HighLevel Voice AI exists on the tenant.
Those are separate claims in separate evidence.

## Requested operation rows (WF00 owns the registry)

Source: the per-operation enumeration already in
`29-ghl-convert-and-flow/references/voice-ai.md` (verified 2026-08-03), which
also records that **no verified `Version` literal exists** for these operations.
The rows below therefore ship with `version=None` and blocker
`B-VERSION-UNVERIFIED`; a call refuses with `voice_contract_pending`
(`voice_wire_version_unverified`) before transport until WF00 freezes the
literal. No version is guessed.

| Operation id | Method | Path | Scope | Kind | Read-back |
|---|---|---|---|---|---|
| `voiceAi.agents.list` | GET | `/voice-ai/agents` | `voice-ai-agents.readonly` | read | - |
| `voiceAi.agents.get` | GET | `/voice-ai/agents/{agentId}` | `voice-ai-agents.readonly` | read | - |
| `voiceAi.agents.create` | POST | `/voice-ai/agents` | `voice-ai-agents.write` | write (approval) | list matched by name |
| `voiceAi.agents.update` | PATCH | `/voice-ai/agents/{agentId}` | `voice-ai-agents.write` | write (approval) | `voiceAi.agents.get` |
| `voiceAi.actions.get` | GET | `/voice-ai/actions/{actionId}` | `voice-ai-agent-goals.readonly` | read | - |
| `voiceAi.actions.create` | POST | `/voice-ai/actions` | `voice-ai-agent-goals.write` | write (approval) | `voiceAi.actions.get` by returned id |
| `voiceAi.actions.update` | PUT | `/voice-ai/actions/{actionId}` | `voice-ai-agent-goals.write` | write (approval) | `voiceAi.actions.get` |
| `voiceAi.calls.list` | GET | `/voice-ai/dashboard/call-logs` | `voice-ai-dashboard.readonly` | read | - |
| `voiceAi.calls.get` | GET | `/voice-ai/dashboard/call-logs/{callId}` | `voice-ai-dashboard.readonly` | read | - |

Tenant binding: list/get/calls rows use `query.locationId`; create/action-update
rows use `body.locationId`; `agents.update` uses `query.locationId`. Those
bindings are the requested rows' values and are part of this checkpoint.

`voice_operations()` merges these rows **only where the shared registry has no
row of the same id**, so a WF00 row always wins once it lands.

## Typed interface

```text
VoiceProviderChoice(provider, reason, price_evidence_ref=None)
VoiceAgentSpec(name, business_name, language, timezone, operating_hours,
               escalation_destination, allowed_call_purposes,
               knowledge_source_ids=(), voice=None, extra={})
VoiceActionSpec(agent_id, action_type, parameters, extra={})
PhoneRouteState(location_id, number_ref, agent_id, inbound_route_ref,
                routing_verified, observed, source, pending_action)
RouteRollback(location_id, agent_id, number_ref, previous_route_ref, captured_at)
PhoneRouteHandoff(location_id, agent_id, number_ref, rollback_ref,
                  requested_action, executed, owner, detail)
CallLogQuery(timezone, start, end, page=1, page_size=50, agent_id=None,
             contact_id=None, call_type=None, action_types=())
CallRecord(call_id, location_id, agent_id, contact_id, direction, mode,
           started_at, duration_s=None, outcome=None, action_refs=(),
           transcript_ref=None)
GuardLimits(max_test_calls=2, max_test_duration_s=180, max_cost_usd=5.0,
            max_retries=0, max_actions_per_test=3,
            allowed_destinations=(), allowed_calendars=())
ControlledTestPlan / ControlledTestEvidence / ControlledTestReceipt
ProvisioningPlan / VoiceInventory
```

Adapter calls (all go through `PublicGhlAdapter.call`):

```text
list_agents(tenant, page, page_size)            -> (OperationResult, payload)
get_agent(tenant, agent_id)                     -> (OperationResult, payload)
get_action(tenant, action_id)                   -> (OperationResult, payload)
create_agent(tenant, spec, idempotency_key, approval)
update_agent(tenant, agent_id, patch, idempotency_key, approval)
create_action(tenant, spec, idempotency_key, approval, action_readback_id=None)
update_action(tenant, action_id, patch, idempotency_key, approval)
inventory(tenant)                               -> VoiceInventory
inspect_phone_assignment(tenant)                -> PhoneRouteState
list_call_logs(tenant, query)                   -> (OperationResult, tuple[CallRecord])
get_call(tenant, call_id)                       -> (OperationResult, CallRecord | None)
```

Writes require an explicit idempotency key and an approval seam. Nothing here
retries; a retry is a new call and the frozen adapter refuses an unreconciled
unknown outcome.

## Agent creation is not phone activation

`create_agent` reads the agent back by name through the list row and records
`configured=true`, `operationally_active=false`. `inspect_phone_assignment`
reports `unknown` until the routing owner's surface is actually read; it never
infers a route from an agent id. `plan_route_activation` requires a
`RouteRollback` (same tenant and agent) and returns a `PhoneRouteHandoff` with
`executed=false`; the phone/routing owner applies the change.

## Provisioning order

`plan_provisioning` orders: inventory -> create/update agent -> create actions
-> attach actions -> attach approved knowledge sources -> phone handoff ->
controlled test -> activation with rollback. A same-name agent is treated as a
replacement and refused unless `allow_replace=True`; duplicate display names
stay distinct ids.

## Controlled test guards

Defaults: 2 test calls, 180 s, USD 5.00, 0 retries, 3 actions per test. A test
also requires: the agent bound in the observed phone state, an allowlisted
destination, and every planned action allowlisted. `verify_controlled_test`
accepts only a `trial` call for the same tenant and agent, with a contact id,
action evidence when actions were planned, and one recorded business outcome
(`booking_created`, `transfer_delivered`, `field_updated`,
`workflow_started`, `knowledge_resolved`). A `live` or `unknown` call never
passes as controlled-test evidence.

## Call logs

Voice-specific rules, not workflow-log cursors: mandatory IANA `timezone`, a
bounded window (both boundaries, maximum 31 days), 1-based `page`, bounded
`pageSize` (1-100). Records carry an explicit trial/live marker; anything else
maps to `unknown` and is not evidence.

## Caller input

Caller speech is untrusted. `screen_caller_input` names (never echoes) any
administrative intent: credential reveal, agent rewrite, routing change,
arbitrary URL, outbound dial, billing change. `require_caller_safe` raises with
rule names only. Customer speech can never change agent configuration, routing,
credentials or spend.

## What this lane does not do

No number purchase, no plan change, no outbound dial, no live call, no phone
routing mutation, no provider retry, no deletion of agents/actions. Those are
owned elsewhere or require separate authorization.

## Acceptance mapping

| Case | Where proved |
|---|---|
| B09, IG-AI-01, IG-AI-02 | provider split; agent created but not routed/active; phone handoff |
| B10, IG-AI-03 | bounded controlled test; call bound to agent/contact/action/outcome; rollback |
| IG-AI-08 (voice) | caller input cannot mutate administrative state |

Focused tests: `tools/engine/tests/test_voice_ai_contract.py` (fixtures:
`tools/engine/tests/voice_fixtures.py`), run with an empty `HOME`:

```bash
PYTHONPATH="$PWD/44-convert-and-flow-operator/tools/engine" \
python3 -m pytest -q \
  44-convert-and-flow-operator/tools/engine/tests/test_voice_ai_contract.py
```

## Open contract items (upstream, not defects in this lane)

1. **Wire version literals** - WF00 must freeze one per voice-ai operation page.
2. **Action create read-back** - no actions LIST/SEARCH row is documented, so a
   created action can only be read back by the id its create response returned.
   Until WF00/WF01 publishes a create-response read-back policy or a list row,
   `create_action` without `action_readback_id` refuses before transport.
3. **Call-log query key names** - `to_query()` uses `startDate`, `endDate`,
   `timezone`, `page`, `pageSize`, `agentId`, `contactId`, `callType`,
   `actionTypes`; confirm against the frozen row/`describe_operation`.
4. **Phone routing read** - no documented routing read row exists; the adapter
   reports `unknown` with the exact pending action instead of guessing.
