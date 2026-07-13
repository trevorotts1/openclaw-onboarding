---
name: loop-protection-system
description: The fleet's reflex arc against crash-loops and token furnaces - the single biggest daily problem on client boxes. A deterministic, zero-model-call, host-level watchdog that runs OUTSIDE every OpenClaw session so it survives the very wedges it treats. It adds the three layers Skill 60 (the Early Warning System) deliberately does not do - RESPOND (a per-class quarantine-and-fix engine), PROTECT (circuit breakers on every supervisor and retry path so a loop trips a breaker instead of running for weeks), and HEAL (auto-apply the proven-deterministic fixes, escalate everything ambiguous to Rescue Rangers, never guess). It carries four loop-specific detectors D1-D4 (restart velocity, idle token-burn rate, repeated-identical-signature, timer re-fire / wedge / orphan-port) that Skill 60's S1-S10 lack, consumes Skill 60's ledger read-only, and contributes nothing client-visible. Deterministic Python + stdlib only, one 15-minute cron, CPU-cheap, DRY_RUN observe-only for the first 7 days on any box. It is OPERATED by the openclaw-maintenance department (the watchdog + sweeps), the Healer department (patches the causes so a loop never recurs), and Bugs (keeps the ledger honest). Trigger with "audit the loop protection", "why is this box restarting", "is a cron looping", "check for idle token burn", "install the loop watchdog", "verify loop protection", "park this unit", or "a loop is confirmed - kill it".
version: 0.3.0
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
   its OWN breaker, never by discovering the damage later.
8. **CANARY, THEN HOLD.** The full install plus drill battery is proven on the
   OPERATOR box first; fleet rollout is HELD at repo-only until the operator's
   explicit word. The system obeys the laws it enforces.

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

## The four loop-specific detectors (D1-D4; full taxonomy in docs/LOOP-CLASS-CATALOG.md)

These are absent from Skill 60's S1-S10 catalog; they are proposed for registration
as Skill 60 signals S11-S14 (Open Decision T2) so the fleet keeps ONE vocabulary.

| # | Detector | Source (all local, deterministic, zero model calls) | Feeds |
|---|---|---|---|
| D1 | **Restart velocity** | `pm2 jlist` restarts / `launchctl` runs / `docker` RestartCount, delta per unit per tick (name/status/pid/restarts ONLY) | LP-B1..B4, the process breaker |
| D2 | **Token-burn rate** | trajectory usage per window, paid vs local, correlated with initiated-session presence | LP-A2/A5/A6/A7 |
| D3 | **Repeated-identical-signature** | rolling hash over (outcome class + tool-call sequence + target) in the new-bytes-since-last-tick slice; a SUCCESSFUL turn hashes as outcome `OK` and counts at the higher `p1_repeat_success` ceiling | LP-A1/A3/A4, LP-D2 |
| D4 | **Timer re-fire / wedge / orphan** | cron fire count vs declared cadence; healthy-probe-but-no-progress; orphan-listener pid vs supervisor on :18789; handoff-file age | LP-B2/B3/B5, LP-C1/C2 |

## The five circuit breakers (spec 5.1; config/breakers.json)

process (D1 restart velocity -> stop+park), turn (D2 paid burn -> heartbeat
allowlist enforce + park cron, never touches the model), retry (D3 identical
signature -> park resumable + escalate), cron (D4 re-fire -> disable, never delete),
healer (the watchdog's OWN fixes -> stop fixing a target fixed >3x/24h or whose last
fix failed verify). Every ceiling is a SAFETY CAP under Skill 60 Signal S4: a raise
without an operator stamp is a P1.

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

## Entry and verify

    bash 61-loop-protection-system/loop-companion.sh tick          # one watchdog tick
    bash 61-loop-protection-system/loop-companion.sh audit --local # read-only detector pass
    bash 61-loop-protection-system/loop-companion.sh status        # armed?, breakers, parked, findings
    bash 61-loop-protection-system/loop-companion.sh --self-test    # every script self-test
    bash 61-loop-protection-system/verify.sh                       # the failable drill battery

The watchdog tick and every companion command route through the ONE sanctioned entry
(`loop-companion.sh`). Every script implements `--self-test` (deterministic, no
network, no model). `verify.sh` is the independent, failable, FULLY OFFLINE end-to-end
proof (eleven drills; the D-ESCALATE drill injects a failing transport, so no external
API is ever touched). Two drills prove the RESPOND path is wired, not just planned:
**D-ARMED-PARK** runs an ARMED tick over the restart-storm fixture and asserts the unit
is parked AND the process breaker tripped; **D-REVERT** executes the emitted one-line
revert (`unpark --finding <id>`) and asserts it unparks.

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
