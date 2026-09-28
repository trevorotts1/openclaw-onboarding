#!/usr/bin/env bash
# install-weekly-cron.sh - Skill 70 (Lean Core File System): register the weekly
# maintenance run as an OpenClaw cron job (an automation, NOT a heartbeat).
#
# THE JOB (exactly one per box, found by its name):
#   name      lean-core-file-system-weekly
#   schedule  30 5 * * 0  (Sunday 05:30, gateway host local time; after the
#             Sunday 03:00 fleet update, so it audits freshly updated files)
#   session   isolated (a fresh session every run, no chat history)
#   thinking  high
#   delivery  --no-deliver (quiet: the run writes a report file; the prompt
#             tells the agent to message the owner only when a human decision
#             is needed)
#   model     primary  = DeepSeek V4.1 Flash on Ollama Cloud
#             fallback = DeepSeek V4.1 Flash on OpenRouter (used only when the
#                        primary fails: full, rate-limited or unavailable)
#             Never an Anthropic or Claude model.
#
# MODEL IDENTIFIERS ARE NEVER GUESSED. They are discovered from THIS box's own
# configured model list (`openclaw models list --json`, which is also the
# allowlist a cron model must be on). Primary must match
#   ollama/deepseek-v4.1-flash[:cloud]  or  ollama-cloud/deepseek-v4.1-flash[:cloud]
# and fallback must equal
#   openrouter/deepseek/deepseek-v4.1-flash
# If either is absent, or the primary is ambiguous, the job is NOT created
# (exit 4) and the message names what is missing. --primary / --fallback
# override the choice, but the value must still be on the box's list.
#
# FLAGS ARE NEVER GUESSED EITHER. Every `cron add` / `cron edit` flag used here
# is first confirmed in that subcommand's own --help (exit 5 names any missing).
#
# MODES
#   (default) or --dry-run   print the plan, change nothing
#   --apply                  create the job, or edit it in place when it drifted
#   --idempotent             same as --apply (the flag update-skills.sh passes)
#   --check                  exit 0 only if exactly one job exists and matches
# OPTIONS
#   --agent ID      agent that runs the job (default: main)
#   --primary ID    explicit primary model id (must be on the box's list)
#   --fallback ID   explicit fallback model id (must be on the box's list)
#   --schedule EXPR five-field cron expression (default: 30 5 * * 0)
#
# EXIT: 0 ok | 1 check failed, duplicate jobs, or read-back mismatch |
#       2 tooling error (openclaw or python3 missing, gateway call failed) |
#       3 usage | 4 model identifiers not provable on this box (refused) |
#       5 this OpenClaw command line lacks a required flag (refused)
#
# NEVER: deletes a cron job, touches any model/provider/credential setting, or
# touches agents.defaults.bootstrapMaxChars / bootstrapTotalMaxChars.
# Works the same on a Mac and inside a server's Docker container (run it
# inside the container there). Test seam: $OPENCLAW_BIN replaces the CLI.

set -u
PROG="install-weekly-cron.sh"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL_DIR="$(cd "$SELF_DIR/.." && pwd)"
# shellcheck source=lib-paths.sh
. "$SELF_DIR/lib-paths.sh"

JOB_NAME="lean-core-file-system-weekly"
SCHEDULE="30 5 * * 0"
THINKING="high"
TIMEOUT_S="3600"
AGENT="main"
PRIMARY_OVERRIDE="" FALLBACK_OVERRIDE=""
MODE="dry-run"
OPENCLAW_BIN="${OPENCLAW_BIN:-openclaw}"

usage_err() { echo "USAGE [$PROG]: $*" >&2; exit 3; }
while [ $# -gt 0 ]; do
  case "$1" in
    --apply|--idempotent) MODE="apply"; shift ;;
    --check)    MODE="check"; shift ;;
    --dry-run)  MODE="dry-run"; shift ;;
    --agent)    [ -n "${2:-}" ] || usage_err "--agent needs a value"; AGENT="$2"; shift 2 ;;
    --primary)  [ -n "${2:-}" ] || usage_err "--primary needs a value"; PRIMARY_OVERRIDE="$2"; shift 2 ;;
    --fallback) [ -n "${2:-}" ] || usage_err "--fallback needs a value"; FALLBACK_OVERRIDE="$2"; shift 2 ;;
    --schedule) [ -n "${2:-}" ] || usage_err "--schedule needs a value"; SCHEDULE="$2"; shift 2 ;;
    -h|--help)  sed -n '2,52p' "$0"; exit 0 ;;
    *) usage_err "unknown argument: $1" ;;
  esac
