# Changelog — Cinematic and Web Funnel Engine (Skill 62)

## 1.0.0 — 2026-07-15

Initial skeleton (build unit U2, branch `skill62/cinematic-engine`).

Added:

- `SKILL.md` with frontmatter `name`/`description`/`version: 1.0.0`.
- `skill-version.txt` (`1.0.0`, lockstep with frontmatter per
  `scripts/qc-assert-skill-frontmatter-version.sh`).
- `CWFE-MANIFEST.json` — the P0-P16 phase spine (17 phases) and 22 `AF-CWFE-*` autofail
  codes (17 per-phase + 5 cross-cutting: front-door, paid-gate, restart-duplicate,
  content-duplicate, secret-leak), mirroring the `AF-FUN-*` pattern established in
  `49-signature-funnel/FUNNEL-MANIFEST.json`.
- `cinematic-web-funnel-entry.sh` — fail-closed front door (ADR-6): dependency check,
  version-lockstep check, run-scoped 0600 nonce mint/export, then orchestrator
  invocation. Mirrors the entry-shell pattern of Skills 49 and 56.
- `run_cinematic_web_funnel.py` — manifest-driven, no-skip orchestrator. Refuses to run
  without a nonce matching the front door's nonce file (`AF-CWFE-FRONT-DOOR`); walks
  `CWFE-MANIFEST.json` phases in order; emits `PROCESS-CERTIFICATE.json` only when every
  phase gate passes.
