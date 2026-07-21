#!/usr/bin/env bash
# 02-configure-providers.sh — Skill 39
# Records which property/geocode/Street View providers are keyed and prints an
# HONEST-GAP summary. Writes a non-secret provider-status file — provider NAMES
# only, NEVER key values. Idempotent.
#
# T2-32: this script and property-lookup.sh disagreed on three axes at once —
# the PATH (a fixed $HOME path here vs the resolved master-files directory
# there), the CAPABILITY NAMES (geocode/lookup/comps/streetview here vs
# geocode/property_lookup/street_view/comps there), and the STATE SHAPE (key
# names mapped to set/unset here vs a "state":"AVAILABLE" field there). The
# consumer therefore saw no status file at all, and its capability checks would
# not have lined up if it had, so every provider read as unavailable.
#
# All three now come from references/provider-status-contract.md
# (`provider-status/v1`), and validate-provider-status.sh enforces it on both
# sides.

set -uo pipefail
P="[skill 39][providers]"
_SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# ---- Resolve MASTER_FILES_DIR through the SAME resolver the consumer uses ----
# shellcheck source=/dev/null
[ -f "$_SELF_DIR/lib-re-events.sh" ] && . "$_SELF_DIR/lib-re-events.sh"
if command -v re_events_master_dir >/dev/null 2>&1; then
  if ! MFD="$(re_events_master_dir)"; then
    echo "$P ERROR: MASTER_FILES_DIR unresolved — set MASTER_FILES_DIR or run 01-locate-master-files-folder.sh first (refusing to fall back to a fixed home path)." >&2
    exit 2
  fi
else
  MFD="${MASTER_FILES_DIR:-}"
  if [ -z "$MFD" ] || [ ! -d "$MFD" ]; then
    echo "$P ERROR: MASTER_FILES_DIR unresolved and lib-re-events.sh resolver unavailable." >&2
    exit 2
  fi
fi
STATUS_FILE="$MFD/.skill-39-provider-status.json"

probe() { # name -> "set"/"unset" (never the value)
  if [ -n "${!1:-}" ]; then echo "set"; else echo "unset"; fi
}

GMK="$(probe GOOGLE_MAPS_API_KEY)"
MBX="$(probe MAPBOX_TOKEN)"
RCK="$(probe RENTCAST_API_KEY)"
RESO="$(probe RESO_API_TOKEN)"

# ---- Build the capability states in the CONTRACT vocabulary -----------------
# geocode is always available: the US Census geocoder is keyless.
GEO_PROVIDERS='"census"'
[ "$GMK" = set ]  && GEO_PROVIDERS="$GEO_PROVIDERS,\"google_maps\""
[ "$MBX" = set ]  && GEO_PROVIDERS="$GEO_PROVIDERS,\"mapbox\""

DATA_PROVIDERS=""
[ "$RCK" = set ]  && DATA_PROVIDERS='"rentcast"'
[ "$RESO" = set ] && { [ -n "$DATA_PROVIDERS" ] && DATA_PROVIDERS="$DATA_PROVIDERS,\"reso\"" || DATA_PROVIDERS='"reso"'; }
if [ -n "$DATA_PROVIDERS" ]; then DATA_STATE="AVAILABLE"; else DATA_STATE="HONEST_GAP"; fi

if [ "$GMK" = set ]; then SV_STATE="AVAILABLE"; SV_PROVIDERS='"google_streetview"'; else SV_STATE="HONEST_GAP"; SV_PROVIDERS=""; fi

NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

mkdir -p "$MFD" 2>/dev/null || true
cat > "$STATUS_FILE" <<EOF
{
  "schema": "provider-status/v1",
  "generated_at": "$NOW",
  "capabilities": {
    "geocode":         { "state": "AVAILABLE",   "providers": [$GEO_PROVIDERS] },
    "property_lookup": { "state": "$DATA_STATE", "providers": [$DATA_PROVIDERS] },
    "street_view":     { "state": "$SV_STATE",   "providers": [$SV_PROVIDERS] },
    "comps":           { "state": "$DATA_STATE", "providers": [$DATA_PROVIDERS] }
  }
}
EOF

# ---- Validate what we just wrote. A producer that writes a non-conforming
# ---- artifact must fail here, not leave the consumer to discover it. --------
VALIDATOR="$_SELF_DIR/validate-provider-status.sh"
if [ -x "$VALIDATOR" ] || [ -f "$VALIDATOR" ]; then
  if ! bash "$VALIDATOR" "$STATUS_FILE"; then
    echo "$P ERROR: the provider-status file just written does not conform to provider-status/v1." >&2
    echo "$P        See references/provider-status-contract.md. Refusing to report success." >&2
    exit 1
  fi
else
  echo "$P ERROR: validate-provider-status.sh not found beside this script — cannot prove the artifact conforms." >&2
  echo "$P        Reporting this as a failure rather than assuming the write was correct." >&2
  exit 2
fi

echo "$P provider status written to $STATUS_FILE (provider NAMES + state only; no key values)"
echo "$P HONEST-GAP summary:"
echo "$P    geocode        : ALWAYS available (US Census, keyless)$( [ "$GMK" = set ] && echo ' + Google' )$( [ "$MBX" = set ] && echo ' + Mapbox' )"
if [ "$DATA_STATE" = AVAILABLE ]; then
  echo "$P    property_lookup/comps: available via keyed provider"
else
  echo "$P    property_lookup/comps: HONEST GAP — no property-data provider keyed (returns available:false; never fabricated)"
fi
if [ "$SV_STATE" = AVAILABLE ]; then
  echo "$P    street_view    : available (Google)"
else
  echo "$P    street_view    : HONEST GAP — GOOGLE_MAPS_API_KEY unset (returns available:false; never fabricated)"
fi
exit 0
