# SOP: Rescue Rangers Loop / Stuck / No-Reply Triage
**Version:** 1.0 | 2026-08-11 | R7 of the Rescue Rangers Loop-Response and Fleet Prevention Plan

## Purpose

This is the runbook a Rescue Rangers responder (human or agent) follows the moment a client says *"it keeps looping" / "it's stuck" / "I got nothing back"*, or a box's own agent escalates the same. Its job is to answer one question fast and correctly: **which of the mechanisms that produce this identical client experience is actually happening on THIS box, right now** — and to do that cheaply, in order, with a control at every step, before any action is taken.

**One client symptom, at least six distinct mechanisms.** "It loops / it's stuck / no reply" has been produced, independently, by: unreachable tools, a runaway self-triggering cron, a fleet-roll-driven gateway restart killing in-flight work, a channel turn-timeout eating the message, completed work whose delivery died in a queue, and narrated tool-call discovery streamed to the client as separate messages — plus a compaction wedge producing the same experience through a completely different failure class. **Triage must be by symptom, discriminating mechanisms in a fixed, cheap-first order — never by assumed cause.** Applying one mechanism's remedy to a box that is failing for a different reason is the single most common way a responder makes things worse.

---

## 0. Doctrine (binding on every responder, human or agent)

1. **Triage by symptom, never by assumed cause.** No action without that box's own detector firing for the step you are on. Six-plus mechanisms share one client-visible symptom; guessing the mechanism from the symptom alone has produced real harm — a fixer once applied one mechanism's remedy to a box that was healthy under that mechanism and broke it.
2. **Read-only first.** No client contact without authorization. No restart unless proven required — and when required, ordered: **fix the cause → verify the config is readable and valid AS THE GATEWAY USER → then restart.** Restarting first, before verifying readability, is a known trap: it forces a read the process cannot perform, and you find out only after the restart.
3. **Sanctioned mitigations only, each with a backup and an announcement in the same message it happens:**
   - `cron disable` — never delete. Deletion re-arms whatever installer created it on the next roll.
   - Whole-object `config patch` — never a dot-path `config set`. A dot-path set can autovivify garbage that only explodes after the next restart.
   - `chown` + verify (read as the gateway user) + restart, in that order.
   - `streaming.mode` → `"off"` — hot-reloads, no restart required.
   - Model or provider changes are **client sovereignty.** Escalate, never auto-correct.
4. **Every negative names its sources and its controls.** UNDETERMINED beats a confident zero. A zero-byte error log proves nothing about whether an error occurred — it may simply mean nothing was ever configured to write to it. An audit file's silence proves only that no CLI-based writer ran; a raw script writing the config directly leaves no trace there at all.
5. **Never auto-restore a registry, a config, or a roster.** A parity violation, a missing department, or an empty section could be an intentional change. Restoring on your own judgment turns a possibly-correct state into a definitely-wrong one. Escalate; let a human or the box's own sentinel make the call.
6. **Escalate out of the ladder** the moment any step is UNDETERMINED in a way that blocks the verdict, or the moment the fix would touch models, credentials, client contact, or a restart on a box already in a degraded/latched state. The escalation packet always contains: the step reached, the evidence gathered, the controls run, the proposed action, and the rollback path.

---

## 1. Where this lives and how it is invoked

- Every box's AGENTS.md carries the `RESCUE_ESCALATION_BOXNAME_V2` section (re-rendered from `scripts/rescue-escalation-section.md.tpl` on every roll via `apply-fleet-standards.sh` §5j — the one proven update-proof delivery channel for doctrine in this repo, because the re-stamp runs unconditionally on every pass).
- A box escalates by POSTing nine required fields to the Rescue Rangers n8n webhook. **Loop/stuck/no-reply symptoms escalate with the `problem` field prefixed `LOOP:`** (see the template) so the receiving workflow routes the ticket to this runbook, and a responder — human or an automated first pass running `scripts/rr-triage.sh` — starts at Step 0 instead of guessing from free text.
- `scripts/rr-triage.sh` is delivered to every box by the normal skills roll (so it self-heals at roll cadence like everything else in the repo-canonical layer) and is runnable over SSH by a responder. It is **read-only**: it never writes, never restarts, never messages a client. It prints a per-step verdict and exits with a bitmask (see its own header for the exact bit assignments) where **`3` always means UNDETERMINED for that step and is never collapsed into a pass.**

