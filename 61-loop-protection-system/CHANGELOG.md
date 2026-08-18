# Changelog - Loop Protection System (Skill 61)

All notable changes to this skill. The skill versions independently of the repo
line (its own `skill-version.txt`), like Skill 60.

## [0.6.0] - 2026-08-18

New loop class **LP-A10: agent-to-agent cross-run resend loop**, closing a real
incident verified live on a client box on 2026-08-04. Repo-only change (this
skill's rollout gate stays HELD, `config/rollout.json` unchanged); no box is
armed, activated, or touched by this release.

**Merge-forward note.** This work was written and reviewed on 2026-08-04
against `LP-A8` / `LF-9`, the first free ids at the time. `main` moved 448
commits in the two weeks this sat as a PR, and the very next day (0.4.0,
2026-08-05, below) independently claimed **both** those ids for an unrelated
class — D5's self-blocking flush-run / transcript-poison detector. That is a
genuinely different fault (a run wedged against the runtime's own identical-
call guard, filling its OWN transcript with refusals) from this one (an
orchestrator misreading a cross-agent delivery timeout and resending as a
brand-new top-level run) — same `F15` taxonomy family, different mechanism,
different detector, different remediation. Reconciled by renumbering this
release's ids forward to the next free slots, `LP-A10` / `LF-12` (family A
already reached `LP-A9` and fix classes `LF-11` by the time of this merge) —
every reference below, in code, config, docs, and tests, reflects the
renumbered ids; nothing else about the design, thresholds, or mechanism
changed.

**The incident.** An orchestrator agent routed work to a department agent via
`sessions_send`, then waited. `sessions_send` falls back to a HARDCODED 30000ms
timeout when the caller omits `timeoutSeconds`. The target department was busy
and did not reply within 30s. The orchestrator misread the LOCAL TIMEOUT as a
DELIVERY FAILURE and re-sent the byte-identical message as a BRAND-NEW
top-level run - 6-8 times, ~34s apart (30s timeout + ~4s overhead is the resend
cadence fingerprint). The victim department churned past 154,000 input tokens
with no brake. Nothing caught it: OpenClaw's own `tools.loopDetection` counts
repeated tool calls WITHIN one run, and `session.agentToAgent.maxPingPongTurns`
bounds the INNER exchange of a single `sessions_send` call - every resend here
was a separate top-level run id, so both counters reset to a clean slate each
time. Zero firings across a 57MB gateway log while the loop was raging; tuning
either existing threshold is a structural no-op for this class.

