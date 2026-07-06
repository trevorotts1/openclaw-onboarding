# Form-Craft SOP Cluster (`universal-sops/form-craft/`)

The SHARED, cross-department procedure for how any department discovers and drives the **GHL native
FORM engine (Skill 6)** end to end: intake -> field resolution (standard + custom) -> `zhc_`
dependency pre-build (Skill 44) -> DUMB browser build (F1..F13) + embed splice -> render-verify +
tag workflow + certificate -> preview + human approve.

> ⚠️ **Convert and Flow = Go High Level = GHL** (one platform; the builder canvas is a cross-origin
> `*.leadconnectorhq.com` iframe inside the agency shell). Any third-party form-tool name that may
> appear in a source caption filename is a **mislabel** — this is Go High Level. Never write a
> non-GHL tool name in any deliverable.
> 🔒 **Fleet-wide repo.** No client names, no location ids, no form/folder ids, no secrets in any file.

This cluster is the `universal-sops` face of the capability. It does NOT re-implement the engine. The
authoritative machine spine lives in the skill:

- `06-ghl-install-pages/tools/ghl_form_builder.py` — the THINK layer (`_resolve_fields`,
  `plan_dependencies`, `_tag_attachment_plan`, `_build_form_plan`, `_emit_click_list` phases
  **F1..F13**, `_run_preflight` checks **F-P1..F-P8**) + the `zhc_` marker helpers (`zhc_field_key`,
  `zhc_tag`, `ensure_zhc_name`). The tool is **GLUE, not the clicker**: it emits ordered
  `agent-browser` commands and owns only its ledgers; it never mutates GHL state directly.
- `06-ghl-install-pages/references/forms-playbook.md` — the live builder rail (how forms reuse the
  browser-operator / GHL-API / embed / verify rails; the two-layer split).
- `06-ghl-install-pages/tools/SELECTORS-LIVE-form.md` — the LOCKED live selectors + the in-iframe
  `[runtime-capture]` constraint (Quick-Add tiles / tabs / field-props are NOT stably ID-anchorable).
- `06-ghl-install-pages/tools/seed-ghl-auth.py` — the token-only seed rail (Firebase refresh token;
  **NO login form, NO 2FA; never reload/full-navigate after seeding — SPA `router.push` only**).
- `06-ghl-install-pages/qc-built-form.sh` — the independent QC gate (QC-F1..F11); no "done" until it
  passes.

<!-- CRAFT_INTENT_TRIGGERS_V1 -->
## Intent triggers

This craft cluster (`universal-sops/form-craft/`) is the execution playbook for the skill(s) below. A specialist reaches for it when the client's plain-language request matches any of these intents — the client never has to name the skill or type its slash command. Source of truth: `23-ai-workforce-blueprint/skill-department-map.json` (Layer D).

| Skill | Reach for this craft when the client says… |
|---|---|
| **06** ghl-install-pages | "build me a form in GHL" · "build me a page in GHL" · "publish this page" · "install this funnel in GHL" |

Dept-scoped: only the task department's craft is offered. Operate the owning skill per the SOPs in this cluster **before** authoring by hand. Rule-Zero paid-call approval (USD announce + budget cap) still applies. Doctrine: `universal-sops/native-skill-invocation.md`.
<!-- END CRAFT_INTENT_TRIGGERS_V1 -->

## The ONE way in

A form is built by the **`build_form`** dispatcher verb in `06-ghl-install-pages/tools/v2_dispatcher.py`
(next to `build_survey` / `build_funnel`), which owns the seeded token-only browser session and the
location gate and hands the task to `ghl_form_builder.py`. The tool always runs its THINK layer
(preflight + form plan + dependency plan + click list); the DUMB browser executes only when the
dependency plan's `zhc_` fields + tags have already been created by **Skill 44**. A hand-rolled GHL
REST call, a raw browser create-on-the-fly custom field, or a build that skips the preflight is the
ungoverned path and is refused (`AF-FORM-CANONICAL-BYPASS` / `AF-FORM-PREFLIGHT`).

**Skill 6 is the ONE GHL delivery rail** — funnels, websites, surveys, AND forms. `ghl_form_builder.py`
is the authoritative form engine; **Skill 44 (`44-convert-and-flow-operator`, the `caf` PIT-authenticated
CLI)** supplies the API-created `zhc_` dependencies.

## The two-layer split (the whole point)

| Layer | Runs on | Owns | Decisions |
|---|---|---|---|
| **SMART / THINK** | a client reasoning model (Ollama-Cloud -> OpenRouter -> Gemini) | P0-INTAKE, P1-FIELDS, P2-DEPENDENCIES, and *emitting* the P3 click list | ALL of them — resolves every field property, pre-plans every `zhc_` dep, writes the fully-explicit click list |
| **DUMB / DO** | agent-browser (MiniMax M3, probe-gated -> DeepSeek v4 pro) | *executing* the P3 click list verbatim | **ZERO** — every target string, label, width, and toggle is pre-specified |

