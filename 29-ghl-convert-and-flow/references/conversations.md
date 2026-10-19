# GHL Conversations + Messages API Reference

> **Scope of this file:** All endpoints under the `conversations` module (conversations and messages).
> Base URL: `https://services.leadconnectorhq.com`
> Auth: `Authorization: Bearer $GOHIGHLEVEL_API_KEY` — the LOCATION PIT from `~/.openclaw/secrets/.env`. In the cURL templates below, substitute `$GOHIGHLEVEL_API_KEY` for `<PRIVATE_INTEGRATION_TOKEN>` and use double quotes so it expands. See SKILL.md "Credentials" for the fail-loud resolver.
> Version header: **required**. Its VALUE is the version documented for that specific operation — for the conversations operations frozen at `v3` per the official operation page `https://marketplace.gohighlevel.com/docs/ghl/conversations/<operation-slug>/` (GHL modernization contract ledger, 2026-10-18). This file also documents operations that the freeze does NOT record; those examples keep their older literal and carry an explicit `Version UNVERIFIED for this operation` marker. Treat the marker as the authority for that block, not this sentence. Read the operation page at `https://marketplace.gohighlevel.com/docs/ghl/conversations/<operation-slug>/` before using any other supported literal. Never send one value for every call.

---

### Module: conversations

#### POST /conversations/ - Create Conversation
> Version UNVERIFIED for this operation - read the operation page before use: https://marketplace.gohighlevel.com/docs/ghl/conversations/
- Description: Creates a new conversation with the data provided
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversations.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/conversations/
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/conversations/' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /conversations/locations/{locationId}/messages/{messageId}/transcription - Get transcription by Message ID
> Version UNVERIFIED for this operation - read the operation page before use: https://marketplace.gohighlevel.com/docs/ghl/conversations/
- Description: Get the recording transcription for a message by passing the message id
- Security: bearer, Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: Not explicitly listed
- Required headers: Version
- Required path params: locationId, messageId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/conversations/locations/{locationId}/messages/{messageId}/transcription
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/conversations/locations/{locationId}/messages/{messageId}/transcription' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /conversations/locations/{locationId}/messages/{messageId}/transcription/download - Download transcription by Message ID
> Version UNVERIFIED for this operation - read the operation page before use: https://marketplace.gohighlevel.com/docs/ghl/conversations/
- Description: Download the recording transcription for a message by passing the message id
- Security: bearer, Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: Not explicitly listed
- Required headers: Version
- Required path params: locationId, messageId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/conversations/locations/{locationId}/messages/{messageId}/transcription/download
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/conversations/locations/{locationId}/messages/{messageId}/transcription/download' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /conversations/messages - Send a new message
- Description: Post the necessary fields for the API to send a new message.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversations/message.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/conversations/messages
  - Headers: Authorization + Version (v3)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/conversations/messages' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: v3' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /conversations/messages/email/{emailMessageId}/schedule - Cancel a scheduled email message.
> Version UNVERIFIED for this operation - read the operation page before use: https://marketplace.gohighlevel.com/docs/ghl/conversations/
- Description: Post the messageId for the API to delete a scheduled email message. <br />
- Security: Not specified
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: Not explicitly listed
- Required headers: Authorization (plus optional Version if endpoint requires it)
- Required path params: emailMessageId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/conversations/messages/email/{emailMessageId}/schedule
  - Headers: Authorization + Version as needed
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/conversations/messages/email/{emailMessageId}/schedule' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /conversations/messages/email/{id} - Get email by Id
- Description: Get email by Id
- Security: Not specified
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: Not explicitly listed
- Required headers: Authorization (plus optional Version if endpoint requires it)
- Required path params: None
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/conversations/messages/email/{id}
  - Headers: Authorization + Version (v3)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/conversations/messages/email/{id}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: v3' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /conversations/messages/inbound - Add an inbound message
