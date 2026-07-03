# MASTER FORM QC AUTO-FAIL RULESET (`universal-sops/form-craft/`)

The table every GHL form intake, field, dependency, build, and render is measured against. Each code is
a hard, named gate — never advisory, never an agent self-score. The deterministic checks live in
`ghl_form_builder.py` `_run_preflight` (F-P1..F-P8) and the independent `06-ghl-install-pages/qc-built-form.sh`
(QC-F1..F11); those are the source of truth. This is the `universal-sops` mirror. SOP-LOCKED: keep this
table in lockstep with the engine's preflight + the QC script.

> 🔒 Fleet-wide: placeholders only (`<client>`, `<LOCATION_ID>`, `<form>`, `<FORM_ID>`). No real ids.

## P0-INTAKE — `_run_preflight` F-P1/F-P2/F-P3 + brief lock

| Code | Fires when |
|---|---|
| AF-FORM-INTAKE-TYPE | The request is not a GHL form build (wrong engine / mislabelled non-GHL tool). |
| AF-FORM-INTAKE-LOCATION | `location_id` is missing/empty (F-P1) — nothing can resolve without it. |
| AF-FORM-INTAKE-SPEC | No form spec present: neither `form_fields` nor a `title`/`form_name` (F-P3). |
| AF-FORM-INTAKE-EMBED-TARGET | The embed target (funnel / website / page) was assumed rather than captured at intake. |
| AF-FORM-INTAKE-TRUTHGATE | A tag, consent line, or bonus was not confirmed REAL — the engine never fabricates a tag/consent. |
| AF-FORM-INTAKE-UNLOCKED | The brief was not locked in ONE block before field resolution began. |

## P1-FIELDS — `_resolve_fields` + F-P4/F-P6/F-P7

| Code | Fires when |
|---|---|
| AF-FORM-ZHC-KEY | A CUSTOM field's unique key is not `zhc_<snake_slug>` (F-P4). |
| AF-FORM-REQ-HIDDEN-EXCL | A field has BOTH `required` and `hidden` set (mutually exclusive). |
| AF-FORM-CUSTOM-VIA-OBJECT-FIELDS | A custom field is not routed via **Add Object Fields** (`add_via != add_object_fields`, F-P7) — i.e. create-on-the-fly. |
| AF-FORM-QUERYKEY-SLUG | A standard field's query key is not a lowercase, no-space, no-special slug. |
| AF-FORM-FIELD-MISSING | A requested field never landed on the canvas (or a kept default was wrongly deleted). |

## P2-DEPENDENCIES — `plan_dependencies` + F-P5

| Code | Fires when |
|---|---|
| AF-FORM-DEP-UNCREATED | A custom field / tag stamped `create` was NOT created by Skill 44 before the browser build ran (or dragged create-on-the-fly). |
| AF-FORM-TAG-ZHC | A tag in the dependency plan is not `zhc_<snake_slug>` (F-P5). |
| AF-FORM-DEP-DUP | The plan created a duplicate of an existing `zhc_` field/tag instead of stamping it `reuse` (idempotency broken). |
| AF-FORM-DEP-LEDGER-MISSING | The dependency plan / created-ID ledger is absent at build time — no proof the deps exist. |

## P3-BUILD — `_emit_click_list` (F1..F13) + seed rail + embed splice

| Code | Fires when |
|---|---|
| AF-FORM-AUTH-SEED | The session was not token-only seeded, OR a `reload`/full-navigate ran after seeding (must be SPA `router.push` only). |
| AF-FORM-BUILD-DRAFT | The build published/went-live instead of stopping at draft + preview (nothing publishes without human approval). |
| AF-FORM-EMBED-VERBATIM | The embed snippet was altered, re-minified, or given `integrity`/`crossorigin` (SRI) attrs — it must be spliced VERBATIM. |
| AF-FORM-INVENTED-SELECTOR | The operator shipped an invented CSS selector for an in-iframe `[runtime-capture]` surface instead of snapshot-and-bind / STOP-and-report. |
| AF-FORM-NAME-ZHC | The form container NAME does not carry the UPPERCASE `ZHC ` prefix (F-P6). |

## P4-CERTIFY — `render_check` + Skill 44 tag workflow + `qc-built-form.sh`

| Code | Fires when |
|---|---|
| AF-FORM-RENDER-200 | `render_check` did not return HTTP 200 for the host page carrying the embed. |
| AF-FORM-MARKER-DOM | The form widget marker (`zhc_` / `data-form-id="<FORM_ID>"`) is absent from the RENDERED (JS-hydrated) DOM — a storage/autosave 201 is NOT verification. |
| AF-FORM-TAG-WORKFLOW | No `Form Submitted -> Add Contact Tag {{contact.zhc_…}}` workflow was built (tag creation ≠ tag attachment). |
| AF-FORM-CERT-MISSING | `qc-built-form.sh` did not emit a PASS certificate (QC-F1..F11 / rubric >= 8.5). |
| AF-FORM-PROCESS-INTEGRITY | A phase was skipped or the ledger chain (plan -> deps -> click list -> operator report -> QC) is broken/out of order. |

## Front door — `_run_preflight` (F-P1..F-P8) + dispatcher

| Code | Fires when |
|---|---|
| AF-FORM-PREFLIGHT | Preflight F-P1..F-P8 did not ALL pass before the browser was dispatched. |
| AF-FORM-CANONICAL-BYPASS | A hand-rolled GHL REST call, a raw create-on-the-fly custom field, or a build that skips `ghl_form_builder.py` was detected. |
| AF-FORM-LOCATION-COMINGLE | The build targeted a location other than the named client's own (F-P2 location gate) — client resources never co-mingle. |

---

**Client-runtime note:** every deterministic check (`_run_preflight`, `qc-built-form.sh`, `render_check`)
is stdlib-only, model-free — it runs identically on a client box using no model at all. Generation
(field resolution / plan) runs on the CLIENT's own configured provider chain, never Anthropic, never
operator keys. Browser control + vision QC use MiniMax M3 (probe-gated) -> DeepSeek v4 pro; MiniMax M2
is BANNED.
