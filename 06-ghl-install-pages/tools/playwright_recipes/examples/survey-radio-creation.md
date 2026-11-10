# Create a survey with an authored Radio question list

The maintained host now accepts `surveys.create` with `radio_questions`. This is
a bounded flow with one to four slides: supply distinct captured standard fields,
one per slide, independently reopen every saved owner, then create/reuse the
authored Radio definitions and place them on the explicit `target_slide`. It does
not configure conditional completion rules or place Radio questions on several
different slides in one creation job.

Use the existing host entrypoint and an already measured same-location
`radio_field_capability` in the probes JSON:

```bash
python3 06-ghl-install-pages/tools/playwright_recipes/host.py \
  --operation surveys.create \
  --inputs /absolute/path/survey-radio-inputs.json \
  --probes /absolute/path/measured-probes.json \
  --evidence-root /absolute/path/durable-survey-run \
  --check
```

Remove `--check` to execute through the maintained authenticated browser manager.
The host capability must be the actual `skill44-radio-fallback-capability/1`
receipt used by `radio_dependencies`; the source test fixture is not client
proof. Missing, stale, foreign-location or unsupported method/version evidence
stops before browser or API creation. No new login, credentials or API transport
is added. Caller-owned authenticated Pages also work through `host.run_recipe`.

Example authored inputs (replace identities, name, field key and options):

```json
{
  "location_id": "LOC",
  "location_name": "Fixture Account",
  "start_url": "https://app.convertandflow.com/v2/location/LOC/survey-builder/main",
  "name": "New authored survey",
  "allow_creation": true,
  "standard_fields": ["Email", "First Name"],
  "target_slide": 2,
  "radio_questions": [{
    "name": "Service",
    "field_key": "contact.service",
    "data_type": "RADIO",
    "options": ["Coaching", "Consulting"],
    "expected_id": null,
    "allow_creation": true
  }]
}
```

Use one to four distinct standard fields from `Email`, `First Name`, `Last Name`
and `Phone`. Each creates one positively loaded native slide owner. For more
than one field, `target_slide` must be an explicit integer from 1 through the
number of fields. The legacy one-field plan may omit it and retains slide 1. Existing same-name surveys are refused when this creation
plan requests its standard field; they are never silently adopted. Existing
Radio definitions require their exact `expected_id` and `allow_creation:false`.
Expected-absent name/key collisions refuse before another schema POST.

The outer job, shell, Radio API and native placement retain separate journals.
An uncertain create/save blocks retry; preserve all evidence and reconcile the
same editor and field identities. A completed outer replay returns its original
receipt without another shell, schema POST or native placement. The receipt
binds the new editor, complete saved owner identity, exact API definitions and
the independently reopened native placement. `NEEDS_VERIFICATION` remains the
final host state because respondent submission and behavioral acceptance are
not implied. Live installed Mac/VPS acceptance is still pending.
