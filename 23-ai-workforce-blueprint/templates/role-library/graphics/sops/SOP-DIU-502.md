# SOP-DIU-502 — Library Governance & Versioning
**ID:** SOP-DIU-502
**Band:** Vendor (5xx — Fidelity & Governance)
**Owner role:** Style Analyst ("The Eye") — acting as Library Registrar until INDEX.md production card count reaches >= 50
**Status:** Vendor SOP — thin wrapper
**Version:** 1.0 | **Date:** 2026-06-12
**Library-version pin:** MASTER-SOP v1.0 (§8 verified 2026-06-12); MODEL-SPECS v1.2 (§6 verified 2026-06-12); INDEX.md v2.0 (registration rules verified 2026-06-12); NEGATIVE-PROMPTING-SOP v1.0 (§5 verified 2026-06-12).

---

## Role Mission (scoped to this SOP)

The Style Analyst, acting under the Library Registrar duty, maintains the integrity and forward-compatibility of the entire design library. This SOP governs four distinct but related responsibilities: (1) card lifecycle management — keeping INDEX.md status in sync with every card's actual test/production state; (2) version control — applying MASTER-SOP §8 versioning rules consistently so the library is auditable and reversible; (3) model governance — executing the MODEL-SPECS §6 new-model and deprecation protocol so the library remains model-agnostic and never requires card rewrites; and (4) avoid-list maintenance — running the quarterly prune defined in NEGATIVE-PROMPTING-SOP §5 so avoid-lists stay sharp.

This SOP is **dormant** until explicitly triggered. The Style Analyst does not run governance checks speculatively or preemptively — triggers are defined below. When the INDEX.md production card count reaches >= 50, the CDO activates the Library Registrar as a standalone role and ownership of this SOP transfers.

---

## Governing Library Files (source of truth — do NOT duplicate content here)

| File | Sections used | What it owns |
|---|---|---|
| `45-design-intelligence-library/library/_system/MASTER-SOP.md` | §8 | Card versioning rules: semantic versioning scheme (v1.0 → v1.1 → v2.0), Changelog append requirement per edit, model-agnostic card design guarantee |
| `45-design-intelligence-library/library/_system/MODEL-SPECS.md` | §6, §7 | New-model addition protocol (7-step procedure); deprecation handling; Changelog; all routing and tier data — style cards are never touched during model changes |
| `45-design-intelligence-library/library/INDEX.md` | Full document | Master lookup table; required registration fields; ID prefix rules; retire-never-delete rule; production card count (Registrar activation counter); status lifecycle (draft / tested / production / retired) |
| `45-design-intelligence-library/library/_system/NEGATIVE-PROMPTING-SOP.md` | §5 | Avoid-list growth protocol: defect-driven addition, Changelog entry requirement, quarterly prune criteria (not relevant in < 10 generations) |

> The library is law. If a rule in this SOP conflicts with any of the library files above, the library file wins. Report the discrepancy to the CDO rather than resolving it silently.

---

## Triggers (when to run)

This SOP is event-driven. It does not run on a fixed schedule except for the quarterly avoid-list prune (trigger D).

| Trigger | Event |
|---|---|
| **A — Status promotion** | Fidelity Tester notifies that a card has been promoted from `draft` → `tested` or `tested` → `production` |
| **B — Version bump** | Fidelity Tester approves a prompt patch; card requires a version increment and Changelog entry |
| **C — Model event** | A new Kie.ai endpoint becomes available, or an existing endpoint is deprecated or significantly updated |
| **D — Quarterly prune** | Avoid-list items in any layer are eligible for demotion (quarterly cadence per NEGATIVE-PROMPTING-SOP §5) |
| **E — Healer sweep flag** | SOP-DIU-615 integrity sweep flags an INDEX integrity issue, a stale version pin, or a card schema gap |
| **F — Retire request** | CDO requests a style card be retired (deprecated, superseded, or client-offboarded) |

---

## Procedure

### Procedure A — Card Status Promotion to INDEX

**When to run:** Trigger A — Fidelity Tester promotion notification received.

**Inputs:** Card ID, new status (`tested` or `production`), card file path, test log file path.

