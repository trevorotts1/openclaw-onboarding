# Publisher sub-mode — twitter (X)

**Fold:** merge plan **C1** — X/Twitter parity with Skill 35 (a *regression fix*, not an extra;
lands FIRST so no client loses X in the cutover).
**Endpoint:** `POST services.leadconnectorhq.com/social-media-posting/{locationId}/posts` (client PIT) —
the **same** GHL-direct handoff as every other platform. Posts through the client's **own GHL X
channel** via **their** Private Integration Token. NEVER a direct `api.twitter.com` / `api.x.com`
send (that trips BYPASS-SCAN / `AF-SM-POST-BYPASS`).

## Enum + discovery
- `twitter` is a first-class value in the `platforms` enum (`config/client-config.schema.json`).
- P0 live connected-accounts discovery (**C2**) reconciles the config enum against the live GHL
  listing, so a just-connected X account is never silently missed and a disconnected one never
  blocks the run.

## Capabilities
- `post` — a single X post reformatted from the week's series (prompt 16), hook in the first line.
- Threads / long-form are NOT modeled here (X-native threading is a `syndicate` v0.4.0 concern, C9).

## Contract
- Reformatter output block present for `twitter` (`AF-SM-CONTRACT-SCHEMA`); the em-dash content ban
  applies unless `emDashPolicy: allow-content` is logged (R4).
- Result: the normalized `{platform:"twitter", success, totalPosts, processedAccounts, errors}`
  (`AF-SM-PUBLISH-RESULT`).

## Guardrail (Q2)
If GHL's X Social Planner channel is unavailable per the client PIT, **escalate** — do not work
around it with a direct API poster. A future direct X path would live behind `syndicate` (C9,
v0.4.0) with an explicit BYPASS-SCAN allow-list carve-out, never inline.
