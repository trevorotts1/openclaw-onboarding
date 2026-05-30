#!/usr/bin/env bash
# govos-landmark.sh — Skill 40 Tier 2 platform ADAPTER (EXAMPLE).
#
# GovOS / Landmark Web (formerly Kofile / Pioneer "Landmark Web Official Records
# Search") powers official-records search for many county clerk/recorder offices.
# This is the SECOND example adapter, demonstrating the same adapter CONTRACT as
# tyler-technologies.sh so an operator can pattern a third vendor adapter.
#
# CONTRACT (identical across adapters):
#   --covers "<county>" "<state>"   exit 0 if handled, else non-zero
#   --plan   "<county>" "<state>" "<record_type>" "<query>"   print the plan
#   --vendor   print the vendor name
#
# Coverage is operator-confirmed + EMPTY by default (universal skill asserts
# nothing it hasn't confirmed). Add pairs via SKILL40_GOVOS_COVERAGE or by
# editing GOVOS_COVERAGE below. Unlisted county => non-zero => router falls
# through to Tier 3 / Tier 4 honest gap. NEVER fabricates a record.
#
# bash -n clean. set -uo pipefail.

set -uo pipefail

VENDOR="GovOS / Landmark Web (Official Records Search)"

GOVOS_COVERAGE="${SKILL40_GOVOS_COVERAGE:-}"

covers() {
  local county="$1" state="$2"
  [ -n "$GOVOS_COVERAGE" ] || return 1
  local want; want="$(echo "${county}:${state}" | tr '[:upper:]' '[:lower:]')"
  local IFS=','
  for pair in $GOVOS_COVERAGE; do
    local norm; norm="$(echo "$pair" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g' | tr '[:upper:]' '[:lower:]')"
    [ "$norm" = "$want" ] && return 0
  done
  return 1
}

case "${1:-}" in
  --vendor) echo "$VENDOR"; exit 0 ;;
  --covers) covers "${2:-}" "${3:-}" && exit 0 || exit 1 ;;
  --plan)
    county="${2:-}"; state="${3:-}"; rtype="${4:-recorder}"; query="${5:-}"
    if ! covers "$county" "$state"; then
      echo "GovOS adapter does NOT cover ${county}, ${state}. Fall through to Tier 3/4." >&2
      exit 1
    fi
    cat <<PLAN
[Tier 2 adapter: $VENDOR]
County: $county, $state   record-type: $rtype
Landmark Web "Official Records Search" is reached from the county clerk/recorder
portal. Operator supplies the county's Landmark base URL (per-county). Then:
  - SEARCH: the "Official Records" search form (name / instrument / date / book-page)
  - FETCH:  LIVE via browser (JS-driven) — respect robots.txt + ToS
  - ATTRIBUTE: record source (county Landmark portal) + retrieval timestamp
Query: $query
HONESTY: unreachable / blocked / not-online => Tier 4 honest gap, never a
fabricated record.
PLAN
    exit 0 ;;
  -h|--help) sed -n '1,33p' "$0"; exit 0 ;;
  *)
    echo "usage: $(basename "$0") --vendor | --covers <county> <state> | --plan <county> <state> <record_type> <query>" >&2
    exit 2 ;;
esac
