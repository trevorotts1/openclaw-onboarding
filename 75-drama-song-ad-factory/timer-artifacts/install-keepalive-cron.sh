#!/usr/bin/env bash
# install-keepalive-cron.sh - register AND reconcile the skill 75 run keepalive
# (ONE cron job) against its FULL desired state. Findings D22/D23/D31 repair.
#
# WHAT THIS DOES
#   Registers exactly one `openclaw` cron job named `skill75-keepalive` whose
#   prompt is timer-artifacts/keepalive-cron-prompt.txt with __SKILL_ROOT__ /
#   __RUNS_DIR__ substituted - and, when the job already exists, RECONCILES the
#   registered job field by field against the desired state below. Name-only
#   presence NEVER passes: a job with the right name and the wrong model,
#   schedule, prompt/root, enabled state, agent, session, delivery or revision
#   is detected and repaired through the supported owner interface
#   (`openclaw cron edit <id>`), then read back and re-compared.
#
#   Desired state (schema blackceo.keepalive-desired-state/v1):
#     * installation/owner identity - declaration key skill75-keepalive:<id>
#       (set at add; a drifted key is reported, never silently re-created),
#       effective agent id read back, script/prompt/skill revisions recorded.
#     * enabled state          - true (a disabled job with the right name is
#                                DRIFT, not health; an operator tombstone is
#                                the only thing that stops this registrar).
#     * schedule               - "*/10 * * * *" (SKILL75_KEEPALIVE_CRON).
#     * agent/role             - --agent only when SKILL75_KEEPALIVE_AGENT or
#                                DS_AGENT_ID is set; never guessed. Role is the
#                                read-only observer (never builder).
#     * effective model and    - --model pinned when requested
#       supported effort        (SKILL75_KEEPALIVE_MODEL, default below) and
#                                the CLI advertises --model. A FAILED PINNED
#                                REGISTRATION NEVER RETRIES UNPINNED:
#                                requested/effective mismatch stays visible and
#                                the exit is non-zero (D22). Effort (--thinking)
#                                is recorded honestly: unsupported is reported
#                                as unsupported, never as an honored setting.
#     * prompt/schema revision - sha256 of the rendered prompt plus schema id,
#                                carried in the job description and compared.
#     * run registry/root      - the runs dir baked into the prompt and echoed
#                                in the description; root drift shows up as
#                                prompt-revision drift and is repaired together.
#     * reporting route        - delivery stays silent (--no-deliver); per-run
#                                client delivery is the prompt's own origin
#                                registry, never a guessed target.
#     * last successful exec.  - attested from the scheduler's own run state
#                                (lastRunAtMs / lastRunStatus / consecutiveErrors),
#                                distinguishing healthy from job loss.
#
#   Attestation (written on --apply, never on --dry-run):
#     <RUNS_DIR>/.keepalive/install-attest.json - requested vs stored vs
#     effective identity for every key above, the readback result, and one
#     proven successful observation tick after any change. "Registration is
#     not health": DONE is only printed when readback matched and the tick
#     (or, with no changes, the scheduler's last successful execution) is
#     proven.
#
# IDEMPOTENT, TOMBSTONE-RESPECTING, IN-PLACE
#   * exact-name presence against `cron list --json` (with --all when the CLI
#     advertises it, so DISABLED jobs stay visible) - never the truncated text
#     table. Presence UNKNOWN = do NOT register (no duplicate crons).
#   * a durable tombstone under <OC_ROOT>/workspace/.cron-tombstones (written
#     only by uninstall.sh) means an operator removed the job on purpose:
#     observed, recorded, nothing registered. Missing-without-tombstone is
#     recoverable job loss and is re-registered. The condition observed
#     (healthy / drift-repaired / recoverable-loss / operator-removal /
#     register-refused / readback-unproven) is recorded in the attestation.
#   * upgrades reconcile the managed job IN PLACE via `cron edit` - no second
#     schedule, and "already present" alone never hides a gap. Duplicate jobs
#     under the managed name are reduced to one, each removal logged.
#   * when the scheduler refuses an edit because the job is system-owned, the
#     refusal is reported once with its exact text; the script does not bypass
#     ownership, does not loop on the same rejected command, and does not
#     create a duplicate job.
#
# MODES
#   --dry-run  (DEFAULT) print the exact plan (register or drift list),
#              register/repair nothing, write nothing, exit 0.
#   --apply    register or reconcile, read back, prove a tick, write attestation.
#   --verify-tick  force one observation-tick proof even when nothing changed.
#
# CLI
#   bash install-keepalive-cron.sh [--dry-run|--apply|--verify-tick]
#        [--agent NAME] [--model ID] [--runs-dir DIR]
#
# EXIT
#   0  reconciled and attested (or dry-run plan printed)
#   2  this skill's own prompt file is missing (repo defect) or bad usage
#   3  NOT reconciled - CLI absent, presence UNKNOWN, pinned registration or
#      repair failed, readback mismatch, or tick unproven. Non-fatal and
#      re-run safe (a later run repairs); the reason is named on stderr.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$HERE/.." && pwd)"
PROMPT_FILE="$HERE/keepalive-cron-prompt.txt"

