#!/usr/bin/env bash
# ============================================================================
# podcast-publish-roll.sh  (S58 podcast publish-proxy fleet roll)
#
# Rolls the five Podbean publish-proxy values onto an EXPLICIT list of boxes:
#
#   PODBEAN_PUBLISH_WEBHOOK_URL   n8n publish-proxy webhook (fleet-shared, non-secret)
#   PODBEAN_PUBLISH_TOKEN         shared proxy header token (SECRET, never printed)
#   PODCAST_CLIENT_LAST_NAME      per-client roster identity (with email)
#   PODCAST_CLIENT_EMAIL          per-client roster identity (with last name)
#   PODCAST_CLIENT_FIRST_NAME     display only, never authorization
#
# into BOTH config stores on each box (the same two stores install.sh S58-U15
# seeds and the operator-box proven pass used):
#   env store:   ~/.openclaw/secrets/.env        (Mac / local)
#                /data/.openclaw/secrets/.env    (VPS container)
#                /docker/<project>/.env          (VPS host canonical, so a later
#                                                 force-recreate re-exports the
#                                                 values into the container env;
#                                                 same convention as
#                                                 propagate-rescue-webhook.sh)
#   json store:  <openclaw home>/openclaw.json   env.vars block
#
# then RESTARTS the gateway (the values are invisible to running agents until
# restart; the rescue-webhook template deliberately skipped this, this script
# does not), VERIFIES the restart and the landed values, and runs ONE dry-run
# wiring test call: a POST to the podcast-standing-check n8n endpoint (the same
# read-only pre-check probe scripts/podbean_publish.sh --dry-run uses). The
# test call publishes NOTHING.
#
# MODELED ON: ~/clawd/fleet-heartbeat/scripts/propagate-rescue-webhook.sh
# (operator-local rescue-webhook fan-out), with these deliberate differences:
#   1. NO embedded roster. Targets come ONLY from --targets FILE. The script
#      can never fan out wider than the rows it is handed.
#   2. Gateway restart is MANDATORY in real mode. Mac: launchctl kickstart, then
#      a stop-and-let-launchd-relaunch fallback -- launchctl ONLY, never
#      `openclaw gateway restart` (see mac_restart_payload). VPS: docker compose
#      up -d --force-recreate. Every restart is verified by a PID change AND a
#      health probe; a box whose gateway does not come back is reported with an
#      explicit GATEWAY_DOWN=MANUAL-INTERVENTION-REQUIRED marker.
#   3. ATOMIC config writes (temp file + rename) with surfaced errors and
#      restore-from-backup on any failure. Closes the known non-atomic
#      json.dump defect in install.sh's _shared_write_ocjson.
#   4. CREDENTIAL SAFETY DIFF: after writing, the backup and the new file are
#      compared with the five podcast keys filtered out. ANY other difference
#      restores the backups and fails the box. The roll can therefore never
#      touch, re-initialise, or clear any other credential.
#   5. Per-box PASS/FAIL JSONL ledger written as the run progresses.
#
# TARGETS FILE (pipe-separated; # comments and blank lines ignored):
#   slug|type|address|container|compose_dir|first_name|last_name|email
#     type=vps    address=IP, ssh root@IP; container + compose_dir required
#     type=mac    address=ssh alias from ~/.ssh/config (cloudflared tunnel);
#                 container and compose_dir are "-"
#     type=local  operator box only (slug must be blackceomacmini); address "-"
#   See podcast-roll-targets.example.txt. The REAL targets file carries client
#   identity values, so it lives operator-local and is NEVER committed.
#
# SHARED VALUES: PODBEAN_PUBLISH_WEBHOOK_URL and PODBEAN_PUBLISH_TOKEN are read
# from the operator's own env store (~/.openclaw/secrets/.env) at run time,
# exactly like install.sh reads OPENCLAW_PODBEAN_PUBLISH_URL/TOKEN. Neither is
# ever printed; the token never rides in argv (base64 over ssh stdin only).
#
# USAGE:
#   podcast-publish-roll.sh --targets FILE [--dry-run] [--yes] [--only SLUG]
#                           [--ledger-dir DIR] [--webhook-url URL]
#                           [--max-boxes N] [--skip-test-call]
#
#   --dry-run        precheck + report what WOULD change + wiring test call;
#                    writes nothing, restarts nothing.
#   --yes            REQUIRED for a real (writing) run. Without it the script
#                    prints the plan and refuses. This is the arming pin.
#   --only SLUG      restrict the run to one slug from the targets file.
#   --max-boxes N    refuse to run if the targets file has more rows (default 15).
#
# HARD RULES:
#   - Never prints, echoes, or logs a secret value. SET / NOT-SET only.
#   - Never re-initialises or overwrites any non-podcast credential (enforced
#     by the credential safety diff, not just intended).
#   - Never aborts the whole batch on one box failure: record and continue.
#   - Bounded foreground polling only; every loop has a hard iteration cap.
#   - Idempotent: a re-run against a correct box is an exact-match no-op on
#     both stores (byte-identical files; proven on the operator box).
#   - No em dashes in output. Slugs only, never client names.
# ============================================================================
set -u
set -o pipefail

# The five keys this roll owns (the remote payload hardcodes the full list;
# NOTHING else is ever written). K_URL / K_TOK are also used by the VPS host
# env writer, which carries only the fleet-shared pair.
K_URL="PODBEAN_PUBLISH_WEBHOOK_URL"
K_TOK="PODBEAN_PUBLISH_TOKEN"

TS="$(date -u +%Y%m%d-%H%M%S)"
SSH_KEY="${SSH_KEY:-${HOME}/.ssh/id_ed25519}"
VPS_SSH_OPTS=(-i "${SSH_KEY}" -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=15 -o ServerAliveCountMax=8 -o UserKnownHostsFile="${HOME}/.ssh/known_hosts")
MAC_SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=25 -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=15 -o ServerAliveCountMax=8)
OPERATOR_SECRETS_ENV="${HOME}/.openclaw/secrets/.env"

TARGETS_FILE=""
DRY_RUN=0
ARMED=0
ONLY_SLUG=""
LEDGER_DIR="${HOME}/clawd/podcast-roll/ledgers"
WEBHOOK_URL_OVERRIDE=""
MAX_BOXES=15
SKIP_TEST_CALL=0

log()  { printf '%s %s\n' "[$(date -u +%H:%M:%SZ)]" "$*"; }
err()  { printf '%s %s\n' "[$(date -u +%H:%M:%SZ)] ERROR:" "$*" >&2; }
die()  { err "$*"; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --targets)        TARGETS_FILE="${2:-}"; shift 2 ;;
    --dry-run)        DRY_RUN=1; shift ;;
    --yes)            ARMED=1; shift ;;
    --only)           ONLY_SLUG="${2:-}"; shift 2 ;;
    --ledger-dir)     LEDGER_DIR="${2:-}"; shift 2 ;;
    --webhook-url)    WEBHOOK_URL_OVERRIDE="${2:-}"; shift 2 ;;
    --max-boxes)      MAX_BOXES="${2:-}"; shift 2 ;;
    --skip-test-call) SKIP_TEST_CALL=1; shift ;;
    -h|--help)        grep '^#' "$0" | sed 's/^# \{0,1\}//' | sed -n '1,80p'; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[ -n "${TARGETS_FILE}" ]   || die "--targets FILE is required (explicit target list; this script never auto-discovers boxes)"
