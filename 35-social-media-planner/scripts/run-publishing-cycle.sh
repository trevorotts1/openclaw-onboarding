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

SCRIPT_VERSION="v10.15.0"
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
ACK_EXECUTION=0
WORKER_ID=""
EXECUTION_ID=""
COMPLETE_PHASE=""
MARK_REVIEW=0
STATUS_ONLY=0
OVERDUE_AFTER="${SKILL35_OVERDUE_AFTER:-900}"

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
  --ack-execution             (worker) Accept the staged dispatch on behalf of
                              --worker-id and record the accepted execution in the
                              durable dispatch record. ONLY after an accepted ack
                              may the CC task move to in_progress. Requires --workdir.
  --worker-id <id>            Worker identity for --ack-execution.
  --execution-id <id>         Optional execution id recorded with the ack
                              (defaults to <run_id>:<worker_id>).
  --complete-phase <id>       (worker) Record phase <id> (1-5) complete: requires
                              an accepted worker ack, the phase's artifacts under
                              working/phase-<id>/artifacts, and a verified
                              artifacts.sha256 manifest. Requires --workdir.
  --mark-review               (worker/orchestrator) Move the cycle to review. ONLY
                              after EVERY phase is complete with verified artifact
                              hashes. This is the ONLY path to review — staging
                              never sets it. Requires --workdir.
  --status                    Print the durable dispatch state as JSON (queued |
                              in_progress | review) plus the overdue condition.
                              Requires --workdir. Read-only; never mutates state.
  --overdue-after <seconds>   Overdue threshold for --status (default 900s). A
                              QUEUED cycle past this threshold with no worker ack
                              is OVERDUE — workers stopped means the cycle stays
                              queued + overdue, never review/done.
  --help, -h                  Show this help and exit.

LIFECYCLE (F04 — staging is NOT work-ready-for-review)
  The default invocation STAGES the cycle: it writes the manifest, prompts and
  a DURABLE DISPATCH RECORD (working/dispatch.json) and returns an explicit
  QUEUED result. It does NOT move the Command Center task to in_progress and
  does NOT move it to review. With every worker stopped the cycle remains
  queued (visible as overdue via --status) with NO review/completion receipt.

    stage (this script, default)   -> state=queued  (CC card stays backlog)
    --ack-execution --worker-id W  -> state=in_progress (accepted execution;
                                      CC card moves in_progress HERE, not before)
    --complete-phase N (per phase) -> phase recorded complete with verified
                                      sha256 artifact hashes
    --mark-review                  -> state=review (CC card moves review; the
                                      independent QC sweep owns review->done)

  Each phase carries a durable operation key (W0 dispatch.json contract) and a
  consumer binding (Command Center social-publish-dispatcher / F33 execution
  policy): a stopped consumer leaves the cycle queued + overdue, never done.

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
           -d '{"brandName":"<brand>","clientEmail":"<email>","company_id":"<company_id>","planner_kind":"social-planner","templateSheetId":"<template_sheet_id>"}'
       -> returns {status, deduped, sheetUrl, sheetId, sheetName, provisioning_key, schema_version};
       store sheetId in MEMORY.md. Never call this again for an existing client
       (the provisioning key company_id::planner_kind reconciles a
       create-then-crash rerun: the webhook returns the existing sheet, deduped=true).

    2) EVERY publish cycle — upsert each keyed content row (after media is
       uploaded to the GHL CDN and you have the CDN url):
         curl -s -X POST "https://main.blackceoautomations.com/webhook/social-planner-row-append" \\
           -H "Content-Type: application/json" \\
           -d '{"sheetId":"<content_sheet_id>","schema_version":"1.1.0","company_id":"<company_id>","cycle_id":"<cycle>","content_revision":"<rev>","account_id":"<account_id>","platform":"<platform>","account_name":"<name>","format":"<format>","scheduled_local":"<local>","scheduled_utc":"<utc>","state":"<state>","qc_state":"<qc>","preview_url":"=IMAGE(\\"https://assets.cdn.filesafe.space/...\\", 1)","remote_url":"<cdn url>"}'
       One row per content revision and destination account, upserted by
       row_key cycle_id::content_revision::account_id (replay updates in
       place, never duplicates). platform is written verbatim — no fallback.
       Image previews MUST be =IMAGE("url", 1) formula strings in
       preview_url; the webhook sizes the preview columns/row via batchUpdate.
       If a webhook call fails, log to
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
  7   lifecycle precondition refused (e.g. --complete-phase without an accepted
      worker execution, --mark-review before every phase is complete with
      verified hashes, ack recorded against a foreign run)
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
    --ack-execution) ACK_EXECUTION=1; shift;;
    --worker-id)  WORKER_ID="${2:-}"; shift 2;;
    --execution-id) EXECUTION_ID="${2:-}"; shift 2;;
    --complete-phase) COMPLETE_PHASE="${2:-}"; shift 2;;
    --mark-review) MARK_REVIEW=1; shift;;
    --status)     STATUS_ONLY=1; shift;;
    --overdue-after) OVERDUE_AFTER="${2:-900}"; shift 2;;
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
# (--verify-receipts / --status are standalone modes and must not be swallowed here.)
if [ -z "$TOPIC" ] && [ -z "$PLATFORMS" ] && [ "$DRY_RUN" -eq 0 ] && [ -z "$VERIFY_RECEIPTS" ] \
   && [ "$STATUS_ONLY" -eq 0 ] && [ "$ACK_EXECUTION" -eq 0 ] && [ "$MARK_REVIEW" -eq 0 ] \
   && [ -z "$COMPLETE_PHASE" ]; then
  print_help
  exit 0
fi

# ---------- F04: durable dispatch record (working/dispatch.json) ----------
# One JSON state file per run dir, read/written by every lifecycle mode. All
# workers read the same record; every transition is recorded here BEFORE the
# Command Center is touched, so the CC card can never outrun the durable state.
# Shape follows the W0 dispatch.json contract fields (operation_key, worker_id,
# attempt, fencing_token, lease/heartbeat/retry) plus the consumer binding.
_dispatch_read() {
  python3 - "$WORKDIR" <<'PYEOF' 2>/dev/null || echo "{}"
import json, sys
try:
    print(open(sys.argv[1] + "/working/dispatch.json").read())
except OSError:
    print("{}")
PYEOF
}

