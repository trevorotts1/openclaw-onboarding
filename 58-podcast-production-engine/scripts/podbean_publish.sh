#!/usr/bin/env bash
#
# podbean_publish.sh
# Podcast Production Engine, Step 15: publish one produced episode to the
# client's Podbean channel (their show under BlackCEO's single host account)
# and capture the permalink.
#
# CREDENTIAL MODEL (read this first): BlackCEO HOSTS every client's show under
# his ONE Podbean account, so the Podbean OAuth app client_id/client_secret are
# BlackCEO's SINGLE shared app - never the client's, never asked from the client.
# The ONLY per-client Podbean value is the Channel ID (PODBEAN_PODCAST_ID), which
# selects the show and is not a secret. THREE modes, selected per box, tried in
# this precedence order - PROXY, then BROKER, then LOCAL:
#   PROXY (fleet default as of the publish-proxy fix): PODBEAN_PUBLISH_WEBHOOK_URL
#     + PODBEAN_PUBLISH_TOKEN are set; this box holds NO Podbean app secret and
#     does NOT upload media to Podbean itself. It POSTs a JSON payload (identity,
#     title, description, the ALREADY-HOSTED audio_url/image_url from Step 14, and
#     an idempotency_key) to the operator's n8n publish workflow, which mints its
#     own Channel-scoped token, downloads the media, uploads it, creates the
#     episode, and returns the permalink synchronously. This also carries the
#     good-standing + identity gate server-side (n8n-side units, not this script).
#     Endpoint (non-secret): https://main.blackceoautomations.com/webhook/podbean-publish
#   BROKER (dormant fallback; kept for back-compat): PODBEAN_BROKER_WEBHOOK_URL +
#     PODBEAN_BROKER_TOKEN are set; this box holds NO Podbean app secret. The n8n
#     Podbean credential broker (config/n8n/podbean-broker.workflow.json) mints a
#     Channel-scoped access token server-side and returns it; THIS box still does
#     the media upload + episode create itself. Nothing to leak here.
#   LOCAL (operator's OWN box fallback only): PODBEAN_CLIENT_ID + PODBEAN_CLIENT_SECRET
#     resolve from the operator env and this script mints the token directly.
# Precedence: if the PROXY pair is set it always wins, regardless of whether the
# BROKER pair or LOCAL credentials also happen to be set on the box. Unset PROXY
# entirely and behavior falls through to BROKER, then LOCAL, exactly as before
# this fix (regression-proven; see scripts/tests/test_podbean_publish_proxy.py).
#
# PROXY MODE PAYLOAD CONTRACT (v2 - the operator's n8n workflow TkL0rn2SH3q32SeB,
# webhook POST https://main.blackceoautomations.com/webhook/podbean-publish):
#   Required: contract_version="2", podcast_id, client_last_name, client_email,
#     title (RAW - the base title; n8n appends "Inspired by <speaker>" itself,
#     this script does NOT pre-append it in proxy mode), description, audio_url,
#     image_url (both must be public HTTPS URLs - GHL Media Library is the
#     default host, Step 14 already uploads and HEAD-verifies there), publish_date
#     (ISO 8601 with time), idempotency_key (stable per episode-job; defaults to
#     --job-id when --idempotency-key is not given).
#   Optional: client_first_name, episode_type (full/trailer/bonus, default full),
#     explicit (clean/explicit, default clean), speaker, season_number, source.
#   Auth: header X-Podcast-Publish-Token: <PODBEAN_PUBLISH_TOKEN>, never in argv.
#   Response (synchronous): 200 {"ok":true,"permalink_url",...}; 403 reason
#     not_in_good_standing / identity_unknown / identity_mismatch; 409 in_flight;
#     422 invalid_payload; 500 publish_failed. See the master spec Section 3 for
#     the full contract (not duplicated in full here to avoid drift).
#
# Design references:
#   PRD.md Section 5, Step 15 (canonical 18-step pipeline)
#   35-social-media-planner/references/playbook.md Section 15 (the proven
#     Podbean flow, here productionized into direct Podbean API calls instead
#     of the legacy n8n webhook)
#   design/webhook-design.md Section 3.4 (double-publish guard: re-read the
#     ledger and skip when podbean_permalink is already set)
#   design/ghl-design.md Section (preconditions: publish precedes link-back;
#     the permalink written to contact.podcast_survey_episode_url is Step 16,
#     owned by the Convert and Flow field layer, NOT by this script)
#
# What this script does (and only this):
#   1. Idempotency guard. If the job ledger already holds a permalink, skip
#      the whole publish and re-emit the existing permalink.
#   2. Obtain a Channel-scoped OAuth access token: from the n8n Podbean broker
#      (broker mode, BlackCEO's shared app stays in n8n) or, on the operator's
#      own box only, via a local client_credentials mint.
#   3. Isolation check (local mode): confirm the target podcast_id belongs to the
#      host account (never commingle, never publish to another channel). In broker
#      mode the broker mints a token already scoped to the requested Channel ID.
#   4. Episode number = existing episode count + 1.
#   5. Authorize and upload the mastered MP3 (and the finalized cover) via
#      files/uploadAuthorize plus a presigned PUT.
#   6. Create the episode: title appends "Inspired by" plus the speaker name;
#      status publish, or scheduled (Podbean status future with a
#      publish_timestamp) when the release date is in the future.
#   7. Capture the permalink and record it through podcast_state.py (the sole
#      state writer) when available; always emit a machine-readable result.
#
# Verified Podbean API shapes (OpenAPI plus a working client_credentials
# reference client; live token-header and endpoint probe belongs to Wave 0.5
# and the canary where real client credentials exist):
#   POST https://api.podbean.com/v1/oauth/token          (HTTP Basic, form grant_type=client_credentials)
#   GET  https://api.podbean.com/v1/podcasts             (?access_token=...)
#   GET  https://api.podbean.com/v1/episodes             (?access_token=...&offset=0&limit=1 -> .count)
#   GET  https://api.podbean.com/v1/files/uploadAuthorize(?access_token=...&content_type=...&filename=...&filesize=...)
#        -> { presigned_url, file_key, expire_at }; then PUT the bytes to presigned_url
#   POST https://api.podbean.com/v1/episodes             (?access_token=...; form title,content,status,type,
#        media_key,logo_key,episode_number[,publish_timestamp]) -> { episode: { permalink_url, id, ... } }
#
# HARD RULES honored here:
#   - Never print, echo, or log a secret value. Credentials are referenced by
#     label only; access tokens and presigned URLs are passed to curl through
#     an in-memory config (process substitution with builtin printf), never in
#     argv (no ps exposure) and never on disk. Any diagnostic text is redacted.
#   - MOVE IN SILENCE: this script emits operator-facing diagnostics on stderr
#     and one machine-readable JSON result on stdout only. It sends zero
#     client-facing messages (no SMS, email, Telegram, or workflow enrollment).
#   - No em dash characters and no triple backtick fences anywhere, including
#     in the emitted JSON result.
#   - This script makes no language-model call at all, so it ships no build-time
#     model id, provider, package, key, or host; the runtime-model guard passes
#     by construction.
#
set -euo pipefail

