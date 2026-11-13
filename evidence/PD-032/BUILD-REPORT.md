# PD-032 — BUILD REPORT (builder: deepseek-chain)

Unit PD-032 · repo `trevorotts1/openclaw-onboarding` · branch `pd/fl03-question-bank`
Worktree used for the build: scratch copy under the unit TMPDIR, created from the branch head
`5a9743c2d690c7f4c43fdc48898c4fd8048ad1b4`; the lane clone
`/Volumes/mac mini m4/swarm-contract/pd-fix/worktrees/onboarding/FL03` was left clean.

This is a build report, not a verdict. A fresh opus-chain reviewer checks it.

---

## 1. The spec I implemented (quoted in full from `01-BUILD-SPEC.md`, section PD-032)

> ### PD-032 — Tell the client what happens next
>
> | Field | Value |
> |---|---|
> | Findings | PD-032 |
> | Severity | Nice-to-have |
> | Builder | deepseek-chain — difficulty mechanical: one JSON key |
> | Quality control (finds and fixes) | suggested opus-chain at thinking level low (mechanical wording, path or one-file change); re-check of any repair by a FRESH opus-chain agent at medium or above; the orchestrator decides |
> | Critical first | no |
> | Lane and repository | FL03 · trevorotts1/openclaw-onboarding |
> | Wave | 3 |
> | Depends on (must be ACCEPTED, that is QC-passed, first) | PD-014 |
> | Held by decision | none |
> | Existing tests it breaks and must update | none known in advance; the lane's reading units and the test census name the rest (rule 15) |
> | Live-action flag | none: files and stubbed tests only |
> | Acceptance rows the checker must run | A1 |
>
> **Read first — consolidation amendments (binding; they override the carried-over text below wherever the two differ):**
>
> Moved ahead of PD-013 so it is not held by decision D-2. It adds the key under `frontdoor` and touches nothing else.
>
> **Carried-over unit text (from `01-BUILD-SPEC.md`, section PD-032; ids, decisions and lanes already converted to final):**
>
> - **Change:** in `conversation_templates.json` add under `frontdoor` the key `"after_intake"` with value: `That is everything I need. Here is what happens now: I research your topic, write the slides, and then send you 3 style samples to pick from (A, B or C). You do not need to do anything until you see those samples. I will message you at each big step and the moment anything needs you.`
> - **Acceptance:** file parses; key present; no other key changed (compare the parsed object before and after, ignoring the new key).

---

## 2. Files changed (commit `e7c631fd5e182a9c08a1a17dc5525ce9d3009434`)

```
1	0	23-ai-workforce-blueprint/templates/role-library/presentations/scripts/conversation_templates.json
104	0	23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd_bank_032_after_intake.py
```

The JSON diff is exactly one added line, inserted as the first key of `frontdoor`:

```diff
@@ -33,6 +33,7 @@
     "frontdoor": {
+        "after_intake": "That is everything I need. Here is what happens now: I research your topic, write the slides, and then send you 3 style samples to pick from (A, B or C). You do not need to do anything until you see those samples. I will message you at each big step and the moment anything needs you.",
         "greeting": "Hello, and welcome. I help get presentations started here. ...",
```

No other file was touched. `update-skills.sh`, `universal-sops/_content-manifest.json` and `install.sh` were not opened for writing.

---

## 3. Acceptance row A1 — PROVEN

Row: file parses; key present; no other key changed (parsed object before vs after, ignoring the new key).

Proof method: parse the **committed base blob** (`git show HEAD:...` taken at the pre-change commit
`5a9743c2d690c7f4c43fdc48898c4fd8048ad1b4`) and the changed working file, remove only
`frontdoor.after_intake` from the latter, canonically serialise both (`sort_keys`, `separators=(',',':')`)
and compare SHA-256.

Command (run in the scratch worktree, base = `HEAD` before the build commit):

```
python3 - "$P" <<'PY'
base=json.loads(subprocess.check_output(['git','show',f'HEAD:{p}']).decode())
head=json.loads(open(p,encoding='utf-8').read())
h=lambda o: hashlib.sha256(json.dumps(o,sort_keys=True,separators=(',',':')).encode()).hexdigest()
h2=copy.deepcopy(head); del h2['frontdoor']['after_intake']
PY
```

