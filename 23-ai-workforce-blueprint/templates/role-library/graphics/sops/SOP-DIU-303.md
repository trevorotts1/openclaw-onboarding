# SOP-DIU-303 — Negative Prompt Assembly
**ID:** SOP-DIU-303
**Band:** Vendor (3xx — Generation Operator)
**Owner role:** Generation Operator ("The Operator")
**Status:** Vendor SOP — thin wrapper
**Version:** 1.0 | **Date:** 2026-06-12
**Library-version pin:** NEGATIVE-PROMPTING-SOP v1.0 (§-refs verified 2026-06-12); MASTER-SOP v1.0; MODEL-SPECS v1.0; TEST-PROTOCOL v1.0.

---

## Role Mission (scoped to this SOP)

The Generation Operator is responsible for assembling a complete, contradiction-free, per-model negative payload before every API submission. This SOP governs that assembly. The three-layer stack is the single source of truth for what goes into every generation's avoid-list; no layer may be skipped, added to ad hoc, or resolved unilaterally. When a contradiction surfaces, the operator halts and returns it to the prompt author — never guesses.

---

## Governing Library Files (source of truth — do NOT duplicate content here)

| File | Sections used | What it owns |
|---|---|---|
| `_system/NEGATIVE-PROMPTING-SOP.md` | §§1–3, §4, §5 | Three-layer stack definition; universal baseline; per-model delivery mechanisms; writing rules; avoid-list growth protocol |
| `_system/MASTER-SOP.md` | §3.2, §7 | Positive Foundation Block and Style DNA (required for contradiction audit in step 5) |
| `_system/MODEL-SPECS.md` | §1, §5 | Per-endpoint character budget caps (Seedream 3,000-char ceiling); JSON template structure for each endpoint |
| `{category}/_RULES.md` | avoid-list section | Layer 2 category-specific negatives |
| `{CARD-ID}.md` (style card) | AVOID-LIST block | Layer 3 card-specific negatives |
| `_local/test-logs/{CARD-ID}-test-log.md` | failure entries | Informs item priority selection (step 4b below) |

> The library is law. If a rule here conflicts with a library file, the library file wins. Report the discrepancy to the CDO rather than resolving it silently.

---

## Procedure

**When to run:** Before every generation. For multi-asset jobs, run once at job start and cache the result. Do not re-derive per asset within the same job.

**Inputs:**
- Style card ID + version (must be present in INDEX.md with `status: production`)
- Category identifier (determines which `_RULES.md` to pull Layer 2 from)
- Fully assembled positive prompt (Foundation Block + Style DNA + Subject Block + filled variables), required for the contradiction audit
- Model + endpoint selection (determines delivery mechanism: Ideogram negative field vs inline imperative conversion)
- `likeness: true` flag if the job includes identity-locked content (activates people-specific baseline additions from NEGATIVE-PROMPTING-SOP §2)

**Steps:**

1. **Pull Layer 1 — Universal baseline.** Read `_system/NEGATIVE-PROMPTING-SOP.md §2`. Copy the universal baseline avoid-list verbatim. If the job is flagged `likeness: true`, also include the people-specific additions block from the same section. This layer is non-negotiable and appears in every generation, no exceptions.

2. **Pull Layer 2 — Category baseline.** Read the avoid-list section of the relevant `{category}/_RULES.md`. If the category `_RULES.md` has no avoid-list section, record "Layer 2: none defined" in the compiled artifact — do not skip the step silently.

3. **Pull Layer 3 — Card-specific avoid-list.** Read the AVOID-LIST block of the style card at the pinned version. If the card has no AVOID-LIST entries, record "Layer 3: none defined" — do not skip silently.

4. **Merge and deduplicate.**
   - Combine all three layers in order: Layer 1 → Layer 2 → Layer 3.
   - Remove exact-string duplicates. Preserve semantically distinct entries even if they address similar concerns (e.g., "extra fingers" and "distorted hands" are distinct — keep both).
   - For inline-conversion endpoints (everything except Ideogram V3): apply the priority step: select the **10 strongest** items from the merged list. If the endpoint is Seedream (3,000-char budget), cap inline negatives at **5 items maximum**, one sentence each. Consult the card's test log for which defects this style actually produces — those items rank highest.

5. **Contradiction audit (NEGATIVE-PROMPTING-SOP §4).** Scan every item in the merged list against the positive Foundation Block and Style DNA:
   - If any negative term directly contradicts a positive instruction (e.g., negative: "harsh shadows" while positive: "dramatic high-contrast lighting"), **halt assembly immediately**.
   - Return to the prompt author with the full conflict itemized: the negative term, its source layer and citation, the conflicting positive term, and its source (Foundation Block or Style DNA section). Do not guess which to drop. Do not proceed until the author resolves the conflict and provides an updated positive prompt or revised avoid-list.

