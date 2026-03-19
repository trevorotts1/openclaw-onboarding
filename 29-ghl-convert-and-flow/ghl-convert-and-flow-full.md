# Convert and Flow API v2 - Complete Reference Guide

## What This Skill Is

Convert and Flow is Trevor's white-labeled version of GoHighLevel, often shortened to GHL. It is an all-in-one business platform that combines customer relationship management, marketing automation, sales pipelines, messaging, calendars, payments, and team management in one system.

If you are new to this world, the easiest way to think about it is this:

1. **Contacts** hold information about people and companies.
2. **Conversations** hold text messages, emails, and message history.
3. **Calendars** handle appointments and availability.
4. **Opportunities** track deals moving through a pipeline.
5. **Payments** handle invoices, subscriptions, orders, and transactions.
6. **Campaigns and automations** move people through follow-up sequences.
7. **Locations** represent sub-accounts or client accounts.
8. **Users and permissions** control who on the team can do what.

This skill is the organized, practical reference for working with the Convert and Flow API v2 inside OpenClaw. It exists so you do **not** have to load the massive master reference every time you need one endpoint.

## The Most Important Rule

The full 430K master reference lives here:

`~/Downloads/openclaw-master-files/Convert and Flow - GoHighLevel API v2 Master Reference.md`

**Rule: NEVER paste the master reference into context.**

Instead, this skill breaks the API into smaller reference files inside the `references/` folder. When you need something, read only the matching file for that domain. This keeps context smaller, cleaner, faster, and safer.

## Base URL and Authentication

### API v2 Base URL

Every Convert and Flow API v2 request begins with this base URL:

```text
https://services.leadconnectorhq.com
```

### Authentication Method

The standard authentication method for this skill is a **Bearer token** using a **Private Integration Token**.

**Header format:**

```http
Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>
```

In practice, this token is usually stored in the environment as `GHL_API_KEY`.

### Required Version Header

Most v2 endpoints also require a version header. In the reference files, you will usually see:

```http
Version: 2021-04-15
```

Some older notes in the broader workspace may mention a different version date. For endpoint execution, always trust the skill's domain reference file for the exact header requirement.

### Content-Type Header

For JSON requests, also include:

```http
Content-Type: application/json
```

### Standard Header Set

A typical request looks like this:

```http
Authorization: Bearer <GHL_API_KEY>
Version: 2021-04-15
Content-Type: application/json
```

## Environment Setup

### Where the Token Lives

For this skill, the environment variable to use is:

```bash
GHL_API_KEY
```

Store it in your local environment file:

```bash
~/clawd/secrets/.env
```

### Example .env Entry

```bash
GHL_API_KEY=pit-xxxxxxxxxxxxxxxxxxxxxxxx
```

Do not paste real secrets into chat, docs, tickets, or screenshots.

### Loading the Token in Shell

If you are working in a shell session and need to load the value:

```bash
set -a
source ~/clawd/secrets/.env
set +a
```

### Verifying the Variable Exists

You can confirm the variable is loaded without printing the whole key:

```bash
python3 - <<'PY'
import os
key = os.getenv('GHL_API_KEY', '')
print('loaded' if key else 'missing')
print(f'length={len(key)}')
PY
```

This is safer than echoing the full value.

## Why This Skill Exists

The Convert and Flow API is powerful, but it is large. The master documentation is too big to keep loading into context for ordinary work. That creates several problems:

1. It wastes tokens.
2. It makes the agent slower.
3. It increases the chance of using the wrong endpoint.
4. It tempts people to guess instead of reading the correct reference file.

This skill fixes that by organizing the API into practical, domain-specific reference files.

## How to Use This Skill Correctly

When a request comes in, follow this workflow:

### Step 1: Identify the business domain

Ask yourself: what is the user actually trying to do?

- Create or find a person -> contacts
- Send a text message -> conversations
- Book an appointment -> calendars
- Update a deal -> opportunities
- Create an invoice -> payments
- Manage a user -> users
- Configure a webhook -> webhooks

### Step 2: Open only the matching reference file

Do not open every file. Read only the file for the domain you need.

### Step 3: Find the exact endpoint and requirements

