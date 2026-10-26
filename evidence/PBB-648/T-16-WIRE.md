# T-16 WIRE — mobile-first capture and the ONE logical SMS email ask

Unit **T-16** · lane **PBB-648** · branch `pb/PBB-648/t-16-wire`
Base `origin/main` = `3d7135664326eeb7857252afcad5506c1381c3d5` · head `fef417b35c93ed3d4db2531cdf66c6e26534a5c8`
Verdict: **WIRED** — evidence only. This is **not** an approval; it needs an independent QC lane (see §7).

---

## 0. Instrument proof, both polarities (same shell, same tools, same run)

Reference counter: `python3 -I tmp/pbb648/refcount.py <tree> <term> [self-path…]`. It walks every
file, counts matching LINES, and excludes self files, `tests`/`test` directories, `test_*`/`*_test.*`
files, `CHANGELOG`, and `evidence` directories. No grep.

| probe | command | expected | result | rc |
|---|---|---|---|---|
| EXPECTED-PASS, known-wired module | `refcount.py <tree> required_context_behaviors scripts/ci/required_context_behaviors.py` | non-zero | **1 hit / 1 file**, `.github/workflows/qc-static.yml:80` | 0 |
| EXPECTED-PASS, ancestry | `git merge-base --is-ancestor 76700ba3648f58472ca9c2111dce717a1cf2c5b7 origin/main` | ancestor | ancestor | **0** |
| control for ancestry | `git merge-base --is-ancestor origin/main origin/main` | ancestor | ancestor | **0** |
| EXPECTED-FAIL, absent path | `refcount.py <tree> zzz_no_such_module_pbb648` | zero | **0 hits / 0 files**, 9,676 files scanned | 0 |
| EXPECTED-FAIL, unrelated sha | `git merge-base --is-ancestor dc5c25aa598d8386f88c0737a8bef3c3d6eb1ff1 origin/main` | non-ancestor | non-ancestor (object exists) | **1** |

`127`/`128` were never observed. The expected-PASS control is non-zero, so a zero from this counter
is a reading, not a broken probe.

## 1. Re-verified UNWIRED (Step 1)

```
$ python3 -I tmp/pbb648/refcount.py tmp/pbb648/before-full progressive_capture shared-utils/capture/progressive_capture.py
TERM 'progressive_capture'  hits=0  files=0  scanned=9676
  excluded={'changelog': 79, 'test': 186, 'test-file': 584, 'binary/undecodable': 206,
            'tests': 2678, 'evidence': 616, 'self': 1}
$ python3 -I tmp/pbb648/refcount.py tmp/pbb648/before-full plan_capture shared-utils/capture/progressive_capture.py
TERM 'plan_capture'  hits=0  files=0  scanned=9676
```

`tmp/pbb648/before-full` is a full `git archive origin/main | tar -x` of the measured sha (13,824
files). Controls in the same instrument at the same sha: `required_context_behaviors` = 1 file
(live), `zzz_no_such_module_pbb648` = 0. **Zero is confirmed: the module was built and unwired.**

## 2. The wiring added (Step 2)

**Call site — existing production entry point: `shared-utils/reminders/reminder_state_machine.py`**
(the module that owns the shared reminder/ask send path for a collection sequence; its production
consumer is `shared-utils/nudge-incomplete-interviews.py`, whose real scan path is pinned by
`shared-utils/reminders/tests/test_reminder_wiring.py`).

| what | location |
|---|---|
| T-16 import block | `shared-utils/reminders/reminder_state_machine.py:108-122` (`from capture.progressive_capture import …` at :115) |
| delegated ask-field helper | `:201-215` (`capture_ask_field`; a pass is not a capture question) |
| production call site | `:899` `send_reminder`; new capture context params `:908-912`; `plan = plan_capture(` at **`:953`** |
| policy refusal | `:959` `capture_ask_refused` event, returns `not_due` with the policy's own reason |
| policy acceptance | `:964` `capture_ask_planned` event carrying `field` + `capture_state` |
| self-check proof (real execution) | `:1893-1938` |

Behaviour, on a real path, no re-export and no test-only surface: a due reminder that is given the
person's known fields carries **only** the ask `plan_capture` permits. When the policy permits none
— email already known (pass-only), a field refusal, an exhausted ask budget, or a stop — the slot
**does not send**, and the result names the policy's reason (e.g. `email_known_pass_only`). The
decision is written to the sequence event trail, so the caller renders the field the policy named
instead of restating it. This module owns WHEN; T-16 owns WHAT.

**CI — exactly one added step**, appended, no other step restructured:
`.github/workflows/qc-static.yml:3220-3243`, explicit path `t="shared-utils/capture/tests/test_progressive_capture.py"` at `:3231`.
Style matches the T-22/T-09 steps: resolve the root, SKIP loudly if the fixture is absent (never a
silent pass), `ls -l`, then `python3 "$t"`.

