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
VERIFY_RECEIPTS=""

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
  --verify-receipts <path>    Post-cycle QC gate (deterministic). Reads
                              publish-receipts.json (file or workdir) and HARD-FAILS
                              (exit 6) when accounts are connected but 0 posts were
                              created, or posts were planned but 0 created. Run this
                              after the orchestrator finishes posting.
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

GOOGLE SHEET CONTENT CALENDAR (manual webhook sequence)
  This orchestrator does NOT create or populate the client's Google Sheet. Sheet
  creation and row-logging happen through two n8n webhooks on
  main.blackceoautomations.com, driven by the master orchestrator / publisher
  agent (see SKILL.md "Media Delivery Contract" + INSTALL.md Step 7, and the
  workflow definitions in config/n8n/):

    1) ONCE, at install (first run only) — create the sheet:
         curl -s -X POST "https://main.blackceoautomations.com/webhook/social-planner-sheet-create" \\
           -H "Content-Type: application/json" \\
           -d '{"brandName":"<brand>","clientEmail":"<email>","idempotencyKey":"<key>"}'
       -> returns {sheetUrl, sheetId, sheetName}; store sheetId in MEMORY.md.
       Never call this again for an existing client (idempotencyKey reconciles
       a create-then-crash rerun).

    2) EVERY publish cycle — log each content row (after media is uploaded to
       the GHL CDN and you have the CDN url):
         curl -s -X POST "https://main.blackceoautomations.com/webhook/social-planner-row-append" \\
           -H "Content-Type: application/json" \\
           -d '{"sheetId":"<content_sheet_id>","row":{"Week Of":"...","Theme of the Week":"...","Core Content":"...","Image URL":"=IMAGE(\\"https://assets.cdn.filesafe.space/...\\", 1)","Notes":"<CDN url>"}}'
       Image cells MUST be =IMAGE("url", 1) formula strings (not raw URLs); the
       webhook writes them with valueInputOption=USER_ENTERED and sizes the
       image column (~108px) and row (~133px). If a webhook call fails, log to
       ~/.openclaw/data/skill35/content-log.jsonl and retry next cycle.

  These calls are issued by the publishing agent at runtime, not by this script.

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
    --verify-receipts) VERIFY_RECEIPTS="${2:-}"; shift 2;;
    --help|-h)    SHOW_HELP=1; shift;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      echo "Try: $SCRIPT_NAME --help" >&2
      exit 2
      ;;
  esac
done

if [ "$SHOW_HELP" -eq 1 ]; then
  print_help
  exit 0
fi

# When called with no arguments, print help (don't fail noisily).
# (--verify-receipts is a standalone QC mode and must not be swallowed here.)
if [ -z "$TOPIC" ] && [ -z "$PLATFORMS" ] && [ "$DRY_RUN" -eq 0 ] && [ -z "$VERIFY_RECEIPTS" ]; then
  print_help
  exit 0
fi

