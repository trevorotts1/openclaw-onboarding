# GHL Webhooks Setup + Events Reference

> **Scope of this file:** Webhook configuration, inbound event types, and event payload patterns for GoHighLevel.
> Base URL: `https://services.leadconnectorhq.com`
> Auth: `Authorization: Bearer $GOHIGHLEVEL_API_KEY` — the LOCATION PIT from `~/.openclaw/secrets/.env`. In the cURL templates below, substitute `$GOHIGHLEVEL_API_KEY` for `<PRIVATE_INTEGRATION_TOKEN>` and use double quotes so it expands. See SKILL.md "Credentials" for the fail-loud resolver.
> Version header: `Version: 2021-04-15` (required on all calls)

---

## Overview

GoHighLevel webhooks deliver real-time event notifications to your endpoint when actions occur inside a location (sub-account). You configure webhooks at the location level. The system sends an HTTP POST to your URL with a JSON payload describing the event.

---

## Webhook Configuration (via GHL UI)

Webhooks in GHL v2 are managed through the GHL UI, not the API directly:

1. Log in to your GHL account (Convert and Flow dashboard)
2. Go to: **Settings > Integrations > Webhooks**
3. Click **Add Webhook**
4. Enter your endpoint URL (must be HTTPS and publicly accessible)
5. Select which event types to subscribe to
6. Save - GHL will send a test ping to verify the endpoint is reachable

---

## Inbound Event Types

GHL fires webhooks for the following event categories. Each event arrives as a POST with `Content-Type: application/json`.

### Contact Events
| Event | Trigger |
|-------|---------|
| `ContactCreate` | New contact created |
| `ContactUpdate` | Contact fields updated |
| `ContactDelete` | Contact deleted |
| `ContactDndUpdate` | Contact DND status changed |
| `ContactTagUpdate` | Tags added or removed |

### Conversation Events
| Event | Trigger |
|-------|---------|
| `ConversationProviderOutboundMessage` | Message sent outbound |
| `InboundMessage` | Inbound message received (SMS, email, FB, IG, etc.) |
| `OutboundMessage` | Outbound message sent |
| `ConversationUnreadUpdate` | Unread status changed |

### Opportunity Events
| Event | Trigger |
|-------|---------|
| `OpportunityCreate` | New opportunity created |
| `OpportunityUpdate` | Opportunity fields updated |
| `OpportunityDelete` | Opportunity deleted |
| `OpportunityStageUpdate` | Stage changed |
| `OpportunityStatusUpdate` | Status changed (open/won/lost/abandoned) |
| `OpportunityMonetaryValueUpdate` | Dollar value changed |

### Appointment / Calendar Events
| Event | Trigger |
|-------|---------|
| `AppointmentCreate` | Appointment booked |
| `AppointmentUpdate` | Appointment changed |
| `AppointmentDelete` | Appointment cancelled |

### Form / Survey Events
| Event | Trigger |
|-------|---------|
| `FormSubmission` | Form submitted by a contact |
| `SurveySubmission` | Survey submitted |

### Order / Payment Events
| Event | Trigger |
|-------|---------|
| `OrderCreate` | New order placed |
| `OrderStatusUpdate` | Order status changed |
| `InvoiceCreate` | Invoice created |
| `InvoiceUpdate` | Invoice updated |
| `InvoiceSent` | Invoice sent to contact |
| `InvoicePaid` | Invoice marked as paid |
| `InvoiceVoid` | Invoice voided |
| `InvoiceDeleted` | Invoice deleted |
| `PaymentReceived` | Payment recorded |
| `SubscriptionCreate` | New subscription created |
| `SubscriptionCancel` | Subscription cancelled |

### Location / Account Events
| Event | Trigger |
|-------|---------|
| `LocationUpdate` | Location settings changed |

### Note Events
| Event | Trigger |
|-------|---------|
| `NoteCreate` | Note added to a contact |
| `NoteUpdate` | Note edited |
| `NoteDelete` | Note deleted |

### Task Events
| Event | Trigger |
|-------|---------|
| `TaskCreate` | Task created |
| `TaskUpdate` | Task updated |
| `TaskComplete` | Task marked complete |
| `TaskDelete` | Task deleted |

### User Events
| Event | Trigger |
|-------|---------|
| `UserCreate` | User added to location |
| `UserUpdate` | User updated |
| `UserDelete` | User removed |

---

## Webhook Payload Structure

Every webhook POST contains a JSON body. The exact fields vary by event type but share this common envelope:

```json
{
  "type": "ContactCreate",
  "locationId": "abc123LocationId",
  "id": "abc123RecordId",
  "timestamp": "2024-01-15T10:30:00Z",
  "data": {
    // event-specific fields
  }
}
```

### Example: Contact Create Payload

```json
{
  "type": "ContactCreate",
  "locationId": "abc123LocationId",
  "id": "contactIdHere",
  "firstName": "Jane",
  "lastName": "Smith",
  "email": "jane@example.com",
  "phone": "+15555551234",
  "tags": ["lead", "webinar"],
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Example: Inbound Message Payload

```json
{
  "type": "InboundMessage",
  "locationId": "abc123LocationId",
  "conversationId": "convIdHere",
  "contactId": "contactIdHere",
  "messageType": "SMS",
  "body": "Hey, I have a question",
  "direction": "inbound",
  "dateAdded": "2024-01-15T10:31:00Z"
}
```

### Example: Opportunity Stage Update Payload

```json
{
  "type": "OpportunityStageUpdate",
  "locationId": "abc123LocationId",
  "id": "opportunityIdHere",
  "name": "Lead from Website",
  "pipelineId": "pipelineIdHere",
  "pipelineStageId": "stageIdHere",
  "status": "open",
  "monetaryValue": 1500,
  "contactId": "contactIdHere"
}
```

---

## Webhook Security

- GHL does NOT currently sign webhook payloads with a secret (unlike Stripe/Twilio).
- Validate the `locationId` in the payload matches your expected location.
- Optionally whitelist GHL IP ranges if you need additional security.
- Return HTTP 200 quickly - GHL will retry if your endpoint times out.

---

## Retry Behavior

- GHL retries failed webhook deliveries (non-200 responses) multiple times with exponential backoff.
- Your endpoint should respond with HTTP 200 within 10 seconds.
- For long-running tasks, respond 200 immediately and process async.

---

## Common Webhook Errors

| Problem | Cause | Fix |
|---------|-------|-----|
| No events arriving | Endpoint not HTTPS or not publicly reachable | Use ngrok for local dev, public URL for prod |
| Events arrive but parsing fails | Payload structure mismatch | Log raw body and inspect `type` field first |
| Duplicate events | GHL retried after your endpoint was slow | Idempotency key: use `id` + `type` + `timestamp` combo |
| Wrong location events | Multiple locations sending to same endpoint | Filter by `locationId` in your handler |
