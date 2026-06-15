# SOP-CAST-01: AUDIENCE COMPOSITION INTAKE AND DECK-WIDE CASTING LEDGER

**Cluster:** Image-Design System (representation and casting)
**Version:** v1.0.0 (2026-06-14)
**Master authority:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md (Section Q9 audience representation intake); SOP-IMG-01-KIE-CALL-MECHANICS.md (check 7, representation tally); qc-specialist-presentations-sops.md (AF-R1, AF-R2, AF-R3, AF-CAST, AF-FACE-MOOD)
**Owning role at write time:** Director of Presentations (intake HALT guard); Slide Copywriter / Brief Author (casting ledger in the brief); Slide Image Creator (per-slide people-prompt from the ledger)
**Enforced at the gate by:** QC Specialist - Presentations (AF-CAST, AF-FACE-MOOD, AF-R1, AF-R2, AF-R3)
**Purpose:** Make the client's real audience composition the single source of truth for every people-prompt in the deck. Eliminate mono-casting, inverted defaults, and any demographic not in the brief.

---

## 1. THE INTAKE FIELD: `audience_composition` (mandatory, non-defaultable)

The field `audience_composition` is added to `intake.json` as a REQUIRED, non-defaultable field. It supersedes and replaces the prior `REPRESENTATION_MIX` / `representation_ratio` usage wherever a client audience breakdown is needed.

**Format:**

```json
{
  "audience_composition": {
    "captured": true,
    "groups": [
      {"demographic": "Caucasian", "percent": 45, "notes": "primary"},
      {"demographic": "Black", "percent": 35, "notes": "primary"},
      {"demographic": "Hispanic", "percent": 10, "notes": "secondary"},
      {"demographic": "Asian", "percent": 5, "notes": "secondary"},
      {"demographic": "biracial / multiracial", "percent": 5, "notes": "secondary"}
    ],
    "source": "client interview",
    "captured_date": "YYYY-MM-DD"
  }
}
```

**HALT rule:** If `audience_composition.captured` is `false` or the field is absent, the build HALTS at intake. No brief author may write a casting ledger. No slide image creator may write a people-prompt. No images are generated. The Director flags the client immediately: "BUILD HALTED: audience_composition is not captured. Deck cannot proceed without the real audience breakdown. Please answer: who is your audience, and how do people in the images break down by demographic? Provide approximate percentages."

**No inverted default.** There is no system default demographic. A missing field is treated as NO PEOPLE (same as AF-R3), not as any assumed group. Reaching for a default demographic when the intake is silent is the exact defect this rule exists to prevent.

**Non-negotiable.** The interviewer (Deep Research Specialist or Director) must ask this question in every intake session. The intake QC checklist item A.8 already covers it; this SOP makes it a build-stopping precondition, not a scored item.

---

## 2. THE CASTING LEDGER (brief author responsibility)

The Brief Author builds a deck-wide casting ledger in the brief before any prompts are written. The ledger is a table that distributes the `audience_composition` groups across ALL people-slides in the deck, so the DECK as a whole matches the intake mix -- not each individual slide.

**Casting ledger format (in the brief, section "CASTING LEDGER"):**

```
| Slide | People | Assigned Demographic | Notes |
|-------|--------|----------------------|-------|
| 05    | yes    | Caucasian woman      | pain beat, soft morning kitchen light |
| 12    | yes    | Black man            | authority, editorial interior |
| 18    | yes    | Caucasian + Black couple | vision, golden-hour |
| 24    | yes    | Hispanic woman       | proof beat |
| 31    | yes    | Black woman          | testimonial |
| 38    | yes    | Caucasian man        | teach slide |
| 45    | yes    | Asian woman + biracial child | future-pace |
| 52    | yes    | Black man            | close / urgency |
...
```

**Distribution rule:** Allocate people-slides to demographic groups proportionally to `audience_composition.groups[].percent`, rounding to the nearest whole slide. The ledger is the authoritative allocation; QC validates the deck-wide tally against it (AF-CAST, AF-R1, AF-R2).

**Delete the per-slide demographic LOCK.** Remove any instruction of the form "do not render a demographic other than [X] on this slide." That phrasing locks each slide to one group and causes mono-casting when prompts are regenerated without changing the lock. Replace with: "render the demographic assigned by the casting ledger (see ledger entry for this slide); render with dignity, warmth, and accurate skin-tone fidelity."