Real output:

```
base object sha (HEAD blob)   : ea363d3c9f7030c4f3f0981616dca14ce72b4be755d1b10488966d27a96b2359
head minus after_intake sha   : ea363d3c9f7030c4f3f0981616dca14ce72b4be755d1b10488966d27a96b2359
NO OTHER KEY CHANGED          : True
base frontdoor keys           : ['greeting', 'handoff', 'not_qualified', 'qualification']
head frontdoor keys           : ['after_intake', 'greeting', 'handoff', 'not_qualified', 'qualification']
exactly one added key         : {'after_intake'}
exactly one added top-level   : []
```

Exact-string match and parse check on the same file:

```
PARSES: yes
KEY PRESENT: True
VALUE:
That is everything I need. Here is what happens now: I research your topic, write the slides, and then send you 3 style samples to pick from (A, B or C). You do not need to do anything until you see those samples. I will message you at each big step and the moment anything needs you.

EXACT STRING MATCH: True
```

Row holds at commit `e7c631fd5e182a9c08a1a17dc5525ce9d3009434` (the PD-032 build commit; base
`5a9743c2d690c7f4c43fdc48898c4fd8048ad1b4` does not contain the key — see §5 BEFORE).

### Permanent check left behind

`23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd_bank_032_after_intake.py`
(104 lines, no framework, never skips) pins: the file parses; `after_intake` is a string equal to the
exact spec sentence; no pre-existing `frontdoor` key is removed; the top-level key set is unchanged.

It deliberately does **not** pin the whole file, so sibling units may edit other keys without tripping it.

---

## 4. Failure proof — mutations that turn the check RED and are reverted

The check must be able to fail. Four mutations were applied to the real artefact in the scratch
worktree, the test run, then the good copy restored from a saved copy (`good-conversation_templates.json`)
and the test re-run GREEN. Head SHA of the artefact stayed `5720fcf15001838d9d7b0ee906bdf1fc920b0b055765876be775a4f273dba824`
before and after the mutation round.

| # | Mutation | Result | Exit |
|---|---|---|---|
| M1 | delete `frontdoor.after_intake` | `FAIL test_after_intake_present_and_exact: frontdoor.after_intake is missing` | 1 |
| M2 | reword `3 style samples` → `two style samples` | `FAIL ... after_intake wording drifted: '... two style samples ...'` | 1 |
| M3 | delete sibling key `frontdoor.handoff` | `FAIL test_no_frontdoor_key_removed: frontdoor lost key(s): ['handoff']` | 1 |
| M4 | add stray top-level key `"stray"` | `FAIL test_no_top_level_key_added_or_removed: top-level keys changed: added=['stray'] removed=[]` | 1 |
| — | restore good copy | 4 PASS, `0 failure(s)` | 0 |

**The control itself was checked, and one earlier attempt was discarded as invalid.** The first
mutation round restored with `git checkout -- <file>`, which reverts to the pre-change commit — so
M2–M4 ran against a file with no `after_intake` and M2 aborted with `KeyError: 'after_intake'`
instead of testing what it claimed. That round proves nothing and is not counted. The table above is
the re-run with copy-based restore; each mutation's assertion message names the mutation that caused it.

---

## 5. BEFORE / AFTER pair on the artefact

| | `frontdoor` keys | `after_intake` present | file parse |
|---|---|---|---|
| BEFORE (`5a9743c2d`) | `greeting, handoff, not_qualified, qualification` | `False` | ok |
| AFTER (`e7c631fd`) | `after_intake, greeting, handoff, not_qualified, qualification` | `True` | ok |

---

## 6. Tests by id — base and head

Same command in both trees, pytest 9.0.3:

```
python3 -m pytest test_item33b_conversation_layer.py test_pd_bank_014_declined_reason_flags.py [-v]
```

### Base — clean lane clone at `5a9743c2d690c7f4c43fdc48898c4fd8048ad1b4`

`1 failed, 23 passed` (exit 1)

