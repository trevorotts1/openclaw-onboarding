# SOP-FUNNEL-03: IMAGE PROMPTS (Kie rule 12 budget) + GENERATION + PROVENANCE

**Cluster:** Funnel-Craft Rules (`universal-sops/funnel-craft/`)
**Master authority:** `49-signature-funnel/MASTERDOC.md` §4 (the 8-block order + Signature Grade Block)
**Owning role:** Signature Funnel Specialist
**Stage:** P2-PROMPTS (author) + P3-IMAGES (generate — DELEGATED to Skill 47)
**Produces:** `working/copy/prompt_ledger.json`, `working/media/media_ledger.json`
**Provers:** `49-signature-funnel/scripts/prove_sf_prompt_floor.py` (prompts) + provenance gate (images)

---

## 0. WHY THIS SOP EXISTS

A short or generic prompt produces a flat, off-brand image. The prompt band is SACRED and follows rule 12 of `07-kie-setup/references/kie-common-rules.md` (floor 80 percent, target 95 to 100 percent of the model cap; the Skill 74 v1.1 prompt-budget change in this release aligns the prover `prove_sf_prompt_floor.py` to it), enforced by a two-floor gate (length floor + structure/excellence
floor). A failing prompt physically CANNOT reach a paid Kie call.

## 1. THE 8-BLOCK BUILD ORDER (every prompt)

1 Subject & Wardrobe · 2 Composition & Shot · 3 Typography (text-bearing sections only; dominant for
Sec 11) · 4 **Signature Grade Block (verbatim)** · 5 Lighting · 6 Quality & Render · 7 Facial
Intelligence · 8 Brand-Style + Negative Block (final paragraph). Front-load subject/emotion/composition;
end-load the negative block.

## 2. HARD RULES

- **Band:** per rule 12 of `07-kie-setup/references/kie-common-rules.md` (AF-FUN-PROMPT-FLOOR / AF-FUN-PROMPT-CEILING).
- **Signature Grade Block** (~1,290 chars) embedded verbatim in block 4 of EVERY prompt (AF-FUN-PROMPT-GRADE).
- **Negative block** present in the final paragraph (AF-FUN-PROMPT-NEGATIVE).
- **No em dashes** anywhere in an image prompt (AF-FUN-PROMPT-EMDASH) — the model-safety rule.
- **Distinct-word density** floor (AF-FUN-PROMPT-DENSITY) — padding attacks fail.
- **Sec 11 is typography-as-art:** three spelling-locked words in quotes (AF-FUN-PROMPT-TYPO); no-text
  sections state "no text anywhere" explicitly.

## 3. GENERATION (P3 — DELEGATED to Skill 47)

Images are generated ONLY through the Skill 47 Kie adapter (`kie_image.py`): `GPT-Image-2.5`,
text-to-image by default, 16:9 & 2K defaults (Sec 4 → 16:9, Sec 12 → 3:4). The optional
`reference_images` hook hands the references to the adapter (≤8 refs; auto image-to-image) with the
mandatory style-only guard appended. The adapter owns the wire field name for the references; the
live GPT-Image-2.5 image-to-image route takes `input_urls` (AGENTS.md N43), so never write either
field by hand. Always use the client's own Kie key, and see `07-kie-setup/references/kie-common-rules.md`
for the shared Kie rules. NEVER hand-roll a Kie `createTask`; that is AF-FUN-CANONICAL-BYPASS.

## 4. PROVENANCE

Every generated image MUST carry a real Kie `taskId` (AF-FUN-IMG-PROVENANCE) — no native/placeholder
image. An empty image set for a page is AF-FUN-IMG-EMPTY. (Host resolution to the GHL media library is
gated at P4 by AF-FUN-IMG-HOST — see SOP-FUNNEL-04.)

## 5. VERIFY BEFORE ADVANCING

```
python3 49-signature-funnel/scripts/prove_sf_prompt_floor.py --ledger working/copy/prompt_ledger.json
```

Exit 0 = every prompt cleared both floors and P3-IMAGES may run. Any `AF-FUN-PROMPT-*` code = fix the
prompt and re-run. Never pad to length — the density floor rejects it.
