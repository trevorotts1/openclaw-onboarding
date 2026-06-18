# TEAM_CONFIG.md - Routing Configuration
# Generated during setup. Edit to update routing.
#
# CO-MINGLING GUARD (v12.4.0): a CLIENT box ships REPLY-TO-SENDER + OWNER-ONLY.
# The BlackCEO operator team (Trevor / LeAnne / Spaulding) must NEVER be stamped
# here as routable "workers" on a client's `main` agent. Operators get INBOUND
# access via the separate `remote-rescue` agent (Skill 15 Step 0.5) — that is the
# only place operator IDs belong on a client box.

## Owner (the client)

| Telegram ID | Name | Role | Type | Reply To |
|-------------|------|------|------|----------|
| {{OWNER_CHAT_ID}} | {{OWNER_NAME}} | Owner (the client) | Owner | {{OWNER_CHAT_ID}} |

## Notes
- This box serves ONE owner (the paying client). Reply ONLY to the sender.
- Do NOT spawn per-person operator worker lanes. There is no operator team on this box.
- Directed sends are allowed when the owner asks ("send [person] X").
- NEVER proactively message an operator ID from this `main` agent.
- Operator (BlackCEO) INBOUND access is configured separately via the
  remote-rescue agent — operator IDs NEVER appear here as workers.
- Update this file (and openclaw.json allowFrom + WORKFLOW_AUTO.md) if the owner changes.

## OPERATOR BOX ONLY (IS_OPERATOR_BOX=1)
# The multi-member BlackCEO dispatcher roster (one row per operator with a
# worker label) belongs ONLY on BlackCEO's own internal operator box. Do NOT
# materialize it on a client box. See 15-blackceo-team-management/INSTALL.md
# Step 0c.
