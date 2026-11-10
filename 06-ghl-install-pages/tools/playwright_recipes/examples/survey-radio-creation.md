# Create a survey with an authored Radio question list

The maintained host now accepts `surveys.create` with `radio_questions`. This is
a bounded single-slide flow: create a new survey containing one explicitly
requested captured standard field, independently reopen that exact new editor,
then create/reuse the authored Radio definitions and place them on its saved
slide through the existing measured Radio API/native chain. It does not create
additional slides or configure conditional completion rules.

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
  "standard_fields": ["Email"],
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

Exactly one standard field is required: `Email`, `First Name`, `Last Name` or
`Phone`. It provides a positively loaded native owner instead of assuming an
empty slide is ready. Existing same-name surveys are refused when this creation
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
