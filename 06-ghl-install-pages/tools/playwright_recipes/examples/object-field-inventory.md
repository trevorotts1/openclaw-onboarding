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

Radio canvas inputs expose the exact API field ID in `name`. That opaque ID,
native Radio type and ordered choices bind the field. The native form Query Key
is separate URL-prefill metadata and is not derived from the API fieldKey.
Existing requested widgets' actual Query Keys are read before any insertion,
preserved through placement, and checked again after independent reopening.
New widgets' native Query Keys are measured after placement and checked against
their own saved values. No planner or API definition is rewritten to guess them.

This inventory support applies to existing form and survey object-field
placement. It does not add native widget support for the unrelated types.