[ -f "${TARGETS_FILE}" ]   || die "targets file not found: ${TARGETS_FILE}"
[ -s "${TARGETS_FILE}" ]   || die "targets file is empty: ${TARGETS_FILE}"
case "${MAX_BOXES}" in ''|*[!0-9]*) die "--max-boxes must be a number" ;; esac

# ---- shared values from the operator env store (values never printed) -------
# Targeted extraction only. NEVER blanket-source the secrets env: it carries
# PATH and HOME overrides that would hijack command resolution and ~/.ssh
# lookups (found live on the operator box). The Mac tunnel ProxyCommands in
# ~/.ssh/config source their own service tokens, so nothing else is needed.
[ -f "${OPERATOR_SECRETS_ENV}" ] || die "operator env store missing: ${OPERATOR_SECRETS_ENV}"
env_value() { # $1=key -> value with one optional layer of quotes stripped
  local line v
  line="$(grep -m1 "^$1=" "${OPERATOR_SECRETS_ENV}" 2>/dev/null || true)"
  [ -n "$line" ] || return 0
  v="${line#*=}"
  case "$v" in
    \'*\') v="${v#\'}"; v="${v%\'}" ;;
    \"*\") v="${v#\"}"; v="${v%\"}" ;;
  esac
  printf '%s' "$v"
}
PP_URL="${WEBHOOK_URL_OVERRIDE:-$(env_value "${K_URL}")}"
PP_TOK="$(env_value "${K_TOK}")"
[ -n "${PP_URL}" ] || die "${K_URL} is NOT-SET in the operator env and no --webhook-url given (both-or-neither doctrine; refusing)"
[ -n "${PP_TOK}" ] || die "${K_TOK} is NOT-SET in the operator env (both-or-neither doctrine; refusing)"
[[ "${PP_URL}" =~ ^https://[^[:space:]]+$ ]] || die "webhook URL is not a clean https URL"
log "shared values: ${K_URL}=SET ${K_TOK}=SET (values never printed)"

# ---- parse + validate the target list (fail-closed, no auto-discovery) ------
ROWS=()
SEEN_SLUGS=" "
while IFS= read -r line || [ -n "$line" ]; do
  line="${line%%$'\r'}"
  [ -z "$line" ] && continue
  case "$line" in \#*) continue ;; esac
  IFS='|' read -r slug btype addr container compose_dir first last email <<< "$line"
  [ -n "${slug:-}" ] && [ -n "${btype:-}" ] || die "malformed targets row (need slug|type|address|container|compose_dir|first|last|email): row starting '${slug:-?}'"
  [[ "$slug" =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "bad slug shape: '${slug}'"
  case "${SEEN_SLUGS}" in *" ${slug} "*) die "duplicate slug in targets: ${slug}" ;; esac
  SEEN_SLUGS="${SEEN_SLUGS}${slug} "
  case "$btype" in
    vps)   [ -n "${addr:-}" ] && [ -n "${container:-}" ] && [ -n "${compose_dir:-}" ] || die "vps row ${slug}: address, container, compose_dir all required" ;;
    mac)   [ -n "${addr:-}" ] || die "mac row ${slug}: ssh alias required in address column" ;;
    local) [ "$slug" = "blackceomacmini" ] || die "type local is allowed only for slug blackceomacmini (operator box), got: ${slug}" ;;
    *)     die "row ${slug}: type must be vps, mac, or local (got '${btype}')" ;;
  esac
  # Identity guards, mirroring install.sh S58-U15: last+email required together,
  # email must look like an email with no whitespace; first name required here
  # because the roll spec injects all five values.
  [ -n "${first:-}" ] && [ -n "${last:-}" ] && [ -n "${email:-}" ] || die "row ${slug}: first, last, and email are all required (fill from the live publish roster)"
  case "$email" in
    *[[:space:]]*) die "row ${slug}: email contains whitespace; refusing (would only ever be refused by the n8n gate)" ;;
    *@*.*) : ;;
    *) die "row ${slug}: email does not look like an email address; refusing" ;;
  esac
  case "${first}${last}" in *[[:space:]]*) die "row ${slug}: identity values must not contain whitespace (the env store writes unquoted VAR=val lines, matching install.sh)" ;; esac
  if [ -n "${ONLY_SLUG}" ] && [ "${slug}" != "${ONLY_SLUG}" ]; then continue; fi
  ROWS+=("${slug}|${btype}|${addr}|${container}|${compose_dir}|${first}|${last}|${email}")
done < "${TARGETS_FILE}"

[ "${#ROWS[@]}" -gt 0 ] || die "no target rows selected (check --only value against the targets file)"
[ "${#ROWS[@]}" -le "${MAX_BOXES}" ] || die "targets file selects ${#ROWS[@]} boxes which exceeds --max-boxes ${MAX_BOXES}; refusing (runaway fan-out guard)"

log "plan: ${#ROWS[@]} box(es), mode=$([ "${DRY_RUN}" = "1" ] && echo dry-run || echo REAL)"
for row in "${ROWS[@]}"; do log "  target: ${row%%|*} ($(printf '%s' "$row" | cut -d'|' -f2))"; done

if [ "${DRY_RUN}" != "1" ] && [ "${ARMED}" != "1" ]; then
  die "REAL mode requires --yes (the arming pin). Re-run with --dry-run to rehearse, or add --yes to write."
fi

mkdir -p "${LEDGER_DIR}" || die "cannot create ledger dir ${LEDGER_DIR}"
LEDGER="${LEDGER_DIR}/podcast-roll-${TS}.jsonl"
: > "${LEDGER}" || die "cannot write ledger ${LEDGER}"
chmod 600 "${LEDGER}" 2>/dev/null || true
log "ledger: ${LEDGER}"

b64() { printf '%s' "$1" | base64 | tr -d '\n'; }

# Values ride to the box as base64 inside the ssh stdin script: never in argv
# (ps-safe), never expanded into logged text.
PP_URL_B64="$(b64 "${PP_URL}")"
PP_TOK_B64="$(b64 "${PP_TOK}")"

