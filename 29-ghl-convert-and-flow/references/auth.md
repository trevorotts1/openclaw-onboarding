# auth.md — authentication, tenant binding and scopes

## Token classes

| Class | Used for | Notes |
|---|---|---|
| Location PIT (`pit-`) | normal public REST; media | `GOHIGHLEVEL_API_KEY`; 10 legacy aliases resolve the same value |
| Agency PIT (`pit-`) | agency-level provisioning, SaaS | 401s on media; never substitute for a location token |
| OAuth access token | marketplace/agency flows | 24h access token; 1-year refresh, rotates on use |
| Firebase refresh token | approved private/internal path | Workflow build/edit/readback; not a public API token |
| Official MCP OAuth/PIT | official MCP operations | Per discovered operation; not a bypass for a beta gate |

A token class is part of the route decision. A generic 403 is classified as token-context mismatch first, authorization second.

## Tenant binding is a row field

The registry records `tenant_binding` per operation (`path.<param>`, `token-id`, `connection scope`, `unknown`, `n/a`). Never send `locationId` indiscriminately in body/path/headers. Projects and several agency operations derive location from the token. A body-supplied company id cannot override server context.

A read on Trevor's location cannot activate a client's location. Token rotation invalidates dependent scope evidence.

## Version header

Mandatory. Value per operation from the row. Omission and invented values are 401s. Full rules: `api-generations.md`.

## Scope state (do not synthesize)

- Keep `scope_state: unverified` until evidence exists.
- Do not derive a read scope by replacing `.write` with `.readonly`.
- The API families use distinct permissions: workflow logs (`workflows.logs`), workflow publish (`workflows.publish` on the beta row), voice agents (`voice-ai-agents.*`), voice goals (`voice-ai-agent-goals.*`), voice dashboard (`voice-ai-dashboard.readonly`), conversation AI (`conversation-ai.*`), Studio (`agent-studio.*`), KB (`knowledge-bases.write` on create), widgets (`chat-widget.*`), Projects (`projects/*`), Social Planner (`socialplanner/*`).
- `pipelines.create` is a user-permission response value, not an OAuth scope on a PIT.
- A scope name containing `oauth` (e.g. `socialplanner/oauth.readonly`) does not by itself forbid a PIT.

## Capability record

Separate: `documented`, `adapter_built`, `offline_tests_passed`, `availability`, `scope_state`, `read_probe`, `write_canary`, `enabled`, `checked_at`, `expires_at`, `fallback_policy`. A `true` in one dimension never implies another.

Canary mode is bounded and explicit. Normal dispatch stays disabled until the canary/readback succeeds; never enable all writes to solve a deadlock.

## Failure classes

| Observation | Meaning | Action |
|---|---|---|
| 401 | missing/invalid token or expired credential | resolver/refresh path; never dump secrets |
| 403 generic | scope, role or wrong tenant | classify; repair or block; never switch tenant |
| 403 beta | explicit beta denial | `beta_not_enabled`; approved fallback; separate access request |
| 404 | missing object vs route vs tenant vs unsupported | distinguish before any create |
| 429 | shared per-location bucket | stop; surface reset; never tier-hop |

## Credential recovery

Use the existing bounded resolver/refresh path. Do not create a second credential system. Firebase-token recovery: token unread/misconfigured → managed Tier-4; token genuinely dead → authorized Tier-2 self-heal. Tier 4 cannot seed a session without a token.

## Historical scope notes (labelled)

Earlier scope inventories were assembled from three disjoint sources and a true union. That work is historical evidence. The registry row is the current authority; a scope not on the row stays `UNKNOWN` rather than being filled from an old list.
