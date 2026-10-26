# C-F03-C-F12-BIND — independent binding of the two contract-trace rows (lane PBB-691)

| Field | Value |
|---|---|
| Unit | PBB-691 (role BUILD). D7 arbiter reserved the **binding** of C-F03 / C-F12 to an agent that did not build them. |
| Rows bound | `live-ledgers/checks.json` → `C-F03` (F-03, admission/crash/unknown send) and `C-F12` (F-12, revision-safe upgrade/rollback) |
| Artefact measured | branch `pb/PBB-686/f03-f12-traces`, head `372c0233bbb4291e89b377295fc4ee95b7e80cd1`, authored by lane PBB-686 (one commit, 3 files, `+368/-0`) |
| Base / live main | `git merge-base origin/main <head>` = `5b3e8005ab2a6526bfe19f7d3bad4f2dbd744a76`; live `origin/main` = `5b3e8005` |
| Remote tip | `git ls-remote origin refs/heads/pb/PBB-686/f03-f12-traces` = `372c0233b` — pushed, **not merged** |
| Worktree used | `/Volumes/.../Purple-Billboard-Client-System-Build/worktrees/PBB-691` (locked, "portable drive"), branch `pb/PBB-691/t-09-bind` at `372c0233b` |
| Model | harness reports `opus-chain[1m]`; spawning harness token is `deepseek-direct`. Both stated, neither invented. Registry native id unavailable (blocker B-11) — none invented. |
| Turn result | Runner re-run green, corruption control red, **2 rows bound, 0 other rows changed, 0 product files touched, 0 receipts written, nothing pushed**. Both bindings **PROVISIONAL** (branch head, not main). |

**I did not build these traces.** PBB-686 authored them and left both rows `UNVERIFIED` on purpose. This lane only measured them and bound them.

## 0. What I verified about the artefact before touching the ledger

| Claim given to me | Measured here | Command |
|---|---|---|
| branch head `372c0233b` | `372c0233bbb4291e89b377295fc4ee95b7e80cd1` | `git rev-parse HEAD` in the lane worktree |
| 3 files, `+368/-0` | `19/0 .github/workflows/qc-static.yml`, `236/0 …/tests/contract_traces_runner.py`, `113/0 fixtures/contract-traces.json`; one commit | `git diff --numstat 5b3e8005b… 372c0233b` |
| fixtures hold 14 cases incl. F-03 and F-12 | 14 cases: `F-03, F-04A..D, F-05A..C, F-06A/B, F-07A, F-08A, F-12, F-12A` | `json.load` of the fixture |
| pushed, not merged | remote ref at the same sha; `merge-base --is-ancestor 372c0233b origin/main` → **rc 1** | `git ls-remote`, `git merge-base --is-ancestor` |

Fixture `sha256 d91fe0983da728980640a86050137fbabaa748a7d3d49b1f5da5b93a2c67eee4` before and after every run below — the real fixture was never modified.

## 1. Instrument controls, both polarities, before any zero was trusted

| Instrument | Polarity | Command | rc | Observed |
|---|---|---|---|---|
| git ancestry | PASS (control) | `git merge-base --is-ancestor 5b3e8005b origin/main` | 0 | the merge-base is on main — the instrument can say yes |
| git ancestry | FAIL (target) | `git merge-base --is-ancestor 372c0233b origin/main` | 1 | the head is **not** on main |
| trace runner | PASS | `python3 -I …/contract_traces_runner.py` (real fixture) | 0 | `14/14 cases matched expected` |
| trace runner | PASS (copy control) | same, `--fixture …/tmp/PBB-691/same-copy.json` | 0 | `14/14` — copying alone does not fail |
| trace runner | FAIL | same, `--fixture …/f03-corrupt.json` | 1 | `13/14` + `FAIL F-03` |
| trace runner | FAIL | same, `--fixture …/f12-corrupt.json` | 1 | `13/14` + `FAIL F-12` |
| trace runner | ABORT | same, `--fixture …/malformed.json` | **2** | `ABORT: cannot read fixture …` |
| trace runner | ABORT | same, `--fixture …/does-not-exist.json` | **2** | `ABORT: … No such file or directory` |
| durable suite (product) | PASS | `python3 -I 38-…/tools/tests/test_durable_processing.py` | 0 | `Ran 26 tests` / `OK` |
| durable suite (product) | FAIL | same file in a throwaway copy, `claim_for_dispatch` `state='queued'` → `state IN ('queued','canceled')` | 1 | `2 FAIL` — `test_canceled_action_cannot_be_dispatched_by_racing_workers`, `test_canceled_is_terminal_and_never_claimable` |
| compat suite (product) | PASS | `python3 -I 38-…/tools/tests/test_compat_guard.py` | 0 | `Ran 25 tests` / `OK` |
| compat suite (product) | FAIL | same file in a throwaway copy, `cas_update` guard `if actual != expected_generation:` → `if False:` | 1 | `3 FAIL` — `test_migration_racing_cas_never_regresses_the_generation`, `test_two_writers_at_one_generation_produce_exactly_one_write`, `test_stale_writer_is_refused_and_writes_nothing` |