Check:

1. Method: GET, POST, PUT, PATCH, DELETE
2. Path
3. Required headers
4. Required query parameters
5. Required scopes
6. Required body fields

### Step 4: Build the request carefully

Use the cURL template or endpoint pattern from the reference file. Do not invent parameters.

### Step 5: Execute safely

For anything destructive or financially sensitive, confirm first.

## Reference File Index

This skill includes 12 domain reference files. Think of this section as your map.

---

## 1. `auth.md`

### What it covers

This file explains authentication and token management.

### Main topics inside

- Private Integration Tokens
- OAuth access tokens
- Deprecated API keys
- Version header rules
- Permission scopes
- Scope troubleshooting

### Use this file when

- You need to understand how auth works
- A request is failing with 401 or 403
- You need to confirm required scopes
- You are setting up a new integration
- You are deciding between Private Integration Token and OAuth

### Plain-English summary

If something says "unauthorized" or "forbidden," read `auth.md` first. Most Convert and Flow API problems come from missing scopes, wrong token types, or missing version headers.

---

## 2. `contacts.md`

### What it covers

This file is the contact management reference.

### Main topics inside

- Contact create, read, update, delete
- Contact search
- Bulk operations
- Tags
- Notes
- Tasks
- DND status
- Workflows tied to contacts
- Business associations

### Use this file when

- You need to create a contact
- You need to search by name, email, or phone
- You need to add or remove tags
- You need to add notes to a contact
- You need to create or update a task
- You need to mark a person Do Not Disturb

### Plain-English summary

If the user is talking about a person, lead, customer, client record, tags, notes, or tasks, start with `contacts.md`.

---

## 3. `conversations.md`

### What it covers

This file handles messaging and conversation history.

### Main topics inside

- Conversation create and retrieval
- Message history
- Sending outbound messages
- Recording inbound messages
- SMS and email conversation flows
- Thread-level operations
- Transcriptions for certain message types

### Use this file when

- You need to send an SMS
- You need to read or search conversation history
- You need to respond in an existing thread
- You need to inspect message records
- You need to work with email threads inside the platform

### Plain-English summary

If the user says "text them," "send a message," "check the thread," or "see the email conversation," this is your file.

---

## 4. `calendars.md`

### What it covers

This file covers calendars, appointment booking, event records, free slots, groups, and related scheduling operations.

### Main topics inside

- List calendars
- Create calendars
- Read availability
- Get free slots
- Book appointments
- Update appointments
- Get appointment notes
- Read event lists
- Manage blocked times and scheduling structures

### Use this file when

- You need to book an appointment
- You need to find open times
- You need to read calendar events
- You need to update an existing appointment
- You need to manage a schedule or resource

### Plain-English summary

If it involves time, availability, bookings, or appointment records, read `calendars.md`.

---

## 5. `opportunities.md`

### What it covers

This file is for pipeline and deal management.

### Main topics inside

- Opportunity create, read, update, delete
- Pipeline stage tracking
- Search opportunities
- Deal status
- Monetary value updates
- Moving records through stages

### Use this file when

- You need to create a deal
- You need to change a pipeline stage
- You need to mark a deal won or lost
- You need to search opportunities by status or pipeline
- You need to update deal value

### Plain-English summary

If the user is talking about pipelines, deals, stages, or opportunities, this file is the right starting point.

---

## 6. `payments.md`

### What it covers

This is one of the largest and most important files. It combines invoices and payments.

### Main topics inside

- Invoices
- Invoice templates
- Estimates
- Payment schedules
- Orders
- Fulfillment
- Transactions
- Subscriptions
- Coupons
- Payment integrations
- Custom payment provider setup

### Use this file when

- You need to create an invoice
- You need to list invoices
- You need to mark something paid
- You need to inspect a transaction
- You need to create or manage a subscription
- You need to work with order data

### Plain-English summary

If money is involved, start with `payments.md`.

### Safety note

Financial actions are sensitive. Read carefully before executing. Do not guess.

---

## 7. `campaigns.md`

### What it covers

This file covers campaign-related automation and campaign management patterns.

### Main topics inside

