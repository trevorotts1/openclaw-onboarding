# GHL Webhook Reference -- Skill 41

Sources:
- Inbound Webhook: https://help.gohighlevel.com/support/solutions/articles/155000003147-workflow-trigger-inbound-webhook
- Custom Webhook: https://help.gohighlevel.com/support/solutions/articles/155000003305-workflow-action-custom-webhook
- Outbound Webhook: https://help.gohighlevel.com/support/solutions/articles/155000003299-workflow-action-webhook-outbound-

## Custom Webhook Action

Sends data to external applications from within a workflow.

## Modes

### CUSTOM (advanced)
- Choose method: GET, POST, PUT, DELETE
- Set Content-Type header manually
- Use Raw Body editor for JSON
- Full control over headers and query parameters
- Best for: JSON payloads with merge fields, authenticated APIs

### POST (simple)
- Body is key/value pairs only
- No raw body editor
- Limited header control
- Best for: simple form-style submissions

### GET (simple)
- No body
- Only query parameters
- Best for: data retrieval, simple triggers

## Headers

```
Content-Type: application/json
  -- Required for CUSTOM mode with raw JSON body
  -- Tells receiving server the body is JSON

Authorization: Bearer ${TOKEN}
  -- For bearer token auth
  -- Operator pastes actual token after build

X-API-Key: ${API_KEY}
  -- For API key auth

Custom headers:
  -- Any key-value pair the receiving system requires
  -- Dynamic values: {{location.api_token}}
```

## Raw JSON Body

Must use CUSTOM event mode. Set Content-Type: application/json. Paste valid JSON with merge fields.

```
{
  "contact_id": "{{contact.id}}",
  "first_name": "{{contact.first_name}}",
  "email": "{{contact.email}}",
  "phone": "{{contact.phone}}",
  "location_id": "{{location.id}}",
  "custom_value": "{{custom_values.office_phone}}"
}
```

## Merge Fields

### Contact fields
{{contact.id}}, {{contact.first_name}}, {{contact.last_name}}, {{contact.full_name}}, {{contact.email}}, {{contact.phone}}, {{contact.address}}, {{contact.city}}, {{contact.state}}, {{contact.postal_code}}, {{contact.country}}, {{contact.tag}}

### Location fields
{{location.id}}, {{location.name}}, {{location.email}}, {{location.phone}}, {{location.address}}, {{location.api_token}}, {{location.external_api_key}}

### Custom values
{{custom_values.<name>}}

### Appointment fields
{{appointment.id}}, {{appointment.start_time}}, {{appointment.end_time}}, {{appointment.status}}, {{appointment.calendar_id}}

### Opportunity fields
{{opportunity.id}}, {{opportunity.name}}, {{opportunity.status}}, {{opportunity.pipeline_id}}, {{opportunity.stage_id}}

## Save Response

Enable "Save response from this Webhook" to store response for follow-up actions. Response stored as custom value or contact field for subsequent actions to reference.

## Security

- Never include real tokens in generated prompts
- Use placeholder syntax: ${TOKEN}, ${API_KEY}
- Operator pastes actual credentials after build
- Always use HTTPS URLs
- Verify webhook URL domain belongs to intended system