NAME="skill75-keepalive"
CRON="${SKILL75_KEEPALIVE_CRON:-*/10 * * * *}"
MODE="dry-run"
FORCE_TICK=0
AGENT="${SKILL75_KEEPALIVE_AGENT:-${DS_AGENT_ID:-}}"
MODEL="${SKILL75_KEEPALIVE_MODEL:-ollama/deepseek-v4.1-flash:cloud}"
EFFORT="${SKILL75_KEEPALIVE_EFFORT:-}"
OPENCLAW_BIN="${OPENCLAW_BIN:-openclaw}"
SCHEMA="blackceo.keepalive-desired-state/v1"
PROMPT_SCHEMA="blackceo.keepalive-prompt/v2"

# The persistent runs dir for this platform (INSTRUCTIONS.md "Studio orders").
if [ -n "${SKILL75_KEEPALIVE_RUNS_DIR:-}" ]; then
  RUNS_DIR="$SKILL75_KEEPALIVE_RUNS_DIR"
elif [ -d /data/.openclaw ]; then
  RUNS_DIR="/data/.openclaw/drama-runs"
elif [ -d "$HOME/.openclaw" ]; then
  RUNS_DIR="$HOME/.openclaw/drama-runs"
else
  RUNS_DIR="$HOME/.openclaw/drama-runs"
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)     MODE="dry-run"; shift ;;
    --apply)       MODE="apply"; shift ;;
    --verify-tick) MODE="apply"; FORCE_TICK=1; shift ;;
    --agent)    AGENT="${2:-}"; shift 2 ;;
    --model)    MODEL="${2:-}"; shift 2 ;;
    --runs-dir) RUNS_DIR="${2:-}"; shift 2 ;;
    -h|--help)  sed -n '2,72p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

_log() { echo "[install-keepalive-cron] $*"; }
_err() { echo "[install-keepalive-cron] $*" >&2; }

if [ ! -f "$PROMPT_FILE" ]; then
  _err "FAIL prompt file not found: $PROMPT_FILE"
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  _err "FAIL python3 is required for desired-state reconciliation (JSON compare + attestation) - cannot attest, NOT registering."
  exit 3
fi

if ! command -v "$OPENCLAW_BIN" >/dev/null 2>&1; then
  _log "SKIP openclaw CLI not on PATH - cannot reconcile '$NAME'. Re-run once it is installed."
  exit 3
fi

# --- durable tombstone (only the operator's uninstall writes one) ------------
_tombstone_dir() {
  local root
  if [ -d /data/.openclaw ]; then root="/data/.openclaw"
  elif [ -d "$HOME/.openclaw" ]; then root="$HOME/.openclaw"
  else return 1; fi
  printf '%s' "$root/workspace/.cron-tombstones"
}
_tombstoned() {
  local dir
  dir="$(_tombstone_dir)" || return 1
  [ -f "$dir/$NAME" ]
}

# --- feature-detect this CLI build -----------------------------------------
_help_cron_add="$("$OPENCLAW_BIN" cron add --help 2>&1 || true)"
_help_cron_edit="$("$OPENCLAW_BIN" cron edit --help 2>&1 || true)"
_help_cron_list="$("$OPENCLAW_BIN" cron list --help 2>&1 || true)"
_has_add() { printf '%s' "$_help_cron_add" | grep -q -- "$1"; }
_has_edit() { printf '%s' "$_help_cron_edit" | grep -q -- "$1"; }
_has_list() { printf '%s' "$_help_cron_list" | grep -q -- "$1"; }

# --- jobs JSON access (list with disabled visible; get/show for one job) -----
_list_jobs_json() {
  if _has_list --all; then
    "$OPENCLAW_BIN" cron list --json --all 2>/dev/null
  else
    "$OPENCLAW_BIN" cron list --json 2>/dev/null
  fi
}
_job_json() {  # $1 = job id
  local raw
  raw="$("$OPENCLAW_BIN" cron get "$1" --json 2>/dev/null)" && [ -n "$raw" ] && { printf '%s' "$raw"; return 0; }
  raw="$("$OPENCLAW_BIN" cron show "$1" --json 2>/dev/null)" && [ -n "$raw" ] && { printf '%s' "$raw"; return 0; }
  return 1
}

