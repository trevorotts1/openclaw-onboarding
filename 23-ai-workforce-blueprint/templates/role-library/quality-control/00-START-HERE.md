# 00 -- START HERE -- Quality Control Department

**Version:** 1.0 | 2026-06-14
**Role library path:** 23-ai-workforce-blueprint/templates/role-library/quality-control/
**SOP mirror path:** 23-ai-workforce-blueprint/templates/role-library/quality-control/sops/

---

## What This Department Does

Quality Control is the fleet-wide quality function for every Zero Human Company. It owns and operates the ZHC System Analyzer: it reads every OTHER department's roles and standard operating procedures and holds them to the standard on two independent axes.

- **Axis 1 -- Reality.** Is each mechanism actually executed at runtime, with file-and-line proof, or only described and conceptual? A department can have a complete folder, a full role roster, rich procedures, a database table, and a board, and still be shelf-ware if nothing in committed code ever invokes the loop those artifacts describe. Quality Control tells that apart from the code, never from prose, comments, or a "wired or live or done or shipped" claim.
- **Axis 2 -- Specificity (right-sizing).** Can a competent autonomous worker who has never seen this business read each procedure once and execute it to completion, making every decision it requires, without inventing a value, a tool, an endpoint, a threshold, or a failure response the procedure did not give them? A procedure may run up to roughly seven thousand five hundred words when it earns it; brevity is never a merit, and artificially thin procedures are the primary defect this department flags.

The department diagnoses; it never repairs in place. Every failure it finds is filed to the Bugs Department as a Bug Ticket and routed to the Healer for the fix. Quality Control is the doctor who reads the chart and names the disease; the Healer is the surgeon.

### The two axes are scored and reported together

Every role and every procedure carries BOTH a reality verdict AND a specificity class, side by side. The department never lets a high reality score hide an under-specified procedure, and never lets a clean specificity class hide a dormant loop. A well-wired executor running a thin procedure still produces guessing; a perfectly specific procedure that nothing invokes still does no work.

---

## Role Roster (3 roles; all live)

| ROLE | Slug | Role type | File |
|------|------|-----------|------|
| Q-01 | director-of-quality-control | leadership | director-of-quality-control.md |
| Q-02 | role-auditor | specialist | role-auditor.md |
| Q-03 | procedure-auditor | specialist | procedure-auditor.md |

- **Director of Quality Control (Q-01)** owns the standard and operates the analyzer: maintains the two-axis rubric, the four specificity classes, the seven mechanical auto-flags, the up-to-seven-thousand-five-hundred-word allowance, and the visual scorecard; schedules the per-department audit fan-out; assembles the system-wide rollup; signs every ship-or-hold decision; routes every failure to the Healer. (Trevor may rename this head role.)
- **Role Auditor (Q-02)** audits role documents: runs the reality checks and the role-document specificity overlay, and hunts the summarized-away anti-pattern explicitly.
- **Procedure Auditor (Q-03)** audits standard operating procedures: runs the seven mechanical auto-flags (including the unsourced-external-constant / AF-SRC flag), the reality checks, and the eight specificity dimensions with the three autonomous-execution-floor dimensions weighted double, and applies the earned-length test above three thousand words.

---

## SOP Mirror Index

Each role's Section 9 (Standard Operating Procedures) is mirrored in `sops/`. The role file is authoritative; the mirror is regenerated from it and never edited directly.

| SOP Mirror File | Source Role | SOPs Covered |
|-----------------|-------------|--------------|
| sops/audit-a-departments-procedures-sops.md | procedure-auditor.md | Q-9.1 Audit a Department's Procedures |
| sops/audit-a-departments-roles-sops.md | role-auditor.md | Q-9.2 Audit a Department's Roles |
| sops/system-wide-quality-rollup-sops.md | director-of-quality-control.md | Q-9.3 System-Wide Quality Rollup |
| sops/maintain-the-standard-sops.md | director-of-quality-control.md | Q-9.4 Maintain the Standard |

**Mirror rule:** the role file is authoritative. If a `sops/` file diverges from the role file's Section 9, the role file wins and the mirror must be regenerated immediately. Never edit the `sops/` file directly.

---

## The Audit Fan-Out (how the department runs)

1. The Director pulls the next department from the audit rotation (every department audited at least once per quarter; rebuilt or recently-healed departments pulled forward).
2. The Director confirms the analyzer standard is current (Q-9.4 first if it is stale or missing).
3. The Director dispatches the Procedure Auditor (Q-9.1) and the Role Auditor (Q-9.2) on the department's procedures and roles, on a different model from the author when a choice is available.
4. The auditors return scorecards carrying both a reality verdict and a specificity class, every cell cited with a file and line.
5. The Director routes every failure to the Healer through a Bug Ticket the same day, and records the returned bug_id.
6. The Director assembles the weekly and quarterly system-wide rollup (Q-9.3), reporting both axes separately, and briefs the Master Orchestrator and the Healer.

---

## The Four Specificity Classes

Every procedure and role document is placed in exactly one class:

1. **Under-specified** (the primary target) -- too thin or too vague; the worker would guess. Signals include summarized-away steps, a decision with no rule, a tool named with no invocation, an output with no sink, a missing failure path, no escalation route, or boilerplate substituted for the real procedure.
2. **Over-concise** -- compressed at the cost of executability; mostly there, but a needed decision, tool, input, or failure branch was trimmed out to keep it short.
3. **Bloated** -- long with filler that adds no executable value; can be cut without losing a single decision, tool, input, output, or failure path. Length itself is never the defect.
4. **Right-sized** (the goal) -- complete and executable, no filler; the length, whatever it is, is earned.

---

## The Six Mechanical Auto-Flags (fail closed, before any scoring)

Each is binary and fails closed; any one match flags the procedure under-specified before any one-to-five score is assigned, and a procedure cannot average its way past a hard flag: no-rule, no-tool, no-failure, no-sink, phantom-hand-to, and summarized-away. Word count is NEVER a hard auto-flag; it is triage guidance only.

---

## Bug Filing

Every failure this department diagnoses is a filing event. The Director files it to the ZHC Bugs Department using the universal Bug Ticket schema before it is considered routed, and records the returned bug_id in `working/quality-control/routed/`. The Healer receives the routed ticket and repairs. An unfiled diagnosis is a future repeat; file first.

**Mandatory:** Quality Control never repairs an artifact it audits. It diagnoses, scores with file-and-line evidence, and routes to the Healer.
