# Explicit native condition order replacement

Use `forms.conditions` with `form-condition-recreate-order.json` when the owner
explicitly requests replacing the order of existing Show/Hide rules. Provide the
complete current `expected_rules`, the same complete rules in desired order,
and `recreate_order`: each original zero-based ordinal exactly once.

This mode retains the unchanged prefix, deletes the changed suffix through the
captured native confirmations, and authors the unchanged rules in requested order.
It recreates those cards; it does not preserve their internal card identifiers or
use native drag reordering. Show/Hide and Redirect cards are supported. Custom
message and message-mode disqualification cards are also supported when their
saved native markup is exactly one unformatted paragraph. Before deleting any
card, the script checks every message in the changed suffix; formatted or
multiline messages stop without deletion. Recreated messages must retain their
original markup hashes. Formatted messages in an unchanged prefix are preserved.
Omit this mode for ordinary in-place edits. Combining reordering with rule
additions, removals or edits refuses before any browser access.

The drawer and outer form save occur only after the complete desired inventory
matches. One independent reopen must confirm the full saved order. A partial
staged failure or uncertain save leaves the parent journal requiring reconciliation;
the job never automatically repeats deletion or creation. Matching desired order
is reused without another write. Respondent branch behavior remains separate proof.
