#!/usr/bin/env bash
# mc-route.sh — SIGNED general task-routing helper (fleet-wide).
#
# This is the GENERAL version of route-presentation.sh: the same signed
# Command-Center ingest helper, but the department is an ARGUMENT instead of the
# hardcoded "presentations". It is the shipped implementation behind the
# `mc-route__route_task` routing tool the CEO/orchestrator uses to route ANY
# task to ANY department without self-executing.
#
#   USAGE:  mc-route.sh task "<short title>" "<owner's exact words>"
#           mc-route.sh existing status "<task title or id>"
#           mc-route.sh existing update "<task title or id>" "<note>"
#           mc-route.sh existing cancel "<task title or id>"
#           (legacy) mc-route.sh auto "<owner message verbatim>"
#           (legacy) mc-route.sh <department_slug> <title> [description...]
#
#   FIRST WORD IS CHECKED (JEV-601): it must be task, existing, auto, help, or a
#     department that EXISTS on this board (its slug, id or name, with or without
#     "dept-"; checked against GET /api/workspaces and sent as the board's real
#     slug). Anything else ("status", "stop", "check", "list", a department this
#     box does not have) prints `mc-route: REFUSED — ...` plus the usage and exits
#     2 WITHOUT creating anything. Before this, any first word was taken as a
#     department, so `mc-route.sh status <task>` made a General Task card.
#
#   EXISTING MODE (work already on the board; NEVER creates a card):
#     finds ONE task in this company by exact id, exact title, or a WHOLE-WORD
#     match at 1.0 on the title -- never a raw substring and never a partial
#     score (GET /api/tasks, then GET /api/tasks/<id> for an archived id).
#       status  read-only (GETs only). Prints
#               STATUS id=<id> status=<s> department=<d> updated=<t> cancelled=<yes|no> title="<title>"
#       update  POST /api/tasks/<id>/messages {content:<note>, sender:owner}  -> UPDATED id=...
#       cancel  POST /api/tasks/<id>/archive (Command Center's cancel: off the board,
#               never dispatched again, row kept) + an owner note -> CANCELLED id=...
#     Same-title cards are ONE job carded twice, not ambiguity: the newest is
#     acted on, and cancel archives every one of them.
#     FAIL-CLOSED (JEV-802): if the task list or the department list cannot be
#     read, or comes back empty, or the matcher itself fails, this exits 1 with
#     FAILED + ESCALATE_TO_OPERATOR -- never NOT_FOUND. NOT_FOUND is only ever
#     said of a list that loaded successfully and genuinely holds no match.
#     No match -> `mc-route: NOT_FOUND ...` (update: new work, run `task`; status or
#     cancel: tell the owner, NO card), several differently-titled matches ->
#     `mc-route: AMBIGUOUS ...` with the candidates; both exit 3 and change nothing.
#     MC_ROUTE_API_BASE overrides the Command Center base URL (default: the ingest
#     URL without /api/tasks/ingest).
#
#   SLUG MODE (legacy) arguments:
#     <department_slug>   target workspace/department (e.g. presentations,
#                         general-task, social-media, video). REQUIRED.
#     <title>             short task title (truncated to 120 chars). REQUIRED.
#     [description...]    the rest of the args are joined with single spaces
#                         into the task description (owner message, verbatim).
#
#   AUTO MODE (JEV live routing): `mc-route.sh auto "<owner message verbatim>"`
#     joins every arg after 'auto' with single spaces into MESSAGE (verbatim; an
#     empty MESSAGE goes through the same usage escalation as a missing slug/title)
#     and posts it alone ({message}, no title/description/department_slug) to the
#     CC ingest raw door, which classifies it and either answers it or creates and
#     routes exactly one card. Reuses the identical signing/secret/retry path below.
#     stdout contract for the caller (the CEO agent):
#       JEV_ANSWER_DIRECTLY intent=<intent>          — a question; answer it, create nothing.
#       ROUTED workspace=<ws> department=<d> resolved_by=<r>   — one card now exists.
#     HTTP 403 {error:control_probe_never_creates} also prints
#     `JEV_ANSWER_DIRECTLY intent=unresolved` (exit 0); every other non-2xx escalates,
#     exactly like slug mode.
#
#   TASK MODE (the CEO already decided "this is work"):
#     `mc-route.sh task "<short title>" "<owner's exact words>"` posts ONE card
#     {title, description=<owner's exact words>} with NO department_slug, so the
#     Command Center picks the department (its picker, then General Task). A typed
#     payload is never re-classified by CC, so a task call is never overruled into
#     "answer". One call = one card: two jobs in one message = two calls with two
#     titles. Leans to a card: a missing title uses the words, missing words use the
#     title; only both empty fails. Idempotent per call: the operation key is derived
#     from (company, source, requester, title, words) and reused for 60 s after the
#     last identical call (state under MC_ROUTE_STATE_DIR), so a retry with the same
#     words dedupes at CC instead of making a second card; MC_ROUTE_EVENT_ID /
#     MC_ROUTE_OPERATION_ID, when set, replace the window with that stable event.
#     stdout on success: the same `ROUTED workspace=<ws> department=<d> resolved_by=<r>`
#     line as auto mode (exit 0). Any failure (transport, non-2xx, a 2xx with no
#     task_id) prints `mc-route: FAILED — ...` + ESCALATE_TO_OPERATOR and exits 1.
#     A card with no workspace, or one CC could only park on ->ceo/->unrouted, prints
#     ROUTED plus an ESCALATE_TO_OPERATOR warning (exit 0: the card exists; retrying
#     would not help).
#
# WHY (identical to route-presentation.sh): the Command Center ships FAIL-CLOSED.
# Middleware 503s external ingest when WEBHOOK_SECRET is unset, and 401s when
# MC_API_TOKEN is set but no Bearer is sent; the /api/tasks/ingest route 401s when
# WEBHOOK_SECRET is set and x-webhook-signature is missing. A loopback curl gets NO
# same-origin exemption (it sends no Origin). So — exactly like the sanctioned
# producer 06-ghl-install-pages/tools/cc_board.py and route-presentation.sh — this
# helper signs BOTH layers:
#   Authorization: Bearer <MC_API_TOKEN>                          (middleware layer)
#   x-webhook-signature: HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex (route layer)
# Secrets are resolved at RUNTIME from the box's stores; NO secret value is ever
# written into this file.
#
# EXIT 0 on a 2xx ingest; 1 (with ESCALATE_TO_OPERATOR) on failure — then the CEO
# must tell the owner it is escalating to the operator (never self-intake, never
# ask intake questions, never retry forever). EXIT 2 = REFUSED usage error and
# EXIT 3 = existing task not found / ambiguous: nothing was created or changed;
# fix the call or ask the owner, do not escalate.
#
# OPTIONAL ENV OVERRIDES (all have safe defaults; the security-critical secret
# resolution + signing are IDENTICAL to route-presentation.sh):
#   MC_ROUTE_INGEST_URL   ingest endpoint    (default http://127.0.0.1:4000/api/tasks/ingest)
#   MC_ROUTE_SOURCE       payload "source"   (default telegram)
#   MC_ROUTE_PRIORITY     payload "priority" (default medium)
#   MC_ROUTE_MAX_RETRIES  retries after 1st  (default 2)
#   MC_ROUTE_REQUESTER_CHAT_ID   P1-04 trust engine: the ORIGINATING client chat id the
#                                Command Center report-back loop acks/progress/dones back to.
#                                Set by the orchestrator when the task came from a client message.
#   MC_ROUTE_REQUESTER_CHANNEL   the client channel (default telegram); only used when
#                                MC_ROUTE_REQUESTER_CHAT_ID is set.
# MC_ROUTE_EVENT_ID: stable originating event (reuse on retry).
# MC_ROUTE_OPERATION_ID: explicit operation fallback; otherwise allocated once per invocation.
# MC_ROUTE_COMPANY_ID scopes the operation at the receiver.
set -uo pipefail

