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
Proceed to the instructions below. Follow the TYP file storage structure.

IF YOU HAVE NOT BEEN TAUGHT TYP:
STOP IMMEDIATELY. Do not read further. Do not attempt to learn or execute
anything in this document. Tell the user exactly this:

  "I have not been taught the Teach Yourself Protocol yet. I cannot safely
   learn or execute these instructions until I have been taught TYP first.
   Please share the Teach Yourself Protocol tab with me before we proceed.
   Without TYP, I will bloat your core .md files and waste your tokens."

DO NOT PROCEED PAST THIS POINT WITHOUT TYP CONFIRMED.

══════════════════════════════════════════════════════════════════
ARCHIFY (69) - HOW TO USE IT (DAILY USAGE GUIDE)
══════════════════════════════════════════════════════════════════

This document explains how to use archify day to day: pick a type, author a
typed JSON specification, validate it, deliver the standalone HTML, then
collect browser evidence. If Node.js >= 18 is not confirmed yet, go to
INSTALL.md first. SKILL.md is the authoritative authoring contract; for field
enums, spacing math and geometry repair rules see
references/authoring-contract.md; for the delivery receipt and visual review
see references/delivery-contract.md. Run every command below from the skill
root (the directory that contains bin/archify.mjs).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT IT IS FOR, AND WHEN TO REACH FOR IT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Archify turns a small, typed JSON specification into a self-contained,
explorable HTML diagram: inline SVG, dark/light themes, optional trace motion,
and PNG/JPEG/WebP/SVG/WebM export. It also accepts pasted Mermaid
(`flowchart`, `sequenceDiagram`, `stateDiagram`) input, and can inspect
repository evidence when the diagram must reflect real code.

Reach for it when the user says or implies:

- "visualize / show me / diagram the architecture"
- infrastructure, cloud, security, or network topology
- technical workflows, runbooks, approval gates, CI/CD
- API call sequences, request lifecycles, async traces
- data pipelines, ETL/ELT, data lineage, governance, consumers
- state machines, status transitions, retries, terminal states
- "convert this Mermaid" or "beautify this Mermaid"

Do NOT reach for it to hand-write SVG, to invent facts the source does not
support, or as a general charting tool. It draws the system you can evidence,
not a plausible-looking re-invention.

Runtime facts: zero-dependency Node.js CLI (`bin/archify.mjs`, Node >= 18).
There is NO API key, NO credential, NO network call, and NO `npm install`.

When the type is ambiguous, ask the packaged guide:

  node bin/archify.mjs guide "<scenario or question>" --json

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE FIVE DIAGRAM TYPES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

| Type | Use for |
|---|---|
| `architecture` | Components, services, cloud/security boundaries, infrastructure |
| `workflow` | Processes, approval gates, tool calls, runbooks, CI/CD |
| `sequence` | API call chains, request lifecycles, async traces, returns |
| `dataflow` | Pipelines, ETL/ELT, lineage, governance, consumers |
| `lifecycle` | State/status transitions, retries, waiting and terminal states |

Mermaid input maps like this: `flowchart` / `graph` -> `workflow` (or
`architecture` for a component map); `sequenceDiagram` -> `sequence`;
`stateDiagram` -> `lifecycle`. Read Mermaid for topology and meaning, then
author fresh Archify JSON. Never mechanically render Mermaid styling.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE COMMANDS (verbatim from --help)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Print the live list any time with `node bin/archify.mjs --help` (exit 0). The
block below is that output verbatim:

Usage:
  archify render <type> <input.json> [output.html] [--quality standard|showcase] [--repo-root path (architecture only)]
  archify compare architecture <base.json> <head.json> [output.html] [--receipt path] [--json] [--quality standard|showcase] [--repo-root path]
  archify deliver <type> <input.json> [output.html] [--json] [--open] [--quality standard|showcase] [--repo-root path (architecture only)]
  archify preview <type> <input.json> [output.html] [--no-open] [--quality standard|showcase] [--repo-root path (architecture only)]
  archify validate <type> <input.json> [--json] [--layout-json] [--quality standard|showcase] [--repo-root path (architecture only)]
  archify migrate workflow <old.json> <new.json> --to-schema 2 [--json]
  archify inspect <type> <input.json>
  archify check <output.html>
  archify visual-check <output.html> [--json]
  archify guide [scenario or question] [--json] [--lang en|zh]
  archify brands [name, alias, domain, or category] [--json]
  archify brands capture <url> [--json]
  archify examples
  archify doctor
  archify demo [output-directory]

