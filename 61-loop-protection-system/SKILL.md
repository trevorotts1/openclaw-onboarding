---
name: loop-protection-system
description: The fleet's reflex arc against crash-loops and token furnaces - the single biggest daily problem on client boxes. A deterministic, zero-model-call, host-level watchdog that runs OUTSIDE every OpenClaw session so it survives the very wedges it treats. It adds the three layers Skill 60 (the Early Warning System) deliberately does not do - RESPOND (a per-class quarantine-and-fix engine), PROTECT (circuit breakers on every supervisor and retry path so a loop trips a breaker instead of running for weeks), and HEAL (auto-apply the proven-deterministic fixes, escalate everything ambiguous to Rescue Rangers, never guess). It carries seven loop-specific detectors D1-D7 (restart velocity, idle token-burn rate, repeated-identical-signature, timer re-fire / wedge / orphan-port, self-blocking-run / transcript poison, futile semantic retry burst, and cross-run resend) that Skill 60's S1-S10 lack - D5 being the one that measures a STOCK (how much of a session transcript is ALREADY loop wreckage) rather than a flow, because a paused loop leaves a poisoned transcript that keeps degrading every later turn, consumes Skill 60's ledger read-only, and contributes nothing client-visible. Deterministic Python + stdlib only, one 15-minute cron, CPU-cheap, DRY_RUN observe-only for the first 7 days on any box. It is OPERATED by the openclaw-maintenance department (the watchdog + sweeps), the Healer department (patches the causes so a loop never recurs), and Bugs (keeps the ledger honest). Trigger with "audit the loop protection", "why is this box restarting", "is a cron looping", "check for idle token burn", "install the loop watchdog", "verify loop protection", "park this unit", or "a loop is confirmed - kill it".
version: v1.0.0
---

# Loop Protection System (Skill 61)

This skill watches the MACHINE, not the work: it makes "this box is stuck in a
loop" a computable fact and, on a client box, hands the operator either a
completed Tier-1 fix report or a one-tap proposal - never a client-visible
message. **Skill 60 is the senses; Loop Protection is the reflexes.** It is not a
second detector (Skill 60 owns detection; this consumes its ledger and contributes
the loop-specific detectors Skill 60 lacks), not an autonomous config rewriter (the
Box D incident is the proof of what an unsupervised self-repairing agent does - the
healer here is deterministic script, allowlisted fix classes only, everything else
escalated), and never client-facing.

> The common shape of every incident this skill exists to end: **a timer or
> supervisor that re-fires an action whose failure mode does not stop the timer.**
> A boot-crash that restarts 56,050 times. A heartbeat that bills a paid model
> 24/7 while the client believes the system is idle. A poller reading past its own
> messages. A compaction that triggers itself on every turn. Every loop class is a
> variation of that one sentence.

## The binding doctrine (every code path honors these)

1. **ZERO model calls, ever, anywhere in the watchdog.** Every check is
   deterministic file / stat / diff / arithmetic work. The system that hunts
   furnaces must be structurally incapable of being one: cadence here costs CPU,
   never tokens. `guard-no-anthropic-runtime.py` still ships and rides the merge
   gate statically, because a future contributor might be tempted to add an
   LLM-judged anomaly check. They must not.
2. **OPERATOR-ONLY, CLIENT-SILENT, STRUCTURALLY.** Tier-1 fix reports, Tier-2
   proposals, and P1 pages go through the box's own gateway to the OPERATOR
   session only, `deliver:false`, deduped. The client's bot, chats, and Telegram
   account are never recipients. Move in silence toward clients is structural.
3. **NEVER print, echo, grep, or paste a secret VALUE.** Process-manager output is
   filtered to `name/status/pid/restarts` ALWAYS (never an env dump - a fleet
   review leaked live credential values exactly that way). A finding reports a key
   PATH and a CLASS only; the value is never reproduced, not even partially.