INGEST_URL="${MC_ROUTE_INGEST_URL:-http://127.0.0.1:4000/api/tasks/ingest}"
MAX_RETRIES="${MC_ROUTE_MAX_RETRIES:-2}"
SOURCE="${MC_ROUTE_SOURCE:-telegram}"
PRIORITY="${MC_ROUTE_PRIORITY:-medium}"
CONNECT_TIMEOUT="${MC_ROUTE_CONNECT_TIMEOUT:-5}"
REQUEST_TIMEOUT="${MC_ROUTE_REQUEST_TIMEOUT:-30}"
TOTAL_TIMEOUT="${MC_ROUTE_TOTAL_TIMEOUT:-95}"
PYTHON="${WORKFORCE_PYTHON:-python3}"
# P1-04 trust engine: the originating client channel + chat id, so the Command
# Center report-back loop can acknowledge/progress/done back to the client. Empty
# (the default) => omitted from the payload (an operator/internal route).
REQUESTER_CHAT_ID="${MC_ROUTE_REQUESTER_CHAT_ID:-}"
REQUESTER_CHANNEL="${MC_ROUTE_REQUESTER_CHANNEL:-telegram}"

ROUTE_MODE="slug"
DEPARTMENT_SLUG=""
TITLE=""
DESCRIPTION=""
MESSAGE=""
# JEV-804: the command word is case-insensitive -- TASK, Task, Existing, Status
# all work. Only the command word is folded; a department slug and a task title
# are passed through exactly as the owner wrote them.
_CMD="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
if [ "$_CMD" = "task" ]; then
  ROUTE_MODE="task"
  shift
  TITLE="${1:-}"
  [ "$#" -gt 0 ] && shift
  # rest args form owner's exact words, joined single spaces.
  DESCRIPTION="$*"
  # Lean to card: fill whichever half missing from other.
  [ -n "$TITLE" ] || TITLE="$DESCRIPTION"
  [ -n "$DESCRIPTION" ] || DESCRIPTION="$TITLE"
elif [ "$_CMD" = "auto" ]; then
  ROUTE_MODE="auto"
  shift
  # rest args (1..N) form owner message, joined single spaces.
  MESSAGE="$*"
elif [ "$_CMD" = "existing" ]; then
  ROUTE_MODE="existing"
  EXISTING_ACTION="$(printf '%s' "${2:-}" | tr '[:upper:]' '[:lower:]')"
  EXISTING_REF="${3:-}"
  shift; [ "$#" -gt 0 ] && shift; [ "$#" -gt 0 ] && shift
  EXISTING_NOTE="$*"
else
  DEPARTMENT_SLUG="${1:-}"
  TITLE="${2:-}"
  # The rest of the args (3..N) form the description, joined with single spaces.
  if [ "$#" -gt 2 ]; then
    shift 2
    DESCRIPTION="$*"
  fi
fi

_escalate() {
  echo "mc-route: FAILED — $1" >&2
  echo "ESCALATE_TO_OPERATOR: task routing failed. The CEO must tell the owner it is escalating this to the operator. Do NOT self-intake, do NOT ask intake questions, do NOT retry." >&2
  exit 1
}

_usage() {
  cat <<'USAGE'
usage:
  mc-route.sh task "<short title>" "<owner's exact words>"      new card, one per job
  mc-route.sh existing status "<task title or id>"              read-only status of existing work; never creates a card
  mc-route.sh existing update "<task title or id>" "<note>"     adds the owner's note or change to that card
  mc-route.sh existing cancel "<task title or id>"              cancels that card
  (legacy) mc-route.sh auto "<message>"  |  mc-route.sh <department> "<title>" [words...]
USAGE
}
_refuse() {  # the caller used the tool wrong: say so, create nothing, exit 2
  echo "mc-route: REFUSED — $1 Nothing was created or changed." >&2
  _usage >&2
  exit 2
}

if [ "$ROUTE_MODE" = "task" ]; then
  [ -n "$TITLE" ] || _escalate 'empty task (usage: mc-route.sh task "<short title>" "<owner'"'"'s exact words>")'
elif [ "$ROUTE_MODE" = "auto" ]; then
  [ -n "$MESSAGE" ] || _escalate 'empty message argument (usage: mc-route.sh auto "<owner message verbatim>")'
elif [ "$ROUTE_MODE" = "existing" ]; then
  case "$EXISTING_ACTION" in
    status|update|cancel) ;;
    *) _refuse "'existing' must be followed by status, update or cancel (got '$EXISTING_ACTION')." ;;
  esac
  [ -n "$EXISTING_REF" ] || _refuse "'existing $EXISTING_ACTION' needs the task title or id."
  [ "$EXISTING_ACTION" != "update" ] || [ -n "$EXISTING_NOTE" ] || _refuse "'existing update' needs the owner's note."
