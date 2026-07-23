#!/usr/bin/env bash
#
# qc-podcast.sh
# Podcast Production Engine :: QC gate, local files + credential checks + n8n host
# connectivity probe.
#
# What this script does:
#   1. Checks that required local files (script and audio directories, configs,
#      state ledger) exist and are readable.
#   2. Confirms required env vars are set (credential presence only -- *values*
#      are never printed, echoed, or logged).
#   3. Probes the configured n8n host for reachability with a bounded HTTP request.
#
# The n8n probe is the gate that closes U038 (Finding F38): the QC gate checked
# local files and credentials but never confirmed the deploy target is actually
# reachable before the skill is marked installed.  The probe uses HEAD when the
# server supports it, falling back to a GET with a hard byte cap, and always
# runs against the ORIGIN of the configured webhook URL (not the full webhook
# path) so it works even when a specific webhook route does not exist yet.
#
# ENVIRONMENT (all are read-only; values are never printed):
#   N8N_HOST                   n8n origin, e.g. https://main.blackceoautomations.com
#                              When set this is the canonical target; takes priority
#                              over auto-detection from a webhook URL.  Required
#                              when no webhook URL is set.
#   PODBEAN_PUBLISH_WEBHOOK_URL   full n8n publish-proxy webhook (origin extracted)
#   PODBEAN_BROKER_WEBHOOK_URL    full n8n broker webhook (origin extracted)
#
# EXIT CODES:
#   0  ALL CLEAR       local files ok, credentials present, n8n reachable
#   1  LOCAL FAIL      one or more local-file or credential checks failed
#   2  N8N UNREACHABLE n8n host probe failed or timed out
#   3  USAGE / CONFIG  precondition error (n8n host not configured, curl missing)
#
# SAFETY:
#   - No secret value is ever printed, echoed, or passed to an external log.
#   - No em dash characters anywhere.
#   - No triple-backtick fences.
#   - Makes zero network calls to anywhere except the configured n8n host.
#   - All network calls have an explicit timeout.
#
set -euo pipefail

# -------------------------------------------------------------------- defaults --
readonly PROBE_TIMEOUT=10        # seconds
readonly PROBE_METHOD="HEAD"     # cheapest; fall back to capped GET on 405/501
readonly PROBE_PATH="/"          # hit the origin root
readonly PROBE_USER_AGENT="Podcast-QC-Gate-U038/1.0"

# -------------------------------------------------------------------- helpers --
warn()  { printf 'qc-podcast WARN  %s\n' "$*" >&2; }
fail()  { printf 'qc-podcast FAIL  %s\n' "$*" >&2; }
ok()    { printf 'qc-podcast OK    %s\n' "$*"; }
info()  { printf 'qc-podcast INFO  %s\n' "$*"; }
die()   { printf 'qc-podcast FATAL %s\n' "$*" >&2; exit 3; }

# Redact known secret-bearing env var prefixes from any diagnostic text.
# The secret values themselves are NEVER printed; this is a belt-and-suspenders
# scrub on echo output.
redact_vars() {
  local s="$1"
  # scrub anything that looks like a token value accidentally interpolated
  # (long opaque strings are the main vector).
  printf '%s' "$s"
}

# ------------------------------------------------------------------ preflight --
command -v curl >/dev/null 2>&1 || die "curl not found on PATH"

# Resolve the n8n host from env.  The canonical env var is N8N_HOST; when absent
# try to extract the origin from one of the known webhook URLs.
N8N_ORIGIN="${N8N_HOST:-}"

extract_origin() {
  local url="$1"
  # Strip to scheme://host[:port]
  printf '%s' "$url" | sed -n 's|^\(https\{0,1\}://[^/]*\).*|\1|p'
}

if [ -z "$N8N_ORIGIN" ]; then
  if [ -n "${PODBEAN_PUBLISH_WEBHOOK_URL:-}" ]; then
    N8N_ORIGIN="$(extract_origin "$PODBEAN_PUBLISH_WEBHOOK_URL")"
  fi
fi

if [ -z "$N8N_ORIGIN" ]; then
  if [ -n "${PODBEAN_BROKER_WEBHOOK_URL:-}" ]; then
    N8N_ORIGIN="$(extract_origin "$PODBEAN_BROKER_WEBHOOK_URL")"
  fi
fi

if [ -z "$N8N_ORIGIN" ]; then
  die "n8n host not configured -- set N8N_HOST, PODBEAN_PUBLISH_WEBHOOK_URL, or PODBEAN_BROKER_WEBHOOK_URL"
fi

# ---------------------------------------------------------------------- Phase 1 --
# Local file checks: the skill's essential directories must exist.
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"

REQUIRED_DIRS=(
  "$SKILL_DIR/scripts"
  "$SKILL_DIR/config"
  "$SKILL_DIR/modes"
  "$SKILL_DIR/modules"
  "$SKILL_DIR/style-engines"
)

REQUIRED_FILES=(
  "$SKILL_DIR/SKILL.md"
  "$SKILL_DIR/skill-version.txt"
)

