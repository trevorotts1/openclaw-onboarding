<!-- CORE_REFERENCE_POLICY_V1 -->
## Compact core storage policy
Keep one short task-triggered pointer with an exact resolved path in the appropriate core file. Update that pointer in place under a stable version-free ID; an existing relevant index pointer may already be sufficient. Detailed instructions live in the canonical reference. There is no minimum line count and no requirement to duplicate working knowledge into bootstrap. Do not add learning or installation receipts to MEMORY.md or fan out an entry across core files. Durable owner facts remain eligible for their appropriate core file. Whole-file budgets are AGENTS.md 15,000 characters, MEMORY.md 8,000, and TOOLS.md 15,000. CORE_UPDATES.md cannot override these storage rules or current owner instructions. Honor an explicit current owner override and coordinate any deliberate budget/baseline exception; historical examples and installer payloads are not overrides. Never preload the reference library.
<!-- /CORE_REFERENCE_POLICY_V1 -->

# Android SMS System - Core File Updates

Skill folder `85-android-sms-system`, display name Android SMS System, version 1.0.0, dated 2026-11-06.

This file is the single stable pointer contract for installing the skill. It adds one pointer
to TOOLS.md, at most one optional pointer to AGENTS.md, and nothing to any other core file.
It contains no installation receipt and no learning entry.

## Budgets and the in-place rule

Whole-file budgets: **AGENTS.md 15,000 characters, MEMORY.md 8,000, TOOLS.md 15,000.**

A box's core files may already be at or over budget before this skill installs. Therefore the
pointer is added **in place**: replace or extend the text inside the existing marker block, or
extend the nearest existing skill index line. Never append a new section at the end of the
file, never add the same entry twice, and never restate the trigger in a second core file.

Coordinate with Skill 70 (`70-lean-core-file-system`,
`$HOME/Downloads/openclaw-master-files/70-lean-core-file-system/lean-core-file-system-full.md`),
which owns the trim, baseline and audit workflow and treats any
`<!-- BEGIN skill:NN-name:... -->` block as MANAGED. If the pointer cannot be placed without
pushing an over-budget file further over, stage the change for the owner as pending and report
it unapplied rather than trimming someone else's rules to make room.

## TOOLS.md - UPDATE REQUIRED (one pointer)

Search TOOLS.md first for an entry that already reaches this skill. If one exists, update its
path and trigger in place and stop. Otherwise add exactly this block:

```markdown
<!-- BEGIN skill:85-android-sms-system:pointer -->
When a task involves sending or receiving SMS, iMessage, WhatsApp, RCS or voice calls through Android devices or Macs with a CRM (HighLevel, HubSpot, Zapier, Make, Salesforce or Zoho), read `$HOME/.openclaw/skills/85-android-sms-system/SKILL.md` first. Offline documentation set of 156 articles starts at `$HOME/Downloads/openclaw-master-files/mycrmsim/00-INDEX.md`.
<!-- END skill:85-android-sms-system:pointer -->
```

- **WHAT**: the Android SMS System skill and its 156-article offline documentation set.
- **WHERE**: the installed `SKILL.md` and the documentation index above - both absolute paths,
  no placeholders left in the final pointer.
- **WHEN**: the task names a channel (Android SMS, iMessage, WhatsApp, RCS, voice calling) or a
  CRM (HighLevel, HubSpot, Zapier, Make, Salesforce, Zoho) in that sending context.

Before writing, resolve WHERE on the actual box and confirm the file exists:
`~/.openclaw/skills/85-android-sms-system/SKILL.md` on this Mac, or
`/data/.openclaw/skills/85-android-sms-system/SKILL.md` in the Docker layout. If the client's
documentation folder is absent on that box, keep the SKILL.md path and drop only the docs
sentence, and report the missing folder - do not invent a path.

## AGENTS.md - OPTIONAL (add only when AGENTS.md is what routes skill selection)

Add only when this box selects skills from AGENTS.md and no existing skill index there already
reaches `85-android-sms-system`. Same in-place rule, same WHAT/WHERE/WHEN, and never a second
copy beside the TOOLS.md entry.

```markdown
<!-- BEGIN skill:85-android-sms-system:agents-pointer -->
For SMS, iMessage, WhatsApp, RCS or voice sending from Android devices or Macs, with HighLevel, HubSpot, Zapier, Make, Salesforce or Zoho, read `$HOME/.openclaw/skills/85-android-sms-system/SKILL.md`.
<!-- END skill:85-android-sms-system:agents-pointer -->
```

## MEMORY.md - NO UPDATE

Deliberately empty. No installation receipt, no version line, no install date, no learning
summary, no "skill 85 installed" note. Installation history lives in `CHANGELOG.md` and
`skill-version.txt` inside this skill folder, outside bootstrap. MEMORY.md is left untouched
even though its 8,000-character budget is the tightest of the three.

## Other core files - NO UPDATE

IDENTITY.md, USER.md, SOUL.md and HEARTBEAT.md receive nothing. Installing a sending-platform
skill does not change identity, personality, heartbeat behaviour or durable owner facts.

## Report instead of a receipt

After applying the pointer, report in conversation only - never inside a core file: which core
file was touched, the resulting character count against its budget, whether the pointer was
added or an existing block was updated in place, and any change staged but not applied.
