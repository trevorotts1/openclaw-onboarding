# Ordered native AND/OR connectors

Use `forms.conditions` with `match: "mixed"` and an explicit `connectors` array
to configure different captured AND/OR tabs between rows of one native rule.
`connectors[0]` joins clause 1 to clause 2; `connectors[1]` joins clause 2 to
clause 3. The final row keeps its native Then tab. The example authors the
literal row sequence If Email Contains @, And First Name Is Filled, Or Website
Is Empty, with Hide Field Last Name as the outcome.

Supply exactly one lowercase `and` or `or` per edge and include both values.
Use the existing `all` or `any` mode for homogeneous groups; those modes reject
an ignored `connectors` array and retain their existing configuration hashes.
Nested groups and authored parentheses have no captured contract and remain
unsupported. This schema binds the visible ordered native expression; it does
not infer the platform's Boolean precedence or claim respondent acceptance.

The same explicit predicate works in `condition.rules` Show/Hide stacks and in
captured redirect, custom-message and disqualification outcome stacks. Existing
Show/Hide stacks may include an exact full `expected_rules` inventory to edit
their connectors without appending rows. Existing card counts and all sibling
rules remain protected. Each authored row/tab is checked in its modal, the full
saved card must match, and independent reopening must retain every connector.
Unexpected homogeneous or reordered readback refuses success.

Fresh and replayed receipts bind the ordered connectors through the existing
configuration hash. A receipt for And/Or cannot satisfy an Or/And request.
The recipe leaves behavior and submission verification pending and does not
submit a form or execute a lead-disqualification journey.
