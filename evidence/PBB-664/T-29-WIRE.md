# T-29 wire report — PBB-664

Unit T-29 · lane PBB-664 · branch `pb/PBB-664/t-29` · repo `trevorotts1/openclaw-onboarding`
(`repo_alias: onboarding`) · base `3d7135664326eeb7857252afcad5506c1381c3d5`.

Verdict: **PASS** (build-side). Independent QC is not this document's claim.

## 1. Deliverable identification (STEP 1)

`control/ledger.json` **does not exist in this run root** (confirmed by `find` over
`control/`, `live-ledgers/`, and the project root, maxdepth 3: the only ledger-named
artifacts are `live-ledgers/` and two scratch files under `tmp/`). The ledger entry read
is `live-ledgers/build.json` → `tasks[]` → `id = "T-29"`:

```json
{
  "id": "T-29",
  "title": "Implement human handoff acceptance/escalation and fence",
  "workflow_id": "W-06",
  "repo_alias": "onboarding",
  "requirement_ids": ["R-19"],
  "check_ids": ["C-29"],
  "artifact": "handoff-lifecycle",
  "acceptance": "Context and actual owner acceptance/due/backup; bot paused and resumed by explicit release.",
  "status": "NOT_STARTED",
  "candidate_sha": null,
  "base_sha": null
}
```

`ledger_owned_paths`: **absent from the ledger entry**. Owned paths are therefore derived
from the merged commits, not assumed from the unit id:

| commit | what it added |
|---|---|
| `21f9be77a258debb382c093e39b420b54a199693` feat(handoff) | `shared-utils/handoff/handoff.py` (+658), `shared-utils/handoff/tests/test_handoff.py` (+522) |
| `a9725fcdbc8bbf5b9acf22de2546cce4f029227f` fix(handoff) (PBB-138) | `shared-utils/handoff/handoff.py` (+64/-24), `shared-utils/handoff/tests/test_handoff.py` (+165), `38-conversational-ai-system/CHANGELOG.md`, `38-conversational-ai-system/skill-version.txt` |
| `53de3d0b5a0ebbe297d6b3ee308319daf63cd36c` merge into batch | the same two handoff files at their merged content |

Real module filename: **`shared-utils/handoff/handoff.py`** (682 lines, sha256
`d01466a5f674d68e7bb6988cb109d1b6e4c3b536efef46ea8e0b06f94d23ed7a`).
Its suite: **`shared-utils/handoff/tests/test_handoff.py`** (681 lines, 50 test cases).

Ancestry proved, not assumed:

```
git merge-base --is-ancestor 21f9be77a origin/main   -> rc 0
git merge-base --is-ancestor a9725fcdb origin/main   -> rc 0
git merge-base --is-ancestor 53de3d0b5 origin/main   -> rc 0
```

The ledger row is stale (`status: NOT_STARTED`, `candidate_sha: null`) while three real
commits are on main. Recorded as-is, not interpreted as absent work.

## 2. Instrument proof, both polarities (STEP 2 preamble)

Scanner: `scratch/lanes/PBB-664/refscan.py` — Python + `ast`, never a grep. A **real
production reference** is one of:
* `import` — an AST-confirmed `import <stem>` / `from <stem> import` in a `.py` file that
  is not a test;
* `exec` — the module file's whole path named in a **command** line
  (`python3|python|bash|sh|node|exec|./`) of a workflow or shell file.

Everything else is classified separately (`collision`, `prose`, `test_import`).

**EXPECTED-PASS** — a module known to be wired:

```
python3 -I refscan.py --repo <worktree> --module scripts/ci/required_context_behaviors.py
module=scripts/ci/required_context_behaviors.py present=True sha256=8d7b0714…b398bd95
real_production_refs=1
  REAL  .github/workflows/qc-static.yml:80  (exec)
```

Non-zero, and the site is the line the task named (`qc-static.yml:80`).

```
git merge-base --is-ancestor 76700ba3648f58472ca9c2111dce717a1cf2c5b7 origin/main -> rc 0
git merge-base --is-ancestor 1111111111111111111111111111111111111111 origin/main -> rc 128
```

