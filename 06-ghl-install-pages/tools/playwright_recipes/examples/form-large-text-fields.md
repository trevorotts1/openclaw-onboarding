# Existing API-owned Multi Line / LARGE_TEXT placement

Use `forms.configure` with `large_text_fields` and `field_dependencies` in their
own job. The API owns the existing `LARGE_TEXT` field definition; native Add
Object Fields places it on the exact existing form. No global field is created
or changed and no respondent input is submitted.

The API definition has four normalized keys: `id`, `name`, `field_key`, and
`data_type`. It has no options list. Each placement request additionally supplies
`native_query_key`, `expected_label`, and `expected_placeholder` from actual
native inventory. Preserve the placeholder exactly, including trailing spaces.
Do not trim it or derive native Query Key from API fieldKey. The captured native
Query Key can contain punctuation such as a colon and question mark that is
absent from the API key. Native Query Keys are compared as opaque strings and
are never interpolated into CSS selectors.

The example uses fictional field data and placeholder IDs; its
`observed_at:0` is deliberately stale. New execution requires a real fresh
successful same-location API GET/list receipt with the exact field definition.
This example is not evidence that an API read occurred.

The native textarea has no API ID or name attribute. The handler binds the
exact API picker row to the unique native Query Key, Label property, and exact
textarea aria-label / Placeholder property. It requires the captured empty
builder value rather than adopting unexpected content. Every existing Large
Text widget is independently inventoried before selection. An initially
disabled API picker row is refused because no captured canvas API-ID attribute
independently proves legacy reuse. Known successful insertion resumes through
its original completed journal; matching native text alone never upgrades an
unknown legacy binding. Unknown, duplicate, changed or conflicting identities
stop before insertion.

Only one exact field is inserted at a time. The observed wrapper position is
used to check all remaining field identities and existing Large Text bindings;
no timestamp or invented canvas ID stands in for an API ID. After native Save
settles, independent Forms-list reopen must return the complete same definitions
and preserved field identities. The result binds the approved API identity,
explicit native Query Key, exact placeholder and configuration hash. Submission
behavior remains unverified. Editing text-field properties and creating API
schemas remain separate operations.