Diff: **2 files, +141/−1** (plus this report). No version marker, CHANGELOG, ledger, census or
decision file touched.

## 3. Proven to bite (Step 3)

Same instrument, same run, controls held constant.

| measure | before (`origin/main` 3d7135664) | after (candidate) |
|---|---|---|
| `progressive_capture` production refs | **0 hits / 0 files** | **3 hits / 2 files** (`.github/workflows/qc-static.yml` ×2, `shared-utils/reminders/reminder_state_machine.py:115`) |
| `plan_capture` production refs | **0 hits / 0 files** | **8 hits / 2 files** (7 in the host incl. the call at `:953`) |
| control `required_context_behaviors` | 1 hit / 1 file | 1 hit / 1 file |
| control `zzz_no_such_module_pbb648` | 0 | 0 |
| workflow files naming the suite (of 66) | **0 / 66** | **1 / 66** (`qc-static.yml`) |
| parsed job | `qc-static` / name `"QC static invariants"` | same job, unchanged |
| parsed step count | **145** | **146** (exactly +1) |
| added step index | — | **145 zero-based** (146th one-based), name `T-16 mobile-first capture + the one logical SMS email ask (suite, explicit path)` |

The added step was extracted from the parsed YAML (Ruby Psych) and executed verbatim against this
worktree: `GITHUB_WORKSPACE=<worktree> bash <step>` → rc 0, `Ran 47 tests … OK`, ending
`✓ T-16 progressive capture + the one logical SMS email ask suite ran and passed`.

## 4. Inverse control (Step 4)

Throwaway revert in the lane worktree (`git checkout origin/main -- <both files>`), counts, restore,
sha256 compare:

| state | `progressive_capture` refs | workflow files naming suite | steps | sha256 |
|---|---|---|---|---|
| candidate | 3 / 2 | 1 / 66 | 146 | qc-static `e94839ae…16e53`, host `48317892…71343` |
| **reverted** | **0 / 0** | **0 / 66** | **145** | — |
| restored | 3 / 2 | 1 / 66 | 146 | **identical** to candidate (both files, byte-for-byte) |

Both counts return to zero, so the counter and the CI measure respond to exactly this wiring and to
nothing else. The restore is sha256-identical; `git status --porcelain` is clean against the commit.

## 5. Acceptance — T-16's frozen rows, verbatim

Frozen sources: `live-ledgers/build.json` tasks line 871; `live-ledgers/checks.json` C-16 / C-F06 /
C-F11; `TODO.md` T-16 block; `ACCEPTANCE-MATRIX.md` R-14/R-16 and the F-06/F-11 fixture lines;
`CHECKLIST.md` R-14/R-16; `DATA-CONTRACTS.md` §7.

> `build.json:871` — `"acceptance": "Single logical ask states, known fields, corrected number/unknown handling; pass-only when email already known."`

> `checks.json:360` (C-16 `scope`, line 352 `"id": "C-16"`) — `"Single logical ask states, known fields, corrected number/unknown handling; pass-only when email already known."`

> `checks.json:1211` (C-F06 `scope`, line 1201 `"id": "C-F06"`) — `"Single logical SMS ask receipt states"`

> `checks.json:1319` (C-F11 `scope`, line 1309 `"id": "C-F11"`) — `"Access failed-step/return/email identity"`

> `TODO.md:259` — `Output: \`progressive-capture-candidate\`.`
> `TODO.md:261` — `Acceptance: Single logical ask states, known fields, corrected number/unknown handling; pass-only when email already known.`
> `TODO.md:263` — `Requirements: R-14, R-16. Checks: C-16, C-F06, C-F11.`

> `ACCEPTANCE-MATRIX.md:35` — `| R-14 | Mobile-first capture and exactly one logical SMS email ask | T-16 T-33 T-41 | C-16 C-33 C-41 C-F06 C-F11 |`
> `ACCEPTANCE-MATRIX.md:39` — `| R-16 | Scoped refusal, opt-out, global stop and human ownership precedence | T-12 T-16 T-17 T-18 | C-12 C-16 C-17 C-18 C-F05 |`
> `ACCEPTANCE-MATRIX.md:101` — `- C-F06 / F-06: Single logical SMS ask receipt states — **UNVERIFIED**.`
> `ACCEPTANCE-MATRIX.md:111` — `- C-F11 / F-11: Access failed-step/return/email identity — **UNVERIFIED**.`

> `CHECKLIST.md:70` — `- [ ] **R-14** Mobile-first capture and exactly one logical SMS email ask`
> `CHECKLIST.md:73` — `  - Checks: C-16, C-33, C-41, C-F06, C-F11`
> `CHECKLIST.md:80` — `- [ ] **R-16** Scoped refusal, opt-out, global stop and human ownership precedence`
> `CHECKLIST.md:83` — `  - Checks: C-12, C-16, C-17, C-18, C-F05`

