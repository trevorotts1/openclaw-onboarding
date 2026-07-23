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
# selects the show and is not a secret. Three modes, selected per box
# (precedence PROXY, then BROKER, then LOCAL - S58-U14):
#   PROXY (new fleet default): PODBEAN_PUBLISH_WEBHOOK_URL + PODBEAN_PUBLISH_TOKEN
#     are set; n8n performs the ENTIRE publish server-side (download audio/image,
#     upload to Podbean, create the episode) and returns the permalink
#     synchronously. This box never holds a Podbean app secret, only the
#     shared publish-proxy token, which is a webhook credential, not a
#     Podbean credential.
#   BROKER (previous fleet default; still supported): PODBEAN_BROKER_WEBHOOK_URL +
#     PODBEAN_BROKER_TOKEN are set; this box holds NO Podbean app secret. The n8n
#     Podbean credential broker (config/n8n/podbean-broker.workflow.json) mints a
#     Channel-scoped access token server-side and returns it. Nothing to leak here.
#   LOCAL (operator's OWN box fallback only): PODBEAN_CLIENT_ID + PODBEAN_CLIENT_SECRET
#     resolve from the operator env and this script mints the token directly.
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
# publish-proxy mode (S58-U14): a distinct exit code for the ONE refusal reason
# that is a client-facing business state, not an error - so the caller can
# detect "not in good standing" without parsing JSON.
readonly EXIT_BLOCKED_STANDING=3

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
  [ -n "${PODBEAN_PUBLISH_TOKEN:-}" ] && s="${s//${PODBEAN_PUBLISH_TOKEN}/[REDACTED_PUBLISH_TOKEN]}"
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
                          in BOTH modes.
  Precedence when more than one mode's variables are set: PROXY, then BROKER,
  then LOCAL (S58-U14). PROXY is the new fleet default (Section 2 of the S58
  server-side-publish spec):
  PODBEAN_PUBLISH_WEBHOOK_URL  n8n publish-proxy webhook (non-secret; e.g.
                          https://main.blackceoautomations.com/webhook/podbean-publish)
  PODBEAN_PUBLISH_TOKEN   shared header token for the proxy (X-Podcast-Publish-Token)
  PODCAST_CLIENT_LAST_NAME  the client's last name (proxy identity tuple, with email)
  PODCAST_CLIENT_EMAIL      the client's email (proxy identity tuple, with last name)
  PODCAST_CLIENT_FIRST_NAME optional; display only, never used for authorization
  Then EITHER broker mode (fleet default; no Podbean secret on this box):
  PODBEAN_BROKER_WEBHOOK_URL  n8n Podbean broker webhook (e.g.
                          https://main.blackceoautomations.com/webhook/podbean-broker)
  PODBEAN_BROKER_TOKEN    low-privilege shared token for the broker (X-Podbean-Broker-Token)
  OR local mode (operator's OWN box fallback only - BlackCEO's SINGLE shared app):
  PODBEAN_CLIENT_ID       BlackCEO shared Podbean app client id
  PODBEAN_CLIENT_SECRET   BlackCEO shared Podbean app client secret

Required arguments:
  --audio <path>          mastered MP3 to publish (must exist)
  --title <text>          base episode title (immutable from the blueprint step)

Common options:
  --cover <path>          finalized cover image (jpeg or png); becomes logo_key
  --audio-url <url>       HTTPS URL to the mastered MP3 (Step 14 output). REQUIRED
                          in proxy mode only (n8n downloads from this URL); ignored
                          in broker/local mode.
  --image-url <url>       HTTPS URL to the cover (Step 14 output). REQUIRED in
                          proxy mode only; ignored in broker/local mode.
  --speaker <name>        speaker or guest name; appends "Inspired by <name>" to the title
  --description <text>    show notes (plain text or html, kept under 3000 chars)
  --release-date <when>   contact.date_for_release (ISO 8601 or unix seconds);
                          a future value schedules the episode instead of publishing now
  --status <value>        force publish | draft | future (default derives from --release-date)
  --type <value>          public | premium | private (default public); ignored
                          in proxy mode (excluded from the v2 payload contract)
  --episode-type <value>  full | trailer | bonus (default full); the Podbean
                          episode type. Pre-flight validated against the allowed
                          set (U037) before any API call.

Idempotency and state (Step 15 double-publish guard):
  --ledger <path>         job ledger json; if it already holds a non-null
                          podbean_permalink, this script skips and re-emits it
  --job-id <id>           records the permalink via podcast_state.py output ...
  --state-writer <path>   path to podcast_state.py (default: sibling in this dir)
  --out <path>            also write the json result to this file

Safety:
  --test                  test run: validate and short-circuit BEFORE any Podbean
                          call (matches the ledger `test` state; never touches Podbean)
  --dry-run               resolve token and episode number but do not upload or
                          create; prints the plan (used by the canary to prove wiring)
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

# U037: Podbean episode-metadata field limits. Pre-flight bounds so an
# over-length / invalid field is rejected HERE with a clear message, not by a
# cryptic API rejection after the upload. The show-notes limit matches the
# documented "kept under 3000 chars" contract (usage text, line ~150); the
# episode-type set is the Podbean episode type vocabulary.
readonly PODBEAN_MAX_DESCRIPTION_LEN="${PODBEAN_MAX_DESCRIPTION_LEN:-3000}"
readonly PODBEAN_MAX_TITLE_LEN="${PODBEAN_MAX_TITLE_LEN:-200}"
readonly PODBEAN_EPISODE_TYPES="full trailer bonus"

# validate_episode_metadata <title> <description> <episode_type>
#   Pre-flight bounds/content checks run BEFORE any Podbean API call. Dies with
#   a clear message on:
#     - show notes (description) longer than PODBEAN_MAX_DESCRIPTION_LEN;
#     - title longer than PODBEAN_MAX_TITLE_LEN;
#     - an episode type outside PODBEAN_EPISODE_TYPES (full/trailer/bonus).
#   Returns 0 (proceeds) when every field is within bounds. Never makes a network
#   call. Lengths are counted in characters (wc -m), matching the "chars" contract.
validate_episode_metadata() {
  local title="$1" description="$2" episode_type="${3:-full}"
  local desc_len title_len

  desc_len="$(printf '%s' "$description" | wc -m | tr -d ' ')"
  if [ "$desc_len" -gt "$PODBEAN_MAX_DESCRIPTION_LEN" ]; then
    die "pre-flight: show notes are ${desc_len} chars, over the Podbean limit of ${PODBEAN_MAX_DESCRIPTION_LEN} — shorten the --description before publishing (the API would reject this)"
  fi

  title_len="$(printf '%s' "$title" | wc -m | tr -d ' ')"
  if [ "$title_len" -gt "$PODBEAN_MAX_TITLE_LEN" ]; then
    die "pre-flight: episode title is ${title_len} chars, over the Podbean limit of ${PODBEAN_MAX_TITLE_LEN} — shorten the --title before publishing (the API would reject this)"
  fi

  case " $PODBEAN_EPISODE_TYPES " in
    *" $episode_type "*) : ;;  # allowed episode type
    *) die "pre-flight: episode type '${episode_type}' is not allowed — must be one of:$(printf ' %s' $PODBEAN_EPISODE_TYPES) (the API would reject this)" ;;
  esac

  return 0
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

# ------------------------------------------------------------ publish-proxy --
# Proxy mode (S58-U14, precedence PROXY > BROKER > LOCAL): n8n performs the
# ENTIRE publish (download audio/image, upload to Podbean, create the
# episode). This box sends the webhook payload contract v2 (S58 spec Section
# 3) over HTTPS with the shared header token and gets back a synchronous JSON
# result carrying the permalink. Podbean's app credentials never touch this
# box in proxy mode either - only the shared publish-proxy token does, and
# that token is a webhook credential, never a Podbean credential.
#
# The auth token rides in a curl config header line (a printf builtin through
# process substitution), never in argv - the same secret-handling contract
# already used for basic auth and the broker token above. The JSON body itself
# carries no secret (client name/email/urls are not secrets), so it may ride
# in argv via --data-binary.
proxy_cfg_lines() {
  local url="$1"
  printf 'request = "POST"\n'
  printf 'url = "%s"\n' "$url"
  printf 'silent\n'
  printf 'show-error\n'
  printf 'location\n'
  printf 'max-time = %s\n' "$CURL_MAX_TIME"
  printf 'header = "Content-Type: application/json"\n'
  printf 'header = "X-Podcast-Publish-Token: %s"\n' "$PODBEAN_PUBLISH_TOKEN"
}

# Extract one field from the JSON body on stdin, normalizing a JSON boolean to
# the lowercase strings "true"/"false" (python str(True) prints "True", which
# would silently defeat a plain [ "$v" = "true" ] comparison) and an absent
# field to "". Kept separate from json_field (used by the OAuth/local paths
# above) so existing call sites are untouched.
proxy_field() {
  python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
v = d.get(sys.argv[1]) if isinstance(d, dict) else None
if isinstance(v, bool):
    print("true" if v else "false")
elif v is None:
    print("")
else:
    print(v)
' "$1"
}

# Build the webhook payload contract v2 JSON body (S58 spec Section 3). Never
# sends a Podbean credential, a GHL token, an operator secret, or an episode
# number ("Never sent" list, Section 3) - n8n computes the episode number
# server-side from the roster-routed channel.
build_proxy_payload() {
  python3 -c '
import json, sys
(podcast_id, last_name, email, first_name, title, description, audio_url,
 image_url, publish_date, idem_key, speaker, source, episode_type) = sys.argv[1:14]
d = {
    "contract_version": "2",
    "podcast_id": podcast_id,
    "client_last_name": last_name,
    "client_email": email,
    "title": title,
    "description": description,
    "audio_url": audio_url,
    "image_url": image_url,
    "publish_date": publish_date,
    "idempotency_key": idem_key,
    "episode_type": episode_type,
    "explicit": "clean",
    "source": source,
}
if first_name:
    d["client_first_name"] = first_name
if speaker:
    d["speaker"] = speaker
print(json.dumps(d))
' "$PODBEAN_PODCAST_ID" "$PODCAST_CLIENT_LAST_NAME" "$PODCAST_CLIENT_EMAIL" \
  "${PODCAST_CLIENT_FIRST_NAME:-}" "$FINAL_TITLE" "$DESCRIPTION" "$AUDIO_URL" \
  "$IMAGE_URL" "$PROXY_PUBLISH_DATE" "$JOB_ID" "${SPEAKER:-}" "skill58-step15" \
  "${EPISODE_TYPE:-full}"
}

# proxy_request URL BODY: POST BODY to URL with the shared header token. Sets
# RESP_BODY / RESP_CODE. Retries ONCE, matching Section 3's box-side contract
# ("one retry on network error with the same idempotency_key"), but ONLY on a
# network-level failure (curl could not get a status line at all, code 000) or
# an n8n-side HTTP 5xx. A 2xx/403/409/422 is a deterministic verdict from the
# gate and is returned to the caller on the FIRST reply - retrying it can never
# change the answer (Section 8: 409/403 need a human or a different key, not a
# tight retry loop). Never returns non-zero; the caller inspects RESP_CODE.
RESP_BODY=""; RESP_CODE=""
proxy_request() {
  local url="$1" body="$2" attempt=1 out
  while :; do
    out="$(curl -K <(proxy_cfg_lines "$url") --data-binary "$body" -w $'\n%{http_code}' 2>/dev/null || true)"
    RESP_CODE="${out##*$'\n'}"
    RESP_BODY="${out%$'\n'*}"
    if [ -z "$RESP_CODE" ] || [ "$RESP_CODE" = "000" ] || [[ "$RESP_CODE" =~ ^5[0-9][0-9]$ ]]; then
      if [ "$attempt" -ge 2 ]; then return 0; fi
      log "publish-proxy attempt ${attempt} returned HTTP ${RESP_CODE:-000}; retrying once (same idempotency_key)"
      sleep 1
      attempt=$(( attempt + 1 ))
      continue
    fi
    return 0
  done
}

# ------------------------------------------------------------- argument parse --
AUDIO=""; TITLE=""; COVER=""; SPEAKER=""; DESCRIPTION=""
RELEASE_DATE=""; STATUS_OVERRIDE=""; EP_TYPE="public"
EPISODE_TYPE="full"   # U037: Podbean episode type (full|trailer|bonus), pre-flight validated
LEDGER=""; JOB_ID=""; STATE_WRITER=""; OUT=""
TEST_RUN=0; DRY_RUN=0
AUDIO_URL=""; IMAGE_URL=""   # publish-proxy only (S58-U14)

while [ $# -gt 0 ]; do
  case "$1" in
    --audio)         AUDIO="${2:-}"; shift 2 ;;
    --title)         TITLE="${2:-}"; shift 2 ;;
    --cover)         COVER="${2:-}"; shift 2 ;;
    --audio-url)     AUDIO_URL="${2:-}"; shift 2 ;;
    --image-url)     IMAGE_URL="${2:-}"; shift 2 ;;
    --speaker)       SPEAKER="${2:-}"; shift 2 ;;
    --description)   DESCRIPTION="${2:-}"; shift 2 ;;
    --release-date)  RELEASE_DATE="${2:-}"; shift 2 ;;
    --status)        STATUS_OVERRIDE="${2:-}"; shift 2 ;;
    --type)          EP_TYPE="${2:-}"; shift 2 ;;
    --episode-type)  EPISODE_TYPE="${2:-}"; shift 2 ;;
    --ledger)        LEDGER="${2:-}"; shift 2 ;;
    --job-id)        JOB_ID="${2:-}"; shift 2 ;;
    --state-writer)  STATE_WRITER="${2:-}"; shift 2 ;;
    --out)           OUT="${2:-}"; shift 2 ;;
    --test)          TEST_RUN=1; shift ;;
    --dry-run)       DRY_RUN=1; shift ;;
    -h|--help)       usage; exit 0 ;;
    *)               usage; die "unknown argument: $1" ;;
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

