# Department Assignment Decision Tree

**Purpose:** Document the deterministic mapping from interview answers to department enablement decisions. An operator can predict which departments will be enabled from a given set of answers without reading the source code.

**Date:** 2026-07-24
**Owner:** Skill 23 (AI Workforce Blueprint)

---

## Overview

Department assignment is a deterministic, four-stage pipeline. Each stage runs in order during the workforce build (`build-workforce.py`). The result is reproducible: the same interview answers always produce the same department set.

```
Interview Answers
       │
       ▼
┌─────────────────────────┐
│ Stage 1: Canonical Floor │  ← 23 mandatory departments (standard-unless-declined)
│ reconcile_canonical_floor│
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ Stage 2: Semantic Merges │  ← Custom depts matched to canonical via keyword model
│ detect_semantic_overlaps │  ← Owner decides: merge INTO canonical or keep standalone
│ apply_semantic_merges    │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ Stage 3: Vertical Packs  │  ← Industry-based department packs
│ apply_vertical_packs     │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ Stage 4: Decision Cover  │  ← Every custom dept needs provenanced yes/no/later
│ _enforce_decision_coverage│
└──────────┬──────────────┘
           │
           ▼
   Final Department Set
```

---

## Stage 1: Canonical Floor (`reconcile_canonical_floor`)

The canonical floor is the set of 23 mandatory departments defined in `department-naming-map.json` . These are included by default unless the client explicitly declined them during the interview.

**Logic:**
```
final = (all canonical MINUS explicit "no" in build-state) UNION client customs
```

**Decision rules:**
- If a `canonicalReconciliation.decisions` block exists in build-state, honor each explicit "no" (drop that canonical dept) and keep everything else.
- If NO reconciliation block exists, include ALL canonical depts (standard) and write an auditable `canonicalReconciliation.autoIncluded` record.
- Client-named canonical depts keep the client's real description (already in `selected_departments`).
- Canonical depts the client did NOT name inherit the naming-map one-liner, contextualized with company industry/voice.
- Client custom (non-canonical) departments are always preserved.
- Idempotent: re-running never duplicates a folder and never overwrites a client-authored description.

**Canonical department IDs (23 mandatory):**
```
marketing, sales, billing-finance, customer-support, web-development,
funnels, app-development, graphics, video, audio, research,
communications, crm, openclaw-maintenance, legal, social-media,
paid-advertisement, personal-assistant, general-task,
project-architecture-office, bugs, healer, quality-control
```

**Decline mechanism:** During the interview, the client can decline any canonical department. The decline is recorded in `build-state.canonicalReconciliation.decisions` with a provenance record. Declined departments are excluded from the final set.

---

## Stage 2: Semantic Merges (`detect_semantic_overlaps` + `apply_semantic_merges`)

Custom departments that semantically overlap a canonical floor department are detected via a deterministic keyword model (no LLM). The owner decides whether to merge or keep.

**Detection:** For each custom dept, the normalized name and description are checked against `SEMANTIC_OVERLAP_KEYWORDS`. A match against exactly one canonical ID makes it a merge candidate.

**Keyword model (deterministic, no LLM):**

| Canonical ID | Keywords (whole-word/phrase signals) |
|---|---|
| billing-finance | accounting, bookkeeping, bookkeep, tax, taxes, payroll, invoicing, accounts payable, accounts receivable, ledger |
| customer-support | client success, customer success, client care, client services, account success, help desk, helpdesk, client experience |
| graphics | brand identity, brand and identity, brand design, identity design, visual identity, branding design, creative design, logo design |
| crm | marketing and crm, crm automation, marketing automation, convert and flow, convert & flow, pipeline automation, customer relationship management |
| openclaw-maintenance | *(vertical keywords in separate map)* |

**Decision rules:**
- `mergeDecisions[<custom_id>] == "merge"` → FOLD the custom INTO the canonical dept. The canonical dept survives; the custom dept's roles/SOPs are layered in. The standalone custom dept is dropped.
- `mergeDecisions[<custom_id>] == "keep"` → Leave both standalone. No merge.
- Absent / any other value → Conservative DEFAULT: keep both standalone and record the proposal as PENDING. NEVER auto-merge without a recorded confirm.

**Idempotent:** A custom already folded (absent from `selected_departments`) is a no-op. Records an auditable `semanticMerges` block into build-state.

---

## Stage 3: Vertical Packs (`apply_vertical_packs`)

Industry-based department packs are applied based on the client's industry answer. Each vertical pack adds a set of departments relevant to that industry.

