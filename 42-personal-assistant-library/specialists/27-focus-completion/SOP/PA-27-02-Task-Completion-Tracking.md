# PA-27-02  --  Task Completion Tracking

**Department:** 27  --  Focus & Completion
**SOP ID:** PA-27-02
**Version:** 1.1
**Last Updated:** 2026-06-03
**Token:** {{TOKEN}}

---

## Objective

Maintain a precise, low-friction log of every task's journey from open to DONE so that stalls, patterns, and completion velocity are visible and improvable.

## Why This Exists

Open loops consume cognitive bandwidth even when you are not actively working on them  --  the Zeigarnik effect keeps unfinished tasks in working memory. A completion tracking system externalizes that load: your brain trusts the system and releases the task. When combined with PA-27-01 focus blocks, tracking reveals exactly where your attention leaks and which task types resist completion.

## DMAIC Procedure

### Define
Define "done" unambiguously for every task before tracking begins. "Work on proposal" is not trackable. "Send proposal V3 to client by 3:00 PM" is. Every task in the tracker must have a binary completion test  --  you or an observer could confirm instantly whether it is done. Without a clear finish line, tasks drift indefinitely.

### Measure
Log every task entered: start time, estimated duration, actual duration, completion status (COMPLETE / PARTIAL / ABANDONED), and switch events. Seed the tracker with no more than 3 priority tasks before the first focus block of the day. More than 3 seeds = you are already multitasking before you begin.

### Analyze
Weekly review identifies three failure patterns: (a) tasks that took 2×+ their original estimates  --  flag for scope or skill investigation; (b) tasks touched across multiple blocks but never completed  --  these are attention sinks consuming focus blocks without producing outcomes; (c) time-of-day patterns revealing when deep work actually occurs vs. when blocks consistently fail  --  use this to schedule future blocks at your proven peak windows.

### Improve
1. **Estimate Calibration Loop:** For every task that exceeded its estimate by >50%, log the actual duration as the new baseline estimate for the next occurrence of that task type. After three iterations of the same task type, your estimates will converge on reality instead of wishful thinking. This alone can reduce the PARTIAL carry-forward rate by 30% or more, because most PARTIAL tasks are simply underestimated, not under-executed.
2. **Chronic Non-Completer Triage:** Any task carried forward as PARTIAL for 3+ consecutive days receives one of three fates decided during the end-of-day scan  --  do not defer: (a) KILL it  --  admit it is not a real priority right now, remove it from the tracker, and release the mental weight; (b) DELEGATE it  --  identify the person who can move it forward and hand it off within 24 hours with clear expectations; (c) BREAK it  --  decompose into sub-tasks each under 30 minutes and re-seed only the first sub-task for tomorrow. Chronic partials are scope failures, not willpower failures.
3. **Quality Flag Gate:** Track a simple quality flag (✓/✗) alongside each COMPLETE status. If >20% of completed tasks show quality flags in a given week, pause new task intake and run a brief root-cause review. The top causes: unclear requirements from upstream (fix the intake form), skill-to-task mismatch (reassign), or rushing to inflate the COMPLETE count (reinforce that one quality completion outweighs five rushed ones).
4. **Morning Vocalization Ritual:** Before the first block of every day, open the tracker and verbally name the ≤3 seeded tasks. Say aloud: "Today I am completing X, Y, and Z." Vocalizing anchors intention in memory and signals to your brain that the system  --  not your working memory  --  holds the open loops. This directly reduces Zeigarnik-effect cognitive load before you start working.
5. **Carry-Forward Lock:** At the end-of-day scan, for every task marked PARTIAL, write tomorrow's first-block outcome in PA-27-01 format ("By [time], I will have [deliverable]") BEFORE closing the tracker. This ensures no partial task falls into the "I will figure it out tomorrow" void. If tomorrow's first block is already claimed by a higher priority, the partial task gets the KILL or DELEGATE treatment immediately.

### Control
- **Verify:** End-of-day scan confirms every focus block has exactly one logged row with start time, actual minutes, status, and a one-line note. No blank rows, no "I will log it tomorrow."
- **Log:** Daily: COMPLETE count, PARTIAL carry-forward count, ABANDONED count with dispositions. Store in the tracker for week-over-week comparison. Weekly: carry-forward aging report  --  any task remaining PARTIAL beyond 3 days is flagged red.
- **Report:** Weekly summary: total COMPLETE tasks vs. previous week, carry-forward aging (flag >3 days), and quality-flag percentage. Surface declining COMPLETE trends to Specialist 16 (Motivation & Momentum). Surface rising quality-flag percentage to Specialist 24 (Superwoman Syndrome) for overcommitment evaluation.

