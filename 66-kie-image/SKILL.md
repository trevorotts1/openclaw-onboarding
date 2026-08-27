---
name: kie-image
description: >
  KIE Image generation via the KIE.ai Market API. Owns model selection across
  14 image families (GPT Image 2, Qwen Image 3.0/Pro, Seedream 5.0 Pro/Lite/4.5,
  Nano Banana 2/2 Lite/Pro/legacy, Wan 2.7 Image, FLUX.2, Z-Image, Ideogram V3,
  Imagen 4), payload validation against a machine-readable registry, prompt
  sizing against published limits, asynchronous task dispatch with callbacks or
  polling, and mandatory real visual QC.
metadata:
  version: "1.0.0"
  priority: HIGH
---

# KIE Image — Model Selection, Validation, Dispatch, and QC

The KIE.ai Market API (`POST https://api.kie.ai/api/v1/jobs/createTask`) serves
every image family this skill covers. All tasks are asynchronous: the 200 from
createTask means the task was CREATED, never completed. This skill owns the
whole path: pick the model, size the prompt, validate the payload, dispatch,
wait (callback or poll), and visually QC the result.

## Routing policy (spec 7.5)

1. **Explicit wins.** If the user names a model/family and it can satisfy the
   request, use it — capability match and user preference win. Never "fix" an
   explicit pick.
2. **Else GPT Image 2 is the preferred default** for high-fidelity general KIE
   image generation/editing, product/brand images, and detailed long-form
   creative instructions (owner's preference, spec 7.4), when compatible
   (respecting its ratio/resolution exclusions).
3. Else by capability match:
   - Nano Banana Pro / Nano Banana 2 — strong general/multi-reference
     alternatives.
   - Seedream 5.0 Pro — complex, controlled, multi-reference, information-rich
     visuals.
   - Ideogram V3 — typography/design-heavy image tasks.
   - Qwen Image 3.0 — structured layouts, multilingual content,
     information-dense composition.
   - Wan 2.7 Image — when its specific control/edit workflow (bbox regions,
     gallery mode) fits and the 5,000-char ceiling is acceptable.
   - Lite/Fast models (Nano Banana 2 Lite, Seedream 5.0 Lite, Imagen 4 Fast) —
     speed/cost/high-volume.
4. **Never call any model universally "best."** Do not pad the routing table
   with unrelated image models (spec 7.2).

## Mandatory sequence: route -> select -> validate -> dispatch

1. **Normalize the alias** (`scripts/normalize_alias.py`) — transcription
   errors ("Quinn", "C Dream", "Idiogram", "Imagine 4", "GPT-img2") resolve to
   real families. Z-Image is its OWN family and never merges into Qwen, even
   for "Z Image by Quinn".
2. **Select** (`scripts/select_image_model.py`) — maps the natural-language
   request to a canonical model id + task, or fails with a valid alternative.
3. **Validate the prompt** (`scripts/validate_prompt.py`) — model-aware band
   check against the registry cap (rules A–E). Verified caps hard-fail
   (exit 2); owner-observed and NOT_PUBLISHED only warn.
4. **Validate the payload** (`scripts/validate_payload.py`) — reference counts,
   MB/format, ratio/resolution enums, per-family rules (GPT Image 2
   per-resolution exclusions, Wan n/bbox, Ideogram strength, seedream
   output_format gaps). Validation happens BEFORE dispatching so bad payloads
   never burn credits.
5. **Dispatch** — POST createTask; then callBackUrl (Skill 46 relay) or
   recordInfo polling (2–3s initial, stepped backoff, respect 429, stop
   ~10–15 min), OR both (callbacks preferred, polling as fallback).
6. **QC** — actually inspect the image (references/qc.md), confirm
   dimensions/ratios/ref fidelity/typography/anatomy; retry only along the
   controlled 5-step ladder, never silently burning credits.

## Registry (machine-readable source of truth)

`models.json` — 30 entries covering all spec 7.2 families and their routes,
each with `source_url`, `last_verified_at`, `cap_status`, prompt caps, house
band, reference limits, resolutions, ratios, and known inconsistencies. Every
numeric limit is traceable to a quoted first-party value fetched 2026-08-26.
NOT_PUBLISHED/UNDETERMINED values are `null` — nothing is invented.

Key cap facts (full matrix: `references/models.md`):

- GPT Image 2: owner-observed ~25,000 chars (`OWNER_OBSERVED` — never treated
  as vendor-verified; house band 5,000–19,000 with ~9,000 target is legal).
- Qwen 3.0/Pro: 4.5K **tokens** advertised — token-aware validation only; never
  converted to a fake char cap (rule D). Docs schemas: maxLength 5000 chars.
- Wan 2.7 Image: 5,000 chars VERIFIED — do NOT force 5,000 as a minimum;
  target 4,500–4,900.
- Ideogram V3, Imagen 4 family: 5,000 chars VERIFIED (target 4,500–4,900).
- All other families: cap NOT PUBLISHED — house band is a TARGET, never an
  invented vendor law; no hard rejections above 19,000 unless a verified cap
  exists.

## House prompt band (spec 5)

- desired minimum when legal: 5,000 chars; normal target: ~9,000; preferred
  max: 19,000. Short user prompts are EXPANDED, never rejected (§5.3).
- Expansion adds real control (objective, subject, environment, composition,
  lens, lighting, material, palette, typography, brand rules, reference roles,
  preservation rules, negatives, output requirements, QC details) — never junk
  padding (§5.4).
- Cron/scheduled jobs store creative INTENT and compose the prompt at
  execution time against the model chosen then (§5.5).

## Prerequisites

- TYP (Skill 01) and Back Yourself Up (Skill 02) first — see PREREQS.json.
- `KIE_API_KEY` present in the box's secrets (env var NAME per repo
  convention; KIE docs use the literal `YOUR_API_KEY` placeholder — nothing
  documents the env var). Verify SET, never print the value. See INSTALL.md.
