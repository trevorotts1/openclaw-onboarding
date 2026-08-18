# Loop-Class Catalog (Skill 61)

The full root-cause taxonomy from `LOOP-PROTECTION-SYSTEM-SPEC-v1.md` Section 2,
grouped by WHERE the loop lives. `F#` maps each class onto the openclaw-maintenance
department's existing furnace-driver taxonomy; new classes extend it (F14+) so the
department SOPs and this skill share one vocabulary. The machine-readable form is
`config/signatures.json` (`loop_classes[]`); this doc is the human reference.

## Family A - AGENT-TURN LOOPS (the token burners: a model call inside the loop)

| Class | F# | Signature (short) | Detector | Kill card / fix |
|---|---|---|---|---|
| LP-A1 | F14 | every turn errors "Context too large"; subtractive `softThresholdTokens` misconfig | D3 (+ S60 S3 write-time) | `/new` via ingress -> correct threshold -> real-reply verify |
| LP-A2 | F1 | paid turns around the clock, zero initiated sessions; heartbeat fan-out | D2 | LF-8 heartbeat allowlist flip + tier pin + cadence floor (Tier 2 -> Tier 1 per box) |
| LP-A3 | F12-adj | agent rewrites `memorySearch.*` repeatedly, terminating at provider=none | D3 | ONE atomic dims-matching deep-merge (Tier 3: never auto) |
| LP-A4 | F3 | redispatch cron re-firing a terminally-failing job / sub-backoff cadence | D3 | park cron -> clear stale run id -> re-arm with backoff+progress+breaker |
| LP-A5 | F9-adj | rapid retries against a 429/dead provider; paid-fallback drain | D3 | full stop -> honor retry window -> exactly one scheduled resume |
| LP-A6 | F3 | resume cron without light-context: huge input, zero tool calls | D2 | LF-5 set `lightContext:true` |
| LP-A7 | F2 | dreaming / re-embed under the sanctioned interval; per-agent shared-corpus re-embed | D2 | pin interval >= floor; point at the single shared index |
| LP-A8 | F15 | a run blocked by the runtime's own identical-call guard, over and over, inside one run; the transcript (and its compaction summaries) fill with the refusals | D5 | LF-10 archive the transcript + roll (move, never delete, never while live); LF-9 abort the run to free the lane (Tier 2); LF-11 prune poisoned checkpoints (Tier 2) |
| LP-A9 | F16 | an agent REWORDS a failing intent: many calls to one tool in a short window, all with DIFFERENT arguments, against a dependency that is refusing on purpose (auth-class). Every args-keyed guard is silent by construction | D6 | doctrine N40 is the live fix (stop at 2, one message, never narrate); the watchdog reports after the fact — Tier 2, escalate, never auto-fix an auth failure |
| LP-A10 | F15 | orchestrator resends a byte-identical `sessions_send` payload as a NEW top-level run after the tool's own hardcoded 30s fallback timeout (caller omitted `timeoutSeconds`); each resend is a FRESH run id so OpenClaw's own `tools.loopDetection` (within-run) and `session.agentToAgent.maxPingPongTurns` (inner ping-pong of one `sessions_send` call) both reset and never fire | D7 | LF-12 `sessions.abort` (native RPC, no-op-safe when nothing is active) on the source's in-flight run + park source, never pkill/gateway-restart |

## Family B - PROCESS / SUPERVISOR LOOPS (restart storms: churn + outage, no model call)

| Class | F# | Signature (short) | Detector | Kill card / fix |
|---|---|---|---|---|
| LP-B1 | F5 | supervisor restart storm; app dies faster than the stability window | D1 | LF-6 stop unit -> capture boot log -> fix cause -> single start -> stability watch |
| LP-B2 | F4 | `*/2` watchdog racing launchd; two supervisors fight one port | D1 | disable the RACING supervisor (one owner per process) -> single clean restart |
| LP-B3 | F5-adj | zombie orphan holds :18789 outside launchd + stale handoff marker | D4 | LF-3 archive marker -> kill orphan on :18789 -> kickstart -> pid-stability verify |
| LP-B4 | F6 | daemon started inside a session; SIGTERMed at teardown; autostart resurrects it | D1 | disable the in-session autostart -> install a host-level watchdog |
| LP-B5 | F13-adj | one illegal key freezes the WHOLE cron engine (incl. self-heal jobs) | D4 | LF-7 restore last-good snapshot as box user -> validate -> sanctioned restart |