The rc 0 is a real PASS. The rc 128 is an **instrument abort** (`fatal: Not a valid
commit name`), not a FAIL — the honest FAIL control is the unrelated *existing* commit
below, which `has` a name and is not an ancestor.

**EXPECTED-FAIL** — known-absent path:

```
python3 -I refscan.py --repo <worktree> --module shared-utils/handoff/NO-SUCH.py
MODULE ABSENT: shared-utils/handoff/NO-SUCH.py
real_production_refs=0
```

**COLLISION CONTROL** (the trap: a `*_handoff.py` filename mention that is NOT an import
must read zero). Synthetic repo, three planted decoys plus one output:

```
notes.md          : "post_delivery_handoff.py is a FILENAME. automation_handoff.py too."
producer.py       : import post_delivery_handoff ; from automation_handoff import thing
docstring_only.py : """Docs. Import: from handoff import HandoffStore"""   <- docstring only
handoff.py        : X = 1
--- result ---
real_production_refs=0
collisions_total=2  collisions_production=2  collision_tokens=['automation_handoff.py','post_delivery_handoff.py']
```

Zero real references despite two filename decoys and one docstring-shaped import. Real-repo
cross-check: `06-ghl-install-pages/tools/ghl_id_handoff.py` reads
`real_production_refs=0` (3 test imports, 0 production), so the `*_handoff.py` population
is not being mistaken for call sites.

## 3. Unwired, re-verified with the whole-token scanner (STEP 2)

Measured on the pre-wire tree (`origin/main` + my branch before the wiring commit; my two
files restored to HEAD for the measurement):

```
module=shared-utils/handoff/handoff.py present=True
real_production_refs=0
test_imports=1        ['shared-utils/handoff/tests/test_handoff.py:26']   # `import handoff`
collisions_total=609  collisions_production=475  collision_files=185
prose_mentions=3665   prose_files=1006
```

Breakdown of what the trap counts were:

| category | count | example |
|---|---|---|
| real import-execution sites (production) | **0** | — |
| test-only import | 1 | `tests/test_handoff.py:26` |
| `*_handoff.py` / `*-handoff.*` filename collisions | 609 tokens / 185 files (475 in production paths) | `post_delivery_discovery`-era `aa_handoff.py`, `import_aa_handoff.py`, `ghl_id_handoff.py`, `automation_handoff.py`, `test_handoff.py`, `PA-26-12-crisis-referral-warm-handoff-protocol.md` |
| whole-word prose/path mentions (docs, CHANGELOG, evidence) | 3665 in 1006 files | `evidence/captures/O3.absent-handoff-lifecycle.txt`, `38-conversational-ai-system/CHANGELOG.md` |

`from handoff import HandoffStore` occurs exactly once outside the tests — **inside
`handoff.py`'s own docstring** (`shared-utils/handoff/handoff.py:43`), which the AST scan
does not treat as an import. The audit's 64 / 15 / 1815 figures are consistent with
substring matches over the 609 collision tokens and the 3665 prose mentions; none of them
is a call site.

Conclusion: genuinely unwired. Wiring proceeds.

## 4. The wiring (STEP 3)

### 4.1 Production call site