6. **Select per-model delivery format (NEGATIVE-PROMPTING-SOP §3):**
   - **Ideogram V3 only:** deliver the merged avoid-list as a comma-separated phrase list in the `negative_prompt` field (5,000-char capacity). Do not also embed negatives in the main prompt — that wastes character budget.
   - **All other endpoints (GPT-Image-2, Nano Banana 2, Seedream 4.5, Wan 2.7):** convert the top-10 (or top-5 for Seedream) selected items to explicit imperative sentences ("Do not..."). Place as the final paragraph of the assembled prompt. Record the conversion mapping in the compiled artifact.
   - Record the delivery format chosen in the compiled artifact.

7. **Write the compiled artifact.** For every job (single or multi-asset), write `_local/jobs/{job-id}/compiled-negatives.json` with:
   - `layer_1`: the universal baseline items used
   - `layer_2`: the category items used (or "none defined")
   - `layer_3`: the card-specific items used (or "none defined")
   - `merged_deduped`: the full merged list before priority selection
   - `delivery_items`: the items selected for delivery (top-10 or top-5 for inline endpoints; full list for Ideogram)
   - `delivery_format`: `"ideogram_negative_field"` or `"inline_imperative"`
   - `contradiction_audit`: `"passed"` or a record of the conflict returned to the author
   - `likeness_job`: `true` or `false`

   For multi-asset jobs: every asset in the job references this single file. Do not re-derive per asset.

---

## Inputs (summary)

| Input | Required | Source |
|---|---|---|
| Style card ID + version at `status: production` | Required | INDEX.md + card file |
| Category identifier | Required | Job brief / CDO request |
| Fully assembled positive prompt | Required | SOP-DIU-301 step 3 output |
| Model + endpoint selection | Required | SOP-DIU-302 output |
| `likeness: true` / `false` flag | Required | Job brief / Photo Shoot Director handoff |

---

## Outputs

| Output | Location | Consumed by |
|---|---|---|
| `compiled-negatives.json` artifact | `_local/jobs/{job-id}/compiled-negatives.json` | SOP-DIU-301 (Workflow B) step 3 — injected into final assembled prompt before preflight |
| Contradiction conflict report (if triggered) | Returned to prompt author; no file written until resolved | Prompt author (CDO or requesting role) |

---

## Handoff Conditions

- **Normal:** Compiled negatives artifact written with `contradiction_audit: "passed"`. Hand to SOP-DIU-301 (Workflow B) for final prompt assembly and injection before preflight gate (SOP-DIU-601).
- **Contradiction found:** Return conflict report to the prompt author. Assembly is halted. No artifact is written in a partial state. Resume only after author provides a resolution and this SOP runs again from step 1.
- **Multi-asset job:** After the artifact is written once at job start, the operator does not re-run this SOP per asset. Every asset references the same artifact.

---

## Escalation Triggers

| Condition | Action | Route to |
|---|---|---|
| Contradiction found in step 5 | Halt assembly; return itemized conflict (negative term + source, positive term + source) to prompt author | Prompt author (CDO or requesting role) |
| Category `_RULES.md` is missing or has no avoid-list section | Record "Layer 2: none defined"; flag to CDO as a gap to fill | CDO |
| Style card has no AVOID-LIST block | Record "Layer 3: none defined"; flag to CDO for card enrichment | CDO |
| Seedream job: merged list exceeds 3,000-char prompt budget after inline conversion is added | Return budget-exceed count to requestor; do not exceed cap silently (silent Seedream failure per SOP-DIU-615 integrity rule) | Prompt author |
| Avoid-list growth event (defect surfaces post-generation) | Do not modify layers directly. Route defect type + generation receipt to Fidelity Tester for avoid-list growth protocol (NEGATIVE-PROMPTING-SOP §5) | Fidelity Tester |

The operator does not modify any avoid-list layer. The Fidelity Tester owns avoid-list growth via TEST-PROTOCOL + NEGATIVE-PROMPTING-SOP §5. The operator consumes the library; it does not edit it.

---

## Avoid-List Growth Protocol (pointer only)

This SOP does not own avoid-list growth. When a defect in a delivered asset implies an avoid-list gap, the operator routes the evidence to the Fidelity Tester. The growth protocol lives in `_system/NEGATIVE-PROMPTING-SOP.md §5` and is executed by the Fidelity Tester role.

---

## Library-Version Pin

```
NEGATIVE-PROMPTING-SOP v1.0   §§1–5   verified 2026-06-12
MASTER-SOP v1.0               §3.2, §7  verified 2026-06-12
MODEL-SPECS v1.0              §1, §5    verified 2026-06-12
TEST-PROTOCOL v1.0            §5        verified 2026-06-12
```

If any pinned file is updated to v1.x or higher, the Healer-Graphics SOP-DIU-615 integrity sweep will flag this pin as stale. The CDO must re-verify all §-references and update this pin line before the SOP is used under the new version.

---

*Thin-wrapper SOP. Content lives in the library files listed above. Do not copy library content into this file — copies drift. This file points; the library governs.*
