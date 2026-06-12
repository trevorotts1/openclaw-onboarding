# SOP-DIU-613 — New-Client Calibration Run

**ID:** SOP-DIU-613
**Classification:** ZHC SOP — thin wrapper
**Owner Role:** Chief Design Officer (orchestrates); Style Analyst + Generation Operator (execute)
**Version:** 1.0 | **Date:** 2026-06-12
**Status:** CANONICAL
**Library-version pin:** MASTER-SOP v1.0, PPT-ANALYSIS-SOP v1.0, PHOTO-SHOOT-SOP v1.0, TEST-PROTOCOL v1.0 (§-refs verified 2026-06-12)

---

## Role Mission

The Chief Design Officer runs this SOP as the mandatory first structured DIU engagement for every new client. This is the DIU's equivalent of Skill 38's "appointment-booking playbook is always first": an identical designed first deliverable on every box. The calibration run establishes the client's style library, seeds their taste profile, verifies the full generation pipeline (keys, hosting, receipts), and delivers a Lookbook. No client proceeds to Workflow B generation requests without a completed calibration run. A client without a calibration run has no library, no taste profile, and no Lookbook — every subsequent generation request would require re-intake from scratch.

---

## Governing Library Files (source-of-truth — do NOT duplicate content)

| File | Sections used | What it governs |
|---|---|---|
| `_system/MASTER-SOP.md` | §6 (style card registration and library activation) | Card creation workflow, Workflow A procedure, registration steps 6–7 |
| `_system/PPT-ANALYSIS-SOP.md` | §4 (batch deck analysis procedure) | Reference deck analysis path when the client has no existing visual assets |
| `_system/PHOTO-SHOOT-SOP.md` | §1 (Identity Lock principles), §2 (identity reference sourcing hierarchy), §3 (per-client folder structure) | Identity profile setup, reference image set curation, standing consent requirements |
| `_system/TEST-PROTOCOL.md` | Full document (cards must reach `tested` status before client sees any output) | 12-dimension card rubric, pass/fail criteria, what constitutes a tested card |

All card creation, testing, identity-profile, and library-registration procedures are read from the governing files above at runtime. Do not reproduce or paraphrase those definitions in this SOP.

---

## Procedure (ordered)

### Step 1 — Collect brand materials

Gather the following from the client intake or onboarding session:
- Logo files (vector preferred; PNG acceptable)
- Brand color codes (hex or RGB)
- Existing visual assets: prior decks, social posts, ad creative — whatever the client has

If the client has no existing visual assets, proceed to Step 2 with a blank-slate brief (see failure mode below for the escalation path when even a blank-slate brief cannot proceed).

### Step 2 — Style Analyst produces 2–3 draft cards

Brief the Style Analyst to analyze the collected brand materials using Workflow A (MASTER-SOP §§3–4) and produce 2–3 draft style cards.

If the client has no existing visual references, request a PPT batch analysis (SOP-DIU-102) using 2–3 competitor or aspirational reference decks that the client approves. The approved reference decks — not the CDO's assumptions — are the input.

### Step 3 — Brand variable verification

Verify all Workflow-B variables resolve correctly from the box's brand config file:
- `{BRAND_COLOR_1}`, `{BRAND_COLOR_2}`, `{LOGO_NOTE}`
- Any additional brand-config variables the draft cards require

If the box has no brand config populated: create `_local/BRAND.md` with the verified values before proceeding to Step 5. Do not generate anything against unverified brand variables.

### Step 4 — Identity profile and standing consent (if likeness work is anticipated)

If the client is likely to request photo-shoot or likeness work in the future (confirm at intake — default to yes for personal-brand clients):

1. Create `personal-photo-shoot/{client-slug}/IDENTITY.md` with the client's physical descriptors and an approved reference image set per PHOTO-SHOOT-SOP §§2–3.
2. Initiate the standing self-likeness consent record per SOP-DIU-608 self-likeness fast path: create `_local/consent/{client-slug}.json` with `status: active` and the standard scope fields. This makes the consent gate a file-read for all future likeness requests instead of a human-approval loop.

If the client explicitly opts out of all likeness work: record `status: opted-out` in the consent record and skip identity profile creation. Document the opt-out with a timestamp.

### Step 5 — Fidelity Tester review (mandatory before any client-facing output)

All 2–3 draft cards must reach `tested` status — passing the full 12-dimension rubric per TEST-PROTOCOL — before any output is presented to the client. Do not present draft or untested cards under any circumstances. If a card fails testing, the Style Analyst revises and the card is retested. There is no exception path that bypasses the Fidelity Tester for calibration cards.

### Step 6 — 1K calibration contact sheet

For each card that reaches `tested` status: generate a 1K SHORT contact sheet (4 variations, cheapest capable endpoint per MODEL-SPECS §2 routing) using the card and the client's verified brand variables.

This step validates:
- `KIE_API_KEY` wiring across all env stores (SOP-DIU-601 preflight)
- Hosting path (SOP-DIU-609 if any reference images are used)
- Receipt plumbing (SOP-DIU-602 smoke-test rule: first-ever generation per client must be a 1K SHORT smoke test)

A contact sheet is the minimum viable output set — not a deliverable. Do not present it as a final asset.

### Step 7 — Client picks favorites

Present the verified contact sheets to the client via the CDO. The client selects their favorite card(s) or individual variations. Record the exact selections (card ID, variation index, any stated reason).

