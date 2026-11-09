# Existing native Address child Query Keys

Use `forms.configure` with `address_fields` to edit the Query Key of an existing
complete native Address group. This handler supports Street Address, Country,
State, City and Postal Code. It requires exactly one Address group with all five
children selected. It does not change labels, child visibility, required states,
choice schemas or legal copy.

Each item requires `field` and `query_key`; `current_query_key` defaults to the
native canonical key. Supply the actual current key after a prior rename. The
handler checks the entire captured contact-field query inventory before any fill,
rejects collisions and swaps, preserves sibling child keys, saves once and reopens
through the native Forms list. Submission behavior stays unverified.

`add_fields` also accepts the four captured native basic contact fields First Name,
Last Name, Phone and Email, in addition to the nine previously supported labels.
It reuses exact existing queries and refuses duplicate/ambiguous placement.

The source is implemented from existing native control captures. Optional and live
tests are deferred at the owner's request; this document does not claim a run.
