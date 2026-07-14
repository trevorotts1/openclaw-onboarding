# U111 (E5-6, closes G4) — "any content" blend-governance proof — evidence

Unit: U111 (P1, ONB). Binding: D1 (the blend GOVERNS voice + content-writing
in every engine, never advisory, no exemptions). Deps: U1/A-U1 (the seam
carries the governing blend; VERIFIED already merged to `main`, confirmed at
`shared-utils/persona_for_job.py:247-266` — `blend`/`topic_hint` kwargs on
`_run_selector` and `persona_for_job` match the A-U1 description exactly).

## First-act engine identification (primary-source read, this pass)

Re-derived from the authoritative `persona_for_job` consumer list
(`shared-utils/persona_for_job.py` module docstring, "ENGINE SCOPE (F4.3)":
consumers 49/50/52/53/54/56/57) plus a targeted repo search for
`persona_for_job`, `persona_blend`, `build_bundle`, `blend=True`, `--blend`
across the whole tree.

| Content type | In-tree engine | Canonical entry point (pre-U111 state) |
|---|---|---|
| Email | `50-email-engine` | `tools/persona_canonical.py` — imported ONLY `persona_for_job`'s helper functions (`section4_excerpt`, `_persona_display_name`) for a style-tier crosswalk excerpt; **never called `persona_for_job()` itself** — zero blend path. |
| Blog | `57-social-media-in-a-box` (golden mode `examples/golden-modes/blog/`; no standalone blog engine exists) | `scripts/persona_adapter.py::resolve()` — called `persona_for_job(...)` for `personaSource=="adapter"`, single-persona mode only, no `blend` kwarg passed at all. |
| Newsletter | Same as blog — `57-social-media-in-a-box` golden mode `examples/golden-modes/newsletter/`, same entry point | Same as blog. |
| Text-message (SMS) | **NOT-FOUND** — no in-tree content-writing engine | n/a |

Confirmed NOT the proven consumers named in the master spec's own G4 framing
("funnel copy + social already proven"): that framing refers to
`persona_for_job`-seam consumption in general (pre-A-U1, single-persona
mode) via `49-signature-funnel/scripts/copy_persona_blend_seam.py` (funnel
copy) — which DOES already call `build_bundle`/blend directly (not through
`persona_for_job`, a parallel/older seam pre-dating A-U1) — and Skill 6's
per-page bundle ladder (`06-ghl-install-pages/tools/persona_bundle_ladder.py`,
also a direct `--blend` selector call). Neither `35-social-media-planner` nor
`57-social-media-in-a-box`'s `persona_adapter.py` had any blend-mode call
before this unit — confirmed by direct read, not assumed from the spec.

## Text-message (SMS) — NOT-FOUND, read in full

Two SMS-adjacent surfaces were located and read in full; neither is a
persona/blend consumer:

1. `38-conversational-ai-system/templates/sms-workflow-ai-prompt-template.md`
   — a GHL "Build with AI" workflow spec. The inbound SMS reply is routed via
   a webhook body carrying `agent_id`/`model` to an externally-hosted
   conversational AI agent; that agent writes the live reply text at
   n8n/GHL-conversation time. This is entirely outside this repo's Python
   `persona_for_job` consumer set — it is a live-agent surface, not a
   Python content engine.
2. `44-convert-and-flow-operator/tools/engine/builders/wf5-ht-interest-builder.py`
   — builds ONE hardcoded GHL nurture workflow (5 email + 1 SMS step) by
   PARSING a pre-written external markdown doc
   (`docs/email-sequences/ht-interest-rewrite.md`, a DIFFERENT repo —
   "social-media-tool repo" per its own docstring). It calls no
   persona/blend API at all (single- or blend-mode) — pure transport/wiring
   for already-authored copy, not a content-writing engine.

