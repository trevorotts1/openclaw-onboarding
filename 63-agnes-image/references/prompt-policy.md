# Agnes Image 2.1 Flash — Prompt Policy & House Bands

Verification Date: 2026-08-26
Authority: Spec §5 & §10.5 (SPEC-hit1.md)

---

## 1. Vendor Cap Status: NOT_PUBLISHED

First-party documentation from Agnes AI (`https://wiki.agnes-ai.com/en/docs/agnes-image-21-flash.md`) does **not** publish a hard character or token ceiling for `agnes-image-2.1-flash`.

- `vendor_hard_cap_chars`: `null`
- `vendor_hard_cap_tokens`: `null`
- `owner_observed_cap_chars`: `null`
- `cap_status`: `"NOT_PUBLISHED"`

### No Invented Vendor Cap (Spec §10.5)
The ~25K figure belongs to KIE GPT Image 2 (owner-observed) and was incorrectly attributed to Agnes in earlier versions of Skill 63. Do not invent or enforce a vendor cap on Agnes.

---

## 2. House Operating Band: TARGET, Not Law

BlackCEO prompt policy defines a production prompting band:
- **House Target Floor**: 5,000 stripped characters
- **House Normal Target**: ~9,000 stripped characters
- **House Preferred Maximum**: 19,000 stripped characters
- **House Band Status**: `PENDING_ACCEPTANCE_TEST` (Rule E: band targets only after an authorized boundary/smoke test demonstrates acceptance; facts show no such test has been authorized or recorded)

### Operating Band vs Hard Rejections
Because the vendor cap is `NOT_PUBLISHED`:
1. **Prompts below 5,000 characters** are thin stubs. Short user prompts are **not** an error (§5.3). The system expands them into rich, production-grade prompts rather than rejecting the request.
2. **Prompts between 5,000 and 19,000 characters** operate in the house target zone.
3. **Prompts above 19,000 characters** trigger a non-fatal warning about exceeding house preferred headroom, but are **not** hard-rejected at the API boundary if they reflect deliberate user intent, because the vendor endpoint does not publish a cutoff.

---

## 3. General Prompt Policy Rules (Spec §5)

- **Rule A (Cap >= 20,000)**: Target 5,000–19,000 chars, ~9,000 target.
- **Rule B (Cap between 5,000 and 19,999)**: Safe ceiling below hard cap; preserve headroom.
- **Rule C (Cap < 5,000)**: 5,000 min impossible; use safe high-information prompt below limit.
- **Rule D (Token cap)**: Never convert token cap to fake exact char cap. Use tokenizer / conservative estimate.
- **Rule E (Unpublished cap)**: Mark `NOT_PUBLISHED`. Do not invent a limit. House band targets only after authorized acceptance test.

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
If a user provides a brief prompt (e.g. "futuristic Black woman CEO standing in a glass office"), the system expands it into the full production structure. Never demand the user manually write 5,000 characters.

### No Junk Padding (§5.4)
Expansion must add genuine visual control, not fluff or repetitive padding. Expand along these exact structural dimensions:

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