# ---------------------------------------------------------------------------
# remote_payload: emits the per-box POSIX-sh payload. Runs directly on Mac and
# local boxes, and INSIDE the container on VPS boxes. All inputs arrive as
# exported env vars (set by the wrapper): RTS, RMODE (dry|real), ENV_FILE,
# JSON_FILE, DO_TEST (0/1), and B64_* for the five values. Emits stable
# KEY=VALUE marker lines the operator side parses; never a secret value.
# ---------------------------------------------------------------------------
remote_payload() {
cat <<'PAYLOAD'
set -u
um="$(umask)"; umask 077
fail() { echo "REMOTE-ERROR: $*" >&2; echo "RESULT=FAIL"; exit 1; }
dec() { printf '%s' "$1" | base64 -d 2>/dev/null || printf '%s' "$1" | base64 -D; }

V_URL="$(dec "${B64_URL}")";   V_TOK="$(dec "${B64_TOK}")"
V_FIRST="$(dec "${B64_FIRST}")"; V_LAST="$(dec "${B64_LAST}")"; V_EMAIL="$(dec "${B64_EMAIL}")"
[ -n "${V_URL}" ] && [ -n "${V_TOK}" ] && [ -n "${V_LAST}" ] && [ -n "${V_EMAIL}" ] || fail "value decode failed"

KEYS="PODBEAN_PUBLISH_WEBHOOK_URL PODBEAN_PUBLISH_TOKEN PODCAST_CLIENT_FIRST_NAME PODCAST_CLIENT_LAST_NAME PODCAST_CLIENT_EMAIL"
val_for() {
  case "$1" in
    PODBEAN_PUBLISH_WEBHOOK_URL) printf '%s' "${V_URL}" ;;
    PODBEAN_PUBLISH_TOKEN)       printf '%s' "${V_TOK}" ;;
    PODCAST_CLIENT_FIRST_NAME)   printf '%s' "${V_FIRST}" ;;
    PODCAST_CLIENT_LAST_NAME)    printf '%s' "${V_LAST}" ;;
    PODCAST_CLIENT_EMAIL)        printf '%s' "${V_EMAIL}" ;;
  esac
}

