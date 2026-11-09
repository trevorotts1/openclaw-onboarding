# Existing native Address child Query Keys

Use `forms.configure` with `address_fields` to edit the Query Key of an existing
complete native Address group. This handler supports Street Address, Country,
State, City and Postal Code. It requires exactly one Address group with all five
children selected. The current native Auto Complete Address / New settings
accordion is recognized separately from those five field identities. Unknown
extra accordions require a new capture.

Each item requires `field` and `query_key`; `current_query_key` defaults to the
native canonical key. Supply the actual current key after a prior rename. The
handler checks the entire captured contact-field query inventory before any fill,
rejects collisions and swaps, preserves sibling child keys, saves once and reopens
through the native Forms list. Submission behavior stays unverified.

An item may also contain `properties` and `expected_properties` with identical
nonempty sets of property keys. Captured child properties are `label`,
`placeholder`, `short_label`, `required`, `hidden`, and `hidden_value`.
Every requested previous value must match before any Query Key or property
write. Untouched text, flags and visible hidden values of the edited child are
preserved; all requested children are preflighted first. The native child header
and visibility checkbox retain their canonical identity when Label is changed.

Use real booleans for Required and Hidden. They remain mutually exclusive,
including while the native controls are changing. Enabling Hidden requires an
explicit authored `hidden_value` string and matching expected absence `null`.
For example:

```json
{
  "field": "Street Address",
  "current_query_key": "address",
  "query_key": "address",
  "expected_properties": {"hidden": false, "hidden_value": null},
  "properties": {"hidden": true, "hidden_value": "Approved default"}
}
```

To change only the label, use `properties:{"label":"Street location"}` and
`expected_properties:{"label":"Street Address"}` with the existing Query Key.
There is no child Field Width control in this capture, so width changes are
refused. Child visibility selection, autocomplete switches, choice schemas and
legal copy remain outside this handler. Native UI was inspected during this
implementation; optional live Python jobs and submissions remain deferred.

`add_fields` also accepts the four captured native basic contact fields First Name,
Last Name, Phone and Email, in addition to the nine previously supported labels.
It reuses exact existing queries and refuses duplicate/ambiguous placement.

The source is implemented from existing native control captures. Optional and live
tests are deferred at the owner's request; this document does not claim a run.