# Production endpoint. PODBEAN_API_BASE exists only so the canary and the test
# harness can point the same code at a mock; unset in production it is the real
# Podbean API, so shipped behavior is unchanged.
readonly PODBEAN_API="${PODBEAN_API_BASE:-https://api.podbean.com/v1}"
readonly RETRIES=3
readonly CURL_MAX_TIME=180

# ------------------------------------------------------------------ logging --
# stderr is the operator channel. Secret values are never passed here.
log()  { printf '%s podbean_publish %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }
die()  { log "ERROR: $*"; exit 1; }

# Redact known secret substrings from any text before it is shown. The secret
# values themselves are only used as a replacement target, never printed.
redact() {
  local s="$1"
  [ -n "${PODBEAN_CLIENT_ID:-}" ]     && s="${s//${PODBEAN_CLIENT_ID}/[REDACTED_CLIENT_ID]}"
  [ -n "${PODBEAN_CLIENT_SECRET:-}" ] && s="${s//${PODBEAN_CLIENT_SECRET}/[REDACTED_CLIENT_SECRET]}"
  [ -n "${PODBEAN_BROKER_TOKEN:-}" ]  && s="${s//${PODBEAN_BROKER_TOKEN}/[REDACTED_BROKER_TOKEN]}"
  [ -n "${ACCESS_TOKEN:-}" ]          && s="${s//${ACCESS_TOKEN}/[REDACTED_TOKEN]}"
  printf '%s' "$s"
}

# ------------------------------------------------------------------- helpers --
usage() {
  cat >&2 <<'USAGE'
Usage: podbean_publish.sh --audio <mp3> --title <base title> [options]

Required environment (values are never printed):
  PODBEAN_PODCAST_ID      the client's Podbean Channel ID (podcast_id) - the ONLY
                          per-client Podbean value; selects the show under
                          BlackCEO's single host account; not a secret. Required
                          in ALL THREE modes.
  Then, in precedence order, the FIRST fully-set pair below selects the mode:
  1) PROXY (fleet default): PODBEAN_PUBLISH_WEBHOOK_URL + PODBEAN_PUBLISH_TOKEN
     (server-side publish; this box uploads nothing to Podbean). ALSO required:
     PODCAST_CLIENT_LAST_NAME + PODCAST_CLIENT_EMAIL (the identity gate lookup
     key on the operator's roster); PODCAST_CLIENT_FIRST_NAME is optional
     (display/email only). In this mode --audio-url and --image-url (public
     HTTPS URLs, not local paths) are also required arguments - see below.
  2) BROKER (dormant fallback): PODBEAN_BROKER_WEBHOOK_URL + PODBEAN_BROKER_TOKEN
  3) LOCAL (operator's OWN box fallback only - BlackCEO's SINGLE shared app):
     PODBEAN_CLIENT_ID + PODBEAN_CLIENT_SECRET

Required arguments:
  --audio <path>          mastered MP3 to publish (must exist); in proxy mode
                          this is used only for local bookkeeping/content-type,
                          NOT uploaded from this box - pass --audio-url too
  --title <text>          base episode title (immutable from the blueprint step)

Proxy-mode-only required arguments (contract v2; ignored in broker/local mode):
  --audio-url <url>        public HTTPS URL to the already-hosted mastered MP3
                          (Step 14's GHL Media Library upload, or a Google Drive
                          direct-download fallback)
  --image-url <url>        public HTTPS URL to the already-hosted cover image

Proxy-mode-only optional arguments:
  --idempotency-key <key>  stable per-episode-job key; defaults to --job-id
  --episode-type <value>   full | trailer | bonus (default full; Podbean feed type,
                          distinct from --type below)
  --explicit <value>       clean | explicit (default clean)
  --season-number <n>      passed through to Podbean if present

Common options:
  --cover <path>          finalized cover image (jpeg or png); becomes logo_key
                          in broker/local mode; ignored in proxy mode (use
                          --image-url instead)
  --speaker <name>        speaker or guest name; broker/local mode appends
                          "Inspired by <name>" to the title itself; proxy mode
                          sends it as a separate field and n8n appends it once
  --description <text>    show notes (plain text or html, kept under 3000 chars)
  --release-date <when>   contact.date_for_release (ISO 8601 or unix seconds);
                          a future value schedules the episode instead of publishing now
  --status <value>        force publish | draft | future (default derives from --release-date;
                          broker/local mode only)
  --type <value>          public | premium | private (default public; Podbean
                          privacy type, broker/local mode only)

Idempotency and state (Step 15 double-publish guard):
  --ledger <path>         job ledger json; if it already holds a non-null
                          podbean_permalink, this script skips and re-emits it
  --job-id <id>           records the permalink via podcast_state.py output ...
  --state-writer <path>   path to podcast_state.py (default: sibling in this dir)
  --out <path>            also write the json result to this file

Safety:
  --test                  test run: validate and short-circuit BEFORE any Podbean
                          call (matches the ledger `test` state; never touches Podbean)
  --dry-run               broker/local mode: resolve token and episode number but
                          do not upload or create; prints the plan (used by the
                          canary to prove wiring). Proxy mode: validate the
                          contract v2 payload and print the plan WITHOUT posting
                          to the publish webhook (no network call at all).
  -h, --help              this text
USAGE
}

# filesize in bytes, portable across BSD (macOS) and GNU stat.
filesize() {
  local f="$1"
  stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null || die "cannot stat $f"
}

