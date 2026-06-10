# Skill 43 — graphify CLI surface (verified)

The exact graphify commands this skill relies on, verified against `graphify --help`
on the installed CLI. Load this when you need the precise flag/subcommand.

## Install / register / wire

| Command | What it does |
|---|---|
| `uv tool install "graphifyy[all]"` | Install graphify (full extras). Preferred. |
| `pip3 install --user "graphifyy[all]" --break-system-packages` | VPS-container fallback (apt is a brew shim — not used). |
| `graphify install --platform claw` | Copy the skill into OpenClaw's platform config dir (registers the skill). `claw` is a supported platform. |
| `graphify claw install` | Write a `## graphify` section into the workspace AGENTS.md (OpenClaw native wiring — makes `/graphify` always-on). |
| `graphify claw uninstall` | Remove the `## graphify` section from AGENTS.md. |

## Free auto-rebuild hook (no LLM)

| Command | What it does |
|---|---|
| `graphify hook install` | Install post-commit + post-checkout git hooks. FREE AST rebuild on every commit. |
| `graphify hook status` | Check whether the hooks are installed. |
| `graphify hook uninstall` | Remove the git hooks. |

## Build / map (semantic pass — client's OWN model)

| Command | What it does |
|---|---|
| `graphify . --backend ollama --model deepseek-v4-pro:cloud` | Full build/map of the current dir using the CLIENT'S OWN Ollama model. `--backend` accepts `gemini\|kimi\|claude\|openai\|deepseek\|ollama`; `--model` overrides the backend default. NEVER use an operator key here. |
| `graphify update .` | FREE structural (AST) re-extract of changed code — no LLM, no tokens. |
| `graphify cluster-only .` | Re-run clustering on an existing graph.json. |

## Query (read the graph — cheap, deterministic)

| Command | What it does |
|---|---|
| `graphify query "<question>"` | BFS traversal — broad context. Add `--dfs` to trace a path, `--budget N` to cap output. |
| `graphify path "A" "B"` | Shortest path between two nodes. |
| `graphify explain "X"` | Plain-language explanation of a node + neighbors. |

## Outputs (in `graphify-out/`)

- `graph.html` — interactive visual graph
- `graph.json` — GraphRAG-ready data (what `query`/`path`/`explain` read)
- `GRAPH_REPORT.md` — communities, god nodes, honest audit trail (EXTRACTED / INFERRED / AMBIGUOUS)
