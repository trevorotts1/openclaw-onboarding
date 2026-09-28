#!/usr/bin/env bash
# =============================================================================
# scripts/rr-escalate.sh -- THE ONE SENDER for Rescue Rangers escalations.
# Delivered to ~/.openclaw/scripts/ (VPS: /data/.openclaw/scripts/) by
# install.sh and update-skills.sh.
#
# WHY THIS EXISTS. Agents used to hand-build a curl POST from AGENTS.md prose.
# When the section was missing, or the curl was wrong, an agent asked to "send
# this to Rescue Rangers" emailed it instead and told the client it was sent.
# Email creates no ticket. Maintenance scripts had the same defect in another
# shape: they POSTed {action, client, agent, message} with NO box field (the
# intake answers 400 "unresolvable box") and treated any answer as success.
#
# WHAT IT DOES. Resolves the box identity itself (box slug, client, agent,
# box type, OpenClaw version), POSTs the nine-field payload to the RR-01 intake
# with the X-Rescue-Secret header, and prints the ticket id. It exits NON-ZERO
# whenever no ticket was minted, so a caller can never mistake a refusal for a
# delivery.
#
# RESOLUTION ORDER for every setting: process env, then openclaw.json
# env.vars, then the secrets env file. The secrets file is PARSED, never
# executed. The secret value is never printed, never placed on a command line
# (curl reads the header from stdin), and never logged.
#
# USAGE
#   rr-escalate.sh --problem "..." [--tried "..."] [--person "..."]
#                  [--return-to "<chat id>"] [--agent NAME] [--client NAME]
#                  [--class CLASS]
#   rr-escalate.sh --resolve <incident_id> --problem "RESOLVED: ..." [--attempt ID]
#   rr-escalate.sh --selftest      # channel check; the intake suppresses it
#
# OUTPUT (stdout, one key=value per line): status=..., ticket=..., incident_id=...
#
# EXIT CODES
#   0  escalation accepted WITH a ticket id / resolution accepted /
#      selftest answered test_suppressed
#   2  usage error
#   3  local configuration missing (URL, secret, box slug, curl, python3)
#   4  intake refused (non-2xx, accepted:false) or accepted without a ticket
#   5  transport failure (curl could not complete the request)
# =============================================================================
set -uo pipefail

_die() { printf 'rr-escalate: %s\n' "$2" >&2; exit "$1"; }

PROBLEM=""; TRIED=""; PERSON=""; RETURN_TO=""; AGENT=""; CLIENT=""; CLASS=""
RESOLVE=""; ATTEMPT=""; MODE="escalate"
while [ $# -gt 0 ]; do
  case "$1" in
    --problem)   [ $# -ge 2 ] || _die 2 "--problem needs a value"; PROBLEM="$2"; shift 2 ;;
    --tried)     [ $# -ge 2 ] || _die 2 "--tried needs a value"; TRIED="$2"; shift 2 ;;
    --person)    [ $# -ge 2 ] || _die 2 "--person needs a value"; PERSON="$2"; shift 2 ;;
    --return-to) [ $# -ge 2 ] || _die 2 "--return-to needs a value"; RETURN_TO="$2"; shift 2 ;;
    --agent)     [ $# -ge 2 ] || _die 2 "--agent needs a value"; AGENT="$2"; shift 2 ;;
    --client)    [ $# -ge 2 ] || _die 2 "--client needs a value"; CLIENT="$2"; shift 2 ;;
    --class)     [ $# -ge 2 ] || _die 2 "--class needs a value"; CLASS="$2"; shift 2 ;;
    --resolve)   [ $# -ge 2 ] || _die 2 "--resolve needs the incident_id"; RESOLVE="$2"; MODE="resolve"; shift 2 ;;
    --attempt)   [ $# -ge 2 ] || _die 2 "--attempt needs a value"; ATTEMPT="$2"; shift 2 ;;
    --selftest|--self-test) MODE="selftest"; shift ;;
    -h|--help)   sed -n '2,42p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) _die 2 "unknown argument: $1 (see --help)" ;;
  esac
done

if [ "$MODE" = "selftest" ]; then
  PROBLEM="__AUTHTEST__ rr-escalate.sh channel self-check (no ticket expected)"