# Convert an ISO 8601 string or a unix-seconds value to unix seconds.
to_epoch() {
  local v="$1"
  if [[ "$v" =~ ^[0-9]+$ ]]; then printf '%s' "$v"; return 0; fi
  if date -d "$v" +%s >/dev/null 2>&1; then date -d "$v" +%s; return 0; fi
  local fmt
  for fmt in "%Y-%m-%dT%H:%M:%S" "%Y-%m-%dT%H:%M" "%Y-%m-%d %H:%M:%S" "%Y-%m-%d"; do
    if date -j -f "$fmt" "${v%%[+-][0-9][0-9]:[0-9][0-9]}" +%s >/dev/null 2>&1; then
      date -j -f "$fmt" "${v%%[+-][0-9][0-9]:[0-9][0-9]}" +%s; return 0
    fi
  done
  return 1
}

# URL-encode a single component (non-secret inputs only).
urlenc() { python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"; }

# Content type from a filename extension.
content_type_for() {
  case "${1##*.}" in
    mp3|MP3)   printf 'audio/mpeg' ;;
    m4a|M4A)   printf 'audio/mp4' ;;
    wav|WAV)   printf 'audio/wav' ;;
    jpg|jpeg|JPG|JPEG) printf 'image/jpeg' ;;
    png|PNG)   printf 'image/png' ;;
    *)         printf 'application/octet-stream' ;;
  esac
}

# Extract a value from a JSON document supplied on stdin. Args are a key path
# walked through nested objects. Kept in-memory (no here-string temp file) so a
# token-bearing body never lands on disk.
json_field() {
  python3 -c '
import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    print(""); sys.exit(0)
for k in sys.argv[1:]:
    d = d.get(k) if isinstance(d, dict) else None
    if d is None:
        break
print("" if d is None else d)
' "$@"
}

# Read one field from a ledger file (safe to touch disk; the ledger is not a secret).
ledger_field() {
  local file="$1" key="$2"
  [ -f "$file" ] || { printf ''; return 0; }
  json_field "$key" < "$file"
}

# Print the podcast ids owned by the account, one per line. Reads a
# GET /v1/podcasts json body on stdin.
podcast_ids() {
  python3 -c '
import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
for p in d.get("podcasts", []):
    if isinstance(p, dict) and p.get("id") is not None:
        print(p["id"])
'
}

# Print the access token scoped to a target podcast id, tolerating both
# documented multiplePodcastsToken shapes (a list under podcast_tokens, or a
# map keyed by podcast id). Reads the json body on stdin; target id is arg 1.
scoped_token() {
  python3 -c '
import json,sys
tgt = sys.argv[1]
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
tok = ""
node = d.get("podcast_tokens")
if isinstance(node, list):
    for t in node:
        if isinstance(t, dict) and str(t.get("podcast_id")) == tgt:
            tok = t.get("access_token", "")
if not tok:
    n = d.get(tgt)
    if isinstance(n, dict):
        tok = n.get("access_token", "")
    elif isinstance(n, str):
        tok = n
print(tok or "")
' "$1"
}

# Build a curl config on stdout carrying the secret url and, optionally, basic
# auth. printf is a shell builtin, so the secret never appears in the process
# list; the config is consumed through process substitution, never a temp file.
cfg_lines() {
  local method="$1" url="$2"
  printf 'request = "%s"\n' "$method"
  printf 'url = "%s"\n' "$url"
  printf 'silent\n'
  printf 'show-error\n'
  printf 'location\n'
  printf 'max-time = %s\n' "$CURL_MAX_TIME"
  if [ "${USE_BASIC:-0}" = "1" ]; then
    printf 'user = "%s:%s"\n' "$PODBEAN_CLIENT_ID" "$PODBEAN_CLIENT_SECRET"
  fi
}

# http_request METHOD URL [extra curl argv...]
# Sets RESP_BODY and RESP_CODE. Returns non-zero only after RETRIES failures.
# URL (which may carry access_token) is passed via cfg_lines, not argv.
RESP_BODY=""; RESP_CODE=""
http_request() {
  local method="$1" url="$2"; shift 2
  local attempt=1 out
  while :; do
    out="$(curl -K <(cfg_lines "$method" "$url") "$@" -w $'\n%{http_code}' 2>/dev/null || true)"
    RESP_CODE="${out##*$'\n'}"
    RESP_BODY="${out%$'\n'*}"
    if [[ "$RESP_CODE" =~ ^2[0-9][0-9]$ ]]; then return 0; fi
    if [ "$attempt" -ge "$RETRIES" ]; then return 1; fi
    log "attempt ${attempt} for ${method} $(redact "${url%%\?*}") returned HTTP ${RESP_CODE:-000}; backing off"
    sleep "$(( attempt * attempt ))"
    attempt=$(( attempt + 1 ))
  done
}

# ---------------------------------------------------------- n8n Podbean broker --
# Broker mode keeps BlackCEO's SINGLE Podbean app (client_id/secret) inside n8n.
# This box holds only the broker webhook URL, a low-privilege shared token, and
# the client's Channel ID. The broker mints a Podbean access token already SCOPED
# to that Channel ID and returns it; no Podbean app secret is ever on this box.
#
# The shared token goes in a curl config (a printf builtin via process
# substitution), never in argv (no ps exposure) and never on disk - mirroring the
# secret-handling contract used for basic auth above. The request body carries
# only the action and the Channel ID (not secrets) so it may ride in argv.
broker_cfg_lines() {
  printf 'request = "POST"\n'
  printf 'url = "%s"\n' "$PODBEAN_BROKER_WEBHOOK_URL"
  printf 'silent\n'
  printf 'show-error\n'
  printf 'location\n'
  printf 'max-time = %s\n' "$CURL_MAX_TIME"
  printf 'header = "Content-Type: application/json"\n'
  printf 'header = "X-Podbean-Broker-Token: %s"\n' "$PODBEAN_BROKER_TOKEN"
}

# broker_mint_token: POST {action:"mint_token", podcast_id:<Channel ID>} to the
# broker. Sets RESP_BODY and RESP_CODE. Returns non-zero only after RETRIES.
broker_mint_token() {
  local body attempt=1 out
  body="$(printf '{"action":"mint_token","podcast_id":"%s"}' "$PODBEAN_PODCAST_ID")"
  while :; do
    out="$(curl -K <(broker_cfg_lines) --data "$body" -w $'\n%{http_code}' 2>/dev/null || true)"
    RESP_CODE="${out##*$'\n'}"
    RESP_BODY="${out%$'\n'*}"
    if [[ "$RESP_CODE" =~ ^2[0-9][0-9]$ ]]; then return 0; fi
    if [ "$attempt" -ge "$RETRIES" ]; then return 1; fi
    log "podbean broker attempt ${attempt} returned HTTP ${RESP_CODE:-000}; backing off"
    sleep "$(( attempt * attempt ))"
    attempt=$(( attempt + 1 ))
  done
}

