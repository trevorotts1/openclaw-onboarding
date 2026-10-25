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

## Run-bound launch, bootstrap and model-role evidence

A card call bound to `--run-dir` or `--run-state-file` uses the durable intake
path even when `--step` is omitted. Continue to use `--step --format
session-json` for the operator loop above. Explicit `studio-json` export and
unbound previews remain static renderers; they do not record a completed
intake. The prior missing-`--step` behavior is not a reason to alter method
or purpose detection or to migrate an existing client project.

Explicit recap confirmation binds the client's AI MODELS pair through
`ai_models.bind_roles`. Each client's explicit builder and checker choices keep their literal
configured aliases: build stages use that builder, QC and repair use that
checker. The stage plan calls
`admit_dispatch` against the saved run bindings and refuses a mismatched role
or requested model. This does not select a chain member, change the client's
provider choices or alter global session settings. Preserve existing run
bindings and attempt records; a different pair is not silently substituted.

The same confirmation prepares missing stages from canonical
`batch_mode.batch.STAGES` through `Store.init_run`. Newly created stages are
`NOT_STARTED`; existing run IDs, stage states, approvals, model bindings and
attempts are preserved. Bootstrap and the next pending research command do
not run a worker, call a language model or generate media.

A model listed by the configured router's `/v1/models` endpoint is available
to route, not proven to have executed. A stage plan marked
`admitted_not_called` is admission evidence only. `record_attempt` refuses
router-chain verification with `CHAIN_RESOLUTION_UNVERIFIED` until dedicated
supported provider identity evidence proves the actual call; an alias name,
model-list response or assistant assertion is not that evidence. Never claim
that chain members or provider execution were verified by this no-generation
intake/bootstrap check. Existing owner projects remain unchanged unless a
separate authorized migration is actually performed and verified.

## Governed production admission

Run confirmed-intake planning without approving an unseen script or storyboard:

```bash
python3 scripts/core/intake_preflight/factory.py preflight --run-dir "$RUN"
python3 scripts/core/intake_preflight/factory.py next --run-dir "$RUN"
```

A dependency-only or diagnostic preflight explicitly reports that it has not
admitted production. To check a particular canonical stage, add
`--stage "<canonical stage>"`. The shared admission code reads the actual
validated factory stage registry; it checks confirmed raw answer provenance,
run identity, completed predecessor transitions and required artifacts. Do not
write an authorization JSON file, card receipt or database row to satisfy a
refusal. These projections do not grant authority.

When the client elected script approval, the whole current script, every scene
and lyrics require their existing revision-bound artifact decisions before
music. Song choice remains a separate downstream gate when elected. Storyboard
artifact approval uses the current shot contracts and stills after keyframes
exist, before video generation. Preferences, spending caps and a general request
to begin do not approve unseen artifacts. Creative dramatic proposals remain
allowed; label their sources accurately and present the whole package.

The paid dispatch boundary checks admission before planning/reserving spend and
rechecks it with the current request before real submission. Vocal separation
and picture repair carry their actual canonical stage context. Explicit offline
runner simulations remain available but report non-authoritative evidence;
their receipts cannot establish a completed production predecessor.

Existing legacy answers are preserved. A legacy run with current revision-bound
artifact decisions and matching governed stage history can resume. Missing or
ambiguous authority returns a specific hold; it does not reset the run or
reconstruct old client replies. Live SQLite state is read without modifying the
source store or ignoring its pending WAL updates.

These checks enforce supported entrypoints and application evidence. They do
not establish an operating-system security boundary against a party able to
rewrite the code and all histories. Do not claim an absolute filesystem lock or
that admission proves a provider call occurred.

## Actual artifact replies and uploaded frames

The pending script response exposes `data.approval_context`: its actual run ID,
open `ask_id` values and current artifact revisions. Send the whole returned
script and lyrics package. When the client replies, carry that new raw message
and its real source reference separately from the presentation identity:

```bash
python3 scripts/core/intake_preflight/factory.py script-reply --run-dir "$RUN" \
  --run-id "<actual saved run_id>" --presentation-ask-id "<actual open ask_id>" \
  --reply-source client --answer-source-ref "<new client message reference>" \
  --reply "<the client's exact artifact reply>"
```

An intake preference such as “yes, show me first”, a reused intake message, or
an assistant assertion cannot approve the artifact. Missing or mismatched
provenance waits without changing the run. Existing contextless Studio apply
commands also wait; supply real channel evidence, never invented source IDs.
A valid client edit rechecks and re-presents the current whole package; it does
not approve a changed script or lyrics.

For an image-to-video first frame, upload the current approved shot still
through the governed producer:

```bash
python3 scripts/core/kie_dispatch/kie_dispatch.py upload-storyboard-frame \
  --run-dir "$RUN" --shot-id "<approved shot_id>" --stage video-generation
```

Use the returned `frame_binding.url` as the existing request builder's
`first_frame_url`, and attach that binding at
`request.frame_bindings.first_frame_url`. The producer reuses Skill 74 upload
transport and binds its actual byte hash, URL, shot and storyboard revision.
An arbitrary URL with approved storyboard metadata is insufficient. Injected
offline uploaders cannot grant paid admission. A separately specified last
frame waits for an approved end-state contract; it is never silently replaced
by the first frame or another still. No generation is performed by this upload
step. Existing text-to-video and measured lip-sync routes retain their own
contracts.