_dispatch_write() {  # _dispatch_write <python-expr-arg-pairs...> — see callers
  python3 - "$WORKDIR" "$@" <<'PYEOF'
import json, os, sys
workdir = sys.argv[1]
args = sys.argv[2:]
path = os.path.join(workdir, "working", "dispatch.json")
try:
    with open(path) as f:
        rec = json.load(f)
except Exception:
    rec = {}
# argv pairs: key value key value ...
i = 0
def jload(s):
    try:
        return json.loads(s)
    except Exception:
        return s
while i + 1 < len(args) + 1 and i < len(args):
    key, val = args[i], jload(args[i + 1]) if i + 1 < len(args) else None
    rec[key] = val
    i += 2
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path + ".tmp", "w") as f:
    json.dump(rec, f, indent=2)
os.replace(path + ".tmp", path)
print(path)
PYEOF
}

# The per-phase operation keys (W0 dispatch.json contract): stable, durable,
# and the idempotency identity a consumer leases against.
_phase_operation_key() {
  printf 'skill35-cycle:%s:phase-%s' "$RUN_ID" "$1"
}

# ---- lifecycle modes that need an EXISTING workdir ----
if [ -n "$VERIFY_RECEIPTS" ]; then :; fi
_needs_workdir=0
[ "$STATUS_ONLY" -eq 1 ] && _needs_workdir=1
[ "$ACK_EXECUTION" -eq 1 ] && _needs_workdir=1
[ -n "$COMPLETE_PHASE" ] && _needs_workdir=1
[ "$MARK_REVIEW" -eq 1 ] && _needs_workdir=1
if [ "$_needs_workdir" -eq 1 ] && [ -z "$WORKDIR" ]; then
  err "this mode requires --workdir (the staged run directory)"; exit 2
fi
if [ "$_needs_workdir" -eq 1 ] && [ ! -d "$WORKDIR" ]; then
  err "--workdir not found: $WORKDIR"; exit 2
fi

_dispatch_now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# --status: print durable state as JSON, read-only, then exit.
if [ "$STATUS_ONLY" -eq 1 ]; then
  WORKDIR="$WORKDIR" RUN_ID="${RUN_ID:-}" OVERDUE_AFTER="$OVERDUE_AFTER" python3 - <<'PYEOF'
import json, os, sys, time
workdir = sys.argv[1] if len(sys.argv) > 1 else None
wd = os.environ["WORKDIR"]
overdue_after = float(os.environ.get("OVERDUE_AFTER") or 900)
path = os.path.join(wd, "working", "dispatch.json")
try:
    rec = json.load(open(path))
except Exception:
    print(json.dumps({"error": "no dispatch record at %s" % path})); sys.exit(2)
out = {
    "run_id": rec.get("run_id"),
    "state": rec.get("state"),
    "overdue": bool(rec.get("overdue")),
    "overdue_reason": rec.get("overdue_reason"),
    "queued_at": rec.get("queued_at"),
    "accepted_execution": rec.get("accepted_execution"),
    "phases_complete": rec.get("phases_complete", []),
    "worker_acks": rec.get("worker_acks", []),
    "review_eligible": rec.get("review_eligible"),
    "completion_receipt": rec.get("completion_receipt"),
}
# A QUEUED cycle past the threshold with NO accepted execution is OVERDUE
# (workers stopped != completion; never review/done, no completion receipt).
if rec.get("state") == "queued" and not rec.get("accepted_execution"):
    try:
        import datetime
        ts = datetime.datetime.strptime(rec.get("queued_at", ""), "%Y-%m-%dT%H:%M:%SZ")
        age = time.time() - ts.replace(tzinfo=datetime.timezone.utc).timestamp()
        if age > overdue_after:
            out["overdue"] = True
            out["overdue_reason"] = "queued %ds with no worker ack (threshold %ds); consumers stopped?" % (int(age), int(overdue_after))
    except (ValueError, TypeError):
        pass
print(json.dumps(out, indent=2))
PYEOF
  exit $?
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

# cc_call_ingest <json-body> -> echoes the 2xx response body; ALWAYS returns 0.
# F12 — canonical /api/tasks/ingest caller with HMAC parity: when
# CC_WEBHOOK_SECRET/WEBHOOK_SECRET is set, the EXACT transmitted bytes are
# signed (x-webhook-signature = HMAC-SHA256 hex), byte-for-byte like the route
# expects. Outage-class failures (5xx/transport) park the body in the run's
# board outbox (via 57's mc_board.py contract shape — a JSONL file under
# $WORKDIR/checkpoints) for one idempotent replay on recovery, so a board
# outage can no longer leave the cycle unregistered (F12 required outcome).
CC_WEBHOOK_SECRET="${CC_WEBHOOK_SECRET:-${WEBHOOK_SECRET:-}}"
CC_OUTBOX_FILE=""
cc_call_ingest() {
  local payload="$1" resp http out sig raw
  _cc_resolve_token
  if [ -z "$CC_TOKEN" ]; then
    return 0
  fi
  command -v curl >/dev/null 2>&1 || { warn "Command Center skipped — curl not available."; return 0; }
  raw="$payload"
  local -a curl_args=(-sS -m 10 -w $'\n%{http_code}' -X POST "$CC_BASE/api/tasks/ingest"
    -H "Authorization: Bearer $CC_TOKEN" -H "Content-Type: application/json")
  if [ -n "$CC_WEBHOOK_SECRET" ] && command -v python3 >/dev/null 2>&1; then
    sig="$(printf '%s' "$raw" | CC_WEBHOOK_SECRET="$CC_WEBHOOK_SECRET" python3 -c "import hashlib,hmac,os,sys; print(hmac.new(os.environ['CC_WEBHOOK_SECRET'].encode('utf-8'), sys.stdin.buffer.read(), hashlib.sha256).hexdigest())" 2>/dev/null || true)"
    # Sign the EXACT body bytes (python read stdin as bytes above; recompute
    # properly below when the fast path produced nothing).
    if [ -z "$sig" ]; then
      sig="$(printf '%s' "$raw" | openssl dgst -sha256 -hmac "$CC_WEBHOOK_SECRET" -hex 2>/dev/null | sed 's/^.*= //')"
    fi
    if [ -n "$sig" ]; then curl_args+=(-H "x-webhook-signature: $sig"); fi
  fi
  resp="$(curl "${curl_args[@]}" -d "$payload" 2>/dev/null)" || {
    warn "Command Center /api/tasks/ingest unreachable — parked in the board outbox (replay on recovery)."
    _cc_outbox_park "$payload" "transport_error"
    return 0
  }
  http="$(printf '%s' "$resp" | tail -n1)"
  out="$(printf '%s' "$resp" | sed '$d')"
  case "$http" in
    2*) printf '%s' "$out"
        _cc_outbox_drain
        return 0;;
    5*) warn "Command Center /api/tasks/ingest returned HTTP $http — parked in the board outbox (replay on recovery)."
        _cc_outbox_park "$payload" "HTTP $http"
        return 0;;
    *)  warn "Command Center /api/tasks/ingest returned HTTP $http — continuing (board update is optional)."; return 0;;
  esac
}

