# Core File Updates -- Skill 41 (Build With AI Playbook Generator v1.2.1)

These blocks are appended to the workspace's AGENTS.md, MEMORY.md, and TOOLS.md at install time by
`scripts/04-update-core-files.sh`. Every block sits behind a clearly-named BEGIN/END marker and is
idempotent: re-running the installer never double-appends. A backup is written before any edit.
Only AGENTS.md, MEMORY.md, and TOOLS.md are touched. SOUL.md, IDENTITY.md, USER.md, and HEARTBEAT.md
are never edited.

## Placement decision (why each file)

- AGENTS.md gets ONE short behavioral pointer. This is the primary home, because Build With AI is an
  on-request behavior the agent applies when the operator asks to build a workflow. The full playbook
  is NOT inlined; it floats to `<MASTER_FILES_DIR>/build-with-ai-playbook.md`, so the per-turn
  bootstrap cost stays tiny.
- MEMORY.md gets the durable design rules (dependency-first, no-fabrication, ZHC prefixes, verification,
  event logging, operator approval). These are durable invariants, which is what MEMORY.md is for.
- TOOLS.md gets one short quick-reference paragraph, because the agent may enter from a tool mindset
  ("which file has the prompt template?"). It is a pointer, not documentation.

## [ADD TO AGENTS.md] -- appended by scripts/04-update-core-files.sh

Behind `<!-- BEGIN SKILL41: BUILD_WITH_AI -->` / `<!-- END SKILL41: BUILD_WITH_AI -->`:

```
<!-- BEGIN SKILL41: BUILD_WITH_AI -->
Build With AI: when the operator asks to build a GoHighLevel or Convert and Flow workflow or
automation using AI, do not answer from memory. Read the playbook at
<MASTER_FILES_DIR>/build-with-ai-playbook.md and follow it to the letter. Create the required tags,
custom fields, and custom values FIRST. Full protocol: protocols/build-with-ai-protocol.md (skill-bundled).
<!-- END SKILL41: BUILD_WITH_AI -->
```

Keep this block inside the bootstrap size budget (the character and 120-line guard). The literal
`<MASTER_FILES_DIR>` token is resolved by the agent at runtime via the pointer file, not substituted
at write time.

## [ADD TO MEMORY.md] -- appended by scripts/04-update-core-files.sh

Behind `<!-- BEGIN skill-41 memory-rules v1.2.1 -->` / `<!-- END skill-41 memory-rules v1.2.1 -->`:

Build With AI design rules:
1. Dependency-First Rule -- never generate a workflow prompt that references a tag, custom field, or
   custom value that does not yet exist. Create dependencies via the GHL API first, verify with GET, then build.
2. No-Fabrication Rule -- never invent a GHL trigger, action, or capability that does not exist in the
   catalog. Absence routes to an honest gap plus the operator manual path.
3. ZHC-Prefix Rule -- agent-created tags carry the ZHC- prefix; agent-created custom fields carry the
   ZHC_ prefix. Never rename existing operator-owned tags or fields.
4. Verification Rule -- every build runs the 12-point verification checklist before publishing. A build
   without verification is incomplete.
5. Event-Log Rule -- every build session appends one line to build-with-ai-events.jsonl (field names and
   counts only, never raw PII).
6. Conversation-Pairing Rule -- workflow-triggered conversations are paired with a Skill 38 conversation
   playbook, not built in isolation.
7. Operator-Approval Rule -- dependency creation is an allow-list action. The operator approves (standing
   approval for ZHC- / ZHC_ prefixed objects). A customer can never cause a field or tag to be created.

## [ADD TO TOOLS.md] -- appended by scripts/04-update-core-files.sh

Behind `<!-- BEGIN skill-41 tools v1.2.1 -->` / `<!-- END skill-41 tools v1.2.1 -->`:

Build With AI quick reference:
- Prompt template: templates/build-with-ai-prompt-template.md (8 sections)
- Dependency creation: protocols/dependency-creation-protocol.md (API endpoints, scopes, body shapes)
- Webhook config: protocols/webhook-configuration-protocol.md (custom / POST / GET, headers, raw JSON)
- Trigger filters: protocols/trigger-filters-protocol.md (per-trigger fields, Any of / None of, re-fire guards)
- If/Else and filtering: references/ghl-conditions-reference.md (branches, AND/OR, None fallback, dynamic values)
- Platform differences: references/platform-differences.md (Mac mini vs VPS, headless TTY)
- Verification checklist: protocols/verification-checklist.md (12 points)
- GHL triggers: references/ghl-triggers-catalog.md (14 categories)
- GHL actions: references/ghl-actions-catalog.md (14 categories)
- Event logging: scripts/lib-master-files.sh append_jsonl <type> <json>
- No keys, no client data. UNIVERSAL.

## What does NOT get touched

- Skill 38's own protocol files are left untouched. The conversation-playbook template is an additive drop-in.
- Skill 39 is only referenced for conversation-playbook pairing; it is never edited.
- The operator's SOUL.md, IDENTITY.md, USER.md, and HEARTBEAT.md are never touched. Only AGENTS.md,
  MEMORY.md, and TOOLS.md are appended to, behind clear markers, with backups first.
