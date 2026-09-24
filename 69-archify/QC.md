# QC Checklist: Archify (JSON-IR → standalone HTML diagrams)

## 1. Purpose
Enables the agent to turn a small, typed JSON specification into a self-contained,
explorable HTML diagram — architecture, workflow, sequence, dataflow, and
lifecycle/state — with inline SVG, dark/light themes, optional trace motion, and
PNG/JPEG/WebP/SVG/WebM export. It accepts plain-language requirements or pasted
Mermaid (`flowchart`, `sequenceDiagram`, `stateDiagram`) input, and can inspect
repository evidence when the diagram must reflect real code. The runtime is a
**zero-dependency Node.js CLI** (`bin/archify.mjs`, Node >= 18): there is no API
key, no credential, no network call, and no `npm install`. Acceptance is an
**artifact** decision — a diagram is delivered only when validation reports a
clean showcase receipt, never because a command merely exited 0.

## 2. Installation Checks
- [ ] Skill folder exists and contains `SKILL.md`, `INSTALL.md`,
      `INSTRUCTIONS.md`, `QC.md`, `CORE_UPDATES.md`, `CHANGELOG.md`,
      `PREREQS.json`, `skill-version.txt`,
      `LICENSE`, `THIRD_PARTY_NOTICES.md`, `package.json`, `skill-release.json`,
      `bin/archify.mjs`, and the `renderers/`, `schemas/`, `examples/`,
      `references/`, `recipes/`, `assets/`, `brand-marks/`, `delta/`,
      `migrations/`, `test/`, `scripts/` directories.
- [ ] `package.json` parses as JSON, has **no `dependencies` key** at all, and
      declares `"engines": { "node": ">=18" }`.
- [ ] `skill-version.txt` reads `v2.17.0` and ends with a trailing newline.
- [ ] No `node_modules/` directory exists in the skill (and none is needed).
- [ ] Vendored upstream files are byte-identical to
      github.com/tt-a1i/archify @ 851b279f3710c3ed6f152f4b044a504ca4eb207c —
      the only onboarding-authored files are `skill-version.txt`,
      `INSTRUCTIONS.md`, `INSTALL.md`, `QC.md`, `CORE_UPDATES.md`,
      `PREREQS.json`, `CHANGELOG.md`, `scripts/onboarding-smoke.sh`, and
      `scripts/cc_board.py` (the large onboarding-authored producer script that
      lands archify runs on the Command Center Kanban board).
- [ ] No secret, token, or API key value appears anywhere in the skill files
      (there is nothing to leak — the skill holds no credential).

## 3. Dependency Checks
- [ ] TYP (Skill 01) and BYUP (Skill 02) are installed first.
- [ ] `node --version` reports **v18 or newer**. archify refuses to be trusted on
      anything older; do not attempt a workaround.
- [ ] `npm install` was **NOT** run and is **NOT** required. The runtime imports
      only Node built-ins (`node:fs`, `node:path`, `node:url`,
      `node:child_process`, `node:crypto`, `node:zlib`, `node:http(s)`, …).
      Verified: `package.json.dependencies` is `undefined`; the only bare
      specifiers anywhere in `bin/` and `renderers/` are `node:*`.
- [ ] The installer understands that `package.json`'s `devDependencies`
      (`ajv`, `parse5`, `saxes`, `simple-icons`) belong to the **upstream
      monorepo's development tooling**, not to diagram rendering, and that the
      upstream-repo npm scripts cannot run in this tree. There are **TWO
      distinct classes** and they fail for different reasons: nine scripts plus
      the composite `test` whose paths point at the upstream monorepo root's
      unvendored CI / documentation-site tooling, and four whose vendored
      script imports an absent upstream devDependency. Enumerated lists and the
      measured failure of each are in INSTALL.md § "UPSTREAM NPM SCRIPTS NOT
      APPLICABLE HERE" — do not collapse the two classes into one claim, and do
      not state a single "N scripts are broken" total.
- [ ] `python3` is not required by this skill (the repo installer/merger needs
      it; archify does not).

## 4. Environment Detection (no credential exists)
- [ ] Confirm the agent does NOT search for an API key, does NOT invent an
      environment variable for this skill, and does NOT ask the operator for a
      credential. **archify has no credential.** A QC report that mentions
      provisioning a key for skill 69 is a fabrication and fails QC.
