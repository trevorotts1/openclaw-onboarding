# Packaging Decision — Skill 75 drama-song-ad-factory

- Unit: W3-02-U3
- Source: directive §2.1 (OpenClaw skill placement and structure), §2.4 (canonical source / release ownership)
- Live repo scanned: `<repo-root>` (origin `https://github.com/trevorotts1/openclaw-onboarding.git`)
- Scan date: 2026-10-07
- Status: builder candidate — no self-approval; verdict left to the judge lane
- Verdict: null (W3-02-U3.builder-evidence.json, `self_approved: false`)

## Decision summary

| Question | Decision | One-line evidence |
|---|---|---|
| Numbering slot | **75 — keep.** Do not renumber to 77. | Live scan: `75-drama-song-ad-factory` already exists; skill-23 map already registers skill `75` slug `drama-song-ad-factory`; slot 76 is `76-local-embedder`; slot 77 free. |
| `.skill` package | **No — do not ship a `.skill` file.** | Skill 74 decision-log D9: no `.skill` package; "the gates do not require one". Live practice: skills 72–76 all omit it. Start Here.md uses optional language ("if one exists"). Install/updater gates do not require presence. |
| `department-wiring/` inside the skill folder | **No — not a packaging requirement.** | Live onboarding root has no `department-wiring/` dir. Department ownership lives in `23-ai-workforce-blueprint/skill-department-map.json`, where skill 75 already has a full entry. Gate `check-skill-department-map.py` exits 0. |
| `universal-sops/` inside the skill folder | **No.** | Live scan: 0 of 76 numbered skill folders contain `universal-sops/`. |

## 1. Current directory scan (live onboarding)

Scan command family: `ls -1` over numbered dirs, `.skill` presence per folder, skill-23 map read, gate script run.

### 1.1 Slot sequence at the end of the numbering run

```text
70-lean-core-file-system
71-blackceo-signature-page
72-motion-video-plus
73-diagnose-explain-fix
74-kie-live-adapter
75-drama-song-ad-factory          <-- this skill, already present
76-local-embedder
```

- Numbered directories on disk: **76** (including archived names)
- Non-ARCHIVED numbered directories: **71**
- Highest occupied slot: **76**
- Slot **77** free (no `77-*` directory)
- `skill-department-map.json` skills list length: **76** (matches disk folder count; gate reports "skill folders on disk: 76")

### 1.2 `.skill` presence (full scan)

- Directories containing a `*.skill` file: **38**
- Directories without: **38**
- Hard split by era: older/mid skills carry `.skill`; recent skills do not.
- Skills **72, 73, 74, 75, 76** — none ship a `.skill` file.
- Skills **66, 67, 68, 70** — do ship `.skill` (pattern varies: `68-kie-audio.skill`, `66-kie-image-1.0.0.skill`).

Live `75-drama-song-ad-factory/` top level (2026-10-07):

```text
DEPENDENCY-MANIFEST.md
SKILL.md
THIRD_PARTY_NOTICES.md
references/          (empty)
scripts/core/        (intake_preflight + control modules + contracts)
skill-version.txt    (v2.3.0)
test-fixtures/       (empty)
tests/               (empty)
```

No `.skill` file. No `department-wiring/`. No `universal-sops/`.

