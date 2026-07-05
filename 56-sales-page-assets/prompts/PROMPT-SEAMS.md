# PROMPT SEAMS — Skill 56 baked prompts (credential + intake neutralization)

The legacy "Sales Page Writer" prompts (Airtable-sourced) are baked into `prompts/baked/` as
**provider-agnostic** artifacts. This file documents every seam that was neutralized so the shipped
prompts carry **zero secrets, zero Anthropic ids, and zero prior-client content**.

**Runtime set = 12 active prompts (FIX-COPY-04(iii)).** Of the 14 legacy extracts, **12 ship as active
runtime prompts** and **2 legacy stubs** (`13-test-prompt-airtable-mcp-demo.md`, `14-empty-record.md`)
were **archived** to `prompts/baked/_archive/` — they were never real generation prompts (an Airtable
MCP test stub and an empty record). The runtime iterates **`prompts/baked/_index.json`** (the canonical
ordered manifest), never a directory glob, so a stray/junk `.md` is never silently picked up.

## 0. Persona Task-Mode seam (FIX-XC-02a — grounding, prepended to every copy prompt)

The copywriter-persona Step-0 grounding (SOP-SALESPAGE-01 §3 Step 0) resolves the matched copy persona
via `persona-selector-v2.py --department marketing` and logs it to `persona-selection-log.md` in the run
dir. Its **Section 4 "Agent Governance Framework"** is injected into the baked copy prompts through this
seam so the writer builds TO the persona's Task Mode, not merely names it:

| Seam | Resolves to | Notes |
|---|---|---|
| `{{SELECTED_PERSONA_ID}}` | the `selected_persona:` slug from `persona-selection-log.md` | a registered Skill-22 persona slug; fail-closed if absent (`AF-SP56-INTAKE-PERSONA-LOG`). |
| `{{PERSONA_TASK_MODE}}` | verbatim Section-4 Execution Standard + Decision Logic + Definition of Done + Failure Patterns from the matched `persona-blueprint.md` | ground every asset's headline/offer/CTA in this Task Mode, INSIDE the brand-voice-lock + locked brief + compliance envelope. The persona NAME alone does not load it. |

> `prove_sp_intake.py` fails closed (**AF-SP56-INTAKE-PERSONA-LOG**) when the persona-selection-log is
> absent or names no registered slug — so the seam is never rendered ungrounded and generation never
> starts without a grounded copy persona (mirrors FAB-QC D4).

## 1. The three legacy secrets — NEUTRALIZED to env placeholders (`secrets_scrubbed = 3`)

The legacy n8n engine hardcoded three inline plaintext secrets in node parameters. Their **literal
values live ONLY in the never-copied `source/raw-workflow-export.json`** (HANDOFF systemic fix #6: raw
exports are never copied into a worktree). The three credential SEAMS are neutralized to env
placeholders in the shipped skill:

| # | Legacy inline secret | Legacy node | Neutralized to | Notes |
|---|---|---|---|---|
| 1 | Anthropic API key (`x-api-key`) | `Claude Copy` (main page Version A) | `${CLIENT_TEXT_API_KEY}` | The whole Anthropic leg is re-pointed to the CLIENT's own writing provider — never Anthropic. |
| 2 | OpenAI bearer token (`Authorization`) | `Image Generation (OpenAI Image 1)` | `${CLIENT_IMAGE_API_KEY}` | Images delegate to Skill 47 or the client's own image provider. |
| 3 | ImgBB key (query `key`) | `ImgBB Upload` (public re-host) | **REMOVED entirely** | Re-hosting is replaced by Skill 6 `ghl_media.py`; there is no ImgBB in the client path. |

> Verified: a pattern scan of the 14 source `.md` extracts found **zero literal key values** in them —
> the extracts are the Airtable prompt text only; the literal keys never left `raw-workflow-export.json`.
> The neutralization above closes the three credential injection points at the seam level so no key can
> ever be reintroduced through the baked prompts. `${CLIENT_TEXT_API_KEY}` / `${CLIENT_IMAGE_API_KEY}`
> resolve at runtime from the CLIENT box's own provider config (never the operator's, never Anthropic).

## 2. Provider / model ids — GENERALIZED

Legacy provider framing was rewritten to be provider-agnostic (zero Anthropic ids anywhere):

- "Advanced Sales Page Creation Instructions **for Anthropic Claude**" -> "... for your configured writing model"
- "Enhanced Sales Page Creator ... **for Gemini 2.5**" -> "... for your configured writing model"
- `claude-3-7-sonnet-*`, `gemini-2.5-pro-preview-*` -> `your-writing-model`
- `gpt-image-1`, `DALL-E` -> `your configured image model`
- `GPT-4.1`, `OpenAI` -> `your configured model` / `your configured provider`

A/B variants are produced by **two client models OR two persona prompts on one client model** — never an
Anthropic/Gemini split as in the legacy engine.

## 2b. Optional image Brand-Style block from a design style card (FIX-XC-02c)