4. **CONFIG WRITES RUN AS THE BOX USER, never root** (`node` on VPS, wrapped in
   `docker exec -u node`). A root-owned config write is the LP-B5 freeze - the fix
   must never cause the disease. Every config-touching path refuses to run as root.
5. **DISABLE, NEVER DELETE. PARK, NEVER KILL-IN-A-LOOP.** Feature-bearing crons are
   sacred (the furnace-watch three-tier rule). A tripped breaker parks its unit
   visible-red; it never silently respawns.
6. **NOTIFY-ON-CHANGE-ONLY.** Silence is healthy. A watchdog that spams is itself a
   loop (the F7 / session-health lesson).
7. **DRY_RUN, THEN ARM.** Observe-only is the default for the first 7 days on any
   box (`armed=false`); Tier-1 arms only on the operator's word. Tier-2 stays
   proposal-only everywhere until a per-box stamp. A healer that loops is stopped by
   its OWN breaker, never by discovering the damage later. **Burn-in exit gate:**
   before any `arm`, confirm `collect_windows` yields non-zero `paid_tokens` on the
   operator box's real trajectory — a silently-zero token feed (a schema field-name
   drift the multi-candidate reader did not cover) would make D2 blind again, the exact
   Star-furnace blind spot, so a live non-zero reading is the arming precondition.
8. **PROVE ON THE OPERATOR BOX, THEN HOLD.** The full install plus drill battery is
   proven on the OPERATOR box first; fleet rollout is HELD at repo-only until the
   operator's explicit word. The system obeys the laws it enforces.

## Reuse before rebuild (this skill integrates, it does not reinvent)

| Fleet asset reused | What Loop Protection does with it |
|---|---|
| Skill 60 sentinel ledger (S1-S10) | The watchdog reads Skill 60's ledger events READ-ONLY; 60 keeps its single writer, 61 writes only its OWN ledger. One-way data flow: 60 detects -> 61 responds. |
| `loop-detector.sh` (operator-side, 1,118 lines) | Its six encoded signatures + progress-comparison are the DNA of D3/D4 and LP-D1/D2. It retires INTO this skill as a named migration once fleet coverage is total (Open Decision T7). |
| `remediate.sh` down-box rescue ladder | The DRY_RUN-plans-a-fix pattern, the classify-then-fix-only-deterministic-classes rule, the append-only change log, and the never-auto-fix-auth/unknown law. |
| The host-level MCP watchdog pattern (Box B) | Supervise outside any OpenClaw session; notify-on-change-only via a state file; silence when healthy. |
| `telegram-offset-healthcheck.sh` (fleet-wide since v10.14.5) | Adopted verbatim as fix class LF-2 (offset rewind + channel restart). |
| `session-health.sh` (DISABLED - the cautionary tale) | Its three defects become three laws: parse evidence with a real parser; every read is banner/noise-safe; every alert dedups. A broken healer is worse than none - so the healer self-breaker ships. |
| Skill 59/60 four-scanner merge-gate family | `guard-no-anthropic-runtime.py`, `scan-no-secrets.sh`, `scan-no-client-identifiers.sh`, `scan-no-json-exports.sh`, same 0/1/2/3/4 exit contract and value-free doctrine. |
| `scripts/skill-content-hash.sh` (repo root) | Auto-picks up `61-*` as a hashed skill dir; the update stamp gate covers Skill 61 with no extra wiring. |

## The seven loop-specific detectors (D1-D7; full taxonomy in docs/LOOP-CLASS-CATALOG.md)

These are absent from Skill 60's S1-S10 catalog; they are proposed for registration
as Skill 60 signals S11-S17 (Open Decision T2) so the fleet keeps ONE vocabulary.

