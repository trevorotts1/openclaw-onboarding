# Interactive workflow owner contract (T-19 / C-19)

The launch runtime contract (`conversation-runtime-contract.md` §1) fixes **one
reply owner** for a launch. This file fixes the same rule for **interactive
workflow steps**: the rendered controls, the provider callbacks they raise, the
free text a buyer types instead of tapping, and the stale tap that arrives after
the step has already moved on.

**One responder, and it is OpenClaw by default.** An interactive step that is
answered twice produces two bookings, two captures, or a capture that advances
while the transcript says something else. So the rule is narrower than "prefer
OpenClaw": a step has exactly one owner, and a second declared responder is a
refusal, not a preference.

Machine-checked by `tools/interactive_owner.py`, its suite
`tools/tests/test_interactive_owner.py`, and `scripts/qc-interactive-owner.sh`.

## 1. Owner

| `owner.kind` | When | Required proof |
|---|---|---|
| `openclaw_inbound` (**default**, and the value used when `owner` is omitted) | The full Skill 38 route. Its inbound path presses, callbacks, free text and stale taps all land on this one owner. | None beyond the contract itself. `owner.inbound_path` or the top-level `inbound_path` names the path when known. |
| `native_ghl` | A deliberately narrower launch that already passed the launch gate as `native_ghl`. | `owner.launch_bundle` must name a launch bundle whose `reply_owner.kind` is `native_ghl`. |

**The approval decision is not re-implemented here.** `translation_approved`,
`prompt_binding.playbook` and `prompt_binding.offer_knowledge_version` belong to
the launch gate (`qc-launch-conversation-ai.sh`, code `REPLY_OWNER_TRANSLATION`).
This contract reads only the launch bundle's owner kind. One authority, one
guard: a bundle that names `native_ghl` without approval is admitted by this
record and still refused by the launch gate.

## 2. Responders

`responders` is optional. Omitted, exactly one is derived from the owner kind.
Declared, it must contain exactly one record whose `kind` matches the owner:

| Condition | Code |
|---|---|
| zero records | `NO_RESPONDER` |
| two or more records | `TWO_RESPONDERS` |
| one record, kind disagrees with the owner | `RESPONDER_MISMATCH` |

A refused contract has no route at all. Every event against it is refused with
the same code, so a two-responder launch cannot answer a single tap.

## 3. Steps

Each step is one interactive ask:

| Field | Rule |
|---|---|
| `step_id` | Nonempty, unique within the contract. |
| `generation` | Integer ≥ 1. Bumped whenever the step is re-rendered. |
| `controls` | Nonempty, unique list of control ids the step renders. |
| `free_text` | `accept` or `reject`. There is no default: a step says which. |

## 4. The four input classes

| Input | Rule | Refusal |
|---|---|---|
| `control` | `step_id` + `control_id` + current `generation` → routed to the owner. | `UNKNOWN_STEP`, `UNKNOWN_CONTROL`, `MALFORMED_EVENT` |
| `callback` | Identical to a control, delivered by the provider. Same owner, same route. | `UNKNOWN_STEP`, `UNKNOWN_CONTROL`, `MALFORMED_EVENT` |
| `free text` | Routed to the owner when the step's `free_text` is `accept`. | `FREE_TEXT_REJECTED` when `reject` |
| `stale tap` | Any control or callback whose `generation` differs from the step's current generation. | `STALE_TAP` |

**A stale tap is derived, never self-declared.** A provider cannot be trusted to
label its own tap stale, so `stale tap` is not one of the event kinds
(`control`, `callback`, `free text`); it is the verdict when the generations
disagree. A tap from the future is refused by the same rule, because the only
safe reading of a generation the contract has not issued is "not current". A
refused stale tap has `route: null`, so the late tap cannot re-open a step, book
twice, or reach a second responder.

## 5. Skill 44 is build-only

Skill 44 (`convert-and-flow-operator`) builds and QC's the GHL workflow that
renders the controls. It **never answers a conversation or an interactive
step**; its native node output is a build artifact, not a responder. The
conflict recorded as D-15 (`44 native-GHL ownership conflicts with 38 full
default`) is closed by this contract plus the pointer line in
`44-convert-and-flow-operator/SKILL.md`: the build path may be native, the
responder may not.

## 6. Record shape

```json
{
  "schema_version": 1,
  "contract_id": "launch-ai/<tenant_id>/<location_id>/<launch_id>",
  "inbound_path": "hooks/skill38-inbound",
  "owner": {"kind": "openclaw_inbound"},
  "responders": [{"id": "openclaw_inbound", "kind": "openclaw_inbound"}],
  "steps": [
    {"step_id": "pick_time", "generation": 3,
     "controls": ["tue_10am", "wed_2pm"], "free_text": "accept"}
  ]
}
```

`owner` and `responders` are both optional; omitting them yields the OpenClaw
default and one derived responder. Schema:
`schemas/interactive-owner.schema.json`.

## 7. Running the proof

```bash
bash 38-conversational-ai-system/scripts/qc-interactive-owner.sh
# same suite directly:
python3 38-conversational-ai-system/tools/tests/test_interactive_owner.py
# one decision:
python3 38-conversational-ai-system/tools/interactive_owner.py resolve \
  --contract <contract.json> \
  --event '{"kind":"control","step_id":"pick_time","control_id":"tue_10am","generation":3}'
```

Exit `0` = accepted or valid, `1` = refused or invalid, `2` = usage or IO. The
suite is offline and stdlib-only; no live effects, no provider calls.
