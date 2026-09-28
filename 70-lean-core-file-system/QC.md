# QC Checklist: Lean Core File System (70)

The automated part of this checklist is `qc-70-lean-core-file-system.sh` (exit 0
PASS, 1 FAIL, 2 tooling). The onboarding verification gate runs it with no
arguments. It is read-only toward the box: every test uses throwaway folders
and a fake `openclaw`.

## 1. Purpose
Keeps every core file (AGENTS.md, TOOLS.md, MEMORY.md, USER.md, IDENTITY.md,
SOUL.md) under 40,000 characters by moving situational blocks into one
playbook per system behind one-line pointers, with always-on rules kept
inline, and runs that upkeep weekly as a quiet OpenClaw cron job.

## 2. Package checks (automated)
- [ ] Every shipped file is present (SKILL.md, the full playbook, INSTALL.md,
      INSTRUCTIONS.md, EXAMPLES.md, CORE_UPDATES.md, QC.md, CHANGELOG.md,
      skill-version.txt, lean-core-file-system.skill, wire.sh, scripts/, tests/).
- [ ] Every shell script parses under the current bash and under macOS bash 3.2.
- [ ] CORE_UPDATES.md: AGENTS.md payload is one line, at most two sentences,
      has a WHEN; the AGENTS.md section opens with the gate-visible sentinel.
- [ ] SKILL.md frontmatter `version:` equals `skill-version.txt`.
- [ ] Hard wall: no script line (outside comments) names
      `bootstrapMaxChars` or `bootstrapTotalMaxChars`.
- [ ] No em dashes in the skill's files.

## 3. Audit script battery (automated: tests/test-pointer-audit.sh)
- [ ] Clean fixture: exit 0.
- [ ] Bloat over 40,000: exit 1, SIZE finding, block listed as a candidate.
- [ ] Broken pointer, orphan (not indexed and no pointer), duplicate playbooks,
      pointer without WHEN, unresolved placeholder, missing index: exit 1 with
      the named finding each time.
- [ ] Dry run writes nothing; a normal run writes exactly one report.
- [ ] Backup copies core files, playbooks and a manifest.
- [ ] Proof passes when moved text is in an archive (including when the
      heading stays behind) and fails, naming the paragraph, when it is not.
- [ ] Missing workspace and unknown flags are exit 2 (tooling), never a verdict.
- [ ] Re-running on an unchanged fixture gives identical output.

## 4. Cron installer battery (automated: tests/test-install-weekly-cron.sh)
- [ ] Discovers `ollama/...:cloud` (or `ollama-cloud/...`) primary and
      `openrouter/deepseek/deepseek-v4.1-flash` fallback from the model list,
      including the provider-plus-id list shape.
- [ ] Apply creates exactly one job: isolated session, thinking high, delivery
      none, weekly schedule stored literally, message with every placeholder
      filled.
- [ ] Re-apply makes no add or edit call; check passes.
- [ ] A drifted job is edited in place, never duplicated; duplicates are
      reported (exit 1) and never deleted.
- [ ] Missing, ambiguous, Anthropic or off-list model ids refuse with exit 4
      and create nothing; a missing flag refuses with exit 5; a gateway failure
      is exit 2; a bad argument is exit 3.

## 5. Installer battery (automated: tests/test-wire.sh)
- [ ] Blocks land once, path resolved, no placeholder, existing content kept,
      sentinel stamped, playbook and index installed, backups taken.
- [ ] Re-run is byte-identical and takes no backup.
- [ ] Existing index never overwritten; a stale block is healed in place.
- [ ] The wired workspace passes the audit.

## 6. On a live box (manual, after install)
- [ ] `install-weekly-cron.sh --check` exits 0 (or the refusal reason is
      reported to the operator).
- [ ] AGENTS.md contains the skill-70 block exactly once; MEMORY.md contains
      the "Core files (definition)" block exactly once.
- [ ] `pointer-audit.sh --dry-run` runs and prints the size table.
- [ ] Nothing changed `agents.defaults.bootstrapMaxChars` or
      `agents.defaults.bootstrapTotalMaxChars`.

## Scoring
Sections 2 to 5 are pass or fail (the script). Section 6 passes when every box
is ticked or each unticked box has a named reason reported to the operator.
