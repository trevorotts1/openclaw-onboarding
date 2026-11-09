# Contact field dependencies through the documented v3 API

`contact_field_dependencies.provision_fields(inputs, evidence_root,
capability=receipt, transport=installed_transport)` implements Contact
`LARGE_TEXT` creation/reuse and exact-ID `SINGLE_OPTIONS` reuse. The default
transport uses the existing Skill44 location-token headers and write gate;
there is no additional credential store or browser login.

The Contact schema was rechecked against current official documentation on
2026-11-09:

- [Contact field creation](https://marketplace.gohighlevel.com/docs/ghl/locations/create-custom-field/)
- [Contact field retrieval](https://marketplace.gohighlevel.com/docs/ghl/locations/get-custom-field/)
- [Contact field inventory](https://marketplace.gohighlevel.com/docs/ghl/locations/get-custom-fields/)
- [Custom Fields V2 object boundary](https://marketplace.gohighlevel.com/docs/ghl/custom-fields/create-custom-field/)

The creation adapter posts only `name`, `dataType:LARGE_TEXT`, explicit
`placeholder`, and `model:contact` to
`/locations/{locationId}/customFields` with Version `v3`. The provider generates
the field key; the separately authored expected `contact.*` key is checked by
independent GET. A mismatched generated key retains the created ID and requires
reconciliation, never another POST. Placeholder whitespace is significant.

**Dropdown creation remains blocked.** The current Contact request schema does
not document an option-array property. Its response lists `picklistOptions`,
which is not permission to use that property in a request. Custom Fields V2
has an options schema but explicitly supports Custom Objects and Company;
this adapter does not send Contact data to it or guess a legacy payload.
Dropdown requests must supply `allow_creation:false`, an exact existing ID and
the complete ordered expected option list. They never fall back to creation.

`inputs` contains only `location_id` and `fields`. Every field supplies `name`,
`field_key`, `data_type`, `expected_id` and a real Boolean `allow_creation`.
LARGE_TEXT additionally requires `placeholder`; SINGLE_OPTIONS requires
`options`. Use `expected_id:null` with explicit creation permission only for
LARGE_TEXT. Existing field IDs remain fixed through GET and replay.

The capability receipt has exactly these keys: `schema:
"skill6-contact-fields-v3-capability/1"`, `location_id`, `provider:"public_api"`,
`auth_kind` (`location_pit` or `location_oauth`), `version:"v3"`, `status:"PASS"`,
`scopes`, `checked_at` and `source`. It must come from the actual authenticated
host probe, be at most one hour old and include
`locations/customFields.readonly`; creating a field also requires
`locations/customFields.write`. Do not stamp an invented successful receipt.

All requests are structurally validated before API work. The complete
Contact-only list and all requested existing definitions are preflighted before
creating any field. The list is refreshed before each POST, with exact
name/key/ID conflict checks. Durable intent precedes POST; uncertain responses
or readbacks retain reconciliation state. Completed replay re-GETs definitions
and never repeats creation. Unsupported/foreign models, type drift, unordered
choices, missing IDs and extra type-specific inputs refuse explicitly.

Receipts are dependency proof only. Captured native placement, saved form
behavior, backend effects and submissions remain separate; no live client API
or native execution is claimed by the offline tests.
