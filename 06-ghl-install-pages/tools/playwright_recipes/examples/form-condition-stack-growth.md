# Grow an explicitly inventoried Show/Hide stack

Supply the complete `condition.expected_rules` inventory and a longer desired
`condition.rules` array to edit existing Show/Hide cards and append new cards in
one job. Existing positions are edited only after their full current predicate,
connectors, effect and target match the expected inventory. Every extra desired
rule is appended once through the already captured Show/Hide tile. All earlier
cards must remain unchanged after each append.

An explicit empty `expected_rules` array requires the actual positive native
empty-state marker; absence is not inferred. The hash binds both arrays,
including the empty expected inventory. The handler saves the complete stack
once and independently reopens it before certifying persistence. A lost Save
or unexpected card/connector drift requires reconciliation rather than another
automatic append.

This extends the existing same-count edit contract to growth. Shrinking the
card count and clearing all cards use the separately captured scoped Delete
confirmation flow documented in `form-condition-stack-contraction.md` and also
require the full expected inventory. This does not add native card reordering,
arbitrary outcome edits, submissions or respondent behavior verification.