The browser operator is capability-suspect on this fleet: handed a fuzzy goal it guesses field names,
invents keys, mis-drags, and skips the embed. So it is given zero judgment — a11y ref first, exact
visible-text fallback, **STOP-and-report on miss (never an invented CSS selector)**, explicit waits,
one action per step, a screenshot after every material step.

## Files

| File | What it governs |
|---|---|
| `FORM-PIPELINE-MANIFEST.json` | The shared pipeline manifest (phases P0..P4, owning roles, SOP refs, `AF-FORM-*` gate codes). |
| `SOP-FORM-01-INTAKE.md` | Lock the form brief in ONE block; standard/custom fields, tags, embed target, styling, keep/delete defaults, form NAME; the truth gate. |
| `SOP-FORM-02-FIELDS.md` | Field resolution — standard via Quick Add, custom via Add Object Fields; labels / query-keys / width / required-XOR-hidden; the `zhc_` key convention. |
| `SOP-FORM-03-DEPENDENCIES.md` | The grocery-shopping rule — Skill 44 pre-creates every `zhc_` custom field + tag idempotently BEFORE the browser build. |
| `SOP-FORM-04-BUILD.md` | The DUMB browser build (F1..F13) — token-only seed, click list, embed capture + verbatim splice; draft only. |
| `SOP-FORM-05-CERTIFY.md` | render_check 200 + marker in the RENDERED DOM + the tag workflow + preview/approve + QC >= 8.5. |
| `MASTER-FORM-QC-AUTOFAIL-RULESET.md` | The auto-fail table every field / dependency / build / render is measured against. |

## Binding law

- **Skill 6 (`06-ghl-install-pages`) is the ONE GHL delivery rail;** `ghl_form_builder.py` is the
  authoritative form engine; **Skill 44** supplies the API-created `zhc_` deps. Nothing else touches
  GHL for a form.
- **Two ZHC conventions on purpose.** The container **NAME** (the form as it shows in the GHL Forms
  list) carries the UPPERCASE `ZHC ` prefix (`ensure_zhc_name` / `ghl_builder.ensure_zhc_prefix`) —
  the fleet convention. The machine **KEYS** (custom-field unique keys) + **TAGS** carry the lowercase
  `zhc_` marker (GHL key/tag rules: lowercase, no spaces). The client-facing **LABEL** stays human —
  the marker lives in the KEY, never the label.
- **Custom-field create-on-the-fly is DISALLOWED.** A custom field reaches the form ONLY by dragging
  the pre-created field from **Add Object Fields** (its unique key + custom-field name are LOCKED =
  proof it is the Skill-44 pre-created field). Dragging a fresh element and letting GHL mint a random
  unique-key suffix is refused.
- **`required` and `hidden` are mutually exclusive** on a field. `embed` is spliced **VERBATIM** with
  **no SRI** (`integrity` / `crossorigin`) attributes — GHL rotates the script. **Render verification
  is 200 + the marker present in the JS-hydrated DOM** — a storage/autosave 201 is NOT verification.
- **Draft only; nothing publishes without human approval.**

## Deliverable labeling grammar

Every form deliverable (locked brief, resolved field list, dependency plan, embed snippet + host-page
splice, preview) is labeled:

```
<client>__<form>__<type>__vNN
```

`type ∈ {brief, fields, deps, embed, preview}`; `vNN` is a zero-padded version (`v01`, `v02`, …).
This mirrors the shape of the funnel-craft labeling grammar; do not diverge the two.

## Flexibility = guide-not-rule

The engine is a GUIDE and a RESOURCE for how a department fulfils a form request; honor an explicit
owner choice about which fields, tags, styling, and embed target. But the `zhc_` marker, the
`required`-XOR-`hidden` exclusivity, custom-via-Add-Object-Fields, embed-verbatim, and the
render-200 + marker-in-DOM gates are hard, named `AF-FORM-*` auto-fails — they are not opinions.

## Client-runtime rule (binding)

The shipped engine on a client box NEVER uses Anthropic / `claude-*` models or operator keys.
Generation + adversarial verify run on the CLIENT's own configured provider chain; the deterministic
gates (`_run_preflight`, `qc-built-form.sh`, `render_check`) are provider-neutral stdlib Python and run
identically everywhere. Browser control + vision QC use **MiniMax M3 (probe-gated) -> DeepSeek v4 pro**;
reasoning uses **Ollama-Cloud -> OpenRouter -> Gemini** (last-resort, credited); **MiniMax M2 is
BANNED**. Publishing is human-approved (a preview URL + a labeled downloads bundle). Reporting is
operator-verbose, never client-facing noise.
