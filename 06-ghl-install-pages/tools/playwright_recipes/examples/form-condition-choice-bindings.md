# Conditions using existing choice fields

Declare the complete typed field inventory in `field_bindings`. Single Dropdown
(`SINGLE_OPTIONS`), Checkbox (`CHECKBOX`), and Radio (`RADIO`) bindings use their
native `query_key`. Multi Dropdown (`MULTIPLE_OPTIONS`) uses its actual Advanced
`unique_key`, including the `contact.` prefix; it has no local Query Key.

Use an exact choice label for `value` with Is Equal To or Is Not Equal To.
Is Empty and Is Filled omit `value`. The native picklist is selected through
`#picklistOptions-N`, then read back; the script never types a choice into a
plain-text control or changes the field's options. The native Checkbox Other
sentinel is represented by its saved summary label, `Other`.

The existing group, ordered stack, and conditional outcome actions share these
bindings. Typed canvas labels, native identity keys, all declared siblings, and
saved conditions remain verified independently of respondent evaluation.
