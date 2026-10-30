# council-before-dispatch — distribution and per-box provisioning

This directory is the plugin's distribution home in `trevorotts1/openclaw-onboarding`
(`extensions/<plugin-id>/`, the same convention as `extensions/ceo-routing-doctrine`
and `extensions/agent-exchange-telemetry`).

It ships the packaging, the plugin runtime (`index.js`, `index.ts`,
`lib/core.mjs`, `test/`), and the provisioning surface in one directory. File
ownership and the exact surface are recorded in `CONTRACT.md`.

Nothing here enables a plugin, edits `openclaw.json`, or touches credentials.

## Preconditions (checked, never assumed)

1. A council runtime release is **activated** on this box:
   `node <skill-root>/scripts/install-runtime.mjs --prefix <OPENCLAW_ROOT>/council-runtime`
2. The front-door shim exists: `<OPENCLAW_ROOT>/council-runtime/bin/council-ask`
3. This box's own Telegram channel, account, DM binding and agent workspace are
   configured through the supported onboarding flow.

## 1. Install the whole declared package

Install the **whole declared package**, not a hand-picked subset. The package
manifest (`package.json` `files`), this list and the built tarball are the same
twelve members:

```
<OPENCLAW_ROOT>/extensions/council-before-dispatch/
  index.js
  index.ts
  lib/core.mjs
  test/core.test.mjs
  install/plugins-entry.example.json
  fixtures/box-config.sample.json
  fixtures/binding.sample.json
  provision.mjs
  openclaw.plugin.json
  package.json
  INSTALL.md
  CONTRACT.md
```

Extract that package over the existing directory without a delete step
(`tar -xzf <tarball> --strip-components=1 -C <dir>` or an equivalent copy). Files
the box already owned and this package does not declare — operator patches,
local notes, an older `install/skill-prose-fix.patch` — are left exactly where
they are. Never install with a synchronise/`--delete` mode: the extension
directory holds box-owned edits this repository does not track.

Then make sure the plugin id is present in the box's `plugins.allow` list. That
list is the box owner's; provisioning never edits it.

## 2. Provision: derive this box's entry

```bash
node <OPENCLAW_ROOT>/extensions/council-before-dispatch/provision.mjs \
  --openclaw-root <OPENCLAW_ROOT> \
  --prefix <OPENCLAW_ROOT>/council-runtime
```

It reads **only** this box's own trusted config and prints JSON. Exit `0` means
`READY`, exit `1` means a typed `NOT_READY` with reasons, exit `2` means usage or
unreadable config.

Derivation, per field:

| field | source (trusted) |
| --- | --- |
| `accountId` | the agent's Telegram binding `match.accountId`; otherwise `--account` / binding file |
| `conversationId` | that binding's `match.peer`; exactly one DM binding, otherwise `--conversation` / binding file |
| `senderIds` | `channels.telegram.accounts.<accountId>.allowFrom` only |
| `agentId` | the agent that owns the Telegram DM binding, otherwise `--agent` |
| `agentWorkspace` | `agents.entries.<agentId>.workspace` |
| `runtimeRoot` | **not emitted.** Provision validates `<prefix>/active.json` `releasePath` and its static closure; the plugin core resolves that same record itself. An explicit `runtimeRoot` is a diagnostic override only. |
| `councilAskPath` | `<prefix>/bin/council-ask` |
| `stateDir` | `<OPENCLAW_ROOT>/council-before-dispatch` |
| `displayTimezone` | this process's resolved zone, otherwise `--timezone` |

There is no fallback that widens authorization: an empty `allowFrom` is
`NOT_READY`, never "all senders". No operator id is baked into this repository.

### Explicit per-box binding (when config cannot settle it)

If a box has several Telegram accounts, several DM bindings, or a routing config
that does not name the account, provisioning refuses rather than guessing. The
owner supplies the binding explicitly:

```json
{
  "schema": "blackceo.council-before-dispatch.binding/v1",
  "telegram": {
    "accountId": "<account id that exists on this box>",
    "conversationId": "<this box's DM chat id>",
    "senderIds": ["<subset of that account's allowFrom>"]
  },
  "agent": { "id": "<agent id on this box>", "workspace": "<must equal agents.entries.<id>.workspace>" }
}
```

```bash
node .../provision.mjs --binding /path/to/binding.json
```

The binding is validated against config, and it only ever **narrows**:

1. `channels.telegram.accounts.<accountId>.allowFrom` is read first. Empty,
   missing, or holding no exact sender id is `NO_AUTHORIZED_SENDERS` even when
   the binding names senders — a binding file cannot authorize a sender the
   account does not already authorize.
2. Every binding `senderIds` entry must be in that same account's `allowFrom`
   (a strict subset). One entry outside it is
   `BINDING_SENDER_NOT_AUTHORIZED`.
3. A wildcard `allowFrom` entry (`*`, `all`, `any`) is never expanded; it is
   `ACCOUNT_ALLOWLIST_WILDCARD` and authorization stays refused.
4. No other account's `allowFrom` is consulted, and no id is inferred across
   accounts.

An account that does not exist, a workspace that disagrees, or either sender
refusal above is a typed `NOT_READY` (`ACCOUNT_NOT_FOUND`, `BINDING_CONFLICT`).
The binding file is never merged silently.