# ------------------------------------------------------------ publish-proxy ---
# Proxy mode keeps BlackCEO's SINGLE Podbean app entirely inside n8n and hands
# the WHOLE publish (mint, download, upload, create) to the operator's server.
# This box's only job is to build the contract v2 JSON payload and POST it with
# the shared header token (never in argv, never on disk - printf builtin via
# process substitution, mirroring broker_cfg_lines above).
readonly PROXY_MAX_TIME=300

proxy_cfg_lines() {
  printf 'request = "POST"\n'
  printf 'url = "%s"\n' "$PODBEAN_PUBLISH_WEBHOOK_URL"
  printf 'silent\n'
  printf 'show-error\n'
  printf 'location\n'
  printf 'max-time = %s\n' "$PROXY_MAX_TIME"
  printf 'header = "Content-Type: application/json"\n'
  printf 'header = "X-Podcast-Publish-Token: %s"\n' "$PODBEAN_PUBLISH_TOKEN"
}

# Converts an ISO 8601 string (passed through unchanged) or a unix-epoch integer
# (converted to Eastern local time) into the contract's "ISO 8601 with time,
# Eastern" publish_date field. Empty input means "now" (immediate publish).
# python3's zoneinfo is stdlib (3.9+) and this script already hard-requires
# python3, so this needs no new dependency.
to_iso8601_eastern() {
  local v="$1"
  if [ -z "$v" ]; then
    python3 -c 'from datetime import datetime; from zoneinfo import ZoneInfo; print(datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds"))'
    return 0
  fi
  if [[ "$v" == *T* ]]; then printf '%s' "$v"; return 0; fi
  if [[ "$v" =~ ^[0-9]+$ ]]; then
    python3 -c 'from datetime import datetime; from zoneinfo import ZoneInfo; import sys; print(datetime.fromtimestamp(int(sys.argv[1]), ZoneInfo("America/New_York")).isoformat(timespec="seconds"))' "$v"
    return 0
  fi
  printf '%s' "$v"
}

# Builds the contract v2 JSON body (master spec Section 3). title is sent RAW
# (not FINAL_TITLE) - n8n does the "Inspired by <speaker>" append server-side in
# proxy mode. Never includes a Podbean credential, a GHL token, or any operator
# secret (the contract's own "never sent" rule); only the shared header token
# (added by proxy_cfg_lines, not this body) authenticates the call.
build_proxy_payload() {
  local json
  json="{\"contract_version\":\"2\""
  json="${json},\"podcast_id\":$(jstr "$PODBEAN_PODCAST_ID")"
  json="${json},\"client_last_name\":$(jstr "$PODCAST_CLIENT_LAST_NAME")"
  json="${json},\"client_email\":$(jstr "$PODCAST_CLIENT_EMAIL")"
  [ -n "${PODCAST_CLIENT_FIRST_NAME:-}" ] && json="${json},\"client_first_name\":$(jstr "$PODCAST_CLIENT_FIRST_NAME")"
  json="${json},\"title\":$(jstr "$TITLE")"
  json="${json},\"description\":$(jstr "$DESCRIPTION")"
  json="${json},\"audio_url\":$(jstr "$AUDIO_URL")"
  json="${json},\"image_url\":$(jstr "$IMAGE_URL")"
  json="${json},\"publish_date\":$(jstr "$PROXY_PUBLISH_DATE")"
  json="${json},\"idempotency_key\":$(jstr "$IDEMPOTENCY_KEY")"
  json="${json},\"episode_type\":$(jstr "${EPISODE_TYPE:-full}")"
  json="${json},\"explicit\":$(jstr "${EXPLICIT_FLAG:-clean}")"
  [ -n "$SPEAKER" ] && json="${json},\"speaker\":$(jstr "$SPEAKER")"
  [[ "${SEASON_NUMBER:-}" =~ ^[0-9]+$ ]] && json="${json},\"season_number\":${SEASON_NUMBER}"
  json="${json},\"source\":\"skill58-step15\""
  json="${json}}"
  printf '%s' "$json"
}

# One POST attempt. Sets RESP_BODY / RESP_CODE. RESP_CODE is empty (not "000")
# on a curl-level network failure (no HTTP exchange happened at all) so the
# caller can tell "no server reached" apart from a real non-2xx HTTP response.
proxy_post() {
  local body="$1" out
  out="$(curl -K <(proxy_cfg_lines) --data "$body" -w $'\n%{http_code}' 2>/dev/null || true)"
  RESP_CODE="${out##*$'\n'}"
  RESP_BODY="${out%$'\n'*}"
  [[ "$RESP_CODE" =~ ^[0-9]{3}$ ]] || RESP_CODE=""
}

# proxy_publish_with_retry BODY: terminal statuses (2xx success, 403 refusal,
# 422 invalid payload) return immediately on the first attempt - retrying a
# standing/identity refusal or a malformed payload cannot make it succeed. A
# network failure (empty RESP_CODE), 409 (in_flight), or 5xx IS retry-worthy and
# is safe to retry with the SAME idempotency_key (master spec Section 8); this
# satisfies the contract's "one retry on network error" as a strict subset of
# its bounded RETRIES-attempt backoff (same constant/backoff shape as
# http_request above, for one consistent retry story in this script). Always
# returns 0; the caller reads RESP_CODE (possibly still empty after RETRIES
# attempts) and RESP_BODY to decide the final outcome.
proxy_publish_with_retry() {
  local body="$1" attempt=1
  while :; do
    proxy_post "$body"
    case "$RESP_CODE" in
      2??|403|422) return 0 ;;
      409|5??|"") : ;;
      *) return 0 ;;
    esac
    if [ "$attempt" -ge "$RETRIES" ]; then return 0; fi
    log "publish-proxy attempt ${attempt} returned HTTP ${RESP_CODE:-000} (no server response counts as retry-worthy); retrying with the same idempotency_key"
    sleep "$(( attempt * attempt ))"
    attempt=$(( attempt + 1 ))
  done
}

# ------------------------------------------------------------- argument parse --
AUDIO=""; TITLE=""; COVER=""; SPEAKER=""; DESCRIPTION=""
RELEASE_DATE=""; STATUS_OVERRIDE=""; EP_TYPE="public"
LEDGER=""; JOB_ID=""; STATE_WRITER=""; OUT=""
TEST_RUN=0; DRY_RUN=0
AUDIO_URL=""; IMAGE_URL=""; IDEMPOTENCY_KEY_ARG=""
EPISODE_TYPE=""; EXPLICIT_FLAG=""; SEASON_NUMBER=""