# _cc_outbox_park <json-body> <reason> — append one deduped op line to the run
# outbox ($WORKDIR/checkpoints/board-outbox.jsonl). Fail-soft; never raises.
_cc_outbox_park() {
  local payload="$1" reason="$2"
  [ -n "$WORKDIR" ] || return 0
  command -v python3 >/dev/null 2>&1 || return 0
  CC_OUTBOX_FILE="$WORKDIR/checkpoints/board-outbox.jsonl"
  python3 - "$CC_OUTBOX_FILE" "$payload" "$reason" <<'PYEOF' 2>/dev/null || true
import hashlib, json, os, sys, time
path, payload, reason = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    body = json.loads(payload)
except Exception:
    body = {"raw": payload}
op_id = hashlib.sha256(("POST /api/tasks/ingest " + json.dumps(body, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()[:24]
os.makedirs(os.path.dirname(path), exist_ok=True)
existing = []
if os.path.exists(path):
    try:
        with open(path) as f:
            existing = [ln for ln in f.read().splitlines() if ln.strip()]
    except OSError:
        existing = []
for ln in existing:
    try:
        if json.loads(ln).get("op_id") == op_id:
            sys.exit(0)  # already parked — one line per logical op
    except Exception:
        pass
with open(path, "a") as f:
    f.write(json.dumps({"op_id": op_id, "method": "POST", "path": "/api/tasks/ingest",
                        "payload": body, "queued_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "attempts": 0, "last_error": reason}, separators=(",", ":")) + "\n")
PYEOF
}

# _cc_outbox_drain — one idempotent replay pass over the run outbox after a
# successful board touch. Re-POSTs /api/tasks/ingest (server dedupes on the
# stable idempotency_key → one consistent card), removes replayed ops.
_cc_outbox_drain() {
  [ -n "$WORKDIR" ] || return 0
  local f="$WORKDIR/checkpoints/board-outbox.jsonl"
  [ -f "$f" ] || return 0
  command -v python3 >/dev/null 2>&1 || return 0
  python3 - "$f" "$CC_BASE" "$CC_TOKEN" "$CC_WEBHOOK_SECRET" <<'PYEOF' 2>/dev/null || true
import hashlib, hmac, json, os, sys, time, urllib.request, urllib.error
path, base, token, secret = sys.argv[1:5]
try:
    lines = [ln for ln in open(path).read().splitlines() if ln.strip()]
except OSError:
    sys.exit(0)
ops = []
for ln in lines:
    try:
        rec = json.loads(ln)
        if rec.get("op_id") and rec.get("payload") is not None:
            ops.append(rec)
    except Exception:
        pass
def call(op):
    raw = json.dumps(op["payload"], separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if secret:
        headers["x-webhook-signature"] = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    req = urllib.request.Request(f"{base}/api/tasks/ingest", data=raw, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.getcode()
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:
        return 0
surviving = []
replayed = 0
for op in ops:
    op["attempts"] = int(op.get("attempts") or 0) + 1
    op["last_attempt_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    code = call(op)
    if code in (200, 201):
        replayed += 1
    else:
        op["last_error"] = f"HTTP {code}"
        surviving.append(op)
try:
    with open(path, "w") as f:
        for op in surviving:
            f.write(json.dumps(op, separators=(",", ":")) + "\n")
except OSError:
    pass
if replayed or surviving:
    print(f"[Skill35][outbox] replayed={replayed} remaining={len(surviving)}")
PYEOF
}

# ---------- post-cycle receipts QC (deterministic 0-posts-as-error gate) ----------
# Reads publish-receipts.json and HARD-FAILS when accounts are connected but no
# posts were created, or posts were planned but none created. The posting step
# (master orchestrator, Phase 5) MUST emit publish-receipts.json with at least:
#   {"connected_accounts": N, "planned_posts": N, "created_posts": N,
#    "posts": [{"platform": "...", "post_id": "...", "url": "...", "tier": N,
#               "readback": {"id": "<post_id>"}}]}
# CC reconciliation additionally requires registered company/queue/account/post
# inventory and independent readback; see references/publication-verification.md.
# U128: counters alone are three numbers from the same pipeline — an empty
# posts array with created_posts=N used to pass. Now each post must carry an
# immutable receipt (non-empty post_id + url), the array length must match
# created_posts, and at least one post must carry a read-back record proving it
# was read back from the remote platform.
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

# U128: per-post immutable receipts. Counters alone are three numbers from the
# same pipeline — a receipt can declare created_posts=N with an empty posts
# array and pass. Require one immutable receipt PER post: each must carry a
# non-empty remote post_id and url, the array length must match created, and at
# least one post must carry a read-back record proving it was read back from the
# remote platform. These requirements only apply when posts were actually
# created — a genuine no-op cycle (nothing planned, nothing created) is still a
# clean pass.
if created > 0:
    posts = d.get("posts")
    if not isinstance(posts, list):
        sys.stderr.write("[Skill35] QC FAIL: receipts carry no 'posts' array — counters alone cannot prove a single post exists.\n"); sys.exit(6)
    if len(posts) < created:
        sys.stderr.write(f"[Skill35] QC FAIL: {created} post(s) declared but only {len(posts)} per-post receipt(s) present.\n"); sys.exit(6)
    for i, post in enumerate(posts):
        if not isinstance(post, dict):
            sys.stderr.write(f"[Skill35] QC FAIL: posts[{i}] is not an object.\n"); sys.exit(6)
        pid = str(post.get("post_id", "") or "").strip()
        url = str(post.get("url", "") or "").strip()
        if not pid:
            sys.stderr.write(f"[Skill35] QC FAIL: posts[{i}] has no remote post_id — the receipt is not immutable.\n"); sys.exit(6)
        if not url:
            sys.stderr.write(f"[Skill35] QC FAIL: posts[{i}] has no url — the post cannot be located on the platform.\n"); sys.exit(6)

    # Read at least one back from the remote platform. The posting step records
    # the read-back (readback.id matching post_id) when it confirms the post
    # exists on the platform. Require at least one post to carry a valid
    # read-back record — proof that the pipeline did not just declare success.
    readback_ok = False
    for post in posts:
        if not isinstance(post, dict):
            continue
        rb = post.get("readback")
        pid = str(post.get("post_id", "") or "").strip()
        if isinstance(rb, dict) and str(rb.get("id", "") or "").strip() == pid and pid:
            readback_ok = True
            break
    if not readback_ok:
        sys.stderr.write("[Skill35] QC FAIL: no post carries a read-back record from the remote platform — success was declared, not verified.\n"); sys.exit(6)

print(f"[Skill35] receipts OK: planned={planned} created={created} connected={connected}")
PYEOF
}

log "$SCRIPT_NAME $SCRIPT_VERSION starting run-id=$RUN_ID"

# ===========================================================================
# F04 — WORKER LIFECYCLE MODES (accepted-execution boundary + artifact gate)
# ---------------------------------------------------------------------------
# --ack-execution / --complete-phase / --mark-review operate on an EXISTING
# staged run dir. They mutate the durable dispatch record FIRST, then mirror
# the accepted state onto the Command Center card (fail-soft). Order is
# enforced:
#   ack       : state must be queued  -> in_progress (CC in_progress happens HERE)
#   complete  : an accepted execution must exist; artifacts must exist and
#               verify against the sha256 manifest
#   review    : every phase complete; CC review happens HERE; QC owns review->done
# ===========================================================================
_cc_task_id_for_run() {
  # Recover the staged CC task id (file first, durable record second).
  local f="$WORKDIR/cc-task-id"
  if [ -s "$f" ]; then cat "$f"; return 0; fi
  python3 - "$WORKDIR" <<'PYEOF' 2>/dev/null || true
import json, os, sys
try:
    print(json.load(open(os.path.join(sys.argv[1], "working", "dispatch.json"))).get("cc_task_id") or "")
except Exception:
    print("")
PYEOF
}

if [ "$ACK_EXECUTION" -eq 1 ]; then
  [ -n "$WORKER_ID" ] || { err "--ack-execution requires --worker-id"; exit 2; }
  _ack_json="$(WORKDIR="$WORKDIR" WORKER_ID="$WORKER_ID" EXECUTION_ID="${EXECUTION_ID:-}" RUN_ID="${RUN_ID:-}" OVERDUE_AFTER="$OVERDUE_AFTER" python3 - <<'PYEOF'
import json, os, sys
wd = os.environ["WORKDIR"]
worker = os.environ["WORKER_ID"]
path = os.path.join(wd, "working", "dispatch.json")
try:
    rec = json.load(open(path))
except Exception as e:
    print(json.dumps({"ok": False, "exit": 7,
                      "error": "no readable dispatch record at %s (%s)" % (path, e)}))
    sys.exit(0)
if str(rec.get("run_id") or "") != (os.environ.get("RUN_ID") or rec.get("run_id")):
    pass  # RUN_ID env is only set by the staging invocation; never block on it
state = str(rec.get("state") or "")
if state not in ("queued", "in_progress"):
    print(json.dumps({"ok": False, "exit": 7,
                      "error": "cannot ack a %s cycle (expected queued)" % state}))
    sys.exit(0)
acks = rec.get("worker_acks") if isinstance(rec.get("worker_acks"), list) else []
for a in acks:
    if isinstance(a, dict) and a.get("worker_id") == worker:
        print(json.dumps({"ok": True, "deduped": True, "state": rec.get("state"),
                          "execution_id": (rec.get("accepted_execution") or {}).get("execution_id")}))
        sys.exit(0)
execution_id = os.environ.get("EXECUTION_ID") or "%s:%s" % (rec.get("run_id") or "run", worker)
rec["accepted_execution"] = {
    "worker_id": worker,
    "execution_id": execution_id,
    "accepted_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
}
acks.append({"worker_id": worker, "execution_id": execution_id,
             "accepted_at": rec["accepted_execution"]["accepted_at"]})
rec["worker_acks"] = acks
rec["state"] = "in_progress"
rec["overdue"] = False
rec["overdue_reason"] = None
with open(path + ".tmp", "w") as f:
    json.dump(rec, f, indent=2)
import os as _os
_os.replace(path + ".tmp", path)
print(json.dumps({"ok": True, "deduped": False, "state": "in_progress",
                  "execution_id": execution_id}))
PYEOF
)"
  _ack_ok="$(printf '%s' "$_ack_json" | python3 -c 'import sys,json; print(str(json.load(sys.stdin).get("ok")).lower())' 2>/dev/null || echo false)"
  if [ "$_ack_ok" != "true" ]; then
    err "worker ack REFUSED: $(printf '%s' "$_ack_json" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("error","unreadable ack result"))' 2>/dev/null || echo 'unreadable ack result')"
    exit 7
  fi
  _cc_tid="$(_cc_task_id_for_run)"
  if [ -n "$_cc_tid" ]; then
    # The ONLY in_progress transition: after an ACCEPTED worker execution.
    cc_call PATCH "/api/tasks/$_cc_tid" "{\"status\":\"in_progress\"}" >/dev/null
    log "worker ack accepted ($_ack_json) — task $_cc_tid moved to in_progress."
  else
    log "worker ack accepted ($_ack_json) — no CC card on record; board mirror skipped."
  fi
  printf '%s\n' "$_ack_json"
  exit 0
fi

if [ -n "$COMPLETE_PHASE" ]; then
  [ -n "$WORKER_ID" ] || { err "--complete-phase requires --worker-id"; exit 2; }
  case "$COMPLETE_PHASE" in
    [1-5]) : ;;
    *) err "--complete-phase takes a phase id 1-5 (got '$COMPLETE_PHASE')"; exit 2;;
  esac
  _cp_json="$(WORKDIR="$WORKDIR" WORKER_ID="$WORKER_ID" PHASE="$COMPLETE_PHASE" python3 - <<'PYEOF'
import datetime, hashlib, json, os, sys
wd, worker, phase = os.environ["WORKDIR"], os.environ["WORKER_ID"], os.environ["PHASE"]
path = os.path.join(wd, "working", "dispatch.json")
def fail(msg, code=7):
    print(json.dumps({"ok": False, "exit": code, "error": msg})); sys.exit(0)
try:
    rec = json.load(open(path))
except Exception as e:
    fail("no readable dispatch record at %s (%s)" % (path, e))
state = str(rec.get("state") or "")
if state not in ("in_progress",):
    fail("phase %s completion requires an accepted worker execution "
         "(state=%r, expected in_progress) — no artifacts count without an ack" % (phase, state))
accepted = rec.get("accepted_execution") or {}
if not isinstance(accepted, dict) or not accepted.get("worker_id"):
    fail("dispatch record carries no accepted execution")
if worker != str(accepted.get("worker_id")):
    fail("worker %r is not the accepted executor %r (a foreign worker cannot complete a phase)"
         % (worker, accepted.get("worker_id")))
pdir = os.path.join(wd, "working", "phase-%s" % phase, "artifacts")
if not os.path.isdir(pdir):
    fail("phase %s has no artifacts directory at %s — completion cannot be claimed "
         "without producer artifacts" % (phase, pdir))
artifacts = {}
for root, _dirs, files in os.walk(pdir):
    for fn in sorted(files):
        full = os.path.join(root, fn)
        rel = os.path.relpath(full, pdir)
        try:
            artifacts[rel] = hashlib.sha256(open(full, "rb").read()).hexdigest()
        except OSError as e:
            fail("artifact %s unreadable (fail-closed): %s" % (rel, e))
if not artifacts:
    fail("phase %s artifacts directory is EMPTY — completion cannot be claimed" % phase)
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
phases = rec.get("phases_complete") if isinstance(rec.get("phases_complete"), list) else []
for p in phases:
    if isinstance(p, dict) and str(p.get("phase")) == str(phase):
        print(json.dumps({"ok": True, "deduped": True, "phase": phase,
                          "artifacts": len(artifacts), "sha256": artifacts}))
        sys.exit(0)
phases.append({"phase": str(phase), "completed_by": worker,
               "execution_id": accepted.get("execution_id"),
               "completed_at": now,
               "artifacts": len(artifacts),
               "sha256": artifacts})
rec["phases_complete"] = phases
with open(path + ".tmp", "w") as f:
    json.dump(rec, f, indent=2)
import os as _os
_os.replace(path + ".tmp", path)
print(json.dumps({"ok": True, "deduped": False, "phase": phase,
                  "artifacts": len(artifacts), "sha256": artifacts}))
PYEOF
)"
  _cp_ok="$(printf '%s' "$_cp_json" | python3 -c 'import sys,json; print(str(json.load(sys.stdin).get("ok")).lower())' 2>/dev/null || echo false)"
  if [ "$_cp_ok" != "true" ]; then
    err "phase completion REFUSED: $(printf '%s' "$_cp_json" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("error","unreadable completion result"))' 2>/dev/null || echo 'unreadable result')"
    exit 7
  fi
  printf '%s\n' "$_cp_json"
  exit 0
fi

if [ "$MARK_REVIEW" -eq 1 ]; then
  _mr_json="$(WORKDIR="$WORKDIR" python3 - <<'PYEOF'
import datetime, hashlib, json, os, sys
wd = os.environ["WORKDIR"]
path = os.path.join(wd, "working", "dispatch.json")
def fail(msg, code=7):
    print(json.dumps({"ok": False, "exit": code, "error": msg})); sys.exit(0)
try:
    rec = json.load(open(path))
except Exception as e:
    fail("no readable dispatch record at %s (%s)" % (path, e))
state = str(rec.get("state") or "")
if state == "queued":
    fail("--mark-review refused: the cycle is still QUEUED with no accepted worker "
         "execution — staging is never review-eligible")
if state == "review":
    print(json.dumps({"ok": True, "deduped": True, "state": "review"})); sys.exit(0)
phases = [p for p in (rec.get("phases_complete") or []) if isinstance(p, dict)]
done = {str(p.get("phase")) for p in phases}
missing = [str(i) for i in range(1, 6) if str(i) not in done]
if missing:
    fail("--mark-review refused: phase(s) %s are not recorded complete with verified "
         "artifact hashes — review requires EVERY phase complete" % ", ".join(missing))
# Re-verify the recorded sha256 manifest against the artifacts ON DISK right now
# (a phase may have been 'completed' against artifacts later edited/deleted).
for p in phases:
    pdir = os.path.join(wd, "working", "phase-%s" % p.get("phase"), "artifacts")
    want = p.get("sha256") if isinstance(p.get("sha256"), dict) else {}
    for rel, sha in sorted(want.items()):
        full = os.path.join(pdir, rel)
        if not os.path.isfile(full):
            fail("--mark-review refused: verified artifact %s (phase %s) is missing on disk"
                 % (rel, p.get("phase")))
        got = hashlib.sha256(open(full, "rb").read()).hexdigest()
        if got != sha:
            fail("--mark-review refused: artifact %s (phase %s) changed after its hash was "
                 "recorded (%s..%s != %s..%s)" % (rel, p.get("phase"), sha[:12], sha[-8:],
                                                  got[:12], got[-8:]))
rec["state"] = "review"
rec["review_eligible"] = True
rec["reviewed_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
with open(path + ".tmp", "w") as f:
    json.dump(rec, f, indent=2)
import os as _os
_os.replace(path + ".tmp", path)
print(json.dumps({"ok": True, "state": "review"}))
PYEOF
)"
  _mr_ok="$(printf '%s' "$_mr_json" | python3 -c 'import sys,json; print(str(json.load(sys.stdin).get("ok")).lower())' 2>/dev/null || echo false)"
  if [ "$_mr_ok" != "true" ]; then
    err "review transition REFUSED: $(printf '%s' "$_mr_json" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("error","unreadable review result"))' 2>/dev/null || echo 'unreadable result')"
    exit 7
  fi
  _cc_tid="$(_cc_task_id_for_run)"
  if [ -n "$_cc_tid" ]; then
    # The ONLY review transition: after every phase is complete with verified
    # hashes. QC owns review->done (this script never sets done).
    cc_call PATCH "/api/tasks/$_cc_tid" "{\"status\":\"review\"}" >/dev/null
    log "cycle moved to review (all 5 phases verified) — task $_cc_tid at review; QC promotes review->done."
  else
    log "cycle moved to review (all 5 phases verified) — no CC card on record; board mirror skipped."
  fi
  printf '%s\n' "$_mr_json"
  exit 0
fi

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
# Brand/source files live in the workspace dir on OpenClaw >= 2026.x
# ($OPENCLAW_DIR/workspace/SOUL.md), not the config root. Prefer workspace/,
# fall back to config root (older layouts / container paths).
# [fix 2026-09-08: Talaya box rc=3 — every cycle stopped, brand files unread]
_ws="$OPENCLAW_DIR/workspace"
SOUL_MD="$OPENCLAW_DIR/SOUL.md";      [ -f "$_ws/SOUL.md" ]      && SOUL_MD="$_ws/SOUL.md"
IDENTITY_MD="$OPENCLAW_DIR/IDENTITY.md"; [ -f "$_ws/IDENTITY.md" ] && IDENTITY_MD="$_ws/IDENTITY.md"
USER_MD="$OPENCLAW_DIR/USER.md";      [ -f "$_ws/USER.md" ]      && USER_MD="$_ws/USER.md"
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
# F18: one documented credential resolver (shared-utils/social_planner_credentials.py)
# resolves the GHL Private Integration Token and Location ID with the explicit
# precedence config field > canonical env name > Skill 44 canonical resolver,
# failing closed on a config/env value conflict (a stale config key must never
# quietly aim the cycle at another client). Missing creds => STOP with a
# plain-English, operator-facing reason (never a silent no-op). Diagnostics are
# REDACTED — presence and source only, never a value.
# These are also exported for downstream phases.
if [ -f "$SECRETS_ENV" ]; then
  set +u; set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a; set -u
fi

_SPRC=""
for _sprc_dir in "$SKILL_DIR/../shared-utils" \
                 "$OPENCLAW_DIR/skills/shared-utils" \
                 "/data/.openclaw/skills/shared-utils" \
                 "$HOME_DIR/.openclaw/skills/shared-utils"; do
  if [ -f "$_sprc_dir/social_planner_credentials.py" ]; then _SPRC="$_sprc_dir"; break; fi
done

_cred_json=""
if [ -n "$_SPRC" ] && command -v python3 >/dev/null 2>&1; then
  _cred_json="$(cd "$_SPRC" && python3 - <<'PYEOF' 2>&1
import json, sys
try:
    from social_planner_credentials import resolve_planner_credentials, diagnose
except Exception as e:  # resolver itself broken: say so, never a silent pass
    print(json.dumps({"error": "resolver import failed: %s" % type(e).__name__}))
    sys.exit(0)
try:
    creds, report = resolve_planner_credentials()
    print(json.dumps({"creds": {k: (v or "") for k, v in creds.items()},
                      "report": report, "diagnostics": diagnose(report)}))
except Exception as e:  # CredentialConflictError and friends: FAIL CLOSED
    print(json.dumps({"error": str(e)}))
PYEOF
)"
  # The env file was sourced above; the resolver only CONFLICT-CHECKS it —
  # its resolved values are re-applied to this shell so downstream phases see
  # exactly what the resolver validated.
  if printf '%s' "$_cred_json" | grep -q '"error"'; then
    err "credential resolver failed closed: $(printf '%s' "$_cred_json" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("error","unknown"))' 2>/dev/null || echo 'unresolvable credential state')"
    MISSING_REQ=$((MISSING_REQ+1))
    note_missing "GHL credentials (PIT + Location ID) — resolve the conflict above, then re-run"
  else
    _pit="$(printf '%s' "$_cred_json" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("creds",{}).get("pit",""))' 2>/dev/null || true)"
    _loc="$(printf '%s' "$_cred_json" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("creds",{}).get("location_id",""))' 2>/dev/null || true)"
    [ -n "$_pit" ] && GOHIGHLEVEL_API_KEY="$_pit"
    [ -n "$_loc" ] && GOHIGHLEVEL_LOCATION_ID="$_loc"
    # Redacted diagnostics: which credentials resolved, from where. No values.
    printf '%s' "$_cred_json" | python3 -c 'import sys,json
d=json.load(sys.stdin)
for k, e in d.get("report", {}).items():
    print("[Skill35] credential %s: %s (source: %s)" % (k, e.get("status","?"), e.get("source") or "none"))' 2>/dev/null || true
  fi
fi
: "${GOHIGHLEVEL_API_KEY:=}"
: "${GOHIGHLEVEL_LOCATION_ID:=}"
[ -n "$GOHIGHLEVEL_API_KEY" ]     || note_missing "GOHIGHLEVEL_API_KEY (GHL Private Integration Token) — required to publish; add it to $SECRETS_ENV"
[ -n "$GOHIGHLEVEL_LOCATION_ID" ] || note_missing "GOHIGHLEVEL_LOCATION_ID — required to publish (prevents cross-location posting); add it to $SECRETS_ENV"

# F18: read-only live account discovery is a PRODUCTION READINESS CHECK
# (no longer opt-in when credentials are present). A transient network error
# only WARNS (never false-blocks the cycle). Distinct failure codes:
#   exit 3  — token rejected (expired/revoked/insufficient scope)
#   exit 3  — LOCATION MISMATCH: the token authenticates but resolves to a
#             different location than the configured one (wrong-tenant token)
#   exit 3  — zero connected social accounts
if [ -n "$GOHIGHLEVEL_API_KEY" ] && [ -n "$GOHIGHLEVEL_LOCATION_ID" ] && command -v curl >/dev/null 2>&1; then
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
      # F18: wrong-LOCATION check — the token works, but does it work for THIS
      # location? A token minted in another sub-account must never publish.
      _loc_probe="$(curl -sS -m 15 -o /dev/null -w '%{http_code}' \
        -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
        -H "Version: 2021-07-28" \
        "https://services.leadconnectorhq.com/locations/$GOHIGHLEVEL_LOCATION_ID" 2>/dev/null || true)"
      if [ "$_loc_probe" = "401" ] || [ "$_loc_probe" = "403" ]; then
        err "GHL token authenticated for social posting but is NOT authorized for the configured location (HTTP $_loc_probe on GET /locations/{loc}) — the PIT belongs to a different sub-account/location."
        err "CLIENT MESSAGE: \"Your GoHighLevel token works but belongs to a different location than the one configured. Send me the Private Integration Token created inside THIS location's Settings > Integrations > Private Integrations. I will not post until this is fixed.\""
        exit 3
      fi
      # GHL wraps the account list: {"success":true,"results":{"accounts":[...]}}.
      # Reading d['accounts'] at the TOP level always yielded None -> 0, so a
      # location with connected channels hard-failed at exit 3 and no cycle ever
      # ran. Parse the documented wrapper (results.accounts, or a bare results
      # array), and keep the legacy unwrapped shape as a fallback.
      #
      # CONTRACT (mirrors 57-social-media-in-a-box/scripts/ghl_contracts.py
      # parse_accounts_payload): an UNRECOGNISED envelope is -1 "inconclusive",
      # never 0. A parser failure must never be misreported as zero accounts —
      # only a genuinely empty list blocks the cycle.
      _acct_count="$(printf '%s' "$_pbody" | python3 -c "import sys,json
try:
    d=json.load(sys.stdin)
    if isinstance(d,list):
        a=d
    elif isinstance(d,dict):
        r=d.get('results')
        if isinstance(r,list):
            a=r
        elif isinstance(r,dict):
            a=r.get('accounts')
        elif r is None and isinstance(d.get('accounts'),list):
            a=d.get('accounts')
        else:
            a=None
    else:
        a=None
    print(len(a) if isinstance(a,list) else -1)
except Exception:
    print(-1)" 2>/dev/null || echo -1)"
      if [ "$_acct_count" = "0" ]; then
        err "GHL returned 0 connected social accounts for this location — there is nothing to publish to."
        err "CLIENT MESSAGE: \"I could not find any social accounts connected in your GoHighLevel Social Planner. Please connect at least one channel (Settings > Social Planner) and tell me when it is done. I will not post until a channel is connected.\""
        exit 3
      fi
      if [ "$_acct_count" = "-1" ]; then
        warn "live preflight inconclusive: could not parse the GHL accounts envelope (unrecognised shape) — NOT blocking, and NOT reporting zero. Posting step will retry per playbook."
      else
        log "live preflight OK: connected account count = $_acct_count"
      fi
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
python3 - "$MANIFEST" "$TOPIC" "$PLATFORMS_NORM" "$SCHEDULE" "$RUN_ID" "$WORKDIR" "$SKILL_DIR/skill-version.txt" <<'PYEOF'
import json, sys, time
from pathlib import Path
manifest_path, topic, platforms, schedule, run_id, workdir, version_file = sys.argv[1:8]
plist = [p for p in platforms.split(",") if p]

manifest = {
    "skill": "35-social-media-planner",
    "skill_version": Path(version_file).read_text().strip(),
    "publication_evidence_contract": "references/publication-verification.md",
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
            "receipt_handoff": "Register complete company/queue/account/post inventory as publish-receipts.json through the production task deliverables endpoint before completing. Verification agents read back these original IDs only; never republish. Follow references/publication-verification.md.",
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

# ---------- Command Center: register the staged cycle (card stays backlog) ----------
# Operators see every run move across the board. Fail-soft: with the board down
# OR MC_API_TOKEN unset, this logs a skip, creates NO task, and the cycle finishes
# exactly as before (manifest + hand-off file, exit 0). QC promotes review->done;
# this script NEVER sets status=done.
#
# F12 (social-planner-september-eighth / WF05) — TRUTHFUL TASK OWNERSHIP:
# task creation moved from the generic POST /api/tasks to the CANONICAL
# /api/tasks/ingest front door, same as every productized skill's mc_board.py.
# The ingest route is the only creation path with the canonical write contract
# (createTaskCore) behind it:
#   - HMAC signing (x-webhook-signature) when CC_WEBHOOK_SECRET/WEBHOOK_SECRET
#     is set — ingest rejects unsigned writes in production otherwise;
#   - company binding: the payload carries the verified client company id
#     (SKILL35_COMPANY_ID or CC_COMPANY_ID, resolved from the operator env;
#     absent → CC's own MC_COMPANY_ID context decides, never another client);
#   - capability routing: department_slug 'social-media' with fallback_ok —
#     when the preferred Marketing/Social department has no eligible worker,
#     CC dispatches to an eligible General/CEO worker for the SAME company
#     server-side (never another client's roster — company scoping is the
#     server's job, and ingest is company-scoped end to end);
#   - idempotency: a stable sha256 key over run_id+topic so a retried cycle
#     never creates a second card.
#
# F04 — STAGING IS QUEUED, NOT IN_PROGRESS: the card is created but is NEVER
# moved here. The card moves to in_progress ONLY when a worker records an
# accepted execution (--ack-execution), and to review ONLY after every phase is
# complete with verified artifact hashes (--mark-review). A staged-but-unowned
# cycle must stay visually queued: "in_progress" was the old lie that turned
# staging into work-ready-for-review.
CC_TASK_FILE="$WORKDIR/cc-task-id"
cc_ingest_body="$(python3 - "$TOPIC" "$PLATFORMS_NORM" "$RUN_ID" <<'PYEOF'
import hashlib, json, os, sys
topic, platforms, run_id = sys.argv[1:4]
company_id = (os.environ.get("SKILL35_COMPANY_ID")
              or os.environ.get("CC_COMPANY_ID") or "").strip()
payload = {
    "title": ("Social cycle: " + topic)[:120],
    "description": (f"Skill 35 weekly publishing cycle (run {run_id}) for platforms: {platforms}. "
                    "STAGED (queued — awaiting an accepted worker execution via "
                    "--ack-execution); NOT yet in progress. QC promotes review->done."),
    # F12 — canonical ingest provenance + dedupe identity. The ingest route
    # embeds [ingest:<key>] and dedupes on it server-side (no schema needed).
    "source": "skill35-publishing-cycle",
    "source_ref": f"skill35:cycle:{run_id}",
    "idempotency_key": hashlib.sha256(f"skill35-cycle:{run_id}:{topic}".encode()).hexdigest(),
    # F12 — capability routing: preferred department first; with
    # fallback_ok the server may dispatch to an eligible General/CEO
    # worker for the SAME company when this department has no capacity.
    "department_slug": "social-media",
    "fallback_ok": True,
}
if company_id:
    # F12 — verified company binding (never trusts a caller-declared name).
    payload["company_id"] = company_id
print(json.dumps(payload))
PYEOF
)"
cc_resp="$(cc_call_ingest "$cc_ingest_body")"
if [ -n "$cc_resp" ]; then
  CC_TASK_ID="$(printf '%s' "$cc_resp" | python3 -c "import sys,json
try:
    d=json.load(sys.stdin)
    print(d.get('id') or d.get('task_id') or (d.get('task') or {}).get('id') or '')
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
  # F04: the card STAYS at backlog while staged — no in_progress move here.
  log "Command Center: task $CC_TASK_ID created (staged/queued — stays backlog until a worker acks; QC promotes review->done)."
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
Skill 35 cycle $RUN_ID is STAGED (QUEUED) for the master orchestrator.

Manifest: $MANIFEST
Workdir : $WORKDIR
Dispatch: $WORKDIR/working/dispatch.json (durable state — see --status)

The orchestrator should now walk phases 1..5 in cycle-manifest.json,
spawn the listed agents (one sub-agent per agent, per N5), and record
deliverables in the per-phase directories. THIS STAGING IS NOT PROGRESS:
the cycle is QUEUED until a worker accepts the dispatch
(--ack-execution --worker-id W), each phase is completed with verified
artifact hashes (--complete-phase N), and the finished work is moved to
review (--mark-review). With all workers stopped the cycle remains
queued + overdue and NO review/completion receipt is ever written.
Engagement Monitor runs continuously for 7 days post-publish per
INSTRUCTIONS.md Phase 5.
EOF

# ---------- F04: durable dispatch record — QUEUED, never completion ----------
# One record per run connecting staging to the DURABLE CONSUMER MODEL
# (Command Center social-publish-dispatcher / F33 execution policy): per-phase
# operation keys (W0 dispatch.json contract), the CC task binding, and the
# accepted-execution gate. With every worker stopped the record keeps the
# cycle in state=queued (overdue past the threshold) — it NEVER acquires a
# review/completion receipt from staging alone.
CC_TASK_ID_STAGED="$(cat "$CC_TASK_FILE" 2>/dev/null || true)"
_dispatch_write \
  "schema" '"skill35-dispatch-v1"' \
  "run_id" "\"$RUN_ID\"" \
  "workdir" "\"$WORKDIR\"" \
  "state" '"queued"' \
  "queued_at" "\"$(_dispatch_now_iso)\"" \
  "topic" "\"$(printf '%s' "$TOPIC" | sed 's/"/\\"/g')\"" \
  "platforms" "\"$PLATFORMS_NORM\"" \
  "schedule" "\"$SCHEDULE\"" \
  "consumer" '"cc-social-publish-dispatcher"' \
  "execution_policy" '"F33-standard-or-ultra"' \
  "cc_task_id" "\"$CC_TASK_ID_STAGED\"" \
  "operation_keys" "$(python3 -c '
import json, sys
rid = sys.argv[1]
print(json.dumps({"phase-1": "skill35-cycle:%s:phase-1" % rid,
                  "phase-2": "skill35-cycle:%s:phase-2" % rid,
                  "phase-3": "skill35-cycle:%s:phase-3" % rid,
                  "phase-4": "skill35-cycle:%s:phase-4" % rid,
                  "phase-5": "skill35-cycle:%s:phase-5" % rid}))' "$RUN_ID")" \
  "accepted_execution" "null" \
  "worker_acks" "[]" \
  "phases_complete" "[]" \
  "review_eligible" "false" \
  "completion_receipt" "null"

log "Cycle $RUN_ID staged as QUEUED (dispatch record: $WORKDIR/working/dispatch.json)."
log "Staging is NOT execution: the cycle runs when a worker acks, completes each phase"
log "with verified artifact hashes, and moves to review via --mark-review. With workers"
log "stopped it stays queued + overdue (no review/completion receipt)."

log "$SCRIPT_NAME staging complete (state=queued)."
exit 0
