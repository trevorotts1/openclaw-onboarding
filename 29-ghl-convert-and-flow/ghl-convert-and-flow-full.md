# Convert and Flow — Complete Operator Guide (registry-derived)

## What this skill is

Convert and Flow is Trevor's white-label GoHighLevel. This skill is the organized, source-indexed knowledge layer for its public API and hybrid seams. It exists so an agent reads one focused reference instead of a giant master file, and so every claim can be traced to the executable registry or an explicitly labelled gap.

**The one rule:** the registry (`public/operations.py`) is the implementation authority. This guide explains it. It cannot enable an operation.

## Objects in plain English

| Object | Meaning |
|---|---|
| Contact | A person/company record |
| Conversation | Message thread |
| Calendar / appointment | Availability and bookings |
| Opportunity | Deal in a pipeline |
| Payment / order / subscription | Money and entitlements |
| Course / category / lesson | Learning content (a course is not a commerce product) |
| Community group / channel | Community structure (not a calendar group) |
| Workflow definition | Automation graph (whole-graph updates) |
| Knowledge base | Trained source material for native AI |
| Widget / Meeting Room / Projects | Native customer-experience and work surfaces |

## Credentials and headers

Use the location PIT from `~/.openclaw/secrets/.env`; fail loud if unresolved. Every call carries `Authorization` and the **row's** `Version`. `Content-Type` is JSON or documented multipart — never guessed.

## Coverage, honestly

The index currently classifies 140 registry operations. Read the live counts and rows from the file rather than trusting a number copied into prose. It also carries 17 documented family routes with no registry row yet; each has an owner and a `GAP-*` label. Those are not implemented operations.

| Classification | What it means for an operator |
|---|---|
| implemented | registered route; check blocker/readback |
| beta-gated | documented staging/beta contract; not production |
| documented-unimplemented | contract may exist; no adapter row here |
| internal-only | approved private path; not public API |
| browser-backed | managed browser only |
| unresolved / retired / excluded | do not execute; report |

## Reading order for a task

1. Index row (classification, version, tenant binding, readback).
2. Family reference (DTO rules, caveats, example/failure/readback).
3. Skill 44 CLI or official MCP if either covers it.

## Family index

- Courses — `references/courses.md`
- Workflows — `references/workflows.md`
- Communities — `references/communities.md`
- Social Planner — `references/social-planner.md`
- Workflow monitoring — `references/workflow-monitoring.md`
- Meeting Rooms — `references/meeting-rooms.md`
- Voice AI — `references/voice-ai.md`
- Conversation AI — `references/conversation-ai.md`
- Agent Studio — `references/agent-studio.md`
- Knowledge Bases — `references/knowledge-base.md`
- Chat Widgets — `references/chat-widgets.md`
- Projects — `references/projects.md`
- Payments — `references/payments.md`
- Calendars — `references/calendars.md`
- Media — `references/medias.md`
- Agency — `references/agency-api.md`
- Versions — `references/api-generations.md`
- Modules — `references/modules.md`

## Behavioral caveats

- Workflow definition writes: whole-graph replacement; opaque revisions; stale → re-read.
- Course media: native `contentId` required; import is asynchronous; browser seam only for the missing ingestion step.
- Community: public coverage is posts/comments/member validation, not group creation; association is its own object.
- Social Planner: one author mapping per account; validation is per channel.
- Projects: token-derived tenant; one assignee; real due date; per-endpoint pagination.
- Monitoring: 30-day windows / 60-day retention; aggregates are not cohort conversion.
- Meetings: UI-only configuration; live AV/recording/transcript are separate proofs.
- Widgets: create allowlist is `liveChat`/`emailChat`; numeric config version; `_id`.
- Voice/Conversation/Studio/KB: native product provisioning is separate from phone assignment, responder ownership, promotion and retrieval.

## What this guide will not do

It will not paste the full implementation spec into every runtime skill, will not claim a browser-only or API-only world where the evidence says hybrid, will not present inherited source evidence as a live test, and will not report a plan as a delivery.

## Provenance

Historical audit evidence and the 2026-08-03 live probes are labelled historical. Revision 3.0 did not re-open every source or run a live canary. `ghl-contract-sources.json` records the fetch state for every cited source.