---

## 2. The triage ladder — cheap first, discriminating, with controls at every step

### STEP 0 — Reach the box and prove your instruments (≈2 min)

Use the fleet access resolver, never a bare SSH config lookalike — Mac-only routing has a documented 0-for-10 failure rate against VPS/Contabo boxes and must never be read as "box unreachable."

On the box, before trusting anything downstream:
- Confirm the box's structured JSON log exists and contains a known-positive marker for **today** (a plain-text log is not the primary source on Mac boxes — it misses reload events, double-counts boots, and cannot see database-only events at all).
- Confirm the state sqlite database opens **read-only**.

**If either control fails, report the instrument itself as broken. Nothing downstream in this ladder is valid until it is fixed.** A failed instrument bounds the instrument, never the box.

### STEP 1 — Is the gateway up, and is it crash-looping? (discriminates total outage)

- Mac: check the LaunchAgent's `LastExitStatus`. `19968` (i.e. exit code 78, `EX_CONFIG`) means a schema rejection; `15` is a normal `SIGTERM`.
- VPS/container: `docker inspect` + `docker logs`.
- Count boots from the **structured JSON log's** boot-phase markers — never a plain-text Library log, which has been measured to undercount boots roughly 2:1 against the structured log on the same box in the same window.
- A crash loop landing on exit 78 with a schema rejection: check the `agents` block's keys and the OpenClaw version **measured live on the box**, never assumed from a roster file — a roster has been measured stale by two minor versions on at least one box.

*Client experience at this step:* total darkness while the process list can still look healthy, because a supervisor keeps respawning the process between checks.

### STEP 2 — Did the work complete but the reply die? (checked BEFORE any loop hunt — it is the cheapest step and has been the actual answer more than once)

- Query `delivery_queue_entries` in the state sqlite for 100%-failed queues. A malformed `to:` target (a bare topic number, or `target:"telegram"` with no chat id) is a known model-composed-target defect — the run will still log "succeeded."
- Query `channel_ingress_events` for `failed_reason='handler-timeout'` at roughly the channel's configured turn cap. **This is DB-only** — a log grep for the same event has returned a false zero on a box where the database showed it fired multiple times the same day.
- Compare cron run logs' `delivery_status` against `delivery_mode='none'` on client-facing crons.

