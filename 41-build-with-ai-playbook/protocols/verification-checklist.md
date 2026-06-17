# Verification Checklist -- Skill 41

## Purpose

The 12-point post-build verification checklist. Run this after every workflow build BEFORE publishing. A build without verification is incomplete.

## The 12 Points

1. **Workflow name matches the prompt**
   - The generated workflow name matches exactly what was specified in the prompt.
   - If the AI renamed it, verify the new name is acceptable.

2. **Trigger is correct type and filters are applied**
   - Trigger type matches the prompt (e.g., Contact Created, Form Submitted).
   - Any filters specified in the prompt are present and configured correctly.
   - Filter values match exactly (form name, tag name, etc.).

3. **All referenced tags exist and are spelled correctly**
   - Every tag in Add/Remove Contact Tag actions exists in the location.
   - Tag names are spelled exactly as in the prompt (case-sensitive).
   - Tags used in If/Else conditions exist.

4. **All referenced custom fields exist and have correct data type**
   - Every custom field in Update Contact Field actions exists.
   - Data types match (text, number, date, dropdown).
   - Field names are spelled exactly as in the prompt.

5. **All referenced custom values exist and have values set**
   - Every custom value referenced in merge fields exists.
   - The value is set (not empty).
   - Name matches exactly.

6. **Action sequence matches the prompt (order, configuration)**
   - Actions are in the same order as specified.
   - Each action's configuration matches (template, recipient, message, etc.).
   - No actions were dropped or added unexpectedly.

7. **If/Else conditions evaluate the right fields with correct operators**
   - Condition field matches the prompt.
   - Operator matches (is, is not, contains, greater than, less than, empty).
   - AND/OR logic matches the prompt.
   - Both YES and NO branches are configured.

8. **Wait steps have correct duration**
   - Wait duration matches the prompt (minutes, hours, days).
   - Timeout branches (if specified) are configured.

9. **Webhook URL is correct and method matches the prompt**
   - URL matches exactly.
   - Method matches (GET, POST, PUT, DELETE).
   - No trailing spaces or hidden characters in the URL.

10. **Webhook headers include Content-Type: application/json (for raw JSON body)**
    - For CUSTOM mode with raw JSON body, Content-Type header is present.
    - Authorization header is present if specified.
    - Custom headers match the prompt.

11. **Settings: re-entry, stop on response, time windows are correct**
    - Allow Re-entry matches the prompt (yes/no).
    - Stop on Response matches the prompt.
    - Time window (business hours) matches the prompt.
    - Sender details (From Name, From Email, From Number) match.

12. **Test the workflow with a test contact before going live**
    - Use GHL's "Test Workflow" feature.
    - Select a test contact and click "Run Test."
    - Verify each action fired as expected.
    - Check execution logs for errors.

## Scoring

- Each point is worth 1 point (12 total).
- Score of 12/12 = ready to publish.
- Score of 10-11/12 = minor fixes needed; fix and re-verify.
- Score below 10/12 = significant issues; rebuild or manual fix required.

## Logging

Record the verification score in build-with-ai-events.jsonl:
- build_completed event: verification_score field
- verification_failed event: failed_items array + fix_suggested string

---

## Cross-reference: Skill 44 WF-1..WF-21 Checklist (caf-built workflows)

For workflows built via Skill 44's Convert and Flow CLI (`caf workflows build`), use the
**Skill 44 WF-1..WF-21 checklist** at
`44-convert-and-flow-operator/references/workflow-build-checklist-template.md` instead.

That checklist is a SUPERSET of this 12-point checklist, extended with Skill 44-specific
gates that are not applicable to Build-with-AI (browser/manual) builds:
- **WF-4** — trigger active flag vs publish-intent (the "trigger-active trap": CAF_DRAFT_ONLY=true
  ships triggers inactive by default; a workflow built as LIVE needs active:true or it
  silently never fires).
- **WF-12** — SMS From-number non-empty on every SMS node (no-From-number = silent send failure).
- **WF-15** — delivery chain linkage (targetActionId/parentKey wired by link_steps).
- **WF-20** — no hallucinated artifacts (build agent claims independently verified via export).
- **WF-21** — pre-build snapshot exists for rollback.
- Gating questions recorded on the checklist (publish decision, re-entry decision).

This Skill 41 checklist applies to **Build-with-AI (manual browser)** builds only.
For caf-built workflows, the Skill 44 WF-1..WF-21 checklist is authoritative.
