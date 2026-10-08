#!/usr/bin/env bash
# ============================================================
#  weekly-batch.sh
#  Skill 35 — Social Media Planner / Content Publishing Engine
#
#  Cron-driven weekly batch (`0 9 * * 1`) that reads
#  ~/.openclaw/config/content-calendar.json and runs the 5-phase
#  cycle for each scheduled topic in the current week.
#
#  Logs to /tmp/skill-35-weekly-<date>.log.
#
#  Closes the v10.14.33 gap: INSTRUCTIONS.md has referenced this
#  cron path since v10.12.0 but the script never existed.
# ============================================================
set -euo pipefail

SCRIPT_VERSION="v10.16.0"
SCRIPT_NAME="weekly-batch.sh"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HOME_DIR="${HOME:-/data}"

OPENCLAW_DIR="$HOME_DIR/.openclaw"
[ ! -d "$OPENCLAW_DIR" ] && [ -d "/data/.openclaw" ] && OPENCLAW_DIR="/data/.openclaw"

CALENDAR_JSON="$OPENCLAW_DIR/config/content-calendar.json"
EXAMPLE_TEMPLATE="$SKILL_DIR/scripts/content-calendar.example.json"
CYCLE_SCRIPT="$SCRIPT_DIR/run-publishing-cycle.sh"

# Persistent log dir — NOT /tmp (which is cleared on reboot; the skill's own cron
# doc requires persistence). Fall back to /tmp only if the dir cannot be created.
LOG_DIR="$OPENCLAW_DIR/data/skill35/logs"
mkdir -p "$LOG_DIR" 2>/dev/null || LOG_DIR="/tmp"
LOG_FILE="$LOG_DIR/skill-35-weekly-$(date +%Y%m%d).log"

