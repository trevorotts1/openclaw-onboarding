# PBB-1969 — carriage audit for the T-25 wire rebuild (old branch vs origin/main)

Unit: PBB-1969 (lane `PBB-1969-lane`). Supersedes the audit that flagged the earlier
`pb/PBB-1360/t-25-wire-rebuild` rebuild as dropping prior work.

| Item | Value |
|---|---|
| Old work (source) | `backup/cc-pin-1360-pre-rebuild` tip `ea361fa8601939879c5132cae771a8684a60e23d` |
| Broken rebuild | `pb/PBB-1360/t-25-wire-rebuild` tip `4aca0e9c85eaa056663f2e6fe3fa6171bca2cf96` |
| Merge base | `64224e6713acfe68592b84b3f84ba8afdc6be7cd` |
| origin/main at audit | `8cb74925a` (v27.1.67) |
| Commits to carry (`base..old`) | 2 — `92aba1bcb` release v25.2.13, `ea361fa86` fleet-refresh deploy-the-pin |
| Denominator (added lines of `git diff -U0 base old`) | **236** across 86 files |
| Carried into the new tip | **198** |
| Removed deliberately, with reason | **38** |
| Unexplained | **0** |

Carriage: 198 of 236 = **83.90 percent** (eighty-three point nine percent).

## How this number was produced

```
git merge-base --is-ancestor deadbeef origin/main   # control, rc=128 (instrument live)
git fetch origin && git rev-parse origin/main
BASE=$(git merge-base origin/main ea361fa8601939879c5132cae771a8684a60e23d)
git log --oneline $BASE..ea361fa86...
git diff -U0 $BASE ea361fa86... | single-plus lines  # denominator = 236
```

Every added line was then looked up in the same file's blob at the new tip
("identical line present"). Runner: `lanes/PBB-1969-lane/carriage.py` (run-root, not committed).

The instrument is validated against the known-good result: pointed at the broken
rebuild `4aca0e9c8` it reproduces the audited **198 of 236** exactly, and its
38-line missing set is *identical* (0 differences either way) to origin/main's
missing set. The rebuild therefore added nothing that main lacked — the 38 were
absent from both, never destroyed by the rebuild.

## Why the old work is already on main

The behavioural core of `ea361fa86` is present verbatim on origin/main:

| File | Old added lines present |
|---|---|
| `scripts/fleet-refresh.sh` | 6 / 6 |
| `shared-utils/fleet_refresh_runner.py` | 57 / 57 |
| `tests/unit/fleet-refresh-roll-safety.test.py` | 56 / 56 |
| `tests/unit/fleet-refresh-cc-main-convergence.test.py` | 1 / 1 |
| `scripts/test-cc-update-only-credential-and-git-sync.sh` | 30 / 30 |
| `32-command-center-setup/scripts/run-full-install.sh` | 32 / 38 |

## The 38 deliberate removals

### A. Release/pin stamps superseded by a later release on main — 31 lines

`06-ghl-install-pages/SKILL.md:12`, `06-ghl-install-pages/skill-version.txt:1`,
`06-ghl-install-pages/tools/browser_manager.py:62`,
`06-ghl-install-pages/tools/browser_manager.sh:61`,
`23-ai-workforce-blueprint/SKILL.md:19`,
`23-ai-workforce-blueprint/skill-version.txt:1`,
`23-ai-workforce-blueprint/templates/role-library/_index.json:3`,
`32-command-center-setup/SKILL.md:3`, `32-command-center-setup/skill-version.txt:1`,
`cc-compat.json:3`, `cc-compat.json:8`, `cc-compat.json:19`,
`README.md:3`, `README.md:6`, `README.md:12`, `README.md:166`,
`DIRECT-TO-AGENT-UPDATE-MESSAGE.md:16`, `DIRECT-TO-AGENT-UPDATE-MESSAGE.md:18`,
`docs/interview-launch-recovery.md:5`, `install.sh:29`,
`scripts/agent-browser-reaper.sh:67`, `scripts/guard-agent-browser-managed.sh:103`,
`update-skills.sh:17`, `version:1`, `tests/unit/cc-runtime-preflight.test.py:34`,
`CHANGELOG.md:1`, `CHANGELOG.md:4`, `CHANGELOG.md:7`, `CHANGELOG.md:8`,
`CHANGELOG.md:9`, `CHANGELOG.md:10`

Reason (checkable): these lines stamp the release as v25.2.13 / Command Center
v7.6.80 / Skill 32 v13.1.38. origin/main is at `v27.1.67` with
`cc-compat.json.pinnedTag = v7.6.112`. Replaying them verbatim would downgrade
the repo from v27.1.67 to v25.2.13 and move the fleet pin backwards from
v7.6.112 to v7.6.80 — the exact class of defect (a roll deploying a stale
Command Center) that the old commit exists to prevent. `CHANGELOG.md` already
carries its own `## [v25.2.13]` section at line 1415 (merge train #1360, pin
v7.6.85) and `## [v25.2.14]` at line 1397, so the release record is not lost;
`cc-compat.json:19` is a single notes blob whose current value is that older
note plus every later pin note.

Verify: `git show origin/main:version` → `v27.1.67`;
`git show origin/main:cc-compat.json` → `"pinnedTag": "v7.6.112"`;
`git show origin/main:CHANGELOG.md` → line 1415.

### B. Old phase-6 branch superseded by an evolved, stricter implementation — 6 lines

`32-command-center-setup/scripts/run-full-install.sh:2043`, `:2044`, `:2087`,
`:2088`, `:2090`, `:2091`

Reason (checkable): origin/main lines 2382–2406 replace the old
"contains the pin ⇒ skip the deploy" branch with a currency test against the
live origin default branch, and the inline comment at 2383–2388 states why:
treating "contains the pin" as "current" made phase 6 exit 0 on a checkout
still behind origin/main, after which `update-skills.sh` printed
`FATAL ... not current on origin/main` and skipped the Command Center steps.
Carrying the old two lines verbatim re-introduces that bug. The fail-closed
message the old line carried now exists in longer form at 2379, 2405 and 2413.

Verify: `git show origin/main:32-command-center-setup/scripts/run-full-install.sh`
lines 2360–2415.

### C. Comment carrying the old release stamp — 1 line

`update-skills.sh:1966` — `# v25.2.13 - safe_json_edit`

Reason (checkable): origin/main line 2063 carries the same section comment with
the current stamp, `# v27.1.67 - safe_json_edit`. Same content, current version.

Verify: `git show origin/main:update-skills.sh` line 2063.

## Result

No old added line was lost without a stated, checkable reason: 198 present
verbatim in the same file, 38 removed deliberately, 0 unexplained. The tree
delta this unit can add to origin/main is documentation of that reconciliation;
the behavioural work of `ea361fa86` is already on main.