# ---- channel id lookup helpers (BOTH config stores) -------------------------
# PODBEAN_PODCAST_ID can live in EITHER store. The publisher reads it from the
# PROCESS environment, which the gateway populates from openclaw.json env.vars
# at start, so a box whose id lives only in the json store is fully provisioned
# and must not be skipped. Consulting only ${ENV_FILE} false-SKIPs those boxes.
#
# PRECEDENCE: openclaw.json env.vars WINS over the env store, because env.vars
# is what the gateway actually injects into the publisher process environment
# at runtime; that is the value production really uses.
#
# DISAGREEMENT is NOT silently resolved. Two stores holding different ids means
# the box is misconfigured, so both fingerprints are printed and the box FAILS
# loudly (a plain REMOTE-ERROR, not a "precheck:" one, so the operator side
# buckets it as FAIL rather than SKIP). The id value itself is never printed.
env_lookup() { # $1=key -> value from ENV_FILE, one optional quote layer stripped
  l="$(grep -m1 "^$1=" "${ENV_FILE}" 2>/dev/null || true)"
  [ -n "$l" ] || return 0
  v="${l#*=}"
  case "$v" in
    \'*\') v="${v#\'}"; v="${v%\'}" ;;
    \"*\") v="${v#\"}"; v="${v%\"}" ;;
  esac
  printf '%s' "$v"
}
json_lookup() { # $1=key -> value from openclaw.json env.vars ("" if absent)
  # same reader json_state() below uses; nonzero exit if the store is unreadable.
  jq -r --arg k "$1" '.env.vars[$k] // ""' "${JSON_FILE}" 2>/dev/null
}
idhash() { # short one-way fingerprint; the id value itself is NEVER printed
  if command -v sha256sum >/dev/null 2>&1; then printf '%s' "$1" | sha256sum | cut -c1-8
  elif command -v shasum >/dev/null 2>&1; then printf '%s' "$1" | shasum -a 256 | cut -c1-8
  else printf 'hash-unavailable'; fi
}

# ---- precheck ---------------------------------------------------------------
command -v jq   >/dev/null 2>&1 || fail "precheck: jq missing on this box"
command -v curl >/dev/null 2>&1 || echo "PRECHECK_CURL=NOT-PRESENT"
[ -f "${ENV_FILE}" ]  || fail "precheck: env store missing at ${ENV_FILE}"
[ -f "${JSON_FILE}" ] || fail "precheck: json store missing at ${JSON_FILE}"
jq -e . "${JSON_FILE}" >/dev/null 2>&1 || fail "precheck: json store is not valid JSON (refusing to touch a corrupt file)"
CID_ENV="$(env_lookup PODBEAN_PODCAST_ID)"
CID_JSON="$(json_lookup PODBEAN_PODCAST_ID)" || fail "precheck: could not read env.vars from ${JSON_FILE} (cannot tell whether this box is provisioned; failing closed)"
if [ -n "${CID_ENV}" ] && [ -n "${CID_JSON}" ]; then
  if [ "${CID_ENV}" = "${CID_JSON}" ]; then CID_SRC="both-agree"; else CID_SRC="both-DISAGREE"; fi
elif [ -n "${CID_JSON}" ]; then CID_SRC="json"
elif [ -n "${CID_ENV}" ]; then CID_SRC="env"
else CID_SRC="none"
fi
echo "PRECHECK_CHANNEL_ID_SOURCE=${CID_SRC}"
if [ "${CID_SRC}" = "none" ]; then
  echo "PRECHECK_CHANNEL_ID=NOT-SET"
  fail "precheck: PODBEAN_PODCAST_ID is NOT-SET in EITHER store (env store and openclaw.json env.vars both empty; box not podcast-provisioned; skip)"
fi
echo "PRECHECK_CHANNEL_ID=SET"
if [ "${CID_SRC}" = "both-DISAGREE" ]; then
  echo "PRECHECK_CHANNEL_ID_ENV_HASH=$(idhash "${CID_ENV}")"
  echo "PRECHECK_CHANNEL_ID_JSON_HASH=$(idhash "${CID_JSON}")"
  fail "PODBEAN_PODCAST_ID DISAGREES between the env store and openclaw.json env.vars (fingerprints above; values never printed). The gateway injects the json value at start, so the stores are inconsistent; refusing to guess which channel is live"
fi
# json env.vars wins (runtime authority); the env store is the fallback.
if [ -n "${CID_JSON}" ]; then CHANNEL_ID="${CID_JSON}"; else CHANNEL_ID="${CID_ENV}"; fi
echo "PRECHECK=OK"

# ---- current-state comparison (drives no-op detection and dry-run report) ---
# env line convention is unquoted VAR=val (install.sh _shared_write_env). A
# pre-existing quoted line with the same inner value counts as already-correct
# and is left byte-identical.
env_state() { # $1=key -> already|append|replace
  k="$1"; want="$(val_for "$k")"
  line="$(grep -m1 "^${k}=" "${ENV_FILE}" 2>/dev/null || true)"
  [ -n "$line" ] || { echo append; return; }
  cur="${line#*=}"
  case "$cur" in
    \'*\') cur="${cur#\'}"; cur="${cur%\'}" ;;
    \"*\") cur="${cur#\"}"; cur="${cur%\"}" ;;
  esac
  [ "$cur" = "$want" ] && echo already || echo replace
}
json_state() { # $1=key -> already|write
  k="$1"; want="$(val_for "$k")"
  cur="$(jq -r --arg k "$k" '.env.vars[$k] // ""' "${JSON_FILE}" 2>/dev/null)" || fail "jq read failed on ${JSON_FILE}"
  [ "$cur" = "$want" ] && echo already || echo write
}

ENV_DIRTY=0; JSON_DIRTY=0
for k in $KEYS; do
  es="$(env_state "$k")"; js="$(json_state "$k")"
  [ "$es" = "already" ] || ENV_DIRTY=1
  [ "$js" = "already" ] || JSON_DIRTY=1
  echo "STATE ${k} env=${es} json=${js}"
done
echo "ENV_CHANGED=${ENV_DIRTY}"
echo "JSON_CHANGED=${JSON_DIRTY}"

if [ "${RMODE}" = "dry" ]; then
  echo "DRY_RUN=1 (no writes, no restart)"
else
  # ---- backup before write (only files that will change) --------------------
  ENV_BAK=""; JSON_BAK=""
  if [ "${ENV_DIRTY}" = "1" ]; then
    ENV_BAK="${ENV_FILE}.bak-pre-podcast-roll-${RTS}"
    cp -p "${ENV_FILE}" "${ENV_BAK}" || fail "backup of env store failed"
  fi
  if [ "${JSON_DIRTY}" = "1" ]; then
    JSON_BAK="${JSON_FILE}.bak-pre-podcast-roll-${RTS}"
    cp -p "${JSON_FILE}" "${JSON_BAK}" || fail "backup of json store failed"
  fi
  restore() {
    [ -n "${ENV_BAK}" ]  && [ -f "${ENV_BAK}" ]  && cp -p "${ENV_BAK}"  "${ENV_FILE}"
    [ -n "${JSON_BAK}" ] && [ -f "${JSON_BAK}" ] && cp -p "${JSON_BAK}" "${JSON_FILE}"
  }

  # ---- env store write: atomic (temp + rename), errors surfaced -------------
  if [ "${ENV_DIRTY}" = "1" ]; then
    TMPE="${ENV_FILE}.tmp.$$"
    grep -vE "^(PODBEAN_PUBLISH_WEBHOOK_URL|PODBEAN_PUBLISH_TOKEN|PODCAST_CLIENT_FIRST_NAME|PODCAST_CLIENT_LAST_NAME|PODCAST_CLIENT_EMAIL)=" "${ENV_FILE}" > "${TMPE}"
    grc=$?
    [ "$grc" -le 1 ] || { rm -f "${TMPE}"; restore; fail "env filter failed (grep rc=${grc}); original untouched"; }
    for k in $KEYS; do printf '%s=%s\n' "$k" "$(val_for "$k")" >> "${TMPE}" || { rm -f "${TMPE}"; restore; fail "env append failed"; }; done
    for k in $KEYS; do grep -qxF "${k}=$(val_for "$k")" "${TMPE}" || { rm -f "${TMPE}"; restore; fail "env temp verification failed for ${k}"; }; done
    chmod 600 "${TMPE}" 2>/dev/null || true
    mv "${TMPE}" "${ENV_FILE}" || { rm -f "${TMPE}"; restore; fail "atomic rename of env store failed"; }
    echo "ENV_WRITE=OK"
  else
    echo "ENV_WRITE=NOOP"
  fi

  # ---- json store write: atomic via jq to temp + validate + rename ----------
  if [ "${JSON_DIRTY}" = "1" ]; then
    TMPJ="${JSON_FILE}.tmp.$$"
    jq --arg u "${V_URL}" --arg t "${V_TOK}" --arg f "${V_FIRST}" --arg l "${V_LAST}" --arg e "${V_EMAIL}" '
      .env = (.env // {}) | .env.vars = (.env.vars // {}) |
      .env.vars.PODBEAN_PUBLISH_WEBHOOK_URL = $u |
      .env.vars.PODBEAN_PUBLISH_TOKEN = $t |
      .env.vars.PODCAST_CLIENT_FIRST_NAME = $f |
      .env.vars.PODCAST_CLIENT_LAST_NAME = $l |
      .env.vars.PODCAST_CLIENT_EMAIL = $e
    ' "${JSON_FILE}" > "${TMPJ}" || { rm -f "${TMPJ}"; restore; fail "jq patch of json store failed; original untouched"; }
    [ -s "${TMPJ}" ] || { rm -f "${TMPJ}"; restore; fail "jq produced an empty json store; original untouched"; }
    jq -e . "${TMPJ}" >/dev/null 2>&1 || { rm -f "${TMPJ}"; restore; fail "patched json store failed validation; original untouched"; }
    chmod 600 "${TMPJ}" 2>/dev/null || true
    mv "${TMPJ}" "${JSON_FILE}" || { rm -f "${TMPJ}"; restore; fail "atomic rename of json store failed"; }
    echo "JSON_WRITE=OK"
  else
    echo "JSON_WRITE=NOOP"
  fi

  # ---- credential safety diff: NOTHING but the five keys may differ ---------
  CS=OK
  if [ -n "${ENV_BAK}" ]; then
    A="/tmp/pcr-a.$$"; B="/tmp/pcr-b.$$"
    grep -vE "^(PODBEAN_PUBLISH_WEBHOOK_URL|PODBEAN_PUBLISH_TOKEN|PODCAST_CLIENT_FIRST_NAME|PODCAST_CLIENT_LAST_NAME|PODCAST_CLIENT_EMAIL)=" "${ENV_BAK}" > "$A" 2>/dev/null
    grep -vE "^(PODBEAN_PUBLISH_WEBHOOK_URL|PODBEAN_PUBLISH_TOKEN|PODCAST_CLIENT_FIRST_NAME|PODCAST_CLIENT_LAST_NAME|PODCAST_CLIENT_EMAIL)=" "${ENV_FILE}" > "$B" 2>/dev/null
    cmp -s "$A" "$B" || CS=ENV-DRIFT
    rm -f "$A" "$B"
  fi
  if [ "${CS}" = "OK" ] && [ -n "${JSON_BAK}" ]; then
    A="/tmp/pcr-ja.$$"; B="/tmp/pcr-jb.$$"
    jq -S 'del(.env.vars.PODBEAN_PUBLISH_WEBHOOK_URL, .env.vars.PODBEAN_PUBLISH_TOKEN, .env.vars.PODCAST_CLIENT_FIRST_NAME, .env.vars.PODCAST_CLIENT_LAST_NAME, .env.vars.PODCAST_CLIENT_EMAIL)' "${JSON_BAK}" > "$A" 2>/dev/null
    jq -S 'del(.env.vars.PODBEAN_PUBLISH_WEBHOOK_URL, .env.vars.PODBEAN_PUBLISH_TOKEN, .env.vars.PODCAST_CLIENT_FIRST_NAME, .env.vars.PODCAST_CLIENT_LAST_NAME, .env.vars.PODCAST_CLIENT_EMAIL)' "${JSON_FILE}" > "$B" 2>/dev/null
    cmp -s "$A" "$B" || CS=JSON-DRIFT
    rm -f "$A" "$B"
  fi
  if [ "${CS}" != "OK" ]; then
    restore
    echo "CRED_SAFETY=${CS}"
    fail "credential safety diff detected a non-podcast change (${CS}); backups restored, box FAILED"
  fi
  echo "CRED_SAFETY=OK"

  # ---- post-write verification: read back both stores -----------------------
  for k in $KEYS; do
    [ "$(env_state "$k")" = "already" ]  || { restore; fail "post-write verify: ${k} did not land in env store"; }
    [ "$(json_state "$k")" = "already" ] || { restore; fail "post-write verify: ${k} did not land in json store"; }
  done
  echo "VERIFY_STORES=OK"
fi

# ---- wiring test call (both modes): read-only standing-check probe ----------
# Same probe scripts/podbean_publish.sh --dry-run uses: POST identity + channel
# id to the podcast-standing-check webhook with the shared header token. The
# endpoint is a roster lookup; nothing is published. Token rides in a curl
# config read from stdin, never argv.
if [ "${DO_TEST}" = "1" ] && command -v curl >/dev/null 2>&1; then
  # CHANNEL_ID was resolved in the precheck from BOTH stores (json env.vars wins,
  # env store is the fallback). Do NOT re-read only ${ENV_FILE} here: that read
  # is what false-skipped json-only boxes.
  STAND_URL="${V_URL%/webhook/podbean-publish}/webhook/podcast-standing-check"
  BODY="$(jq -cn --arg l "${V_LAST}" --arg e "${V_EMAIL}" --arg p "${CHANNEL_ID}" '{client_last_name:$l, client_email:$e} + (if $p != "" then {podcast_id:$p} else {} end)')"
  RESP="/tmp/pcr-resp.$$"
  HTTP_CODE="$(printf 'header = "X-Podcast-Publish-Token: %s"\n' "${V_TOK}" | curl -s -m 25 -K - -X POST -H "Content-Type: application/json" --data-binary "${BODY}" -o "${RESP}" -w '%{http_code}' "${STAND_URL}" 2>/dev/null || echo 000)"
  GOOD="$(jq -r '.good_standing // empty' "${RESP}" 2>/dev/null || true)"
  rm -f "${RESP}"
  echo "TEST_HTTP=${HTTP_CODE}"
  echo "TEST_GOOD_STANDING=${GOOD:-unknown}"
  case "${HTTP_CODE}" in 2*) echo "TEST_CALL=PASS" ;; *) echo "TEST_CALL=FAIL" ;; esac
elif [ "${DO_TEST}" = "1" ]; then
  echo "TEST_CALL=SKIPPED (curl missing)"
else
  echo "TEST_CALL=SKIPPED (flag)"
fi

umask "$um"
echo "RESULT=OK"
PAYLOAD
}

