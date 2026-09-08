# Agnes Image 2.1 Flash — Prompt Policy & House Bands

Verification Date: 2026-09-08 (social-planner scoped override F32; prior verification 2026-08-26)
Authority: SPEC.md "Build contract for detailed image prompts" (program social-planner-september-eighth); Spec §5 & §10.5 (SPEC-hit1.md) for the unscoped base policy.

---

## 0. SCOPED OVERRIDE — Social Planner Only (F32)

The social media planner (Skill 35 social-media-planner / Skill 57 social-media-in-a-box image paths, Kie GPT Image 2 via Kie + Agnes adapters) carries a HARD house band:

- **House band (social planner ONLY)**: **9,000–19,000** stripped Unicode characters, enforced FAIL-CLOSED — 8,999 fails production preflight, 9,000 passes length checks (semantic QC still required), 19,000 passes, 19,001 fails.
- Count rule: `len(unicodedata.normalize("NFC", final).strip())` in Python; `Array.from(normalized.trim()).length` in TypeScript. Validate the FINAL transmitted prompt AFTER reference instructions and negatives are added. Record hash + count + policy version + provider/model + capability source before spend.
- Authority: `shared-utils/social_prompt_policy.json` + `shared-utils/social_prompt_compiler.py` (single source of truth; this file mirrors it for Skill 63 operators).
- **This override does NOT change bands for unrelated skills.** Outside the social planner, the general Agnes guidance below (target, not law) still applies.

---

## 1. Vendor Cap Status: NOT_PUBLISHED

First-party documentation from Agnes AI (`https://wiki.agnes-ai.com/en/docs/agnes-image-21-flash.md`) does **not** publish a hard character or token ceiling for `agnes-image-2.1-flash`.

- `vendor_hard_cap_chars`: `null`
- `vendor_hard_cap_tokens`: `null`
- `owner_observed_cap_chars`: `null`
- `cap_status`: `"NOT_PUBLISHED"`

### No Invented Vendor Cap (Spec §10.5)
The ~25K figure belongs to KIE GPT Image 2 (owner-observed; its PUBLISHED text-to-image schema maxLength is 20,000) and was incorrectly attributed to Agnes in earlier versions of Skill 63. Do not invent or enforce a vendor cap on Agnes. This uncertainty is retained: no published Agnes cap exists, so the house band governs and an authorized integration test validates the operating range.

---

## 2. House Operating Band: TARGET, Not Law (GENERAL — non-social-planner work)

BlackCEO prompt policy defines a production prompting band for general Agnes work:
- **House Target Floor**: 5,000 stripped characters
- **House Normal Target**: ~9,000 stripped characters
- **House Preferred Maximum**: 19,000 stripped characters
- **House Band Status**: `PENDING_ACCEPTANCE_TEST` (Rule E: band targets only after an authorized boundary/smoke test demonstrates acceptance; facts show no such test has been authorized or recorded)

### Operating Band vs Hard Rejections (GENERAL path)
Because the vendor cap is `NOT_PUBLISHED`:
1. **Prompts below 5,000 characters** are thin stubs. Short user prompts are **not** an error (§5.3). The system expands them into rich, production-grade prompts rather than rejecting the request.
2. **Prompts between 5,000 and 19,000 characters** operate in the house target zone.
3. **Prompts above 19,000 characters** trigger a non-fatal warning about exceeding house preferred headroom, but are **not** hard-rejected at the API boundary if they reflect deliberate user intent, because the vendor endpoint does not publish a cutoff.

### Social-planner path (override)
For social planner prompts routed through this skill, §0 above replaces the general band: 9,000–19,000 is HARD (fail-closed via the pregen gate + compiler). A short client brief is expanded by the compiler (`shared-utils/social_prompt_compiler.py`) into the full structure — never rejected for length, never padded with filler.

---

## 3. General Prompt Policy Rules (Spec §5)

- **Rule A (Cap >= 20,000)**: Target 5,000–19,000 chars, ~9,000 target. Social-planner override: hard 9,000–19,000 (§0).
- **Rule B (Cap between 5,000 and 19,999)**: Safe ceiling below hard cap; preserve headroom.
- **Rule C (Cap < 5,000)**: 5,000 min impossible; use safe high-information prompt below limit.
- **Rule D (Token cap)**: Never convert token cap to fake exact char cap. Use tokenizer / conservative estimate.
- **Rule E (Unpublished cap)**: Mark `NOT_PUBLISHED`. Do not invent a limit. House band targets only after authorized acceptance test. (Social planner: the owner requirement itself is the authorization for the scoped hard band.)

