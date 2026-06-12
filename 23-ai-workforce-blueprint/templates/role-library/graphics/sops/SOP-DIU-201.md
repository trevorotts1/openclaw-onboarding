# SOP-DIU-201 — Deck Style System Analysis

**SOP ID:** SOP-DIU-201
**Classification:** Vendor SOP (thin wrapper)
**Owner Role:** Deck Systems Specialist ("The Architect")
**Namespace:** Vendor band 2xx — reserved per SOP-ALLOCATION.md
**Library-version pin:** PPT-ANALYSIS-SOP v1.1, MASTER-SOP v1.1, STYLE-CARD-TEMPLATE v1.0 (§-refs verified 2026-06-12)

---

## Role Mission

The Deck Systems Specialist owns the full lifecycle of slide deck style systems: from receiving client reference decks through producing a registered, tested Deck Style System file ready for generation. This SOP governs the analysis phase — transforming raw client deck materials into a structured style system file (Shared Foundation + Family Cards + Usage Rules). It does NOT cover manifest assembly or generation (SOP-DIU-202) or the boundary decision between DIU and Presentations pipelines (SOP-DIU-611).

---

## Governing Library Files (Source of Truth — Do NOT Duplicate Content Here)

All protocol, schema, and rule detail lives in the library. This SOP points; the library governs.

| File path | Sections used | What it owns |
|---|---|---|
| `_system/PPT-ANALYSIS-SOP.md` | Full document (§§1–5) | Deck-as-style-system concept; rasterize→survey→cluster→foundation→12-dimension→prompt→usage-rules→register protocol; Deck Style System file schema; Rotation Engine (§3B); format/resolution rules (§3C); batch image-set handling (§4); practical limits (§5) |
| `_system/MASTER-SOP.md` | §4 (12-Dimension Protocol) | Per-family dimension analysis executed in PPT-ANALYSIS-SOP Step 5 |
| `_system/STYLE-CARD-TEMPLATE.md` | Full template | Card schema that family cards conform to within the Deck Style System file |
| `powerpoint-designs/_RULES.md` | Full document | Rotation Engine parameters; text strategy (a vs. b); PowerPoint-category hard rules |
| `_system/MODEL-SPECS.md` | §§2, 3, 5 | Endpoint routing; format/resolution availability per endpoint (cross-ref PPT-ANALYSIS-SOP §3C) |

**The library is law.** If any instruction below conflicts with a library file, the library wins. Report conflicts to the CDO rather than silently resolving them.

---

## Procedure (Ordered Steps)

**When to run:** A deck brief arrives requiring a new style system analysis — no existing PPT-category card in INDEX.md covers this client's brand deck aesthetic.

**Frequency:** On-demand; typically 1–3 times per week.

### Step 1 — Confirm brief completeness
Verify the brief contains: client name, reference deck files (minimum 1; 2–3 preferred), deck purpose, target audience, slide count target, resolution preference, and deadline. If any required field is missing, return the brief to the CDO with a specific list of missing fields. Do not begin analysis on an incomplete brief.

### Step 2 — Verify library-version pin
Open `_system/PPT-ANALYSIS-SOP.md` and confirm the version at its header matches the pin at the top of this SOP. If the pin is stale (library file has advanced), halt and flag to the CDO before proceeding. Do not execute analysis against a version mismatch.

### Step 3 — Rasterize source materials
Convert all reference decks to images per PPT-ANALYSIS-SOP §2 Step 1 (rasterization procedure). Store all slide images in the job directory before beginning any analysis. Do not analyze from PPTX or PDF directly.

### Step 4 — Batch survey and clustering pass
Execute PPT-ANALYSIS-SOP §2 Steps 2–3: survey all slides in batches of ~10, tag each slide's layout archetype + dominant colors + text density + imagery type, then cluster into 3–8 families. Record the slide-to-family assignment map (evidence trail required). Do not proceed to analysis until the cluster map is complete across ALL slides (do not cluster on partial evidence — see PPT-ANALYSIS-SOP §5 on large decks).

### Step 5 — Extract Shared Foundation
Execute PPT-ANALYSIS-SOP §2 Step 4: identify what ALL families share — master palette, typography system, grid and margins, recurring motifs, grade, logo/footer conventions. Document the Shared Foundation completely before authoring family cards. Write the foundation prompt block (~800–1,200 characters) following the schema at PPT-ANALYSIS-SOP §3.

### Step 6 — Run 12-Dimension Protocol per family
Execute PPT-ANALYSIS-SOP §2 Step 5 (cross-reference MASTER-SOP §4 for the 12-dimension protocol): for each family, analyze 2–3 representative slides and record ONLY what differs from or specializes the Shared Foundation. Family cards are deltas, not full repeats.

### Step 7 — Write family prompt templates
Execute PPT-ANALYSIS-SOP §2 Step 6: for each family write SHORT and MEDIUM prompt templates (each = foundation block + family delta). Write LONG templates only for families designated for standalone hero image generation (typically Family A). Measure actual character lengths for each template tier; record character counts explicitly in the card. Flag any tier exceeding 2,800 characters — Seedream hard cap is 3,000 characters.

