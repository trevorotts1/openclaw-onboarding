# T-36 — wire the client-bootstrap engine: call site, CI step, proof

Unit: **PBB-2185** (role BUILD), carrying the PBB-651 T-36 work on branch
`pb/PBB-1961/t-36-wire-carry`. Every number below was measured on this
branch's tree at HEAD `75ac2f5e6468a6a1acb9c3b2660fb9c0d917174b`; the tree it
is compared against is `origin/main` at
`8cb74925ad94c05ce9eb639e7554d02fcd780e20` (the branch's merge base).

This receipt is BUILD evidence only. **It is not self-approval: T-36 needs an
independent QC lane** (author/reviewer separation, QC-AND-REPAIR "Fixed owner
role policy"). Nothing here is a merge or an acceptance decision.

## 1. What this branch changes — the diff it must describe

`git diff --stat origin/main...HEAD`:

| file | insertions | deletions |
|---|---|---|
| `.github/workflows/qc-static.yml` | 17 | 0 |
| `38-conversational-ai-system/scripts/03-create-journey-templates.sh` | 68 | 16 |
| `evidence/PBB-651/T-36-WIRE.md` (this receipt) | 229 | 0 |
| **total** | **314** | **16** |

Three files, nothing else. Four commits sit on top of the merge base, in order:

| commit | subject |
|---|---|
| `bb4d13fd7` | `feat(38): wire the T-36 bootstrap engine into the guided-setup provisioning step (PBB-651)` |
| `fec3f9efb` | `ci(qc-static): run the T-36 bootstrap engine suite by explicit path (PBB-651)` |
| `d1ab69b1c` | `docs(T-36): PBB-651 wiring receipt — call site, CI step, both polarities, inverse control, acceptance rows (PBB-651)` |
| `75ac2f5e6` | `fix(T-36): replace the operator absolute path with <PATH> in the PBB-651 receipt` |

`git rev-list --left-right --count origin/main...HEAD` → `0	4` (0 behind,
4 ahead). The earlier lane's freshness merge `4956257d31477087ded2f84e5b0fe4618fab4ccd`
is **not** in this branch's ancestry (`git merge-base --is-ancestor` rc 1); the
carry re-based the work onto `8cb74925a`, so the receipt no longer claims it.

## 2. Claim ledger — each claim against the file and line that carries it

| # | claim | measured on this tree | verdict |
|---|---|---|---|
| 1 | The script names the engine at its real path | `03-create-journey-templates.sh:30` = `ENGINE="$SKILL_DIR/tools/bootstrap_engine.py"` | VERIFIED |
| 2 | The script fails closed when the engine is absent | `03-create-journey-templates.sh:31` = `[ -f "$ENGINE" ] \|\| { echo … not found"; exit 1; }` | VERIFIED |
| 3 | The script runs an inline-Python heredoc | `03-create-journey-templates.sh:33` = `… python3 - <<'PY'` | VERIFIED |
| 4 | Inline-Python heredocs are the existing style of sibling setup scripts | `05-update-agents-md.sh` runs `python3 - <<'PY'`; `31-generate-workflow-visual.sh` runs `python3 - "$VISUAL_JSON" … <<'PYEOF'` and `SLUG=… python3 - <<'PY_REC'`; `11-run-qc-checklist.sh` runs `python3 - "$OC_CONFIG" <<'PY_BACKEND_EOF'` | VERIFIED |
| 5 | The heredoc imports `BootstrapEngine, ResourceSpec` | `03-create-journey-templates.sh:39` = `from bootstrap_engine import BootstrapEngine, ResourceSpec  # noqa: E402` | VERIFIED |
| 6 | One `ResourceSpec` per provisioned file: 8 × `journey_template` + 1 × `journey_registry`, with `adopt_existing=True` | `03-create-journey-templates.sh:47-65` (TYPES tuple at `:44-45` has 8 names; registry append at `:57-65`; `adopt_existing=True` at `:53` and `:63`) | VERIFIED |
| 7 | The engine is constructed with exactly two permissions | `03-create-journey-templates.sh:67-70`, `permissions=("kind:journey_template", "kind:journey_registry")` at `:69` | VERIFIED |
| 8 | The call site is `report = engine.run(specs)` | `03-create-journey-templates.sh:71` = `report = engine.run(specs)` | VERIFIED |
| 9 | The report is mapped to the existing STATUS lines and the script exits 1 on anything not provisioned | `03-create-journey-templates.sh:73-91`; `sys.exit(1)` at `:91` | VERIFIED |
| 10 | The engine's state file is `<target_root>/.bootstrap-state.json`, lock is `<state_path>.lock` | `bootstrap_engine.py:68` = `DEFAULT_STATE_NAME = ".bootstrap-state.json"`; `:282-285` docstring: state_path defaults to `<target_root>/.bootstrap-state.json`, "the lock is `<state_path>.lock`" | VERIFIED |
| 11 | Exactly one CI step was added, after the T-24 step, and nothing else in the file was touched | `.github/workflows/qc-static.yml:3351-3366` (T-24 step at `:3344`); diff hunk `@@ -3347,6 +3347,23 @@` is additions only (17/0) | VERIFIED |
| 12 | The CI step resolves the root, dry-lists the explicit path, runs it | `qc-static.yml:3355` root resolution, `:3357` `t="38-conversational-ai-system/tools/tests/test_bootstrap_engine.py"`, `:3367`-adjacent `ls -l "$t"` at `:3364`, `python3 "$t"` at `:3365` | VERIFIED |
| 13 | Step count and step position | `qc-static.yml` step rows (`^      - name:`) 163 on `origin/main` → **164** on this branch; the T-36 step is **one-based 154 / zero-based 153**, name `T-36 bootstrap engine suite (explicit path)`, `shell: bash` | VERIFIED |
| 14 | Workflow files in the repo | `.github/workflows` holds **67** files on both `origin/main` and this branch; **1** names T-36's suite (`qc-static.yml`) | VERIFIED |
| 15 | Production references to the literal `bootstrap_engine.py` | this branch, tracked tree (14,058 files): **PRODUCTION 2** — `03-create-journey-templates.sh` (1, `:30`), `qc-static.yml` (1, `:3357`, inside the suite path). Classes: SELF 2 (engine), TEST 4 (suite), CHANGELOG 5, EVIDENCE 38 across the 11 other evidence files (this receipt cites the literal too and is not counted) | VERIFIED |
| 16 | Production references on `origin/main` | **0.** Only three files differ from `origin/main`, and the two that carry the literal are the ones this diff adds it to (`origin/main` versions of both files hold 0 occurrences; the receipt is new); every other carrier is byte-identical to `origin/main` | VERIFIED (derived, exact) |
| 17 | Expected-PASS control is non-zero on the same instrument | literal `required_context_behaviors.py` → **PRODUCTION 1** (`.github/workflows/qc-static.yml:80`), SELF 2, TEST 2, CHANGELOG 1, EVIDENCE 2 on `origin/main` | VERIFIED |
| 18 | The known-absent control returns zero | no file carries `zzz_no_such_module_651.py` | VERIFIED |
| 19 | Install step 03 is part of the guided setup and is idempotent | `38-conversational-ai-system/INSTALL.md:37` "## Install order (run the scripts in this order; each is idempotent)"; `INSTALL.md:45` `./03-create-journey-templates.sh     # Step 9.28 customer journey templates` | VERIFIED |
| 20 | `origin/main` version provisioned 8 templates + registry with raw `cp` | `origin/main` script (42 lines) loops over the same 8 type names and `cp`s `journey.md`, then `cp`s `registry.md`; 0 occurrences of `bootstrap_engine.py` | VERIFIED |
| 21 | Engine symbols cited by the frozen rows | `bootstrap_engine.py:427` `def discover`, `:460` `def plan` ("Pure diff" at `:461`), `:562` `def run`, `:79` `REASON_OWNER_HANDOFF`, `:543-549` block/handoff `Step`, `:96` `TRAFFIC_AUTHORIZED = False`, `:26-29` write-ahead receipt doctrine, `:41-42` no network/subprocess/scheduler, `:615-623` receipt written before artifact | VERIFIED |
| 22 | T-36's suite has 35 tests and passes | `python3 -I 38-conversational-ai-system/tools/tests/test_bootstrap_engine.py` → `Ran 35 tests … OK`, rc 0 | VERIFIED |
| 23 | The frozen acceptance rows are verbatim from the spec TODO | `<RUN-ROOT>/TODO.md:569` heading, `:577` integration requirements, `:579` output, `:581` acceptance, `:583` requirements — all five match the rows below | VERIFIED |
| 24 | The repo checkout itself contains no `TODO.md` holding those rows | the checkout's three `*TODO.md` files are `project-prds/anthology-engine/TODO.md`, `project-prds/podcast-engine/TODO.md` and `QUALITY-CONTROL/book-writer-review-20260824/CHECKLIST-and-TODO.md`; none contains the T-36 heading | VERIFIED (so the row source is the run-root spec, not a repo file) |

### Claims the earlier revision made that this revision does **not** repeat

These were not reproducible and are withdrawn rather than restated:

- The CI step line range `qc-static.yml:3221-3236` — the step is at **3351-3366**.
- `qc-static.yml` sha256 `8b6dd53c…` — this tree's file hashes **`fdda15f56e0926aa0fe6e37b4d11d8d03a3e304f1182e9fcc17f5d3890ce23f7`**.
- Step counts 145 → 146 and index 145/146 — measured **163 → 164**, index **153/154**.
- "66 workflow files" — measured **67** on both sides.
- "13,818 files scanned / 3,530 .py files" and per-class counts "SELF 2, TEST 4, CHANGELOG 5, EVIDENCE 37 across 10 files" at `de85ac2f0` — that tree is not this branch's base. This branch: **14,058 files / 3,657 .py**; the literal's class counts are as in claim 15.
- "0 behind / 3 ahead … 2 wiring commits + 1 real merge commit" — measured **0 behind / 4 ahead**, and the merge commit is not an ancestor (see section 1).
- The scratch instruments `scratch/lanes/PBB-651/{count_refs,ci_proof,scan_imports}.py` and the sandbox transcript with sha256 `1fb0877…` — **not present in the run root or this tree**, so nothing here depends on them. The measurements above were re-derived with scripts written into `tmp/PBB-2185/` (`verify.py`, `sandbox_check.py`, `idem_check.py`, `before_after.py`) and the sandbox runs in section 4.
- "Memory tier GREEN, 9 heavy permits" — a lane-bookkeeping statement, not a property of this tree; dropped.

## 3. The wiring, as it behaves

`03-create-journey-templates.sh` is install step 03 of the guided setup. Before
this branch it copied the 8 journey templates plus `registry.md` with raw `cp`
and left no record. After it, provisioning goes through the engine: only
permitted, absent resources are created, an object the engine does not own is
never overwritten, and a step receipt lands in `<DST>/.bootstrap-state.json`
before each artifact.

It is a call (`:71`), not a re-export and not a test. The AST instrument the
earlier revision used could not see it (the caller is inline Python inside a
shell entry point), which is why the behavioural evidence below carries the
claim.

## 4. Test evidence produced for this receipt

All runs use the branch worktree, a throwaway sandbox at
`tmp/PBB-2185/sandbox/master` as `MASTER_FILES_DIR`, and `python3 -I`.

| check | result |
|---|---|
| first run of install step 03 | rc 0, 9 `installed` lines |
| provisioned bytes vs `templates/journey-templates/` | 9/9 byte-identical, `content-diff parity breaks: []` |
| new artifacts | `.bootstrap-state.json` (2,278 bytes, 9 receipts, schema `skill38.bootstrap_state.v1`) + `.bootstrap-state.json.lock` |
| third run, no edits | rc 0, 9 × "already exists — preserved", state file sha256 unchanged (`fa4425ce…`) — a true no-op |
| hand-edited `coach/journey.md`, then run | rc 0, that line preserved, file sha256 identical before and after (`9fe00ffe…`) — an unowned object is never overwritten |
| `bash -n 03-create-journey-templates.sh` | rc 0 |
| `qc-config-schema-safety.sh` (repo's install-script config-key gate) | `RESULT: PASS — no config-invalidating writes and no jq-1.7-invalid programs in the install scripts.` |
| T-36 suite | `Ran 35 tests … OK`, rc 0 |

Not run, and not claimed: full repository suite, build, package, install, live
proof.

## 5. T-36 frozen acceptance rows (verbatim, `<RUN-ROOT>/TODO.md:569-583`)

| frozen row (verbatim) | source | mark | evidence |
|---|---|---|---|
| `## T-36 — Implement idempotent guided setup, permitted provisioning and resume` | TODO.md:569 | PASS | module `38-conversational-ai-system/tools/bootstrap_engine.py:2-4`; suite `…/tools/tests/test_bootstrap_engine.py` 35 tests OK |
| `Output: \`client-bootstrap-engine\`.` | TODO.md:579 | PASS | `bootstrap_engine.py:1` (module present on `origin/main`; now wired at `03-create-journey-templates.sh:71`) |
| `Acceptance: Discover/reuse supported objects;` | TODO.md:581 | PASS | `bootstrap_engine.py:427` `discover()`; `:543-549` reuse/adopt path; suite discover/reuse cases |
| `scoped diff/provision/` | TODO.md:581 | PASS | `bootstrap_engine.py:460` `plan()` "Pure diff. Never creates, never writes" (`:461`); `:562` `run()` executes; provisioning proven in section 4 (9 files) |
| `owner auth handoff;` | TODO.md:581 | PASS | `bootstrap_engine.py:79` `REASON_OWNER_HANDOFF`; `:543-549` unowned matching object blocks with the handoff reason |
| `step receipts` | TODO.md:581 | PASS | `bootstrap_engine.py:26-29` doctrine; `:615-623` write-ahead receipt before artifact; live `.bootstrap-state.json` written by install step 03 |
| `and no traffic until authorized.` | TODO.md:581 | PASS | `bootstrap_engine.py:96` `TRAFFIC_AUTHORIZED = False`; `:41-42` no network, no subprocess, no scheduler |
| `Requirements: R-26, R-29. Checks: C-36.` | TODO.md:583 | PENDING (independent QC lane) | C-36 is a QC check, not a builder artifact; not self-approvable |
| `Integration requirements: accepted_exact_candidate, independent_required_checks, compatible_target_lease.` | TODO.md:577 | PENDING (independent QC lane) | no merge, no ledger/census edit, no lease claimed by this lane |
| wiring defect leg: real production call site | this unit's brief | PASS | `03-create-journey-templates.sh:30,33,39,67-71`, behavioural proof in section 4 |
| wiring defect leg: suite wired into CI by explicit path | this unit's brief | PASS | `.github/workflows/qc-static.yml:3351-3366` (1 added step, index 153/154, 163 → 164 steps) |

The spec TODO lives at the run root, not in this checkout (claim 24); the rows
above are quoted from `<RUN-ROOT>/TODO.md` at the lines given.

## 6. Staleness

- Measured against `origin/main` = `8cb74925ad94c05ce9eb639e7554d02fcd780e20`,
  which is this branch's merge base (`git merge-base HEAD origin/main`).
- `git rev-list --left-right --count origin/main...HEAD` → `0	4`.
- No merge commit is claimed or required: the carry re-based the four commits
  directly onto the merge base.

## 7. Defects and limits

- No product defect found in the module or its suite; the defect this unit
  repairs is built-but-unwired.
- The call site is inline Python inside a shell entry point, so an AST scan
  over `.py` files alone reports 0 importers. A QC lane that requires an
  AST-visible `.py` importer should say so against this receipt rather than
  infer a zero.
- `.bootstrap-state.json` and `.bootstrap-state.json.lock` appear in
  `<MASTER_FILES_DIR>/journey-templates/` on real installs. That is T-36's step
  receipt contract; the provisioned template bytes are unchanged (section 4).
- Nothing was merged, force-pushed, or written to the ledger, census,
  DECISIONS, or another unit's files by this lane.

## 8. Reproduce

```bash
RUN="<RUN-ROOT>"
WT="$RUN/worktrees/PBB-2185-t-36-wire-carry"
cd "$WT"
git rev-list --left-right --count origin/main...HEAD
git diff --stat origin/main...HEAD
S="$RUN/tmp/PBB-2185/sandbox"
mkdir -p "$S/master"
MASTER_FILES_DIR="$S/master" bash 38-conversational-ai-system/scripts/03-create-journey-templates.sh
MASTER_FILES_DIR="$S/master" bash 38-conversational-ai-system/scripts/03-create-journey-templates.sh
python3 -I 38-conversational-ai-system/tools/tests/test_bootstrap_engine.py
```