while [ $# -gt 0 ]; do
  case "$1" in
    --audio)            AUDIO="${2:-}"; shift 2 ;;
    --title)            TITLE="${2:-}"; shift 2 ;;
    --cover)            COVER="${2:-}"; shift 2 ;;
    --speaker)          SPEAKER="${2:-}"; shift 2 ;;
    --description)      DESCRIPTION="${2:-}"; shift 2 ;;
    --release-date)     RELEASE_DATE="${2:-}"; shift 2 ;;
    --status)           STATUS_OVERRIDE="${2:-}"; shift 2 ;;
    --type)             EP_TYPE="${2:-}"; shift 2 ;;
    --ledger)           LEDGER="${2:-}"; shift 2 ;;
    --job-id)           JOB_ID="${2:-}"; shift 2 ;;
    --state-writer)     STATE_WRITER="${2:-}"; shift 2 ;;
    --out)              OUT="${2:-}"; shift 2 ;;
    --audio-url)        AUDIO_URL="${2:-}"; shift 2 ;;
    --image-url)        IMAGE_URL="${2:-}"; shift 2 ;;
    --idempotency-key)  IDEMPOTENCY_KEY_ARG="${2:-}"; shift 2 ;;
    --episode-type)     EPISODE_TYPE="${2:-}"; shift 2 ;;
    --explicit)         EXPLICIT_FLAG="${2:-}"; shift 2 ;;
    --season-number)    SEASON_NUMBER="${2:-}"; shift 2 ;;
    --test)             TEST_RUN=1; shift ;;
    --dry-run)          DRY_RUN=1; shift ;;
    -h|--help)          usage; exit 0 ;;
    *)                  usage; die "unknown argument: $1" ;;
  esac
done

command -v curl    >/dev/null 2>&1 || die "curl is required"
command -v python3 >/dev/null 2>&1 || die "python3 is required"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Emit the final machine-readable result to stdout (and --out), no backticks.
emit_result() {
  local json="$1"
  if [ -n "$OUT" ]; then printf '%s\n' "$json" > "$OUT"; fi
  printf '%s\n' "$json"
}

# JSON string escaper for values we place into the emitted result.
jstr() { python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "${1:-}"; }

# ------------------------------------------------------- idempotency and test --
# Ledger-driven skip: the single most important guard for Step 15. A crash and
# resume inside one job must never create a second Podbean episode.
if [ -n "$LEDGER" ]; then
  existing_permalink="$(ledger_field "$LEDGER" podbean_permalink || true)"
  ledger_state="$(ledger_field "$LEDGER" state || true)"
  if [ -n "$existing_permalink" ] && [ "$existing_permalink" != "None" ]; then
    log "ledger already holds a permalink for this job; skipping publish (idempotent)"
    emit_result "{\"status\":\"skipped\",\"reason\":\"permalink_present\",\"idempotent_skip\":true,\"permalink_url\":$(jstr "$existing_permalink")}"
    exit 0
  fi
  if [ "$ledger_state" = "test" ]; then
    TEST_RUN=1
  fi
fi

# Test records never touch Podbean (webhook-design test-flag contract).
if [ "$TEST_RUN" = "1" ]; then
  log "test run: validating inputs and short-circuiting before any Podbean call"
fi

# --------------------------------------------------------- validate the inputs --
[ -n "$AUDIO" ] || { usage; die "--audio is required"; }
[ -n "$TITLE" ] || { usage; die "--title is required"; }
[ -f "$AUDIO" ] || die "audio file not found: $AUDIO"
if [ -n "$COVER" ] && [ ! -f "$COVER" ]; then die "cover file not found: $COVER"; fi
case "$EP_TYPE" in public|premium|private) ;; *) die "--type must be public, premium, or private" ;; esac
if [ -n "$EPISODE_TYPE" ]; then
  case "$EPISODE_TYPE" in full|trailer|bonus) ;; *) die "--episode-type must be full, trailer, or bonus" ;; esac
fi
if [ -n "$EXPLICIT_FLAG" ]; then
  case "$EXPLICIT_FLAG" in clean|explicit) ;; *) die "--explicit must be clean or explicit" ;; esac
fi
if [ -n "$SEASON_NUMBER" ]; then
  [[ "$SEASON_NUMBER" =~ ^[0-9]+$ ]] || die "--season-number must be a non-negative integer"
fi

# Credentials are checked for presence only; values are never printed.
# The Channel ID is the ONLY per-client Podbean value and is required in ALL
# THREE modes (proxy, broker, local).
: "${PODBEAN_PODCAST_ID:?PODBEAN_PODCAST_ID is NOT SET (the client Podbean Channel ID / podcast_id)}"

# Mode selection (per box), precedence PROXY > BROKER > LOCAL. PROXY if the n8n
# publish-proxy webhook URL and its shared header token both resolve (fleet
# default as of the publish-proxy fix; BlackCEO's app credentials never touch
# this box AND this box never uploads media to Podbean itself). Else BROKER if
# the n8n Podbean broker webhook URL and its shared token both resolve (dormant
# fallback, kept unchanged for back-compat). Else LOCAL client_credentials,
# which is the operator's OWN box fallback and needs the shared app
# client_id/secret. When PROXY_MODE and BROKER_MODE are both 0 below, everything
# in this elif chain is byte-for-byte the pre-fix broker/local selection logic -
# unset PODBEAN_PUBLISH_WEBHOOK_URL/PODBEAN_PUBLISH_TOKEN and behavior on this
# box is unchanged from before the publish-proxy fix.
PROXY_MODE=0
BROKER_MODE=0
if [ -n "${PODBEAN_PUBLISH_WEBHOOK_URL:-}" ] && [ -n "${PODBEAN_PUBLISH_TOKEN:-}" ]; then
  PROXY_MODE=1
  : "${PODCAST_CLIENT_LAST_NAME:?PODCAST_CLIENT_LAST_NAME is NOT SET (publish-proxy identity/roster-lookup field; required whenever PODBEAN_PUBLISH_WEBHOOK_URL + PODBEAN_PUBLISH_TOKEN are both set). The engine never guesses this value - it is provisioned per box from the operator roster.}"
  : "${PODCAST_CLIENT_EMAIL:?PODCAST_CLIENT_EMAIL is NOT SET (publish-proxy identity/roster-lookup field; required whenever PODBEAN_PUBLISH_WEBHOOK_URL + PODBEAN_PUBLISH_TOKEN are both set). The engine never guesses this value - it is provisioned per box from the operator roster.}"
  [ -n "$AUDIO_URL" ] || die "--audio-url is required in publish-proxy mode (contract v2 requires a public HTTPS audio_url; this box does not upload media to Podbean directly under this transport)."
  [ -n "$IMAGE_URL" ] || die "--image-url is required in publish-proxy mode (contract v2 requires a public HTTPS image_url; this box does not upload media to Podbean directly under this transport)."
