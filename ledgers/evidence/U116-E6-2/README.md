# U116 (E6-2, closes G8) — communication trigger + audience-confirmation prompt — evidence

Unit: U116 (P1, both — this evidence covers the ONB (`openclaw-onboarding`)
leg only). Binding: D1 (the blend GOVERNS voice + content-writing in every
engine, never advisory, no exemptions) + its ADD-2 extension (operator
ruling, closed here). Deps: U1/A-U1 (the seam the trigger rides — VERIFIED
merged to `main`, `shared-utils/persona_for_job.py`'s `blend`/`topic_hint`
kwargs), U4/A-U4 (the audience-confirm + per-department confirm-policy
machinery — VERIFIED merged, `resolve_conversion_goal`'s always-confirm
shape is the pattern this unit mirrors for the standard-vs-specific fork),
U5/A-U5 (per-page scoped blends — VERIFIED merged, `resolve_audience`/
`build_bundle` reused verbatim, no new door), U42 (task-detail modal —
VERIFIED merged; the ordering rule "U116 reuses the U4 confirm door —
serialize behind U5/U42/U4" is satisfied, all three are on `main`). D1
RULED (comms mandatory-governed, never asked).

Routed from U111 (E5-6/G4, VERIFIED merged): U111's "any content"
blend-governance proof named + proved email/blog/newsletter each governed
through the U1 seam, confirmed the text-message/SMS engine NOT-FOUND
in-tree, and — per its own build/route-decision rule — routed the SMS
question to this unit. This unit's first act (below) resolves that decision.

## What this unit builds (ONB leg)

A communication TRIGGER + audience-confirmation contract on the U1 seam,
fired whenever the system produces an outside-world communication (page,
blog, email, text/SMS, social post):

1. `23-ai-workforce-blueprint/scripts/persona_blend.py` — additive
   `force_content_task` kwarg on `build_bundle()`. A comms artifact is now
   ALWAYS blend-governed, independent of `is_content_task()`'s keyword
   heuristic (a bare "opt-in-page" brief with no `is_content_task` trigger
   word in it, e.g., no `page`/`landing`/`sales`, would otherwise slip
   through ungoverned). Default off — byte-identical to pre-U116 behavior
   for every existing caller (proven: the persona-blend-matcher T1-T13 suite
   and the A-U5 scoped-bundle suite both still pass 100% unmodified).
2. `shared-utils/comms_audience_trigger.py` — the new module:
   - `COMMS_TYPES = ("page", "blog", "email", "sms", "social")` — the five
     ADD-2 comms types.
   - `build_comms_trigger(comms_type, task_text, department, ...)` — the ONE
     call site every comms-producing write path calls before writing:
     forces the blend governance (1), REFUSES (never silently writes) when
     the topic is not factored (2), fires the standard-vs-specific audience
     fork BEFORE writing and records `audience_source` on the bundle (3).
   - `resolve_comms_audience()` — the standard-vs-specific fork, reusing
     `persona_blend.resolve_audience()`'s own always-confirm resolution
     verbatim; adds no new audience-resolution logic, only the ADD-2
     standard-vs-specific framing + `audience_source` recording on top.
   - `STANDARD_OR_SPECIFIC_PROMPT` — the exact ADD-2 question verbatim:
     "Should I use your standard audience, or is there a specific/different
     audience you want this message for?"
   - Flag-gated behind `COMMS_AUDIENCE_PROMPT` (default ON; `0`/`false`/
     `off`/`no` reverts to a plain `build_bundle(...)` pass-through — "today's
     per-task audience resolution", no new door).
3. `tests/unit/u116-comms-audience-trigger-proof.test.py` — the acceptance
   battery (BINARY (a)-(d); (e) recorded OWED — see below).
4. `.github/workflows/u116-comms-audience-trigger-guard.yml` — CI gate.

## SMS/text-message routing decision (this unit's first act)

Per this unit's own "what" ("this unit therefore OWNS the SMS-engine
decision: whether to BUILD a text-message/SMS engine or ROUTE SMS comms
through an existing engine/channel, decided and recorded as part of this
unit's build — never a silent gap"):

**DECISION: ROUTE.** SMS is wired as a first-class `comms_type` value
(`"sms"`) handled by the SAME generic trigger email/blog/social already
ride — no second, bespoke SMS-writing engine is built.

Re-confirmed this pass (both named surfaces re-read in full, same as
U111's own investigation):
- `38-conversational-ai-system/templates/sms-workflow-ai-prompt-template.md`
  — a GHL "Build with AI" workflow spec; the live reply text is written by
  an externally-hosted conversational agent at n8n/GHL-conversation time,
  entirely outside this repo's Python `persona_for_job` consumer set.
- `44-convert-and-flow-operator/tools/engine/builders/wf5-ht-interest-builder.py`
  — pure transport/wiring for an already-authored nurture workflow; calls no
  persona/blend API at all.

Why ROUTE and not BUILD: (1) no in-tree SMS content-WRITING engine exists to
attach a call site to; (2) this repo's standing constraint is REPO/CODE SIDE
ONLY — never deploy live n8n, never call live GHL/Podbean/n8n — so a full
parallel SMS engine on the scale of Skill 50's email engine (tone-tier
library, live-send wiring) is disproportionate to what a routing decision
needs and would require exactly the live-infra reach this repo may not
touch; (3) the governance contract is engine-agnostic: whichever concrete
surface eventually sends the SMS adopts mandatory governance the moment it
calls `build_comms_trigger("sms", ...)` — proven live-exercised in the test
suite (`test_sms_routes_through_the_same_generic_trigger_as_every_other_type`),
not just documented.

A regression guard (`test_sms_adjacent_surfaces_stay_confirmed_not_found_not_stale`)
fails loud if either named surface starts referencing
`persona_for_job`/`blend_directive` without this module being updated —
mirrors U111's own `test_text_message_engine_is_recorded_not_found_and_routed_to_u116`.

## BINARY acceptance — ONB leg

- (a) each of the five comms types produces a governed, topic-populated
  artifact — one individually-failable assertion per type
  (`test_<type>_produces_governed_topic_populated_artifact`, 5/5 PASS).
- (b) no override -> `audience_source=standard`, prompt emitted, standard
  audience resolved from the fixture ICP, never fabricated (PASS).
- (c) an override -> `audience_source=specific`, the chosen audience reaches
  the written bundle's `resolved_audience.label` (PASS).
- (d) an un-factored topic, or (defensively) an unrecorded audience
  decision, is refused (`refused=True`, `bundle=None`) — never a silent
  write (2/2 PASS).
- (e) **OWED** — the Command Center leg (board card renders the chosen
  audience alongside the persona-blend chips, `PersonaSlotChips`). Same
  per-repo/offline split already established for A-U5/U115; not exercised
  in this repo. Recorded here, not silently dropped.

## Proof run (this box, this pass)

```
$ python3 -m py_compile shared-utils/persona_for_job.py \
    shared-utils/comms_audience_trigger.py \
    23-ai-workforce-blueprint/scripts/persona_blend.py
COMPILE_OK

$ OPENCLAW_PLATFORM=mac python3 shared-utils/persona_for_job.py --self-test
== persona_for_job self-test: ALL PASSED ==   (18/18, unchanged by this unit)

$ OPENCLAW_PLATFORM=mac python3 shared-utils/comms_audience_trigger.py --self-test
== comms_audience_trigger self-test: ALL PASSED ==   (6/6)

$ python3 23-ai-workforce-blueprint/scripts/test-persona-blend-matcher.py
RESULTS: 57 passed, 0 failed   (unchanged by this unit)

$ python3 23-ai-workforce-blueprint/scripts/test-a-u5-scoped-bundle.py
RESULTS: 14 passed, 0 failed   (unchanged by this unit)

$ OPENCLAW_PLATFORM=mac python3 tests/unit/u116-comms-audience-trigger-proof.test.py
  [PASS] test_page_produces_governed_topic_populated_artifact
  [PASS] test_blog_produces_governed_topic_populated_artifact
  [PASS] test_email_produces_governed_topic_populated_artifact
  [PASS] test_sms_produces_governed_topic_populated_artifact
  [PASS] test_social_produces_governed_topic_populated_artifact
  [PASS] test_no_override_defaults_to_standard_audience_recorded
  [PASS] test_override_selects_specific_audience_recorded
  [PASS] test_standard_and_specific_are_independently_recorded_not_a_shared_default
  [PASS] test_unfactored_topic_is_refused_not_silently_written
  [PASS] test_unrecorded_audience_is_refused_fail_closed
  [PASS] test_sms_routes_through_the_same_generic_trigger_as_every_other_type
  [PASS] test_sms_adjacent_surfaces_stay_confirmed_not_found_not_stale
  [PASS] test_flag_off_degrades_to_plain_build_bundle_passthrough
  [PASS] test_force_content_task_default_off_is_unchanged_behavior
  [PASS] test_force_content_task_true_overrides_the_keyword_heuristic
  [PASS] test_unknown_comms_type_raises_value_error
  [OWED] (e) board-card audience chip render — Command Center leg, not exercised here.
== U116 comms-audience-trigger proof: ALL PASSED ==
EXIT=0
```

**Fail-first proof** (2.1 discipline): `git stash` on just
`persona_blend.py`'s `force_content_task` addition, same test run -> 11/16
checks ERROR (`TypeError: build_bundle() got an unexpected keyword argument
'force_content_task'`) -> `git stash pop` restores the build, all 16 green
again. Confirms the battery is a real regression lock, not a tautology.

## What this unit does NOT claim

- It does not build the Command Center board-card audience chip (item (4) of
  the unit's own "what" / BINARY (e)) — that is the CC leg, owed, tracked
  above, not silently dropped.
- It does not build a bespoke SMS content-writing engine — the ROUTE
  decision above is deliberate and recorded, not a placeholder.
- It does not make `COMMS_AUDIENCE_PROMPT` behavior the ONLY path into
  `build_bundle` — a caller that never adopts `build_comms_trigger` (i.e.
  every pre-U116 caller) is completely unaffected; this unit adds a new,
  additive mandatory-governance call site, it does not rewire existing ones.
