# Council Model Routing Reference

## The selection rule

The client selects their model, or their configured default applies.
This skill never prescribes a specific named model, in its docs, its
configuration, or its runtime behavior. It may present recommendations
with reasons as guidance; a recommendation is never a hidden
prescription, a silent default, or a fallback that swaps models behind
the client's back.

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
