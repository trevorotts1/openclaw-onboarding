#!/usr/bin/env bash
# =============================================================================
# podbean-publish-provision-roll.sh  (S58-U18 fleet provisioning roll)
# =============================================================================
# WHAT: ONE batched, idempotent, reversible provisioning roll that injects the
# S58-U15 Podbean server-side publish values onto every podcast-enabled box:
#
#   PODBEAN_PUBLISH_WEBHOOK_URL   (non-secret; fixed fleet constant below)
#   PODBEAN_PUBLISH_TOKEN         (secret; the shared X-Podcast-Publish-Token,
#                                  read from the OPERATOR's own secrets store
#                                  at apply time, never from the repo)
#   PODCAST_CLIENT_LAST_NAME      (per-box identity tuple, from the roster)
#   PODCAST_CLIENT_EMAIL          (per-box identity tuple, from the roster)
#   PODCAST_CLIENT_FIRST_NAME     (optional; display/email text only)
#   PODBEAN_PODCAST_ID            (required per-box Podbean Channel ID)
#
# and then VALIDATES per box, per the S58 spec U18 accept clause:
#   1. every value SET by name (secrets/.env AND openclaw.json env.vars), and
#   2. `podbean_publish.sh --dry-run` in proxy mode exits 0 — that dry-run
#      probes the U13 standing-check endpoint only; IT PUBLISHES NOTHING.
#
# WHY: S58-U14 made the publish-proxy the fleet-default transport and U4 put
# header auth on the live webhook. A box without these values falls back to
# broker/local mode (or gets a 401), so the proxy cutover is only real once
# the fleet holds them. This script is the batch vehicle — standing fleet
# doctrine is ONE batched roll, never per-fix drip provisioning.
#
# HARD SAFETY PROPERTIES
#   * --dry-run is the DEFAULT and is strictly read-only on every box.
#   * OPERATOR BOX FIRST, STRUCTURALLY: in --apply mode, boxes with
#     role="client" are SKIPPED unless --include-clients is passed, and even
#     then every client box is REFUSED unless a role="operator" box PASSED
#     earlier in the same run. A client box can never be provisioned by a run
#     that has not just proven the operator box.
#   * IDEMPOTENT: a value already exactly set is a byte-identical no-op (the
#     same exact-line check install.sh's _shared_write_env uses). Re-running
#     converges; it never duplicates or reorders lines.
#   * REVERSIBLE: before any write on a box, that box's secrets/.env,
#     openclaw.json, and (on VPS) host compose .env are copied once into unique
#     timestamped backups. Exact no-ops create no backup. A failed required
#     backup aborts before the first mutation.
#   * ZERO SECRET VALUES IN OUTPUT: box reports carry variable NAMES and
#     SET/NOT-SET/WRITTEN/ALREADY labels plus exit codes only. Secret values
#     exist only inside a 0600 temp payload file (deleted on exit) and the
#     box's own stores.
#   * PER-BOX ISOLATION: one box failing never aborts the batch.
#   * IDENTITY FAIL-CLOSED: a manifest entry whose roster identity is
#     incomplete (no last name, email, or Podbean Channel ID) is BLOCKED, never
#     half-written.
#
# MANIFEST (--boxes-file; OPERATOR-PRIVATE — never committed to any repo):
#   JSON array, built by
#   scripts/fleet-roll/podbean-publish-provision-manifest.py, which joins the
#   operator-private fleet box list with the n8n podcast roster at runtime.
#   [
#     {"name":"operator-mac","role":"operator","platform":"mac",
#      "ssh_target":"local",
#      "identity":{"last_name":"...","email":"...","first_name":"...",
#                  "podcast_id":"...","complete":true}},
#     {"name":"openclaw-xxxx","role":"client","platform":"vps",
#      "ssh_target":"root@<ip>",
#      "container":"openclaw-xxxx-openclaw-1","compose_dir":"/root/openclaw",
#      "identity":{"last_name":"...","email":"...","first_name":"",
#                  "podcast_id":"","complete":true}}
#   ]
#   ssh_target "local" runs against THIS box (used for the operator box).
#   An optional per-entry "home" overrides the box home root (sandbox/test
#   use only; production entries omit it and get $HOME).
#
# TRANSPORT (platform-aware; the VPS gap was a QC finding):
#   mac  : payload over `ssh 'sh -s'`, writes $HOME/.openclaw directly.
#   vps  : plain ssh would write the HOST home — NOT the gateway's store, which
#          lives at /data/.openclaw INSIDE the Docker container. The payload
#          instead rides base64 inside a host wrapper that (1) runs it in the
#          container via `docker exec -i -u node`, (2) mirrors the values into
#          the host compose env_file, and (3) on change runs
#          `docker compose up -d --force-recreate` (compose only reads the
#          env_file at create; a bare restart keeps the old env). Roll in
#          place, force-recreate, NEVER re-init credentials — same pattern the
#          production-proven rescue-webhook propagation uses.
#          Manifest: "compose_dir" is REQUIRED for a vps --apply; "container"
#          defaults to "<name>-openclaw-1".
#
# RESTART (deliberate, verified decision — not an accident of omission):
#   openclaw.json env.vars reach the gateway runtime ONLY at gateway start, the
#   gateway never reads secrets/.env, and podbean_publish.sh resolves the proxy
#   pair from PROCESS env — so a freshly provisioned box would keep silently
#   falling back to broker mode until its next restart. Therefore: when (and
#   only when) a box actually CHANGED, mac boxes get a gateway restart
#   (launchctl kickstart, stop fallback on rc 125/126, then PID-change + health
#   proof) and vps boxes get the force-recreate above. OK_ALREADY boxes are
#   NEVER restarted, so idempotent re-runs disturb nothing. --no-restart skips
#   both (box grades PARTIAL, not OK — a changed-but-not-restarted box is not a
#   proven box).
#
# USAGE:
#   bash scripts/fleet-roll/podbean-publish-provision-roll.sh \
#        --boxes-file <manifest>                      # DRY-RUN (default)
#   bash scripts/fleet-roll/podbean-publish-provision-roll.sh \
#        --boxes-file <manifest> --apply --local --box operator-mac
#   bash scripts/fleet-roll/podbean-publish-provision-roll.sh \
#        --boxes-file <manifest> --apply --include-clients   # operator-gated
#
# FLAGS:
#   --dry-run            read-only survey (DEFAULT)
#   --apply              provision (writes on boxes)
#   --local              force selected boxes to run against THIS box, no SSH
#   --box <name>         restrict to one manifest entry (repeatable)
#   --boxes-file <f>     manifest path (default: $P18_MANIFEST or
#                        ~/.openclaw/secrets/s58-u18-provision-manifest.json)
#   --include-clients    allow role="client" boxes in --apply (still requires
#                        an operator box to pass earlier in the same run)
#   --no-standing-probe  skip the podbean_publish.sh --dry-run validation leg
#   --no-restart         skip the changed-box gateway restart / force-recreate
#                        (changed boxes then grade PARTIAL, never OK)
#   --log-file <f>       per-box ledger log (default: $P18_LOG_FILE or
#                        ~/.openclaw/logs/s58-u18-provision-roll.log)
#
# EXIT CODES: 0 = everything attempted passed (skips are neutral)
#             1 = fatal (bad flags, unreadable manifest, token not resolvable
#                 locally in --apply, python3 missing)
#             2 = at least one box failed / refused / blocked / only partially
#                 proven (apply), or errored/unreachable (dry-run)
#
# ENV (sandbox/test only): P18_HOME (box home root for local runs),
#   P18_MANIFEST, P18_LOG_FILE.
#
# Portable: bash 3.2 safe. The per-box payload is POSIX sh (dash-safe), the
# SAME generated script for local and ssh transport.
# =============================================================================
set -u

SCRIPT_NAME="$(basename "$0")"

# ---- fleet constants (non-secret; the URL is already documented in install.sh)
PUBLISH_URL="https://main.blackceoautomations.com/webhook/podbean-publish"