## Family C - CHANNEL / DELIVERY LOOPS

| Class | F# | Signature (short) | Detector | Kill card / fix |
|---|---|---|---|---|
| LP-C1 | F7-adj | telegram `lastUpdateId` advanced past pending (deaf inbound); or duplicate pollers | D4 | LF-2 offset rewind + channel restart (shipped fleet-wide) + duplicate-poller kill |
| LP-C2 | F10 | announce-mode cron pushing every run to a chat (worst: a CLIENT chat) | D4 | LF-4 no-deliver conversion + state-file notify-on-change |

## Family D - TASK / PROGRESS LOOPS (stalls that look healthy)

| Class | F# | Signature (short) | Detector | Kill card / fix |
|---|---|---|---|---|
| LP-D1 | F10 | empty-prompt no-op cron: fires ok forever, does nothing | D4 | escalate with the exact cron id (directive is client-specific; escalate-not-guess) |
| LP-D2 | F3 | build cron re-running because an outdated QC script can never pass | D3 | pull updated gate scripts via the sanctioned skill-update path, re-run |
| LP-D3 | F10/F11 | delivery retried against a completed/failed id; two crons trigger one function | D4 | LF-4 mark the ledger, disable the duplicate (comment out, never delete) |

## A note on LP-A8: it is the only class whose fault lives in the CONTEXT

Every other class here is a fault in the ENVIRONMENT - a timer, a supervisor, a
port, a config key. You fix the environment and the loop ends. LP-A8 is different:
the run that ignites it can be gone, its trigger removed and its config corrected,
and the transcript it left behind will still degrade every later turn, because the
model reads that transcript as its own history. That is why D5 measures a stock
rather than a flow, and why its fix ARCHIVES the transcript rather than restarting
anything.

**Recognising it by hand:** an agent that answers CORRECTLY but SLOWLY. A broken
agent gives wrong answers; a poisoned one gives right answers slowly. Operator
emergency recovery is `/new`.

**The catch that makes it two-part:** compaction checkpoint summaries can capture
the loop verbatim, and those are re-injected on resume and SURVIVE a transcript
roll. Rolling the transcript alone is not a complete fix (that is LF-11's job, and
it is Tier 2 because the live gateway rewrites the session store).

## A note on LP-A9: it is the only class every OTHER guard is blind to BY CONSTRUCTION

LP-A8 is caught because the runtime refuses the call and leaves a structural record.
LP-A9 leaves no such record, because **nothing refuses anything**. The agent varies
its arguments, so the runtime's `(toolName, sha256(params))` guard never matches; the
always-armed runaway guard needs `resultHash` to match too, so it is stricter and even
blinder; and D3 hashes the target, which also varies. Three independent guards, one
shared assumption — *a loop repeats itself exactly* — and an agent that rewords
violates that assumption without trying to.

It is also the only class where **the tool calls SUCCEED**. `exec` running a curl
against a fail-closed API exits 0 and is recorded `status: completed`. There is no
error to count. D6 therefore counts *fail-closed refusals in the result payload*
(auth-class markers, counted and discarded — never stored), because the futility is
in what the dependency said, not in what the tool did.

**Recognising it by hand:** the client sees the agent narrating a search — "let me
check the other endpoint", "trying the credentials file" — several messages in under a
minute. The tell is not volume, it is *rewording*: each message describes a different
route to the same blocked thing.

**The fix is doctrine, not detection.** D6 runs on a 15-minute watchdog tick and reports
after the loop is over. N40 (`AGENTS.md`) is what stops it while it is happening: at most
2 attempts against a fail-closed dependency, then ONE message, and never a narrated hunt.

## Two deliberate non-classes (stated so nobody adds them)

- **Content-quality failures** - the Quality Control department's 8.5 gate owns those;
  this system watches machines, not work.
- **Provider-side outages with correct local backoff already in flight** - that is
  patience, not a loop.
