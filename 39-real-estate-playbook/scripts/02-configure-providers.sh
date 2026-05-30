#!/usr/bin/env bash
# 02-configure-providers.sh — Skill 39
# Records which property/geocode/Street View providers are keyed and prints an
# HONEST-GAP summary. Writes a non-secret provider-status file (key NAMES +
# set/unset only — NEVER the key values). Idempotent.

set -uo pipefail
P="[skill 39][providers]"

mkdir -p "$HOME/.openclaw" 2>/dev/null || true
STATUS_FILE="$HOME/.openclaw/.skill-39-provider-status.json"

probe() { # name -> "set"/"unset" (never the value)
  if [ -n "${!1:-}" ]; then echo "set"; else echo "unset"; fi
}

GMK="$(probe GOOGLE_MAPS_API_KEY)"
MBX="$(probe MAPBOX_TOKEN)"
RCK="$(probe RENTCAST_API_KEY)"
RESO="$(probe RESO_API_TOKEN)"

if command -v jq >/dev/null 2>&1; then
  jq -n \
    --arg gmk "$GMK" --arg mbx "$MBX" --arg rck "$RCK" --arg reso "$RESO" \
    '{
      geocode:   {google_maps_api_key:$gmk, mapbox_token:$mbx, census:"keyless-always-available"},
      lookup:    {rentcast_api_key:$rck, reso_api_token:$reso},
      comps:     {rentcast_api_key:$rck, reso_api_token:$reso},
      streetview:{google_maps_api_key:$gmk}
    }' > "$STATUS_FILE"
else
  # jq-less fallback (still no secret values written)
  cat > "$STATUS_FILE" <<EOF
{"geocode":{"google_maps_api_key":"$GMK","mapbox_token":"$MBX","census":"keyless-always-available"},
 "lookup":{"rentcast_api_key":"$RCK","reso_api_token":"$RESO"},
 "comps":{"rentcast_api_key":"$RCK","reso_api_token":"$RESO"},
 "streetview":{"google_maps_api_key":"$GMK"}}
EOF
fi

echo "$P provider status written to $STATUS_FILE (key NAMES + set/unset only; no values)"
echo "$P HONEST-GAP summary:"
echo "$P    geocoding   : ALWAYS available (US Census, keyless)$( [ "$GMK" = set ] && echo ' + Google' )$( [ "$MBX" = set ] && echo ' + Mapbox' )"
[ "$RCK" = set ] || [ "$RESO" = set ] \
  && echo "$P    lookup/comps: available via keyed provider" \
  || echo "$P    lookup/comps: HONEST GAP — no property-data provider keyed (returns available:false; never fabricated)"
[ "$GMK" = set ] \
  && echo "$P    street view : available (Google)" \
  || echo "$P    street view : HONEST GAP — GOOGLE_MAPS_API_KEY unset (returns available:false; never fabricated)"
exit 0
