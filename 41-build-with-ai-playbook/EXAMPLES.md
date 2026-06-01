# Skill 41 -- Worked Examples

All examples use UNIVERSAL placeholders. No real business name, location id, or key appears. Replace
<...> placeholders with the live values at runtime. Every example shows the honest-gap path where
a GHL capability may be unavailable.

## Example 1 -- New lead welcome sequence (no webhook)

```
Operator: "Build me a workflow that welcomes new leads."

Agent (Skill 41 brainstorm flow):
  1. Summarize: "You want a workflow that triggers when a new contact is created,
     adds a tag, sends a welcome email, waits a day, then sends a follow-up SMS if
     they haven't responded. Is that right?"
  2. Operator confirms YES.
  3. Dependency audit:
     - Tag ZHC-new-lead: does not exist --> CREATE
     - Tag ZHC-welcome-sent: does not exist --> CREATE
     - Tag ZHC-responded: does not exist --> CREATE
     - Custom value welcome_email_subject: does not exist --> CREATE
  4. Create dependencies via GHL API (dependency-creation.sh):
     - POST /locations/<locationId>/tags --> ZHC-new-lead
     - POST /locations/<locationId>/tags --> ZHC-welcome-sent
     - POST /locations/<locationId>/tags --> ZHC-responded
     - POST /locations/<locationId>/customValues --> welcome_email_subject = "Welcome to <Business>!"
     - GET each back to verify
     - Emit dependency_created events
  5. Generate standardized prompt (8 sections):

```
WORKFLOW NAME: New Lead Welcome Sequence

TRIGGER SPECIFICATION:
- Trigger: Contact Created
- Filters: none (all new contacts)

DEPENDENCY LIST (created before build):
- Tag: ZHC-new-lead
- Tag: ZHC-welcome-sent
- Tag: ZHC-responded
- Custom Value: welcome_email_subject = "Welcome to <Business>!"

ACTION SEQUENCE:
1. Add Tag: ZHC-new-lead
2. Send Email:
   - Template: Welcome
   - To: {{contact.email}}
   - From Name: {{location.name}}
   - Subject: {{custom_values.welcome_email_subject}}
   - Body: "Hi {{contact.first_name}}, welcome to <Business>! We're excited to help you."
3. Add Tag: ZHC-welcome-sent
4. Wait: 1 day
5. If/Else: Does contact have tag ZHC-responded?
   - YES branch: Remove from workflow
   - NO branch: Send SMS
     - To: {{contact.phone}}
     - Message: "Hi {{contact.first_name}}, just checking in! Reply STOP to opt out."

CONDITIONS:
- If/Else Step 5: contact.tag contains ZHC-responded
  - YES: exit workflow
  - NO: send SMS follow-up

WEBHOOK CONFIGURATION:
- None

SETTINGS:
- Allow Re-entry: No
- Stop on Response: Yes
- Time Window: All hours
- Sender Details: From Name = {{location.name}}, From Email = {{location.email}}

POST-BUILD VERIFICATION CHECKLIST:
1. Workflow name matches: "New Lead Welcome Sequence"
2. Trigger is Contact Created with no filters
3. Tags ZHC-new-lead, ZHC-welcome-sent, ZHC-responded exist
4. Custom value welcome_email_subject exists with value set
5. Action sequence: Add Tag --> Send Email --> Add Tag --> Wait --> If/Else --> SMS
6. If/Else evaluates tag ZHC-responded correctly
7. Wait step is 1 day
8. No webhook configured
9. Settings: re-entry = No, stop on response = Yes
10. Test with a test contact before publishing
```

  6. Operator pastes into GHL Workflow AI Builder (Automations > Build using AI).
  7. Operator runs verification checklist (all 10 items pass).
  8. Workflow published.
  9. Event log: build_completed (verification_score: 10/10).
```

## Example 2 -- Appointment reminder with webhook to external CRM

```
Operator: "Build a workflow that reminds people of appointments and sends the
appointment details to my external CRM."

Agent (Skill 41 brainstorm flow):
  1. Summarize: "You want a workflow triggered by an upcoming appointment that sends
     a reminder email/SMS AND posts the appointment data to an external CRM via webhook.
     Is that right?"
  2. Ask smart gaps:
     - How far before the appointment should the reminder fire? (operator: 24 hours)
     - What is the external CRM webhook URL? (operator: https://api.<crm>.com/webhooks/appointment)
     - What authentication does the CRM need? (operator: Bearer token in header)
  3. Operator confirms YES.
  4. Dependency audit:
     - Tag ZHC-appointment-reminder-sent: does not exist --> CREATE
     - Custom field ZHC_appointment_date: does not exist --> CREATE
     - Custom value crm_webhook_url: does not exist --> CREATE
     - Custom value crm_auth_token: operator says they will handle --> note, do NOT create
  5. Create dependencies via GHL API.
  6. Generate standardized prompt (webhook section included):

```
WORKFLOW NAME: Appointment Reminder + CRM Sync

