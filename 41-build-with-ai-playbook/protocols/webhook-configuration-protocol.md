# Webhook Configuration Protocol -- Skill 41

## Purpose

Deep-dive on configuring the Custom Webhook action in GHL workflows. Covers modes, headers, raw JSON body, merge fields, and save response.

## Modes

### CUSTOM (advanced)
- Choose any HTTP method: GET, POST, PUT, DELETE
- Set Content-Type header manually
- Use Raw Body editor for JSON
- Full control over headers and query parameters
- Use this mode for JSON payloads with merge fields

### POST (simple)
- Body is key/value pairs only
- No raw body editor
- Limited header control
- Use this mode for simple form-style submissions

### GET (simple)
- No body
- Only query parameters
- Use this mode for data retrieval or simple triggers

## Headers

```
Content-Type: application/json
  -- Required for CUSTOM mode with raw JSON body
  -- Tells the receiving server the body is JSON

Authorization: Bearer ${TOKEN}
  -- For bearer token auth
  -- Operator must paste their actual token after build
  -- Never include real tokens in the generated prompt

X-API-Key: ${API_KEY}
  -- For API key auth
  -- Operator pastes their key after build

Custom headers:
  -- Any key-value pair the receiving system requires
  -- Can use merge fields: {{location.api_token}}
```

## Raw JSON Body (CUSTOM mode only)

1. Select CUSTOM event mode
2. Set Content-Type: application/json
3. Paste valid JSON in the Raw Body editor
4. Embed merge fields directly in the JSON:

```
{
  "contact_id": "{{contact.id}}",
  "first_name": "{{contact.first_name}}",
  "last_name": "{{contact.last_name}}",
  "email": "{{contact.email}}",
  "phone": "{{contact.phone}}",
  "tags": "{{contact.tag}}",
  "location_id": "{{location.id}}",
  "location_name": "{{location.name}}",
  "custom_field_value": "{{contact.ZHC_lead_source}}",
  "custom_value": "{{custom_values.office_phone}}",
  "appointment_date": "{{appointment.start_time}}",
  "appointment_status": "{{appointment.status}}"
}
```

## Merge fields available in webhooks

### Contact fields
- {{contact.id}}
- {{contact.first_name}}
- {{contact.last_name}}
- {{contact.full_name}}
- {{contact.email}}
- {{contact.phone}}
- {{contact.address}}
- {{contact.city}}
- {{contact.state}}
- {{contact.postal_code}}
- {{contact.country}}
- {{contact.tag}}

### Location fields
- {{location.id}}
- {{location.name}}
- {{location.email}}
- {{location.phone}}
- {{location.address}}
- {{location.api_token}}
- {{location.external_api_key}}

### Custom values
- {{custom_values.<name>}}

### Appointment fields (when trigger is appointment-related)
- {{appointment.id}}
- {{appointment.start_time}}
- {{appointment.end_time}}
- {{appointment.status}}
- {{appointment.calendar_id}}

### Opportunity fields (when trigger is opportunity-related)
- {{opportunity.id}}
- {{opportunity.name}}
- {{opportunity.status}}
- {{opportunity.pipeline_id}}
- {{opportunity.stage_id}}

## Save Response

Enable "Save response from this Webhook" to store the response for follow-up actions:
- The response is stored as a custom value or contact field (depending on workflow configuration)
- Subsequent actions can reference the saved response
- Useful for: checking CRM sync status, parsing external API responses, conditional branching based on response

## Security notes

- Never include real API keys or tokens in the generated prompt
- Use placeholder syntax: ${TOKEN}, ${API_KEY}, <OPERATOR_WILL_PASTE>
- The operator pastes their actual credentials after the AI builds the workflow
- Always use HTTPS URLs (never HTTP)
- Verify the webhook URL domain belongs to the intended system

## Common webhook patterns

### CRM sync
POST to CRM API with contact data
Headers: Content-Type, Authorization
Body: contact fields + appointment/opportunity data

### Slack notification
POST to Slack incoming webhook
Headers: Content-Type
Body: {"text": "New lead: {{contact.first_name}} {{contact.last_name}}"}

### Zapier trigger
POST to Zapier webhook URL
Headers: Content-Type
Body: full contact object as JSON

### Internal API
POST to operator's internal API
Headers: Content-Type, X-API-Key
Body: contact data + custom fields

## Error handling

If the webhook fails at runtime:
1. Check execution logs for the exact error
2. Verify the URL is correct and reachable
3. Verify headers are correct (especially Authorization)
4. Verify the raw JSON body is valid JSON
5. Verify merge fields are spelled correctly
6. Test the webhook independently with a tool like curl or Postman
7. If the receiving system requires specific formatting, adjust the raw body