# ---------- logging helpers ----------
RUN_ID="$(date +%Y%m%d-%H%M%S)-$$"
log()  { printf '[%s] [Skill35] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
warn() { printf '[%s] [Skill35][WARN] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }
err()  { printf '[%s] [Skill35][ERR ] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }

# ---------- Command Center (Kanban) helpers — fail-soft, operator-only ----------
# Every Command Center call is best-effort: a missing token or an unreachable
# board logs a warning and returns 0. Publishing MUST finish exactly as it would
# with no board at all. Never print the token. HTTP only — never touch the .db.
CC_BASE="${MISSION_CONTROL_URL:-http://localhost:4000}"
CC_TOKEN="${MC_API_TOKEN:-}"
CC_TASK_ID=""
CC_AGENT_ID="skill35-cycle"
CC_TOKEN_SKIP_LOGGED=0

_cc_resolve_token() {
  # Resolve MC_API_TOKEN in priority order (never silently skip on a stale path):
  #   1) env var already set (MC_API_TOKEN)
  #   2) ~/projects/command-center/.env.local     (run-full-install.sh DASHBOARD_DIR)
  #   3) ~/projects/command-center/.env           (run-full-install.sh DASHBOARD_DIR)
  #   4) /data/projects/command-center/.env.local (VPS container path)
  #   5) /data/projects/command-center/.env       (VPS container path)
  #   6) $HOME/command-center/app/.env.local      (legacy path — backward compat, checked last)
  [ -n "$CC_TOKEN" ] && return 0

  local candidates=(
    "$HOME_DIR/projects/command-center/.env.local"
    "$HOME_DIR/projects/command-center/.env"
    "/data/projects/command-center/.env.local"
    "/data/projects/command-center/.env"
    "$HOME_DIR/command-center/app/.env.local"
  )
  local envfile
  for envfile in "${candidates[@]}"; do
    [ -f "$envfile" ] || continue
    CC_TOKEN="$(grep -E '^MC_API_TOKEN=' "$envfile" 2>/dev/null | head -1 \
      | sed -E 's/^MC_API_TOKEN=//; s/^"//; s/"$//; s/\r$//')"
    [ -n "$CC_TOKEN" ] && return 0
  done

  if [ "$CC_TOKEN_SKIP_LOGGED" -eq 0 ]; then
    warn "[CC-SKIP] MC_API_TOKEN not found in: ${candidates[*]} — board update skipped (publishing continues)."
    CC_TOKEN_SKIP_LOGGED=1
  fi
  return 0
}

# cc_call <METHOD> <path> [json-body] -> echoes 2xx response body; ALWAYS returns 0.
cc_call() {
  local method="$1" path="$2" payload="${3:-}" resp http out
  _cc_resolve_token
  if [ -z "$CC_TOKEN" ]; then
    # _cc_resolve_token already emitted the loud [CC-SKIP] warning with the
    # full list of paths checked; don't spam a second, vaguer message here.
    return 0
  fi
  command -v curl >/dev/null 2>&1 || { warn "Command Center skipped — curl not available."; return 0; }
  if [ -n "$payload" ]; then
    resp="$(curl -sS -m 10 -w $'\n%{http_code}' -X "$method" "$CC_BASE$path" \
      -H "Authorization: Bearer $CC_TOKEN" -H "Content-Type: application/json" \
      -d "$payload" 2>/dev/null)" || { warn "Command Center $method $path unreachable — continuing."; return 0; }
  else
    resp="$(curl -sS -m 10 -w $'\n%{http_code}' -X "$method" "$CC_BASE$path" \
      -H "Authorization: Bearer $CC_TOKEN" 2>/dev/null)" || { warn "Command Center $method $path unreachable — continuing."; return 0; }
  fi
  http="$(printf '%s' "$resp" | tail -n1)"
  out="$(printf '%s' "$resp" | sed '$d')"
  case "$http" in
    2*) printf '%s' "$out"; return 0;;
    *)  warn "Command Center $method $path returned HTTP $http — continuing (board update is optional)."; return 0;;
  esac
}

# ---------- post-cycle receipts QC (deterministic 0-posts-as-error gate) ----------
# Reads publish-receipts.json and HARD-FAILS when accounts are connected but no
# posts were created, or posts were planned but none created. The posting step
# (master orchestrator, Phase 5) MUST emit publish-receipts.json with at least:
#   {"connected_accounts": N, "planned_posts": N, "created_posts": N,
#    "posts": [{"platform": "...", "post_id": "...", "url": "...", "tier": N}]}
verify_receipts() {
  local rfile="$1"
  [ -d "$rfile" ] && rfile="$rfile/publish-receipts.json"
  if [ ! -f "$rfile" ]; then
    err "publish-receipts.json not found at: $rfile"
    err "0 posts is an ERROR, not silent success — the posting step did not emit receipts."
    return 6
  fi
  python3 - "$rfile" <<'PYEOF'
import json, sys
p = sys.argv[1]
try:
    d = json.load(open(p))
except Exception as e:
    sys.stderr.write(f"[Skill35] receipts unreadable: {e}\n"); sys.exit(6)
connected = int(d.get("connected_accounts", 0) or 0)
planned   = int(d.get("planned_posts", 0) or 0)
created   = int(d.get("created_posts", 0) or 0)
if connected > 0 and created <= 0:
    sys.stderr.write(f"[Skill35] QC FAIL: {connected} account(s) connected but 0 posts created.\n"); sys.exit(6)
if planned > 0 and created <= 0:
    sys.stderr.write(f"[Skill35] QC FAIL: {planned} post(s) planned but 0 created.\n"); sys.exit(6)
if created < planned:
    sys.stderr.write(f"[Skill35] QC WARN: created {created} < planned {planned} (partial publish).\n")
print(f"[Skill35] receipts OK: planned={planned} created={created} connected={connected}")
PYEOF
}

log "$SCRIPT_NAME $SCRIPT_VERSION starting run-id=$RUN_ID"

# ---------- verify-receipts mode (post-cycle QC gate; runs and exits) ----------
if [ -n "$VERIFY_RECEIPTS" ]; then
  verify_receipts "$VERIFY_RECEIPTS"
  exit $?
fi

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

# ---------- GHL credential preflight (runtime HARD-STOP) ----------
# A publishing cycle cannot post without the GoHighLevel Private Integration
# Token (GOHIGHLEVEL_API_KEY) and the Location ID. Missing creds => STOP with a
# plain-English, operator-facing reason (never a silent no-op). Canonical names
# match Skill 36 / Skill 44 (caf). These are also exported for downstream phases.
if [ -f "$SECRETS_ENV" ]; then
  set +u; set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a; set -u
fi
: "${GOHIGHLEVEL_API_KEY:=}"
: "${GOHIGHLEVEL_LOCATION_ID:=}"
[ -n "$GOHIGHLEVEL_API_KEY" ]     || note_missing "GOHIGHLEVEL_API_KEY (GHL Private Integration Token) — required to publish; add it to $SECRETS_ENV"
[ -n "$GOHIGHLEVEL_LOCATION_ID" ] || note_missing "GOHIGHLEVEL_LOCATION_ID — required to publish (prevents cross-location posting); add it to $SECRETS_ENV"

# Optional live connection probe (OPT-IN: set SKILL35_LIVE_PREFLIGHT=1). When
# enabled it HARD-STOPS the batch if the PIT is rejected (401/403) or zero social
# accounts are connected — no rung can fix an un-connected OAuth account. A
# transient network error only WARNS (never false-blocks the cycle).
if [ "${SKILL35_LIVE_PREFLIGHT:-0}" = "1" ] && [ -n "$GOHIGHLEVEL_API_KEY" ] && [ -n "$GOHIGHLEVEL_LOCATION_ID" ] && command -v curl >/dev/null 2>&1; then
  log "live preflight: querying connected GHL social accounts (GET /social-media-posting/{loc}/accounts)"
  _probe="$(curl -sS -m 15 -w $'\n%{http_code}' \
    -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
    -H "Version: 2021-07-28" \
    "https://services.leadconnectorhq.com/social-media-posting/$GOHIGHLEVEL_LOCATION_ID/accounts" 2>/dev/null || true)"
  _phttp="$(printf '%s' "$_probe" | tail -n1)"
  _pbody="$(printf '%s' "$_probe" | sed '$d')"
  case "$_phttp" in
    401|403)
      err "GHL rejected the Private Integration Token (HTTP $_phttp). The PIT is expired/revoked or missing the social-media-posting scope."
      err "CLIENT MESSAGE: \"Your GoHighLevel Private Integration Token needs attention. In GHL go to Settings > Integrations > Private Integrations, regenerate the token with the social-media-posting.read/write scope, and send it to me. I will not post until this is fixed.\""
      exit 3
      ;;
    2*)
      _acct_count="$(printf '%s' "$_pbody" | python3 -c "import sys,json