# Credentials are checked for presence only; values are never printed.
# The Channel ID is the ONLY per-client Podbean value and is required in BOTH modes.
: "${PODBEAN_PODCAST_ID:?PODBEAN_PODCAST_ID is NOT SET (the client Podbean Channel ID / podcast_id)}"

# Transport precedence (per box): PROXY, then BROKER, then LOCAL (S58-U14).
# PROXY wins when both PODBEAN_PUBLISH_WEBHOOK_URL and PODBEAN_PUBLISH_TOKEN
# resolve: n8n performs the entire publish and this box holds no Podbean
# credential at all, not even a broker-scoped one (S58 spec Section 2). When
# PROXY is not configured, the BROKER/LOCAL selection below is unchanged and
# runs exactly as it did before this unit (byte-identical block, only gated).
PROXY_MODE=0
if [ -n "${PODBEAN_PUBLISH_WEBHOOK_URL:-}" ] && [ -n "${PODBEAN_PUBLISH_TOKEN:-}" ]; then
  PROXY_MODE=1
fi

BROKER_MODE=0
if [ "$PROXY_MODE" != "1" ]; then
# Mode selection (per box). BROKER if the n8n Podbean broker webhook URL and its
# shared token both resolve (fleet default; BlackCEO's app client_id/secret stay
# inside n8n and never touch this box). Otherwise LOCAL client_credentials, which
# is the operator's OWN box fallback and needs the shared app client_id/secret.
BROKER_MODE=0
if [ -n "${PODBEAN_BROKER_WEBHOOK_URL:-}" ] && [ -n "${PODBEAN_BROKER_TOKEN:-}" ]; then
  BROKER_MODE=1
