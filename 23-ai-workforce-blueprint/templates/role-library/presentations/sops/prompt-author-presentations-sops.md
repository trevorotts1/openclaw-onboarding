# SOPs Mirror -- Prompt Author

**Source:** presentations/prompt-author-presentations.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 — Author each slide prompt to the 5,000-char standard

**When to run:** Phase P4-PROMPT, after the Typography Architect locks the design system (`working/typography/design_system.json`) and the Slide Copywriter's copy is QC-passed, and before the deterministic render.

**Inputs:**
- `working/copy/slides_copy.md` (the verbatim per-slide copy)
- `working/typography/design_system.json` (per-slide archetype + type treatment)
- `working/research/design-brief-*.md` (per-slide art direction)

**Steps:**

1. For each slide ordinal N, open the slide's archetype, type treatment, and verbatim copy.
2. Write `working/prompts/slide-NN.txt` carrying ALL 15 elements: ARCHETYPE declaration (line 1), scene, full-bleed/zone layout, every copy line with per-line weight + point size, placement/anchor, logo treatment, color from the locked STYLE BLOCK, and a dedicated NEGATIVE BLOCK with at least three "Do not …" imperatives and a spelling-lock of every on-slide word.
3. The prompt MUST be >= 5,000 non-whitespace characters (`PROMPT_CHAR_FLOOR`) and <= 18,000 (`PROMPT_CHAR_CEILING`). A prompt below the floor is NOT run, NOT rendered, NOT updated (AF-P1 / AF-PROMPT-FLOOR). Re-author until every slide clears the floor.
4. Never bake a hardcoded demographic-default split (the 60/30/10 landmine) into a prompt — representation comes from the casting ledger (SOP-CAST-01 / AF-R3).
5. WORDS-BAKED + NO SKIP/OVERLAY (FIX-4): write the slide's exact verbatim words INTO the prompt's copy elements so kie.ai bakes them in the same generation; never defer a word to a later step. The 5,000-char floor counts only when those characters include the verbatim baked words (padding the scene while omitting the words is a stub, AF-P1). Pure-typography hook/section slides are authored as full kie.ai renders, never a skipped or locally-rendered card. The prompt body must contain NONE of the banned skip/overlay phrases ("kie.ai SKIPPED", "skip kie.ai", "post-production overlay", "applied in post", "typography overlay readiness", "overlay the headline", "typography system renders the slide", "render locally", "Pillow slide canvas", "native typography card", "PowerPoint text on top"). The canonical render path is `scripts/build_deck.py` / `scripts/run_signature_deck.py` only; a hand-rolled `working/*.py` renderer, local Pillow canvas, or native-text assembler is a canonical-render bypass (AF-CANONICAL-RENDER-BYPASS / AF-LOCAL-CANVAS).
6. Hand off to the Prompt QC Specialist (Phase P-PROMPT-QC) for independent grading. Do NOT self-certify.

**Output:** `working/prompts/slide-*.txt`, one >=5,000-char prompt per slide with the verbatim words baked into the prompt body, rendered VERBATIM by `build_deck.py`.