# ---------------------------------------------------------------------------
# restart payloads
# ---------------------------------------------------------------------------
mac_restart_payload() {
cat <<'RESTART'
set -u
GW_LABEL="ai.openclaw.gateway"
GW_HEALTH_URL="http://127.0.0.1:18789/health"

gw_pid() { launchctl list 2>/dev/null | awk -v l="${GW_LABEL}" '$3==l{print $1}'; }

# Did the process ACTUALLY restart? Bounded poll; sets NEW_PID / PID_CHANGED.
# A gateway that never restarted has NOT loaded the new values, so "something
# answers the health port" is not sufficient evidence of a successful roll.
poll_pid() {
  i=0; NEW_PID=""; PID_CHANGED=0
  while [ "$i" -lt 12 ]; do
    sleep 5
    NEW_PID="$(gw_pid)"
    case "${NEW_PID}" in
      ""|-) ;;
      *) case "${OLD_PID}" in
           ""|-) PID_CHANGED=1; break ;;
           *) [ "${NEW_PID}" != "${OLD_PID}" ] && { PID_CHANGED=1; break; } ;;
         esac ;;
    esac
    i=$((i+1))
  done
}

# Health needs its OWN bounded poll: the process appears (new PID) seconds
# before the port binds, so a single probe right after the PID flip can catch
# the gap and report a false FAIL (observed live on the operator box).
poll_health() {
  HEALTH=""; HEALTH_OK=0
  j=0
  while [ "$j" -lt 12 ]; do
    HEALTH="$(curl -s -m 5 "${GW_HEALTH_URL}" 2>/dev/null || true)"
    case "${HEALTH}" in *'"ok":true'*) HEALTH_OK=1; break ;; esac
    sleep 5
    j=$((j+1))
  done
}

# SAFE RESTART METHODS ONLY: launchctl kickstart, then a stop fallback that
# lets launchd relaunch the job. `openclaw gateway restart` is deliberately NOT
# used here: on 2026-06-08 that exact command took a Mac gateway DOWN and LEFT
# IT DOWN, and its output was discarded so the failure was invisible. It also
# adds no capability launchd does not already have -- if launchd owns the job,
# kickstart restarts it; if launchd does not, the CLI can only start a gateway
# outside supervision with nothing to relaunch it. The proven fleet reference
# (~/clawd/fleet-heartbeat/scripts/propagate-rescue-webhook.sh) restarts Macs
# with launchctl only.
kickstart_gw() { # echoes rc + any launchctl diagnostic, never a secret
  KOUT="$(launchctl kickstart -k "gui/$(id -u)/${GW_LABEL}" 2>&1)"; KRC=$?
  [ -n "${KOUT}" ] && echo "RESTART_LAUNCHCTL_OUT=$(printf '%s' "${KOUT}" | tr '\n' ' ')"
  return "${KRC}"
}

OLD_PID="$(gw_pid)"
echo "GATEWAY_OLD_PID=${OLD_PID:-none}"

kickstart_gw; rc=$?
if [ "$rc" -eq 0 ]; then
  echo "RESTART_METHOD=kickstart"
else
  # ANY nonzero kickstart rc falls back to stop-and-let-launchd-relaunch. The
  # old chain only did this for rc 125/126 and routed every other rc (e.g. 3,
  # "no such service") straight to the gateway-killer CLI path.
  echo "RESTART_METHOD=stop-fallback (kickstart rc=${rc})"
  SOUT="$(launchctl stop "${GW_LABEL}" 2>&1)"; rc=$?
  [ -n "${SOUT}" ] && echo "RESTART_LAUNCHCTL_OUT=$(printf '%s' "${SOUT}" | tr '\n' ' ')"
  echo "RESTART_STOP_RC=${rc}"
