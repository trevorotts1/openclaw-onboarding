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
#   geocode "<raw address>"          -> normalize + geocode (keyless US Census first)
#   lookup "<normalized addr>"       -> property record (provider-gated)
#   comps "<normalized addr>"        -> comparable sales (provider-gated)
#   streetview "<lat>,<lon>" [out]   -> fetch the Street View image BYTES
#                                       server-side and emit a local image_path
#                                       (Google key-gated; the API key is NEVER
#                                        placed in the emitted URL/output)
#
# OS-aware, requires curl + jq. Read-only apart from the streetview image file
# it writes (a local artifact for the agent to attach) — no other state writes.

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
# SECURITY (FIX-S36-09): the API key is used ONLY in server-side requests inside
# this process — it is NEVER placed in the emitted image_url (which would ship the
# raw key into the client conversation and the event log). We (1) probe the free
# Street View METADATA endpoint and honest-gap when status != OK (no imagery at
# that point), then (2) fetch the image BYTES server-side and emit a LOCAL
# image_path. The caller attaches that file; no keyed URL ever leaves the process.
streetview() {
  local latlon="${1:-}" out="${2:-}"
  [ -n "$latlon" ] || { echo '{"available":false,"reason":"empty lat,lon"}'; return 0; }
  if [ -z "${GOOGLE_MAPS_API_KEY:-}" ]; then
    # HONEST GAP — no Street View key. NEVER fabricate an image.
    echo '{"available":false,"source":"none","reason":"GOOGLE_MAPS_API_KEY not set"}'
    return 0
  fi
  _need curl; _need jq
  local enc meta status
  enc="$(jq -rn --arg s "$latlon" '$s|@uri')"

  # 1) Probe the metadata endpoint FIRST (free, no image quota). Only "OK" means
  #    imagery exists for this location — anything else is an honest gap, never a
  #    fabricated / blank tile.
  meta="$(curl -fsS --max-time 20 \
    "https://maps.googleapis.com/maps/api/streetview/metadata?size=640x640&location=${enc}&key=${GOOGLE_MAPS_API_KEY}" \
    2>/dev/null || true)"
  status=""
  [ -n "$meta" ] && status="$(printf '%s' "$meta" | jq -r '.status // empty' 2>/dev/null || true)"
  if [ "$status" != "OK" ]; then
    jq -cn --arg st "${status:-unreachable}" \
      '{available:false, source:"google_streetview", reason:("street view metadata status: " + $st)}'
    return 0
  fi

  # 2) Fetch the image BYTES server-side to a local file (key stays in-process).
  local dest
  if [ -n "$out" ]; then
    dest="$out"
    mkdir -p "$(dirname "$dest")" 2>/dev/null || true
  else
    dest="$(mktemp -t skill39-streetview.XXXXXX 2>/dev/null || mktemp)"
  fi
  if curl -fsS --max-time 25 -o "$dest" \
      "https://maps.googleapis.com/maps/api/streetview?size=640x640&location=${enc}&key=${GOOGLE_MAPS_API_KEY}" \
      2>/dev/null && [ -s "$dest" ]; then
    local bytes ctype
    case "$(uname -s)" in
      Darwin) bytes="$(stat -f%z "$dest" 2>/dev/null || echo 0)" ;;
      *)      bytes="$(stat -c%s "$dest" 2>/dev/null || echo 0)" ;;
    esac
    ctype="image/jpeg"
    command -v file >/dev/null 2>&1 && ctype="$(file --brief --mime-type "$dest" 2>/dev/null || echo image/jpeg)"
    # Emit the LOCAL path + metadata only. NO url, NO key.
    jq -cn --arg path "$dest" --argjson bytes "${bytes:-0}" --arg ctype "$ctype" \
      '{available:true, source:"google_streetview", image_path:$path, bytes:$bytes, content_type:$ctype}'
    return 0
  fi

  # Fetch failed after an OK metadata probe — honest gap, no fabrication.
  [ -z "$out" ] && [ -f "$dest" ] && rm -f "$dest" 2>/dev/null || true
  echo '{"available":false,"source":"google_streetview","reason":"street view image fetch failed"}'
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
