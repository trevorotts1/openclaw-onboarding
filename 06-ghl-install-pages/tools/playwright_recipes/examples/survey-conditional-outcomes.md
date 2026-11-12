# Survey conditional outcomes

Use `surveys.configure` with `configuration.outcomes` for an existing, explicitly
identified survey. Supply its exact name, complete numbered slide labels and the
complete intended rule order. This uses the current survey conditional builder.
The older `survey_rule_stack` flow remains the captured forward Jump To path.

The native survey controls were inspected on November 11, 2026 for compound
Show/Hide, custom messages and disqualification with a message or HTTPS redirect.
Disqualification currently supports **Disqualify After Submit** only. Other timing
modes stop for reconciliation. File Upload and Signature questions support owned
creation, existing-property edits, accepted file types, multiple files and max-file
limits. A saved upload field's public/private access setting is immutable.

Example input (replace the account, survey and slide identities with the actual
saved values; this example expects no existing rules):

```json
{
  "location_id": "LOC",
  "location_name": "Example Account",
  "start_url": "https://app.convertandflow.com/v2/location/LOC/survey-builder-v2/SURVEY",
  "configuration": {
    "expected_survey_name": "ZHC Application survey",
    "expected_slide_count": 2,
    "slide_labels": ["P1 - Contact", "P2 - Details"],
    "outcomes": {
      "expected_rules": [],
      "source_indices": [null],
      "rules": [
        {
          "match": "all",
          "clauses": [
            {"if_field": "Email", "operator": "Is Filled"},
            {"if_field": "First Name", "operator": "Is Filled"}
          ],
          "effect": "Display custom message",
          "message": "Thanks. We received your application."
        }
      ]
    }
  }
}
```

Built-in fields in this example must exist in the survey. Custom text and Number
conditions require the complete `field_bindings` inventory, including unused
siblings of the bound types. Each binding contains `label`, `query_key` and
`field_type` (`TEXT` or `NUMERICAL`). Number `Between` uses two inclusive decimal
bounds, for example `"value": ["2", "8"]`, when that shared profile is installed.

For a disqualification outcome, use `"effect": "Disqualify lead"` with either
`"mode": "Show custom message"` and `message`, or `"mode": "Redirect to URL"` and
an explicit credential-free HTTPS `redirect_url`. The script checks the captured
After Submit timing; it does not switch timing modes.

Keep existing rules in the complete authored inventory. The script stops on an
unrecognized existing effect or mixed legacy Jump To stack instead of replacing
it. Existing rich message markup is hashed and retained; plain authored messages
are distinct from arbitrary rich-HTML authoring.

A successful receipt binds the survey, all slide owners, complete saved rule order
and message markup hashes after Save/reopen. Completed replay rereads that state
without reauthoring rules. Receipts retain `behavior_verified: false`,
`submission_verified: false` and `disqualification_executed: false`: these source
and saved-configuration checks do not claim that a respondent submitted the survey
or executed an outcome.