# --- the prompt (placeholders substituted, never a second copy) -------------
PROMPT="$(sed -e "s|__SKILL_ROOT__|$SKILL_ROOT|g" -e "s|__RUNS_DIR__|$RUNS_DIR|g" "$PROMPT_FILE")"
[ -n "$PROMPT" ] || { _err "FAIL prompt file rendered empty: $PROMPT_FILE"; exit 2; }
PROMPT_REV="$(printf '%s' "$PROMPT" | python3 -c 'import hashlib,sys;print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())')"
SCRIPT_REV="$(python3 -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$0")"
SKILL_VER="$(cat "$SKILL_ROOT/skill-version.txt" 2>/dev/null || echo unknown)"
INSTALL_ID="${SKILL75_KEEPALIVE_INSTALL_ID:-unknown}"
RUNS_ROOT_CANON="$(python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "$RUNS_DIR")"

DESC="managed-by=install-keepalive-cron.sh schema=$SCHEMA prompt_schema=$PROMPT_SCHEMA prompt_rev=$PROMPT_REV runs_dir=$RUNS_ROOT_CANON skill_root=$SKILL_ROOT skill_version=$SKILL_VER install_id=$INSTALL_ID"

MISMATCHES=""
_add_mismatch() { MISMATCHES="${MISMATCHES}${MISMATCHES:+,}$1"; }

# --- desired-state comparer (normalized across known job JSON shapes) -------
# Prints drifted keys, one per line. "declkey" drift cannot be repaired in
# place (identity is set at add) and is reported as visible mismatch only.
_ds_compare() {
  DS_DESIRED="$1" DS_JOB="$2" python3 - <<'PYEOF'
import json, os, sys

def norm(job):
    if not isinstance(job, dict):
        return {}
    p = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    sch = job.get("schedule") if isinstance(job.get("schedule"), dict) else {}
    dev = job.get("delivery") if isinstance(job.get("delivery"), dict) else {}
    expr = sch.get("expr") or (job.get("schedule") if isinstance(job.get("schedule"), str) else "") or job.get("cron") or ""
    message = p.get("message") or p.get("text") or job.get("message") or ""
    model = p.get("model") or job.get("model") or job.get("modelOverride") or ""
    thinking = p.get("thinking") or job.get("thinking") or ""
    return {
        "enabled": bool(job.get("enabled", True)) and job.get("status") != "disabled",
        "schedule": " ".join(str(expr).split()),
        "model": str(model),
        "thinking": str(thinking),
        "agent": str(job.get("agentId") or job.get("agent") or job.get("effectiveAgentId") or ""),
        "session": str(job.get("sessionTarget") or job.get("session") or ""),
        "message": str(message),
        "description": str(job.get("description") or ""),
        "declkey": str(job.get("declarationKey") or ""),
        "delivery_silent": dev.get("mode") == "none" or bool(job.get("noDeliver")) or (dev.get("mode") is None and job.get("announce") is False),
    }

try:
    desired = json.loads(os.environ["DS_DESIRED"])
    job = json.loads(os.environ["DS_JOB"])
except Exception:
    print("job-json-unreadable")
    sys.exit(0)

cur = norm(job)
out = []
for key, want in desired.items():
    if want is None:
        continue
    if key == "description":
        have = cur.get("description", "")
        missing = False
        for tok in str(want).split():
            if "=" in tok:
                k = tok.split("=", 1)[0]
                cur_tok = [t for t in have.split() if t.startswith(k + "=")]
                if not cur_tok or cur_tok[0] != tok:
                    missing = True
        if missing:
            out.append("description")
        continue
    if key == "message":
        if cur.get("message", "") != want:
            out.append("message")
        continue
    if key == "declkey":
        if want and cur.get("declkey", "") != want:
            out.append("declkey")
        continue
    if key in ("thinking", "agent", "session"):
        if want and cur.get(key, "") != want:
            out.append(key)
        continue
    if key == "model":
        # A pin is a contract: an empty stored model against a requested pin is
        # a mismatch, and so is ANY other model. Never normalized away.
        if want and cur.get("model", "") != want:
            out.append("model")
        continue
    if key == "delivery_silent":
        if bool(want) and not cur.get("delivery_silent", False):
            out.append("delivery_silent")
        continue
    if key == "enabled":
        if bool(want) != bool(cur.get("enabled", True)):
            out.append("enabled")
        continue
    if cur.get(key) != want:
        out.append(key)
print("\n".join(out))
PYEOF
}

