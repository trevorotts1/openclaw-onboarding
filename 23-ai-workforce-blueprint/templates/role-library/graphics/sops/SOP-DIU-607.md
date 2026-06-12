# SOP-DIU-607 — Named Styles, Client Aliases & Lookbook

**ID:** SOP-DIU-607
**Classification:** ZHC SOP — thin wrapper
**Owner Role:** Style Analyst (Section 9.7)
**Version:** 1.0 | **Date:** 2026-06-12
**Status:** CANONICAL
**Library-version pin:** MASTER-SOP v1.0, STYLE-CARD-TEMPLATE v1.0, INDEX.md v1.0, PHOTO-SHOOT-SOP v1.0 (§-refs verified 2026-06-12)

---

## Role Mission

The Style Analyst maintains per-client alias records that map a plain-English name ("Style 1", "Bold Dark Executive") to a card ID pinned at a specific version, a frozen reference-image set, and any client brand-variable overrides. This makes the "build it in Style 1" instruction actionable — the Operator resolves the alias to an exact card ID + version + overrides with no guessing and no archaeology into past generation logs.

Alias records are created at the moment of client approval and never retroactively reconstructed from memory. Version pinning semantics protect brand consistency: minor prompt-patches auto-advance (v1.x rule), but a v2.0 re-analysis must pass a side-by-side regression render against the frozen references and receive CDO confirmation before the alias moves forward.

The outward-facing artifact of this SOP is the client Style Lookbook — a plain-language menu of named styles with thumbnails and best-for guidance. Clients choose by looking, not by reading markdown. The Lookbook reflects production-status cards only and is regenerated whenever a card's status changes.

---

## Governing Library Files (source-of-truth — do NOT duplicate content)

| File | Sections used | What it governs |
|---|---|---|
| `_system/MASTER-SOP.md` | §3.2 (assembly packet requirements — alias must resolve to a complete packet), §7 step 6 (approval moment; client selection triggers alias capture) | When an alias is created; what the resolved alias must supply to the Operator |
| `_system/STYLE-CARD-TEMPLATE.md` | Changelog section (version increment rules; what triggers a v2.0), Summary/Mood/Palette fields (what the alias description and Lookbook entry are drawn from) | Version semantics; what fields may be quoted in the alias record without duplicating the card |
| `library/INDEX.md` | Status column (production / tested / draft / retired — Lookbook shows production-only) | Authoritative source for which cards are eligible for alias assignment and Lookbook display |
| `_system/PHOTO-SHOOT-SOP.md` | §3 (per-client folder precedent; frozen reference-image set pattern) | How frozen reference images are stored and named per client; sourcing precedent |

All card content, version change triggers, and style-quality definitions are read from the library files above at runtime. Do not reproduce card field definitions or version-bump criteria in this SOP — STYLE-CARD-TEMPLATE and MASTER-SOP are the single sources of truth.

---

## Procedure (ordered)

### A. Alias Capture (triggered by client approval — one alias per approved card selection)

1. **Receive handoff from Generation Operator.** At the approval moment (MASTER-SOP §7 step 6), the Operator delivers:
   - The verified local asset path (postflight-complete per SOP-DIU-601)
   - The generation receipt including card ID + version, model, tier, seed (if available), and exact filled prompt

2. **Confirm card is in production status.** Look up the card ID in `library/INDEX.md`. A card must have `status: production` before an alias can be assigned. If the card is in `tested` or `draft` status, block alias assignment and return to the CDO for promotion decision.

3. **Collect the client-facing alias name.** Receive the alias from the CDO or client-approval record. The alias must be:
   - Plain English (readable without markdown knowledge)
   - Unique within this client's `_local/NAMED-STYLES.md`
   - Not derived by guessing — taken verbatim from the approval record

4. **Identify frozen reference images.** Pull the approved output asset plus any identity reference images used in the generation (from the generation receipt and PHOTO-SHOOT-SOP §3 per-client folder) as the frozen reference set. These are the ground-truth for regression checks at v2.0 re-analysis. Record their absolute paths — do not copy unless the originals are at risk of deletion.

