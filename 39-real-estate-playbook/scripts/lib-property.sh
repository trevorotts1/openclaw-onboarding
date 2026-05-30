#!/usr/bin/env bash
# lib-property.sh — Skill 39 property-intelligence provider abstraction.
#
# ONE contract, MANY providers, OPERATOR-SUPPLIED env keys, HONEST GAP on
# absence. THIS LIBRARY NEVER FABRICATES PROPERTY DATA. When a provider key is
# missing or a lookup returns nothing, the relevant function prints a JSON
# object with "available": false (or "matched": false for geocode) and a
# machine-readable reason — it NEVER invents an address, price, comp, owner, or
# photo. See references/property-provider-abstraction.md for how to add/swap a
# provider, and qc-no-fabrication.sh which machine-enforces this floor.
#
# Subcommands:
#   geocode "<raw address>"     -> normalize + geocode (keyless US Census first)
#   lookup "<normalized addr>"  -> property record (provider-gated)
#   comps "<normalized addr>"   -> comparable sales (provider-gated)
#   streetview "<lat>,<lon>"    -> Street View image URL (Google key-gated)
#
# OS-aware, requires curl + jq. Read-only (no state writes beyond stdout).

set -uo pipefail

_need() { command -v "$1" >/dev/null 2>&1 || { echo "{\"error\":\"$1 not found on PATH\"}"; exit 2; }; }