# Desired-state JSON: a key is None (skipped) when this CLI cannot express it;
# unsupported surfaces then read back as visible mismatch, never as pass.
_desired_json() {
  DS_MODEL="" DS_THINK="" DS_SESSION="" DS_NODELIVER="" DS_DECLKEY=""
  if [ -n "$MODEL" ]; then
    if _has_add --model; then DS_MODEL="$MODEL"; fi
  fi
  if [ -n "$EFFORT" ] && _has_add --thinking; then DS_THINK="$EFFORT"; fi
  if _has_add --session || _has_edit --session; then DS_SESSION="isolated"; fi
  if _has_add --no-deliver || _has_edit --no-deliver; then DS_NODELIVER=1; fi
  if [ "$INSTALL_ID" != "unknown" ]; then DS_DECLKEY="skill75-keepalive:$INSTALL_ID"; fi
  python3 - "$CRON" "$DS_MODEL" "$DS_THINK" "$AGENT" "$DS_SESSION" "$DS_NODELIVER" "$DESC" "$DS_DECLKEY" <<'PYEOF'
import json, os, sys
cron, model, think, agent, session, nodeliver, desc, declkey = sys.argv[1:9]
print(json.dumps({
    "enabled": True,
    "schedule": " ".join(cron.split()),
    "model": model or None,
    "thinking": think or None,
    "agent": agent or None,
    "session": session or None,
    "message": os.environ.get("DS_MSG", ""),
    "description": desc,
    "declkey": declkey or None,
    "delivery_silent": bool(nodeliver),
}))
PYEOF
}

_desired_json_with_message() {
  # message is large: pass via env to keep argv small
  DS_MSG="$PROMPT" _desired_json
}

# --- attestation sink -------------------------------------------------------
ATTEST_DIR="$RUNS_DIR/.keepalive"
ATTEST_FILE="$ATTEST_DIR/install-attest.json"
ATTEST_KV=""

_attest() { ATTEST_KV="${ATTEST_KV}${ATTEST_KV:+
}$1	$2"; }

_write_attest() {  # $1 condition-observed  $2 tick-status
  [ "$MODE" = "apply" ] || return 0
  mkdir -p "$ATTEST_DIR" 2>/dev/null || { _err "WARN cannot create $ATTEST_DIR - attestation NOT written"; return 1; }
  ATTEST_CONDITION="$1" ATTEST_TICK="$2" ATTEST_KV="$ATTEST_KV" \
  ATTEST_FILE="$ATTEST_FILE" ATTEST_SCHEMA="$SCHEMA" ATTEST_NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  ATTEST_NAME="$NAME" ATTEST_MODEL="$MODEL" ATTEST_EFFORT="$EFFORT" ATTEST_AGENT="$AGENT" \
  ATTEST_PROMPT_REV="$PROMPT_REV" ATTEST_SCRIPT_REV="$SCRIPT_REV" ATTEST_SKILL_ROOT="$SKILL_ROOT" \
  ATTEST_SKILL_VER="$SKILL_VER" ATTEST_INSTALL_ID="$INSTALL_ID" ATTEST_RUNS="$RUNS_ROOT_CANON" \
  ATTEST_CRON="$CRON" ATTEST_DESC="$DESC" ATTEST_MISMATCH="$MISMATCHES" \
  python3 - <<'PYEOF'
import json, os
kv = {}
for line in os.environ.get("ATTEST_KV", "").splitlines():
    if "\t" in line:
        k, v = line.split("\t", 1)
        kv[k] = v
def jget(k, default):
    try:
        return json.loads(kv.get(k, ""))
    except Exception:
        return default
doc = {
    "schema": os.environ["ATTEST_SCHEMA"],
    "name": os.environ["ATTEST_NAME"],
    "written_at": os.environ["ATTEST_NOW"],
    "condition_observed": os.environ["ATTEST_CONDITION"],
    "installation_identity": {
        "skill_root": os.environ["ATTEST_SKILL_ROOT"],
        "skill_version": os.environ["ATTEST_SKILL_VER"],
        "install_id": os.environ["ATTEST_INSTALL_ID"],
        "installer_sha256": os.environ["ATTEST_SCRIPT_REV"],
        "prompt_sha256": os.environ["ATTEST_PROMPT_REV"],
        "runs_root": os.environ["ATTEST_RUNS"],
    },
    "requested": {
        "schedule": os.environ["ATTEST_CRON"],
        "model": os.environ["ATTEST_MODEL"],
        "effort": os.environ["ATTEST_EFFORT"] or None,
        "agent": os.environ["ATTEST_AGENT"] or None,
        "enabled": True,
        "delivery_silent": True,
    },
    "desired_description": os.environ["ATTEST_DESC"],
    "stored": jget("stored", {}),
    "effective": jget("effective", {}),
    "readback": jget("readback", {}),
    "tick": jget("tick", {}),
    "last_successful_execution": jget("lastexec", None),
    "unresolved_mismatches": [m for m in os.environ.get("ATTEST_MISMATCH", "").split(",") if m],
}
tmp = os.environ["ATTEST_FILE"] + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2, sort_keys=True)
os.replace(tmp, os.environ["ATTEST_FILE"])
PYEOF
  if [ $? -eq 0 ]; then _log "ATTEST wrote $ATTEST_FILE"; else _err "WARN attestation write failed"; return 1; fi
}