# ---- defaults ----------------------------------------------------------------
APPLY=0
LOCAL=0
INCLUDE_CLIENTS=0
STANDING_PROBE=1
NO_RESTART=0
BOXES_FILE="${P18_MANIFEST:-$HOME/.openclaw/secrets/s58-u18-provision-manifest.json}"
LOG_FILE="${P18_LOG_FILE:-$HOME/.openclaw/logs/s58-u18-provision-roll.log}"
BOX_FILTERS=""

err() { printf '%s\n' "$SCRIPT_NAME: $*" >&2; }
die() { err "$*"; exit 1; }
usage() { sed -n '2,/^set -u/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0; }
shquote() { python3 -c 'import shlex,sys; print(shlex.quote(sys.argv[1]))' "$1"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)           APPLY=0; shift ;;
    --apply)             APPLY=1; shift ;;
    --local)             LOCAL=1; shift ;;
    --include-clients)   INCLUDE_CLIENTS=1; shift ;;
    --no-standing-probe) STANDING_PROBE=0; shift ;;
    --no-restart)        NO_RESTART=1; shift ;;
    --box)               BOX_FILTERS="$BOX_FILTERS $2"; shift 2 ;;
    --boxes-file)        BOXES_FILE="$2"; shift 2 ;;
    --log-file)          LOG_FILE="$2"; shift 2 ;;
    --help|-h)           usage ;;
    *) die "unknown flag: $1 (see --help)" ;;
  esac
done

command -v python3 >/dev/null 2>&1 || die "python3 is required (manifest parse + openclaw.json merge)"
[ -f "$BOXES_FILE" ] || die "manifest not found: $BOXES_FILE (build it with scripts/fleet-roll/podbean-publish-provision-manifest.py)"

# ---- resolve the shared publish token from the OPERATOR's own secrets store --
# Apply mode needs the value; dry-run only reports whether the operator's
# local store could supply it (SET/NOT-SET). Read by NAME into a variable;
# never printed.
OP_SECENV="${P18_HOME:-$HOME}/.openclaw/secrets/.env"
read_secret_by_name() { sed -n "s/^$1=//p" "$2" 2>/dev/null | head -n 1; }
PUBLISH_TOKEN=""
if [ -f "$OP_SECENV" ]; then
  PUBLISH_TOKEN="$(read_secret_by_name PODBEAN_PUBLISH_TOKEN "$OP_SECENV")"
  [ -n "$PUBLISH_TOKEN" ] || PUBLISH_TOKEN="$(read_secret_by_name OPENCLAW_PODBEAN_PUBLISH_TOKEN "$OP_SECENV")"
fi
if [ "$APPLY" = "1" ] && [ -z "$PUBLISH_TOKEN" ]; then
  die "PODBEAN_PUBLISH_TOKEN is NOT SET in the operator's local secrets store ($OP_SECENV) — cannot provision. Set it there first (U15 names it OPENCLAW_PODBEAN_PUBLISH_TOKEN at install time)."
fi
TOKEN_LOCAL_STATE="NOT-SET"; [ -n "$PUBLISH_TOKEN" ] && TOKEN_LOCAL_STATE="SET"

# ---- parse the manifest into pipe-delimited box lines -------------------------
# Fields: name | role | platform | ssh_target | home | container | compose_dir |
#         complete | last_name | email | first_name | podcast_id
# PIPE, NOT TAB: tab is IFS whitespace, so `read` COLLAPSES consecutive tabs and
# an empty optional field (home, first_name, podcast_id) silently shifts every
# following column. A non-whitespace delimiter preserves empty fields exactly.
# Identity values ride in shell variables only — never echoed by this script.
MANIFEST_TSV="$(python3 - "$BOXES_FILE" <<'PYEOF'
import json, sys

def clean(v):
    return str(v if v is not None else "").replace("\t", " ").replace("\n", " ").replace("|", " ")

try:
    rows = json.load(open(sys.argv[1]))
except Exception as e:
    sys.stderr.write("manifest parse error: %s\n" % e)
    sys.exit(1)
if not isinstance(rows, list) or not rows:
    sys.stderr.write("manifest must be a non-empty JSON array\n")
    sys.exit(1)
out = []
for r in rows:
    ident = r.get("identity") or {}
    out.append("|".join([
        clean(r.get("name", "")),
        clean(r.get("role", "client")),
        clean(r.get("platform", "")),
        clean(r.get("ssh_target", "")),
        clean(r.get("home", "")),
        clean(r.get("container", "")),
        clean(r.get("compose_dir", "")),
        "1" if ident.get("complete") else "0",
        clean(ident.get("last_name", "")),
        clean(ident.get("email", "")),
        clean(ident.get("first_name", "")),
        clean(ident.get("podcast_id", "")),
    ]))
print("\n".join(out))
PYEOF
)" || die "could not parse manifest $BOXES_FILE"

# Order: operator role first (stable), then clients.
ORDERED_TSV="$(printf '%s\n' "$MANIFEST_TSV" | awk -F'|' '{ if ($2=="operator") print "0\t"$0; else print "1\t"$0 }' | sort -s -k1,1 | cut -f2-)"

