---
name: design-intelligence-library
description: Design Intelligence Unit (DIU) — a self-contained image-style analysis and generation system. Ships a 12-dimension style analysis protocol, style-card library with 3 prompt tiers (SHORT/MEDIUM/LONG), deterministic deck generation via Style Rotation Engine, personal photo shoot mode with identity-lock guarantees, and a fidelity-test protocol (≥4.0 avg, 3-strike escalation). Routes across 7 image-generation endpoints (GPT-Image 2 T2I/I2I, Nano Banana 2, Seedream 4.5 T2I/Edit, Ideogram V3, Wan 2.7). Five specialist roles + extended Brainstorming Buddy + gatekeeper (Chief Design Officer) + operating rules. Skill 07 (Kie.ai) prerequisite.
version: 1.3.2
---

# Skill 45: Design Intelligence Library

## Teach Yourself Protocol read order

1. **SKILL.md** (this file) — what the DIU is, the protocol layers, the role model, prerequisite
2. **INSTALL.md** — seeding procedure, two-zone update contract (repo-owned _system/rules vs box-owned INDEX/cards)
3. **INSTRUCTIONS.md** — runtime guide (semantic embedding search is NOT YET AVAILABLE; INDEX.md is the lookup surface)
4. **CORE_UPDATES.md** — exact text to merge into AGENTS.md / TOOLS.md / MEMORY.md
5. **library/README.md** — quick-start for the AI agent (analyze / generate / deck / photo shoot / model update)
6. **library/_system/MASTER-SOP.md** — the 12-dimension style analysis brain
7. **CHANGELOG.md** — skill version history

Per N3 ("read before act"), do not skip. Per N4, follow in declared order.

---

## What This Skill Is

Skill 45 ships a **Design Intelligence Unit (DIU) library** — a knowledge system that teaches any AI agent to:

1. **Analyze images** across 12 style dimensions (render, composition, subject, color, grading, lighting, typography, layering, subject-background, negative space, workflow, unity).
2. **Extract transferable style** — separate content from aesthetic DNA so the style card works for any new subject.
3. **Write style cards** in three tiers (SHORT ≤500 / MEDIUM ≤2,800 / LONG ≤18,000 chars), calibrated to real API limits.
4. **Generate style-faithful images** via 7 endpoints (GPT-Image 2, Nano Banana 2, Seedream 4.5, Ideogram V3, Wan 2.7), routed per category and model-fitness rules.
5. **Analyze decks** as systems (not slides) and run **Style Rotation Engine** — deterministic multi-slide generation with rhythm constraints and cohesion.
6. **Execute identity-locked personal photo shoots** — real-person imagery with consent gates, identity preservation, and surgical retouching (Seedream 4.5 Edit).
7. **Test fidelity** across 12 dimensions (≥4.0 avg, no <3, zero hard-rule violations), patch failures in a 3-strike loop, escalate to producer on the third failure.

End state: a human says *"Use style FB-003 to advertise [product] with [headline]"* and the AI produces an on-brand, style-faithful image without re-analysis.

---

## SCOPE: what Skill 45 decks ARE and are NOT (boundary contract)

**Webinar, funnel, sales, and audience presentation decks are NOT owned by Skill 45.** They are owned by the **Presentations department** and governed by `universal-sops/CLIENT-WEBINAR-DECK-SOP.md` plus the presentations role library. The DIU **Style Rotation Engine** (`PPT-ANALYSIS-SOP.md` §3B) serves **brand / strategy / campaign / pitch / internal decks only**: visual-style-driven multi-slide systems, not communication-driven webinar funnels.

This boundary is enforced, not advisory: the Deck Systems Specialist's SOP 9.5 [SOP-DIU-611] explicitly FORBIDS webinar/funnel/audience decks from routing through the DIU Rotation Engine (`presentations/00-START-HERE.md`). Skill 45 and the Presentations dept are **two separate systems joined by one explicit crossing**: the Presentations Brand Steward MAY submit a reference deck to the DIU Style Analyst for a PPT-tier style card, whose ID is then handed to the Presentations Slide Image Creator. That is the ONLY legal handoff. A webinar/audience deck never runs end-to-end through Skill 45.

