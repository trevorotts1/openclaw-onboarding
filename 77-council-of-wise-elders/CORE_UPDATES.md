# Council of Wise Elders (77): Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

These payloads are applied by the existing idempotent core-update merger
(update-skills.sh wire_core_updates), which wraps each appended block in
<!-- BEGIN skill:77-council-of-wise-elders:<target> --> and
<!-- END skill:77-council-of-wise-elders:<target> --> markers and stamps
the sentinel <!-- skill:77-council-of-wise-elders:core-update-applied -->
into AGENTS.md. Do NOT paste the block by hand, and never overwrite a
whole core file for this skill.

The AGENTS.md block is deliberately short: it carries the front-door
phrases, the existing-session rule, the advice-versus-authorization
boundary, and the label discipline, then points at this skill's files
for the full protocol. Long council knowledge lives in this skill's
references, never in a core file.

---

## AGENTS.md - UPDATE REQUIRED
<!-- skill:77-council-of-wise-elders:core-update-applied -->

Add:

```
## Council of Wise Elders (77)
When the client says "Ask my Council of Wise Elders", "Take this decision to the council", "Review this plan with the council", or asks for a named seat ("Ask the Tiffany Aliche seat"), use Skill 77 (77-council-of-wise-elders): read its SKILL.md and references/protocol.md first. Resolve existing-session controls before creating new work: "Stop that council" acts on the existing session, "What did they decide?" is a read of the stored verdict. A council result is advice, never execution permission: preview, approval, task creation, and execution authorization are separate steps. Every seat is an AI perspective, labeled exactly "AI perspective inspired by the published work of [name]. Not the individual and not an endorsement." Never present a seat as the real person, and never invent quotations.
Trigger records (CWE-037): when a council session's work completes, the completion scan enqueues follow-up candidates onto the session's scan queue with their source session recorded; processing a scan item creates at most a proposal, never a task, and every enqueue is journaled, never silent. Council-generated work is tagged with its source session: the council capability cannot invoke itself from its own drafts, approvals, or outcome reminders, and a council-generated action cannot trigger another council without a separately authorized need. Scheduled outcome reviews are deduplicated by decision and review period. Department and CEO requests that route to the council preserve their source department and task references; a rerun never inherits the original approval.
```

---

## TOOLS.md - NO UPDATE NEEDED
This skill registers no tools of its own at this stage. Its scripts are
invoked by path from the skill folder during install and QC only.

## MEMORY.md - NO UPDATE NEEDED
Council state is not memory. Sessions, briefs, and verdicts live in the
authoritative council store for the installation's chosen mode (managed:
the Command Center database; standalone: the per-user council database
outside the skills tree), never in MEMORY.md and never inside the skill
folder.

## SOUL.md - NO UPDATE NEEDED

## IDENTITY.md - NO UPDATE NEEDED

## USER.md - NO UPDATE NEEDED

## HEARTBEAT.md - NO UPDATE NEEDED
Scheduled council reviews are created only through the council's own
authorized review mechanism, deduplicated by decision and review period,
so the council can never retrigger itself from a heartbeat.