else
  case "$(printf '%s' "$DEPARTMENT_SLUG" | tr '[:upper:]' '[:lower:]')" in -h|--help|help) _usage; exit 0 ;; esac
  [ -n "$DEPARTMENT_SLUG" ] || _refuse "no command given."
  # Words models used for existing work (JEV-592 acceptance run): refuse them
  # before any network call and point at `existing`.
  case "$(printf '%s' "$DEPARTMENT_SLUG" | tr '[:upper:]' '[:lower:]')" in
    -*|status|stop|check|list|show|get|find|cancel|update|resume|pause|continue|kill|delete|close|done|tasks|queue|exec|execution|progress|info)
      _refuse "'$DEPARTMENT_SLUG' is not a command or a department. For work already on the board use: mc-route.sh existing status|update|cancel \"<task title or id>\"." ;;
  esac
  # The title is checked after the board check below, so an unknown first word
  # is always a REFUSED usage error, never an escalation.
fi

for _numeric in "$MAX_RETRIES" "$CONNECT_TIMEOUT" "$REQUEST_TIMEOUT" "$TOTAL_TIMEOUT"; do
  case "$_numeric" in ''|*[!0-9]*) _escalate 'timeout/retry settings must be integer seconds' ;; esac
done
[ "$MAX_RETRIES" -le 5 ] || _escalate 'at most five retries are allowed'
[ "$REQUEST_TIMEOUT" -gt 0 ] && [ "$CONNECT_TIMEOUT" -gt 0 ] && [ "$TOTAL_TIMEOUT" -gt 0 ] || _escalate 'timeouts must be positive'
# ── Runtime secret resolution (reads only; never hardcoded) ──────────────────
# Store order mirrors the Command Center's own env precedence so the signature
# matches what the CC server validates against; the WEBHOOK_SECRET alias order
# (WEBHOOK_SECRET, then CC_WEBHOOK_SECRET) mirrors cc_board.py. Live process env
# is the last-resort fallback. IDENTICAL to route-presentation.sh.
_ENV_STORES=(
  "$HOME/projects/command-center/.env.local"
  "$HOME/projects/command-center/.env"
  "/data/projects/command-center/.env.local"
  "/data/projects/command-center/.env"
  "$HOME/.openclaw/secrets/.env"
  "/data/.openclaw/secrets/.env"
)

_resolve() {
  # $@ = candidate key names (aliases). First non-empty across the dotenv stores
  # (in order) then the live process env. Prints ONLY the value. Uses python3 for
  # robust dotenv parsing (export / quotes / comments).
  RP_KEYS="$*" "$PYTHON" - "${_ENV_STORES[@]}" <<'PYRESOLVE'
import os, sys
keys = os.environ.get("RP_KEYS", "").split()
stores = sys.argv[1:]

def parse(path):
    out = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("export "):
                    s = s[len("export "):]
                if "=" not in s:
                    continue
                k, v = s.split("=", 1)
                k = k.strip(); v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                    v = v[1:-1]
                out[k] = v
    except Exception:
        return {}
    return out

for path in stores:
    kv = parse(path)
    for k in keys:
        if kv.get(k):
            sys.stdout.write(kv[k]); sys.exit(0)
for k in keys:
    v = os.environ.get(k)
    if v:
        sys.stdout.write(v); sys.exit(0)
PYRESOLVE
}

MC_API_TOKEN="$(_resolve MC_API_TOKEN)"
WEBHOOK_SECRET="$(_resolve WEBHOOK_SECRET CC_WEBHOOK_SECRET)"

# ── Build the EXACT raw body once (compact JSON, like cc_board.py) ───────────
BODY_FILE="$(mktemp "${TMPDIR:-/tmp}/mc-route.XXXXXX")" || _escalate "mktemp failed"
HEADER_FILE="$(mktemp "${TMPDIR:-/tmp}/mc-route-headers.XXXXXX")" || _escalate "mktemp failed"
WS_FILE="$(mktemp "${TMPDIR:-/tmp}/mc-route-ws.XXXXXX")" || _escalate "mktemp failed"
TASKS_FILE="$(mktemp "${TMPDIR:-/tmp}/mc-route-tasks.XXXXXX")" || _escalate "mktemp failed"
trap 'rm -f "$BODY_FILE" "$HEADER_FILE" "$WS_FILE" "$TASKS_FILE"' EXIT

# ── Command Center reads/writes other than ingest (JEV-601) ──────────────────
API_BASE="${MC_ROUTE_API_BASE:-${INGEST_URL%/api/tasks/ingest}}"
API_CODE=""
API_OUT=""
_api() {  # $1=METHOD $2=path [$3=JSON body file]. One try. Sets API_CODE (000 = transport) + API_OUT.
  local h=(-H 'Accept: application/json') raw rc=0
  [ -n "$MC_API_TOKEN" ] && h+=(-H "Authorization: Bearer $MC_API_TOKEN")
  [ -n "${3:-}" ] && h+=(-H 'Content-Type: application/json' --data-binary @"$3")
  raw="$(curl -sS --connect-timeout "$CONNECT_TIMEOUT" --max-time "$REQUEST_TIMEOUT" \
    -X "$1" "$API_BASE$2" "${h[@]}" -w $'\n%{http_code}' 2>/dev/null)" || rc=$?
  API_CODE="${raw##*$'\n'}"
  API_OUT="${raw%$'\n'*}"
  [ "$rc" -eq 0 ] || API_CODE="000"
}
_load_departments() {  # this company's board departments -> $WS_FILE, or escalate
  _api GET /api/workspaces
  case "$API_CODE" in 2[0-9][0-9]) ;; *) _escalate "could not read the department list (GET /api/workspaces HTTP $API_CODE); nothing was created or changed" ;; esac
  printf '%s' "$API_OUT" >"$WS_FILE"
  # JEV-802 (class F, fail-closed): an unreadable or EMPTY department list is not
  # a board without departments. Escalate here, so no later lookup can read it as
  # "no matching department" and report a miss it never proved.
  "$PYTHON" - "$WS_FILE" <<'PYWS' || _escalate "the department list from Command Center was unreadable or empty; nothing was created or changed"