*Verdict here means:* there is no loop. The fix is delivery-side (correct the cron's `delivery_mode`, stop the payload from self-addressing) — never a loop-detector change.

### STEP 3 — Is it narration spam, not repetition? (an amplifier, not a loop)

- Read `channels.telegram.streaming` directly from `openclaw.json` — **`openclaw config get` cannot answer this question**, because it reports file contents, not the effective runtime value, and exits nonzero with "path not found" on a key that is legally absent.
- **Absence of the key means the effective mode is `"partial"` — this is a positive finding, not a clean result.** In partial mode, every inter-tool narration block can surface as its own client message, so one turn that narrates a multi-step hunt reads to the client as a burst of many messages.
- Confirm against the session transcript: N tool calls with distinct arguments in the same short window, each producing its own client-visible message, is the signature.
- **Fix:** `streaming.mode` → `"off"` via a whole-object `config patch` (hot-reloads; the process PID is not disturbed). Do **not** tune the loop detector in response to this — the detector was correctly silent, because nothing actually repeated.

### STEP 4 — Tool-unreachable loop?

- Check `tools.toolSearch`'s value: a scalar, or the strings `"tools"`/`"code"`, means broken. The healthy shape is an object: `{"enabled": true, "mode": "directory"}`.
- Attribute to this mechanism **only** when the structured log shows BOTH `Tool <x> not found` occurring more than zero times AND `compact prompt surface` occurring more than zero times — a generic "loop detected" log line alone does not discriminate this mechanism from any other, because the loop-detector is engine-agnostic.
- As a positive control that the log itself CAN record a hit for this mechanism, also look for `compact directory surface` / `hydrated deferred` entries.
- **Fix:** whole-object `config patch` to the directory-mode shape, validate the config as the gateway user, one restart, then verify with a real sentinel tool call (not just an exit code) that tools actually hydrate afterward.
- Container boxes specifically: this can be re-broken by the container's own boot-window persistence re-serializing an older config shape — check whether a drift guard is already installed on that box before assuming a fresh fix is needed.

### STEP 5 — Cron engine or restart-kill?

- **Cron:** query `cron_run_logs` for real fire counts per job against any declared cap. A cron whose `session` is `main` on a short interval (e.g. every 30 minutes) is the onboarding-resume class of runaway. **Fix: `cron disable`, never `rm`** — deletion re-arms the installer on the next roll. Prove the disable took by checking that zero new runs start at the job's next scheduled boundary, without disturbing the box's PID in the process.
- **Restarts:** look for reload/restart log lines clustering within seconds of a fleet-roll's own backup-file timestamps — that pattern is a roll-chain oscillation, not an independent crash. Run the restart-source discriminator procedure exactly as documented, starting with its own Step 0 control, before concluding a roll caused a given restart.

### STEP 6 — Compaction wedge? (the mechanism the rest of this ladder cannot see)

- In the structured log, look for `contextEngine.compact() threw`, `Compaction timed out`, or a client-visible "Auto-compaction could not recover this turn."
- Compare session token count against the model's context window, and check whether failures span **both** the primary model and its fallback (`outcome=failed`, an aborted-operation detail on both).
- **This is invisible to every check above it:** nothing repeats (so loop detection is silent), and nothing is down (so an uptime check is silent). Every turn on the affected session simply errors.
- **Response:** never issue `/new` first — it destroys the session's context. The sanctioned recovery is: export the transcript → archive the wedged session → produce an out-of-band summary of the archived transcript with an explicitly chosen summarizer → seed a fresh session with that summary → verify with one real, delivered reply. Note honestly: the archive step is proven safe on this fleet; the re-seed step has not yet been exercised anywhere and should be treated as first-time-careful, not routine.

### STEP 7 — Substrate checks (always run last, because always worth confirming even when an earlier step already found the answer)

- Compare the config file's owner against the gateway process's uid (a `su -s /bin/sh <gateway-user> -c 'head -c1 <config>'`-style read test, not a `stat` of the file's octal mode alone).
- Confirm a `timeoutSeconds` value is **present** for every provider backing a live model pin — this is an absence-detector: a missing key is the finding, not a value to sanity-check.
- **Registry parity:** compare the `agents` entry count in the config against the count of per-agent subdirectories under `<oc-root>/agents/`. A large gap between the two — a small registry count against a much larger directory count — is the registry-strip signature (see R0 in the prevention plan): the on-disk agent identities survived; only the registry pointing to them was emptied. `config validate` passes on this state; it is not a health signal.
- Check whether the config's `meta.lastTouchedAt` stamp is frozen while the file's own mtime has moved — a frozen stamp with a moved mtime means a raw writer touched the file outside the normal write path.
- VPS/container path differs from Mac: expect `/opt/clients/<box>/data/config/openclaw.json`-shaped paths, not the Mac `~/.openclaw/...` layout — do not assume Mac paths, and do not overwrite the wrong file because of it.

---

## 3. Escalation out of the ladder

Escalate — with the standard packet (step reached, evidence, controls run, proposed action, rollback path) — the instant any of the following is true:
- A step's verdict is UNDETERMINED and blocks the ladder from reaching a conclusion.
- The remedy at hand touches models, credentials, client contact, or a restart on a box that is already latched or in a beta/experimental state.
- Two or more steps produce evidence pointing at different mechanisms and they cannot be reconciled from this box alone.

---

## 4. Recurrence handling — the "if it ever happens again" contract

Every mechanism in this ladder now has four things: a **detector** (a specific, named place it runs), a **discriminator** (this ladder, in this fixed order), a **sanctioned fix** (listed at its step, above), and a **proof pattern** (named at its step, above). **If a recurrence of any of these six-plus mechanisms ever reaches a client again, that is a detector failure first.** File it against the detector before touching the box a second time — the box's own fix from last time may already be correct, and the thing that actually failed is the layer that was supposed to catch it earlier.