elif [ -n "${PODBEAN_PUBLISH_WEBHOOK_URL:-}" ] || [ -n "${PODBEAN_PUBLISH_TOKEN:-}" ]; then
  die "only one of PODBEAN_PUBLISH_WEBHOOK_URL / PODBEAN_PUBLISH_TOKEN is set - both are required for publish-proxy mode. Unset both to fall back to broker/local mode."
elif [ -n "${PODBEAN_BROKER_WEBHOOK_URL:-}" ] && [ -n "${PODBEAN_BROKER_TOKEN:-}" ]; then
  BROKER_MODE=1
else
  : "${PODBEAN_CLIENT_ID:?PODBEAN_CLIENT_ID is NOT SET. Configure the n8n publish-proxy (PODBEAN_PUBLISH_WEBHOOK_URL + PODBEAN_PUBLISH_TOKEN), the n8n Podbean broker (PODBEAN_BROKER_WEBHOOK_URL + PODBEAN_BROKER_TOKEN) on this box, or - on the operator OWN box only - set the BlackCEO shared Podbean app client id.}"
  : "${PODBEAN_CLIENT_SECRET:?PODBEAN_CLIENT_SECRET is NOT SET (the BlackCEO shared Podbean app secret; operator OWN box only - prefer the n8n publish-proxy or broker so no secret sits on a client box).}"
fi

# ------------------------------------------------------ title and publish plan --
# Title convention: append "Inspired by <speaker>" once, only when a speaker is
# supplied and the phrase is not already present (idempotent title building).
FINAL_TITLE="$TITLE"
if [ -n "$SPEAKER" ] && [[ "$FINAL_TITLE" != *"Inspired by ${SPEAKER}"* ]]; then
  FINAL_TITLE="${TITLE} Inspired by ${SPEAKER}"
fi

# Description defaults to the final title when show notes are absent (Podbean
# requires episode content). Never inject an em dash or a code fence.
[ -n "$DESCRIPTION" ] || DESCRIPTION="$FINAL_TITLE"

# Status: publish now, or schedule for a future release date. A future date maps
# to Podbean status "future" plus a unix publish_timestamp.
PUBLISH_STATUS="publish"
PUBLISH_TIMESTAMP=""
if [ -n "$RELEASE_DATE" ]; then
  rel_epoch="$(to_epoch "$RELEASE_DATE" || true)"
  [ -n "$rel_epoch" ] || die "could not parse --release-date: $RELEASE_DATE"
  now_epoch="$(date +%s)"
  if [ "$rel_epoch" -gt "$now_epoch" ]; then
    PUBLISH_STATUS="future"
    PUBLISH_TIMESTAMP="$rel_epoch"
  fi
fi
# An explicit override wins, but a future status still needs a timestamp.
if [ -n "$STATUS_OVERRIDE" ]; then
  case "$STATUS_OVERRIDE" in
    publish|draft|future) PUBLISH_STATUS="$STATUS_OVERRIDE" ;;
    *) die "--status must be publish, draft, or future" ;;
  esac
  if [ "$PUBLISH_STATUS" = "future" ] && [ -z "$PUBLISH_TIMESTAMP" ]; then
    [ -n "$RELEASE_DATE" ] || die "status future requires --release-date"
    PUBLISH_TIMESTAMP="$(to_epoch "$RELEASE_DATE")"
  fi
  if [ "$PUBLISH_STATUS" != "future" ]; then PUBLISH_TIMESTAMP=""; fi
fi

log "plan: status=${PUBLISH_STATUS} type=${EP_TYPE} title=$(jstr "$FINAL_TITLE")"

if [ "$TEST_RUN" = "1" ]; then
  emit_result "{\"status\":\"test-skipped\",\"reason\":\"test_flag\",\"idempotent_skip\":false,\"episode_title\":$(jstr "$FINAL_TITLE"),\"publish_status\":$(jstr "$PUBLISH_STATUS")}"
  exit 0
fi