log()  { printf '[%s] [Skill35-batch] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_FILE"; }
warn() { printf '[%s] [Skill35-batch][WARN] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_FILE" >&2; }
err()  { printf '[%s] [Skill35-batch][ERR ] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_FILE" >&2; }

# --- Exit codes:
#   0  = work done (one or more topics published)
#   10 = zero-work idle (no calendar or no entries due)
#   4+ = error (4=missing cycle script, 6=publishing failure)
ZERO_WORK_EXIT=10

# Zero-work heartbeat file (written every idle batch)
IDLE_HEARTBEAT="$OPENCLAW_DIR/data/skill35/last-zero-work-heartbeat"
HEARTBEAT_DIR="$(dirname "$IDLE_HEARTBEAT")"
mkdir -p "$HEARTBEAT_DIR" 2>/dev/null || true

write_idle_heartbeat() {
  local now_iso
  now_iso="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '{"status":"idle","reason":"%s","timestamp":"%s","batch_version":"%s"}\n' \
    "${1:-no-calendar}" "$now_iso" "$SCRIPT_VERSION" > "$IDLE_HEARTBEAT" 2>/dev/null || true
  log "zero-work heartbeat written to $IDLE_HEARTBEAT (reason: ${1:-no-calendar})"
}

# ---------- weekly drama-song step (plan 6.15, owner D27/D35) ----------
# ONE 9:16 ad per week from the Theme of the Week — one per batch, never one
# per topic. Runs before the calendar gate so an idle week still ships the ad.
# Fail-soft by contract: Skill 74 not active -> the step writes
# drama-song-skipped.json and exits 0 (a normal weekly outcome); module not
# staged yet -> warning and the batch continues. Skill 74 is the only KIE
# path; there is never a fallback to a private KIE client.
run_drama_song_step() {
  # Contract (plan 6.15, owner D27/D35): Skill 74 active mode only. When
  # the gate is closed the step writes drama-song-skipped.json, prints a
  # plain-English client reason and exits 0. Skill 74 is the only KIE
  # path; there is never a fallback to a private KIE client, so this
  # function never opens a second client and never spends.
  local step="" theme="" out="" rc marker factory_entry
  for step in \
      "$SKILL_DIR/../75-drama-song-ad-factory/scripts/core/smp/weekly_step/weekly_step.py" \
      "$HOME_DIR/.openclaw/skills/75-drama-song-ad-factory/scripts/core/smp/weekly_step/weekly_step.py"; do
    [ -f "$step" ] && break
    step=""
  done
  if [ -z "$step" ]; then
    warn "drama-song step skipped: core/smp/weekly_step/weekly_step.py is not staged on this box yet"
    return 0
  fi
  for factory_entry in \
      "$SKILL_DIR/../75-drama-song-ad-factory/scripts/core/intake_preflight/factory.py" \
      "$HOME_DIR/.openclaw/skills/75-drama-song-ad-factory/scripts/core/intake_preflight/factory.py"; do
    [ -f "$factory_entry" ] && break
    factory_entry=""
  done

  theme="${DRAMA_SONG_THEME:-}"
  marker="$OPENCLAW_DIR/data/skill35/weekly-theme-last-run.json"
  if [ -z "$theme" ] && [ -f "$marker" ]; then
    theme="$(python3 -c 'import json,sys
try:
    print(json.load(open(sys.argv[1])).get("theme") or "")
except Exception:
    pass' "$marker" 2>/dev/null || true)"
  fi
  if [ -z "$theme" ]; then
    warn "drama-song step skipped: no Theme of the Week (set DRAMA_SONG_THEME, or let the Saturday skill35-weekly-theme cron record one)"
    return 0
  fi

  out="$OPENCLAW_DIR/data/skill35/drama-song/$(date +%Y%m%d)"
  mkdir -p "$out" 2>/dev/null || out="/tmp"
  log "drama-song step = $step (theme: $theme)"
  if [ -n "$factory_entry" ]; then
    if python3 "$step" --theme "$theme" --out-dir "$out" \
         --factory-entry "$factory_entry" >>"$LOG_FILE" 2>&1; then
      log "   ok drama-song step finished (generated, or intentionally skipped while KIE is off)"
    else
      rc=$?
      warn "   drama-song step rc=$rc - see $LOG_FILE (weekly batch continues; a KIE-off skip exits 0)"
    fi
  else
    # No factory entry staged: keep the step's own behavior (it asks for the
    # entry or reports the miss in its result envelope); never invent a path.
    if python3 "$step" --theme "$theme" --out-dir "$out" >>"$LOG_FILE" 2>&1; then
      log "   ok drama-song step finished (no factory entry staged; step handled it)"
    else
      rc=$?
      warn "   drama-song step rc=$rc - see $LOG_FILE (weekly batch continues; a KIE-off skip exits 0)"
    fi
  fi
  _drama_song_row_fields "$out"
  return 0
}

# ---------- H5 (B5 step 4): map the weekly step's result to the row ----------
# The Weekly Overview drama-song columns use the INSTALLED schema 1.3.0 keys
# from config/sheet-template.schema.json (drama_song block): drama_song_style,
# drama_song_status, kie_cost_cents, drama_song_video_url, drama_song_channels.
# This reads the step's own drama-song-result.json / drama-song-skipped.json
# and writes one sidecar the row-append caller (or the publisher agent) picks
# up for the Weekly Overview row — it never posts by itself and never invents
# a column name. Key names below are copied from the installed contract, never
# renamed here.
_drama_song_row_fields() {
  local out="$1" result_file status
  result_file="$out/drama-song-result.json"
  [ -f "$result_file" ] || result_file="$out/drama-song-skipped.json"
  [ -f "$result_file" ] || { warn "drama-song: no result/skipped artifact in $out (row fields not written)"; return 0; }
  command -v python3 >/dev/null 2>&1 || return 0
  python3 - "$result_file" "$out/drama-song-row-fields.json" <<'PYEOF' 2>>"$LOG_FILE" || warn "drama-song: could not derive row fields (batch continues)"
import json, sys, os

src, dst = sys.argv[1], sys.argv[2]
try:
    doc = json.load(open(src, encoding="utf-8"))
except Exception as exc:
    sys.stderr.write("drama-song row fields: unreadable %s: %s\n" % (src, exc))
    sys.exit(0)

style = doc.get("style") or {}
style_text = ", ".join(str(style.get(k)) for k in
                       ("look", "music", "voice", "length")
                       if style.get(k) not in (None, ""))
status = str(doc.get("status") or "")
cost = doc.get("cost_cents")
cost_str = ""
if isinstance(cost, int) and not isinstance(cost, bool):
    cost_str = str(cost)
elif isinstance(cost, float):
    cost_str = str(int(cost))
channels = doc.get("channels") or []
video_path = doc.get("video_path") or doc.get("stories_teaser_path") or ""

fields = {
    # Installed schema 1.3.0 drama_song keys (config/sheet-template.schema.json).
    "drama_song_style": style_text,
    "drama_song_status": status,          # ok | dry-run | skipped | waiting | ...
    "kie_cost_cents": cost_str,           # whole usd_cents, RAW
    "drama_song_video_url": os.path.expanduser(str(video_path)) if video_path else "",
    "drama_song_channels": ", ".join(str(c) for c in channels),
    "_source_artifact": os.path.basename(src),
    "_week_dir": os.path.dirname(src),
}
tmp = dst + ".tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump(fields, fh, indent=2, sort_keys=True)
    fh.write("\n")
os.replace(tmp, dst)
print("drama-song row fields written: %s" % dst)
PYEOF
  return 0
}

case "${1:-}" in
  --help|-h)
    cat <<EOF
$SCRIPT_NAME ($SCRIPT_VERSION) — Skill 35 weekly cron batch

CRON
  0 9 * * 1 bash $SCRIPT_DIR/$SCRIPT_NAME

WHAT IT DOES
  Reads $CALENDAR_JSON, finds every entry whose 'date' falls between
  today (Monday, 00:00 local) and the following Sunday (23:59 local),
  and invokes run-publishing-cycle.sh once per entry with that entry's
  topic + platforms.

CALENDAR FORMAT
  {
    "version": "v1.0",
    "entries": [
      { "date": "2026-05-25", "topic": "...", "platforms": ["linkedin", "x"] },
      { "date": "2026-05-27", "topic": "...", "platforms": ["medium"] }
    ]
  }

  See $EXAMPLE_TEMPLATE for a complete starter.

LOG
  $LOG_FILE
EOF
    exit 0
    ;;
esac

log "$SCRIPT_NAME $SCRIPT_VERSION starting"
log "calendar  = $CALENDAR_JSON"
log "cycle     = $CYCLE_SCRIPT"
log "log       = $LOG_FILE"

# ---------- ensure the cycle script exists ----------
if [ ! -x "$CYCLE_SCRIPT" ]; then
  if [ -f "$CYCLE_SCRIPT" ]; then
    chmod +x "$CYCLE_SCRIPT" || true
  fi
fi
if [ ! -f "$CYCLE_SCRIPT" ]; then
  err "run-publishing-cycle.sh not found at $CYCLE_SCRIPT — re-run update-skills.sh."
  exit 4
fi

# ---------- weekly drama-song ad (before the calendar gate) ----------
run_drama_song_step

# ---------- ensure calendar exists ----------
if [ ! -f "$CALENDAR_JSON" ]; then
  cat | tee -a "$LOG_FILE" <<EOF

────────────────────────────────────────────────────────────────────
  Skill 35 weekly batch: no content calendar found.
────────────────────────────────────────────────────────────────────

Expected file: $CALENDAR_JSON

This is informational, not a failure — the calendar is opt-in. To
enable weekly automation:

  1. Copy the starter template:
       mkdir -p $(dirname "$CALENDAR_JSON")
       cp $EXAMPLE_TEMPLATE $CALENDAR_JSON

  2. Edit it to list the topics + platforms + dates you want
     published this quarter.

  3. The cron line in INSTRUCTIONS.md (\`0 9 * * 1\`) will then
     fire run-publishing-cycle.sh once per scheduled topic each
     Monday morning.

Exiting $ZERO_WORK_EXIT (nothing to do today -- idle heartbeat).
────────────────────────────────────────────────────────────────────
EOF
  write_idle_heartbeat "no-calendar"
  exit $ZERO_WORK_EXIT
fi

# ---------- parse + filter calendar ----------
if ! command -v python3 >/dev/null 2>&1; then
  err "python3 is required to parse the calendar. Install python3 and retry."
  exit 1
fi

DUE_THIS_WEEK="$(python3 - "$CALENDAR_JSON" <<'PYEOF'
import json, sys, datetime as dt

path = sys.argv[1]
try:
    data = json.load(open(path))
except Exception as e:
    print(f"# parse-error: {e}", file=sys.stderr); sys.exit(2)

entries = data.get("entries") or data.get("calendar") or []
if not isinstance(entries, list):
    print("# entries: not a list", file=sys.stderr); sys.exit(2)

today = dt.date.today()
# Monday of this week
monday = today - dt.timedelta(days=today.weekday())
sunday = monday + dt.timedelta(days=6)

count = 0
for e in entries:
    if not isinstance(e, dict): continue
    d = e.get("date")
    topic = e.get("topic")
    platforms = e.get("platforms") or []
    if not d or not topic or not platforms: continue
    try:
        ed = dt.datetime.strptime(d, "%Y-%m-%d").date()
    except Exception:
        continue
    if monday <= ed <= sunday:
        plats = ",".join(str(p) for p in platforms)
        sched = e.get("schedule", "auto")
        # tab-separated: date \t topic \t platforms \t schedule
        # Escape tabs in topic just in case.
        safe_topic = topic.replace("\t", " ")
        print(f"{d}\t{safe_topic}\t{plats}\t{sched}")
        count += 1

print(f"# matched: {count}", file=sys.stderr)
PYEOF
)" || true

if [ -z "$DUE_THIS_WEEK" ]; then
  log "calendar present but no entries match the current week. Nothing to do."
  write_idle_heartbeat "no-matching-entries"
  exit $ZERO_WORK_EXIT
fi

COUNT=$(printf '%s\n' "$DUE_THIS_WEEK" | grep -c . || true)
log "found $COUNT topic(s) due this week"

# ---------- iterate ----------
FAIL=0
INDEX=0
while IFS=$'\t' read -r CAL_DATE TOPIC PLATFORMS SCHEDULE; do
  [ -z "$TOPIC" ] && continue
  INDEX=$((INDEX+1))
  log "── topic $INDEX/$COUNT: [$CAL_DATE] $TOPIC ($PLATFORMS, schedule=$SCHEDULE)"
  if bash "$CYCLE_SCRIPT" \
       --topic "$TOPIC" \
       --platforms "$PLATFORMS" \
       --schedule "$SCHEDULE" >>"$LOG_FILE" 2>&1; then
    log "   ✓ cycle queued"
  else
    RC=$?
    warn "   ✗ cycle failed (rc=$RC) — see $LOG_FILE"
    FAIL=$((FAIL+1))
  fi
done <<<"$DUE_THIS_WEEK"

log "weekly batch complete. ok=$((COUNT-FAIL)) fail=$FAIL of $COUNT"
[ "$FAIL" -gt 0 ] && exit 6 || exit 0
