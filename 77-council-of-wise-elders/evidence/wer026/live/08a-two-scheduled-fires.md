Proof A — two genuine launchd-scheduled fires
==============================================
No `launchctl kickstart` was run at any point. No shell ever invoked
runner.mjs directly. Every fire below was started by launchd from the
registered LaunchAgent (StartInterval 600, RunAtLoad true).

Fire 1
  launchd start → pid 89299 (admitted line in 06-fire1-launchd-stdout.raw.log)
  scheduled tick 1 start  2026-10-18T23:24:17.122Z  (action at_ms 1792365857122)
  receipt RCPT-000001, decision_kind SCHEDULED, completed_sweeps 1
  ledger_generation 1, process exit code 0

Fire 2
  launchd start → pid 17322 (distinct process, distinct admitted line)
  scheduled tick 2 start  2026-10-18T23:35:02.274Z  (action at_ms 1792366502274)
  receipt RCPT-000002, decision_kind SCHEDULED, completed_sweeps 2
  ledger_generation 2, process exit code 0

Measured separation of the two scheduled ticks: 645 s.
  = 600 s StartInterval + the 45 s in-tick work window (--tick-work-ms 45000).
  launchd re-arms StartInterval when the job exits; the job's own work window
  is therefore added to the wall-clock gap. The scheduling interval itself is
  exactly 600 s, as `launchctl print` reports: "run interval = 600 seconds".

launchd's own counters after fire 2 (05c-launchctl-print-after-fire2.raw.txt):
  runs = 2
  last exit code = 0
  run interval = 600 seconds

Durable evidence that the ticks were real scheduled sweeps, not manual runs:
  state.planner.scheduled_sweeps = 2, last_completion_kind = SCHEDULED,
  journal action per tick targeting its own pending id (PEND-000001,
  PEND-000002), and `completed_sweeps` advanced 0 → 1 → 2.
