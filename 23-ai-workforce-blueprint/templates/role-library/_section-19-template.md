# Section 19 Template — When to Spawn a Sub-Specialist

Every how-to.md must end with this section. The standard work + 3-5 named sub-specialists make the role architecturally extensible.

## Verbatim template to include in every how-to.md

```markdown
## 19. When to Spawn a Sub-Specialist

This role can delegate to sub-specialists for tasks requiring deeper domain
expertise. Sub-specialists are spawned on demand (not full-time agents) and
inherit this role's identity + any assigned persona for the duration of the task.

### Common sub-specialists for this role

| Sub-specialist | When to spawn | Example task | Typical duration |
|---|---|---|---|
| {{SUB_1_NAME}} | {{SUB_1_TRIGGER}} | {{SUB_1_TASK}} | {{SUB_1_DURATION}} |
| {{SUB_2_NAME}} | {{SUB_2_TRIGGER}} | {{SUB_2_TASK}} | {{SUB_2_DURATION}} |
| {{SUB_3_NAME}} | {{SUB_3_TRIGGER}} | {{SUB_3_TASK}} | {{SUB_3_DURATION}} |

### How to spawn

\`\`\`python
from openclaw_subagent import spawn

result = spawn(
    sub_agent_type="sub-specialist",
    parent_role=__file__,  # this role's how-to.md path
    sub_specialty="<sub-specialist name from table above>",
    persona_inherited=current_persona,
    context_files=[
        "MEMORY.md",  # this role's memory
        "AGENTS.md",  # workspace tools
        # plus any task-specific context
    ],
    timeout_seconds=1800,
    return_to="MEMORY.md",  # sub-specialist appends learnings here
)
\`\`\`

### Persona inheritance

The sub-specialist inherits whatever persona is currently governing this role's
task. The Persona Governance Override (Section 2) applies — the sub-specialist
acts AS that persona for the duration of its work. When it finishes, its output
is reviewed by this role before shipping.

### Owner-discoverable sub-specialists (promotion rule)

If this role frequently spawns the same sub-specialist (>10 times in 30 days),
flag it for promotion to a permanent specialist in this department's roster. The
Department Director surfaces this in the weekly review. This keeps the org chart's
standing roster lean while letting it grow organically as real demand emerges.
```

## Examples of named sub-specialists by role

Writers can pull from these patterns when generating Section 19 for a specific role:

| Role | Likely sub-specialists |
|---|---|
| Email Deliverability Specialist | Crisis Email Response Specialist, Domain Reputation Investigator, Blacklist Delisting Specialist, IP Warmup Coordinator |
| Director of Marketing | Brand Crisis Specialist, Campaign Postmortem Analyst, Competitive Counter-Move Specialist |
| Director of Sales | Pipeline Forensics Specialist, Deal Resurrection Specialist, Quarterly Forecasting Analyst |
| CRM Platform Administrator | Data Migration Specialist, Custom Field Architect, Integration Debugger |
| Master Orchestrator (CEO) | Strategic Postmortem Analyst, Cross-Department Conflict Mediator, Board Briefing Specialist |
| SEO Specialist | Penalty Recovery Specialist, Schema Markup Specialist, Local SEO Specialist |
| Web Security Specialist | Incident Response Specialist, Pentest Coordinator, Compliance Audit Specialist |
| Tier 1 Support | Escalation Triage Specialist, Refund Negotiator, Voice-of-Customer Synthesizer |

## QC enforcement (Dimension 10)

- ≥3 named sub-specialists listed → required for full score
- Each sub-specialist has all 4 sub-fields: name, when, example task, duration
- Spawn mechanism snippet included
- Persona-inheritance paragraph included
- Promotion rule included
