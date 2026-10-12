# ghl_sender (U17) — the GHL text/e-mail sender, version 1

ONE sender the drama-song studio uses to hand a finished video's **link** to a
client and to send the follow-up **nudges**, over the client's own GoHighLevel
(white label: Convert and Flow) conversation rail. It is not a second sender, a
proxy, an adapter or a dashboard: it reuses the canonical shape the repo already
documents (`38-conversational-ai-system/references/ghl-api-quick-reference.md`).

## Two channels, one endpoint

| Channel | GHL `type` | Required fields |
| --- | --- | --- |
| `text` | `SMS` | `contactId`, `locationId`, `message` |
| `email` | `Email` | `contactId`, `locationId`, `subject`, `html`, `emailFrom`, `emailTo` |

Both POST to `https://services.leadconnectorhq.com/conversations/messages` with
headers `Version: 2021-04-15` and `Content-Type: application/json`.

## Token-presence gating — no token means refuse, never send

The sender runs ONLY where the box has a working GHL token. `token_present()`
checks the location-token env NAMES and returns a boolean. A send with no token
REFUSES with `AF-U17-TOKEN-MISSING` before anything is built or transmitted.
Only the presence check exists: the token VALUE is never read into a variable
this module returns, stores or prints. `Authorization: Bearer <token>` is
attached by the injected transport from the runtime's own secret store, so the
secret never enters this module's request bytes, receipts or output.

## No live send, no test send

This module opens no socket. The wire call is a TRANSPORT the runtime injects
(`transport(request) -> result`), and there is NO default live transport: a send
with none injected REFUSES with `AF-U17-TRANSPORT-MISSING`. Tests inject a
recording stub, so the unit proves the request bytes are exactly the canonical
shape without transmitting anything.

## API

```python
from ghl_sender import ghl_sender as GHL

GHL.token_present(env)                     # presence only; never a value
GHL.build_request("text", contact, loc, text="your video is ready: <url>")
GHL.send("email", contact, loc, subject=..., html=..., email_from=..., email_to=...,
         purpose="link", transport=stub, env=env)   # -> ONE receipt
```

## CLI

`python3 ghl_sender.py build --channel text --contact-id C --location-id L --text "..."` prints the exact request (no send). `send` refuses: there is no live transport here (`exit 5`).

## Receipts

`build_receipt()` returns ONE receipt per message: channel, type, purpose,
contact/location, url, the request `body_sha256`, the rail's `messageId` /
`conversationId`, and `sent_at`. Never a secret, never the body verbatim.