**Routing decision:** mandatory blend-governance for outside-world text/SMS
communication is already in-spec as its own master unit — **U116** (E6-2,
ADD-2: "any OUTSIDE-WORLD COMMUNICATION — a page, blog, email, text/SMS,
social post... MUST be governed by the blend"), which explicitly names
text/SMS as one of the five comms types it wires mandatory governance +
the audience-confirmation trigger onto. U111 does not build a second,
competing SMS engine ahead of U116; it records the gap as a real,
machine-checked NOT-FOUND assertion (see the test file below) so the gap
stays visible rather than silently closing.

## Build (additive, backward-compatible)

1. `50-email-engine/tools/persona_canonical.py` — added `blend_block()`, a
   genuine `persona_for_job(..., blend=True)` call site (department
   `"marketing"` — Skill 50's real seeded fleet department per
   `test_department_routing.py`, never the unseeded literal `"email"`).
   Existing `persona_block()` style-crosswalk untouched.
2. `57-social-media-in-a-box/scripts/persona_adapter.py` — `resolve()`'s
   `"adapter"` branch now passes `blend=bool(cfg.get("blend"))` and a
   `topic_hint` through to `persona_for_job`. Default OFF — byte-identical
   to pre-U111 behavior for every caller that never sets `cfg["blend"]`
   (proven by `test_adapter_blend_omitted_is_unchanged_single_persona_shape`
   and the pre-existing self-test cases, both still green).
3. `tests/unit/u111-any-content-blend-proof.test.py` — the acceptance
   battery (binary acceptance (a)/(b)/(c)).
4. `.github/workflows/u111-any-content-blend-guard.yml` — CI gate.

## Proof run (this box, this pass)

```
$ python3 -m py_compile 50-email-engine/tools/persona_canonical.py \
    57-social-media-in-a-box/scripts/persona_adapter.py shared-utils/persona_for_job.py
COMPILE_OK

$ OPENCLAW_PLATFORM=mac python3 shared-utils/persona_for_job.py --self-test
== persona_for_job self-test: ALL PASSED ==   (18/18, unchanged by this unit)

$ OPENCLAW_PLATFORM=mac python3 57-social-media-in-a-box/scripts/persona_adapter.py --self-test
== persona_adapter self-test: ALL PASSED ==   (9/9, incl. 4 new U111 blend cases)

$ OPENCLAW_PLATFORM=mac python3 tests/unit/u111-any-content-blend-proof.test.py
  [PASS] test_email_engine_receives_governing_blend
  [PASS] test_blog_mode_receives_governing_blend
  [PASS] test_newsletter_mode_receives_governing_blend
  [PASS] test_blog_and_newsletter_are_independently_invoked_not_a_shared_singleton
  [PASS] test_text_message_engine_is_recorded_not_found_and_routed_to_u116
  [PASS] test_email_style_crosswalk_path_unchanged
  [PASS] test_adapter_blend_omitted_is_unchanged_single_persona_shape
== U111 any-content blend-governance proof: ALL PASSED ==
EXIT=0
```

**Fail-first proof** (2.1 discipline — the test would have failed against
the pre-U111 tree): `git stash` on just the two engine files, same test run
→ 5/7 checks FAIL/ERROR (`AttributeError: module 'persona_canonical' has no
attribute 'blend_block'`; blog/newsletter outputs carry no `blend_directive`
because `blend` was never passed through) → `git stash pop` restores the
build, all 7 green again. Confirms the battery is a real regression lock,
not a tautology.

## What this unit does NOT claim

- It does not decommission any engine's local voice logic (that is U114,
  P3, scoped to Skills 51/58/54/59 — the product-voice engines — not the
  content engines this unit proves).
- It does not make `blend=True` the DEFAULT for email/blog/newsletter in
  production — it proves the call-site CAPABILITY is wired correctly and
  reachable; flipping the production default (if desired) is a separate,
  intentionally out-of-scope decision for the owning engine's own train
  (U111's own revert note: test-only, additive, no runtime default changed).
- It does not build an SMS content engine — that gap is explicitly routed to
  U116, never silently closed.
