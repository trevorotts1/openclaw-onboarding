Native written-answer authoring supports the measured Short Answer `TEXT`,
Long Answer `LARGE_TEXT`, and Number `NUMERICAL` tiles. It can author an ordered
mix on one exact existing page. Supply all existing page labels and every prior
question's complete properties. Existing CHECKBOX questions also require their
three exact option values; scoring/category/disabled/jump metadata is inventoried
and preserved read-only. Native active jumps or Spread to columns require a
separate captured destination inventory and stop before insertion.

All new labels and Query Keys must be unique and disjoint from existing values.
The captured initial keys are `single_line` for TEXT, `multi_line` for LARGE_TEXT,
and `text` for NUMERICAL. Existing default keys may remain: the exact one-widget
delta and new ordered index bind the selected new widget, then every old property
must remain unchanged when the authored final key is read back. The Number key
is the observed native `text`, not an invented
`number` token. Its canvas component also exposes a typeless `input.form-control`
with no ID, name or placeholder attribute; it is not an HTML `type=number`.
Number placeholder edits are verified through fresh native property readback,
because the captured canvas component does not mirror that property attribute.

Long Answer uses the captured empty `textarea.form-placeholder.form-control`
with accessible name `Type your message here`, empty placeholder and no ID,
name or type. Generated labels have six random characters for Short/Long Answer
and five for Number. The common writer uses the actual Question, Placeholder,
Short Label and Query Key property inputs and Required/Hidden checkboxes. It
skips unchanged text values to avoid unnecessary native property rerenders.

The shared pointer rail uses fresh measured handle/canvas/final-question bounds
and the successfully captured point seven pixels inside the last wrapper's
lower edge. It performs one pointer drag, including three repeated final point
events, and stops on changed page count, wrong appended index/type/defaults,
old-question drift or any lost save. A native insertion can land before a prior
question; that outcome is refused before Save. A blank tail is not required.

The parent runner must journal intent before the drag, bind the complete exact
input hash on first execution and replay, and keep this as a separately
journaled assessment action. Completion requires independent quiz-list reopen
and the complete saved desired inventory. The unsaved native captures were
discarded; source and fixture checks do not prove live saved behavior, numerical
validation, routing, scoring effects or submitted answers.

Native title visibility can precede saved question DOM hydration. Before the
first inventory, the writer waits for the correct nonempty title, exact page
headings and positive expected baseline widgets on Edit. Missing loading DOM
waits within the normal bounded readiness budget; a wrong nonempty owner, URL,
type, label or positive count is refused. A declared empty page still needs
its captured visible drop placeholder, never zero nodes alone. After reopening,
readiness uses the complete desired inventory including the newly added fields.

Immediately after the single drag, a complete read-only inventory must prove
the exact old prefix unchanged, every other page unchanged and exactly one new
last widget of the requested type. This happens before any authored property
write. A misplaced new field must never cause an old default-looking last field
to be selected for authoring merely because its type/default key also matches.
