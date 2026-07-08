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

# MASTER_FILES_DIR resolution — env, then the persisted selection written by
# 01-locate-master-files-folder.sh. NEVER a silent Downloads fallback: an
# unresolved dir would send the cache + per-day cap counter to a throwaway path
# (a fresh caller gets a zero cap counter, weakening the 200/day cap). Fail LOUD.
_master_files_dir() {
  local mfd="${MASTER_FILES_DIR:-}"
  local state="${HOME:-/root}/.openclaw/.skill-40-master-files-dir"
  if [ -z "$mfd" ] && [ -f "$state" ]; then
    mfd="$(tr -d '[:space:]' < "$state" 2>/dev/null || true)"
  fi
  if [ -z "$mfd" ]; then
    echo "[skill 40][records] FATAL: MASTER_FILES_DIR unresolved — set MASTER_FILES_DIR or run scripts/01-locate-master-files-folder.sh." >&2
    return 1
  fi
  printf '%s' "$mfd"
}

_cache_dir() {
  local mfd; mfd="$(_master_files_dir)" || return 1
  printf '%s/public-records-cache' "$mfd"
}

# Operator-built Tier-3 configs live beside the cache (written by 06-build-tier3-config.sh).
_tier3_dir() {
  local mfd; mfd="$(_master_files_dir)" || return 1
  printf '%s/public-records-tier3' "$mfd"
}

_emit() { bash "$EVENTS" pr_event "$1" "$2" >/dev/null 2>&1 || true; }

# ---------- compliance + attribution helpers (all enforced in query()) ----------

# _is_placeholder <value> — exit 0 if the value is empty or an unfilled
# "<OPERATOR_FILLS_…>" / "<https://…>" template placeholder. A placeholder URL is
# NOT a real acknowledgeable target.
_is_placeholder() {
  local v="${1:-}"
  [ -z "$v" ] && return 0
  case "$v" in
    *"<"*|*OPERATOR_FILLS*|*"how-to-fill"*|*"css-selector"*) return 0 ;;
  esac
  return 1
}

# tos_url_valid <url> — exit 0 if the tos_url is a real http(s) URL (not empty,
# not a placeholder). Used to reject configs that merely CLAIM a ToS reference.
tos_url_valid() {
  local u="${1:-}"
  _is_placeholder "$u" && return 1
  case "$u" in http://*|https://*) return 0 ;; *) return 1 ;; esac
}

# Persisted per-target ToS acknowledgement (recorded by ack_tos). A target with a
# valid tos_url STILL needs an explicit operator ack on file before any live fetch.
_tos_ack_file() {
  local target="${1:-}" d
  [ -n "$target" ] || return 1
  d="$(_cache_dir)" || return 1
  printf '%s/.tos-ack-%s' "$d" "$(printf '%s' "$target" | tr -c 'A-Za-z0-9_-' '_')"
}

# ack_tos <target_ref> <tos_url> — persist the operator's ToS acknowledgement for
# a target. Refuses a placeholder/empty tos_url (nothing to acknowledge).
ack_tos() {
  local target="${1:-}" url="${2:-}" f
  [ -n "$target" ] || { echo "ack_tos: missing target_ref" >&2; return 2; }
  tos_url_valid "$url" || { echo "ack_tos: refusing to record a placeholder/invalid tos_url for $target" >&2; return 1; }
  f="$(_tos_ack_file "$target")" || { echo "ack_tos: cache dir unresolved" >&2; return 1; }
  mkdir -p "$(dirname "$f")" 2>/dev/null || true
  printf '%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$url" > "$f" || return 1
  echo "[skill 40] ToS acknowledged for $target"
}

# tos_ack_present <target_ref> — exit 0 if a persisted ack exists for the target.
tos_ack_present() {
  local f; f="$(_tos_ack_file "${1:-}")" || return 1
  [ -f "$f" ]
}