TRIGGER SPECIFICATION:
- Trigger: Appointment Status
- Filters: Status = "confirmed", 24 hours before start time

DEPENDENCY LIST (created before build):
- Tag: ZHC-appointment-reminder-sent
- Custom Field: ZHC_appointment_date (dataType: date)
- Custom Value: crm_webhook_url = "https://api.<crm>.com/webhooks/appointment"

ACTION SEQUENCE:
1. Add Tag: ZHC-appointment-reminder-sent
2. Send Email:
   - To: {{contact.email}}
   - Subject: "Reminder: Your appointment tomorrow"
   - Body: "Hi {{contact.first_name}}, this is a reminder about your appointment
     on {{appointment.start_time}}."
3. Send SMS:
   - To: {{contact.phone}}
   - Message: "Reminder: You have an appointment tomorrow at {{appointment.start_time}}."
4. Custom Webhook (CUSTOM mode):
   - Method: POST
   - URL: {{custom_values.crm_webhook_url}}
   - Headers:
     - Content-Type: application/json
     - Authorization: Bearer <OPERATOR_WILL_PASTE_TOKEN>
   - Raw Body:
     {
       "contact_id": "{{contact.id}}",
       "first_name": "{{contact.first_name}}",
       "email": "{{contact.email}}",
       "phone": "{{contact.phone}}",
       "appointment_date": "{{appointment.start_time}}",
       "appointment_status": "{{appointment.status}}",
       "location_id": "{{location.id}}"
     }
   - Save Response: Yes

CONDITIONS:
- None (linear sequence)

WEBHOOK CONFIGURATION:
- Mode: CUSTOM (advanced)
- Method: POST
- URL: {{custom_values.crm_webhook_url}}
- Headers: Content-Type = application/json, Authorization = Bearer <operator-pasted-token>
- Raw JSON Body with merge fields for contact and appointment data
- Save Response enabled for follow-up actions

SETTINGS:
- Allow Re-entry: Yes (appointments can be rescheduled)
- Stop on Response: No
- Time Window: Business hours only (9 AM - 6 PM)
- Sender Details: From Name = {{location.name}}, From Number = {{location.phone}}

POST-BUILD VERIFICATION CHECKLIST:
1. Workflow name matches: "Appointment Reminder + CRM Sync"
2. Trigger is Appointment Status with confirmed filter
3. Tag ZHC-appointment-reminder-sent exists
4. Custom field ZHC_appointment_date exists (date type)
5. Custom value crm_webhook_url exists
6. Action sequence: Add Tag --> Email --> SMS --> Webhook
7. Webhook method is POST
8. Webhook URL matches custom value
9. Webhook headers include Content-Type: application/json
10. Raw JSON body includes contact.id, appointment.start_time, appointment.status
11. Settings: re-entry = Yes, time window = business hours
12. Test with a test contact before publishing
```

  7. Operator pastes into GHL Workflow AI Builder.
  8. Operator manually pastes their CRM Bearer token into the webhook Authorization header.
  9. Operator runs verification checklist (all 12 items pass).
  10. Workflow published.
  11. Event log: build_completed (verification_score: 12/12), webhook_configured.
```

## Example 3 -- Lead scoring with If/Else branches

```
Operator: "Build a workflow that scores leads based on form answers and routes
hot leads to sales."

Agent (Skill 41 brainstorm flow):
  1. Summarize: "You want a workflow triggered by a form submission that scores
     the lead based on their answers, tags hot leads, and sends a notification to
     sales. Is that right?"
  2. Ask smart gaps:
     - Which form? (operator: "Discovery Form")
     - What makes a lead "hot"? (operator: budget > $5000 AND timeline < 30 days)
  3. Operator confirms YES.
  4. Dependency audit:
     - Tag ZHC-hot-lead: does not exist --> CREATE
     - Tag ZHC-warm-lead: does not exist --> CREATE
     - Tag ZHC-cold-lead: does not exist --> CREATE
     - Custom field ZHC_budget_range: does not exist --> CREATE
     - Custom field ZHC_timeline_days: does not exist --> CREATE
  5. Create dependencies via GHL API.
  6. Generate standardized prompt:

```
WORKFLOW NAME: Lead Scoring and Routing

TRIGGER SPECIFICATION:
- Trigger: Form Submitted
- Filters: Form = "Discovery Form"

DEPENDENCY LIST (created before build):
- Tag: ZHC-hot-lead
- Tag: ZHC-warm-lead
- Tag: ZHC-cold-lead
- Custom Field: ZHC_budget_range (dataType: text)
- Custom Field: ZHC_timeline_days (dataType: number)