---

## The five specialist roles (live in role-library/graphics after converge)

| Role | Slug | Owns |
|---|---|---|
| **Style Analyst** ("The Eye") | `style-analyst.md` | MASTER-SOP analysis, style-card creation, batch clustering, Library Registrar duty (dormant; activates at 50+ cards) |
| **Deck Systems Specialist** ("The Architect") | `deck-systems-specialist.md` | PPT-ANALYSIS-SOP, Style Rotation Engine, Slide Manifest, multi-slide cohesion |
| **Generation Operator** ("The Operator") | `generation-operator.md` | MASTER-SOP Workflow B (generation), negative prompting, API routing, model selection |
| **Photo Shoot Director** ("The Director") | `photo-shoot-director.md` | PHOTO-SHOOT-SOP (consent, identity lock, retouch), legal escalation, identity-profile maintenance |
| **Fidelity Tester** ("The Critic") | `fidelity-tester.md` | TEST-PROTOCOL, fidelity testing, patch loops, diagnosis mode, avoid-list growth, status lifecycle |

All five roles report to **Chief Design Officer** (producer / gatekeeper). No DIU role delivers directly to the owner; all outputs route through CDO Gate 4.

---

## Intake routing (who gets the request)

| Request | Routes to |
|---|---|
| "Analyze this image / batch" | Style Analyst (Deck Systems Specialist if .pptx/.pdf/4+ images) |
| "Generate using style {ID}" | Generation Operator |
| "Build slides using PPT style {ID}" | Deck Systems Specialist |
| Anything involving a real person's likeness | Photo Shoot Director (consent gate FIRST) |
| "It came out wrong" / off-style results | Fidelity Tester (Diagnosis Mode) |
| Fuzzy new idea | Brainstorming Buddy — Graphics (extended), then CDO |

**Extended Brainstorming Buddy — Graphics:** the existing BB-graphics role receives 4 new questions capturing DIU intent (reference images, style ID reuse, likeness/identity consent, deck slides + resolution). The BB role's question bank is extended; it remains the single front door per dept.

---

## Prerequisite: Skill 07 (Kie.ai)

This skill requires **Skill 07 (kie-setup)** to be completed on the box. The DIU routes style-based generation and photo shoots through Kie.ai endpoints (GPT-Image 2, Nano Banana 2, Seedream 4.5, Ideogram V3, Wan 2.7). 

- **If Skill 07 is installed:** the KIE_API_KEY is available; DIU generation proceeds normally.
- **If Skill 07 is absent:** `INSTALL.md` step 3 will flag the missing prerequisite and provide the satisfy path.

---

## Governing protocol (binding for this skill)

This skill is governed by `../QC-PROTOCOL.md` (repo root) — the Sub-Agent Handoff and Mandatory QC Protocol. Every install runs the 10-category QC rubric (8.5 threshold) BEFORE declaring done.

---

## The two-zone runtime contract (CRITICAL DESIGN RULE)

**Problem:** style cards and client identity profiles are CLIENT DATA and never enter the repo. The repo ships the system files + library schema + _RULES. Each box owns the mutable copy.

**Solution:** a two-zone seeding contract:

| Zone | Ownership | Files | Update behavior |
|---|---|---|---|
| **System** | Repo | `_system/*` + every `_RULES.md` | Overwritten on every skill update (rsync) |
| **Client Data** | Box | `INDEX.md`, style-card files, `personal-photo-shoot/{client}/` identity folders | Seeded ONCE if absent (`cp -n`); NEVER overwritten |

**Practical:**
- First skill install: INSTALL.md seeds both zones.
- Skill re-install / `update-skills.sh` run: _system and _RULES are refreshed; INDEX and cards persist.
- Library Registrar (dormant duty) owns INDEX integrity, card versioning, and quarterly avoid-list pruning.

**Idempotent, additive, with timestamped backup.** The QC script (`qc-design-intelligence-library.sh`) verifies the installer cannot clobber a populated INDEX.md.

---

## File structure

