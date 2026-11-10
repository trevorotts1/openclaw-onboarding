# Native Single Line survey creation

Pass `survey-single-line-creation.json` through the existing `surveys.create`
recipe. A `text` batch places one captured Single Line (`TEXT`) question on an
explicitly empty requested slide. Label, Placeholder, Short Label, Query Key,
Required, Hidden and the conditional Hidden value are authored and independently
read after Save and list reopen. Required and Hidden cannot both be true.

Each slide accepts one Single Line batch before any Radio batch on that slide.
Existing Radio batches may follow it; their public API definitions remain on the
existing capability-gated dependency path. A survey containing only text batches
needs no Radio custom-field API capability and creates no API field schema.

Insertion and Save retain their own durable child intent journal. An uncertain
insertion or Save stops for reconciliation instead of repeating either action.
The aggregate survey receipt binds all saved owners, authored order and exact
question properties. This does not establish respondent submission behavior.
Populated-slide TEXT append, other widget types and media remain separate scope.