5. **Write the alias record.** Append the following block to `_local/NAMED-STYLES.md` (create the file from the template at `templates/NAMED-STYLES.md` if it does not exist):

   ```yaml
   - alias: "<plain-English name>"
     card_id: "<ID>"
     card_version: "<version at approval>"
     frozen_refs:
       - "<absolute path to approved output asset>"
       # add additional reference image paths if applicable
     brand_overrides:
       # populate only fields where this client's brand config diverges from the card defaults
       # example: BRAND_COLOR_1: "#1A1A2E"
       # leave empty if no overrides apply
     captured_at: "<ISO 8601 timestamp>"
     captured_from_receipt: "<receipt filename>"
   ```

6. **Regenerate the Style Lookbook.** After every alias write, regenerate `_local/LOOKBOOK.md` per procedure C below.

### B. Version Advance Rules

The alias record moves to a new card version only as described below. Do not silently advance aliases — brand consistency depends on predictable pinning.

**v1.x auto-advance (minor prompt-patch only):**
1. Confirm the version bump qualifies as v1.x per the STYLE-CARD-TEMPLATE Changelog definition (prompt-patch only; no re-analysis; card content fields unchanged).
2. Update `card_version` in the alias record to the new v1.x value.
3. Record the advance in the alias record with an inline comment: `# auto-advanced from v1.N per Changelog entry <date>`.
4. Regenerate the Lookbook.

**v2.0 re-analysis (requires CDO confirmation + regression render):**
1. Confirm the bump qualifies as v2.0 per the STYLE-CARD-TEMPLATE Changelog definition (re-analysis; card content fields changed).
2. Halt alias advance. Do NOT update `card_version` until the following steps complete.
3. Perform a regression render: submit a generation using the new card version with the same tier, model, variables, and filled prompt structure that produced the frozen reference output. Route through the Operator (SOP-DIU-301 / SOP-DIU-601) as a normal job.
4. Produce a side-by-side comparison: new output vs. the frozen reference images recorded in the alias record.
5. Deliver the side-by-side to the CDO with a written summary of what changed between versions per the Changelog.
6. Await explicit CDO written confirmation before moving the alias. CDO confirmation is the handoff artifact — no verbal or chat-only approvals.
7. On CDO confirmation: update `card_version`, record `v2_advance_confirmed_by` and `v2_advance_confirmed_at` in the alias record, update the frozen reference set with the new approved output, and regenerate the Lookbook.
8. On CDO rejection: alias remains pinned at the previous version. Record `v2_advance_rejected_at` and `v2_advance_rejection_reason` in the alias record. The old version remains in service indefinitely until the next promotion attempt.

### C. Lookbook Regeneration

Run after every alias write, every version advance, and every INDEX.md status change that affects a card with an active alias.

1. Read `_local/NAMED-STYLES.md` for all alias records.
2. For each alias, confirm the card's current status in `library/INDEX.md`. Include only `status: production` cards. Retired or demoted cards are listed in a separate "Retired Styles" section at the bottom of the Lookbook — never silently dropped, never shown as active.
3. Produce `_local/LOOKBOOK.md` with the following structure for each active alias:

   ```markdown
   ## <alias name>

   **Style:** <card_id>@<card_version>
   **Best for:** <one-line from STYLE-CARD-TEMPLATE Summary field — do NOT paraphrase>
   **Mood:** <from STYLE-CARD-TEMPLATE Mood field>
   **Reference thumbnail:** ![](<absolute path to first frozen_ref asset>)
   **Available tiers:** SHORT / MEDIUM / LONG (per MODEL-SPECS §3 — read at runtime)
   ```

4. If the client has no active aliases (NAMED-STYLES.md is empty or all aliases are on non-production cards), the Lookbook renders a single line: `No production styles registered yet. Calibration run required (SOP-DIU-613).`
5. Record `lookbook_generated_at` at the top of the Lookbook file on every regeneration.

---

## Inputs

