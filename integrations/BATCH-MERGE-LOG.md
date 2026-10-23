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

### Merge proof — Batch 1 (appended by W12B at Batch 2)

- Member pull request [#2491](https://github.com/trevorotts1/openclaw-onboarding/pull/2491)
  (`w12a-u1/cohort1-w8a-w10b`, assembly head `dd318fa76`, final head `c2775d6db`) was folded by
  the merge train into batch pull request
  [#2492](https://github.com/trevorotts1/openclaw-onboarding/pull/2492) (`batch/auto-merge`) and
  merged to `main` 2026-10-23T15:59Z — `CONTROL/AUTOMERGE.log`: `MERGED BATCH #2492 -> 510995e0c`
  / `MERGED #2491 via batch #2492 -> 510995e0c`.
- Merge commit: `510995e0cadff7d863c8be62d272613c1af512f4` (origin/main at Batch 2 freeze).
- Ancestry proven 2026-10-23 (W12B, `git merge-base --is-ancestor <sha> origin/main`):
  W8A `89af6b7cab534fe3bbd27655b5a658db8447954f` → true;
  W10B `e8cfa1bf8f6755cbd438f23967b5f1673248f761` → true.

## Batch 2 — 2026-10-23 — repo `trevorotts1/openclaw-onboarding`

- Base (cohort freeze): `510995e0cadff7d863c8be62d272613c1af512f4` (origin/main, post #2492).
- Exact versions at base: /version `v27.1.65` (all 10 version markers agree — `scripts/batch-prep.sh --check`),
  release-cohort.json `onb_version=v27.1.65 cc_version=v7.6.112 contract=1.1.0`,
  cc-compat.json `commandCenter.pinnedTag=v7.6.112`;
  `49-signature-funnel/skill-version.txt` `v2.1.22` at base → `v2.1.23` in this cohort
  (G3 mechanical bookkeeping by `scripts/batch-prep.sh`: W9B adds `role_wrappers.py` content to
  skill directory `49-signature-funnel/`; the only version-file change in this cohort).
- Member pull request: [#2496](https://github.com/trevorotts1/openclaw-onboarding/pull/2496)
  (`w12b-u1/cohort2-ghl-delivery` → `main`), ONE pull request for this repository cohort.
  Assembly head `a87cf0cc9524b421096afeb54daa3402508944d9` (manifest commit); final head =
  tip of this pull request at fold time (exact SHA in the W12B integration evidence).
- Release policy: no member changes `/version`; the train performs ONE version bump + ONE
  combined CHANGELOG entry at fold time, and `auto-tag-on-merge` cuts the tag on the merged commit.

| Unit | Branch (pushed) | Head (exact, 40-char) | Files | Runnable check (run on merged tree) | Result |
|---|---|---|---|---|---|
| W2A-U1 | `w2a-u1/capability-inventory` | `f72aec0307339ce4de2a7db3e6a8190943c450a8` | `shared-utils/ghl/capability_inventory.py`, `shared-utils/ghl/__init__.py` | `python3 -I shared-utils/ghl/capability_inventory.py` | `capability_inventory self-check: PASS` (37 routes), exit 0 |
| W1A-U1 | `unit/W1A-U1-npage-contract` | `8a7090cd1812a99b0896e50dee31c96c7733543f` | `shared-utils/delivery/npage_contract.py` | `python3 -I shared-utils/delivery/npage_contract.py --self-test` | `SELF-TEST OK`, exit 0 |
| W1C-U1 | `w1c-u1/graph-validation` | `b20fcf35ae6d7e80539daa4855c4f6f5e5c59c66` | `shared-utils/delivery/graph_validation.py` | `python3 -I shared-utils/delivery/graph_validation.py` | `graph_validation self-check: PASS`, exit 0 |
| W3A-U1 | `w3a-u1/browser-writer-lease` | `32b7ef361695579ff22f9c0267a61b6154b9e5c8` | `shared-utils/browser/browser_manager.py`, `browser_manager_selfcheck.py` | `python3 -I shared-utils/browser/browser_manager_selfcheck.py` | `{"checks_passed": 8}`, exit 0 |
| W3B-U1 | `w3b-u1/iframe-router-safeguards` | `1e4354635f69fd3ce475d481a3403ab5d078ea0d` | `shared-utils/browser/iframe_router.py` | `python3 -I shared-utils/browser/iframe_router.py --selftest` | `SELFTEST PASS (20 checks)`, exit 0 |
| W3C-U1 | `w3c-u1/runtime-adapters` | `9c65a117d66af4e1913392d6850f04ad13c6f133` | `shared-utils/browser/runtime_adapters.py`, `test_runtime_adapters.py` | `python3 -m pytest -q shared-utils/browser/test_runtime_adapters.py` | `8 passed`, exit 0 |
| W4A-U1 | `W4A-U1/checkpoints` | `cf54fd731c2d1c144518cf8e26ad14d43ab45b9a` | `shared-utils/delivery/checkpoints.py` | `python3 -I shared-utils/delivery/checkpoints.py` | `self-check OK (54 assertions)`, exit 0 |
| W4B-U1 | `W4B-U1/evidence-states` | `3b3052ef5b79de7d3faee9f9486b5a5779f729fc` | `shared-utils/delivery/evidence.py` | `python3 -I shared-utils/delivery/evidence.py` | `OK 28 PASS`, exit 0 |
| W7B-U1 | `W7B-U1/link-resolution` | `632a79d6aea44f2251510e04a767322a107fe996` | `shared-utils/delivery/link_resolution.py` | `python3 -I shared-utils/delivery/link_resolution.py` | `OK 40 PASS`, exit 0 |
| W5A-U1 | `w5a-u1/ghl-primitives` | `690ba93cbbd7426b75730e9997aa7c12e8393018` | `shared-utils/ghl/primitives.py` | `python3 shared-utils/ghl/primitives.py` (no `-I`: sibling import of `capability_inventory`; `-I` fails identically in its own lane — instrument, not merge) | `primitives self-check: PASS`, exit 0 |
| W2-U1 | `w2-u1/object-router` | `ec20a41e323c66fd835e2ece5c67bf72ebe77307` | `shared-utils/ghl/object_router.py` | `python3 -I shared-utils/ghl/object_router.py` | `object_router self-check: PASS` (53 registrations), exit 0 |
| W2-U2 | `w2-u2/recipe-transport` | `41dc631747b5f297e5dfc0f03bdbfd3dd95ef5fe` | `shared-utils/ghl/recipe_transport.py` | `python3 -I shared-utils/ghl/recipe_transport.py` | `recipe_transport self-check: PASS`, exit 0 |
| W8B-U1 | `w8b-u1/native-upsell` | `bf020fbf697f832e43a8440189012dd4b2eb1f6c` | `skills/80-upsell/native_upsell.py` | `python3 -I skills/80-upsell/native_upsell.py` | `native_upsell self-check: 40 assertions OK`, exit 0 |
| W8D-U1 | `w8d-u1/products-prices` | `a11babb15d5310e7c57eff9b1e0986cc0a23db9d` | `shared-utils/ghl/products_prices.py` | `python3 -I shared-utils/ghl/products_prices.py` | `self-check OK (34 assertions)`, exit 0 |
| W6C-U1 | `W6C-U1/embed-handoff` | `0e335918c13c1084ed09b6899b3b0e8a432404cb` | `shared-utils/ghl/embed_handoff.py` | `python3 -I shared-utils/ghl/embed_handoff.py` | `OK 28 PASS`, exit 0 |
| W6A-U1 | `W6A-U1/forms` | `09ddbaedbcd5cb3d15c17bd5e2fd49067f1a6087` | `shared-utils/ghl/forms.py` | `python3 -I shared-utils/ghl/forms.py` | `OK forms self-check: 40 assertions`, exit 0 |
| W6B-U1 | `W6B-U1/surveys` | `afa5d8842a8e7a58be4400c8218f7d1e4a025f17` | `shared-utils/ghl/surveys.py` | `python3 -I shared-utils/ghl/surveys.py` | `self-check OK (29 assertions)`, exit 0 |
| W9A-U1 | `w9a-u1/design-composition` | `1ef4557ecb30213ec165df5ecf44d24da73d727c` | `shared-utils/design/composition.py` | `python3 -I shared-utils/design/composition.py` | `OK 70 PASS kinds=8 roles=7`, exit 0 |
| W9B-U1 | `W9B-U1/role-wrappers` | `a4a185538639d1b05488c582225695136c8a23d9` | `49-signature-funnel/role_wrappers.py` | `python3 -I 49-signature-funnel/role_wrappers.py` | `OK role_wrappers self-check: 64 assertions`, exit 0 |
| W7C-U1 | `W7C-U1/publishing-coordinator` | `dff57971f57812ab002a63255754e8e66b1233c8` | `shared-utils/delivery/publishing.py` | `python3 -I shared-utils/delivery/publishing.py` | `W7C-U1 self-check: all assertions passed`, exit 0 |

Excluded from this cohort (per rule: self-check must pass on the merged tree):

| Unit | Branch | Head | Reason |
|---|---|---|---|
| W1B-U1 | `w1b-u1/route-adapters` | `88ad2f6e680fea3e4e5375336cdd65f2a1440bb5` | Self-check fails on the merged tree once W1A's `shared-utils/delivery/npage_contract.py` exists: `load_npage_contract()` (`route_adapters.py:155-159`) runs `module_from_spec` + `exec_module` without registering the module in `sys.modules`, so `@dataclass` in `npage_contract.py:121` raises `AttributeError: 'NoneType' object has no attribute '__dict__'` under Python 3.14 lazy annotation evaluation (crash at `contract_status()`). Passes in its own lane (65 assertions) only because the seam file is absent there (`npage_contract_present: false` path). Minimal repro `/tmp` (2 files, no repo) reproduces exactly: with the file present → exit 1; removed → `OK route_adapters self-check: 65 assertions`. Not a conflict and not an instrument artifact (fails with and without `-I`). Unit needs a one-line loader fix (`sys.modules[spec.name] = module` before `exec_module`) in its OWN file by its own writer; re-enter at a later batch. |

Cohort assembly: `git merge --no-ff` of each unit commit onto the base, in dependency order
(W2A first — W2-U1/W2-U2/W5A depend on it; W4A/W4B/W7B before W7C; W7C last of the delivery
modules). Disjoint owned files across all 20 units, all 20 merges clean, zero conflicts.
Merge commits (in order): `3dac87571` W2A · `31c2f88d4` W1A · `cc30c55e8` W1C · `dcb2203f2` W3A ·
`c014b00cb` W3B · `1822b7054` W3C · `1469c8660` W4A · `5c51a9f2c` W4B · `0ca0fbc02` W7B ·
`ad5444c57` W5A · `fc857b150` W2-U1 · `5cc4e2600` W2-U2 · `de0e40104` W8B · `6c6717ff9` W8D ·
`60d59b48e` W6C · `e39759088` W6A · `1b4c3e7f3` W6B · `d122b6c2a` W9A · `ebd92b7e7` W9B ·
`ec44bffcf` W7C. Additional merged-tree evidence: `python3 -m py_compile` on all 22 added
files exit 0; `bash scripts/batch-prep.sh` → `All 10 version markers agree.` /
skill-frontmatter-version-guard PASS / skill-version-newline-guard PASS / `batch-prep: done`,
exit 0 (produced the `49-signature-funnel` v2.1.22→v2.1.23 bump above).
Assembly head before this log commit: `1e9e16fec98112952272f701b857d144c41aad6f`; final
cohort head = tip of the member pull request (exact SHA in the W12B integration evidence and in
the follow-up log commit below).
