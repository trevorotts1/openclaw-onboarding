#!/usr/bin/env bash
# lib-records.sh — Skill 40 TIERED public-records ROUTER.
#
# address/ZIP -> county+state -> Tier 1? -> Tier 2? -> Tier 3? -> else Tier 4
# (HONEST GAP). THIS ROUTER NEVER FABRICATES A RECORD. When no tier can serve a
# query, or compliance/cost gates block it, it returns an honest-gap JSON object
# ("tier":"tier4_honest_gap" / "blocked": ...) — it NEVER invents an owner,
# deed, lien, NOD, tax balance, or permit. A record without source +
# retrieved_at is not a record. qc-no-fabrication.sh machine-enforces this.
#
# Compliance is enforced BEFORE any live fetch:
#   - robots.txt checked (disallow -> honest gap)
#   - per-target ToS must be acknowledged (tos_url in the config)
#   - every returned record is stamped source + retrieved_at
# CONTRACT: an unattributed result (no source + retrieved_at) is not a record and is refused.
# Cost + rate caps via lib-cost-cap.sh; 30-day cache.
#
# Subcommands:
#   resolve "<address-or-zip>"          -> {county_fips, state} or {resolved:false}
#   tier "<county_fips>"                -> which tier serves this county (config-driven)
#   robots_ok "<base_url>" "<path>"     -> exit 0 if allowed, 1 if disallowed
#   query "<address-or-zip>" "<type>" [--force-refresh]  -> the full routed query
#
# OS-aware, requires curl + jq. Tier-1 configs live in
# references/tier1-counties/*.json; Tier-3 configs in the operator's master files.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TIER1_DIR="$SKILL_ROOT/references/tier1-counties"
EVENTS="$SCRIPT_DIR/lib-pr-events.sh"
COSTCAP="$SCRIPT_DIR/lib-cost-cap.sh"

PR_CACHE_TTL_DAYS="${PR_CACHE_TTL_DAYS:-30}"

_cache_dir() {
  local mfd="${MASTER_FILES_DIR:-}"
  if [ -z "$mfd" ]; then case "$(uname -s)" in Darwin) mfd="$HOME/Downloads" ;; *) mfd="/data" ;; esac; fi
  printf '%s/public-records-cache' "$mfd"
}

_emit() { bash "$EVENTS" pr_event "$1" "$2" >/dev/null 2>&1 || true; }