# ---- emit the per-box payload script (POSIX sh; same for local and ssh) -------
# The inject-mode values are embedded by build_payload via a generated
# assignment header (python shlex.quote) — they appear ONLY inside the 0600
# temp payload file, never in argv, never on stdout.
emit_box_script() {
  cat <<'PAYLOAD_EOF'
#!/bin/sh
# S58-U18 per-box payload. Modes: probe (read-only) | inject (provision+prove)
# | hostenv (VPS host leg: mirror values into the docker compose env_file).
# Contract: print ONLY labels, variable NAMES, SET/NOT-SET/WRITTEN/ALREADY and
# exit codes. NEVER print a value.
umask 077
BOX_HOME="${P18_HOME:-$HOME}"
SECENV="$BOX_HOME/.openclaw/secrets/.env"
OCJSON="$BOX_HOME/.openclaw/openclaw.json"
SKILL="$BOX_HOME/.openclaw/skills/58-podcast-production-engine/scripts/podbean_publish.sh"
REQUIRED_NAMES="PODBEAN_PUBLISH_WEBHOOK_URL PODBEAN_PUBLISH_TOKEN PODCAST_CLIENT_LAST_NAME PODCAST_CLIENT_EMAIL PODBEAN_PODCAST_ID"
OPTIONAL_NAMES="PODCAST_CLIENT_FIRST_NAME"
NAMES="$REQUIRED_NAMES $OPTIONAL_NAMES"
CHANGED=0

secenv_state() { # name -> SET|NOT-SET
  _sv="$(sed -n "s/^$1=//p" "$SECENV" 2>/dev/null | head -n 1)"
  [ -n "$_sv" ] && { echo SET; return; }
  echo NOT-SET
}
ocjson_state() { # name -> SET|NOT-SET|NOFILE|UNREADABLE|NOTOOL
  # python3 preferred; jq fallback for Docker containers whose node image may
  # not ship python3 (the rescue-webhook propagation used jq in-container).
  # Neither tool -> NOTOOL, which validation treats as not-proven (fail-closed).
  [ -f "$OCJSON" ] || { echo NOFILE; return; }
  if command -v python3 >/dev/null 2>&1; then
    OCJSON="$OCJSON" V="$1" python3 - <<'PY' 2>/dev/null || { echo UNREADABLE; return; }
import json, os
try:
    d = json.load(open(os.environ["OCJSON"]))
except Exception:
    d = {}
value = ((d.get("env", {}) or {}).get("vars", {}) or {}).get(os.environ["V"], "")
print("SET" if str(value) else "NOT-SET")
PY
  elif command -v jq >/dev/null 2>&1; then
    _jv="$(jq -r --arg k "$1" '.env.vars[$k] // empty' "$OCJSON" 2>/dev/null)" || { echo UNREADABLE; return; }
    if [ -n "$_jv" ]; then echo SET; else echo NOT-SET; fi
  else
    echo NOTOOL
  fi
}

secenv_value_matches() { # name expected -> exact, non-printing comparison
  [ -f "$SECENV" ] && grep -qxF "$1=$2" "$SECENV" 2>/dev/null
}

ocjson_value_matches() { # name expected -> exact, non-printing comparison
  [ -f "$OCJSON" ] || return 1
  if command -v python3 >/dev/null 2>&1; then
    OCJSON="$OCJSON" V="$1" EXPECTED="$2" python3 - <<'PY' >/dev/null 2>&1
import json, os, sys
try:
    data = json.load(open(os.environ["OCJSON"]))
except Exception:
    raise SystemExit(1)
actual = ((data.get("env", {}) or {}).get("vars", {}) or {}).get(os.environ["V"])
raise SystemExit(0 if actual == os.environ["EXPECTED"] else 1)
PY
  elif command -v jq >/dev/null 2>&1; then
    jq -e --arg k "$1" --arg v "$2" '.env.vars[$k] == $v' "$OCJSON" >/dev/null 2>&1
  else
    return 1
  fi
}

pair_needs_write() { # name expected -> 0 when either durable store differs
  secenv_value_matches "$1" "$2" && ocjson_value_matches "$1" "$2" && return 1
  return 0
}

write_env() { # name value -> prints label only; install.sh exact-line no-op, but the
  # replace+append is built ENTIRELY in a tmp file and lands in ONE mv (atomic).
  # install.sh's original appends to the live file after the mv, which can lose
  # the var on a mid-write failure and can duplicate it on a grep error.
  [ -f "$SECENV" ] || { : > "$SECENV" || return 1; chmod 600 "$SECENV" 2>/dev/null || :; }
  if grep -qxF "$1=$2" "$SECENV" 2>/dev/null; then echo "env:$1=ALREADY"; return 0; fi
  _rc=0
  grep -v "^$1=" "$SECENV" > "$SECENV.tmp.s58u18" 2>/dev/null || _rc=$?
  if [ "$_rc" -ge 2 ]; then
    # grep errored: fail CLOSED — never append beside an unremoved old line.
    rm -f "$SECENV.tmp.s58u18"
    return 1
  fi
  printf '%s=%s\n' "$1" "$2" >> "$SECENV.tmp.s58u18" || { rm -f "$SECENV.tmp.s58u18"; return 1; }
  chmod 600 "$SECENV.tmp.s58u18" 2>/dev/null || :
  mv "$SECENV.tmp.s58u18" "$SECENV" || { rm -f "$SECENV.tmp.s58u18"; return 1; }
  echo "env:$1=WRITTEN"
  CHANGED=1
  return 0
}

write_ocjson() { # name value -> prints label only. Differences from install.sh's
  # _shared_write_ocjson, on purpose (QC findings on a live-fleet tool):
  #   * ATOMIC: serialize to a tmp file, os.replace() over the original — a
  #     crash mid-write can never leave a truncated gateway config.
  #   * FAIL-CLOSED on unparseable json: install.sh's `d = {}` fallback would
  #     REBUILD openclaw.json as a minimal stub, destroying the box's config.
  #   * FAIL-CLOSED on a missing file: a live box without openclaw.json is
  #     broken; provisioning half a box and reporting OK would be a false-done.
  [ -f "$OCJSON" ] || { echo "ocjson:$1=NOFILE"; return 1; }
  if command -v python3 >/dev/null 2>&1; then
    _label="$(OCJSON="$OCJSON" VAR="$1" VAL="$2" python3 - <<'PY' 2>/dev/null
import json, os
p, v, val = os.environ["OCJSON"], os.environ["VAR"], os.environ["VAL"]
try:
    d = json.load(open(p))
except Exception:
    print("UNPARSEABLE")
    raise SystemExit(0)
vars_ = d.setdefault("env", {}).setdefault("vars", {})
if vars_.get(v) == val:
    print("ALREADY")  # exact -> byte-identical no-op (idempotent)
else:
    vars_[v] = val
    tmp = p + ".tmp.s58u18"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, p)
    print("WRITTEN")
PY
)"
  elif command -v jq >/dev/null 2>&1; then
    # container fallback; jq errors on unparseable json -> empty tmp -> ERROR
    _cur="$(jq -r --arg k "$1" '.env.vars[$k] // empty' "$OCJSON" 2>/dev/null)"
    if [ "$_cur" = "$2" ]; then
      _label="ALREADY"
    elif jq --arg k "$1" --arg v "$2" \
        '.env = (.env // {}) | .env.vars = (.env.vars // {}) | .env.vars[$k] = $v' \
        "$OCJSON" > "$OCJSON.tmp.s58u18" 2>/dev/null && [ -s "$OCJSON.tmp.s58u18" ]; then
      mv "$OCJSON.tmp.s58u18" "$OCJSON" && _label="WRITTEN" || _label="ERROR"
    else
      rm -f "$OCJSON.tmp.s58u18"
      _label="ERROR"
    fi
  else
    _label="NOTOOL"
  fi
  [ -n "$_label" ] || _label="ERROR"
  [ "$_label" = "WRITTEN" ] && CHANGED=1
  echo "ocjson:$1=$_label"
  case "$_label" in WRITTEN|ALREADY) return 0 ;; *) return 1 ;; esac
}

# VPS post-recreate proof. Expected values are embedded in this stdin payload,
# never argv or output. Prove the NEW container inherited every required value
# and that its gateway returns ok:true before the wrapper can report success.
if [ "${P18_MODE:-probe}" = "runtimeverify" ]; then
  _runtime_ok=1
  [ "${PODBEAN_PUBLISH_WEBHOOK_URL:-}" = "$S58V_URL" ] || _runtime_ok=0
  [ "${PODBEAN_PUBLISH_TOKEN:-}" = "$S58V_TOKEN" ] || _runtime_ok=0
  [ "${PODCAST_CLIENT_LAST_NAME:-}" = "$S58V_LAST" ] || _runtime_ok=0
  [ "${PODCAST_CLIENT_EMAIL:-}" = "$S58V_EMAIL" ] || _runtime_ok=0
  [ "${PODBEAN_PODCAST_ID:-}" = "$S58V_PODCAST_ID" ] || _runtime_ok=0
  if [ -n "${S58V_FIRST:-}" ]; then
    [ "${PODCAST_CLIENT_FIRST_NAME:-}" = "$S58V_FIRST" ] || _runtime_ok=0
  fi
  echo "runtime_values=$_runtime_ok"
  [ "$_runtime_ok" = "1" ] || exit 1

  _health_ok=0
  _h=0
  while [ "$_h" -lt 12 ]; do
    _health="$(curl -s -m 5 http://127.0.0.1:18789/health 2>/dev/null || true)"
    if printf '%s\n' "$_health" | grep -Eq '"ok"[[:space:]]*:[[:space:]]*true'; then
      _health_ok=1
      break
    fi
    sleep 5
    _h=$((_h + 1))
  done
  echo "health_ok=$_health_ok"
  [ "$_health_ok" = "1" ] || exit 1
  exit 0
fi

if [ "${P18_MODE:-probe}" = "probe" ]; then
  echo "box_home_present=$([ -d "$BOX_HOME/.openclaw" ] && echo yes || echo no)"
  if [ -f "$SKILL" ]; then
    # NOTE: no `|| echo 0` — grep -c prints "0" itself on no-match (rc 1), and
    # `$(grep -c ... || echo 0)` would capture "0<newline>0", corrupting the report.
    _n=$(grep -c "PODBEAN_PUBLISH_WEBHOOK_URL" "$SKILL" 2>/dev/null)
    [ -n "$_n" ] || _n=0
    echo "skill_script=present proxy_mode_markers=$_n"
  else
    echo "skill_script=missing proxy_mode_markers=0"
  fi
  for v in $NAMES; do
    echo "probe:$v:env=$(secenv_state "$v"):ocjson=$(ocjson_state "$v")"
  done
  exit 0
fi

