# CORE_UPDATES - Self-Improving Agent

## Rule
Apply updates only to relevant core files for this skill.
Do not update unrelated core files.

## Relevant (update allowed)
- AGENTS.md
- TOOLS.md
- MEMORY.md

## Optional (only if explicitly needed)
- SOUL.md

## Non-relevant (do not edit)
- USER.md
- IDENTITY.md
- HEARTBEAT.md

## Suggested snippets
### AGENTS.md
- Add a short rule that this skill must pass TYP before execution.
- Add skill-specific trigger/use statement.

### TOOLS.md
- Add only tool commands/endpoints this skill needs.

### MEMORY.md
- Add only persistent facts and constraints learned from this skill.

### USER.md
- Update only when this skill needs user preferences or user-specific routing.
