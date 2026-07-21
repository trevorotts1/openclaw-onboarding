# Lead Routing Protocol (by agent specialty)

Routes each qualified real-estate lead to the best-fit agent, using the
operator-filled roster at `templates/agent-specialty-roster.template.json`,
with fair-housing guardrails and round-robin fairness on ties.

## When this protocol activates

A lead has been qualified (buyer / seller / investor) and is ready to be handed
to a human agent (or a dedicated AI sub-agent).

## Inputs (from the roster)

Each agent entry carries:
- `agent_ref` — opaque handle (NOT PII in the event log)
- `specialties` — any of: `buyer`, `listing`, `luxury`, `investment`,
  `first_time`, `relocation`, `commercial`, plus `areas` (geographic)
- `active` — whether the agent is currently taking leads
- `capacity_weight` — relative load for round-robin fairness

## The routing entry point (the only supported path)

Every route goes through **`scripts/route-lead.sh`**:

```bash
scripts/route-lead.sh --lead <lead.json> --roster <roster.json> [--json]
```

It runs the protected-attribute detector over the lead **and** the roster
**before any filtering or scoring**, refuses non-zero (exit 3) on a forbidden
key, and only then computes the route. Do not route a lead any other way — a
route computed outside this entry point is a route no gate has examined.

Exit codes: `0` routed (or held for the fallback queue) · `2` bad invocation ·
`3` REFUSED, a protected-class field was present · `4` roster empty/unfilled,
the lead is held · `5` the decision could not be appended to the event log.

## Routing algorithm

1. **Filter to active agents.**
2. **Score by specialty match** against the qualified lead's role + signals
   (e.g. seller intent → `listing`; high price band → `luxury`; investor →
   `investment`; new buyer → `first_time`; relocation cues → `relocation`).
   Geographic `areas` add to the score when the property/area is known.
3. **Break ties by round-robin** weighted by `capacity_weight` and least-recently-
   routed (tracked locally, not in the PII-free event log).
4. **Never route on, or differentiate by, a protected class.** Specialty and
   availability only (see `references/fair-housing-guardrails.md`).
5. **Emit the event** — append a `lead_route` event with `agent_specialty`,
   `reason`, and `tie_broken_by`.

## Fallbacks

- No active agent matches the specialty → route to the broker/general queue and
  flag for manual assignment; never drop the lead silently.
- Roster missing or unfilled → halt routing, tell the operator to fill
  `agent-specialty-roster.template.json`, and hold the lead.

## Honesty floor

Never tell a lead they are matched to a "specialist" the roster does not show.
