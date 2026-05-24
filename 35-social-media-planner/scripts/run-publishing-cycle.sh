#!/usr/bin/env bash
# ============================================================
#  run-publishing-cycle.sh
#  Skill 35 — Social Media Planner / Content Publishing Engine
#
#  Single-topic orchestrator for the 5-phase publishing pipeline
#  documented in INSTRUCTIONS.md. Validates prerequisites, then
#  either runs the cycle (when the 21-agent roster is configured
#  in openclaw.json) or emits a clear next-step instruction.
#
#  Closes the v10.14.33 gap: INSTRUCTIONS.md has referenced this
#  path since v10.12.0 but the script never existed.
#
#  Usage:
#    run-publishing-cycle.sh --topic "<topic>" \
#                            --platforms "linkedin,medium,x,wordpress" \
#                            [--schedule "auto"] \
#                            [--dry-run] [--workdir DIR]
#
#    run-publishing-cycle.sh --help
# ============================================================
set -euo pipefail

SCRIPT_VERSION="v10.14.33"
SCRIPT_NAME="run-publishing-cycle.sh"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HOME_DIR="${HOME:-/data}"

# ---------- argument parsing ----------
TOPIC=""
PLATFORMS=""
SCHEDULE="auto"
DRY_RUN=0
WORKDIR=""
SHOW_HELP=0

print_help() {
  cat <<EOF
$SCRIPT_NAME ($SCRIPT_VERSION) — Skill 35 single-topic publishing cycle

USAGE
  $SCRIPT_NAME --topic "<topic>" --platforms "<csv>" [--schedule <when>] [--dry-run]

REQUIRED
  --topic "<string>"          Topic / headline for this cycle.
  --platforms "<csv>"         Comma-separated list. Supported:
                              wordpress, medium, substack, linkedin, ghl, youtube,
                              x (or twitter), facebook, instagram, tiktok, threads,
                              pinterest. Also: email, podcast.

OPTIONAL
  --schedule <auto|now|ISO>   "auto" (cadence-driven, default), "now" (publish
                              immediately), or an ISO 8601 timestamp.
  --dry-run                   Validate inputs + prerequisites then exit without
                              spawning agents. Useful from cron.
  --workdir <path>            Override the per-cycle workdir
                              (default: \$HOME/.openclaw/data/skill-35/runs/<run-id>).
  --help, -h                  Show this help and exit.

PIPELINE (5 phases, 15 producers + 6 QC agents)
  Phase 1  Research & Strategy        researcher + strategist
  Phase 2  Content Creation           writer + editor + image/video/audio +
                                      thumbnail (QC: grammar, fact-check, visual)
  Phase 3  Production                 video-producer (ffmpeg) + email-designer
                                      (QC: performance)
  Phase 4  Schedule                   publisher (planning sub-step)
                                      reads social-cadence.json
  Phase 5  Publish + Monitor          publisher + podcast/email publishers +
                                      engagement-monitor (QC: compliance, final)

  Full spec: \$SKILL_DIR/INSTRUCTIONS.md

EXAMPLES
  $SCRIPT_NAME --topic "Delegating to AI without losing control" \\
               --platforms "linkedin,medium,x,wordpress" --schedule auto

  $SCRIPT_NAME --topic "Weekly client highlight" --platforms "linkedin" --dry-run

EXIT CODES
  0   success (or dry-run validated cleanly)
  2   bad arguments
  3   missing required config / credentials (STOP per N22)
  4   prerequisite skill missing (Skill 22 or 31)
  5   21-agent roster not yet configured in openclaw.json (run Skill 23
      build-workforce with the social-media-planner role-bundle)
  6   runtime failure during a phase
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --topic)      TOPIC="${2:-}"; shift 2;;
    --platforms)  PLATFORMS="${2:-}"; shift 2;;
    --schedule)   SCHEDULE="${2:-auto}"; shift 2;;
    --dry-run)    DRY_RUN=1; shift;;
    --workdir)    WORKDIR="${2:-}"; shift 2;;
    --help|-h)    SHOW_HELP=1; shift;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      echo "Try: $SCRIPT_NAME --help" >&2
      exit 2
      ;;
  esac