# ---------- geocode (keyless US Census first; optional Google/Mapbox) ----------
geocode() {
  local addr="${1:-}"
  [ -n "$addr" ] || { echo '{"matched":false,"reason":"empty address"}'; return 0; }
  _need curl; _need jq

  # 1) US Census Geocoder — free, no key. US addresses only.
  local enc resp
  enc="$(jq -rn --arg a "$addr" '$a|@uri')"
  resp="$(curl -fsS --max-time 20 \
    "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress?address=${enc}&benchmark=Public_AR_Current&vintage=Current_Current&format=json" \
    2>/dev/null || true)"
  if [ -n "$resp" ] && printf '%s' "$resp" | jq -e '.result.addressMatches | length > 0' >/dev/null 2>&1; then
    printf '%s' "$resp" | jq -c '
      .result.addressMatches[0] as $m
      | {
          matched: true,
          source: "census",
          normalized: $m.matchedAddress,
          lat: $m.coordinates.y,
          lon: $m.coordinates.x,
          county_fips: (($m.geographies.Counties[0].STATE // "") + ($m.geographies.Counties[0].COUNTY // "")),
          state: ($m.geographies.Counties[0].STATE // null)
        }'
    return 0
  fi

  # 2) Optional Google Geocoding (precise / non-US) if keyed.
  if [ -n "${GOOGLE_MAPS_API_KEY:-}" ]; then
    resp="$(curl -fsS --max-time 20 \
      "https://maps.googleapis.com/maps/api/geocode/json?address=${enc}&key=${GOOGLE_MAPS_API_KEY}" \
      2>/dev/null || true)"
    if [ -n "$resp" ] && printf '%s' "$resp" | jq -e '.results | length > 0' >/dev/null 2>&1; then
      printf '%s' "$resp" | jq -c '
        .results[0] as $r
        | {matched:true, source:"google", normalized:$r.formatted_address,
           lat:$r.geometry.location.lat, lon:$r.geometry.location.lng,
           county_fips:null, state:null}'
      return 0
    fi
  fi

  # 3) Optional Mapbox if keyed.
  if [ -n "${MAPBOX_TOKEN:-}" ]; then
    resp="$(curl -fsS --max-time 20 \
      "https://api.mapbox.com/geocoding/v5/mapbox.places/${enc}.json?access_token=${MAPBOX_TOKEN}&limit=1" \
      2>/dev/null || true)"
    if [ -n "$resp" ] && printf '%s' "$resp" | jq -e '.features | length > 0' >/dev/null 2>&1; then
      printf '%s' "$resp" | jq -c '
        .features[0] as $f
        | {matched:true, source:"mapbox", normalized:$f.place_name,
           lat:$f.center[1], lon:$f.center[0], county_fips:null, state:null}'
      return 0
    fi
  fi

  # HONEST GAP — no match. NEVER guess coordinates.
  echo '{"matched":false,"source":"none","reason":"no geocoder matched this address"}'
  return 0
}

# ---------- lookup (provider-gated; honest gap without a key) ----------
lookup() {
  local addr="${1:-}"
  [ -n "$addr" ] || { echo '{"available":false,"reason":"empty address"}'; return 0; }

  # Example provider adapter: RentCast (operator-supplied RENTCAST_API_KEY).
  # Add your own provider adapter here following the same contract; see
  # references/property-provider-abstraction.md.
  if [ -n "${RENTCAST_API_KEY:-}" ]; then
    _need curl; _need jq
    local enc resp
    enc="$(jq -rn --arg a "$addr" '$a|@uri')"
    resp="$(curl -fsS --max-time 25 -H "X-Api-Key: ${RENTCAST_API_KEY}" \
      "https://api.rentcast.io/v1/properties?address=${enc}" 2>/dev/null || true)"
    if [ -n "$resp" ] && printf '%s' "$resp" | jq -e 'type=="array" and length>0' >/dev/null 2>&1; then
      # Return field NAMES present (not values) so the EVENT LOG stays PII-free;
      # the agent gets the full record on stdout for the live reply.
      printf '%s' "$resp" | jq -c '{available:true, source:"rentcast", record:.[0]}'
      return 0
    fi
    echo '{"available":false,"source":"rentcast","reason":"provider returned no record for this address"}'
    return 0
  fi

  # HONEST GAP — no property-data provider configured. NEVER fabricate a record.
  echo '{"available":false,"source":"none","reason":"no property-data provider configured"}'
  return 0
}

# ---------- comps (provider-gated; honest gap without a key) ----------
comps() {
  local addr="${1:-}"
  [ -n "$addr" ] || { echo '{"available":false,"reason":"empty address"}'; return 0; }

  if [ -n "${RENTCAST_API_KEY:-}" ]; then
    _need curl; _need jq
    local enc resp
    enc="$(jq -rn --arg a "$addr" '$a|@uri')"
    resp="$(curl -fsS --max-time 25 -H "X-Api-Key: ${RENTCAST_API_KEY}" \
      "https://api.rentcast.io/v1/avm/value?address=${enc}" 2>/dev/null || true)"
    if [ -n "$resp" ] && printf '%s' "$resp" | jq -e 'has("comparables")' >/dev/null 2>&1; then
      printf '%s' "$resp" | jq -c '{available:true, source:"rentcast", comp_count:(.comparables|length), comparables:.comparables}'
      return 0
    fi
    echo '{"available":false,"source":"rentcast","reason":"provider returned no comps for this address"}'
    return 0
  fi

  # HONEST GAP — no comps source. NEVER fabricate comps.
  echo '{"available":false,"source":"none","reason":"no comps provider configured"}'
  return 0
}

# ---------- streetview (Google key-gated; honest gap without a key) ----------
streetview() {
  local latlon="${1:-}"
  [ -n "$latlon" ] || { echo '{"available":false,"reason":"empty lat,lon"}'; return 0; }
  if [ -z "${GOOGLE_MAPS_API_KEY:-}" ]; then
    # HONEST GAP — no Street View key. NEVER fabricate an image.
    echo '{"available":false,"source":"none","reason":"GOOGLE_MAPS_API_KEY not set"}'
    return 0
  fi
  _need jq
  local enc url
  enc="$(jq -rn --arg s "$latlon" '$s|@uri')"
  url="https://maps.googleapis.com/maps/api/streetview?size=640x640&location=${enc}&key=${GOOGLE_MAPS_API_KEY}"
  jq -cn --arg url "$url" '{available:true, source:"google_streetview", image_url:$url}'
  return 0
}

if [ "${BASH_SOURCE[0]:-}" = "${0:-}" ]; then
  cmd="${1:-}"; shift || true
  case "$cmd" in
    geocode)    geocode "$@" ;;
    lookup)     lookup "$@" ;;
    comps)      comps "$@" ;;
    streetview) streetview "$@" ;;
    -h|--help)  sed -n '1,20p' "$0" ;;
    *) echo "usage: $0 {geocode|lookup|comps|streetview} <arg>" >&2; exit 2 ;;
  esac
fi
