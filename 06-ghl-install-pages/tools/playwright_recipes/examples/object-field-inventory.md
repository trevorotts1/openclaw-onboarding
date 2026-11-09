# API-owned object field inventory

The native Radio placement handler accepts a fresh successful same-location
`custom_fields.get` or `custom_fields.list` dependency receipt. Supply normalized
records with their exact `id` and `field_key`. A location-wide list may also
contain unrelated field types: these retain their identities and never become
placement targets merely because they appear in the receipt.

Every requested field must match its complete API-owned Radio definition,
including name, type and ordered options. Duplicate IDs or keys anywhere in the
inventory, malformed identity records, stale reads, foreign locations and
missing or changed requested definitions stop before native insertion. The
handler does not create or modify API field definitions.

This inventory support applies to existing form and survey object-field
placement. It does not add native widget support for the unrelated types.
