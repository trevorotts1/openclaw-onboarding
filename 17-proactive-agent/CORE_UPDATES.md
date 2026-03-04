# CORE_UPDATES - Proactive Agent

## Rule
Apply updates only to relevant core files for this skill.
Do not update unrelated core files.

## Relevant (update allowed)
- AGENTS.md
- TOOLS.md
- MEMORY.md
- USER.md
- SOUL.md
- HEARTBEAT.md

## Optional (only if explicitly needed)
- IDENTITY.md

## Non-relevant (do not edit)
- None

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