else
  : "${PODBEAN_CLIENT_ID:?PODBEAN_CLIENT_ID is NOT SET. Configure the n8n Podbean broker (PODBEAN_BROKER_WEBHOOK_URL + PODBEAN_BROKER_TOKEN) on this box, or - on the operator OWN box only - set the BlackCEO shared Podbean app client id.}"
  : "${PODBEAN_CLIENT_SECRET:?PODBEAN_CLIENT_SECRET is NOT SET (the BlackCEO shared Podbean app secret; operator OWN box only - prefer the n8n broker so no secret sits on a client box).}"
fi
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

# U037: PRE-FLIGHT METADATA BOUNDS CHECK. Validates the episode metadata against
# Podbean's field limits BEFORE any API call (proxy or broker/local), so an
# over-length show-notes/title or an invalid episode type is rejected HERE with a
# clear message instead of a cryptic API rejection after the upload. Dies on a
# violation; proceeds silently when every field is within bounds.
validate_episode_metadata "$FINAL_TITLE" "$DESCRIPTION" "$EPISODE_TYPE"

if [ "$TEST_RUN" = "1" ]; then
  emit_result "{\"status\":\"test-skipped\",\"reason\":\"test_flag\",\"idempotent_skip\":false,\"episode_title\":$(jstr "$FINAL_TITLE"),\"publish_status\":$(jstr "$PUBLISH_STATUS")}"
  exit 0