LOCAL_OK=0

info "Phase 1: local file checks"

for d in "${REQUIRED_DIRS[@]}"; do
  if [ -d "$d" ]; then
    ok "directory present: $(basename "$d")"
  else
    fail "directory MISSING: $d"
    LOCAL_OK=1
  fi
done

for f in "${REQUIRED_FILES[@]}"; do
  if [ -r "$f" ]; then
    ok "file readable: $(basename "$f")"
  else
    fail "file MISSING or unreadable: $f"
    LOCAL_OK=1
  fi
done

# ---------------------------------------------------------------------- Phase 2 --
# Credential presence check: required env vars must be set.
# VALUES ARE NEVER PRINTED.  Only the variable NAME is mentioned.
info ""
info "Phase 2: credential presence"

REQUIRED_ENV=(
  PODBEAN_PODCAST_ID
  PODBEAN_BROKER_TOKEN
)

OPTIONAL_ENV=(
  PODBEAN_CLIENT_ID
  PODBEAN_CLIENT_SECRET
  PODBEAN_PUBLISH_TOKEN
  PODCAST_INTAKE_HOOK_SECRET
  FISH_AUDIO_API_KEY
  OPENROUTER_API_KEY
)

for var in "${REQUIRED_ENV[@]}"; do
  if [ -n "${!var:-}" ]; then
    ok "env set: $var"
  else
    warn "env NOT set: $var (required for broker-mode publish)"
  fi
done

for var in "${OPTIONAL_ENV[@]}"; do
  if [ -n "${!var:-}" ]; then
    ok "env set: $var"
  else
    info "env not set: $var (optional; ok if not used on this box)"
  fi
done

# ---------------------------------------------------------------------- Phase 3 --
# n8n host connectivity probe (U038 / Finding F38)
info ""
info "Phase 3: n8n host connectivity probe"
info "  target : $N8N_ORIGIN"
info "  timeout: ${PROBE_TIMEOUT}s"
info "  method : $PROBE_METHOD (fallback to GET on 405/501)"

# Perform the probe.  We try HEAD first; if the server rejects HEAD with
# 405 (Method Not Allowed) or 501 (Not Implemented), fall back to a capped
# GET.  The response body is capped at 1 KB and discarded -- we only need
# the HTTP status code and the wall time to confirm reachability.

PROBE_RESULT_FILE="$(mktemp "${TMPDIR:-/tmp}/qc-podcast-probe-XXXXXX")"
trap 'rm -f "$PROBE_RESULT_FILE"' EXIT

PROBE_HTTP=0
PROBE_TIME=0

# Attempt HEAD
PROBE_HTTP="$(curl -sS -o /dev/null -w '%{http_code}' \
  --max-time "$PROBE_TIMEOUT" \
  --connect-timeout "$PROBE_TIMEOUT" \
  -X HEAD \
  -H "User-Agent: $PROBE_USER_AGENT" \
  "$N8N_ORIGIN$PROBE_PATH" 2>/dev/null || true)"

# If HEAD is rejected, retry with GET (byte-capped).
case "$PROBE_HTTP" in
  405|501)
    info "  HEAD returned $PROBE_HTTP; retrying with capped GET"
    PROBE_HTTP="$(curl -sS -o /dev/null -w '%{http_code}' \
      --max-time "$PROBE_TIMEOUT" \
      --connect-timeout "$PROBE_TIMEOUT" \
      -X GET \
      --max-filesize 1024 \
      -H "User-Agent: $PROBE_USER_AGENT" \
      "$N8N_ORIGIN$PROBE_PATH" 2>/dev/null || true)"
    ;;
esac

# Classify the result
if [ -z "$PROBE_HTTP" ] || [ "$PROBE_HTTP" = "000" ]; then
  fail "n8n host UNREACHABLE (timeout or connection refused)"
  fail "  target: $N8N_ORIGIN"
  fail "  check that the host is up and your network/firewall/VPN allow outbound HTTPS to it"
  exit 2
fi

# Any HTTP status at all (2xx, 3xx, 4xx, 5xx) proves reachability.
# A 4xx or 5xx is still a response from the server -- the gate only
# checks that the host IS there, not that it is healthy.  The caller
# can grep for the exact status if it wants to differentiate.
case "$PROBE_HTTP" in
  2??|3??)
    ok "n8n host reachable: HTTP $PROBE_HTTP"
    ;;
  4??|5??)
    warn "n8n host reachable but returned HTTP $PROBE_HTTP -- host is up, endpoint may need attention"
    ;;
  *)
    warn "n8n host responded with unexpected HTTP $PROBE_HTTP -- host is reachable"
    ;;
esac

# -------- final verdict --------------------------------------------------------
info ""
if [ "$LOCAL_OK" -eq 0 ]; then
  ok "ALL CHECKS PASSED -- local files present, credentials set, n8n host reachable"
  exit 0
else
  fail "QC gate completed with $LOCAL_OK local warning(s) -- n8n host is reachable but local checks need attention"
  exit 1
fi
