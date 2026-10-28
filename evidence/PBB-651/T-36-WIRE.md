# T-36 (PBB-651) — wire the client-bootstrap engine: call site, CI step, proof

Unit: PBB-651 (role BUILD). Task: T-36. Branch: `pb/PBB-651/t-36-wire`.
Base: `de85ac2f0f0f5a09cb30e1af0d2db94eaffb7a62` (origin/main at lane start).
Freshness merge: `4956257d31477087ded2f84e5b0fe4618fab4ccd` merges
origin/main `3d7135664326eeb7857252afcad5506c1381c3d5` (no conflicts).

Verdict on the defect: **BUILT_UNWIRED confirmed, and now wired** — the module
has one real production call site and one CI step that runs its suite by
explicit path. This receipt is BUILD evidence only. **It is not self-approval:
T-36 needs an independent QC lane** (author/reviewer separation, QC-AND-REPAIR
"Fixed owner role policy"). Nothing here is a merge or an acceptance decision.

## Instruments (no grep)

All counts come from AST/text instruments executed with `python3 -I`, never
`grep`:

- `scratch/lanes/PBB-651/count_refs.py <tree> <literal> [self_relpath]`
  (textual literal count, classified SELF / TEST / CHANGELOG / EVIDENCE /
  PRODUCTION; a PRODUCTION hit is any hit in a file that is none of the first
  four classes).
- `scratch/lanes/PBB-651/ci_proof.py <tree> <needle>` (workflow text scan +
  parsed `qc-static.yml` job/step rows).
- `scratch/lanes/PBB-651/scan_imports.py <tree> <modules> <symbols>
  <exclude_prefix>` (AST import-edge / call-site scan over .py files).

Instrument proof, both polarities, on the pristine tree before any edit:

| control | expectation | observed |
|---|---|---|
| known-wired `scripts/ci/required_context_behaviors.py` (runs at `qc-static.yml:80`) | non-zero production refs | **PRODUCTION 1** (`.github/workflows/qc-static.yml`); SELF 2, TEST 2, CHANGELOG 1, EVIDENCE 1 |
| known-absent `zzz_no_such_module_651.py` | zero | **0 in every class** |
| `git merge-base --is-ancestor 76700ba3648f58472ca9c2111dce717a1cf2c5b7 origin/main` | rc 0 | **rc 0** |
| `git merge-base --is-ancestor 06ff3de51385f84ddb6389f55727c49cbe3d6272 origin/main` (real, unmerged) | rc 1 | **rc 1** |

No `127`/`128` abort was observed. The expected-PASS control was non-zero, so
the counter is trustworthy for the zeros it reports below.

## STEP 1 — re-verified unwired at origin/main

```
python3 -I scratch/lanes/PBB-651/count_refs.py <tree> \
  'bootstrap_engine.py' '38-conversational-ai-system/tools/bootstrap_engine.py'
```

At `de85ac2f0f0f5a09cb30e1af0d2db94eaffb7a62` (13,818 files scanned):
**PRODUCTION REFERENCE COUNT: 0**. SELF 2 (the module), TEST 4 (its suite),
CHANGELOG 5, EVIDENCE 37 across 10 evidence files. The secondary literal
`bootstrap_engine` (no extension) is also **PRODUCTION 0**. AST scan over 3,530
.py files: production importers of `bootstrap_engine` = **0**; production call
sites of `BootstrapEngine` = **0** (`ResourceSpec` 1 hit is an unrelated
same-named symbol in skill 23). The reviewer's finding reproduces.

## STEP 2 — the wiring

### Production call site (existing entry point, real path)

`38-conversational-ai-system/scripts/03-create-journey-templates.sh` is install
step 03 of the guided setup (INSTALL.md "Install order ... each is idempotent");
until now it copied the 8 journey templates + registry with raw `cp` and left
no record of what it provisioned.

- `03-create-journey-templates.sh:30` names the engine at its real path
  (`ENGINE="$SKILL_DIR/tools/bootstrap_engine.py"`), `:31` fails closed if it is
  absent.
- `:33` runs `python3 - <<'PY'` (the inline-Python style already used by sibling
  setup scripts 05/11/31), `:39` imports `BootstrapEngine, ResourceSpec` via the
  module's documented stdlib path pattern.
- `:47-65` builds one `ResourceSpec` per provisioned file (8 × kind
  `journey_template` + 1 × kind `journey_registry`) with the template bytes as
  the payload and `adopt_existing=True`.
- `:67-70` constructs the engine with exactly two permissions
  (`kind:journey_template`, `kind:journey_registry`).
- **`:71 report = engine.run(specs)`** — the call executes on every real run of
  install step 03; the engine creates only permitted, absent resources and
  writes a step receipt per step into `<DST>/.bootstrap-state.json`.
