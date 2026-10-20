# GHL capability note — launch automation families (checklist C2)

**Unit:** U-GHL-PROBE · **Date:** 2026-10-20 · **Method:** official GoHighLevel API docs + Skill 44 code only. No account calls, no live runs.

**Answer for every family in spec §3.3: Skill 44 engine.** The newest official GHL API cannot create, update, publish or trigger a workflow. Its only workflow operation is `GET /workflows/` (read), in both the v2 and v3 specs. Every automation build therefore goes through Skill 44's internal-API engine (`caf workflows create` / `CampaignBuilder`), with the managed-browser Tier-4 backstop where the engine has no verified payload.

## Why — the API ceiling

| Capability | Official API | Evidence |
|---|---|---|
| Create workflow | No | `apps/workflows.json` and `apps/v3/workflows-v3.json` each contain exactly one path: `GET /workflows/`, scope `workflows.readonly`, Version `2021-07-28` |
| Update / publish workflow | No | same specs — no POST/PUT/PATCH/DELETE |
| Create trigger / action nodes | No | no endpoint in any app spec |
| Create folders | No | not exposed publicly; Skill 44 notes neither transport lists folders |
| Create location tag | No | no tags app in the official spec listing; Skill 44 uses internal `POST /workflow/{loc}/tags/create` |
| Create custom field | Yes | `POST /custom-fields/` (`apps/custom-fields.json`) |
| Add / remove contact tags | Yes (per contact) | `POST` / `DELETE /contacts/{contactId}/tags` |
| Enroll contact in an existing workflow | Yes | `POST /contacts/{contactId}/workflow/{workflowId}` — enrollment only, not authoring |
| Send SMS / email message | Yes (one-off) | `POST /conversations/messages` |
| Create calendar / appointment | Yes | `POST /calendars/`, `POST /calendars/events/appointments` |
| Create Conversation AI agent / actions | Yes | `POST /conversation-ai/agents`, `POST /conversation-ai/agents/{agentId}/actions` (Version `2021-04-15`, scope `conversation-ai.write`) |
| Read campaigns / forms | Yes (read only) | `GET /campaigns/`, `GET /forms/` — no create |
| Funnels / pages | Read + redirects only | `apps/v3/funnels-v3.json` |

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

## Sources

- `https://github.com/GoHighLevel/highlevel-api-docs` → `apps/workflows.json`, `apps/v3/workflows-v3.json` (single `GET /workflows/`), `apps/contacts.json`, `apps/custom-fields.json`, `apps/conversations.json`, `apps/calendars.json`, `apps/campaigns.json`, `apps/forms.json`, `apps/conversation-ai.json`, `apps/v3/funnels-v3.json`.
- `44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/internal/endpoints.py` — internal base URL and workflow/trigger/tag paths.
- `44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/utils/workflow_builder.py` — `VERIFIED_ACTIONS`, `CampaignBuilder`, tag-only trigger, draft-only.
- `44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py` — `workflows create`, `create-step`, `patch-trigger`, `get/export`.
- `44-convert-and-flow-operator/INSTRUCTIONS.md` — per-operation decision rule, token-aware build path, Tier-4 backstop.
- `44-convert-and-flow-operator/references/workflow-timing.md` — event waits need the managed browser.