# _rule_blocks_path <path> <disallow_rule> — exit 0 if the robots Disallow rule
# blocks the path. Handles the `*` wildcard SAFELY: a bare "/" or "/*" blocks
# everything; a single TRAILING "*" is a prefix rule; any other embedded/multiple
# wildcard is unevaluable → FAIL CLOSED (treat as blocked), never parsed
# literally (the old code compared "/*" as a literal string and never matched).
_rule_blocks_path() {
  local path="${1:-/}" rule="${2:-}"
  [ -n "$rule" ] || return 1
  # strip a Google-style "$" end-anchor conservatively → exact match only
  case "$rule" in
    *'$')
      local base="${rule%\$}"
      [ "$path" = "$base" ] && return 0 || return 1 ;;
  esac
  local stars="${rule//[!\*]/}"      # keep only the '*' characters
  case "${#stars}" in
    0)  case "$path" in "$rule"*) return 0 ;; *) return 1 ;; esac ;;   # literal prefix
    1)  if [ "${rule%\*}*" = "$rule" ]; then                            # single TRAILING '*'
          local pre="${rule%\*}"
          [ -z "$pre" ] && return 0                                     # rule was just "*"
          case "$path" in "$pre"*) return 0 ;; *) return 1 ;; esac
        else
          return 0                                                      # embedded '*' → fail closed
        fi ;;
    *)  return 0 ;;                                                     # 2+ wildcards → fail closed
  esac
}

# robots_disallowed <robots_txt> <path> — exit 0 if the global (User-agent: *)
# block disallows the path. Pure/offline (no network); robots_ok wraps it.
robots_disallowed() {
  local robots="${1:-}" path="${2:-/}"
  [ -n "$robots" ] || return 1
  local dis rule
  dis="$(printf '%s\n' "$robots" | awk '
    BEGIN{IGNORECASE=1; inglobal=0}
    /^[[:space:]]*user-agent:[[:space:]]*\*/ {inglobal=1; next}
    /^[[:space:]]*user-agent:/ {inglobal=0}
    inglobal && /^[[:space:]]*disallow:/ {sub(/^[[:space:]]*[Dd]isallow:[[:space:]]*/,""); print}
  ')"
  while IFS= read -r rule; do
    rule="${rule%$'\r'}"
    [ -z "$rule" ] && continue
    _rule_blocks_path "$path" "$rule" && return 0
  done <<< "$dis"
  return 1
}

