#!/usr/bin/env bash
# tyler-technologies.sh — Skill 40 Tier 2 platform ADAPTER (EXAMPLE).
#
# Tyler Technologies powers a large family of county recorder/clerk/land-records
# portals (e.g. "Tyler Eagle" / "EagleWeb" land-records search) used by many U.S.
# counties. A Tier 2 adapter abstracts "how to search a Tyler-platform portal"
# ONCE, so any county on that vendor can be covered without a per-county Tier 1
# entry.
#
# ADAPTER CONTRACT (every adapter in this folder implements it):
#   <adapter> --covers "<county>" "<state>"   -> exit 0 if this adapter handles
#                                                 that county; else non-zero.
#   <adapter> --plan   "<county>" "<state>" "<record_type>" "<query>"
#                                              -> print the search plan (base URL
#                                                 + method + param) for the agent
#                                                 to execute LIVE (curl/browser).
#   <adapter> --vendor                         -> print the vendor name.
#
# This adapter ships a small operator-editable coverage map (TYLER_COVERAGE):
# county|state pairs the operator has confirmed run on the Tyler platform. It is
# EMPTY by default on purpose — a UNIVERSAL skill must not assert a county runs a
# vendor it hasn't confirmed. The operator adds confirmed pairs (or sets
# SKILL40_TYLER_COVERAGE="county:ST,county:ST"). If a county is not in the map,
# --covers returns non-zero and the router falls through to Tier 3 / Tier 4
# (honest gap) — NEVER a fabricated record.
#
# bash -n clean. set -uo pipefail.

set -uo pipefail

VENDOR="Tyler Technologies (Eagle / EagleWeb land records)"

# Operator-confirmed coverage. Format: "county:ST" comma-separated. EMPTY default.
# Example to enable (operator edits, having CONFIRMED the county uses Tyler):
#   TYLER_COVERAGE="example county:ZZ"
TYLER_COVERAGE="${SKILL40_TYLER_COVERAGE:-}"

covers() {
  local county="$1" state="$2"
  [ -n "$TYLER_COVERAGE" ] || return 1
  local want; want="$(echo "${county}:${state}" | tr '[:upper:]' '[:lower:]')"
  local IFS=','
  for pair in $TYLER_COVERAGE; do
    local norm; norm="$(echo "$pair" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g' | tr '[:upper:]' '[:lower:]')"
    [ "$norm" = "$want" ] && return 0
  done
  return 1
}

case "${1:-}" in
  --vendor) echo "$VENDOR"; exit 0 ;;
  --covers)
    covers "${2:-}" "${3:-}" && exit 0 || exit 1 ;;
  --plan)
    county="${2:-}"; state="${3:-}"; rtype="${4:-recorder}"; query="${5:-}"
    if ! covers "$county" "$state"; then
      echo "Tyler adapter does NOT cover ${county}, ${state} (not in operator coverage map). Fall through to Tier 3/4." >&2
      exit 1
    fi
    cat <<PLAN
[Tier 2 adapter: $VENDOR]
County: $county, $state   record-type: $rtype
The Tyler Eagle land-records search is typically reached from the county's
clerk/recorder portal. Operator must supply the county's Tyler base URL (it is
per-county). With that base URL:
  - SEARCH: navigate the Eagle "Search Public Records" / land-records form
  - PARAM:  enter the property address / grantor-grantee / instrument
  - FETCH:  LIVE via browser (Eagle is JS-heavy) — respect robots.txt + ToS
  - ATTRIBUTE: record source (the county Tyler portal) + retrieval timestamp
Query: $query
HONESTY: if the portal is unreachable, blocked, or the record is not online,
report a Tier 4 honest gap. Do NOT fabricate a record.
PLAN
    exit 0 ;;
  -h|--help) sed -n '1,40p' "$0"; exit 0 ;;
  *)
    echo "usage: $(basename "$0") --vendor | --covers <county> <state> | --plan <county> <state> <record_type> <query>" >&2
    exit 2 ;;
esac
