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

---

# COHORT 3 SECTION — 7 units, changed-risk review (unit W12B-U3)

Appended by the focused changed-risk reviewer for merged cohort 3 (W12B-U3,
owner order 2026-10-23; the cohort-1 half above is W12-U1's and the cohort-2
half is W12B-U2's — neither is re-covered here). Same taxonomy as C2-3,
extended by the two classes the owner order adds: event/outbox idempotency
and monotonic sequence, and page-count generality (no fixed role-slot
assumptions). Method: read every line of the seven merged files at the merged
tree, judge against those classes, prove merge state with git. Per the owner
order this review REUSES the self-check evidence recorded in TASK-LEDGER.md
and does NOT re-execute any self-check, compile or suite — judgement over the
code only.

## C3-1. Scope — what is merged

Repo: `trevorotts1/openclaw-onboarding`. Cohort 3 is merged: member PR #2499
(`w12b-u1/cohort3-ghl-delivery`) folded into merge train PR #2500
(`batch/auto-merge`) at `origin/main` =
`fb41a73d3e8396a85b03536b8c74a0a2f469d22d` (fold merge `e5d247ce5`, cohort
head `cf46bded030feecc9808a969095cff2df16dea45`). The 7 units and their
owned files (exactly the cohort surface):

W1B `shared-utils/signature_launch/route_adapters.py` (head `6aa7887d12fde641bee8960f5a19384081dfa291`) ·
W4C `shared-utils/delivery/reconciliation.py` (`c51c36a5f266464280796eabec4e9adc43b29e44`) ·
W5B `shared-utils/ghl/funnel_adapter.py` (`7c14db9e92d8db583107e08d7b3e32dd4423993f`) ·
W5C `shared-utils/ghl/website_adapter.py` (`c662ccffef82f5a9e3a2cac6a4978a92e3da8c2e`) ·
W7A `shared-utils/delivery/page_scheduler.py` (`218bf7e214d402c5d6016cb8f4ee5eff9e952726`) ·
W11A `shared-utils/cc/board_events.py` (`1c477e8108948cfaba934114cc623497ffcac610`) ·
W11C `shared-utils/cc/event_outbox.py` (`0f3607e29b506037246f0fb68cc39581060577af`).
Out of scope: cohorts 1-2 above (already reviewed), cohort 4 (W8C/W8D) not
yet landed at this commit, S75X/Skill-77 batches (fenced), the 999 backport
(separate repo), owner live testing (owner-side, never executed here).

## C3-2. Merge facts (command evidence, run at this tree)

```
$ for sha in 6aa7887d c51c36a5 7c14db9e c662ccff 218bf7e2 1c477e81 0f3607e29
             cf46bded0 e5d247ce5; do git merge-base --is-ancestor $sha origin/main; done
9/9 exit 0 (full 40-char heads in C3-1; fold + cohort head included)
$ git diff --stat d430a4d74..fb41a73d3
 7 files changed, 6064 insertions(+)   # exactly the seven unit files
$ git rev-parse origin/main
 fb41a73d3e8396a85b03536b8c74a0a2f469d22d
```
Pure addition over the cohort-2 head: 6,064 insertions, **0 deletions**; no
pre-existing line changed, so the regression surface is the Python import
graph (new namespace modules `shared-utils/cc/`) plus the finding paths below.

## C3-3. Changed-risk findings (owner-order classes)

| # | Risk class | Finding | Verdict |
|---|---|---|---|
| C1 | Blind retry after an uncertain write | No finding. W4C `attempt()` refuses a second attempt while the op lacks a definite outcome (`reconciliation.py:465-467`, PendingOperationError; self-checked). W5B `CheckpointingExecutor` holds a pending-op lock on UNCERTAIN and refuses re-dispatch with no transport call (`funnel_adapter.py:262-284, 309-315`). W7A leaves UNRESOLVED/READBACK_MISMATCH ops open and re-runs see `blocked-pending` with zero dispatches (`page_scheduler.py:411-428`, self-check F). W5C's `RecipeExecutor` never re-runs — one retry authority (the W2-U2 runner's bounded, reconcile-before-retry budget), exhausted/denied results terminal (`website_adapter.py:618-633`). W11C redelivers only under the SAME event identity and a `not_applied`-vs-seq contradiction is never resent (`event_outbox.py:533-548`). | Holds |
| C2 | Create without read-before-create | No finding. W4C `plan()` classifies against authoritative state before any CREATE_NEW and adopts a unique existing object (`reconciliation.py:488-535`). W5B reads the checkpoint store first (`funnel_adapter.py:429-444`) and W5A `plan_primitives` reconciles against verified listings. W5C plans against `existing`/`checkpointed_existing` with ambiguous matches blocked (`website_adapter.py:288-320, 477-509`). W7A branches on `plan_create` and adopts `PageSpec.native_id` objects (`page_scheduler.py:323-350`). | Holds |
| C3 | Name-only identity matching | No finding. W4C confirms only on exact name AND slug in scope and rejects name-only, partial and out-of-scope-only evidence (`reconciliation.py:264-305, 307-333`). W7A identity is the composite CheckpointKey (location/kind/parent/logical_id) with name/slug attributes only (`page_scheduler.py:99-100`). W11A/W11C address by stable hashed task id + idempotency key + event id, never by title (`board_events.py:276-283`, `event_outbox.py:222-230`). W5B/W5C reuse is exact-single-match via W5A, ambiguous refused. | Holds |
| C4 | Publishing without explicit approval | No finding. None of the seven modules publishes anything. W5B/W5C report `desired_state=published` as W7-owned work and refuse PUBLISHED/VERIFIED states (`funnel_adapter.py:588-594`, `website_adapter.py:392-397`, self-checked both ways). W7A exposes no publish API and reports `beyond-scheduler` (`page_scheduler.py:459-463`, self-check K). W11C's "published" is a delivery-stage label on a board event, not a platform publish. | Holds |
| C5 | Treating a save as a publish | No finding. W5B advances a page to CONFIGURED only after a confirmed content write and asserts `published_url is None` throughout (`funnel_adapter.py:495-505`). W5C caps states at CONFIGURED and fails loudly if any row escapes (`website_adapter.py:83-84, 417-420`). W7A reports "saving is never publishing" and keeps `published_url` unset. W4C has no publish surface at all. | Holds |
| C6 | Required/hidden state written but not read back | **DEFECT F3 (W7A-U1)** `page_scheduler.py:399-402`: a create whose readback is unverified (`FinalStatus.OK_UNVERIFIED` — "reported incomplete, never as done", `recipe_transport.py:605-614`) is persisted as a CONFIRMED identity via `complete_op(op_id, native_id=...)` → `STATE_CREATED` ("the confirmed ID is persisted immediately", `checkpoints.py:525-539`). **DEFECT F1 (W5C-U1)** `website_adapter.py:535-540`: `_persist` records ANY row carrying a native_id as a confirmed identity — including `uncertain_unreconciled` rows (`primitives.py:878, 893`), whose id comes from `_native_id_from_body` accepting the key `"id"` from ANY response dict (`website_adapter.py:644-655`). Both launder an unverified value into the durable "confirmed" record. W4C holds the class exactly (name+slug recorded and both read back; explicit `native_id` is the only escape hatch). | FAIL (F1, F3) |
| C7 | Picking an arbitrary tab/frame | No finding. None of the seven selects a tab or frame. W5C's only browser surface routes through the W2A catalog capability `browser.page_content` behind the W3 managed-browser gate and refuses any route switch ("never switch tools to bypass a denial", `website_adapter.py:556-600`, negative control in self-check 11). | Holds |
| C8 | Claiming a platform capability that is not verified | No finding. Missing write routes become capture requests — "capability incomplete, never done", never a guessed selector (W5B `funnel_adapter.py:583-587`, W5C `website_adapter.py:381-391` and the "no verified independent read route" restriction at `:398-401`). W11C `seam_status()` lists its outstanding wiring explicitly (`event_outbox.py:611-626`). W1B records `INTEGRATION_OUTSTANDING` in every doc. W7A reports `no-route` from the real transport. | Holds |
| C9 | Resume/reconcile duplicating pages, forms or products | **DEFECT F2 (W5C-U1)** `website_adapter.py:337` + `:422-424`: every platform write runs inside `execute_plan` BEFORE `_persist` persists anything, the store is optional (`:327`), and there is no `begin_op` anywhere in the path — a crash (or an executor exception) after page creates lands duplicates every created page on resume, and the module's own "no verified independent read route" (`:398-401`) means no listing can even detect the duplicate. The module claims "Confirmed native IDs are persisted immediately ... so a resume never duplicates pages" (`:30-32`). F1's laundering is the same class from the other side (resume binds to an unverified identity and never re-checks). Holds elsewhere: W5B resume is zero-creates with duplicate-create refused (`funnel_adapter.py:274-284`, self-checks); W7A resume dispatches nothing and never re-creates (`page_scheduler.py:336-340`, self-check D); W4C "resume never duplicates" is its guarantee 3 with adopt-in-place. | FAIL (F2, F1) |
| C10 | Event/outbox idempotency and monotonic sequence | **DEFECT F4 (W11A-U1, seam W11C)** `board_events.py:491-498, 558` + `event_outbox.py:274-280`: idempotency itself holds (deterministic keys, UNIQUE key, same-identity retry, nothing deleted), and within one process seq is strictly monotonic in both modules — but the producer's seq allocator is process-memory only while the envelope always carries that explicit seq and the outbox refuses any seq <= its durable `last_seq` (`stale_seq`). After a producer restart the stream re-arms at 1 and every new event for that task is refused until a caller manually re-arms via `SeqAllocator.observe(task_id, outbox.last_seq(task_id))` — a seam named in neither module's outstanding list. Fail-closed (older state never overwrites newer) but cross-run emission is blocked. See C3-4 F4. | FAIL (F4) |
| C11 | Page-count generality (no fixed role-slot assumptions) | No finding. W1B allocates logical IDs per PAGE NODE, never per role ("any number of instances of one role is legal"), never imposes a preset on a caller's own set, and proves 3 repeated role instances on one role (self-check "three repeated downsell instances, three IDs"). W7A schedules "whatever was approved" with 1/4/12/20 asserted and no role table. W5B/W5C iterate `doc.pages`/`admin_folders` at any count. | Holds |

