# Native form Pixel tracking settings

`forms.settings` accepts a `tracking` object with `expected` and `changes`.
Both maps must have the same nonempty set of keys chosen from `pixel_id`,
`page_view_event`, and `submission_event`. Supply exact inventoried previous
values and approved desired values; the example config changes only the native
submission event and preserves the existing Pixel ID.

Pixel IDs are explicit numeric strings; `""` clears the existing ID. Event
values use the exact native labels, including spaces: `Page View` and
`Submit Application`. The native menu capture also includes AddToWishlist,
CompleteRegistration, Contact, CustomizeProduct, Donate, FindLocation,
InitiateCheckout, Lead, Purchase, Schedule, Search, StartTrial and Subscribe.
Unknown labels require a new capture rather than a guessed mapping.

The handler reads all three settings before the first change, requires every
requested previous value to match, preserves untouched tracking settings, and
checks the full target state before Save. Native event options are found by a
bounded scroll of the actual virtualized option list and exact visible text.
After the native outer Save, independent Forms-list reopen checks all values.
The completion binds the configuration hash and exact form editor identity.

No Preview, submission or Pixel event test is executed. A saved configuration
does not prove Meta received events. Cookie consent belongs to the native
Integrate / Embed code options and is not changed by this Settings operation.
This module does not claim support for arbitrary third-party integrations.