Build-root staging tree `<build-root>/onboarding/75-drama-song-ad-factory/` (this build's owned output root) matches the same packaging shape: manifest notices + `scripts/core/`, empty `references/` `test-fixtures/` `tests/`, no `.skill`.

### 1.3 Department wiring on disk

- Live onboarding root: **no** `department-wiring/` directory
- Only skill folder that contains `department-wiring/` internally: **23-ai-workforce-blueprint** (anthology-engine, podcast-engine wiring artifacts — skill 23's own kit, not a per-skill packaging rule)
- Live gate output (`python3 23-ai-workforce-blueprint/scripts/check-skill-department-map.py`):

```text
role-library version: 26.1.1  live departments: 68  live roles: 538
skills in map: 76  client-facing: 31  infra: 45
skill folders on disk: 76
OK — orphan check PASSED: every client-facing skill resolves to a live department + specialist role.
     Coverage complete (map <-> disk), infra ownership valid, execution SOPs resolve.
rc=0
```

Skill 75 map entry (already present, not written by this unit):

```json
{
  "skill": "75",
  "slug": "drama-song-ad-factory",
  "name": "drama-song-ad-factory",
  "client_facing": true,
  "dept_owner": "video",
  "intent_triggers": ["make me a drama song ad", "produce a drama-song advertisement", "song ad for my product", "create a music-driven ad campaign", "run drama song factory job"],
  "execution_sops": ["video-pipeline-craft"],
  "departments": ["video"],
  "roles": [
    {"dept": "video", "primary": true,  "slug": "video-editor"},
    {"dept": "video", "primary": false, "slug": "head-of-video-production"},
    {"dept": "video", "primary": false, "slug": "storyboard-pre-production-specialist"}
  ]
}
```

## 2. CONTRIBUTING / decision-log text (the discrepancy)

### 2.1 CONTRIBUTING.md (live repo) — reads as if `.skill` were required

`<repo-root>/CONTRIBUTING.md` lines 14–21:

```text
1. **Create the skill folder** with the standard 7-file structure:
   - SKILL.md (overview, prerequisites, reading order)
   - INSTALL.md (step-by-step installation with TYP check block at top)
   - INSTRUCTIONS.md (day-to-day usage after install)
   - EXAMPLES.md (real command examples with expected output)
   - CORE_UPDATES.md (exact text to add to AGENTS.md, TOOLS.md, MEMORY.md)
   - [skill-name].skill (metadata/compressed package)
   - QC.md (verification checklist) - optional but recommended
```

Same file, lines 43–46 — updater scan does **not** depend on `.skill`:

```text
6. **update-skills.sh** (repo root — there is no other updater; the retired
   legacy `update-skills.sh` shim under the `scripts/` directory was deleted outright, OCT4 issue #10) - No edit needed: the skill directory scan uses a
   pure `[0-9]*/` glob (no `seq` range to extend).
```

### 2.2 Skill 74 decision log — explicit "no `.skill`"

`<repo-root>/74-kie-live-adapter/references/decision-log.md` D9:

```text
## D9. No .skill package
- Evidence: skill 73 (minimal legal skill) ships none; the gates do not require one for new skills.
- Safer: fewer stale copies. Rollback: n/a.
```

D11 (department registry shape, same log):

```text
## D11. Registry entry shape
- The department map uses the key dept_owner (not owner). Skill 74 copies the
  66, 67, 68 shape: client_facing false, dept_owner openclaw-maintenance, empty triggers.
```

### 2.3 Start Here.md — operator-facing optional language

`<repo-root>/Start Here.md` line 1376:

```text
**Each skill folder contains some combination of SKILL.md, INSTALL.md, INSTRUCTIONS.md, EXAMPLES.md, CORE_UPDATES.md.** Some skills also include a `[skill-name]-full.md`, a `.skill` package file, an `upstream-original/` subfolder, or additional reference documents. File count varies by skill. If SKILL.md or INSTALL.md is missing from a folder, stop and tell the user before proceeding.
```

Line 1565:

```text
7. Install the .skill package file (if one exists in this folder)
```

Line 1380:

```text
- The .skill file (when present) matches the folder name without the number prefix
```

### 2.4 Installer / updater gates — `.skill` not required

- `install.sh` line 6206 and 6238: file-coverage find uses
  `\( -name "*.md" -o -name "*.skill" \)`. Presence of `.skill` is **optional** in the predicate; a skill with only `.md` files still matches.
- `update-skills.sh`: skill discovery is the pure `[0-9]*/` glob (CONTRIBUTING line 44). No `.skill` existence check.
- Only skill-specific exception found: `03-agent-browser/qc-agent-browser.sh` FAILs if **its own** `agent-browser.skill` archive is missing or stale (skill 03's bundling rule, not a repo-wide rule). No equivalent `qc-75-*` exists in live `75-drama-song-ad-factory/`.

## 3. Discrepancy resolution (explicit)

**Conflict:** CONTRIBUTING's "standard 7-file structure" lists `[skill-name].skill (metadata/compressed package)` alongside files that are unambiguously required (SKILL.md, INSTALL.md, INSTRUCTIONS.md, EXAMPLES.md, CORE_UPDATES.md). Directive §2.1 already flagged this: "The audited Skill 74 decision log and CONTRIBUTING guidance differ on whether a `.skill` package is required. Record the applicable convention and resolve the discrepancy rather than assuming either form is mandatory."

**Resolution — applicable convention is: `.skill` is NOT required for new skills.**

Precedence applied (in order):

1. **Executable gates beat prose checklists.** Installer and updater both work without a `.skill` file (`install.sh` find predicate is OR-shaped; `update-skills.sh` scans `[0-9]*/` only). No gate fails a skill for shipping no `.skill`.
2. **The audited decision log named by the directive governs the disputed item.** Skill 74 D9 is the recorded packaging decision for new skills after the minimal-skill policy (skill 73): no `.skill` package; gates do not require one.
3. **Live practice confirms the log.** Skills 72, 73, 74, 75, 76 all ship without `.skill`. A rule that 76 skills already violate in the most recent five consecutive slots is not the applicable convention.
4. **Start Here.md agrees with the log, not with CONTRIBUTING's checklist shape.** Operator install step is conditional ("if one exists"); naming rule is conditional ("when present").
5. **CONTRIBUTING's checklist item is therefore stale as a *requirement*.** It remains useful as a *naming* convention when a `.skill` file is deliberately produced for a skill that needs one (pattern: skill 03's bundled-archive QC). It is not mandatory for skill 75.

**Skill 75 packaging instruction:** ship without `drama-song-ad-factory.skill`. If a future per-skill QC gate ever requires a bundled archive, generate `[skill-name].skill` from the live folder at that time — do not pre-create a stale copy (D9's stated reason: fewer stale copies).

**Numbering slot resolution — explicit:**

- Directive §2.1: "`NN-drama-song-ad-factory/  # 75 at audited snapshot; recheck before placement… take the next valid canonical slot according to onboarding rules."
- Recheck result: slot **75 is occupied by this skill itself** (live folder + skill-23 map entry skill=`75` slug=`drama-song-ad-factory`). Slot 74 `kie-live-adapter` is occupied (directive's "must be reused" note was about not overwriting 74). Slot 76 is `local-embedder`, a different product.
- Conclusion: **75 is already the canonical slot for this skill.** Rebuilding it at 77 would fork the skill identity, break the existing map entry, and violate "Do NOT rename any folder or file" (Start Here.md line 1381). Build-root staging path `onboarding/75-drama-song-ad-factory/` is correct.
- If a *different, new* skill needed a slot after this audit, the next free canonical slot would be **77**.

**Department-wiring resolution — explicit:**

- Directive §2.1 lists `universal-sops/` and `department-wiring/` under "only if current repo convention requires it."
- Live convention: neither is required inside a skill folder. `universal-sops/` exists once, at the **repo root** (shared craft clusters: `anthology-craft/`, `podcast-craft/`, `funnel-craft/`, … plus `_content-manifest.json`) — it is a shared library, not a per-skill payload; 0 of 76 skill folders embed it. Department ownership is the skill-23 machine-readable map (`dept_owner`, `departments`, `roles`, `intent_triggers`, `execution_sops`); skill 75 is already registered there and the orphan gate is green.
- Build-root `onboarding/department-wiring/drama-song-ad-factory/` (empty staging dir) is **unit W3-02-U4's** owned deliverable path — a workforce-routing document outside the skill folder. It is not evidence that skill folders must embed `department-wiring/`.
- `execution_sops: ["video-pipeline-craft"]` points at the shared craft-cluster SOP under the skill-23 kit; it does not require a `universal-sops/` folder inside 75.

## 4. Canonical source and release mechanism (directive §2.4, recorded here)

| Item | Recorded value | Evidence |
|---|---|---|
| Canonical source (OpenClaw distribution) | Live repo path `75-drama-song-ad-factory/` on `trevorotts1/openclaw-onboarding` | Folder present; SKILL.md frontmatter `version: v2.3.0`; `skill-version.txt` = `v2.3.0` |
| Build staging tree for this build | `<build-root>/onboarding/75-drama-song-ad-factory/` | This unit's owned output root; modules staged by W3-02-U1 |
| Runtime twin (Claude-Nine / Claude Code) | `999-setup/.claude/skills/drama-song-ad-factory/` | Directive §2.2; live 999 skill folder present |
| Release / install mechanism | Repo-root `update-skills.sh` only | CONTRIBUTING lines 43–46: retired legacy updater shim under `scripts/` deleted; scan is `[0-9]*/` glob |
| Department wiring mechanism | `23-ai-workforce-blueprint/skill-department-map.json` + `check-skill-department-map.py` | Gate rc=0; skill 75 entry present |
| Parity enforcement | `tests/distribution-parity/` (unit W3-06) | Live tree `openclaw-onboarding/tests/distribution-parity/` exists |

**Bounded handback (not resolved by this unit — outside owned path `PACKAGING-DECISION.md`):**

- Directive §2.4 asks for `ARCHITECTURE-DECISIONS.md` before coding. Live onboarding root has `VERSION-ARCHITECTURE.md` only — no `ARCHITECTURE-DECISIONS.md`. Owner/orchestrator should open that file or fold §2.4 architecture text into the release docs owned by W3-02-U5. This unit does not write it (exclusive ownership of PACKAGING-DECISION.md only).
- Directive §2.4 also asks for a release manifest (core + adapter versions, schema versions, Command Center API versions, source commits, dependency hashes, third-party notices, migrations/rollback). Partial pieces exist (`DEPENDENCY-MANIFEST.md`, `THIRD_PARTY_NOTICES.md`, `skill-version.txt`); the consolidated manifest is W3-02-U5's INSTALL/skill-version work. Recorded here so the decision lane does not silently own it.

## 5. What this decision does **not** authorize

- No merge to `main`, no push, no fleet install, no skill-count bumps in `Start Here.md` / `install.sh` / `README.md` / `CHANGELOG.md` (those follow CONTRIBUTING when the skill folder content lands).
- No `.skill` file creation.
- No renumber to 77.
- No rewrite of `skill-department-map.json` (entry already present and gate-green).
- No self-approval. Judge lane owns the PASS/FAIL verdict at `evidence/W3-02/W3-02-U3.verdict.json`.

## 6. Repro

Lane evidence and the re-runnable check live in:

```text
<build-root>/swarm-plans/pkg/lanes/W3-02-U3-lane/
```

Run:

```bash
python3 <build-root>/swarm-plans/pkg/lanes/W3-02-U3-lane/check_packaging_decision.py
```

Expected: every claim prints `PASS`; script exit 0. Any `FAIL` means the live repo drifted and this decision must be re-audited before use.
