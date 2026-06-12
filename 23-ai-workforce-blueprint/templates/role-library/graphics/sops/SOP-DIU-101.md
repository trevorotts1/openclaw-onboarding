# SOP-DIU-101 — Style Analysis & Card Creation (Vendor Workflow A)

**ID:** SOP-DIU-101
**Type:** Vendor SOP (thin wrapper)
**Owner Role:** Style Analyst ("The Eye")
**Namespace band:** 1xx (Vendor — reserved, DEPARTMENT-BUILD-BRIEF §3)
**Status:** Active
**Version:** 1.0
**Date:** 2026-06-12
**Library-version pin:** MASTER-SOP v1.1, STYLE-CARD-TEMPLATE v1.0 — §-refs verified 2026-06-12. If either file version advances, re-verify all §-refs in this wrapper before executing.

---

## Role Mission (Style Analyst)

Turn source imagery into production-grade, reusable style cards. The Style Analyst's job is to extract **how** an image looks — its transferable aesthetic DNA — and encode that into the rigid STYLE-CARD-TEMPLATE schema so any future AI session can execute it cold. The Analyst never generates images and never delivers to clients; every output goes to the Fidelity Tester first.

---

## Governing Library Files (Source of Truth — Do NOT Duplicate Content Here)

All analysis protocols, dimension definitions, prompt construction rules, and character limits live in these files. This SOP points; the library governs.

| File | Repo Path | Sections Governing This SOP |
|---|---|---|
| MASTER-SOP | `45-design-intelligence-library/library/_system/MASTER-SOP.md` | §3 (Golden Rule + variable system), §4 (12-Dimension Protocol), §5 (Prompt Tier Construction), §6 (Workflow A — end-to-end card creation) |
| STYLE-CARD-TEMPLATE | `45-design-intelligence-library/library/_system/STYLE-CARD-TEMPLATE.md` | Full file — the mandatory card schema |
| PPT-ANALYSIS-SOP | `45-design-intelligence-library/library/_system/PPT-ANALYSIS-SOP.md` | §2 (deck-sourced reference clustering, when reference material arrives as a slide deck rather than a single image) |
| INDEX.md | `45-design-intelligence-library/library/INDEX.md` | Registration rows, status authority, retire-never-delete rule |

**Rule:** If this wrapper and a library file disagree, the library file wins. Raise a flag to the CDO — do not silently follow the wrapper.

---

## Inputs

- Reference material: one or more source images, a mood board, reference deck excerpt, or brand collateral provided by the CDO or Brainstorming Buddy
- Brief: category (SI/FB/BC/MAG/SM/BN/AD/PPT/PS prefix), client name, intended use case
- Any CDO notes on known style families or exclusions

If any of the three input fields above are missing, return a specific question list to the CDO before beginning any analysis. Do not partially execute.

---

## Procedure (Ordered Steps)

**Step 1 — Intake & Brief Validation**
Confirm all three inputs are present (reference material, category, client + use case). If anything is missing, stop and return a written question list to the CDO. Do not begin analysis without a complete brief.

**Step 2 — Dedupe Pre-Check (SOP-DIU-606)**
Before doing any analysis work, run a semantic pre-check against the style index. Compose a 2–3 sentence description of the reference's dominant mood, palette, and style and query the embedding index per SOP-DIU-606. Record the top-3 similarity scores.
- Score >= 0.92: **HALT.** Surface to the CDO: *"This reference closely resembles [CARD-ID] (similarity: X.XX). Should I version the existing card or proceed with a new card?"* Do not proceed without a written CDO decision.
- Score 0.80–0.91: Proceed, but plan mandatory sibling cross-links in the new card's Model Notes.
- Score < 0.80: Proceed without flags.

**Step 3 — Provenance Classification**
Classify the reference source before any analysis:
- **Client-owned:** full analysis permitted.
- **Licensed:** record license scope in the card's Source / Provenance field; note any reproduction restrictions.
- **Third-party-style-only:** style analysis permitted; near-verbatim reproduction prohibited — record this constraint in the card's Hard Rules (Dimension 12).

If the reference depicts a real person's face or likeness (other than the client's own face with a standing self-likeness release), **HALT.** Notify the CDO and Photo Shoot Director — the PHOTO-SHOOT-SOP §1 consent gate must run before the card enters draft status. Do not proceed past this step without written consent confirmation.

**Step 4 — Execute Workflow A Analysis (MASTER-SOP §§3–6)**
Run the full 12-Dimension Analysis Protocol per MASTER-SOP §4, in order. Dimension 1 sets the vocabulary for all subsequent dimensions; do not reorder.

