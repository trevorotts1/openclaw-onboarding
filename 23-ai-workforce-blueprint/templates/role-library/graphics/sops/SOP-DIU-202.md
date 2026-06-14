# SOP-DIU-202 — Deck Generation & Rotation Engine
**Version:** 1.0 | **Date:** 2026-06-12
**Classification:** Vendor SOP (thin wrapper)
**Owner Role:** Deck Systems Specialist ("The Architect")
**Status:** CANONICAL
**Library-version pin:** PPT-ANALYSIS-SOP v1.1, powerpoint-designs/_RULES.md v1.0, MASTER-SOP v1.1, MODEL-SPECS v1.2 (§-refs verified 2026-06-12)

---

## Role Mission

The Deck Systems Specialist converts an approved PPT-category style card into a complete, cohesion-safe generated deck. This SOP governs the Slide Manifest assembly, the Style Rotation Engine execution, and the handoff to the Generation Operator. The role is a **planner and orchestrator** — it never submits API calls directly and never delivers assets to a client.

---

## Governing Library Files (source-of-truth — do NOT duplicate content here)

| File | Canonical path | Sections governing this SOP |
|---|---|---|
| PPT Analysis SOP | `45-design-intelligence-library/library/_system/PPT-ANALYSIS-SOP.md` | §3B (Rotation Engine — all 5 steps), §3C (format & resolution) |
| PowerPoint Category Rules | `45-design-intelligence-library/library/powerpoint-designs/_RULES.md` | Full file: hard rules, model routing, text strategy decision |
| Master SOP | `45-design-intelligence-library/library/_system/MASTER-SOP.md` | §3.2 (card production status gate), §7 step 6 (handoff confirmation) |
| Model Specs | `45-design-intelligence-library/library/_system/MODEL-SPECS.md` | §§2,5 (endpoint routing, resolution availability, tier mapping) |
| Style Card Index | `45-design-intelligence-library/library/INDEX.md` | Card status verification before any generation |
| Photo Shoot SOP | `45-design-intelligence-library/library/_system/PHOTO-SHOOT-SOP.md` | Mode E (Identity Lock Block for client-in-slide scenarios) |

> **Do not copy protocol text from these files into this SOP.** The library is the law. If a library file and this SOP conflict, the library file wins and this SOP must be updated.

---

## Procedure (ordered)

### Step 1 — Verify production status before any work begins

Open `INDEX.md` and confirm all three conditions are true:
1. The style card ID referenced in the brief exists in the index.
2. Its status is **production** (not draft, not retired).
3. The version in the index matches the version pinned in the brief.

If any condition fails: **halt immediately**. Notify CDO with the specific condition that failed. Do not proceed until CDO resolves the status issue.

### Step 2 — Apply the deck boundary decision

Before assembling any manifest, apply the routing decision table in `powerpoint-designs/_RULES.md` (mirrored as SOP-DIU-611 in the role file). Webinar and funnel decks are never routed through the Rotation Engine — they belong to the Presentations department. If the deck type is ambiguous, escalate to CDO before touching the manifest.

### Step 3 — Set the text strategy

**ROUTING INTERLOCK - AUDIENCE/WEBINAR DECKS:** An audience deck, webinar deck, funnel deck, or any deck matching a CLIENT-WEBINAR-DECK-SOP archetype CANNOT proceed on this DIU pipeline. Route immediately to the Presentations department via CDO. This is not a judgment call - it is a hard stop. A deck assembled on this pipeline with strategy (b) backgrounds when it should run the Presentations text-in-image pipeline is an architecture violation and will AUTO-FAIL final QC.

Choose strategy (a) or (b) per `powerpoint-designs/_RULES.md` and record it in the manifest header:
- **(a)** AI renders text in-image - use exact-text quoting; required for audience/webinar decks (routing interlock above applies - those decks must not reach this step on the DIU pipeline at all).
- **(b)** Background/imagery only, text overlay added in PowerPoint later - valid ONLY for non-audience, non-webinar DIU-routed decks (brand/strategy/campaign/portfolio decks with a style ID); prompts must include explicit clear-zone language.

Do not leave the strategy field blank. For audience/webinar decks: halt immediately per the routing interlock above. For confirmed DIU-routed non-audience decks: record the strategy and document the basis for the routing decision.

### Step 4 — Assemble the Slide Manifest

Build the manifest as an ordered table following PPT-ANALYSIS-SOP §3B Step 1. Each row must contain:

| Field | Notes |
|---|---|
| Slide number | Sequential, 1-indexed |
| Slide purpose | Title / section open / content / quote / CTA / transition-divider |
| Assigned family | Family letter + card ID@version (e.g., PPT-008-C@v1.2) |
| Flex variation | Explicit flex-state values (image side, bg hue, accent) — not blank |
| Text strategy | (a) or (b) — must match Step 3 decision |
| Generation tier | Per MODEL-SPECS tier definitions |
| Destination resolution | 1K / 2K / 4K — client's choice governs; default 2K |
| Identity lock | `true` if client likeness appears in this slide; `false` otherwise |

Apply the family assignment rules from PPT-ANALYSIS-SOP §3B Step 2 in priority order: purpose mapping → proportions → rhythm constraint (no more than 3 consecutive same-family slides) → bookend rules (slide 1 = Family A; closing slide = CTA family if defined).