# ============================ DRY-RUN =======================================
if [ "$MODE" = "dry-run" ]; then
  _log "DRY-RUN plan (nothing registered, nothing written)."
  _log "  desired: name=$NAME schedule='$CRON' session=isolated delivery=silent(no-deliver)"
  _log "  desired: model=${MODEL:-<unrequested>} effort=${EFFORT:-<unrequested>} agent=${AGENT:-<none: box-bound default>}"
  _log "  desired: prompt_rev=$PROMPT_REV runs_dir=$RUNS_ROOT_CANON"
  _log "  reconcile keys: enabled,schedule,model,thinking,agent,session,message,description,declkey,delivery_silent"
  if [ -n "$MODEL" ] && ! _has_add --model; then
    _log "  WARN this CLI advertises no --model: a model pin CANNOT be registered - a mismatch will be left visible (no silent unpin)."
  fi
  exit 0
fi

# ============================ APPLY =========================================
ATT_CONDITION="healthy"
TICK_STATUS="not-needed"

# --- 1. tombstone: operator removal is final for this registrar -------------
if _tombstoned; then
  _log "SKIP $NAME is tombstoned (an operator removed it) - not registering."
  _attest readback '{"tombstoned": true}'
  _write_attest "operator-removal" "$TICK_STATUS"
  exit 0
fi

# --- 2. read the registry (exact name; disabled jobs visible when possible) --
JOBS_RAW="$(_list_jobs_json)"
if [ -z "$JOBS_RAW" ]; then
  _err "FAIL could not read 'cron list --json' - presence of '$NAME' UNKNOWN, NOT registering (would risk a duplicate). Re-run to backfill."
  exit 3
fi

MATCHES="$(JOBS_RAW="$JOBS_RAW" python3 - "$NAME" <<'PYEOF'
import json, os, sys
try:
    data = json.loads(os.environ["JOBS_RAW"])
except Exception:
    sys.exit(2)
jobs = data if isinstance(data, list) else data.get("jobs", [])
out = [json.dumps(j) for j in jobs if isinstance(j, dict) and j.get("name") == sys.argv[1]]
print("\n".join(out))
PYEOF
)" || { _err "FAIL cron list JSON unreadable - NOT registering."; exit 3; }

MATCH_COUNT="$(printf '%s' "$MATCHES" | grep -c . )"
MATCH_COUNT="${MATCH_COUNT:-0}"