import json, sys
try:
    with open(sys.argv[1], "r", encoding="utf-8", errors="replace") as fh:
        d = json.load(fh)
except Exception:
    sys.exit(9)
if isinstance(d, dict):
    d = d.get("workspaces") if isinstance(d.get("workspaces"), list) else ([d] if d.get("id") else [])
if not isinstance(d, list) or not [x for x in d if isinstance(x, dict)]:
    sys.exit(9)
PYWS
}

if [ "$ROUTE_MODE" = "existing" ]; then
  _load_departments
  # JEV-803: includeArchived=true — a cancelled or done card IS the honest answer
  # to a status or cancel question. Without it the archived row vanishes from the
  # list and the caller wrongly reports NOT_FOUND for work that really exists.
  _TASKS_MAX=500
  _api GET "/api/tasks?limit=$_TASKS_MAX&includeArchived=true"
  case "$API_CODE" in 2[0-9][0-9]) ;; *) _escalate "could not read the task list (GET /api/tasks HTTP $API_CODE); nothing was changed" ;; esac
  printf '%s' "$API_OUT" >"$TASKS_FILE"
  # JEV-803: at the limit, "nothing matching is on the board" is a claim about a
  # page, not about the board. Say so rather than imply the whole board was read.
  _TASKS_ROWS="$("$PYTHON" -c 'import json,sys
try:
    with open(sys.argv[1], "r", encoding="utf-8", errors="replace") as fh:
        d = json.load(fh)
except Exception:
    sys.exit(4)
if isinstance(d, dict):
    d = d.get("tasks") if isinstance(d.get("tasks"), list) else ([d] if d.get("id") else [])
