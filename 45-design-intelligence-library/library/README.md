# DESIGN LIBRARY — Quick Start
**{{COMPANY_NAME}} | v2.0 | 2026-06-12**

A self-contained system that teaches any AI agent to analyze image styles, generate style-faithful prompts, run deck style systems with rotation, and execute identity-locked personal photo shoots. Drop this folder into `/master-files/`.

## For the AI agent — your five jobs

**1. "Analyze this image / batch / deck"**
→ `_system/MASTER-SOP.md` (single images, Workflow A) or `_system/PPT-ANALYSIS-SOP.md` (decks & batches — including multi-style batch clustering).
→ Output style cards per `_system/STYLE-CARD-TEMPLATE.md`; register in `INDEX.md`; test per `_system/TEST-PROTOCOL.md`.

**2. "Generate using style {ID}"**
→ `INDEX.md` → the card → category `_RULES.md` → MASTER-SOP Workflow B → negatives per `_system/NEGATIVE-PROMPTING-SOP.md` → API call per `_system/MODEL-SPECS.md`.

**3. "Build slides using PowerPoint style {ID}"**
→ Style Rotation Engine: `_system/PPT-ANALYSIS-SOP.md` §3B. Slide Manifest FIRST. Always 16:9. Resolution = client's choice (default 2K).

**4. "Put the client in it / photo shoot / retouch"**
→ `_system/PHOTO-SHOOT-SOP.md`. Identity Lock Block mandatory; skin-tone preservation is a hard rule; Seedream 4.5 Edit for surgical edits.

**5. "A new model is out"**
→ Update ONLY `_system/MODEL-SPECS.md` per its §6. Never touch style cards.

## Building a team around this library?
→ `DEPARTMENT-BUILD-BRIEF.md` — roles, role-SOP breakdown, and unit operating rules for the zero-human company repo.

## File map
```
design-library/
├── README.md                  ← you are here
├── INDEX.md                   ← master style lookup (all categories + PS shoot cards + client profiles)
├── DEPARTMENT-BUILD-BRIEF.md  ← org-builder instructions: roles, SOPs, placement
├── _system/                   ← the brain (7 files)
│   ├── MASTER-SOP.md          ├── MODEL-SPECS.md         ├── STYLE-CARD-TEMPLATE.md
│   ├── PPT-ANALYSIS-SOP.md    ├── NEGATIVE-PROMPTING-SOP.md
│   ├── PHOTO-SHOOT-SOP.md     └── TEST-PROTOCOL.md
├── {8 design category folders}/   ← each: _RULES.md + style cards
└── personal photo shoot/          ← _RULES.md + PS- shoot cards + {client}/IDENTITY.md folders
```