# ---- hostenv modes (VPS host leg) --------------------------------------------
# Mirrors the six values into the docker compose env_file on the HOST, so the
# container process env carries them from the next force-recreate onward
# (compose reads the env_file only at container create). Same exact-line
# idempotency and atomic tmp+mv as write_env. Values that are not dotenv-safe
# verbatim (spaces, quotes, '#') are double-quoted with escapes — dotenv-style.
# The wrapper runs hostenvbackup BEFORE the container leg so a failed host
# snapshot cannot leave even the container store half-mutated.
if [ "$P18_MODE" = "hostenvbackup" ]; then
  HF="${P18_HOSTENV_FILE:-}"
  [ -n "$HF" ] || { echo "result=FAILED reason=hostenv_file_unset"; exit 1; }
  [ -f "$HF" ] || { echo "result=FAILED reason=hostenv_file_missing"; exit 1; }
  hostenv_desired_line() { # name value -> dotenv-compatible line (captured only)
    case "$2" in
      ''|*[!A-Za-z0-9_@.:/+-]*)
        _q=$(printf '%s' "$2" | sed 's/\\/\\\\/g; s/"/\\"/g')
        printf '%s="%s"\n' "$1" "$_q"
        ;;
      *) printf '%s=%s\n' "$1" "$2" ;;
    esac
  }
  hostenv_value_matches() {
    _expected="$(hostenv_desired_line "$1" "$2")"
    grep -qxF "$_expected" "$HF" 2>/dev/null
  }
  HOST_NEEDS_BACKUP=0
  hostenv_value_matches PODBEAN_PUBLISH_WEBHOOK_URL "$S58V_URL" || HOST_NEEDS_BACKUP=1
  hostenv_value_matches PODBEAN_PUBLISH_TOKEN "$S58V_TOKEN" || HOST_NEEDS_BACKUP=1
  hostenv_value_matches PODCAST_CLIENT_LAST_NAME "$S58V_LAST" || HOST_NEEDS_BACKUP=1
  hostenv_value_matches PODCAST_CLIENT_EMAIL "$S58V_EMAIL" || HOST_NEEDS_BACKUP=1
  hostenv_value_matches PODBEAN_PODCAST_ID "$S58V_PODCAST_ID" || HOST_NEEDS_BACKUP=1
  if [ -n "${S58V_FIRST:-}" ]; then
    hostenv_value_matches PODCAST_CLIENT_FIRST_NAME "$S58V_FIRST" || HOST_NEEDS_BACKUP=1
  fi
  if [ "$HOST_NEEDS_BACKUP" = "0" ]; then
    echo "hostenv_backup=not_needed"
    exit 0
  fi
  HTS="$(date -u +%Y%m%dT%H%M%SZ)"
  HB="$(mktemp "${HF}.bak.s58u18-${HTS}.XXXXXX")" || {
    echo "result=FAILED reason=hostenv_backup_create_failed"; exit 1;
  }
  if ! cp -p "$HF" "$HB"; then
    rm -f "$HB"
    echo "result=FAILED reason=hostenv_backup_copy_failed"
    exit 1
  fi
  echo "hostenv_backup=copied"
  exit 0
fi

if [ "$P18_MODE" = "hostenv" ]; then
  [ -n "${S58V_URL:-}" ] || { echo "result=FAILED reason=hostenv_requires_inject_payload"; exit 1; }
  [ "${P18_HOSTENV_BACKUP_OK:-0}" = "1" ] || { echo "result=FAILED reason=hostenv_backup_not_proven"; exit 1; }
  HF="${P18_HOSTENV_FILE:-}"
  [ -n "$HF" ] || { echo "result=FAILED reason=hostenv_file_unset"; exit 1; }
  fmt_dotenv() {
    case "$1" in
      ''|*[!A-Za-z0-9_@.:/+-]*) printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')" ;;
      *) printf '%s' "$1" ;;
    esac
  }
  hostenv_write() { # name value -> prints label only
    _line="$1=$(fmt_dotenv "$2")"
    [ -f "$HF" ] || return 1
    if grep -qxF "$_line" "$HF" 2>/dev/null; then echo "hostenv:$1=ALREADY"; return 0; fi
    _hrc=0
    grep -v "^$1=" "$HF" > "$HF.tmp.s58u18" 2>/dev/null || _hrc=$?
    if [ "$_hrc" -ge 2 ]; then rm -f "$HF.tmp.s58u18"; return 1; fi
    printf '%s\n' "$_line" >> "$HF.tmp.s58u18" || { rm -f "$HF.tmp.s58u18"; return 1; }
    mv "$HF.tmp.s58u18" "$HF" || { rm -f "$HF.tmp.s58u18"; return 1; }
    echo "hostenv:$1=WRITTEN"
    CHANGED=1
    return 0
  }
  hostenv_write PODBEAN_PUBLISH_WEBHOOK_URL "$S58V_URL"  || { echo "result=FAILED reason=hostenv_write_failed"; exit 1; }
  hostenv_write PODBEAN_PUBLISH_TOKEN "$S58V_TOKEN"      || { echo "result=FAILED reason=hostenv_write_failed"; exit 1; }
  hostenv_write PODCAST_CLIENT_LAST_NAME "$S58V_LAST"    || { echo "result=FAILED reason=hostenv_write_failed"; exit 1; }
  hostenv_write PODCAST_CLIENT_EMAIL "$S58V_EMAIL"       || { echo "result=FAILED reason=hostenv_write_failed"; exit 1; }
  hostenv_write PODBEAN_PODCAST_ID "$S58V_PODCAST_ID"    || { echo "result=FAILED reason=hostenv_write_failed"; exit 1; }
  if [ -n "${S58V_FIRST:-}" ]; then
    hostenv_write PODCAST_CLIENT_FIRST_NAME "$S58V_FIRST" || { echo "result=FAILED reason=hostenv_write_failed"; exit 1; }
  fi
  echo "hostenv_changed=$([ "$CHANGED" = "1" ] && echo yes || echo no)"
  exit 0
fi

# ---- inject mode -------------------------------------------------------------
NEED_BACKUP=0
pair_needs_write PODBEAN_PUBLISH_WEBHOOK_URL "$S58V_URL" && NEED_BACKUP=1
pair_needs_write PODBEAN_PUBLISH_TOKEN "$S58V_TOKEN" && NEED_BACKUP=1
pair_needs_write PODCAST_CLIENT_LAST_NAME "$S58V_LAST" && NEED_BACKUP=1
pair_needs_write PODCAST_CLIENT_EMAIL "$S58V_EMAIL" && NEED_BACKUP=1
pair_needs_write PODBEAN_PODCAST_ID "$S58V_PODCAST_ID" && NEED_BACKUP=1
if [ -n "${S58V_FIRST:-}" ]; then
  pair_needs_write PODCAST_CLIENT_FIRST_NAME "$S58V_FIRST" && NEED_BACKUP=1
fi
if [ "$NEED_BACKUP" = "1" ]; then
  TS="$(date -u +%Y%m%dT%H%M%SZ)"
  BK_PARENT="$BOX_HOME/.openclaw/backups"
  mkdir -p "$BK_PARENT" || { echo "result=FAILED reason=backup_dir_uncreatable"; exit 1; }
  BK="$(mktemp -d "$BK_PARENT/s58-u18-$TS.XXXXXX")" || {
    echo "result=FAILED reason=backup_dir_uncreatable"; exit 1;
  }
  chmod 700 "$BK" || { echo "result=FAILED reason=backup_dir_unprotectable"; exit 1; }
  if [ -f "$SECENV" ] && ! cp -p "$SECENV" "$BK/secrets.env"; then
    echo "result=FAILED reason=backup_copy_failed store=secrets.env"
    exit 1
  fi
  if [ -f "$OCJSON" ] && ! cp -p "$OCJSON" "$BK/openclaw.json"; then
    echo "result=FAILED reason=backup_copy_failed store=openclaw.json"
    exit 1
  fi
  echo "backup_dir_present=yes"
  echo "backup:secrets.env=$([ -f "$BK/secrets.env" ] && echo copied || echo absent)"
  echo "backup:openclaw.json=$([ -f "$BK/openclaw.json" ] && echo copied || echo absent)"
else
  echo "backup=not_needed"
fi

write_pair() { # name value
  write_env "$1" "$2" || { echo "result=FAILED reason=env_write_failed"; exit 1; }
  write_ocjson "$1" "$2" || { echo "result=FAILED reason=ocjson_write_failed"; exit 1; }
  return 0
}

