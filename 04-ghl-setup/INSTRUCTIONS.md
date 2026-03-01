# GHL (GoHighLevel) Setup - How to Use It Day to Day

This document explains how to actually USE the GHL API integration after it has been set up. If you have not completed setup yet, go read INSTALL.md first.

After setup is complete, your AI agent can search contacts, send SMS and email messages, manage calendars, work with opportunities (deals), and access the media library. This guide covers all the common operations.


## The Base URL

Every GHL API request starts with this base URL:

```
https://services.leadconnectorhq.com
```

All the endpoint paths below get added to the end of this base URL.


## Required Headers for Every Request

Every single API call to GHL must include these two headers. No exceptions.

```
Authorization: Bearer YOUR_API_KEY
Version: 2021-07-28
```

If you forget the Version header, you will get confusing 400 errors. This is the most common mistake.


## Priority Scopes (Test These First)

When you first start using GHL, focus on these three areas. They are the ones you will use most often:

1. **Contacts** - searching, creating, and updating contact records
2. **Media Library** - uploading and listing media files (images, documents, etc.)
3. **Conversations** - sending SMS text messages and emails to contacts


## Common Operations

### Working with Contacts

**Search for a contact by email or name:**
```
GET /contacts/search?query=john@email.com
```

**Get a specific contact by their ID:**
```
GET /contacts/{contactId}
```
Replace {contactId} with the actual contact ID.

**Create a new contact:**
```
POST /contacts/
```
Send the contact details in the request body as JSON (name, email, phone, etc.).

**Update an existing contact:**
```
PUT /contacts/{contactId}
```
Send only the fields you want to change in the request body.


### Sending Messages

**Send an SMS text message to a contact:**
```
POST /conversations/messages
```
Request body:
```json
{
  "type": "SMS",
  "contactId": "the-contact-id-here",
  "message": "Your text message goes here"
}
```

**Send an email to a contact:**
```
POST /conversations/messages
```
Request body:
```json
{
  "type": "Email",
  "contactId": "the-contact-id-here",
  "subject": "Your email subject",
  "html": "<p>Your email body in HTML format.</p>"
}
```

Note: Both SMS and email use the same endpoint. The "type" field tells GHL which one to send.


### Working with Calendars

**Get available time slots for a calendar:**
```
GET /calendars/{calendarId}/free-slots
```

**Book an appointment:**
```
POST /calendars/events/appointments
```


### Working with Opportunities (Deals)

**List opportunities (with search):**
```
GET /opportunities/search
```

**Create a new opportunity:**
```
POST /opportunities/
```

**Update an existing opportunity:**
```
PUT /opportunities/{id}
```


### Working with Media

**List files in the media library:**
```
GET /medias/?locationId=$GHL_LOCATION_ID&limit=10
```

**Upload a file to the media library:**
This requires a multipart form upload. Your AI agent should handle the file encoding automatically.


## Important Rules

1. **Never use the native GHL node in n8n.** It is limited and often broken. Always use HTTP Request nodes for GHL API calls instead.

2. **Always include the Version header.** This cannot be stressed enough. Without it, requests will fail.

3. **Rate limits exist.** GHL allows approximately 100 requests per minute for most endpoints. If your AI is making rapid-fire requests (like importing hundreds of contacts), it needs to pace itself and not exceed this limit.

4. **Webhooks are available.** Instead of constantly checking for updates (polling), you can set up webhooks in GHL so it automatically notifies your system when something happens (new contact created, appointment booked, etc.). This is more efficient and faster.

5. **Always check both credential locations.** Your AI should check ~/clawd/secrets/.env AND ~/.openclaw/openclaw.json for GHL credentials, because different setups store them in different places.


## Troubleshooting Common Issues

### Getting 400 errors
The most likely cause is a missing Version header. Make sure every request includes:
```
Version: 2021-07-28
```

### Getting 401 (Unauthorized) errors
Your API key may be expired or incorrect. Go back to GHL Settings and verify the key is still active.

### Getting 404 (Not Found) errors
Double-check the endpoint path. Make sure you are using the correct URL format. Also verify that the contact ID, calendar ID, or other resource ID you are referencing actually exists.

### Requests timing out
GHL's servers can sometimes be slow. Set your timeout to at least 30 seconds. If the problem persists, check GHL's status page for any outages.

### SMS not sending
Make sure the contact has a valid phone number. Also verify that your GHL account has SMS sending enabled and that you have sufficient credits/balance for sending.

### Email not sending
Make sure the contact has a valid email address. Check that your GHL account has email configured (SMTP settings, sending domain, etc.).


## What to Add to Your Core .md Files

After learning this, update your files following TSP rules:

**TOOLS.md** - Add the GHL API base URL, the Version header requirement, and the list of common endpoints.

**MEMORY.md** - Note that GHL credentials are configured and where they are stored.

**AGENTS.md** - Add the rule to always include the Version header in every GHL request.
