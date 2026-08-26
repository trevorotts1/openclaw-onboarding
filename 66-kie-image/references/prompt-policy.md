# KIE Image — Prompt Policy & House Bands

Verification date: 2026-08-26. Authority: Spec 5 (BlackCEO Media Prompt Policy),
Spec 7.4 (per-family prompt caps), and first-party KIE research
(`01-kie-common.md`, `02-kie-image-a.md`, `03-kie-image-b.md`).

---

## 1. House band (spec 5.1)

BlackCEO house prompting policy — NOT a universal provider limit:

- desired minimum when legal: **5,000 characters**
- normal target when legal: **~9,000 characters**
- preferred maximum when legal: **19,000 characters**

The runtime selects the model FIRST, then calculates the legal band for that
model (spec 5.2). The cap fields per entry:

```
vendor_hard_cap_chars | vendor_hard_cap_tokens | owner_observed_cap_chars |
cap_status: VERIFIED | OWNER_OBSERVED | NOT_PUBLISHED | LIVE_PROBE_REQUIRED |
house_prompt_min_chars: 5000 | house_prompt_target_chars: 9000 |
house_prompt_max_chars: 19000
```

## 2. Rule A — verified cap >= 20,000

Use 5,000–19,000 chars; target ~9,000. No KIE image family currently qualifies
with a vendor-verified cap at/above 20,000.

## 3. Rule B — verified cap between 5,000 and 19,999

Do not use 19,000. Use a safe ceiling BELOW the hard cap; preserve headroom for
wrappers/rewrites. Wording per family:

- **Wan 2.7 Image** (`wan/2-7-image`, `wan/2-7-image-pro`): hard cap **5,000
  chars VERIFIED** ("with a minimum of 1 characters and a maximum of 5,000
  characters"). Do NOT force 5,000 as a minimum — 5,000 IS the ceiling.
  Target **4,500–4,900** with headroom. `validate_prompt.py` warns when a
  prompt hits >= 98% of the cap.
- **Ideogram V3** (all three routes): prompt max **5,000 chars** ("Maximum
  length: 5000 characters"), negative_prompt same. Target 4,500–4,900.
- **Imagen 4 family** (all three): prompt max **5,000 chars** ("Max length:
  5000 characters"), negative_prompt same. Target 4,500–4,900.

## 4. Rule C — verified cap below 5,000

The 5,000-char house minimum is impossible. Use a safe high-information prompt
below the model limit. No KIE image family currently sits here.

## 5. Rule D — token cap, not character cap

Qwen Image 3.0 / Pro advertise "up to 4.5K token inputs" (marketing page,
verbatim). That is a TOKEN limit, not a character limit.

- NEVER convert it to a fake exact char cap.
- Use a tokenizer when available; otherwise a conservative token estimate
  (the validators use ~chars/4) and validate before dispatch.
- The docs schemas ALSO publish maxLength 5000 chars — that is the authoritative
  API validation surface; both statements recorded in `models.json`
  (`known_inconsistencies`), status disambiguation left as
  `LIVE_PROBE_REQUIRED`.

## 6. Rule E — KIE does not publish a hard cap

Do not invent one. Mark `NOT_PUBLISHED` or `LIVE_PROBE_REQUIRED`. Use the house
operating band only AFTER an authorized boundary/smoke test demonstrates the
endpoint accepts it. Applies to: Seedream 5.0 Pro / Lite / 4.5, Nano Banana 2 /
2 Lite / Pro / legacy, FLUX.2 (all 4 routes), Z-Image.

Context windows are NOT prompt caps: Nano Banana Pro's "64K input and 32K
output" is a context window on the legacy page, not a request-field maximum.

## 7. Per-family band summary

| Family | Cap status | Legal band |
|---|---|---|
| GPT Image 2 | OWNER_OBSERVED ~25K | house 5,000–19,000 legal; 19,000+ warns (never hard-fails on observed cap) |
| Qwen 3.0 / Pro | LIVE_PROBE_REQUIRED (4.5K tokens; docs 5000 chars) | token-estimate validation; docs char max 5,000 |
| Seedream 5.0 Pro/Lite/4.5 | NOT_PUBLISHED | house band as TARGET only; no invented ceiling |
| Nano Banana 2 / 2 Lite / Pro / legacy | NOT_PUBLISHED | house band as TARGET only |
| Wan 2.7 Image | VERIFIED 5,000 | 4,500–4,900 target; >5,000 HARD REJECTED |
| FLUX.2 | NOT_PUBLISHED | house band as TARGET only |
| Z-Image | NOT_PUBLISHED | house band as TARGET only |
| Ideogram V3 | VERIFIED 5,000 | 4,500–4,900 target; >5,000 HARD REJECTED |
| Imagen 4 | VERIFIED 5,000 | 4,500–4,900 target; >5,000 HARD REJECTED |

## 8. Short user prompt is not an error (spec 5.3)

If the user says only "make me a futuristic Black woman CEO standing in a glass
office", the system EXPANDS that into the model-appropriate robust production
prompt. Never demand the user type 5,000 characters.

## 9. Do not pad prompts with junk (spec 5.4)

Long prompts must add useful control, not repetition. Expansion improves these
image-prompt dimensions (compress intelligently for small-cap models rather
than deleting the most important control information):

1. objective
2. primary subject identity/geometry
3. environment
4. composition and framing
5. lens/camera language when useful
6. lighting
7. material/texture detail
8. palette
9. typography/text requirements
10. brand/product rules
11. reference-image roles
12. preservation/edit rules
13. explicit exclusions/negative constraints
14. output/aspect/resolution requirements
15. QC-critical details

## 10. Cron/scheduled prompts (spec 5.5)

If a scheduled job will create an image later, store the creative INTENT and
route through the same model-aware prompt composer at execution time. Do NOT
freeze a 19,000-character blob that may be incompatible with a different model
selected later.

## 11. Validation

`scripts/validate_prompt.py` implements rules A–E deterministically:
- exit 0: acceptable (warnings may exist)
- exit 1: soft-fail (house band violation / cap-status concern; `--strict`
  promotes warnings to errors)
- exit 2: hard-fail (prompt exceeds a VERIFIED hard cap)

Run it BEFORE dispatch (spec 14: validation happens before charging provider
credits whenever possible).
