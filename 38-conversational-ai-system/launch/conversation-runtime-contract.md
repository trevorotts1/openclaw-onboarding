# Launch Conversation-AI runtime contract (AI-2)

Everything below is checked offline by
`qc-launch-conversation-ai.sh --bundle <evidence.json>`. The playbooks in this
directory say what the bot may say; this file says what must exist, for which
target, before a launch Conversation-AI unit counts as complete.

**Completion is target-specific.** A row in a registry, a tidy folder, or a
global "all playbooks present" pass never proves the requested bot was built for
this tenant, this workflow, this launch revision and this playbook.

## 1. One reply owner

A launch declares exactly one reply owner. Two responders on one thread is how
duplicate replies and double bookings happen.

| `reply_owner.kind` | When | Required proof |
|---|---|---|
| `openclaw_inbound` (default) | The full Skill 38 route. The existing OpenClaw inbound path owns every reply; its channel playbooks and these launch playbooks govern content. | `inbound_path` names the path handling replies. The GHL Conversation AI node is **not** a second responder. |
| `native_ghl` | A deliberately narrower mode that uses the GHL Conversation AI action itself. | `translation_approved: true`, plus `prompt_binding.playbook` and `prompt_binding.offer_knowledge_version` naming the approved prompt and the exact knowledge version. Approval is the operator's, never the bot's. |

A `native_ghl` build without that approved prompt/knowledge translation is not
equivalent to the full route and fails the gate. Do not paper over it by
declaring the OpenClaw path in prose while the native node answers.

## 2. Mode adapters (observed schemas only)

Each mode needs an adapter built from an **observed** schema, never an invented
one. Required adapters:

| `mode` | Adapters |
|---|---|
| `faq` | `faq` |
| `booking` | `booking` |
| `checkout` | `checkout` |
| `full` | `faq` + `booking` + `checkout` |

Every adapter record carries:

- `observed_schema` — the observed schema identity it was built from.
- `required_fields` — nonempty list of the fields it reads.
- `actions` — nonempty list of the actions it performs.
- `saved_graph_readback: true` — the saved definition was read back after build.
- `bot_registration_receipt` — the registered bot receipt identity.

`none` is not a runtime mode. `requested: true` + `mode: "none"` is an invalid
plan and stops the build (`not-requested-path.md`).

## 3. Enrollment, state, consent

- **Enrollment.** `enrollment.launch_enrolled`, `.location_enrolled` and
  `.contact_enrolled` must all be true, and `enrollment.launch_id` /
  `.location_id` must match the bundle. A bot that is not enrolled cannot be
  reached by this launch's contacts.
- **Namespaced state.** `state.namespace` must be
  `launch-ai/<tenant_id>/<location_id>/<launch_id>/` and every key must live
  under it. Conversation state is never shared across tenants, locations or
  launches.
- **Channel consent.** Every channel the plan lists needs `granted: true` with a
  nonempty `source` and `captured_at`. A channel not in the plan must not hold
  consent. Consent granted for one launch does not carry to another.

## 4. Bounded human fallback

`human_fallback` must name the human, bound the bot, and close the loop:

- `owner` — who takes over.
- `max_turns` — integer 1–10.
- `timeout_minutes` — integer 1–1440.
- `triggers` — nonempty list (unknown, no availability, purchase uncertainty,
  second decline).
- `closure_path` — how the handoff ends.
- `bounded: true`.

An unbounded "the operator will handle it" is not a fallback.

## 5. Per-offer knowledge

See `offer-knowledge.md`. At least one versioned offer record must exist, with
`update_rule: operator_published_only`, `unknown_policy: escalate`,
`invention_guard: true` and a named `escalation_owner`.

## 6. Target-specific evidence

For **each required playbook** the bundle needs both:

1. a `graph_readback` record, and
2. a `bot_registration_receipt` record,

and each record must carry:

| Field | Rule |
|---|---|
| `tenant_id` | Exactly the bundle tenant |
| `location_id` | Exactly the bundle location |
| `workflow_id` | Exactly the bundle workflow |
| `launch_id` | Exactly the bundle launch |
| `launch_revision` | Exactly the bundle revision |
| `playbook` | The exact playbook filename |
| `records` | Integer >= 1 |
| `digest` | Nonempty |

A record with `scope: "global"` or `global_registry_hygiene: true` is ignored.
If it is the only evidence, the gate fails with `EVIDENCE_GLOBAL`: a global
registry hygiene pass never satisfies requested-bot completion for a specific
launch.

## 7. Behaviour evidence

The bundle records the eight launch outcomes, each with a typed `outcome`
token and an `evidence_ref` that must equal the digest of this bundle's
targeted evidence for the matching playbook. `human_handoff` also names
`observable_owner` and `closure_path`.

| Scenario | Required `outcome` |
|---|---|
| `booking_success` | `booked` |
| `no_availability` | `no_availability` |
| `answered_not_booked` | `answered` |
| `timeout` | `timed_out` |
| `repeat_reply` | `answered_once` |
| `keyword_wake` | `reactivated` |
| `stop_opt_out` | `opted_out` |
| `human_handoff` | `handed_off` |

Any other value — including `failed`, an empty string, or a prose sentence —
fails `SCENARIO_OUTCOME`. A failed required scenario never satisfies
completion. An `evidence_ref` naming no targeted digest in this bundle fails
`SCENARIO_EVIDENCE`.

`qa_probes` holds at least 30 buyer questions. Each is `grounded` (with a
`grounded_ref` naming the plan field) or `escalated` (with an
`escalation_owner`). Every probe keeps `config_mutation: false`. An injection
probe must escalate. A divergent reported price must escalate; a restated plan
price may be grounded.

`isolation` lists at least two distinct launches, requires
`unrelated_support_isolated: true`, and `false_booking_success: false` — two
launches plus unrelated support never cross-book or claim a booking that did not
happen.

## 8. No live effects

`live_effects` must be empty. This lane sends nothing, charges nothing, books
nothing, grants no access, and mutates no provider. Every fixture is synthetic
and local.

## 9. Staging acceptance

Buyer-journey and channel tests may run only under a **separately authorized**
account. When no such account exists, the bundle records:

```json
"staging": {
  "authorized_account": false,
  "result": "blocked",
  "reason": "<precise reason>"
}
```

Claiming `result: "pass"` without `authorized_account: true` fails
`STAGING_BYPASS`. Never bypass it.

## 10. Running the gate

```bash
bash 38-conversational-ai-system/launch/qc-launch-conversation-ai.sh \
  --bundle 38-conversational-ai-system/launch/fixtures/pass-full.json

bash 38-conversational-ai-system/launch/tests/qc-launch-conversation-ai.test.sh
```

Exit `0` = complete for the exact target; `1` = incomplete (codes printed);
`2` = usage or IO. The gate is offline and stdlib-only.
