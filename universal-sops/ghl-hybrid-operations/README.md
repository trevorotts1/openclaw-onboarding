# GHL Hybrid Operations SOP Cluster (`universal-sops/ghl-hybrid-operations/`)

**Status:** CANONICAL for Convert and Flow / GoHighLevel / GHL operations.
**Revision:** 3.0 (2026-11-08).
**Binding machine source:** `23-ai-workforce-blueprint/skill-department-map.json`.
**Frozen consumer contract:** `universal-sops/ghl-hybrid-operations/WF16-CP01-ALIAS-AND-POINTER-CONTRACT.json`.

This is the ONE canonical GHL operating cluster. There is no `universal-sops/ghl-operations/`
second cluster: every procedure the revision-3 source guide proposed is either here (SOP-GHL-01..13)
or already exists in another canonical SOP that this README links to.

> **Fleet-wide repo.** No client names, location ids, object ids, customer content or secrets in any
> file in this cluster. Use synthetic values (`SYNTHETIC_GHL_LOCATION`) in every example.

<!-- CRAFT_INTENT_TRIGGERS_V1 -->
## Intent triggers

This craft cluster (`universal-sops/ghl-hybrid-operations/`) is the execution playbook for the skill(s) below. A specialist reaches for it when the client's plain-language request matches any of these intents — the client never has to name the skill or type its slash command. Source of truth: `23-ai-workforce-blueprint/skill-department-map.json` (Layer D).

| Skill | Reach for this craft when the client says… |
|---|---|
| **06** ghl-install-pages | "build me a form in GHL" · "build me a page in GHL" · "publish this page" · "install this funnel in GHL" · "create a course with modules and lessons" |
| **35** social-media-planner | "post my content this week" · "run my social" · "schedule posts" · "plan my social calendar" · "post this lesson announcement to our community" |

Dept-scoped: only the task department's craft is offered. Operate the owning skill per the SOPs in this cluster **before** authoring by hand. Rule-Zero paid-call approval (USD announce + budget cap) still applies. Doctrine: `universal-sops/native-skill-invocation.md`.
<!-- END CRAFT_INTENT_TRIGGERS_V1 -->

## Capability ownership

| Owner | Owns | Does not own |
|---|---|---|
| **CRM department** (`crm`) | Platform administration, automation, integration, account/capability management, agency/sub-account credential recovery, workflow build/schedule, monitoring reads, Projects provisioning, native Voice/Conversation/Studio/KB/Widget provisioning | Curriculum, member experience, course outcomes |
| **Courses department** (`courses`) | Learning outcomes, curriculum, lesson content, assessments, course production acceptance, learner-visible checks | GHL API mechanics, browser selectors, member moderation |
| **Community Builder department** (`community-builder`) | Group/channel structure, moderation, member operations, learning association, member experience, inside-the-room voice | Workflow construction, course authoring, CRM credential repair |
| **Social Media department** (`social-media`) | Content calendar, brand-level publishing strategy, approved handoff to Community publishing | Community strategy ownership; a second poster |

### Contextual platform aliases (not departments)

`Convert and Flow`, `Convert & Flow`, `GoHighLevel` and `GHL` are **platform aliases for the `crm`
department**. A request that mentions GHL is NOT automatically a CRM request — classify the actual
business outcome first (Section 13.2 of the revision-3 implementation spec). Never create a `ghl`
department, never rename `crm`, never add a second CRM workspace.

## Skill mapping

| Skill | Role in GHL operations | Rail it drives |
|---|---|---|
| **44** `convert-and-flow-operator` | Typed public operations, CLI, workflow build/publish, products/prices, monitoring, native AI/KB/Widget/Projects provisioning, authorized private fallback | Public REST (workflow v3, courses, community social, monitoring, meeting rooms, native AI, KB, widgets, projects) → official MCP when an exact discovered operation exists → existing Firebase/internal fallback → nothing |
| **6** `ghl-install-pages` | Page/form/survey/funnel delivery; course construction/deployment coordinator; Community/Learning UI authoring; Meeting Rooms; marketing quizzes | Managed browser + proven upload/binding operations; never teaches or invents curriculum |
| **35** `social-media-planner` | Approved Community publishing handoff (post/comment), scheduled vs published state | Shared Community publishing adapter; never owns Community strategy |
| **29** `ghl-convert-and-flow` | Supporting knowledge pointer: human-readable API knowledge, source-indexed contract references | No credential ownership, no execution authority |
| **36** `ghl-mcp-setup` | Supporting knowledge pointer: official MCP connection, discovery evidence, per-client transport instructions | No token creation, no execution authority |
| **38** `conversational-ai-system` | Conversational behavior policy and single-responder ownership (native Conversation/Voice/KB/widget threads) | Behavior only; transport is 44/6 |

## Transport decision (one route per mutation)