fi
[ -n "$PROBLEM" ] || _die 2 "--problem is required (what is broken, in plain words)"

command -v python3 >/dev/null 2>&1 || _die 3 "python3 not found on PATH"
command -v curl >/dev/null 2>&1 || _die 3 "curl not found on PATH"

# OpenClaw root: the same /data-else-HOME detection every fleet script uses.
if [ -z "${OC_ROOT:-}" ]; then
  if [ -f /data/.openclaw/openclaw.json ]; then OC_ROOT=/data/.openclaw; else OC_ROOT="$HOME/.openclaw"; fi
fi

OC_VERSION=""
if command -v openclaw >/dev/null 2>&1; then
  OC_VERSION="$(openclaw --version 2>/dev/null | head -1 | tr -d '"')" || OC_VERSION=""
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/rr-escalate.XXXXXX")" || _die 3 "cannot create a temp dir"
chmod 700 "$WORK" 2>/dev/null || true
trap 'rm -rf "$WORK"' EXIT

# ---- build the payload + resolve config (writes three files into $WORK) ------
RR_MODE="$MODE" RR_PROBLEM="$PROBLEM" RR_TRIED="$TRIED" RR_PERSON="$PERSON" \
RR_RETURN_TO="$RETURN_TO" RR_AGENT="$AGENT" RR_CLIENT="$CLIENT" RR_CLASS="$CLASS" \
RR_RESOLVE="$RESOLVE" RR_ATTEMPT="$ATTEMPT" RR_OC_VERSION="$OC_VERSION" \
RR_OC_ROOT="$OC_ROOT" RR_WORK="$WORK" python3 - <<'PY'
import hashlib, json, os, platform, sys, time

E = os.environ
root = E["RR_OC_ROOT"]
work = E["RR_WORK"]

def unquote(v):
    v = (v or "").strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1]
    return v.strip()

