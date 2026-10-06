> **N24 — Use the teach-yourself-protocol (Skill 01):** Before any action in this skill, the installing sub-agent MUST read every file under skills/01-teach-yourself-protocol/ and follow its procedural read-order. No shortcuts.

╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TYP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TYP).

HOW TO CHECK:
- Look in your AGENTS.md, TOOLS.md, or MEMORY.md for any mention of:
  "Teach Yourself Protocol" or "TYP"
- Look in your session context for prior TYP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF YOU HAVE BEEN TAUGHT TYP:
Proceed to the instructions below.

IF YOU HAVE NOT BEEN TAUGHT TYP:
STOP IMMEDIATELY. Do not read further. Tell the user you must be taught the
Teach Yourself Protocol first.

DO NOT PROCEED PAST THIS POINT WITHOUT TYP CONFIRMED.

CONFLICT RULE (applies to all skill installs):
If this skill's SKILL.md, CORE_UPDATES.md, or any other file in this skill
folder conflicts with TYP regarding WHICH core .md files to update or WHAT
content to add, always follow this skill's files. The skill takes precedence
over TYP on core file update decisions. TYP governs the storage method (lean
summaries + file paths). The skill governs the content and which files it
touches. When in doubt: skill docs win.

EXECUTION DISCIPLINE - MANDATORY BEFORE YOU START
╚══════════════════════════════════════════════════════════════╝

RULE 1: READ EVERYTHING BEFORE YOU TOUCH ANYTHING.
RULE 2: DO NOT CHANGE THE OPERATOR'S INTENT — execute steps exactly as written.
RULE 3: NEVER MODIFY API keys, commands, config values, model names, or file
        paths without permission. Model name spelling matters.
RULE 4: BUILD YOUR CHECKLIST BEFORE EXECUTING.
RULE 5: CHECK YOURSELF AGAINST THE CHECKLIST WHEN DONE.
RULE 6: REPORT WHAT YOU DID.

══════════════════════════════════════════════════════════════════
ARCHIFY (69) - INSTALLATION GUIDE
══════════════════════════════════════════════════════════════════

archify is a Node.js CLI that turns a small, typed JSON specification into a
self-contained, explorable HTML diagram — inline SVG, dark/light themes,
optional trace motion, and PNG/JPEG/WebP/SVG/WebM export. It accepts
plain-language requirements or pasted Mermaid (`flowchart`, `sequenceDiagram`,
`stateDiagram`) input, and can inspect repository evidence when the diagram must
reflect real code.

"Installing" this skill means exactly four things:

  1. confirm the one prerequisite (Node.js >= 18),
  2. confirm that NO `npm install` is needed,
  3. run the packaged smoke test and see it pass,
  4. wire the lean core-file pointers.

There is no account to create, no API key, no credential, and no software to
install. Do not improvise extra steps.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1: CONFIRM THE PREREQUISITE — Node.js >= 18
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Check the version:

   node --version

   Expected: a `v<major>.<minor>.<patch>` string, e.g. `v26.8.1`. The major
   version must be >= 18. `package.json` declares this contract as
   `"engines": { "node": ">=18" }`.