1. Open INDEX.md. Locate the card's existing row by ID.
2. Verify the card file exists at the declared path and the file's own `status:` field matches the incoming promotion. If there is a mismatch, halt and return the discrepancy to the Fidelity Tester — do not update INDEX.md against a card file that contradicts it.
3. Update the row: set `Status` column to the new value; update `Ver` and `Date` columns from the card file header.
4. **Increment the Registrar counter.** The INDEX.md summary block tracks the cumulative count of `tested` + `production` cards. Add 1 for each promotion event.
5. **If counter >= 50:** Immediately raise a CDO activation ticket: "Library Registrar activation threshold reached (N tested+production cards). Per DEPARTMENT-BUILD-BRIEF §3 Role 6 and SOP-DIU-502, the Library Registrar role is eligible for spin-out. Please schedule `add-role.sh --dept graphics --role 'Library Registrar'` and confirm INDEX write ownership transfer."
6. Write the update. If a concurrent INDEX.md write is detected (file modified timestamp changed since step 1), abort the write, emit a per-card receipt file capturing the intended change, and notify the CDO of the collision. Execute a compiled INDEX write from all pending receipts only after CDO confirms no data loss.

---

### Procedure B — Card Version Bump

**When to run:** Trigger B — Fidelity Tester patch approval received.

**Inputs:** Card ID, old version, new version, change description (from Fidelity Tester).

1. Open the card file. Verify the current version matches `old version` in the notification. If not, halt and reconcile with the Fidelity Tester before touching anything.
2. Apply the version number change to the card file header per MASTER-SOP §8 scheme:
   - Prompt patch (parameters, tone adjustments): increment minor version (e.g., v1.0 → v1.1).
   - Re-analysis (12-dimension re-evaluation, structural card rewrite): increment major version (e.g., v1.x → v2.0).
3. Append a Changelog line to the card file: `| {date} | {new version} | {change description} | {Fidelity Tester name/ID} |`
4. Update the INDEX.md row for this card: `Ver` and `Date` columns only. Do not change `Status` unless the Fidelity Tester's notification includes an explicit status change.
5. Check NAMED-STYLES.md (if present in the client folder) for any alias pinned to this card ID:
   - **v1.x patch (minor bump):** Alias pointer auto-advances. Update the alias's pinned version to the new version.
   - **v2.0 re-analysis (major bump):** Do NOT auto-advance. Route to SOP-DIU-607 version-advance logic: CDO confirmation required + Fidelity Tester side-by-side regression render against the frozen reference set before the alias pointer moves.

---

### Procedure C — Model Event (New Model or Deprecation)

**When to run:** Trigger C — new Kie.ai endpoint confirmed available, or an endpoint confirmed deprecated.

**Inputs:** API documentation (new endpoint) or deprecation notice (existing endpoint). Verified from the actual Kie.ai API docs — never assumed.

**Adding a new model (MODEL-SPECS §6, 7-step protocol):**

1. Obtain the actual API documentation. Record all fields: model ID, prompt character limit, negative prompt support, reference image support (count, size), aspect ratios, resolutions, required vs. optional parameters, special parameters.
2. Add a row to the MODEL-SPECS §1 roster table and aspect-ratio table.
3. Update the MODEL-SPECS §2 routing table if the new endpoint wins any task category over an existing first-choice entry.
4. Update MODEL-SPECS §3 tier compatibility.
5. Add a MODEL-SPECS §4 prompting-notes block and a MODEL-SPECS §5 JSON template for the new endpoint.
6. Bump MODEL-SPECS version and date; log the change in MODEL-SPECS §7 Changelog.
7. **Do NOT touch any style card.** Cards are model-agnostic by design. This rule is absolute.
8. Update the library-version pin in this SOP (SOP-DIU-502) and notify the CDO so all thin-wrapper SOPs that reference MODEL-SPECS can be re-verified and re-pinned.

**Deprecating an existing model:**

1. Flag the deprecated endpoint in MODEL-SPECS §1 as `DEPRECATED` with effective date.
2. Update MODEL-SPECS §2 routing table: remove the deprecated endpoint from first-choice and backup columns. Promote the next-best endpoint accordingly.
3. Update MODEL-SPECS §3 and §4 to remove or mark deprecated entries.
4. Log the change in MODEL-SPECS §7 Changelog with the deprecation date and reason.
5. **Do NOT touch any style card.** Cards are model-agnostic.
6. Notify the CDO: any active jobs or in-flight receipts referencing the deprecated model must be re-routed before their next submission attempt.

---

### Procedure D — Quarterly Avoid-List Prune

**When to run:** Trigger D — quarterly cadence, or on CDO request.