`shared-utils/reminders/reminder_state_machine.py` — the **existing production send
path**: the cron script `shared-utils/nudge-incomplete-interviews.py` (header: "Run via
cron every 6 hours") constructs `ReminderStateMachine` and calls `machine.send_reminder`
(line 122) / `machine.dispatch_final`; both build the `outbound_gate` evaluator and
dispatch. The chain is `cron -> nudge-incomplete-interviews.py -> ReminderStateMachine ->
outbound_gate.dispatch`, so the new code executes on a real path.

| where | change |
|---|---|
| `shared-utils/reminders/reminder_state_machine.py:77-79` | sys.path: `shared-utils/handoff` added on the import path (not only under direct-script execution) |
| `…:102` | `from handoff import HandoffError, HandoffStore` — **the production reference** |
| `…:426` | `self._handoffs: Optional[HandoffStore] = None` |
| `…:430-438` | `handoffs` property: `HandoffStore(self.identity.db_path)` — same tenant database, two additive tables |
| `…:440-475` | `_gate_evaluator()`: consent evaluator first; if it ALLOWs, `handoffs.gate_decision(tenant, contact)` must also ALLOW. An open handoff row suppresses even when the consent fence flag is clear (`gate_decision` reads rows *and* the fence). An unverifiable contact returns `SUPPRESSED` with `reason: handoff:unavailable` (fail closed, never a guess) |
| `…:1015` (`send_reminder`) | `evaluator = self._gate_evaluator()` |
| `…:1522` (`dispatch_final`) | `evaluator = self._gate_evaluator()` |

Both dispatch sites use it, so a reminder and the reserved final action obey one fence.
No new module, no re-export, no bare import: the returned dict is the value
`outbound_gate.dispatch` consumes on every attempt.

### 4.2 Bite proof (the wiring is not decorative)

`scratch/lanes/PBB-664/bite.py` drives the real `send_reminder` path:

```
CONTROL   status=sent          sender_called=True   reason=
FENCE     status=suppressed    sender_called=False  reason=consent:human_owned
          open_handoff=ho_4d3c887d… state=offered
          consent_fence_paused=False open_rows=1
DECISIVE  status=suppressed    sender_called=False  reason=handoff:human_owned
BITE_PROOF=PASS
```

FENCE is suppressed by the consent gate's queue-time pre-check (the handoff's own
`create()` pauses the consent fence), which is correct but not evidence of *this* wire.
**DECISIVE** isolates it: a handoff row exists with a no-op fence, so the consent
pre-check allows, the dispatch gate is reached, and only `gate_decision()` can suppress.
It does — with the evidence shape this patch emits (`reason: handoff:human_owned`,
`source: handoff`).

### 4.3 CI step (exactly one, no restructuring)

`.github/workflows/qc-static.yml:3221-3240`, appended as the last step of the existing
job:

```yaml
      - name: T-29 human handoff lifecycle suite (explicit name)
        shell: bash
        run: |
          set -uo pipefail
          # … comment block in the file's own style …
          root="${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
          cd "$root" || { echo "✗ cannot cd to the repo root ($root)"; exit 1; }
          t="shared-utils/handoff/tests/test_handoff.py"
          if [ ! -f "$t" ]; then
            echo "✗ T-29 handoff lifecycle suite is absent from this checkout: $t missing. A MISSING suite is a red, not a skip."
            exit 1
          fi
          python3 -I "$t"
          echo "✓ T-29 human handoff lifecycle suite (50 cases) is green"
```

Style matches the file's neighbouring suite steps (root resolution, explicit path,
missing-suite-is-red). No other step was touched. No `${{ }}` expression is interpolated
into the shell, so the step adds no command-injection surface.

## 5. Before → after (STEP 4)

Held constant across both measurements: the known-wired control reads **1**
(`.github/workflows/qc-static.yml:80`), the known-absent control reads **0**.

| measurement | before | after |
|---|---|---|
| real production references to `shared-utils/handoff/handoff.py` | **0** | **1** — `shared-utils/reminders/reminder_state_machine.py:102` (import) |
| of which import-execution sites | 0 | 1 |
| of which CI exec sites | 0 | 0 |
| test-only imports | 1 | 1 (unchanged) |
| collision tokens (excluded from refs) | 609 | 610 (the +1 is my own step naming `test_handoff.py`; correctly classified as a collision, not a reference) |
| collision files | 185 | 186 |
| whole-word prose mentions | 3665 | 3672 |
| workflow files naming the suite | **0** | **1** (`qc-static.yml`) |
| parsed job | `qc-static` / name `QC static invariants` | same |
| steps in that job | **145** | **146** |
| new step index | — | **146** (last) |

Exact after-run:

```
real_production_refs=1
  REAL  shared-utils/reminders/reminder_state_machine.py:102  (import)
test_imports=1 ['shared-utils/handoff/tests/test_handoff.py:26']
collisions_total=610 collisions_production=476 files=186
```

## 6. Inverse control (STEP 5)

