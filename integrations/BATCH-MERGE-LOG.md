# BATCH-MERGE-LOG.md — W12A integration writer, exact-version manifest

Append-only. ONE integration writer per repository. Cohorts land ONLY through the existing
protected batch process (merge train `batch/auto-merge`, LaunchAgent `com.blackceo.pres-automerge`
→ `pres-automerge.sh` → `pres-batch-tick.py`; manual kick `~/.claude/tools/pres-batch-merge.sh`).
Never admin-merge, bypass, force-push, or disable checks. One batch in flight per repo — an active
batch marks the next due, never a competing train.

## Batch 1 — 2026-10-23 — repo `trevorotts1/openclaw-onboarding`

- Base (cohort freeze): `4b48ce34775b78afd55abfcd52fa85c8efc3c271` (origin/main)
- Exact versions at base: /version `v27.1.65` (all 10 version markers agree — `scripts/bump-version.sh --check`),
  release-cohort.json `onb_version=v27.1.65 cc_version=v7.6.112 contract=1.1.0`,
  cc-compat.json `commandCenter.pinnedTag=v7.6.112`,
  79-signature-order-form/skill-version.txt `0.1.6` (not bumped by this cohort — W8A adds a new
  contract module under `skills/79-checkout/`, which is not a top-level `NN-` skill directory;
  `scripts/batch-prep.sh` selected no skill-version guards for this diff)
- Member pull request: [#2491](https://github.com/trevorotts1/openclaw-onboarding/pull/2491)
  (`w12a-u1/cohort1-w8a-w10b` → `main`), ONE pull request for this repository cohort
- Release policy: no member changes `/version`; the train performs ONE version bump + ONE combined
  CHANGELOG entry at fold time, and `auto-tag-on-merge` cuts the tag on the merged commit.

| Unit | Branch (pushed) | Head (exact, 40-char) | Files | Runnable check (run on merged tree) | Result |
|---|---|---|---|---|---|
| W8A-U1 | `w8a-u1/order-bumps` | `89af6b7cab534fe3bbd27655b5a658db8447954f` | `skills/79-checkout/order_bumps.py` | `python3 -I skills/79-checkout/order_bumps.py` | `self-check OK (23 assertions)`, exit 0 |
| W10B-U1 | `W10B-U1/discovery-aliases` | `e8cfa1bf8f6755cbd438f23967b5f1673248f761` | `shared-utils/skills/discovery_aliases.py`, `shared-utils/skills/__init__.py` | `python3 -I shared-utils/skills/discovery_aliases.py` | `OK 75 PASS`, exit 0 |

Verdicts (independent QC, judged before integration):
`evidence/W8A/W8A-U1.verdict.json` (PASS, head 89af6b7cab534fe3bbd27655b5a658db8447954f),
`evidence/W10B/W10B-U1.verdict.json` (PASS, head e8cfa1bf8f6755cbd438f23967b5f1673248f761).

Cohort assembly: `git merge --no-ff` of each unit branch onto the base, disjoint files
(`skills/79-checkout/` vs `shared-utils/skills/`), both merges clean, zero conflicts.
Additional merged-tree evidence: `python3 -m py_compile` on all three files exit 0;
`bash scripts/batch-prep.sh` → `All 10 version markers agree.` / `batch-prep: done`, exit 0.

## Merge proof (per batch, appended at the next entry)

Definition of merged: the batch process merges the fold of this pull request, and after
`git fetch origin` each unit head and the cohort head must be ancestors of `origin/main`
(`git merge-base --is-ancestor`). Recorded per batch in the next append of this log and in the
integration run evidence; a unit is never recorded merged before that proof.