rows = [x for x in d if isinstance(x, dict)] if isinstance(d, list) else []
print(len(rows))' "$TASKS_FILE")" \
    || _escalate "the task list from Command Center was unreadable; nothing was created or changed"
  if [ "${_TASKS_ROWS:-0}" -ge "$_TASKS_MAX" ]; then
    echo "mc-route: NOTE — the board returned $_TASKS_ROWS cards, the $_TASKS_MAX-card page limit, so only the most recent page was covered. If the owner's card is not here it may be on an older page: say the list may be incomplete rather than that the work does not exist." >&2
  fi
  _find_task() {  # prints FOUND + 6 fields, AMBIGUOUS + candidates, or NONE
    "$PYTHON" - "$EXISTING_REF" "$WS_FILE" "$TASKS_FILE" <<'PYFIND'
import json, re, sys
ref, ws_path, tasks_path = sys.argv[1], sys.argv[2], sys.argv[3]
def load(path):
    # JEV-802 (class F, fail-closed): an unreadable file, a payload with no rows,
    # or a row with no id is a broken read -- exit 4 so the caller escalates.
    # It must never come back as an empty list, because empty reads as "NONE"
    # and NONE reads as "the owner's work does not exist".
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            d = json.load(fh)
    except Exception:
        sys.exit(4)
    if isinstance(d, dict):
        d = d.get("tasks") if isinstance(d.get("tasks"), list) else ([d] if d.get("id") else [])
    if not isinstance(d, list) or not [x for x in d if isinstance(x, dict)]:
        sys.exit(4)
    return [x for x in d if isinstance(x, dict)]
ws_rows = load(ws_path)
ws = {str(w.get("id")): str(w.get("slug") or w.get("id")) for w in ws_rows if w.get("id")}
# This company only: tasks on one of its departments (or not yet on any).
tasks = []
for t in load(tasks_path):
    if not t.get("id"):
        sys.exit(4)
    if t.get("workspace_id") and str(t["workspace_id"]) not in ws:
        continue
    tasks.append(t)
STOP = {"the", "and", "for", "that", "this", "task", "card", "job", "with", "from", "our", "your", "about", "please", "one"}
def words(s):
    return {w for w in re.findall(r"[a-z0-9]+", str(s or "").lower()) if len(w) > 2 and w not in STOP}
def title(t):
    return " ".join(str(t.get("title") or "").split())
key = ref.strip().lower()
pick = [t for t in tasks if str(t["id"]).lower() == key] or [t for t in tasks if title(t).lower() == key]
if not pick:
    # JEV-802: exact id, exact title, or a WHOLE-WORD match at 1.0 -- nothing else.
    # No raw substring ("art" must not hit "cart") and no partial score ("invoice
    # draft" must not half-hit "invoice" alone). A task matches only when every
    # word of the reference appears in its title as a whole word.
    want = words(key)
    if want:
        pick = [t for t in tasks if want <= words(title(t))]
if pick:
    # Same-title cards are ONE job carded twice (a double card), not ambiguity:
    # newest first so the live card is the one acted on. Cancel archives them all.
    pick.sort(key=lambda t: str(t.get("updated_at") or ""), reverse=True)
if len(pick) == 1:
    t = pick[0]
    print("FOUND")
    for v in (t["id"], t.get("status"), ws.get(str(t.get("workspace_id")), t.get("workspace_id") or "none"),
              t.get("updated_at"), "yes" if t.get("archived_at") else "no", title(t).replace('"', "'")):
        print("" if v is None else " ".join(str(v).split()))
elif pick and len({title(t).lower() for t in pick}) == 1:
    t = pick[0]
    print("FOUND")
    for v in (t["id"], t.get("status"), ws.get(str(t.get("workspace_id")), t.get("workspace_id") or "none"),
              t.get("updated_at"), "yes" if t.get("archived_at") else "no", title(t).replace('"', "'")):
        print("" if v is None else " ".join(str(v).split()))
    # Everything below the 7 fields: the same-title duplicates, tab-separated
    # id / already-cancelled / title. Cancel archives every one of them.
    for d in pick[1:]:
        print("\t".join([str(d["id"]), "yes" if d.get("archived_at") else "no",
                         title(d).replace("\t", " ").replace('"', "'")]))
elif pick:
    print("AMBIGUOUS")
    for t in pick[:5]:
        print('  id=%s status=%s title="%s"' % (t["id"], t.get("status"), title(t)))
else:
    print("NONE")
PYFIND
  }
  _FIND_RC=0
  FOUND="$(_find_task)" || _FIND_RC=$?
  # JEV-802 (class F, fail-closed): the matcher could not read the board it was
  # given. That is not "no matching card" -- never let it reach the NOT_FOUND text.
  [ "$_FIND_RC" -eq 0 ] || _escalate "the task list from Command Center could not be read or matched, so no card could be identified; nothing was created or changed"
  if [ "$(printf '%s\n' "$FOUND" | sed -n '1p')" = "NONE" ]; then
    case "$EXISTING_REF" in
      *[[:space:]]*|'') ;;
      *)  # an id the open list does not hold (e.g. already cancelled): read it directly
        _api GET "/api/tasks/$("$PYTHON" -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$EXISTING_REF")"
        case "$API_CODE" in
          2[0-9][0-9]) printf '%s' "$API_OUT" >"$TASKS_FILE"
            _FIND_RC=0
            FOUND="$(_find_task)" || _FIND_RC=$?
            [ "$_FIND_RC" -eq 0 ] || _escalate "the task record read for \"$EXISTING_REF\" was unreadable, so it could not be matched; nothing was created or changed" ;;
          404) ;;  # the board answered: no such id (the honest NONE)
          *) _escalate "could not read task \"$EXISTING_REF\" (GET /api/tasks HTTP $API_CODE); nothing was created or changed" ;;
        esac
        ;;
    esac
  fi
  case "$(printf '%s\n' "$FOUND" | sed -n '1p')" in
    FOUND) ;;
    AMBIGUOUS)
      echo "mc-route: AMBIGUOUS — several tasks match \"$EXISTING_REF\". Nothing was created or changed. Ask the owner which one, or re-run with its id:"
      printf '%s\n' "$FOUND" | sed '1d'
      exit 3 ;;
    *)
      # JEV-801 (class F): only `update` points on to `task`. A status question or a
      # cancel about something not on the board is never new work.
      case "$EXISTING_ACTION" in
        update) echo "mc-route: NOT_FOUND: no matching existing card. This is new work: run mc-route.sh task \"<short title>\" \"<owner's exact words>\" (nothing was created or changed for \"$EXISTING_REF\")" ;;
        status) echo "mc-route: NOT_FOUND: nothing matching is on the board. Tell the owner; do NOT create a card. (nothing was created or changed for \"$EXISTING_REF\")" ;;
        *)      echo "mc-route: NOT_FOUND: nothing matching is on the board to cancel. Tell the owner; do NOT create a card. (nothing was created or changed for \"$EXISTING_REF\")" ;;
      esac
      exit 3 ;;
  esac
  _T_ID="$(printf '%s\n' "$FOUND" | sed -n '2p')"
  _T_STATUS="$(printf '%s\n' "$FOUND" | sed -n '3p')"
  _T_DEPT="$(printf '%s\n' "$FOUND" | sed -n '4p')"
  _T_UPDATED="$(printf '%s\n' "$FOUND" | sed -n '5p')"
  _T_CANCELLED="$(printf '%s\n' "$FOUND" | sed -n '6p')"
  _T_TITLE="$(printf '%s\n' "$FOUND" | sed -n '7p')"
  _T_PATH="/api/tasks/$("$PYTHON" -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$_T_ID")"
  _note() {  # $1 = note text -> POST it to the card as an owner message
    NOTE="$1" "$PYTHON" -c 'import json, os, sys; sys.stdout.write(json.dumps({"content": os.environ["NOTE"], "sender": "owner"}))' >"$BODY_FILE"
    _api POST "$_T_PATH/messages" "$BODY_FILE"
  }
  case "$EXISTING_ACTION" in
    status)
      echo "STATUS id=$_T_ID status=$_T_STATUS department=$_T_DEPT updated=$_T_UPDATED cancelled=$_T_CANCELLED title=\"$_T_TITLE\""
      ;;
    update)
      _note "$EXISTING_NOTE"
      case "$API_CODE" in 2[0-9][0-9]) ;; *) _escalate "could not add the note to task $_T_ID (HTTP $API_CODE)" ;; esac
      echo "UPDATED id=$_T_ID title=\"$_T_TITLE\""
      ;;
    cancel)
      if [ "$_T_CANCELLED" = "yes" ]; then
        echo "CANCELLED id=$_T_ID title=\"$_T_TITLE\" (it was already cancelled)"
        exit 0
      fi
      _api POST "$_T_PATH/archive"
      case "$API_CODE" in 2[0-9][0-9]) ;; *) _escalate "could not cancel task $_T_ID (HTTP $API_CODE)" ;; esac
      _note "Cancelled by the owner.${EXISTING_NOTE:+ $EXISTING_NOTE}"
      case "$API_CODE" in 2[0-9][0-9]) ;; *) echo "mc-route: WARNING — task $_T_ID is cancelled but the cancel note was not saved (HTTP $API_CODE)." >&2 ;; esac
      echo "CANCELLED id=$_T_ID title=\"$_T_TITLE\""
      # JEV-802: same-title duplicates are the same job carded twice. Cancelling
      # the job cancels all of them, or the survivors keep the work alive on the
      # board after the owner was told it was cancelled.
      printf '%s\n' "$FOUND" | sed -n '8,$p' | while IFS="$(printf '\t')" read -r _DID _DCANCELLED _DTITLE; do
        [ -n "$_DID" ] || continue
        if [ "$_DCANCELLED" = "yes" ]; then
          echo "CANCELLED id=$_DID title=\"$_DTITLE\" (it was already cancelled)"
          continue
        fi
        _api POST "/api/tasks/$("$PYTHON" -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$_DID")/archive"
        case "$API_CODE" in
          2[0-9][0-9]) echo "CANCELLED id=$_DID title=\"$_DTITLE\" (duplicate of the same job)" ;;
          *) echo "mc-route: WARNING — duplicate card $_DID of the same job was NOT cancelled (HTTP $API_CODE); the owner should be told." >&2 ;;
        esac
      done
      ;;
  esac
  exit 0
fi

if [ "$ROUTE_MODE" = "slug" ]; then
  # The first word must be a department that exists on this board; send its real slug.
  _load_departments
  _DEPT_RC=0
  _DEPT="$("$PYTHON" - "$DEPARTMENT_SLUG" "$WS_FILE" <<'PYDEPT'
