# Session storage contract (Skill 78)

Two stores implement one contract. The semantics (opaque ref, TTL,
resume-with-revalidation, reconfirm-on-material-change, idempotent
confirm, tenant isolation, expiry that never defaults a package) live in
`scripts/selection_session.py` and are inherited unchanged by both.

## In-memory core: `selection_session.SessionStore`

Deterministic, process-local. Used by tests, previews, and any runtime
that supplies its own persistence around the core semantics.

## Production store: `selection_session_store.DurableSessionStore`

SQLite (stdlib), one database per tenant:

- Layout: `<base_dir>/<tenant>/selection-sessions.sqlite3` (mode 0600),
  plus `<base_dir>/index.sqlite3` mapping an opaque ref to its tenant.
  The index holds no selection content; it exists so a lookup opens only
  the owning tenant's file. Tenant isolation is enforced by file scoping
  AND by the core's tenant/launch check on every resume and confirm.
- Records: ref, selection JSON (the validated selection.json intent),
  tenant_id, launch_id, created_at, expires_at. Draft references persist
  in the same database, so a double confirm across processes or restarts
  returns the one existing draft reference.
- Fail closed on read: a missing file, corrupt database, or malformed
  row resolves to the core's `expired` state with the helpful restart
  message. A stored selection is never returned from a damaged store.
- Fail loud on write: if a record cannot be persisted, `create` raises
  `StorageError` (code `S78-SESSION-STORAGE`). There is no silent
  fallback to memory: a session that would vanish at restart must not be
  created.
- The store choice is made by the host at construction (see
  `references/runtime-adapter-contract.md`), never by request data.
- Record and index are written in two commits (tenant database first,
  then the ref index). A crash between them can leave a record row no
  ref can reach; every read still fails closed, so the orphan is inert
  data, never a reachable or cross-tenant selection. (Noted by
  independent review S78-10 as informational.)

What is never stored: contact identity, card data, query-string values,
or any price authority beyond the approved catalog snapshot already
inside the validated selection intent.
