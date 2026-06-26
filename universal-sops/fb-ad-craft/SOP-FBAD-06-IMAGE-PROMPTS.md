# SOP-FBAD-06: WRITE THE IMAGE PROMPTS + MAKE THE IMAGES

**Cluster:** FB/IG Ad-Craft Rules
**Master authority:** `AD-PIPELINE-MANIFEST.json` + `MASTER-AD-QC-AUTOFAIL-RULESET.md` (Gate B + Gate C) + Design Intelligence Unit (Skill 45)
**Owning role:** AI Image Generator Specialist (the "Prompt Author" method; NO book author; never Vsevolod Pudovkin — that persona is for video/film editing)
**Stages:** S4-IMAGE-PROMPTS (`depends_on: [PICK-10]`) → S5-IMAGE-GEN (`depends_on: [S4-IMAGE-PROMPTS]`)
**Produces:** S4 → `working/s4-image-prompts.md` + `working/checkpoints/s4-receipt.json`; S5 → the images + `working/checkpoints/s5-image-receipt.json`
**Gates:** S4 — AF-FBAD-PROMPT-ORDER, AF-FBAD-PROMPT-RICHNESS, AF-FBAD-PROMPT-STYLEBLOCK, AF-FBAD-PROMPT-QC (Gate B); S5 — AF-FBAD-IMAGE-TASKID, AF-FBAD-IMAGE-SIZE, AF-FBAD-IMAGE-MODEL, AF-FBAD-TALLY-CROSS, AF-FBAD-IMAGE-QC (Gate C)

---

## 0. WHY THIS SOP EXISTS

The text is **baked into the image by the model** — there is no separate overlay/OCR
step. So the prompt must spell out, in full, BOTH the picture and the exact words to
render, and the image must come out a legible 1500×1500 square on the gpt-image family.
Two things are dropped by decision: no ad-policy gate, no separate text-reading step —
legibility is judged by an independent VISION reviewer at Gate C and by the human at
the approve pause.

---

## PART A — THE 10 IMAGE PROMPTS (S4)

### A1. The fixed build order (every prompt, in this order)

Each prompt declares these eight sections, in order (AF-FBAD-PROMPT-ORDER):

1. **subject** — who/what is in frame (the host, the guest archetype, the scene).
2. **composition** — 1:1 framing, rule-of-thirds, safe zones, where the baked text sits.
3. **typography** — the EXACT words to bake in (the chosen overlay line), the typeface
   character (weight, case), size hierarchy, and that the text must be spelled
   correctly, letter-for-letter, in English/Latin only.
4. **color-grading** — palette, contrast, mood; brand colours.
5. **lighting** — key/fill/rim, time of day, softness.
6. **quality** — resolution, sharpness, "professional ad photography / editorial".
7. **facial-intelligence** — natural faces (no melted features, no extra fingers);
   **deep skin tones rendered rich and dimensional, never ashy or grey**.
8. **brand-style-block** — the recurring brand style descriptor + the baked words
   restated, so the model cannot drop them.

### A2. The richness floor

Each prompt is **3,500–18,000 characters** (AF-FBAD-PROMPT-RICHNESS). A thin prompt
yields generic stock art; this length is what encodes creativity, typography,
color-grading, quality, and facial-intelligence in enough specificity to be one cohesive
campaign of 10.

### A3. The style-block + baked text (auto-failed)

Every prompt must SPELL OUT the brand style-block AND the exact words to bake in
(AF-FBAD-PROMPT-STYLEBLOCK). The model bakes whatever text is in the prompt, so the
exact text must be present, verbatim, with the spell-correctly instruction.

### A4. Gate B — independent prompt QC

The 10 prompts are graded by an **Independent Prompt Reviewer** (not the prompt author):
right build order, enough specific detail, on-brand, exact baked words present,
buildable as one clear image. Pass = 8.5+ no category < 7 (AF-FBAD-PROMPT-QC) AND
independent.

### A5. S4 attestation
`working/checkpoints/s4-receipt.json`:
```json
{
  "prompt_count": 10,
  "prompts": [
    { "char_count": 6200,
      "sections": ["subject","composition","typography","color-grading","lighting","quality","facial-intelligence","brand-style-block"],
      "styleblock_ok": true, "baked_text_present": true },
    "... one object per prompt ..."
  ]
}
```

---

## PART B — MAKE THE 10 IMAGES (S5)

### B1. The engine (reused as-is)

Generate via the reused Kie adapter `kie_image.py` with the **client's own KIE_API_KEY**.
The model id is `gpt-image-2-*` today and **auto-adopts any future gpt-image version**
— the gate accepts any model id beginning `gpt-image-` (AF-FBAD-IMAGE-MODEL), so a bump
to gpt-image-3 needs no code change. Render **1500×1500, 1:1** (AF-FBAD-IMAGE-SIZE).

### B2. Money discipline (the running tally — not a balance call per image)

Before each paid image, the producer checks the cheap LOCAL tally: `spent + next ≤
ceiling?` If the next image would cross, the run **STOPS** (record `would_cross: true`)
— it does not spend (AF-FBAD-TALLY-CROSS). Every image's real task-id is logged in the
run-id ledger so a retry skips finished images and never re-pays.

### B3. Anti-fabrication

Every image records a **real** `kie_task_id` (never a placeholder like `TASK_ID`)
(AF-FBAD-IMAGE-TASKID). A missing/placeholder id means the image was not really made.

### B4. Gate C — independent VISION QC (where legibility lives)

A reviewer that can actually SEE the picture and did NOT generate it grades each image:
the baked-in words read correctly (a floor item — garbled text forces a redo), looks
professional (no melted faces/extra fingers), looks like one campaign, right shape +
safe zones, represents the audience well (deep skin tones rich and dimensional). Pass =
8.5+ no category < 7 (AF-FBAD-IMAGE-QC) AND independent. **3 redos per image** (the
model is least predictable); every redo costs money and counts against the ceiling.

### B5. S5 attestation
`working/checkpoints/s5-image-receipt.json`:
```json
{
  "image_count": 10,
  "images": [
    { "kie_task_id": "a27542cb60343417e562afc2be65da5c", "width": 1500, "height": 1500,
      "model": "gpt-image-2-text-to-image", "would_cross": false },
    "... one object per image ..."
  ]
}
```
`_chk_image_taskid` / `_chk_image_size` / `_chk_image_model` / `_chk_tally_ceiling`
validate this receipt; the gpt-image-* prefix check is what makes the model
forward-compatible.
