#!/usr/bin/env bash
# route-lead.sh — Skill 39 THE lead-routing entry point (SK1-30 / T0-52).
#
# WHY THIS EXISTS
#   Fair housing was "machine-enforced" by a denylist at the point an event is
#   WRITTEN (lib-re-events.sh :: re_event) — which is AFTER the routing decision
#   has already been made. A route computed on a protected attribute was
#   prevented only from being LOGGED with that attribute in the payload; the
#   routing itself was never examined. qc-fair-housing.sh then certified
#   "fair-housing is machine-enforced" on the strength of a `grep -qi "never
#   route on"` over a markdown file. On a surface with real legal exposure, the
#   thing being enforced was the shape of a log line.
#
#   This script makes the decision itself the enforced object. It is the ONE
#   entry point for routing a qualified lead to an agent. It runs the
#   protected-attribute detector over BOTH payloads — the lead AND the roster —
#   BEFORE any filtering or scoring happens, refuses non-zero on a forbidden
#   key, and only then computes the route.
#
# CONTRACT
#   route-lead.sh --lead <lead.json> --roster <roster.json> [--json]
#
#   exit 0  a route (or the fallback queue) was computed and logged
#   exit 2  bad invocation / unreadable or non-object payload
#   exit 3  REFUSED — a protected-class field is present in the lead or roster.
#           Nothing was filtered, scored or routed.
#   exit 4  the roster is missing, empty, or still carries template placeholders
#           (the protocol says HOLD the lead, never guess an agent)
#   exit 5  the routing decision could not be appended to the F52 event log
#
#   SKILL39_ROUTE_TRACE=<path>  optional audit trace. When set, every scoring
#           step appends one line to that file. It exists so the fair-housing
#           gate can prove the refusal happened BEFORE any scoring — an empty
#           trace on a refused payload is that proof. Off by default.
#
# Fair-housing rule (references/fair-housing-guardrails.md,
# protocols/lead-routing-protocol.md): route on specialty, availability and area
# ONLY. Never on, or differentiated by, a protected class.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
P="[skill 39][route]"

# shellcheck source=/dev/null
. "$SCRIPT_DIR/lib-re-events.sh"

command -v jq >/dev/null 2>&1 || { echo "$P jq required" >&2; exit 2; }

LEAD_FILE=""; ROSTER_FILE=""; AS_JSON=0
while [ $# -gt 0 ]; do
  case "$1" in
    --lead)   LEAD_FILE="${2:-}"; shift 2 ;;
    --roster) ROSTER_FILE="${2:-}"; shift 2 ;;
    --json)   AS_JSON=1; shift ;;
    -h|--help) sed -n '1,45p' "$0"; exit 0 ;;
    *) echo "$P unknown argument: $1" >&2; exit 2 ;;
  esac
done

[ -n "$LEAD_FILE" ] && [ -f "$LEAD_FILE" ]     || { echo "$P --lead <lead.json> is required and must exist" >&2; exit 2; }
[ -n "$ROSTER_FILE" ] && [ -f "$ROSTER_FILE" ] || { echo "$P --roster <roster.json> is required and must exist" >&2; exit 2; }

LEAD="$(cat "$LEAD_FILE")"
ROSTER="$(cat "$ROSTER_FILE")"
printf '%s' "$LEAD"   | jq -e 'type=="object"' >/dev/null 2>&1 || { echo "$P lead payload is not a JSON object" >&2; exit 2; }
printf '%s' "$ROSTER" | jq -e 'type=="object"' >/dev/null 2>&1 || { echo "$P roster payload is not a JSON object" >&2; exit 2; }

_trace() { [ -n "${SKILL39_ROUTE_TRACE:-}" ] && printf '%s\n' "$*" >> "$SKILL39_ROUTE_TRACE"; return 0; }

# ─── STEP 1 (FIRST, ALWAYS): protected-attribute detection ───────────────────
# Nothing above this point filters, scores, sorts or selects. If this block is
# ever moved below the scoring block, the fair-housing gate's empty-trace
# assertion turns red — which is the point.
LEAD_HITS="$(fair_housing_offending_keys "$LEAD")"
ROSTER_HITS="$(fair_housing_offending_keys "$ROSTER")"
if [ -n "$LEAD_HITS" ] || [ -n "$ROSTER_HITS" ]; then
  ALL_HITS="$(printf '%s\n%s\n' "$LEAD_HITS" "$ROSTER_HITS" | grep -v '^$' | sort -u | paste -sd, - 2>/dev/null | sed 's/,$//')"
  echo "$P REFUSED (fair-housing): protected-class field(s) present: $ALL_HITS" >&2
  echo "$P No lead was filtered, scored or routed. Remove the protected attribute" >&2
  echo "$P from the intake and the roster — routing is on specialty, availability" >&2
  echo "$P and area ONLY (references/fair-housing-guardrails.md)." >&2
  # The refusal itself is auditable. The payload carries the offending KEY NAMES
  # only (never their values), so it passes the same denylist at the chokepoint.
  MASTER_FILES_DIR="${MASTER_FILES_DIR:-}" re_event lead_route_refused \
    "$(jq -cn --arg keys "$ALL_HITS" '{lead_ref:"withheld", reason:"fair_housing_protected_attribute", offending_key_names:($keys|split(","))}')" \
    >/dev/null 2>&1 || echo "$P WARN: the refusal event could not be appended (the refusal itself still stands)" >&2
  exit 3