## C3-4. The four defects (do not repair here — repair is a separate owned unit)

**F1 — unverified identity persisted as confirmed — W5C-U1,
`shared-utils/ghl/website_adapter.py:535-540` (`_persist`, 512-546).**
```python
elif row.native_id:
    cp = store.record_create(key, name=spec.name, slug=spec.slug, native_id=row.native_id)
```
`record_create(..., native_id=...)` is the store's CONFIRMED path
(`checkpoints.py:322-332`: "the confirmed ID is persisted immediately and the
state becomes CREATED"). But the rows feeding it include
`uncertain_unreconciled` rows — W5A builds those when the create outcome is
UNCERTAIN or the readback did not confirm, and hands the transport-extracted
id along (`primitives.py:878, 893`). That id comes from
`_native_id_from_body` (`:644-655`), which accepts the key `"id"` from ANY
JSON dict in ANY attempt body — including an error body — and the bridge's
UNCERTAIN results carry it (`:611-623`). Failure scenario: a
`browser.page_content` create ends UNRESOLVED (timeout) with last attempt
body `{"id": "req-123", "error": "..."}`; the row is `uncertain_unreconciled`
with `native_id="req-123"`; `_persist` stamps `STATE_CREATED`/confirmed; the
run honestly reports the page uncertain, but the next run's
`checkpointed_existing` returns the hint and plans REUSE ("resume must never
re-create" — self-check 12 asserts exactly this for ANY stored hint): the
approved page is never created, never reconciled (W5C opens no op — see O3 —
so its own "reconcile before any retry" branch at `:526-531` has nothing to
reconcile), and later reports say reused. Contrast W5B, where the same
UNCERTAIN outcome holds a pending-op lock and the id is NOT persisted
(`funnel_adapter.py:309-311`), and W7A's honest no-id branch
(`page_scheduler.py:389-391`, PLANNED "until confirm_native").

**F2 — crash gap: persisted only after the whole batch — W5C-U1,
`shared-utils/ghl/website_adapter.py:337` (all writes),
`:422-424` (persistence), `:327` (store optional).**
Failure scenario: a 3-page website run creates page "about" on the platform;
the process is killed (or an executor raises) before `_persist` runs; the
store holds nothing; the next run's `checkpointed_existing` returns no hints,
`plan_website` plans CREATE for all three and "about" is created a second
time — a duplicate page that no listing can detect ("website surfaces have
no verified independent read route", the module's own restriction at
`:398-401`). The claim at `:30-32` ("Confirmed native IDs are persisted
immediately ... so a resume never duplicates pages") holds only within the
window after `_persist`; with `store=None` (the default) there is no resume
protection at all while creates still run. Contrast W5B's per-operation
discipline (begin_op before each write, complete_op immediately after,
`funnel_adapter.py:286-315`) and W4C guarantee 1 ("durable intent BEFORE the
uncertain call").

**F3 — unverified create persisted as confirmed — W7A-U1,
`shared-utils/delivery/page_scheduler.py:399-402` (function `_allocate_one`).**
```python
if step.final is rt.FinalStatus.OK_UNVERIFIED:
    if native_id:
        self._store.complete_op(op_id, native_id=native_id)
```
`OK_UNVERIFIED` is the transport's own "readback not performed — contract
demands readback; no probe configured — **reported incomplete, never as
done**" (`recipe_transport.py:605-614`) or "readback inconclusive — reported
unverified" (`:626-629`). `complete_op(native_id=...)` persists the
"confirmed ID immediately" as `STATE_CREATED` (`checkpoints.py:525-539`).
Failure scenario: the provider returns 200 + `{"id":"pg-9"}` but the create
did not persist (exactly why the readback is demanded); the store now claims
a confirmed identity; phase 2 passes its gate (`:469`, state == CREATED) and
dispatches EDIT content to the phantom id; every later run reports ST_REUSED
"already checkpointed; resume must never duplicate" (`:336-340`) and
`counts()` counts it CREATED — the approved page silently never exists while
the reports say configured/reused. The module's own neighboring branch
(`:389-391`) shows the honest pattern for the no-id case (record stays
PLANNED "until confirm_native"); the per-run row says `created-unverified`
but the durable record cannot carry that nuance, and `run()` can erase even
the per-run signal by taking the configure outcome over the allocation
outcome (`:276-283`).

**F4 — cross-run monotonic seq blocked by fail-closed stale_seq — W11A-U1
(seam W11C), `shared-utils/cc/board_events.py:491-498, 558` with
`shared-utils/cc/event_outbox.py:274-280`.**
`SeqAllocator` keeps `_last` in process memory and `BoardEventStream._build`
allocates from it per event; `to_outbox_envelope` always carries that explicit
seq (`board_events.py:471-478`), and the outbox refuses any explicit seq that
is not strictly greater than its durable per-task `last_seq`
(`OutboxError("stale_seq: ...")`). Failure scenario: run 1 of a builder emits
create/start (outbox seq 1, 2) for one ingest correlation; the process
restarts (crash/resume — this project's core scenario); run 2 emits complete;
the fresh allocator yields seq 1; `append_envelope` raises `stale_seq` and the
completion event never enqueues — the board never shows the task finishing.
Idempotency is untouched (keys derive from logical identity) and the refusal
is fail-closed (older state never overwrites newer — rule 3 holds), but the
producer rule the contract states ("the producer assigns a strictly
increasing per-task seq", `board_events.py:26-28`) is true only within one
process. The recovery seam exists in both modules
(`SeqAllocator.observe`, `EventOutbox.last_seq`) but is wired by nobody and
named in neither module's outstanding list (W11A has none; W11C
`seam_status()` lists only the producer call wiring and the reconcile
resolver).

## C3-5. Observations — no demonstrated failure, no change made (owners named)

- O1 W4C `reconciliation.py:257-263, 407-408` — an empty authoritative scope
  is a sound absence claim (`not_found`, lock released for a clean retry). If
  an injected lookup is eventually consistent, an applied-but-not-yet-visible
  write classifies `not_found` and the retry can duplicate. The lookup is
  declared authoritative ("authoritative state comes from the W2 operation
  catalog"), so this is the seam's contract; the W2 read adapters must keep
  read-after-write consistency. Owners W4C/W2.
- O2 W5B `funnel_adapter.py:312-315` — definite non-OK outcomes
  (RATE_LIMITED/TRANSIENT_ERROR/REFUSED/ERROR) release the pending lock as
  `not_found` and the transport may bound-retry; safe only under the stated
  honest-seam rule ("a transport that cannot prove non-creation must return
  UNCERTAIN"). W2-U2 `classify` (held in cohort 2) marks 5xx-on-write
  UNCERTAIN, so the seam holds today. Owners W5B/W2.
- O3 W5C `_persist`'s `blocked-pending` branch (`:526-531`) can never fire for
  W5C's own writes — the adapter opens no checkpoint op anywhere, so its own
  uncertain outcomes leave no lock for the promised reconciliation. Part of
  F1's shape; called out so the repair fixes both. Owner W5C.
- O4 W11A `board_events.py:487` says "Retries do not allocate; only new
  logical events do", but `BoardEventStream._build` allocates a fresh seq on
  every call including a same-key retry (`:558`, asserted by self-check 8
  "never the same seq slot"). Harmless while consumers key-dedupe first; the
  docstring is the wrong half of the pair. Owner W11A.
- O5 Self-check hygiene: W5C uses `tempfile.mktemp` (`:887`, test-only,
  removed in `finally`); W7A (`lane-W7A-U1-`) and W11C (`lane-W11C-U1-`,
  cleanup tuple now covers `-wal/-shm/.env`) clean up their scratch. W5B
  cleans `operator-W5B-U1-` in `finally`. W4C/W11A use `TemporaryDirectory`.
  No residue concerns beyond the mktemp naming. Owners W5C et al.

## C3-6. Completion evidence (reused from TASK-LEDGER.md, per owner order)

Recorded by the integrator and coordinator-verified on the train tree
(2026-10-23T22:46Z): all seven self-checks re-proven — W4C 54 · W5B 58 · W5C
PASS · W7A 86 · W11A 68 · **W11C OK 54 PASS twice consecutively** · W1B 65
assertions (both npage_contract present AND absent) — py_compile sweep clean,
`batch-prep.sh --check` rc=0, and all seven unit heads proven ancestors of
`origin/main` independently by the coordinator. This reviewer did NOT
re-execute any of that per the owner order ("changed-risk reading, not
re-execution"); it read the merged code in full and independently proved
ancestry (C3-2) and each defect path (C3-4) against the tree. No disabled or
missing platform capability is claimed as done anywhere in the seven modules:
every missing route is a capture request, W5C states its readback is
"executor-provided only (outstanding)", and W11C `seam_status()` lists its
integration as outstanding.

## C3-7. Verdict

**Cohort 3 (7 units) changed risk: FAIL** — four findings:
F1 W5C-U1 `website_adapter.py:535-540` (uncertain identity persisted as
confirmed; resume launders the uncertainty);
F2 W5C-U1 `website_adapter.py:337/422-424` (crash gap — resume duplicates
pages; store optional);
F3 W7A-U1 `page_scheduler.py:399-402` (unverified create persisted as
confirmed CREATED);
F4 W11A-U1 `board_events.py:491-498, 558` with `event_outbox.py:274-280`
(cross-run seq re-arm refused as stale_seq — fail-closed, blocks emission).
All other named classes: no finding (Holds per C3-3). Repair belongs to the
owning units in separate repair work — this reviewer changed no product code.
Review commits: this append + `evidence/W12B/W12B-U3.verdict.json` on branch
`w12b-u3/cohort3-review` (based on `fb41a73d3`). Landing remains the
integrator's protected batch process — this reviewer never merges.
