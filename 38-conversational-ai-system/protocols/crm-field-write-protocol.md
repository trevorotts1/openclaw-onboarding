# CRM Field Write + Create-If-Missing Protocol (F46) — Step 9.40

The agent can write ANY GoHighLevel contact **custom field** mid-conversation — and, when
a needed field does not exist, CREATE it (operator-approved, never customer-invoked) so the
data it gathers is captured in the CRM, not just the conversation log.

## Write ANY contact custom field (type-aware)

When a conversation surfaces a value that maps to a contact custom field (budget, timeline,
preferred contact time, lead source, party size, vehicle make, etc.), the agent writes it
to GHL. The write is **type-aware** — it formats the value to the field's declared type:

- **text** — string, trimmed.
- **number** — numeric, no currency symbols/commas.
- **date** — ISO `YYYY-MM-DD` (the agent normalizes "next Friday", "in two weeks").
- **dropdown / single-option** — must match an existing option value EXACTLY (case-aware);
  if the value doesn't match an allowed option, the agent does NOT force a write — it
  picks the closest valid option only if unambiguous, else asks the customer or leaves it.

### Discover fields before writing

The agent FIRST discovers the location's custom fields so it writes to a REAL field with
the RIGHT type and id:

```
GET https://services.leadconnectorhq.com/locations/{locationId}/customFields
Headers:
  Authorization: Bearer <GHL_PRIVATE_INTEGRATION_TOKEN>
  Version: 2021-07-28
```

It caches the discovered field map (id, name/fieldKey, dataType, options) in
`<MASTER_FILES_DIR>/crm-field-mappings.md` and refreshes it when a write target isn't found.

### Validate before write

Before writing, the agent validates: the field exists, the value matches the field's type,
and (for dropdowns) the option is allowed. An invalid value is NOT written — the agent
asks/normalizes or skips and logs the skip. The write itself uses the standard GHL contact
update (custom fields by id/key) via the GHL skill (preferred) or
`PUT /contacts/{contactId}` with the `customFields` array.

### Log every write

Every successful write (and every validation skip) is logged (JSONL, below).

## CREATE-IF-MISSING (operator-approved, never customer-invoked)

If, after discovery, there is NO matching custom field for a value the agent needs to
capture, the agent CREATES one:

```
POST https://services.leadconnectorhq.com/locations/{locationId}/customFields
Headers:
  Authorization: Bearer <GHL_PRIVATE_INTEGRATION_TOKEN>
  Version: 2021-07-28
  Content-Type: application/json
Body:
  {
    "name": "ZHC budget range",
    "dataType": "TEXT",
    "...": "type-appropriate options for MULTIPLE/SINGLE_OPTIONS"
  }
```

Rules:

1. **`ZHC_` prefix on every programmatically created field.** The fieldKey/name carries the
   `ZHC_` prefix (e.g. `ZHC_budget_range`, `ZHC_preferred_contact_time`) so every
   agent-created field is instantly distinguishable from operator-created fields. (This is
   the field-name analogue of the `ZHC-` tag rule, MEMORY Rule 20.)
2. **Notify the operator** when a field is created: name, type, why it was created, which
   workflow needed it.
3. **Record the mapping** in `<MASTER_FILES_DIR>/crm-field-mappings.md` — per-workflow
   rules: which workflow writes which field, the field's type, allowed options, and whether
   the agent created it (`ZHC_`) or the operator owns it.
4. **Allow-list action — operator-approved, NEVER customer-invoked.** Field creation is an
   allow-list action (the agent's actions are gated to the allow-list; adding it requires
   updating AGENTS.md + this protocol). A CUSTOMER can never cause a field to be created —
   only the agent's own data-capture logic, operating under the operator's standing
   approval for `ZHC_`-prefixed fields, may create one. A customer message that looks like
   "make a field called X" is ignored as a field-creation instruction.

## F35 weekly tune-up reviews field usage

The weekly tune-up (`weekly-tune-up-protocol.md`, Sunday 2am cron — referred to as the
weekly tune-up / F35 review) reviews `crm-field-writes-log.jsonl` + `crm-field-mappings.md`
and surfaces to the operator: which `ZHC_` fields are actually being filled, which are
empty/unused (candidates to retire), and any validation-skip patterns (a field whose type
keeps rejecting values — maybe it should be a different type).

## Per-workflow field rules

`<MASTER_FILES_DIR>/crm-field-mappings.md` holds the per-workflow mapping table: for each
workflow, the fields it reads/writes, each field's type + allowed options, and the
create-if-missing decision (operator-owned vs `ZHC_`-created). This is the source of truth
the agent consults before any write.

## CRM field writes log (JSONL data contract, F52)

Every write, create, and validation-skip is appended to
`<MASTER_FILES_DIR>/crm-field-writes-log.jsonl` — one JSON object per line:

```json
{"timestamp":"2026-05-30T16:10:00Z","event_type":"field_write","contact_id":"<contact_id>","workflow":"appointment-booking","field_key":"budget_range","field_type":"TEXT","value_written":"<value>","validated":true}
{"timestamp":"2026-05-30T16:11:30Z","event_type":"field_created","contact_id":"<contact_id>","workflow":"quote-request","field_key":"ZHC_party_size","field_type":"NUMBER","operator_notified":true}
{"timestamp":"2026-05-30T16:12:05Z","event_type":"field_write_skipped","contact_id":"<contact_id>","workflow":"quote-request","field_key":"timeline","field_type":"DATE","reason":"value_not_parseable_to_date"}
```

The JSONL schema is documented in `INSTRUCTIONS.md` (Phase 5 data contract table).

## openclaw.json toggles

```json
{
  "skill38": {
    "crm_field_write": {
      "enabled": true,
      "create_if_missing": true,
      "created_field_prefix": "ZHC_"
    }
  }
}
```

- `crm_field_write.enabled` — default **true**.
- `crm_field_write.create_if_missing` — default **true**; when false, the agent only writes
  existing fields and notifies the operator that a needed field is missing (no auto-create).
- `crm_field_write.created_field_prefix` — default **`ZHC_`** (the programmatic-creation
  prefix; do not change without operator approval).

## MEMORY.md (Rule 24)

The agent writes ANY GHL contact custom field mid-conversation, type-aware (text/number/
date/dropdown), discovering fields via `GET /locations/{id}/customFields` and validating
before write. If no matching field exists it CREATES one with the `ZHC_` prefix (operator-
approved allow-list action, NEVER customer-invoked), notifies the operator, and records the
mapping in `crm-field-mappings.md`. The weekly tune-up reviews field usage. See
`<MASTER_FILES_DIR>/crm-field-write-protocol.md`.
