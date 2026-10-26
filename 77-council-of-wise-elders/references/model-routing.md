# Council Model Routing Reference

## The selection rule

The model is the client's choice, per run. The convening agent asks the
client which model to use, lists the options from
`blackceo-council routes`, and offers the default for the harness it is
running in. It never picks a model silently, and no route is hard-wired
for everyone. The client's explicit route and model always win. Only
when the client defers does the harness default below apply, and the
agent says which model that is. A recommendation with reasons is
allowed; it is never a hidden prescription or a fallback that swaps
models behind the client's back.

## Harness defaults

| Harness the council is convened from | Route | Model |
|---|---|---|
| claude-nine | claude-nine-configured | the launcher's own configured default (no model is passed) |
| Claude Code | claude-configured | Sonnet |
| DeepSeek direct | deepseek-configured | the latest DeepSeek Flash, resolved at run time |

The harness is detected from the environment of the command
(`CLAUDE_CONFIG_DIR` ending in `.claude-nine` means claude-nine;
`CLAUDECODE=1` otherwise means Claude Code). DeepSeek direct has no
reliable marker, so it is chosen with `--harness deepseek`. When no
route is given and the harness is unknown, the council refuses with a
typed error rather than guessing.

### The latest-DeepSeek-Flash rule

The DeepSeek Flash model id is resolved from the provider's live model
list (`GET {baseUrl}/models`) at each run, and the newest Flash in that
list is used. It is never pinned in this skill, in configuration, or in
code, and the single id written in a client's provider configuration is
not trusted for this purpose. If the list cannot be fetched or contains
no Flash model, the run refuses with a typed error. It never falls back
to the configured id or to an older Flash.

## Council sizes

Every mode seats the full nine-advisor council; the mode changes the
rounds and the concurrency only. Light (all 9 seats, exactly 2 rounds, at
most 3 provider calls in parallel in waves of 3), medium (all 9 seats, 1
to 4 rounds) and heavy (all 9 seats, 3 to 10 rounds). Convening with no
`--mode` runs medium: that default is deliberate, and the convene output
always prints the size it ran. "quick answer" means light; "full council"
means heavy.

## Provider order and parallel limits

Two limits decide how many seats run at once, and the lower one wins:

- **The provider's ceiling.** Only Ollama has one, fixed by the plan the
  client pays for: the $20 a month plan 3 at a time, the $100 a month
  plan 10. Every other provider (OpenRouter, Agnes 3.0 Flash, DeepSeek
  Direct and any other direct paid route) adds no ceiling of its own.
- **The mode's wave width.** Light runs waves of 3; medium and heavy run
  the whole nine.

A provider with no ceiling therefore does not make an unlimited sitting:
light runs 3 at a time on every route, and only on an uncapped route do
medium and heavy run the whole panel at once (an Ollama $20 plan still
holds them to 3; its $100 ceiling of 10 exceeds the nine seats, so it
changes nothing). The convene output prints the resulting
`parallel limit`. The rule is enforced in
`runtime/src/providers/parallel.ts` (the provider cap) and
`runtime/src/contracts/modes.ts` (the mode's wave width).

The council offers its providers in this fixed order:

1. **OpenRouter (first, and recommended).** No ceiling of its own and no
   plan question, so the sitting runs at the mode's wave width.
2. **The client's own Ollama.** Only when the client prefers it. If
   their plan is not already known, ask once: the $20 a month plan runs
   at most 3 advisors at a time; the $100 a month plan runs at most 10.
   When Ollama fails and the client named an OpenRouter fallback model,
   the failed seats re-run on OpenRouter (see Fallback policy).
3. **Agnes 3.0 Flash.** When the client selects it: no ceiling of its
   own, so the mode's wave width applies.

A seat that cannot be run because the plan is unknown is a typed refusal,
never a guess.

## Fallback policy

`fallback_policy: none` for the four older modes. When the selected route
is unavailable, unresponsive, or returns an unusable result, the council
reports the blocker precisely (which route, what failed) and stops or
waits. It never substitutes a different model and presents the output as
if the selected route produced it.

The one exception is the client's own Ollama in light/medium/heavy: when
Ollama fails and the client named an OpenRouter fallback model, the seats
that failed are re-run on that model. The convene output names the
fallback route and model it will use (`Fallback: <route> / <model>`); the
verdict itself does not record which route answered which seat. With no
fallback model given, the older failure path applies and the output says
`Fallback: none (<reason>)`.

## Route identity

Routes report identity at one of three levels:

1. The route's own declared identity, when the provider exposes it.
2. The configured route name, when only the configuration is known.
3. Unknown, stated as unknown.

When the underlying model identity is not independently exposed, the
report uses this exact sentence: "Selected route used; underlying
model identity not independently exposed." Inventing a model name to
fill the gap is a report defect.

## Usage accounting

Every provider request counts against the session's ceiling (see
protocol.md), including retries and repairs: 50 for light, 50 for medium,
100 for heavy, and 50 for the four older modes. Usage records keep the
route, the request count, and the outcome per round, so a verdict can
always be audited for the provider requests it used and for which route
actually produced it.

## What the installer must preserve

Installing or updating this skill never changes global model defaults,
never re-pins a route, and never rewrites another skill's model
configuration. The release receipt records that the client's route
selection and defaults were preserved (see INSTALL.md, Step 10).
