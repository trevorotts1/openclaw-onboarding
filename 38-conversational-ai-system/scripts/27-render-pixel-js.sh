#!/usr/bin/env bash
# 27-render-pixel-js.sh — ZHC Pixel (Feature 49) per-client generator.
#
# Renders templates/zhc-pixel/zhc-pixel.template.js into a per-client pixel JS by
# substituting the three placeholders with this client's OWN values:
#   __ZHC_PIXEL_ENDPOINT__  -> https://pixel.<CLIENT_DOMAIN>/hooks/pixel-visitor-signal
#                              (their tunnel, NOT a shared service)
#   __ZHC_PIXEL_SITE_ID__   -> a per-client unique site id (generated if not provided)
#   __ZHC_PIXEL_AGENT_ID__  -> the Pixel Concierge agent id (default pixel-concierge)
#
# Output: <MASTER_FILES_DIR>/pixel/zhc-pixel.js  (the file CF Pages will host)
# Also prints the one-line <script> paste snippet for the operator.
#
# UNIVERSAL: no personal/client data baked into the skill — every value comes from
# env at render time. Idempotent: re-running re-renders cleanly.
#
# OS-aware (Darwin + Linux). BASH only. Never echoes the hooks token.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE="${ZHC_PIXEL_TEMPLATE:-$SKILL_DIR/templates/zhc-pixel/zhc-pixel.template.js}"

# -------- Master files dir (read the pointer with head, NEVER source it) --------
MASTER_FILES_POINTER="${HOME}/.openclaw/.skill-38-master-files-dir"
if [ -z "${MASTER_FILES_DIR:-}" ] && [ -f "$MASTER_FILES_POINTER" ]; then
  MASTER_FILES_DIR="$(head -n1 "$MASTER_FILES_POINTER")"
fi
: "${MASTER_FILES_DIR:?MASTER_FILES_DIR not set (run 01-locate-master-files-folder.sh first)}"

[ -f "$TEMPLATE" ] || { echo "[27-render-pixel-js] template not found: $TEMPLATE" >&2; exit 2; }

# -------- Resolve per-client inputs --------
# CLIENT_DOMAIN: the apex/registered domain (e.g. <CLIENT_DOMAIN>). The pixel host is
# pixel.<CLIENT_DOMAIN>. If a full PIXEL_HOSTNAME is supplied, it wins.
if [ -z "${PIXEL_HOSTNAME:-}" ]; then
  : "${CLIENT_DOMAIN:?CLIENT_DOMAIN not set (e.g. CLIENT_DOMAIN=example.com) — or set PIXEL_HOSTNAME directly}"
  PIXEL_HOSTNAME="pixel.${CLIENT_DOMAIN}"
fi

# SITE_ID: per-client unique id. Generate a stable one if not supplied.
if [ -z "${ZHC_PIXEL_SITE_ID:-}" ]; then
  if command -v uuidgen >/dev/null 2>&1; then
    ZHC_PIXEL_SITE_ID="zhc-$(uuidgen | tr 'A-Z' 'a-z' | tr -d '-' | head -c 16)"
  else
    ZHC_PIXEL_SITE_ID="zhc-$(date +%s | sha1sum 2>/dev/null | head -c 16 || echo $$$(date +%s))"
  fi
fi

AGENT_ID="${ZHC_PIXEL_AGENT_ID:-pixel-concierge}"
ENDPOINT="https://${PIXEL_HOSTNAME}/hooks/pixel-visitor-signal"

# -------- Render --------
OUT_DIR="$MASTER_FILES_DIR/pixel"
mkdir -p "$OUT_DIR"
OUT_FILE="$OUT_DIR/zhc-pixel.js"

# Substitute placeholders. Use a temp + awk-free sed-free approach via bash so we
# never trip on slashes in the URL. Read template, replace, write.
render() {
  local content
  content="$(cat "$TEMPLATE")"
  content="${content//__ZHC_PIXEL_ENDPOINT__/$ENDPOINT}"
  content="${content//__ZHC_PIXEL_SITE_ID__/$ZHC_PIXEL_SITE_ID}"
  content="${content//__ZHC_PIXEL_AGENT_ID__/$AGENT_ID}"
  printf '%s\n' "$content"
}
render > "$OUT_FILE"

# Guard: no placeholder may remain in the rendered output.
if grep -q '__ZHC_PIXEL_' "$OUT_FILE"; then
  echo "[27-render-pixel-js] ERROR: unresolved placeholder remains in $OUT_FILE" >&2
  grep -n '__ZHC_PIXEL_' "$OUT_FILE" >&2
  exit 3
fi

# Persist the site id + endpoint to the run-state so the deploy + hook scripts agree.
RUN_STATE="${RUN_STATE_FILE:-$MASTER_FILES_DIR/.skill38-run-state.env}"
upsert_state() {
  local k="$1" v="$2"
  [ -f "$RUN_STATE" ] || : > "$RUN_STATE"
  if grep -qE "^${k}=" "$RUN_STATE" 2>/dev/null; then
    # portable in-place replace
    tmp="$(mktemp)"; grep -vE "^${k}=" "$RUN_STATE" > "$tmp"; mv "$tmp" "$RUN_STATE"
  fi
  printf '%s=%s\n' "$k" "$v" >> "$RUN_STATE"
}
upsert_state "ZHC_PIXEL_SITE_ID" "$ZHC_PIXEL_SITE_ID"
upsert_state "ZHC_PIXEL_HOSTNAME" "$PIXEL_HOSTNAME"
upsert_state "ZHC_PIXEL_AGENT_ID" "$AGENT_ID"
upsert_state "ZHC_PIXEL_RENDERED" "true"

echo "[27-render-pixel-js] rendered: $OUT_FILE" >&2
echo "[27-render-pixel-js]   site_id : $ZHC_PIXEL_SITE_ID" >&2
echo "[27-render-pixel-js]   agent   : $AGENT_ID" >&2
echo "[27-render-pixel-js]   endpoint: $ENDPOINT" >&2
echo "" >&2
echo "[27-render-pixel-js] Operator paste-snippet for the client's site (<head>):" >&2
echo "  <script src=\"https://${PIXEL_HOSTNAME}/zhc-pixel.js\" async></script>" >&2
echo "" >&2
echo "[27-render-pixel-js] Next: scripts/28-configure-pixel-hook.sh (register the hook + Pixel Concierge agent)," >&2
echo "[27-render-pixel-js]       then scripts/26-verify-pixel-prerequisites.sh + scripts/29-deploy-pixel-cloudflare.sh (scope-gated deploy)." >&2