fi

# Never exit on the restart rc alone: a nonzero rc may still have killed the
# running gateway, so the box must be verified (and recovered) either way.
poll_pid
poll_health
echo "GATEWAY_NEW_PID=${NEW_PID:-none}"
echo "GATEWAY_PID_CHANGED=${PID_CHANGED}"

# One bounded recovery kickstart before declaring the box down or unrestarted.
if [ "${HEALTH_OK}" != "1" ] || [ "${PID_CHANGED}" != "1" ]; then
  echo "RESTART_RECOVERY=attempting (pid_changed=${PID_CHANGED} health_ok=${HEALTH_OK})"
  kickstart_gw; rrc=$?
  echo "RESTART_RECOVERY_RC=${rrc}"
  poll_pid
  poll_health
  echo "GATEWAY_NEW_PID=${NEW_PID:-none}"
  echo "GATEWAY_PID_CHANGED=${PID_CHANGED}"
fi

if [ "${HEALTH_OK}" = "1" ] && [ "${PID_CHANGED}" = "1" ]; then
  echo "GATEWAY_HEALTH=live"
  echo "RESTART=OK"
elif [ "${HEALTH_OK}" = "1" ]; then
  # The gateway answers, but it is the SAME process that was running before:
  # it never reloaded config, so the five podcast values are NOT live. This
  # used to be scored RESTART=OK, which reported PASS on an unrolled box.
  echo "GATEWAY_HEALTH=live"
  echo "RESTART=FAIL (gateway process never restarted: pid unchanged at ${NEW_PID:-none}; new values are NOT loaded)"
  exit 1
else
  echo "GATEWAY_HEALTH=${HEALTH:-none}"
  echo "GATEWAY_DOWN=MANUAL-INTERVENTION-REQUIRED"
  echo "RESTART=FAIL (GATEWAY DOWN - MANUAL INTERVENTION REQUIRED: no ok:true from ${GW_HEALTH_URL} after the restart chain and one recovery kickstart)"
  exit 1
fi
RESTART
}

# ---------------------------------------------------------------------------
# per-box drivers. Each returns 0 on PASS, nonzero on FAIL/SKIP; parsed marker
# lines are appended to the ledger. set +e discipline: one box never kills the
# batch.
# ---------------------------------------------------------------------------
ledger_append() { # slug type mode result reason markers_file
  local slug="$1" btype="$2" mode="$3" result="$4" reason="$5" markers="$6"
  jq -cn \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg slug "$slug" --arg type "$btype" --arg mode "$mode" \
    --arg result "$result" --arg reason "$reason" \
    --arg markers "$(cat "$markers")" \
    '{ts:$ts, slug:$slug, type:$type, mode:$mode, result:$result, reason:$reason,
      markers:($markers | split("\n") | map(select(length>0 and (startswith("REMOTE-ERROR") or test("^(PRECHECK|STATE|ENV_|JSON_|HOST_ENV|CRED_SAFETY|VERIFY|TEST_|RESULT|RESTART|GATEWAY_|RUNTIME_ENV|DRY_RUN)")))))}' \
    >> "${LEDGER}"
}

# Common env preamble shipped ahead of the payload (values as base64; the
# heredoc rides ssh stdin so nothing appears in argv).
payload_env() { # $1=RMODE $2=ENV_FILE $3=JSON_FILE $4=first_b64 $5=last_b64 $6=email_b64
  printf 'export RTS="%s" RMODE="%s" ENV_FILE="%s" JSON_FILE="%s" DO_TEST="%s"\n' \
    "${TS}" "$1" "$2" "$3" "$([ "${SKIP_TEST_CALL}" = "1" ] && echo 0 || echo 1)"
  printf 'export B64_URL="%s" B64_TOK="%s" B64_FIRST="%s" B64_LAST="%s" B64_EMAIL="%s"\n' \
    "${PP_URL_B64}" "${PP_TOK_B64}" "$4" "$5" "$6"
}

run_local_box() { # slug first_b64 last_b64 email_b64 -> markers in $MARKERS
  local mode="$1" f="$2" l="$3" e="$4"
  {
    payload_env "${mode}" "${HOME}/.openclaw/secrets/.env" "${HOME}/.openclaw/openclaw.json" "$f" "$l" "$e"
    remote_payload
    if [ "${mode}" = "real" ]; then mac_restart_payload; fi
  } | bash -s > "${MARKERS}" 2>&1
}

run_mac_box() { # alias mode f l e
  local alias="$1" mode="$2" f="$3" l="$4" e="$5"
  {
    # HOME differs per box: emit the env preamble with remote-side expansion.
    printf 'export RTS="%s" RMODE="%s" DO_TEST="%s"\n' "${TS}" "${mode}" "$([ "${SKIP_TEST_CALL}" = "1" ] && echo 0 || echo 1)"
    printf 'export ENV_FILE="${HOME}/.openclaw/secrets/.env" JSON_FILE="${HOME}/.openclaw/openclaw.json"\n'
    printf 'export B64_URL="%s" B64_TOK="%s" B64_FIRST="%s" B64_LAST="%s" B64_EMAIL="%s"\n' \
      "${PP_URL_B64}" "${PP_TOK_B64}" "$f" "$l" "$e"
    remote_payload
    if [ "${mode}" = "real" ]; then mac_restart_payload; fi
  } | ssh "${MAC_SSH_OPTS[@]}" "${alias}" "zsh -lc 'bash -s'" > "${MARKERS}" 2>&1
}

