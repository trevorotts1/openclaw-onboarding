# Supported gateway receipt authorities

Closeout verifies gateway acceptance records. It does not claim the owner opened or read a Telegram message. A captured message ID or prior bare `status: pass` is never its own proof.

The verifier supports the legacy JSON sent-message registry and the SQLite plugin-state contract inspected in installed **OpenClaw 2026.9.1**. Unsupported/missing/corrupt schemas remain capability-unavailable; the verifier never migrates or writes the gateway database and never scans other agents, plugins, namespaces or chats.

## SQLite contract and source evidence

The inspected installed source files are under the OpenClaw package's `dist/` directory:

- `extensions/telegram/openclaw.plugin.json` and `extensions/telegram/index.js`: plugin ID is exactly `telegram`.
- `sent-message-cache.legacy-state-BigwweVO.js`: sent-message namespace is `telegram.sent-messages`; scope key is the first 24 hex characters of SHA-256 of the exact UTF-8 session store path. Entry key is the first 32 hex characters of SHA-256 of `scopeKey + NUL + chatId + NUL + messageId`. This is the session store path, not the JSON registry suffix or another agent's store.
- `send-DHnAItg0.js` (`openSentMessageStore`, `readPersistedSentMessages`, `persistSentMessage`): registered values are `{scopeKey, chatId, messageId, timestamp}` with a 24-hour TTL; persisted reads require the same scope.
- `plugin-state-store-PhQA2Nhh.js` (`selectPluginStateEntry`): `plugin_state_entries` has `plugin_id`, `namespace`, `entry_key`, `value_json`, `created_at`, `expires_at`; expiry is in milliseconds and entries are readable only if expiry is null or later than the current time.

`gateway_sqlite_receipts.py` checks that exact schema, plugin, namespace, key, stored scope/chat/message, finite positive timestamps, cache age and expiry. It uses `mode=ro`, query-only mode, a 100 ms lock timeout and a 500 ms query interruption deadline. Exact indexed lookups retrieve at most two rows; an ambiguous record is rejected. No schema changes, registration writes, deletes, migrations or discovery scans occur.

## Configuration

For a standard own installation, the wrapper defaults to `<OC_ROOT>/state/openclaw.sqlite` and derives the exact session store by removing `.telegram-sent-messages.json` from that installation's registry path. Normal default scope is `<OC_ROOT>/agents/main/sessions/sessions.json`.

For a configured non-main Telegram owner agent or custom `session.store`, provide:

- `ZHC_TG_STATE_DB`: absolute path to that installation's `state/openclaw.sqlite`.
- `ZHC_TG_SESSION_STORE`: the exact absolute session store string used by the gateway, including the correct agent. Do not normalize a symlink to a different path before hashing.
- `ZHC_TG_REGISTRY`: optional corresponding legacy JSON registry path.

If `ZHC_STATE_FILE` or `ZHC_TG_REGISTRY` is overridden, SQLite access is disabled unless `ZHC_TG_STATE_DB` is explicitly supplied. Test and scratch paths therefore cannot silently read a live gateway database. An explicit SQLite DB without an explicit session store can derive the scope only from a registry path with the known suffix. No fallback to another agent's session store is allowed.

## Retained evidence

A currently observed JSON or SQLite receipt is retained in the build-state ledger, bound to the exact build, owner chat, slot, message and current artifact/message digest. SQLite receipts additionally retain exact database/store/scope/plugin/namespace/entry identity. This lets verified historical acceptance survive registry expiry without resending. Changing the build, artifact, message, chat, configured SQLite scope or database invalidates that retained proof. A missing capability with no prior exact authoritative receipt remains pending.

Regression tests use only temporary synthetic databases/files. Installed source was read to establish the contract; no live client database was opened for development or validation.
