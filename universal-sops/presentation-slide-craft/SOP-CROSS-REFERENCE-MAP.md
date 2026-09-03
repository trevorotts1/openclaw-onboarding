# SOP-CROSS-REFERENCE-MAP -- Cross-SOP Reference Map for the Presentations Department

**Cluster:** Infrastructure
**Status:** REFERENCE -- maps every cross-SOP citation so restructure blast radius is computable.
**Created:** 2026-08-10 (WORK-ITEM-11, Decision D5)

---

## 1. PURPOSE

When a master SOP is restructured (e.g., CLIENT-WEBINAR-DECK-SOP section renumbering, or SOP-SLIDE-00 gateway rule reorganization), this map tells you every SOP that cites the affected section so you know what needs to be updated. It is an index, not an enforcer.

---

## 2. MASTER SOP REFERENCES (cited by others)

### 2.1 CLIENT-WEBINAR-DECK-SOP.md (the deterministic pipeline)

| Cited section | Citers (SOP file:line) |
|---|---|
| Section 4.3 rule 9 | SOP-SLIDE-01 (ONE-BIG-IDEA: refs Section 4.3 rule 9 + Section 5.1 criterion 1) |
| Section 4.3 rule 15 | SOP-SLIDE-02 (AUDIENCE-FACING: refs Section 4.3 rule 15) |
| Section 5.1 criterion 1 | SOP-SLIDE-01 |
| Section 5.1 criterion 11 | SOP-SLIDE-03 (HOOK-DOCTRINE: refs Section 4.3 rule 1 + Section 5.1 criterion 11) |
| Section 9.0 model manifest | SOP-IMG-01 (KIE-CALL-MECHANICS: library-version pin) |
| Section 9 (Phase 4) + Appendix A | SOP-IMG-01 (master authority extended) |
| ../BUILDER-PROMPT.md (line 15) | CLIENT-WEBINAR-DECK-SOP (self-ref: "Read it first on every deck task") |

### 2.2 SOP-SLIDE-00-MASTER-QC-AUTOFAIL-RULESET.md (the authoritative ruleset)

| Cited section | Citers (SOP file:line) |
|---|---|
| Section 5 (machine-checkable summary table) | SOP-SLIDE-06 (lockstep procedure), sync_check.py |
| Section 8b + Section 9 code index | SOP-STORY-01 (VILLAIN-HERO-ARC: VILLAIN registered status ref) |
| Line 31 (8-slide doctrinal target reconciliation) | SOP-SLIDE-04 (DENSITY-AND-PACING), SOP-PITCH-01 (SLOW-DROP-PROCESS) |
| Entire document | SOP-SLIDE-02 (AUDIENCE-FACING: exact-document duplicate noted) |

### 2.3 SOP-SLIDE-06-EXTENSION-AND-SYNC.md (lockstep procedure)

| Cited section | Citers (SOP file:line) |
|---|---|
| Entire document (the lockstep procedure) | Every SOP header that declares registration status |
| The four mandatory steps | sync_check.py (enforces step (i) through (iv)) |

### 2.4 SOP-ENGINE-00-INTELLIGENCE-ENGINES-FRAMEWORK.md

| Cited section | Citers (SOP file:line) |
|---|---|
| Section 4 (Intelligence-Engine doctrines) | SOP-SLIDE-04 (DENSITY-AND-PACING: Section 2.1 Required Slide-Type Beats) |
| Engine 4 | SOP-STORY-01 (VILLAIN-HERO-ARC: registered status ref) |
| Engine 5 (World Intelligence) | SOP-IMG-01 (KIE-CALL-MECHANICS: GPT-Image-2 pin rationale) |

---

## 3. CLUSTER SOP CROSS-REFERENCES

### 3.1 Design-System Cluster (SOP-DESIGN-00..04)

| SOP | References |
|---|---|
| SOP-DESIGN-00 (Integration Map) | Refs AF-C2, AF-F7, AF-F6, AF-P3, AF-I1, AF-F9 (live enforcement) |
| SOP-DESIGN-01 (Typography Guide) | Refs prompt_gate.py enforcement |
| SOP-DESIGN-02 (Pure Typography Hook Slides) | Refs AF-LOCAL-CANVAS, SOP-IMG-01 Mode A/B, SOP-IMG-05 (PIL logo composite) |
| SOP-DESIGN-04 (Logo Consistency) | Refs SOP-IMG-05 (PIL fallback), AF-F7 |

