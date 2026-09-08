# Prompt 05 — Visual Prompt Architect (capability-routed, unified brief)

- **Source workflow:** `03-image-generator` (03-Social Media in a Box Image Generator)
- **Model at export time:** OpenRouter `google/gemini-2.0-flash-001` (runtime = client-configured provider)
- **Purpose:** Converts the day's theme into a detailed image prompt using the UNIFIED IMAGE BRIEF and CAPABILITY-BASED routing — subject / lighting / style, brand and reference roles, safe areas, destination dimensions; no aspect-ratio params in the text (the provider call carries the ratio/resolution).
- **F29 (2026-09-08):** the stale Midjourney v6 naming is REMOVED. The pipeline routes by model CAPABILITY (reliable text rendering, reference handling) from `shared-utils/model-capabilities.json` — never by a model name frozen in a prompt. The historical export note above is provenance, not routing truth.
- **Anonymization:** verified clean — no client names or secrets in this prompt text. Client-identifying data in this workflow family lives ONLY in raw-export `pinData` (see ANALYSIS.md `client_name_locations`); it is excluded here.

## The unified image brief (F29 — required before any prompt is written)

One brief per asset, carrying ALL of these fields (validated by `shared-utils/social_image_brief.py` `validate_brief`; missing fields fail BEFORE prompt compilation and before any provider is charged):

| Field | Required content |
|---|---|
| `brand_palette` | Verified hex palette from the approved brand profile (never ad-hoc colors). |
| `logo_rules` | Usage, placement, clear space, and per-reference `role` (identity / product / layout / style) with role-correct instructions. An identity/logo reference PRESERVES the approved mark; a style-only reference must not copy subject/text — per-reference instructions, never global (F32 correction). |
| `audience` | Intended audience and intended emotional response. |
| `composition` | Focal message, hierarchy, framing, whitespace, crop ratio. |
| `copy` | Exact approved on-image text (empty string = explicitly NO text), spelling lock, placement, hierarchy. |
| `approved_assets` | The approved reference/product asset ids actually cleared for use. |
| `safe_areas` | Platform safe areas (keep-in zone) so platform UI never covers critical content. |
| `destination_dimensions` | Platform + ratio + pixels (e.g. instagram / 4:5 / 1080x1350). |

## System

```
You are a Visual Prompt Architect. Your goal is to translate the day's brief into a complete, production-grade image prompt for the routed image model.
```

## User

```
INPUT THEME: "{{ $json.theme }}"
UNIFIED IMAGE BRIEF: {{ $json.imageBrief }}

ROUTING (capability, not brand name):
- If the brief's copy.on_image_text is non-empty (text-bearing asset), the prompt
  is routed to a model that declares reliable text rendering
  (shared-utils/model-capabilities.json): Ideogram V3 DESIGN, GPT Image 2 via Kie,
  or Agnes through their verified adapters. Never route text-bearing assets to a
  non-text model by name or habit.
- Non-text imagery may route to any verified image-generation model.

TASK:
1. Convert the brief + theme into a detailed image prompt: SUBJECT, LIGHTING,
   STYLE, COMPOSITION, and the role-correct instructions for every approved
   reference (identity preserves the mark; style-only does not copy subject/text).
2. State the exact on-image copy verbatim when copy.on_image_text is non-empty;
   state "NO text in this image" when it is empty.
3. Respect safe_areas and destination_dimensions in the composition.
4. Do NOT include aspect-ratio parameters in the text (the provider call carries them).
5. Never invent client-specific product facts.

OUTPUT:
Return ONLY the prompt text.
```

## Post-generation validation (F29 — before scheduling)

The finished creative is validated, not assumed:

1. **Dimensions** — delivered pixels must equal `destination_dimensions.pixels` (`AF-VQC-DIMENSIONS`).
2. **Crops/safe areas** — the delivered crop must respect the declared safe areas (`AF-VQC-CROP`).
3. **Legibility/OCR + spelling** — the actual vision reviewer sees the real asset; delivered text must match the approved copy exactly (`AF-VQC-OCR`).
4. **Brand consistency** — approved palette present, logo reproduced faithfully (`AF-VQC-BRAND`).
5. **Receipts** — preview URL and original URL recorded; the preview references the approved revision (`AF-VQC-REVISION`, `AF-VQC-RECEIPT`).
6. **Isolation** — one failed asset is isolated with bounded regeneration cost/retries and alternatives exposed for approval; one failure NEVER discards successful copy or other account assets.

A delivered asset failing any check above is fixed/regenerated within bounds — it never schedules.