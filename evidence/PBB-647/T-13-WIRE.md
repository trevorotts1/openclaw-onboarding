# T-13 WIRE — build evidence (PASS at build level; independent QC required)

Unit **T-13** — "Implement original direct fulfillment independently" · lane **PBB-647** ·
branch `pb/PBB-647/t-13-wire` · head measured **a169265a8** (this report's commit follows it)
· base **de85ac2f0** (origin/main at start) · freshness base **3d7135664** (origin/main at merge)
· model `opus-chain` · MEMORY tier **GREEN (9 heavy permits)**; one permit claimed for the
targeted single-file stdlib suite runs below. No helpers, no agents, no workflows, no background
shells. No `git grep`/`grep` was used as an instrument: every count below comes from this lane's
own AST/text scanners (`scratch/lanes/PBB-647/count_refs.py`, `scan_imports.py`, `ci_proof.py`).

Verdict: the module now has a real production call site and exactly one CI step. It is **not
self-approved** — an independent QC lane must judge the acceptance rows below.

---

## 0. Instrument proof FIRST, both polarities

Both polarities were run with the same instruments, on the same trees, before any claim.
`127`/`128` are instrument aborts, never facts.

| # | Control | Command (abridged) | Result | Verdict |
|---|---|---|---|---|
| PASS-1 | known-wired module has non-zero production references | `python3 -I count_refs.py <tree> required_context_behaviors scripts/ci/required_context_behaviors.py` | `files=1 occurrences=1` (`.github/workflows/qc-static.yml:80`) | PASS |
| PASS-2 | T-22/T-24 merge commit is on current main | `git merge-base --is-ancestor 76700ba3648f58472ca9c2111dce717a1cf2c5b7 origin/main` | `rc=0` | PASS |
| FAIL-1 | known-absent stem returns zero | `python3 -I count_refs.py <tree> zzz_no_such_module_pbb647` | `files=0 occurrences=0` | FAIL as intended |
| FAIL-2 | a valid commit NOT on main returns 1 | `git merge-base --is-ancestor f9a9e7795b0f2bc61d591319710d5fd2019271db origin/main` (`cat-file -t` = `commit`) | `rc=1` | FAIL as intended |

Note on the empty-tree object: `4b825dc642cb6eb9a060e54bf8d69288fbee4904` is a **tree**, not a
commit, on this git; `merge-base --is-ancestor` returns **128 ("Not a valid commit name")**, which
is an abort, not a fact. The expected-FAIL polarity therefore uses a real unmerged commit above.
The counter's expected-PASS control returns non-zero, so a zero it reports can be trusted.

## 1. STEP 1 — re-verified UNWIRED (no manufactured work)

Counting definition (the reviewer's, re-implemented with no grep): a hit counts as a production
reference iff the referencing file is non-self, non-test, non-CHANGELOG, non-evidence, and is
production surface (`.py .ts .tsx .js .mjs .sh .php` or `.github/workflows/*.yml|*.yaml`).

```
python3 -I count_refs.py <tree> direct_fulfillment 38-conversational-ai-system/tools/direct_fulfillment.py
```

| Tree | Production refs |
|---|---|
| origin/main `de85ac2f0` (before) | **files=0 occurrences=0** |
| origin/main `3d7135664` (merged base) | **files=0 occurrences=0** |

AST instrument (import edges / call sites, 0 parse errors over 3,530 `.py` files):

| Symbol | origin/main `3d7135664` |
|---|---|
| production importers of module `direct_fulfillment` | **0** (test importers: 1) |
| production call sites of `can_continue` | **0** (test: 1) |
| production call sites of `record_delivery_proof` | **0** (test: 1) |
| control: production importers of `durable_store` | 5 (constant across every run) |

So the unit was unwired: the module and its suite existed, nothing production called it.

## 2. STEP 2 — the wiring

### 2a. Real production call site, in an EXISTING production entry point

`38-conversational-ai-system/tools/pb_contracts.py` — the shared contract CLI that already fronts
the outbound-action lifecycle (`dispatch` / `receipt`) — gains six subcommands, each driving
`tools/direct_fulfillment.py` through its public API only:

| Command | Call site | Public API it calls |
|---|---|---|
| `fulfill-basis` | `pb_contracts.py:1310-1321` | `FulfillmentLedger.record_basis` (`:1316`) |
| `fulfill-access` | `pb_contracts.py:1324-1338` | `FulfillmentLedger.record_reader_access` (`:1331`) |
| `fulfill` | `pb_contracts.py:1277-1282` | `direct_fulfillment.fulfill` (`:1281`) |
| `fulfill-resume` | `pb_contracts.py:1285-1291` | `direct_fulfillment.resume` (`:1289`) |
| `fulfill-proof` | `pb_contracts.py:1294-1299` | `direct_fulfillment.record_delivery_proof` (`:1298`) |
| `fulfill-continue` | `pb_contracts.py:1302-1307` | `direct_fulfillment.can_continue` (`:1306`) |

The late import at `pb_contracts.py:1236` (`import direct_fulfillment`) is a call path, not an
import for its own sake: every one of the six commands fails without it. The file's charter ("it
never talks to a provider and never sends anything") stays true — the module sends through the
caller's append-only journal (`JournalTransport`), and the CLI hands it files and prints its
outcome; no provider call is made here. Style follows the file: `sub.add_parser` + `emit()` JSON +
`0 ok / 1 refusal / 2 usage` exit codes. Plugin-free, stdlib only.

End-to-end CLI smoke (local, throwaway inputs under the run root `tmp/`):

```
fulfill-basis            -> ok true
fulfill                  -> sent / accepted        (journal rows: 1)
fulfill (second call)    -> already_satisfied / already_sent   (journal rows still: 1)
fulfill-proof            -> accepted -> delivered  (real receipt, pinned hash + destination)
fulfill-continue         -> continuation_ready, continuation_allowed: true
fulfill-resume           -> nothing_to_do
```

That is a real path: one send, no double send, a truthful receipt, a continuation answer.

### 2b. Exactly ONE added CI step, by explicit path

`.github/workflows/qc-static.yml:3230-3246` — one step block appended after the T-24 pb-contracts
step, in the T-22/T-15 explicit-name pattern (resolve root, DRY-list, absent checkout SKIPs
loudly, `python3 -I`). No other step touched.

```
- name: T-13 direct original fulfillment suite (explicit path)
  shell: bash
  run: |
    ...
    t="38-conversational-ai-system/tools/tests/test_direct_fulfillment.py"
    python3 -I "$t"
    python3 -I 38-conversational-ai-system/tools/direct_fulfillment.py
```

YAML parse (`python3 -I ci_proof.py`): 1 job (`qc-static`), step count **145 -> 146**, the step
naming the suite at **index 146 one-based / 145 zero-based**, `name="T-13 direct original
fulfillment suite (explicit path)"`, `shell=bash`.

## 3. STEP 3 — prove it bites (before -> after, controls constant)

Measured against the merged base **3d7135664** (before = a clean worktree of origin/main) and the
branch head **a169265a8** (after). Same instruments, same inclusion rules.

| Metric | Before | After | Control |
|---|---|---|---|
| production refs to `direct_fulfillment` (stem) | 0 files / 0 occ | **2 files / 6 occ** (`pb_contracts.py:27,1219,1236,1237`; `qc-static.yml:3236,3245`) | `required_context_behaviors` 1 file / 1 occ **constant** |
| AST production importers of module | 0 | **1** (`pb_contracts.py`) | `durable_store` 5 **constant** |
| AST production call sites `can_continue` | 0 | **1** (`pb_contracts.py`) | absent symbol 0 **constant** |
| AST production call sites `record_delivery_proof` | 0 | **1** (`pb_contracts.py`) | absent package 0 **constant** |
| workflow files naming the suite | **0 of 66** | **1 of 66** (`qc-static.yml`) | 66 files both runs |
| qc-static steps | **145** | **146** (delta exactly +1, none removed) | job name `QC static invariants` unchanged |
| step index naming the suite | — | **146 one-based** | — |

## 4. STEP 4 — inverse control

Throwaway copy of the branch head (`git archive HEAD` into `tmp/wt647/inverse-final`), then the two
wiring files restored from `origin/main` blobs — nothing else touched:

| Instrument | Inverse copy | After restoring from HEAD |
|---|---|---|
| production refs `direct_fulfillment` | **0 files / 0 occ** | **2 files / 6 occ** |
| workflow files naming the suite | **0 of 66** | 1 of 66 |
| qc-static steps | **145** | 146 |
| AST importers / call sites | **0 / 0** | 1 / 1 |

Restore verification — `sha256` of the restored inverse files equals both `git show HEAD:` and the
worktree bytes:

| File | sha256 (HEAD == inverse-restored == worktree) |
|---|---|
| `38-conversational-ai-system/tools/pb_contracts.py` | `01c5ce42de1eef7a653cba88…` ✔ all equal |
| `.github/workflows/qc-static.yml` | `81ae6f94ee35b5736f841410…` ✔ all equal |

Both counts return to zero without the wiring and come back with it: the fix is what flips them.

## 5. STEP 5 — acceptance rows (frozen, quoted verbatim)

Source: `live-ledgers/checks.json` (frozen acceptance rows; `candidate_sha` is null in all four).

| Row (file:line) | Scope, verbatim | Build verdict |
|---|---|---|
| **C-13** (`live-ledgers/checks.json:293`, `type=focused_artifact_or_required_ci`) | "Approved accessible immutable resource, correct receipt/continuation/no-known-failure; no dependency on T-15." | **PASS (build level, judged by QC)** — approved+immutable identity `direct_fulfillment.py:118-140`; receipt `:632`; continuation `:427`; resume/no-known-failure `:562`; suite cases `tests/test_direct_fulfillment.py:153,168,204,224,303,339`; no T-15 dependency (imports only `durable_store:59`, `outbound_gate:72`, `reconciliation:80`); the required CI leg is §2b |
| **C-F04** (`live-ledgers/checks.json:1153`, `type=minimal_focused_trace`, fixture F-04) | "Every-send gate STOP/rebind/window" | **PENDING (suite not run)** — no F-04 trace fixture/runner is tracked in this checkout; the suite's consent-stop case (`tests/test_direct_fulfillment.py:277`) covers only part of the clause |
| **C-F07** (`live-ledgers/checks.json:1222`, `type=minimal_focused_trace`, fixture F-07) | "Original gift while bonus unavailable" | **PENDING (suite not run)** — no F-07 trace fixture/runner is tracked here; the no-T-15 import graph and `tests/test_direct_fulfillment.py:327` support it indirectly, which is not the same as running the trace |
| **C-F09** (`live-ledgers/checks.json:1265`, `type=minimal_focused_trace`, fixture F-09) | "Permanent original/host migration" | **PENDING (suite not run)** — no F-09 trace fixture/runner is tracked here; the behavioural case `tests/test_direct_fulfillment.py:303` proves the semantic but is not the F-09 trace |

Nothing above is claimed green on a suite that was not run. **This needs an independent QC lane;
the builder does not approve its own unit.**

## 6. STEP 6 — staleness, true numbers

| Measure | Value |
|---|---|
| base at start | `de85ac2f0` |
| origin/main when re-fetched (before merge) | `3d7135664` — **12 behind, 2 ahead** |
| merge performed | real merge commit `a169265a8` (parents `fcc2a3a29`, `3d7135664`) |
| conflicts | 3, all resolved and recorded: `CHANGELOG.md` (both prepended; this entry kept on top, renumbered `2.0.152 -> 2.0.179` above main's newest `2.0.178`, main's entries preserved in order), `skill-version.txt` (both bumped; resolved `v2.0.179`), `qc-static.yml` (auto-merged; both steps kept) |
| after merge (measured) | behind **0**, ahead **3** against `3d7135664` |
| branch | `pb/PBB-647/t-13-wire` (no force-push, no merge to main) |

## 7. Suite status (MEMORY GREEN — one heavy permit claimed)

| Suite | Result |
|---|---|
| `python3 -I 38-conversational-ai-system/tools/tests/test_direct_fulfillment.py` | **16 tests OK** |
| `python3 -I 38-conversational-ai-system/tools/direct_fulfillment.py` (module self-check) | **OK 8 PASS** |
| `python3 -I 38-conversational-ai-system/tools/tests/test_pb_contracts.py` (regression) | **46 OK (skipped=1)** |
| `bash 38-conversational-ai-system/scripts/qc-pb-contracts.sh` (regression) | **46 OK** |
| `python3 -I 38-conversational-ai-system/tools/tests/test_interactive_owner.py` | **4 failures — pre-existing, controlled**: the same file on a clean `origin/main` `3d7135664` checkout fails **7**; the failures are T-19's bookkeeping locks against numbers already published on main, and the version re-cut moves them from 7 to 4. This change adds none. |
| Full repository suite / other skills / install / build | **PENDING (suite not run)** — not attempted here |

## 8. Limits and hygiene

- No merge to main, no force-push, no ledger / census / DECISIONS edits, no other unit's deliverable
  edited. `pb_contracts.py` is T-08's long-merged CLI and the campaign's established entry-point
  pattern (T-15 extended T-14's CLI the same way); note that lane **PBB-649** is extending
  `pb_contracts.py` concurrently for T-23, so the merge train may need a text resolution there.
- Release bookkeeping follows the repo's own gate (`tests/test_interactive_owner.py`
  `BookkeepingTests`): `CHANGELOG [2.0.179]`, `skill-version.txt v2.0.179`.
- Worktree `worktrees/PBB-647`, branch and `tmp/` artifacts are retained: hygiene cleanup happens
  only after a merged reconcile proves the merge commit is preserved by a keep-ref.
- Temporary inputs live under the run root `tmp/wt647/`; nothing wrote to `/tmp`.
