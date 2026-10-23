# CHANGED-RISK-REVIEW.md — W12 focused changed-risk reviewer (unit W12-U1)

One focused changed-risk review + completion-evidence check over merged GHL-delivery
cohorts. One writer for this file: W12-U1. Method: read every changed line at the
merged tree, re-run every claimed check independently (never relaying the integrator's
or builders' claims), and prove merge state with git. No full-repo campaigns, no paid
renders, no live GHL operations.

Runnable check for this review: `python3 -I integrations/changed_risk_review_selfcheck.py`
(assert-based, stdlib only, re-proves every factual claim below).

## 1. Scope — what is merged as of this review

Repo: `trevorotts1/openclaw-onboarding`. Exactly one GHL-delivery cohort is merged:

| Cohort | Land path | Train merge | Member unit heads (40-char) |
|---|---|---|---|
| Batch 1 (cohort 1) | PR #2491 (`w12a-u1/cohort1-w8a-w10b`) folded by merge train #2492 | `510995e0cadff7d863c8be62d272613c1af512f4` on `origin/main` | W8A-U1 `89af6b7cab534fe3bbd27655b5a658db8447954f`, W10B-U1 `e8cfa1bf8f6755cbd438f23967b5f1673248f761` |

Cohort freeze base: `4b48ce34775b78afd55abfcd52fa85c8efc3c271`. Integration manifest
(commit `c2775d6dbe355dbc36a3d241bd70016bd747dfb2`): `integrations/BATCH-MERGE-LOG.md` (W12A, sole writer).

Out of scope, stated as outstanding integration (provisional):
- Cohort 2 (21-unit assembly) is NOT merged — W12B-U1 is assembling `w12b-u1/cohort2-ghl-delivery`;
  PR open + batch-train landing still pending. Queued members per the ledger:
  W2A `f72aec03`, W3A `32b7ef36`, W3B `1e435463`, W3C `9c65a117`, W6C `0e335918`, W8B `bf020fbf`.
- 999 backport (W10A) lands in the separate `999-setup` repository — its own changed-risk pass there.
- S75X batches (#2493/#2494, Skill 75) are fenced outside this implementation; not reviewed here.
- Owner live testing (real funnels, native checkout/bump purchase flows) is owner-side per spec
  completion criteria and was never executed by this reviewer.

## 2. Changed-surface facts (command evidence)

```
$ git diff --stat 4b48ce347..510995e0c
 integrations/BATCH-MERGE-LOG.md          |  42 ++++
 shared-utils/skills/__init__.py          |  31 +++
 shared-utils/skills/discovery_aliases.py | 356 +++++++++++++++++++++++++++++
 skills/79-checkout/order_bumps.py        | 375 +++++++++++++++++++++++++++++++
 4 files changed, 804 insertions(+)
```

Pure addition: 804 insertions, **0 deletions**. No pre-existing line changed or removed,
so no existing code path can change behavior; the only regression surface is the Python
import graph (checked at R1 below).

Ancestry (all `git merge-base --is-ancestor` → exit 0, run at `origin/main` = `563321f61`):
`89af6b7ca…` YES · `e8cfa1bf8…` YES · `c2775d6db…` YES · `510995e0c…` (train merge) YES.

Version markers at the merged tree:
`bash scripts/bump-version.sh --check` → `All 10 version markers agree.` exit 0
(release-cohort.json `onb_version=v27.1.65 cc_version=v7.6.112`).

## 3. Changed-risk findings (against GHL-DELIVERY-SPEC.md risk classes)

| # | Risk class | Finding | Verdict |
|---|---|---|---|
| R1 | Import-graph regression (only non-additive surface) | New `shared-utils/skills` regular package vs pre-existing top-level `skills/` dir (contains only `79-checkout/`, no `__init__.py` = namespace portion). Python resolves a regular package ahead of namespace portions regardless of path order, so `from skills.discovery_aliases import …` (the documented pattern) cannot be shadowed. Conversely `skills.79-checkout` was never importable by dotted name (hyphen). `grep` found zero pre-existing `import skills` / `from skills` outside the new package. | No risk |
| R2 | Commerce red lines (spec "Commerce (W8)") | `skills/79-checkout/order_bumps.py` is stdlib-only (dataclasses/typing), zero network, zero subprocess, zero card/payment handling. Configuration + integer-minor-unit arithmetic only. Unknown price is never zero (negative refused at construction); float and bool amounts refused (assert-proven). Double-charge guard: duplicate `native_price_id` in one checkout refused at construction. Silent preselection is unrepresentable: `BumpConfig` has no selection field, `Selection.fresh` is all-unselected, and `select()` is the only selection mutation (assert-proven: fresh totals carry no bump line). | Holds |
| R3 | Invented platform limits (spec gap 3 analog) | `ComponentFamily` limits are caller-declared "from the W2 capability inventory, never invented here"; exceeding `max_bumps` or attaching recurring bumps to a forbidding family fails closed (assert-proven both ways). | Holds |
| R4 | Silent validation of unknowns (spec gap 5 analog) | `canon_skill_id` returns None for unknown names (assert-proven for unknown id, empty name, and fenced skills 75/77); a directory without `SKILL.md` is never validated as a skill (assert-proven); known spelling absent from every root resolves to None, never an invented record. | Holds |
| R5 | Accurate terms | `verify_approved` requires whole-object equality with the approved `PriceRef`; amount drift and currency drift both refused (assert-proven). Bump currency must match checkout currency (assert-proven). | Holds |
| R6 | Recurrence terms | recurring ⇔ interval required, `trial_days` forbidden; `trial_then_recurring` ⇔ `trial_days >= 1` required; `one_time` forbids recurrence terms; recurring/trial bumps require `disclosure_text` (each assert-proven). | Holds |
| R7 | Secrets / logging | No logging, no env reads in `order_bumps.py`; `discovery_aliases.py` reads only `OPENCLAW_SKILLS` (path) and filesystem metadata. No secret surface. | Holds |
| R8 | Self-check hygiene | W10B self-check scratch: `mkdtemp(prefix="operator-W10B-U1-", dir="/tmp")`, removed in `finally`. No residue. | Holds |
| R9 | Merge safety | Disjoint owned files (`skills/79-checkout/` vs `shared-utils/skills/`), both cohort merges clean per manifest; all heads proven ancestors of `origin/main` independently (section 2). | Holds |

## 4. Observations — no demonstrated failure, so no change made
(W8A and W10B remain the sole writers of their files; a reviewer does not edit them.)

- O1 `Selection.flags` is a shallow-frozen dataclass: a caller-supplied dict can be mutated
  after construction, bypassing `select()`. Module-internal constructors build fresh dicts,
  so no demonstrated failure; hardening if ever adopted: freeze with `types.MappingProxyType`.
  Owner W8A.
- O2 `PriceRef.recurrent_interval_or_empty()` is a once-used public-looking helper (cosmetic). Owner W8A.
- O3 `skill_package()["shared_utils"]` reports `real_path.parent / "shared-utils"` without an
  existence check — informational manifest field only. Owner W10B.

## 5. Completion-evidence check (independently re-run at the merged tree)

| Unit | Owned output (exists at head) | Runnable check — exact command | Output / exit | Verdict file | Head match |
|---|---|---|---|---|---|
| W8A-U1 | `skills/79-checkout/order_bumps.py` (375 lines, read in full — real implementation, no stub) | `python3 -I skills/79-checkout/order_bumps.py` | `self-check OK (23 assertions)`, exit 0 | `evidence/W8A/W8A-U1.verdict.json` PASS | `89af6b7ca…` matches unit head |
| W10B-U1 | `shared-utils/skills/discovery_aliases.py` (356 lines) + `shared-utils/skills/__init__.py` (31 lines), both read in full | `python3 -I shared-utils/skills/discovery_aliases.py` | `OK 75 PASS`, exit 0 | `evidence/W10B/W10B-U1.verdict.json` PASS | `e8cfa1bf8…` matches unit head |
| both | — | `python3 -m py_compile skills/79-checkout/order_bumps.py shared-utils/skills/discovery_aliases.py shared-utils/skills/__init__.py` | exit 0 | — | — |

Both self-checks were executed by W12-U1 on the merged tree (`510995e0c` checkout), not
relayed from builder reports. Assert counts match the manifest (23 / 75). No disabled or
missing platform capability is claimed as done: both modules are pure local contract/
discovery code; live GHL behavior belongs to later cohorts and owner testing.

## 6. Verdict

**Batch 1 (W8A + W10B) changed risk: PASS** — no blocking finding; nine risk classes
checked, three non-blocking observations recorded for the owning builders.
**Completion evidence: complete** for both merged units (real implementations, runnable
checks pass at the merged tree, verdict heads match unit heads, manifest heads exact).

Review commits: this file + `integrations/changed_risk_review_selfcheck.py` on branch
`w12-u1/changed-risk-review` (based on `510995e0c`). Merging remains the integrator's
protected batch process — this reviewer never merges, publishes, or deploys.

Re-run: `python3 -I integrations/changed_risk_review_selfcheck.py`
