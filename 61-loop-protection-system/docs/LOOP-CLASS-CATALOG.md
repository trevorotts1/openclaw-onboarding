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

## Two deliberate non-classes (stated so nobody adds them)

- **Content-quality failures** - the Quality Control department's 8.5 gate owns those;
  this system watches machines, not work.
- **Provider-side outages with correct local backoff already in flight** - that is
  patience, not a loop.