```
45-design-intelligence-library/                    (skill root)
├── SKILL.md                                       ← you are here
├── INSTALL.md                                     ← seeding: two-zone contract, step-by-step
├── INSTRUCTIONS.md                                ← runtime: agent guide + optional embedding-index
├── CORE_UPDATES.md                                ← appends to AGENTS.md / TOOLS.md / MEMORY.md
├── CHANGELOG.md                                   ← version history
├── PREREQS.json                                   ← declares Skill 07 (KIE_API_KEY) dependency
├── qc-design-intelligence-library.sh              ← QC: verify 20 library files, INDEX integrity, INDEX clobber-safety, no client data committed, diu_validator gate self-tests
├── skill-version.txt                              ← skill-independent version (see CHANGELOG.md for the current value)
├── scripts/
│   └── diu_validator.py                           ← deterministic gates (prompt-length caps, routing interlock, fidelity + 3-strike) — stdlib only
├── docs/
│   └── VENDOR-BUILD-BRIEF.md                      ← vendor document (provenance stamp, superseded)
└── library/                                       (system library — copy to $OC_ROOT/master-files/design-library/)
    ├── README.md                                  ← agent quick-start guide
    ├── INDEX.md                                   ← EMPTY SEED; box fills this at runtime
    ├── _system/ (7 protocol files — repo-owned)
    │   ├── MASTER-SOP.md                          ← the analysis brain
    │   ├── MODEL-SPECS.md                         ← API limits, model routing, JSON templates
    │   ├── NEGATIVE-PROMPTING-SOP.md              ← 3-layer avoid-list system
    │   ├── PHOTO-SHOOT-SOP.md                     ← consent, identity lock, retouching
    │   ├── PPT-ANALYSIS-SOP.md                    ← deck analysis + Style Rotation Engine
    │   ├── STYLE-CARD-TEMPLATE.md                 ← rigid schema every style card follows
    │   └── TEST-PROTOCOL.md                       ← fidelity testing + patch loop
    ├── advertisement-designs/_RULES.md            ← category constraints (hard rules per design type)
    ├── banner-designs/_RULES.md
    ├── book-cover-designs/_RULES.md
    ├── facebook-ad-designs/_RULES.md
    ├── funnel-page-designs/_RULES.md
    ├── magazine-cover-designs/_RULES.md
    ├── personal-photo-shoot/_RULES.md
    ├── powerpoint-designs/_RULES.md
    ├── single-image-designs/_RULES.md
    └── social-media-designs/_RULES.md
```

---

## What gets installed on each box

On-box runtime home (seeded once, persisted thereafter):

```
$OC_ROOT/master-files/design-library/           ← OC_ROOT = /data/.openclaw (VPS) | ~/.openclaw (Mac)
```

INSTALL.md manages the idempotent seeding. On update (e.g., `update-skills.sh` run), the _system files and _RULES are refreshed; INDEX.md and style cards survive.

---

## The five DIU operating rules (from vendor, applied as written)

1. **Producer Gatekeeper:** All DIU outputs route through the Chief Design Officer (producer) for Gate 4 owner approval. No role delivers directly to the owner/client.
2. **Library Is Law:** Changes to library files (_system/ or _RULES) go through this repo (Skill 45 CHANGELOG), never silent on-box edits. Updates via `update-skills.sh` / `bump-version.sh`.
3. **Single Source of Truth:** Each role's SOP Section 9 starts with *"Open and follow `<library file + §>` — that file is the single source of truth; this SOP adds only role-specific procedure, inputs/outputs, and handoffs."* Style-card logic never duplicates into role files.
4. **3-Strike Escalation:** Fidelity Tester fails a card 3 times → escalates to CDO with evidence. CDO decides: patch again, retire the card, or escalate to owner if the failure is systemic.
5. **Intake Routing:** Brainstorming Buddy — Graphics (extended) captures the DIU intent; CDO routes to the right specialist per the routing table above.

---

## Binding enforcement — coded gates (`scripts/diu_validator.py`)