# --- 3. duplicates under the managed name: reduce to one (each logged) ------
PRIMARY_ID=""
if [ "$MATCH_COUNT" -gt 1 ]; then
  _log "WARN $MATCH_COUNT jobs share the managed name '$NAME' - reducing to one (each removal logged below)."
  ORDERED_IDS=()
  while IFS= read -r _id; do
    [ -n "$_id" ] && ORDERED_IDS+=("$_id")
  done < <(printf '%s' "$MATCHES" | python3 -c '
import json, sys
rows = [json.loads(l) for l in sys.stdin if l.strip()]
def key(j):
    desc = str(j.get("description", ""))
    managed = 0 if "managed-by=install-keepalive-cron.sh" in desc else 1
    return (managed, j.get("createdAtMs") or 0, str(j.get("id") or ""))
rows.sort(key=key)
for j in rows:
    print(j.get("id", ""))')
  PRIMARY_ID="${ORDERED_IDS[0]:-}"
  _i=1
  while [ "$_i" -lt "${#ORDERED_IDS[@]}" ]; do
    dup="${ORDERED_IDS[$_i]}"
    _log "REMOVE duplicate $NAME id=$dup (keeping id=$PRIMARY_ID)"
    "$OPENCLAW_BIN" cron rm "$dup" >/dev/null 2>&1 \
      || _err "WARN could not remove duplicate id=$dup - REMOVE IT BY HAND: $OPENCLAW_BIN cron rm $dup"
    _i=$((_i + 1))
  done
  MATCH_COUNT=1
  [ -n "$PRIMARY_ID" ] && MATCHES="$(_job_json "$PRIMARY_ID" 2>/dev/null || printf '%s' "$MATCHES" | head -1)"
fi

# --- 4. register when absent (PINNED ONLY - never an unpinned fallback) -----
if [ "$MATCH_COUNT" -eq 0 ]; then
  if [ -n "$MODEL" ] && ! _has_add --model; then
    _add_mismatch "model-pin-unsupported-by-cli"
    _err "MISMATCH model '$MODEL' requested but this CLI advertises no --model: registering unpinned would be a silent unpin - NOT registering. KEEPALIVE_PIN_UNSUPPORTED"
    _write_attest "register-refused-pin-unsupported" "not-needed"
    exit 3
  fi
  ADD_ARGS=(--name "$NAME" --cron "$CRON" --message "$PROMPT" --description "$DESC")
  [ -n "$AGENT" ] && ADD_ARGS+=(--agent "$AGENT")
  _has_add --no-deliver && ADD_ARGS+=(--no-deliver)
  _has_add --session && ADD_ARGS+=(--session isolated)
  _has_add --declaration-key && ADD_ARGS+=(--declaration-key "skill75-keepalive:$INSTALL_ID")
  [ -n "$MODEL" ] && ADD_ARGS+=(--model "$MODEL")
  [ -n "$EFFORT" ] && _has_add --thinking && ADD_ARGS+=(--thinking "$EFFORT")
  _log "REGISTER $NAME ($CRON, silent, agent=${AGENT:-box-bound default}, model=${MODEL:-unrequested})"
  ADD_OUT="$("$OPENCLAW_BIN" cron add "${ADD_ARGS[@]}" 2>&1)"
  ADD_RC=$?
  if [ "$ADD_RC" -ne 0 ]; then
    _err "FAIL 'cron add' rc=$ADD_RC. KEEPALIVE_REGISTER_FAILED. Tail: $(printf '%s' "$ADD_OUT" | tail -2)"
    if [ -n "$MODEL" ]; then
      _err "MISMATCH requested model '$MODEL' was NOT registered. NOT retrying unpinned - a silent unpin would claim a model the job does not run (D22). KEEPALIVE_PIN_MISMATCH"
      _add_mismatch "pinned-registration-failed:$MODEL"
    fi
    _write_attest "register-failed" "not-needed"
    exit 3
  fi
  # readback right away; a command that returned 0 must still land
  sleep 1
  MATCHES="$(JOBS_RAW="$(_list_jobs_json)" python3 - "$NAME" <<'PYEOF'
import json, os, sys
data = json.loads(os.environ["JOBS_RAW"])
jobs = data if isinstance(data, list) else data.get("jobs", [])
print("\n".join(json.dumps(j) for j in jobs if isinstance(j, dict) and j.get("name") == sys.argv[1]))
PYEOF
)"
  MATCH_COUNT="$(printf '%s' "$MATCHES" | grep -c . )"
  MATCH_COUNT="${MATCH_COUNT:-0}"
  if [ "$MATCH_COUNT" -eq 0 ]; then
    _err "FAIL '$NAME' did not land after cron add (rc=0 but absent on readback). NOT retrying. KEEPALIVE_REGISTER_FAILED"
    _write_attest "register-not-landed" "not-needed"
    exit 3
  fi
  ATT_CONDITION="registered"
fi

if [ -z "$PRIMARY_ID" ]; then
  PRIMARY_ID="$(printf '%s' "$MATCHES" | head -1 | python3 -c 'import json,sys;print(json.loads(sys.stdin.readline()).get("id",""))')"
fi
JOB_JSON="$(printf '%s' "$MATCHES" | head -1)"

# --- 5. desired-state reconciliation ---------------------------------------
DESIRED="$(_desired_json_with_message)"
DRIFT="$(DS_DESIRED="$DESIRED" DS_JOB="$JOB_JSON" _ds_compare "$DESIRED" "$JOB_JSON")"