```
test_item33b_conversation_layer.py::test_client_action_park_produces_a_plain_words_brief PASSED
test_item33b_conversation_layer.py::test_other_classes_are_silent_to_the_client PASSED
test_item33b_conversation_layer.py::test_fallback_notify_when_the_layer_is_unavailable PASSED
test_item33b_conversation_layer.py::test_park_seam_reports_unavailable_without_a_park_record FAILED
test_item33b_conversation_layer.py::test_qualified_style_pick_records_once_and_dispatches_once PASSED
test_item33b_conversation_layer.py::test_unqualified_style_pick_produces_no_signal PASSED
test_item33b_conversation_layer.py::test_style_pick_against_the_wrong_park_is_a_mismatch PASSED
test_item33b_conversation_layer.py::test_reply_to_an_unparked_run_produces_no_signal PASSED
test_item33b_conversation_layer.py::test_qualified_plan_answer_locks_and_is_the_signal PASSED
test_item33b_conversation_layer.py::test_unknown_plan_tier_is_refused_before_any_write PASSED
test_item33b_conversation_layer.py::test_plan_decline_locks_the_decline_and_resumes_nothing PASSED
test_item33b_conversation_layer.py::test_a_kind_with_no_sanctioned_writer_is_escalated_not_routed PASSED
test_item33b_conversation_layer.py::test_a_reply_without_a_message_id_is_refused PASSED
test_item33b_conversation_layer.py::test_frontdoor_handoff_carries_no_answers_and_no_intake_state PASSED
test_item33b_conversation_layer.py::test_handoff_validator_refuses_answer_shaped_keys PASSED
test_item33b_conversation_layer.py::test_delivery_brief_renders_the_bounded_sequence PASSED
test_item33b_conversation_layer.py::test_delivery_brief_refuses_an_unverified_delivery PASSED
test_item33b_conversation_layer.py::test_skill38_receipt_record_lands_validated PASSED
test_item33b_conversation_layer.py::test_doctrine_text_and_code_agree PASSED
test_pd_bank_014_declined_reason_flags.py::test_default_no_reasons_are_optional_in_both_bank_shapes PASSED
test_pd_bank_014_declined_reason_flags.py::test_default_yes_reasons_keep_their_blocking_gate PASSED
test_pd_bank_014_declined_reason_flags.py::test_waiver_mapping_marks_the_three_as_not_required PASSED
test_pd_bank_014_declined_reason_flags.py::test_question_sequence_projects_the_prior_yes_half PASSED
FAILED test_item33b_conversation_layer.py::test_park_seam_reports_unavailable_without_a_park_record
```

### Head — PD-032 build commit

`1 failed, 27 passed` (exit 1) — the same pre-existing failure plus the four new PD-032 tests:

```
... (base ids unchanged, all PASSED) ...
test_pd_bank_032_after_intake.py::test_file_parses PASSED
test_pd_bank_032_after_intake.py::test_after_intake_present_and_exact PASSED
test_pd_bank_032_after_intake.py::test_no_frontdoor_key_removed PASSED
test_pd_bank_032_after_intake.py::test_no_top_level_key_added_or_removed PASSED
FAILED test_item33b_conversation_layer.py::test_park_seam_reports_unavailable_without_a_park_record
```

### The one red test is pre-existing and is NOT caused by PD-032

`test_park_seam_reports_unavailable_without_a_park_record` fails identically on the untouched base
clone, before any PD-032 change:

```
>       assert result["status"] == "layer_unavailable"
E       AssertionError: assert 'client_silent' == 'layer_unavailable'
test_item33b_conversation_layer.py:161: AssertionError
```

It exercises `conversation_layer.park_notice`, which never reads `frontdoor.after_intake`. It was not
weakened, deleted, renamed, skipped or marked xfail. It remains red on the branch and belongs to
whichever unit owns that seam.

---

## 7. Hunk attribution (merge-base `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc` to head)

Commits already on `pd/fl03-question-bank` before this unit, with their hunks:

| Commit | Unit | Files |
|---|---|---|
| `941a777cf` | PD-024 | `intake/deck-intake-questions.json` (12/12 wording) |
| `0678e4822` | PD-014 | `intake/deck-intake-questions.json` (34/16), `intake/question_sequence.py` (12/0) |
| `84f907214` | PD-014 | `intake/question_sequence.py` (5/6) |
| `479411406` | PD-014 | `scripts/tests/test_pd_bank_014_declined_reason_flags.py` (129/0) |
| `5a9743c2d` | PD-933 | `intake/interview-app/test/test_email_election_flow.py` (14/3), `evidence/PD-933/BUILD-REPORT.md` (122/0) |
| `e7c631fd` | **PD-032 (this unit)** | `scripts/conversation_templates.json` (1/0), `scripts/tests/test_pd_bank_032_after_intake.py` (104/0) |

No sibling commit touches `scripts/conversation_templates.json`. PD-032's hunks are the only ones in
that file since the merge-base, and its only sibling-adjacent file is the new test in
`scripts/tests/` — PD-014's test file there is untouched.

---

## 8. PD-014 flags and PD-909 — what I can see on this branch

The handoff says PD-014 is passed here and PD-909 is currently blocked because PD-014 bank flags are
absent from every bank on this branch. I did not touch the banks. What is on this branch at
`5a9743c2d690c7f4c43fdc48898c4fd8048ad1b4`:

```
23-.../intake/deck-intake-questions.json -> ask_only_if_previously_wanted count: 6
                                            waiver_required count: 4
23-.../intake/upsell-questions.json     -> ask_only_if_previously_wanted count: 0
                                            waiver_required count: 0
```

`ask_if` also appears in `intake/question_sequence.py`, `scripts/deck-intake-driver.py`, and the
interview-app payload/worker files. So on `deck-intake-questions.json` the flags **are visible**, added
by commits `0678e4822`, `84f907214` and `479411406`; they are **absent from `upsell-questions.json`**
(0 occurrences in both keys). If PD-909's gate reads the upsell bank, that is the empty surface it
would be looking at. I have not changed either bank and take no position beyond that observation.

---

## 9. Remote-head proof

Pre-build remote head, from `git ls-remote --heads origin refs/heads/pd/fl03-question-bank`:

```
5a9743c2d690c7f4c43fdc48898c4fd8048ad1b4	refs/heads/pd/fl03-question-bank
```

Post-push remote head (the report commit is pushed on top of the build commit
`e7c631fd5e182a9c08a1a17dc5525ce9d3009434`); the literal 40-character result of the verification
command is recorded in the unit handback.

---

## 10. What is not proved / limits

- Only A1 exists for this unit; there are no other acceptance rows.
- The `after_intake` string is client copy but no test drives it through a live conversation; the
  unit's own text says "files and stubbed tests only" and the live-action flag is `none`.
- The pre-existing red test in §6 is reported, not fixed — fixing it would be a change no one asked for.
- Nothing was tested against the interview app's rendered payload; PD-032 adds a template key whose
  consumer (`conversation_layer.frontdoor_handoff`) is unchanged and its 19 tests still pass.

---

## 11. Instrument correction — temp files moved out of `/var/folders`

The first pytest runs let pytest's `tmp_path` fall back to the machine temp root
(`/private/var/folders/yf/.../T/pytest-of-blackceomacmini/pytest-418`), which violates this unit's
binding storage rule. That directory was identified by its contents (it held
`test_park_seam_reports_unavail0`, one of the ids from my run), deleted, and the tests were re-run
with `TMPDIR` pointed at the unit scratch directory. Nothing else under that temp root was touched —
23 sibling `pytest-*` directories belong to other concurrent agents and remain as they were.

Both suites were re-run on the corrected instrument and are unchanged:

```
base (5a9743c2d): 1 failed, 23 passed   # head-pytest-clean.log / base-pytest-clean.log
head (e7c631fd):  1 failed, 27 passed
```

`tempfile.gettempdir()` inside that run resolved to
`/Volumes/mac mini m4/swarm-contract/pd-fix/tmp/PD-032`, and the count of `pytest-*` directories under
the machine temp root was 23 before and 23 after each run.