## Procedure

### Daily Setup (1 minute)
1. Open the Completion Tracker  --  a spreadsheet, Notion database, or plain-text file with these columns:

```
| Task ID | Task Description | Started | Est. Min | Actual Min | Status | Block ID | Switches | Quality | Notes |
```

2. Seed with no more than 3 tasks from the day's priority list. More than 3 = you are already multitasking before you start.

### During Work
1. At the start of every focus block (PA-27-01), enter the task in the tracker with a start timestamp.
2. If you switch to another task during a block, increment the Switches counter. Do NOT erase the original task  --  it stays open.
3. At the end of every block, update Actual Min and Status (COMPLETE / PARTIAL / ABANDONED).
4. Add a one-line Note for anything that blocked progress or accelerated it.

### End of Day (3 minutes)
1. Scan today's entries. Count COMPLETE tasks. Count PARTIAL tasks carried forward.
2. For any PARTIAL task: write tomorrow's first block outcome using the PA-27-01 format.
3. For any ABANDONED task: decide  --  kill it permanently, delegate it, or promote it to tomorrow with a new approach.
4. Mark the quality flag (✓/✗) for each COMPLETE task based on whether the output met the standard.

## Edge Cases

- **Task exceeds estimate by >50%:** Flag it. At weekly review, investigate: bad estimate, scope creep, skill gap, or the wrong task entirely?
- **Task completed but quality is poor:** Mark COMPLETE but set quality flag to ✗. Track quality-flags over time  --  if >20% of completions are flagged, root cause is upstream (unclear requirements, wrong person, insufficient resources).
- **Zero completions in a day:** Do not shame yourself. It's data. Ask: were tasks too large? Too many switches? Insufficient block protection?

## Integration Points
- Feeds PA-27-05 (Weekly WIN Accounting) for pattern analysis.
- Feeds PA-27-03 (Multitasking Audit)  --  the Switches column is direct input.
- Complements PA-27-01 (Focus Block Setup)  --  each block produces one tracker row.

## CTQ (Critical to Quality)  --  Binary Checks
- [ ] Tracker seeded with ≤3 priority tasks before the first block of the day
- [ ] Every focus block produces one tracker row with start time, actual minutes, status, and quality flag
- [ ] End-of-day scan completed: COMPLETE count logged, PARTIAL tasks assigned tomorrow's first block
- [ ] ABANDONED tasks have an explicit disposition (kill, delegate, or promote with new approach)
- [ ] Quality flag marked for every COMPLETE task; >20% flagged triggers root-cause review

## Metrics
| Metric | Target |
|---|---|
| Daily tasks logged vs. tasks worked | 100% |
| PARTIAL tasks carried forward >3 days | 0 |
| End-of-day scan completed | 100% of working days |
| Quality flag rate | ≤ 20% |

## Escalation
If any task exceeds 2× original estimate on 3+ consecutive entries, escalate to Specialist 24 (Superwoman Syndrome) for scope-creep and overcommitment pattern evaluation. If zero COMPLETE tasks for 2+ consecutive days, escalate to Specialist 09 (Emotional Support & Wellbeing) for depletion assessment. If the tracker is abandoned for 5+ working days, notify Master Orchestrator.

## Definition of Done
Task Completion Tracking is complete for the day when all blocks have logged rows with statuses and quality flags, the end-of-day scan has assigned tomorrow's first block for every PARTIAL task, and any task carried forward beyond 3 days has been triaged.

## Tone & Persona Note
Data over drama. The tracker is a mirror, not a report card  --  it reflects what happened without judgment. {{TOKEN}} should feel curious, not shamed, when reviewing it. "The tracker doesn't measure your worth. It shows where your attention went  --  so you can decide where you want it to go tomorrow."

## References
- Zeigarnik, B. (1927). Das Behalten erledigter und unerledigter Handlungen. *Psychologische Forschung*, 9, 1–85.
- Rubinstein, J. S., Meyer, D. E., & Evans, J. E. (2001). Executive control of cognitive processes in task switching. *Journal of Experimental Psychology: Human Perception and Performance*, 27(4), 763–797.
