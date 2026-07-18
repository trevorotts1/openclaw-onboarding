# Changelog - BlackCEO Team Management

All notable changes to this skill wrapper are documented here.

---

## [v6.7.2] - 2026-07-17

### Fixed - PRIVACY (fleet no-client-names invariant)

- CHANGELOG.md and INSTALL.md still carried real personal names and Telegram IDs from the pre-template design (an operator-team member and clients). Replaced with role placeholders ("a client", "Chief of Operations", `{{TEAM_MEMBER_CHAT_ID}}`). This unblocks the fail-closed `qc-assert-no-client-names` gate (PR #612 successor) in local/pre-commit full mode, where the accounts.md-derived roster made these five hits hard-block every commit on the operator box.

---

## [v6.7.0] - 2026-06-15

### Added - OPERATOR/OWNER SESSION ISOLATION

Root cause: `install-remote-rescue.sh` was adding operator IDs to both `allowFrom` AND `groupAllowFrom`, and the `remote-rescue` agent had no `telegram.allowFrom` binding or `workspace` field. This caused operator and owner messages to share the same OpenClaw session (`agent:main:telegram:<chatId>`), so each could see the other's private messages.

**Fix -- three changes to `install-remote-rescue.sh`:**
1. Operator IDs are now STRIPPED from `channels.telegram.groupAllowFrom` (the group-session collision vector). Previous installs are repaired via `--repair` flag.
2. The `remote-rescue` agent now gets a `telegram.allowFrom` binding (listing operator chat IDs) so OpenClaw routes operator DMs to `remote-rescue` before falling back to `main`.
3. The `remote-rescue` agent now gets a dedicated `workspace` path, physically separating its session storage from the `main` agent.

**Resulting session keys (fully disjoint):**
- Owner: `agent:main:telegram:<ownerChatId>`
- Each operator: `agent:remote-rescue:telegram:<operatorChatId>`

**QC enforcement (`qc-blackceo-team-management.sh` v2.0.0):**
Added 5 HARD auto-fail gates that fail QC if:
- `remote-rescue` has no `telegram.allowFrom` binding (unbound stub falls through to `main`)
- `remote-rescue` has no `workspace` field (session storage not isolated)
- Operator IDs are in `groupAllowFrom` (group-session collision)
- Operator IDs are bound to the `main` agent's `telegram.allowFrom`
- `remote-rescue` is missing from `agents.list`

**INSTALL.md, QC.md, SKILL.md:** Updated with isolation verification steps, live-turn test requirement, and documentation of the two-layer isolation model (intra-owner dispatcher/worker vs. operator/owner cross-session).

---

## [v2.0.0] - March 8, 2026

### Changed - STRUCTURAL REWRITE (Template System)
- Removed ALL hardcoded team member IDs, names, and roles from client-facing files.
- Original design referenced real personal names and Telegram IDs (of the operator and of clients) - these are now replaced with configurable placeholders.
- Added Step 0: Team Member Intake - agent collects team data from operator before touching config.
- Added TEAM_CONFIG.md generation step - stores team data in a structured file per deployment.
- SKILL.md: "Three BlackCEO team IDs always present" replaced with "Configure any team size (2-20 members)."
- INSTALL.md: Complete rewrite - hardcoded IDs replaced with intake flow and placeholder syntax.
- INSTRUCTIONS.md: Hardcoded team table replaced with TEAM_CONFIG.md reading instructions.
- EXAMPLES.md: All real person/ID examples replaced with generic placeholders (Alice Johnson, Bob Smith, etc.).
- CORE_UPDATES.md: Rewritten to TYP-lean format. HEARTBEAT.md and USER.md entries removed (not needed).
- blackceo-team-management-full.md: All hardcoded IDs/names replaced with [TEAM_MEMBER_NAME], [TEAM_MEMBER_ID], [ROLE] placeholders.
- Deployment checklist updated: "Add BLACK CEO team IDs" replaced with "Add all team member IDs collected during Step 0 intake."

## [v1.5.0] - March 7, 2026

### Changed
- Converted INSTALL.md to agent-executable, autonomous execution format.
- Ensured TYP guardrails are present: MANDATORY TYP CHECK, CONFLICT RULE, and TYP file storage instructions.
- Fixed isolation rules: context/data isolation only. Communication is allowed when explicitly directed. Removed communication lockdown interpretation.
