# GHL (GoHighLevel) Setup - Real Examples

This document shows real examples of using the GHL API through your AI agent. Each example includes the exact command, what you should expect to see, and what to do if something goes wrong.


## Example 1: Search for a Contact and Send Them an SMS

This is the most common workflow - find someone in your contacts, then send them a message.

**Step 1 - Search for the contact:**

```bash
curl -X GET "https://services.leadconnectorhq.com/contacts/search?query=john@email.com" \
  -H "Authorization: Bearer $GHL_API_KEY" \
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
  -H "Authorization: Bearer $GHL_API_KEY" \
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
- If you get a 401 error: Your API key may be expired. Check GHL Settings.
- If the SMS does not arrive: Make sure the contact has a valid phone number and your GHL account has SMS credits


## Example 2: Send an Email to a Contact

```bash
curl -X POST "https://services.leadconnectorhq.com/conversations/messages" \
  -H "Authorization: Bearer $GHL_API_KEY" \
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
echo "API Key: $(echo $GHL_API_KEY | head -c 10)..."
echo "Location ID: $GHL_LOCATION_ID"
```

Expected output: You should see the first 10 characters of your API key and your full Location ID. If either is blank, your credentials are not loaded. Go back to INSTALL.md Step 2.

**Test 2 - Test API connection:**
```bash
curl -s -X GET "https://services.leadconnectorhq.com/locations/$GHL_LOCATION_ID" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28"
```

Expected output: A JSON object with your location name, address, phone number, and other business details. If you see an error message instead, your API key or Location ID is incorrect.

**Test 3 - Test contact search:**
```bash
curl -s -X GET "https://services.leadconnectorhq.com/contacts/?locationId=$GHL_LOCATION_ID&limit=1" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28"
```

Expected output: A JSON object with a "contacts" array. The array might be empty if you have no contacts yet, but you should still get a valid JSON response (not an error).

**Test 4 - Test media library:**
```bash
curl -s -X GET "https://services.leadconnectorhq.com/medias/?locationId=$GHL_LOCATION_ID&limit=1" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28"
```

Expected output: A JSON object with a media files list. This proves your media library permissions are working.


## Example 4: Create a New Contact

```bash
curl -X POST "https://services.leadconnectorhq.com/contacts/" \
  -H "Authorization: Bearer $GHL_API_KEY" \
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
  -H "Authorization: Bearer $GHL_API_KEY" \
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
curl -X GET "https://services.leadconnectorhq.com/contacts/?locationId=$GHL_LOCATION_ID&limit=1" \
  -H "Authorization: Bearer $GHL_API_KEY"
```

**What you will see:** A 400 Bad Request error. The error message may be confusing and not clearly tell you that the Version header is missing.

**Correct (with Version header):**
```bash
curl -X GET "https://services.leadconnectorhq.com/contacts/?locationId=$GHL_LOCATION_ID&limit=1" \
  -H "Authorization: Bearer $GHL_API_KEY" \
  -H "Version: 2021-07-28"
```

**What you will see:** A proper JSON response with your contacts list.

The lesson: ALWAYS include the Version header. Every time. No exceptions.


## Example 7: How the AI Agent Should Handle a User Request

Here is how a conversation between a user and an AI agent with GHL access should look:

**User:** "Send a text to LeAnne Dolce saying the meeting is rescheduled to 3pm."

**AI Agent's process:**

1. Search for the contact:
```
GET /contacts/search?query=LeAnne Dolce
```

2. Find the contact ID from the response.

3. Send the SMS:
```
POST /conversations/messages
Body: {
  "type": "SMS",
  "contactId": "aoDwlb2aG4VHVWMGWcBS",
  "message": "Hi LeAnne, the meeting has been rescheduled to 3pm. Please let me know if that works for you."
}
```

4. Confirm to the user: "Done. SMS sent to LeAnne Dolce at her number on file. Message ID: msg_xyz123."

The AI agent should never ask the user for the contact's phone number or email if it is already in GHL. It should search for the contact and use the information that is already there.