# ---------------------------------------------------------- publish-proxy ----
# n8n does the ENTIRE publish (mint, download, upload, create, respond). This
# box never touches a Podbean credential or a Podbean API endpoint in this mode.
if [ "$PROXY_MODE" = "1" ]; then
  IDEMPOTENCY_KEY="${IDEMPOTENCY_KEY_ARG:-$JOB_ID}"
  [ -n "$IDEMPOTENCY_KEY" ] || die "publish-proxy mode requires --idempotency-key or --job-id (contract v2 requires a stable idempotency_key so a redelivered request cannot create a second episode)."
  PROXY_PUBLISH_DATE="$(to_iso8601_eastern "$RELEASE_DATE")"

  if [ "$DRY_RUN" = "1" ]; then
    log "dry-run (publish-proxy): payload validated; not contacting the publish-proxy webhook (no network call)"
    emit_result "{\"status\":\"dry-run\",\"idempotent_skip\":false,\"transport\":\"publish-proxy\",\"episode_title\":$(jstr "$TITLE"),\"publish_status\":$(jstr "$PUBLISH_STATUS"),\"idempotency_key\":$(jstr "$IDEMPOTENCY_KEY"),\"publish_date\":$(jstr "$PROXY_PUBLISH_DATE")}"
    exit 0
  fi

  PROXY_BODY="$(build_proxy_payload)"
  log "posting contract v2 payload to the publish-proxy webhook (idempotency_key set; token not shown, never in argv)"
  proxy_publish_with_retry "$PROXY_BODY"
  PROXY_BODY=""   # drop the payload (carries client_email) from the shell as soon as possible

  case "$RESP_CODE" in
    2??)
      ok_field="$(printf '%s' "$RESP_BODY" | json_field ok)"
      if [ "$ok_field" != "True" ]; then
        die "publish-proxy returned HTTP ${RESP_CODE} with an unexpected body shape (ok is not true): $(redact "$RESP_BODY")"
      fi
      PERMALINK="$(printf '%s' "$RESP_BODY" | json_field permalink_url)"
      EPISODE_ID="$(printf '%s' "$RESP_BODY" | json_field episode_id)"
      PROXY_EPISODE_NUMBER="$(printf '%s' "$RESP_BODY" | json_field episode_number)"
      REPLAY="$(printf '%s' "$RESP_BODY" | json_field idempotent_replay)"
      RESP_BODY=""
      [ -n "$PERMALINK" ] || die "publish-proxy returned ok:true but no permalink_url"
      log "publish-proxy episode published (or idempotent replay); permalink captured"
      SW="${STATE_WRITER:-$SCRIPT_DIR/podcast_state.py}"
      if [ -n "$JOB_ID" ] && [ -f "$SW" ]; then
        if python3 "$SW" output --job-id "$JOB_ID" --field podbean_permalink --value "$PERMALINK" >&2; then
          log "permalink recorded via podcast_state.py for job ${JOB_ID}"
        else
          log "warning: podcast_state.py did not record the permalink; caller must persist it"
        fi
      elif [ -n "$JOB_ID" ]; then
        log "podcast_state.py not found at ${SW}; emitting result for the caller to persist"
      fi
      emit_result "{\"status\":\"published\",\"idempotent_skip\":false,\"transport\":\"publish-proxy\",\"permalink_url\":$(jstr "$PERMALINK"),\"episode_id\":$(jstr "$EPISODE_ID"),\"episode_number\":$( [[ "$PROXY_EPISODE_NUMBER" =~ ^[0-9]+$ ]] && printf '%s' "$PROXY_EPISODE_NUMBER" || printf 'null' ),\"episode_title\":$(jstr "$TITLE"),\"idempotent_replay\":$( [ "$REPLAY" = "True" ] && printf 'true' || printf 'false' )}"
      exit 0
      ;;
    403)
      reason="$(printf '%s' "$RESP_BODY" | json_field reason)"
      RESP_BODY=""
      case "$reason" in
        not_in_good_standing)
          log "publish-proxy refused: not_in_good_standing"
          emit_result "{\"status\":\"blocked\",\"reason\":\"not_in_good_standing\"}"
          exit 3
          ;;
        identity_unknown|identity_mismatch)
          log "publish-proxy refused: ${reason}"
          emit_result "{\"status\":\"blocked\",\"reason\":$(jstr "$reason")}"
          exit 3
          ;;
        *)
          die "publish-proxy refused (HTTP 403, reason=${reason:-unknown})"
          ;;
      esac
      ;;
    409)
      RESP_BODY=""
      die "publish-proxy: idempotency_key still in_flight (HTTP 409) after ${RETRIES} attempts; safe to retry the whole job later with the same idempotency_key"
      ;;
    422)
      die "publish-proxy rejected the payload (HTTP 422 invalid_payload): $(redact "$RESP_BODY")"
      ;;
    *)
      die "publish-proxy failed (HTTP ${RESP_CODE:-000} after ${RETRIES} attempts): $(redact "$RESP_BODY")"
      ;;
  esac
fi

# --------------------------------------------------------------- OAuth 2.0 ----
ACCESS_TOKEN=""
if [ "$BROKER_MODE" = "1" ]; then
  # Broker mode: BlackCEO's single Podbean app lives only inside n8n. Ask the
  # broker for a token already SCOPED to this client's Channel ID. No Podbean app
  # secret is present on this box; the isolation guard lives in the broker (it
  # only mints tokens for channels on the host account).
  log "requesting a Channel-scoped Podbean token from the n8n broker (app credentials never leave n8n)"
  broker_mint_token || die "podbean broker token request failed (HTTP ${RESP_CODE:-000}): $(redact "$RESP_BODY")"
  broker_ok="$(printf '%s' "$RESP_BODY" | json_field ok)"
  ACCESS_TOKEN="$(printf '%s' "$RESP_BODY" | json_field access_token)"
  RESP_BODY=""   # drop the token-bearing body from memory as soon as possible
  [ -n "$ACCESS_TOKEN" ] || die "podbean broker returned no access_token (ok=${broker_ok:-unknown}); check PODBEAN_BROKER_TOKEN and that the broker workflow is active"
  log "Channel-scoped access token acquired from broker (value not shown)"
else
  log "requesting a client_credentials access token from BlackCEO's shared Podbean app (local fallback, operator box only)"
  USE_BASIC=1 http_request POST "$PODBEAN_API/oauth/token" \
    --data-urlencode "grant_type=client_credentials" \
    || die "oauth token request failed (HTTP ${RESP_CODE:-000}): $(redact "$RESP_BODY")"
  ACCESS_TOKEN="$(printf '%s' "$RESP_BODY" | json_field access_token)"
  [ -n "$ACCESS_TOKEN" ] || die "oauth response carried no access_token (HTTP ${RESP_CODE}): $(redact "$RESP_BODY")"
  RESP_BODY=""   # drop the token-bearing body from memory as soon as possible
  log "access token acquired (value not shown)"

  # ---------------------------------------------- isolation: own channel only ---
  # Confirm the configured podcast_id belongs to this account. This is the anti
  # commingling guard: refuse to publish to any channel that is not the target channel.
  if http_request GET "$PODBEAN_API/podcasts?access_token=${ACCESS_TOKEN}&offset=0&limit=100"; then
    account_ids="$(printf '%s' "$RESP_BODY" | podcast_ids)"
    RESP_BODY=""
    if [ -n "$account_ids" ]; then
      if ! printf '%s\n' "$account_ids" | grep -qxF "$PODBEAN_PODCAST_ID"; then
        die "configured PODBEAN_PODCAST_ID is not present on this Podbean account; refusing to publish (isolation guard)"
      fi
      # More than one podcast on the account: obtain a token scoped to the target.
      if [ "$(printf '%s\n' "$account_ids" | grep -c .)" -gt 1 ]; then
        log "account hosts multiple podcasts; requesting a token scoped to the target channel"
        if USE_BASIC=1 http_request POST "$PODBEAN_API/oauth/multiplePodcastsToken" \
             --data-urlencode "grant_type=client_credentials" \
             --data-urlencode "podcast_id=${PODBEAN_PODCAST_ID}"; then
          scoped="$(printf '%s' "$RESP_BODY" | scoped_token "$PODBEAN_PODCAST_ID")"
          RESP_BODY=""
          if [ -n "$scoped" ]; then
            ACCESS_TOKEN="$scoped"
            log "scoped token acquired for target channel (value not shown)"
          fi
        else
          log "warning: multiplePodcastsToken unavailable (HTTP ${RESP_CODE:-000}); continuing with the base token"
        fi
      fi
    fi
  else
    log "warning: could not list podcasts (HTTP ${RESP_CODE:-000}); continuing (single-podcast apps are already scoped)"
  fi
