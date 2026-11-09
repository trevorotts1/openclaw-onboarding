# SOP-GHL-12 — Workflow Monitoring

**Cluster:** `universal-sops/ghl-hybrid-operations/` · **Owner:** Skill 44 (CRM) · **Revision:** 3.0 (2026-11-08)

**Trigger:** A request to inspect workflow logs, failed steps, or execution statistics — including
"show which automation steps failed yesterday". This is a READ procedure: it never creates a workflow.

**Inputs:** operation ids, location, explicit time window (start/end), pagination cursor, retention
window, aggregate vs event-level intent, and the exact metric definition requested.

**Required pointers:** Skill 44 `public/workflow_monitoring.py` and command module; Skill 29 references
for field meaning; `SOP-GHL-02-WORKFLOW-BUILD-AND-EDIT.md` for any follow-up repair.

**Ordered steps:**
1. Classify the request as read-only. If it asks for a create/edit, route to SOP-GHL-02 and stop here.
2. Bound the window explicitly. Respect the provider's retention; state when the window exceeds it.
3. Page with the returned cursor. Do not infer completeness from the first page.
4. Preserve the schema's new/unknown fields; record schema growth rather than dropping it.
5. Report event-level facts (step, status, error, timestamp) separately from aggregate counts.
6. Label aggregate counts exactly. An aggregate count is NOT cohort conversion; a rehearsal is NOT a
   live execution.
7. Redact runtime diagnostics: no secrets, tokens, PII, or customer content in the report; hash
   approved content separately from redacted diagnostics.
8. Emit a read receipt (no write attempt) with the window, cursor trail, and metric definitions.

**Allowed route changes:** Public monitoring operations first; private fallback only for a documented
gap. Reads never escalate to a browser unless the API has no equivalent and the operator approves.

**Required output / receipt:** window, cursor trail, event rows, aggregate counts with their exact
meaning, redaction statement, read receipt.

**Approval boundary:** reading is allowed for anyone authorized in the location; exporting customer
content or sharing logs outside the tenant requires owner approval.

**Failures:** Recoverable — rate limit → honor reset and continue with the same cursor; cursor expired →
restart the bounded window and say so. Terminal — window beyond retention → report the exact
limitation; tenant mismatch → stop. Never present a partial page as complete.

**Acceptance:** an accurate, bounded, redacted log/aggregate result with explicit metric meaning and a
separate controlled-live proof where a live claim is made.
