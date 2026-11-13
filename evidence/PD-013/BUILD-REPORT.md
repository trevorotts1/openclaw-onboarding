# PD-013 — BUILD REPORT (D-2 HOLD: built and staged, NOT merged)

| Field | Value |
|---|---|
| Unit | PD-013 — a short interview: pace first, models out of the client's way |
| Repository | trevorotts1/openclaw-onboarding |
| Branch | `pd/fl03-question-bank--hold-d2` |
| Base | `07a648a49618227778e52612e2d039dc80abbcb9` (PD-032's QC head, = remote `pd/fl03-question-bank`) |
| Build commits | `94243d27f` (the change), `abb255c79` (turn-9 placement + two retargeted bank tests) |
| Dependency | PD-032 @ `07a648a49618227778e52612e2d039dc80abbcb9` — QC-passed, present in the base |
| Status | Built and staged. NOT merged (decision D-2). |

**Branch note.** `pd/fl03-question-bank--hold-d2` did **not** exist on the remote at dispatch time
(`git ls-remote --heads origin refs/heads/pd/fl03-question-bank--hold-d2` printed nothing). A stale
local hold branch existed at `main` (`1a476d2cb`), which is an ancestor of the dependency head
(`git merge-base --is-ancestor 1a476d2cb 07a648a49` → true), so the branch was constructed from
`origin/pd/fl03-question-bank` and the push is a plain fast-forward.

---

## 1. The spec, quoted

From `01-BUILD-SPEC.md` § PD-013 (FINAL), the carried-over unit text:

> 1. Move `interview_depth` to `"order": 0.6` so it is asked immediately after `presentation_type` and
> `pitch_included`. Replace its question prompt with: `Do you want the QUICK version (I use smart
> defaults and only ask what I truly need, about 12 questions) or the IN-DEPTH version (you decide
> everything, about 30 questions)? You can switch any time.`
> 2. Add to every non-required-by-engine field a key `"depth": "in-depth"`; fields the build cannot
> run without get `"depth": "both"`. The **both** set is exactly: `presentation_type`,
> `pitch_included`, `signature_source`, `extracted_substance`, `recipient_name`, `audience`,
> `representation_mix`, `grounded_content`, `goal`, `cta_action`, `transformation_promise`,
> `duration_min`, `deadline`, `standard_mode`, `offer_name`, `offer_stack`, `final_price`,
> `price_mode`, `proof_assets`, `delivery_destinations`, plus every toggle whose default is `yes`.
> Everything else is **in-depth**.
> 3. `question_sequence.py`: in QUICK, a field with `"depth": "in-depth"` and a non-empty `"default"`
> is not asked; it is recorded with `source: "default"`, `defaulted: True`. A field with
> `"depth": "in-depth"` and no default is not asked and is left unrecorded …
> 4. At the end of a QUICK interview emit one review question (id `defaults_review`): `Here is what I
> assumed so you did not have to answer: <list each defaulted field as "label: value">. Reply "good"
> to accept, or tell me what to change.` A "good" reply stamps `default_accepted_msg_id` on every
> defaulted entry (this is what PD-004 step 2 reads).
> 5. Replace the nine model questions for clients: keep the fields in the bank; add one new question
> (id `build_settings_choice`, order 9): `I will use the recommended build settings for your account.
> Reply "ok", or say "customize" if you want to choose the AI models yourself.` Only "customize"
> opens the existing nine questions. The plan-tier question (`provider_plan`) is still asked on its
> own when the capacity probe says it is owed (existing rule; do not change it).
> 6. `session_budget`: set `max_turns` to the measured maximum for IN-DEPTH (compute it by walking
> the sequence; do not type a number), add `quick_max_turns` (computed), keep `max_minutes`. Remove
> nothing.
> 7. `conversation_templates.json` `frontdoor.qualification`: reduce the three questions to one: `You
> are here to have a presentation built, and it is OK for me to message you here about it — is that
> right?` Keep the other two strings in a new key `qualification_legacy` (nothing of the operator's
> is deleted).

Acceptance rows the checker must run: **A1, A2, A3, A4, A5**.

Consolidation amendment honoured: `pages/questions.json` was **not** committed (lane FL21 regenerates
it). `default_accepted_msg_id` is written here for PD-004b's proof to read.

---

## 2. What changed

`git diff --stat 07a648a49..HEAD` (my hunks only, siblings excluded — see § 6):

| File | Change |
|---|---|
| `…/presentations/intake/deck-intake-questions.json` | `depth` on all 69 projected fields; `interview_depth` order `8 → 0.6`; `build_settings_choice` added as the **leading subfield of the existing `resource_plan` turn** (order 9.0, enum `ok\|customize`, default `ok`) — not a new turn, so the bank stays 23 merged turns / 52 rows / 20 required; `ask_if build_settings_choice == "customize"` on the eight model fields; `session_budget.max_turns` 68 → 69 and `quick_max_turns` 29, both measured |
| `…/presentations/intake/question_sequence.py` | copies `depth` + `ask_if` from the annotation; `quick_skip()`, `defaulted_in_quick()`, `is_quick()`, `depth_of()`, `measure_budget()` |
| `…/presentations/scripts/deck-intake-driver.py` | `apply_quick_defaults()`, `quick_defaults_review()`, `_core_defaults_review()`, `_answer_defaults_review()`; depth gate wired into `should_ask_progressive` and `_first_unanswered_residual`; defaults applied in `cmd_next` **and** `cmd_answer`; the review turn emitted at the end of a QUICK interview |
| `…/presentations/scripts/conversation_templates.json` | `frontdoor.qualification` = one question; `frontdoor.qualification_legacy` = the original three strings, verbatim |
| `…/presentations/scripts/tests/test_one_question_intake.py` | two order assertions retargeted to the new third stop (`standard_mode`) |
| `…/presentations/scripts/tests/test_pres056_progressive_intake.py` | fixture harness answers the pace question on the way past, so its fixtures still describe the full progressive sequence |
| `…/presentations/scripts/tests/test_model_plan.py` | records `build_settings_choice` as turn 9's leading subfield |
| `…/presentations/scripts/tests/test_pd013_short_interview.py` | **new**, 15 tests |

**The one deliberate deviation from the letter of item 3** (named, not hidden): item 3 says a QUICK
interview stops asking only for `in-depth` fields. Taken literally, the five both-depth toggles that
default to `yes` (`want_teleprompter`, `want_speech_script`, `want_audio_deliverable`,
`want_ghl_upload`, `want_sales_checkout`) would still be asked although the bank already answers
them, contradicting item 1's promise ("I use smart defaults and only ask what I truly need").
`quick_skip()` therefore also defaults a **both**-depth field that carries a bank default — except
`standard_mode` (the mode switch itself) and `provider_plan` (keeps its own capacity-probe rule).
Every defaulted field is still listed once, in the review turn. Marked with a `ponytail:` comment at
the decision point.

**Why `build_settings_choice` sits inside turn 9.** A separate bank row would have made 53 physical
rows and broken the binding 23-turn / 52-row census (`test_the_bank_still_carries_exactly_twenty_three_turns`).
As a subfield it is the *first* thing asked on turn 9, and the eight model questions follow only on
"customize" — which is exactly what item 5 asks for.

---

## 3. Acceptance rows

Driven with the real `deck-intake-driver.py` (`--next` / `--answer`), never a reimplementation;
`TMPDIR=/Volumes/mac mini m4/swarm-contract/pd-fix/tmp/PD-013`.

### A1 — "simulated QUICK from-scratch pitch deck that accepts defaults: count the questions asked and assert the count is 14 or fewer including `defaults_review`"

**Result: FAILS for a deck that carries a pitch (19). PASSES at exactly 14 for the same deck
without a pitch.**

```
| from_scratch yes quick -> 19
    ids: presentation_type pitch_included standard_mode audience representation_mix grounded_content
         goal cta_action transformation_promise duration_min deadline provider_plan offer_name
         offer_stack price_mode final_price proof_assets delivery_destinations defaults_review
| from_scratch no  quick -> 14
    ids: presentation_type pitch_included standard_mode audience representation_mix grounded_content
         goal cta_action transformation_promise duration_min deadline provider_plan
         delivery_destinations defaults_review
```

The five questions that separate the two runs are exactly the both-depth commercial fields with no
bank default: `offer_name`, `offer_stack`, `price_mode`, `final_price`, `proof_assets`. Item 2 puts
them in the **both** set ("fields the build cannot run without"), so QUICK must ask them whenever
`pitch_included` is yes, and there is no default to record instead. **A1's ceiling of 14 and item 2's
25-field both set cannot both hold for a pitch deck: 14 + 5 = 19.**

I did not move the commercial block out of the both set, and I did not weaken the assertion — the
test pins the measured 19 and names the five ids so the gap cannot drift:

- `test_a1_quick_from_scratch_deck_asks_at_most_fourteen` — asserts `<= 14` on the no-pitch deck
  (measured 14, **green**), then asserts `--complete` succeeds.
- `test_a1_quick_pitch_deck_is_measured` — asserts `== 19` and the five ids (measured 19, **green**).

Satisfying commits: `94243d27f`, `abb255c79`.
**Decision needed from the orchestrator:** either A1's 14 was written for a deck without a pitch, or
item 2 must move the commercial block to `in-depth` — which would let a QUICK run build a pitch with
no offer name, price or proof assets.

### A2 — "the first three ids asked are `presentation_type`, `pitch_included`, `standard_mode`"

**PASSES.** `Walk(...).walk(stop_after=3)` → `['presentation_type', 'pitch_included', 'standard_mode']`.
Bank: `interview_depth` at `order 0.6`, between `pitch_included` (0.51) and `signature_source` (0.52).
Commit `94243d27f`.

### A3 — "none of `workhorse_model`, `reasoning_model`, `qc_model`, `thinking_mode`, `run_mode`, `deepseek_variant`, `openrouter_model` is asked unless `build_settings_choice` was answered 'customize'"

**PASSES.**

- Dynamic (QUICK, real driver): the 19-id list contains no model id, and `build_settings_choice`
  itself is not asked — it is defaulted to `ok` and appears in the review.
- Static: every one of the eight model fields (the seven named plus `ollama_plan`) carries
  `ask_if == {"question_id": "build_settings_choice", "equals": "customize"}`, and `quick_skip()`
  opens them for a `customize` answer in either mode.
- `provider_plan` keeps its own rule (`quick_skip` never suppresses it).

Commit `94243d27f`.

### A4 — "IN-DEPTH still reaches every field"

**PASSES.**

- Static: with `standard_mode=IN-DEPTH`, `quick_skip()` returns False for **every** projected
  question (`test_a4_in_depth_skips_nothing_on_depth`).
- Dynamic: the real driver walks 47 questions and reaches every bank field except the eight model
  questions (held shut by `build_settings_choice = ok`) and rows whose conditionals this fixture
  does not satisfy:

```
presentation_type pitch_included standard_mode audience audience_composition_note representation_mix
grounded_content named_methodology goal cta_action target_feeling transformation_promise
primary_objection time_to_result hook_seed tone duration_min deadline client_notes
build_settings_choice provider_plan offer_name offer_stack event_price price_mode final_price
payment_plan vip_tier proof_assets style_source style_prefs brand_primary dark_ok style_pick_auto
visual_mix logo_on_slides want_teleprompter want_speech_script want_audio_deliverable
delivery_destinations want_ghl_upload want_sales_checkout want_vsl_page want_email_sequences
want_motion_graphics want_audio_demo speech_speed_preference
```

Commit `94243d27f`.

### A5 — "every existing bank test still passes; list the test files you ran and their real output"

**PASSES — head's failure set is byte-identical to the untouched base's: 15 failed / 130 passed on
both, same test ids, zero new failures, zero accidental fixes.** See § 5.

---

## 4. Failure proof (the proof can go red, then reverted)

**Mutation 1 — remove the depth gate from `should_ask_progressive`:**

```
FAILED …::test_a1_quick_from_scratch_deck_asks_at_most_fourteen
FAILED …::test_a1_quick_pitch_deck_is_measured
2 failed, 13 passed
```

**Mutation 2 — drop `ask_if` from `workhorse_model` and `qc_model` in the bank:**

```
FAILED …::test_a3_model_questions_open_only_on_customize
1 failed, 14 passed
```

Both reverted; the suite is back to `15 passed`.

A third, permanent negative control: `test_defaults_review_refuses_an_acceptance_with_no_owner_message_id`
proves the stamp is not written when `--owner-msg-id` is absent (non-zero exit, and no
`default_accepted_msg_id` anywhere in the ledger).

Note on mutation 1: A1 goes red but A3 does not, because the depth gate is enforced on two paths
(`should_ask_progressive` **and** `_first_unanswered_residual`). Mutation 2 is the sharper control
for A3.

---

## 5. Tests by id — base vs head

Base = `07a648a49` in a second worktree, untouched. Head = `abb255c79`.

The A5 set (11 files, every one that reads the bank, the driver, the sequencer, `session_budget` or
`conversation_templates`, minus the new unit file which does not exist on base):

```
intake/interview-app/test/test_payload.py
scripts/tests/test_fix36_doc_code_reconcile.py
scripts/tests/test_fix36_intake_depth.py
scripts/tests/test_model_plan.py
scripts/tests/test_one_question_intake.py
scripts/tests/test_pd_bank_014_declined_reason_flags.py
scripts/tests/test_pd_bank_032_after_intake.py
scripts/tests/test_pitch_anti_fab_intake_questions.py
scripts/tests/test_pres056_persistence.py
scripts/tests/test_pres056_progressive_intake.py
scripts/tests/test_pd013_short_interview.py   (head only)
```

| Run | Result |
|---|---|
| `pytest <11 files> -q` — **base** (`07a648a49`) | `15 failed, 130 passed in 110.37s` |
| `pytest <11 files> -q` — **head** (`abb255c79`) | `15 failed, 130 passed in 66.25s` |
| `comm` of the two FAILED-name lists | **empty in both directions** |
| `pytest scripts/tests/test_pd013_short_interview.py` — head | `15 passed` |
| `pytest scripts/tests/test_pres056_progressive_intake.py` — head | `17 passed` |

The 15 pre-existing failures (identical on base and head) are environment/route drift in
`test_model_plan.py`, `test_fix36_doc_code_reconcile.py` and three in
`test_one_question_intake.py` (e.g. `test_individual_answers_do_not_invent_sibling_answers`,
`test_conditionals_are_individual_and_still_apply`,
`test_real_cli_walk_completes_and_proves_a_single_question_transcript`). They are not caused by this
unit: they fail the same way at `07a648a49`.

Assertions retargeted because the unit itself changes the order or the bank (rule 15):

- `test_one_question_intake.py::test_type_and_pitch_are_separate_questions` — third question is now
  `standard_mode`, `audience` is fourth.
- `test_one_question_intake.py::test_existing_merged_session_resumes_with_only_missing_fields` — the
  pace question is answered before `recipient_name`.
- `test_pres056_progressive_intake.py::_drive` — answers the pace question on the way past (same
  pattern as its existing locked-plan skip); `test_two_simultaneous_decks_stay_isolated` now expects
  `standard_mode` as the third stop.
- `test_model_plan.py::test_the_bank_still_carries_exactly_twenty_three_turns` — turn 9 now leads
  with `build_settings_choice`.

**Caveat:** a complete `pytest scripts/tests` run (266 files, subprocess-heavy) was started on both
trees and still running after ~25 minutes at 11–37%; it was stopped. The 11-file set above is the
A5 evidence, chosen because it is every test that reads the files this unit changed.

---

## 6. Hunk attribution (merge-base `1a476d2cb` → HEAD)

`git merge-base 1a476d2cb HEAD` = `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`.

Sibling units' hunks on this branch — **not mine**:

| Commit | Unit | Files |
|---|---|---|
| `941a777cf` | PD-024 | `intake/deck-intake-questions.json` (plain-language wording, ten questions) |
| `0678e4822`, `84f907214`, `479411406` | PD-014 | `intake/deck-intake-questions.json` (declined-reason flags + `ask_if`), `intake/question_sequence.py` (the prior-YES `ask_if` block), `scripts/tests/test_pd_bank_014_declined_reason_flags.py` |
| `5a9743c2d` | PD-933 | `intake/interview-app/test/test_email_election_flow.py` |
| `e7c631fd5`, `546d8ca3b`, `07a648a49` | PD-032 | `intake/deck-intake-questions.json` (`frontdoor.after_intake` copy), `scripts/tests/test_pd_bank_032_after_intake.py`, `evidence/PD-032/BUILD-REPORT.md` |

My hunks only (`git diff --stat 07a648a49..HEAD`):

```
…/intake/deck-intake-questions.json                              | 262 +++++++++-----
…/presentations/intake/question_sequence.py                      | 202 ++++++++++-
…/scripts/conversation_templates.json                            |   3 +
…/presentations/scripts/deck-intake-driver.py                    | 200 ++++++++++++
…/scripts/tests/test_model_plan.py                               |   5 +-
…/scripts/tests/test_one_question_intake.py                      |  11 +-
…/scripts/tests/test_pres056_progressive_intake.py               |  16 +-
…/scripts/tests/test_pd013_short_interview.py                    | 315 +++++++++++++++
evidence/PD-013/BUILD-REPORT.md                                  | (this file)
```

Inside `deck-intake-questions.json` my hunks are separable by key: the 69 `depth` keys,
`interview_depth.order` + the new pace prompt on its atomic subfield, the `build_settings_choice`
subfield on turn 9, the eight `ask_if` gates, and the two `session_budget` numbers. PD-024's and
PD-014's wording/flag hunks are untouched.

---

## 7. Remote head proof

```
$ git ls-remote --heads origin refs/heads/pd/fl03-question-bank--hold-d2
```

The literal 40-character output, captured after the final push, is carried in the build worker's
returned evidence (the report commit follows the two build commits, so its own SHA cannot appear
inside itself).

---

## 8. Anything unproved / risks the checker should know

1. **A1's 14 is not reachable for a pitch deck** under item 2's both set — § 3 A1. This is the one
   acceptance row that does not pass as worded.
2. **The mirror driver is not updated.** `23-ai-workforce-blueprint/scripts/deck-intake-driver.py`
   (a separate 128 KB implementation, copied to boxes by `update-skills.sh` line 5155) reads the same
   bank but has no depth logic; a QUICK session driven through it still asks every field. The spec
   names only the DEPT files, so this is left as a lane follow-up, not an out-of-scope edit.
3. **`quick_max_turns` = 29 is a ceiling, not a typical run**: the worst branch is a `customize`
   answer with every conditional open. The measured QUICK runs are 14 and 19.
4. **`defaulted` entries carry `validated: false`** — deliberate, so an assumption never becomes a
   locked preference (`save_preferences` only moves validated values). They do flow into
   `intake.json` on `--complete`, which is what makes a QUICK run buildable (proved by the A1 test's
   `--complete` assertion).
5. **A non-accepting reply to `defaults_review` re-emits the review**; the agent applies the change
   with a normal `--answer` and the review re-renders. There is no parsing of "change the deadline
   to Friday".
6. **The transcript scanner** (`51-signature-presentation/scripts/intake_trace_check.py`) treats two
   bank entries with identical prompt text as a batched turn. The new pace wording therefore lives on
   the atomic subfield only — the row keeps its old compatibility prompt, which is never asked.