**Logic:** The `apply_vertical_packs` function reads the client's industry from `core_answers["industry"]` and matches it against known vertical packs. Matched packs add their departments to the selected set.

---

## Stage 4: Decision Coverage (`_enforce_decision_coverage_or_refuse`)

Every custom department must carry a provenanced yes/no/later decision. If any custom dept lacks a decision, the build is REFUSED.

**Logic:** The function checks that every custom department in `selected_departments` has a corresponding entry in `build-state.canonicalReconciliation.decisions`. If any are missing, the build refuses with `RECONCILIATION_NOT_COMPLETE`.

---

## Decision-Tree Preview (Phase 5.6 -- Pipeline Output Before Finalizing)

During the interview flow, after completing Phase 5.5 reconciliation, the operator renders the full 4-stage pipeline output before the owner confirms the final department set. This is a new Phase 5.6 step -- it shows the actual computed result of running Stages 1-4 against the owner's answers, not just a description of what will happen.

### 1. Canonical Floor Report (Stage 1 output)
- Every canonical department (23 mandatory) with its status:
  - `INCLUDED` -- part of the final set (not declined)
  - `DECLINED` -- owner explicitly said no (with decline provenance)
  - `COVERED` -- owner already named this department in Phase 4
  - `MISSING` -- not yet addressed; needs a decision before finalizing
- Count: how many of 23 are included vs declined

### 2. Semantic Merge Proposals (Stage 2 output)
- Each custom department flagged by `detect_semantic_overlaps()`:
  - The custom department name + the canonical department it maps to
  - The keyword signal(s) that triggered the overlap detection
  - Decision recorded: `merge`, `keep`, or `PENDING`
- Count: how many merges proposed, how many decided

### 3. Vertical Pack Additions (Stage 3 output)
- The detected industry and which vertical packs matched
- Each additional department added by the matched packs
- Whether each vertical-pack department is floor (universal-primary) or industry-gated
- Count: how many vertical departments added

### 4. Custom Departments (Stage 4 output)
- Every custom department the owner named that did NOT match a canonical ID
- Each custom department's decision: `yes`, `no`, `later`, or `PENDING`
- Count: how many customs in the final set

### Preview Format

The operator renders the preview as a single structured message to the owner:

```
=== DEPARTMENT DECISION-TREE PREVIEW ===

STAGE 1 -- CANONICAL FLOOR (23 mandatory)
  INCLUDED (N):
    [list each with display_name + one_liner]
  DECLINED (N):
    [list each with decline reason]

STAGE 2 -- SEMANTIC MERGES
  PROPOSED:
    [custom_name] -> [canonical_name] (signal: [keyword])
    Decision: [merge / keep / PENDING]
  NO OVERLAPS DETECTED

STAGE 3 -- VERTICAL PACKS
  Industry: [detected industry]
  Packs matched: [pack names]
  Departments added (N):
    [list each with display_name + one_liner]

STAGE 4 -- CUSTOM DEPARTMENTS
  KEPT (N):
    [list each]
  MERGED INTO CANONICAL (N):
    [custom_name] -> [canonical_name]
  DECLINED (N):
    [list each]

FINAL SET: [N] departments
  Canonical: [N] | Vertical: [N] | Custom: [N] | Total: [N]

Ready to finalize? (YES / ADJUST)
```

The operator confirms or adjusts before the build proceeds. No department advances to `status: "done"` until the owner confirms the preview.

---

## Reproducibility

The same interview answers always produce the same department set. The mapping is deterministic:

- Canonical floor: determined by `department-naming-map.json` + decline decisions
- Semantic merges: determined by `SEMANTIC_OVERLAP_KEYWORDS` + owner merge/keep decisions
- Vertical packs: determined by industry answer
- Decision coverage: enforced, not optional

No LLM is used in the department assignment logic. The AI generates the interview questions dynamically, but the mapping from answers to departments is deterministic code.

---

## Validation

The canonical department IDs in this document are validated against `department-naming-map.json` by two automated checks:

1. **CI test:** `tests/unit/u052-department-doc-validation.test.sh` -- asserts every canonical ID listed in this document exists in `department-naming-map.json` and that every mandatory department in the naming map appears in this document. Fails if any ID is fabricated or missing.

2. **Manual validation script:** `scripts/qc-validate-department-docs.py` -- cross-references this document against the naming map and reports any mismatches with exit code 0 (clean) or 1 (drift detected).

Both checks are mutation-proof: altering a canonical ID in this document to an invalid value makes the test FAIL (RED); reverting the change makes it PASS (GREEN).

---

*End of DEPARTMENTS.md. This document is the single source of truth for the department assignment decision tree.*
