# Skill 43 — Graphify Knowledge Graph — Changelog

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
