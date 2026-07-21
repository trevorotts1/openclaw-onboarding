# Stage 2 QC Summary — role library

**Measurement status:** not-measured
**Last measured at repo version:** v11.0.1
**Last measured (UTC):** 2026-06-09
**Roles observed at last measurement:** 244
**Stage 2 verdict at the current repo version:** NONE — NOT MEASURED

There is no Stage 2 quality-control verdict for this library at the current repo
version. This file does not certify anything. The only run on record is
Role Library v11.0.1, described below, and it does not describe the tree that
ships today.

## Why this file no longer carries a verdict (finding T0-07)

This artifact was generated once, on 2026-05-19 at v10.6.0, and last genuinely
re-measured on 2026-06-09 at v11.0.1 (commit `5c4075a5`), covering 244 roles
across 19 departments.

It was also registered as a repo-wide **version marker**, so
`scripts/bump-version.sh` rewrote the version out of its heading on every
release. Nothing re-ran quality control; only the number moved. Across more than
500 commits since that run the heading advanced from v11.0.1 to v20.0.87 while
the generation date, the role count and the blanket pass verdict stayed exactly
where the 2026-06-09 run had left them. It was restamped three more times during
the review that produced this fix — twice on the branch that removed it.

The result was an artifact that read as a current, comprehensive certification of
a library it had never been run against — and that renewed that claim
automatically on every release. Every version gate in the repository passed the
whole time, because the marker genuinely did equal `/version`. The number it
agreed on was simply meaningless.

**What changed:** the rewrite was removed from `scripts/bump-version.sh`, and the
marker entry was removed from `scripts/version-markers.json` and from the inline
fallback list in `23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py`.
This file is now rewritten only by a real quality-control run, which must write
the count it observed and the timestamp it ran at.
`scripts/qc-assert-qc-summary-provenance.py` fails CI if this file is ever again
stamped with a version it was not generated at, or re-registered as a version
marker.

**Deliberately not done:** no verdict was invented to replace the one that was
removed, and no role count was written that was not measured. An honest
"not measured" is the correct content for this file until a run produces a real
one.

## Current library inventory — an inventory, NOT a quality-control result

Counted directly from the tree at the commit that wrote this file. These are
file-system observations. No role was read, no dimension was scored, and nothing
below is a judgement about role quality.

| Observation | Value | How it was measured |
|---|---|---|
| Department directories | 36 | directories directly under `role-library/`, excluding `_`-prefixed |
| Role documents | 450 | `.md` files directly inside those 36 directories, excluding `_`-prefixed |
| Role sub-directories | 46 | directories nested inside those 36 directories (not counted above) |
| Roles declared by `_index.json` | 438 | its `total_roles` field |
| Departments declared by `_index.json` | 36 | its `total_departments` field |

Two things worth recording, neither of them resolved here:

- The direct file count (450) and the index's declared role count (438) **do not
  agree**. Reconciling them is a job for a real run, not for this file.
- Both are far above the 244 the last recorded run covered, and the department
  count has grown from 19 to 36. Whatever the 2026-06-09 verdict established, it
  did not establish it about the roles added since.

## Last recorded Stage 2 run (historical — superseded, not current)

| Field | Value |
|---|---|
| Repo version | v11.0.1 |
| Date | 2026-06-09 |
| Roles covered | 244 |
| Departments covered | 19 |
| Commit | `5c4075a5` |

The per-department result table from that run has been removed rather than
carried forward. It described 19 departments that no longer describe this tree,
and a reader scanning this file for a verdict should not find one that predates
the library by 194 or more roles. The full historical content remains in git
history and in `23-ai-workforce-blueprint/CHANGELOG.md`.

## Rubric a run must score against (specification, not a result)

These are the thresholds a Stage 2 run applies. Listing them here states what
*would* be measured; none of them has been measured at the current version.

| Dim | Name | Threshold |
|---|---|---|
| D1 | Structural Completeness (19 sections) | ≥6.5 |
| D2 | Persona Governance Override | ≥6.5 |
| D3 | Tier-1 Research Citations | ≥6.5 |
| D4 | SOP Atomicity and Count (≥5 / ≥8 for QC+DR) | ≥6.5 |
| D5 | KPI Revenue Linkage | ≥6.5 |
| D6 | Concrete Examples | ≥6.5 |
| D7 | Edge Case Rigor | ≥6.5 |
| D8 | Token Correctness (no literal client data) | ≥6.5 |
| D9 | Industry-Agnostic Framing | ≥6.5 |
| D10 | Section 19 Sub-Specialists (≥3) | ≥6.5 |
| D11 | Model Compliance (no Anthropic/Claude) | ≥6.5 |

**Pass threshold:** total ≥85 AND every dimension ≥6.5.

## What a real run must write here

A run that regenerates this file must replace the provenance block with its own
observations:

- `Measurement status:` `measured`
- `Last measured at repo version:` the repo `/version` the run executed at
- `Last measured (UTC):` the real completion timestamp of the run
- `Roles observed at last measurement:` the count of role documents the run
  actually read — not a count copied from `_index.json`, and not a target

and only then may it state a verdict. A verdict without those four fields is not
evidence.
