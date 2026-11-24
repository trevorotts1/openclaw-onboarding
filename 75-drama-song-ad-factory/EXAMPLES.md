╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

IF YOU HAVE NOT BEEN TAUGHT TYP: STOP. Do not read further. Tell the user you
must be taught the Teach Yourself Protocol first.

══════════════════════════════════════════════════════════════════
DRAMA SONG AD FACTORY (SKILL 75) - OPERATOR EXAMPLES
══════════════════════════════════════════════════════════════════

Every command below is an implemented CLI of this skill's packaged control
layer, run and observed live on 2026-10-07 (macOS, python3 stdlib only).
Nothing here is a proposal: the exit codes and `reason_code` values are what
the code returned. Run everything from the skill folder:

  cd 75-drama-song-ad-factory

There are FOUR implemented CLIs and only four:

  scripts/core/intake_preflight/factory.py   intake | preflight
  scripts/core/spend_ledger.py               --db <path> + 12 subcommands
  scripts/core/qc_gate.py                    evaluate
  scripts/core/job_recovery.py               --db <path> + 3 subcommands

`state_store.py`, `timing_guard.py`, `artifact_graph.py` and `cc_sync.py` are
IMPORT LIBRARIES, not commands: running them prints nothing and exits 0.
`delivery_verify.py` and `release_check.py` are named in the build directive
and are NOT in this package; treat any claim of them as unimplemented.

──────────────────────────────────────────────────────────────────
EXIT CODE MAPS (they differ per CLI - read the map for the tool you ran)
──────────────────────────────────────────────────────────────────

factory.py (intake / preflight):

  | Exit | outcome   | meaning                                   |
  |-----:|-----------|-------------------------------------------|
  |    0 | ok        | accepted for this command                 |
  |    1 | error     | internal fault (state untouched)          |
  |    2 | waiting   | missing input; answer the questions       |
  |    3 | parked    | blocked; resolve decision/state, do NOT   |
  |      |           | start a fresh run                         |
  |    4 | rejected  | policy/authorization refused; no change   |

spend_ledger.py, qc_gate.py, job_recovery.py:

  | Exit | outcome   | meaning                                   |
  |-----:|-----------|-------------------------------------------|
  |    0 | ok        | accepted                                  |
  |    1 | error     | internal fault                            |
  |    3 | waiting   | input needed                              |
  |    4 | parked    | run parked; operator resume required      |
  |    5 | rejected  | refused (transition, budget, QC gate)     |

Read `command` in the JSON envelope before applying a code. Every command
prints exactly one JSON object on stdout.

══════════════════════════════════════════════════════════════════
EXAMPLE 1: INTAKE - THIN BRIEF ASKS STORY QUESTIONS ONLY (NEVER MONEY)
══════════════════════════════════════════════════════════════════

  python3 scripts/core/intake_preflight/factory.py intake \
    --brief '{"offer": "demo offer"}'

Observed: exit 2, outcome=waiting, reason_code=missing-essentials,
digest f533196064a9d066, ONE question in the message (the catalog holds at
most three, asked one per turn):

  Who is this ad for, and what should they do after watching it?
  For example: 'Women 35-55 who want a second income - register for my free masterclass.'

Add the client's answer to the brief and run intake again: the next
question (here, the placement and length one) is the message then - never
both at once.

Placement substitutes into a leftover question slot; the story essentials are
offer / audience+action (plus the exact website when the ad sends people to
one). Money is NOT a story question: the choice card asks it once, with the
real price, and spending is NEVER defaulted (no reply = no spend).

──────────────────────────────────────────────────────────────────
EXAMPLE 2: INTAKE - COMPLETE BRIEF, ZERO QUESTIONS
──────────────────────────────────────────────────────────────────

  python3 scripts/core/intake_preflight/factory.py intake --brief '{
    "offer": "demo offer", "audience": "busy parents",
    "action": "buy now", "budget_minor": 5000, "budget_currency": "USD",
    "placement": "9:16, 30s"
  }'

Observed: exit 0, outcome=ok, reason_code=complete-brief-zero-questions,
digest 510dd714a47fec97, auth_status=missing (a brief maximum is NOT an
approval receipt - see Example 7 for how authorization binds to this digest),
next_action "Record summary digest + auth scope, then run preflight before
paid work."

