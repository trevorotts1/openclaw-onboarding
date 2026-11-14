# PD-081 — BUILD REPORT

Unit: **PD-081** — "A web 'Signature' choice does not start a build until the 8 questions are answered"
Lane: FL21 · Repository: trevorotts1/openclaw-onboarding · Branch: `pd/fl21-web-interview`
Builder: deepseek-chain · QC (per ledger): opus-chain, thinking max
Date: 2026-11-13 (Eastern)

Build base: `2af1f5a0b68f3f60645ba8e862fc72e162a50318` (remote head before this unit)
Head: `6fe23dd50dd924ec50f2c658f7ad301525bb9d29`

---

## 1. Spec rows (quoted)

### 1.1 `01-BUILD-SPEC.md` — critical-first table row (line 166)

```
| 45 | 6 | PD-081 | Critical | fixes Critical finding PD-081 | FL21 | logic | opus-chain max | PD-106, PD-001, RD-12 | none |
```

### 1.2 `01-BUILD-SPEC.md` — lane row (line 371)

```
| PD-081 ◆ | Critical | logic | opus-chain max | FL21 | onboarding | 1 | PD-106, PD-001, RD-12 | — |
```

### 1.3 `01-BUILD-SPEC.md` — unit section (line 3569)

```
### PD-081 — A web "Signature" choice does not start a build until the 8 questions are answered

| Field | Value |
|---|---|
| Findings | PD-081 |
| Severity | Critical |
| Builder | deepseek-chain — difficulty logic: a bridge block plus a page label |
| Quality control (finds and fixes) | suggested opus-chain at thinking level max (Critical, concurrency risk); re-check of any repair by a FRESH opus-chain agent at max or above; the orchestrator decides |
| Critical first | yes: fixes Critical finding PD-081 |
| Lane and repository | FL21 · trevorotts1/openclaw-onboarding |
| Wave | 1 |
| Depends on (must be ACCEPTED, that is QC-passed, first) | PD-106, PD-001, RD-12 |
| Held by decision | none |
| Existing tests it breaks and must update | none known in advance; the lane's reading units and the test census name the rest (rule 15) |
| Live-action flag | The page and the hosted worker under `deployed-r2/` are live on Cloudflare. Merging changes the repository only. Deploying the worker or the page is a separate live action that needs Trevor's go; no builder or checker deploys. |
| Acceptance rows the checker must run | A1, A2, A3, A4 |
```

Consolidation amendment (binding, quoted verbatim):

```
Decision D-20 default applies: the 8 questions are asked in chat through the driver. The client-facing label is in `06-DECISIONS-FOR-TREVOR.md`, section "Client-facing wording".
```

Carried-over unit text (quoted verbatim):

```
- **Build unit PD-081 (Critical, Sonnet; lane FL21; default of D-20).** In `_drive_submission_claimed`, after the run record is written and before the board card: when `intake["presentation_type"] == "signature"` and `<run_dir>/working/copy/sp_intake.json` does not exist, call `_ll.mark_blocked` with reason `signature interview not done: the 8 questions have not been asked` and remediation `ask the 8 questions in chat with deck-intake-driver.py --run-dir <RUN_DIR> --signature --sig-next, then delete this submission state file to re-drive`, notify once, return rc 8. In `pages/index.html` (and its byte-identical deployed copy) change the signature option label to `The full Signature Presentation (100+ slides). You will answer 8 more questions in chat after this form.` Acceptance (`test/test_pd081_signature_block.py`): (A1) signature intake, no `sp_intake.json` → rc 8, no board call, no launcher call (stubs record calls); (A2) same with `sp_intake.json` present → proceeds to the board step; (A3) from-scratch intake unaffected; (A4) the two page copies are byte-identical.
```

### 1.4 `02-SWARM-PLAN.md` rows (lines 114, 149, 252)

```
| 6 | PD-063 (FL19, logic), PD-081 (FL21, logic), PD-301 (FL33, logic), PD-300b (FL35, logic) | RD-12, RD-13 |
| FL21 | PD-083 ◇, PD-084 ◇, PD-104 ◇, PD-085 ◇, PD-106 ◇, PD-081 ◆ |
| FL21 | openclaw-onboarding | `pd/fl21-web-interview` | the interview web application: page, hosted worker, bridge and question payload | PD-083 ◇, PD-084 ◇, PD-104 ◇, PD-085 ◇, PD-106 ◇, PD-081 ◆, PD-107, PD-086 [D-19], PD-082a [D-18] |
```

---

## 2. Branch proof before editing

```
$ python3 -I .../scripts/step_gate.py ready --control .../loop-control/pd-fix
{"id": "PD-081", "kind": "build", "lane": "FL21", "branch": "pd/fl21-web-interview", ...}

$ git ls-remote --heads https://github.com/trevorotts1/openclaw-onboarding.git pd/fl21-web-interview main
ebf5c769a2ad5b2582bf2256588095cbef20cfac	refs/heads/main
2af1f5a0b68f3f60645ba8e862fc72e162a50318	refs/heads/pd/fl21-web-interview
```