`127`/`128` never appeared; every non-zero above is a real `1` or `2` from the runner/unittest, captured with stderr merged.

## 2. Runner re-run, verbatim

```
$ cd worktrees/PBB-691
$ python3 -I 38-conversational-ai-system/tests/contract_traces_runner.py --verbose
PASS F-03: RECONCILE_UNKNOWN_EFFECT_SINGLE_SEND
PASS F-04A: QUARANTINED
PASS F-04B: SUPPRESSED
PASS F-04C: SUPPRESSED
PASS F-04D: SUPPRESSED
PASS F-05A: CHECK_COMMON_GATE_NOT_BYPASS
PASS F-05B: SUPPRESSED
PASS F-05C: SUPPRESSED
PASS F-06A: RECONCILE_SAME_ACTION_NO_NEW_ASK
PASS F-06B: FRESH_GATE_SAME_ACTION
PASS F-07A: ORIGINAL_INDEPENDENT_BONUS_NOT_READY
PASS F-08A: OPENER_ONLY_NO_DRIP
PASS F-12: ROLLBACK_REFUSED_NO_STALE_OVERWRITE
PASS F-12A: CAS_CONFLICT_FORWARD_REPAIR
contract-traces: 14/14 cases matched expected
RC=0
```

Worktree `git status --porcelain` empty after the run (no `__pycache__` left; `PYTHONDONTWRITEBYTECODE=1`).

## 3. Corrupted throwaway copies — the runner bites

Copies written to `…/Purple-Billboard-Client-System-Build/tmp/PBB-691/` (project tmp, never `/tmp`, never inside the repo). One case corrupted per copy; the rest untouched.

| Copy | Corruption | Result |
|---|---|---|
| `same-copy.json` | none (byte copy) | `14/14`, **rc 0** — the copy mechanism is not what fails |
| `f03-corrupt.json` | F-03 `send_result` `UNKNOWN` → `SENT` | `13/14`, **rc 1**, `FAIL F-03: trace outcome != expected / computed='NO_RESEND_ON_RECOVERY' expected='RECONCILE_UNKNOWN_EFFECT_SINGLE_SEND'` |
| `f12-corrupt.json` | F-12 `client_fix_after_upgrade` `true` → `false` | `13/14`, **rc 1**, `FAIL F-12: trace outcome != expected / computed='ROLLBACK_CAS_SAFE' expected='ROLLBACK_REFUSED_NO_STALE_OVERWRITE'` |
| `malformed.json` | `{ this is not json` | `ABORT`, **rc 2** |

**Corrupted copy failed: yes, rc=1 for both corrupted cases.** The real fixture under `worktrees/PBB-691/fixtures/` was not touched (sha256 unchanged, §0).

## 4. The honest limitation the artefact itself states — the trace is contract-level, not product-level

The runner's own docstring, quoted verbatim from the committed file:

> "Scope note (deliberate): this runner executes the CONTRACT RULES, not the shipped product handlers. Binding C-F03 / C-F12 to actual product code is a separate, independently reviewed job. Nothing here marks an acceptance row PASS."

PBB-686's own report says the same: "It does **not** bind F-03/F-12 to the shipped product handlers … That binding is the separate independent job."

So the green 14/14 proves the **fixture and the runner work and bite**; it does **not** prove the shipped handlers implement the contract. To give the binding a real product-level limb at the same head I ran the head's own focused product suites (§1) — 26/26 and 25/25 green, each shown to go red under a one-line semantic mutation. Those suites are the product-level evidence; the new fixture is the contract-level evidence. **Neither is a PASS for T-09's acceptance, and I do not claim one.**