> `DATA-CONTRACTS.md:39` — `## 7. Capture, refusal and one SMS email ask`
> `DATA-CONTRACTS.md:42` — `One logical SMS email-ask action has queued, dispatching, accepted, failed_not_sent, unknown or suppressed state. Known nonexecution can retry the SAME action after a fresh gate; unknown must reconcile. A corrected number is not a new ask. Email arriving before dispatch suppresses the ask and leaves a separately rendered pass-only intent if needed. Accepted ask is not repeated because the person did not answer. Carrier failure after acceptance is not automatically proven nonexecution.`

| # | frozen row | status | evidence |
|---|---|---|---|
| 1 | `build.json:871` / `checks.json:360` — single logical ask states, known fields, corrected number/unknown handling | **PASS (module + reachability)** | suite `shared-utils/capture/tests/test_progressive_capture.py` 47 tests OK (queued/dispatching/accepted/failed_not_sent/unknown/suppressed, corrected-number retry of the same action, unknown never replayed); reachable from the production send path at `reminder_state_machine.py:953` |
| 2 | same row — pass-only when email already known | **PASS (module + enforced on the host path)** | suite test `test_email_already_known_is_pass_only_never_an_email_ask`; host self-check `reminder_state_machine.py:1927-1938` proves a due slot returns `not_due` / `email_known_pass_only` and nothing is sent |
| 3 | `checks.json:1211` C-F06 — single logical SMS ask receipt states | **PASS (state model)** / **PENDING (live provider receipt)** | state mapping proven in suite (`SmsEmailAsk.state_after`, `view`); no live carrier/provider receipt exists, so the live-receipt half is not claimed |
| 4 | `checks.json:1319` C-F11 — access failed-step/return/email identity | **PENDING (suite not run for the access route; producer blocked)** | `bind_email` is covered in suite, but the failed-step/return half needs T-15's access route, whose receipt is `verdict: BLOCKED` (`control/qc/T-15.ab3f4123ed18294dc13ca2a61304651b779e79e3.json`). Not green. |
| 5 | `ACCEPTANCE-MATRIX.md:35` R-14 row | **PASS (capture half)** | rows 1-3 above; R-14's T-33/T-41 halves belong to other units |
| 6 | `ACCEPTANCE-MATRIX.md:39` R-16 row | **PASS (module-level precedence)** / **PENDING (end-to-end runtime)** | refusal/opt-out/global-stop/human-ownership precedence is exercised by the T-16 and T-17 suites; the live runtime STOP path is `PENDING (no live runtime run)` |
| 7 | `TODO.md:259` output `progressive-capture-candidate` | **PASS (exists and is reachable)** | module on main since `edc20ea1d`; production call site added at `reminder_state_machine.py:953` |

Nothing above is self-approved. Every PASS is a command + a printed result; every unproven half is
`PENDING` with the missing producer or run named.

## 6. Staleness — true counts

Measured with `git rev-list --left-right --count origin/main...HEAD` in this worktree:

- `origin/main` = **`3d7135664326eeb7857252afcad5506c1381c3d5`**
- branch head = **`fef417b35c93ed3d4db2531cdf66c6e26534a5c8`**
- **ahead 2, behind 0** (`0 2`)
- origin/main advanced from `de85ac2f0` to `3d7135664` while this lane worked (T-25 batch merge). It
  was folded in as a **real merge commit** `fef417b35`; `qc-static.yml` and the host file merged with
  **no conflicts** and no resolutions to record. Post-merge suites were re-run (§7).

## 7. Suites, memory tier, permit — and who may judge

Memory tier: **GREEN** (`loop-control/Purple-Billboard-Client-System-Build/memory_sample.json` →
`"tier": "GREEN"`). Permit claimed: **one targeted-suite class only** — the four executions below.
No full-repo suite, no install, no live provider, no heavy build.

| run | command | result |
|---|---|---|
| T-16 suite (candidate, post-merge) | `python3 -I shared-utils/capture/tests/test_progressive_capture.py` | **Ran 47 tests — OK**, rc 0 |
| host self-check | `python3 -I shared-utils/reminders/reminder_state_machine.py` | **27 assertions passed** (was 21; +6 T-16 wiring assertions), rc 0 |
| T-17 regression, post-merge | `python3 -I -m unittest discover -s shared-utils/reminders/tests -t shared-utils/reminders/tests -p 'test_*.py'` | **Ran 54 tests — OK**, rc 0 |
| added CI step, verbatim from parsed YAML | `GITHUB_WORKSPACE=<worktree> bash <step>` | rc 0, `Ran 47 tests — OK` |

Everything wider is `PENDING (no heavy permit)`: full repo suite, install, live Page/SMS provider and
the `openclaw_inbound` runtime path (external to this repo per
`38-conversational-ai-system/launch/conversation-runtime-contract.md`).

**This lane does not approve T-16.** The wiring, the CI step, the counts and the inverse control are
evidence for an independent QC lane on this head. Judgement is theirs.