# cache_put <target_ref> <county_fips> <record_type> <record_json>
#   ATTRIBUTION-GATED cache WRITE. Refuses (exit 1, writes nothing) unless the
#   record carries BOTH source AND retrieved_at — an unattributed result is not a
#   record. This is the ONLY writer of the cache; a cache_hit is only reachable
#   because a prior attributed retrieval called cache_put here.
cache_put() {
  local target="${1:-}" fips="${2:-}" rtype="${3:-ownership}" rec="${4:-}"
  [ -n "$target" ] && [ -n "$rec" ] || { echo "cache_put: missing target/record" >&2; return 2; }
  command -v jq >/dev/null 2>&1 || { echo "cache_put: jq required" >&2; return 2; }
  printf '%s' "$rec" | jq -e 'type=="object"' >/dev/null 2>&1 || { echo "cache_put: record is not a JSON object" >&2; return 2; }
  # ATTRIBUTION CONTRACT (SK1-25) — refuse a record whose attribution is missing
  # OR structurally implausible. `source` must be a real, non-placeholder origin
  # (a URL, provider slug, or "census" — but NOT empty, a "<…>" placeholder, or
  # "unknown"/"none"), and `retrieved_at` must be an ISO-8601 UTC timestamp — not
  # merely a non-empty string. This raises the forgery bar: a hook can no longer
  # pass the gate by stuffing arbitrary junk (e.g. retrieved_at:"yesterday" or a
  # placeholder source) into those two fields.
  if ! printf '%s' "$rec" | jq -e '
        ((.source // "" | ascii_downcase) as $s
          | ($s != "" and ($s | test("^<") | not) and $s != "unknown" and $s != "none"))
        and ((.retrieved_at // "") | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"))
      ' >/dev/null 2>&1; then
    echo "cache_put: REFUSED — record attribution invalid (source must be a real, non-placeholder origin and retrieved_at an ISO-8601 timestamp; an unattributed/implausible result is not a record)" >&2
    return 1
  fi
  local cdir key cfile
  cdir="$(_cache_dir)" || return 1
  mkdir -p "$cdir" 2>/dev/null || true
  key="$(printf '%s|%s|%s' "$target" "$fips" "$rtype" | (shasum 2>/dev/null || sha1sum) | awk '{print $1}')"
  cfile="$cdir/$key.json"
  printf '%s' "$rec" | jq -c '.' > "$cfile" || return 1
  echo "$cfile"
}

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
      .result.addressMatches[0] as $m
      | $m.geographies.Counties[0] as $c
      | {resolved:true, source:"census",
         county_fips: (($c.STATE // "") + ($c.COUNTY // "")),
         state: ($c.STATE // null),
         county_name: ($c.NAME // null),
         state_abbr: (($m.addressComponents.state) // null)}'
    return 0
  fi
  # HONEST GAP — could not resolve county. NEVER guess.
  echo '{"resolved":false,"reason":"could not resolve county/state from query"}'
  return 0
}

# _config_servable <config.json> — exit 0 only if a Tier-1/Tier-3 config is
# actually usable LIVE: validated==true AND a real (non-placeholder) portal_url
# AND a valid (non-placeholder http/https) tos_url. A config with validated:false
# or placeholder URLs is NOT tier-servable — it falls through, forcing the
# operator through 05-validate-target.sh before any live use.
_config_servable() {
  local f="${1:-}"
  [ -f "$f" ] || return 1
  command -v jq >/dev/null 2>&1 || return 1
  local validated portal tos
  validated="$(jq -r '.validated // false' "$f" 2>/dev/null || echo false)"
  [ "$validated" = "true" ] || return 1
  portal="$(jq -r '.portal_url // .base_url // empty' "$f" 2>/dev/null || true)"
  _is_placeholder "$portal" && return 1
  tos="$(jq -r '.tos_url // empty' "$f" 2>/dev/null || true)"
  tos_url_valid "$tos" || return 1
  return 0
}

# ---------- tier selection (config-driven) ----------
# tier <county_fips> [county_name] [state_abbr]
#   Tier-1 curated config (servable) → Tier-2 vendor adapters (scripts/adapters/*)
#   → operator Tier-3 config (servable) → else Tier-4 honest gap.
tier() {
  local fips="${1:-}" county="${2:-}" st="${3:-}"
  [ -n "$fips" ] || { echo '{"tier":"tier4_honest_gap","reason":"county_unresolved"}'; return 0; }
  local have_jq=0; command -v jq >/dev/null 2>&1 && have_jq=1
  # SK1-24: track a config that MATCHES this county but is not yet servable
  # (validated:false / placeholder URLs). The shipped Tier-1 configs all ship
  # unvalidated by design, so without this the router would return a generic
  # "no_online_db" and hide the fact that a curated config exists and just needs
  # 05-validate-target.sh. Make that tier state EXPLICIT instead.
  local matched_unvalidated=""

  # Tier 1: a curated config whose "county_fips" matches AND is servable.
  if [ "$have_jq" -eq 1 ] && [ -d "$TIER1_DIR" ]; then
    local f
    for f in "$TIER1_DIR"/*.json; do
      [ -f "$f" ] || continue
      local cfips
      cfips="$(jq -r '.county_fips // empty' "$f" 2>/dev/null || true)"
      [ -n "$cfips" ] && [ "$cfips" = "$fips" ] || continue
      if _config_servable "$f"; then
        local slug platform
        slug="$(jq -r '.slug // empty' "$f")"
        platform="$(jq -r '.platform // empty' "$f")"
        jq -cn --arg slug "$slug" --arg plat "$platform" \
          '{tier:"tier1", target_ref:$slug, platform:$plat, reason:"curated tier1 config (validated)"}'
        return 0
      fi
      # matched but not validated/filled → do NOT serve; record it (SK1-24) so
      # the honest gap can say the config exists and just needs validation.
      [ -z "$matched_unvalidated" ] && matched_unvalidated="$(jq -r '.slug // empty' "$f" 2>/dev/null || true)"
    done
  fi

  # Tier 2: iterate the executable vendor adapters (scripts/adapters/*.sh). Each
  # honors the --covers "<county>" "<state>" contract; a covered county routes to
  # that vendor adapter. Coverage is operator-confirmed (empty by default), so an
  # unconfirmed county falls through — never a fabricated route.
  local adir="$SCRIPT_DIR/adapters"
  if [ -n "$county" ] && [ -d "$adir" ]; then
    local ad
    for ad in "$adir"/*.sh; do
      [ -f "$ad" ] || continue
      if bash "$ad" --covers "$county" "$st" >/dev/null 2>&1; then
        local vendor tref
        vendor="$(bash "$ad" --vendor 2>/dev/null || basename "$ad" .sh)"
        tref="$(basename "$ad" .sh)"
        jq -cn --arg tr "$tref" --arg v "$vendor" \
          '{tier:"tier2", target_ref:$tr, platform:$v, reason:"vendor adapter covers this county"}' 2>/dev/null \
          || printf '{"tier":"tier2","target_ref":"%s","platform":"%s","reason":"vendor adapter covers this county"}\n' "$tref" "$vendor"
        return 0
      fi
    done
  fi

  # Tier 3: an operator-built config (06-build-tier3-config.sh) in the master
  # files whose county_fips matches AND is servable.
  if [ "$have_jq" -eq 1 ]; then
    local t3dir; t3dir="$(_tier3_dir 2>/dev/null || true)"
    if [ -n "$t3dir" ] && [ -d "$t3dir" ]; then
      local g
      for g in "$t3dir"/*.json; do
        [ -f "$g" ] || continue
        local gfips
        gfips="$(jq -r '.county_fips // empty' "$g" 2>/dev/null || true)"
        [ -n "$gfips" ] && [ "$gfips" = "$fips" ] || continue
        if _config_servable "$g"; then
          local gslug
          gslug="$(jq -r '.slug // empty' "$g")"
          jq -cn --arg slug "$gslug" '{tier:"tier3", target_ref:$slug, platform:"custom", reason:"operator tier3 config (validated)"}'
          return 0
        fi
        # matched but not validated/filled → record it (SK1-24) for an explicit gap.
        [ -z "$matched_unvalidated" ] && matched_unvalidated="$(jq -r '.slug // empty' "$g" 2>/dev/null || true)"
      done
    fi
  fi

  # Else Tier 4 — honest gap. NEVER FABRICATE. Make the tier state EXPLICIT
  # (SK1-24): if a curated/operator config MATCHED this county but was not yet
  # validated/filled, say so — the operator can then run 05-validate-target.sh —
  # rather than implying no data source exists at all.
  if [ -n "$matched_unvalidated" ] && [ "$have_jq" -eq 1 ]; then
    jq -cn --arg slug "$matched_unvalidated" \
      '{tier:"tier4_honest_gap", reason:"config_present_unvalidated", target_ref:$slug, hint:"a curated config matches this county but is not validated/filled — run 05-validate-target.sh, fill portal_url/tos_url/selectors, set validated:true"}' \
      2>/dev/null && return 0
  fi
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
  # global "User-agent: *" Disallow (wildcard-safe matcher; fail-closed on any
  # unevaluable wildcard rule) that covers our path.
  [ -z "$robots" ] && return 0
  if robots_disallowed "$robots" "$path"; then return 1; fi
  return 0
}

# _config_for_target <tier> <slug> — echo the config-file path backing a routed
# target (Tier-1 curated config or operator Tier-3 config), else nothing.
_config_for_target() {
  local tier="${1:-}" slug="${2:-}" dir="" g
  case "$tier" in
    tier1) dir="$TIER1_DIR" ;;
    tier3) dir="$(_tier3_dir 2>/dev/null || true)" ;;
    *) return 1 ;;
  esac
  [ -n "$dir" ] && [ -d "$dir" ] || return 1
  command -v jq >/dev/null 2>&1 || return 1
  for g in "$dir"/*.json; do
    [ -f "$g" ] || continue
    [ "$(jq -r '.slug // empty' "$g" 2>/dev/null)" = "$slug" ] && { printf '%s' "$g"; return 0; }
  done
  return 1
}

# ---------- the full routed query ----------
query() {
  local q="${1:-}" rtype="${2:-ownership}"; shift 2 2>/dev/null || true
  local force="false"
  for a in "$@"; do [ "$a" = "--force-refresh" ] && force="true"; done
  local qref; qref="q_$(date +%s)_$RANDOM"

  # 1) resolve county
  local r fips state county st_abbr
  r="$(resolve "$q")"
  if [ "$(printf '%s' "$r" | jq -r '.resolved' 2>/dev/null)" != "true" ]; then
    _emit honest_gap "$(printf '{"query_ref":"%s","target_ref":"unknown","reason":"county_unresolved"}' "$qref")"
    echo "$r" | jq -c '. + {tier:"tier4_honest_gap"}' 2>/dev/null || echo '{"tier":"tier4_honest_gap","reason":"county_unresolved"}'
    return 0
  fi
  fips="$(printf '%s' "$r" | jq -r '.county_fips')"
  state="$(printf '%s' "$r" | jq -r '.state')"
  county="$(printf '%s' "$r" | jq -r '.county_name // empty')"
  st_abbr="$(printf '%s' "$r" | jq -r '.state_abbr // empty')"

  # 2) tier selection (adapters + tier3 consulted before an honest gap)
  local t tname target
  t="$(tier "$fips" "$county" "$st_abbr")"
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

  # 3) cache check (fresh hit = free + instant). Cache entries are only ever
  #    written by cache_put (attribution-gated), so a hit is already attributed.
  local cdir key cfile
  cdir="$(_cache_dir)" || {
    _emit honest_gap "$(jq -cn --arg q "$qref" --arg tr "$target" '{query_ref:$q, target_ref:$tr, reason:"master_files_unresolved"}')"
    echo '{"blocked":true,"reason":"master_files_unresolved","tier":"'"$tname"'"}'
    return 0
  }
  mkdir -p "$cdir" 2>/dev/null || true
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

  # 4) COMPLIANCE GATE (binding, runs in query() itself before any live fetch).
  #    For a config-backed target (Tier-1/Tier-3) we know the portal + tos_url:
  #      (a) robots.txt must ALLOW the search path, else compliance_block/robots_disallow
  #      (b) a persisted per-target ToS acknowledgement must exist, else
  #          compliance_block/tos_unacknowledged
  #    A Tier-2 vendor adapter is per-county operator-driven (no shipped base
  #    URL); its --plan output carries the same robots+ToS obligation.
  local cfg base spath tos
  cfg="$(_config_for_target "$tname" "$target" 2>/dev/null || true)"
  if [ -n "$cfg" ]; then
    base="$(jq -r '.portal_url // .base_url // empty' "$cfg" 2>/dev/null || true)"
    spath="$(jq -r '.search_path // "/"' "$cfg" 2>/dev/null || echo /)"
    tos="$(jq -r '.tos_url // empty' "$cfg" 2>/dev/null || true)"
    if ! robots_ok "$base" "$spath"; then
      _emit compliance_block "$(jq -cn --arg q "$qref" --arg tr "$target" '{query_ref:$q, target_ref:$tr, reason:"robots_disallow"}')"
      echo "$t" | jq -c --arg q "$qref" '. + {query_ref:$q, blocked:true, reason:"robots_disallow", available:false}'
      return 0
    fi
    if ! { tos_url_valid "$tos" && tos_ack_present "$target"; }; then
      _emit compliance_block "$(jq -cn --arg q "$qref" --arg tr "$target" '{query_ref:$q, target_ref:$tr, reason:"tos_unacknowledged"}')"
      echo "$t" | jq -c --arg q "$qref" '. + {query_ref:$q, blocked:true, reason:"tos_unacknowledged", available:false}'
      return 0
    fi
  fi

  # 5) cost cap (per-day) — refuse over the cap (never silent overrun)
  if ! bash "$COSTCAP" under_daily_cap; then
    _emit cost_block "$(jq -cn --arg q "$qref" --arg tr "$target" '{query_ref:$q, target_ref:$tr, reason:"daily_cap"}')"
    echo '{"blocked":true,"reason":"daily_cap","tier":"'"$tname"'"}'
    return 0
  fi

  # 6) cost estimate + per-target rate limit + counter increment — WIRED at the
  #    real fetch call site (not merely defined). estimate() logs cost_estimate;
  #    rate_wait() honors the per-target min interval; record_query() increments
  #    today's counter so the daily cap can actually bite.
  local est waited
  est="$(bash "$COSTCAP" estimate 1 2>/dev/null || true)"
  [ -n "$est" ] && _emit cost_estimate "$(printf '%s' "$est" | jq -c --arg q "$qref" --arg tr "$target" '. + {query_ref:$q, target_ref:$tr, confirmed:true}' 2>/dev/null || printf '{"query_ref":"%s","target_ref":"%s","confirmed":true}' "$qref" "$target")"
  waited="$(bash "$COSTCAP" rate_wait "$target" 2>/dev/null || echo 0)"
  if [ "${waited:-0}" -gt 0 ] 2>/dev/null; then
    _emit rate_limit_wait "$(jq -cn --arg q "$qref" --arg tr "$target" --argjson w "$waited" '{query_ref:$q, target_ref:$tr, waited_seconds:$w}')"
    sleep "$waited" 2>/dev/null || true
  fi
  bash "$COSTCAP" record_query || {
    _emit cost_block "$(jq -cn --arg q "$qref" --arg tr "$target" '{query_ref:$q, target_ref:$tr, reason:"cap_state_unresolved"}')"
    echo '{"blocked":true,"reason":"cap_state_unresolved","tier":"'"$tname"'"}'
    return 0
  }

  # 7) live fetch + selector extraction is delegated to the tier-specific adapter
  #    (Tier-1 config / Tier-2 adapter / Tier-3 config). An optional operator hook
  #    (SKILL40_RETRIEVE_CMD) may perform the LIVE retrieval and print ONE record
  #    JSON; if it does, cache_put stores it — but ONLY if the record carries
  #    source + retrieved_at (attribution). The router NEVER synthesizes a record
  #    itself; a hookless call is an honest available:false handoff, not a
  #    fabricated record.
  # SK1-25: the operator retrieval hook is FAIL-CLOSED and sandboxed.
  #   - It runs ONLY when explicitly enabled (SKILL40_ALLOW_RETRIEVE_CMD=1), so a
  #     stray/injected SKILL40_RETRIEVE_CMD can never trigger code execution.
  #   - SKILL40_RETRIEVE_CMD must resolve to an executable (command -v) and is
  #     invoked DIRECTLY, never via `bash -c "<string>"` — an inline shell
  #     payload (metacharacters, pipes, subshells) is no longer evaluated.
  #   - Its output is still attribution-gated by cache_put (now http(s)+ISO gated).
  if [ -n "${SKILL40_RETRIEVE_CMD:-}" ]; then
    local rec put
    if [ "${SKILL40_ALLOW_RETRIEVE_CMD:-0}" != "1" ]; then
      _emit compliance_block "$(jq -cn --arg q "$qref" --arg tr "$target" '{query_ref:$q, target_ref:$tr, reason:"retrieve_cmd_not_enabled"}')"
    elif ! command -v "$SKILL40_RETRIEVE_CMD" >/dev/null 2>&1; then
      _emit compliance_block "$(jq -cn --arg q "$qref" --arg tr "$target" '{query_ref:$q, target_ref:$tr, reason:"retrieve_cmd_not_executable"}')"
    else
      rec="$(SKILL40_QUERY="$q" SKILL40_TARGET="$target" SKILL40_RTYPE="$rtype" "$SKILL40_RETRIEVE_CMD" 2>/dev/null || true)"
      if [ -n "$rec" ]; then
        if put="$(cache_put "$target" "$fips" "$rtype" "$rec" 2>/dev/null)"; then
          _emit query "$(printf '%s' "$rec" | jq -c --arg q "$qref" --arg tr "$target" --arg rt "$rtype" '{query_ref:$q, target_ref:$tr, record_type:$rt, result_count:1, source:(.source), retrieved_at:(.retrieved_at)}' 2>/dev/null || printf '{"query_ref":"%s","target_ref":"%s","record_type":"%s","result_count":1}' "$qref" "$target" "$rtype")"
          jq -c --arg q "$qref" '. + {query_ref:$q, cache_hit:false, available:true}' "$put" 2>/dev/null || cat "$put"
          return 0
        fi
        # Hook returned an UNATTRIBUTED record → refuse it (never cache/fabricate).
        _emit compliance_block "$(jq -cn --arg q "$qref" --arg tr "$target" '{query_ref:$q, target_ref:$tr, reason:"unattributed"}')"
        echo "$t" | jq -c --arg q "$qref" '. + {query_ref:$q, blocked:true, reason:"unattributed", available:false}'
        return 0
      fi
    fi
  fi

  echo "$t" | jq -c --arg q "$qref" --arg rt "$rtype" \
    '. + {query_ref:$q, record_type:$rt, available:false, note:"live retrieval is performed by the tier adapter after robots+ToS+attribution pass; the router NEVER synthesizes a record itself"}'
  return 0
}

if [ "${BASH_SOURCE[0]:-}" = "${0:-}" ]; then
  cmd="${1:-}"; shift || true
  case "$cmd" in
    resolve)     resolve "$@" ;;
    tier)        tier "$@" ;;
    robots_ok)   robots_ok "$@"; exit $? ;;
    # robots_match <path> <rule> — exit 0 if the Disallow rule blocks the path
    # (offline; the wildcard-safe matcher qc-compliance.sh exercises).
    robots_match) _rule_blocks_path "${1:-/}" "${2:-}"; exit $? ;;
    tos_valid)   tos_url_valid "${1:-}"; exit $? ;;
    config_servable) _config_servable "${1:-}"; exit $? ;;
    ack_tos)     ack_tos "$@" ;;
    tos_ack)     tos_ack_present "${1:-}"; exit $? ;;
    cache_put)   cache_put "$@" ;;
    query)       query "$@" ;;
    -h|--help)   sed -n '1,30p' "$0" ;;
    *) echo "usage: $0 {resolve <q>|tier <fips> [county] [ST]|robots_ok <base> <path>|robots_match <path> <rule>|tos_valid <url>|ack_tos <target> <url>|tos_ack <target>|cache_put <target> <fips> <type> <json>|query <q> <type> [--force-refresh]}" >&2; exit 2 ;;
  esac
fi
