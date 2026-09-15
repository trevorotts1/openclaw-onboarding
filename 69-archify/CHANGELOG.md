# Changelog - archify

All notable changes to this skill are documented here.

This file is ONBOARDING-AUTHORED. The upstream project keeps its own release
history at https://github.com/tt-a1i/archify/releases; this changelog records
what the onboarding repo vendored and what the integration changed.

---

## [v2.17.1] - 2026-09-14

### Fixed
- **QC.md no longer contradicts INSTALL.md on how many upstream npm scripts are
  broken.** QC.md claimed "the seven `../scripts/*.mjs` npm scripts are
  upstream-repo-only", while INSTALL.md documents TWO classes: nine scripts plus
  the composite `test` whose paths point at the upstream monorepo root's
  unvendored CI / documentation-site tooling, and four whose vendored script
  imports an absent upstream devDependency. Both numbers were defensible for
  different things (8 npm script ENTRIES reference `../scripts/`, resolving to 7
  distinct `.mjs` FILES) which is exactly why the single total was misleading.
  QC.md now points at the two-class model and explicitly says not to state a
  single "N scripts are broken" total. No behavioural change; documentation
  only. Bumped per CI guard G3, which requires a `skill-version.txt` bump for
  any change inside a skill directory.

## [v2.17.0] - 2026-09-14

### Added — vendored upstream skill
- Vendored **archify** as Skill 69 from upstream
  **github.com/tt-a1i/archify @ `851b279f3710c3ed6f152f4b044a504ca4eb207c`**,
  upstream skill version **2.17.0**, **MIT** licensed (upstream `LICENSE`
  vendored verbatim; third-party attributions preserved in
  `THIRD_PARTY_NOTICES.md`).
- archify is a **zero-dependency Node.js CLI** (`package.json` declares no
  `dependencies` at all; `engines.node` is `>=18`). Entry point:
  `bin/archify.mjs`. It renders a small typed JSON specification into a
  self-contained, explorable **standalone HTML** diagram — inline SVG,
  dark/light themes, optional trace motion, PNG/JPEG/WebP/SVG/WebM export —
  across five diagram types: **architecture, workflow, sequence, dataflow,
  lifecycle**. It also accepts pasted Mermaid (`flowchart`, `sequenceDiagram`,
  `stateDiagram`) input and can inspect repository evidence.
- Vendored upstream tree kept **byte-identical to the upstream commit**:
  `SKILL.md`, `package.json`, `package-lock.json`, `bin/`, `renderers/`,
  `schemas/`, `examples/`, `references/`, `recipes/`, `assets/`,
  `brand-marks/`, `delta/`, `migrations/`, `test/`, `scripts/` (upstream's own
  in-tree scripts), `LICENSE`, `THIRD_PARTY_NOTICES.md`, `skill-release.json`.

### Added — onboarding integration (the only onboarding-authored files)
- `skill-version.txt` → `v2.17.0` (repo convention; trailing newline, per the
  `skill-version-newline-guard`).
- `INSTALL.md` — opens with the mandatory TYP check block, then documents the
  single prerequisite (Node.js >= 18), states explicitly that **NO `npm install`
  is required**, gives the installer steps, the exact verification commands with
  their expected results, and an honest "upstream npm scripts not applicable
  here" section.
- `INSTRUCTIONS.md` — the day-to-day usage guide that follows install: what
  archify is for and when to reach for it, the five diagram types, the real CLI
  commands (verbatim from `node bin/archify.mjs --help`), the authoring
  workflow (choose type, read the schema and one example, author the candidate,
  `validate`, `render`, `deliver`, `visual-check`), the Fast authoring path and
  its bounded-path discipline, `doctor`-first troubleshooting, and the honest
  upstream-npm-scripts disclosure.
- `QC.md` — verification checklist with the real commands and exit codes, a
  real-artifact inspection section (a passing exit code is not QC), and the
  repo-standard install-time rubric with the **8.5/10 pass gate**.
