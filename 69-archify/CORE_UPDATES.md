# Archify (69) - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

These sections are consumed by the format-robust CORE_UPDATES merger in
`update-skills.sh` (`wire_core_updates()`, v12.3.11). The merger appends each
section body into its target core file wrapped in
`<!-- BEGIN/END skill:69-archify:<target> -->` markers, resolves
`[MASTER_FILES_FOLDER]` to this box's absolute master-files path, and stamps
`<!-- skill:69-archify:core-update-applied -->` into AGENTS.md. Do NOT paste
these payloads by hand — during onboarding the merger runs automatically, and a
hand-paste has no idempotency marker and will duplicate on the next update.

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## Archify (69) - Diagram Authoring
- Diagram or visual-explanation request -> Archify (69). Types: architecture, workflow, sequence, dataflow, lifecycle.
- Reaches for it on: "visualize / show me the architecture", infrastructure or cloud / security / network topology, technical workflows, API call sequences, request lifecycles, data pipelines, ETL/ELT, data lineage, state machines, and "convert or beautify this Mermaid" (flowchart, sequenceDiagram, stateDiagram).
- Entry point: node [MASTER_FILES_FOLDER]/69-archify/bin/archify.mjs <command>
- Zero-dependency Node.js CLI (Node >= 18). There is NO npm install, no API key, no credential, and no network call. Never install dependencies for this skill.
- Author a typed JSON specification (schemas/ + one matching examples/ file). Never hand-write SVG, and never hand-place coordinates before a diagnostic asks for them.
- Validate before handoff: node bin/archify.mjs validate <type> <candidate.json> --quality showcase --json
  A showcase pass requires ALL 9 artifact checks ok with 0 composition errors and 0 warnings. A 4-check receipt is basic validation, never showcase acceptance.
- Deliver with: node bin/archify.mjs deliver <type> <candidate.json> <output.html> --quality showcase --json
- A non-zero exit can never be described as success, and a failed delivery preserves the previous output.
- Full reference: [MASTER_FILES_FOLDER]/69-archify/SKILL.md
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## Archify (69) - Diagram CLI (zero dependency)
- Command: node [MASTER_FILES_FOLDER]/69-archify/bin/archify.mjs <command>
- Prereq: Node.js >= 18 (`node --version`). NO npm install: package.json declares no dependencies, and the runtime imports only Node built-ins.
- Types: architecture | workflow | sequence | dataflow | lifecycle
- Commands: render, compare, deliver, preview, validate, migrate, inspect, check, visual-check, guide, brands, examples, demo, doctor (`--help` prints the full usage)
- validate <type> <input.json> [--json] [--layout-json] [--quality standard|showcase] [--repo-root path]
- render <type> <input.json> [output.html] [--quality standard|showcase]
- deliver <type> <input.json> [output.html] [--json] [--open] [--quality standard|showcase]
- visual-check <output.html> [--json] -> automated-browser receipt; status "pass" still reports visualReview "pending", so it does NOT replace looking at the artifact
- Output: ONE standalone HTML document with inline SVG, inline CSS and inline runtime (0 external script/link/img references; the bundled architecture example renders to ~811 KB)
- Upstream npm scripts (generate:viewer, check:viewer, check:release-identity, build:gallery, build:guide, build:start, build:readme-showcase, and the composite test) belong to the upstream archify monorepo, are intentionally not vendored, and are NOT usable here. Do not run npm install to "fix" them; the onboarding verifier is `bash scripts/onboarding-smoke.sh`.
- Full reference: [MASTER_FILES_FOLDER]/69-archify/SKILL.md
```

---

## MEMORY.md - UPDATE REQUIRED

Add:

```
## Archify (69) - installed
- Zero-dependency Node.js CLI (Node >= 18); entry point [MASTER_FILES_FOLDER]/69-archify/bin/archify.mjs; no npm install, no API key, no network
- Diagram types: architecture, workflow, sequence, dataflow, lifecycle -> one standalone HTML with inline SVG (dark/light themes, optional motion, PNG/JPEG/WebP/SVG/WebM export)
- Reach for it when asked to visualize architecture, workflows, API sequences, request lifecycles, data pipelines, data lineage or state machines, or to convert/beautify Mermaid
- Validate before handoff (`--quality showcase --json` must show 9/9 checks with 0 errors and 0 warnings); a non-zero exit is never success
- Full reference: [MASTER_FILES_FOLDER]/69-archify/SKILL.md
```

---

## IDENTITY.md - NO UPDATE NEEDED

---

## HEARTBEAT.md - NO UPDATE NEEDED

---

## USER.md - NO UPDATE NEEDED

---

## SOUL.md - NO UPDATE NEEDED