do_restart() { # gateway restart on THIS box, only when something changed.
  # WHY (verified live, not assumed): the gateway never reads secrets/.env, and
  # podbean_publish.sh takes the proxy pair from PROCESS env, which the gateway
  # populates from openclaw.json env.vars ONLY at start. Without a restart a
  # freshly provisioned box passes every SET check yet still publishes in
  # broker-fallback mode. OK_ALREADY (changed=no) never restarts.
  # VPS boxes bake P18_RESTART=0: their restart is the wrapper's
  # docker compose force-recreate, never an in-container restart.
  [ "$CHANGED" = "1" ] || { echo "restart=not_needed"; return 0; }
  case "${P18_RESTART:-1}" in
    external) echo "restart=deferred_to_wrapper"; return 0 ;;  # VPS: wrapper force-recreates
    1) : ;;
    *) echo "restart=skipped_by_flag"; return 1 ;;             # --no-restart => PARTIAL
  esac
  if [ -n "${P18_HOME:-}" ]; then echo "restart=skipped_sandbox_home"; return 0; fi
  PATH="$HOME/.local/bin:$HOME/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
  _old_pid="$(launchctl list 2>/dev/null | awk '$3=="ai.openclaw.gateway"{print $1}')"
  launchctl kickstart -k "gui/$(id -u)/ai.openclaw.gateway" >/dev/null 2>&1
  _rrc=$?
  _method=kickstart
  if [ "$_rrc" = "125" ] || [ "$_rrc" = "126" ]; then
    # Some boxes reject kickstart; the KeepAlive=true plist restarts on stop.
    _method=stop-fallback
    launchctl stop ai.openclaw.gateway >/dev/null 2>&1
    _rrc=$?
  fi

  # A zero command status is not proof. The 2026-06-08 incident returned zero
  # while the gateway stayed down. Prove both a new launchd PID and ok:true from
  # the bounded local health poll before reporting success.
  _pid_changed=0
  _new_pid=""
  _i=0
  while [ "$_i" -lt 12 ]; do
    sleep 5
    _new_pid="$(launchctl list 2>/dev/null | awk '$3=="ai.openclaw.gateway"{print $1}')"
    case "$_new_pid" in
      ""|-) : ;;
      *)
        case "$_old_pid" in
          ""|-) : ;; # no before identity means a change cannot be proven
          *) [ "$_new_pid" != "$_old_pid" ] && _pid_changed=1 ;;
        esac
        [ "$_pid_changed" = "1" ] && break
        ;;
    esac
    _i=$((_i + 1))
  done

  _health_ok=0
  _j=0
  while [ "$_j" -lt 12 ]; do
    _health="$(curl -s -m 5 http://127.0.0.1:18789/health 2>/dev/null || true)"
    if printf '%s\n' "$_health" | grep -Eq '"ok"[[:space:]]*:[[:space:]]*true'; then
      _health_ok=1
      break
    fi
    sleep 5
    _j=$((_j + 1))
  done

  if [ "$_rrc" = "0" ] && [ "$_pid_changed" = "1" ] && [ "$_health_ok" = "1" ]; then
    echo "restart=ok pid_changed=1 health_ok=1 method=$_method rc=$_rrc"
    return 0
  fi
  echo "GATEWAY_DOWN=1"
  echo "restart=failed pid_changed=$_pid_changed health_ok=$_health_ok method=$_method rc=$_rrc"
  return 1
}

# Required five runtime values (embedded by the generator header as S58V_*).
write_pair PODBEAN_PUBLISH_WEBHOOK_URL "$S58V_URL"
write_pair PODBEAN_PUBLISH_TOKEN "$S58V_TOKEN"
write_pair PODCAST_CLIENT_LAST_NAME "$S58V_LAST"
write_pair PODCAST_CLIENT_EMAIL "$S58V_EMAIL"
write_pair PODBEAN_PODCAST_ID "$S58V_PODCAST_ID"
if [ -n "${S58V_FIRST:-}" ]; then
  write_pair PODCAST_CLIENT_FIRST_NAME "$S58V_FIRST"
fi
echo "changed=$([ "$CHANGED" = "1" ] && echo yes || echo no)"

# Post-write SET-by-name validation (fail-closed) — BOTH stores, per the U18
# accept clause ("secrets/.env AND openclaw.json env.vars"). env missing is a
# hard FAIL; ocjson missing is PARTIAL (values durable in env, runtime store
# unproven) so it is never reported as a clean OK.
for v in $NAMES; do
  echo "validate:$v:env=$(secenv_state "$v"):ocjson=$(ocjson_state "$v")"
done
MISSING=""
OCJ_MISSING=""
for v in $REQUIRED_NAMES; do
  [ "$(secenv_state "$v")" = "SET" ] || MISSING="$MISSING $v"
  [ "$(ocjson_state "$v")" = "SET" ] || OCJ_MISSING="$OCJ_MISSING $v"
done
if [ -n "$MISSING" ]; then
  echo "result=FAILED reason=post_write_validation_missing"
  exit 1
fi
if [ -n "$OCJ_MISSING" ]; then
  do_restart || :  # align runtime with the stores even on a PARTIAL box
  echo "result=PARTIAL reason=ocjson_not_proven"
  exit 4
fi

# Standing dry-run (U13 reachability; publishes nothing).
if [ "${P18_STANDING:-1}" != "1" ]; then
  echo "dryrun=skipped reason=disabled"
  if do_restart; then
    echo "result=OK"
    exit 0
  fi
  echo "result=PARTIAL reason=changed_but_not_restarted"
  exit 4
fi
_pm=$(grep -c PODBEAN_PUBLISH_WEBHOOK_URL "$SKILL" 2>/dev/null)
[ -n "$_pm" ] || _pm=0
if [ ! -f "$SKILL" ] || [ "$_pm" = "0" ]; then
  echo "dryrun=skipped reason=skill_script_missing_or_no_proxy_mode"
  do_restart || :  # align runtime with the stores even on a PARTIAL box
  echo "result=PARTIAL reason=values_set_but_dry_run_not_runnable"
  exit 4
fi
get_ocjson() { # gateway runtime source; never read probe values from secrets/.env
  if command -v python3 >/dev/null 2>&1; then
    OCJSON="$OCJSON" V="$1" python3 - <<'PY' 2>/dev/null
import json, os
try:
    data = json.load(open(os.environ["OCJSON"]))
except Exception:
    raise SystemExit(1)
value = ((data.get("env", {}) or {}).get("vars", {}) or {}).get(os.environ["V"], "")
print(value if isinstance(value, str) else str(value))
PY
  else
    jq -r --arg k "$1" '.env.vars[$k] // empty' "$OCJSON" 2>/dev/null
  fi
}
V_URL=$(get_ocjson PODBEAN_PUBLISH_WEBHOOK_URL)
V_TOKEN=$(get_ocjson PODBEAN_PUBLISH_TOKEN)
V_LAST=$(get_ocjson PODCAST_CLIENT_LAST_NAME)
V_EMAIL=$(get_ocjson PODCAST_CLIENT_EMAIL)
V_PID=$(get_ocjson PODBEAN_PODCAST_ID)
TMPA="$(mktemp "${TMPDIR:-/tmp}/s58u18-dryrun.XXXXXX")" || exit 1
trap 'rm -f "$TMPA"' EXIT
DRYOUT="$(PODBEAN_PUBLISH_WEBHOOK_URL="$V_URL" PODBEAN_PUBLISH_TOKEN="$V_TOKEN" \
  PODCAST_CLIENT_LAST_NAME="$V_LAST" PODCAST_CLIENT_EMAIL="$V_EMAIL" \
  PODBEAN_PODCAST_ID="$V_PID" \
  bash "$SKILL" --audio "$TMPA" --title "S58-U18 provisioning dry-run (no publish)" --dry-run 2>/dev/null)"
DRYRC=$?
GS="$(printf '%s\n' "$DRYOUT" | sed -n 's/.*"good_standing":\([a-z]*\).*/\1/p' | head -n 1)"
echo "dryrun_exit=$DRYRC good_standing=${GS:-unknown}"
if [ "$DRYRC" = "0" ]; then
  if do_restart; then
    echo "result=OK"
    exit 0
  fi
  echo "result=PARTIAL reason=changed_but_not_restarted"
  exit 4
fi
echo "result=FAILED reason=standing_dry_run_failed"
exit 1
PAYLOAD_EOF
}

# ---- per-box runner ------------------------------------------------------------
TMP_PAYLOAD=""
ORDERED_FILE=""
cleanup() {
  [ -n "$TMP_PAYLOAD" ] && rm -f "$TMP_PAYLOAD" 2>/dev/null
  [ -n "$ORDERED_FILE" ] && rm -f "$ORDERED_FILE" 2>/dev/null
  return 0
}
trap cleanup EXIT