import json, re, sys
def norm(s):
    s = re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-")
    return s[5:] if s.startswith("dept-") else s
try:
    rows = json.load(open(sys.argv[2]))
except Exception:
    sys.exit(3)
if not isinstance(rows, list):
    sys.exit(3)
rows = [r for r in rows if isinstance(r, dict) and (r.get("slug") or r.get("id"))]
arg = sys.argv[1].strip().lower()
exact = [r for r in rows if arg in (str(r.get("slug") or "").lower(), str(r.get("id") or "").lower())]
want = norm(arg)
loose = [r for r in rows if want and want in (norm(r.get("slug")), norm(r.get("id")), norm(r.get("name")))]
hit = exact[:1] or (loose if len(loose) == 1 else [])
if hit:
    print(hit[0].get("slug") or hit[0].get("id"))
    sys.exit(0)
print(" ".join(sorted({str(r.get("slug") or r.get("id")) for r in rows})))
sys.exit(1)
PYDEPT
)" || _DEPT_RC=$?
  case "$_DEPT_RC" in
    0) DEPARTMENT_SLUG="$_DEPT" ;;
    1) _refuse "'$DEPARTMENT_SLUG' is not a command or a department on this board (departments: ${_DEPT:-none}). To make a card and let Command Center pick the department use: mc-route.sh task \"<short title>\" \"<owner's exact words>\"." ;;
    *) _escalate "the department list from Command Center was unreadable; nothing was created" ;;
  esac
  [ -n "$TITLE" ] || _escalate "empty title argument (usage: mc-route.sh <department_slug> <title> [description...])"
fi

if [ "$ROUTE_MODE" = "auto" ]; then
  _BODY_BUILD_OK=0
  MESSAGE="$MESSAGE" SOURCE="$SOURCE" PRIORITY="$PRIORITY" \
    REQUESTER_CHAT_ID="$REQUESTER_CHAT_ID" REQUESTER_CHANNEL="$REQUESTER_CHANNEL" \
    "$PYTHON" - >"$BODY_FILE" <<'PYBODY_AUTO' && _BODY_BUILD_OK=1
import json, os, sys, uuid
operation = os.environ.get('MC_ROUTE_EVENT_ID') or os.environ.get('MC_ROUTE_OPERATION_ID') or str(uuid.uuid4())
payload = {
    'idempotency_key': operation,
    'external_session_id': os.environ.get('MC_ROUTE_EXTERNAL_SESSION_ID', ''),
    "message": os.environ.get("MESSAGE", ""),
    "source": os.environ.get("SOURCE", "telegram"),
    "priority": os.environ.get("PRIORITY", "medium"),
}
company = os.environ.get('MC_ROUTE_COMPANY_ID', '').strip()
if company:
    payload['company_id'] = company
# P1-04 trust engine: pass the originating client chat id through so the Command
# Center captures it and reports acknowledge/progress/done back to the client.
# Only added when present — an operator/internal route omits it entirely.
_rcid = os.environ.get("REQUESTER_CHAT_ID", "").strip()
if _rcid:
    payload["requester_chat_id"] = _rcid
    payload["requester_channel"] = os.environ.get("REQUESTER_CHANNEL", "telegram").strip() or "telegram"
sys.stdout.write(json.dumps(payload, separators=(",", ":")))
PYBODY_AUTO
  [ "$_BODY_BUILD_OK" -eq 1 ] || _escalate "could not build request body"
elif [ "$ROUTE_MODE" = "task" ]; then
  if ! TITLE="$TITLE" DESCRIPTION="$DESCRIPTION" SOURCE="$SOURCE" PRIORITY="$PRIORITY" \
       REQUESTER_CHAT_ID="$REQUESTER_CHAT_ID" REQUESTER_CHANNEL="$REQUESTER_CHANNEL" \
       MC_ROUTE_STATE_DIR="${MC_ROUTE_STATE_DIR:-${TMPDIR:-/tmp}/mc-route-task-$(id -u)}" \
       "$PYTHON" - >"$BODY_FILE" <<'PYBODY_TASK'
import hashlib, json, os, sys, time, uuid
env = os.environ.get
title = env("TITLE", "")[:120]
words = env("DESCRIPTION", "")
company = env("MC_ROUTE_COMPANY_ID", "").strip()
rcid = env("REQUESTER_CHAT_ID", "").strip()
channel = (env("REQUESTER_CHANNEL", "telegram").strip() or "telegram") if rcid else ""
job = hashlib.sha256(json.dumps([company, env("SOURCE", "telegram"), channel, rcid, title, words]).encode()).hexdigest()[:32]
event = env("MC_ROUTE_EVENT_ID") or env("MC_ROUTE_OPERATION_ID")
if event:
    # Stable originating event: same event + same job = same operation; two jobs
    # from one event stay two operations (two cards).
    key = "mc-route-task:" + hashlib.sha256((event + "\0" + job).encode()).hexdigest()[:40]
else:
    # 60 s retry window, sliding from the last identical call.
    # ponytail: no lock; two identical calls in the same instant can mint two keys.
    state_dir = env("MC_ROUTE_STATE_DIR")
    os.makedirs(state_dir, mode=0o700, exist_ok=True)
    path = os.path.join(state_dir, job)
    now = time.time()
    key = ""
    try:
        if now - os.path.getmtime(path) < 60:
            key = open(path).read().strip()
    except OSError:
        pass
    if not key:
        key = "mc-route-task:%s:%s" % (job, uuid.uuid4().hex[:12])
    with open(path, "w") as fh:
        fh.write(key)
    for name in os.listdir(state_dir):  # prune stale window files (> 1 h)
        try:
            if now - os.path.getmtime(os.path.join(state_dir, name)) > 3600:
                os.remove(os.path.join(state_dir, name))
        except OSError:
            pass
payload = {
    "idempotency_key": key,
    "external_session_id": env("MC_ROUTE_EXTERNAL_SESSION_ID", ""),
    "title": title,
    "description": words,
    "source": env("SOURCE", "telegram"),
    "priority": env("PRIORITY", "medium"),
}
if company:
    payload["company_id"] = company
if rcid:
    payload["requester_chat_id"] = rcid
    payload["requester_channel"] = channel