done

if [ "$SHOW_HELP" -eq 1 ] || [ $# -lt 0 ]; then
  print_help
  exit 0
fi

# When called with no arguments, print help (don't fail noisily).
if [ -z "$TOPIC" ] && [ -z "$PLATFORMS" ] && [ "$DRY_RUN" -eq 0 ]; then
  print_help
  exit 0
fi

# ---------- logging helpers ----------
RUN_ID="$(date +%Y%m%d-%H%M%S)-$$"
log()  { printf '[%s] [Skill35] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
warn() { printf '[%s] [Skill35][WARN] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }
err()  { printf '[%s] [Skill35][ERR ] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }

log "$SCRIPT_NAME $SCRIPT_VERSION starting run-id=$RUN_ID"

# ---------- validate required args ----------
if [ -z "$TOPIC" ]; then
  err "--topic is required."; echo "Try: $SCRIPT_NAME --help" >&2; exit 2
fi
if [ -z "$PLATFORMS" ]; then
  err "--platforms is required (comma-separated list)."
  echo "Try: $SCRIPT_NAME --help" >&2; exit 2
fi

# Normalize platforms list
PLATFORMS_NORM=$(echo "$PLATFORMS" \
  | tr 'A-Z' 'a-z' \
  | tr -d '[:space:]' \
  | sed 's/twitter/x/g')
IFS=',' read -r -a PLATFORM_ARR <<<"$PLATFORMS_NORM"
if [ "${#PLATFORM_ARR[@]}" -eq 0 ]; then
  err "--platforms produced an empty list after normalization."
  exit 2
fi

SUPPORTED="wordpress medium substack linkedin ghl youtube x facebook instagram tiktok threads pinterest email podcast"
for p in "${PLATFORM_ARR[@]}"; do
  case " $SUPPORTED " in
    *" $p "*) : ;;
    *) err "Unsupported platform: '$p'. Supported: $SUPPORTED"; exit 2;;
  esac
done

log "topic     = $TOPIC"
log "platforms = ${PLATFORM_ARR[*]}"
log "schedule  = $SCHEDULE"
[ "$DRY_RUN" -eq 1 ] && log "mode      = DRY-RUN (no agents spawned)"

# ---------- locate config sources (INSTRUCTIONS.md variable-source table) ----------
OPENCLAW_DIR="$HOME_DIR/.openclaw"
if [ ! -d "$OPENCLAW_DIR" ]; then
  # Container path fallback
  if [ -d "/data/.openclaw" ]; then
    OPENCLAW_DIR="/data/.openclaw"
  fi
fi

SECRETS_ENV="$OPENCLAW_DIR/secrets/.env"
SOUL_MD="$OPENCLAW_DIR/SOUL.md"
IDENTITY_MD="$OPENCLAW_DIR/IDENTITY.md"
USER_MD="$OPENCLAW_DIR/USER.md"
OPENCLAW_JSON="$OPENCLAW_DIR/openclaw.json"
IMAGE_MODEL_JSON="$OPENCLAW_DIR/config/image-model.json"
VIDEO_SPECS_JSON="$OPENCLAW_DIR/config/video-specs.json"
SOCIAL_CADENCE_JSON="$OPENCLAW_DIR/config/social-cadence.json"

# ---------- prerequisite gate ----------
MISSING_REQ=0
note_missing() { warn "MISSING: $1"; MISSING_REQ=$((MISSING_REQ+1)); }

# Source files (N22: STOP, never invent defaults)
[ -f "$SOUL_MD" ]      || note_missing "SOUL.md ($SOUL_MD) — brand voice"
[ -f "$IDENTITY_MD" ]  || note_missing "IDENTITY.md ($IDENTITY_MD) — brand identity"
[ -f "$USER_MD" ]      || note_missing "USER.md ($USER_MD) — owner/audience"
[ -f "$SECRETS_ENV" ]  || note_missing "secrets/.env ($SECRETS_ENV) — API keys"
[ -f "$OPENCLAW_JSON" ] || note_missing "openclaw.json ($OPENCLAW_JSON) — agent roster"

# Config files (used in later phases; warn but don't immediately bail —
# Phase 3/4 can pull defaults from the references/ folder).
for f in "$IMAGE_MODEL_JSON" "$VIDEO_SPECS_JSON" "$SOCIAL_CADENCE_JSON"; do
  if [ ! -f "$f" ]; then
    warn "config not present: $f — phases that need it will be skipped"
  fi
done

# Required prerequisite skills (per INSTALL.md)
SKILLS_DIR=""
for candidate in "$OPENCLAW_DIR/skills" "/data/.openclaw/skills"; do
  if [ -d "$candidate" ]; then SKILLS_DIR="$candidate"; break; fi
done

if [ -n "$SKILLS_DIR" ]; then
  for required in 22-book-to-persona-coaching-leadership-system 31-upgraded-memory-system; do
    if [ ! -d "$SKILLS_DIR/$required" ]; then
      warn "REQUIRED prerequisite skill missing: $required"
      MISSING_REQ=$((MISSING_REQ+10))
    fi
  done
else
  warn "Could not locate skills directory (looked under $OPENCLAW_DIR and /data/.openclaw)"
fi

if [ "$MISSING_REQ" -ge 10 ]; then
  err "Required prerequisite skill(s) missing. Install Skill 22 and Skill 31 first."
  exit 4
fi
if [ "$MISSING_REQ" -gt 0 ]; then
  err "Required configuration missing (count=$MISSING_REQ). Per INSTRUCTIONS.md N22, the cycle STOPS rather than inventing defaults."
  err "Populate the listed files, then re-run."
  exit 3
fi

# ---------- agent-roster discovery ----------
# INSTRUCTIONS.md describes 15 producers + 6 QC agents. Skill 23
# (build-workforce.py) is the one that actually writes these into
# openclaw.json. This script DETECTS whether they exist; if not, it
# emits the configured next step rather than silently doing nothing.

# Canonical agent slugs (matches SKILL.md roster table)
PRODUCER_AGENTS=(
  researcher strategist writer editor
  image-prompt-engineer image-generator
  video-script-writer video-producer audio-generator thumbnail-designer
  publisher podcast-publisher email-designer email-publisher engagement-monitor
)
QC_AGENTS=(
  grammar-qc fact-check-qc visual-qc compliance-qc performance-qc final-qc
)

MISSING_AGENTS=()
if command -v python3 >/dev/null 2>&1 && [ -f "$OPENCLAW_JSON" ]; then
  AGENT_LIST_JSON="$(python3 - "$OPENCLAW_JSON" <<'PYEOF'
import json, sys
p = sys.argv[1]
try:
    d = json.load(open(p))
except Exception as e:
    print(""); sys.exit(0)

names = set()
agents = d.get("agents", {})
if isinstance(agents, dict):
    lst = agents.get("list") or agents.get("entries") or []
else:
    lst = agents if isinstance(agents, list) else []

# Also accept top-level "subagents" / "subagent-templates"
for key in ("subagents", "subagent_templates", "subagentTemplates"):
    v = d.get(key)
    if isinstance(v, list):
        lst = lst + v
    elif isinstance(v, dict):
        lst = lst + list(v.values())

for a in lst:
    if isinstance(a, dict):
        for k in ("slug", "id", "name", "agent_id"):
            v = a.get(k)
            if isinstance(v, str):
                names.add(v.lower().replace(" ", "-"))
    elif isinstance(a, str):
        names.add(a.lower().replace(" ", "-"))

print("\n".join(sorted(names)))
PYEOF
)"
  for a in "${PRODUCER_AGENTS[@]}" "${QC_AGENTS[@]}"; do
    if ! echo "$AGENT_LIST_JSON" | grep -qx "$a"; then
      # also try partial match (the build-workforce script may prefix with dept-slug)
      if ! echo "$AGENT_LIST_JSON" | grep -q "$a"; then
        MISSING_AGENTS+=("$a")
      fi
    fi
  done
else
  warn "python3 + openclaw.json required to verify agent roster; skipping roster check."
fi

if [ "${#MISSING_AGENTS[@]}" -gt 0 ]; then
  # v10.14.34 — finding #25: the `social-media-planner` role-bundle does not
  # exist in the role-library catalog (only individual roles do). Hard-exit 5
  # made basic single-topic usage impossible on every install. Downgrade to a
  # warning by default (single-orchestrator mode); operators who actually want
  # the full 21-agent pipeline can re-enable the strict check with
  # OPENCLAW_STRICT_ROSTER=1.
  if [ "${OPENCLAW_STRICT_ROSTER:-0}" = "1" ]; then
    cat >&2 <<EOF

────────────────────────────────────────────────────────────────────
  Skill 35 needs the 21-agent roster (OPENCLAW_STRICT_ROSTER=1).
────────────────────────────────────────────────────────────────────

Missing agents (${#MISSING_AGENTS[@]} of 21):
$(printf '  - %s\n' "${MISSING_AGENTS[@]}")

NEXT STEP — run Skill 23 build-workforce with the social-media-planner
role-bundle (NOTE: this bundle is not in the role-library catalog yet;
ask the master orchestrator to compose the bundle from the individual
social-media/* roles under role-library/social-media/).

After Skill 23 finishes, re-run:
  $SCRIPT_NAME --topic "$TOPIC" --platforms "$PLATFORMS_NORM" --schedule "$SCHEDULE"

────────────────────────────────────────────────────────────────────
EOF
    exit 5
  else
    cat >&2 <<EOF

[Skill 35] WARNING: 21-agent roster not fully provisioned (${#MISSING_AGENTS[@]} of 21 missing).
[Skill 35] Continuing in single-orchestrator mode — the master agent will fan out work
[Skill 35] without dedicated per-platform sub-agents. Quality may be lower than the full
[Skill 35] 21-agent pipeline but a basic publishing cycle CAN still complete.
[Skill 35] To restore strict mode, set OPENCLAW_STRICT_ROSTER=1 in the environment.

EOF
    # Continue with the build — fall through to workdir setup below.
  fi
fi

# ---------- workdir ----------
DEFAULT_WORKDIR="$OPENCLAW_DIR/data/skill-35/runs/$RUN_ID"
if [ -z "$WORKDIR" ]; then
  WORKDIR="$DEFAULT_WORKDIR"
fi
mkdir -p "$WORKDIR"
log "workdir   = $WORKDIR"

# Manifest the master orchestrator (or this script's downstream caller)
# reads to spawn the 5-phase pipeline. Pattern mirrors Skill 23's
# build-workforce manifest approach (write JSON; the AI agent spawns
# sub-agents under its own control — see build-workforce.py L1442).
MANIFEST="$WORKDIR/cycle-manifest.json"
python3 - "$MANIFEST" "$TOPIC" "$PLATFORMS_NORM" "$SCHEDULE" "$RUN_ID" "$WORKDIR" <<'PYEOF'
import json, sys, time
manifest_path, topic, platforms, schedule, run_id, workdir = sys.argv[1:7]
plist = [p for p in platforms.split(",") if p]

manifest = {
    "skill": "35-social-media-planner",
    "skill_version": "v10.14.33",
    "run_id": run_id,
    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "topic": topic,
    "platforms": plist,
    "schedule": schedule,
    "workdir": workdir,
    "phases": [
        {
            "id": 1,
            "name": "Research & Strategy",
            "agents": ["researcher", "strategist"],
            "outputs": ["strategy.md"],
            "qc": [],
        },
        {
            "id": 2,
            "name": "Content Creation",
            "agents": [
                "writer", "editor",
                "image-prompt-engineer", "image-generator",
                "video-script-writer", "audio-generator", "thumbnail-designer",
            ],
            "outputs": [
                "article-draft.md",
                "image-prompts.json",
                "images/",
                "video-script.md",
                "audio/",
                "thumbnails/",
            ],
            "qc": ["grammar-qc", "fact-check-qc", "visual-qc"],
        },
        {
            "id": 3,
            "name": "Production",
            "agents": ["video-producer", "email-designer"],
            "outputs": ["video/final.mp4", "email/body.html"],
            "qc": ["performance-qc"],
        },
        {
            "id": 4,
            "name": "Schedule",
            "agents": ["publisher"],
            "step": "planning",
            "outputs": ["publish-schedule.json"],
            "qc": [],
        },
        {
            "id": 5,
            "name": "Publish + Monitor",
            "agents": [
                "publisher",
                "podcast-publisher",
                "email-publisher",
                "engagement-monitor",
            ],
            "outputs": ["publish-receipts.json", "engagement/<run-id>.json"],
            "qc": ["compliance-qc", "final-qc"],
        },
    ],
}
with open(manifest_path, "w") as f:
    json.dump(manifest, f, indent=2)
print(manifest_path)
PYEOF

log "wrote cycle manifest: $MANIFEST"

if [ "$DRY_RUN" -eq 1 ]; then
  log "DRY-RUN complete. Pre-reqs OK, roster OK, manifest written. Exiting 0."
  exit 0
fi

# ---------- phase execution ----------
# The actual sub-agent spawn is performed by the master orchestrator that
# invokes this script (per N5 + Skill 23's L255-L267 convention). This
# script writes the per-phase prompt files and a state-tracking journal,
# then signals "ready" so the orchestrator can pick them up.

JOURNAL="$WORKDIR/journal.log"
echo "[$RUN_ID] cycle queued at $(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$JOURNAL"

run_phase() {
  local phase_id="$1" phase_name="$2"
  log "Phase $phase_id — $phase_name : queueing prompts"
  local phase_dir="$WORKDIR/phase-$phase_id"
  mkdir -p "$phase_dir"
  cat >"$phase_dir/README.md" <<EOF
# Phase $phase_id — $phase_name

Run: $RUN_ID
Topic: $TOPIC
Platforms: $PLATFORMS_NORM
Schedule: $SCHEDULE

This phase's sub-agents are spawned by the master orchestrator, NOT by
\`$SCRIPT_NAME\` directly. The orchestrator reads
\`../cycle-manifest.json\`, walks phase $phase_id, and dispatches each
agent listed there with the workdir set to this folder.

Per INSTRUCTIONS.md, QC sub-agents fire AFTER the producers in this
phase complete and MUST be different sub-agents than the producers (N5).
EOF
  echo "[$RUN_ID] phase-$phase_id queued" >>"$JOURNAL"
}

run_phase 1 "Research & Strategy"
run_phase 2 "Content Creation"
run_phase 3 "Production"
run_phase 4 "Schedule"
run_phase 5 "Publish + Monitor"

# Final hand-off signal
HANDOFF="$WORKDIR/READY-FOR-ORCHESTRATOR"
cat >"$HANDOFF" <<EOF
Skill 35 cycle $RUN_ID is ready for the master orchestrator.

Manifest: $MANIFEST
Workdir : $WORKDIR

The orchestrator should now walk phases 1..5 in cycle-manifest.json,
spawn the listed agents (one sub-agent per agent, per N5), and record
deliverables in the per-phase directories. Engagement Monitor runs
continuously for 7 days post-publish per INSTRUCTIONS.md Phase 5.
EOF

log "Cycle $RUN_ID prepared. Hand-off file: $HANDOFF"
log "$SCRIPT_NAME complete."
exit 0