fi

if [ "$PROXY_MODE" = "1" ]; then
  # -------------------------------------------------------- publish-proxy ----
  # Identity comes from the per-box env set by S58-U15 (never a CLI flag - the
  # operator provisions these once per box from the roster; the skill never
  # guesses them). Both halves of the identity tuple are required even for
  # --dry-run, since the standing pre-check (U13) needs them to look up the
  # roster row.
  : "${PODCAST_CLIENT_LAST_NAME:?PODCAST_CLIENT_LAST_NAME is NOT SET (required in publish-proxy mode; half of the roster identity tuple, with email).}"
  : "${PODCAST_CLIENT_EMAIL:?PODCAST_CLIENT_EMAIL is NOT SET (required in publish-proxy mode; half of the roster identity tuple, with last name).}"

  # Standing-check endpoint (U13), derived from the publish webhook URL unless
  # explicitly overridden. Both endpoints share the same header credential.
  PODBEAN_STANDING_CHECK_URL="${PODBEAN_STANDING_CHECK_URL:-${PODBEAN_PUBLISH_WEBHOOK_URL%/webhook/podbean-publish}/webhook/podcast-standing-check}"

  if [ "$DRY_RUN" = "1" ]; then
    log "dry-run (publish-proxy): probing the standing-check endpoint for reachability; no publish call"
    precheck_body="$(python3 -c '
