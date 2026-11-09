# modules.md — surface map derived from the registry

> Authority and evidence state: `ghl-hybrid-capability-index.json` and `ghl-contract-sources.json`. This page orients; it does not carry an independent endpoint count.

## How to use this page

1. Pick the family.
2. Open its reference for DTO rules and caveats.
3. Look up the exact operation id, version and classification in the index before calling.

Do not copy endpoint counts from this page into a client document: the registry grows additively, and a stale count is a claim with no source.

## High-use families

| Family | Registry prefix | Typical rail | Reference |
|---|---|---|---|
| Contacts | `contacts.*`, `tags.*`, `custom_fields.*`, `custom_values.*` | public REST | `contacts.md` |
| Opportunities/pipelines | `opportunities.*`, `pipelines.*` | public REST | `opportunities.md` |
| Conversations | `conversations.*` | public REST (send is approval-gated) | `conversations.md` |
| Calendars/appointments | `calendars.*`, `appointments.*`, `events.*` | public REST; Meeting Room UI seam | `calendars.md`, `meeting-rooms.md` |
| Payments/commerce | `products.*`, `orders.*`, `subscriptions.*`, `coupons.*`, `transactions.*`, `invoices.*`, `estimates.*` | public REST (`v3`, rollback `2021-07-28`) | `payments.md` |
| Media | `media.*` | public REST multipart | `medias.md` |
| Social | `social.*` | public REST (spec blocker) | `social-planner.md` |
| Funnels/pages | `funnels.*` | reads public; authoring managed browser | `../06-ghl-install-pages` |
| Workflows | `workflows.*` | public read/enroll; beta v4 definition; private fallback | `workflows.md` |
| AI families | no rows yet | documented-unimplemented / browser | `voice-ai.md`, `conversation-ai.md`, `agent-studio.md`, `knowledge-base.md`, `chat-widgets.md` |
| Projects | no rows yet | beta-gated | `projects.md` |
| Monitoring | no rows yet | documented-unimplemented | `workflow-monitoring.md` |
| Agency | `locations.get`; agency docs | PIT/OAuth by operation | `agency-api.md` |

## Router classes

- `public_direct` — registered public REST.
- `official_mcp` — official MCP operation.
- `skill44_private` — approved internal/Firebase path.
- `skill06_authoring` — managed browser authoring.
- `capability_gap` — no rail recorded; report.
- `retired` / `excluded` — not a route / not in the required matrix.

## Known gaps visible on this branch

Courses (WF06), voice (WF27), conversation AI (WF28), Studio (WF29), KB (WF30), widgets (WF31), Projects (WF32), monitoring (WF25), Meeting Rooms (WF26). Gaps are labelled in the index; they are not "optional future work" for their owners, and they are not silently implemented by a doc edit.
