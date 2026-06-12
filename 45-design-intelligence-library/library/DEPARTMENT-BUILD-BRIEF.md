# DEPARTMENT BUILD BRIEF — Design Intelligence Unit
**Version:** 1.0 | **Date:** 2026-06-12
**Audience:** The org-builder AI of the zero-human company (GitHub onboarding repo). This brief tells you how to turn the attached Design Library into roles, SOPs, and an operating unit.

---

## 1. WHAT YOU HAVE BEEN HANDED

A complete, self-contained Design Library: a style-analysis and prompt-generation system (`design-library/`). It contains the full operating knowledge — analysis protocols, model specs with verified API limits and JSON templates, prompt-tier rules, negative prompting, deck style systems with a rotation engine, personal photo shoot mode, and testing protocols. Your job is NOT to rewrite this knowledge. Your job is to wrap it in roles, role-level SOPs, and handoffs so it runs as a department function.

## 2. PLACEMENT RECOMMENDATION

**Default: do NOT create a new department.** Create a new unit inside the existing Graphics Department called the **Design Intelligence Unit (DIU)**. Rationale: this work is graphics production with an intelligence layer; a separate department creates a handoff seam exactly where you want none.
**Exception:** if no Graphics Department exists in the repo, create one and make the DIU its founding unit.

## 3. RECOMMENDED ROLES (5 core + 1 optional)

### Role 1 — Style Analyst ("The Eye")
- **Mission:** Turn source images into production-grade style cards.
- **Owns:** MASTER-SOP §§3–4 (Golden Rule + 12-Dimension Protocol), STYLE-CARD-TEMPLATE, batch clustering (PPT-ANALYSIS-SOP §§2, 4).
- **Outputs:** Style cards (status: draft), INDEX registrations.
- **Hands off to:** Fidelity Tester (every new/edited card).

### Role 2 — Deck Systems Specialist ("The Architect")
- **Mission:** Analyze decks into style systems; generate decks via the Rotation Engine.
- **Owns:** PPT-ANALYSIS-SOP in full (families, foundation blocks, usage rules, §3B Rotation Engine, §3C format/resolution), powerpoint-designs/_RULES.
- **Outputs:** Deck Style System files, Slide Manifests, generated slide sets.
- **Hands off to:** Producer (manifest approval on 10+ slide decks), Fidelity Tester (cohesion checks).

### Role 3 — Generation Operator ("The Operator")
- **Mission:** Execute "use style {ID}" requests end-to-end.
- **Owns:** MASTER-SOP Workflow B, MODEL-SPECS (routing, tiers, JSON assembly, the Editing Hierarchy), NEGATIVE-PROMPTING-SOP (merge + delivery), category _RULES compliance.
- **Outputs:** Assembled API requests, generated images, generation logs.
- **Hands off to:** Producer (all deliverables), Fidelity Tester (off-style results → diagnosis mode).

### Role 4 — Photo Shoot Director ("The Director")
- **Mission:** Run Personal Photo Shoot Mode: identity-locked scenes, wardrobe, poses, stylization, and retouching.
- **Owns:** PHOTO-SHOOT-SOP in full (consent, identity sourcing hierarchy, Identity Lock Block, all shoot modes, the retouch chain), personal-photo-shoot/_RULES, client IDENTITY.md profiles, Seedream 4.5 Edit mastery.
- **Outputs:** Identity profiles, contact sheets, finished shoot deliverables, shoot cards.
- **Hands off to:** Producer (consent verification + every deliverable).
- **Note:** likeness consent rules and the skin-tone hard rule are non-negotiable in this role's SOP.

### Role 5 — Fidelity Tester ("The Critic")
- **Mission:** Nothing reaches production untested; failures become institutional memory.
- **Owns:** TEST-PROTOCOL in full (transfer tests, 12-dimension scoring, patch loop, diagnosis mode), avoid-list growth (NEGATIVE-PROMPTING-SOP §5), card status lifecycle + INDEX status sync.
- **Outputs:** Test logs, scored verdicts, patched prompts, version bumps.
- **Hands off to:** Style Analyst (cards failing the Golden Rule on far-transfer), Producer (3-strike escalations).

### Role 6 (optional) — Library Registrar
- INDEX integrity, version/changelog audits, MODEL-SPECS updates when new models ship (its §6 protocol), quarterly avoid-list prunes. Fold into Role 1 if headcount should stay lean; spin out once the library exceeds ~50 cards.

---

## 4. SUGGESTED ROLE-SOP BREAKDOWN (names you can create)

| SOP file to author | For role | Built from library files |
|---|---|---|
| SOP-DIU-101 Style Analysis & Card Creation | Style Analyst | MASTER-SOP §§1–6, STYLE-CARD-TEMPLATE |
| SOP-DIU-102 Batch & Multi-Style Clustering | Style Analyst | PPT-ANALYSIS-SOP §§2–4 |
| SOP-DIU-201 Deck Style System Analysis | Deck Systems Specialist | PPT-ANALYSIS-SOP §§1–2 |
| SOP-DIU-202 Deck Generation & Rotation Engine | Deck Systems Specialist | PPT-ANALYSIS-SOP §§3B–3C, powerpoint-designs/_RULES |
| SOP-DIU-301 Style-Based Generation (Workflow B) | Generation Operator | MASTER-SOP §7, category _RULES |
| SOP-DIU-302 Model Routing & API Execution | Generation Operator | MODEL-SPECS |
| SOP-DIU-303 Negative Prompt Assembly | Generation Operator | NEGATIVE-PROMPTING-SOP |
| SOP-DIU-401 Personal Photo Shoot Operations | Photo Shoot Director | PHOTO-SHOOT-SOP §§1–5, 7–9 |
| SOP-DIU-402 Retouching & Surgical Editing | Photo Shoot Director | PHOTO-SHOOT-SOP §6, MODEL-SPECS Editing Hierarchy |
| SOP-DIU-501 Fidelity Testing & Patch Loop | Fidelity Tester | TEST-PROTOCOL |
| SOP-DIU-502 Library Governance & Versioning | Registrar (or Analyst) | INDEX, MODEL-SPECS §6, changelog rules |

Each role SOP should be a thin wrapper: role mission, the pointer list to the governing library files (the library stays the single source of truth — do not copy its content into role SOPs, or they will drift), role-specific procedures, and handoff contracts.

---

## 5. OPERATING RULES TO ENCODE AT UNIT LEVEL

1. **Producer gatekeeper:** every client-facing output routes through the producer. No AI role ever delivers directly to a client or author.
2. **The library is law:** roles execute the library's protocols; proposed protocol changes go through the Registrar function with a changelog entry — never silent edits.
3. **Single source of truth:** model knowledge lives ONLY in MODEL-SPECS; style knowledge ONLY in cards; role SOPs point, never duplicate.
4. **Escalation:** 3 failed patch attempts on one dimension → human/producer escalation with evidence (TEST-PROTOCOL §4).
5. **Intake routing:** "analyze this" → Analyst (or Deck Specialist if multi-slide). "Generate with style X" → Operator. "Anything with a real person's likeness" → Director. "It came out wrong" → Tester.

---

## 6. ONBOARDING SEQUENCE FOR NEW AI EMPLOYEES IN THIS UNIT

1. Read `design-library/README.md` then `_system/MASTER-SOP.md` in full.
2. Read the files your role owns (Section 3 above).
3. Read your role SOP (thin wrapper).
4. First task: shadow-run — re-execute a completed, logged task from the Test Log and compare your output to the recorded result before taking live work.
