# SOP-DIU-401 — Personal Photo Shoot Operations (Vendor Wrapper)

**SOP ID:** SOP-DIU-401  
**Owner Role:** Photo Shoot Director ("The Director")  
**Vendor SOP.** Wraps `PHOTO-SHOOT-SOP §§1–5, 7–9`.  
**Allocation authority:** SOP-ALLOCATION.md vendor band 4xx (split into SOP-DIU-401a + SOP-DIU-401b for role-file Section 9 entries; this file is the unified thin-wrapper reference).  
**Library-version pin:** PHOTO-SHOOT-SOP v1.0, MODEL-SPECS v1.2, MASTER-SOP v1.1, NEGATIVE-PROMPTING-SOP v1.0, personal-photo-shoot/_RULES.md (no semver — check file header) — all §-refs verified 2026-06-12.  
**Version:** 1.0 | **Date:** 2026-06-12

---

## Role Mission

The Photo Shoot Director runs every pipeline that involves a real person's likeness. Nothing in that pipeline fires without active consent scope. No reference image enters without a verified who-appears inventory. No deliverable leaves without a Rights Manifest entry. This SOP covers the full personal photo-shoot lifecycle: from the first consent gate through Identity Lock Block assembly, shoot-mode routing, and shoot-record closure.

---

## Governing Library Files (Source of Truth)

Do NOT duplicate or paraphrase the content of these files in this SOP. Read them directly.

| File | Path | Sections covered by this SOP |
|---|---|---|
| PHOTO-SHOOT-SOP | `45-design-intelligence-library/library/_system/PHOTO-SHOOT-SOP.md` | §§1–5, 7–9 (full scope of this SOP) |
| MODEL-SPECS | `45-design-intelligence-library/library/_system/MODEL-SPECS.md` | §§1, 2, 5 (routing table, format/size limits, JSON templates) |
| MASTER-SOP | `45-design-intelligence-library/library/_system/MASTER-SOP.md` | §3.2 (variable system), §7 (Workflow B) |
| NEGATIVE-PROMPTING-SOP | `45-design-intelligence-library/library/_system/NEGATIVE-PROMPTING-SOP.md` | §§1–3 (layer merge for shoot prompts) |
| Personal Photo Shoot category rules | `45-design-intelligence-library/library/personal-photo-shoot/_RULES.md` | Full file |

---

## Ordered Procedure

This procedure runs in strict sequence. Do not skip or reorder steps. Steps 1–7 = consent + identity gate (maps to SOP-DIU-401a in the role-file mirror). Steps 8–14 = Identity Lock Block assembly + shoot execution (maps to SOP-DIU-401b in the role-file mirror).

### Phase 1: Consent & Identity Gate (PHOTO-SHOOT-SOP §§1–3)

**Step 1 — Locate the consent record.**  
Read `personal-photo-shoot/{client-slug}/CONSENT.md`. If the file does not exist, the shoot cannot proceed: create a `pending` record and route to the producer for consent collection. Do NOT advance to Step 2.

**Step 2 — Check consent status machine.**  
Status must be `active`. If `expired` or `revoked`, halt immediately and notify producer. If `pending`, halt and notify producer that collection is outstanding.

**Step 3 — Verify scope coverage.**  
Confirm the active record covers: (a) the requested shoot modes A–F, (b) the commercial/internal use flag in the brief, (c) all distribution channels listed. Mode F (stylized creative) requires explicit opt-in. If any element falls outside scope, halt and route to producer for sign-off.

**Step 4 — MINORS HARD BLOCK.**  
If any subject in the brief is under 18, STOP unconditionally. Route to producer with the statement: "Minor likeness — hard block, cannot proceed." No escalation path. No exceptions.

**Step 5 — Who-appears inventory.**  
Run the inventory on every reference image in the brief per PHOTO-SHOOT-SOP §1: identify every recognizable person in each image. For any non-subject recognizable person, halt and resolve (crop/exclude the face or obtain an independent release) before continuing. Log the inventory result in the shoot record.

**Step 6 — Sourcing hierarchy check.**  
Confirm all reference images satisfy PHOTO-SHOOT-SOP §2: client's design library identity folder or client-provided uploads via GHL media library only. Public web searches and unvetted media library folders are prohibited sources. If sourcing cannot be confirmed, halt and resolve.

**Step 7 — Record gate outcome.**  
Write the gate result in the shoot brief header: `consent_verified: true`, `modes_approved: [list]`, `inventory_complete: true`, `gate_date: {date}`, `gate_by: photo-shoot-director`. A failing or halted gate records the halt reason, required resolution, and CDO notification status.

> Gate failure rule: if the consent record cannot be read (file missing, YAML parse error, ambiguous scope field), treat as NOT active and halt. Never infer consent from memory or chat history.

---

### Phase 2: Identity Lock Block Assembly & Shoot Execution (PHOTO-SHOOT-SOP §§4–5, 7–9)

**Step 8 — Open IDENTITY.md.**  
Read `personal-photo-shoot/{client-slug}/IDENTITY.md`. Confirm the reference-image set is current and hosting-verified (see SOP-DIU-609 for hosting mechanics). If IDENTITY.md is missing or stale, halt and update the profile before continuing.

**Step 9 — Assemble the Identity Lock Block.**  
Build the block per PHOTO-SHOOT-SOP §4: exact physical descriptors from the IDENTITY.md profile, framed as hard constraints. The block must be present verbatim in every generation prompt for this shoot. Do NOT summarize or paraphrase descriptors. Add the universal clause: `"Do not render any other recognizable real person in the scene."` This clause is mandatory on every block, regardless of mode.