What each one is for:

- `validate` - authoring-time repair loop. `--json` prints the receipt;
  `--layout-json` prints the stable workflow v2 compiler receipt.
- `render` - write the HTML artifact. Fast path, no frozen-byte receipt.
- `deliver` - final acceptance. Freezes the exact specification bytes into a
  same-directory snapshot, renders and checks that snapshot, atomically commits
  the HTML, and reports SHA-256 plus byte counts for both specification and
  artifact. This is deterministic artifact evidence; it does not exercise the
  Viewer in a browser.
- `visual-check` - post-delivery automated browser evidence from the exact
  delivered HTML. It never modifies or re-renders the artifact.
- `check` - re-run the 9 artifact checks against a delivered HTML file.
- `compare` - architecture-only before/after diff of two specifications.
- `migrate` - workflow schema v1 -> v2 migration.
- `inspect` - print the parsed IR, resolved layout mode, and viewBox.
- `preview` - live preview loop for active authoring. Never start it by
  default.
- `guide` - scenario-to-type recommendation with must-include guidance.
- `brands` - query the built-in brand catalog by name/alias/domain/category;
  `brands capture <url>` pins an official URL into a brand object.
- `examples` - re-render the five bundled examples into `examples/*.html`
  (in place and byte-identical, but it changes their mtimes; run it before, not
  after, any byte-identity audit).
- `doctor` - environment and vendored-tree health.
- `demo` - render a sample diagram into a directory to prove the install.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE AUTHORING WORKFLOW (the normal path)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Choose the type from the question (use `guide` when ambiguous).

2. Read the matching schema: `schemas/<type>.schema.json` plus
   `schemas/common.schema.json`.

3. Read ONE matching example in `examples/` for field shape only. Never copy
   its facts, IDs, or layout.

4. Write the candidate JSON. New stable IDs, domain wording, fresh layout.
   New workflows use `schema_version: 2` and its readable layout contract; keep
   `schema_version: 1` only to preserve an existing workflow's fixed geometry.
   Set `meta.quality_profile` to `"showcase"` unless a dense `standard` map was
   explicitly requested. Omit `meta.visual_preset` and `meta.subtitle` by
   default. When real product identity matters, query
   `node bin/archify.mjs brands "<name>" --json` instead of guessing a logo.

5. Validate after every candidate edit:

   node bin/archify.mjs validate <type> <candidate.json> --quality showcase --json

   Acceptance is the receipt, not the exit code alone: all 9 artifact checks
   (`single_svg`, `finite_svg`, `orthogonal_arrows`, `label_route_clearance`,
   `relationship_crossings`, `relationship_corridors`, `container_border_runs`,
   `route_rhythm`, `legend_clearance`) must be `true`, with
   `composition.status` `"pass"`, 0 errors and 0 warnings. A receipt with only
   4 checks is basic validation, never showcase acceptance. If the candidate
   omits or misspells `meta.quality_profile`, fix that before touching geometry.

6. Ship it. Use `render` while iterating, and `deliver` once for final
   acceptance:

   node bin/archify.mjs deliver <type> <candidate.json> <output.html> --quality showcase --json

7. Collect bounded browser evidence after a successful delivery:

   node bin/archify.mjs visual-check <output.html> --json

   Keep the three claims separate: `deliver` proves deterministic artifact
   checks, `visual-check` proves bounded behavior in a real browser, and
   perceptual review requires an actual human or image-capable reviewer.
   `visual-check` reports `visualReview: "pending"` even on a pass, so it never
   replaces looking at the artifact. If no browser exists on the box, report
   the check as NOT RUN, never as passed.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE FAST AUTHORING PATH (bounded-path discipline)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This bounded path is the default for ordinary generation. Do not read the