**Scope:** Layer 1 (universal baseline in NEGATIVE-PROMPTING-SOP §2), Layer 2 (category `_RULES.md` avoid-list sections), Layer 3 (per-card AVOID-LIST blocks).

1. For each avoid-list item in each layer, count how many test logs reference that item as having prevented a defect in the last 10 generations of that style (or across the library, for Layer 1 items).
2. Items with zero relevance hits across 10+ generations of their scope are candidates for demotion.
3. **Do not delete candidates unilaterally.** Compile a demotion candidate list and present it to the CDO as: `[item text] | Layer {1/2/3} | Last relevant generation: {log entry} | Candidate reason: no hits in last N generations`.
4. Prune only items the CDO explicitly approves for removal.
5. For each approved removal, append a Changelog line to the affected file: date, version bump, item removed, demotion reason, and the CDO approval reference.
6. If the prune affects a card's AVOID-LIST (Layer 3), this constitutes a v1.x minor version bump. Apply Procedure B for the version bump and INDEX update.

---

### Procedure E — Healer Sweep Response

**When to run:** Trigger E — SOP-DIU-615 flags an issue.

1. Read the Healer's flagged item report in full before taking any action.
2. For each flagged item, identify the governing procedure from this SOP (A through F) and execute it.
3. Stale version pins (this SOP's library-version pin block does not match the current file versions): re-verify all §-references against the current library file versions, update the pin block at the bottom of this file, and log the re-verification date.
4. INDEX bijection failures (a card file exists but has no INDEX row, or an INDEX row points to a missing file): resolve by adding the missing INDEX row (if the card file is valid) or marking the INDEX row `retired` with a note (if the card file is gone and intent is confirmed by CDO).
5. Report resolution to the Healer and CDO. Do not mark a Healer flag as resolved without a confirmed, disk-persisted fix.

---

### Procedure F — Style Card Retirement

**When to run:** Trigger F — CDO requests a card be retired.

1. Confirm the retirement reason with the CDO (deprecated, superseded by newer card, client offboarded, quality failure with no patch path).
2. Update the card file header: set `status: retired`, add a `Retired:` line with the date and reason.
3. Update the INDEX.md row: set `Status` to `retired`; update the `One-Line Summary` to append `(retired: {reason})`.
4. **Never delete the INDEX row.** History matters — the retire-never-delete rule is absolute.
5. Check NAMED-STYLES.md for any alias pointing to this card ID. If found, the alias must be re-pointed to an active card or marked as retired by the CDO before this procedure is complete. Do not leave a broken alias pointer.
6. Notify the CDO that the card is retired and any downstream aliases have been resolved.

---

## Inputs

| Input | Required | Source |
|---|---|---|
| Fidelity Tester promotion notification (Procedures A, B) | Required for A/B | Fidelity Tester |
| Card file with updated content and version (Procedure B) | Required for B | Fidelity Tester patch output |
| Verified API documentation for new endpoint (Procedure C) | Required for C-add | Kie.ai API docs (verified, not assumed) |
| Deprecation notice with effective date (Procedure C) | Required for C-deprecate | Kie.ai official notice |
| Test log generation history for prune scoring (Procedure D) | Required for D | `_local/test-logs/` per card |
| CDO prune approval list (Procedure D) | Required for D | CDO |
| Healer-Graphics SOP-DIU-615 flagged-item report (Procedure E) | Required for E | Healer-Graphics role |
| CDO retirement confirmation (Procedure F) | Required for F | CDO |

---

## Outputs

| Output | Location | Consumed by |
|---|---|---|
| Updated INDEX.md row(s) | `45-design-intelligence-library/library/INDEX.md` | All roles — INDEX is the global lookup authority |
| Updated card file (version bump + Changelog) | Card's declared file path | Fidelity Tester, Generation Operator |
| Updated MODEL-SPECS.md (model event) | `45-design-intelligence-library/library/_system/MODEL-SPECS.md` | Generation Operator, Fidelity Tester, all thin-wrapper SOPs referencing MODEL-SPECS |
| Updated NEGATIVE-PROMPTING-SOP.md (prune) | `45-design-intelligence-library/library/_system/NEGATIVE-PROMPTING-SOP.md` | Generation Operator (SOP-DIU-303) |
| Registrar activation ticket (if counter >= 50) | CDO | CDO (role-activation decision) |
| Alias advance or hold notification (version bump) | NAMED-STYLES.md + CDO notification | SOP-DIU-607, CDO |
| Retirement notification + alias resolution (Procedure F) | CDO + NAMED-STYLES.md | CDO, Style Analyst (lookbook update) |

---

## Handoff Conditions

- **Card status promotion (A):** INDEX.md updated with new status, Registrar counter incremented, activation ticket raised if >= 50. Hand to CDO if activation ticket was raised; otherwise no further handoff required.
- **Version bump (B):** Card Changelog updated, INDEX.md version field updated, alias advance or hold resolved per SOP-DIU-607 if applicable. Hand to Fidelity Tester if a v2.0 regression render is required before alias advance.
- **Model addition (C-add):** MODEL-SPECS fully updated through all 7 steps, Changelog entry written, version bumped, all thin-wrapper SOP owners notified to re-verify their pins. No card was touched — confirm this explicitly in the notification.
- **Model deprecation (C-deprecate):** MODEL-SPECS updated, in-flight jobs using the deprecated model identified and CDO notified for re-routing. No card was touched.
- **Quarterly prune (D):** CDO-approved items removed from avoid-lists with Changelog entries; affected cards version-bumped; INDEX updated. Hand to CDO for final approval sign-off.
- **Healer sweep response (E):** All flagged items resolved and confirmed to disk. Report sent to Healer and CDO. No flag left open without a resolved state.
- **Retirement (F):** Card and INDEX retired, alias pointers resolved or retired. Hand to CDO for confirmation; hand to Style Analyst to remove the card from the client-facing Lookbook (SOP-DIU-607).

---

## Escalation Triggers

| Condition | Action | Route to |
|---|---|---|
| INDEX.md concurrent write detected | Abort second write; emit per-card receipt files; halt until CDO confirms resolution | CDO |
| Card file version does not match Fidelity Tester notification (Procedure B) | Halt all version-bump steps; return discrepancy with card file header and notification text | Fidelity Tester |
| Candidate new model cannot be fully documented from API docs (missing char limit, template fields, etc.) | Do not add incomplete row to MODEL-SPECS; return gap list to CDO | CDO |
| Avoid-list prune candidate has ambiguous generation history (log files missing or incomplete) | Do not score that item; flag it as "unscored — log gap" in the candidate list presented to CDO | CDO |
| NAMED-STYLES.md alias found pointing to a card being retired, but CDO has not confirmed a replacement target | Halt Procedure F completion; retirement is not complete until alias is resolved | CDO |
| Registrar counter reaches >= 50 | Raise activation ticket immediately; do not defer until "next session" | CDO |
| Healer sweep flags this SOP's own library-version pin as stale | Re-verify all §-references against current file versions; update pin block; report to Healer | Healer-Graphics, CDO |
| Any library file conflict with a rule in this SOP | Library file wins; report the discrepancy to CDO rather than resolving silently | CDO |

---

## Library Governance Note — Dormant-Until-Active Clause

This SOP describes the Registrar duty folded into the Style Analyst role per DEPARTMENT-BUILD-BRIEF §3 Role 6. The duty is dormant in the sense that it only fires on explicit triggers — there is no background polling or speculative governance. Once the INDEX.md production card count reaches >= 50, the CDO spins out the Library Registrar as a standalone role. At that point:

1. Ownership of this SOP transfers to the Library Registrar.
2. The Style Analyst's section-9 entry for SOP-DIU-502 in `SOP--style-analyst-sops.md` is updated to show "Owner transferred to Library Registrar."
3. INDEX.md write authority is transferred — the Style Analyst no longer writes INDEX rows directly.

Until that threshold is crossed, the Style Analyst executes this SOP in full.

---

## Library-Version Pin

```
MASTER-SOP v1.0                §8                  verified 2026-06-12
MODEL-SPECS v1.2               §6, §7              verified 2026-06-12
INDEX.md v2.0                  full document       verified 2026-06-12
NEGATIVE-PROMPTING-SOP v1.0    §5                  verified 2026-06-12
```

If any pinned file is updated to a new version, the Healer-Graphics SOP-DIU-615 integrity sweep will flag this pin as stale. The CDO (or Library Registrar once active) must re-verify all §-references and update this pin block before this SOP is used under the new version.

---

*Thin-wrapper SOP. All protocol content lives in the library files listed above. Do not copy library content into this file — copies drift. This file points; the library governs.*
