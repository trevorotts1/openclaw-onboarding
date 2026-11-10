# Native Single Line survey creation

Pass `survey-single-line-creation.json` through the existing `surveys.create`
recipe. A `text` batch places one or more captured Single Line (`TEXT`) questions on an
explicitly requested slide, starting from its positive empty owner. Label, Placeholder, Short Label, Query Key,
Required, Hidden and the conditional Hidden value are authored and independently
read after Save and list reopen. Required and Hidden cannot both be true.

Each slide accepts ordered Single Line batches before any Radio batch on that slide.
Each question gets its own retained child journal. Subsequent TEXT insertion uses
the captured blank tail beneath the complete prior question inventory; if that
measured region is unavailable, the writer stops without an edge/new-page fallback.
Existing Radio batches may follow it; their public API definitions remain on the
existing capability-gated dependency path. A survey containing only text batches
needs no Radio custom-field API capability and creates no API field schema.

Insertion and Save retain their own durable child intent journal. An uncertain
insertion or Save stops for reconciliation instead of repeating either action.
The aggregate survey receipt binds all saved owners, authored order and exact
question properties. This does not establish respondent submission behavior.
Other widget types and media remain separate scope.

Use `survey-single-line-properties.json` with `surveys.configure` to edit existing
TEXT properties. Supply every TEXT question on every slide in both `expected`
and `desired`, including unchanged siblings. Counts and positions must agree.
All current properties are checked before edits; Query Key swaps are refused,
and Query Key edits alongside other widget types require their separately
captured complete key inventory. Required/Hidden transitions disable the active
exclusion first. A single Save is followed by exact property and sibling reopen.