box_selected() {
  [ -z "$BOX_FILTERS" ] && return 0
  for f in $BOX_FILTERS; do [ "$f" = "$B_NAME" ] && return 0; done
  return 1
}

build_payload() { # mode -> 0600 temp payload in $TMP_PAYLOAD
  TMP_PAYLOAD="$(mktemp "${TMPDIR:-/tmp}/s58u18-payload.XXXXXX.sh")" || die "mktemp failed"
  chmod 600 "$TMP_PAYLOAD"
  {
    if [ "$1" = "inject" ]; then
      S58_TOKEN_INPUT="$PUBLISH_TOKEN" \
        python3 - "$B_LAST" "$B_EMAIL" "$B_FIRST" "$B_PID" "$PUBLISH_URL" <<'PYEOF'
import os, shlex, sys
last, email, first, pid, url = sys.argv[1:6]
token = os.environ["S58_TOKEN_INPUT"]
for name, val in [("S58V_LAST", last), ("S58V_EMAIL", email),
                  ("S58V_FIRST", first), ("S58V_PODCAST_ID", pid),
                  ("S58V_URL", url), ("S58V_TOKEN", token)]:
    print("%s=%s" % (name, shlex.quote(val)))
PYEOF
      # The override hook lets the VPS wrapper re-run the SAME payload file in
      # hostenv mode on the host after the docker-exec container leg.
      printf 'P18_MODE="${P18_MODE_OVERRIDE:-inject}"\n'
    else
      printf 'P18_MODE="${P18_MODE_OVERRIDE:-probe}"\n'
    fi
    [ "$STANDING_PROBE" = "1" ] || printf 'P18_STANDING=0\n'
    # In-payload restart is for mac/local boxes only; a VPS box restarts via the
    # wrapper's force-recreate, never from inside its own container.
    if [ "$NO_RESTART" = "1" ]; then
      printf 'P18_RESTART=0\n'
    elif [ "$B_PLATFORM" = "vps" ]; then
      printf 'P18_RESTART=external\n'
    fi
    [ -z "$B_HOME" ] || printf 'P18_HOME=%s\n' "$(shquote "$B_HOME")"
    emit_box_script
  } > "$TMP_PAYLOAD" || die "could not build payload"
}

run_vps_box() { # mode -> report on stdout; rc returned. Docker transport.
  # Plain `ssh 'sh -s'` writes the HOST home, which is NOT the gateway store —
  # that lives at /data/.openclaw INSIDE the container. The payload rides
  # base64 inside a generated host wrapper (stdin-only; never argv):
  #   1. snapshot the host compose env_file once (inject only; fail closed)
  #   2. docker exec -i -u node <container> sh -s   (container files, HOME=/data)
  #   3. same payload re-run on the host in hostenv mode -> compose env_file
  #   4. anything WRITTEN => docker compose up -d --force-recreate (compose
  #      reads the env_file only at create; a bare restart keeps the old env),
  #      then prove a new container, exact inherited values, and gateway health.
  #      Roll in place, force-recreate, NEVER re-init credentials.
  _pb64="$(base64 < "$TMP_PAYLOAD" | tr -d '\n')"
  _wrap="$(mktemp "${TMPDIR:-/tmp}/s58u18-wrap.XXXXXX.sh")" || die "mktemp failed"
  chmod 600 "$_wrap"
  {
    printf 'set -u\numask 077\n'
    printf 'CONTAINER=%s\n' "$(shquote "$B_CONTAINER")"
    printf 'COMPOSE_DIR=%s\n' "$(shquote "$B_COMPOSE")"
    printf 'MODE=%s\n' "$(shquote "$1")"
    printf 'DO_RECREATE=%s\n' "$([ "$NO_RESTART" = "1" ] && echo 0 || echo 1)"
    # Base64's alphabet is safe in an unquoted shell assignment. Keep the
    # token-bearing payload out of shquote/python argv and write it with printf.
    printf 'PB64=%s\n' "$_pb64"
    cat <<'WRAP_EOF'
TMP="$(mktemp /tmp/s58u18-p.XXXXXX)" || exit 97
trap 'rm -f "$TMP"' EXIT
chmod 600 "$TMP" 2>/dev/null || :
printf '%s' "$PB64" | base64 -d > "$TMP" || { rm -f "$TMP"; exit 97; }
HOUT=""
if [ "$MODE" = "inject" ]; then
  HBOUT="$(P18_MODE_OVERRIDE=hostenvbackup P18_HOSTENV_FILE="$COMPOSE_DIR/.env" sh "$TMP")"
  HBRC=$?
  printf '%s\n' "$HBOUT"
  if [ "$HBRC" != "0" ]; then
    rm -f "$TMP"
    echo "result=FAILED reason=hostenv_backup_failed"
    exit 1
  fi
fi
OLD_CID=""
if [ "$MODE" = "inject" ]; then
  OLD_CID="$(docker inspect -f '{{.Id}}' "$CONTAINER" 2>/dev/null || true)"
fi
COUT="$(docker exec -i -u node -e P18_HOME=/data "$CONTAINER" sh -s < "$TMP")"
CRC=$?
printf '%s\n' "$COUT"
if [ "$CRC" != "0" ]; then rm -f "$TMP"; exit "$CRC"; fi
if [ "$MODE" = "inject" ]; then
  HOUT="$(P18_MODE_OVERRIDE=hostenv P18_HOSTENV_BACKUP_OK=1 P18_HOSTENV_FILE="$COMPOSE_DIR/.env" sh "$TMP")"
  HRC=$?
  printf '%s\n' "$HOUT"
  if [ "$HRC" != "0" ]; then
    rm -f "$TMP"
    echo "result=PARTIAL reason=hostenv_write_failed_on_host"
    exit 4
  fi
fi
if [ "$MODE" = "probe" ]; then
  # host-side survey leg: compose env_file SET/NOT-SET by NAME only
  for _v in PODBEAN_PUBLISH_WEBHOOK_URL PODBEAN_PUBLISH_TOKEN PODCAST_CLIENT_LAST_NAME PODCAST_CLIENT_EMAIL PODBEAN_PODCAST_ID PODCAST_CLIENT_FIRST_NAME; do
    if [ -n "$COMPOSE_DIR" ] && [ -f "$COMPOSE_DIR/.env" ] && grep -q "^$_v=" "$COMPOSE_DIR/.env" 2>/dev/null; then
      echo "hostenv:$_v=SET"
    else
      echo "hostenv:$_v=NOT-SET"
    fi
  done
  exit 0
fi
NEED=no
printf '%s\n%s\n' "$COUT" "$HOUT" | grep -q '=WRITTEN' && NEED=yes
if [ "$NEED" = "yes" ]; then
  if [ "$DO_RECREATE" != "1" ]; then
    echo "restart=skipped_by_flag"
    echo "result=PARTIAL reason=changed_but_not_restarted"
    exit 4
  fi
  if [ -z "$OLD_CID" ]; then
    echo "GATEWAY_DOWN=1"
    echo "restart=failed method=recreate container_id_before=unproven"
    echo "result=PARTIAL reason=container_identity_before_recreate_not_proven"
    exit 4
  fi
  CF=""
  for _c in compose.yaml compose.yml docker-compose.yaml docker-compose.yml; do
    [ -f "$COMPOSE_DIR/$_c" ] && { CF="$_c"; break; }
  done
  if [ -z "$CF" ]; then
    echo "restart=failed reason=no_compose_file"
    echo "result=PARTIAL reason=changed_but_cannot_recreate"
    exit 4
  fi
  ( cd "$COMPOSE_DIR" && docker compose up -d --force-recreate >/dev/null 2>&1 )
  RRC=$?
  if [ "$RRC" != "0" ]; then
    echo "restart=failed method=recreate rc=$RRC"
    echo "result=PARTIAL reason=recreate_failed"
    exit 4
  fi

  NEW_CID=""
  RUNNING=false
  _i=0
  while [ "$_i" -lt 12 ]; do
    NEW_CID="$(docker inspect -f '{{.Id}}' "$CONTAINER" 2>/dev/null || true)"
    RUNNING="$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || echo false)"
    if [ "$RUNNING" = "true" ] && [ -n "$NEW_CID" ] && [ "$NEW_CID" != "$OLD_CID" ]; then
      break
    fi
    sleep 5
    _i=$((_i + 1))
  done
  if [ "$RUNNING" != "true" ] || [ -z "$NEW_CID" ] || [ "$NEW_CID" = "$OLD_CID" ]; then
    echo "GATEWAY_DOWN=1"
    echo "restart=failed method=recreate rc=0 container_id_changed=0"
    echo "result=PARTIAL reason=container_recreate_not_proven"
    exit 4
  fi

  VOUT="$(docker exec -i -u node -e P18_HOME=/data -e P18_MODE_OVERRIDE=runtimeverify "$CONTAINER" sh -s < "$TMP")"
  VRC=$?
  printf '%s\n' "$VOUT"
  if [ "$VRC" != "0" ]; then
    echo "GATEWAY_DOWN=1"
    echo "restart=failed method=recreate rc=0 container_id_changed=1"
    echo "result=PARTIAL reason=runtime_not_proven"
    rm -f "$TMP"
    exit 4
  fi
  echo "restart=recreate rc=0 container_id_changed=1 health_ok=1 runtime_values=1"
else
  echo "restart=not_needed"
fi
rm -f "$TMP"
exit 0
WRAP_EOF
  } > "$_wrap" || die "could not build vps wrapper"
  ssh -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=5 \
      -o ServerAliveCountMax=3 \
      "$B_SSH" 'sh -s' < "$_wrap"
  _vrc=$?
  rm -f "$_wrap" 2>/dev/null
  return $_vrc
}