The image-prompt template carries an OPTIONAL Brand-Style seam. When the intake supplies
`${INTAKE.style_card_id}` (a registered Skill 45 `FN-...` card), DIU Workflow B resolves the card and its
**LONG tier** is embedded VERBATIM as the **Brand-Style block (block 8)** of every image prompt, ahead of
the always-on negative directives — the same block-8 contract the Skill 6 rail
(`ghl_image_stage._derive_copy_specs`) and Skill 49 (PROMPT 7) use, so a page and its sales-page assets
can share ONE registered style. **Unset `style_card_id` = current behavior** (brand-color default; block 8
is the default Brand-Style + Negative paragraph). Purely additive — the intake field is `required:false`
and the image floor prover (`prove_sp_prompt_floor.py`) is unaffected when it is absent. The per-image
`aspect_ratio` remains an API parameter carried on the prompt entry (FIX-IMG-03), never baked into prompt
text.

## 3. Prior-client content — GENERALIZED

The legacy main-page prompts (01, 02) embedded a real prior client's full page HTML (brand name, logo
URL, founder name, ImgBB image URLs, a default first name) as a few-shot example. All of it was removed:

- Embedded `<!DOCTYPE html> … </html>` example page(s) -> a single neutralization marker
  (`[NEUTRALIZED: prior-client example page HTML removed …]`); the section SPEC around it is preserved.
- `i.ibb.co` / `storage.googleapis.com` / `drive.google.com` image + logo URLs -> dropped.
- Prior-client brand/product tokens -> dropped.

## 4. Infra / intake seams — MAPPED to `${INTAKE.*}`

Airtable record/base/table ids and n8n webhook body references were replaced with intake seams that bind
to the fleet-clean intake contract (`intake/spa-intake.schema.json`):

| Legacy webhook body key | Intake seam |
|---|---|
| `Sales_Page_Writer_Brand_Info` / `brand_info` | `${INTAKE.brand_info}` |
| `Sales_Page_Writer_Product _Info` (embedded space, repaired) | `${INTAKE.product_info}` |
| `Sales_Page_Writer_Primary_Brand_Color` / `brand_color` | `${INTAKE.primary_brand_color}` |
| `Sales_Page_Writer_Brand_Logo` / `brand_logo` | `${INTAKE.brand_logo}` |
| `Sales_Page_Writer_Prompt_Count` | `${INTAKE.image_prompt_count}` |
| `upsellOneProductDescription ` (trailing space, repaired) / `upsell_desc` | `${INTAKE.upsell_desc}` |
| `downSellOneProductDescription` / `downsell_desc` | `${INTAKE.downsell_desc}` |
| `bumpSaleProductDescription` / `bump_sale_desc` | `${INTAKE.bump_desc}` |
| `highTicketProductDescription` | `${INTAKE.high_ticket_desc}` |
| `first_name` / `last_name` / `email` | `${INTAKE.first_name}` / `${INTAKE.last_name}` / `${INTAKE.email}` |
| image slice, e.g. `image_array.split(",").slice(4,8)` | `${INTAKE.field}` (the P4 media CDN map supplies the per-stage image URLs) |

Airtable `rec…`/`app…`/`tbl…` ids and the "Source: base … table …" provenance lines were dropped.

## 5. The baked prompts (12 active + 2 archived)

The runtime set is the 12 active prompts below, in `prompts/baked/_index.json` order:

| File | Asset | Prover that gates its output |
|---|---|---|
| `01-starter-page-prompt.md` | main page A (8-section + countdown) | `prove_sp_main_structure.py` |
| `02-starter-page-b-prompt.md` | main page B (loader/animation variant) | `prove_sp_main_structure.py` |
| `03-bump-sell-prompt.md` | bump copy (40-80 words + checkbox) | `prove_sp_bump_band.py` |
| `04-upsell-1-prompt-page-a.md` | upsell A (Trevor Otts 9-section) | `prove_sp_upsell_structure.py` |
| `05-upsell-1-prompt-page-b.md` | upsell B (Emotional Hijacking persona) | `prove_sp_upsell_structure.py` |
| `06-downsell-1-prompt-page-a.md` | downsell A (recovery) | (9-section reuse) |
| `07-downsell-1-prompt-page-b.md` | downsell B | (9-section reuse) |
| `08-high-ticket-page-a-prompt.md` | high-ticket A (Sovereign Architect) | `prove_sp_highticket_band.py` |
| `09-high-ticket-page-b-prompt.md` | high-ticket B | `prove_sp_highticket_band.py` |
| `10-high-ticket-page-c-prompt.md` | high-ticket C | `prove_sp_highticket_band.py` |
| `11-hight-ticket-product-overview-prompt.md` | high-ticket product overview | — |
| `12-high-ticket-product-ad-copy-prompt.md` | high-ticket ad copy | — |

**Archived (not in the runtime set)** — moved to `prompts/baked/_archive/`:

| File | Why archived |
|---|---|
| `_archive/13-test-prompt-airtable-mcp-demo.md` | legacy Airtable MCP test stub — never a real generation prompt |
| `_archive/14-empty-record.md` | legacy empty Airtable record — never a real generation prompt |

All (12 active + 2 archived) verified clean: zero `api.anthropic.com` / `claude-*` / `Gemini` /
`OpenAI` / `gpt-image-1` ids, zero `ibb.co` / Drive URLs, zero Airtable/webhook infra ids, zero
prior-client tokens, zero secrets.