I did not edit, reformat or improve the runner, the fixtures, or any product file — including the one line of each product module I mutated, which was mutated only inside a throwaway copy under `tmp/PBB-691/mut/` and restored byte-identically (`compat_guard.py` copy re-compared to the worktree: identical).

## 5. Evidence IDs used in the binding, defined

These are binding-record anchors (this document), not `live-ledgers/evidence.json` items: registering evidence items or writing a receipt is outside this unit's ownership. Each ID names a measured run above.

| Evidence ID | What it names |
|---|---|
| `E-PBB691-F03-TRACE-RUN` | §2 runner run, F-03 `PASS`, `14/14`, rc 0, at `372c0233b` |
| `E-PBB691-F12-TRACE-RUN` | §2 runner run, F-12 `PASS`, `14/14`, rc 0, at `372c0233b` |
| `E-PBB691-F03-PRODUCT-SUITE` | `test_durable_processing.py` `Ran 26 tests / OK`, rc 0, at `372c0233b` |
| `E-PBB691-F12-PRODUCT-SUITE` | `test_compat_guard.py` `Ran 25 tests / OK`, rc 0, at `372c0233b` |
| `E-PBB691-F03-BITE-CONTROL` | §1 canceled-claimable mutation → `2 FAIL`, rc 1 |
| `E-PBB691-F12-BITE-CONTROL` | §1 disabled stale-generation guard → `3 FAIL`, rc 1 |
| `E-PBB691-BIND-RECORD` | this document |

## 6. The exact `live-ledgers/checks.json` change — two rows, nothing else

File `sha256` before `cb169e2b54516dc16286b156df1368e2626ffc706cba7a1c17485885d5309e52`, after `3c74b1f0797c49e3e3f16d699a5b0aa34d5441f4b81ea77ed5593ae4a76edb24`.

### C-F03 — before (lines 1130-1151)

```json
{
  "id": "C-F03",
  "fixture_id": "F-03",
  "task_ids": ["T-09", "T-10", "T-12"],
  "requirement_ids": ["R-23", "R-24"],
  "scope": "Admission/crash/unknown send",
  "status": "UNVERIFIED",
  "type": "minimal_focused_trace",
  "candidate_sha": null,
  "checker_native_id": null,
  "evidence_ids": [],
  "required": true,
  "required_qc_alias": "opus-chain",
  "different_native_agent_after_repair": true
}
```

(array layout in the file is one element per line; reflowed here only for width)

### C-F03 — after (lines 1130-1162)

```json
{
  "id": "C-F03",
  "fixture_id": "F-03",
  "task_ids": ["T-09", "T-10", "T-12"],
  "requirement_ids": ["R-23", "R-24"],
  "scope": "Admission/crash/unknown send",
  "status": "PENDING",
  "type": "minimal_focused_trace",
  "candidate_sha": "372c0233bbb4291e89b377295fc4ee95b7e80cd1",
  "checker_native_id": "opus-chain/PBB-691-lane",
  "evidence_ids": ["E-PBB691-F03-TRACE-RUN", "E-PBB691-F03-PRODUCT-SUITE",
                    "E-PBB691-F03-BITE-CONTROL", "E-PBB691-BIND-RECORD"],
  "required": true,
  "required_qc_alias": "opus-chain",
  "different_native_agent_after_repair": true,
  "author_native_ids": ["PBB-686"],
  "binding_kind": "PROVISIONAL_BRANCH_HEAD",
  "candidate_merged_to_main": false,
  "binding_limit": "PROVISIONAL BINDING TO AN UNMERGED BRANCH HEAD. The F-03 trace artefact is on branch pb/PBB-686/f03-f12-traces at 372c0233bbb4291e89b377295fc4ee95b7e80cd1 and is NOT on main: git merge-base --is-ancestor 372c0233bbb4291e89b377295fc4ee95b7e80cd1 origin/main returned rc=1. Project precedent binds merged candidates only (C-11 candidate 4e5ffa7ca and C-12 candidate a2d8b3720 are both ancestors of origin/main, rc=0), so this binding is provisional and must be re-bound to the merge commit and independently re-QCed. The fixture trace executes the CONTRACT RULES inside the runner, not the shipped product handlers (the runner docstring says so); the product-level limb measured here is the head's own suite: 38-conversational-ai-system/tools/tests/test_durable_processing.py Ran 26 tests OK rc=0, and the same suite goes 2 FAIL rc=1 under a canceled-claimable mutation of durable_store.claim_for_dispatch. Row status is PENDING, never PASS: T-09 acceptance is reserved for a separate re-QC and T-09 row 6 is still PENDING on CI."
}
```

