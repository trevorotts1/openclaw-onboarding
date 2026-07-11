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

4. **Connect the Google credential (one-time).** Every Google HTTP Request node
   (the `create_book_tree` / `create_participant_tree` list+create+share nodes and the
   per-Doc `CD*` / `UP*` / `SD*` / `PD*` nodes) references a credential of type **Google
   Drive OAuth2 API** named *"BlackCEO Anthology Drive (connect me)"* with a placeholder
   id (`REPLACE_WITH_GOOGLE_CREDENTIAL_ID`). Create/select Trevor's Google credential on
   those nodes (a service-account or OAuth2 credential with **Drive scope**; the per-Doc
   branches deliberately use Drive-scope-only endpoints — `files.create` + media update +
   `files.export` — so **no Documents scope is required**). This is the credential that
   never leaves n8n. Tip: import once, connect the credential on any one node, then use
   n8n's "apply to all nodes of this type" to fan it across the rest.
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

**Implemented — the per-participant tree + the four per-Doc actions.** These close the
E9 gap so the WHOLE S0..S8 Drive path runs on a pure client box through the broker:

- `create_participant_tree` `{ producer, anthology, participant }` → idempotent
  get-or-create of `root/producer/anthology/participant`; returns
  `{ ok, via, root_folder_id, producer_folder_id, anthology_folder_id, participant_folder_id }`.
  This is the S0 "on first sight" runtime tree.
- `create_doc` `{ parent_folder_id, name, text, share_mode? }` → creates a Google Doc in
  the folder (via `files.create` + a `uploadType=media` text/plain update — **Drive
  scope only, no Docs API**), optionally shares it (`view`→reader / `edit`→writer,
  anyone-with-link), returns `{ ok, via, doc_id, doc_url, share_mode, permission_id }`.
- `upload_pdf` `{ parent_folder_id, name, content_b64, mime, share_mode? }` → lands a
  base64-relayed binary (the S7 cover PNG or a rendered PDF), optionally shares it,
  returns `{ ok, via, file_id, drive_url, download_url, share_mode, permission_id }`.
- `share_doc_edit` `{ file_id, share_mode }` → anyone-with-link `view`/`edit` share,
  returns `{ ok, via, file_id, share_mode, permission_id, view_url }`.
- `pull_doc_text` `{ doc_id }` → exports the Doc body as `text/plain` (the
  confirm-then-pull read-back), returns `{ ok, via, doc_id, text }`.
- `capabilities` `{}` → `{ ok, via, implemented_actions: [...] }` — the set this
  workflow implements, for `broker-preflight`. A `probe:true` on any known action is a
  side-effect-free `{ ok, action, probe:true, implemented:true }` (preflight fallback).

Because the per-Doc branches use Drive-scope-only endpoints, the single **Google Drive
OAuth2 API** credential above is sufficient (no separate Documents scope needed).

## Skill side

`scripts/drive_adapter.py` speaks this contract. When `broker_configured()` (both
`N8N_DRIVE_WEBHOOK_URL` and `N8N_DRIVE_WEBHOOK_TOKEN` resolve): `provision_book_tree`
POSTs `create_book_tree`; `deliver_doc`/`deliver_media`/`do_share`/`pull_doc_text` POST
the per-Doc actions; and `drive-tree-provision.py provision` POSTs
`create_participant_tree`. Otherwise every path falls back to the local SA (operator's
own box). CLI: `drive_adapter.py broker-status`, `drive_adapter.py broker-preflight`
(HOLDs by name on a missing action), `drive-tree-provision.py create-book-tree ...`.
Offline contract tests: `tests/test_drive_broker.py`,
`tests/test_drive_broker_per_doc.py`, `tests/test_drive_broker_workflow.py`.

## Operational standing rules for the n8n deployment (learned from the July 2026 outage)

The broker runs on a **Recreate-strategy, 1-replica** `n8n-main` Kubernetes deployment
(no rolling update — every pod recreation is a brief outage). A July 2026 incident where
the broker's Code node could not read `$env.*` (root cause: n8n v2 defaults to blocking
`$env` access inside Code nodes) produced three standing rules that bind EVERY future
touch of this deployment, not just that incident. These rules outlive
`N8N-DRIVE-BROKER-FIX-SPEC.md` (retired after this port — see `AGENTS.md` for the
pointer) and are restated here in full because this file is the durable ops runbook for
the deployment they govern:

1. **Batch env changes — never one-at-a-time.** On a Recreate/1-replica deployment,
   every `kubectl set env` triggers a pod recreation, and a pod recreation is an outage.
   Setting three env vars one call at a time is three outages where one would do. Always
   combine every env var that needs to change into a SINGLE `kubectl set env` call.

2. **Digest pins only — never floating tags.** Never `image: n8nio/n8n:latest` and never
   `imagePullPolicy: Always` on this deployment. An upgrade is a deliberate, pinned digest
   change, with a database backup taken FIRST — never an implicit pull-through on the next
   pod recreation.

3. **`N8N_BLOCK_ENV_ACCESS_IN_NODE` defaults ON (true) in n8n v2.** n8n v2 blocks `$env`
   access inside Code nodes by default. Any workflow whose Code nodes read `$env.*` (this
   broker's `Authorize & Dispatch` node does) needs `N8N_BLOCK_ENV_ACCESS_IN_NODE` set to
   `false` on the deployment — and that needs testing end-to-end at go-live ("it
   activated" is not proof; a Code node that cannot read `$env.*` still activates, it just
   500s on first real call), not assumed from a successful `POST /activate`.

Rollback for this deployment NEVER touches the persistent volume or the SQLite database,
NEVER changes the image or re-adds `:latest`, and NEVER deletes the deployment — unset the
same batched env vars in one call, or deactivate ONLY the workflow
(`POST /api/v1/workflows/<id>/deactivate`) if n8n itself is healthy and only the workflow
misbehaves.