> Version UNVERIFIED for this operation - read the operation page before use: https://marketplace.gohighlevel.com/docs/ghl/conversations/
- Description: Post the necessary fields for the API to add a new inbound message. <br />
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversations/message.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/conversations/messages/inbound
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/conversations/messages/inbound' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /conversations/messages/outbound - Add an external outbound call
> Version UNVERIFIED for this operation - read the operation page before use: https://marketplace.gohighlevel.com/docs/ghl/conversations/
- Description: Post the necessary fields for the API to add a new outbound call.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversations/message.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/conversations/messages/outbound
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/conversations/messages/outbound' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /conversations/messages/upload - Upload file attachments
> Version UNVERIFIED for this operation - read the operation page before use: https://marketplace.gohighlevel.com/docs/ghl/conversations/
- Description: Post the necessary fields for the API to upload files. The files need to be a buffer with the key "fileAttachment". <br /><br /> The allowed file types are: <br/> <ul><li>JPG</li><li>JPEG</li><li>PNG</li><li>MP4</li><li>MPEG</li><li>ZIP</li><li>RAR</li><li>PDF</li><li>DOC</li><li>DOCX</li><li>TXT</li><li>MP3</li><li>WAV</li></ul> <br /><br /> The A
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversations/message.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/conversations/messages/upload
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/conversations/messages/upload' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /conversations/messages/{id} - Get message by message id
> Version UNVERIFIED for this operation - read the operation page before use: https://marketplace.gohighlevel.com/docs/ghl/conversations/
- Description: Get message by message id.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversations/message.readonly
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/conversations/messages/{id}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/conversations/messages/{id}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /conversations/messages/{messageId}/locations/{locationId}/recording - Get Recording by Message ID
> Version UNVERIFIED for this operation - read the operation page before use: https://marketplace.gohighlevel.com/docs/ghl/conversations/
- Description: Get the recording for a message by passing the message id
- Security: bearer, Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: Not explicitly listed
- Required headers: Version
- Required path params: locationId, messageId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/conversations/messages/{messageId}/locations/{locationId}/recording
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/conversations/messages/{messageId}/locations/{locationId}/recording' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /conversations/messages/{messageId}/schedule - Cancel a scheduled message.
> Version UNVERIFIED for this operation - read the operation page before use: https://marketplace.gohighlevel.com/docs/ghl/conversations/
- Description: Post the messageId for the API to delete a scheduled message. <br />
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversations/message.write
- Required headers: Version
- Required path params: messageId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/conversations/messages/{messageId}/schedule
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/conversations/messages/{messageId}/schedule' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /conversations/messages/{messageId}/status - Update message status
> Version UNVERIFIED for this operation - read the operation page before use: https://marketplace.gohighlevel.com/docs/ghl/conversations/
- Description: Post the necessary fields for the API to update message status.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversations/message.write
- Required headers: Version
- Required path params: messageId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/conversations/messages/{messageId}/status
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/conversations/messages/{messageId}/status' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### POST /conversations/providers/live-chat/typing - Agent/Ai-Bot is typing a message indicator for live chat
> Version UNVERIFIED for this operation - read the operation page before use: https://marketplace.gohighlevel.com/docs/ghl/conversations/
- Description: Agent/AI-Bot will call this when they are typing a message in live chat message
- Security: Location-Access
- Token type: Sub-Account (Location) Token
- Required scopes: conversations/livechat.write
- Required headers: Version
- Required path params: None
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: POST
  - URL: https://services.leadconnectorhq.com/conversations/providers/live-chat/typing
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request POST 'https://services.leadconnectorhq.com/conversations/providers/live-chat/typing' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /conversations/search - Search Conversations
- Description: Returns a list of all conversations matching the search criteria along with the sort and filter options selected.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversations.readonly
- Required headers: Version
- Required path params: None
- Required query params: locationId
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/conversations/search
  - Headers: Authorization + Version (v3)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/conversations/search' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: v3' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /conversations/{conversationId} - Get Conversation
- Description: Get the conversation details based on the conversation ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversations.readonly
- Required headers: Version
- Required path params: conversationId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/conversations/{conversationId}
  - Headers: Authorization + Version (v3)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/conversations/{conversationId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: v3' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### PUT /conversations/{conversationId} - Update Conversation
> Version UNVERIFIED for this operation - read the operation page before use: https://marketplace.gohighlevel.com/docs/ghl/conversations/
- Description: Update the conversation details based on the conversation ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversations.write
- Required headers: Version
- Required path params: conversationId
- Required query params: None
- Required body fields: Body required but fields not explicit 
- HTTP structure:
  - Method: PUT
  - URL: https://services.leadconnectorhq.com/conversations/{conversationId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request PUT 'https://services.leadconnectorhq.com/conversations/{conversationId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json' \
  -d '{"key":"value"}'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### DELETE /conversations/{conversationId} - Delete Conversation
> Version UNVERIFIED for this operation - read the operation page before use: https://marketplace.gohighlevel.com/docs/ghl/conversations/
- Description: Delete the conversation details based on the conversation ID
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversations.write
- Required headers: Version
- Required path params: conversationId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: DELETE
  - URL: https://services.leadconnectorhq.com/conversations/{conversationId}
  - Headers: Authorization + Version (2021-04-15)
- cURL template:
```bash
curl --request DELETE 'https://services.leadconnectorhq.com/conversations/{conversationId}' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: 2021-04-15' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

#### GET /conversations/{conversationId}/messages - Get messages by conversation id
- Description: Get messages by conversation id.
- Security: bearer
- Token type: Private Integration Token or OAuth Access Token
- Required scopes: conversations/message.readonly
- Required headers: Version
- Required path params: conversationId
- Required query params: None
- Required body fields: None 
- HTTP structure:
  - Method: GET
  - URL: https://services.leadconnectorhq.com/conversations/{conversationId}/messages
  - Headers: Authorization + Version (v3)
- cURL template:
```bash
curl --request GET 'https://services.leadconnectorhq.com/conversations/{conversationId}/messages' \
  -H 'Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>' \
  -H 'Version: v3' \
  -H 'Content-Type: application/json'
```
- Common 400/401 causes:
  - Missing required path/query/body fields
  - Missing `Version` header when required
  - Invalid/expired token or wrong token type for endpoint security