**Step 10 — Select mode-appropriate workflow.**  
Route to the correct mode workflow per PHOTO-SHOOT-SOP §5. Model routing assignments (which endpoint, tier, and resolution) are governed by MODEL-SPECS §§1–2, 5. If a routing assignment is ambiguous due to a MODEL-SPECS change, escalate to the Chief Design Officer — never guess the endpoint.

**Step 11 — Compile the full shoot prompt.**  
Combine: Identity Lock Block + mode-appropriate context descriptors + applicable constraints from `personal-photo-shoot/_RULES.md` + negative prompt assembled per NEGATIVE-PROMPTING-SOP §§1–3 layer merge (plus the universal Identity Lock negative: no other recognizable real persons in scene). Fill all Workflow-B variables per MASTER-SOP §3.2 (`{SUBJECT_NAME}`, `{SETTING}`, `{MOOD}`, `{BRAND_COLOR_1}/{BRAND_COLOR_2}` if applicable, `{LOGO_NOTE}` if applicable). Zero unfilled `{VARIABLE}` tokens may remain.

**Step 12 — Finalize shoot brief and hand to Generation Operator.**  
Confirm endpoint assignment, aspect ratio, resolution tier, and all required params per the MODEL-SPECS §5 JSON template for the selected mode. Confirm reference image URLs are live-verified per SOP-DIU-609. Pass the complete shoot brief (Identity Lock Block + sourced refs + mode record + endpoint + params) to the Generation Operator for Kie.ai execution.

**Step 13 — Receive and verify results.**  
Review completed outputs from the Generation Operator against the hard-rule checks from PHOTO-SHOOT-SOP §10: no lightened skin, no text on face, no identity drift, no unauthorized persons in scene, no consent-gap content. Any hard-rule failure routes to SOP-DIU-604 quarantine immediately — the output is not delivered and is not reused.

**Step 14 — Log shoot record and close.**  
Write all shoot session data to the per-client folder per PHOTO-SHOOT-SOP §8. Append the Rights Manifest entry immediately on verified delivery per SOP-DIU-610 — never batch manifest entries. Apply synthetic-media disclosure per the channel × jurisdiction table before handing the finalized asset to the producer.

---

## Inputs

- Shoot request: client name, subject name, shoot mode(s) requested, reference images or reference-image path, intended use channel, commercial/internal flag
- Active CONSENT.md record for the subject
- IDENTITY.md profile for the subject
- MODEL-SPECS §5 JSON template for the target endpoint
- Category `_RULES.md` for `personal-photo-shoot`

---

## Outputs

- Consent-verified, Identity-Lock-annotated shoot brief (handed to Generation Operator)
- Verified deliverable asset (after Operator returns results)
- Shoot record entry (per-client folder, PHOTO-SHOOT-SOP §8)
- Rights Manifest receipt entry (SOP-DIU-610) — per-item, append-only
- Synthetic-media disclosure applied to deliverable where required

OR (on gate failure):

- Halt notice with reason code, required resolution action, and CDO notification

---

## Handoff Conditions

| From → To | Condition |
|---|---|
| Chief Design Officer → Photo Shoot Director | Shoot request received with brief and reference images |
| Photo Shoot Director → Generation Operator | Consent gate passed (Steps 1–7), shoot brief fully compiled (Steps 8–12) |
| Generation Operator → Photo Shoot Director | Results returned; Director runs Steps 13–14 |
| Photo Shoot Director → Chief Design Officer | Verified deliverable + closed shoot record + manifest entry confirmed |
| Photo Shoot Director → Chief Design Officer (halt) | Any halt condition: gate failure, quarantine trigger, ambiguous endpoint routing |

---

## Escalation Triggers

Escalate to the Chief Design Officer immediately on any of the following; do not attempt to resolve without CDO involvement:

1. Consent record does not exist, is expired, revoked, or scope-ambiguous for the requested mode
2. Who-appears inventory finds a non-consented recognizable person in a reference image that cannot be resolved by cropping
3. Minor likeness hard block (no escalation path — halt is the resolution)
4. IDENTITY.md missing or stale and the subject cannot be re-profiled without producer coordination
5. Output fails a hard-rule check (lightened skin, text on face, identity drift, unauthorized person in scene, consent gap) — triggers SOP-DIU-604 quarantine first, then CDO notify
6. Deletion of hosted reference images cannot be confirmed within 24 hours of job completion (SOP-DIU-609)
7. MODEL-SPECS routing assignment for the requested mode is ambiguous or endpoint is unreachable

---

## Library-Version Pin

```
PHOTO-SHOOT-SOP        v1.0   — verified 2026-06-12
MODEL-SPECS            v1.2   — verified 2026-06-12
MASTER-SOP             v1.1   — verified 2026-06-12
NEGATIVE-PROMPTING-SOP v1.0   — verified 2026-06-12
personal-photo-shoot/_RULES.md — no semver; verified 2026-06-12
```

If any governing file version bumps, re-verify all §-refs in this SOP against the updated file before the next shoot run. Stale pins are flagged by SOP-DIU-615 (Healer-Graphics integrity sweep).

---

*Role-file mirror entries: [SOP-DIU-401a] photo-shoot-director.md §9.1 | [SOP-DIU-401b] photo-shoot-director.md §9.2. This file is the unified standalone reference. The role file is authoritative on Section 9 content; if they diverge, the role file wins and this wrapper must be updated.*