# ---------- resolve address/ZIP -> county_fips + state (no fabrication) ----------
resolve() {
  local q="${1:-}"
  [ -n "$q" ] || { echo '{"resolved":false,"reason":"empty query"}'; return 0; }
  command -v curl >/dev/null 2>&1 || { echo '{"resolved":false,"reason":"curl missing"}'; return 0; }
  command -v jq >/dev/null 2>&1 || { echo '{"resolved":false,"reason":"jq missing"}'; return 0; }
  local enc resp
  enc="$(jq -rn --arg a "$q" '$a|@uri')"
  # Reuse the keyless US Census geocoder for county FIPS (same source Skill 39 uses).
  resp="$(curl -fsS --max-time 20 \
    "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress?address=${enc}&benchmark=Public_AR_Current&vintage=Current_Current&format=json" \
    2>/dev/null || true)"
  if [ -n "$resp" ] && printf '%s' "$resp" | jq -e '.result.addressMatches | length > 0' >/dev/null 2>&1; then
    printf '%s' "$resp" | jq -c '
      .result.addressMatches[0].geographies.Counties[0] as $c
      | {resolved:true, source:"census",
         county_fips: (($c.STATE // "") + ($c.COUNTY // "")),
         state: ($c.STATE // null)}'
    return 0
  fi
  # HONEST GAP — could not resolve county. NEVER guess.
  echo '{"resolved":false,"reason":"could not resolve county/state from query"}'
  return 0
}

# ---------- tier selection (config-driven) ----------
tier() {
  local fips="${1:-}"
  [ -n "$fips" ] || { echo '{"tier":"tier4_honest_gap","reason":"county_unresolved"}'; return 0; }
  # Tier 1: a curated config whose "county_fips" matches.
  if [ -d "$TIER1_DIR" ]; then
    local f
    for f in "$TIER1_DIR"/*.json; do
      [ -f "$f" ] || continue
      if command -v jq >/dev/null 2>&1; then
        local cfips slug platform
        cfips="$(jq -r '.county_fips // empty' "$f" 2>/dev/null || true)"
        if [ -n "$cfips" ] && [ "$cfips" = "$fips" ]; then
          slug="$(jq -r '.slug // empty' "$f")"
          platform="$(jq -r '.platform // empty' "$f")"
          jq -cn --arg slug "$slug" --arg plat "$platform" \
            '{tier:"tier1", target_ref:$slug, platform:$plat, reason:"curated tier1 config"}'
          return 0
        fi
      fi
    done
  fi
  # Tier 2: a county on a known platform with an adapter, but no Tier-1 config.
  # (Config-driven: a Tier-1 config that names a platform but is marked
  # tier2_only would route here; absent that, fall through honestly.)
  # Tier 3: an operator config in the master files (checked by the caller's
  # build step). If none, fall through.
  # Else Tier 4 — honest gap.
  echo '{"tier":"tier4_honest_gap","reason":"no_online_db"}'
  return 0
}

# ---------- robots.txt compliance (binding) ----------
robots_ok() {
  local base="${1:-}" path="${2:-/}"
  [ -n "$base" ] || return 1
  command -v curl >/dev/null 2>&1 || return 1
  local robots
  robots="$(curl -fsS --max-time 10 "${base%/}/robots.txt" 2>/dev/null || true)"
  # No robots.txt => not disallowed (allowed by convention). Present => honor a
  # global "User-agent: *" Disallow that prefixes our path.
  [ -z "$robots" ] && return 0
  # Extract Disallow lines under the global agent block (simple, conservative).
  local dis
  dis="$(printf '%s\n' "$robots" | awk '
    BEGIN{IGNORECASE=1; inglobal=0}
    /^[[:space:]]*user-agent:[[:space:]]*\*/ {inglobal=1; next}
    /^[[:space:]]*user-agent:/ {inglobal=0}
    inglobal && /^[[:space:]]*disallow:/ {sub(/^[[:space:]]*[Dd]isallow:[[:space:]]*/,""); print}
  ')"
  local rule
  while IFS= read -r rule; do
    [ -z "$rule" ] && continue
    # "Disallow: /" blocks everything; a prefix match blocks that subtree.
    case "$path" in "$rule"*) return 1 ;; esac
  done <<< "$dis"
  return 0
}

# ---------- the full routed query ----------
query() {
  local q="${1:-}" rtype="${2:-ownership}"; shift 2 2>/dev/null || true
  local force="false"
  for a in "$@"; do [ "$a" = "--force-refresh" ] && force="true"; done
  local qref; qref="q_$(date +%s)_$RANDOM"

  # 1) resolve county
  local r fips state
  r="$(resolve "$q")"
  if [ "$(printf '%s' "$r" | jq -r '.resolved' 2>/dev/null)" != "true" ]; then
    _emit honest_gap "$(printf '{"query_ref":"%s","target_ref":"unknown","reason":"county_unresolved"}' "$qref")"
    echo "$r" | jq -c '. + {tier:"tier4_honest_gap"}' 2>/dev/null || echo '{"tier":"tier4_honest_gap","reason":"county_unresolved"}'
    return 0
  fi
  fips="$(printf '%s' "$r" | jq -r '.county_fips')"
  state="$(printf '%s' "$r" | jq -r '.state')"

  # 2) tier selection
  local t tname target
  t="$(tier "$fips")"
  tname="$(printf '%s' "$t" | jq -r '.tier')"
  target="$(printf '%s' "$t" | jq -r '.target_ref // "unknown"')"
  _emit tier_decision "$(jq -cn --arg q "$qref" --arg tr "$target" --arg tier "$tname" --arg f "$fips" --arg s "$state" --arg reason "$(printf '%s' "$t" | jq -r '.reason')" \
    '{query_ref:$q, target_ref:$tr, tier:$tier, county_fips:$f, state:$s, reason:$reason}')"

  if [ "$tname" = "tier4_honest_gap" ]; then
    _emit honest_gap "$(jq -cn --arg q "$qref" --arg tr "$target" '{query_ref:$q, target_ref:$tr, reason:"no_online_db"}')"
    # HONEST GAP — never fabricate.
    echo "$t" | jq -c --arg q "$qref" '. + {query_ref:$q, available:false}'
    return 0
  fi

  # 3) cache check (fresh hit = free + instant)
  local cdir key cfile
  cdir="$(_cache_dir)"; mkdir -p "$cdir" 2>/dev/null || true
  key="$(printf '%s|%s|%s' "$target" "$fips" "$rtype" | (shasum 2>/dev/null || sha1sum) | awk '{print $1}')"
  cfile="$cdir/$key.json"
  if [ "$force" != "true" ] && [ -f "$cfile" ]; then
    local age_days
    if [ "$(uname -s)" = "Darwin" ]; then
      age_days=$(( ( $(date +%s) - $(stat -f %m "$cfile") ) / 86400 ))
    else
      age_days=$(( ( $(date +%s) - $(stat -c %Y "$cfile") ) / 86400 ))
    fi
    if [ "$age_days" -lt "$PR_CACHE_TTL_DAYS" ]; then
      _emit cache_hit "$(jq -cn --arg q "$qref" --arg tr "$target" --arg rt "$rtype" --argjson age "$age_days" \
        '{query_ref:$q, target_ref:$tr, record_type:$rt, age_days:$age}')"
      jq -c --arg q "$qref" '. + {query_ref:$q, cache_hit:true}' "$cfile" 2>/dev/null \
        || cat "$cfile"
      return 0
    fi
  fi
  [ "$force" = "true" ] && _emit force_refresh "$(jq -cn --arg q "$qref" --arg tr "$target" --arg rt "$rtype" '{query_ref:$q, target_ref:$tr, record_type:$rt}')"

  # 4) cost cap (per-day) — refuse over the cap (never silent overrun)
  if ! bash "$COSTCAP" under_daily_cap; then
    _emit cost_block "$(jq -cn --arg q "$qref" --arg tr "$target" '{query_ref:$q, target_ref:$tr, reason:"daily_cap"}')"
    echo '{"blocked":true,"reason":"daily_cap","tier":"'"$tname"'"}'
    return 0
  fi

  # 5) compliance gate + live fetch happen here in the live runtime. In this
  #    library the live fetch + selector extraction is delegated to the
  #    tier-specific adapter (Tier-1 config / Tier-2 adapter / Tier-3 config),
  #    which MUST (a) pass robots_ok, (b) have an acknowledged tos_url, and
  #    (c) stamp source + retrieved_at on every record. If the adapter cannot
  #    satisfy all three, it returns an honest gap rather than a record.
  #    The router NEVER synthesizes a record itself.
  echo "$t" | jq -c --arg q "$qref" --arg rt "$rtype" \
    '. + {query_ref:$q, record_type:$rt, available:false, note:"live retrieval is performed by the tier adapter after robots+ToS+attribution pass; no record is fabricated by the router"}'
  return 0
}

if [ "${BASH_SOURCE[0]:-}" = "${0:-}" ]; then
  cmd="${1:-}"; shift || true
  case "$cmd" in
    resolve)   resolve "$@" ;;
    tier)      tier "$@" ;;
    robots_ok) robots_ok "$@"; exit $? ;;
    query)     query "$@" ;;
    -h|--help) sed -n '1,30p' "$0" ;;
    *) echo "usage: $0 {resolve <q>|tier <fips>|robots_ok <base> <path>|query <q> <type> [--force-refresh]}" >&2; exit 2 ;;
  esac
fi