import json, sys
d = {"client_last_name": sys.argv[1], "client_email": sys.argv[2]}
if sys.argv[3]:
    d["podcast_id"] = sys.argv[3]
print(json.dumps(d))
' "$PODCAST_CLIENT_LAST_NAME" "$PODCAST_CLIENT_EMAIL" "${PODBEAN_PODCAST_ID:-}")"
    proxy_request "$PODBEAN_STANDING_CHECK_URL" "$precheck_body"
    if [[ "$RESP_CODE" =~ ^2[0-9][0-9]$ ]]; then
      GOOD_STANDING="$(printf '%s' "$RESP_BODY" | proxy_field good_standing)"
      GOOD_STANDING_JSON="null"
      case "$GOOD_STANDING" in
        true)  GOOD_STANDING_JSON="true" ;;
        false) GOOD_STANDING_JSON="false" ;;
      esac
      log "dry-run (publish-proxy): standing-check endpoint reachable (good_standing=${GOOD_STANDING:-unknown})"
      emit_result "{\"status\":\"dry-run\",\"idempotent_skip\":false,\"reachable\":true,\"good_standing\":${GOOD_STANDING_JSON}}"
      exit 0
    fi
    die "publish-proxy dry-run: standing-check endpoint unreachable (HTTP ${RESP_CODE:-000}): $(redact "$RESP_BODY")"
  fi

  [ -n "$AUDIO_URL" ] || die "--audio-url is required in publish-proxy mode (n8n downloads the audio from this URL; Step 14 already produced it)"
  [ -n "$IMAGE_URL" ] || die "--image-url is required in publish-proxy mode (n8n downloads the cover from this URL; Step 14 already produced it)"
  [ -n "$JOB_ID" ]    || die "--job-id is required in publish-proxy mode (its value becomes the required idempotency_key)"

  PROXY_PUBLISH_DATE="$RELEASE_DATE"
  [ -n "$PROXY_PUBLISH_DATE" ] || PROXY_PUBLISH_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  log "publish-proxy: sending the v2 payload to n8n (identity and urls only; no Podbean or n8n secret in the body)"
  PROXY_PAYLOAD="$(build_proxy_payload)"
  proxy_request "$PODBEAN_PUBLISH_WEBHOOK_URL" "$PROXY_PAYLOAD"
  PROXY_PAYLOAD=""

  if [[ "$RESP_CODE" =~ ^2[0-9][0-9]$ ]]; then
    PROXY_OK="$(printf '%s' "$RESP_BODY" | proxy_field ok)"
    if [ "$PROXY_OK" != "true" ]; then
      die "publish-proxy returned HTTP ${RESP_CODE} but ok was not true: $(redact "$RESP_BODY")"
    fi
    PROXY_IDEMPOTENT="$(printf '%s' "$RESP_BODY" | proxy_field idempotent_replay)"
    PERMALINK="$(printf '%s' "$RESP_BODY" | proxy_field permalink_url)"
    EPISODE_ID="$(printf '%s' "$RESP_BODY" | proxy_field episode_id)"
    EPISODE_NUMBER="$(printf '%s' "$RESP_BODY" | proxy_field episode_number)"
    PROXY_SCHEDULED="$(printf '%s' "$RESP_BODY" | proxy_field scheduled)"
    RESP_BODY=""
    [ -n "$PERMALINK" ] || die "publish-proxy replied ok:true but carried no permalink_url"

    SW="${STATE_WRITER:-$SCRIPT_DIR/podcast_state.py}"
    if [ -n "$JOB_ID" ] && [ -f "$SW" ]; then
      if python3 "$SW" output --job-id "$JOB_ID" --field podbean_permalink --value "$PERMALINK" >&2; then
        log "permalink recorded via podcast_state.py for job ${JOB_ID}"
      else
        log "warning: podcast_state.py did not record the permalink; caller must persist it"
      fi
    fi

    if [ "$PROXY_IDEMPOTENT" = "true" ]; then
      log "publish-proxy: idempotent replay (episode already existed for this idempotency_key)"
      emit_result "{\"status\":\"skipped\",\"reason\":\"idempotent_replay\",\"idempotent_skip\":true,\"permalink_url\":$(jstr "$PERMALINK")}"
    else
      log "publish-proxy: episode published"
      EPISODE_NUMBER_JSON="null"
      [[ "$EPISODE_NUMBER" =~ ^[0-9]+$ ]] && EPISODE_NUMBER_JSON="$EPISODE_NUMBER"
      PUBLISH_STATUS_JSON='"publish"'
      [ "$PROXY_SCHEDULED" = "true" ] && PUBLISH_STATUS_JSON='"future"'
      emit_result "{\"status\":\"published\",\"idempotent_skip\":false,\"permalink_url\":$(jstr "$PERMALINK"),\"episode_id\":$(jstr "$EPISODE_ID"),\"episode_number\":${EPISODE_NUMBER_JSON},\"episode_title\":$(jstr "$FINAL_TITLE"),\"publish_status\":${PUBLISH_STATUS_JSON},\"publish_timestamp\":null}"
    fi
    exit 0
  fi

  if [ "$RESP_CODE" = "403" ]; then
    PROXY_REASON="$(printf '%s' "$RESP_BODY" | proxy_field reason)"
    if [ "$PROXY_REASON" = "not_in_good_standing" ]; then
      log "publish-proxy refused: not in good standing"
      emit_result "{\"status\":\"blocked\",\"reason\":\"not_in_good_standing\"}"
      exit "$EXIT_BLOCKED_STANDING"
    fi
    die "publish-proxy refused (${PROXY_REASON:-unknown_403}): $(redact "$RESP_BODY")"
  fi

  if [ "$RESP_CODE" = "409" ]; then
    die "publish-proxy: another request for this idempotency_key is already in_flight (HTTP 409); retry later with the same --job-id"
  fi

  if [ "$RESP_CODE" = "422" ]; then
    die "publish-proxy rejected the payload (HTTP 422): $(redact "$RESP_BODY")"
  fi

  die "publish-proxy failed (HTTP ${RESP_CODE:-000}): $(redact "$RESP_BODY")"