The wiring was reverted to `HEAD` in place, measured, then re-applied from a saved patch.

```
git diff > scratch/lanes/PBB-664/wire.patch        # 147 lines
sha256 (wired)  reminder_state_machine.py 5f1c3c340e2ebf7ce7ff2d8b14c2fd131f961bb1d9dd6616f4acc12915e72413
                qc-static.yml             9d34e1b4bf61d4be796b4fdaebabe99a39458c10105e7a52530d7a6a02156a99
git checkout -- <both files>                       # inverse
real_production_refs=0                             # returns to zero
workflow steps=145 ; workflow files naming suite=0 # returns to zero
git apply --check && git apply                     # restore
sha256 (restored) identical, diff of the two files -> SHA256_MATCH=YES
```

Both counters return to their before values and the restore is byte-identical.

## 7. Acceptance (STEP 6)

Ledger acceptance row, verbatim: **"Context and actual owner acceptance/due/backup; bot
paused and resumed by explicit release."**
Requirement R-19, verbatim: **"Owned human handoff, acceptance and escalation"**.
Check C-29 scope, verbatim: **"Context and actual owner acceptance/due/backup; bot paused
and resumed by explicit release."**

| row | verdict | evidence (`file:line`) |
|---|---|---|
| A1 context: no handoff opens without a context reference | PASS | `shared-utils/handoff/tests/test_handoff.py:75` `test_create_requires_a_context_reference` |
| A2 context: summary required | PASS | `…/test_handoff.py:84` `test_create_requires_a_context_summary` |
| A3 due: a due action is required | PASS | `…/test_handoff.py:93` `test_create_requires_a_due_action` |
| A4 due: a due time must be in the future | PASS | `…/test_handoff.py:102` `test_create_requires_a_future_due_time` |
| A5 backup: backup owner must differ | PASS | `…/test_handoff.py:113` `test_create_requires_a_distinct_backup_owner` |
| A6 context and due returned verbatim | PASS | `…/test_handoff.py:120` `test_context_and_due_are_returned_verbatim` |
| A7 assignment is not acceptance | PASS | `…/test_handoff.py:182` `test_assignment_is_not_acceptance` |
| A8 opening the handoff pauses the bot | PASS | `…/test_handoff.py:188` `test_opening_the_handoff_pauses_the_bot` |
| A9 only the offered owner accepts | PASS | `…/test_handoff.py:199` `test_only_the_offered_owner_can_accept` |
| A10 the offered owner becomes the actual owner | PASS | `…/test_handoff.py:212` `test_the_offered_owner_accepts_and_owns_it` |
| A11 acceptance after the due time is refused | PASS | `…/test_handoff.py:219` `test_acceptance_after_the_due_time_is_refused` |
| A12 overdue escalation offers the backup and stays paused | PASS | `…/test_handoff.py:268` `test_overdue_escalation_offers_the_backup_and_stays_paused` |
| A13 backup acceptance requires the escalation | PASS | `…/test_handoff.py:290` `test_backup_acceptance_requires_the_escalation` |
| A14 only the named backup accepts after escalation | PASS | `…/test_handoff.py:299` `test_only_the_named_backup_can_accept_after_escalation` |
| A15 backup acceptance changes the owner and keeps the fence | PASS | `…/test_handoff.py:307` `test_backup_acceptance_changes_the_owner_and_keeps_the_fence` |
| A16 a lapsed (never-accepted) offer reaches the backup | PASS | `…/test_handoff.py:472` `test_an_overdue_unaccepted_offer_is_escalated_to_the_backup` |
| A17 the backup releases after a lapsed offer | PASS | `…/test_handoff.py:497` `test_the_backup_release_resumes_the_bot_after_a_lapsed_offer` |
| A18 resume happens ONLY by explicit release | PASS | `…/test_handoff.py:377` `test_explicit_release_resumes_the_bot` |
| A19 only the actual owner can release | PASS | `…/test_handoff.py:342` `test_only_the_actual_owner_can_release` |
| A20 a timeout never releases the bot | PASS | `…/test_handoff.py:402` `test_timeout_never_releases_the_bot` |
| A21 release requires a reason; double release refused | PASS | `…/test_handoff.py:365`, `:412` |
| A22 one release never unpauses a sibling | PASS | `…/test_handoff.py:575` `test_releasing_one_handoff_keeps_the_fence_while_a_sibling_is_open` |
| B1 the module has a real production call site | PASS | `shared-utils/reminders/reminder_state_machine.py:102` (import) + `:1015`, `:1522`; bite proof §4.2 |
| B2 the suite is executed by a CI workflow naming it | PASS | `.github/workflows/qc-static.yml:3221-3240`, step 146 of job `QC static invariants` |
| C1 committed secrets in the diff | PASS | diff is two files: an import + evaluator + one YAML step; no credential, token or key material |
| C2 writes outside owned paths | PASS | changed: `shared-utils/reminders/reminder_state_machine.py` (the call site the task requires), `.github/workflows/qc-static.yml` (exactly one added step), this report. Nothing else. No ledger, census or DECISIONS edit |
| C3 model/provider/credential or LOCKED value change | PASS | none; no model string, provider pin or credential is touched |
| C4 required CI checks on the exact head | **PENDING (reason: no PR exists, so no check-run rollup can be read on this head; CI cannot be executed from this lane)** | — |
| C5 mergeability against current `origin/main` | PASS | `origin/main` folded into the branch, no conflict; `git rev-list --left-right --count origin/main...HEAD` = `0  2` |
| S1 full repository suite (heavy) | **PENDING (reason: not run; targeted suites only under the claimed permit)** | — |