run_vps_box() { # ip container compose_dir mode f l e
  local ip="$1" container="$2" compose_dir="$3" mode="$4" f="$5" l="$6" e="$7"
  local inner host_script
  inner="$( { echo 'set -u'; remote_payload; } )"
  host_script="$(cat <<HOST
set -u
CONTAINER="${container}"
COMPOSE_DIR="${compose_dir}"
RMODE="${mode}"
HB64_URL="${PP_URL_B64}"
HB64_TOK="${PP_TOK_B64}"
docker inspect -f '{{.State.Running}}' "\${CONTAINER}" 2>/dev/null | grep -q true || { echo "REMOTE-ERROR: container not running"; echo "RESULT=FAIL"; exit 1; }

# host .env (canonical Hostinger env store; same convention as the rescue
# webhook fan-out): backup + atomic rewrite of ONLY the fleet-shared pair.
# Values arrive base64 and are decoded host-side; never in argv, never echoed.
# Identity keys are box-local runtime config; host .env carries only the URL
# and token so a later force-recreate re-exports them into the container env.
HV_URL="\$(printf '%s' "\${HB64_URL}" | base64 -d)"
HV_TOK="\$(printf '%s' "\${HB64_TOK}" | base64 -d)"
[ -n "\${HV_URL}" ] && [ -n "\${HV_TOK}" ] || { echo "REMOTE-ERROR: host value decode failed"; echo "RESULT=FAIL"; exit 1; }
HOST_ENV="\${COMPOSE_DIR}/.env"
if [ "\${RMODE}" = "real" ]; then
  [ -f "\${HOST_ENV}" ] || { echo "REMOTE-ERROR: host env store missing at \${HOST_ENV}"; echo "RESULT=FAIL"; exit 1; }
  NEEDED=0
  grep -qxF "${K_URL}=\${HV_URL}" "\${HOST_ENV}" || NEEDED=1
  grep -qxF "${K_TOK}=\${HV_TOK}" "\${HOST_ENV}" || NEEDED=1
  if [ "\${NEEDED}" = "1" ]; then
    cp -p "\${HOST_ENV}" "\${HOST_ENV}.bak-pre-podcast-roll-${TS}" || { echo "REMOTE-ERROR: host env backup failed"; echo "RESULT=FAIL"; exit 1; }
    TMPH="\${HOST_ENV}.tmp.\$\$"
    grep -vE "^(${K_URL}|${K_TOK})=" "\${HOST_ENV}" > "\${TMPH}"; grc=\$?
    [ "\$grc" -le 1 ] || { rm -f "\${TMPH}"; echo "REMOTE-ERROR: host env filter failed"; echo "RESULT=FAIL"; exit 1; }
    printf '%s=%s\n' "${K_URL}" "\${HV_URL}" >> "\${TMPH}"
    printf '%s=%s\n' "${K_TOK}" "\${HV_TOK}" >> "\${TMPH}"
    grep -qxF "${K_URL}=\${HV_URL}" "\${TMPH}" || { rm -f "\${TMPH}"; echo "REMOTE-ERROR: host env temp verification failed"; echo "RESULT=FAIL"; exit 1; }
    # credential safety: nothing but the two keys may differ from the backup
    grep -vE "^(${K_URL}|${K_TOK})=" "\${HOST_ENV}.bak-pre-podcast-roll-${TS}" > "/tmp/pcr-ha.\$\$" 2>/dev/null
    grep -vE "^(${K_URL}|${K_TOK})=" "\${TMPH}" > "/tmp/pcr-hb.\$\$" 2>/dev/null
    if ! cmp -s "/tmp/pcr-ha.\$\$" "/tmp/pcr-hb.\$\$"; then
      rm -f "\${TMPH}" "/tmp/pcr-ha.\$\$" "/tmp/pcr-hb.\$\$"
      echo "REMOTE-ERROR: host env credential safety diff failed; original untouched"; echo "RESULT=FAIL"; exit 1
    fi
    rm -f "/tmp/pcr-ha.\$\$" "/tmp/pcr-hb.\$\$"
    chmod 600 "\${TMPH}" 2>/dev/null || true
    mv "\${TMPH}" "\${HOST_ENV}" || { rm -f "\${TMPH}"; echo "REMOTE-ERROR: host env atomic rename failed"; echo "RESULT=FAIL"; exit 1; }
    echo "HOST_ENV=WRITTEN"
  else
    echo "HOST_ENV=NOOP"
  fi
else
  echo "HOST_ENV=DRY-SKIP"
fi

# container payload over docker stdin (argv shows only sh -s; values ride stdin)
docker exec -i -u node "\${CONTAINER}" sh -s <<'INNERWRAP'
$(payload_env "${mode}" "/data/.openclaw/secrets/.env" "/data/.openclaw/openclaw.json" "$f" "$l" "$e")
${inner}
INNERWRAP
prc=\$?
[ "\$prc" -eq 0 ] || { echo "RESULT=FAIL"; exit "\$prc"; }

if [ "\${RMODE}" = "real" ]; then
  echo "RESTART_METHOD=compose-force-recreate"
  # A container that never restarted is still "running", so "running" alone can
  # never prove a restart. Two independent proofs are REQUIRED here:
  #   1. docker compose exited 0. Its status is CAPTURED, never piped away.
  #   2. the container ID CHANGED. --force-recreate always builds a NEW
  #      container, so an unchanged ID means the OLD container, carrying the OLD
  #      config, is still the one serving.
  # Then the new value must be reachable by the new gateway (process env or the
  # json store inside the NEW container) or the box FAILS.
  OLD_CID="\$(docker inspect -f '{{.Id}}' "\${CONTAINER}" 2>/dev/null || true)"
  printf 'RESTART_CONTAINER_OLD_ID=%.12s\n' "\${OLD_CID:-none}"
  CUP_OUT="/tmp/pcr-compose.\$\$"
  ( cd "\${COMPOSE_DIR}" && docker compose up -d --force-recreate ) > "\${CUP_OUT}" 2>&1
  crc=\$?
  tail -4 "\${CUP_OUT}"; rm -f "\${CUP_OUT}"
  echo "RESTART_COMPOSE_RC=\${crc}"
  if [ "\${crc}" -ne 0 ]; then
    echo "RESTART=FAIL (docker compose up -d --force-recreate exited rc=\${crc}; container NOT recreated, OLD config still live)"
    echo "RESULT=FAIL"; exit 1
  fi
  i=0; RUNNING=false; NEW_CID=""
  while [ "\$i" -lt 12 ]; do
    sleep 5
    NEW_CID="\$(docker inspect -f '{{.Id}}' "\${CONTAINER}" 2>/dev/null || true)"
    RUNNING="\$(docker inspect -f '{{.State.Running}}' "\${CONTAINER}" 2>/dev/null || echo false)"
    if [ "\${RUNNING}" = "true" ] && [ -n "\${NEW_CID}" ] && [ "\${NEW_CID}" != "\${OLD_CID}" ]; then break; fi
    i=\$((i+1))
  done
  printf 'RESTART_CONTAINER_NEW_ID=%.12s\n' "\${NEW_CID:-none}"
  if [ "\${RUNNING}" != "true" ]; then
    echo "RESTART=FAIL (container not running after bounded poll)"; echo "RESULT=FAIL"; exit 1
  fi
  if [ -z "\${NEW_CID}" ] || [ "\${NEW_CID}" = "\${OLD_CID}" ]; then
    echo "RESTART=FAIL (container id unchanged after force-recreate; the OLD container is still running with the OLD config)"
    echo "RESULT=FAIL"; exit 1
  fi
  # Proof the value reached the NEW container. Either load path is sufficient:
  # the process env (host .env re-exported by the recreate) or the json store
  # env.vars block the gateway reads at load. NEITHER present means the recreate
  # did not carry the value (for example a non-persistent /data volume), which
  # is exactly the silent failure this roll exists to prevent.
  RUNTIME_OK=0
  if docker exec -u node "\${CONTAINER}" printenv ${K_URL} >/dev/null 2>&1; then
    echo "RUNTIME_ENV=${K_URL}=SET"; RUNTIME_OK=1
  else
    echo "RUNTIME_ENV=${K_URL}=NOT-SET"
  fi
  if docker exec -u node "\${CONTAINER}" sh -c 'jq -e ".env.vars.${K_URL} // empty" /data/.openclaw/openclaw.json' >/dev/null 2>&1; then
    echo "RUNTIME_ENV_JSON=${K_URL}=SET"; RUNTIME_OK=1
  else
    echo "RUNTIME_ENV_JSON=${K_URL}=NOT-SET"
  fi
  if [ "\${RUNTIME_OK}" -ne 1 ]; then
    echo "RESTART=FAIL (new container carries ${K_URL} in NEITHER its process env NOR its json store; the value did not survive the recreate)"
    echo "RESULT=FAIL"; exit 1
  fi
  echo "RESTART=OK"
fi
HOST
)"
  printf '%s\n' "${host_script}" | ssh "${VPS_SSH_OPTS[@]}" "root@${ip}" "bash -s" > "${MARKERS}" 2>&1
}

