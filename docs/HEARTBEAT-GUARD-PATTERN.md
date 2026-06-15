# HEARTBEAT Guard Pattern — Fleet-Wide Reference

**Version:** v1.0.0 (introduced v12.14.0)

## Why this exists

The fleet-wide heartbeat token furnace (diagnosed 2026-06-14) was caused by a recurring real-work task written as prose in a client's HEARTBEAT.md:

```markdown
### Saturday 8:00 AM — Social Media Theme Request
Ask client: "What's the theme for next week's social media content?"
```

The agent reads HEARTBEAT.md on **every heartbeat tick** (which can be as short as 5–30 minutes during onboarding). Because there was no day-of-week gate and no idempotency marker, the full Skill 35 content pipeline (15+ agent calls) fired on every tick, burning the metered model continuously.

**Proven root cause location:** `35-social-media-planner/INSTALL.md` Step 9 (pre-v12.14.0) appended this block to the live HEARTBEAT.md with no guards.

---

## The rule

**Never write a recurring real-work task directly into HEARTBEAT.md without guards.**

Real-work = any task that calls an API, runs a pipeline, sends a message, or invokes a sub-agent. Status checks and passive reads are not "real work."

**Preferred mechanism:** register a hard cron via `openclaw cron add`. Crons fire on a strict schedule and never run on heartbeat ticks.

---

## When a cron is not available: the guard pattern

If a recurring task absolutely must live in HEARTBEAT.md (rare), it MUST include BOTH:

1. **Day-of-week / time gate** — check with `date` before doing any work
2. **Idempotency marker** — a file that proves this period's fire already ran

```bash
#!/usr/bin/env bash
# ── HEARTBEAT.md recurring real-work guard pattern (fleet-wide template) ──
# Replace DOW, MARKER_PATH, PERIOD_KEY format, and the work block.

DOW=6                          # 1=Mon … 7=Sun (date +%u); 6=Saturday
MARKER_PATH="$HOME/.openclaw/data/<skill>/weekly-task-last-run.json"
PERIOD_KEY="$(date +%Y-%U)"   # ISO year + week number; change to %Y-%m-%d for daily

# Guard 1: day-of-week gate
if [ "$(date +%u)" != "$DOW" ]; then
  echo "HEARTBEAT guard: not the target day (day=$(date +%u), want=$DOW) — skip"
  exit 0
fi

# Guard 2: idempotency (already ran this period?)
if [ -f "$MARKER_PATH" ] && python3 -c "
import json, sys
d = json.load(open('$MARKER_PATH'))
sys.exit(0 if d.get('period') == '$PERIOD_KEY' else 1)
" 2>/dev/null; then
  echo "HEARTBEAT guard: already ran for period $PERIOD_KEY — skip"
  exit 0
fi

# ── Do real work here ────────────────────────────────────────────────────────
# ... your task ...

# ── Write idempotency marker ─────────────────────────────────────────────────
mkdir -p "$(dirname "$MARKER_PATH")"
python3 -c "
import json, datetime
json.dump(
  {'period': '$PERIOD_KEY', 'ts': datetime.datetime.utcnow().isoformat()},
  open('$MARKER_PATH', 'w')
)
"
echo "HEARTBEAT guard: work done for period $PERIOD_KEY — marker written"
```

---

## QC enforcement

Both `qc-skill35.sh` and `qc-social-media-planner.sh` assert that:

- INSTALL.md does NOT contain an ungated `Saturday 8:00 AM` HEARTBEAT.md task block
- INSTRUCTIONS.md contains the `skill35-weekly-theme` cron registration

A global grep guard is embedded in each QC script. Any INSTALL.md in this repo that re-introduces an ungated `### Saturday 8:00 AM` HEARTBEAT block will cause QC to fail (exit 1).

---

## Heartbeat cadence standards (v12.14.0)

| Agent type | Default `every` | Set via |
|---|---|---|
| `agents.defaults` (all agents) | `6h` | `install.sh` Fix D + `openclaw config set agents.defaults.heartbeat.every 6h` |
| `main` agent (explicit per-agent) | `6h` | `install.sh` Fix D2: `openclaw config set agents.list[main].heartbeat.every 6h` |
| Department sub-agents | DISABLED | `agentsOnly: ["main"]` |

**Why per-agent override for `main`?** `default: true` in `openclaw.json` marks the agent as the default routing target; it does NOT make that agent inherit `agents.defaults.heartbeat`. Any agent with `default: true` needs its OWN explicit `heartbeat.every` override or it falls back to the OpenClaw system default (which may be 5m or 30m, not 6h).

---

## Related files

- `35-social-media-planner/INSTALL.md` — Step 9 (furnace fix)
- `35-social-media-planner/INSTRUCTIONS.md` — §Weekly trigger, §Guard pattern
- `35-social-media-planner/qc-skill35.sh` — QC assertion Section I
- `35-social-media-planner/qc-social-media-planner.sh` — QC assertion Section I
- `install.sh` — Fix D (agents.defaults.heartbeat) + Fix D2 (per-agent main override)