Branch present (40 chars). Dependencies already on the lane tip:

```
$ git log --oneline -1 2af1f5a0b
2af1f5a0b PD-106: build report with rows, mutation proof and remote-head proof

$ git log --oneline --all --grep='PD-001'
5ff8a5f22 PD-001: qc fix wrong confirm flag in new tests
37fc849c2 PD-001: signature intake always asks the 8 questions; no false success
```

RD-12 is a reading unit (no code of its own). Work done in a private scratch clone on the
portable drive (`.../pd-fix/tmp/PD-081/work.DUFe7C/repo`); no lane clone was touched.

---

## 3. Files changed (hunk attribution)

`git show --numstat HEAD`:

```
24   0  .../intake/interview-app/bridge/intake_bridge.py
1    1  .../intake/interview-app/deployed-r2/public/index.html
1    1  .../intake/interview-app/pages/index.html
1    1  .../intake/interview-app/pages/questions.json
1    1  .../intake/interview-app/schema/intake_fields.js
171  0  .../intake/interview-app/test/test_pd081_signature_block.py
16   0  .../intake/interview-app/test/test_pres008_durable_states.py
```

Attribution:

| Hunk | Belongs to PD-081 | Note |
|---|---|---|
| `bridge/intake_bridge.py` +24 | yes | the signature gate in `_drive_submission_claimed`, inserted after the run-dir record and before `# 2) the board card` |
| `schema/intake_fields.js` 1/1 | yes | the label's SOURCE — the page is generated from this contract |
| `pages/index.html` 1/1 | yes | regenerated by `node tools/gen_ui_questions.mjs` (not hand-edited) |
| `pages/questions.json` 1/1 | yes | same regeneration (the JSON projection) |
| `deployed-r2/public/index.html` 1/1 | yes | `cp pages/index.html deployed-r2/public/index.html` — still byte-identical |
| `test/test_pd081_signature_block.py` +171 | yes | the acceptance test the spec names |
| `test/test_pres008_durable_states.py` +16 | yes | required fix: the gate broke 5 scenarios; fixture now seeds `sp_intake.json` |

No shared file is touched by a sibling unit: `intake_bridge.py` is the FL21 bridge file for
this unit; the page/contract files are the ones the unit names.

---

## 4. Per-row proof (head)

Command: `python3 -I test/test_pd081_signature_block.py` (run from the interview-app dir).
All 4 rows green at head:

```
test_a1_signature_without_sp_intake_blocks_before_the_board ... ok
test_a2_signature_with_sp_intake_proceeds_to_the_board ... ok
test_a3_from_scratch_intake_is_unaffected ... ok
test_a4_the_two_page_copies_are_byte_identical ... ok
Ran 4 tests in 0.163s
OK
```

| Row | Assertion | Head |
|---|---|---|
| A1 | signature, no `sp_intake.json` → rc 8, 0 board calls, 0 launcher calls, ledger `blocked_actionable`, exact reason, 1 notification; re-poll stays blocked with no board call | PASS |
| A2 | same intake with `sp_intake.json` → reaches the board step (1 board call) | PASS |
| A3 | `from_scratch` intake → reaches the board step, no `sp_intake.json` written | PASS |
| A4 | `pages/index.html` == `deployed-r2/public/index.html` byte-for-byte and carries the new label | PASS |

At base (`2af1f5a0b`, production files stashed, same tests in the tree):

```
FAIL: test_a1_signature_without_sp_intake_blocks_before_the_board
FAIL: test_a4_the_two_page_copies_are_byte_identical
Ran 4 tests in 0.301s
FAILED (failures=2)
```

---

## 5. Mutation proof (neutralise → RED → restore → GREEN)

Mutation: `if False and str(intake.get("presentation_type") ...) == "signature":`

```
FAIL: test_a1_signature_without_sp_intake_blocks_before_the_board
AssertionError: 0 != 8 : {'verdict': 'complete', 'state': 'worker_acknowledged',
                          'detail': 'stub worker acknowledged', '_rc': 0}
Ran 4 tests in 0.015s
FAILED (failures=1)
```

The mutation lets the signature intake run straight through to board + launch and report
success — exactly the defect PD-081 fixes. Restored (`grep` shows the plain condition back at
line 612) and re-run:

```
Ran 4 tests in 0.005s
OK
```

---

## 6. Wider affected suite — base vs head

Python, every `*.py` under `test/` and `deployed-r2/test/`, run by file with real output:

| Test file | Base `2af1f5a0b` | Head `6fe23dd50` |
|---|---|---|
| test_email_election_flow.py | OK 11 tests | OK 11 tests |
| test_email_help_contract_agreement.py | OK 3 tests | OK 3 tests |
| test_intake_bridge_dispatch.py | OK 11 tests | OK 11 tests |
| test_intake_writer_run_mode.py | FAILED (failures=1) of 24 | FAILED (failures=1) of 24 |
| test_intake_writer.py | OK 13 tests | OK 13 tests |
| test_operator_contract_handoff.py | rc 0, silent | rc 0, silent |
| test_payload.py | FAILED (failures=3) of 12 | FAILED (failures=3) of 12 |
| test_pd_webapp_pd106_confirm_code.py | OK 4 tests | OK 4 tests |
| **test_pd081_signature_block.py** | **FAILED (failures=2) of 4** | **OK 4 tests** |
| test_pd085_resume_company_id.py | OK 2 tests | OK 2 tests |
| test_pres006_canonical_paths.py | FAILED (failures=2) of 20 | FAILED (failures=2) of 20 |
| test_pres008_durable_states.py | OK 10 tests | OK 10 tests |
| test_pres009_bridge_and_migration.py | OK 13 tests | OK 13 tests |
| test_pres023_bridge_ack.py | OK 7 tests | OK 7 tests |
| test_waiver_decline_flow.py | FAILED (failures=1) of 10 | FAILED (failures=1) of 10 |

The four red files are byte-identical at base and head (not in this commit): the same 7 failing
test cases run at base and at head. They are pre-existing, proven by running them at
`2af1f5a0b`.

Node (`node --test`), same file list:

| Test file | Base | Head |
|---|---|---|
| deployed-r2/test/pres024_deployed_r2.test.mjs | rc 0 | pass 8 / fail 0 |
| deployed-r2/test/test_intake_completeness_canonical.test.mjs | rc 0 | pass 3 / fail 0 |
| deployed-r2/test/test_pd106_confirm_code.mjs | rc 0 | pass 2 / fail 0 |
| deployed-r2/test/test_pd106_paging.mjs | rc 0 | pass 2 / fail 0 |
| deployed-r2/test/test_pres005_worker.mjs | rc 0 | pass 9 / fail 0 |
| test/pres024_env.mjs | rc 0 | pass 1 / fail 0 |
| test/pres024_interview_app.test.mjs | rc 0 | pass 5 / fail 0 |
| test/test_branded_page_session_flow.test.mjs | rc 0 | pass 2 / fail 0 |
| test/test_dept_start_handoff.mjs | **rc 1** | **rc 1 (pass 0 / fail 1)** |
| test/test_pres006_contract.mjs | rc 0 | pass 14 / fail 0 |
| test/test_pres023_worker_authority.mjs | rc 0 | pass 13 / fail 0 |
| test/test_worker.mjs | rc 0 | pass 7 / fail 0 |

`test_dept_start_handoff.mjs` fails identically at base and at head — pre-existing.

---

## 7. Required fix found while proving

`_drive_submission_claimed` is exercised by five `test_pres008_durable_states.py` scenarios
that drive signature intakes. The new gate blocked them (5 failures at head, 10/10 OK at base).
Those scenarios test the durable handoff, not the interview, so the fixture now seeds
`working/copy/sp_intake.json` per driven session (`_seed_sp_intake`), with a docstring pointing
at the gate's own test. Pres008 is 10/10 green at head again.

`test_pres006_contract.mjs` also caught a real mistake during the build: `pages/index.html` is
GENERATED from `schema/intake_fields.js` by `tools/gen_ui_questions.mjs --check`. The label was
therefore changed at its source and the page regenerated, not hand-edited. 14/14 green.

---

## 8. Remote-head proof

```
$ git ls-remote --heads https://github.com/trevorotts1/openclaw-onboarding.git pd/fl21-web-interview
6fe23dd50dd924ec50f2c658f7ad301525bb9d29	refs/heads/pd/fl21-web-interview

$ git rev-parse HEAD
6fe23dd50dd924ec50f2c658f7ad301525bb9d29
```

Fast-forward only (`2af1f5a0b..6fe23dd50`). No rebase, no force-push, nothing pushed to `main`.

---

## 9. Honest unproved

- **The deployed Cloudflare page and worker were not deployed.** The spec's live-action flag is
  explicit: merging changes the repository only; deploying is Trevor's call. Nothing was
  deployed, so the live page still shows the old label until someone deploys.
- **`sp_intake.json` presence is the only signal used**, per the spec. A hand-planted or stale
  file would satisfy the gate; the spec does not ask for content validation, so none was added.
- **The four red Python files and `test_dept_start_handoff.mjs`** are pre-existing and were run
  at base to prove it; this unit does not repair them.
- **`test/test_operator_contract_handoff.py` prints nothing** and exits 0 at both base and head;
  its rc is the only signal recorded here (no per-case count was obtained from it).