- Campaign access
- Automation entry points
- Trigger-oriented workflows
- Connections to broader marketing functions

### Use this file when

- You need to understand campaign structures
- You need to connect contacts to campaigns
- You need to inspect automation patterns
- You need workflow-related campaign context

### Plain-English summary

If the task is about follow-up sequences, marketing flows, or campaign logic, open `campaigns.md`.

---

## 8. `locations.md`

### What it covers

This file is about sub-account or location management.

### Main topics inside

- Location lookup
- Location updates
- Search or list locations
- Custom fields
- Tags
- Custom values
- Templates
- Location-level tasks and settings

### Use this file when

- You need to work inside a specific sub-account
- You need a location ID
- You need to inspect or update location metadata
- You need custom fields or tags at the location level

### Plain-English summary

If the question is really about a client account, sub-account, or location setup, read `locations.md`.

---

## 9. `users.md`

### What it covers

This file handles user and team management.

### Main topics inside

- Team member records
- User lookup
- User create and update
- Roles
- Membership and assignment patterns
- Permission-related user operations

### Use this file when

- You need to add a user
- You need to update a team member
- You need to inspect who has access
- You need to manage role-related details

### Plain-English summary

If the task is about staff, team access, or user records, `users.md` is the correct file.

---

## 10. `phone-numbers.md`

### What it covers

This file deals with phone number management.

### Main topics inside

- Phone number lookup
- Number purchase patterns
- Number assignment and configuration
- Phone system related management steps

### Use this file when

- You need to inspect available numbers
- You need to configure phone settings
- You need to work with existing assigned numbers

### Plain-English summary

If the task is about a number itself instead of the message thread, use `phone-numbers.md`.

### Safety note

Phone number removals can be high-impact. Be careful.

---

## 11. `webhooks.md`

### What it covers

This file explains webhook setup and event subscriptions.

### Main topics inside

- Webhook setup through the UI
- Event categories
- Event payload patterns
- Real-time event subscriptions
- Endpoint expectations
- Practical webhook design notes

### Use this file when

- You need to subscribe to contact events
- You need to subscribe to message or appointment events
- You need to understand webhook payload structure
- You need to troubleshoot webhook delivery logic

### Plain-English summary

If you want Convert and Flow to notify another system when something happens, start here.

---

## 12. `modules.md`

### What it covers

This file is a broad overview of all major GHL modules.

### Main topics inside

- High-level module summaries
- Top endpoints per module
- Scope reminders
- Quick orientation across the platform

### Use this file when

- You are not sure which domain file to read first
- You want an overview of the whole API surface
- You need a quick top-endpoint map before deeper work

### Plain-English summary

When you are lost, `modules.md` helps you get un-lost.

---

## Common Workflows

This section translates real business requests into practical API thinking.

## Workflow 1: Create a Contact

### Business request

"Add this new lead to Convert and Flow."

### What you need

1. Contact details such as name, phone, or email
2. The correct endpoint from `contacts.md`
3. Auth headers

### Suggested process

1. Open `references/contacts.md`
2. Find the create contact endpoint
3. Confirm required fields
4. Build the JSON body carefully
5. Send the POST request
6. Save the returned contact ID if you will need it later

### Why it matters

Almost everything else connects to contacts. Messaging, appointments, campaigns, opportunities, and invoices all usually depend on a contact record.

## Workflow 2: Search Contacts

### Business request

"Find John Smith in the CRM."

### What you need

1. Search term such as name, email, or phone
2. Search endpoint from `contacts.md`
3. The correct location if required by the endpoint

### Suggested process

1. Open `references/contacts.md`
2. Prefer the search endpoint over deprecated list endpoints
3. Search using the most reliable identifier available
4. Review results for duplicates
5. Extract the correct contact ID for follow-up actions

### Why it matters

Search is usually the first step before sending a message, booking an appointment, adding a note, or creating an opportunity.

## Workflow 3: Send an SMS

### Business request

"Text this person a reminder."

### What you need

1. Contact or conversation context
2. Messaging endpoint from `conversations.md`
3. Correct location or thread details
4. Message body

### Suggested process

