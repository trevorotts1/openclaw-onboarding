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
5. Hand off to the Prompt QC Specialist (Phase P-PROMPT-QC) for independent grading. Do NOT self-certify.

**Output:** `working/prompts/slide-*.txt`, one >=5,000-char prompt per slide, rendered VERBATIM by `build_deck.py`.