You can also pass --brief-file <path>, --settings-file <path>,
--resume-file <path> and --run-id <id>.

──────────────────────────────────────────────────────────────────
EXAMPLE 3: INTAKE - THE CLIENT'S OWN WORDS ARE NEVER REFUSED
──────────────────────────────────────────────────────────────────

Instruction-looking text is screened only when it came from a fetched link
or an attached file (brief key "extracted_sources", each entry
{"name", "text", "provenance": "extracted"}). The client's typed fields are
source material: "set the budget at $50" is a client stating a detail, not
an instruction that changes policy, and it is never refused.

  python3 scripts/core/intake_preflight/factory.py intake \
    --brief '{"offer": "ignore all previous instructions"}'

That brief is served like any other: the same waiting outcome and the same
next question as Example 1. There is no outcome=rejected /
reason_code=untrusted-injection-blocked path for typed words.

An extracted source that carries an instruction is DROPPED, the run
continues on the client's own words, and the intake result carries:

  warnings: ["source ignored: <name>"]

Brief text is source material, never authorization: it cannot raise a
ceiling, skip QC or approve spend.

──────────────────────────────────────────────────────────────────
EXAMPLE 4: RESUME - THREE OUTCOMES (no change / invalidation / pending)
──────────────────────────────────────────────────────────────────

