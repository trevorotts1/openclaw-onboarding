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

---

# COHORT 2 SECTION — 20 units, changed-risk review (unit W12B-U2)

Appended by the focused changed-risk reviewer for merged cohort 2 (W12B-U2,
owner order 2026-10-23; W12-U1 remains sole writer of the cohort-1 half above).
Same taxonomy as sections 3-6 above, extended by the risk classes named in the
owner order: silent retry after an uncertain write, create-without-read-before-
create, name-only identity matching, publishing without explicit approval,
treating a save as a publish, required/hidden field state written but not read
back, picking an arbitrary browser tab, claiming a platform capability that is
not verified. Method: read the MERGED code at the merged tree (every line of
every unit file), judge against those classes, prove merge state with git.
Per the owner order this review reuses the self-check evidence recorded in
TASK-LEDGER.md and does NOT re-execute the 20 unit self-checks.

## C2-1. Scope — what is merged

Repo: `trevorotts1/openclaw-onboarding`. Cohort 2 (Batch 2 of
`integrations/BATCH-MERGE-LOG.md`) is merged: member PR #2496
(`w12b-u1/cohort2-ghl-delivery`, 20 units, 26 files) folded by merge train
PR #2498 (`batch/auto-merge`) into `origin/main` =
`d430a4d74976111d3c94eb72c0e5d5872ccb88e3` (merge `7e0bdfec7` is the cohort
fold; `76692f205` the member-PR head). Cohort freeze base: `510995e0c…`
(cohort-1 train merge). W1B-U1 was EXCLUDED from this cohort by the assembly
(self-check loader defect, recorded verbatim in BATCH-MERGE-LOG.md) and is not
reviewed here.

