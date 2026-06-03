# PA-27-03  --  Multitasking Audit

**Department:** 27  --  Focus & Completion
**SOP ID:** PA-27-03
**Version:** 1.1
**Last Updated:** 2026-06-03
**Token:** {{TOKEN}}

---

## Objective

Conduct a data-driven audit of multitasking behavior to quantify attention fragmentation, calculate switch-cost losses, and build an anti-multitasking discipline.

## Why This Exists

Multitasking is a lie the brain tells itself. What feels like simultaneous productivity is actually rapid serial task-switching, and every switch exacts a cognitive toll. Rubinstein, Meyer, and Evans (2001) established that task-switching introduces measurable time penalties  --  the brain must unload one task's rules and reload another's, a process that cannot be shortcut. This SOP turns that invisible tax into a visible number so the operator can no longer pretend multitasking is free.

## DMAIC Procedure

### Define
Define a "switch event" precisely: any moment you change applications, tasks, or mental contexts before the current task is marked COMPLETE. This includes checking any communication channel (email, Slack, Telegram, texts), opening an unrelated browser tab, responding to any notification, starting a conversation about a different project, or "just quickly" doing anything that is not the current ONE task. Vagueness is the enemy of measurement  --  if you have to ask "was that a switch?", it was.

### Measure
For one full workday, record every switch event in real time using a physical tally counter (preferred  --  tactile, immediate, impossible to ignore), a simple spreadsheet cell you increment, or the Switches column in the PA-27-02 tracker. Do not judge. Do not try to reduce switches yet. Day 1 is pure measurement  --  observation without intervention. The goal is a clean baseline, not a good-looking number.

### Analyze
Calculate switch cost: total switches × 20 minutes (conservative Rubinstein estimate of deep-focus recovery time per interruption). Compare against your actual completed-task minutes from PA-27-02. Compute your efficiency ratio: completed minutes ÷ (completed minutes + switch-cost minutes). A ratio below 50% means you spent more time switching than completing  --  this is common on first audit and unacceptable to remain at. Then, categorize every switch into one of three buckets: Self-Interrupt (you initiated the break  --  boredom, avoidance, curiosity), External-Interrupt (someone or something triggered it  --  notification, person, alert), or Environmental (physical space broke focus  --  noise, discomfort, hunger). The single largest category is your primary countermeasure target.

### Improve
1. **Category Strike  --  Largest First:** Target the single largest switch category immediately. If Self-Interrupt dominates (>50% of switches), install the PA-27-04 Tier 3 internal discipline countermeasures  --  especially the urge-surfing protocol and scratch-pad capture. If External-Interrupt dominates, harden the PA-27-04 Tier 1 digital fortress and evaluate whether your focus blocks are genuinely being respected by others. If Environmental leads, redesign the physical workspace per PA-27-04 Tier 2 before attempting any behavioral changes  --  environment always beats willpower.
2. **Notification Source Autopsy:** For every External-Interrupt switch, identify the specific source: which app, which person, which device triggered it. Disable notifications from that source permanently  --  not just during blocks, not just for today. If a notification has ever pulled you out of deep focus, it has demonstrated it cannot be trusted with your attention. One notification source disabled = potentially hundreds of future switches prevented.
3. **Self-Interrupt Pattern Map:** For every Self-Interrupt switch, log the exact time and what you switched TO. After one full audit day, patterns will emerge: email checks cluster at 10:15 AM? Social media opens after lunch? These are habit loops, not character flaws. Schedule 5-minute intentional check windows at those exact times  --  the brain tolerates delaying a craving when it knows exactly when gratification will arrive.
4. **Block Integrity Cross-Reference:** Compare your PA-27-01 focus block log against your switch log. For any block that recorded >0 switches, the block was not genuinely protected  --  something broke containment. Identify the specific breach (a notification you believed was off? a person who ignored the door sign? a device you forgot to remove?) and patch that exact gap before the next block. One unresolved breach will repeat across every future block.
5. **Re-Audit Within 5 Business Days:** Repeat the full-day capture after countermeasures are installed. If switch count has not dropped by ≥30% from baseline, the countermeasures were not fully installed or were actively circumvented. Audit the countermeasure installation  --  not the person. A countermeasure you can override in 2 seconds by habit is not a countermeasure; add friction (app blocker, phone lockbox, accountability partner check-in).