| Input | Required | Source |
|---|---|---|
| Generation receipt (card ID + version, model, tier, seed, filled prompt, asset path) | Yes | Generation Operator via SOP-DIU-602 |
| Postflight-complete verified asset | Yes | SOP-DIU-601 postflight pass |
| Client alias name (plain English, from approval record) | Yes | CDO or client-approval record at MASTER-SOP §7 step 6 |
| Card status = production in INDEX.md | Yes | `library/INDEX.md` — checked at alias capture |
| Frozen reference image paths | Yes | Generation receipt + PHOTO-SHOOT-SOP §3 per-client folder |
| Brand-variable overrides (if applicable) | Conditional | Client box brand config (`brand_config` block) |
| STYLE-CARD-TEMPLATE Changelog entry (for version advances) | Yes | `_system/STYLE-CARD-TEMPLATE.md` Changelog section |
| CDO written confirmation (v2.0 advances only) | Conditional | CDO approval artifact — never chat-only |
| Regression render output (v2.0 advances only) | Conditional | Generation Operator via SOP-DIU-301 + SOP-DIU-601 |

---

## Outputs

| Output | Location | State at exit |
|---|---|---|
| Alias record appended | `_local/NAMED-STYLES.md` | Written and complete |
| Style Lookbook regenerated | `_local/LOOKBOOK.md` | Current as of regeneration timestamp |
| v2.0 side-by-side comparison (if applicable) | `_local/receipts/{regression-render-receipt-id}/` | Delivered to CDO |
| v2.0 advance or rejection logged | `_local/NAMED-STYLES.md` alias block | Inline record |

---

## Handoff Conditions

- **Alias captured:** Operator can now resolve the alias by name from `_local/NAMED-STYLES.md` and receive a complete assembly packet (card ID + version + brand overrides). No generation may use an alias that is not in this file.
- **Lookbook regenerated:** CDO delivers the updated `_local/LOOKBOOK.md` to the client as the style menu. CDO owns client-facing delivery — the Style Analyst produces the file; CDO sends it.
- **v2.0 advance pending CDO confirmation:** Alias is frozen at the previous version. Operator must use the prior pinned version until CDO confirmation arrives. Do not unilaterally advance.
- **Card retired (INDEX.md status = retired):** Style Analyst moves the alias to the Retired Styles section of the Lookbook and notifies CDO. CDO decides whether to assign the alias to a successor card or retire the alias with the client.

---

## Escalation Triggers

| Condition | Action |
|---|---|
| Card ID from the generation receipt is not found in INDEX.md | Hard stop. Do not create the alias. Route to CDO — an un-indexed card cannot receive an alias. Never improvise an ID. |
| Card exists in INDEX.md but is not in production status | Block alias assignment. Notify CDO of promotion decision needed. |
| Alias name already exists in `_local/NAMED-STYLES.md` for a different card ID | Hard stop. Alias names must be unique per client. Return to CDO for deconfliction. |
| Frozen reference images are missing or inaccessible at their recorded paths | Flag immediately to CDO. A regression render for a future v2.0 bump cannot proceed without the frozen reference set — rebuild the set from the generation receipts before the Lookbook regeneration is marked complete. |
| v2.0 regression render fails preflight (SOP-DIU-601) or is quarantined (SOP-DIU-604) | Block v2.0 advance. Report to CDO with the failed receipt and the preflight or quarantine details. Alias remains on the previous version. |
| CDO confirmation for a v2.0 advance is not received within 5 business days | Re-notify CDO with the side-by-side comparison. Do not advance the alias unilaterally. Log the re-notification in the alias record. |
| INDEX.md is modified in a way that changes the status of a card with an active alias | Trigger Lookbook regeneration immediately. Notify CDO of the status change and its effect on the client alias. |
| SOP-DIU-615 (Healer integrity sweep) flags a stale library-version pin on this SOP | Pause alias operations. Re-verify all §-refs against the current library files. Update pin line and report to CDO before resuming. |

---

*Library-version pin: MASTER-SOP v1.0, STYLE-CARD-TEMPLATE v1.0, INDEX.md v1.0, PHOTO-SHOOT-SOP v1.0 (§-refs verified 2026-06-12).*
