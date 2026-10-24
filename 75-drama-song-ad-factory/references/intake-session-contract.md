# Durable interactive intake contract

This is the operator contract for new interactive intakes in both runtime
flavors. It uses the existing question renderer and the persistent intake
session; it does not replace the question list or change creative policy.
For this path it supersedes older instructions to replay every answer with
repeated `--reply` flags, preselect defaults, or declare a fixed question count.

## Render, send, record, resume

1. Open the pending turn through the supported entrypoint:

   ```bash
   python3 scripts/core/intake_preflight/factory.py card --step --run-dir "$RUN" --format session-json
   ```

2. Send the returned `message` verbatim. Preserve its `question_id` and
   `question_digest` with the delivery record. Never rewrite its question,
   descriptions, order, option labels or recommendations; never invent a menu.
   The supplementary Agnes/KIE explanation belongs to the renderer too.

3. Wait for one explicit human reply. Carry its exact raw text and the actual
   originating message or transcript reference into the next turn:

   ```bash
   python3 scripts/core/intake_preflight/factory.py card --step --run-dir "$RUN" --format session-json \
     --question-id "<question_id from the last response>" \
     --question-digest "<question_digest from the last response>" \
     --reply "<exact raw client reply>" --reply-source client \
     --answer-source-ref "<actual originating message or transcript reference>"
   ```

   A normal turn can omit the source reference at the CLI level, but the
   operator must provide it whenever the channel supplies one. The normal-turn
   provenance field is `source_ref`; the CLI flag is `--answer-source-ref`.
   Never label an assistant recap, a suggested default, silence or an inferred
   preference as a client reply. `recommended` counts only when the client
   explicitly replies with it to the displayed question.

4. Use the returned `message` for the next turn. An interruption needs no
   history retyping: repeat the first command with the same `--run-dir` and no
   reply to retrieve the saved pending question. Do not create a fresh run to
   work around a refusal or an unreadable session.

`--run-state-file` is optional for callers that use the existing one-time
intro. An intro response has no question identity: show it, then make another
no-reply call to obtain the first question. Do not answer a question that has
not been rendered. With no run directory, the session is stored beside that
run-state file; production runs should use their established `--run-dir`.

The session at `$RUN/control/intake-session.json` saves each accepted answer
before returning the next turn. Its `events` and `answer_records` retain the
raw text, client source, source reference, timestamp, question identity and
exact rendered question, parsed answer and option identity. Preserve the
original wording of business facts and character details. Ages are not video
durations; a number in one question is never an answer to another question.

Unknown or mismatched options, wrong question IDs/digests and answers to
unseen questions cannot advance intake. On a menu revision, retain existing
raw evidence, show the new exact question and obtain an explicit reply bound
to its new digest. Never reuse an old menu number against a different menu.
Unchanged valid facts stay saved; ask only for choices whose meaning is
actually ambiguous or missing. Do not silently substitute another model,
length, character, provider or purpose.

## Reuse explicit prior client facts

Do not ask clients to repeat business facts that already have explicit raw
client evidence. Import those facts using the supported seed path:

```bash
python3 scripts/core/intake_preflight/factory.py card --step --run-dir "$RUN" --format session-json \
  --seed-answers-file "$PRIOR_ANSWERS"
```

`$PRIOR_ANSWERS` must be a JSON list. Each row carries `question_id`,
`raw_answer` and a nonempty `source_ref` pointing to the actual client answer;
`source`, when supplied, must be `client`. Example shape only:

```json
[
  {
    "question_id": "offer",
    "raw_answer": "<the client's exact offer name>",
    "source_ref": "<actual message or transcript reference>"
  }
]
```

Typed business facts and an explicit dollar amount for `spend` can be seeded
before the purpose question has been answered. Menu choices require the
current pending question ID and matching `question_digest`, plus an explicit
supported nonnumeric choice; old numeric menu selections are refused. Do not seed a
confirmation, an assistant summary, a guessed song selection, or a choice
whose original question is unknown. Conflicting saved facts are held for
resolution; they are not overwritten. Keep genuinely ambiguous evidence and
explain the one unresolved choice without discarding established facts.

Legacy `card-answers.json` is preserved as unverified evidence when it lacks
this provenance. It is never automatically remapped or treated as a completed
new session. Legacy bulk Studio order replay does not supply this contract:
it currently fails closed rather than accepting an unprovenanced answer
batch. Preserve the order and its source evidence, seed explicit supported
facts, and continue the pending questions through the supported entrypoint.
Do not bypass that refusal with the stateless renderer, claim the Studio web
producer has been updated, or claim a failed bulk replay saved its answers.

## Completion and approval boundaries

The response's `answered_count`, `total_count` and `done` are the completion
record. Never state a fixed count or say all questions are answered from
memory. `done` becomes true only when all current required questions have
valid saved answers and the client explicitly confirms the rendered recap.
A recap awaiting confirmation is still incomplete. Replying with a line
number at the recap reopens that line through the renderer.

For a run carrying a durable intake session, `factory.py next --run-dir
"$RUN"` returns waiting/exit 2 with `INTAKE_NOT_CONFIRMED` and no stage command
while intake is incomplete. An unreadable session returns error/exit 1 with
`INTAKE_SESSION_UNREADABLE`. Follow its resume command and preserve the state.
Old runs without this session retain their established path; absence of a
session file is not evidence that a new intake was completed.

Normal valid card turns return exit 0; answer-validation waits return exit 2;
state/adapter errors return exit 1. Read `outcome` and `reason_code` as well as
the process exit status; an emitted question is not a completed intake.

The SCRIPT APPROVAL, SONG APPROVAL and STORYBOARD answers are preferences for
later gates. Intake recap confirmation does not approve any actual script,
song take, storyboard, spend or paid provider request. Present the whole
script with all scenes and lyrics together for its explicit artifact
approval; keep the actual song-selection and storyboard approval records
separate and bound to their artifacts. Existing budget, provider, creative,
lip-sync and independent QC gates continue to apply. A statement such as
"recorded" in an assistant recap is not an approval receipt.