- `CORE_UPDATES.md` — merger-recognized sections that teach AGENTS.md, TOOLS.md
  and MEMORY.md that archify exists and when to reach for it. Applied by the
  format-robust CORE_UPDATES merger in `update-skills.sh`
  (`wire_core_updates()`), which resolves `[MASTER_FILES_FOLDER]` and stamps
  `<!-- skill:69-archify:core-update-applied -->`.
- `PREREQS.json` — machine-readable prerequisites: Skills 01 and 02, plus the
  Node >= 18 runtime declared as `type: "binary"`, `check: {"binary": "node",
  "minVersion": "18"}`. Both directions verified against the real checker in
  `shared-utils/check-skill-prereqs.sh`: node present → exit 0; node absent from
  PATH → exit 2 with `node-runtime` reported UNMET (so the declaration enforces
  something rather than always passing).
- `scripts/onboarding-smoke.sh` — the onboarding-native verifier. Derives the
  skill root from its own location (safe from any cwd), runs `doctor`, runs
  `validate` on a bundled example requiring `"ok": true`, renders one example to
  a temp file, asserts the HTML exists and is non-empty, removes the temp dir,
  and exits 0 with `ONBOARDING SMOKE PASS` / non-zero with a named failing step.
- `scripts/cc_board.py` — the large onboarding-authored producer script that
  lands archify runs on the Command Center Kanban board: one run grouping with
  one card per lifecycle phase (received -> authoring -> validate -> render ->
  deliver), fail-soft by design, stdlib only, credentials from env.

### Verified at vendoring time (measured, on the vendoring box)
- `node bin/archify.mjs doctor` → 15 `[ok]` lines, `Archify is ready.`, **exit 0**.
- `node bin/archify.mjs validate architecture examples/web-app.architecture.json
  --quality showcase --json` → `"ok": true`, **9/9** artifact checks true,
  `composition.status: "pass"`, 0 errors / 0 warnings, **exit 0**.
- `node bin/archify.mjs render architecture examples/web-app.architecture.json
  OUT.html` → **exit 0**, **811,157 bytes** standalone HTML, 1 inline `<svg>`,
  **0** external `<script src>` / `<link href="http…">` / `<img src="http…">`.
- `node bin/archify.mjs visual-check OUT.html --json` → **exit 0**,
  `status: "pass"`, `evidenceKind: "automated-browser"`
  (`visualReview` remains `"pending"` — an automated pass does not replace
  looking at the artifact).
- `bash scripts/onboarding-smoke.sh` → **exit 0**.
- `bash scripts/qc-assert-skill-frontmatter-version.sh` → **exit 0**.
- `bash tests/unit/core-updates-all-skills-wired.test.sh` → **18 passed, 0 failed**,
  including `47/47 skills produced their sentinel` and
  `0 unrecognized headers` (this skill's `CORE_UPDATES.md` parses under
  `CORE_UPDATES_STRICT=1`).
- `bash scripts/qc-prereqs-json.sh --verbose` → `OK 69-archify/PREREQS.json
  (3 prereqs)`, **exit 0**.

### Notes — upstream npm scripts are NOT usable in this tree (honest disclosure)
`package.json` is vendored byte-identical to upstream, so it still declares
upstream-repo scripts that cannot run here. They were deliberately NOT removed:
pruning them would break byte-identity and make future re-vendoring/diffing
unreliable. Documented instead:

- **Class 1 — the script path points at the upstream monorepo root
  `../scripts/`**, which is intentionally NOT vendored because it is not
  diagram-rendering runtime (site viewer, gallery, guide, start page, README
  showcase, release identity). Nine scripts belong here, plus the composite
  `test`: `generate:viewer`, `check:viewer`, `check:release-identity`,
  `build:gallery`, `build:guide`, `build:start`, `build:readme-showcase`,
  `test:webm`, and `render:examples`.
