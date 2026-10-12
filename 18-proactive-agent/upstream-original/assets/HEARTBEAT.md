# HEARTBEAT.md - Periodic Check (bounded, report-only)

Rules (read first):
- Run at most 4 shell commands in total. Finish in under 3 minutes.
- Report only. Do not investigate, diagnose, repair or edit anything. Do not open other scripts, skills, cron jobs or other logs, and do not chase a finding.
- Never message the owner or any client from a heartbeat. Findings go in the one log line (step 3) only.
- If nothing needs attention, reply HEARTBEAT_OK.

1. Log review (one command). Use this box's OpenClaw logs folder (`~/.openclaw/logs`; `/data/.openclaw/logs` on Docker boxes):
   `tail -n 100 <logs folder>/*.log 2>/dev/null | grep -i "error\|fail\|warn" | tail -n 20`
   Summarise in one short phrase. Do not follow up on what it shows.

2. Disk (one command): `df -h / | tail -n 1`
   Note the used percentage. Do not clean anything up.

3. Record (one command): append one line `Heartbeat <date> <time>: <log review phrase>; disk <used %>` to `memory/heartbeat.log` in your workspace.

That is the whole checklist. Anything that needs action waits for the owner's next conversation or the scheduled jobs built for it.