try:
    d=json.load(sys.stdin)
    a=d.get('accounts') if isinstance(d,dict) else d
    print(len(a) if isinstance(a,list) else 0)
except Exception:
    print(-1)" 2>/dev/null || echo -1)"
      if [ "$_acct_count" = "0" ]; then
        err "GHL returned 0 connected social accounts for this location — there is nothing to publish to."
        err "CLIENT MESSAGE: \"I could not find any social accounts connected in your GoHighLevel Social Planner. Please connect at least one channel (Settings > Social Planner) and tell me when it is done. I will not post until a channel is connected.\""
        exit 3
      fi
      log "live preflight OK: connected account count = $_acct_count"
      ;;
    *)
      warn "live preflight inconclusive (HTTP '$_phttp') — transient/unknown; NOT blocking. Posting step will retry per playbook."
      ;;
  esac
fi

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

# ---------- Command Center: create-or-reuse card + mark in_progress ----------
# Operators see every run move across the board. Fail-soft: with the board down
# OR MC_API_TOKEN unset, this logs a skip, creates NO task, and the cycle finishes
# exactly as before (manifest + hand-off file, exit 0). QC promotes review->done;
# this script NEVER sets status=done.
CC_TASK_FILE="$WORKDIR/cc-task-id"
cc_create_body="$(python3 - "$TOPIC" "$PLATFORMS_NORM" "$RUN_ID" "$CC_AGENT_ID" <<'PYEOF'
import json, sys
topic, platforms, run_id, agent = sys.argv[1:5]
print(json.dumps({
    "title": ("Social cycle: " + topic)[:120],
    "description": (f"Skill 35 weekly publishing cycle (run {run_id}) for platforms: {platforms}. "
                    "Staged by run-publishing-cycle.sh in the Marketing/Content workspace; "
                    "QC promotes review->done."),
    "status": "backlog",
    "created_by_agent_id": agent,
    "updated_by_agent_id": agent,
}))
PYEOF
)"
cc_resp="$(cc_call POST /api/tasks "$cc_create_body")"
if [ -n "$cc_resp" ]; then
  CC_TASK_ID="$(printf '%s' "$cc_resp" | python3 -c "import sys,json
