# Existing native two-clause T&C configuration

Use `forms.configure` with `consent` to edit existing native T&C clauses without
creating contact-field schemas, adding/removing clauses or checking visitor
consent. Native two-clause identity is mandatory. Supply caller-approved plaintext;
there is no generated legal-copy default. The example's text and hash markers must
be replaced before execution.

`expected_query_key` identifies the existing native element. Each requested clause
requires `index` (1 or 2), `text`, and `expected_html_sha256`. The helper
`forms_advanced.inspect_consent(page)` can read those hashes using the existing
managed page without exposing clause text or saving. Omitting a clause preserves
its exact existing HTML. Edited plaintext normalizes line endings and outer
whitespace, and intentionally replaces that clause's formatting.

`required` is optional and requires `expected_required` when supplied. `query_key`
is optional; the handler checks native contact-field query collisions before a
rename. It never clicks the visitor's consent checkboxes or the remove-clause
control. Saved values and sibling HTML are independently read after list reopen;
submission and behavior proof remain pending.

Existing custom simple form fields can use the normal `fields` input with an
explicit `field_type` (text/email/date/select), `current_placeholder` and
`current_query_key`. Only the captured five-property General Settings layout is
accepted. Extra choice/upload/constraint controls still require their own native
implementation; this is existing presentation editing, not custom-schema creation.

No optional/live tests were run for this feature at the owner's request.
