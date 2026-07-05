# Skill 43 — Graphify Knowledge Graph — Changelog

## 1.0.3 — 2026-07-05

Correctness pass on the install docs, the model claims, and the install QC (skills-analysis sweep — FIX-S36-21..24, FIX-XC-09d).

- **Semantic map no longer 404s on every install.** `OLLAMA_BASE_URL` is now pinned to the `…:11434/v1` form in INSTALL.md, CORE_UPDATES.md, and SKILL.md — graphify passes the base URL verbatim as the OpenAI-style base_url, so a bare `:11434` made the `POST /chat/completions` 404 and the semantic pass fail for every client. The install QC now asserts the `/v1` form and fails if a bare `:11434` base URL remains.
- **Install QC no longer always-red.** `qc-graphify-knowledge-graph.sh` hard-asserted `skill-version.txt == 1.0.0` while the file was already `1.0.2`, so the gate failed on every correct install and agents learned to ignore it. It now asserts the version is valid semver AND matches the `version:` field in SKILL.md frontmatter (the single source the skill loader reads) — no hardcoded literal to drift.
- **Corrected the false "free + nothing leaves the box" claim.** The docs defaulted `deepseek-v4-pro:cloud`, but a `:cloud` model runs on Ollama Cloud **off the box** and **bills the client** — neither free nor private. The default is now a genuinely-local model (e.g. `qwen2.5-coder:7b`), and every doc discloses that `:cloud` models are off-box + billed and are owner-opt-in only.
- **Sovereignty: bare re-map is now a documented violation.** A bare `/graphify .` re-map lets graphify's `detect_backend()` auto-pick a resident API key and can silently route the client's corpus to a paid/Anthropic backend. INSTRUCTIONS.md, CORE_UPDATES.md, and INSTALL.md now require the explicit `graphify extract . --backend ollama`, and CORE_UPDATES carries a binding BACKEND-PIN rule (FIX-XC-09d).
- **Verify step now checks the mapped folder.** INSTALL.md Step 6 passes `"$WORKFORCE"` to `verify-graphify-install.sh` so the graph + hook checks actually run against the mapped folder (advisory/WARN-only, since the map is owner-triggered); with no argument those checks are skipped.
- **Reference doc completed.** `references/GRAPHIFY-COMMANDS.md` adds the canonical `graphify extract . --backend ollama` row and an Ollama environment-variable table (`OLLAMA_BASE_URL` = `…/v1`, `OLLAMA_MODEL`) that INSTALL relies on.

## 1.0.2 — 2026-07-03

- Added the `version:` field to SKILL.md YAML frontmatter and aligned it with `skill-version.txt`, closing the SKILL.md-frontmatter-vs-skill-version drift the new repo frontmatter-version CI guard enforces.

## 1.0.1 — 2026-06-10

- Unified Mac + VPS repo (PRD 2.1): platform-aware paths throughout the skill docs (`~/.openclaw/…` on Mac, `/data/.openclaw/…` on VPS) so the one skill folder installs correctly on both platforms.

## 1.0.0 — 2026-06-06

Initial release. Ships graphify as standalone Skill 43.

- Installs graphify on the client box: `uv tool install "graphifyy[all]"` (with `pipx` / `pip3 --user` fallbacks).
- Registers the OpenClaw skill: `graphify install --platform claw`.
- Maps the client's OWN workforce ONCE using the CLIENT'S OWN model (`deepseek-v4-pro:cloud` via their local Ollama, `--backend ollama`, or their configured model) — NEVER the operator's keys.
- Installs the FREE AST auto-rebuild hook (`graphify hook install`) so the structural graph stays current on every git commit at no model cost.
- Wires `/graphify` (query / path / explain) so the client's agent reaches for the graph FIRST on codebase/workforce questions.
- Two-tier design made explicit: heavy semantic pass is on-demand (owner-triggered); AST rebuild is free + automatic.
- SKILL.md / INSTALL.md / INSTRUCTIONS.md / CORE_UPDATES.md, `references/GRAPHIFY-COMMANDS.md`, `scripts/verify-graphify-install.sh`, `qc-graphify-knowledge-graph.sh`.
- Carries the binding NO-COMINGLING rule: the graph and the model are this client's alone; if the client's model isn't available, STOP and WAIT — never substitute. References `../NO-COMINGLING-RULE.md` and AGENTS.md N0.
- All commands verified against github.com/safishamsi/graphify and docs.openclaw.ai. No client PII or working artifacts shipped.