- **Measured**: `npm run check:viewer` exits 1 with
  `Cannot find module '…/onb-archify/scripts/generate-viewer.mjs'` — note the
  path resolves into the *onboarding repo's own* `scripts/` directory, which is
  a different tree entirely. Every other Class 1 script fails the same way
  (`generate:viewer` → `…/scripts/generate-viewer.mjs`;
  `check:release-identity` → `…/scripts/check-release-identity.mjs`;
  `build:gallery`, `build:guide`, `build:start`, `build:readme-showcase` →
  their own `…/scripts/build-*.mjs`), each **exit 1**. This is exactly why these
  scripts must never be presented as this skill's test suite.
- `test:webm` is in **Class 1, not the devDependency class**. It runs
  `node test/webm-artifact.smoke.mjs && node --test test/site-language-integration.mjs`,
  and the second stage statically imports `../../scripts/site-copy.mjs` from the
  upstream monorepo root. **Measured**:
  `node --test test/site-language-integration.mjs` exits 1 with
  `Cannot find module '…/onb-archify/scripts/site-copy.mjs'` (imported from
  `69-archify/test/site-language-continuity.test.mjs`).
- `render:examples` is **Class 1** as well, and carries an extra hazard. It runs
  `node scripts/render-examples.mjs ../examples`, and the vendored script
  resolves its output root with `path.resolve(process.argv[2] || …)` against the
  CURRENT WORKING DIRECTORY, so it writes to `<cwd>/../examples` — a **parent
  directory of this skill** (from `69-archify` that is
  `…/onb-archify/examples`, outside the skill). It must not be run casually from
  inside the skill directory, and it is not the same command as
  `node bin/archify.mjs examples`, which re-renders the bundled examples in
  place inside this skill.
- The composite **`npm test`** chains `check:viewer`, `check:brand-marks`,
  `check:validators`, `check:release-identity`, `node test/golden.mjs` and the
  also-unvendored `../scripts/run-tests.mjs`. **Measured**: it fails at its first
  link with `Cannot find module '…/onb-archify/scripts/generate-viewer.mjs'`
  (exit 1).
- **Class 2 — the script IS vendored, but it imports an upstream
  devDependency that is intentionally not installed** (the runtime needs none).
  **Measured**: `npm run check:brand-marks` → `Cannot find package
  'simple-icons'` (exit 1); `npm run check:validators` → `Cannot find package
  'ajv'` (exit 1). Same class: `generate:brand-marks` and `generate:validators`.
- The onboarding-native verifier is therefore `bash scripts/onboarding-smoke.sh`.
  A failure from any upstream npm script is NOT a failure of Skill 69 and is NOT
  a reason to run `npm install`.

### Notes — `archify examples` re-renders the bundled example HTML in place
`node bin/archify.mjs examples` is not a read-only listing: it invokes the
vendored `scripts/render-examples.mjs` with the skill root as cwd, which
re-renders all five bundled examples into `examples/*.html`. Measured during
vendoring: the output is **deterministic and byte-identical** — all five files
(`workflow-agent-tool-call-rendered.html`, `sequence-cache-miss-request.html`,
`dataflow-product-analytics.html`, `lifecycle-agent-run.html`,
`web-app-rendered.html`) `cmp`-matched a fresh render exactly, and their byte
sizes are unchanged from the vendored originals. No vendored content changes,
but the files' mtimes do — so run this command BEFORE, not after, any
byte-identity audit of the vendored tree.

### Notes — version identity
- `skill-release.json` (upstream, unmodified) declares
  `"version": "2.17.0-dev.1"`, `"channel": "development"`, and an update-manifest
  URL at `https://tt-a1i.github.io/archify/skill-updates/archify/stable.json`.
  The onboarding `skill-version.txt` records the **upstream release version
  2.17.0** at the vendored commit, not the `-dev.1` development stamp.
- `SKILL.md`'s frontmatter carries its version nested under `metadata:` as
  `2.17`; there is **no top-level `version:` field**. The repo's
  `skill-frontmatter-version-guard` therefore reports this skill as SKIPPED
  (reported, not failed) and exits 0 — verified. No vendored byte was changed to
  satisfy it. This matches the five most recently added skills (63, 65, 66, 67,
  68), none of which carry a top-level frontmatter version.
