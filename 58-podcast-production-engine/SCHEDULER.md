# Podcast Production Engine Scheduler (act-4)

Zero em dashes; no triple-backtick fences.

## The doctrine (binding)

THE CONTROLLER IS THE PROCESSOR; THE SCHEDULER IS ITS HEARTBEAT.

- podcast_controller.py is the production processor: the one program that runs
  the 18-step pipeline over queued TaskFlows. Each accepted intake submission
  becomes one TaskFlow whose flow key IS the job_key
  (23-ai-workforce-blueprint/department-wiring/podcast-engine/wiring.json,
  session_binding.flow_identity), bound to sessionKey
  podcast:intake:<client-slug> and owned by director-of-podcast (steps 0, 1, 2,
  12 to 16, 17, 18; statuses received, researching, publishing, enrolling,
  complete, failed, queued_credit_out).
- The scheduler is that processor's heartbeat. Without it the controller never
  activates, which is precisely the failure the activation ticket describes:
  intake and publish work, queued flows never run the 18 steps.

Nothing in this unit executes a pipeline step itself. Every state write still
goes through podcast_state.py (the sole writer); every step record still moves
through the ledger and cc_board.py. The scheduler only makes the processor run
on time.

## Shape of the heartbeat

ONE entry PER BOX (not per client), every 5 minutes, invoking

    scripts/podcast_scheduler_runner.sh

The runner sources the podcast env (secrets env file: labels and locations
only, values never printed), takes a portable single-instance lock (a stale
tick never overlaps a fresh one), and runs

    python3 podcast_controller.py --once

The controller's exit code is the tick's exit code. A missing controller logs
and exits 0 on purpose: the heartbeat stays green until the processor slice
lands on the box, then flips to real work with zero reconfiguration.

## Platform entries (match the box idiom)

- Linux: config/cron.d/podcast-scheduler (same shape as
  config/cron.d/qmd-orphan-sweep: comment header, env-var list, one 5-minute
  line, user field is the OpenClaw runtime user, never root). Installed into
  /etc/cron.d/ by the installer; the runner is copied to
  /usr/local/bin/podcast-scheduler-runner.sh.
- macOS: config/launchd/com.openclaw.podcast-scheduler.plist.template,
  rendered into ~/Library/LaunchAgents/com.openclaw.podcast-scheduler.plist
  (StartInterval 300). OpenClaw itself runs as a launchd user service on the
  Mac mini, so a user agent is the matching idiom.
- Fallback (no root, no launchd): one line in the runtime user's crontab.

## Installation (idempotent)

    scripts/install-podcast-scheduler.sh [--check] [--force launchd|cron.d|usercrontab]

Re-running converges: identical artifacts are left untouched, a changed runner
is replaced, the launchd agent is bootout-then-bootstrap. --check is read-only
and reports whether the heartbeat is active (used by the activation audit).
The installer NEVER registers an openclaw cron job.

## Furnace reconciliation (guard-cron-inventory.py)

The guard enforces, per client, EXACTLY ONE recurring openclaw cron (the daily
smoke test), never a heartbeat entry, never a queue poller, never an
announce-mode delivery, and zero recurring jobs for a departed client. This
scheduler violates none of it:

- It is ONE OS-level entry PER BOX, not an openclaw client cron, so it is not
  subject to the per-client census. guard-cron-inventory.py recognizes it by
  name (podcast-scheduler), excludes it from the census and the churn sweep,
  and reports the excluded count (extra.scheduler_recognized) so an auditor
  can see it was seen.
- Recognition never exempts shape: a poller-shaped or announce-shaped entry
  named podcast-scheduler still fails the guard, and more than one tick per
  inventory fails as a furnace.
- Churn posture: a departed client leaves ZERO client crons behind (the
  furnace law), and the box-level tick remains until the engine itself leaves
  the box (SOP-PODCAST-03 Step 7 removes it).

## Wiring summary

| Part | File |
|---|---|
| Heartbeat runner | scripts/podcast_scheduler_runner.sh |
| Installer | scripts/install-podcast-scheduler.sh |
| Linux entry | config/cron.d/podcast-scheduler |
| macOS template | config/launchd/com.openclaw.podcast-scheduler.plist.template |
| Recognition | scripts/guard-cron-inventory.py (box-scheduler recognition) |
| Processor (sibling slice) | scripts/podcast_controller.py (--once) |