- `curl` available for verification and dispatch.

## Files in This Folder (Reading Order)

1. **SKILL.md** — you are here.
2. **models.json** — machine-readable capability registry (30 entries).
3. **references/models.md** — human golden matrix + per-family guidance.
4. **references/prompt-policy.md** — prompt rules A–E, per-family bands.
5. **references/api-patterns.md** — generic createTask/recordInfo conventions
   and per-family request schemas.
6. **references/qc.md** — real visual QC checklist + retry ladder.
7. **INSTRUCTIONS.md** — daily usage walkthrough.
8. **INSTALL.md** — credential check + connect verification.
9. **EXAMPLES.md** — copy-paste curl payloads (GPT Image 2 t2i/i2i, Wan bbox,
   Seedream i2i, NB2 i2i).
10. **CORE_UPDATES.md** — core-file wiring (performed by `wire.sh`).
11. **QC.md** — verification checklist.
12. **scripts/** — `normalize_alias.py`, `select_image_model.py`,
    `validate_prompt.py`, `validate_payload.py` (each with `--self-test`).

## Critical Things to Know

- **200 from createTask is NOT completion.** All KIE generation tasks are
  asynchronous. Poll recordInfo (state enum: `waiting`, `queuing`,
  `generating`, `success`, `fail`) or use callBackUrl.
- **Validators run before dispatch.** Never send too many refs, an illegal
  ratio/resolution for the model, an over-limit prompt, or an unsupported mode
  combination.
- **GPT Image 2 ratio rules are hard:** 2K/4K exclude 5:4, 4:5, 3:1, 1:3, 9:21;
  `auto` yields 1K only; 1:1 cannot convert to 4K. `validate_payload.py`
  enforces all three.
- **Wan bbox/n rules:** each input image supports up to 2 boxes; `n` 1–4
  (1–12 with `enable_sequential`); input images min 240 px per side, max 10 MB.
- **Credential:** `KIE_API_KEY` env var; never echo/cat/log the value.
- **Rate limits:** 20 new generation requests/10 seconds, 100+ concurrent per
  account; 429 = rejected before queueing — back off. Media deleted after 14
  days; result URLs expire ~24h — persist immediately when needed.
- **Logo I2I rule:** any client logo/brand-mark generation MUST be image-to-
  image with the logo as a reference, never text-to-image; style-reference
  attachments carry the mandatory style-reference-only directive.
- **Retry ladder:** same model corrected -> same model alternate encoding ->
  another same-provider model (only if selection was automatic or permitted) ->
  another provider (only if permitted) -> stop and report. Never silently burn
  credits.