| # | Detector | Source (all local, deterministic, zero model calls) | Feeds |
|---|---|---|---|
| D1 | **Restart velocity** | `pm2 jlist` restarts / `launchctl` runs / `docker` RestartCount, delta per unit per tick, BASELINED per unit so first sight reads 0 (name/status/pid/restarts ONLY) | LP-B1..B4, the process breaker |
| D2 | **Token-burn rate** | trajectory usage per window, paid vs local, correlated with initiated-session presence | LP-A2/A5/A6/A7 |
| D3 | **Repeated-identical-signature** | rolling hash over (outcome class + tool-call sequence + target) in the new-bytes-since-last-tick slice; a SUCCESSFUL turn hashes as outcome `OK` and counts at the higher `p1_repeat_success` ceiling | LP-A1/A3/A4, LP-D2 |
| D4 | **Timer re-fire / wedge / orphan** | cron fire count vs declared cadence; healthy-probe-but-no-progress; orphan-listener pid vs supervisor on :18789; handoff-file age | LP-B2/B3/B5, LP-C1/C2 |
| D5 | **Self-blocking run / transcript poison** | bounded TAIL of each session transcript: runtime tool-loop block records (matched structurally on `details.status=blocked` + `deniedReason=tool-loop`, never on prose), longest block burst, trailing-window block share, and compaction summaries that captured loop text | LP-A8, the session breaker |
| D6 | **Futile retry burst (SEMANTIC repetition, ARGUMENT-BLIND)** | same bounded tails: per (transcript, tool), the heaviest sliding 60s window of calls, with how many FAILED and how many carried a fail-closed auth-class refusal in the result payload (counted, then discarded) | LP-A9 |
| D7 | **Cross-run resend (provenance-stamped)** | the RECEIVING agent's session transcript `message.provenance` (kind=`inter_session`, sourceTool=`sessions_send`, sourceSessionKey) - hashed payload, counted across DISTINCT run ids inside a rolling 300s window, offset-tracked, cheap enough for a 60s cadence | LP-A10, the resend breaker |

### D6 is argument-blind on purpose — every other guard on the box is not

D1-D5 and the runtime's own guards all share one assumption: **a loop repeats itself
exactly.** The runtime keys on `toolName` + `sha256(params)`; this repo's always-armed
runaway guard keys on `toolName` + `argsHash` + `resultHash`, stricter and therefore
blinder; D3 hashes outcome class + tool sequence + target. An agent that REWORDS a
failing intent defeats all four at once without trying to — and OpenClaw exposes no
per-turn tool-call ceiling to fall back on.

D6 never reads arguments at all. It asks the one question that survives rewording:
*is this tool producing no progress, over and over?* Its primary face counts
**fail-closed refusals in the result payload**, because in this class **the tool calls
SUCCEED** — an `exec` running a curl against a refusing API exits 0 and is recorded
`status: completed`, so there is no error for an error-keyed detector to find.

**Volume is never the signal.** The obvious design — count same-tool calls in a window —
was measured against the operator box's real 998-transcript corpus and REJECTED: that
corpus contains a healthy burst of 460 `exec` calls in 48.2 seconds, and ~100 file/tool
pairs at or above the incident's own 13-calls-per-60s. A count-only detector would fire
on roughly a quarter of healthy sessions. D6 requires evidence of FUTILITY, and on that
same corpus yields 11 findings across 998 transcripts (1.1%) — one of them landing on an
archived transcript already named for the loop it recorded.

**D6 is a watchdog, not a brake.** It runs on the 15-minute tick and reports after the
fact. The live fix is doctrine **N40** in the fleet's canonical `AGENTS.md`: against a
fail-closed dependency, at most 2 attempts, then ONE message stating what is blocked and
what is needed — and never a narrated hunt in front of a client.

### D5 measures a STOCK, not a flow - that is the whole point

D1-D4 all measure FLOW: events per tick. They answer *"is a loop running right
now?"* and go silent the moment it pauses. D5 answers a different question:
***how much of this transcript is ALREADY loop wreckage?*** That distinction is
load-bearing. A loop can stop while its transcript stays full of its own refusals,
and every later turn on that transcript starts degraded - so a flow detector hands
back a false all-clear on a fault that is still doing damage. The incident this
detector comes from survived three separate fixes aimed at the ENVIRONMENT while
the fault sat in the CONTEXT.

