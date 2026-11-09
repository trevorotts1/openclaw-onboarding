# Contract or clear an explicitly inventoried Show/Hide stack

Supply the complete `condition.expected_rules` and the shorter final
`condition.rules` list. The handler first proves the full native inventory,
then removes the last card one at a time until the desired count remains.
Each scoped `#delete-condition` opens the measured second dialog, headed
Delete Condition with the exact confirmation question. The handler verifies
the Cancel/Delete controls and rechecks every underlying card immediately
before clicking the scoped confirmation Delete button.

After each confirmation, exactly one card must disappear, the confirmation
must close, and every remaining predicate/connector/effect/target must equal
the full preceding prefix. Count alone cannot establish which card was
removed. Desired edits to the retained positions then use the existing
full-inventory editor. This does not infer or perform native drag reordering.

To clear all Show/Hide cards, supply an explicit empty `rules` array with the
complete expected old inventory. An empty array without `expected_rules` is
invalid. Clearing requires the observed positive empty-state text, supporting
message and image identity after the final deletion, before Save and after
independent reopen. Unknown native outcomes cannot be represented as expected
Show/Hide rules and therefore refuse before any deletion.

All deletions remain staged until one drawer Save-close and one outer form
Save. Independent Forms-list reopen must retain the complete desired list or
the positive loaded-empty state. A lost Save, changed confirmation, concurrent
inventory drift or removal of the wrong card refuses success; preserve the
journal and reconcile instead of blindly deleting again. Fresh and replayed
receipts bind both old and desired stacks, including a zero final rule count.

The native Delete/Cancel/loaded-empty lifecycle was captured on a private draft
fixture and discarded by reload. Native final-script Save/reopen acceptance
and respondent behavior remain separately pending. This recipe does not
submit forms, execute disqualification outcomes or send notifications.
