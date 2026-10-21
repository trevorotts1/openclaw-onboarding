# GHL capability note — launch automation families (checklist C2)

**Unit:** U-GHL-PROBE · **Date:** 2026-10-20 · **Corrected:** 2026-10-21 (tag operations — see below) · **Method:** official GoHighLevel API docs + Skill 44 code + the checked-in capability receipt only. No account calls, no live runs.

**Answer for every family in spec §3.3: Skill 44 engine.** The newest official GHL API cannot create, update, publish or trigger a workflow. Its only workflow operation is `GET /workflows/` (read), in both the v2 and v3 specs. Every automation build therefore goes through Skill 44's internal-API engine (`caf workflows create` / `CampaignBuilder`), with the managed-browser Tier-4 backstop where the engine has no verified payload.

## Why — the API ceiling

| Capability | Official API | Evidence |
|---|---|---|
| Create workflow | No | `apps/workflows.json` and `apps/v3/workflows-v3.json` each contain exactly one path: `GET /workflows/`, scope `workflows.readonly`, Version `2021-07-28` |
| Update / publish workflow | No | same specs — no POST/PUT/PATCH/DELETE |
| Create trigger / action nodes | No | no endpoint in any app spec |
| Create folders | No | not exposed publicly; Skill 44 notes neither transport lists folders |
| Create location tag | Yes (documented) | official `POST /locations/{locationId}/tags` (v3, registry row `tags.create`, status `B-NO-ADAPTER`); Skill 44's internal `POST /workflow/{loc}/tags/create` is a second, private transport — see the corrected tag section below |
| Create custom field | Yes | `POST /custom-fields/` (`apps/custom-fields.json`) |
| Add / remove contact tags | Yes (per contact) | `POST` / `DELETE /contacts/{contactId}/tags` |
| Enroll contact in an existing workflow | Yes | `POST /contacts/{contactId}/workflow/{workflowId}` — enrollment only, not authoring |
| Send SMS / email message | Yes (one-off) | `POST /conversations/messages` |
| Create calendar / appointment | Yes | `POST /calendars/`, `POST /calendars/events/appointments` |
| Create Conversation AI agent / actions | Yes | `POST /conversation-ai/agents`, `POST /conversation-ai/agents/{agentId}/actions` (Version `2021-04-15`, scope `conversation-ai.write`) |
| Read campaigns / forms | Yes (read only) | `GET /campaigns/`, `GET /forms/` — no create |
| Funnels / pages | Read + redirects only | `apps/v3/funnels-v3.json` |

### Tag operations — corrected 2026-10-21

The 2026-10-20 row said *"no tags app in the official spec listing"*. That conflated three different questions and was wrong about the first one. Location tags **are** documented; what is missing is an implemented public adapter and any tenant verification.

| Layer | `tags.create` | `tags.list` | Evidence |
|---|---|---|---|
| **1. Documented capability** (official reference, doc fetch 2026-10-18) | `POST /locations/{locationId}/tags`, Version `v3`, doc slug `locations/create-tag` | `GET /locations/{locationId}/tags`, Version `v3`, doc slug `locations/get-location-tags` | frozen registry rows in `tools/engine/cli_anything/gohighlevel/public/operations.py` (`DOC_FETCH_DATE = "2026-10-18"`) |
| **2. Implemented adapter support** | Public adapter: **none** — the row is frozen at `B-NO-ADAPTER`. Internal Skill 44 adapter: **built** — `create_location_tag()` → `POST /workflow/{loc}/tags/create`, body `{"tag": "..."}` | Public adapter: registry row exists (`A-UNVERIFIED`), tenant read not observed. Internal adapter: not implemented | `public/operations.py:337-342`; `internal/endpoints.py:52-54`; `utils/ghl_internal_client.py:219-225`; internal route asserted by `tools/engine/tests/test_adapter_probe.py:605-606` |
| **3. Actual tenant verification** | **Not verified** — no `tags.create` entry in the capability receipt, so no 200 was ever observed for the tenant | **Not verified** — same reason | `tools/engine/state/ghl-public-capabilities.json`, `recorded_at: 2026-10-19`, tenant `Mct54Bwi1KlNouGXQcDX`; its six verified reads are `locations.get`, `contacts.list`, `contacts.search`, `custom_fields.list`, `pipelines.list`, `media.files.list` — no `tags.*` row |

**What a builder may say today:** official API *documents* location-tag create/list; Skill 44 *implements* tag creation only on the internal transport; no tenant has *verified* either tag operation. Do not advertise "tags are supported by the API" as a tested capability, and do not claim the internal path is the only documented option.

Note on the 2026-10-20 wording: the raw `apps/*.json` bundles cited under Sources carry no separate `tags` app. That is a statement about the bundled specs, **not** about the official reference — the Marketplace location pages document both operations, and the frozen registry transcribes them.

## Per-family verdicts (spec §3.3)

