# SOP Mirror -- Rescue Rangers Escalation (Cross-Cutting)

**SOP ID:** `SOP-MAINT-RESCUE-RANGERS-ESCALATION`
**Source:** openclaw-maintenance (cross-cutting; co-owned by R1, R2, R3, R4)
**Authority:** This SOP is authoritative for all roles in openclaw-maintenance. Role files embed it by reference. This file is the canonical copy.
**Type:** Cross-cutting escalation SOP -- always-on
**Triggers:** Any ambiguous, feature-bearing, or unresolvable finding from any maintenance specialist
**HARD RULE:** NEVER bypass the OpenClaw gateway for Telegram. All messages go through `openclaw message send` (per memory `feedback-never-bypass-openclaw-telegram.md`).

---

## 9. Standard Operating Procedures

### SOP 9.1 -- When to Escalate to Rescue Rangers

**Mandatory escalation triggers (any of these = escalate):**
1. A finding is AMBIGUOUS -- could be a furnace condition OR a legitimate feature (e.g., a cron that fires frequently but may have a valid business reason).
2. An auto-fix was applied but verification failed (the condition persists after remediation).
3. The fix would require touching something the maintenance role is NOT authorized to touch (Tier 3: feature-bearing config, master SOP, model manifest, by-design primary, operator-explicit setting).
4. A gateway or tunnel recovery attempt failed after the maximum retry count.
5. A breaking change blocks a pending upgrade and operator decision is required.
6. Any finding that could be a false positive on a critical feature.
7. The maintenance role's config validate fails after a backup restore (unexpected state).

**DO NOT escalate for:**
- Clean sweeps (silence is the correct signal for healthy state).
- Tier 1 auto-fixes that verified successfully.
- Routine notifications (upgrade complete, model swap complete).

---

### SOP 9.2 -- Escalation Message Format

**When to run:** Whenever a mandatory trigger from SOP 9.1 fires.

**Steps:**
1. Build the escalation message. Required fields:
   ```
   [RESCUE-RANGERS] Maintenance Escalation
   Box: {box_name or hostname}
   Role: {which specialist is escalating: R1/R2/R3/R4}
   Driver: {furnace driver id e.g. F6, or free-text description}
   Finding: {one sentence describing what was found}
   Evidence: {log path or inline quote -- never guess; attach actual evidence}
   Proposed fix: {what the role would do if authorized}
   Why escalating: {the specific reason this is Tier 3 / ambiguous / unresolved}
   Action needed: {what the operator should decide or approve}
   ```
2. Send via: `openclaw message send --channel telegram -t "${RESCUE_RANGERS_HELP_CHAT_ID}"` (the shared Rescue Rangers HQ Telegram group).
3. Log the escalation to `working/maintenance/escalations/esc-YYYYMMDD-HHMMSS.json`.
4. After sending: HALT this fix thread and wait for operator response. Do NOT retry the fix without operator direction.

**Outputs:** Escalation message delivered to Rescue Rangers HQ; local escalation log entry.

**Hand to:** Operator (human decision required). **Failure mode:** `openclaw message send` itself fails (gateway down): execute SOP-MAINT-UPTIME (S4) first to restore gateway, then send the escalation. If gateway cannot be restored: write the escalation to `working/maintenance/escalations/UNSENT-esc-YYYYMMDD-HHMMSS.json` and retry on next probe.

---

### SOP 9.3 -- Responding to Operator Decision

**When to run:** After operator replies to an escalation.

**Steps:**
1. Read the operator's decision. Valid responses: APPROVE (proceed with the proposed fix), DENY (do not apply the fix; log as DECLINED), MODIFY (apply a different fix -- operator will specify).
2. Apply the approved action per the appropriate role SOP, but NOW with Tier 3 written approval (log the operator message text as the approval evidence in the escalation record).
3. Run `openclaw config validate` after any config change. Restore backup on failure.
4. Confirm back to the operator (one notification) that the action is complete and verified.
5. Update `working/maintenance/escalations/esc-YYYYMMDD-HHMMSS.json`: `{ operator_response, action_taken, verified_at, outcome }`.

**Outputs:** Applied action, operator notification, closed escalation record. **Hand to:** Done. **Failure mode:** Operator response is ambiguous: ask ONE clarifying question. Do NOT guess or proceed on ambiguity.

---

### SOP 9.4 -- Escalation Ledger Hygiene

**When to run:** Weekly, as part of any maintenance specialist's weekly sweep.

**Steps:**
1. Read `working/maintenance/escalations/`. Count open escalations (no `operator_response` field).
2. For escalations open > 7 days: send ONE follow-up reminder to Rescue Rangers HQ (do NOT spam).
3. For UNSENT escalations: retry sending once per day.
4. Close escalations with `outcome: resolved|declined|superseded` as appropriate.

**Outputs:** Updated escalation records. **Hand to:** Operator (for open items). **Failure mode:** More than 5 open escalations with no response: send a single summary to Rescue Rangers HQ listing all open items.

---