sys.stdout.write(json.dumps(payload, separators=(",", ":")))
PYBODY_TASK
  then
    _escalate "could not build request body"
  fi
else
  if ! DEPARTMENT_SLUG="$DEPARTMENT_SLUG" TITLE="$TITLE" DESCRIPTION="$DESCRIPTION" \
       SOURCE="$SOURCE" PRIORITY="$PRIORITY" \
       REQUESTER_CHAT_ID="$REQUESTER_CHAT_ID" REQUESTER_CHANNEL="$REQUESTER_CHANNEL" \
       "$PYTHON" - >"$BODY_FILE" <<'PYBODY'
import json, os, sys, uuid
operation = os.environ.get('MC_ROUTE_EVENT_ID') or os.environ.get('MC_ROUTE_OPERATION_ID') or str(uuid.uuid4())
payload = {
    'idempotency_key': operation,
    'external_session_id': os.environ.get('MC_ROUTE_EXTERNAL_SESSION_ID', ''),
    "title": os.environ.get("TITLE", "")[:120],
    "description": os.environ.get("DESCRIPTION", ""),
    "department_slug": os.environ.get("DEPARTMENT_SLUG", ""),
    "source": os.environ.get("SOURCE", "telegram"),
    "priority": os.environ.get("PRIORITY", "medium"),
}
company = os.environ.get('MC_ROUTE_COMPANY_ID', '').strip()
if company:
    payload['company_id'] = company
# P1-04 trust engine: pass the originating client chat id through so the Command
# Center captures it and reports acknowledge/progress/done back to the client.
# Only added when present — an operator/internal route omits it entirely.
_rcid = os.environ.get("REQUESTER_CHAT_ID", "").strip()
if _rcid:
    payload["requester_chat_id"] = _rcid
    payload["requester_channel"] = os.environ.get("REQUESTER_CHANNEL", "telegram").strip() or "telegram"
sys.stdout.write(json.dumps(payload, separators=(",", ":")))
PYBODY
  then
    _escalate "could not build request body"
  fi
fi

# ── Sign the RAW body: HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex (openssl) ─────
# BYTE-FOR-BYTE identical to route-presentation.sh so the signature the CC server
# validates is produced the same way regardless of which helper routed the task.
SIG=""
if [ -n "$WEBHOOK_SECRET" ]; then
  if command -v openssl >/dev/null 2>&1; then
    SIG="$(openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" <"$BODY_FILE" 2>/dev/null | sed -E 's/^.*= *//' | tr -d ' \r\n')"
  fi
  if [ -z "$SIG" ]; then
    # openssl unavailable / parse miss — python3 hmac fallback over the SAME bytes.
    SIG="$(WEBHOOK_SECRET="$WEBHOOK_SECRET" "$PYTHON" - "$BODY_FILE" <<'PYSIG'
import hashlib, hmac, os, sys
sys.stdout.write(hmac.new(os.environ.get("WEBHOOK_SECRET", "").encode("utf-8"),
                          open(sys.argv[1], "rb").read(), hashlib.sha256).hexdigest())
PYSIG
)"
  fi
fi

# ── Headers: send Bearer / signature ONLY when the respective secret exists ──
_H=(-H 'Content-Type: application/json' -H 'Accept: application/json')
[ -n "$MC_API_TOKEN" ] && _H+=(-H "Authorization: Bearer $MC_API_TOKEN")
[ -n "$SIG" ]          && _H+=(-H "x-webhook-signature: $SIG")

# ── POST with retries (MAX_RETRIES retries after the first attempt) ──────────
attempt=0
http_code=""
resp_body=""
started=$SECONDS
while :; do
  remaining=$((TOTAL_TIMEOUT - (SECONDS - started)))
  [ "$remaining" -gt 0 ] || break
  deadline=$REQUEST_TIMEOUT
  [ "$deadline" -le "$remaining" ] || deadline=$remaining
  curl_rc=0
  RAW="$(curl -sS --connect-timeout "$CONNECT_TIMEOUT" --max-time "$deadline" \
    -D "$HEADER_FILE" -X POST "$INGEST_URL" "${_H[@]}" --data-binary @"$BODY_FILE" -w $'\n%{http_code}' 2>/dev/null)" || curl_rc=$?
  http_code="${RAW##*$'\n'}"
  resp_body="${RAW%$'\n'*}"
  [ "$curl_rc" -eq 0 ] && case "$http_code" in 2[0-9][0-9]) break ;; esac
  case "$curl_rc:$http_code" in
    0:408|0:429|0:500|0:502|0:503|0:504|5:*|6:*|7:*|18:*|28:*|52:*|55:*|56:*) ;;
    *) break ;;
  esac
  [ "$attempt" -lt "$MAX_RETRIES" ] || break
  attempt=$((attempt + 1))
  delay="$("$PYTHON" - "$HEADER_FILE" "$attempt" <<'PYRETRY'
import email.utils, sys, time
headers=open(sys.argv[1]).read().splitlines()
delay=min(2**(int(sys.argv[2])-1),8)
for line in headers:
    if line.lower().startswith('retry-after:'):
        value=line.split(':',1)[1].strip()
        try: delay=max(0,int(value))
        except ValueError:
            try: delay=max(0,int(email.utils.parsedate_to_datetime(value).timestamp()-time.time()))
            except Exception: pass
print(delay)
PYRETRY
)"
  remaining=$((TOTAL_TIMEOUT - (SECONDS - started)))
  [ "$delay" -lt "$remaining" ] || break
  sleep "$delay"
done

if [ "$ROUTE_MODE" != "slug" ]; then
  echo "mc-route: HTTP ${http_code:-<none>} from $INGEST_URL (mode=$ROUTE_MODE)"
else
  echo "mc-route: HTTP ${http_code:-<none>} from $INGEST_URL (department=$DEPARTMENT_SLUG)"
fi
[ -n "$resp_body" ] && printf '%s\n' "$resp_body"

[ "$curl_rc" -eq 0 ] || _escalate "transport failed (curl=$curl_rc) after bounded retry budget"

case "$http_code" in
  2[0-9][0-9])
    if [ "$ROUTE_MODE" = "task" ]; then
      _TASK_FIELDS="$(printf '%s' "$resp_body" | "$PYTHON" -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
if not isinstance(d, dict):
    d = {}