D5 has two faces, in the order they matter:

- **IGNITION (primary, early).** Consecutive blocks inside one run. High-precision
  and fires seconds in - long before the transcript is measurably poisoned, and
  long before the run's hold on the conversation lane becomes user-visible.
- **AFTERMATH (secondary).** The trailing-window block share plus compaction
  summaries that captured the loop verbatim. This is the part that persists and
  that a roll must clear. It is deliberately a TRAILING window and never a
  cumulative ratio: a whole-file ratio lags by thousands of records and stays
  quiet for hours after onset.

Two properties are non-negotiable and are drilled as such:

1. **Size never fires on its own.** Transcript size is a severity MODIFIER only.
   The control archive used to prove this is larger than the poisoned one on every
   axis and must stay perfectly silent.
2. **A live transcript is never rolled.** The auto-fix refuses a transcript still
   being written; a burning session gets the P1 and a prepared abort, never a file
   pulled from under a running gateway.

**The symptom signature to recognise by hand:** *an agent that answers CORRECTLY
but SLOWLY.* A broken agent gives wrong answers; a poisoned one gives right answers
slowly, because a doomed run is holding the lane while messages queue behind it.
Emergency operator recovery is `/new` - start a fresh session.

## The seven circuit breakers (spec 5.1; config/breakers.json)

process (D1 restart velocity -> stop+park), turn (D2 paid burn -> heartbeat
allowlist enforce + park cron, never touches the model), retry (D3 identical
signature -> park resumable + escalate), cron (D4 re-fire -> disable, never delete),
**session (D5 transcript poison -> archive the transcript and roll, MOVE never
delete, and never while it is live)**, healer (the watchdog's OWN fixes -> stop
fixing a target fixed >3x/24h or whose last fix failed verify), resend (D7
cross-run identical-payload resend -> abort the source session's in-flight run
via the native `sessions.abort` RPC, no-op-safe when nothing is active, + park
the source; NEVER pkill node, NEVER a gateway restart). Every ceiling is a
SAFETY CAP under Skill 60 Signal S4: a raise without an operator stamp is a P1.

## Three fix tiers (spec 6.2)

- **TIER 1 - AUTO-FIX** (deterministic, proven, reversible-in-one-line, blast radius
  = the looping unit only): the LF-* classes in `config/fix-classes.json`. Apply
  immediately (when armed), report after.
- **TIER 2 - FIX WITH OPERATOR STAMP** (config-shape changes): the watchdog prepares
  the exact command + snapshot + revert line and sends a one-tap proposal to the
  OPERATOR (never the client); an `approve <finding-id>` reply executes it.
- **TIER 3 - NEVER AUTO** (propose and hold): a client's model choice (sovereignty is
  absolute - the system parks timers, never substitutes models), credentials,
  doctrine files, deletion of anything, ambiguous findings, and any fix whose verify
  failed once. These go to Rescue Rangers with the structured escalation format.

**Every escalation passes a per-key gate first** (RR-ESC-GATE-20260826). The channel
had no dedup and no backoff: on one live box a single `dedup_key` produced **992
escalations**, because a finding whose escalation the intake never admitted is left
OPEN by design and therefore re-posts on every 15-minute tick, forever. The intake's
rate limit is **GLOBAL** across the fleet (12/60s), so one box's runaway key sheds
other clients' live escalations. Two controls now stand in front of the send, both
keyed on the finding's own `dedup_key`:

- **Dedup** - one escalation per key per `alert.escalation.dedup_window_hours`
  (**12h**, deliberately quieter than the 6h operator-alert window: an alert is a
  local note in this box's ledger, an escalation pages a human rescue team over a
  globally rate-limited intake). The digest is stamped **only on an ADMITTED
  delivery**, never on an attempt - a refusal that silenced its own retry would be
  silent loss.