optional Viewer Runtime reference unless the user asks about those features.
Do not read `renderers/shared/geometry.mjs`, renderer source, validator source,
tests, or benchmarks before the first candidate exists. Inspect implementation
only for an unsupported internal diagnostic, or after two focused repairs fail.

- Read only what the path needs: one schema, `common.schema.json`, one example.
  Read `references/brand-marks.md` only for an unknown brand with a
  user-provided URL.
- Artifact first: the next tool action after choosing the type writes the
  candidate. Do not plan exact coordinates in prose.
- Start simple: one clear main path, short side branches, sparse labels, at
  most 12 primary nodes.
- Start with automatic routes and labels. Do not add `via`, `channelX`,
  `channelY`, or `labelAt` before a diagnostic calls for one, and apply at
  most one diagnosed geometry control per repair.
- Repair loop: change only the diagnosed `subject`, verify `evidence`, choose
  from `supportedFixes`, and rerun. Continue while the objective error count
  reaches a new minimum. If two consecutive rounds do not improve the best
  count, stop and report the unresolved diagnostics truthfully.
- A passing final validation FREEZES the candidate: never edit it afterwards.
- Relationship labels are semantic data. When one collides, move the label,
  adjust the route or spacing, then shorten the wording while preserving
  meaning. Deleting a meaningful label is not a geometry repair.
- A non-zero exit can NEVER be described as success. A failed delivery
  preserves the previous output, so do not run `visual-check` on that path: it
  would inspect the stale last-good artifact instead of the failed candidate.
- Check the delivered HTML at 1440x900, 1600x1000 and 1920x1080 (add
  2048x1320 for a large desktop target); `document.documentElement.scrollWidth
  <= window.innerWidth` and `scrollHeight <= window.innerHeight` must hold at
  every checked size.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TROUBLESHOOTING (START WITH doctor)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Environment and tree health, always the first command:

  node bin/archify.mjs doctor

Expected: 15 `[ok]` lines (Node.js, Core template, Example renderer, Live
preview runtime, Visual-check runtime, Output path safety runtime, Scenario
recipe guide, Progressive authoring references, Architecture compare runtime
and proof fixtures, Standalone schema validators, and one per renderer:
architecture, workflow, sequence, dataflow, lifecycle), then
`Archify is ready.` and exit 0.

| Symptom | What it means | What to do |
|---|---|---|
| A `[FAIL]` line, or non-zero `doctor` | The vendored tree is incomplete | Re-vendor from upstream. Never patch a vendored file. |
| `node --version` below v18 | Unsupported runtime | Stop; ask the operator for Node.js 18+. Do not work around it. |
| `validate` exits non-zero | Real schema or composition diagnostics | Read the diagnostics, change only the diagnosed subject, rerun. Do not delete meaningful labels or edges to pass. |
| Receipt shows only 4 checks | Basic validation, not showcase | Correct `meta.quality_profile` to `"showcase"` and rerun with `--quality showcase`. |
| Workflow layout diagnostics | Geometry, not solver internals | `node bin/archify.mjs validate workflow <candidate.json> --layout-json` and act on the compiler diagnostic. |
| `deliver` exits non-zero | Publication failed; previous output preserved | Never call it success. Do not `visual-check` that path. Repair, then deliver again. |
| `visual-check` says `visualReview: "pending"` | Expected, even on a pass | Do a real perceptual review, or report it as not performed. |
| A render looks plausible but wrong | Fidelity problem, not a geometry problem | Re-read the source facts and the schema; a passing receipt does not prove content fidelity. |
| Any `npm run ...` upstream script fails | Expected in this vendored tree | See the next section. This is NOT a failure of skill 69 and NOT a reason to run `npm install`. |

Proof-of-life commands that always work on a healthy install:

  node bin/archify.mjs demo /tmp/archify-demo
  node bin/archify.mjs validate architecture examples/web-app.architecture.json --quality showcase --json
  node bin/archify.mjs render architecture examples/web-app.architecture.json /tmp/out.html

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
UPSTREAM NPM SCRIPTS ARE NOT USABLE HERE (honest disclosure)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

