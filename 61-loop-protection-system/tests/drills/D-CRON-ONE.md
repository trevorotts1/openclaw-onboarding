# D-CRON-ONE / D-TICK-FRESH — the standing gate (v0.6.5)

Every drill in this battery ran against scratch fixtures. All of them were green on
**2026-08-26**, the day the fleet was measured and found carrying **2–12 duplicate
watchdog cron jobs on 25 of 34 running boxes** — every duplicate enabled, every one on
`*/15`. Green drills, broken fleet. The two drills here close that gap: they read the
box the skill is actually installed on.

## The two defects they exist to catch

**Duplicate cron jobs.** `openclaw cron add` has no upsert, and `install.sh` called it
unconditionally, so every re-run added another job. The operator box held three
identical `loop-tick-<host>` jobs whose `lastRunAtMs` values were **4 seconds apart** —
one window, three ticks, the same finding processed three times over.

**No liveness signal.** There was no direct "when did the watchdog last RUN" fact
anywhere. The proxy in use was `MAX(findings.tick_ts)`, which is not liveness: it
answers *does this box have a loop condition*. A healthy box that finds nothing reads as
a dead watchdog. It produced a false **"6 boxes unwatched"** report; one of the six had
ticked **13 minutes** earlier.

| Drill | Proves | Instrument |
|---|---|---|
| **D-CRON-ONE** | This box carries **exactly one** loop-tick job, it is **enabled**, its schedule is **`*/15 * * * *`**, and its payload is **ours** (a command job invoking `loop-companion.sh tick`). | `loop_cron.py status` → `openclaw cron list --all --json` |
| **D-TICK-FRESH** | The watchdog **completed** a tick within 45 minutes (three missed `*/15` ticks). | `loop_ledger.py liveness` → ledger meta `last_tick_ts` |

**Exactly one — never `>= 1`.** That is the verified correct post-state across all 25
boxes remediated on 2026-08-26, and a `>=` check is precisely what let 2–12 duplicates per
box pass for healthy.

## What the reconciler will and will not touch

| Condition | Action |
|---|---|
| no loop-tick job | add one |
| one enabled, correct | **nothing at all** — not one add/edit/rm call |
| one enabled, wrong schedule | edit the schedule **in place** |
| several enabled | collapse to one, oldest kept, rest removed by id |
| drifted **name** / command / cwd | reported, **left alone** — `BOX` comes from `hostname`, which flaps `Mac.lan` → `Mac`, and renaming a working job on every flap is churn |
| every registration **disabled** | **exit 4, never re-enabled, never duplicated** — a disabled cron is a decision somebody made, quite possibly to stop a runaway. An installer that quietly undoes a human decision is a worse failure than the one it is fixing |
| a `loop-tick-*` job that is not ours | reported, never removed |

The schedule flag itself is **probed, not assumed**: the reconciler reads
`openclaw cron add --help` and uses whichever of `--cron` / `--schedule` that CLI offers,
and refuses outright if it offers neither. `--schedule` was removed from this installer in
v0.4.0 (`2e2766c77`) because 2026.7.1-2 has no such flag; a box still invoking it is
running an install.sh older than that. The probe means the next rename surfaces instead of
silently no-opping.

`--all` is load-bearing, not defensive: `openclaw cron list` **hides disabled jobs**
(2026.7.1-2: `--all  Include disabled jobs (default: false)`). Without it a disabled
loop-tick job is invisible, the reconciler concludes "none exist", and adds a duplicate
of a job that was already there. `loop_cron.py --self-test` proves the instrument before
it proves the behaviour: it asserts the stub listing **hides** the seeded disabled job,
so dropping `--all` makes that case fail rather than silently pass.

## Failable in both directions — run, not asserted

Six sandboxed runs of `verify.sh --live` against a stub gateway and a scratch ledger:

| Box state | Exit | Verdict |
|---|---|---|
| 0 cron jobs, no stamp | 4 | D-CRON-ONE **FAIL** (+ D-TICK-FRESH undetermined) |
| 1 job, `*/15`, stamp 0.9s old | 0 | both PASS |
| 3 duplicate jobs | 4 | D-CRON-ONE **FAIL**, count=3 named |
| 1 job on `*/5` | 4 | D-CRON-ONE **FAIL** on the schedule |
| 1 job, disabled | 4 | D-CRON-ONE **FAIL**, and the installer will not re-enable it |
| 1 job, stamp from yesterday | 4 | D-TICK-FRESH **FAIL** |
| `cron list` exits 7 | 5 | **UNDETERMINED**, never a pass |
| `openclaw` unresolvable | 5 | **UNDETERMINED**, every probed path named |

## UNDETERMINED is its own exit code

Exit **5**, never folded into the pass. An unreachable gateway, an unresolvable
`openclaw` binary, or a ledger written by a pre-0.6.5 watchdog are each a statement that
**we could not look** — not evidence the box is fine, and not evidence it is broken. A
bare `openclaw` is absent from a Mac's bare-ssh `PATH`
(`/usr/bin:/bin:/usr/sbin:/sbin`) while the binary sits in `/opt/homebrew/bin`,
`/usr/local/bin` or `~/.local/bin`; reporting that as "no gateway" is how 19 of 26 roll
logs came to say **Install OK** over a box nothing was ever scheduled on.
