# Existing API-owned Single Dropdown placement

Use `forms.configure` with `dropdown_fields` and `field_dependencies` in their
own job. The API owns the existing `SINGLE_OPTIONS` schema and ordered options;
this handler places it through the captured native Add Object Fields picker.
It never creates or edits a global contact-field definition.

Each requested field supplies the exact API `id`, `name`, `field_key`,
`data_type`, and ordered `options`, plus two independently inventoried native
values: `native_query_key` and `expected_label`. Do not derive the native Query
Key by stripping `contact.` from the API key. A captured legacy dropdown exposed
`contact.select_your_tshirt_size` in the API-backed picker but
`select_your_t-shirt_size` in the native Query Key property. They are distinct
bindings. The example illustrates that observed distinction; replace its IDs,
account and receipt with the actual approved inventory.

The example `observed_at:0` is deliberately stale. A new execution requires a
real fresh successful same-location API GET/list receipt. Unknown types, changed
definitions, missing option lists, duplicates or foreign receipts fail before
the first insertion. The dependency records contain API values only; do not
stamp native UI values into an API receipt.

The native dropdown has no API field ID on its canvas wrapper. The handler
selects the exact API-ID picker row, then checks the actual native Query Key,
label and complete ordered option text. Generated option timestamps are ignored.
Existing dropdowns are activated one at a time for preservation inventory. An
initially disabled API picker row is refused: its name/query/options do not
independently link the opaque API ID to a canvas widget. Resume a known
successful insertion through its original completed journal. An enabled row
cannot adopt another widget merely because its caption resembles the requested
field. Unknown legacy reuse needs explicit identity reconciliation.

Every requested row and existing dropdown definition is read before selection.
Only one exact field is selected and inserted at a time. The observed new
wrapper position, complete remaining field identities and all other dropdown
definitions must remain consistent. After native Save settles, independent
Forms-list reopen must return the same full native definitions and identities.
The result binds the API identity, explicit native Query Key and configuration
hash. Submission behavior remains unverified. New schema creation, changing
dropdown properties/options and other widget types are separate operations.