fi

# ─── STEP 2: the roster must be real ─────────────────────────────────────────
ROSTER_N="$(printf '%s' "$ROSTER" | jq -r '[.agents[]? | select(.active == true)] | length')"
PLACEHOLDERS="$(printf '%s' "$ROSTER" | jq -r '[.agents[]? | .agent_ref // "" | select(test("^<.*>$"))] | length')"
if [ "${ROSTER_N:-0}" -eq 0 ] || [ "${PLACEHOLDERS:-0}" -gt 0 ]; then
  echo "$P HOLD: the agent roster is empty or still carries template placeholders" >&2
  echo "$P (active=$ROSTER_N, placeholder agent_refs=$PLACEHOLDERS). Fill" >&2
  echo "$P templates/agent-specialty-roster.template.json before routing. The lead is" >&2
  echo "$P held, never routed to a guessed agent." >&2
  exit 4
fi

# ─── STEP 3: filter → score → tie-break (specialty, availability, area ONLY) ──
_trace "scoring $ROSTER_N active agent(s)"
STATE_DIR="${HOME:-/tmp}/.openclaw"
LRT_FILE="$STATE_DIR/.skill-39-last-routed.json"
mkdir -p "$STATE_DIR" 2>/dev/null || true
LRT="$(cat "$LRT_FILE" 2>/dev/null || true)"
printf '%s' "$LRT" | jq -e 'type=="object"' >/dev/null 2>&1 || LRT='{}'

DECISION="$(printf '%s' "$ROSTER" | jq -c \
  --argjson lead "$LEAD" --argjson lrt "$LRT" '
  . as $R
  | ($lead.role // "" | ascii_downcase) as $role
  | ([$role] + (($lead.signals // []) | map(ascii_downcase)))
      | map(if . == "seller" then "listing"
            elif . == "investor" then "investment"
            elif . == "new_buyer" then "first_time"
            else . end) as $want
  | (($lead.area // "") | ascii_downcase) as $area
  | [ $R.agents[]? | select(.active == true)
      | . as $a
      | ([ $a.specialties[]? | ascii_downcase | select(. as $s | $want | index($s)) ] | length) as $spec
      | (if ($area != "") and (([$a.areas[]? | ascii_downcase] | index($area)) != null) then 1 else 0 end) as $areahit
      | { agent_ref: $a.agent_ref,
          specialty_matches: $spec,
          area_match: ($areahit == 1),
          score: ($spec + $areahit),
          capacity_weight: ($a.capacity_weight // 1.0),
          last_routed: ($lrt[$a.agent_ref] // 0) }
    ]
  | sort_by([(-.score), (-.capacity_weight), .last_routed, .agent_ref]) as $ranked
  | ($ranked | map(select(.score > 0))) as $matched
  | if ($matched | length) == 0 then
      { routed: false, agent_ref: null,
        fallback_queue: ($R.fallback_queue // "broker-general-queue"),
        reason: "no_specialty_match_routed_to_fallback_queue",
        tie_broken_by: "n/a", considered: ($ranked | length) }
    else
      ($matched[0]) as $w
      | { routed: true, agent_ref: $w.agent_ref,
          agent_specialty: $w.specialty_matches, area_match: $w.area_match,
          score: $w.score,
          reason: "specialty_and_availability_match",
          tie_broken_by: (if ($matched | length) > 1
                            and ($matched[1].score == $w.score)
                          then (if $matched[1].capacity_weight != $w.capacity_weight
                                then "capacity_weight" else "least_recently_routed" end)
                          else "no_tie" end),
          considered: ($ranked | length) }
    end')"

_trace "decision: $(printf '%s' "$DECISION" | jq -r '.reason')"

# ─── STEP 4: record the decision, then report it ─────────────────────────────
CHOSEN="$(printf '%s' "$DECISION" | jq -r '.agent_ref // empty')"
if ! MASTER_FILES_DIR="${MASTER_FILES_DIR:-}" re_event lead_route \
      "$(printf '%s' "$DECISION" | jq -c '{lead_ref:"opaque", agent_ref:(.agent_ref // null), agent_specialty:(.agent_specialty // 0), reason:.reason, tie_broken_by:.tie_broken_by, considered:.considered}')"; then
  echo "$P FATAL: the lead_route decision could not be appended to the F52 event log." >&2
  echo "$P        Refusing to report a route that was never recorded." >&2
  exit 5
fi

if [ -n "$CHOSEN" ]; then
  printf '%s' "$LRT" | jq -c --arg a "$CHOSEN" --argjson ts "$(date +%s)" '. + {($a): $ts}' > "$LRT_FILE.tmp.$$" 2>/dev/null \
    && mv -f "$LRT_FILE.tmp.$$" "$LRT_FILE" 2>/dev/null || rm -f "$LRT_FILE.tmp.$$" 2>/dev/null || true
fi

if [ "$AS_JSON" -eq 1 ]; then
  printf '%s\n' "$DECISION"
else
  printf '%s\n' "$DECISION" | jq -r --arg p "$P" '
    if .routed then "\($p) routed to \(.agent_ref) (specialty matches: \(.agent_specialty), tie broken by: \(.tie_broken_by))"
    else "\($p) no specialty match — held for the fallback queue \(.fallback_queue)" end'
fi
exit 0