Fill every section of STYLE-CARD-TEMPLATE.md. No section may be left blank or marked "TBD" in a submitted draft. Apply the Golden Rule (MASTER-SOP §3) throughout: style cards describe **how** an image looks, never **what** it depicts. Use the standard variable tokens (`{SUBJECT}`, `{HEADLINE_TEXT}`, etc. — MASTER-SOP §3.2) for all content slots.

**Step 5 — Prompt Tier Construction (MASTER-SOP §5)**
Build all three prompt tiers (SHORT / MEDIUM / LONG) following the structures defined in MASTER-SOP §5. Tier character budgets are non-negotiable API limits; do not exceed them.

After writing each tier, **count the actual character length** (do not estimate) and write it explicitly in the card's character-count annotation line:
- SHORT: must be <= 500 characters.
- MEDIUM: must be <= 2,800 characters. This is the default production tier. **Flag any MEDIUM draft exceeding 2,500 characters as a warning.**
- LONG: must be <= 18,000 characters (GPT-Image-2 and Nano Banana 2 only; document model constraint in the card).

Seedream 4.5 hard cap is 3,000 characters per prompt; flag any tier intended for Seedream that exceeds 2,800 characters with a prominent warning in the card.

**Step 6 — Set Status and Emit Receipt**
Set card status field = `"draft"`.

Emit a per-card receipt file at `{CARD-ID}.json` containing:
```
{
  "id": "",
  "name": "",
  "category": "",
  "status": "draft",
  "version": "1.0",
  "authored-by": "",
  "authored-date": "",
  "similarity-scores-at-creation": [],
  "provenance-class": "",
  "sibling-cross-links": []
}
```
The receipt file is the ground-truth audit trail. It must exist before the card is handed off.

**Step 7 — Handoff to Fidelity Tester**
Hand the following to the Fidelity Tester:
1. Draft card file path
2. Per-card receipt file path
3. Reference images path (or hosted URL)
4. One-line handoff note: intended test category + any flags from Steps 2–3 (dedupe score, provenance class, likeness flags)

Do not hand off a card without all four items.

---

## Outputs

| Output | Format | Destination |
|---|---|---|
| Draft style card | STYLE-CARD-TEMPLATE.md schema | Fidelity Tester |
| Per-card receipt file | `{CARD-ID}.json` | Fidelity Tester + CDO audit trail |
| Handoff note | One-line plain text | Fidelity Tester |

---

## Handoff Conditions

Hand off to the **Fidelity Tester** when:
- All 12 dimensions are complete with no TBD fields
- All three prompt tiers are authored with actual character counts recorded
- Card status is set to `"draft"`
- Per-card receipt file exists and is current
- Any flags from the dedupe check or provenance check are documented in the handoff note

Do **not** hand off if:
- Any STYLE-CARD-TEMPLATE section is incomplete
- A dedupe halt (>= 0.92) has not been resolved in writing by the CDO
- A likeness consent gate is pending

---

## Escalation Triggers

Escalate to the **CDO** (not the Fidelity Tester) under these conditions:

| Trigger | Escalation Action |
|---|---|
| Dedupe score >= 0.92 | Halt and request written CDO decision before proceeding |
| Reference depicts a real person's face/likeness | Halt, notify CDO + Photo Shoot Director; consent gate required before draft |
| After 2 analysis attempts the reference is too low-resolution, too stylistically ambiguous, or too legally ambiguous to produce a complete card | Submit a written diagnosis to the CDO — do not submit an incomplete card |
| A library file (MASTER-SOP, STYLE-CARD-TEMPLATE) has a version bump that changes a §-ref used in this wrapper | Flag to CDO for re-verification of this SOP's §-refs before next execution |

---

## Library-Version Pin

```
MASTER-SOP v1.1 (§§3,4,5,6 — verified 2026-06-12)
STYLE-CARD-TEMPLATE v1.0 (full schema — verified 2026-06-12)
PPT-ANALYSIS-SOP v1.0 (§2 — verified 2026-06-12)
INDEX.md v1.0 (registration rules — verified 2026-06-12)
```

If any pinned file version advances, the Healer-Graphics SOP-DIU-615 sweep will flag the stale pin. The Style Analyst must re-verify all §-refs against the new version before executing this SOP again.

---

*SOP-DIU-101 is a vendor SOP. The library files listed above are the single source of truth. This wrapper provides role context, intake/output contracts, and escalation triggers only. Do not duplicate library content here.*