1. Find the contact or conversation first
2. Open `references/conversations.md`
3. Choose the outbound message endpoint
4. Confirm required fields such as body, channel, or conversation identifiers
5. Send the request
6. Confirm delivery record in the response if available

### Why it matters

Messaging operations are common and sensitive. The wrong thread or wrong number can create confusion fast.

## Workflow 4: Book an Appointment

### Business request

"Book them for next Tuesday at 2 PM."

### What you need

1. Contact identity
2. Calendar ID or appropriate booking context
3. Slot availability
4. Endpoint details from `calendars.md`

### Suggested process

1. Search the contact if you do not already have the contact ID
2. Open `references/calendars.md`
3. Find available slots if needed
4. Build the appointment payload
5. Create the appointment
6. Save the appointment ID for future changes

### Why it matters

Scheduling flows often fail because people skip the availability step or use the wrong calendar.

## Workflow 5: Create an Invoice

### Business request

"Send this client an invoice."

### What you need

1. Contact or account details
2. Invoice items or amount information
3. Correct invoice endpoint from `payments.md`
4. Required headers and payload format

### Suggested process

1. Open `references/payments.md`
2. Confirm whether you need invoice create, estimate create, or another billing endpoint
3. Build the body carefully
4. Send the request
5. Review the returned invoice object
6. If another endpoint is needed to send or update it, read that exact section too

### Why it matters

Invoice operations can affect real money. Slow down and verify.

## Workflow 6: Create or Update an Opportunity

### Business request

"Move this deal to proposal sent."

### What you need

1. Opportunity ID
2. Pipeline and stage context
3. Correct endpoint from `opportunities.md`

### Suggested process

1. Search the opportunity if needed
2. Open `references/opportunities.md`
3. Confirm the update endpoint and payload fields
4. Change only the intended values
5. Review the response to confirm the new stage

### Why it matters

Pipelines drive reporting. Incorrect stage changes can distort sales dashboards.

## Workflow 7: Configure a Webhook

### Business request

"Notify our system every time a new lead comes in."

### What you need

1. Public HTTPS endpoint
2. Correct event types from `webhooks.md`
3. UI access to set up the webhook in Convert and Flow

### Suggested process

1. Open `references/webhooks.md`
2. Review supported event categories
3. Choose only the events you actually need
4. Configure the webhook in the UI
5. Confirm your receiving system handles POST requests correctly
6. Log and inspect the first sample payloads

### Why it matters

Webhooks are how you build real-time automation between Convert and Flow and external systems.

## Choosing the Right Reference File Fast

If you are under time pressure, use this quick routing table:

| Request | Start Here |
|--------|------------|
| Add person, search person, tag person | `contacts.md` |
| Send text, read thread, send email in thread | `conversations.md` |
| Book appointment, get free slot, update booking | `calendars.md` |
| Move deal, search pipeline item | `opportunities.md` |
| Create invoice, inspect payment, manage subscription | `payments.md` |
| Campaign or automation-related question | `campaigns.md` |
| Need location or sub-account details | `locations.md` |
| Need team member or user record | `users.md` |
| Need number information or phone setup | `phone-numbers.md` |
| Need push events to another app | `webhooks.md` |
| Need auth or scope help | `auth.md` |
| Need a high-level API map | `modules.md` |

## Safe Working Rules

### 1. Never guess at endpoint syntax

Even if you think you remember the path, read the domain file first.

### 2. Never paste the master reference into context

The whole point of this skill is to avoid that.

### 3. Treat secrets like passwords

That includes:

- `GHL_API_KEY`
- Private Integration Tokens
- OAuth tokens
- webhook signatures if applicable in your integration design

### 4. Be careful with financial actions

Invoices, subscriptions, payment updates, and order-related changes can have real consequences.

### 5. Be careful with phone number changes

Phone number management can affect deliverability, routing, and client operations.

### 6. Respect user intent

If the user asked a question, answer first. Do not turn a question into an action without permission.

## Troubleshooting Guide

## Problem: 401 Unauthorized

### Likely causes

1. Wrong token
2. Expired OAuth token
3. Missing scope
4. Bad Authorization header format

