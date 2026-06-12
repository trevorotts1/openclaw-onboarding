# SOP-DIU-102 — Batch & Multi-Style Clustering from Deck Sources

**ID:** SOP-DIU-102
**Classification:** Vendor SOP (thin wrapper)
**Owner Role:** Style Analyst ("The Eye")
**Version:** 1.0
**Date:** 2026-06-12
**Library-version pin:** PPT-ANALYSIS-SOP v1.1, MASTER-SOP v1.0, STYLE-CARD-TEMPLATE v1.0, INDEX.md v1.0 (§-refs verified 2026-06-12).

---

## 1. ROLE MISSION (scoped to this SOP)

The Style Analyst's batch responsibility is to extract a complete, collision-free set of style cards from a multi-slide or multi-image source rather than a single reference. This SOP governs that extraction: clustering the source into visually distinct families, confirming the cluster map with the CDO before any card is written, running per-cluster dedupe, authoring individual cards per cluster, cross-linking siblings, and emitting both per-card and batch-level receipts. The library files listed in Section 2 are the source of truth — this wrapper does not duplicate their content.

---

## 2. GOVERNING LIBRARY FILES (source of truth — do not duplicate)

| File path (from repo root `45-design-intelligence-library/library/`) | Sections governing this SOP | What this SOP uses from it |
|---|---|---|
| `_system/PPT-ANALYSIS-SOP.md` | §2 (batch survey + clustering protocol), §4 (batch analysis of non-deck image sets) | Clustering pass algorithm, family identification rules, cross-reference rules for sibling styles, batch receipt schema, practical limits |
| `_system/MASTER-SOP.md` | §§3–4 (Golden Rule + 12-Dimension Protocol), §6 steps 6–7 (card registration) | Per-card analysis protocol executed for each non-duplicate cluster |
| `_system/STYLE-CARD-TEMPLATE.md` | Full template | Card format each cluster produces; Model Notes cross-reference field |
| `_system/INDEX.md` | Registration rules | Dedupe pre-check authority; registration target after Fidelity Tester promotion |

**Cross-SOP dependencies invoked during this procedure:**

| SOP | When invoked |
|---|---|
| SOP-DIU-101 (SOP 9.1 in style-analyst role) | Steps 4–7 of this SOP: per-cluster card authoring follows SOP-DIU-101 steps 4–7 exactly |
| SOP-DIU-606 (SOP 9.4) | Step 3 of this SOP: dedupe pre-check per cluster |

---

## 3. WHEN TO RUN

**Trigger:** A multi-slide PowerPoint, multi-page PDF, or batch of 4+ related images arrives from the CDO or Brainstorming Buddy requiring style system extraction — i.e., the source is expected to contain more than one distinct visual style.

**Do NOT run this SOP** for a single-image or single-slide reference — use SOP-DIU-101 (Workflow A) directly.

**Frequency:** On-demand; typically 1–3 times per month per client.

---

## 4. INPUTS