- `:73-91` maps the report to the script's existing STATUS lines and exits 1 on
  any skipped/refused/failed/unattempted resource (fail closed).

It is a call, not a re-export, not an import for its own sake, and not a test.

Behaviour parity, measured against the origin/main version of the same script
driven in a separate sandbox with the same inputs:

- old: 9 files provisioned; new: the same 9 files, **all 9 byte-identical**
  (`content-diff parity breaks: []`), same stdout lines.
- new additionally writes `.bootstrap-state.json` (+ `.lock`) — the T-36 step
  receipts; that is the contract, not drift.
- second run: 9 × "already exists — preserved", rc 0, state file
  **byte-identical** (sha256 unchanged) — a true no-op.
- hand-edited `coach/journey.md`: preserved byte-for-byte on the next run
  (sha256 `1fb0877…` before and after), rc 0 — an unowned object is never
  overwritten.
- `bash -n` clean; `qc-config-schema-safety.sh` (the repo's install-script
  config-key gate) PASS.

### CI step (exactly one)

`.github/workflows/qc-static.yml:3221-3236` — one added step, appended after
the existing T-24 step, following the file's existing T-22/T-24 suite-step
style (resolve root, dry-list the explicit path, execute it directly):

```
- name: T-36 bootstrap engine suite (explicit path)
  shell: bash
  run: |
    ... t="38-conversational-ai-system/tools/tests/test_bootstrap_engine.py"
    ... python3 "$t"
```

No other step was touched, reordered, or restructured (17 insertions,
0 deletions in that file for this commit).

## STEP 3 — proof that it bites

Measured against **current** origin/main `3d7135664326eeb7857252afcad5506c1381c3d5`
(full `git archive` extract) vs this branch's merged tree:

| measure | before (origin/main) | after (pb/PBB-651/t-36-wire) | delta |
|---|---|---|---|
| production refs to `bootstrap_engine.py` (count_refs) | **0** | **2** — `03-create-journey-templates.sh` (1), `qc-static.yml` (1, the step naming the suite file `test_bootstrap_engine.py`) | **+2** |
| same instrument, control `required_context_behaviors.py` | 1 | 1 | **0 (held constant)** |
| workflow files naming T-36's suite (66 workflow files) | 0 | 1 (`qc-static.yml`) | **+1** |
| parsed job | `qc-static` | `qc-static` | job count 1 → 1 |
| `qc-static` step count (parsed) | 145 | 146 | **+1 exactly** |
| step hit | none | index 145 zero-based / 146 one-based, name "T-36 bootstrap engine suite (explicit path)", shell bash | — |

The one production hit in `qc-static.yml` is the suite path itself
(`…/tests/test_bootstrap_engine.py` embeds the literal `bootstrap_engine.py`),
so the module-level production count is reported as 2 while the **call-site**
count is 1. AST importers of `bootstrap_engine` remain 0 after wiring because
`scan_imports.py` parses `.py` files only and the call site is inline Python in
a shell entry point; the behavioural evidence above, not the AST count, is what
proves this call executes.

## STEP 4 — inverse control (throwaway copy)

Full `git archive HEAD` extract of the merged tree into a throwaway copy;
reverted only the two wiring files to their origin/main blobs; measured; then
restored from HEAD blobs.

| state | production refs | workflow files naming suite | qc-static steps | control literal |
|---|---|---|---|---|
| wired throwaway | 2 | 1 | 146 | 1 |
| reverted throwaway | **0** | **0** | **145** | 1 (held) |
| restored throwaway | 2 | — | — | — |

Restore sha256, throwaway vs worktree vs HEAD blob (identical):

- `03-create-journey-templates.sh` `76aae437b24b23d8ee9907416d88182ab7e010686ae654e0d95ad704a971e9ec`
- `.github/workflows/qc-static.yml` `8b6dd53c6afc802e66ab9f1b7138295eaa17aeeee0750caa1340206ce8f3861c`

Both counts return to zero on revert and the control is unchanged, so the Step 1
zero was the module's, not the instrument's.

## STEP 5 — T-36 frozen acceptance rows (verbatim, TODO.md:569-583)