| Family | Verdict | Trigger / engine note |
|---|---|---|
| Pre-launch | **Skill 44 engine** | Workflow + tag trigger via engine. Calendar "Wait until" dates are rejected by the API builder (duration waits only) → managed browser for the date waits. Public API can create the custom fields the calendar reads. |
| Opt-in / register / log-in | **Skill 44 engine** | `CampaignBuilder` auto-creates only a **Tag Added** trigger. Form Submitted / registration triggers need `caf workflows patch-trigger` with a trigger definition, or the Tier-4 browser. |
| Event reminders + replay / no-show | **Skill 44 engine** | Same trigger limit. Event-relative waits ("1 day / 1 hour before") are NOT a verified API payload — `references/workflow-timing.md` requires the managed browser for event timing. |
| Post-sale purchase | **Skill 44 engine** | Order Submitted / Payment received trigger is not auto-built; engine + patch-trigger/browser. Goal/exit nodes (`workflow_goal`) are in `VERIFIED_ACTIONS`. |
| Upsell / downsell branch | **Skill 44 engine** | `if_else` + `goto` are in `VERIFIED_ACTIONS`; branch templates are raw step templates through the engine. |
| Abandoned checkout | **Skill 44 engine** | Form Submitted + wait + `if_else` on purchase tag; trigger not auto-built. |
| Page-visit retargeting | **Skill 44 engine** | Page Visit trigger is not supported by `CampaignBuilder`; engine `patch-trigger` or browser. Facebook/Google audience sync happens outside GHL. |
| Onboarding + review / referral | **Skill 44 engine** | Purchase trigger + `review_request` action (in `VERIFIED_ACTIONS`); trigger not auto-built. |
| Win-back | **Skill 44 engine** | Recurring/scheduled trigger + last-open field check; scheduler triggers are not auto-built. |
| Failed payment (plans only) | **Skill 44 engine** | Payment-failed trigger + recovery steps; trigger not auto-built. |
| Conversation AI (spec §3.4, optional) | **API for the bot, engine for the wiring** | Create agent + actions with the official Conversation AI API. The Customer Replied workflow and the `conversation_ai` action node still need the Skill 44 engine (action type verified; no builder helper — raw template or browser). |

## Engine facts the WF-AUTO lanes must design around

- `CampaignBuilder` creates workflows as **draft** and writes triggers `status: "draft"` with `active` gated by `CAF_DRAFT_ONLY` (default inactive). Nothing goes live.
- Auto-created trigger is **Tag Added only** (`type: "contact_tag"`). Everything else uses `caf workflows patch-trigger --trigger-json <file>` (internal API, snapshot before write) or Tier 4.
- `VERIFIED_ACTIONS` = 56 action types, including `sms`, `email`, `wait`, `if_else`, `goto`, `workflow_goal`, `conversation_ai`, `review_request`, `webhook`, `update_custom_value`, `membership_grant_offer`.
- API builder verifies **duration waits** only. Event/calendar waits require the managed browser; do not strip the timing contract to make the API accept it.
- Engine writes go to `backend.leadconnectorhq.com` with the location's Firebase refresh token. Public-API-only (PIT) sessions can read (`GET /workflows/`) but cannot build.
- No folder listing exists on either transport, so folder de-duplication is the lane's job (`--folder-id` when unsure).

## Handover facts — these match the installed receipts

Verified 2026-10-21 by reading the files in this repo; each row is checkable at the path named.

| Fact | Value | Receipt |
|---|---|---|
| Capability receipt version | `record_version: 1` | `tools/engine/state/ghl-public-capabilities.json` |
| Receipt recorded at | `2026-10-19` | same file, `recorded_at` |
| Receipt tenant | `Mct54Bwi1KlNouGXQcDX` ("BlackCEO LLC") | same file, `tenant` |
| Receipt authority | GU-004 3.2 rules 2-3 (GHL-150 live verification amendment) | same file, `authority` |
| Tenant-verified operations | 6 reads: `locations.get`, `contacts.list`, `contacts.search`, `custom_fields.list`, `pipelines.list`, `media.files.list` | same file, `capabilities` (all `activation: VERIFIED`, `canary_verified: false`) |
| Unverified operations | every other operation, incl. `tags.create` and `tags.list`, stays `enabled=false` / `UNVERIFIED` | same file; default-deny in `public/capability.py` |
| Registry freeze date | `2026-10-18` (doc fetch), rows `tags.create` = `B-NO-ADAPTER`, `tags.list` = `A-UNVERIFIED` | `public/operations.py` |
| Verification rule | a tenant claim needs a real 200; `activation: VERIFIED` demands `read_verified`, and `canary_verified` is separate | `public/capability.py` docstring and `Capability.__post_init__` |
| Internal tag-create adapter | `POST /workflow/{loc}/tags/create`, body `{"tag": ...}` | `internal/endpoints.py:52-54`, `utils/ghl_internal_client.py:219-225` |
| Installed app bundle claim | the `apps/*.json` bundles cited below have no separate tags app — that is not a claim about the Marketplace reference | Sources section |

## Sources

- `https://github.com/GoHighLevel/highlevel-api-docs` → `apps/workflows.json`, `apps/v3/workflows-v3.json` (single `GET /workflows/`), `apps/contacts.json`, `apps/custom-fields.json`, `apps/conversations.json`, `apps/calendars.json`, `apps/campaigns.json`, `apps/forms.json`, `apps/conversation-ai.json`, `apps/v3/funnels-v3.json`.
- `44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/internal/endpoints.py` — internal base URL and workflow/trigger/tag paths.
- `44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/utils/workflow_builder.py` — `VERIFIED_ACTIONS`, `CampaignBuilder`, tag-only trigger, draft-only.
- `44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py` — `workflows create`, `create-step`, `patch-trigger`, `get/export`.
- `44-convert-and-flow-operator/INSTRUCTIONS.md` — per-operation decision rule, token-aware build path, Tier-4 backstop.
- `44-convert-and-flow-operator/references/workflow-timing.md` — event waits need the managed browser.
- `44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py` — frozen operation registry (doc fetch `2026-10-18`); `tags.create` row is `B-NO-ADAPTER`, `tags.list` is `A-UNVERIFIED`.
- `44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/capability.py` — default-deny gate; a tenant claim requires a real 200 and `canary_verified` is separate from `read_verified`.
- `44-convert-and-flow-operator/tools/engine/state/ghl-public-capabilities.json` — the installed tenant receipt (`recorded_at: 2026-10-19`, tenant `Mct54Bwi1KlNouGXQcDX`); no `tags.*` entry exists, so tag operations stay unverified.
