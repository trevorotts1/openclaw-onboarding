# Authored Contact definitions to an existing form

`form_contact_field_chain.build_form_fields(inputs, evidence_root, page=page,
capability=receipt, transport=installed_transport)` combines the documented
Contact dependency adapter with the existing captured Dropdown or LARGE_TEXT
placement writer. Supply the existing authenticated caller-owned Page; this
function does not create forms or another browser/authentication session.

The input keys are `location_id`, `location_name`, `start_url`,
`expected_form_name`, `fields` and `native_bindings`. `fields` uses the exact
API input schema from [contact-field-dependencies.md](contact-field-dependencies.md).
A chain contains one field family only, with one separate `native_bindings`
entry per exact `field_key`:

```json
{
  "field_key": "contact.audience",
  "native_query_key": "audience:_who?",
  "expected_label": "Audience",
  "expected_placeholder": "Describe your audience. "
}
```

That example is a fictional LARGE_TEXT binding. `expected_placeholder` is
required only for LARGE_TEXT; Dropdown bindings instead use the key, native
Query Key and expected label alone. These native strings must be supplied
independently. The script does not strip `contact.`, derive punctuation, trim
placeholder whitespace, or infer native canvas IDs from API keys. An actual
native mismatch refuses completion and retains evidence for reconciliation.

All native binding values are validated before any API write. The exact
existing form URL/name and complete canvas identity are read before dependency
creation, then checked again before placement. A binding file owns this root
before a global Contact schema can be written. API intent and native intent
have separate journals. Retargeting that root to another form, definition or
native Query Key refuses before another API call.

The API returns canonical IDs/types/names/ordered options; these go through the
real `forms.configure` compiler/validator and existing native leaf. Placement
uses an enabled exact API picker row and its measured one-widget delta.
Dropdown/LARGE_TEXT wrappers expose no API field ID, so arbitrary disabled-row
legacy reuse remains refused. An API schema reused from the location is not
proof that a widget already on the form belongs to that schema.

Completed replay re-GETs API definitions but retains the original native job's
observed-at timestamp for its exact fingerprint. It never creates the field or
inserts the widget again. An uncertain POST or native Save retains its original
intent; rerunning is not permission to repeat the write.

The returned state remains `NEEDS_VERIFICATION` with false behavior/submission
flags. This work adds no new native selectors and does not complete all advanced
form families. Dropdown creation remains blocked by the documented Contact
option-array gap. Final client API/native execution, shared-field effects,
submitted answers and backend behavior remain separate pending proof.