### Control
- **Verify:** Weekly re-audit confirms switch count is trending down. Efficiency ratio is calculated fresh each week and compared against the prior week's value. The trend direction matters more than the absolute number  --  two weeks of decline is progress; two weeks of increase is a red flag regardless of the absolute count.
- **Log:** Store each audit's results in a running log (a dedicated sheet or a section of the PA-27-02 tracker): date, total switch count, efficiency ratio, top category, top 3 specific triggers, and countermeasures applied. This creates a visible improvement trajectory.
- **Report:** Monthly trend review: switch-count trajectory, efficiency-ratio trajectory, and persistent top-3 switch triggers. If switch count increases for 2+ consecutive weeks despite full countermeasure installation, escalate immediately. If efficiency ratio remains below 50% after 4 weeks of protocol adherence, escalate for structural review.

## Procedure

### Phase 1  --  Capture (1 full workday)
1. At the start of the day, open a simple counter. Physical tally counter preferred  --  it is tactile and impossible to ignore.
2. Every time you switch tasks before completing the current one, click the counter. This includes:
   - Checking email/slack/telegram mid-task
   - Opening a new browser tab for an unrelated task
   - Responding to a notification
   - Starting a conversation about a different project
   - "Just quickly" doing anything that is not the current task
3. Do not judge. Do not try to reduce switches. Just count. Day 1 is pure measurement.

### Phase 2  --  Calculate (15 minutes at end of audit day)
1. Total switch count: _____
2. Switch cost (switches × 20 min): _____ minutes lost
3. Compare against your PA-27-02 task log: how many minutes of actual completed-task output did you produce?
4. Efficiency ratio = completed-task minutes / (completed-task minutes + switch cost minutes)
5. A ratio below 50% means you spent more time switching than completing. This is common on first audit. It is not acceptable to stay here.

### Phase 3  --  Root Cause (15 minutes)
1. Categorize every switch into one of:
   - **Self-Interrupt:** You initiated the switch (boredom, avoidance, curiosity)
   - **External-Interrupt:** Someone/something else triggered it (notification, person, alert)
   - **Environmental:** Physical environment broke focus (noise, discomfort, hunger)
2. Identify the single largest category. That is your primary target for PA-27-04 countermeasures.

## Edge Cases

- **"But I have to be responsive to clients":** Block time, don't eliminate responsiveness. PA-27-01 defines protected blocks. Outside blocks, responsiveness is fine. The audit reveals whether blocks are actually protected.
- **Audit day was abnormal:** Run a second day. Patterns emerge over 2–3 captures. One weird day is noise; three days is signal.
- **Switch count is zero but nothing got done:** You may be stuck in a single task without progress  --  that is avoidance, not focus. Flag it in PA-27-02 as PARTIAL and investigate.

## CTQ (Critical to Quality)  --  Binary Checks
- [ ] Every switch event recorded in real time for one full workday (no retrospective guessing)
- [ ] Switch-cost calculation completed: total switches × 20 min = attention tax in minutes
- [ ] Switches categorized into Self-Interrupt, External-Interrupt, or Environmental
- [ ] Top category identified as primary target for PA-27-04 countermeasures
- [ ] Block integrity cross-reference completed: any block with >0 switches investigated for containment breach

## Metrics
| Metric | Target |
|---|---|
| Weekly switch count vs. baseline | ≤ 50% of baseline within 4 weeks |
| Sustained switch count | ≤ 5 per day |
| Efficiency ratio (completed ÷ total) | ≥ 70% |

## Escalation
If switch count increases for 2+ consecutive weeks despite countermeasures, escalate to Specialist 09 (Emotional Support & Wellbeing)  --  rising switching may signal avoidance or overwhelm. If Self-Interrupt category dominates at >70%, escalate to Specialist 24 (Superwoman Syndrome) for overfunctioning-pattern investigation. If switch count remains zero but output also flatlines, escalate to Specialist 16 (Motivation & Momentum) for engagement assessment.

## Definition of Done
Multitasking Audit is complete when a full workday of switch events has been captured and categorized, switch-cost has been calculated, the efficiency ratio is computed, the primary countermeasure target has been routed to PA-27-04, and a re-audit date is set within 5 business days.

## Tone & Persona Note
The audit is pure observation  --  think naturalist, not judge. {{TOKEN}} is not "bad at focusing"; her environment and habits have been optimized for interruption without her consent. The audit makes the invisible visible. "This isn't about willpower. It's about seeing the traps so you can disarm them. You're not broken  --  your workspace was built for distraction, and we're rebuilding it for you."

## References
- Rubinstein, J. S., Meyer, D. E., & Evans, J. E. (2001). Executive control of cognitive processes in task switching. *Journal of Experimental Psychology: Human Perception and Performance*, 27(4), 763–797.
