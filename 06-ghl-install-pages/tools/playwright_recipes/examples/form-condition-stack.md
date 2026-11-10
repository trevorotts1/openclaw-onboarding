# Ordered native conditional effects on multiple fields

Use `forms.conditions` with `condition.rules` to author the complete ordered
native Show/Hide rule list. The native target picker selects one field, so a
single predicate affecting two targets is represented as two explicit rules.
The example hides Phone and Email when First Name is filled.

Supply 1 to 50 rules, or an explicit empty desired list with the complete expected previous inventory when clearing. Every rule has `match`, `clauses`, `effect`, and one
`target`. A rule accepts 1 to 20 captured source/operator clauses; compound
rules use AND (`all`), OR (`any`), or explicit mixed ordered connectors (`mixed`). Binary operators require an
explicit text value. Nested groups, unknown native effects, duplicate predicates
for one target and conflicting Show/Hide predicates for one target are refused.

Existing cards must be the exact prefix of the entire requested rule list.
Their order, source/operator/value tokens and target/effect must match before
any missing rule is added. The handler appends only the missing suffix through
the observed Show/Hide Fields tile. Without an expected previous inventory it does not edit, delete or reorder existing
cards to force a match. Supply the full intended stack rather than an arbitrary
append request.

For editing existing Show/Hide cards, also supply `condition.expected_rules`
with the entire inventoried previous rule list. It may have fewer, the same number, or more cards than desired `rules`. Every actual card must match the complete previous
stack before the first edit. Only changed cards are opened through their scoped
Edit control. The existing native modal's full predicate, connectors, effect and
target are independently checked before any authored edit. The complete changed
predicate/effect/target is then checked, and every untouched card must remain
unchanged after each modal Save. The hash binds both previous and desired lists.

Changing existing AND/OR connectors does not append a row. Clauses can retain
their count, grow through native append controls, or shrink by removing tail
rows. Each removal is bound to the exact tail row's owner and captured trash
SVG, never the first If row. There is no confirmation dialog in this captured
flow. Every remaining prefix clause, connector, effect and target is checked
after each removal. Card growth appends the exact desired suffix after protected edits. Card contraction
removes exact tail cards through the measured second Delete confirmation; clearing
requires positive loaded-empty proof. Drag reordering remains unsupported. A conflicting previous Show/Hide pair may be
explicitly inventoried and corrected; conflicting desired predicates for one
target remain refused. See `form-condition-stack-edit.json`.

Each new card is checked immediately against the complete expected prefix.
The drawer Save-close and outer form Save follow; Save traffic must settle
before navigating away. Independent Forms-list reopen must return the exact
complete stack. Lost or unsettled Save refuses success and requires journal
reconciliation rather than blindly repeating the append. An already complete
stack is independently reopened without adding cards or repeating outer Save.

The result binds the ordered configuration hash and rule count. Native
submission behavior and effect precedence remain unverified; source and
configuration persistence are separate from respondent acceptance tests.