cfg = {}
try:
    with open(os.path.join(root, "openclaw.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
except Exception:
    cfg = {}
cfg_vars = ((cfg.get("env") or {}).get("vars") or {}) if isinstance(cfg, dict) else {}

secrets = {}
try:
    with open(os.path.join(root, "secrets", ".env"), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            k, v = line.split("=", 1)
            secrets[k.strip()] = unquote(v)
except Exception:
    pass

def get(name):
    for src in (E, cfg_vars, secrets):
        v = unquote(str(src.get(name) or ""))
        if v:
            return v
    return ""

url = get("RESCUE_RANGERS_WEBHOOK_URL")
secret = get("RESCUE_RANGERS_WEBHOOK_SECRET")
box = get("FLEET_STANDING_BOX_SLUG")

missing = [n for n, v in (("RESCUE_RANGERS_WEBHOOK_URL", url),
                          ("RESCUE_RANGERS_WEBHOOK_SECRET", secret),
                          ("FLEET_STANDING_BOX_SLUG", box)) if not v]
if missing:
    sys.stderr.write("rr-escalate: NOT SENT -- missing %s (checked: process env, %s env.vars, %s)\n"
                     % (", ".join(missing), os.path.join(root, "openclaw.json"),
                        os.path.join(root, "secrets", ".env")))
    sys.exit(3)

def default_agent():
    agents = ((cfg.get("agents") or {}).get("list") or []) if isinstance(cfg, dict) else []
    agents = [a for a in agents if isinstance(a, dict)]
    pick = next((a for a in agents if a.get("default") or a.get("isDefault")), None)
    pick = pick or (agents[0] if agents else {})
    return str(pick.get("name") or pick.get("id") or "main")

if root == "/data/.openclaw":
    box_type = "VPS"
elif os.path.exists("/.dockerenv"):
    box_type = "Docker"
elif platform.system() == "Darwin":
    box_type = "Mac Mini"
else:
    box_type = "Linux"

mode = E["RR_MODE"]
problem = E["RR_PROBLEM"]
client = E["RR_CLIENT"] or get("OPENCLAW_COMPANY_NAME") or get("OPENCLAW_COMPANY_SLUG") or box
agent = E["RR_AGENT"] or default_agent()

if mode == "resolve":
    incident = E["RR_RESOLVE"]
    payload = {
        "action": "escalate",
        "clientName": client,
        "agentName": agent,
        "boxName": box,
        "runtime_id": box,
        "incident_id": incident,
        "operation_id": "res-%s-%s" % (incident, time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())),
        "attempt_id": E["RR_ATTEMPT"],
        "result_digest": "sha256-" + hashlib.sha256(problem.encode("utf-8")).hexdigest(),
        "problem": problem,
        "message": problem,
    }
else:
    payload = {
        "action": "escalate",
        "person": E["RR_PERSON"] or get("OPENCLAW_OWNER_NAME"),
        "clientName": client,
        "agentName": agent,
        "boxName": box,
        "boxType": box_type,
        "openclawVersion": E["RR_OC_VERSION"] or "unknown",
        "problem": problem,
        "alreadyTried": E["RR_TRIED"],
        "returnTo": E["RR_RETURN_TO"],
        "message": problem,
        "source": "rr-escalate.sh",
    }
    if E["RR_CLASS"]:
        payload["class"] = E["RR_CLASS"]

with open(os.path.join(work, "payload.json"), "w", encoding="utf-8") as fh:
    json.dump(payload, fh)
with open(os.path.join(work, "url"), "w", encoding="utf-8") as fh:
    fh.write(url)
# curl config for the header: keeps the secret off every command line.
esc = secret.replace("\\", "\\\\").replace('"', '\\"')
fd = os.open(os.path.join(work, "curl.cfg"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    fh.write('header = "X-Rescue-Secret: %s"\n' % esc)
PY
_rc=$?
[ "$_rc" -eq 0 ] || exit "$_rc"

# ---- POST -------------------------------------------------------------------
_url="$(cat "$WORK/url")"
_raw="$(curl -sS -X POST "$_url" \
          --max-time "${RR_ESCALATE_TIMEOUT:-60}" \
          -H 'Content-Type: application/json' \
          --config - \
          --data-binary "@$WORK/payload.json" \
          -w '\n%{http_code}' < "$WORK/curl.cfg" 2>"$WORK/curl.err")"
_curl_rc=$?
if [ "$_curl_rc" -ne 0 ]; then
  printf 'rr-escalate: NOT SENT -- transport failure (curl rc=%s): %s\n' \
    "$_curl_rc" "$(tr '\n' ' ' < "$WORK/curl.err" | cut -c1-300)" >&2
  exit 5
fi

# ---- verdict ----------------------------------------------------------------
printf '%s' "$_raw" > "$WORK/response"
RR_MODE="$MODE" RR_WORK="$WORK" python3 - <<'PY'
import json, os, sys

work = os.environ["RR_WORK"]
mode = os.environ["RR_MODE"]
raw = open(os.path.join(work, "response"), encoding="utf-8", errors="replace").read()
body, _, code = raw.rpartition("\n")
code = code.strip()
try:
    doc = json.loads(body) if body.strip() else {}
except ValueError:
    doc = None

def out(msg):
    sys.stdout.write(msg + "\n")

def refuse(reason):
    sys.stderr.write("rr-escalate: REJECTED -- http=%s %s\n" % (code or "?", reason))
    sys.exit(4)

if not isinstance(doc, dict):
    refuse("unparseable intake answer: %s" % " ".join(body.split())[:200])
status = str(doc.get("status") or "")
reason = str(doc.get("reason") or doc.get("error") or "")
ticket = doc.get("ticketId") or doc.get("ticket_id") or doc.get("incident_id")
if not code.startswith("2"):
    refuse("status=%s reason=%s" % (status or "-", reason or "-"))
if doc.get("accepted") is False:
    refuse("accepted=false status=%s reason=%s" % (status or "-", reason or "-"))

out("status=%s" % (status or "accepted"))
if mode == "selftest":
    if status == "test_suppressed":
        out("selftest=ok (URL, secret and box accepted; no ticket created)")
        sys.exit(0)
    refuse("selftest expected status=test_suppressed, got status=%s" % (status or "-"))
if mode == "resolve":
    sys.exit(0)
if not ticket:
    refuse("intake answered without a ticket id (status=%s) -- NOT a delivered escalation"
           % (status or "-"))
out("ticket=%s" % ticket)
out("incident_id=%s" % ticket)
PY
