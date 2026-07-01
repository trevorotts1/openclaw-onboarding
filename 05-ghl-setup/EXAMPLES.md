# GHL (GoHighLevel) Setup - Real Examples

This document shows real examples of using the GHL API through your AI agent. Each example includes the exact command, what you should expect to see, and what to do if something goes wrong.

> **Prefer MCP / caf first (tiering):** For day-to-day GHL operations, prefer the Official GHL MCP (skill 36, 36 tools) and the Community GHL MCP (skill 36, Tier 2), and build workflows with caf (skill 44, Tier 0). Use the raw curl examples below only when an MCP/caf tool for the operation is unavailable. The raw REST shown here is the foundation/fallback tier — it is required for credential bootstrap and connectivity proof, not for routine bulk operations.

> **Credential variable names:** Examples read the canonical `$GOHIGHLEVEL_API_KEY` (a Private Integration Token, not an API key) and `$GOHIGHLEVEL_LOCATION_ID`. The installer also writes the legacy aliases `GHL_API_KEY` / `GHL_LOCATION_ID` for back-compat, so either name resolves at runtime.


## Example 1: Search for a Contact and Send Them an SMS

This is the most common workflow - find someone in your contacts, then send them a message.

**Step 1 - Search for the contact:**

```bash
curl -X GET "https://services.leadconnectorhq.com/contacts/search?query=john@email.com" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28"
```

**What you should see:** A JSON response containing the contact's details, including their contactId, name, email, and phone number. It will look something like this:

```json
{
  "contacts": [
    {
      "id": "abc123def456",
      "firstName": "John",
      "lastName": "Smith",
      "email": "john@email.com",
      "phone": "+15551234567"
    }
  ]
}
```

**Step 2 - Send the SMS using the contact ID from Step 1:**

```bash
curl -X POST "https://services.leadconnectorhq.com/conversations/messages" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "SMS",
    "contactId": "abc123def456",
    "message": "Hello from your AI assistant!"
  }'
```

Replace "abc123def456" with the actual contact ID you received in Step 1.

**What you should see:** A JSON response with a messageId confirming the SMS was sent:

```json
{
  "messageId": "msg_789xyz",
  "status": "sent"
}
```

**What to do if it fails:**
- If you get a 400 error: Check that you included the Version header (2021-07-28)
- If you get a 401 error: The Private Integration Token (PIT) may be expired or revoked. A PIT is static — it cannot be refreshed, so you must rotate and replace it. Go to Convert and Flow Settings > Integrations > Private Integrations, revoke the old token, create a new one, and update `GOHIGHLEVEL_API_KEY` in `~/.openclaw/secrets/.env`.
- If the SMS does not arrive: Make sure the contact has a valid phone number and your GHL account has SMS credits


## Example 2: Send an Email to a Contact

```bash
curl -X POST "https://services.leadconnectorhq.com/conversations/messages" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "Email",
    "contactId": "abc123def456",
    "subject": "Test Email from AI",
    "html": "<p>This is a test email from your AI assistant.</p>"
  }'
```

**What you should see:** A JSON response with a messageId confirming the email was queued:

```json
{
  "messageId": "msg_email123",
  "status": "sent"
}
```

**What to do if it fails:**
- Make sure the contact has a valid email address
- Make sure your GHL account has email sending configured (SMTP settings, verified domain)


## Example 3: Verify Your Setup is Working (Run All Tests)

Here is a complete test sequence you can run to verify everything is connected properly:

**Test 1 - Check that credentials exist:**
```bash
echo "API Key: $(echo $GOHIGHLEVEL_API_KEY | head -c 10)..."
echo "Location ID: $GOHIGHLEVEL_LOCATION_ID"
```

Expected output: You should see the first 10 characters of your API key and your full Location ID. If either is blank, your credentials are not loaded. Go back to INSTALL.md Step 2.

**Test 2 - Test API connection:**
```bash
curl -s -X GET "https://services.leadconnectorhq.com/locations/$GOHIGHLEVEL_LOCATION_ID" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28"
```

Expected output: A JSON object with your location name, address, phone number, and other business details. If you see an error message instead, your API key or Location ID is incorrect.

**Test 3 - Test contact search:**
```bash
curl -s -X GET "https://services.leadconnectorhq.com/contacts/?locationId=$GOHIGHLEVEL_LOCATION_ID&limit=1" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28"
```

Expected output: A JSON object with a "contacts" array. The array might be empty if you have no contacts yet, but you should still get a valid JSON response (not an error).

