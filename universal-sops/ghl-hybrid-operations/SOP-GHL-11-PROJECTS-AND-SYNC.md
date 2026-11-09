# SOP-GHL-11 — Projects and Sync

**Cluster:** `universal-sops/ghl-hybrid-operations/` · **Owner:** Skill 44 (Projects adapter) + Command Center (mapping) · **Revision:** 3.0 (2026-11-08)

**Trigger:** A request to create or update a GHL Projects space/list/task, or to mirror an approved
client checklist into Projects — including "mirror this verified client checklist into HighLevel
Projects".

**Inputs:** tenant token context, space/list/status model, task fields (title, due date, status,
assignee), subtask/member/comment decisions, and the explicit one-way sync decision (or none).

**Required pointers:** Skill 44 Projects adapter/commands; Command Center task/receipt schema and
scoped mapping module; `SOP-GHL-06-FULFILLMENT-AND-EVIDENCE.md` for completion authority.

**Ordered steps:**
1. Derive the tenant from the token; do not accept a caller-supplied tenant that disagrees.
2. Distinguish UI availability from API availability (Labs/beta). Record which one the operation uses.
3. Resolve the default list and the endpoint-specific pagination before reading.
4. Create/update structure: space → list → task → subtask. Respect the single-assignee bound.
5. Set due date, status, and members only within the approved rules.
6. If mirroring from Command Center: apply the explicit one-way mapping, keep field ownership
   documented, and preserve Command Center as completion authority.
7. Verify no back-loop: a Projects update must never re-trigger a CC task mutation.
8. Emit a receipt with the mapping (CC task id ↔ Projects task id) and field ownership.

**Allowed route changes:** Public Projects operations first; private fallback only for a documented
gap; browser only for a UI-only control. Never duplicate a task across rails.

**Required output / receipt:** space/list/task ids, field ownership map, pagination evidence, sync
direction record, receipt.

**Approval boundary:** enabling any CC→Projects sync, changing participants/permissions, and writing
into a client's shared project require explicit owner approval. A read or a dry-run mapping does not.

**Failures:** Recoverable — beta not enabled → record `beta_not_enabled`, keep the mapping, and queue
the access request separately; pagination incomplete → continue with the cursor. Terminal — tenant
mismatch, unsupported rule (e.g. multiple assignees beyond the bound), or a sync loop → stop.

**Acceptance:** the requested structure/tasks exist with correct due dates/status/access, the
pagination worked, and a one-way sync never loops or falsely completes a CC task.