The gates above are no longer prose-only. `scripts/diu_validator.py` (Python stdlib, zero third-party deps) makes four of them MECHANICAL — a violation is a hard non-zero exit an agent cannot narrate past (mirrors Skill 47's deterministic-gate pattern):

| Gate | Command | Enforces | Fail exit |
|---|---|---|---|
| **Prompt-length caps** | `diu_validator.py prompt-caps --tier {SHORT\|MEDIUM\|LONG} --prompt-file P` | SHORT ≤500 / MEDIUM ≤2,800 / LONG ≤18,000 chars (MODEL-SPECS tier table). Over-cap ⇒ fall back a tier, never silently truncate. | 3 (`AF-DIU-PROMPT-CAP`) |
| **DIU routing interlock** | `diu_validator.py route-check --deck-kind K` | SOP-DIU-611 §D.1 coded hard stop: audience/webinar/funnel/sales/virtual-event decks CANNOT run on the Rotation Engine — route to Presentations. | 2 (`AF-DIU-ROUTING-INTERLOCK`) |
| **Consent + minor + PII gate** | `diu_validator.py consent-check --identity-file IDENTITY.md` | PHOTO-SHOOT-SOP §1 fail-closed: real-person likeness needs documented+dated consent, an attested-adult subject (Minors = HARD NO), and an at-rest-protected biometric store. Unconfirmed ⇒ do not generate. | 4 (`AF-DIU-CONSENT`) |
| **Fidelity receipt + 3-strike** | `diu_validator.py fidelity --run-dir R --card-id ID --scores-file S` | TEST-PROTOCOL §5: avg ≥4.0 AND no dim <3 AND zero hard-rule violations; appends a receipt; 3 consecutive fails on one dimension ⇒ escalate to CDO. | 3 (fail) / 5 (`AF-DIU-3-STRIKE` escalate) |

Receipts append to `working/checkpoints/diu_fidelity_receipts.json` (never deleted — the card's institutional memory). The Generation Operator runs `prompt-caps` before every dispatch; the Deck Systems Specialist runs `route-check` at SOP-DIU-611 step A before any manifest work; the Fidelity Tester runs `fidelity` on every graded PNG. The consent-gate-first rule (PHOTO-SHOOT-SOP §1) is now a coded fail-closed gate (`consent-check`), run before any real-person generation — not prose alone.

---

## The model rule: Kie.ai endpoint routing

MODEL-SPECS.md (repo-owned, vendor-asserted) specifies API limits, character tiers (SHORT/MEDIUM/LONG), and per-category routing rules:

- **GPT-Image 2** — T2I (layout adherence) / I2I (precise edits). Default general-purpose.
- **Nano Banana 2** — people-led creative, faster, great for lifestyle/portrait.
- **Seedream 4.5** — identity-locked personal photo shoots; surgical retouch (Mode G).
- **Ideogram V3** — design/typography-heavy; clean graphic elements.
- **Wan 2.7** — variant exploration, draft-stage testing.

Library _RULES.md per category list preferred models and fallback chains. Generation Operator selects per brief + image type.

---

## Skill versioning: independent line

Skill 45 versions independently of the repo — see `skill-version.txt` and the CHANGELOG for the current value (the SKILL.md frontmatter `version` must match `skill-version.txt`, enforced by the frontmatter-version guard). The repo version rolls all skills in parallel; individual skills track their own major.minor.patch for feature parity and vendor library updates.

---

## Next steps after install

1. **Read library/README.md** — the agent's quick-start guide.
2. **Shadow a Style Analyst.** Request a simple image analysis; watch them apply the 12-dimension protocol and write a SHORT-tier style card.
3. **Request a style-based generation.** Pick a category (e.g., FB-001 if available), supply a new subject and headline, watch Generation Operator route and execute.
4. **Test fidelity.** Request an off-style result and watch Fidelity Tester diagnose and patch.

---

## Support & escalation

- **DIU errors, stalls, or process questions** → Healer — Graphics receives the routed bug ticket (presentations dept precedent).
- **Legal / likeness concerns** → Director of Legal + CDO simultaneously (PHOTO-SHOOT-SOP §1; escalation rows in each role's §12).
- **Model/endpoint changes** → Registrar duty (dormant; activated when INDEX >50 cards) updates MODEL-SPECS per its §6 protocol; never touch style cards for a model change.

---

## End of Skill 45 SKILL.md
