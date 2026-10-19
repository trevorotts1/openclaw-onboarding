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

## Fallback policy

`fallback_policy: none`. When the selected route is unavailable,
unresponsive, or returns an unusable result, the council reports the
blocker precisely (which route, what failed) and stops or waits. It
never substitutes a different model and presents the output as if the
selected route produced it.

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

Every provider request counts against the session's 50-request ceiling
(see protocol.md), including retries and repairs. Usage records keep
the route, the request count, and the outcome per round, so a verdict
can always be audited for what it actually cost and which route
actually produced it.

## What the installer must preserve

Installing or updating this skill never changes global model defaults,
never re-pins a route, and never rewrites another skill's model
configuration. The release receipt records that the client's route
selection and defaults were preserved (see INSTALL.md, Step 10).