done

tool_err() { echo "TOOLING ERROR [$PROG]: $*" >&2; exit 2; }
command -v "$OPENCLAW_BIN" >/dev/null 2>&1 || tool_err "openclaw command not found on PATH (on a server, run this inside the OpenClaw container)"
command -v python3 >/dev/null 2>&1 || tool_err "python3 not found"

TMP="$(mktemp -d 2>/dev/null || mktemp -d -t pointercron)" || tool_err "mktemp failed"
trap 'rm -rf "$TMP"' EXIT

# ── 1. Flags: confirm every flag in the CLI's own help ───────────────────────
has_flag() { grep -qE -- "(^|[[:space:],])$2([[:space:],=<]|$)" "$1"; }
"$OPENCLAW_BIN" cron add --help > "$TMP/add-help" 2>&1 || tool_err "'openclaw cron add --help' failed"
"$OPENCLAW_BIN" cron list --help > "$TMP/list-help" 2>&1 || tool_err "'openclaw cron list --help' failed"
MISSING=""
for f in --name --description --agent --cron --session --message --model --fallbacks --thinking --timeout-seconds --no-deliver; do
  has_flag "$TMP/add-help" "$f" || MISSING="$MISSING $f"
done
has_flag "$TMP/list-help" --json || MISSING="$MISSING (cron list)--json"
if [ -n "$MISSING" ]; then
  echo "REFUSED [$PROG]: this OpenClaw command line does not offer:$MISSING" >&2
  echo "  Update OpenClaw, then re-run. No job was created." >&2
  exit 5
fi
LIST_ALL=""; has_flag "$TMP/list-help" --all && LIST_ALL="--all"

# ── 2. Models: discover from the box's own configured list ───────────────────
if ! "$OPENCLAW_BIN" models list --json > "$TMP/models.json" 2> "$TMP/models.err"; then
  echo "TOOLING ERROR [$PROG]: 'openclaw models list --json' failed; the gateway may be down. Last lines:" >&2
  tail -3 "$TMP/models.err" >&2
  exit 2
fi
SEL="$(PRIMARY_OVERRIDE="$PRIMARY_OVERRIDE" FALLBACK_OVERRIDE="$FALLBACK_OVERRIDE" python3 - "$TMP/models.json" <<'PY'
import json, os, re, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception as exc:
    print("ERROR=models list output is not JSON (%s)" % type(exc).__name__); sys.exit(0)
ids = set()
ID_RE = re.compile(r"^[A-Za-z0-9._-]+/\S+$")
def walk(o):
    if isinstance(o, dict):
        for k in ("key", "ref", "fullId", "modelRef", "id", "model"):
            v = o.get(k)
            if isinstance(v, str) and ID_RE.match(v.strip()):
                ids.add(v.strip())
        prov, mid = o.get("provider"), o.get("id") or o.get("model")
        if isinstance(prov, str) and isinstance(mid, str) and not mid.startswith(prov + "/"):
            ids.add(prov + "/" + mid)
        for v in o.values():
            walk(v)
    elif isinstance(o, list):
        for v in o:
            walk(v)
    elif isinstance(o, str) and ID_RE.match(o.strip()):
        ids.add(o.strip())
walk(data)
banned = re.compile(r"anthropic|claude", re.I)
def pick(override, pattern, label):
    if override:
        if banned.search(override):
            return "REFUSED_%s=%s is an Anthropic or Claude model, which this job must never use" % (label, override)
        if override not in ids:
            return "MISSING_%s=%s (not on this box's configured model list)" % (label, override)
        return "%s=%s" % (label, override)
    hits = sorted(i for i in ids if re.fullmatch(pattern, i) and not banned.search(i))
    if len(hits) > 1:
        cloud = [h for h in hits if h.endswith(":cloud")]
        hits = cloud if cloud else hits
    if len(hits) == 1:
        return "%s=%s" % (label, hits[0])
    if not hits:
        return "MISSING_%s=no id matching %s" % (label, pattern)
    return "AMBIGUOUS_%s=%s" % (label, ",".join(hits))