If the client declines to select or requests significant changes: classify per SOP-DIU-614 (preference within brief vs. scope change). Do not iterate open-endedly — more than one round of type-(b) re-runs on the calibration run escalates to the CDO for a scope decision.

### Step 8 — Taste profile seeded

Write initial entries to `_local/TASTE-PROFILE.md` based on the client's selections per SOP-DIU-614 taste-profile mechanics:
- Liked: dimensions and elements the client selected
- Disliked: anything the client explicitly rejected or commented on negatively
- Standing pre-approvals: any elements the client confirmed they always want

Taste-profile entries are disk-persisted only — never chat-only, never session-memory only.

### Step 9 — Lookbook v1 published

Trigger SOP-DIU-607 (via Style Analyst) to generate the client's first Lookbook from the winning card(s). The Lookbook contains the cards' production names, thumbnails, and best-for guidance in plain-English — not markdown tables or card IDs.

Deliver Lookbook v1 to the client as the calibration run's primary deliverable.

---

## Inputs

| Input | Required | Source |
|---|---|---|
| Logo files (vector preferred) | Yes (or blank-slate brief if none) | Client onboarding session / brand materials |
| Brand color codes (hex or RGB) | Yes | Client onboarding session |
| Existing visual assets (decks, social posts, ad creative) | Conditional | Client onboarding session; competitor/aspirational decks acceptable substitute |
| Approved reference decks for PPT batch analysis (if no existing assets) | Conditional | Client-approved; never CDO-assumed |
| Box brand config file (`_local/BRAND.md`) | Yes (created in Step 3 if absent) | Box-owned; created from verified values at Step 3 |
| Client's physical descriptors + reference image set (if likeness work anticipated) | Conditional | Client onboarding session; curated per PHOTO-SHOOT-SOP §§2–3 |
| `KIE_API_KEY` verified across all env stores | Yes | Verified at Step 6 (SOP-DIU-601 preflight) |
| Client's budget config block | Yes | Client box config; required before any generation (SOP-DIU-601 preflight Step 9) |

---

## Outputs

| Output | Location | State at exit |
|---|---|---|
| 2–3 tested style cards registered in INDEX.md | `library/INDEX.md` + card files | `tested` or `production` (Analyst upgrades to production on CDO confirmation) |
| Brand config file | `_local/BRAND.md` | Verified; all Workflow-B variables resolved |
| Identity profile (if applicable) | `personal-photo-shoot/{client-slug}/IDENTITY.md` | Created with reference image set |
| Standing consent record (if applicable) | `_local/consent/{client-slug}.json` | `status: active` |
| 1K calibration contact sheets | `_local/results/{job-id}/` | Verified via SOP-DIU-601 postflight |
| Initial taste profile | `_local/TASTE-PROFILE.md` | Seeded from client selections |
| Lookbook v1 | `_local/lookbook/{client-slug}-v1.md` | Delivered to client via CDO |

---

## Handoff Conditions

- **Cards reach tested status → Step 6:** Fidelity Tester hands tested cards back to CDO. CDO proceeds to contact sheet generation.
- **Contact sheets verified → Step 7:** Generation Operator confirms postflight pass on all 1K contact sheets. CDO presents to client.
- **Client selects favorites → Steps 8–9:** CDO records selections, triggers taste-profile seeding (SOP-DIU-614 mechanics), and triggers Lookbook generation (SOP-DIU-607 via Style Analyst).
- **Calibration run complete:** Cards are now available for Workflow B requests from any department via CDO intake (SOP-DIU-612 cross-department request gate). The client has a library, a taste profile, and a Lookbook — the preconditions for all future DIU work are met.

---

## Escalation Triggers

| Condition | Action |
|---|---|
| Client has no visual assets and refuses to approve any reference decks | Halt calibration run. Escalate to the client via the human owner for a brief intake session. Do not produce a blank calibration run. Record the halt in the client's `_local/` directory with a timestamp. |
| Brand config values cannot be confirmed from client materials | Halt Step 3. Escalate to CDO. Do not generate against unverified brand variables. |
| No card passes the Fidelity Tester's 12-dimension rubric after two revision rounds | Escalate to CDO with the failing Test Log entries and the original brand materials. Do not present client-facing output until at least one card is tested. |
| `KIE_API_KEY` absent from all env stores at Step 6 | Hard stop per SOP-DIU-601. Escalate to CDO with list of all env stores checked. No generation proceeds without a verified key. |
| Client's budget config block is absent | Hard stop per SOP-DIU-601 preflight Step 9. Escalate to CDO for budget config before any generation. |
| Likeness work anticipated but client declines to provide a reference image set | Do not create an identity profile with inferred or assumed descriptors. Record the opt-out or incomplete intake state. Escalate to CDO before any photo-shoot or likeness generation is attempted. |
| Client requests more than one round of type-(b) preference re-runs on the calibration contact sheet | Escalate to CDO with a scope decision recommendation (iterate on existing cards vs. initiate a new brief). Do not continue open-ended re-runs. |
| Consent record cannot be written to disk (permissions error, directory missing) | Halt Step 4. Create the directory and file immediately before proceeding. A calibration run completed without a consent record leaves every future likeness request ungated. |

---

*Library-version pin: MASTER-SOP v1.0, PPT-ANALYSIS-SOP v1.0, PHOTO-SHOOT-SOP v1.0, TEST-PROTOCOL v1.0 (§-refs verified 2026-06-12).*