| Input | Required | Notes |
|---|---|---|
| Source deck or image batch | Yes | .pptx, .pdf, or 4+ related images; rasterize per PPT-ANALYSIS-SOP §2 Step 1 before analysis |
| Brief from CDO | Yes | Client name, intended category, how many distinct style families expected (CDO's prior belief), provenance classification (client-owned vs. third-party-style-only) |
| INDEX.md (read access) | Yes | Required for dedupe pre-check per cluster |
| Embedding index (via SOP-DIU-606) | Yes | Required for similarity scoring during dedupe |

---

## 5. PROCEDURE

### Step 1 — Receive and confirm the brief

Receive the source and the brief. Before any analysis begins, confirm with the CDO:

- How many distinct style families are expected?
- Is this source client-owned provenance or third-party-style-only provenance? (Third-party: style analysis is permitted; near-verbatim reproduction is prohibited.)
- If any slide or image depicts a real person's face or likeness: HALT and notify the CDO + Photo Shoot Director. The PHOTO-SHOOT-SOP §1 consent gate must run BEFORE that slide's style enters a card as a reference.

Do not proceed until provenance is confirmed and any likeness gate is resolved.

---

### Step 2 — Run the PPT-ANALYSIS-SOP §2 clustering pass

Execute the full batch survey and clustering protocol from PPT-ANALYSIS-SOP §2 (Steps 1–3):

1. Rasterize all slides/pages per §2 Step 1.
2. Batch-survey slides in groups of ~10; tag each slide with layout archetype, dominant colors, text density, and imagery type (§2 Step 2).
3. Cluster slides into distinct style families: target 3–8 families; a family requires ≥2 member slides unless structurally critical (e.g., the sole title slide). Merge families that differ only in content, not style. Record slide-to-family membership evidence (§2 Step 3).

**Gate — cluster map review:** Produce a written cluster map (family labels, member slide numbers, one-sentence visual description per family). Do not proceed to individual card authoring until the CDO has reviewed and confirmed the cluster map. Record the CDO's confirmation in the batch receipt.

For non-deck image batches, follow PPT-ANALYSIS-SOP §4 instead: determine whether the batch resolves to one consistent style (→ single SOP-DIU-101 card) or multiple styles (→ this SOP continues). Report the evidence and recommendation and obtain CDO confirmation before writing files.

---

### Step 3 — Dedupe pre-check per cluster

For each confirmed cluster, run SOP-DIU-606 (SOP 9.4, Steps — Dedupe Gate) before assigning any card ID:

- Compute the embed payload from a 2–3 sentence description of the cluster's dominant mood, palette, and style.
- Query the embedding index for top-5 nearest neighbors.
- Record similarity scores per cluster.
- Apply thresholds:
  - **≥ 0.92:** HALT — surface to CDO: "Cluster [X] closely resembles [CARD-ID] (similarity: N.NN). Should I version the existing card, register as sibling, or proceed as independent with documented rationale?" Do not proceed without a written CDO decision.
  - **0.80–0.91:** Register with mandatory sibling cross-links in both cards' Model Notes. Record the similarity score and sibling card IDs in the new card's receipt.
  - **< 0.80:** Proceed without flags.

---

### Step 4 — Author individual cards per cluster

For each cluster that cleared the dedupe gate, author a style card following SOP-DIU-101 Steps 4–7 exactly:

- Execute the 12-Dimension Protocol per MASTER-SOP §§3–4 on 2–3 representative slides from the cluster. Record only what differs from or specializes any identified shared foundation (see PPT-ANALYSIS-SOP §2 Step 4).
- Fill every section of STYLE-CARD-TEMPLATE.md. No section may be left blank or marked "TBD."
- Count actual prompt characters for each tier block; annotate explicitly. Flag any tier exceeding 2,800 characters (Seedream hard cap: 3,000 chars).
- Set card status = "draft."
- Emit a per-card receipt file: `{CARD-ID}.json` with fields: id, name, category, status, version, authored-by, authored-date, similarity-scores-at-creation, provenance-class, batch-id.

---

### Step 5 — Cross-reference sibling styles

Per PPT-ANALYSIS-SOP §4 (sibling style rule): when two or more cards emerge from the same source deck or batch, add cross-reference links in each card's Model Notes section. Format: `Sibling styles from same source: [CARD-ID-A], [CARD-ID-B] — [source-deck-name]`.

If the batch produced a set of families that share a common visual foundation (same palette and type system, different layouts), evaluate whether this is better represented as a PPT Deck Style System file rather than independent cards. If yes, flag to CDO and route to Deck Systems Specialist per SOP-DIU-201. Do not author flat cards for a set that warrants the deck schema.

---

### Step 6 — Emit batch receipt and hand off

**Per-card receipts:** already emitted in Step 4. Each goes to the Fidelity Tester with a handoff note per SOP-DIU-101 Step 7.

**Batch-level receipt:** emit `{BATCH-ID}-batch.json` containing:

```json
{
  "batch_id": "{BATCH-ID}",
  "source_deck_path": "{path}",
  "source_provenance": "client-owned | third-party-style-only",
  "cdo_cluster_confirmation_date": "{ISO date}",
  "cards_produced": ["{CARD-ID-1}", "{CARD-ID-2}", "..."],
  "cards_halted_duplicate": [{"cluster": "X", "matched": "CARD-ID", "similarity": 0.00}],
  "cluster_similarity_scores": [{"cluster": "A", "top_match": "CARD-ID", "score": 0.00}, "..."],
  "batch_receipt_authored": "{ISO date}"
}
```

**Send to:** Batch receipt → CDO. Each individual draft card + per-card receipt → Fidelity Tester (one handoff per card, per SOP-DIU-101 Step 7).

---

## 6. INPUTS SUMMARY

| Input | Description |
|---|---|
| Source deck or image batch | Rasterized slides/pages or 4+ related images |
| CDO brief | Client, category, expected families, provenance |
| INDEX.md + embedding index | For dedupe gate per cluster |
| CDO cluster-map confirmation | Written approval before card authoring begins |

---

## 7. OUTPUTS

| Output | Destination |
|---|---|
| 1–N completed draft style cards (STYLE-CARD-TEMPLATE format) | Fidelity Tester (one per cluster that cleared dedupe) |
| N per-card receipt files (`{CARD-ID}.json`) | Fidelity Tester (with each card) |
| 1 batch-level receipt (`{BATCH-ID}-batch.json`) | CDO |
| CDO cluster-map confirmation record | Retained in batch receipt |
| Cross-reference links in each card's Model Notes | Embedded in card files |

---

## 8. HANDOFF CONDITIONS

| Condition | Action |
|---|---|
| Cluster map complete | Hand cluster map to CDO for written confirmation before writing any card. |
| Dedupe score ≥ 0.92 on a cluster | Halt that cluster; surface to CDO for decision before proceeding. |
| All cards authored and receipted | Hand each draft card + per-card receipt to Fidelity Tester via SOP-DIU-101 Step 7 handoff note. |
| Batch complete | Hand batch-level receipt to CDO. |
| Set qualifies as a Deck Style System | Flag to CDO; route to Deck Systems Specialist (SOP-DIU-201). Do not author flat cards. |

---

## 9. ESCALATION TRIGGERS

| Trigger | Escalate to | Evidence required |
|---|---|---|
| Any cluster dedupe score ≥ 0.92 | CDO | Cluster description, matched CARD-ID, similarity score |
| Any slide depicts a real person's likeness | CDO + Photo Shoot Director | Slide number(s), description of likeness present |
| Source deck contains < 5 slides per cluster | CDO | Cluster ID, member slide count, note: "insufficient signal — recommend collecting additional reference slides before authoring" |
| After 2 analysis attempts, a cluster is too visually ambiguous to produce a complete card | CDO | Cluster description, slides examined, written diagnosis — never submit an incomplete card |
| Deck resolves to a Style System (shared foundation + family set) | CDO + Deck Systems Specialist | Evidence: which slides share foundation vs. differ; recommendation to build as PPT Deck Style System file |
| Source provenance is legally ambiguous (unlicensed, unclear ownership) | CDO | Source description, ambiguity statement — do not proceed until provenance is resolved |

---

## 10. LIBRARY-VERSION PIN

**Mandatory.** This SOP is pinned to the following library file versions. If any file version advances, the Healer-Graphics SOP-DIU-615 sweep will flag this pin as stale and a regeneration is required before executing this SOP against updated library content.

| Library file | Pinned version | Pin verified |
|---|---|---|
| `_system/PPT-ANALYSIS-SOP.md` | v1.1 | 2026-06-12 |
| `_system/MASTER-SOP.md` | v1.0 | 2026-06-12 |
| `_system/STYLE-CARD-TEMPLATE.md` | v1.0 | 2026-06-12 |
| `_system/INDEX.md` | v1.0 | 2026-06-12 |

---

*End of SOP-DIU-102. Authority: vendor DEPARTMENT-BUILD-BRIEF §4. Authoritative role entry: style-analyst.md Section 9.2. Mirror: SOP--style-analyst-sops.md SOP 9.2.*