**The detection signal (proven on the live box).** Every inbound cross-agent
message the gateway delivers is stamped in the RECEIVING agent's session
transcript as `message.provenance = {kind:"inter_session",
sourceTool:"sessions_send", sourceSessionKey:...}` - structural, and present
regardless of what the sending side logged (a resend is a fresh run at the
sender, so nothing the sender wrote survives the resend boundary; only the
receiver's transcript does).

**Post-push correction (same day, before merge).** A second verification pass
against a LIVE OpenClaw 2026.7.1-2 box checked this release's two remaining
"plausible, confirm during burn-in" items and found one right and one wrong:
the provenance/payload shape was CONFIRMED CORRECT as designed (see the
tightened field list below); the abort mechanism was NOT - `openclaw sessions
--help` on that box lists only `cleanup / compact / export-trajectory / list`,
there is NO `sessions abort` CLI subcommand, so the originally-shipped
`openclaw sessions abort --session <key> --json` call would have failed on
every invocation and, because it was designed to fail soft, would have
returned `{ok:false}`, applied only the park, and LOOKED fine while never
actually aborting anything - precisely the silent-no-op failure mode this
skill exists to prevent. Both are fixed below before this ever merged; no box
was ever armed with the wrong command (repo-only PR, rollout gate HELD).

Added:
- **D7 - cross-run resend (provenance-stamped)** (`loop_detectors.py
  :: d7_cross_run_resend`). Reads AGENT SESSION transcripts
  (`agents/*/sessions/*.jsonl` - a DIFFERENT stream from the
  `*.trajectory.jsonl` event log D1-D4 read; a bare `*.jsonl` glob is
  explicitly filtered to exclude the trajectory suffix), offset-tracked
  (`loop_watchdog.py :: collect_cross_run_sends` / `_read_new_session_rows`,
  its own `loop-sess:<path>` cursor namespace, never colliding with D3's
  `loop-traj:<path>`), bounded to recently-modified files - cheap enough for a
  60s cadence even though it currently rides the existing 15-minute tick (no
  new cron/pulse-lane is added by this release; see Known gaps below). Groups
  by (source, target, normalized-payload-hash) and slides a 300s window over
  each group's DISTINCT run ids; `>= 3` inside the window is loop-confirmed P1,
  `== 2` is WARN-only, and a genuine multi-message handoff (distinct payload
  hashes per send) never accumulates a group at all - conservative by default.
  D5 and D6 landed independently on `main` on 2026-08-05 (self-blocking
  flush-run / transcript poison, and semantic retry burst - see the
  merge-forward note above); D7 is unrelated to both and does not consume
  either detector number.
  **Field shape CONFIRMED against a live OpenClaw 2026.7.1-2 box** (real
  captured row, not a guess): top-level row `{type, id, parentId, timestamp,
  message}`; `message: {role, content, timestamp, provenance}`;
  `message.provenance = {kind:"inter_session", sourceSessionKey,
  sourceTool:"sessions_send", [sourceChannel]}`; qualifying rows are
  `role:"user"`. The confirmed path is now PRIMARY in every candidate list
  (`_PROVENANCE_PATHS`, `_PAYLOAD_PATHS` -> `message.content`,
  `_TIMESTAMP_PATHS` -> `timestamp` not the old guessed `ts`), with the prior
  guesses kept only as defensive fallbacks. `sourceChannel` is CONFIRMED
  optional (present on one live sample, absent on another) and is never read
  or required - its absence cannot cause a miss (drilled in
  `loop_watchdog.py`'s self-test: one resend row carries it, two don't, all
  three still match). There is no confirmed per-run identifier field on this
  row shape (no `runId`); the row's own `id` (confirmed present on every row)
  is used as the run/delivery identifier instead - `runId`/`run_id` are tried
  first only in case a differently-enveloped row attaches one directly.
  `loop_common.py :: parse_iso8601` was hardened to also accept a numeric
  epoch timestamp (seconds or milliseconds, including as a numeric STRING)
  as a defensive fallback alongside ISO-8601, since the `timestamp` field
  NAME is now confirmed but its VALUE shape was not independently verified.
- **Never-log-raw-body boundary** (`loop_common.py ::
  normalize_inter_session_payload` / `cross_run_payload_hash`). The raw
  message body - which can carry a live client credential pasted
  mid-conversation - is normalized (leading bracketed preamble stripped,
  whitespace collapsed) and SHA-256 hashed (16-hex, matching
  `signature_hash`'s truncation) INSIDE the collector, one call, one stack
  frame; unlike D3 (whose structural fields carry no client content), the
  hash boundary sits at the collector here so the raw text never crosses into
  a detector, a finding, the ledger, or any log line anywhere in this skill.
- **LF-12 - abort + park** (`loop_killcards.py :: lf12_abort_cross_run_resend`,
  Tier 1, config-free like LF-6, so it applies for real in-tick on an armed
  box). Calls the native `sessions.abort` RPC on the resending SOURCE
  session's in-flight run via **`openclaw gateway call sessions.abort
  --params '{"key":"<session-key>","agentId":"<agent-id>"}'`**
  (`_sessions_abort_via_gateway_rpc`; `agentId` is best-effort-extracted from
  the session key's own `agent:<agentId>:...` shape via
  `_agent_id_from_session_key`) then parks the source unit visible-red. NEVER
  pkill node, NEVER restarts the gateway. **CONFIRMED live** (OpenClaw
  2026.7.1-2, 2026-08-04): `openclaw sessions --help` lists only
  `cleanup / compact / export-trajectory / list` - there is no `sessions
  abort` CLI subcommand, so this is the ONLY real call path (`openclaw
  gateway --help` -> `call  Call a Gateway method`); exercised live against a
  session with no active run and confirmed to return
  `{"ok":true,"abortedRunId":null,"status":"no-active-run"}` - a documented
  SAFE no-op, so it is safe to call speculatively. Response parsing
  (`_rpc_signals_success_or_noop`) treats `status:"no-active-run"` as a
  SUCCESSFUL no-op independent of whether `ok` is also present - never a
  failed fix, never a retry trigger; only the healer breaker (>3 fixes on the
  same target/24h, or any verify failure) governs whether LF-12 fires again. A
  600s action cooldown (the incident's own proven-safe spacing) is enforced
  via the ledger's EXISTING digest/dedup primitive (the same one the alert
  path uses) - a second call inside the window is REFUSED, never re-applied.
  `run_fix()`'s `fix <finding-id>` operator path gained a matching `fc ==
  "LF-12"` branch (mirrors the LF-6 branch exactly).
- **`resend` breaker** (`config/breakers.json`, `loop_breaker.py ::
  resend_breaker_trips`) - the independent ceiling-copy predicate every other
  breaker carries (the S4 cap-raise-without-stamp pattern).
- **`config/thresholds.json :: d7_cross_run_resend`** - `window_seconds: 300`,
  `warn_repeat: 2`, `p1_repeat: 3`, `action_cooldown_seconds: 600` - the
  proven-safe values from the live incident.
- **`config/signatures.json` / `docs/LOOP-CLASS-CATALOG.md`**: `LP-A10`
  registered (family A, `F15` - the taxonomy's next LP-introduced extension
  after `F14`=LP-A1, per SKILL.md's "F14+" rule - `LP-A8`/`LP-A9` having since
  been claimed by D5/D6, see the merge-forward note above), detector `D7`,
  tier default 1.
- **Tests**: `tests/fixtures/cross-run-resend.sends.json` (3 groups: a 3-send
  true positive, a 2-send below-threshold pair, and a 3-message legitimate
  fan-out with distinct payloads) + `tests/drills/D-RESEND.md`, wired into
  `verify.sh` step 3 (now twenty-three drills, alongside D5/D6's own nine
  landed 2026-08-05) and into `loop_detectors.py` /
  `loop_watchdog.py` / `loop_killcards.py` / `loop_breaker.py`'s own
  `--self-test`s.

Known gaps (stated plainly, not silently dropped; updated after the live-box
verification pass above - two of the original three are now CONFIRMED, not
just plausible):

1. **Still open, unchanged.** D7 rides the EXISTING 15-minute tick, not a
   dedicated 60s pulse-lane cron. It is built cheap enough to run at 60s
   (offset cursors, recent-mtime file filtering, no gateway-log tail) but no
   new cron/pulse-lane infrastructure ships in this release - that remains a
   separate, larger change. D5/D6 (landed 2026-08-05) also ride the same
   15-minute tick, not a dedicated pulse lane.
2. **RESOLVED - confirmed correct, not merely plausible.** The provenance /
   payload field shape (`message.provenance`, `message.content`,
   `role:"user"`, optional `sourceChannel`) was independently verified
   against a live OpenClaw 2026.7.1-2 box's real captured session row and
   matches this design exactly; the confirmed path is now primary in every
   candidate list (see the D7 "Field shape CONFIRMED" note above). What
   remains genuinely unconfirmed on this row shape: whether `timestamp`'s
   VALUE is always an ISO-8601 string (the FIELD NAME is confirmed; the value
   shape is defended, not proven, by the new numeric-epoch fallback in
   `parse_iso8601`), and whether a `sourceSessionKey` is ever shaped
   differently from the observed `agent:<agentId>:<channel>:<mode>:<kind>:
   <chatId>` convention `_agent_id_from_session_key` relies on.
3. **RESOLVED - was a real, confirmed defect; now fixed.** The abort
   mechanism originally called a `sessions abort` CLI subcommand that does
   not exist on a live box (`openclaw sessions --help` lists only
   `cleanup / compact / export-trajectory / list`); because the call was
   designed to fail soft, this would have silently returned `{ok:false}`,
   still applied the park, and reported the fix as "applied" while never
   actually aborting anything on a live box - exactly the silent-no-op
   failure mode this skill exists to catch in OTHER systems. Replaced with
   the verified real path, `openclaw gateway call sessions.abort --params
   '{"key":"<session-key>","agentId":"<agent-id>"}'`, independently exercised
   live and confirmed to return `{"ok":true,"abortedRunId":null,"status":
   "no-active-run"}` against a session with nothing to abort - a documented
   safe no-op. The `agentId` param's extraction from the session key
   (`agent:<agentId>:...`) is a best-effort convention inferred from the one
   live sample seen; a session key of a different shape degrades to using the
   whole key as `agentId` (never a crash), and the RPC call itself remains
   best-effort - an unreachable/wrong response still parks the source (the
   park, not the RPC, is what actually breaks the loop).

## [0.5.0] - 2026-08-05

**The post-update restore-verify script lands in the skill.**

`openclaw update` reinstalls node_modules and silently reverts the dist patch that makes
a runaway tool loop actually abort; it can also regenerate the gateway service-env file.
Until now the only record of how to put that protection back was a scratch file. Two new
files:

- `scripts/openclaw-loop-protection-restore.sh` — detects all nine pieces of the
  protection stack (dist runaway-abort patch, the Telegram spooled-handler turn timeout,
  memory-flush journaling and its byte-exact prompt hints, the six loop-detection
  thresholds plus any per-agent override that would silently beat them, the daily
  memory-stub guard and its cron registration, the `ceo-routing-doctrine` plugin, and
  that the retired CEO intent-gate has not resurrected). Read-only by default; `--apply`
  repairs only what is safe to repair. Exit 0 clean / 3 drift / 4 hard fail / 2 usage.
  It NEVER restarts the gateway — it says a restart is needed and stops.
  Fail-loud by design: if a dist anchor is neither found nor already-applied it reports
  `UPSTREAM_CHANGED` and refuses to patch rather than guessing.
  Section 9 also flags the failure shape that caused the two-week outage from the other
  direction — a `tools.allow` list that OMITS `write` — and deliberately does not
  auto-fix it, because an agent's tool grants are the operator's call.
- `tests/secret-leak-test.sh` — builds a fake HOME whose secret-bearing files are stuffed
  with unique tracer strings, stubs the `openclaw` CLI so every config read returns
  tracer-laden output, runs the restore script in BOTH modes, and asserts no tracer
  reaches stdout, stderr, or any written file. Carries its own 4/4 instrument control so a
  pass cannot be a silently-broken test. The one sanctioned exception is the mode-600
  backup of the secrets file itself, which is asserted to be a faithful copy.

Hardening applied before commit: two predictable `/tmp/<name>.$$` staging paths were
replaced with `mktemp`. A PID-named path in a world-writable directory is a
symlink-clobber target, and one of those values is fed straight back into
`openclaw config set`.

Portability: every path derives from `$HOME` or the resolved `openclaw` binary. No
hostnames, client names, chat IDs, tokens, or machine-specific absolute paths — clean
under all three repo scanners (client-identifiers, secrets, json-exports), each run
with its own `--self-test` control.

## [0.4.0] - 2026-08-05

**D5 - the first detector in this skill that measures a STOCK instead of a flow.**
D1-D4 all count events per tick: they answer "is a loop running right now?" and go
quiet the moment it pauses. That leaves a real gap, and an operator-box incident
walked straight through it - a run wedged against the runtime's own identical-call
guard filled a session transcript with ~1,100 of its own refusals, and because the
model reads that transcript back as its own history, every later turn on it stayed
degraded after the run was long dead. Three fixes aimed at the ENVIRONMENT were
deployed during that incident and none ended it, because the fault was in the
CONTEXT. D3 hashes the new-bytes-since-last-tick slice, so once the loop paused D3
reported all-clear on a transcript that was still ~72% wreckage.

**ARMED on the operator box; fleet rollout still HELD** (`config/rollout.json`
`fleet_rollout_enabled` stays `false`, awaiting a separate explicit operator GO).

### A correction to this entry's own premise, recorded on purpose

D5 was first specified against the theory that accumulated transcript poison was
the PRIMARY cause of that incident. **That theory was refuted before this shipped**
and the detector was redesigned rather than quietly re-labelled. The counterexamples
were decisive: the first burst ignited from a context measured at 0% loop text, and
the fully-poisoned session still answered a normal question correctly in seconds.
Poison was neither necessary nor sufficient. The apparent "clean experiment" behind
the original theory was confounded - the fast reply came from a brand-new session
created seconds after the old one died, so the variable that actually moved was
conversation-lane occupancy, not transcript cleanliness.

So D5 ships with IGNITION (a blocked-call burst) as the primary, early, high-
precision face, and poison ratio DEMOTED to a secondary aftermath signal. The
aftermath face is still worth having - it is what persists and what a roll must
clear - but a detector built on it alone fires late, after the damage.

### Added

- **`d5_transcript_poison()`** in `loop_detectors.py` + **`collect_sessions()`** in
  `loop_watchdog.py`, wired into `run_detectors`/`collect_evidence` exactly like
  D1-D4. New loop class **LP-A8** (F15), new **session** circuit breaker, new fix
  classes **LF-9/LF-10/LF-11**.
- The block signature is **STRUCTURAL, never prose**: `details.status == "blocked"`
  and `details.deniedReason == "tool-loop"` on a `toolResult` record. It is
  therefore language- and wording-drift-independent, and no message content enters
  a finding (counts, enum values and tool NAMES only). The blocked tool name is
  recorded but never assumed - both `read` and `tool_call` appeared in the measured
  incident, so nothing hard-codes a single tool.
- **Second carrier detection.** Compaction checkpoint summaries can capture the
  loop verbatim; those are re-injected on resume and **survive a transcript roll**,
  which is why rolling the file alone is not a complete fix. D5 counts them and
  says so in the finding (`SECOND CARRIER`). Measured: 7 of 16 checkpoint summaries
  poisoned in the incident file, 0 of 14 in a healthy control archive.
- **LF-10 auto-roll**: archives a confirmed-poisoned transcript to a timestamped
  name beside it so the next turn starts clean. **MOVE, never delete**; the
  one-line revert moves it back. Guarded by a **live-transcript refusal** - the
  unattended tick can clear yesterday's wreckage but can never roll a conversation
  in progress.
- **Four failable drills** (`D-POISON`, `D-POISON-CLEAN`, `D-POISON-ROLL`,
  `D-POISON-LIVE`) over two new synthetic fixtures, plus `tests/drills/D-POISON.md`.
- **Four more failable drills for the re-roll crash below** (`D-POISON-REROLL`,
  `-BOUND`, `-REFUSAL`, `-TICK`) plus `tests/drills/D-POISON-REROLL.md`, which
  records the tick-by-tick measurement of the crash. Fixtures are synthetic; the
  240-byte session name is generated in the drill.
- **`loop_watchdog.py tick --dry-run`** - forces `armed=false` regardless of ledger
  state, for any caller that must be certain it mutates nothing outside our own
  ledger. `--no-send` was never that flag: it suppresses delivery, not application.

### Fixed

- **LF-10 re-archived its own archive every tick until the filename killed the
  scheduled job. Reproduced before it was fixed, then re-run to prove it gone.**
  `collect_sessions()` globbed every `*.jsonl` under `agents/*/sessions/` except
  trajectories - and an LF-10 archive is a `*.jsonl` in that same directory,
  carrying the same poisoned bytes, with the original mtime preserved by
  `shutil.move`. So the archive re-measured as poisoned AND idle on the next tick,
  D5 raised a fresh P1, and LF-10 archived the archive, appending another
  `.loop-archive-<stamp>` to the name every tick: 26 bytes, 56, 86 ... 236, and on
  the 8th roll `OSError: [Errno 63] File name too long` - **uncaught**, out of
  `tick()`. Two things made that worse than a wasted tick. The healer self-breaker
  could not catch it, because it counts fixes per *unit* and D5's unit is derived
  from the FILENAME, which changed on every roll; and an uncaught `OSError` in a
  scheduled job is not one lost finding but a watchdog that dies every run while the
  box still looks watched. A loop-protection system had built itself a loop. Three
  independent stops now:
  1. `_session_files()` **skips any transcript carrying `ARCHIVE_MARKER`** - an
     archive is finished work and leaves D5's scope permanently. This is the root
     cause; the marker is a module constant in `loop_killcards.py` so the producer
     and the consumer cannot drift apart.
  2. `lf10_archive_and_roll_session()` **refuses a path that is already an archive**,
     and builds its name through `bounded_archive_name()`, which holds the component
     to 255 BYTES (not characters) by truncating the stem and appending a short
     sha256 of the full stem - unique, and deterministic, so a re-run is idempotent
     instead of piling up near-duplicates. A name that already fits is untouched.
  3. `tick()` gives **every finding its own failure boundary**: an exception out of
     the plan/apply/escalate path is counted in the new `errors` field, written to
     stderr, and the tick CONTINUES to the next finding. `lf10` additionally
     converts an `OSError` from the move into a plain refusal, leaving the
     transcript exactly as found.

  It crashed on both interpreters, which matters because a cron `PATH=/usr/bin:/bin`
  resolves the system one: 3.9.6 raises inside the `Path.exists()` pre-flight check,
  3.14.5 survives that and raises in `shutil.move`. Both the fix and the whole
  battery are now proven on **both** (`verify.sh` exit 0 under each).

- **`install.sh` passed a flag that does not exist, so cron registration could never
  succeed - and the failure was invisible.** It called `openclaw cron add --schedule
  "*/15 * * * *"`. Checked against the live binary (OpenClaw 2026.7.1-2, `cron add
  --help` exit 0, 50 option lines): there is **no `--schedule`** - the schedule is
  `--cron` / `--every` / `--at`, or a positional. `--name`, `--command`,
  `--no-deliver` and `--command-cwd` all exist and were confirmed present on the same
  read. So the command exited non-zero every time, and because the whole invocation
  was `>/dev/null 2>&1` the operator saw only `WARN: cron add failed (register
  manually)` with no reason. Now it uses `--cron`, and on the FAILURE path it prints
  the real stderr plus a copy-pasteable manual command. **A diagnostic that discards
  the diagnosis is worse than no diagnostic.**
- **`install.sh`'s "leaves the box in DRY_RUN observe-only" guarantee was false on an
  already-armed box, and its self-test could not catch that.** The post-install tick
  ran `loop_watchdog.py tick --no-send`, and `--no-send` suppresses *delivery* only -
  `armed` still came from the ledger. On a box whose ledger already says
  `armed=true` (which survives a re-install) that line was a **fully armed tick over
  that box's real sessions**, while printing the word DRY_RUN. Three changes:
  a new **`--dry-run` flag on the watchdog CLI** that pins `armed=false` whatever the
  ledger says; `install.sh` uses it, and says so when it detects an armed ledger; and
  the header now claims only what is true - install never *changes* `armed`, it
  cannot promise the box *is* in DRY_RUN.
  The self-test gap is the instructive part: it asserted `armed == False` against a
  **fresh sandbox ledger**, where that is trivially true, so it passed while the
  guarantee was false. It now also installs over a **deliberately armed** sandbox
  **baited with a poisoned transcript aged past the auto-roll floor** - something an
  armed tick would really archive. An empty sandbox could not have caught this
  either: an armed tick with nothing to fix applies nothing however it is invoked, so
  the first version of this assertion was vacuous, and was only found to be vacuous
  by mutation-testing it. Verified failable: dropping `--dry-run` now fails the
  install self-test, and therefore the aggregate gate.

- **`collect_units()` reported a unit's LIFETIME restart count as its per-tick
  delta.** pm2's `restart_time` is cumulative, so the first tick on any real box
  read a long-lived unit's entire history as one storm - a false D1 P1 for every
  unit that had ever restarted, and on an armed box a false park. Restart counts
  are now baselined per unit in ledger meta: first sight is always delta 0, and a
  counter that goes backwards re-baselines instead of spiking. Found while
  assessing whether arming this box was safe; it was not, and this is why. Covered
  by a new self-test case.

### Proven

- **Offline (drills, in `verify.sh`, exit 0):** 22 drills, all four merge-gate
  scanners clean, on **both** Python 3.9.6 (`/usr/bin/python3`, what a cron
  `PATH=/usr/bin:/bin` resolves) and 3.14.5 (homebrew). Each scanner's own
  `--self-test` control was run first and detected its planted violation (a scanner
  that passes everything is not a scanner).
- **Failability, mutation-tested rather than assumed:** raising the D5 thresholds
  out of reach fails all four D5 drills; removing BOTH the silence rule and the
  size guard fails `D-POISON-CLEAN`. Honestly noted in `D-POISON.md`: removing
  either guard *alone* is masked by the other, so no single mutation catches it -
  the two are redundant by design.
- **The re-roll drills were proven in both directions.** Run against the pre-fix
  scripts they reproduce the production fault and fail the battery (exit 4, `Errno
  63` on the 8th roll) while the pre-fix self-tests still pass - i.e. the old
  battery was blind to it. Four one-at-a-time mutations of the fixed tree each kill
  their own drill and no other: restoring the collector's blind spot fails
  `D-POISON-REROLL`; weakening `NAME_MAX_BYTES` 255 -> 10000 fails
  `-BOUND`; removing the `OSError` catch fails `-REFUSAL`; removing `tick()`'s
  per-finding boundary fails `-TICK`. The drills assert 255 as a LITERAL, never by
  reading `NAME_MAX_BYTES`, because a test that takes its ceiling from the code
  under test cannot catch that ceiling being weakened. `D-POISON-REROLL` asserts the
  FINDING count as well as the roll count - with the archive back in scope the kill
  card's own guard still refuses the second roll, so `applied` alone would have
  hidden the defect.
- **Live, read-only, on the operator box** (detector only - `tick()` was never
  called, so LF-10 could not run and no real file was moved):
  - TRUE POSITIVE - the archived incident transcript (4,607,807 bytes) yields
    exactly one P1 `LP-A8`: 275-block ignition burst, 50% trailing-200 share,
    7 poisoned checkpoints.
  - TRUE NEGATIVE (hard control) - a **larger** healthy archive from the same box
    and same agent (17,160,766 bytes, 3.7x the poisoned one, 8x past the flush
    re-arm floor): **0 findings**.
  - TRUE NEGATIVE (breadth) - all 69 live session transcripts for that agent:
    **0 findings**. One carried a single block, correctly below the WARN floor of
    3 and correctly silent.

### NOT verified (stated plainly)

- **LF-9 (abort the run) has never been executed and cannot be.** No supported
  run-abort CLI was found in OpenClaw 2026.7.1-2 (`openclaw sessions` offers
  `cleanup`/`compact`/`export-trajectory`/`list` only). It ships **Tier 2,
  prepare-only**. Aborting is believed to be the highest-value remediation - it is
  what frees the conversation lane, and the runtime rather than the model ended
  most observed bursts - but this skill does not do it today.
- **LF-11 (prune poisoned checkpoints) is prepare-only and was never executed.**
  The live gateway rewrites the session store, so an in-place edit without a
  restart is clobbered.
- **LF-10 has never fired on a real poisoned transcript in production.** It is
  proven on fixtures and by the armed-tick drill; the archived incident transcript
  was rolled by hand before this work began.
- **The re-roll crash was reproduced in a scratch tree, never observed in
  production, and the fix is proven on fixtures only.** No live transcript was
  touched to prove either. The reason it could not have bitten yet is that nothing
  schedules this skill's tick: the operator box carries the ledger
  (`~/.openclaw/loop-protection/loop.db`, `armed=true`) but no installed scripts
  (`~/.openclaw/scripts/loop-protection` does not exist), and no scheduler entry.
  Sources checked for a scheduler: the user crontab (`crontab -l` rc=0, 40 lines, no
  match for `loop-companion`/`loop_watchdog`/`loop-protection`) and
  `~/Library/LaunchAgents` (36 plists). **NOT checked:** the root crontab,
  `/Library/Launch{Agents,Daemons}`, OpenClaw's own cron engine, or any other box.
  One decoy is worth naming: `~/Library/LaunchAgents/ai.openclaw.loop-watchdog.plist`
  fires a file also called `loop_watchdog.py` every 60s, but it is an unrelated
  cross-run resend-loop breaker at a different path with zero Skill-61 markers in it.
  It is easy to mistake for this skill's tick; it is not.
- **The registered cron would run code out of a live git checkout - KNOWN, not fixed
  here.** `install.sh` builds the cron command from `SELF_DIR`, i.e. wherever the
  engine was installed from. Run out of the repo working tree, the scheduled job
  executes whatever that checkout currently has on disk, so **a `git checkout` of
  another branch silently changes the code the watchdog runs** - and a `git bisect`
  or a mid-rebase state could point it at a half-written tree. `--command-cwd` is now
  passed so at least the working directory is explicit, but that pins the CWD, **not
  the code**. Deliberately NOT fixed in this commit: the clean fix is to install the
  engine to a stable path outside any checkout (e.g. `~/.openclaw/scripts/
  loop-protection/`, matching how the unrelated `ai.openclaw.loop-watchdog` launchd
  job is deployed) and register the cron against THAT copy, which is an install-layout
  change and belongs with the registration task, not with a crash fix. **Register from
  a stable copy, not from a branch.**
- **`--cron "*/15 * * * *"` has not been executed against a live gateway.** The flag
  was verified to EXIST (`cron add --help`, exit 0); no `cron add` was run, no job was
  registered, and no cron output was observed - registration is a separate, currently
  blocked task. What is proven is that the old flag could not work and the new one is
  accepted by the parser's help contract on this version.
- The thresholds are derived from **ONE** incident on **ONE** box against that
  box's own healthy corpus. They are measured, not invented, and the derivation is
  recorded in `config/thresholds.json`, but a second incident could move them.
- **No claim is made about which config change prevents recurrence.** Config
  remediation was owned by other work and is not part of this skill.

## [0.3.2] - 2026-07-16

X/U-X3 (U93), D20 Option B: `scripts/loop-protection-canary.sh` renamed to
`scripts/loop-protection-first-proof.sh` (doctrine scrub, "CANARY, THEN HOLD" ->
"PROVE ON THE OPERATOR BOX, THEN HOLD" — this skill's law 8 in `SKILL.md` reworded
to match). A one-release shim is retained at the old path (`exec bash`'s the new
script with `"$@"`, no reimplemented behavior) so a live-box cron still calling
`loop-protection-canary.sh` keeps resolving unchanged; verified byte-identical
output between the old-path shim and the new path. `install.sh`/`update-skills.sh`
persist BOTH files for the one-release window. `HOW-TO-USE.md` and
`config/rollout.json` updated to match. No box behavior change; still DISARMED
(DRY_RUN default, rollout HELD).

## [0.3.1] - 2026-07-13

Field-hardening + doc-honesty correction for the D2 token reader (QC follow-up to
0.3.0). No box behavior changes; still DISARMED (DRY_RUN default, rollout HELD).

Fixed:
- **`_usage_total()` is now a multi-candidate, fail-soft extractor** instead of a
  single hard-coded `usage.total` read. It tries `usage.total` (the CONFIRMED
  emitted aggregate) -> `usage.totalTokens` / `usage.total_tokens` (defensive raw-
  schema aliases) -> the summed component buckets `input+output+cacheRead+cacheWrite`
  (== the writer's own `derivedTotal`). If a future schema drops `total` but keeps
  the buckets, D2 still charges non-zero rather than going silently blind - the exact
  Star-furnace failure mode. Mirrors Skill 60's `_extract_context_tokens` posture so
  the two skills share ONE defensive reader convention. The verified within-run
  cumulative-DELTA charging is preserved unchanged.
- **Doc-honesty**: replaced every "verified against a live box" / "verified live
  values" overclaim in `loop_watchdog.py` and this changelog with the truth. The D2
  token field is **confirmed from the OpenClaw 2026.6.11 trajectory-writer source**
  (`getUsageTotals()` emits `usage.total`; writer `dist/selection-CVIPXpKT.js:14200`
  / `:14217`, shape `:4328-4339`, normalizer `dist/usage-C67Kbb7n.js:44-64`, codex
  `dist/run-attempt-CJMFmJj8.js:5276`). The remaining field names (session triggers,
  cron last-run markers, handoff keys) are honestly labeled plausible OpenClaw-schema
  candidates, read defensively, **to be confirmed on the operator canary during
  burn-in**. This also resolves Skill 60's `_CONTEXT_TOKEN_FIELDS` OPEN QUESTION for
  the token field: the raw `total_tokens` / `input_tokens` guesses are aliases the
  writer consumes but never emits into the trajectory - the emitted field is `total`.

Added:
- **BURN-IN EXIT GATE** documented on `collect_windows()` and in `SKILL.md` doctrine
  7: *before any `arm`, confirm `collect_windows` yields non-zero `paid_tokens` on the
  operator canary's real trajectory* - a live non-zero reading is the arming
  precondition, so a silently-zero feed can never reach an armed box.
- **Two new failable drills** in `verify.sh` + the watchdog self-test:
  `D-COLLECT-DELTA` (a SINGLE runId whose cumulative usage rises 100k->800k, charged
  as the 800k DELTA and NOT the 3.6M naive sum - and carried under component buckets
  only, so it also exercises the derivedTotal fallback) and `D-COLLECT-FALLBACK` (a
  `total_tokens`-only row with no `usage.total`, asserting D2 still charges non-zero).
  Both FAIL against the old single-field reader and PASS after the fix.

## [0.3.0] - 2026-07-13

The collect layer is REAL. `loop_watchdog.py :: collect_evidence()` was a stub
that returned `{"windows": [], "runs": [], "crons": [], "wedge": {}}` - so even a
fully armed watchdog handed D2, D3, and D4 EMPTY evidence on a real box; only D1
(pm2) had a live feed. This is why the 2026-07-13 token-furnace / correction-wave
incident produced zero findings (fix design SS4, finding 2: "the single most
important repo finding"). No box behavior changes until the operator's batched
roll; DRY_RUN/armed/rollout gates all stay intact.

Added:
- **`collect_windows()` (D2 feed)**: hourly paid/local token windows for the
  trailing 24h from the trajectory stream's `model.completed` events. Usage
  totals are CUMULATIVE PER RUN, so each
  completion contributes its DELTA, making a burn visible MID-RUN while the
  looping run is still alive (a run-end-only source sees a furnace only after it
  stops). `trace.artifacts` totals back-fill runs whose completions carried no
  usage - never double-counted. `initiated_sessions` counts only HUMAN-triggered
  `session.started` rows (`data.trigger == "user"`; cron/heartbeat stay
  idle-classified). Windows also carry per-hour `completions` as the future D5
  completion-rate feed.
- **`collect_runs()` (D3 feed)**: offset-tracked NEW-bytes trajectory slice
  (ledger offsets `loop-traj:<path>`, line-boundary safe, rotation-safe) ->
  one signature per finished run from `trace.artifacts`: outcome class + ordered
  tool NAMES (`data.toolMetas[].toolName`) + target. BOTH outcomes collected:
  SUCCESSFUL runs hash as outcome `OK` - the correction wave was "successful"
  turns end to end, invisible to failure-only hashing. Erroring `session.ended`
  rows without an artifacts row are synthesized. Tool names only; arguments and
  message content are never collected.
- **`collect_crons()` + `collect_wedge()` (D4 feeds)**: `openclaw cron list
  --json` (read-only, fail-soft) with OBSERVED fire counting - last-run marker
  transitions persisted in ledger meta over a trailing 24h window; a strict
  lower bound, `None` (silent) until a fire is actually observed. Wedge probe:
  demand-without-progress tick counter (increments only when the slice shows
  prompts/starts with zero completions while the gateway process is up; resets
  on progress; HOLDS on an idle box - idleness is never a wedge) + orphan
  :18789 listener vs the declared supervisor pid in a STALE (expired or >=1h
  old) restart-handoff file; a fresh handoff mid-restart never reports.
- **D3 success ceiling**: `d3_identical_signature` accepts outcome `OK` runs at
  the new `config/thresholds.json` `p1_repeat_success: 10` (failures keep WARN 3
  / P1 5; successes never WARN) - so a heartbeat succeeding once per slice stays
  silent while 10+ back-to-back identical successful turns confirm a loop.
- **`LOOP_NO_PROBES=1` env seam**: disables every subprocess probe
  (pm2/openclaw/pgrep/lsof) so self-tests and drills are hermetic.
- **D-COLLECT drill** in `verify.sh` + collect cases in the watchdog self-test:
  a synthetic loop trajectory (real v20 schema) in a scratch openclaw root must
  yield non-empty windows/runs, D2 must flag the idle paid burn, D3 must flag
  the repeated identical successful turn, and the slice must be offset-consumed.

Changed:
- `collect_evidence(led=None)` now takes the tick's Ledger (offsets + persisted
  counters); with `led=None` (the read-only `audit` path) it PEEKS at bounded
  tails and advances nothing. The D5/D6 attach points (gateway-log model-fetch
  counts; sendguard ledger) are documented in its docstring per the fix design -
  deliberately NOT built here.

## [0.2.0] - 2026-07-10

Repo-side path to live: the machinery is WIRED into onboarding + the updater, but
still HELD by a fleet gate (canary-then-hold, law 8, stays intact). No box is armed
by this change; no client box is activated until the operator flips the gate.

Added:
- **Fleet rollout gate** `config/rollout.json` (`fleet_rollout_enabled: false` by
  default; env override `OPENCLAW_LOOP_PROTECTION_ROLLOUT`). Mechanically enforces
  the HOLD instead of relying on the absence of wiring.
- **Shared activation helper** `scripts/activate-loop-protection.sh` (repo root),
  called by BOTH `install.sh` (onboarding) and `update-skills.sh` (updater) — one
  definition, no copy-paste drift. Installs Skill 60 FIRST, then Skill 61 only if 60
  installed cleanly (60 is a hard prerequisite; 61 consumes 60's ledger read-only).
  Client role is GATED (HELD by default); operator role is UNGATED (the canary).
  NEVER arms; asserts `armed=false` afterward. `--self-test` (offline, sandboxed).
- **Operator canary** `scripts/loop-protection-canary.sh` — `install | verify |
  status | arm | disarm | runbook`. Idempotent; stamps a 7-day burn-in clock on
  first install; `arm` is refused before 7 days (unless `--force`) and requires
  `--yes`; refuses to arm a non-operator ledger. `--self-test` (offline, sandboxed).
- **Wiring proof** `scripts/test-loop-protection-wiring.sh` — 9 offline checks that
  install.sh + update-skills.sh call the helper, persist both scripts, keep the gate
  HELD by default, and that the helper, canary, and both skill installers self-test.

Wiring (repo change only; execution deferred to the operator):
- `install.sh` (end-of-run, before the final gateway restart) runs the activation
  helper with `--role client`; persists both loop-protection scripts to
  `~/.openclaw/scripts` (or `/data/.openclaw/scripts`).
- `update-skills.sh` apply-phase post-sync hook runs the same helper `--role client`;
  both scripts are added to the persistent-copy loop (survive temp-clone cleanup).

Deferred (operator-timed, NOT run here): the operator-box canary install + arm, and
the fleet rollout (flip `fleet_rollout_enabled=true` in ONE batch on Trevor's word).

## [0.1.0] - 2026-07-10

Initial build (repo-only; HELD pending the operator-box canary + 7-day burn-in per
spec 9.2). Implements the greenlit scope of `LOOP-PROTECTION-SYSTEM-SPEC-v1.md`.

Added:
- **Watchdog + detectors.** `loop_watchdog.py` (the host-level 15-minute tick,
  outside every OpenClaw session, zero model calls) driving the four loop-specific
  detectors `loop_detectors.py`: D1 restart velocity, D2 idle token-burn rate, D3
  repeated-identical-signature, D4 timer re-fire / wedge / orphan-port.
- **Protection.** `loop_breaker.py` - five circuit breakers (process / turn / retry
  / cron / healer) with S4-cap-raise-without-stamp detection; `loop_backoff.py` -
  persisted exponential backoff with jitter (2h base, doubling, 24h cap) reconciling
  the never-stop doctrine (spec 5.4).
- **Response.** `loop_killcards.py` - Tier-1 reversible kill cards (LF-1 stale-lock,
  LF-2 offset rewind, LF-4 cron park, LF-6 process park) with the DRY_RUN quarantine
  ladder and the healer self-breaker; `loop_escalate.py` - Rescue Rangers escalation
  via the n8n webhook with an injectable transport and the UNSENT fallback.
- **State.** `loop_ledger.py` - the single SQLite-WAL writer (findings, fix_actions,
  breaker_state, backoff_state, offsets, digests, meta); `armed=false` DRY_RUN
  observe-only default.
- **Surface.** `loop-companion.sh` (sole entry) + `scripts/loop_companion.sh`
  (audit/status/troubleshoot), `install.sh`, `preflight.sh`, `verify.sh` (nine
  offline drills).
- **Config as data.** `config/thresholds.json`, `breakers.json`, `fix-classes.json`,
  `signatures.json` (the loop taxonomy + LP<->F14+ mapping).
- **Gates.** The four merge-gate scanners (guard-no-anthropic-runtime,
  scan-no-secrets, scan-no-client-identifiers, scan-no-json-exports), same
  0/1/2/3/4 exit contract as Skill 59/60.
- **Tests.** `tests/fixtures/` (restart storm, identical-signature runs, corrupted
  offset, orphan-port, subtractive misconfig, idle-burn trajectory) + `tests/drills/`
  (D-RESTART, D-SIG, D-OFFSET, D-ORPHAN, D-BURN, D-BACKOFF, D-HEALERLOOP, D-ESCALATE,
  D-DRYRUN).

Interlock:
- Consumes Skill 60's ledger read-only; contributes D1-D4 (proposed as Skill 60
  signals S11-S14, Open Decision T2). Operated by openclaw-maintenance + Healer +
  Bugs (spec Section 8); the maintenance role SOPs now invoke
  `loop-companion.sh audit --local` and the kill cards, and carry the F14+ extension.
