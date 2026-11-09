---
name: ghl-convert-and-flow
description: Domain-specific, source-indexed reference files for the GoHighLevel / Convert and Flow public REST and hybrid surfaces. Tier 3 in the access chain, used after the Convert and Flow CLI (Skill 44) and the official MCP (Skill 36) where those cover the operation. Every current claim is derived from the executable operation registry; this skill documents, and cannot enable, an operation.
---

> **GHL PIT aliases:** `GOHIGHLEVEL_API_KEY` is the preferred name; 10 additional aliases resolve the same LOCATION PIT. See **`TERMINOLOGY.md`** (repo root) for the canonical alias set.

# GHL API Skill — GoHighLevel / Convert and Flow

> **What changed in revision 3.0.** This skill no longer carries a frozen endpoint count or a blanket "workflows are read-only / courses are browser-only" doctrine. It is a **registry-derived** index: the executable registry is the implementation authority, this skill explains it, and gaps are labelled instead of guessed.

## Read this first

1. **`references/ghl-hybrid-capability-index.json`** — one machine-readable record per registry operation: method, path, version, documented level, route class, tenant binding, write/approval flags, scopes, source URL + fetch date, blocker, readback plan, registry-row hash, and a classification (`implemented`, `documented-unimplemented`, `internal-only`, `browser-backed`, `beta-gated`, `unresolved`, `retired`, `excluded`).
2. **`references/ghl-contract-sources.json`** — the source register with an explicit fetch state. No page was refetched in this lane; inherited evidence is labelled inherited.
3. Then the one domain reference for the task. Do not dump this skill into a core file.

The index is **derived**. A missing registration cannot be hidden by adding a standalone demo client, and reading a reference cannot enable an operation. Enablement lives in the capability gate per `(operation_id, tenant)`.

## Tier in the access chain

This skill is **Tier 3** — direct public REST and documented hybrid seams. Prefer, in order:

1. **Tier 0** — the Convert and Flow CLI (Skill 44) for every operation it covers.
2. **Official MCP** — only for an authenticated, discovered, exact operation (Skill 36). The community GHL MCP is retired and is not a route.
3. **This skill's public references** — when the operation is registered here and no higher tier covers it.
4. **The approved private/Firebase path** — only for a documented public feature gap, through Skill 44's controls.
5. **Skill 6's managed browser** — for actual UI-only authoring/verification gaps, with captured selectors.

Never attempt every transport for one request. Select the cheapest proven route from current capability evidence. Never issue the same mutation twice on two rails.

## Version rule (still binding)

There are **five concurrently supported versions**: `v3`, `2023-02-21`, `2021-07-28`, `2021-04-15`, `legacy` — all "Supported until: TBD". The value is declared **per operation**. Send the row's `version`; `version_alternates` records a documented alternate. Never add `/v3` to every URL, never run a global version substitution, never omit the header (401).

`v4` appears only as a **staging** contract on beta-gated workflow-definition rows. It is not a sixth supported production version and must not be added to the supported set.

A historical live-probe finding (2026-08-03) showed established v2 paths returning 200 under several version strings. That is **historical evidence**, not a licence to ignore the row's version: renamed/generation-gated paths hard-404 under the wrong literal.

## Base URL and credentials

| Item | Value |
|---|---|
| Base URL | `https://services.leadconnectorhq.com` |
| Auth | `Authorization: Bearer $GOHIGHLEVEL_API_KEY` (location PIT, `pit-`) |
| Location | `GOHIGHLEVEL_LOCATION_ID` |
| Version | Per operation, from the registry row |
| Content-Type | `application/json` or documented multipart; never guessed |

Fail-loud resolver (never fire an empty Bearer):