- [ ] Confirm `node` resolves on PATH (`command -v node`) and report its
      absolute path and major version.
- [ ] Confirm there is no network dependency: `render` and `validate` must
      succeed with networking unavailable.

## 5. Functional Checks
- [ ] `node bin/archify.mjs doctor` → **exit 0**, exactly 15 `[ok]` lines
      (Node.js, Core template, Example renderer, Live preview runtime,
      Visual-check runtime, Output path safety runtime, Scenario recipe guide,
      Progressive authoring references, Architecture compare runtime and proof
      fixtures, Standalone schema validators, and one per renderer:
      architecture, workflow, sequence, dataflow, lifecycle), ending
      `Archify is ready.` A `[FAIL]` line or non-zero exit = incomplete vendored
      tree; re-vendor, never patch.
- [ ] `node bin/archify.mjs validate architecture
      examples/web-app.architecture.json --quality showcase --json` → **exit 0**,
      `"ok": true`, **9/9** artifact checks true (`single_svg`, `finite_svg`,
      `orthogonal_arrows`, `label_route_clearance`, `relationship_crossings`,
      `relationship_corridors`, `container_border_runs`, `route_rhythm`,
      `legend_clearance`), `composition.status` `"pass"`,
      `composition.summary.errors` = 0 and `warnings` = 0.
      A 4-check receipt is basic validation, NEVER showcase acceptance.
- [ ] `node bin/archify.mjs render architecture
      examples/web-app.architecture.json <tmp>/out.html` → **exit 0** and a
      non-empty output file. Measured on the vendoring box: **811,157 bytes**.
- [ ] `bash scripts/onboarding-smoke.sh` → **exit 0**, prints
      `ONBOARDING SMOKE PASS`, and leaves no temp files behind.
- [ ] Determinism: run `validate` twice on the same input. The `ok`, `checks`,
      and `composition` fields must be identical both times. A receipt that
      changes between identical runs is a failure.
- [ ] The agent can explain the acceptance rule: **a non-zero exit can never be
      described as success**, and a failed delivery preserves the previous
      output — so never run `visual-check` against the path of a failed
      candidate (it would inspect the stale last-good artifact).

## 6. Real Artifact QC — after render, MANDATORY
A successful exit code is NOT QC. Open the artifact and inspect it.

### 6.1 Structure
- [ ] File exists and is non-empty (0 bytes, or an HTML error page saved as
      `.html`, is a failure).
- [ ] Contains exactly **one** `<svg>` block (inline vector, not a rasterized
      screenshot): `grep -c '<svg' out.html` → `1`.
- [ ] **Standalone**: zero external `<script src=…>`, zero
      `<link href="http…">`, zero `<img src="http…">` (measured 0/0/0). It must
      render with the network off.
- [ ] `node bin/archify.mjs check <out.html>` → **exit 0**, `"ok": true` with the
      same 9 checks and a `pass` composition.

### 6.2 Content fidelity
- [ ] Every node/edge the user asked for is present, with the RIGHT labels and
      the right relationships — not a plausible-looking re-invention.
- [ ] The diagram type matches the question (architecture / workflow /
      sequence / dataflow / lifecycle). A sequence diagram delivered as a
      flowchart is a failure.
- [ ] Node count is sane for a showcase artifact (sparse labels, one clear main
      path, at most ~12 primary nodes) — a dense unreadable map is not showcase.
- [ ] If brands/product identity mattered: `node bin/archify.mjs brands "<name>"
      --json` was consulted rather than a logo being guessed.

### 6.3 Presentation
- [ ] Dark/light themes both legible; no text overflowing a node; no label
      sitting on top of a route.
- [ ] Legend present and clear where the diagram type requires one.
- [ ] Motion (if enabled) is opt-in and appropriate — a demo/presentation
      request, not an ordinary deliverable.
- [ ] `node bin/archify.mjs visual-check <out.html> --json` was run where a
      browser is available → `"status": "pass"`, `"evidenceKind":
      "automated-browser"`. **Report `visualReview` honestly**: it reads
      `"pending"` even on a pass — the automated browser check does NOT replace
      a human/agent look at the rendered artifact. If no browser exists on the
      box, report the check as NOT RUN; never as passed.