## 3. Merge the printed entry (owner action)

Take `entry` from the `READY` output and place it at
`plugins.entries["council-before-dispatch"]` in `openclaw.json`. Keep every
pre-existing key the box already had. `install/plugins-entry.example.json` shows
the shape with placeholders only.

Do **not** add `runtimeRoot`. The plugin follows `<prefix>/active.json`, where
`<prefix>` is the parent of `dirname(councilAskPath)`. If an existing config
already carries a `runtimeRoot`, remove it when it names a numbered skill tree:
the shipped skill tree has neither `dist/` nor `node_modules/`, and the new core
refuses an incomplete override with `COUNCIL_RUNTIME_UNRESOLVED` instead of
falling back.

### Runtime closure the plugin requires

Before any import, the core checks the resolved root for the advertised package
entry `dist/index.js`, the two plugin import points
(`dist/brief/permitted-brief.js`, `dist/contracts/index.js`),
`dist/contracts/schemas.js`, `node_modules/zod/package.json` at the exact pin in
the runtime's own `package.json`, that zod's ESM import target exists, and that
the graph reachable from those three roots is Node-ESM loadable: every relative
specifier carries a file extension, every target exists inside the release root,
and every bare specifier names a package installed under that root. The claim is
bounded to those roots; a module no root reaches is not covered.

That last check is what a presence-only preflight cannot see. A TypeScript build
configured with `moduleResolution: "Bundler"` emits relative specifiers exactly
as written, so `export * from './errors'` compiles cleanly and then fails at
`import()` because Node ESM never appends `.js`. The runtime's `src/contracts/*`
and `src/sources/*` specifiers therefore carry explicit `.js` extensions, and
both the installer and the plugin refuse a tree whose graph still has an
extensionless relative. The skill tree is never a valid root.

That is also why the root must already resolve `zod` at capture time: OpenClaw's
package capture copies only what resolves from the original importer path, and a
computed absolute import URL is not rewritten by it at all.

Neither the `.skill` archive nor this plugin tarball vendors `zod`. The installer
runs `npm ci` in the staged runtime, which fetches the locked, integrity-pinned
dependency from the registry recorded in `package-lock.json`; installation
therefore requires network access. The preflight and the dependency receipt prove
the installed files are present and statically consistent — they are not runtime
resolution proof.

## Readiness semantics

`status: READY` means: this box's stated config is internally consistent, the
authorized sender set is non-empty and came from the account's own allowlist, and
the activated release contains its runtime closure files.

It does **not** mean a Council ask works. `claims.runtimeClosure` is
`"static_metadata_only"` and `claims.runtimeResolutionProven` is always `false`:
nothing is imported, resolved or executed by provisioning or by the installer's
dependency receipt. Only a real ask, sent by the owner, proves the path.

`NOT_READY` codes: `OPENCLAW_CONFIG_UNREADABLE`, `TELEGRAM_CHANNEL_ABSENT`,
`TELEGRAM_CHANNEL_DISABLED`, `NO_TELEGRAM_DM_BINDING`, `AMBIGUOUS_AGENT`,
`AGENT_NOT_FOUND`, `AGENT_WORKSPACE_MISSING`, `NO_DM_BINDING`,
`AMBIGUOUS_CONVERSATION`, `AMBIGUOUS_ACCOUNT`, `ACCOUNT_NOT_FOUND`,
`ACCOUNT_DISABLED`, `ACCOUNT_ALLOWLIST_WILDCARD`, `NO_AUTHORIZED_SENDERS`, `BINDING_UNREADABLE`,
`BINDING_SCHEMA_MISMATCH`, `BINDING_CONFLICT`, `BINDING_SENDER_NOT_AUTHORIZED`,
`RUNTIME_NOT_ACTIVATED`, `RUNTIME_ACTIVE_NO_RELEASE_PATH`,
`RUNTIME_ACTIVE_UNREADABLE`, `RUNTIME_RELEASE_MISSING`,
`RUNTIME_ROOT_IS_SOURCE_SKILL`, `RUNTIME_ENTRY_MISSING`,
`RUNTIME_CONTRACTS_MISSING`, `RUNTIME_DEPENDENCY_MISSING`,
`RUNTIME_IMPORT_UNRESOLVED`, `RUNTIME_LOCK_MISSING`, `COUNCIL_ASK_MISSING`.

## Why `runtimeRoot` is never the skill tree

The skill tree's `runtime/` is gitignored (`node_modules/`, `dist/`), is rewritten
by `update-skills.sh`, and — as shipped — contains no build at all. Provisioning
refuses a `runtimeRoot` inside a numbered skill directory
(`RUNTIME_ROOT_IS_SOURCE_SKILL`) and always prefers `<prefix>/active.json`
`releasePath`, which is the dependency-complete, atomically rolled-back release.

## Never

- No hardcoded chat id, account id, Telegram user id, or agent id.
- No all-sender capture; `allowFrom` is the only sender source.
- No write to `openclaw.json`, no plugin enable, no credential, provider, model or
  auth-boundary change.
- No claim that a box is "rolled out" because provisioning printed `READY`.