print(pick(os.environ.get("PRIMARY_OVERRIDE", ""),
           r"(ollama|ollama-cloud)/deepseek-v4\.1-flash(:cloud)?", "PRIMARY"))
print(pick(os.environ.get("FALLBACK_OVERRIDE", ""),
           r"openrouter/deepseek/deepseek-v4\.1-flash", "FALLBACK"))
PY
)"
PRIMARY="$(printf '%s\n' "$SEL" | sed -n 's/^PRIMARY=//p')"
FALLBACK="$(printf '%s\n' "$SEL" | sed -n 's/^FALLBACK=//p')"
if [ -z "$PRIMARY" ] || [ -z "$FALLBACK" ]; then
  echo "REFUSED [$PROG]: the model identifiers could not be proven on this box, so no job was created or changed:" >&2
  printf '%s\n' "$SEL" | grep -v -E '^(PRIMARY|FALLBACK)=' | sed 's/^/  /' >&2
  echo "  Add the missing model to this box's configured models (the operator decides), or pass --primary/--fallback with an id that is on the list." >&2
  exit 4
fi

# ── 3. Desired job ───────────────────────────────────────────────────────────
MFD="$(pr_master_files)"
HOME70="$MFD/70-lean-core-file-system"
PLAYBOOK="$HOME70/lean-core-file-system-full.md"
[ -f "$PLAYBOOK" ] || PLAYBOOK="$SKILL_DIR/lean-core-file-system-full.md"
MSG="$(sed -e "s|{{PLAYBOOK}}|$PLAYBOOK|g" -e "s|{{AUDIT}}|$SKILL_DIR/scripts/pointer-audit.sh|g" \
           -e "s|{{REPORTS_DIR}}|$HOME70/reports|g" "$SELF_DIR/weekly-cron-message.txt")"
DESC="Skill 70 Lean Core File System: weekly core-file audit and playbook upkeep (quiet; report file only)"

# ── 4. Existing job(s) ───────────────────────────────────────────────────────
read_state() { # prints COUNT=, ID=, KIND=, DIFF=
  # shellcheck disable=SC2086
  "$OPENCLAW_BIN" cron list --json $LIST_ALL > "$TMP/jobs.json" 2> "$TMP/jobs.err" \
    || { echo "LISTERR=1"; return 0; }
  JOB_NAME="$JOB_NAME" W_MODEL="$PRIMARY" W_FB="$FALLBACK" W_THINK="$THINKING" W_EXPR="$SCHEDULE" \
  W_AGENT="$AGENT" W_MSG="$MSG" python3 - "$TMP/jobs.json" <<'PY'
import json, os, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("LISTERR=1"); sys.exit(0)
jobs = d.get("jobs", d) if isinstance(d, dict) else d
jobs = [j for j in (jobs or []) if isinstance(j, dict) and j.get("name") == os.environ["JOB_NAME"]]
print("COUNT=%d" % len(jobs))
if len(jobs) != 1:
    print("IDS=%s" % ",".join(str(j.get("id")) for j in jobs)); sys.exit(0)
j = jobs[0]; p = j.get("payload") or {}; s = j.get("schedule") or {}; dl = j.get("delivery") or {}
print("ID=%s" % j.get("id")); print("KIND=%s" % p.get("kind"))
fb = p.get("fallbacks")
want = {
    "model": (p.get("model"), os.environ["W_MODEL"]),
    "fallbacks": (list(fb) if isinstance(fb, list) else fb, [os.environ["W_FB"]]),
    "thinking": (p.get("thinking"), os.environ["W_THINK"]),
    "schedule": (s.get("expr"), os.environ["W_EXPR"]),
    "session": (j.get("sessionTarget"), "isolated"),
    "delivery": (dl.get("mode", "none"), "none"),
    "agent": (j.get("agentId") or "main", os.environ["W_AGENT"]),
    "message": (p.get("message"), os.environ["W_MSG"]),
    "enabled": (j.get("enabled", True), True),
}
print("DIFF=%s" % ",".join(k for k, (have, need) in want.items() if have != need))
PY
}
state_val() { printf '%s\n' "$STATE" | sed -n "s/^$1=//p"; }
STATE="$(read_state)"
[ -z "$(state_val LISTERR)" ] || tool_err "'openclaw cron list --json' failed or returned unreadable output"
COUNT="$(state_val COUNT)"; JOB_ID="$(state_val ID)"; KIND="$(state_val KIND)"; DIFF="$(state_val DIFF)"