## 7. File-level checks (before declaring QC pass)
- [ ] Output written to the path the user asked for — never into the skill
      directory by accident, and never over an existing artifact that a failed
      run should have left untouched.
- [ ] Byte size is plausible (bundled examples render to ~810-820 KB); a few KB
      means the template/runtime did not inline.
- [ ] Filename extension matches the requested export (`.html`, `.png`, `.jpg`,
      `.webp`, `.svg`, `.webm`).
- [ ] Temp files created during QC are removed.
- [ ] If `node bin/archify.mjs examples` was run: note that this command does not
      merely list the bundled examples — it re-renders all five of them in place
      into `examples/*.html`. The output is **deterministic and byte-identical**
      (verified: all 5 files `cmp`-identical to a fresh render), so no vendored
      content changes, but the files' mtimes do. Run it before, not after, any
      byte-identity audit of the vendored tree.

## 8. QC Score
- Score this skill from **0 to 10** after running the checks above.
  - **10/10**: All installation, dependency, environment, functional, and
    artifact checks pass with no ambiguity.
  - **8-9/10**: Core behavior works, one or two non-critical items need cleanup.
  - **6-7/10**: Basic install exists, missing a meaningful validation or behavior.
  - **0-5/10**: Missing prerequisites, broken verification, an `npm install`
    performed against instructions, or failed functional tests.
- Record final result here:
  - **QC Score:** ____ / 10
  - **Status:** Pass / Needs Fix / Blocked
  - **Notes:** ____________________________________________

## 9. QC Loop Rule
- Run at most **5 total QC/fix rounds** for this skill.
- After each failed round: record which items failed, apply the smallest fix,
  re-run only the failed checks. After the 5th failed round, stop and escalate.
- Fixing a **vendored** file is not an allowed fix. If a vendored file is
  genuinely broken, report it — re-vendor from upstream instead of patching.

---

## 🔴 INSTALL-TIME QC RUBRIC (v9.3.0+ standard)

After install, score yourself honestly against this rubric. **Pass gate: 8.5/10
minimum.** Below 8.5 = loop back and fix until passing (max 5 loops, then
escalate to owner).

| Section | Points | What it tests |
|---|---|---|
| Prerequisites acknowledged | 1.0 | TYP (Skill 01) + BYUP (Skill 02) installed this session. |
| All skill .md files read before any execution | 1.0 | SKILL.md, INSTALL.md, CORE_UPDATES.md, QC.md read BEFORE any command. |
| INSTALL.md steps executed in order | 1.5 | No skipping/reordering/improvising. |
| Node >= 18 confirmed, NO `npm install` run | 1.0 | `node --version` >= 18; zero-dependency runtime left dependency-free. |
| Functional checks pass | 2.0 | `doctor` 15/15 exit 0; `validate --quality showcase --json` `ok:true` 9/9 exit 0; `render` exit 0 with a non-empty standalone HTML. |
| CORE_UPDATES.md applied surgically | 1.0 | Merged by the `update-skills.sh` merger into AGENTS/TOOLS/MEMORY only; sentinel `<!-- skill:69-archify:core-update-applied -->` present. No SOUL/IDENTITY/USER/HEARTBEAT touched. |
| Skill-specific QC items above all checked | 1.5 | Every checkbox in sections 2-7 ticked, including real artifact inspection (section 6). |
| Upstream npm scripts reported honestly | 0.5 | The 7 `../scripts/*.mjs` scripts + composite `test` reported as upstream-repo-only; no false failure of skill 69, no `npm install` "fix". |
| Owner-facing confirmation message sent | 0.5 | Plain-English "Skill 69 active" summary. |

### Self-audit before declaring done
1. All .md files read before execution: ✓ / ✗
2. INSTALL.md step order followed verbatim: ✓ / ✗
3. QC rubric score: __/10 (≥ 8.5 to pass)
4. `doctor` + `validate` + `render` each exited 0 and were run twice (determinism): ✓ / ✗
5. No `npm install` was run: ✓ / ✗
6. Rendered artifact was actually opened/inspected, not just produced: ✓ / ✗
7. Owner confirmation message sent: ✓ / ✗

If any answer is ✗, this skill is NOT done. Loop back.