if [ -n "$DRIFT" ]; then
  _log "DRIFT detected on $NAME id=$PRIMARY_ID: $(printf '%s' "$DRIFT" | tr '\n' ' ')"
  ATT_CONDITION="drift-repaired"
  EDIT_ARGS=()
  while IFS= read -r key; do
    case "$key" in
      enabled)
        if _has_edit --enable; then EDIT_ARGS+=(--enable); else _add_mismatch "enabled-edit-unsupported"; fi ;;
      schedule)
        if _has_edit --cron; then EDIT_ARGS+=(--cron "$CRON"); else _add_mismatch "schedule-edit-unsupported"; fi ;;
      model)
        if _has_edit --model; then
          EDIT_ARGS+=(--model "$MODEL")
        else
          _add_mismatch "model-drift:$MODEL"
          _err "MISMATCH job model differs from requested '$MODEL' and this CLI cannot edit it. NOT clearing the pin, NOT recreating silently. KEEPALIVE_PIN_MISMATCH"
        fi ;;
      thinking)
        if _has_edit --thinking; then EDIT_ARGS+=(--thinking "$EFFORT"); else _add_mismatch "effort-unsupported"; fi ;;
      agent)
        if _has_edit --agent; then EDIT_ARGS+=(--agent "$AGENT"); else _add_mismatch "agent-edit-unsupported"; fi ;;
      session)
        if _has_edit --session; then EDIT_ARGS+=(--session isolated); else _add_mismatch "session-edit-unsupported"; fi ;;
      delivery_silent)
        if _has_edit --no-deliver; then EDIT_ARGS+=(--no-deliver); else _add_mismatch "no-deliver-unsupported"; fi ;;
      message)
        _log "REPAIR message/root prompt_rev=$PROMPT_REV"
        if ! "$OPENCLAW_BIN" cron edit "$PRIMARY_ID" --message "$PROMPT" >/dev/null 2>&1; then
          _add_mismatch "message-edit-refused"
          _err "MISMATCH 'cron edit --message' refused (prompt/root drift stays visible). KEEPALIVE_EDIT_REFUSED message"
        fi ;;
      description)
        _log "REPAIR description bundle (prompt_rev/runs_dir/identity)"
        if ! "$OPENCLAW_BIN" cron edit "$PRIMARY_ID" --description "$DESC" >/dev/null 2>&1; then
          _add_mismatch "description-edit-refused"
          _err "MISMATCH 'cron edit --description' refused (revision/root drift stays visible). KEEPALIVE_EDIT_REFUSED description"
        fi ;;
      declkey)
        _add_mismatch "declkey-drift"
        _err "MISMATCH declaration key drifted on id=$PRIMARY_ID - identity is set at add and cannot be edited in place. NOT recreating silently. KEEPALIVE_DECLKEY_MISMATCH" ;;
      job-json-unreadable)
        _add_mismatch "job-json-unreadable"
        _err "FAIL could not normalize job JSON for id=$PRIMARY_ID" ;;
    esac
  done <<< "$DRIFT"
  if [ "${#EDIT_ARGS[@]}" -gt 0 ]; then
    _log "REPAIR ${EDIT_ARGS[*]}"
    EDIT_OUT="$("$OPENCLAW_BIN" cron edit "$PRIMARY_ID" "${EDIT_ARGS[@]}" 2>&1)"
    if [ $? -ne 0 ]; then
      _add_mismatch "edit-refused:${EDIT_ARGS[*]}"
      _err "MISMATCH 'cron edit' refused for: ${EDIT_ARGS[*]} - owned/unsupported edit NOT bypassed, NOT looped on, NOT replaced with a duplicate job. Tail: $(printf '%s' "$EDIT_OUT" | tail -2)"
      _err "  repair through the scheduler's supported owner path, or by hand: $OPENCLAW_BIN cron edit $PRIMARY_ID <flags>"
    fi
  fi
fi

# --- 6. READBACK: stored vs desired, and stored vs effective identity -------
sleep 1
RB_JSON="$(_job_json "$PRIMARY_ID" 2>/dev/null || true)"
if [ -z "$RB_JSON" ]; then
  _err "FAIL readback could not fetch job id=$PRIMARY_ID - reconciliation NOT proven. KEEPALIVE_READBACK_MISMATCH"
  _add_mismatch "readback-fetch-failed"
  _attest stored "$JOB_JSON"
  _attest readback '{"fetched": false}'
  _write_attest "readback-unproven" "not-needed"
  exit 3
fi
DRIFT2="$(DS_DESIRED="$DESIRED" DS_JOB="$RB_JSON" _ds_compare "$DESIRED" "$RB_JSON")"
if [ -n "$DRIFT2" ]; then
  while IFS= read -r key; do
    [ -n "$key" ] || continue
    _add_mismatch "readback:$key"
    _err "  KEEPALIVE_READBACK_MISMATCH $key (requested vs effective kept visible)"
  done <<< "$DRIFT2"
  _err "MISMATCH after repair (readback still differs): $(printf '%s' "$DRIFT2" | tr '\n' ' ')"
  ATT_CONDITION="readback-mismatch"
fi

EFF_JSON="$(printf '%s' "$RB_JSON" | python3 -c '
import json,sys
j=json.load(sys.stdin)
p=j.get("payload") if isinstance(j.get("payload"),dict) else {}
out={
 "id": j.get("id"),
 "name": j.get("name"),
 "declarationKey": j.get("declarationKey"),
 "effectiveAgentId": j.get("effectiveAgentId"),
 "enabled": j.get("enabled"),
 "status": j.get("status"),
 "configRevision": j.get("configRevision"),
 "model_effective": p.get("model") or j.get("model") or j.get("modelOverride"),
 "thinking_effective": p.get("thinking") or j.get("thinking"),
 "sessionTarget": j.get("sessionTarget"),
 "nextRunAtMs": j.get("nextRunAtMs"),
}
print(json.dumps(out))')"
LASTEXEC_JSON="$(printf '%s' "$RB_JSON" | python3 -c '
import json,sys
j=json.load(sys.stdin)
st=j.get("state") if isinstance(j.get("state"),dict) else {}
print(json.dumps({
 "lastRunAtMs": st.get("lastRunAtMs") or j.get("lastRunAtMs"),
 "lastRunStatus": st.get("lastRunStatus") or j.get("lastRunStatus"),
 "consecutiveErrors": st.get("consecutiveErrors"),
 "nextRunAtMs": st.get("nextRunAtMs") or j.get("nextRunAtMs"),
}))')"