- **Backoff** - a refusal (HTTP 429/502, read timeout) advances that key through the
  existing `loop_backoff` ladder and the `backoff_state` table: 2h/4h/8h/16h/24h(cap),
  jittered. A refusal can never produce an immediate identical retry. An admitted
  delivery clears the ladder.

Both are **per key**. A genuinely new problem carries a new `dedup_key` and escalates
immediately, on the same tick, even while another key sits in a 24h backoff - turning
a noisy system into a silent one would be the worse failure by far. A suppressed
finding is left `open` and is never marked `escalated`. The tick summary separates
`escalated` (admitted), `escalation_unsent` (refused) and `escalation_suppressed`
(never attempted). Drills: `tests/drills/D-ESC-GATE.md`.

## One cron job, and a way to tell it is alive (v0.6.5)

Two facts about a box were unknowable from inside this skill until 0.6.5, and both had
already gone wrong at fleet scale.

**Exactly one watchdog cron job.** `openclaw cron add` has no upsert and `install.sh`
called it unconditionally, so every re-run added another job. Measured 2026-08-26 across
34 running boxes: **25 carried 2-12 duplicate `loop-tick-*` jobs**, all enabled, all
`*/15`. `scripts/loop_cron.py` replaces the blind add with LIST → DECIDE → ACT →
**LIST AGAIN AND PROVE IT**. Running `install.sh` ten times now leaves exactly one job.
`--all` is mandatory on the listing, because `openclaw cron list` **hides disabled jobs**
and a disabled loop-tick job that cannot be seen is a duplicate waiting to be created.
Only a job that is BOTH named `loop-tick-*` AND recognisably ours (a command payload
invoking `loop-companion.sh tick`) is ever removed; anything else is reported and left
alone. A **disabled** registration is never switched back on and never duplicated
alongside — a disabled cron is a decision somebody made, and an installer that quietly
undoes a human decision is a worse failure than the one it is fixing. The schedule flag is
**probed off `openclaw cron add --help`**, never assumed, so the next CLI rename surfaces
instead of silently no-opping the way `--schedule` did before v0.4.0.

**`last_tick_ts`.** There was no direct "when did the watchdog last RUN" signal, so
liveness was inferred from `MAX(findings.tick_ts)` — which measures whether a box *has a
loop condition*, not whether the watchdog ran. **A healthy box reads as a dead
watchdog**, and that produced a false "6 boxes unwatched" report on 2026-08-26; one of
the six had ticked 13 minutes earlier. Every completed tick now stamps `last_tick_ts`
(plus `last_tick_findings`, `last_tick_errors`, `last_tick_armed`, and `last_tick_mode`
= live | dry-run), **including a tick that finds nothing** — exactly the case the old
proxy got wrong. `loop_ledger.py liveness` is the instrument.

Neither fact is allowed to be free: an install whose cron job is not PROVEN exits **5**
and cannot print "Install OK", and a listing that cannot be read is **UNDETERMINED**,
never "no jobs". Drills: `tests/drills/D-CRON-ONE.md`.

## Entry and verify

    bash 61-loop-protection-system/loop-companion.sh tick          # one watchdog tick
    bash 61-loop-protection-system/loop-companion.sh audit --local # read-only detector pass
    bash 61-loop-protection-system/loop-companion.sh status        # armed?, last tick, breakers, findings
    bash 61-loop-protection-system/loop-companion.sh --self-test    # every script self-test
    bash 61-loop-protection-system/verify.sh                       # drills + the standing gate
    bash 61-loop-protection-system/verify.sh --live                # THIS box: ONE */15 cron job, fresh tick
    python3 61-loop-protection-system/scripts/loop_cron.py status  # how many loop-tick jobs exist
    python3 61-loop-protection-system/scripts/loop_ledger.py liveness  # when did it last tick