No self-approval: every row above is measured, and independent QC (`opus-chain`) is still
required by the ledger.

## 8. Tests run (targeted only)

```
python3 -I shared-utils/handoff/tests/test_handoff.py                        Ran 50 tests, OK
python3 -I -m unittest discover -s shared-utils/reminders/tests …            Ran 54 tests, OK
python3 -I shared-utils/reminders/reminder_state_machine.py                  self-check: 21 assertions passed
python3 -I scratch/lanes/PBB-664/bite.py <worktree>                          BITE_PROOF=PASS
```

All five runs repeated **after** the `origin/main` fold (`ef7a70d21`) with the same results.

Memory tier: **`LOCAL_INTERNAL_DISK`** (`control/census.json → memory_tier.tier`).
Permit claimed: **1 heavy permit**, used for the two targeted suites above (T-29 50 cases,
reminders 54 cases). No full-repo suite was run.

## 9. Staleness (STEP 7)

| | sha | note |
|---|---|---|
| measured against | `c994359d6329b6f958c217ee455b40cfb8a0543c` | `origin/main` after `git fetch origin main` |
| base at branch creation | `3d7135664326eeb7857252afcad5506c1381c3d5` | the T-25 merge; still an ancestor of the reported head (`git merge-base --is-ancestor` rc 0) |
| wiring commit | `2d06167b1c2161586241a2109571c9f6f5d85e62` | call site + exactly one CI step |
| freshness fold | `ef7a70d2166cf2ff31d4d9805ee7c8fbf5ee75d1` | `merge: fold origin/main (c994359d6) into the T-29 wire branch (PBB-664)` |
| branch tip | `pb/PBB-664/t-29` (report commits on top of `ef7a70d21`) | read with `git rev-parse origin/pb/PBB-664/t-29` |

True ahead/behind against **current** `origin/main`:

```
git rev-list --left-right --count origin/main...HEAD
0	3
```

behind **0**, ahead **3** (wiring commit, fold merge, and the evidence commits).
The count was `0 2` at the moment the wiring was measured (`ef7a70d21`); the third
commit is this report and touches no production file. The 40 commits that landed on
main between `3d7135664` and `c994359d6` do not touch either changed file
(`git diff --stat 3d7135664..origin/main -- shared-utils/reminders/reminder_state_machine.py
.github/workflows/qc-static.yml` → empty).

Ancestry was checked directly, not inferred: T-29's three commits are ancestors of
`origin/main` (§1). Nothing in this report assumes which units are on main.

No merge to main, no force-push, no ledger/census/DECISIONS edit, no other unit's file
touched.
