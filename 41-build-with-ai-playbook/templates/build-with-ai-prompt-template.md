# Build With AI Prompt Template -- Skill 41

## Instructions

Copy this template and fill in each section. Every generated prompt MUST contain all 8 sections in this order. Use plain English, not JSON. Use GHL merge field syntax where appropriate.

---

## Section 1: Workflow Name

[Clear, descriptive name for the workflow. Under 60 characters.]

Example: New Lead Welcome Sequence

---

## Section 2: Trigger Specification

[Trigger type + any filters. Be specific.]

Example:
- Trigger: Contact Created
- Filters: none (all new contacts)

Example with filter:
- Trigger: Form Submitted
- Filters: Form = "Discovery Form"

Rigor: always state filters as field, operator, value, scoped to the intended audience. Use the filter
fields the chosen trigger actually exposes, use Any of / None of for tag include or exclude, and add a
re-fire guard where the trigger can fire repeatedly. See protocols/trigger-filters-protocol.md.

---

## Section 3: Dependency List

[ALL tags, custom fields, and custom values that must exist BEFORE building. List each with its purpose.]

Example:
- Tag: ZHC-new-lead (created before build)
- Tag: ZHC-welcome-sent (created before build)
- Tag: ZHC-responded (created before build)
- Custom Value: welcome_email_subject = "Welcome to <Business>!" (created before build)
- Custom Field: ZHC_lead_source (dataType: text, created before build)

---

## Section 4: Action Sequence

[Numbered steps with exact configuration. Be specific about templates, recipients, messages, wait durations.]

Example:
1. Add Tag: ZHC-new-lead
2. Send Email:
   - Template: Welcome
   - To: {{contact.email}}
   - From Name: {{location.name}}
   - Subject: {{custom_values.welcome_email_subject}}
   - Body: "Hi {{contact.first_name}}, welcome! We're excited to help you."
3. Add Tag: ZHC-welcome-sent
4. Wait: 1 day
5. If/Else: Does contact have tag ZHC-responded?
   - YES branch: Remove from workflow
   - NO branch: Send SMS
     - To: {{contact.phone}}
     - Message: "Hi {{contact.first_name}}, just checking in!"

---

## Section 5: Conditions

[If/Else logic with explicit branches. Specify the field, operator, and value for each condition. Name
each If/Else as a question, set AND/OR grouping to match intent, order branches so the first match wins,
and always give the auto-created None branch a sensible fallback. See references/ghl-conditions-reference.md.]

Example:
- If/Else Step 5: contact.tag contains ZHC-responded
  - YES branch: exit workflow
  - NO branch: send SMS follow-up

Example with nested logic:
- Main If/Else: ZHC_budget_range > $5000 AND ZHC_timeline_days < 30
  - YES: Hot lead path
  - NO: Warm/cold evaluation path
- Nested If/Else (inside NO): ZHC_budget_range > $1000
  - YES: Warm lead
  - NO: Cold lead

---

## Section 6: Webhook Configuration

[If applicable. If no webhook, write "None."]

Example:
- Mode: CUSTOM (advanced)
- Method: POST
- URL: {{custom_values.crm_webhook_url}}
- Headers:
  - Content-Type: application/json
  - Authorization: Bearer <OPERATOR_WILL_PASTE_TOKEN>
- Raw JSON Body:
  {
    "contact_id": "{{contact.id}}",
    "first_name": "{{contact.first_name}}",
    "email": "{{contact.email}}",
    "appointment_date": "{{appointment.start_time}}"
  }
- Save Response: Yes

---

## Section 7: Settings

[Workflow-level settings.]

Example:
- Allow Re-entry: No
- Stop on Response: Yes
- Time Window: All hours
- Sender Details:
  - From Name: {{location.name}}
  - From Email: {{location.email}}
  - From Number: {{location.phone}}

---

## Section 8: Post-Build Verification Checklist

[Copy-paste the 12-point checklist. The operator runs this after building.]

1. Workflow name matches the prompt
2. Trigger is correct type and filters are applied
3. All referenced tags exist and are spelled correctly
4. All referenced custom fields exist and have correct data type
5. All referenced custom values exist and have values set
6. Action sequence matches the prompt (order, configuration)
7. If/Else conditions evaluate the right fields with correct operators
8. Wait steps have correct duration
9. Webhook URL is correct and method matches the prompt
10. Webhook headers include Content-Type: application/json (for raw JSON body)
11. Settings: re-entry, stop on response, time windows are correct
12. Test the workflow with a test contact before going live

---

## Notes for the Operator

After generating this prompt:
1. Navigate to Automations > Workflows in GHL / Convert and Flow
2. Click "Build using AI" (top-right)
3. Paste this entire prompt
4. Click "Build Workflow"
5. Review the generated workflow
6. Run the verification checklist above
7. Toggle to Published and Save