run_box() { # mode -> box report on stdout; box exit code returned
  # Remote stdout is captured CLEAN — the caller parses ^-anchored fields, so a
  # prefix (the original piped remote output through `sed 's/^/.../'`) makes
  # every remote verdict unparseable: apply runs would always grade FAILED.
  # Remote stderr flows through to the operator terminal untouched; the payload
  # contract already forbids values on any stream. The payload file is removed
  # per box — one long-lived trap-cleaned file would still leave N-1 stale
  # token-bearing temp files behind on a multi-box run.
  case "$B_PLATFORM" in
    mac|vps) : ;;
    *) echo "result=FAILED reason=unsupported_platform"; return 64 ;;
  esac
  build_payload "$1"
  if [ "$LOCAL" = "1" ] || [ "$B_SSH" = "local" ]; then
    bash "$TMP_PAYLOAD"
    _brc=$?
  elif [ "$B_PLATFORM" = "vps" ]; then
    run_vps_box "$1"
    _brc=$?
  elif [ "$B_PLATFORM" = "mac" ]; then
    ssh -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=5 \
        -o ServerAliveCountMax=3 \
        "$B_SSH" 'sh -s' < "$TMP_PAYLOAD"
    _brc=$?
  else
    echo "result=FAILED reason=unsupported_platform"
    _brc=64
  fi
  rm -f "$TMP_PAYLOAD" 2>/dev/null
  TMP_PAYLOAD=""
  return $_brc
}

prepare_ledger() { # fail before transport: a fleet mutation never runs blind
  [ -n "$LOG_FILE" ] || die "ledger path is empty"
  _d="$(dirname "$LOG_FILE")"
  mkdir -p "$_d" 2>/dev/null || die "ledger directory is not creatable: $_d"
  chmod 700 "$_d" 2>/dev/null || die "ledger directory cannot be protected: $_d"
  ( : >> "$LOG_FILE" ) 2>/dev/null || die "ledger is not writable: $LOG_FILE"
  chmod 600 "$LOG_FILE" 2>/dev/null || die "ledger cannot be protected: $LOG_FILE"
}

log_line() { # durable append first; stop immediately if the ledger fails later
  ( printf '%s\n' "$1" >> "$LOG_FILE" ) 2>/dev/null || die "ledger append failed: $LOG_FILE"
  printf '%s\n' "$1"
  return 0
}

field() { # extract a field from a box report: $1=report $2=sed-pattern
  printf '%s\n' "$1" | sed -n "$2" | tail -n 1
}

# ---- main loop (redirection, NOT a pipeline: counters survive) ----------------
prepare_ledger
MODE_LABEL="DRY-RUN (read-only)"; [ "$APPLY" = "1" ] && MODE_LABEL="APPLY"
printf '=== %s: %s | manifest=%s | operator-local-token=%s ===\n' \
  "$SCRIPT_NAME" "$MODE_LABEL" "$BOXES_FILE" "$TOKEN_LOCAL_STATE"

OPERATOR_PROVEN=0
COUNT_OK=0; COUNT_SKIP=0; COUNT_FAIL=0; COUNT_BLOCKED=0; COUNT_TOTAL=0
COUNT_GATEWAY_DOWN=0
ORDERED_FILE="$(mktemp "${TMPDIR:-/tmp}/s58u18-ordered.XXXXXX")" || die "mktemp failed"
printf '%s\n' "$ORDERED_TSV" > "$ORDERED_FILE"

