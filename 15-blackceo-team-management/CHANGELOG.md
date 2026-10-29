# Changelog - BlackCEO Team Management

All notable changes to this skill wrapper are documented here.

---

## [7.1.8] - 2026-10-29

### Fixed - REMOTE RESCUE INSTALLER ON A BOX WITH A BELOW-FLOOR NODE FIRST ON PATH

- Defect (Big Fleet Roll 20261029, a Mac on OpenClaw 2026.10.8): with a below-floor node first on PATH, every `openclaw` call prints `openclaw: Retrying with "<cli-node>/node" (cached OpenClaw runtime; current Node failed runtime admission).` on stderr. `scripts/lib/rr-validate-candidate.sh` ran `openclaw config validate --json` with `2>&1` and parsed the whole text as one JSON document, so a VALID candidate (`{"valid":true,...,"warnings":[]}`) was classified `candidate-invalid` and refused (state `refused`, installer exit 4, live config untouched). `update-skills.sh` then withheld the skill's `.wired` sentinel.
- Fix, `scripts/lib/rr-validate-candidate.sh`: stdout and stderr are captured apart and the verdict is the last JSON object that carries a `valid` key, so runtime-retry preamble lines on either stream are ignored. Still fail-closed: no verdict, a non-zero exit, or no `openclaw` on PATH is a refusal, and the refusal detail never quotes the retry line.
- Defect, same run: `Routing acceptance BLOCKED: no installed OpenClaw resolver found` although `<prefix>/lib/node_modules/openclaw/dist/plugin-sdk/routing.js` existed. The resolver search used `npm root -g`, which answers for whichever node is first on PATH, not for the package that holds the `openclaw` binary.
- Fix, `scripts/install-remote-rescue.sh`: the search now starts from the package directory of the `openclaw` binary on PATH (symlink followed), then `OPENCLAW_ROUTING_MODULE`, `npm root -g`, and the fixed prefixes, now including `/opt/homebrew/lib/node_modules`. A box with no resolver is still reported BLOCKED.
- Test: `tests/unit/skill15-cli-preamble.test.sh` (10 checks): retry line on stderr and on stdout, an invalid verdict, no verdict, a non-zero exit and an absent `openclaw` (all still refused), and two end-to-end installer runs (candidate promoted with the retry line present; resolver found when `npm root -g` names another root, with a BLOCKED control). Checks 1, 2, 4, 6 and 7 fail on 7.1.7.
- skill-version v7.1.7 -> v7.1.8.

## [7.1.7] - 2026-10-13

### Changed - model doctrine cleanup

- Cost strategy and the tier chains no longer prescribe named models. Each tier resolves to the model the client selected for that tier, or the client's configured default model. Recommendations survive as guidance where a genuine rationale exists (a heavyweight model for hard reasoning, a fast model for quick tasks). Runtime resolution through select_model.py is unchanged.
- skill-version v7.1.6 -> v7.1.7.

## [7.1.6] - 2026-10-12

### Fixed - REMOTE RESCUE WORKSPACE SEED (RRS001)

- The installer created `workspaces/remote-rescue` empty. OpenClaw then filled it with blank starter files and a `BOOTSTRAP.md` birth script on the first operator DM, and the agent reported the owner's workspace as unconfigured because it only looked in its own folder.
- `seed_workspace()` in `scripts/lib/rr-config-transaction.py` seeds `IDENTITY.md`, `SOUL.md`, `AGENTS.md`, `TOOLS.md` from `templates/remote-rescue/` when the file is absent, empty or still OpenClaw starter text, names the owner's main workspace by absolute path, and removes an untouched template `BOOTSTRAP.md`. Never overwrites a file with real content. `--check` is read-only and reports `seed-needed`.
- New QC gate (`qc-blackceo-team-management.sh`, `QC.md` 7C2). Test: `tests/unit/skill15-workspace-seed.test.sh`.

---

## [7.1.1] - 2026-09-17

### Fixed - DOCS (roster key naming)

- `SKILL.md` described the `remote-rescue` agent as living in `agents.list`, the legacy array
  form only. `qc-blackceo-team-management.sh` has accepted both the `agents.entries{}` map form
  and the legacy `agents.list[]` array form since the entries/list split, so the doc named only
  half of what the gate checks and read as a hard requirement for the legacy shape. Both
  occurrences (the Layer 2 isolation description and the "what breaks isolation" bullet) now
  read `agents.entries` (or legacy `agents.list`).
- Documentation only. The QC script, the `remote-rescue` requirement and the installer are
  unchanged.

---

## [7.0.0] - 2026-07-17

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

## [v7.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
