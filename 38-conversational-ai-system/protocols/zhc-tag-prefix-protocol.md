# ZHC Tag-Prefix Protocol — Step 9.42

Every tag the agent creates **programmatically** (via the GHL skill `create_tag`
method, or a direct `POST /locations/{locationId}/tags`) MUST be prefixed
`ZHC-`. This gives the operator a single, unambiguous namespace for "tags the AI
made on its own," cleanly separated from the tags the operator (or other tools)
created by hand.

This protocol does NOT rename or migrate any tag that already exists — it is
**not retroactive**. It governs only NEW programmatic tag creation from this
version forward.

## Scope — what the rule covers

| Situation | Prefix rule |
|---|---|
| Agent creates a tag itself via the GHL skill / API (the CREATE-TAG-FIRST step of a workflow build, an F44/F45/F46/F47/F50 firing, any auto-tag) | **MUST** be `ZHC-…` |
| A tag the OPERATOR already made by hand, or that a customer/3rd-party tool made | left exactly as-is — **never** renamed |
| Applying (not creating) an already-existing tag to a contact | use the existing tag name verbatim — no prefix surgery |
| A tag referenced in a GHL Build-with-AI workflow filter that the agent created first (per conversation-workflows-protocol.md §D.1) | **MUST** be `ZHC-…` (the agent creates it, so it is programmatic) |

The single test is: **"Did the AGENT create this tag?"** If yes → `ZHC-` prefix.
If the tag pre-existed (operator/human/other tool) → leave it untouched.

## Naming form

```
ZHC-<lower-kebab-purpose>
```

Examples (canonical, used across this skill's protocols and references):

- `ZHC-tension-detected` / `ZHC-aggression-detected` (F50, aggression-detection-protocol.md)
- `ZHC-bot-suspected` (F50, the going-forward bot signal — supersedes the legacy `bot-detected` in NEW firings)
- `ZHC-interrupt-handled` / `ZHC-faq-detoured` / `ZHC-aggression-handled-and-resumed` (F44, smart-playbook-switching-protocol.md)
- `ZHC-out-of-service-area` / `ZHC-service-area-confirmed` / `ZHC-service-area-flexible` (F45, geo-qualification-protocol.md)
- `ZHC-faq-answered` (F47, smart-faq-tool-protocol.md)

> CRM custom **fields** the agent creates use the parallel `ZHC_` (underscore)
> prefix (F46, crm-field-write-protocol.md) — fields and tags are different GHL
> objects, so they get visually-distinct prefixes (`ZHC-` for tags, `ZHC_` for
> fields).

## Why

1. **Operator clarity.** One glance at Settings → Tags tells the operator which
   tags the AI minted versus which they created. They can bulk-review, audit, or
   prune the `ZHC-*` namespace without touching their own taxonomy.
2. **Safe automation.** The agent never collides with or overwrites an operator
   tag, because its created tags live in a reserved namespace.
3. **Auditability.** Every JSONL log this skill emits records the exact tag it
   applied; a `ZHC-` prefix makes "the AI did this" greppable end-to-end.

## How the agent applies it (at tag-creation time)

The CREATE-TAG-FIRST mechanism already lives in:
- `protocols/conversation-workflows-protocol.md` §D.1 (the `create_tag` call + the
  `POST /locations/{locationId}/tags` fallback), and
- `references/workflow-ai-instructions-standard.md` §6 (the binding CREATE-TAG-FIRST rule).

This protocol does NOT add a second creation path — it **constrains the existing
one**: whenever the agent reaches that creation step, it prepends `ZHC-` to the
tag name before the `create_tag` / `POST …/tags` call, then references the now-
existing `ZHC-…` tag in the workflow filter / Add-Tag action.

```
# Programmatic creation (the agent made this tag) → ZHC- prefix:
ghl_skill.create_tag(location_id=<LOCATION_ID>, name="ZHC-pricing-interest")

# Applying a tag the operator already created → use it verbatim, no surgery:
ghl_skill.add_tag(contact_id=<CONTACT_ID>, name="vip")   # operator's own tag — untouched
```

## NOT retroactive — bot-detection continuity note

The one continuity note: the long-standing bot-detection tag (`bot-detected` in
`conversational-safeguards.md` Safeguard 3) is, going forward, created as
`ZHC-bot-suspected` when the agent newly creates it. Existing `bot-detected` tags
are left as-is (not retroactive); both are honored at read time.

## Operator-facing note

The agent tells the operator, when it first creates a `ZHC-` tag in their
account:

> "Heads up — tags I create on my own are prefixed `ZHC-` (for example
> `ZHC-pricing-interest`). That keeps my auto-tags clearly separated from the
> tags you made yourself, so you can always tell at a glance which is which in
> Settings → Tags. I never rename or touch tags you created."

## Cross-references

- AGENTS.md tag-creation behavioral note: inserted by
  `scripts/05-update-agents-md.sh` (marker `SKILL38_ZHC_TAG_PREFIX`).
- MEMORY.md Rule 20: appended by `scripts/06-append-memory-rules.sh`.
- Machine-enforced (programmatic tag EXAMPLES use the `ZHC-` prefix) by
  `scripts/qc-zhc-tag-prefix.sh`, wired into `scripts/11-run-qc-checklist.sh` + CI.