else
# --------------------------------------------------------------- OAuth 2.0 ----
ACCESS_TOKEN=""
# T0-19: set to 1 only on a path that has PROVEN the token can reach the target
# channel and nothing else. The episode-create call refuses to run without it, so
# a future edit that adds a new token path cannot silently publish unscoped.
CHANNEL_SCOPE_PROVEN=0
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
  # The broker mints per-Channel tokens and refuses channels that are not on the
  # host account, so a token returned here is scoped by construction.
  CHANNEL_SCOPE_PROVEN=1
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
  # T0-19: EVERY scoping failure is fatal. This block had exactly one hard stop —
  # the configured channel not appearing on the account — and three paths that
  # logged a warning and carried on holding the ACCOUNT-WIDE token: the listing
  # call failing, the identifier list parsing empty, and the scoped-token request
  # failing or returning nothing. On a shared account hosting several channels,
  # any of those three placed a client-facing episode on a channel that was never
  # proven to be the target. Targeting must never be a function of which token
  # happened to survive.
  #
  # Note on transients: http_request already retries a non-2xx up to $RETRIES with
  # quadratic backoff, so a network blip is retried BEFORE it becomes a verdict
  # here. What reaches these die() calls is a failure that survived the retries.
  if ! http_request GET "$PODBEAN_API/podcasts?access_token=${ACCESS_TOKEN}&offset=0&limit=100"; then
    die "could not list podcasts on this account (HTTP ${RESP_CODE:-000}) after ${RETRIES} attempt(s); refusing to publish with an unscoped token (isolation guard)"
  fi
  account_ids="$(printf '%s' "$RESP_BODY" | podcast_ids)"
  RESP_BODY=""
  if [ -z "$account_ids" ]; then
    die "podcast listing returned no channel identifiers; the target channel could not be confirmed, refusing to publish (isolation guard)"
  fi
  if ! printf '%s\n' "$account_ids" | grep -qxF "$PODBEAN_PODCAST_ID"; then
    die "configured PODBEAN_PODCAST_ID is not present on this Podbean account; refusing to publish (isolation guard)"
  fi
  # More than one podcast on the account: a token scoped to the target is
  # MANDATORY. Without it the base token can write to any channel on the account.
  if [ "$(printf '%s\n' "$account_ids" | grep -c .)" -gt 1 ]; then
    log "account hosts multiple podcasts; requesting a token scoped to the target channel"
    if ! USE_BASIC=1 http_request POST "$PODBEAN_API/oauth/multiplePodcastsToken" \
         --data-urlencode "grant_type=client_credentials" \
         --data-urlencode "podcast_id=${PODBEAN_PODCAST_ID}"; then
      die "multiplePodcastsToken unavailable (HTTP ${RESP_CODE:-000}) on a multi-channel account; refusing to publish with the account-wide token (isolation guard)"
    fi
    scoped="$(printf '%s' "$RESP_BODY" | scoped_token "$PODBEAN_PODCAST_ID")"
    RESP_BODY=""
    if [ -z "$scoped" ]; then
      die "multiplePodcastsToken returned no token for the target channel on a multi-channel account; refusing to publish with the account-wide token (isolation guard)"
    fi
    ACCESS_TOKEN="$scoped"
    CHANNEL_SCOPE_PROVEN=1
    log "scoped token acquired for target channel (value not shown)"
  else
    # Single channel on the account: the base token cannot reach another channel.
    CHANNEL_SCOPE_PROVEN=1
    log "account hosts exactly one podcast; the base token is already scoped to it"
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
# T0-19: refuse to create an episode on a token whose channel scope was never
# proven. Every path above either proves it or dies; this is the belt that makes
# a future token path fail closed instead of publishing account-wide.
[ "${CHANNEL_SCOPE_PROVEN:-0}" = "1" ] \
  || die "channel scope was never proven for this token; refusing to create an episode (isolation guard)"
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
fi