# ---------------------------------------------------------------------------
# main loop: one box at a time, record and continue
# ---------------------------------------------------------------------------
PASS_LIST=""; FAIL_LIST=""; SKIP_LIST=""; PARTIAL_LIST=""; GWDOWN_LIST=""
MODE_LABEL="$([ "${DRY_RUN}" = "1" ] && echo dry || echo real)"

for row in "${ROWS[@]}"; do
  IFS='|' read -r slug btype addr container compose_dir first last email <<< "${row}"
  MARKERS="$(mktemp "${TMPDIR:-/tmp}/pcr-markers.XXXXXX")"
  F64="$(b64 "${first}")"; L64="$(b64 "${last}")"; E64="$(b64 "${email}")"
  log "box ${slug} (${btype}): starting (${MODE_LABEL})"
  rc=0
  case "${btype}" in
    local) run_local_box "${MODE_LABEL}" "${F64}" "${L64}" "${E64}" || rc=$? ;;
    mac)   run_mac_box "${addr}" "${MODE_LABEL}" "${F64}" "${L64}" "${E64}" || rc=$? ;;
    vps)   run_vps_box "${addr}" "${container}" "${compose_dir}" "${MODE_LABEL}" "${F64}" "${L64}" "${E64}" || rc=$? ;;
  esac
  # Surface the marker lines (never contain secret values by construction).
  sed 's/^/    /' "${MARKERS}"
  if [ "${rc}" -eq 0 ] && grep -q '^RESULT=OK' "${MARKERS}"; then
    if [ "${MODE_LABEL}" = "real" ] && ! grep -q '^RESTART=OK' "${MARKERS}"; then
      log "box ${slug}: FAIL (payload ok but restart not confirmed)"
      ledger_append "${slug}" "${btype}" "${MODE_LABEL}" "FAIL" "restart-not-confirmed" "${MARKERS}"
      FAIL_LIST="${FAIL_LIST} ${slug}"
    elif grep -q '^TEST_CALL=FAIL' "${MARKERS}"; then
      # The wiring test RAN and FAILED. That is the exact symptom this roll
      # exists to clear (an HTTP 401 means the box is not authorized against the
      # publish proxy), so it can never be recorded as PASS. A deliberate skip
      # (TEST_CALL=SKIPPED, from curl missing or --skip-test-call) is NOT a
      # failure and does not match this branch.
      test_http="$(grep -m1 '^TEST_HTTP=' "${MARKERS}" | cut -d= -f2- || true)"
      if [ "${MODE_LABEL}" = "real" ]; then
        reason="wiring-test-failed (HTTP ${test_http:-none}); values written and verified but box NOT proven working"
      else
        reason="wiring-test-failed (HTTP ${test_http:-none}); dry-run, nothing was written"
      fi
      log "box ${slug}: PARTIAL (${reason})"
      ledger_append "${slug}" "${btype}" "${MODE_LABEL}" "PARTIAL" "${reason}" "${MARKERS}"
      PARTIAL_LIST="${PARTIAL_LIST} ${slug}"
    else
      log "box ${slug}: PASS"
      ledger_append "${slug}" "${btype}" "${MODE_LABEL}" "PASS" "" "${MARKERS}"
      PASS_LIST="${PASS_LIST} ${slug}"
    fi
  elif grep -q '^REMOTE-ERROR: precheck' "${MARKERS}"; then
    reason="$(grep -m1 '^REMOTE-ERROR: precheck' "${MARKERS}" | sed 's/^REMOTE-ERROR: //')"
    log "box ${slug}: SKIP (${reason})"
    ledger_append "${slug}" "${btype}" "${MODE_LABEL}" "SKIP" "${reason}" "${MARKERS}"
    SKIP_LIST="${SKIP_LIST} ${slug}"
  else
    reason="$(grep -m1 '^REMOTE-ERROR:' "${MARKERS}" | sed 's/^REMOTE-ERROR: //' || true)"
    [ -n "${reason}" ] || reason="$(grep -m1 '^RESTART=FAIL' "${MARKERS}" || true)"
    [ -n "${reason}" ] || reason="ssh or payload failure (rc=${rc})"
    if grep -q '^GATEWAY_DOWN=MANUAL-INTERVENTION-REQUIRED' "${MARKERS}"; then
      reason="GATEWAY DOWN - MANUAL INTERVENTION REQUIRED :: ${reason}"
      GWDOWN_LIST="${GWDOWN_LIST} ${slug}"
    fi
    log "box ${slug}: FAIL (${reason})"
    ledger_append "${slug}" "${btype}" "${MODE_LABEL}" "FAIL" "${reason}" "${MARKERS}"
    FAIL_LIST="${FAIL_LIST} ${slug}"
  fi
  rm -f "${MARKERS}"
done

echo
echo "==================================================================="
echo "Podcast publish-proxy roll summary (UTC ${TS})  mode=${MODE_LABEL}"
echo "  pass: ${PASS_LIST:- none}"
echo "  skip: ${SKIP_LIST:- none}"
echo "  partial: ${PARTIAL_LIST:- none}  (stores written, wiring test FAILED, box NOT proven)"
echo "  fail: ${FAIL_LIST:- none}"
if [ -n "${GWDOWN_LIST}" ]; then
  echo "  !! GATEWAY DOWN - MANUAL INTERVENTION REQUIRED:${GWDOWN_LIST}"
  echo "  !! The gateway on the box(es) above did not answer ok:true after the"
  echo "  !! restart chain and one recovery kickstart. Get hands on them now."
fi
echo "  ledger: ${LEDGER}"
echo "==================================================================="
# PARTIAL is a non-success verdict: it exits nonzero exactly like FAIL, so no
# caller can read a failed wiring test as a green run. GWDOWN_LIST is a strict
# subset of FAIL_LIST (every gateway-down box is also appended to FAIL_LIST in
# the else branch above), so it needs no separate term here.
[ -z "${FAIL_LIST}${PARTIAL_LIST}" ] || exit 2
exit 0