ACTION SEQUENCE:
1. Update Contact Field:
   - Field: ZHC_budget_range
   - Value: {{form.budget}}
2. Update Contact Field:
   - Field: ZHC_timeline_days
   - Value: {{form.timeline}}
3. If/Else: Is ZHC_budget_range greater than "$5000" AND ZHC_timeline_days less than "30"?
   - YES branch (HOT):
     a. Add Tag: ZHC-hot-lead
     b. Send Internal Notification:
        - To: sales team
        - Message: "HOT LEAD: {{contact.first_name}} {{contact.last_name}} --
          Budget: {{contact.ZHC_budget_range}}, Timeline: {{contact.ZHC_timeline_days}} days"
     c. Assign to User: sales-manager
   - NO branch (WARM/COLD):
     a. If/Else: Is ZHC_budget_range greater than "$1000"?
        - YES branch: Add Tag: ZHC-warm-lead
        - NO branch: Add Tag: ZHC-cold-lead
     b. Add to Workflow: "Nurture Sequence"

CONDITIONS:
- Main If/Else (Step 3):
  - Segment 1: ZHC_budget_range > $5000 AND ZHC_timeline_days < 30
    - YES: Hot lead path
    - NO: Warm/cold evaluation path
- Nested If/Else (Step 4a):
  - Segment 1: ZHC_budget_range > $1000
    - YES: Warm lead
    - NO: Cold lead

WEBHOOK CONFIGURATION:
- None

SETTINGS:
- Allow Re-entry: No
- Stop on Response: No
- Time Window: All hours
- Sender Details: From Name = {{location.name}}

POST-BUILD VERIFICATION CHECKLIST:
1. Workflow name matches: "Lead Scoring and Routing"
2. Trigger is Form Submitted with "Discovery Form" filter
3. Tags ZHC-hot-lead, ZHC-warm-lead, ZHC-cold-lead exist
4. Custom fields ZHC_budget_range and ZHC_timeline_days exist
5. Action sequence: Update Field --> Update Field --> If/Else --> branches
6. Main If/Else evaluates budget > $5000 AND timeline < 30
7. Nested If/Else evaluates budget > $1000
8. Hot branch adds ZHC-hot-lead + sends notification + assigns to sales-manager
9. Warm branch adds ZHC-warm-lead + adds to "Nurture Sequence"
10. Cold branch adds ZHC-cold-lead + adds to "Nurture Sequence"
11. Settings: re-entry = No
12. Test with a test contact before publishing
```

  7. Operator pastes into GHL Workflow AI Builder.
  8. Operator runs verification checklist.
  9. Workflow published.
  10. Event log: build_completed (verification_score: 12/12).
```

## Example 4 -- Honest gap: trigger not available on plan tier

```
Operator: "Build a workflow using the Shopify Abandoned Cart trigger."

Agent (Skill 41):
  1. Check GHL triggers catalog (references/ghl-triggers-catalog.md):
     - "Shopify Abandoned Cart (Deprecating Soon)" is listed but marked as deprecating.
  2. Check operator's plan tier via API (or ask):
     - Operator is on Starter plan; Shopify triggers require Pro plan.
  3. HONEST GAP reply:
     "The Shopify Abandoned Cart trigger is only available on the Pro plan and above,
     and it's also being deprecated. I can suggest two alternatives:
     1. Use the 'Abandoned Checkout' trigger (available on your current plan) for
        HighLevel's native store.
     2. Use an Inbound Webhook trigger and send abandoned-cart events from Shopify
        to HighLevel via a custom integration.
     Which would you prefer?"
  4. Operator chooses option 2.
  5. Continue with dependency audit and prompt generation for Inbound Webhook approach.
  6. Event log: dependency_audited (missing trigger noted), build_initiated (operator_confirmed: true).
```

## Example 5 -- Reading the event log (operator ground truth)

```bash
$ tail -3 "$MASTER_FILES_DIR/build-with-ai-events.jsonl"
{"ts":"2026-05-30T20:00:01Z","skill":"41-build-with-ai-playbook","event":"dependency_created","session_ref":"sess_a1b2","source":"api_response","object_type":"tag","object_name":"ZHC-new-lead","zhc_prefixed":true}
{"ts":"2026-05-30T20:00:02Z","skill":"41-build-with-ai-playbook","event":"prompt_generated","session_ref":"sess_a1b2","source":"ghl_catalog","prompt_section_count":8,"sections_present":["workflow_name","trigger","dependencies","actions","conditions","webhook","settings","verification"]}
{"ts":"2026-05-30T20:05:00Z","skill":"41-build-with-ai-playbook","event":"build_completed","session_ref":"sess_a1b2","source":"operator","workflow_name":"New Lead Welcome Sequence","verification_score":10}
```

The log records object names and counts, never raw contact data or full URLs with tokens.