---

## 4. Boundary Probe Protocol

If high-volume production requires knowing the exact Agnes prompt ceiling:
1. Obtain explicit operator authorization before running any probe.
2. Run a non-destructive boundary probe using dedicated test fixtures.
3. Record observed results into `models.json` under `owner_observed_cap_chars` with `cap_status: "OWNER_OBSERVED"`.
4. Keep vendor documentation facts separate from observed behavior.

---

## 5. Short User Prompts & No Junk Padding (Spec §5.3, §5.4)

### Short Prompts (§5.3)
If a user provides a brief prompt (e.g. "futuristic Black woman CEO standing in a glass office"), the system expands it into the full production structure. Never demand the user manually write 5,000 characters. (Social planner: the compiler expands to the 9,000–19,000 house band automatically.)

### No Junk Padding (§5.4)
Expansion must add genuine visual control, not fluff or repetitive padding. The compiler REJECTS padding (repeated sentences, duplicated 8-word-gram ratio > 0.08) before spend (AF-PROMPT-PADDING). Expand along these exact structural dimensions:

1. **Objective** — Core scene intent and mood.
2. **Primary Subject Identity & Geometry** — Subject proportions, pose, features, expression, clothing, materials.
3. **Environment & Setting** — Architecture, interior/exterior elements, background depth, atmospheric conditions.
4. **Composition & Framing** — Rule of thirds, camera angle, perspective, eye level, focal point.
5. **Lens & Camera Language** — Focal length, depth of field, aperture, shutter effects, sensor characteristics.
6. **Lighting** — Key, fill, rim, practical lights, color temperature, directionality, shadow density.
7. **Material & Texture Detail** — Surface properties, roughness, reflectivity, fabric weave, skin texture.
8. **Palette & Color Grade** — Dominant colors, accents, contrast balance, tonal range, color harmony.
9. **Typography & Text Requirements** — Placement, font style, legibility, exact wording if any.
10. **Brand & Product Rules** — Strict color codes, proportions, positioning.
11. **Reference Image Roles** — Explicit instructions for each attached reference.
12. **Preservation & Edit Rules** (I2I) — What stays identical vs what changes.
13. **Explicit Exclusions & Negative Constraints** — Artifacts or unwanted elements to avoid.
14. **Output, Aspect Ratio & Resolution Requirements** — Tier (`1K`–`4K`), ratio enum match.
15. **QC-Critical Details** — Hands, facial geometry, edge boundaries, symmetry, fine details.

---

## 6. Reference Roles — the Logo Conflict CORRECTED (F32)

The old global style-ref rule ("use attached images only as style reference ... do not copy their subjects, faces, or text") contradicted logo preservation when the attached reference WAS the client's approved mark. The corrected rule is PER-REFERENCE, never global:

| Reference role | Instruction carried |
|---|---|
| **identity** (client's approved logo/mark) | REPRODUCE exactly: preserve the approved mark's geometry, colors, proportions and wordmark spelling. Do not redraw, recolor, restyle or reinterpret it. NEVER carries a "do not copy text/subject" directive — that directive would forbid reproducing the wordmark. |
| **product** | Match the reference product's shape, materials and labeling; do not invent product features. |
| **layout** | Layout structure and spacing only; do not copy the subject, faces or text. |
| **style** (style-only) | Style reference ONLY for color grading, lighting and composition mood — do not copy its subjects, faces, or text. NEVER carries a preserve-the-mark directive. |

A prompt that assigns a style-only do-not-copy directive to an identity reference, or a preserve-the-mark directive to a style-only reference, is CONTRADICTORY and fails preflight (AF-PROMPT-CONFLICT) before spend. `scripts/validate_prompt.py --style-ref` applies the directive only when the reference is style-only; `--logo` requires identity-role I2I intent and the preserve instruction.

Finished-image OCR, dimensions, brand and crop checks remain mandatory regardless of prompt length.