rb = str(d.get("resolved_by") or "")
dept = d.get("resolved_department")
if not dept and rb.startswith("auto-route:"):
    dept = rb[len("auto-route:"):]
    if dept == "general-task-fallback":
        dept = "general-task"
for v in (d.get("task_id"), d.get("workspace_id"), dept or d.get("workspace_id"), rb):
    print("" if v is None else str(v))' 2>/dev/null || true)"
      _TASK_ID="$(printf '%s\n' "$_TASK_FIELDS" | sed -n '1p')"
      _TASK_WORKSPACE="$(printf '%s\n' "$_TASK_FIELDS" | sed -n '2p')"
      _TASK_DEPARTMENT="$(printf '%s\n' "$_TASK_FIELDS" | sed -n '3p')"
      _TASK_RESOLVED_BY="$(printf '%s\n' "$_TASK_FIELDS" | sed -n '4p')"
      [ -n "$_TASK_ID" ] || _escalate "ingest returned HTTP $http_code but no task_id — the card was NOT confirmed"
      echo "ROUTED workspace=$_TASK_WORKSPACE department=$_TASK_DEPARTMENT resolved_by=$_TASK_RESOLVED_BY"
      case "$_TASK_WORKSPACE:$_TASK_RESOLVED_BY" in
        :*|*'->ceo'|*'->unrouted')
          echo "mc-route: WARNING — card $_TASK_ID was created but has no department lane (workspace='$_TASK_WORKSPACE', resolved_by='$_TASK_RESOLVED_BY')." >&2
          echo "ESCALATE_TO_OPERATOR: the card exists but could not be routed to a department. The CEO must tell the owner it is escalating to the operator. Do NOT call mc-route again for this job." >&2
          ;;
      esac
      exit 0
    fi
    if [ "$ROUTE_MODE" = "auto" ]; then
      # Raw-door response: {created:false,intent:...} means JEV answered without a
      # card; anything else with a 2xx is a created/auto-routed card. Never print
      # ESCALATE here — a 2xx ingest always succeeded at the transport layer.
      _AUTO_FIELDS="$(printf '%s' "$resp_body" | "$PYTHON" -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
if not isinstance(d, dict):
    d = {}
created = d.get("created")
print("false" if created is False else "true")
for key in ("intent", "workspace_id", "resolved_department", "resolved_by"):
    v = d.get(key)
    print("" if v is None else str(v))' 2>/dev/null || true)"
      _AUTO_CREATED="$(printf '%s\n' "$_AUTO_FIELDS" | sed -n '1p')"
      _AUTO_INTENT="$(printf '%s\n' "$_AUTO_FIELDS" | sed -n '2p')"
      _AUTO_WORKSPACE="$(printf '%s\n' "$_AUTO_FIELDS" | sed -n '3p')"
      _AUTO_DEPARTMENT="$(printf '%s\n' "$_AUTO_FIELDS" | sed -n '4p')"
      _AUTO_RESOLVED_BY="$(printf '%s\n' "$_AUTO_FIELDS" | sed -n '5p')"
      if [ "$_AUTO_CREATED" = "false" ]; then
        echo "JEV_ANSWER_DIRECTLY intent=${_AUTO_INTENT:-unresolved}"
      else
        echo "ROUTED workspace=$_AUTO_WORKSPACE department=$_AUTO_DEPARTMENT resolved_by=$_AUTO_RESOLVED_BY"
      fi
      exit 0
    fi
    # Workspace-mismatch guard: warn if the card did NOT land on the requested
    # department workspace (mirrors route-presentation.sh's presentations check,
    # generalized to the department_slug argument).
    WS="$(printf '%s' "$resp_body" | "$PYTHON" -c '
import json, sys
try:
    d = json.load(sys.stdin)
    sys.stdout.write(str(d.get("workspace_id", "")) if isinstance(d, dict) else "")
except Exception:
    sys.stdout.write("")' 2>/dev/null || true)"
    if [ -n "$WS" ] && [ "$WS" != "$DEPARTMENT_SLUG" ]; then
      RESOLVED_BY="$(printf '%s' "$resp_body" | "$PYTHON" -c '
import json, sys
try:
    d = json.load(sys.stdin)
    sys.stdout.write(str(d.get("resolved_by", "")) if isinstance(d, dict) else "")
except Exception:
    sys.stdout.write("")' 2>/dev/null || true)"
      # Landing on the General Task catch-all is not a blocker: never warn/escalate
      # when the mismatch IS the documented catch-all fallback.
      _GENERAL_TASK_LANDING=0
      case "$RESOLVED_BY" in
        unrecognized-slug-\>general|general-task-fallback|auto-route:general-task-fallback)
          _GENERAL_TASK_LANDING=1
          ;;
      esac
      case "$WS" in
        general-task|dept-general-task) _GENERAL_TASK_LANDING=1 ;;
      esac
      if [ "$_GENERAL_TASK_LANDING" -eq 1 ]; then
        echo "mc-route: INFO — landed on General Task (catch-all); not a blocker."
      else
        echo "mc-route: WARNING — task landed on workspace '$WS', NOT '$DEPARTMENT_SLUG'." >&2
        echo "ESCALATE_TO_OPERATOR: the '$DEPARTMENT_SLUG' department may be absent on this box. The CEO must tell the owner it is escalating to the operator instead of proceeding or self-intaking." >&2
      fi
    fi
    exit 0
    ;;
  403)
    if [ "$ROUTE_MODE" = "auto" ]; then
      _AUTO_ERROR="$(printf '%s' "$resp_body" | "$PYTHON" -c '
import json, sys
try:
    d = json.load(sys.stdin)
    sys.stdout.write(str(d.get("error", "")) if isinstance(d, dict) else "")
except Exception:
    sys.stdout.write("")' 2>/dev/null || true)"
      if [ "$_AUTO_ERROR" = "control_probe_never_creates" ]; then
        echo "JEV_ANSWER_DIRECTLY intent=unresolved"
        exit 0
      fi
    fi
    _escalate "ingest POST returned HTTP ${http_code:-<none>} after ${attempt} retr(y|ies)"
    ;;
  *)
    _escalate "ingest POST returned HTTP ${http_code:-<none>} after ${attempt} retr(y|ies)"
    ;;
esac