echo "[$PROG] job '$JOB_NAME' agent=$AGENT schedule='$SCHEDULE' session=isolated thinking=$THINKING delivery=none"
echo "[$PROG] primary model:  $PRIMARY"
echo "[$PROG] fallback model: $FALLBACK"
echo "[$PROG] existing jobs with this name: ${COUNT:-0}${DIFF:+ (drifted: $DIFF)}"

if [ "${COUNT:-0}" -gt 1 ]; then
  echo "FAIL [$PROG]: $COUNT jobs named '$JOB_NAME' (ids: $(state_val IDS)). Two jobs would double-run. Remove the extras with 'openclaw cron remove <id>' after checking which one to keep; this script never deletes jobs." >&2
  exit 1
fi

if [ "$MODE" = "check" ]; then
  if [ "${COUNT:-0}" = "1" ] && [ -z "$DIFF" ]; then echo "PASS [$PROG]: exactly one job and it matches"; exit 0; fi
  echo "FAIL [$PROG]: job missing or drifted; run with --apply" >&2; exit 1
fi

COMMON="--cron|$SCHEDULE|--agent|$AGENT|--session|isolated|--message|$MSG|--model|$PRIMARY|--fallbacks|$FALLBACK|--thinking|$THINKING|--timeout-seconds|$TIMEOUT_S|--no-deliver|--description|$DESC"
if [ "$MODE" = "dry-run" ]; then
  if [ "${COUNT:-0}" = "0" ]; then echo "PLAN [$PROG]: would ADD the job (dry run; pass --apply to create it)"
  elif [ -n "$DIFF" ]; then echo "PLAN [$PROG]: would EDIT job $JOB_ID in place ($DIFF) (dry run)"
  else echo "PLAN [$PROG]: nothing to do, job is current"; fi
  exit 0
fi

# ── 5. Apply ─────────────────────────────────────────────────────────────────
run_cli() { # run_cli <subcommand...> -- then COMMON split on |
  local old_ifs="$IFS"; IFS='|'; set -f   # split on | only; never glob the "*" in the schedule
  # shellcheck disable=SC2086
  set -- "$@" $COMMON
  set +f; IFS="$old_ifs"
  "$OPENCLAW_BIN" "$@" > "$TMP/apply.out" 2>&1
}
if [ "${COUNT:-0}" = "0" ]; then
  run_cli cron add --name "$JOB_NAME" || { tail -5 "$TMP/apply.out" >&2; tool_err "'openclaw cron add' failed"; }
  echo "[$PROG] added job '$JOB_NAME'"
elif [ -n "$DIFF" ]; then
  if [ "$KIND" != "agentTurn" ]; then
    echo "FAIL [$PROG]: job $JOB_ID is kind '$KIND', not agentTurn; editing its model would rewrite its payload. Leaving it untouched." >&2
    exit 1
  fi
  "$OPENCLAW_BIN" cron edit --help > "$TMP/edit-help" 2>&1 || tool_err "'openclaw cron edit --help' failed"
  for f in --cron --agent --session --message --model --fallbacks --thinking --timeout-seconds --no-deliver --description --enable; do
    has_flag "$TMP/edit-help" "$f" || { echo "REFUSED [$PROG]: 'cron edit' lacks $f; no change made" >&2; exit 5; }
  done
  run_cli cron edit "$JOB_ID" --enable || { tail -5 "$TMP/apply.out" >&2; tool_err "'openclaw cron edit' failed"; }
  echo "[$PROG] edited job $JOB_ID in place ($DIFF)"
else
  echo "[$PROG] job is current; nothing changed"
fi

# ── 6. Read back ─────────────────────────────────────────────────────────────
STATE="$(read_state)"
[ -z "$(state_val LISTERR)" ] || tool_err "read-back 'openclaw cron list --json' failed"
if [ "$(state_val COUNT)" = "1" ] && [ -z "$(state_val DIFF)" ]; then
  echo "PASS [$PROG]: read-back confirms exactly one '$JOB_NAME' job with the intended model order, schedule, session, thinking and quiet delivery"
  exit 0
fi
echo "FAIL [$PROG]: read-back mismatch (count=$(state_val COUNT) drifted=$(state_val DIFF))" >&2
exit 1