```bash
[ -f ~/.openclaw/secrets/.env ] && { set -a; . ~/.openclaw/secrets/.env; set +a; }
: "${GOHIGHLEVEL_API_KEY:=${GHL_API_KEY:-${GHL_PIT:-${GHL_TOKEN:-${GHL_PRIVATE_INTEGRATION_TOKEN:-${PRIVATE_INTEGRATION_TOKEN:-${GHL_PRIVATE_TOKEN:-${PIT_TOKEN:-${GHL_PIT_TOKEN:-${GOHIGHLEVEL_LOCATION_PIT:-${GHL_LOCATION_PIT:-}}}}}}}}}}}}"
: "${GOHIGHLEVEL_LOCATION_ID:=${GHL_LOCATION_ID:-}}"
[ -n "$GOHIGHLEVEL_API_KEY" ] && [ -n "$GOHIGHLEVEL_LOCATION_ID" ] || { echo "BLOCKED — GHL credential(s) not resolved" >&2; return 1 2>/dev/null || exit 1; }
```

Never print a token. Agency PITs 401 on media; media needs the location PIT.

## Trigger map

| Domain | Reference |
|---|---|
| Courses, modules, lessons, offers, enrollment, lesson quiz, import | `references/courses.md` |
| Workflow read, definition beta, enrollment, publish status, folders, fallback | `references/workflows.md` |
| Community groups/channels/Learning, member administration | `references/communities.md` |
| Social Planner posts, comments, queues, member authors | `references/social-planner.md` |
| Workflow logs, statistics, runtime-verification states | `references/workflow-monitoring.md` |
| Meeting Rooms (UI-only configuration) | `references/meeting-rooms.md` |
| Native Voice AI | `references/voice-ai.md` |
| Native Conversation AI and responder ownership | `references/conversation-ai.md` |
| Agent Studio Flow Agents | `references/agent-studio.md` |
| Knowledge Bases | `references/knowledge-base.md` |
| Chat Widgets | `references/chat-widgets.md` |
| GHL Projects and the one-way Command Center projection | `references/projects.md` |
| Calendars, appointments, services, Meeting Room integration boundary | `references/calendars.md` |
| Invoices, payments, orders, subscriptions, coupons | `references/payments.md` |
| Media Library upload (location PIT, multipart) | `references/medias.md` |
| Contacts, tags, fields, values, opportunities | `references/contacts.md`, `references/opportunities.md`, `references/locations.md` |
| Conversations and messages | `references/conversations.md` |
| Which Version, generation-gated paths, v3/v4 distinction | `references/api-generations.md` |
| Agency-level: OAuth, provisioning, SaaS, snapshots | `references/agency-api.md` |
| Whole-surface orientation | `references/modules.md` |

## Source facts vs activation receipts

`documented: true` (a page exists) and `adapter_built: true` (the code exists) are not `scope_state: verified`, `availability: available`, or `write_canary: passed`. Keep account availability, authorization, implementation, read evidence, write-canary evidence, and functional readiness as independent dimensions. Trevor's owner-supplied Agency Pro fact is not evidence that every client account is Pro.

## Behavioral caveats schemas cannot capture

- Workflow definition updates are **whole-graph replacement**; stale revisions are re-read, not retried.
- Course native media needs a real `contentId`; a CDN URL is not one. Import processing is not completed course creation.
- Community publishing must carry a real member `contactId` per account; a staff id or `oauthId` is wrong.
- Projects task create accepts at most one assignee and requires a real due date; location is token-derived.
- Workflow aggregate counts are event counts, not cohort conversion.
- Meetings: no public lifecycle contract is confirmed; UI configuration and live AV proof are separate.
- The managed browser is the last resort and its selectors stay `capture-runtime`/`capture-pending` until a real capture.

## Safety rules

1. Phone-number release is TREVOR-ONLY.
2. Billing/payment actions are TREVOR-ONLY without explicit instruction.
3. Never expose credentials in logs, messages or documents.
4. No sandbox: destructive actions are irreversible. Dry-run and read back.
5. On 429, stop and surface the reset. Never tier-hop to escape quota.
6. After a write, give the operator a one-line "verify in Convert and Flow UI" pointer.

## Caller contract

Skill 29 is a library. It owns no Command Center board and no coaching persona. Callers write task/progress state. A write is reported complete only with a readback; a receipt is evidence, not a claim.

## QC

`tests/test_docs_contract.py` proves A18: every registry operation has a source record, every documented route has a real adapter or a labelled gap, the registry hash the index claims still matches, and the stale GET-only/browser-only claims are gone.