**Facial-intelligence rule (applies to every people-prompt):** Real, dignified, age-appropriate, role-appropriate faces. On positive beats (vision, future-pace, celebration, close): a bright, warm, hopeful expression. On pain beats: brow tension, the "2am-spreadsheet" face (see Expression Vocabulary Table, slide-image-creator-sops.md SOP 9.2 strengthening). Never a dour, flat, or blank expression on a positive beat. This is enforced by AF-FACE-MOOD.

---

## 3. PROPAGATION RULE: REPRESENTATION FLOWS FROM INTAKE INTO EVERY PEOPLE-PROMPT

The `audience_composition` field flows from intake.json into:

1. The STYLE BLOCK (written as `REPRESENTATION_MIX` for backward compatibility with existing prompt elements 11 and 13 checks).
2. The Casting Ledger (the per-slide allocation table).
3. Every people-prompt: the Slide Image Creator reads the Casting Ledger to get the assigned demographic for slide N, writes it into element 11 (Audience Engine) as the explicit representation group.
4. The QC Specialist (AF-CAST / AF-R1 / AF-R2) tallies the deck-wide distribution against the intake percentages.

No people-prompt may go to QC without a ledger-sourced demographic line. A prompt whose element 11 Audience Engine section references only a generic group (e.g., "a diverse person") with no specific ledger-assigned demographic is a prompt-defect at Phase 3 QC.

---

## 4. THE QC ENFORCEMENT CODES (summary; full definitions in qc-specialist-presentations-sops.md)

| Code | What it catches |
|------|----------------|
| AF-CAST | Deck-wide distribution does not match intake mix within tolerance; all-one-race when intake says multicultural; inverted default (intake says multicultural but render is mono-cast to a different single group) |
| AF-FACE-MOOD | Dour or flat expression on a positive beat |
| AF-R1 | Deck-wide tally outside +/- 10 pct on generated images |
| AF-R2 | Deck-wide tally outside +/- 10 pct on the final assembled deck |
| AF-R3 | People rendered when audience_composition was not captured |

These codes are additive to the existing AF-R1 / AF-R2 / AF-R3 system. AF-CAST fires before AF-R1 / AF-R2 when the violation is obvious (all-one-race, inverted default); AF-R1 / AF-R2 fire for the proportional-distribution audit.

---

## 5. PASS vs FAIL EXAMPLES

**FAIL:** Intake says "mostly Caucasian and Black, some Hispanic, Asian, biracial" but 55 of 62 slides render Black subjects only. The all-one-race condition triggers AF-CAST immediately. Root cause: a per-slide "do not render a demographic other than [Black woman]" lock was applied to every slide. The fix: delete the per-slide lock, rebuild the Casting Ledger from the intake percentages, and re-generate the people-slides.

**PASS:** Intake says the above multicultural mix. The Casting Ledger distributes 45% Caucasian, 35% Black, 10% Hispanic, 5% Asian, 5% biracial across people-slides. Each prompt's element 11 references the assigned demographic from the ledger. The QC tally confirms the rendered deck is within +/- 10 pct of every group. AF-CAST, AF-R1, AF-R2 all pass.

**FAIL:** No audience_composition in intake.json. People-slides are generated anyway with an assumed demographic. AF-R3 fires (invented demographic). Root cause: the build was not HALTED at intake. The fix: HALT, capture the field, rebuild from intake.

---

## 6. ESCALATION / REPAIR PATH

1. If audience_composition is missing at intake: HALT the build. The Director issues the intake flag. Do not proceed until the field is captured.
2. If AF-CAST fires at Phase 5 (image QC): re-cast the failing slides using the Casting Ledger. The Slide Image Creator rewrites only the demographic assignment in element 11 and re-submits to Kie. Do not touch any other element.
3. If AF-CAST fires at Phase 6 (final deck QC): the deck cannot ship. Re-cast and re-assemble. Log in `run_ledger.json`.
4. If AF-FACE-MOOD fires: re-prompt the specific slide with the corrected Expression Vocabulary Table entry. A dour face on a vision slide is a single-slide fix, not a full re-cast.

---

## 7. INTEGRATION NOTE

This SOP extends (does not replace) the existing representation system (AF-R1, AF-R2, AF-R3, the brand-steward NO-PEOPLE default, the STYLE BLOCK representation_ratio). It adds: (a) the build-HALT precondition on a missing field, (b) the Casting Ledger as the per-slide allocation tool replacing per-slide locks, (c) AF-CAST and AF-FACE-MOOD as two new auto-fail codes in the QC gate, and (d) the explicit propagation path from intake into every people-prompt.
