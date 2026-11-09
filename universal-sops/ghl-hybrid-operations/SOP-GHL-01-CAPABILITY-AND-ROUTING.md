# SOP-GHL-01 — Capability and Routing

**Cluster:** `universal-sops/ghl-hybrid-operations/` · **Owner:** Skill 44 (CRM) owns route selection; Skill 29/36 supply knowledge · **Revision:** 3.0 (2026-11-08)

**Trigger:** Any GHL request reaches a department, before any mutation is attempted — including a
retry, a "quick fix", or a request that names GHL but not an outcome.

**Inputs:**
- The owner's request in their own words and the classified business outcome (course, group, post,
  automation, page, native AI, KB, widget, project, monitoring, quiz).
- `company_id`, `location_id`, `agency_company_id` where the operation is agency-scoped.
- The operation registry row from `public/operations.py` and the current capability record.
- Credential reference (never the secret) and its fingerprint.

**Required pointers:**
- `44-convert-and-flow-operator/INSTRUCTIONS.md` — the per-operation decision rule.
- `44-convert-and-flow-operator/tools/engine/public/operations.py` — the implementation authority.
- `29-convert-and-flow/` knowledge references and `36-ghl-mcp-setup/` discovery references — context
  only; they never grant execution authority.
- `universal-sops/ghl-hybrid-operations/README.md` — transport decision table.

**Ordered steps:**
1. Classify the business outcome. A mention of GHL alone is not a CRM request (spec §13.2).
2. Resolve tenant, operation, plan identity, and authorization. Record `company_id`, `location_id`,
   `agency_company_id`; never substitute one for another.
3. If the request is dry-run/plan-only: validate or compile, make no mutating network call, emit a
   `planned` receipt.
4. Read the registry row and current capability evidence: `documented`, `adapter_built`,
   `offline_tests_passed`, `availability`, `scope_state`, `read_probe`, `write_canary`, `enabled`,
   `checked_at`, `expires_at`, `fallback_policy`.
5. Apply the transport decision (README): exactly one public implementation for this caller; do not
   run REST and MCP for the same mutation.
6. On an explicit beta error `WORKFLOW_API_NOT_ENABLED_FOR_LOCATION`: record `beta_not_enabled`,
   select the approved existing private fallback for that operation, and queue the access request
   separately.
7. On a documented feature gap: use the approved private operation where supported; otherwise a
   registered managed-browser operation in Skill 6.
8. Bind the chosen credential to the exact operation and location BEFORE the call.
9. Emit one logical operation receipt naming every attempt and the actual selected rail.

**Allowed route changes:**
- Public REST → official MCP only when an exact authorized/discovered operation exists AND no
  mutation has been submitted yet.
- Public → existing private/Firebase fallback on an explicit beta denial or documented gap.
- Any rail → Skill 6 managed browser only when no API/private operation covers the outcome.
- After a write is submitted: reconcile on that same rail. A route change is forbidden until the
  outcome is known.

**Required output / receipt:** one operation receipt (`workflow-receipt.v1` envelope) with the
stable operation key, `rail` naming the actual route, `outcome` from the fixed vocabulary, the
capability evidence snapshot used, and `next_action` when not `verified`.

**Approval boundary:** the owner or the authorized operator approves any first live write for a new
operation/location (canary), any publish/activation, any spend, and any operation touching customer
communications. Reading, listing and dry-run compilation need no extra approval.

**Failures:**
- Recoverable: 401/expired credential → bounded resolver/refresh, then retry once inside policy.
  429 → honor provider reset + shared per-location budget, do not switch rails to escape quota.
  422 validation → fix the stated field; stale workflow revision → re-read the current graph and
  reapply intent.
- Terminal for that attempt: generic 403 / missing scope / wrong role → record the exact cause and
  repair authorization or block the operation; never change tenant. 404 → distinguish missing object,
  invalid route, wrong tenant, unsupported operation before creating anything. 409 published
  workflow → preserve live state; never auto-pause.
- `unknown_outcome` (timeout after write, 5xx with ambiguous commit): reconcile by object ids and
  reads. NEVER repeat the write on this or another rail.

**Acceptance:** route selection recorded per attempt; exactly one mutation per logical operation;
beta denial and auth denial are classified differently; an ambiguous write is reconciled, not
repeated; the receipt names the real rail.