### Step 8 — Write Usage Rules
Execute PPT-ANALYSIS-SOP §2 Step 7: document the family-to-purpose mapping, rhythm rules, source-observed proportions, and transition logic. These rules are the intelligence layer that prevents a generated deck from looking stamped. Do not skip or abbreviate.

### Step 9 — Assemble the Deck Style System file
Write the complete Deck Style System file conforming to PPT-ANALYSIS-SOP §3 schema: DECK HEADER (ID, status=draft, version, source, family roster, slide-to-family map) + SHARED FOUNDATION + FOUNDATION PROMPT BLOCK + one FAMILY section per detected family (each following STYLE-CARD-TEMPLATE.md conventions for structure) + USAGE RULES + AVOID-LIST (deck-wide, per NEGATIVE-PROMPTING-SOP) + TEST LOG (empty at this stage) + CHANGELOG.

Assign the deck ID per the PPT scheme: `PPT-{NNN}` for the parent system; `PPT-{NNN}-A`, `PPT-{NNN}-B`, etc. for families. Confirm the next available ID with the CDO or Style Analyst before assigning — do not self-assign without verification.

### Step 10 — Hand draft to Style Analyst for registration
Do NOT register the Deck Style System file in INDEX.md yourself. Hand the draft file to the Style Analyst with: the draft file path, the job directory path containing all slide images, and a one-line note specifying: number of families, whether the client's likeness appears in any reference slide, and any flags from steps 1–9. The Style Analyst owns INDEX.md registration, embedding index update, and deduplication check.

### Step 11 — Notify CDO
Confirm to the CDO: analysis is complete, the card is in the Style Analyst's registration queue, and manifest assembly (SOP-DIU-202) should not begin until the CDO confirms the card has reached production status in INDEX.md.

---

## Inputs

| Input | Required | Source |
|---|---|---|
| Client reference decks (PPTX, PDF, or slide images) | Required; 2–3 preferred, 1 minimum | CDO-provided via brief |
| Deck brief (client name, purpose, audience, slide count target, resolution, deadline) | Required; all fields must be present | CDO |
| Next available PPT-{NNN} ID | Required before Step 9 | Style Analyst or CDO confirms |
| Confirmed text strategy (a = text in generated layer; b = background-only + text-clear zones) | Required before Step 7 | CDO or inferred from `powerpoint-designs/_RULES.md` |

---

## Outputs

| Output | Format | Destination |
|---|---|---|
| Deck Style System file (status: draft) | `PPT-{NNN}_{deck-style-name}.md` in job directory | Handed to Style Analyst |
| Rasterized slide images | PNG files in job directory | Retained in job directory |
| Slide-to-family assignment map | Embedded in Deck Style System file DECK HEADER | Part of the file |
| Handoff note to Style Analyst | One-line note with file path + flags | Style Analyst's queue |
| CDO notification | Written confirmation | CDO |

---

## Handoff Conditions

**Hand to Style Analyst when:**
- The Deck Style System file is complete per PPT-ANALYSIS-SOP §3 schema (all sections present, no blanks, no TBDs).
- Character counts are recorded for all prompt tiers.
- The slide-to-family map is documented with evidence (slide numbers per family).
- The Usage Rules section is substantive — not placeholder text.

**Manifest assembly (SOP-DIU-202) begins only after:**
- The CDO confirms the card has reached production status in INDEX.md.
- Production status is confirmed by reading INDEX.md directly — not from the Style Analyst's verbal report.

---

## Escalation Triggers

| Condition | Action |
|---|---|
| 2–3 reference decks have irreconcilably different visual styles | Halt analysis. Flag to CDO: "Two distinct style systems detected. Which should govern this engagement?" Do not produce a hybrid. CDO decides. |
| Brief is incomplete at Step 1 | Return brief to CDO with specific missing fields listed. Do not begin rasterization. |
| Library-version pin mismatch at Step 2 | Halt. Flag to CDO. Update pin and re-verify §-refs before continuing. |
| Deck exceeds ~40 slides | Process in passes of 20 per PPT-ANALYSIS-SOP §5. Complete Step 2 tags for ALL slides before clustering. |
| Source material is visually incoherent (no coherent system) | Flag to CDO with diagnosis. Recommend analyzing only the strongest 10–15 slides. Do not produce a card from garbage input. |
| Any reference slide depicts a real person's likeness | Halt card authoring. Notify CDO + Photo Shoot Director — PHOTO-SHOOT-SOP §1 consent gate must clear BEFORE the card enters draft. |
| ID conflict or uncertainty on PPT-{NNN} assignment | Do not self-assign. Confirm with CDO or Style Analyst before proceeding to Step 9. |

---

*SOP-DIU-201 is a vendor SOP. Protocol detail lives in the governing library files above. This wrapper provides role context, procedure ordering, and handoff contracts. The library is the single source of truth.*