### C-F12 — before (lines 1329-1349)

```json
{
  "id": "C-F12",
  "fixture_id": "F-12",
  "task_ids": ["T-09", "T-39"],
  "requirement_ids": ["R-24", "R-27"],
  "scope": "Revision-safe upgrade/rollback",
  "status": "UNVERIFIED",
  "type": "minimal_focused_trace",
  "candidate_sha": null,
  "checker_native_id": null,
  "evidence_ids": [],
  "required": true,
  "required_qc_alias": "opus-chain",
  "different_native_agent_after_repair": true
}
```

### C-F12 — after (lines 1340-1371)

```json
{
  "id": "C-F12",
  "fixture_id": "F-12",
  "task_ids": ["T-09", "T-39"],
  "requirement_ids": ["R-24", "R-27"],
  "scope": "Revision-safe upgrade/rollback",
  "status": "PENDING",
  "type": "minimal_focused_trace",
  "candidate_sha": "372c0233bbb4291e89b377295fc4ee95b7e80cd1",
  "checker_native_id": "opus-chain/PBB-691-lane",
  "evidence_ids": ["E-PBB691-F12-TRACE-RUN", "E-PBB691-F12-PRODUCT-SUITE",
                    "E-PBB691-F12-BITE-CONTROL", "E-PBB691-BIND-RECORD"],
  "required": true,
  "required_qc_alias": "opus-chain",
  "different_native_agent_after_repair": true,
  "author_native_ids": ["PBB-686"],
  "binding_kind": "PROVISIONAL_BRANCH_HEAD",
  "candidate_merged_to_main": false,
  "binding_limit": "PROVISIONAL BINDING TO AN UNMERGED BRANCH HEAD. The F-12 trace artefact is on branch pb/PBB-686/f03-f12-traces at 372c0233bbb4291e89b377295fc4ee95b7e80cd1 and is NOT on main: git merge-base --is-ancestor 372c0233bbb4291e89b377295fc4ee95b7e80cd1 origin/main returned rc=1. Project precedent binds merged candidates only (C-11 candidate 4e5ffa7ca and C-12 candidate a2d8b3720 are both ancestors of origin/main, rc=0), so this binding is provisional and must be re-bound to the merge commit and independently re-QCed. The fixture trace executes the CONTRACT RULES inside the runner, not the shipped product handlers (the runner docstring says so); the product-level limb measured here is the head's own suite: 38-conversational-ai-system/tools/tests/test_compat_guard.py Ran 25 tests OK rc=0, and the same suite goes 3 FAIL rc=1 under a disabled stale-generation guard in compat_guard.cas_update. Row status is PENDING, never PASS: T-09 acceptance is reserved for a separate re-QC and T-09 row 6 is still PENDING on CI."
}
```

### Proof that exactly two rows moved

| Check | Result |
|---|---|
| Item count | `70` → `70` |
| Item id list identical | `True` |
| Rows whose serialised object changed | **`n = 2` → `['C-F03', 'C-F12']`** |
| Every other item serialises identically | `True` (68/68) |
| All non-`items` keys identical | `True` (schema_version, package_id, created, implementation_status, documents_are_not_implementation, package_policy_version) |
| Textual `difflib.unified_diff` of the whole file | **2 hunks only**: `@@ -1141,12 +1141,23 @@` (C-F03), `@@ -1339,12 +1350,23 @@` (C-F12) |
| Status counts after | `UNVERIFIED 64, PENDING 2 (mine), PASS 2 (pre-existing C-11/C-12), DEFERRED_AUTH 2` |
| Pre-existing PASS rows still validator-clean | `True` — C-11/C-12 keep `checker_alias: opus-chain`, non-empty resolving evidence, no self-approval; **0 errors** |
| New dangling evidence refs among PASS rows | `0` (no row was made PASS, so no new resolving requirement) |

The before-copy used for this diff is a transient diff fixture at `tmp/PBB-691/checks.before.json`; it is listed in §11 and is not a backup of record — the two "before" blocks above are the restore recipe.

## 7. Merged artefact versus branch head — the binding is PROVISIONAL