`verify.sh` exits **0** verified, **4** drift/failure, **5** standing gate UNDETERMINED.
Exit 5 is the one that matters most in practice: an unreachable gateway, an unresolvable
`openclaw` binary (a Mac's bare-ssh `PATH` is `/usr/bin:/bin:/usr/sbin:/sbin` — no
openclaw) or a pre-0.6.5 ledger means **we could not look**, and that is never reported
as a pass.

The watchdog tick and every companion command route through the ONE sanctioned entry
(`loop-companion.sh`). Every script implements `--self-test` (deterministic, no
network, no model). `verify.sh` is the independent, failable end-to-end
proof: sections 1-3 are FULLY OFFLINE (the D-ESCALATE drill injects a failing transport,
so no external API is ever touched) and section 4 is the v0.6.5 STANDING GATE, which
reads this box's own cron table and ledger because a battery that only ever examined
scratch fixtures stayed green while 25 of 34 boxes accumulated duplicate cron jobs.
Use `--offline` to skip it (CI, a source checkout); the offline verdict then says so
out loud, so it can never be read as a fact about a real box. Two drills prove the RESPOND path is wired, not just planned:
**D-ARMED-PARK** runs an ARMED tick over the restart-storm fixture and asserts the unit
is parked AND the process breaker tripped; **D-REVERT** executes the emitted one-line
revert (`unpark --finding <id>`) and asserts it unparks. Four more prove D5 in BOTH
directions - **D-POISON** (a blocked-burst transcript is P1), **D-POISON-CLEAN** (a
LARGER, busier, clean transcript stays silent even past the re-arm floor),
**D-POISON-ROLL** (an armed tick archives it, moved not deleted) and **D-POISON-LIVE**
(a transcript still being written is refused) - and all four are mutation-proven
failable (see `tests/drills/D-POISON.md`).

Four more hold the line on a REPRODUCED crash: the roll was not idempotent, so LF-10
re-archived its own archive every tick until the filename passed 255 bytes and an
uncaught `OSError` killed the whole tick. **D-POISON-REROLL** asserts ten armed ticks
over one poisoned transcript yield exactly one finding and one roll; **-BOUND** that the
constructed name is byte-bounded and deterministic; **-REFUSAL** that a filesystem
error is a refusal, not a crash; **-TICK** that an exception escaping a kill card is
contained and the finding behind it is still processed. **One bad unit never kills the
tick** - a watchdog that dies quietly leaves a box that only looks watched (see
`tests/drills/D-POISON-REROLL.md`).

**What the operator commands actually do.** `park <unit>` / `unpark <unit>` and the
emitted revert `unpark --finding <id>` (finding→unit resolved from the ledger) are
real, tested, and reversible. `fix <finding-id>` executes the **config-free**
process-unit park (LF-6) for real against the ledger — the one act that touches no
client config — and records its one-line revert. Every **config-touching** Tier-1 class
(LF-1/2/4/5/7) and every Tier-2 config-shape change (LF-8) is **prepared** by
`fix`/`approve` (the exact command + one-line revert) and applied **ON-BOX** via the
maintenance path (`docker exec -u node` on VPS), **never auto-applied off-box**. This is
a deliberate, honest scope: the unattended tick and the off-box `fix` never mutate
client config; only a supervised process gets parked automatically.

## Who operates it (the architecture answer, spec Section 8)

Skill 61 ships the machinery. It is OPERATED by departments that already exist on
every box: **openclaw-maintenance** runs the watchdog and the sweeps (its Token
Manager / Furnace Watch and Uptime / Connectivity Watchdog roles invoke
`loop-companion.sh audit --local` and the kill cards); the **Healer** department
patches the causes so the same loop never recurs; **Bugs** keeps the ledger honest.
The F-taxonomy the maintenance department already carries is extended by the LP loop
classes (F14+). This skill is the enforcement pipeline those roles were missing -
"enforcement, not description."