**Test 4 - Test media library:**
```bash
curl -s -X GET "https://services.leadconnectorhq.com/medias/?locationId=$GOHIGHLEVEL_LOCATION_ID&limit=1" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28"
```

Expected output: A JSON object with a media files list. This proves your media library permissions are working.


## Example 4: Create a New Contact

```bash
curl -X POST "https://services.leadconnectorhq.com/contacts/" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28" \
  -H "Content-Type: application/json" \
  -d '{
    "firstName": "Jane",
    "lastName": "Doe",
    "email": "jane@example.com",
    "phone": "+15559876543",
    "locationId": "YOUR_LOCATION_ID"
  }'
```

Replace YOUR_LOCATION_ID with your actual Location ID.

**What you should see:** A JSON response containing the new contact's details, including their newly generated contactId:

```json
{
  "contact": {
    "id": "new_contact_id_here",
    "firstName": "Jane",
    "lastName": "Doe",
    "email": "jane@example.com",
    "phone": "+15559876543"
  }
}
```


## Example 5: Update an Existing Contact

Let us say you need to update Jane Doe's phone number:

```bash
curl -X PUT "https://services.leadconnectorhq.com/contacts/new_contact_id_here" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28" \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "+15551112222"
  }'
```

Replace "new_contact_id_here" with the actual contact ID.

**What you should see:** A JSON response showing the updated contact details with the new phone number.

**Important:** You only need to send the fields you want to change. You do not need to send the entire contact record again.


## Example 6: What Happens When You Forget the Version Header

This is the most common mistake. Here is what it looks like:

**Wrong (missing Version header):**
```bash
curl -X GET "https://services.leadconnectorhq.com/contacts/?locationId=$GOHIGHLEVEL_LOCATION_ID&limit=1" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY"
```

**What you will see:** A 400 Bad Request error. The error message may be confusing and not clearly tell you that the Version header is missing.

**Correct (with Version header):**
```bash
curl -X GET "https://services.leadconnectorhq.com/contacts/?locationId=$GOHIGHLEVEL_LOCATION_ID&limit=1" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28"
```

**What you will see:** A proper JSON response with your contacts list.

The lesson: ALWAYS include the Version header. Every time. No exceptions.


## Example 7: How the AI Agent Should Handle a User Request

Here is how a conversation between a user and an AI agent with GHL access should look:

**User:** "Send a text to Jane Smith saying the meeting is rescheduled to 3pm."

**AI Agent's process:**

1. Search for the contact:
```
GET /contacts/search?query=Jane Smith
```

2. Find the contact ID from the response.

3. Send the SMS:
```
POST /conversations/messages
Body: {
  "type": "SMS",
  "contactId": "CONTACT_ID_HERE",
  "message": "Hi Jane, the meeting has been rescheduled to 3pm. Please let me know if that works for you."
}
```

4. Confirm to the user: "Done. SMS sent to Jane Smith at her number on file. Message ID: msg_xyz123."

The AI agent should never ask the user for the contact's phone number or email if it is already in GHL. It should search for the contact and use the information that is already there.


## Example 8: Upload a File to the Media Library

Listing media is a simple GET. Uploading is a multipart/form-data POST to a different endpoint.

**Important:** Media uploads must use the **Location** Private Integration Token (`$GOHIGHLEVEL_API_KEY`), not an Agency PIT. With an Agency PIT the upload is rejected.

**Upload a local file:**

```bash
curl -X POST "https://services.leadconnectorhq.com/medias/upload-file" \
  -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
  -H "Version: 2021-07-28" \
  -F "file=@/path/to/local/image.png" \
  -F "name=image.png"
```

Notes:
- Do NOT set `Content-Type` by hand. `curl -F` sends `multipart/form-data` with the correct boundary automatically.
- Size limits: up to 25 MB for regular files, up to 500 MB for video.
- To register a file already hosted at a URL instead of uploading bytes, send `-F "hosted=true" -F "fileUrl=https://..."` in place of the `file` field.

**What you should see:** A JSON response containing the new media object's `fileId`/`id` and its hosted `url`.

**What to do if it fails:**
- 401: You are likely using an Agency PIT. Switch to the Location PIT in `$GOHIGHLEVEL_API_KEY`.
- 400: Confirm the Version header is `2021-07-28` and that you sent either `file` (upload) or `hosted=true` + `fileUrl` (link), not both.
- 413 / size error: The file exceeds the 25 MB (non-video) limit.
