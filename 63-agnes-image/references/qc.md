# Agnes Image 2.1 Flash — Real Image Quality Control (QC)

Authority: Spec §10.7 ("API success alone is insufficient"), Spec §15 (Retry ladder)

---

## 1. Visual Verification Mandate

A 200 OK from the Agnes API only proves byte delivery. Production release requires visual verification of the resulting image asset.

### QC Checklist
1. **Visual Inspection**: Download and inspect the full-resolution asset.
2. **Subject Identity & Integrity**: Subject count matches prompt; facial features, hands, limbs, and anatomical geometry are correct.
3. **Reference & Edit Fidelity (I2I)**:
   - For image-to-image transformations, verify specified elements changed while preserved elements (composition, perspective, subject layout) remained intact.
   - For logo/brand requests, verify exact geometry was preserved from the reference image.
4. **Dimension & Tier Verification**: Image resolution exactly matches requested tier × ratio (e.g., `16:9` at `2K` must be `2624x1472`).
5. **Prompt Fidelity & Typography**:
   - Palette, lighting, environment, and style directives followed.
   - Any requested text/lettering is spelled correctly and legible.
6. **Artifact & Watermark Check**: No synthetic watermarks, unnatural noise, seam lines, or boundary distortion.
7. **Directive Compliance**:
   - Logo requests used I2I (`extra_body.image`).
   - Style-reference-only directive was included verbatim when style references were attached.

---

## 2. Controlled Retry Ladder (Spec §15)

When visual QC detects a defect:
1. **Step 1 — Prompt Adjustment**: Refine the prompt (adjust lighting, composition phrasing, or negative constraints) on `agnes-image-2.1-flash`.
2. **Step 2 — Alternate Encoding / Framing**: If using I2I, verify reference image resolution, crop, or switch between URL and Data-URI format.
3. **Step 3 — Controlled Cap**: Never loop indefinitely or silently burn credits. Stop after 3 failed attempts, log exact failure symptoms, and escalate to operator.