### What to do

1. Read `auth.md`
2. Confirm you are using Bearer format
3. Confirm required scope in the endpoint file
4. Confirm the integration actually has that scope enabled

## Problem: 400 Bad Request

### Likely causes

1. Missing version header
2. Missing required query parameter
3. Invalid JSON body
4. Missing path parameter

### What to do

1. Read the endpoint section again carefully
2. Confirm header names exactly
3. Confirm query params exactly
4. Validate JSON before sending

## Problem: 403 Forbidden

### Likely causes

1. Token has access, but not to that account or location
2. Wrong token type for that endpoint
3. Agency vs location access mismatch

### What to do

1. Re-read the endpoint's token requirements
2. Confirm whether it expects location access or agency access
3. Confirm the location or account context is valid

## Problem: Wrong results or empty search

### Likely causes

1. Wrong search field
2. Wrong location context
3. Deprecated endpoint used instead of preferred search endpoint

### What to do

1. Use the search endpoint from `contacts.md` or the domain file in question
2. Check whether a location ID is required
3. Try searching by a more unique value like phone or email

## Example Request Patterns

These are general patterns, not substitutes for reading the domain file.

### Generic GET pattern

```bash
curl --request GET 'https://services.leadconnectorhq.com/example-path' \
  -H 'Authorization: Bearer '$GHL_API_KEY \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```

### Generic POST pattern

```bash
curl --request POST 'https://services.leadconnectorhq.com/example-path' \
  -H 'Authorization: Bearer '$GHL_API_KEY \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```

Again, read the exact domain file before using a real endpoint.

## Integration with OpenClaw

This skill fits OpenClaw very naturally because OpenClaw is already built around reading the smallest correct source file before acting.

### How OpenClaw should use this skill

1. Detect the user's intent
2. Map the request to the correct domain file
3. Read that reference file only
4. Build the request from documented syntax
5. Execute or answer carefully
6. Report back in plain English

### Example: OpenClaw receives "Create a contact"

OpenClaw should:

1. Read `references/contacts.md`
2. Find the create contact endpoint
3. Confirm required fields
4. Use `GHL_API_KEY`
5. Execute the request
6. Return the created contact details clearly

### Example: OpenClaw receives "Set up a webhook for new appointments"

OpenClaw should:

1. Read `references/webhooks.md`
2. Review the appointment event types
3. Explain setup steps or proceed if explicitly asked and possible
4. Keep the explanation tied to real documented events

### Why this approach is better

- Lower context usage
- Fewer hallucinated endpoints
- Faster troubleshooting
- Better safety for high-impact operations

## For People 60 and Older: A Simple Mental Model

If this API feels overwhelming, use this simple cheat sheet:

- **Person record** = `contacts.md`
- **Message thread** = `conversations.md`
- **Appointment** = `calendars.md`
- **Deal** = `opportunities.md`
- **Money** = `payments.md`
- **Automation** = `campaigns.md`
- **Sub-account** = `locations.md`
- **Team member** = `users.md`
- **Phone number itself** = `phone-numbers.md`
- **Real-time notifications** = `webhooks.md`
- **Login and permissions** = `auth.md`
- **Big picture map** = `modules.md`

When in doubt, start with `modules.md`, then go narrower.

## Final Reminders

1. The base URL is `https://services.leadconnectorhq.com`
2. Auth uses a Bearer token, usually from `GHL_API_KEY`
3. Store the token in `~/clawd/secrets/.env`
4. Read the matching `references/*.md` file before acting
5. Never paste the 430K master reference into context
6. Slow down for billing, phone number, and destructive operations

## Conclusion

Convert and Flow is not just one tool. It is an entire operating system for customer relationships, messaging, sales, scheduling, and payments. That is why the documentation can feel huge.

This skill makes the API manageable by turning one giant reference into a practical index and a set of focused domain files. If you follow the method in this guide, the work becomes much simpler:

1. Identify the domain.
2. Read the matching file.
3. Use the documented endpoint.
4. Execute carefully.

That is the whole game.

If you keep those four steps in mind, you can work confidently in Convert and Flow without dragging the giant master reference into every task.