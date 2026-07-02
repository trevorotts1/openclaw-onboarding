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
mc-route.sh <department_slug> <title> [description...]
```

- `<department_slug>` — target workspace/department (e.g. `presentations`,
  `general-task`, `social-media`). REQUIRED.
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

Exit `0` on a 2xx ingest; non-zero on failure. On non-zero the helper prints an
`ESCALATE_TO_OPERATOR:` line — the CEO must tell the owner it is escalating (never
self-intake, never ask intake questions, never retry forever). On a 2xx whose
`workspace_id` != the requested `department_slug`, it warns + emits an
`ESCALATE_TO_OPERATOR:` line (the department may be absent on this box).

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
so it cannot allow the sanctioned helpers while denying arbitrary shell. That
command-level "only the sanctioned helpers" restriction is enforced by the
PreToolUse **intent-gate** (`hooks/ceo-intent-gate.sh`), which default-**denies**
every non-routing exec. Fully dropping `exec` at the config layer would deny the
CEO the `route-presentation.sh` helper that REFLEX V2 STEP 1 mandates (a
documented flow), because a config-layer deny is restrict-only and cannot be
un-denied by the hook. So exec stays as the channel for the two anchored
sanctioned helpers only; it is retired outright once the reflex migrates
`route-presentation.sh` onto `mc-route__route_task`.

## Follow-ups for other owners (out of this fix's lane)

These land the fix fleet-wide; each is one edit in another owner's file:

1. **Intent-gate carve-out** (`hooks/ceo-intent-gate.sh`, gate owner): add an
   ANCHORED `mc-route.sh` allow beside the existing `route-presentation.sh` one
   (ceo-intent-gate.sh:224). Suggested, mirroring that line exactly:
   ```
   if printf '%s' "$_CMD" | grep -qE '^[[:space:]]*((bash|sh)[[:space:]]+)?[~/][^[:space:]]*/\.openclaw/scripts/mc-route\.sh([[:space:]]|$)'; then
     exit 0
   fi
   ```
   Anchored to the command's start (optionally through a leading `bash`/`sh`), so
   a look-alike mentioned mid-command does NOT match (no substring bypass).
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
