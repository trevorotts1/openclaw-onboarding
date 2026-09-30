# mc-route — the general signed task-routing tool

`scripts/mc-route.sh` is the **general** version of `route-presentation.sh`: the
same signed Command-Center ingest helper, but the department is an **argument**
instead of the hardcoded `presentations`. It is the shipped implementation behind
the `mc-route__route_task` routing tool the CEO/orchestrator uses to route ANY
task to ANY department **without self-executing**.

This closes final-review Point 7 fix 6 (ranked remediation #6): _"Ship `mc-route`
and remove `exec` from the CEO allow-set (retire the interim)."_

## Usage

```
mc-route.sh task "<short title>" "<owner's exact words>"      new card, one per job
mc-route.sh existing status "<task title or id>"              read-only status of existing work; never creates a card
mc-route.sh existing update "<task title or id>" "<note>"     adds the owner's note or change to that card
mc-route.sh existing cancel "<task title or id>"              cancels that card
(legacy) mc-route.sh auto "<owner message verbatim>"
(legacy) mc-route.sh <department_slug> <title> [description...]
```

### The first word is checked (JEV-601)

The first word must be `task`, `existing`, `auto`, `help`, or a department that
exists on this board. Before JEV-601 any first word was taken as a department, so
a model that ran `mc-route.sh status <task>` or `mc-route.sh stop <task>` made a
General Task card. That caused 757 of the 984 extra cards in the JEV-592
acceptance run.

- A department is checked against `GET /api/workspaces` (this company's board).
  It matches the workspace's slug or id, or its name or slug with or without
  `dept-` (so `social-media` finds `dept-social-media`, and `Marketing` finds
  `marketing`). The card is sent with the board's real slug.
- Anything else prints `mc-route: REFUSED — ...` and the usage on stderr, creates
  nothing and exits `2`. Words models used for existing work (`status`, `stop`,
  `check`, `list`, `show`, `cancel`, `update`, `resume` and similar) are refused
  before any network call, with a pointer to `existing`.
- If the department list can't be read (Command Center down), the helper prints
  `mc-route: FAILED — ...` and `ESCALATE_TO_OPERATOR:`, creates nothing and
  exits `1`.
- `help`, `-h` or `--help` prints the usage and exits `0`.

### Slug mode (legacy) arguments

- `<department_slug>` — target workspace/department (e.g. `presentations`,
  `general-task`, `social-media`). REQUIRED, and it must exist on the board.
- `<title>` — short task title (truncated to 120 chars). REQUIRED.
- `[description...]` — the remaining args are joined with single spaces into the
  task description (owner message, verbatim).

Optional env overrides (safe defaults; the **secret resolution + HMAC signing are
byte-for-byte identical to `route-presentation.sh`**):

| Var | Default |
|---|---|
| `MC_ROUTE_INGEST_URL` | `http://127.0.0.1:4000/api/tasks/ingest` |
| `MC_ROUTE_SOURCE` | `telegram` |
| `MC_ROUTE_PRIORITY` | `medium` |
| `MC_ROUTE_MAX_RETRIES` | `2` |
| `MC_ROUTE_API_BASE` (department check and `existing` mode) | `MC_ROUTE_INGEST_URL` without `/api/tasks/ingest` |

Exit `0` on a 2xx ingest; non-zero on failure. On non-zero the helper prints an
`ESCALATE_TO_OPERATOR:` line — the CEO must tell the owner it is escalating (never
self-intake, never ask intake questions, never retry forever). On a 2xx whose
`workspace_id` != the requested `department_slug`, it warns + emits an
`ESCALATE_TO_OPERATOR:` line (the department may be absent on this box) — unless
the mismatch IS the documented General Task catch-all (`workspace_id` is
`general-task`/`dept-general-task`, or `resolved_by` is
`unrecognized-slug->general`, `general-task-fallback` or
`auto-route:general-task-fallback`), which prints an `INFO` line instead and is
never a blocker.

## Auto mode (JEV live routing)

```
mc-route.sh auto "<owner message verbatim>"
```

Every arg after `auto` is joined with single spaces into the owner's message
(verbatim; an empty message hits the same usage escalation as a missing
`department_slug`/`title`). The message alone (`{message}`, no title,
description or `department_slug`) is posted to the same signed CC ingest
endpoint via the identical signing/secret/retry path as slug mode — JEV
classifies it and Command Center either answers it or creates and routes
exactly one card. The CEO's `NEW INTAKE` policy calls this for every new owner
message instead of deciding a department itself.

stdout contract for the caller:

| CC response | stdout | exit |
|---|---|---|
| 2xx, `created: false` | `JEV_ANSWER_DIRECTLY intent=<intent>` | `0` |
| 2xx, a card was created | `ROUTED workspace=<ws> department=<d> resolved_by=<r>` | `0` |
| `403 {"error":"control_probe_never_creates"}` | `JEV_ANSWER_DIRECTLY intent=unresolved` | `0` |
| anything else | `ESCALATE_TO_OPERATOR:` (same as slug mode) | `1` |

`ESCALATE_TO_OPERATOR` is never printed for a 2xx response in auto mode.

## Task mode (the CEO decides; Command Center only picks the department)

```
mc-route.sh task "<short title>" "<owner's exact words>"
```

Use this when the CEO AI has decided the owner asked for work. A question or
small talk gets an answer and no call at all.

- **One call = one card.** If one message holds two jobs, call it twice with two
  titles and the same owner words. Each call makes its own card.
- **No department is sent.** The helper posts a typed card (`title`, `description`
  = the owner's exact words, no `department_slug`, no `message`). Command Center
  picks the department with its own picker, and General Task is the fallback. A
  typed card is never re-classified, so Command Center cannot overrule a task
  call and turn it into "answer".
- **Leans to a card.** A missing title uses the owner words, and missing owner
  words use the title. Only a call with both empty fails.
- **Retry-safe.** The operation key comes from company, source, requester chat,
  title and owner words. It is reused for 60 seconds after the last identical
  call, so a retry makes no second card. Command Center dedupes on that key.
  Window files live in `MC_ROUTE_STATE_DIR` (default
  `${TMPDIR:-/tmp}/mc-route-task-<uid>`) and are pruned after an hour. When
  `MC_ROUTE_EVENT_ID` or `MC_ROUTE_OPERATION_ID` is set, that stable event
  replaces the 60-second window. Two jobs from one event still get two keys.

stdout contract:

| CC response | output | exit |
|---|---|---|
| 2xx with a `task_id` (new or deduped) | `ROUTED workspace=<ws> department=<d> resolved_by=<r>` | `0` |
| 2xx with a `task_id` but no workspace, or `resolved_by` ending `->ceo` / `->unrouted` | the `ROUTED` line, plus a `WARNING` and `ESCALATE_TO_OPERATOR:` on stderr (the card exists, so don't call again) | `0` |
| 2xx with no `task_id` | `mc-route: FAILED — ...` and `ESCALATE_TO_OPERATOR:` | `1` |
| transport failure or any non-2xx | `mc-route: FAILED — ...` and `ESCALATE_TO_OPERATOR:` | `1` |

`department` is CC's `resolved_department` when it sends one. Otherwise it is
the department named in `resolved_by=auto-route:<dept>`
(`general-task-fallback` is shown as `general-task`), and failing that the
workspace.

`auto` mode keeps working unchanged for boxes whose CEO rule still calls it.

## Existing mode (work already on the board)

```
mc-route.sh existing status "<task title or id>"
mc-route.sh existing update "<task title or id>" "<note>"
mc-route.sh existing cancel "<task title or id>"
```

Use this when the owner asks about, changes or stops work that is already on
the board ("Is that finished?", "Make it two pages", "Stop that task"). It never
creates a card.

**Finding the task.** The helper reads this company's departments
(`GET /api/workspaces`) and the open tasks (`GET /api/tasks?limit=500`). It keeps
only tasks on one of those departments, or on none yet. It then picks one task
in this order:

1. The exact task id.
2. The exact title (not case-sensitive). With two cards of the same title, the
   newest.
3. The best word match on the title. At least half of the words you give must
   be in the title, ignoring short words and words like "the", "task" and "card".

An id that isn't in the open list, such as a cancelled card, is read with
`GET /api/tasks/<id>`.

**What each action does:**

| Action | Command Center calls | stdout on success |
|---|---|---|
| `status` | GETs only (strictly read-only) | `STATUS id=<id> status=<s> department=<slug> updated=<t> cancelled=<yes\|no> title="<title>"` |
| `update` | `POST /api/tasks/<id>/messages` `{content: <note>, sender: "owner"}` (an `owner_message` on the card) | `UPDATED id=<id> title="<title>"` |
| `cancel` | `POST /api/tasks/<id>/archive`, then an owner note "Cancelled by the owner." | `CANCELLED id=<id> title="<title>"` |

Command Center v7.6.90 has no "cancelled" status. Soft-archive is its way to
cancel: the card leaves the board, auto-dispatch skips it, its pending dispatch
intents are cancelled, and the row and its history are kept. A session that is
already running on the card is not stopped by this. It can be
restored with `DELETE /api/tasks/<id>/archive`. The signed
`POST /api/tasks/<id>/status` route is not used, because it only moves cards
made by a board producer (Skill 6 and similar) and refuses owner cards. Cancelling
a card that's already cancelled prints `CANCELLED ... (it was already cancelled)`
and changes nothing.

**When it can't act (nothing is created or changed):**

| Case | output | exit |
|---|---|---|
| no task matches | `mc-route: NOT_FOUND — ...` (ask the owner which task; do not make a new card) | `3` |
| several tasks match equally | `mc-route: AMBIGUOUS — ...`, then up to 5 `id=... status=... title="..."` lines (re-run with the id) | `3` |
| wrong action, missing title or id, `update` without a note | `mc-route: REFUSED — ...` and the usage | `2` |
| Command Center unreachable or a non-2xx | `mc-route: FAILED — ...` and `ESCALATE_TO_OPERATOR:` | `1` |

These calls use `Authorization: Bearer <MC_API_TOKEN>`, resolved the same way as
for ingest. `MC_ROUTE_API_BASE` sets the Command Center base URL. By default it
is `MC_ROUTE_INGEST_URL` without `/api/tasks/ingest`.

## Why signed (fail-closed Command Center)

Middleware 503s external ingest when `WEBHOOK_SECRET` is unset and 401s when
`MC_API_TOKEN` is set but no Bearer is sent; the `/api/tasks/ingest` route 401s
when `WEBHOOK_SECRET` is set and `x-webhook-signature` is missing. So the helper
resolves both secrets at RUNTIME (never embedded) and signs BOTH layers:

- `Authorization: Bearer <MC_API_TOKEN>` (middleware layer)
- `x-webhook-signature: HMAC-SHA256(WEBHOOK_SECRET, rawBody)` hex (route layer)

Secret store order and the `WEBHOOK_SECRET` → `CC_WEBHOOK_SECRET` alias order
mirror `cc_board.py` and `route-presentation.sh` exactly, so the signature the CC
server validates is produced the same way regardless of which helper routed.

## How this retires the `exec` interim (and what remains)

`hooks/lib-ceo-tool-gate.sh` — the canonical CEO tool-gate — now carries
`mc-route__route_task` in `CEO_GATE_ALLOW_TOOLS`. Because the CEO routes by
**calling that tool** (a structured tool call, no shell), routing no longer
depends on `exec`. `verify-routing.sh` G7 (lines 500-503) treats `exec` in `allow`
as a hole **only when no `*__route_task` tool is present**, so shipping this tool
clears the G7 INTERIM classification.

`exec` is **retained, not removed**, and this is deliberate: OpenClaw's
config-layer `exec` policy is `{security, ask}` and **cannot command-allowlist**,
so it cannot allow the sanctioned helpers while denying arbitrary shell.

> **UPDATE 2026-08-05 — there is currently NO command-level exec restriction.**
> That restriction used to be enforced by the PreToolUse **intent-gate**
> (`hooks/ceo-intent-gate.sh`), which default-**denied** every non-routing exec.
> Per Trevor, that hook has been **deleted from the repo and unwired fleet-wide**
> — it was the source of the write-deny/`memoryFlush` loop that ate two weeks of
> Telegram messages. Nothing replaced it at the command level: the CEO Routing
> Doctrine plugin that replaced the gate is a **prompt-injection** layer
> (`before_prompt_build`) with **no tool-deny** at all. So `exec` on the router is
> today restricted only by the `{security, ask}` config policy. Treat any claim
> below that the intent-gate enforces something as historical.

Fully dropping `exec` at the config layer would still deny the CEO the
`route-presentation.sh` helper that REFLEX V2 STEP 1 mandates (a documented
flow), because a config-layer deny is restrict-only. So exec stays as the channel
for the sanctioned helpers; it is retired outright once the reflex migrates
`route-presentation.sh` onto `mc-route__route_task`.

## Follow-ups for other owners (out of this fix's lane)

These land the fix fleet-wide; each is one edit in another owner's file:

1. ~~**Intent-gate carve-out** (`hooks/ceo-intent-gate.sh`, gate owner): add an
   ANCHORED `mc-route.sh` allow beside the existing `route-presentation.sh` one.~~
   **NO LONGER APPLICABLE (2026-08-05).** `hooks/ceo-intent-gate.sh` was deleted
   from the repo and unwired fleet-wide (see the UPDATE box above), so there is no
   allowlist to carve out and no gate to add it to. `mc-route.sh` needs no
   exec carve-out: with the hook gone, nothing denies it at the command level.
   Do not re-create the hook to add a carve-out — that reintroduces the loop.
2. **Config write-sites re-sync** (`23-ai-workforce-blueprint/scripts/build-workforce.py`,
   `scripts/apply-routing-fix.sh`, `scripts/apply-fleet-standards.sh` — their
   owners): add `mc-route__route_task` to each inline CEO allow list (the sites
   already carry `"exec"  # INTERIM — replace with mc-route__route_task once that
   MCP tool ships`). Until synced, a real box stays in the PRE-EXISTING INTERIM
   state — no regression.
3. **Distribution + MCP registration**: stamp/copy `mc-route.sh` to the box's
   canonical `$OC_ROOT/scripts/mc-route.sh` (like `route-presentation.sh`) and
   register the `mc-route` MCP server exposing `route_task` (backed by this
   script) so the CEO can call `mc-route__route_task` directly. Once done and the
   reflex is migrated, `exec` can be dropped from `CEO_GATE_ALLOW_TOOLS` and the
   deny set, for a fully-clean G7 with no exec.