fi

# ------------------------------------------------------- episode numbering ----
log "reading current episode count for numbering"
http_request GET "$PODBEAN_API/episodes?access_token=${ACCESS_TOKEN}&offset=0&limit=1" \
  || die "could not list episodes for numbering (HTTP ${RESP_CODE:-000}): $(redact "$RESP_BODY")"
EPISODE_COUNT="$(printf '%s' "$RESP_BODY" | json_field count)"
[[ "$EPISODE_COUNT" =~ ^[0-9]+$ ]] || EPISODE_COUNT=0
EPISODE_NUMBER=$(( EPISODE_COUNT + 1 ))
log "existing episode count ${EPISODE_COUNT}; this episode is number ${EPISODE_NUMBER}"

# ------------------------------------------------- authorize and upload media --
# uploadAuthorize returns a presigned url plus the file_key that becomes the
# media_key (audio) or logo_key (cover). The bytes are PUT to the presigned url.
upload_file() {
  # $1 = local path, $2 = content type; echoes the file_key on success.
  local path="$1" ct="$2" fn size url presigned key
  fn="$(basename "$path")"
  size="$(filesize "$path")"
  url="$PODBEAN_API/files/uploadAuthorize?access_token=${ACCESS_TOKEN}&content_type=$(urlenc "$ct")&filename=$(urlenc "$fn")&filesize=${size}"
  http_request GET "$url" \
    || { log "uploadAuthorize failed for ${fn} (HTTP ${RESP_CODE:-000}): $(redact "$RESP_BODY")"; return 1; }
  presigned="$(printf '%s' "$RESP_BODY" | json_field presigned_url)"
  key="$(printf '%s' "$RESP_BODY" | json_field file_key)"
  [ -n "$presigned" ] && [ -n "$key" ] || { log "uploadAuthorize returned no presigned_url or file_key"; return 1; }
  # PUT the bytes to the presigned url; Content-Type must match the signed one.
  http_request PUT "$presigned" -T "$path" -H "Content-Type: ${ct}" \
    || { log "presigned upload failed for ${fn} (HTTP ${RESP_CODE:-000})"; return 1; }
  printf '%s' "$key"
}

if [ "$DRY_RUN" = "1" ]; then
  log "dry-run: token, isolation, and numbering resolved; skipping upload and create"
  emit_result "{\"status\":\"dry-run\",\"idempotent_skip\":false,\"episode_number\":${EPISODE_NUMBER},\"episode_title\":$(jstr "$FINAL_TITLE"),\"publish_status\":$(jstr "$PUBLISH_STATUS")}"
  exit 0
fi

AUDIO_CT="$(content_type_for "$AUDIO")"
log "authorizing and uploading audio (${AUDIO_CT})"
MEDIA_KEY="$(upload_file "$AUDIO" "$AUDIO_CT")" || die "audio upload to Podbean failed"
[ -n "$MEDIA_KEY" ] || die "audio upload returned no media_key"

LOGO_KEY=""
if [ -n "$COVER" ]; then
  COVER_CT="$(content_type_for "$COVER")"
  log "authorizing and uploading cover (${COVER_CT})"
  LOGO_KEY="$(upload_file "$COVER" "$COVER_CT")" || die "cover upload to Podbean failed"
fi

# ---------------------------------------------------------- create episode ----
log "creating episode ${EPISODE_NUMBER} on the client's channel (Channel ID ${PODBEAN_PODCAST_ID})"
create_args=(
  --data-urlencode "title=${FINAL_TITLE}"
  --data-urlencode "content=${DESCRIPTION}"
  --data-urlencode "status=${PUBLISH_STATUS}"
  --data-urlencode "type=${EP_TYPE}"
  --data-urlencode "media_key=${MEDIA_KEY}"
  --data-urlencode "episode_number=${EPISODE_NUMBER}"
)
[ -n "$LOGO_KEY" ]         && create_args+=( --data-urlencode "logo_key=${LOGO_KEY}" )
[ -n "$PUBLISH_TIMESTAMP" ] && create_args+=( --data-urlencode "publish_timestamp=${PUBLISH_TIMESTAMP}" )

http_request POST "$PODBEAN_API/episodes?access_token=${ACCESS_TOKEN}" "${create_args[@]}" \
  || die "episode create failed (HTTP ${RESP_CODE:-000}): $(redact "$RESP_BODY")"

PERMALINK="$(printf '%s' "$RESP_BODY" | json_field episode permalink_url)"
EPISODE_ID="$(printf '%s' "$RESP_BODY" | json_field episode id)"
[ -n "$PERMALINK" ] || die "episode created but no permalink_url returned (HTTP ${RESP_CODE}): $(redact "$RESP_BODY")"
RESP_BODY=""
log "episode published; permalink captured"

# ---------------------------------------------- record via the sole writer ----
# podcast_state.py is the single state writer (dashboard-design Section 5.4). It
# records podbean_permalink into the ledger and SQLite in lockstep. The Convert
# and Flow custom-field write (Step 16) is a separate slice and is NOT done here.
SW="${STATE_WRITER:-$SCRIPT_DIR/podcast_state.py}"
if [ -n "$JOB_ID" ] && [ -f "$SW" ]; then
  if python3 "$SW" output --job-id "$JOB_ID" --field podbean_permalink --value "$PERMALINK" >&2; then
    log "permalink recorded via podcast_state.py for job ${JOB_ID}"
  else
    log "warning: podcast_state.py did not record the permalink; caller must persist it"
  fi
elif [ -n "$JOB_ID" ]; then
  log "podcast_state.py not found at ${SW}; emitting result for the caller to persist"
fi

# ------------------------------------------------------------------- result ----
emit_result "{\"status\":\"published\",\"idempotent_skip\":false,\"permalink_url\":$(jstr "$PERMALINK"),\"episode_id\":$(jstr "$EPISODE_ID"),\"episode_number\":${EPISODE_NUMBER},\"episode_title\":$(jstr "$FINAL_TITLE"),\"publish_status\":$(jstr "$PUBLISH_STATUS"),\"publish_timestamp\":$( [ -n "$PUBLISH_TIMESTAMP" ] && printf '%s' "$PUBLISH_TIMESTAMP" || printf 'null' )}"
exit 0