| frozen row (verbatim) | source | mark | evidence |
|---|---|---|---|
| `## T-36 — Implement idempotent guided setup, permitted provisioning and resume` | TODO.md:569 | PASS | module `38-conversational-ai-system/tools/bootstrap_engine.py:2-4`; suite `…/tools/tests/test_bootstrap_engine.py` 35 tests OK |
| `Output: \`client-bootstrap-engine\`.` | TODO.md:579 | PASS | `38-conversational-ai-system/tools/bootstrap_engine.py:1` (module present on origin/main; now wired at `03-create-journey-templates.sh:71`) |
| `Acceptance: Discover/reuse supported objects;` | TODO.md:581 | PASS | `bootstrap_engine.py:427` `discover()`; `:543-549` reuse/adopt path; suite `test_bootstrap_engine.py` (discover/reuse cases) |
| `scoped diff/provision/` | TODO.md:581 | PASS | `bootstrap_engine.py:460` `plan()` "Pure diff. Never creates, never writes"; `:562` `run()` executes; provisioning proven in the sandbox run (9 files) |
| `owner auth handoff;` | TODO.md:581 | PASS | `bootstrap_engine.py:79` `REASON_OWNER_HANDOFF`; `:543-549` unowned matching object blocks with the handoff reason |
| `step receipts` | TODO.md:581 | PASS | `bootstrap_engine.py:26-29` doctrine; `:615-623` write-ahead receipt before artifact; live `.bootstrap-state.json` written by install step 03 |
| `and no traffic until authorized.` | TODO.md:581 | PASS | `bootstrap_engine.py:96` `TRAFFIC_AUTHORIZED = False`; `:41-42` no network, no subprocess, no scheduler |
| `Requirements: R-26, R-29. Checks: C-36.` | TODO.md:583 | PENDING (independent QC lane) | C-36 is a QC check, not a builder artifact; not self-approvable |
| `Integration requirements: accepted_exact_candidate, independent_required_checks, compatible_target_lease.` | TODO.md:577 | PENDING (independent QC lane) | no merge, no ledger/census edit, no lease claimed by this lane |
| wiring defect leg: real production call site | this unit's brief (T-28 precedent) | PASS | `03-create-journey-templates.sh:30,33,39,67-71` (call site), behavioural proof above |
| wiring defect leg: suite wired into CI by explicit path | this unit's brief (T-28 precedent) | PASS | `.github/workflows/qc-static.yml:3221-3236` (1 added step, index 145/146, 145 → 146) |

Rows needing a suite/run that cannot be produced here: **PENDING (no heavy
permit)** — full repository suite, build, package, install, live proof. The
targeted T-36 suite was run under the heavy-permit allowance (below).

## STEP 6 — staleness

- Measured against: `origin/main` = `3d7135664326eeb7857252afcad5506c1381c3d5`
  (fetched during this lane; the lane's start base `de85ac2f0…` was 12 commits
  behind it).
- True ahead/behind: **0 behind / 3 ahead** before the evidence commit
  (`git rev-list --left-right --count origin/main...HEAD` → `0  3`), i.e.
  2 wiring commits + 1 real merge commit.
- Freshness merge: `4956257d31477087ded2f84e5b0fe4618fab4ccd` — real MERGE
  commit of `3d7135664`; the merge was automatic (ort) with **no conflicts**
  (the incoming batch touched `qc-static.yml` at a different step, T-25 at line
  877; T-36's step stayed at the end).

## Suite status and permit

Memory tier: **GREEN, 9 heavy permits**. Permit claimed: **one targeted suite
run** for T-36's suite (run twice: pre-wiring and post-merge).

- command: `python3 38-conversational-ai-system/tools/tests/test_bootstrap_engine.py`
  (exactly what the CI step executes), run from the repo root
- pre-wiring: `Ran 35 tests … OK`, rc 0
- post-merge: `Ran 35 tests … OK`, rc 0
- module self-check: `bootstrap_engine.py` `_self_check()` is exercised by the
  suite; the module's own `python3 -I bootstrap_engine.py` self-check is
  unchanged by this lane
- wider runs (full repo suite, install, live): **PENDING (no heavy permit)**

## Defects and limits

- No product defect found in the module or the suite; the only defect is the
  one this unit repairs (built-but-unwired).
- The AST instrument (`.py` only) reports 0 production importers after wiring;
  the call site is inline Python inside a shell entry point, so the textual
  instrument plus the executed-sandbox evidence carry the wiring claim. A QC
  lane that requires an AST-visible `.py` importer should say so against this
  receipt rather than infer a zero.
- `.bootstrap-state.json` (+ `.lock`) is a new artifact in
  `<MASTER_FILES_DIR>/journey-templates/` on real installs. That is T-36's step
  receipt contract; the provisioned template bytes are unchanged.
- Nothing was merged, force-pushed, or written to the ledger, census, DECISIONS,
  or another unit's files.

## Reproduce

```bash
RUN="${RUN_ROOT:?set RUN_ROOT to the Purple-Billboard-Client-System-Build run root}"
WT="$RUN/worktrees/PBB-651"
python3 -I "$RUN/scratch/lanes/PBB-651/count_refs.py" "$WT" 'bootstrap_engine.py' \
  '38-conversational-ai-system/tools/bootstrap_engine.py'
python3 -I "$RUN/scratch/lanes/PBB-651/ci_proof.py" "$WT" \
  '38-conversational-ai-system/tools/tests/test_bootstrap_engine.py'
cd "$WT" && python3 38-conversational-ai-system/tools/tests/test_bootstrap_engine.py
```
