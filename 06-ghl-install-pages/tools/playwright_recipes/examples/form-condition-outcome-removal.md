# Remove inventoried form condition outcomes

Use `forms.conditions` with `condition.expected_rules` containing every existing
rule in its exact order. Set `condition.rules` to an unchanged ordered subset of
that list. Use an empty `rules` list to remove every inventoried card.

```json
{
  "location_id": "LOC",
  "location_name": "Fixture Account",
  "start_url": "https://app.convertandflow.com/v2/location/LOC/form-builder-v2/FORM",
  "condition": {
    "expected_rules": [{
      "match": "all",
      "clauses": [{"if_field": "Email", "operator": "Is Filled"}],
      "effect": "Redirect to URL",
      "redirect_url": "https://example.com/approved"
    }],
    "rules": []
  }
}
```

Use the exact predicate schema from the existing condition examples; do not
infer the live inventory from this example. Supported existing outcomes are
Redirect to URL, Display custom message and Disqualify lead, alongside captured
Show/Hide rules. A retained card must have one unambiguous exact match. Edits,
new cards or reordered retained cards require separate operations.

The writer checks the complete native rich-content inventory before opening
and confirming each scoped Delete Condition dialog. It verifies every retained
card after each deletion, requires the captured positive empty markers for
clear-all, then saves once and independently reopens the result. The parent
runner retains its lease, original intent and uncertain-write refusal. Existing
append inputs and receipt hashes stay compatible. Source checks do not establish
live outcome deletion or respondent behavior.
