# SOPs Mirror -- Director of Quality Control (Q-9.3 System-Wide Quality Rollup)

**Source:** quality-control/director-of-quality-control.md
**Extract:** Section 9 procedure Q-9.3 full text.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated. Never edit this mirror directly.

---

## 9. Standard Operating Procedures (Numbered)

### Q-9.3 -- System-Wide Quality Rollup

**Purpose.** Turn the per-department audits (Q-9.1 procedures, Q-9.2 roles) into one company-wide picture: which departments are real and which are scaffolding, where procedures are mostly under-specified, and what the single highest-leverage fixes are across the whole company. The rollup is what the Master Orchestrator and the owner read to know the true quality state of the machine, and it is what tells the Healer which defects recur across departments so they are healed once at the source.

**The hard rule.** The rollup reports BOTH axes for the whole company and never collapses them. A department's reality score (does its loop run) and its specificity class distribution (are its procedures executable as written) are reported side by side, because a well-wired executor running a thin procedure still produces guessing, and a perfectly specific procedure that nothing ever invokes still does no work. The rollup never reports a single blended "quality number" that hides either axis. Every department figure traces to a per-department scorecard with file-and-line evidence; the rollup adds no claim its source audits did not establish.

**When to run.** Weekly (the Friday rollup) and at the close of every quarterly full census. May be run on demand when the Master Orchestrator asks for the current state.

**Inputs.**
- `working/quality-control/rollup.json` -- the append-only ledger the per-department audits write their counts to (per department: last-audited timestamp, reality weighted score, role class distribution, procedure class distribution).
- `working/quality-control/audits/<department_id>/` -- the per-department scorecards (the evidence behind every figure).
- `working/quality-control/routed/` -- the routed-failure ledger (bug_id per routed failure), so the rollup can report how many failures are open versus healed.
- `python3 23-ai-workforce-blueprint/scripts/list-canonical-departments.py --json` -- the canonical floor, so the rollup can report which in-scope departments have NOT been audited yet (coverage gaps).

**Steps.**
1. **Resolve the scope.** Read the canonical floor to get every in-scope department. Mark any department with no entry in `rollup.json`, or a last-audited timestamp older than ninety days, as a coverage gap; coverage gaps are themselves a finding.
2. **Assemble the reality table.** For each audited department, pull its reality weighted score and classify it: executed (the loop runs, gaps are edge cases), partially wired (some real code, the closing link is missing or manual), or scaffolding (real artifacts, dormant loop). Cite the per-department scorecard for each.
3. **Assemble the specificity distribution table.** For each audited department, pull the role class distribution and the procedure class distribution (counts of under-specified, over-concise, bloated, right-sized). A department whose procedures are mostly under-specified is flagged even when its reality score is high.
4. **Rank the highest-leverage fixes.** Across all departments, collect the single highest-leverage fix named on each failing scorecard. Group recurring fixes (the same defect shape appearing in multiple departments, for example a summarized-away procedure set or a phantom hand-to) so the Healer can heal the pattern once at the source rather than department by department.
5. **Report open versus healed.** From the routed-failure ledger, report how many routed failures are open, how many the Healer has marked fixed, and how many fixes the re-audit has confirmed. A Healer "fixed" that the re-audit has not confirmed is reported as fixed-unverified, not closed.
6. **Write the rollup.** Produce the system-wide rollup document with the reality table, the specificity distribution table, the coverage-gap list, the ranked highest-leverage fixes, and the open-versus-healed counts. Lead with the two or three findings that most threaten the Zero Human Experience (a floor department that is scaffolding; a department whose procedures are mostly under-specified).
7. **Deliver.** Write the rollup to its sink and brief the Master Orchestrator. Hand the grouped recurring patterns to the Healer.

**Outputs.**
- `working/quality-control/rollups/<ISO_DATE>-system-rollup.md` -- the dated system-wide rollup with the reality table, specificity distribution table, coverage-gap list, ranked fixes, and open-versus-healed counts, every figure traced to a per-department scorecard.
- A brief to the Master Orchestrator naming the two or three highest-threat findings.
- A grouped recurring-pattern list handed to the Healer (the Chief Healer for cross-department patterns).

**Hand-to.** The Master Orchestrator (consumes the rollup and the highest-threat brief). The Healer (consumes the recurring-pattern list; the Chief Healer for cross-department patterns).

**Failure mode.** If `rollup.json` is missing or unparseable, do not fabricate a rollup from memory; rebuild the figures by re-reading the per-department scorecards under `working/quality-control/audits/`, and if those are absent, report the rollup as un-producible and trigger the missing audits via the Director's queue rather than reporting a hollow "all green." If a department figure has no backing scorecard, omit it and record the coverage gap; never carry a claim the source audits did not establish. If a routed failure has no bug_id, treat it as a lost report and re-file it before the rollup reports it as routed.

**Generic pass-versus-fail examples (no client names).**
- **PASS.** A weekly rollup reports a sample department as scaffolding (reality weighted score low, loop dormant) with the empty executor grep cited, AND reports a different sample department as fully executed but with a procedure distribution that is mostly under-specified, with the summarized-away findings cited. Both axes are visible; neither hid the other. Coverage gaps and open-versus-healed counts are present.
- **FAIL.** A rollup reports one blended quality percentage per department, so a department with a real loop but mostly thin procedures reads as "healthy" and the under-specification is invisible. This collapses the two axes and is rejected; the rollup is re-produced with both axes reported separately.
- **FAIL.** A rollup reports a department green with no backing per-department scorecard on disk (a figure carried from memory or a stale claim). The figure is removed and the department is recorded as a coverage gap until a real audit produces a scorecard.

**Escalation to the Healer.** The recurring-pattern list IS the escalation: a defect shape that recurs across several departments is filed to the Bugs Department once as a pattern ticket and routed to the Chief Healer, so the fix lands at the source (a shared template, a generator, a master procedure) rather than being routed department by department. The single-department failures continue to route through Q-9.1 and Q-9.2. Quality Control never repairs; it diagnoses, rolls up, and routes.

---

**Enforcement check.** A reviewer can confirm the dated rollup contains both a reality table and a separate specificity distribution table (never one blended number), that every department figure cites a per-department scorecard on disk, that the coverage-gap list reconciles against the canonical floor, and that the open-versus-healed counts reconcile against the routed-failure ledger. A blended single-number report, a figure with no backing scorecard, or counts that do not reconcile is a defect in the rollup and the rollup is re-produced.