```text
1. Resolve tenant, operation, plan identity, authorization.
2. Dry-run? validate/compile only, no mutating network call.
3. Read the operation registry row + current capability evidence.
4. Select exactly ONE public implementation for the caller:
   - deterministic CLI/worker without MCP: verified shared public REST;
   - MCP-capable session with an exact authorized/discovered operation: official MCP;
   - missing MCP operation: verified public REST (not "API absent").
5. Bind connection/credential to the exact operation + location.
6. Documented feature gap / beta not enabled / unimplemented public feature:
   approved existing private operation where supported.
7. Otherwise: a registered managed-browser operation in Skill 6.
8. After a write is submitted, reconcile on THAT route. Never repeat on another route.
9. Emit one logical operation receipt naming attempts and the actual selected route.
```

Public capability failure is never permission to bypass account authorization. Classify 401 / generic
403 / wrong tenant / missing role / revoked credential BEFORE any fallback (see SOP-GHL-01).

## Canonical procedures

| File | Procedure |
|---|---|
| `SOP-GHL-01-CAPABILITY-AND-ROUTING.md` | Tenant/auth resolution; public/MCP/private/browser choice; error classification; beta request; no ambiguous retry |
| `SOP-GHL-02-WORKFLOW-BUILD-AND-EDIT.md` | Approved intent, dependencies, step schemas, validate/create/readback, safe update, explicit publish, fallback |
| `SOP-GHL-03-COURSE-PRODUCTION.md` | Curriculum handoff, permanent media, course/modules/lessons, native content, release, learner checks |
| `SOP-GHL-04-COMMUNITY-AND-LEARNING.md` | Group/channel creation, settings, member operations, course association, visibility, residue-aware cleanup |
| `SOP-GHL-05-COMMUNITY-PUBLISHING.md` | Channel account and member resolution, post/comment contracts, notification approval, scheduled/published distinction |
| `SOP-GHL-06-FULFILLMENT-AND-EVIDENCE.md` | Commerce vs offer/grant, required delivery receipts, access test, Kanban/launch handoff, pending-state wording |
| `SOP-GHL-07-MEETING-ROOMS.md` | Skill 6: host/location/security, observed setup, calendar/course/event binding, isolated guest check |
| `SOP-GHL-08-NATIVE-AI.md` | Skill 38 + 44: provider choice, behavior plan, native provisioning, responder ownership, promotion/activation |
| `SOP-GHL-09-KNOWLEDGE-LIFECYCLE.md` | Skill 38 + 44: approved sources, upload/crawl, train, attach, retrieve; source/job/agent identity |
| `SOP-GHL-10-WIDGET-INSTALLATION.md` | Skill 44 + 6: supported write type, readback, real embed, duplicate prevention, inbox behavior |
| `SOP-GHL-11-PROJECTS-AND-SYNC.md` | Skill 44 + Command Center: API/Labs distinction, structure/tasks/access, one-way sync |
| `SOP-GHL-12-WORKFLOW-MONITORING.md` | Skill 44: windows/cursors/retention, exact metric meaning, redacted runtime diagnostics |
| `SOP-GHL-13-MARKETING-QUIZZES.md` | Skill 6: outcome/scoring/branching, native builder, test submission, CRM wiring |

Revision-3 extensions (07-13) were added to this SAME cluster by DECISION 5 of the revision-3 change
ledger. They are not a second cluster and must not be forked into one.

## Related canonical SOPs (do not duplicate their authority)

- `universal-sops/form-craft/` — native GHL form engine.
- `universal-sops/funnel-craft/`, `universal-sops/website-craft/` — page/funnel construction.
- `universal-sops/social-media-craft/` — content calendar and brand publishing strategy.
- `universal-sops/funnel-automation-build-quality-rubric.md` — workflow build rubric.
- `universal-sops/native-skill-invocation.md` — how departments reach these skills from plain intent.

## The receipt contract (every procedure emits one)

A logical operation has the stable key `(company_id, location_id, run_id, operation_key)`.
Attempts have unique ids underneath it. Outcomes are exactly: `planned`, `submitted`, `processing`,
`verified`, `failed`, `blocked`, `unknown_outcome`, `not_requested`. Receipt fields:
`schema_version`, `receipt_id`, `attempt_id`, `event_sequence`, `run_id`, `operation_key`,
`operation_id`, `company_id`, `location_id`, `task_id`, `skill`, `rail`, `outcome`, `build_state`,
`requested_visibility`, `actual_visibility`, `request_hash`, `object_refs`, `readback`, `attempts`,
`evidence_refs`, `next_action`, `observed_at`. A receipt is an immutable event: re-delivery keeps
the original id and bytes; a later verification emits a NEW event with the next sequence.

## Non-negotiables

1. One route per mutation. `unknown_outcome` is reconciled by ids/reads before ANY retry.
2. No duplicate create across rails. GET-first / idempotency is local unless the endpoint documents
   an idempotency mechanism.
3. Draft/inactive by default; publishing and active triggers require an explicit owner/CAMPAIGN answer.
4. Secrets never enter a receipt, a log line, a commit message or a transcript.
5. The registry (`public/operations.py`) is the implementation authority; documentation cannot
   enable an operation.
6. Live canaries are operator-authorized and recorded separately from offline tests.