**Convention measured, not assumed.** The only two `PASS` check rows in this ledger name candidate shas that are **ancestors of `origin/main`**:

- `C-11` candidate `4e5ffa7ca9db2cacdb1b2f198ca749b0263e3bee` → `git merge-base --is-ancestor … origin/main` **rc 0**
- `C-12` candidate `a2d8b3720440baa9437d1541008077ada268fc40` → **rc 0**

The artefact bound here, `372c0233b`, returns **rc 1** against the same instrument (whose positive control returns rc 0). It is pushed to `refs/heads/pb/PBB-686/f03-f12-traces` and absent from main.

Therefore, stated in the binding itself rather than only here:

> `binding_kind = PROVISIONAL_BRANCH_HEAD`, `candidate_merged_to_main = false`, and `candidate_sha` is the **branch head**, not a merge commit.

The artefact is **not** on main and no field of either row implies that it is. When the branch lands, the binding must be re-pointed at the merge commit and independently re-QCed at the merged digest; this document is not that re-QC.

## 8. What I deliberately did NOT do to T-09

- No T-09 acceptance row is PASS. Both bound rows are `PENDING`, never `PASS`.
- T-09 row 6 (`required CI check C-09`) is untouched and still PENDING: the branch is published only as a feature branch, and the run I made is local. No CI run is claimed, and none is implied.
- The `qc/` receipt for T-09 is untouched. No receipt was written anywhere, in either store.

## 9. `control/ledger.json` does not exist — the ledger is at the loop-control root

Checked, named, not inferred:

- `control/` exists and holds `qc/`, `state/`, `tests/`, `census.json` and a set of `.md` reports, but **no `ledger.json`**: `test -e $LOOP_ROOT/control/ledger.json` → **ABSENT**. Same probe, same answer: `control/checks.json` ABSENT, `control/evidence.json` ABSENT.
- The ledger is `…/loop-control/Purple-Billboard-Client-System-Build/ledger.json` (the loop-control root, sibling of `env.sh`), alongside `census.json`, `DECISIONS.md`, `LEDGER-BINDINGS.json`.
- The live check/evidence files this lane bound are `…/Purple-Billboard-Client-System-Build/live-ledgers/checks.json` and `…/live-ledgers/evidence.json` (portable-drive run root, `$LOOP_ROOT`).

## 10. Scope respected

| Out of bounds | Touched? |
|---|---|
| Any product file (runner, fixtures, `durable_store.py`, `compat_guard.py`, workflow, skills) | **No** — the worktree is clean at `372c0233b`; the two mutations were made only inside `tmp/PBB-691/mut/`, a throwaway copy whose `compat_guard.py` was restored byte-identically |
| `live-ledgers/checks.json` rows other than C-F03 / C-F12 | **No** — proven in §6 (2 of 70) |
| `ledger.json`, `census.json`, `DECISIONS.md` | **No** |
| `live-ledgers/evidence.json`, any receipt (`control/qc/`, `qc/*.json`) | **No** — evidence IDs in §5 are binding-record anchors, stated as such |
| Merge, push, publish, PR, force-push | **No** — the report is committed locally on `pb/PBB-691/t-09-bind` only |
| Helper agents, workflows, background shells | **No** |
| `/tmp` (internal disk) | **Never** — all temp under `$LOOP_ROOT/tmp/PBB-691/` |

## 11. Hygiene and what is still owed

Branch `pb/PBB-691/t-09-bind` holds one commit: this document. Not pushed, not merged, so no worktree removal, no `git branch -d`, no `tmp/` deletion is due — those follow an explicit reconcile that a merge commit is preserved by a keep-ref.

Files this lane wrote:

- `live-ledgers/checks.json` (two rows) — the binding.
- `CONTROL/qc/C-F03-C-F12-BIND.md` (committed) and `lanes/PBB-691-lane/C-F03-C-F12-BIND.md` (copy).
- `tmp/PBB-691/`: `same-copy.json`, `f03-corrupt.json`, `f12-corrupt.json`, `malformed.json`, `durable.log`, `mutA.log`, `mutB.log`, `checks.before.json`, `mut/` (throwaway product copy). All disposable; removal is part of the post-merge hygiene pass.
- Worktree `worktrees/PBB-691` (locked, "portable drive") — must stay until the branch is merged, per `HYGIENE.md`.
