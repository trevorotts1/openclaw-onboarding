# ZHC Tag-Prefix Protocol — Step 9.42

A single, universal rule for every tag the agent creates programmatically.

## The rule

**Every tag the agent creates PROGRAMMATICALLY must be prefixed `ZHC-`.**

When the agent creates a tag itself — via the GHL skill's `create_tag` method or the
fallback `POST /locations/{locationId}/tags` (the mechanism documented in
`conversation-workflows-protocol.md` Section D.1 and `references/workflow-ai-instructions-standard.md`
Section 6) — the tag name MUST carry the `ZHC-` prefix. Examples:

- `ZHC-tension-detected`, `ZHC-aggression-detected` (F50)
- `ZHC-interrupt-handled`, `ZHC-faq-detoured`, `ZHC-aggression-handled-and-resumed` (F44)
- `ZHC-out-of-service-area`, `ZHC-service-area-confirmed`, `ZHC-service-area-flexible` (F45)
- `ZHC-faq-answered` (F47)
- `ZHC-bot-suspected` (the bot-detection tag, going forward — see below)
- workflow tags the agent creates (e.g. `ZHC-pricing-interest`, `ZHC-discovery-scheduled`)

This makes every agent-created tag instantly distinguishable from tags the operator or the
GHL platform created, so the operator can audit, filter, and trust the agent's tagging.

## REUSE the existing tag-creation mechanism

This rule does NOT introduce a new tag API. It REUSES the existing programmatic
tag-creation path (D.1 + Section 6). The ONLY change is enforcing the `ZHC-` prefix on the
NAME the agent passes to `create_tag` / the tags endpoint.

## NOT retroactive

This is **not retroactive**. The agent does NOT rename existing tags, does NOT touch tags
the operator created, and does NOT re-tag historical contacts. The rule applies to tags the
agent creates GOING FORWARD. Tags referenced in a Build-with-AI prompt that the OPERATOR
already created keep their existing names — the agent only prefixes the ones IT creates.

The one continuity note: the long-standing bot-detection tag (`bot-detected` in
`conversational-safeguards.md` Safeguard 3) is, going forward, created as `ZHC-bot-suspected`
when the agent newly creates it. Existing `bot-detected` tags are left as-is (not
retroactive); both are honored at read time.

## Companion: programmatically created CRM custom FIELDS use `ZHC_`

The field-name analogue (F46, `crm-field-write-protocol.md`): custom fields the agent
creates programmatically carry the `ZHC_` prefix (underscore, GHL field-key convention).
Same intent — instant distinguishability — different separator because GHL field keys use
underscores while tags use hyphens.

## MEMORY.md (Rule 20)

See MEMORY Rule 20 — the canonical statement of this rule, appended by
`scripts/06-append-memory-rules.sh`.

## AGENTS.md tag-creation behavioral note

See the `SKILL38_ZHC_TAG_PREFIX` marker block (AGENTS.md, inserted by
`scripts/05-update-agents-md.sh`).
