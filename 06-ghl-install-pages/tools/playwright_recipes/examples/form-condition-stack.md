# Ordered native conditional effects on multiple fields

Use `forms.conditions` with `condition.rules` to author the complete ordered
native Show/Hide rule list. The native target picker selects one field, so a
single predicate affecting two targets is represented as two explicit rules.
The example hides Phone and Email when First Name is filled.

Supply 1 to 50 rules. Every rule has `match`, `clauses`, `effect`, and one
`target`. A rule accepts 1 to 20 captured source/operator clauses; compound
rules use homogeneous AND (`all`) or OR (`any`). Binary operators require an
explicit text value. Nested groups, unknown native effects, duplicate predicates
for one target and conflicting Show/Hide predicates for one target are refused.

Existing cards must be the exact prefix of the entire requested rule list.
Their order, source/operator/value tokens and target/effect must match before
any missing rule is added. The handler appends only the missing suffix through
the observed Show/Hide Fields tile. It never deletes, edits or reorders existing
cards to force a match. Supply the full intended stack rather than an arbitrary
append request.

Each new card is checked immediately against the complete expected prefix.
The drawer Save-close and outer form Save follow; Save traffic must settle
before navigating away. Independent Forms-list reopen must return the exact
complete stack. Lost or unsettled Save refuses success and requires journal
reconciliation rather than blindly repeating the append. An already complete
stack is independently reopened without adding cards or repeating outer Save.

The result binds the ordered configuration hash and rule count. Native
submission behavior and effect precedence remain unverified; source and
configuration persistence are separate from respondent acceptance tests.
