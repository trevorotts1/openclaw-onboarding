# Tag Migration Notes — ZHC Tag-Prefix Rule (optional, operator-driven)

This is the migration reference for the **ZHC Tag-Prefix Rule**
(`protocols/zhc-tag-prefix-protocol.md`). It documents how legacy / bare
agent-created tags map to their `ZHC-` equivalents, so an operator who *wants*
a tidy, fully-namespaced GHL tag list can optionally clean up after the fact.

## The rule is NOT retroactive

The ZHC Tag-Prefix Rule governs only **NEW** programmatic tag creation from this
version forward. It does **not** rename, merge, or delete any tag that already
exists in the GHL location. There is **nothing the operator is required to do** —
existing tags keep working, and at read time the agent honors both the legacy
bare form and the `ZHC-` form (see the bot-detection continuity note in the
protocol).

This file exists only for the operator who *chooses* to consolidate their
historical tags into the `ZHC-` namespace for a cleaner Settings → Tags view.
**It is optional and operator-driven.** Skipping it is fully supported.

## Why migration is optional (and usually unnecessary)

- The agent never re-creates an existing tag, so no duplicates are minted by
  leaving legacy tags in place.
- Going forward, every agent-created tag already lands in the `ZHC-` namespace,
  so the "which tags did the AI make?" question is already answered for all new
  tags without touching old ones.
- GHL tag renames cascade to every contact, workflow filter, and automation that
  references the tag — a non-trivial, account-wide change the operator should own
  deliberately, not something the agent does on its own.

## Mapping table — legacy bare tag → `ZHC-` equivalent

Use this only if you are doing an optional manual cleanup. For each row: in GHL
**Settings → Tags**, rename the legacy tag to its `ZHC-` equivalent (GHL renames
in place and updates all references), OR create the `ZHC-` tag and bulk-move
contacts, then archive the legacy tag.

| Legacy / bare tag (pre-rule) | `ZHC-` equivalent (current) | Source feature |
|---|---|---|
| `bot-detected` | `ZHC-bot-suspected` | F50 / conversational-safeguards Safeguard 3 |
| `stalled-sales` | `ZHC-stalled-sales` | F29 / intelligent-followup + sales-best-practices |
| `cold-lead-released` | `ZHC-cold-lead-released` | F29 / intelligent-followup (T10 release) |
| `followup-opted-out` | `ZHC-followup-opted-out` | F29 / intelligent-followup (negative signal) |
| `pricing-interest` | `ZHC-pricing-interest` | conversation-workflows §D.1 example |
| `discovery-scheduled` | `ZHC-discovery-scheduled` | conversation-workflows §D.1 example |
| `buyer-lead` | `ZHC-buyer-lead` | real-estate journey / Skill 39 |
| `seller-lead` | `ZHC-seller-lead` | real-estate journey / Skill 39 |
| `listing-alert-engaged` | `ZHC-listing-alert-engaged` | real-estate journey (Skill 38) |
| `showing-confirmed` | `ZHC-showing-confirmed` | real-estate journey (Skill 38) |
| `offer-active` | `ZHC-offer-active` | real-estate journey (Skill 38) |
| `under-contract` | `ZHC-under-contract` | real-estate journey (Skill 38) |
| `closed` | `ZHC-closed` | real-estate journey (Skill 38) |
| `post-close-nurture` | `ZHC-post-close-nurture` | real-estate journey (Skill 38) |
| `sphere-reactivation` | `ZHC-sphere-reactivation` | real-estate journey (Skill 38) |

> **Add your own rows.** Any other tag the agent created in your account before
> this rule shipped follows the same shape: `your-tag` → `ZHC-your-tag`
> (lower-kebab, `ZHC-` prefix). Tags YOU created by hand stay exactly as they are —
> never migrate operator-owned tags into the `ZHC-` namespace.

## What NOT to migrate

- **Operator-owned tags** (anything you or another tool created by hand, e.g.
  `vip`, `newsletter`, pipeline-stage tags you manage) — leave them untouched.
  The `ZHC-` namespace is reserved for tags the AI minted on its own.
- **Tags currently referenced by a live "does not contain" workflow filter** —
  rename the tag and the filter together so you don't strand contacts mid-flow.

## After an optional cleanup

If you do migrate, re-run a spot check in GHL: filter contacts by the old tag
(should be empty if you renamed in place) and confirm the matching workflows now
reference the `ZHC-` form. No agent restart is required — the agent reads tags by
name at runtime.