# --- 7. prove ONE successful observation tick -------------------------------
TICK_NEED=0
case "$ATT_CONDITION" in registered|drift-repaired) TICK_NEED=1 ;; esac
[ "$FORCE_TICK" = "1" ] && TICK_NEED=1
if printf '%s' "$LASTEXEC_JSON" | python3 -c '
import json,sys
d=json.load(sys.stdin)
sys.exit(0 if (d.get("lastRunStatus") == "ok" and not d.get("consecutiveErrors")) else 1)'; then
  :
else
  TICK_NEED=1
fi

TICK_JSON='{"proven": false, "method": "none"}'
if [ "$TICK_NEED" = "1" ]; then
  if "$OPENCLAW_BIN" cron run --help >/dev/null 2>&1; then
    BEFORE_MS="$(printf '%s' "$LASTEXEC_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("lastRunAtMs") or 0)')"
    _log "TICK requesting one observation tick ($OPENCLAW_BIN cron run $PRIMARY_ID) and waiting for scheduler state..."
    "$OPENCLAW_BIN" cron run "$PRIMARY_ID" >/dev/null 2>&1 || true
    TICK_JSON="$(BEFORE_MS="$BEFORE_MS" TICK_JID="$PRIMARY_ID" OPENCLAW_BIN="$OPENCLAW_BIN" python3 - <<'PYEOF'
import json, os, subprocess, time
before = int(os.environ.get("BEFORE_MS") or 0)
jid = os.environ["TICK_JID"]
bin_ = os.environ.get("OPENCLAW_BIN", "openclaw")
deadline = time.time() + 90
last = {"proven": False, "method": "cron run + scheduler state readback"}
while time.time() < deadline:
    try:
        raw = subprocess.run([bin_, "cron", "get", jid, "--json"], capture_output=True, text=True, timeout=20).stdout
        j = json.loads(raw)
        st = j.get("state") if isinstance(j.get("state"), dict) else {}
        last = {
            "proven": bool((st.get("lastRunAtMs") or 0) > before and (st.get("lastRunStatus") or "") == "ok"),
            "method": "cron run + scheduler state readback",
            "lastRunAtMs": st.get("lastRunAtMs") or j.get("lastRunAtMs"),
            "lastRunStatus": st.get("lastRunStatus") or j.get("lastRunStatus"),
            "consecutiveErrors": st.get("consecutiveErrors"),
        }
        if last["proven"]:
            break
    except Exception:
        pass
    time.sleep(3)
print(json.dumps(last))
PYEOF
)"
    if printf '%s' "$TICK_JSON" | python3 -c 'import json,sys;sys.exit(0 if json.load(sys.stdin).get("proven") else 1)'; then
      TICK_STATUS="proven"
      _log "TICK proven: one successful observation tick observed on $NAME."
    else
      TICK_STATUS="unproven"
      _add_mismatch "tick-unproven"
      _err "MISMATCH no successful observation tick proven within 90s of the change. KEEPALIVE_TICK_UNPROVEN (job present but health unproven)"
    fi
  else
    TICK_STATUS="unsupported-by-cli"
    _add_mismatch "tick-unsupported-by-cli"
    _err "MISMATCH this CLI has no 'cron run' - a changed registration cannot be tick-proven here. KEEPALIVE_TICK_UNPROVEN"
  fi
else
  TICK_STATUS="not-needed-last-exec-ok"
  _log "TICK no change and last execution healthy - attesting scheduler's last successful execution instead."
fi

# --- 8. attestation: requested vs stored vs effective -----------------------
_attest stored "$JOB_JSON"
_attest effective "$EFF_JSON"
_attest readback "{\"fetched\": true, \"drift_after_repair\": $( [ -n "${DRIFT2:-}" ] && echo true || echo false )}"
_attest tick "$TICK_JSON"
_attest lastexec "$LASTEXEC_JSON"

if [ -n "$MISMATCHES" ]; then
  _err "DONE-WITH-MISMATCHES $NAME: unresolved: $MISMATCHES (requested/effective kept visible - never claimed as honored)"
  _write_attest "$ATT_CONDITION" "$TICK_STATUS"
  exit 3
fi

case "$ATT_CONDITION" in
  registered)     ATT_CONDITION="healthy-registered" ;;
  drift-repaired) ATT_CONDITION="healthy-after-repair" ;;
esac
EFF_AGENT="$(printf '%s' "$EFF_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("effectiveAgentId") or "box-bound default")')"
EFF_MODEL="$(printf '%s' "$EFF_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("model_effective") or "unrequested/unpinned")')"
_log "DONE $NAME reconciled ($CRON, silent, agent=$EFF_AGENT, model=$EFF_MODEL, tick=$TICK_STATUS)"
_write_attest "$ATT_CONDITION" "$TICK_STATUS"
exit 0