try:
    d=json.load(sys.stdin)
    print(d.get('id') or (d.get('task') or {}).get('id') or '')
except Exception:
    print('')" 2>/dev/null || true)"
fi
if [ -n "$CC_TASK_ID" ]; then
  printf '%s\n' "$CC_TASK_ID" > "$CC_TASK_FILE"
fi
# U100 — the producer-reconcile pattern generalized from B-U13/U27: ALWAYS
# record this run's board-ingest attempt outcome into the cycle manifest, not
# just on success, so `cycle_manifest_reconcile.py reconcile` can later tell
# "no card because nothing to build" apart from "no card because the board
# was unreachable/unconfigured and the cycle silently continued unregistered"
# — the same SKILL.md:607-608-style blindness B-U13 closed for Skill 6.
# Fail-soft: any error writing this is swallowed; NEVER blocks the cycle.
python3 - "$MANIFEST" "$CC_TASK_ID" "$CC_TOKEN" <<'PYEOF' 2>/dev/null || true
import json, sys
p, tid, token = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    d = json.load(open(p))
except Exception:
    d = {}
if tid:
    d["cc_task_id"] = tid
d["cc_board_attempt"] = {
    "mc_token_resolved": bool(token),
    "ok": bool(tid),
    "task_id": tid or None,
}
try:
    json.dump(d, open(p, "w"), indent=2)
except Exception:
    pass
PYEOF
if [ -n "$CC_TASK_ID" ]; then
  cc_call PATCH "/api/tasks/$CC_TASK_ID" \
    "{\"status\":\"in_progress\",\"updated_by_agent_id\":\"$CC_AGENT_ID\"}" >/dev/null
  log "Command Center: task $CC_TASK_ID created and moved to in_progress."
else
  log "Command Center: no task id captured (board optional) — continuing without a card."
fi

# ---------- phase execution ----------
# The actual sub-agent spawn is performed by the master orchestrator that
# invokes this script (per N5 + Skill 23's L255-L267 convention). This
# script writes the per-phase prompt files and a state-tracking journal,
# then signals "ready" so the orchestrator can pick them up.
#
# NOTE (Google Sheet): this orchestrator intentionally does NOT create or
# populate the client's Google Sheet content calendar. That is done by the
# master orchestrator / publisher agent via the two social-planner n8n webhooks
# (social-planner-sheet-create once at install, social-planner-row-append every
# cycle) — see the "GOOGLE SHEET CONTENT CALENDAR" block in --help, SKILL.md
# "Media Delivery Contract", INSTALL.md Step 7, and config/n8n/. Keeping sheet
# writes out of this script avoids double-creating sheets and keeps the webhook
# contract in one place.

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

# ---------- Command Center: hand-off -> review (QC promotes review->done) ----------
# The builder may NOT self-grade (QC gate): this script moves the card to 'review'
# and STOPS. The independent QC auto-scorer / dept QC agent promotes review->done.
if [ -n "$CC_TASK_ID" ]; then
  cc_call PATCH "/api/tasks/$CC_TASK_ID" \
    "{\"status\":\"review\",\"updated_by_agent_id\":\"$CC_AGENT_ID\"}" >/dev/null
  log "Command Center: task $CC_TASK_ID moved to review (QC promotes review->done; this script never sets done)."
fi

log "$SCRIPT_NAME complete."
exit 0