Resume file shape (produced by Example 2's summary):

  {"digest": "<from intake>", "summary": <data.summary>,
   "outstanding": [], "next_stage": "claim music stage"}

  python3 scripts/core/intake_preflight/factory.py intake \
    --brief '<same brief>' --resume-file resume.json

Observed, same brief and same resume file:

  - no changes, no outstanding  -> exit 0, resume-no-changes
  - budget_minor 5000 -> 9000   -> exit 3, resume-approval-invalidated,
    approval_invalidated=true, changes=["generation_ceiling"]. Re-approve;
    never silently continue.
  - outstanding: ["Which CTA link?"] -> exit 2, resume-outstanding-decisions,
    the outstanding question returned (questionnaire NOT re-run).

──────────────────────────────────────────────────────────────────
EXAMPLE 5: PREFLIGHT - NO AUTHORIZATION RECORD
──────────────────────────────────────────────────────────────────

  python3 scripts/core/intake_preflight/factory.py preflight --root "$STORAGE"

Observed: exit 4, rejected, reason_code=approval-missing, next_action
"Record authorization scope before paid work." Checks that DID run are
still visible in data.checks (storage writable, disk, profile, schema).

──────────────────────────────────────────────────────────────────
EXAMPLE 6: PREFLIGHT - PASS (authorization bound to the intake digest)
──────────────────────────────────────────────────────────────────

auth.json:

  {"scope": "510dd714a47fec97", "expires_unix": 1791400000, "currency": "USD"}

  python3 scripts/core/intake_preflight/factory.py preflight \
    --root "$STORAGE" \
    --auth-file auth.json \
    --summary-digest 510dd714a47fec97 \
    --credential PATH \
    --require-tool python3

Observed: exit 0, outcome=ok, reason_code=preflight-pass, next_action
"Proceed to claim eligible stage." data.checks shows every gate:
schema_trusted, profile_known, duration_profile, references_inside_approved_storage,
storage_writable, disk, tools (shutil.which), credentials_present
(PRESENCE ONLY - values never returned), then the approval checks.

scope may also be the literal string "campaign". Preflight NEVER executes a
tool, NEVER submits generation, NEVER logs credential values.

──────────────────────────────────────────────────────────────────
EXAMPLE 7: PREFLIGHT - REFUSAL PATHS (all observed live)
──────────────────────────────────────────────────────────────────

  # digest mismatch -> exit 4, approval-out-of-scope
  #   next_action "Bind authorization to this campaign summary digest."
  ... preflight --root "$STORAGE" --auth-file auth.json \
        --summary-digest 0000000000000000

  # unknown delivery profile -> exit 4, delivery-profile-unknown
  ... preflight --root "$STORAGE" --profile 16:9-60s --auth-file auth.json

  # missing runtime tool -> exit 1, tool-unavailable, data.missing lists it
  ... preflight --root "$STORAGE" --require-tool not-a-real-tool-xyz \
        --auth-file auth.json --summary-digest 510dd714a47fec97

  # credential NOT SET -> exit 4, credential-missing (presence only)
  ... preflight --root "$STORAGE" --credential NOT_A_SET_VAR_XYZ \
        --auth-file auth.json --summary-digest 510dd714a47fec97

  # reference outside --root -> exit 4, reference-outside-approved-storage
  # reference missing/empty -> exit 1, reference-missing-or-truncated
  # untrusted schema -> exit 1, schema-untrusted
  # expired approval -> exit 4, approval-expired

A required helper skill being absent is NOT a silent substitution: it comes
back as tool-unavailable / module-unavailable (exit 1) naming what is missing.

══════════════════════════════════════════════════════════════════
EXAMPLE 8: SPEND LEDGER - FULL PAID LIFECYCLE
══════════════════════════════════════════════════════════════════

Ceiling is minor currency units (5000 = USD 50.00), recorded by the operator
before any work. Subcommands: init_run, plan, reserve, mark_unknown, cancel,
mark_submitted, mark_terminal, reconcile, summary, can_spend, park_run,
unpark.

  SL="python3 scripts/core/spend_ledger.py --db run/spend.sqlite3"

  $SL init_run --run demo-run --ceiling 5000 --currency USD
    -> exit 0, OK
  $SL plan --run demo-run --key music/suno/verse1 --attempt a1 \
      --digest <64-hex request digest> --est 600 --stage music
    -> exit 0, OK, next_action "reserve before dispatch"
  $SL reserve --run demo-run --key music/suno/verse1 --attempt a1
    -> exit 0, OK, next_action "dispatch only against this reservation"
  $SL mark_submitted --run demo-run --key music/suno/verse1 \
      --attempt a1 --remote-id task_demo_1
    -> exit 0, OK
  $SL mark_terminal --run demo-run --key music/suno/verse1 \
      --attempt a1 --outcome succeeded
    -> exit 0, OK
  $SL reconcile --run demo-run --key music/suno/verse1 --attempt a1 \
      --final succeeded --actual 600 --provider-ref task_demo_1 \
      --evidence-ref receipts/verse1.json
    -> exit 0, OK
  $SL summary --run demo-run
    -> exit 0: actual_cost 600, remaining_budget 4400, currency USD,
       provider_cost_by_stage {"music": 600}, run_status active

RULES THE LEDGER ENFORCES (observed, not aspirational):

  - duplicate reserve of a reserved key -> exit 5, BAD_TRANSITION
    ("state reserved cannot reserve")
  - can_spend past the ceiling -> exit 5, BUDGET_EXCEEDED
    ("budget violation parks the run instead of continuing")
  - park_run -> exit 4 (parked); afterwards can_spend -> exit 5, RUN_PARKED;
    unpark -> exit 0. Only an operator unparks.
  - reserve BEFORE every paid submission; reconcile to actual AFTER.
  - unknown provider outcome: mark_unknown, never resubmit (directive 18).

──────────────────────────────────────────────────────────────────
EXAMPLE 9: QC GATE - THE FIVE OUTCOMES
──────────────────────────────────────────────────────────────────

Records are qc-schema v1.0.0 objects (see scripts/core/contracts/
qc-schema.json): schema_version, check_id, run_id, stage, check, verdict
(PASS|FAIL|UNAVAILABLE), evidence.summary, checker_version, reviewer
{identity, session, authority}; a timing record additionally needs
timing_detail {sample_ref, confidence, annotation_method}.

  python3 scripts/core/qc_gate.py evaluate \
    --run demo-run --stage music \
    --records records.json \
    --makers makers.json \
    --required lyrics,song \
    --critical lyrics,text_product

makers.json maps check_id -> maker identity (from artifact provenance).

Observed outcomes (records.json / makers.json varied per case):

  1. all required PASS, reviewer != maker
     -> exit 0, ALL_REQUIRED_PASS, next_action "advance stage"
  2. one required FAIL
     -> exit 5, CHECK_FAIL, repair_scope=["ck-lyrics"],
        next_action "repair checks ck-lyrics with new attempt ids;
        approved assets stand"  (targeted repair, directive 17.7)
  3. UNAVAILABLE on a required check
     -> exit 5, UNAVAILABLE_MANDATORY,
        "hand back: UNAVAILABLE_MANDATORY; same records cannot pass"
        (UNAVAILABLE never becomes PASS - directive 17.8)
  4. reviewer identity == maker
     -> exit 5, MAKER_SELF_REVIEW (independent verifier law, 17.6)
  5. required check with no record
     -> exit 5, MISSING_QC
  6. timing record missing timing_detail
     -> exit 5, SCHEMA_VIOLATION
  7. --profile profile.json with --expect-profile 2.0.0 while profile says 1.0.0
     -> exit 5, PROFILE_MISMATCH

Gate PASS needs EVERY required check to pass. Averages never erase a
critical defect (lyrics, text_product by default: critical failures are
listed in evidence.critical_failures, never weighted away).

──────────────────────────────────────────────────────────────────
EXAMPLE 10: JOB RECOVERY - POLL, NEVER RESUBMIT
──────────────────────────────────────────────────────────────────

  JR="python3 scripts/core/job_recovery.py --db run/spend.sqlite3"
  # (same DB the spend ledger writes: job rows are ledger rows)

  $JR ingest_event --run demo-run --key music/suno/verse1 --attempt a1 \
      --event-id evt_1 --seq 1 --status complete \
      --payload '{"result":{"audio_url":"https://example.com/verse1.mp3"}}' \
      --artifact artifacts/verse1.mp3 --sha abc123 --bytes 10
    -> exit 0, OK, evidence.state=submitted
  $JR ingest_event ... same --event-id evt_1 again
    -> exit 0, DUPLICATE_EVENT, "event already applied; no state change"
  $JR ingest_event ... --event-id evt_0 --seq 0 --status progress
    -> exit 0, STALE_SEQ, "older than applied seq 1; recorded, not applied"
  $JR recover --run demo-run
    -> exit 0, OK, next_action "resume from last incomplete stage;
       no job re-dispatched"; evidence.jobs[0].action=POLL,
       "polling is distinct from resubmitting"
  $JR recover --run no-such-run
    -> exit 1, NO_SUCH_RUN

Before remote task IDs exist, recovery only BLOCKS - it never
auto-resubmits an uncertain submission.

──────────────────────────────────────────────────────────────────
COMMON MISTAKES TO AVOID
──────────────────────────────────────────────────────────────────

MISTAKE 1: Applying one exit map to every tool.
  WRONG: treating spend_ledger/qc_gate exit 4 as factory.py's "parked" when
         reading a rejected record, or factory.py exit 2 as a ledger code.
  RIGHT: read `command` first, then that CLI's map (two tables above). The
         same numeric code means different outcomes: factory 4 = rejected,
         ledger/qc_gate 4 = parked.

MISTAKE 2: Treating the intake digest or a brief budget as authorization.
  WRONG: preflight without --auth-file because "the brief said 5000".
  RIGHT: auth_status=missing until an authorization object binds scope to the
         digest; preflight then refuses with approval-missing.

MISTAKE 3: Dispatching a paid job without a ledger reservation.
  WRONG: provider call first, ledger later.
  RIGHT: init_run -> plan -> reserve, dispatch against the reservation,
         then mark_submitted / mark_terminal / reconcile.

MISTAKE 4: Resubmitting after an unknown provider outcome.
  WRONG: retry the Suno/video call "because nothing came back".
  RIGHT: mark_unknown (spend_ledger) and recover/POLL (job_recovery).
         Directive 18: unknown never auto-resubmits.

MISTAKE 5: Letting a maker grade its own artifact, or swapping in a fresh
         reviewer for a failed record without new evidence.
  WRONG: reviewer identity == maker, or re-running the same FAIL record.
  RIGHT: a fresh independent reviewer with session + authority, and NEW
         attempt ids for repaired checks (MAKER_SELF_REVIEW and same-record
         retries are rejected by the gate).

MISTAKE 6: Inventing commands.
  WRONG: invoking timing_guard / state_store / artifact_graph / cc_sync as
         if they were CLIs, or any delivery_verify.py / release_check.py
         invocation.
  RIGHT: the four CLIs listed at the top; everything else is an import or
         not shipped yet.

MISTAKE 7: Reading a passing preflight as "the video was generated".
  RIGHT: preflight NEVER submits generation. API success is not quality
         success - run the QC gates (QC.md, section 17 evidence gates).

──────────────────────────────────────────────────────────────────
WORKED EXAMPLE: NATIVE RATE AND DUPLICATE FRAMES BEFORE SPEND
──────────────────────────────────────────────────────────────────

Duplicate frames are generated inside a clip, at that clip's own native rate.
A timeline conform cannot remove them, so the measurement is a CLIP-SIDE gate
that runs before any conform and before assembly, never a timeline-rate change.

What is measured, and when
1. Before any paid step, record the clip's native rate from the model: MiniMax
   H3 and Hailuo 02 Standard are native 24 fps; a Kling clip carries its own
   native rate (30 for the Kling standard model). It is read from the model,
   never guessed.
2. When each clip lands, measure its duplicate frames with the existing
   mpdecimate procedure in `final_assembler/fps_conform.py`, under
   `load_governor`. A clip over the 2 percent cap is refused and remade
   clip-side (retake or replace); it never enters the timeline.
3. A deliberate still is declared `hold` so its held frames are not counted as
   defects. Hold spans are declared in the shot's storyboard row before the clip
   is measured.

The non-30 timeline escape
`fps_set_by_choice_card` is the only path to a timeline rate other than the
master's native rate, and it passes only when all three hold: the run owner
recorded the rate on the choice card; every clip's native rate equals the
chosen rate or is matched by plain frame repeat or drop; and every clip's
mpdecimate duplicate ratio was measured and is under the cap before assembly.
A timeline that fails any of the three is refused (`TIMELINE_FPS_NOT_30` or
`TIMELINE_DUP_FRAMES`). It is never used to hide duplicate frames. Every clip
is still measured at its own native rate first.

A segment report line
For each clip the segment report records: shot id, native rate, measured
duplicate count, cap pass/fail, any declared hold span, and the action taken
(kept, remade clip-side). A per-segment count over the cap is advice only while
the whole master stays under the 2 percent cap (N-15); it is never a reason to
change the timeline rate.

MISTAKE: Fixing duplicate frames with a 24-to-30 conform.
  WRONG: motion-interpolating a native-24 clip up to a 30 fps timeline to
         "smooth" it, or re-timing the timeline to drop frames.
  RIGHT: remake or replace the clip; match a different-rate clip with plain
         frame repeat or drop only.

──────────────────────────────────────────────────────────────────
WORKED EXAMPLE: THE BUILD-RECORD A DELIVERED RUN SHIPS
──────────────────────────────────────────────────────────────────

Every delivered run ships a BUILD-RECORD a reader can reproduce the master
from. It is written from verified facts, never a summary. Fields:

  job                   run id and the brief it came from
  assembler             path + SHA-256 of the file that ran
  commands              exact commands, verbatim
  timeline              SHA-256 of edit/timeline.json + TIMELINE_WRITTEN
  shots                 one row per shot, on-disk SHA-256 of every input
  gate results          every gate's verdict per stage, with code(s)
  refusals              every refusal and how it was cleared (or not), by code
  corrections           what changed after a gate, and why
  not done by design    checks/steps deliberately not run, named
  concurrent writer     which writer owned which output file
  credit reconciliation reserved vs actual per stage + ledger totals
  verification status   measured / UNAVAILABLE / passed by a person
  measurement renders   the renders used as measurements, with paths
  files delivered       every delivered file with its SHA-256

A BUILD-RECORD a reader could not reproduce the master from is a provenance
FAIL, the same as a missing assembler receipt.
══════════════════════════════════════════════════════════════════

## Worked example: a 3-minute Soul Ballad campaign run

One 3-minute Soul Ballad song ad on a method run. The sheet below is the run's own sheet,
with only three things replaced by placeholders: the coach's name is `[Coach]`, the named
product and package are `[Offer]`, and the website is `[website] dot [tld]`. The persona,
the words, the section order and the timings are the run's own. "Uncle Sam" is the IRS,
not a client.

**The persona line** (the brief's audience, one line, copied not paraphrased):

  a career professional woman: she has the degree, she works 40 hours plus overtime
  and a second job, she carries the bills and the family, and she has nothing to show
  for it

**The sanitized sheet**, in the order it was written. The hooks repeat one two-line motif;
they are shown condensed as `Hook 1` and `Hook 2`, then the `Bridge`, then `Hook 3` and
`Hook 4` - the real order is Hook 1, Hook 2, Bridge, Hook 3, Hook 4, and the Bridge is
between the second and third hook, not after all four:

  [Intro (spoken): plain natural speaking voice, weary and close, soft felt piano only,
   no melody, no singing yet]
  Forty hours, overtime, a second job, and my account still says zero.

  [Backstory (spoken): same weary speaking voice, slow, a pause after every line, low
   strings tighten under the piano, no melody, no singing yet]
  My babies need new shoes, my mama needs her pills, and they all lean on me.
  I got the degree, played the game, and I'm still drowning.
  Insurance, car note, rent, taxes, and nothing left for me.
  Then April comes, and Uncle Sam's letter lands on my counter.

  [Verse 1 (sung): the groove drops in here, heavy half-time with a deep kick,
   first sung line lands on the drop, raw close vocal]
  I work too hard to not have nothing
  I work too hard to be stressing like this
  no trips for me, no retirement
  my friends are living, I pay rent

  [Pre-Chorus 1 (sung): pressure rises, ticking pulse, aching lift]
  I work, I work, I work all day
  they tax, they tax, I pay, I pay

  [Verse 2 (sung): slow and close, bitter and heavy]
  Uncle Sam don't care how hard I'm working
  don't care about the family I'm raising
  in the end he leaves me nothing

  [Pre-Chorus 2 (sung): key change up, drums pull back, space opens, relief and
   possibility]
  [Coach] gave me the key
  her [Offer] keeps my money
  (annotation, not a lyric line: the hero enters here)

  [Hook 1 (sung): full voice, the hook lands at full arrangement]
  Keep my money, no more fear
  my cushion growing this year

  [Hook 2 (sung): same motif, full voice]
  Keep my money, no more fear
  my cushion growing this year

  [Bridge (sung): stripped back, steady and sure]
  I answer his letter
  my babies sleep better

  [Hook 3 (sung): same motif, full voice]
  Keep my money, no more fear
  my cushion growing this year

  [Hook 4 (sung): same motif, full voice, the last one]
  Keep my money, no more fear
  my cushion growing this year

  [Outro (spoken): plain speaking voice, no melody, the band keeps playing softly]
  Go to [website] dot [tld].
  Claim the [Offer].

**The spoken opening, counted.** 12 spoken words in the Intro, 48 in the Backstory: 60
spoken words before any sung word. At the style's planned spoken rate (1.85 words/s) that
is 32.4 s planned, against `control/method.json`'s ERM apex of 32.5 s (window 25-40 s). The
Intro is 12 words on purpose: it is `opener_max` without a method and enough to set the
room, and the Backstory is what carries the pain. A single spoken Intro cannot hold the
opening: 12 words lands singing at about 5 s, which is exactly the measured failure below.

**Measured, not assumed - and judged, not assumed.** Six takes were generated and each was
measured by word timing (`first_sung.measurement.source` = `word_timing`, faster-whisper
`small`). The first sung line, "I work too hard to not have nothing", measured at 38.0 s,
39.0 s, 40.8 s, 42.9 s, 44.5 s and 46.0 s. All six are past the 30-second rule and past
the 32.4 s plan; real speech runs slower than the planned rate, so the takes land later
than planned, and the gap is recorded, not argued about. The singing detector alone
reported 0-10 s on the same takes, because it heard the spoken backstory over the piano as
melody: the word timing is the measurement and the detector is only the fallback.

**The six takes are not a pass under the current window.** `judge_first_vocal_at_erm`
marks a method take early or late and fails both. Its window here is
`[apex - 1.5 s, apex + 1.5 s]`, i.e. `[31.0 s, 34.0 s]`, so every one of the six takes
scores **FAIL, late** ("late, redo"):

- 38.0 s: 5.5 s after apex 32.5 s (window 31.0-34.0 s): late, redo
- 39.0 s: 6.5 s after: late, redo
- 40.8 s: 8.3 s after: late, redo
- 42.9 s: 10.4 s after: late, redo
- 44.5 s: 12.0 s after: late, redo
- 46.0 s: 13.5 s after: late, redo

The example copies the measurement and states the verdict; it does not call these takes a
pass. The recorded result keeps each FAIL as FAIL - no measured gate is rewritten to PASS.
The run moved on because `first_sung` is emitted by the take judge but is not in
`REQUIRED_TAKE_GATES`, so the delivery decision `take_accepted` does not check it: the
late FAIL is written into the take's own gate record and the take is not stopped by it. The
operator-decision record cannot cover this gate either - its `gates_not_proven` accepts
only D1-D5, so `first_sung` is not nameable there. That gap is an open defect: until
`first_sung` is delivery-required, a late FAIL is recorded and does not stop delivery.

**Known conflict (open defect) - the late bound contradicts the operator's rule.** The
operator's rule is a floor: the first sung word is at or after 30 s. The code adds a late
bound at `apex + 1.5 s` = 34.0 s, which is 4 s stricter than the 30-second floor. A take
the operator calls good at 38-46 s therefore scores FAIL "late, redo" in code. The two
bounds must be reconciled before the example can be copied as a pass: either the code's
late bound moves (the operator's rule is a floor only) or the plan's apex is set so the
window's high end covers the measured landing. Until then, treat these takes as **measured
and recorded as FAIL**, never as an accepted pass.

**Which lines were the client's own.** Four, all cleaned only for grammar and meter and
all kept in the pain sections, original next to cleaned:

- "I work too hard to not have nothing" - kept word for word.
- "I work I work I work, they tax they tax they tax, I pay I pay I pay" became
  "I work, I work, I work all day / they tax, they tax, I pay, I pay".
- "insurance, car notes, rent, taxes and nothing left for me" became "Insurance, car
  note, rent, taxes, and nothing left for me."
- "Uncle Sam doesn't care about how hard I work, he doesn't care about the family I'm
  raising, and at the end he leaves nothing for me" became "Uncle Sam don't care how hard
  I'm working / don't care about the family I'm raising / in the end he leaves me
  nothing".

The rest of the sheet is the writer's, built on those lines and on the brief's audience.

**The three instructions that tell Suno to wait** - all three are needed, and all three
are in this sheet:

1. **Every spoken cue ends "no melody, no singing yet"**, with sparse instruments named
   (soft felt piano, low strings). The Intro and the Backstory both carry it; that is what
   keeps the first 30 seconds spoken.
2. **The first sung cue says "the groove drops in here, ... first sung line lands on the
   drop"** - here "the groove drops in here, heavy half-time with a deep kick, first sung
   line lands on the drop". The writer writes this cue; it is what makes Verse 1 the
   entrance instead of another spoken line.
3. **The final style carries "no singing until the groove drops"**, written by
   `suno_recipe.method_pace_clauses` from the run's pace plan and enforced by
   `song_contract.check_pace_style` before any spend.

**What failed before this run, and which row catches it now:**

- **The wrong persona.** Earlier rounds were written for a nail tech / hustler instead of
  the degree-holding professional the brief names. Caught by the persona row.
- **The pain rushed into the solution.** Pain was summarized in one or two lines and the
  hero arrived immediately. Caught by the five-pain-details and two-sung-pain-sections
  rows.
- **A 12-word Intro and then singing**, measured at about 5 s: no Backstory, no
  groove-hold in the style, and the sung Intro line became a verse. Caught by
  `check_pre_erm_opening` (`PRE_ERM_SPOKEN_SHORT`), by the style's
  "no singing until the groove drops" clause (`PACE_DIRECTION_MISSING`), and by the
  first-sung gate.
- **The timing could not be read at all.** Word timing failed silently for hours because
  faster-whisper `small` was never installed on the box, so first-sung was judged on the
  singing detector and mis-scored the spoken backstory. That is `WORD_TIMING_UNAVAILABLE`:
  stop and fix the install, never accept a guessed time.
