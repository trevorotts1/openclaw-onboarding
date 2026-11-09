# Contact fields through the named Skill 6 front door

Use `forms.configure` with one exclusive `contact_field_plan`. The parent binds
the existing form URL and account; the plan contains the exact form title,
Contact API definitions, and separately observed native Query Keys/labels.

```json
{
  "location_id": "LOC",
  "location_name": "Fixture Account",
  "start_url": "https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM",
  "contact_field_plan": {
    "expected_form_name": "Existing form",
    "fields": [{
      "name": "Audience",
      "field_key": "contact.audience",
      "data_type": "LARGE_TEXT",
      "placeholder": "Describe your audience. ",
      "expected_id": null,
      "allow_creation": true
    }],
    "native_bindings": [{
      "field_key": "contact.audience",
      "native_query_key": "audience:_who?",
      "expected_label": "Audience",
      "expected_placeholder": "Describe your audience. "
    }]
  }
}
```

Supply the actual current sub-account Contact v3 capability in the host probe's
`contact_field_capability`, outside these authored inputs. Use the exact schema
documented in [contact-field-dependencies.md](contact-field-dependencies.md),
with location-level PIT/OAuth, a fresh `checked_at`, and read scope plus write
scope when creation is requested. Never put credentials in either JSON file.
The probe's `lanes` must describe an actually available maintained browser rail.

Validate the full host route without opening a browser or writing evidence:

```bash
python3 host.py --operation forms.configure --inputs form-fields.json \
  --probes actual-host-probes.json --evidence-root /absolute/durable/run --check
```

Remove `--check` to run through the existing managed browser/Firebase lifecycle.
Python hosts may instead call `host.run_recipe(..., page=owned_page)`. A measured
fallback Page still runs the same native chain and cannot use a generic provider
callback as completion proof. The standalone `recipe_cli.py` can compile/check
this job, but direct execution without the host's live capability refuses.

The chain verifies the exact existing form/canvas before global field creation,
then runs the captured native insertion and independent reopening. It retains
an outer runner journal plus separate `contact-fields/delivery-state.json` and
`contact-fields/native/state.json` journals. Interrupted writes require explicit
reconciliation. Completed replay validates the original identities and returns
pending proof without another API POST, insertion, or managed browser launch.

Only documented Contact `LARGE_TEXT` creation and exact existing Dropdown reuse
are supported. Dropdown option-array creation, arbitrary legacy native reuse,
submissions, behavior acceptance, and publication remain unsupported or pending.
`NEEDS_VERIFICATION` is the expected saved-configuration outcome.