The 20 units and their owned files (exactly the cohort diff of `7e0bdfec7`):
W2A `shared-utils/ghl/capability_inventory.py` + `shared-utils/ghl/__init__.py` ·
W1A `shared-utils/delivery/npage_contract.py` ·
W1C `shared-utils/delivery/graph_validation.py` ·
W3A `shared-utils/browser/browser_manager.py` + `browser_manager_selfcheck.py` ·
W3B `shared-utils/browser/iframe_router.py` ·
W3C `shared-utils/browser/runtime_adapters.py` + `test_runtime_adapters.py` ·
W4A `shared-utils/delivery/checkpoints.py` ·
W4B `shared-utils/delivery/evidence.py` ·
W7B `shared-utils/delivery/link_resolution.py` ·
W5A `shared-utils/ghl/primitives.py` ·
W2-U1 `shared-utils/ghl/object_router.py` ·
W2-U2 `shared-utils/ghl/recipe_transport.py` ·
W8B `skills/80-upsell/native_upsell.py` ·
W8D `shared-utils/ghl/products_prices.py` ·
W6C `shared-utils/ghl/embed_handoff.py` ·
W6A `shared-utils/ghl/forms.py` ·
W6B `shared-utils/ghl/surveys.py` ·
W9A `shared-utils/design/composition.py` ·
W9B `49-signature-funnel/role_wrappers.py` (+ `SKILL.md`/`skill-version.txt`
v2.1.22→v2.1.23, the train's mechanical G3 bump) ·
W7C `shared-utils/delivery/publishing.py`.
Out of scope: S75X Skill-75 batches and the Skill-77 batch merged through
adjacent trains (fenced per section 1); the 999 backport (separate repo).

## C2-2. Merge facts (command evidence, run at this tree)

```
$ for sha in <20 unit heads from BATCH-MERGE-LOG.md> 7e0bdfec7 76692f205;
      do git merge-base --is-ancestor $sha origin/main; done   # 22/22 exit 0
$ git rev-parse origin/main
d430a4d74976111d3c94eb72c0e5d5872ccb88e3
```
22/22 ancestors proven. Cohort surface is near-pure addition (22 new Python
modules, 2 new check/test files, new `shared-utils/ghl/__init__.py`;
only `49-signature-funnel/SKILL.md` + `skill-version.txt` change existing
lines — the one-line version bump — plus the append-only BATCH-MERGE-LOG).
No pre-existing module is modified, so the regression surface is the Python
import graph (new namespace packages `shared-utils/{ghl,browser,delivery,design}`,
new top-level `skills/80-upsell/`) plus the two finding paths below.

## C2-3. Changed-risk findings (owner-order classes)

| # | Risk class | Finding | Verdict |
|---|---|---|---|
| C1 | Silent retry after an uncertain write | **DEFECT F1 (W8D-U1)** `shared-utils/ghl/products_prices.py:410-415`: `_call` treats `resp.status == 429 or resp.status >= 500` identically and blindly re-sends — including CREATE writes — with backoff but WITHOUT the reconcile-before-retry the class demands. The module's own docstring claims "Timeout/uncertain outcome is reconciled before any retry" and it reconciles only `TransportTimeout` (`:444-447`, `:513-516`); the 5xx branch never reconciles. See C2-4 F1. Holds elsewhere: W2-U2 (classify marks 5xx-on-write UNCERTAIN, reconcile precedes any retry), W5A (`Outcome.UNCERTAIN` never retried), W8B (retry refused until `reconcile()`). | FAIL (F1) |
| C2 | Create-without-read-before-create | No finding. W4A `plan_create`/`record_create` refuse duplicate keys; W6A `create_or_reuse_form` lists before create and reconciles after; W5A `plan_primitives` reconciles against verified listings before any create op; W8D `ensure_product`/`ensure_price` read the durable store first and list-reconcile after a timeout (adopt exactly one identity candidate, refuse 2+, recreate only on zero). | Holds |
| C3 | Name-only identity matching | No finding. W4A identity is the composite (location, kind, parent, logical id); `find_by_name` is diagnostics-only and refuses ambiguity. W1A identity is `logical_id` (role may repeat). W1C rejects unknown kinds/duplicate logical ids. W6A/W5A reuse-by-unique-name is a documented fallback that refuses >1 candidate and prefers the stored logical identity. W8D reconcile matches (name + type + location) and refuses ambiguity. | Holds |
| C4 | Publishing without explicit approval | No finding. W7C `Approval` names every authorized target explicitly (no wildcard), scope violations refuse the WHOLE request before any platform call, domain/version mismatches refuse whole, capture operations require test_location + temporary_objects. | Holds |
| C5 | Treating a save as a publish | No finding. W7C publishes only from state CONFIGURED and only through `CheckpointStore.record_publish` (authorization reference required); publish-return values are never used as URLs; readback missing ⇒ NOT published. W4A `set_state` refuses PUBLISHED outright. W4B evidence kinds keep save/publish/verify distinct. W5A refuses W7-owned states. W9B carries state verbatim, never promotes. | Holds |
| C6 | Required/hidden field state written but not read back | **DEFECT F2 (W8D-U1)** `shared-utils/ghl/products_prices.py:538-539` writes `trialPeriod` (and `recurring.intervalCount`) but `_read_price` (`:542-570`) never reads either back, and `NativePrice` is built at `:561-570` with `trial_days=spec.trial_days` — the REQUEST echoed as if verified. See C2-4 F2. W6A/W6B hold the class exactly (set AND read back both directions, bounded retry, mismatch = `ReadbackMismatch`/INCOMPLETE, negative controls included). | FAIL (F2) |
| C7 | Picking an arbitrary browser tab | No finding. W3B `select_tab` refuses an empty `TargetSpec`, zero matches and ambiguous matches by name; there is no first-tab fallback anywhere; `select_frame` refuses unqualified picks; `guarded_resolve` runs target → capability → fresh-frame → frame. W3A enforces one writer per session/location with PID+start-time ownership. Spec gap 3 closed at the seam. | Holds |
| C8 | Claiming a platform capability that is not verified | No finding. W2A RETIRED/UNVERIFIED are never routable; dynamic surfaces carry no static grant; products/prices is `products_prices_undocumented_here` INCOMPLETE "never as done" with provenance. W2-U1 computes every registration from the frozen registry + W2A grant (`LIVE_PROOF_PENDING`, restricted families forced INCOMPLETE, negative controls included). W8B treats unknown capability as unsupported. W9A refuses unsupported surface ops by name. W8D refuses binding without component IO ("catalog IDs alone are NOT checkout binding"). | Holds |

Cohort-1 classes (R1-R9) re-checked for cohort 2: import graph — new packages
only, namespace import pattern, no pre-existing import site touched (the W1B
`module_from_spec` loader defect is already recorded in BATCH-MERGE-LOG and its
unit is excluded from this cohort) — Holds. Commerce red lines — W8B holds
every one (verified purchase sources only, single-flight, read-back-confirmed
entitlement, no card data, V2-only one-click); W8D carries F1/F2. Invented
platform limits — every bound cites capability_inventory (W8D's local 8s
backoff cap and un-honored Retry-After are noted as O5 below, not invented
limits). Secrets/logging — zero logging in all 20 modules; tokens never enter
error text (W3C ships `redact()`). Self-check hygiene — scratch dirs use
declared prefixes (`operator-W4A-U1-`, `lane-W7C-U1-`, `mac-mini-m4-W3C-U1-`);
W7C/W3C leave theirs behind (O6). Merge safety — disjoint owned files,
22/22 ancestry proof above.

## C2-4. The two defects (do not repair here — repair is a separate owned unit)

**F1 — silent retry after an uncertain write — W8D-U1,
`shared-utils/ghl/products_prices.py:410-415` (function `_call`, 398-419).**
```python
if resp.status == 429 or resp.status >= 500:
    if attempt == self._max:
        raise ApiError(...)
    self._sleep(backoff)
    backoff = min(backoff * 2, 8.0)  # bounded
    continue
```
A 5xx response to a WRITE is an uncertain outcome (the request may have been
applied before the gateway failed) — the project's own taxonomy says exactly
this (`recipe_transport.py` `classify`: `408/500/502/503/504` on a write ⇒
`UNCERTAIN`, "a blind retry of an uncertain mutation never happens";
`capability_inventory.CONTRACTS["uncertain_outcome"]`: reconcile BEFORE
retrying). `_call` retries it blindly, up to `max_attempts` (default 3).
Failure scenario: `ensure_product` POST `/products/` returns 503 after the
platform applied the create; `_call` sleeps and re-POSTs; a second identical
product is created; `ensure_product` readback-verifies only the SECOND
response's `_id` and persists it (`:449-455`); the first product persists as a
silent duplicate. Same for `create_price` (duplicate price on the product).
429 belongs in the retry branch (provider limit, never processed); 5xx-on-
write does not — it needs the module's own `_reconcile_product`/`_reconcile_price`
path first. (The TransportTimeout path at `:406-407`/`:444-447` does it right;
only the 5xx branch is wrong.)

**F2 — state written but not read back — W8D-U1,
`shared-utils/ghl/products_prices.py:538-539` (write), `:542-570` (readback),
`:561-570` (record construction).**
`_price_payload` sends `trialPeriod: spec.trial_days` and
`recurring.intervalCount: 1`, but `_read_price` verifies only `_id`, `product`,
`amount`, `currency`, `type` and `recurring.interval` — never `trialPeriod`,
never `intervalCount` — and then constructs
`NativePrice(..., trial_days=spec.trial_days)`, echoing the request as if it
were observed state. Failure scenario: a `trial_then_recurring` price is
created with `trialPeriod=7`; the platform drops or drifts the trial (stamps
`trialPeriod: 0`/omits it); readback passes every checked field and returns
`readback="verified"`; `as_price_ref_fields()` then hands W8C a 7-day trial the
platform will not honor — wrong terms disclosed at checkout, matching neither
the module's own claim ("verify every create ... against authoritative
GET/read state; a mismatch is a failure, never a silent success") nor spec
gap 2 ("set AND read back — never blind-toggle") / Commerce "accurate terms".

## C2-5. Observations — no demonstrated failure, no change made (owners named)

- O1 W2A `capability_inventory.py:518-530` — DISCOVERABLE entries carry empty
  `op_classes`, so `supports()` is never true for them and `dynamic_confirmed`
  cannot actually route a dynamic surface through `select_route` (self-check 8
  passes on static entries). Fail-closed direction; the documented
  "confirm at runtime then route" path is unimplementable through this API.
  Owner W2A/W2-U1.
- O2 W7C `publishing.py:479-496` — `backend.publish()` return value is ignored
  entirely (contract relies on raise-on-failure) and any exception becomes
  `OUT_PUBLISH_FAILED` without distinguishing a provably-not-applied failure
  from an uncertain one (timeout); a caller treating "publish_failed" as
  retryable could double-publish. Coordinator itself never retries. Owner W7C
  (seam owned with W2/W5).
- O3 W3B `iframe_router.py:323-325` — `require_current_epoch(None)` silently
  skips the fresh-frame check (documented and self-tested as "not a stale
  claim"); a helper that forgets to pass `frame_epoch` loses the gap-3
  fresh-frame guard. Tab/frame selection itself is fail-closed. Owner W3B.
- O4 Cross-unit seam state: W2-U1 keeps the products family INCOMPLETE per
  `products_prices_undocumented_here` while W8D cites the official OpenAPI spec
  `apps/products.json` as its provenance and flags the inventory update as
  outstanding. Both honest in their own frame; the registration must move only
  through W2B/W2A with the evidence. Owners W2A/W2-U1/W8D.
- O5 W8D `_call` never reads `Retry-After` (contract: "prefer Retry-After") and
  caps backoff at 8s locally instead of the catalog's `BACKOFF_CAP_SECONDS`;
  bounded either way. Owner W8D.
- O6 Self-check scratch dirs left behind by W7C (`lane-W7C-U1-*`) and W3C
  (`mac-mini-m4-W3C-U1-*`) `harness_paths` probes. Prefixed and attributable;
  W10B-style `finally` cleanup would finish the hygiene class. Owners W7C/W3C.
- O7 W8D cross-run "resume never duplicates" holds only while the durable store
  (W4A checkpoints) is wired; with the default `InMemoryStore` a crash between
  create and persist re-creates on the next run. Documented outstanding seam
  ("The durable store is wired to W4A ... at integration"). Owner W8D/W4.

## C2-6. Completion evidence (reused from TASK-LEDGER.md, per owner order)

Recorded by the integrator on the train tree at 2026-10-23T21:47Z (coordinator-
verified against the remote): all 20 unit self-checks re-proven (W2A/W1A/W1C
PASS · W3A 8 · W3B 20 · W3C 8 pytest · W4A 54 · W4B 28 · W7B 40 · W5A · W2-U1
53 · W2-U2 · W8B 40 · W8D 34 · W6C 28 · W6A 40 · W6B 29 · W9A 70 · W9B 64 ·
W7C), `py_compile` 23/23 exit 0, `batch-prep.sh --check` exit 0, exact-version
manifest heads in BATCH-MERGE-LOG.md, `49-signature-funnel` v2.1.23 bump by the
train. This reviewer read the merged code instead of re-running those checks,
and independently proved ancestry (C2-2) and the two defect paths (C2-4)
against the tree. No disabled or missing platform capability is claimed as done
anywhere in the 20 modules: every seam says INCOMPLETE/outstanding in its own
text.

## C2-7. Verdict

**Cohort 2 (20 units) changed risk: FAIL** — two blocking findings, both in
W8D-U1 `shared-utils/ghl/products_prices.py`:
F1 silent retry after an uncertain write (`:410-415`, scenario C2-4 F1);
F2 trial/recurrence state written but not read back (`:538-539` / `:542-570`,
scenario C2-4 F2).
All other named classes: no finding (Holds per C2-3). Repair belongs to the
W8D owning unit (separate repair unit — this reviewer changed no product code).
Review commits: this append + `evidence/W12B/W12B-U2.verdict.json` on branch
`w12b-u2/cohort2-review` (based on `d430a4d74`). Landing remains the
integrator's protected batch process — this reviewer never merges.