### 3.2 Image-Gen Cluster (SOP-IMG-00..05)

| SOP | References |
|---|---|
| SOP-IMG-00 (Cluster Index) | Refs NAMED-STYLES.md (may not ship), skill 45 |
| SOP-IMG-01 (KIE Call Mechanics) | Refs MODEL-SPECS.md, CLIENT-WEBINAR-DECK-SOP Section 9.0 |
| SOP-IMG-02 (DIU Integration) | Refs skill 45, INDEX.md |
| SOP-IMG-03 (Style/Creative Develop) | Refs brainstorming-buddy-graphics.md, Q21/Q22 |
| SOP-IMG-04 (Signature Style Recall) | Refs MODEL-SPECS.md Section 4, MASTER-SOP Section 3.2 |
| SOP-IMG-05 (PIL Logo Composite) | Refs Decision 5C (native text overlay eliminated) |

### 3.3 North-Star Cluster (NORTHSTAR / MODE / INTEGRATION / PRIORITY / PROCLAMATION / OBJECTION)

| SOP | References |
|---|---|
| SOP-NORTHSTAR-00 | Parent of SOP-ENGINE-00, SOP-PRIORITY-01, SOP-PRIORITY-02, SOP-VISION-01, SOP-PROCLAMATION-01 |
| SOP-MODE-00 | Child of SOP-NORTHSTAR-00 |
| SOP-INTEGRATION-00 | Child of SOP-NORTHSTAR-00; carries 14-item gate |
| SOP-PRIORITY-01 | Child of SOP-NORTHSTAR-00; sibling of SOP-PRIORITY-02 |
| SOP-PRIORITY-02 | REGISTERED in PIPELINE-MANIFEST v20+; sibling of SOP-PRIORITY-01 |
| SOP-PROCLAMATION-01 | Child of SOP-NORTHSTAR-00 + SOP-PRIORITY-01 |
| SOP-OBJECTION-01 | Child of SOP-NORTHSTAR-00 + SOP-VISION-01 + SOP-PRIORITY-01 |

### 3.4 Pitch-Craft Cluster (SOP-PITCH-01..06)

| SOP | References |
|---|---|
| SOP-PITCH-01 (Slow Drop) | Refs AF-C7, SOP-SLIDE-04 DEN-1 |
| SOP-PITCH-02 (Value Stack) | Refs AF-C7 sub-condition (c), Offer Price Strategist SOP 9.2 |
| SOP-PITCH-03 (Re-Pitch) | Refs QC criteria c23/c24 |
| SOP-PITCH-04 (Wall of Wins) | Refs AF-NO-EXPERT-PROOF |
| SOP-PITCH-05 (Deliverable Bundle) | Refs fish-audio-voice-sop.md |
| SOP-PITCH-06 (Pitch Engines) | REGISTERED in PIPELINE-MANIFEST.autofails |

### 3.5 Signature Presentation Cluster (SOP-SIGPRES-00..06)

| SOP | References |
|---|---|
| SOP-SIGPRES-00 (The Law) | Refs presentation-canonical-entry.sh, AF-CANONICAL-RENDER-BYPASS |
| SOP-SIGPRES-01 (8 Questions) | Refs deck-intake-turngate.py --signature, `asked_all_at_once` deprecations |
| SOP-SIGPRES-02..05 (Phases 1-4) | Ref prove_sp_*.py provers, AF-SP-* family |
| SOP-SIGPRES-06 (Frames) | Refs frame-templates/the-{rulebook,vault,quest,original}.md |

---

## 4. HOW TO USE THIS MAP

When you restructure any SOP (renumber sections, rename files, move clusters):

1. Find the SOP in Section 2 (if it is a master/landing SOP) or Section 3 (if it is a cluster SOP).
2. Read the "Citers" column -- those are the files that must be updated.
3. Update each citer's reference to the new section number or file path.
4. Update this map to reflect the new structure.

This map is a best-effort index, not machine-enforced. When it drifts, the SOPs will carry stale references that human readers will notice. Keep it current.

---

**File written by WORK-ITEM-11 (2026-08-10) per operator Decision D5.**