2. If `node` is not on PATH, or the major version is < 18, STOP. This skill
   cannot run. Ask the operator to install Node.js 18 or newer
   (https://nodejs.org/ or a package manager). Do NOT install a Node runtime
   onto the box yourself without permission, and do NOT work around it with a
   different JS engine.

3. `python3` is NOT required by this skill. The repo's installer, the
   CORE_UPDATES merger, and the prereq checker use python3, but archify itself
   does not.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2: NO `npm install` IS REQUIRED — THE RUNTIME IS ZERO-DEPENDENCY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Do NOT run `npm install` in this folder.** Say this out loud to yourself
before proceeding.

- `package.json` has **no `dependencies` block at all**. The runtime —
  `bin/archify.mjs` and everything it loads from `renderers/`, `schemas/`,
  `references/`, `assets/`, `brand-marks/` — imports only Node built-ins
  (`node:fs`, `node:path`, `node:url`, `node:child_process`, `node:zlib`, …).
- There is **no `node_modules/` directory** in this skill, and none is needed.
- The `devDependencies` listed in `package.json` (`ajv`, `parse5`, `saxes`,
  `simple-icons`) belong to the **upstream monorepo's development tooling** —
  schema/validator generation, brand-mark generation, and the browser-DOM test
  helpers. They are NOT part of the diagram-rendering runtime. Leaving them
  uninstalled is the intended state on an onboarding box. See
  "UPSTREAM NPM SCRIPTS NOT APPLICABLE HERE" at the end of this document.

If you find yourself wanting to install a dependency to make a diagram render,
you have taken a wrong turn: run `node bin/archify.mjs doctor` and read the
`[FAIL]` line instead.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3: RUN THE ONBOARDING SMOKE TEST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

`install.sh` reads this file and executes it in order. The onboarding-native
verifier for this skill is:

   bash scripts/onboarding-smoke.sh

The script derives the skill root from its own location, so it may be invoked
from any working directory. It:

  1. runs `node bin/archify.mjs doctor` and requires exit 0,
  2. runs `node bin/archify.mjs validate architecture
     examples/web-app.architecture.json --quality showcase --json` and requires
     `"ok": true`,
  3. runs `node bin/archify.mjs render architecture
     examples/web-app.architecture.json <tmp>/smoke.html` and asserts the
     output HTML exists and is non-empty,
  4. deletes the temporary directory it created,
  5. prints `ONBOARDING SMOKE PASS` and exits 0.

Expected: exit 0, ending with `ONBOARDING SMOKE PASS: archify (69) is
operational`. Any non-zero exit prints a `SMOKE FAIL` line naming the step that
failed — fix that before continuing. Do not treat a partial pass as a pass.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4: VERIFICATION — EXACT COMMANDS AND EXPECTED RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Run all four from inside this skill directory (or use `bash
scripts/onboarding-smoke.sh`, which does the first three for you).

TEST 1 — environment health:

   node bin/archify.mjs doctor

   Expected: 15 `[ok]` lines — Node.js version, Core template, Example renderer,
   Live preview runtime, Visual-check runtime, Output path safety runtime,
   Scenario recipe guide, Progressive authoring references, Architecture compare
   runtime and proof fixtures, Standalone schema validators, and one line per
   renderer (architecture, workflow, sequence, dataflow, lifecycle) — followed
   by `Archify is ready.` and **exit 0**. A `[FAIL]` line, or a non-zero exit,
   means the vendored tree is incomplete: re-vendor, do not patch.

TEST 2 — schema + composition validation of a bundled example:

   node bin/archify.mjs validate architecture examples/web-app.architecture.json --quality showcase --json

   Expected: a JSON receipt on stdout with `"ok": true`, a `checks` array of
   **9** artifact checks (`single_svg`, `finite_svg`, `orthogonal_arrows`,
   `label_route_clearance`, `relationship_crossings`, `relationship_corridors`,
   `container_border_runs`, `route_rhythm`, `legend_clearance`) each with
   `"ok": true`, and `composition.status` = `"pass"` with
   `composition.summary.errors` = 0 and `warnings` = 0 — and **exit 0**.

   A receipt with only 4 checks is basic validation, never showcase acceptance.
   A showcase pass must report all 9 checks clean.

TEST 3 — render a standalone HTML artifact:

   node bin/archify.mjs render architecture examples/web-app.architecture.json /tmp/archify-smoke.html

   Expected: **exit 0**, and `/tmp/archify-smoke.html` exists and is non-empty.
   Measured on the vendoring box: **811,157 bytes**, a fully standalone document
   (inline SVG + inline CSS + inline runtime — no network fetches, no external
   assets). Delete the file afterwards.

TEST 4 — the packaged smoke test, run from a different working directory to
prove the script is location-independent:

   cd /tmp && bash /path/to/69-archify/scripts/onboarding-smoke.sh

   Expected: exit 0 and `ONBOARDING SMOKE PASS`.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 5: WIRE CORE FILES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CORE_UPDATES.md carries the exact text for AGENTS.md, TOOLS.md, and MEMORY.md so
a client agent knows archify exists and when to reach for it. The generic,
format-robust merger inside `update-skills.sh` (function `wire_core_updates`)
applies it — it recognises the `## <FILE>.md - UPDATE REQUIRED` headers, wraps
each block in `<!-- BEGIN/END skill:69-archify:<target> -->` markers, resolves
`[MASTER_FILES_FOLDER]` to this box's absolute master-files path, and stamps
`<!-- skill:69-archify:core-update-applied -->` into AGENTS.md.

Do NOT paste the CORE_UPDATES.md payloads by hand, and do NOT write them into
SOUL.md, IDENTITY.md, USER.md, or HEARTBEAT.md — those are marked NO UPDATE
NEEDED. During onboarding, `update-skills.sh` performs this step automatically.
Confirm afterwards that the sentinel is present:

   grep -F '<!-- skill:69-archify:core-update-applied -->' \
     "${OPENCLAW_WORKSPACE_DIR:-$HOME/.openclaw/workspace}/AGENTS.md"

Expected: the sentinel line is printed (exit 0). If it is absent, report the
wiring as incomplete rather than claiming success.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SETUP CHECKLIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[ ] `node --version` reports v18 or newer
[ ] NO `npm install` was run — the runtime is zero-dependency (no node_modules)
[ ] Test 1 passed — `doctor` printed 15 `[ok]` lines and `Archify is ready.`, exit 0
[ ] Test 2 passed — `validate … --quality showcase --json` printed `"ok": true`, 9/9 checks, exit 0
[ ] Test 3 passed — `render …` produced a non-empty standalone HTML, exit 0
[ ] Test 4 passed — `scripts/onboarding-smoke.sh` exited 0 from a foreign cwd
[ ] STEP 5 sentinel `<!-- skill:69-archify:core-update-applied -->` present in AGENTS.md
[ ] No upstream npm script was reported as a failure of this skill

DO NOT tell the user the skill is active until every box above is checked.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
UPSTREAM NPM SCRIPTS NOT APPLICABLE HERE (honest disclosure)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

`package.json` is vendored **byte-identical to upstream** (github.com/tt-a1i/
archify @ 851b279f3710c3ed6f152f4b044a504ca4eb207c), so it still declares
upstream-repo scripts that cannot run in this onboarding tree. They were NOT
deleted, because a vendored file that no longer matches its upstream commit
cannot be re-diffed, re-verified, or safely re-vendored later. Documenting them
honestly is the correct move; silently pruning them is not.

The genuinely broken scripts fall into **TWO distinct classes**, and they fail
for different reasons. Do not merge them into one claim.

CLASS 1 — the script path points at the **upstream monorepo root's
`../scripts/`** CI and documentation-site tooling, which is deliberately NOT
vendored (it builds the project website, the gallery, the guide, and the
release-identity check; none of it is diagram-rendering runtime). Nine scripts,
plus the composite `test`, belong to this class:

  1. `npm run generate:viewer`      -> node ../scripts/generate-viewer.mjs
  2. `npm run check:viewer`         -> node ../scripts/generate-viewer.mjs --check
  3. `npm run check:release-identity` -> node ../scripts/check-release-identity.mjs
  4. `npm run build:gallery`        -> node ../scripts/build-gallery.mjs ../docs
  5. `npm run build:guide`          -> node ../scripts/build-guide.mjs ../docs/guide.html
  6. `npm run build:start`          -> node ../scripts/build-start.mjs ../docs/start.html
  7. `npm run build:readme-showcase` -> node ../scripts/build-readme-showcase.mjs
  8. `npm run test:webm`            -> node test/webm-artifact.smoke.mjs && node --test test/site-language-integration.mjs
  9. `npm run render:examples`      -> node scripts/render-examples.mjs ../examples

Measured on the vendoring box (every one of them exits 1):

  $ npm run check:viewer
  Error: Cannot find module '…/onb-archify/scripts/generate-viewer.mjs'
  $ npm run generate:viewer          # same shape
  Error: Cannot find module '…/onb-archify/scripts/generate-viewer.mjs'
  $ npm run check:release-identity
  Error: Cannot find module '…/onb-archify/scripts/check-release-identity.mjs'
  $ npm run build:gallery            # build:guide, build:start, build:readme-showcase too
  Error: Cannot find module '…/onb-archify/scripts/build-gallery.mjs'

Note the path resolves into the *onboarding repo's own* `scripts/` directory,
which is a different tree entirely. That is exactly why these must never be
presented as this skill's test suite.

`test:webm` is in THIS class, **not** the devDependency class. It runs
`node test/webm-artifact.smoke.mjs && node --test test/site-language-integration.mjs`,
and the second stage statically imports `../../scripts/site-copy.mjs` from the
upstream monorepo root. Measured:

  $ node --test test/site-language-integration.mjs
  Error [ERR_MODULE_NOT_FOUND]: Cannot find module '…/onb-archify/scripts/site-copy.mjs'
  imported from …/69-archify/test/site-language-continuity.test.mjs   (exit 1)

`render:examples` is in this class too, and it carries an extra hazard. It runs
`node scripts/render-examples.mjs ../examples`, and the vendored script resolves
its output root with `path.resolve(process.argv[2] || …)` against the CURRENT
WORKING DIRECTORY. It therefore writes to `<cwd>/../examples`, a **parent
directory of this skill** (run from `69-archify`, that is
`…/onb-archify/examples`, outside the skill), so it must not be run casually
from inside the skill directory. It is NOT the same command as
`node bin/archify.mjs examples`, which re-renders the bundled examples in place
inside this skill.

Plus the composite `npm test`, which chains `check:viewer`,
`check:brand-marks`, `check:validators`, `check:release-identity`,
`node test/golden.mjs`, and the also-unvendored `../scripts/run-tests.mjs`.
Measured: it fails at its first link with the same
`Cannot find module '…/onb-archify/scripts/generate-viewer.mjs'` (exit 1).

CLASS 2 — the script **is** vendored, but it imports an upstream
**devDependency** that is intentionally not installed (Step 2; the runtime needs
none of them). Measured, exit 1 for each:

  $ npm run check:brand-marks        # same class: generate:brand-marks
  Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'simple-icons'
  imported from …/69-archify/scripts/generate-brand-marks.mjs

  $ npm run check:validators         # same class: generate:validators
  Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'ajv'
  imported from …/69-archify/scripts/generate-validators.mjs

WHAT THIS MEANS FOR YOU:

- A failure from any of the scripts above is **NOT** a failure of skill 69 and
  **NOT** a reason to run `npm install`.
- The onboarding-native verifier is `bash scripts/onboarding-smoke.sh`. It is
  the only test command this skill asks you to run.
- The runtime commands that DO work, and that you should use, are `doctor`,
  `validate`, `render`, `deliver`, `preview`, `compare`, `migrate`, `inspect`,
  `check`, `visual-check`, `guide`, `brands`, `examples`, and `demo` —
  invocation list via `node bin/archify.mjs --help`.

---

## 🔴 GATEWAY RESTART PROTOCOL - NEVER TRIGGER AUTONOMOUSLY

If any step here appears to require an OpenClaw gateway restart, STOP. Do NOT run
`openclaw gateway restart` yourself. Notify the user and ask them to trigger it
(for example via `/restart` in Telegram). Wait for confirmation before
proceeding. This skill does not require a restart in the normal path.