Apply within-family flex rotation per PPT-ANALYSIS-SOP §3B Step 3: cycle flex states deterministically by position-within-family so the same request always yields the same manifest.

### Step 5 — Check for unfilled placeholders and identity flags

Scan every row of the manifest:
- If any cell contains an unfilled token (e.g., `{CLIENT_NAME}`, `{SLIDE_TITLE}`, `[TBD]`): **halt**. Return the incomplete brief to CDO with the specific unfilled fields listed. Never pass a manifest with placeholder tokens to the Generation Operator.
- For every row with `identity_lock: true`: the Photo Shoot Director must supply a confirmed active consent record covering Mode E usage and must attach the Identity Lock Block to that manifest row before the Generation Operator may submit it. Sequence identity-locked slides into a separate batch from non-identity slides.

### Step 6 — CDO approval gate (decks of 10 or more slides)

For decks of 10 or more slides, present the complete manifest to CDO for approval **before any generation begins**. CDO approval covers:
- Cost and timeline authorization (include an estimated total generation cost in the manifest header).
- Style sign-off (card ID@version confirmed).

Record the CDO approval timestamp in the manifest header row. Do not proceed to Step 7 until the approval timestamp is recorded.

### Step 7 — Write the manifest file and hand off

Write the manifest to the job directory:
```
_local/jobs/{job-id}/SLIDE-MANIFEST.md
```

Hand the approved manifest to the Generation Operator with:
- Card ID@version
- Manifest file path
- Budget ceiling
- Resolution
- Deadline
- Identity involvement flag (true/false — if true, Photo Shoot Director must complete identity rows first)

Manifest ownership transfers to the Generation Operator at this point. The Deck Systems Specialist does not re-enter the generation lane unless a cohesion review (SOP 9.4 in the role file) flags slides for regeneration.

---

## Inputs

| Input | Source | Required before Step |
|---|---|---|
| Production-status PPT-category style card (ID@version confirmed in INDEX.md) | Style Analyst → CDO confirmation | Step 1 |
| Complete deck brief: slide count, purpose, all verbatim text strings, brand variables, resolution, deadline | CDO | Step 3 |
| CDO approval to proceed | CDO | Step 3 |
| Active consent record + Identity Lock Block (identity slides only) | Photo Shoot Director | Step 5 |
| CDO manifest approval (10+ slide decks) | CDO | Step 6 |

---

## Outputs

| Output | Destination | Notes |
|---|---|---|
| Approved Slide Manifest file | `_local/jobs/{job-id}/SLIDE-MANIFEST.md` | Single interface artifact crossing into Generation Operator's lane |
| Generation Operator briefing | Generation Operator | Card ID@version, manifest path, budget, resolution, deadline, identity flag |
| CDO notification (identity slides) | CDO | Confirmation that Photo Shoot Director has cleared identity rows before generation begins |

---

## Handoff Conditions

The handoff to the Generation Operator is valid only when ALL of the following are true:

1. INDEX.md shows the style card at production status.
2. Slide Manifest file exists at `_local/jobs/{job-id}/SLIDE-MANIFEST.md`.
3. No unfilled placeholder tokens remain in any manifest row.
4. Text strategy is recorded in the manifest header (not blank).
5. CDO approval timestamp is present (required for 10+ slide decks; for decks under 10 slides, the manifest completion itself serves as authorization).
6. Identity-locked rows have the Identity Lock Block attached and the Photo Shoot Director's consent confirmation on record.
7. Estimated generation cost is recorded in the manifest header.

The Generation Operator may not begin generation if any of the above conditions is unmet. The Deck Systems Specialist is responsible for ensuring all conditions are satisfied before handing off.

---

## Escalation Triggers

| Condition | Escalation path |
|---|---|
| Style card not at production status in INDEX.md | Halt → notify CDO with card ID and current status |
| Deck type is ambiguous (webinar vs. DIU boundary) | Halt → escalate to CDO; CDO routes to Director of Presentations for arbiter decision if needed |
| Brief contains unfilled placeholder tokens | Halt → return to CDO with specific unfilled fields listed |
| Consent record missing or expired for client-in-slide slides | Halt → notify CDO and Photo Shoot Director; do not generate identity-locked slides until resolved |
| Two or more irreconcilably different style systems detected in the reference deck (upstream of this SOP, in SOP-DIU-201) | Halt → escalate to CDO: "Two distinct style systems detected. Which should govern?" |
| Director of Presentations disputes DIU routing after manifest assembly has begun | Halt generation immediately → escalate to CDO; CDO is final arbiter |
| Rotation Engine rhythm constraint cannot be satisfied given the brief's slide count and purpose mix | Flag to CDO before manifest delivery; document the constraint and propose resolution options |

---

*Library-version pin (mandatory): PPT-ANALYSIS-SOP v1.1, powerpoint-designs/_RULES.md v1.0, MASTER-SOP v1.1, MODEL-SPECS v1.2 — §-refs verified 2026-06-12. If any referenced library file is versioned higher than this pin at the time of execution, re-verify §-references and update this pin before proceeding.*