while IFS='|' read -r B_NAME B_ROLE B_PLATFORM B_SSH B_HOME B_CONTAINER B_COMPOSE B_COMPLETE B_LAST B_EMAIL B_FIRST B_PID; do
  [ -n "$B_NAME" ] || continue
  box_selected || continue
  COUNT_TOTAL=$((COUNT_TOTAL + 1))
  NOW_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  # Identity fail-closed: every runtime-critical per-box value is required.
  if [ "$B_COMPLETE" != "1" ] || [ -z "$B_LAST" ] || [ -z "$B_EMAIL" ] || [ -z "$B_PID" ]; then
    log_line "[$NOW_UTC] box=$B_NAME role=$B_ROLE platform=$B_PLATFORM verdict=BLOCKED_IDENTITY_INCOMPLETE detail=roster_identity_missing_last_name_email_or_podcast_id"
    COUNT_BLOCKED=$((COUNT_BLOCKED + 1))
    if [ "$APPLY" = "1" ]; then COUNT_FAIL=$((COUNT_FAIL + 1)); fi
    continue
  fi

  # Match run_box's exact local-transport condition. A manifest row can request
  # local transport without --local; never let either path write a client
  # identity onto the operator filesystem.
  if [ "$APPLY" = "1" ] && { [ "$LOCAL" = "1" ] || [ "$B_SSH" = "local" ]; } \
      && [ "$B_ROLE" != "operator" ]; then
    log_line "[$NOW_UTC] box=$B_NAME role=$B_ROLE platform=$B_PLATFORM verdict=BLOCKED_LOCAL_CLIENT_IDENTITY detail=local_transport_may_only_apply_operator_identity"
    COUNT_BLOCKED=$((COUNT_BLOCKED + 1))
    COUNT_FAIL=$((COUNT_FAIL + 1))
    continue
  fi

  # structural operator-first gate (APPLY only)
  if [ "$APPLY" = "1" ] && [ "$B_ROLE" != "operator" ]; then
    if [ "$INCLUDE_CLIENTS" != "1" ]; then
      log_line "[$NOW_UTC] box=$B_NAME role=$B_ROLE platform=$B_PLATFORM verdict=SKIPPED_OPERATOR_GATE detail=client_boxes_require_include_clients_flag"
      COUNT_SKIP=$((COUNT_SKIP + 1))
      continue
    fi
    if [ "$OPERATOR_PROVEN" != "1" ]; then
      log_line "[$NOW_UTC] box=$B_NAME role=$B_ROLE platform=$B_PLATFORM verdict=REFUSED_OPERATOR_NOT_PROVEN detail=operator_box_must_pass_earlier_in_same_run"
      COUNT_FAIL=$((COUNT_FAIL + 1))
      continue
    fi
  fi

  # VPS transport completeness — fail closed BEFORE touching the box: an apply
  # without a compose_dir could inject the container but never mirror the
  # env_file or force-recreate, leaving a half-provisioned box.
  if [ "$B_PLATFORM" = "vps" ] && [ "$B_SSH" != "local" ] && [ "$LOCAL" != "1" ]; then
    [ -n "$B_CONTAINER" ] || B_CONTAINER="${B_NAME}-openclaw-1"
    if [ "$APPLY" = "1" ] && [ -z "$B_COMPOSE" ]; then
      log_line "[$NOW_UTC] box=$B_NAME role=$B_ROLE platform=$B_PLATFORM verdict=BLOCKED_VPS_MANIFEST_INCOMPLETE detail=compose_dir_required_for_apply"
      COUNT_BLOCKED=$((COUNT_BLOCKED + 1))
      COUNT_FAIL=$((COUNT_FAIL + 1))
      continue
    fi
  fi

  if [ "$APPLY" = "1" ]; then BOX_MODE="inject"; else BOX_MODE="probe"; fi
  REPORT="$(run_box "$BOX_MODE")"
  BOX_RC=$?
  printf '%s\n' "$REPORT" | sed "s/^/  [$B_NAME] /"

  RESULT="$(field "$REPORT" 's/^result=\([A-Z]*\).*/\1/p')"
  REASON="$(field "$REPORT" 's/^result=[A-Z]* reason=\(.*\)/\1/p')"
  CHANGED_ST="$(field "$REPORT" 's/^changed=\(.*\)/\1/p')"
  HOST_CHANGED_ST="$(field "$REPORT" 's/^hostenv_changed=\(.*\)/\1/p')"
  EFFECTIVE_CHANGED_ST="$CHANGED_ST"
  [ "$HOST_CHANGED_ST" = "yes" ] && EFFECTIVE_CHANGED_ST="yes"
  DRYEXIT="$(field "$REPORT" 's/^dryrun_exit=\([0-9]*\).*/\1/p')"
  GS="$(field "$REPORT" 's/^dryrun_exit=[0-9]* good_standing=\([a-z]*\).*/\1/p')"
  SKILL_ST="$(field "$REPORT" 's/^skill_script=\([a-z]*\).*/\1/p')"
  RESTART_ST="$(field "$REPORT" 's/^restart=\(.*\)/\1/p')"
  GATEWAY_DOWN_ST="$(field "$REPORT" 's/^GATEWAY_DOWN=\([01]\)$/\1/p')"
  [ "$GATEWAY_DOWN_ST" = "1" ] && COUNT_GATEWAY_DOWN=$((COUNT_GATEWAY_DOWN + 1))
  if [ "$APPLY" = "1" ]; then PFIX="validate"; else PFIX="probe"; fi
  V_URL_ST="$(field "$REPORT" "s/^$PFIX:PODBEAN_PUBLISH_WEBHOOK_URL:env=\\([A-Z-]*\\).*/\\1/p")"
  V_TOK_ST="$(field "$REPORT" "s/^$PFIX:PODBEAN_PUBLISH_TOKEN:env=\\([A-Z-]*\\).*/\\1/p")"
  V_LN_ST="$(field "$REPORT" "s/^$PFIX:PODCAST_CLIENT_LAST_NAME:env=\\([A-Z-]*\\).*/\\1/p")"
  V_EM_ST="$(field "$REPORT" "s/^$PFIX:PODCAST_CLIENT_EMAIL:env=\\([A-Z-]*\\).*/\\1/p")"
  V_PID_ST="$(field "$REPORT" "s/^$PFIX:PODBEAN_PODCAST_ID:env=\\([A-Z-]*\\).*/\\1/p")"
  V_URL_OCJ="$(field "$REPORT" "s/^$PFIX:PODBEAN_PUBLISH_WEBHOOK_URL:env=[A-Z-]*:ocjson=\\([A-Z-]*\\).*/\\1/p")"
  V_TOK_OCJ="$(field "$REPORT" "s/^$PFIX:PODBEAN_PUBLISH_TOKEN:env=[A-Z-]*:ocjson=\\([A-Z-]*\\).*/\\1/p")"
  V_LN_OCJ="$(field "$REPORT" "s/^$PFIX:PODCAST_CLIENT_LAST_NAME:env=[A-Z-]*:ocjson=\\([A-Z-]*\\).*/\\1/p")"
  V_EM_OCJ="$(field "$REPORT" "s/^$PFIX:PODCAST_CLIENT_EMAIL:env=[A-Z-]*:ocjson=\\([A-Z-]*\\).*/\\1/p")"
  V_PID_OCJ="$(field "$REPORT" "s/^$PFIX:PODBEAN_PODCAST_ID:env=[A-Z-]*:ocjson=\\([A-Z-]*\\).*/\\1/p")"
  STORES_PROVEN=1
  if [ "$V_URL_ST" != "SET" ] || [ "$V_TOK_ST" != "SET" ] || \
     [ "$V_LN_ST" != "SET" ] || [ "$V_EM_ST" != "SET" ] || \
     [ "$V_PID_ST" != "SET" ] || [ "$V_URL_OCJ" != "SET" ] || \
     [ "$V_TOK_OCJ" != "SET" ] || [ "$V_LN_OCJ" != "SET" ] || \
     [ "$V_EM_OCJ" != "SET" ] || [ "$V_PID_OCJ" != "SET" ]; then
    STORES_PROVEN=0
  fi

  VERDICT="OK"
  if [ "$APPLY" = "1" ]; then
    if [ "$BOX_RC" != "0" ]; then
      VERDICT="FAILED"
      REASON="transport_exit_nonzero"
    else
      case "$RESULT" in
        OK)
          if [ "$STORES_PROVEN" = "1" ]; then
            VERDICT="OK"
            [ "$EFFECTIVE_CHANGED_ST" = "no" ] && VERDICT="OK_ALREADY"
          else
            VERDICT="PARTIAL"
            REASON="runtime_store_not_proven"
          fi
          ;;
        PARTIAL) VERDICT="PARTIAL" ;;
        *)       VERDICT="FAILED" ;;
      esac
    fi
  else
    if [ "$BOX_RC" != "0" ]; then
      VERDICT="UNREACHABLE_OR_ERROR"
    elif [ "$STORES_PROVEN" != "1" ]; then
      VERDICT="PARTIAL"
      REASON="runtime_store_not_proven"
    fi
  fi

  log_line "[$NOW_UTC] box=$B_NAME role=$B_ROLE platform=$B_PLATFORM verdict=$VERDICT${REASON:+ reason=$REASON} transport_rc=$BOX_RC url=${V_URL_ST:-?} token=${V_TOK_ST:-?} last_name=${V_LN_ST:-?} email=${V_EM_ST:-?} podcast_id=${V_PID_ST:-?} runtime_url=${V_URL_OCJ:-?} runtime_token=${V_TOK_OCJ:-?} runtime_last_name=${V_LN_OCJ:-?} runtime_email=${V_EM_OCJ:-?} runtime_podcast_id=${V_PID_OCJ:-?}${SKILL_ST:+ skill=$SKILL_ST}${EFFECTIVE_CHANGED_ST:+ changed=$EFFECTIVE_CHANGED_ST}${HOST_CHANGED_ST:+ host_changed=$HOST_CHANGED_ST}${DRYEXIT:+ dryrun_exit=$DRYEXIT}${GS:+ good_standing=$GS}${RESTART_ST:+ restart=$RESTART_ST}${GATEWAY_DOWN_ST:+ gateway_down=$GATEWAY_DOWN_ST}"

  if [ "$VERDICT" = "OK" ] || [ "$VERDICT" = "OK_ALREADY" ]; then
    COUNT_OK=$((COUNT_OK + 1))
    [ "$B_ROLE" = "operator" ] && OPERATOR_PROVEN=1
  elif [ "$VERDICT" != "SKIPPED_OPERATOR_GATE" ]; then
    COUNT_FAIL=$((COUNT_FAIL + 1))
  fi
done < "$ORDERED_FILE"
rm -f "$ORDERED_FILE"

printf '=== summary: total=%d ok=%d skipped=%d blocked_identity=%d failed=%d gateway_down=%d | log=%s ===\n' \
  "$COUNT_TOTAL" "$COUNT_OK" "$COUNT_SKIP" "$COUNT_BLOCKED" "$COUNT_FAIL" "$COUNT_GATEWAY_DOWN" "$LOG_FILE"

if [ "$COUNT_FAIL" -gt 0 ]; then exit 2; fi
exit 0