`package.json` is vendored byte-identical to upstream, so it still declares
upstream-repo scripts that cannot run in this layout. Pruning them would break
byte-identity and make re-vendoring unreliable, so they are documented instead.
There are exactly TWO classes of breakage, and they are NOT the same failure.

CLASS 1 - the script path points at the upstream monorepo root `../scripts/`,
which is deliberately not vendored (it builds the project website, gallery,
guide, and release identity; none of it is diagram-rendering runtime):

  generate:viewer, check:viewer, check:release-identity, build:gallery,
  build:guide, build:start, build:readme-showcase, test:webm, render:examples,
  and the composite `test`.

Measured, exit 1 for each:

  $ npm run check:viewer
  Error: Cannot find module '<repo>/scripts/generate-viewer.mjs'

  (note the path resolves into the ONBOARDING REPO's own scripts/ directory,
  which is a different tree entirely)

`test:webm` runs
`node test/webm-artifact.smoke.mjs && node --test test/site-language-integration.mjs`.
It belongs to this class because the second stage imports
`../../scripts/site-copy.mjs` from the upstream monorepo root. Measured:

  $ node --test test/site-language-integration.mjs
  Error [ERR_MODULE_NOT_FOUND]: Cannot find module '<repo>/scripts/site-copy.mjs'
  imported from .../69-archify/test/site-language-continuity.test.mjs   (exit 1)

`render:examples` runs `node scripts/render-examples.mjs ../examples`, and the
vendored script resolves its output root with
`path.resolve(process.argv[2] || ...)` against the CURRENT WORKING DIRECTORY.
That means it writes to `<cwd>/../examples`, a PARENT directory of the skill,
so it must never be run casually from inside the skill directory: from
`69-archify` it targets `<repo>/examples`. It is not the same thing as
`node bin/archify.mjs examples`, which re-renders the bundled examples in place
inside this skill.

The composite `npm test` fails at its first link (`check:viewer`) and also
chains the unvendored `../scripts/run-tests.mjs`:

  $ npm test
  Error: Cannot find module '<repo>/scripts/generate-viewer.mjs'   (exit 1)

CLASS 2 - the script IS vendored, but it imports an upstream devDependency that
is intentionally not installed (the runtime needs none of them). Measured,
exit 1 for each:

  $ npm run check:brand-marks      # also generate:brand-marks
  Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'simple-icons'
  imported from .../69-archify/scripts/generate-brand-marks.mjs

  $ npm run check:validators       # also generate:validators
  Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'ajv'
  imported from .../69-archify/scripts/generate-validators.mjs

WHAT THIS MEANS FOR YOU:

- A failure from any upstream npm script is NOT a failure of skill 69 and is
  NOT a reason to run `npm install`.
- The onboarding-native verifier is `bash scripts/onboarding-smoke.sh`, which
  is location-independent and exits 0 printing `ONBOARDING SMOKE PASS`. It is
  the only test command this skill asks you to run.
- The commands that DO work are the runtime commands listed above:
  `render`, `compare`, `deliver`, `preview`, `validate`, `migrate`, `inspect`,
  `check`, `visual-check`, `guide`, `brands`, `examples`, `doctor`, `demo`.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRACTICAL NUMBERS (measured on the vendoring box)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- `doctor` reports 15 subsystems; a showcase `validate` receipt carries 9
  artifact checks.
- The bundled architecture example renders to a fully standalone document
  (inline SVG + inline CSS + inline runtime, 0 external `<script src>`,
  `<link href="http...">` or `<img src="http...">` references): measured
  **811,157 bytes**. The other bundled examples land in the same ~810-820 KB
  band. A few KB means the template/runtime did not inline.
- Node >= 18 is required and `package.json` declares no `dependencies` at all.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT TO RETURN TO THE USER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Report the checked HTML path, the diagram type, the validation summary, the
specification/artifact receipt (SHA-256 plus byte counts), the browser-evidence
status, and a truthful visual-review status. Never claim success for a non-zero
command, and never claim a visual inspection you did not perform.
