# SOP-GHL-02 — Workflow Build and Edit

**Cluster:** `universal-sops/ghl-hybrid-operations/` · **Owner:** Skill 44 (CRM automation) owns; builder is the CRM Automation Workflow Specialist · **Revision:** 3.0 (2026-11-08)

**Trigger:** A CRM-owned request to create, modify, publish or retire a GHL automation/workflow, or a
workflow returned for repair by QC.

**Inputs:**
- Approved intent: desired result, trigger type, every pinned constraint (exact copy, waits, tags,
  channels, business hours), offer/branch logic.
- Gating answers: PUBLISH (draft vs live) and RE-ENTRY (once vs allow-multiple).
- Dependency evidence: every tag, custom field and custom value already exists (GET-verified).
- The current workflow graph and opaque/fractional version when editing an existing workflow.

**Required pointers:**
- `44-convert-and-flow-operator/INSTRUCTIONS.md` — Step 0 model pre-flight, PLAN MODE, gating questions.
- `universal-sops/funnel-automation-build-quality-rubric.md` — build-quality rubric (≥ 8.5 floor).
- `44-convert-and-flow-operator/automation-templates/` + `_matcher/cli.py` — reuse-first templates.
- `universal-sops/ghl-hybrid-operations/SOP-GHL-12-WORKFLOW-MONITORING.md` — post-publish reads.

**Ordered steps:**
1. Reuse-first: run the template matcher; a template is a guide, never a rule — honor explicit spec.
2. Restate A1 (outcome), A2 (pinned values), A3 (approach). Ambiguous → stop and ask, never invent.
3. GET-verify every dependency. Missing non-`zhc_` dependency → surface for approval before building.
4. Instantiate the WF-1..WF-21 checklist with every Expected field filled.
5. Present the plan, the checklist, and the two gating questions; WAIT. Defaults after a genuine
   wait: PUBLISH=draft, RE-ENTRY=once — recorded explicitly as defaults.
6. Validate/compile. `POST /workflows/search` is a READ; validation consumes write quota but does not
   persist. Never classify by HTTP verb alone.
7. Create only when no matching existing workflow exists (idempotency is local, GET-first).
8. Read back the created workflow: id, opaque version, trigger state, node order, action types,
   SMS `fromNumber`, email sender, exit/suppression rules.
9. Apply draft/inactive unless LIVE was explicitly chosen; a published workflow is never silently set
   to draft and a draft is never silently published.
10. For an edit: re-read the current graph/version first; reapply intent; preserve unknown valid
    fields, provider step ids, opaque/fractional versions and unapproved deletions.
11. Emit a `verified` receipt only after readback matches intent; otherwise `submitted`/`failed`.

**Allowed route changes:**
- Public Workflow API v3 first; on explicit beta denial use the approved existing private fallback;
  on a documented authoring gap use the Skill 6 managed-browser build.
- Never duplicate a create because a response was lost. Reconcile by workflow id/version first.

**Required output / receipt:** workflow id, name, publish/active state, opaque version, filled
checklist (Expected + Observed), rubric score, pre-mutation snapshot path, receipt with `rail` and
`readback.state`.

**Approval boundary:** publishing and `active:true` require an explicit owner/CAMPAIGN yes. Complex
workflows need Director review. Any deletion of graph elements, any publish transition, and any
workflow touching live customer communications are owner-visible decisions.

**Failures:**
- Recoverable: 422 validation → fix the named issue; stale revision → re-read and reapply; missing
  dependency → create via the approved dependency step, then rebuild the plan.
- Terminal: 409 published conflict → report and use an explicitly authorized draft transition (never
  auto-pause); missing browser selector → capture the real UI state and fix that selector, never
  guess; validation returns `valid=false` or a business-critical no-op warning → refuse completion.
- `unknown_outcome`: reconcile by workflow id + readback before any retry on any rail.

**Acceptance:** the built workflow's observed state matches every pinned value; exactly one create;
draft stays draft unless approved; a stale edit is re-read, not retried; receipt `verified` only on a
matching readback.