- `MASTERDOC.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `QC.md` (this changelog's siblings).

Not yet included (later build units): phase gate scripts, provider adapters, schemas,
state engine, budget gate logic, content-methodology router, intake, scene/journey
planner, image/video generation flow, FFmpeg pipeline, seam QC, Next.js template, GHL
integration, Vercel deployment adapter, iframe embed package, accessibility/performance
paths, tests, and every registry/department-map registration (`skill-department-map.json`,
`06-ghl-install-pages/funnel-engines/registry.json`, `cc-compat.json`).

## Unreleased — registration wiring (build unit U22, branch `skill62/cinematic-engine`)

Closes the "every registry/department-map registration" gap named in the 1.0.0 entry
above. On-branch only — not merged, not deployed, no version/tag ripple (deferred to
U25/U27 per the ledger). Frontmatter/`skill-version.txt` stay at `1.0.0` (no engine
behavior changed, wiring-only).

Added, in the shared fleet registration files (outside this skill directory):

- `23-ai-workforce-blueprint/skill-department-map.json` — Skill 62 client-facing entry:
  `departments: ["web-development"]`, primary role `funnel-builder-specialist`,
  10 plain-language intent triggers (spec §3.4), `execution_sops: ["funnel-craft",
  "website-craft", "video-pipeline-craft"]`. Closes the orphan check
  (`check-skill-department-map.py`: skill folder 62 existed on disk but was not in the
  map; now 0 violations, 62 skills / 28 client-facing).
- `06-ghl-install-pages/funnel-engines/registry.json` — third STEP-0 funnel-engine
  selector entry (`cinematic-web-funnel-engine`, priority 8, confidence_threshold 0.55),
  following the exact template Skills 49/56 already used. Proven not to hijack ordinary
  funnel/webinar/static requests or the other two engines' explicit names, and to route
  cinematic/animated/immersive/scroll requests correctly (see U22 ledger evidence).
- `cc-compat.json` — standard registration note: NO new Command Center endpoint, NO
  `mission-control.db` schema change, minVersion/pinnedTag UNCHANGED (v4.59.1 / v6.0.2).
- Generated/re-stamped from the map (idempotent, marker-guarded; no hand edits):
  `templates/role-library/web-development/funnel-builder-specialist.md` ("Skills You
  Operate" block), `templates/role-library/web-development/how-to-use-this-department.md`
  ("Skills This Department Can Operate For You" block), and the Intent-triggers headers
  in `universal-sops/funnel-craft/README.md`, `universal-sops/website-craft/README.md`
  (new block), and `universal-sops/video-pipeline-craft/README.md`. Content-hash
  manifests re-stamped clean (`23-ai-workforce-blueprint/scripts/hash-content-manifest.py`,
  `scripts/hash-universal-sops-manifest.py`).

Command Center generic-discovery no-change proof and any justified Command Center
enhancement are separate, later build units (U23/U24) — not part of this entry.

### QC fix — artifact-coverage SKILLS-COUNT gate (post-U22)

An independent QC pass flagged that the artifact-coverage consistency gate
(`23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py --only artifact`,
the `SKILLS-COUNT` dimension, wired as a hard, non-`continue-on-error` step in
`.github/workflows/qc-static.yml`) failed rc=6: `install.sh`'s two "active skill
count" prose statements ("`(56 active + 5 archived)`" and "`The 56 active skills`")
still read 56, while the skill-dir tree has carried 57 active skills since this
unit added the `62-cinematic-web-funnel-engine/` client-facing registration. The
drift pre-dated U22 (present since U2 created the folder) and was not part of this
unit's original "Verified green" evidence list, which was an omission — the
1.0.0/U22 entries above explicitly deferred it as install-wave-sequencing work,
but the gate checks a simple count-of-active-skill-directories fact, unrelated to
which install wave a skill is assigned to.

Fixed: both `install.sh` prose occurrences bumped 56 → 57 (matching the tree and
the already-correct `README.md` count). No install-wave assignment changed —
Skill 62 is still not listed under any `Wave N` section; that remains a later
merge/install unit decision (U25/U27), unchanged by this fix.

Re-verified: `qc-assert-repo-consistency.py` (both the 5-dimension gate and
`--only artifact`) → rc=0, 10/10 artifact dimensions OK; adversarial fixture
suite `test-artifact-coverage.sh` → 10/10 passed; full skill test suite
re-run clean: unit 672/672, integration 44/44, e2e 23/23,
`prove_certificate.py --self-test` → PASS.

## Unreleased — Command Center ZERO-CHANGE discovery proof (build unit U23, branch `skill62/cinematic-engine`)

Proves the spec §2.2 "Default ruling" / §21.2 "Conditional Command Center changes"
requirement: Command Center's existing generic skill matcher (`matchSkillsForTask()`
in `blackceo-command-center/src/lib/context-pack.ts`) discovers and correctly ranks
this engine's real, unmodified, shipped `SKILL.md` with **zero changes to the Command
Center repository**. On-branch only — not merged, no version/tag ripple.

Added:

- `scripts/prove_command_center_discovery.py` — standalone prover (not a
  `CWFE-MANIFEST.json` phase gate; same family as `funnel_engine_selector.py
  --self-test`, U22). `--self-test` runs fully offline (no Node, no network, no
  external checkout). `--cc-repo <path> --run-dir <dir>` is the live mode: builds a
  fixture skill root from this skill's real `SKILL.md` plus two real neighbor skills
  (`49-signature-funnel`, `25-video-creator`) and a real copy of
  `23-ai-workforce-blueprint/skill-department-map.json`, points the operator-supplied
  Command Center checkout at that fixture via its already-documented env overrides
  (`CC_SKILL_ROOTS` / `CC_SKILL_DEPARTMENT_MAP`), and writes
  `cc-discovery-evidence.json` on either outcome. Never clones, assumes, or mutates
  the external repository — the caller supplies a throwaway checkout with its own
  `npm install` already run.
- `scripts/lib/cc_discovery_harness.mjs` — the Node/`tsx` harness the Python prover
  shells out to for live mode. Imports the target checkout's real
  `matchSkillsForTask()` / `renderMatchedSkillsSection()` / `buildContextPack()` /
  `renderContextPackSection()` by absolute path (read-only; never writes under
  `CC_REPO_PATH`) and runs 23 checks: all 10 real spec-3.4 intent triggers surface
  the skill (department-scoped to `web-development`), a keyword-disjoint task returns
  no match, and the strongest positive match round-trips through both the manual-
  dispatch ("SKILLS AVAILABLE FOR THIS TASK" block) and auto-dispatch
  (`buildContextPack`/`renderContextPackSection`) paths with a resolvable on-disk
  `SKILL.md` location. Also records two non-gating, pre-existing, catalog-wide
  observations (not this registration's defect, not asserted pass/fail): the real
  `skill-department-map.json` ships `skills` as an array of skill-record objects,
  a shape `context-pack.ts`'s `loadSkillDeptMap()` doesn't recognize, so department
  scoping is currently a no-op for all ~30 client-facing skills; and the zero-config
  keyword-overlap fallback can co-match genuinely video-adjacent tasks across skills.
- `tests/unit/test_prove_command_center_discovery.py` — 27 fast, fully offline unit
  tests covering `onboarding_repo_root()`, `sha256_file()`, `build_fixture()` (byte-
  identical real-file copies plus three independent fail-closed paths: bogus root,
  missing department map, missing neighbor skill), `validate_cc_repo()`'s five
  fail-closed checks (nonexistent path, missing `context-pack.ts`, missing
  `package.json`, wrong package name, missing `node`/`tsx`) plus one pass-path
  variant, `run_harness()`'s stdout/JSON parsing and pass/fail rollup (driven by a
  fake `subprocess.run`, including an embedding-key env-leak check), and
  `evaluate()`'s usage-error / pass / fail / evidence-write paths.

Verified: `python3 scripts/prove_command_center_discovery.py --self-test` → `RESULT:
PASS` (12 offline checks). Live proof against a fresh, throwaway clone of
`trevorotts1/blackceo-command-center` (`git clone --depth 1`, `npm install`, never
`~/command-center/app`): `python3 scripts/prove_command_center_discovery.py --cc-repo
<throwaway-clone> --run-dir <dir>` → `[PASS] Command Center discovery — 23/23 checks
passed; overall=PASS`; `git status --porcelain` in the throwaway clone confirmed zero
tracked-file changes before and after the run. Full skill test suite re-run clean
with the new tests included: unit 699/699 (was 672), integration 44/44, e2e 23/23.
No Command Center change was made or is justified by this proof — no real gap was
found (spec §2.2 lists the qualifying gap conditions; none apply). Build unit U24
(independent QC) and any separately-justified Command Center enhancement (U25 per
the checklist's item 25, deferred unless a future unit proves a real gap) are not
part of this entry.
