# SOP-SLIDE-07: PRICE LADDER SPACING RECONCILIATION -- The Single Authoritative Gap Standard

**Cluster:** Slide-Craft Rules
**Status:** BINDING. This is the SINGLE authoritative document for the price-drop spacing standard. All three conflicting SOPs defer to this one.
**Parent SOPs reconciled:** SOP-SLIDE-04 (DECK-DENSITY-AND-PACING, DEN-1), SOP-PITCH-01 (SLOW-DROP-PROCESS, line 27-28), SOP-SLIDE-00 (MASTER-QC-AUTOFAIL-RULESET, line 31)
**Created:** 2026-08-10 (WORK-ITEM-11, Decision D5 -- fix three-way contradiction)

---

## 1. THE RULING (authoritative, 2026-08-10)

> **The 8-slide minimum gap between price drops is the GOLD-STANDARD DOCTRINAL TARGET. The 2-slide minimum gap is the HARD AUTO-FAIL FLOOR enforced by AF-C7 sub-condition (a).**

This ruling, originally stated in SOP-SLIDE-00 line 31, is the authoritative reconciliation. It is repeated here as a standalone SOP so all three SOPs (SOP-SLIDE-04, SOP-PITCH-01, SOP-SLIDE-00) reference this ONE document instead of each other, eliminating the three-way contradiction.

---

## 2. THE TWO STANDARDS (both are true; they govern at different levels)

| Standard | Value | Enforcement | Source |
|---|---|---|---|
| **DOCTRINAL TARGET** | 8 slides minimum gap between adjacent price beats | Flag for Director review when not met. NOT an auto-fail. | Gold-standard reference deck (gaps 11/16/14/8); SOP-SLIDE-04 DEN-1 (downgraded from hard gate to doctrinal target per this SOP) |
| **HARD AUTO-FAIL FLOOR** | No 2 drops within 2 slides | Auto-fail AF-C7 sub-condition (a). Deck fails QC and cannot proceed. | SOP-SLIDE-00 line 31; SOP-PITCH-01 line 27; PIPELINE-MANIFEST.autofails AF-C7 |

---

## 3. WHY TWO STANDARDS

The gold-standard reference deck achieves gaps of 11, 16, 14, and 8 slides between drops. An 8-slide gap is what the best decks produce when the anatomy is correct (formula slide, measurable results, before-and-after, decision tree, Wall of Wins at proper spacing). But the hard auto-fail floor is 2 slides because:

1. **A deck CAN be too thin to spread drops 8 apart.** The forensic reference deck had a 71%-depth anchor with drops at gaps 2, 3, and 6. That deck FAILED DEN-2 (anchor placement) AND DEN-1 (gap spacing) -- but the root cause was the thin deck (DEN-8), not the gap floor.
2. **The 2-slide floor catches catastrophic compression.** When drops land within 2 slides of each other, the value has not had time to register. This is a real and detectable defect regardless of deck length.
3. **The 8-slide target guides design, not enforcement.** The Director uses the 8-slide target when building the arc; the QC specialist uses the 2-slide floor when auto-failing.

---

## 4. HOW THE GATES INTERACT

| Gate | What it enforces | Tool |
|---|---|---|
| DEN-1 (doctrinal) | Gap < 8 = flagged for Director review | Manual: Director checks arc_allocation.json |
| AF-C7 sub-condition (a) (hard) | Gap < 2 = auto-fail | Automatic: build_deck.py `_chk_ladder_spacing` (via AF-C7) |
| DEN-2 | Anchor at 25-45% depth | Automatic via AF-DENSITY |
| DEN-8 | Section minimum slide counts | Automatic via AF-DENSITY |

A deck that passes AF-C7 sub-condition (a) but fails DEN-1 is NOT auto-failed on spacing. It is flagged so the Director can either accept the tighter spacing (because the deck is naturally short, e.g., a 30-minute talk) or add more slides.

---

## 5. THE THREE SOPS, RECONCILED

| SOP | Pre-reconciliation state | Post-reconciliation state |
|---|---|---|
| **SOP-SLIDE-04** (DECK-DENSITY-AND-PACING) | DEN-1: "Any gap < 8 = fail" (hard gate) | DEN-1: "Any gap < 8 = flag for Director review (doctrinal target); hard floor is 2 slides per AF-C7." Updated 2026-08-10 per this SOP. |
| **SOP-PITCH-01** (SLOW-DROP-PROCESS) | Line 27: "no 2 drops fall within 2 slides" (hard floor); Line 28: "DOCTRINAL TARGET: aim for at least 8 slides." CORRECT. | No change needed. Already correctly states the dual standard. |
| **SOP-SLIDE-00** (MASTER-QC-AUTOFAIL-RULESET) | Line 31: "8-slide figure is gold-standard DOCTRINAL TARGET; 2-slide is hard auto-fail floor. Do NOT introduce a contradictory hard 8-slide auto-fail." CORRECT. | No change needed. This line is the original authoritative statement. |

---

## 6. REFERENCE

- Gold-standard reference deck: ladder at s24/35/51/65/73, gaps 11/16/14/8, Wall of Wins 5 slides before offer, re-pitch s74-75.
- AF-C7 sub-conditions: (a) SPREAD -- no 2 drops within 2 slides; (b) EARNED+BUILT-UP -- every drop preceded by a buildup; (c) ADDS-value -- every price drop adds visible new value; (d) FINAL-below-ladder -- the final price is below every earlier price.
- This SOP replaces the three-way cross-reference (SOP-SLIDE-04 -> SOP-PITCH-01 -> SOP-SLIDE-00) with one authoritative document.

---

**File written by WORK-ITEM-11 (2026-08-10) per operator Decision D5.**
