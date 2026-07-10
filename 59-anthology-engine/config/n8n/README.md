# Anthology Drive Broker (n8n) — the Google credential broker for the fleet

`anthology-drive-broker.workflow.json` is the n8n workflow that acts as the Google
Drive **credential broker** for the Anthology engine. Trevor's Google service-account
credential lives **only** inside n8n. A client box holds **no** Google key — only the
broker webhook URL plus a low-privilege shared token. The privileged folder-tree
creation and share happen inside n8n, so a compromised client box cannot leak Google
creds because they were never there.

## Import (manual — required)

The n8n management API key configured for the MCP could **not** authenticate at build
time (`AUTHENTICATION_ERROR` on every write), so the workflow was **validated offline**
but **not** created on the instance. Import it by hand:

1. n8n → **Workflows → Import from File** → select
   `59-anthology-engine/config/n8n/anthology-drive-broker.workflow.json`.
2. The webhook path is `anthology-drive`, so the production URL is
   `https://main.blackceoautomations.com/webhook/anthology-drive` — this is the value a
   client box stores as `N8N_DRIVE_WEBHOOK_URL`.
3. Leave the workflow **inactive** until steps 4–6 are done; nothing calls it yet.

## One-time credential + env setup (inside n8n only)

4. **Connect the Google credential (one-time).** The nine Google HTTP Request nodes
   (`List/Create Client|Producer|Book Folder`, `Share Book To Producer`) reference a
   credential of type **Google Drive OAuth2 API** named
   *"BlackCEO Anthology Drive (connect me)"* with a placeholder id. Create/select
   Trevor's Google credential on those nodes (a service-account or OAuth2 credential with
   Drive scope). This is the credential that never leaves n8n.
5. Set two n8n **environment variables** (Settings → Variables/Env, or the container env):
   - `ANTHOLOGY_DRIVE_BROKER_TOKEN` — the low-privilege shared token. It must equal the
     value a client box holds as `N8N_DRIVE_WEBHOOK_TOKEN`.
   - `ANTHOLOGY_DRIVE_ROOT_FOLDER` — the folder id of Trevor's Anthology root in his Drive
     (the tree `client_key / producer_email / book_title` is created under it).
6. **Activate** the workflow.

## Contract

`POST` JSON to the webhook. Auth header `X-Anthology-Broker-Token: <token>` (body
`token` is also accepted). Dispatch is on the body field `action`.

**Implemented — `create_book_tree`:**

```
{ "action": "create_book_tree",
  "client_key": "...", "producer_email": "...", "book_title": "...",
  "co_author": "..."   // optional; per-Doc EDIT is handled at doc time, not here
}
```

Response (200):

```
{ "ok": true, "action": "create_book_tree", "via": "n8n_broker",
  "root_folder_id": "...", "client_folder_id": "...",
  "producer_folder_id": "...", "book_folder_id": "...",
  "producer_editor_shared": true }
```

Behaviour: idempotent get-or-create of `root/client_key/producer_email/book_title`
(re-runs return the same ids), then a named-user **editor** (writer) share of the book
folder to `producer_email`. Bad/absent token → `401`; missing fields → `400`.

**Stubbed (designed extension points, not faked)** — `create_doc`, `upload_pdf`,
`share_doc_edit`, `pull_doc_text` return `501 { "error": "not_implemented" }`. Until
they are built, a client box can mint the per-book tree through the broker, but the
per-Doc operations still require the operator's own box (local service account). See
`MASTERDOC.md` floor #10.

## Skill side

`scripts/drive_adapter.py` speaks this contract: `provision_book_tree(...)` POSTs
`create_book_tree` when `broker_configured()` (both `N8N_DRIVE_WEBHOOK_URL` and
`N8N_DRIVE_WEBHOOK_TOKEN` resolve), else falls back to the local SA. CLI:
`drive_adapter.py provision-book-tree ...`, `drive_adapter.py broker-status`,
`drive-tree-provision.py create-book-tree ...`.
