# Graphify — Command Reference

> Verified against https://github.com/safishamsi/graphify. Use these exact commands; do not invent flags.

## Install

```bash
uv tool install "graphifyy[all]"      # PyPI package is "graphifyy" (double-y); CLI is "graphify". [all] = all extractors.
# Fallbacks:
pipx install "graphifyy[all]"
pip3 install --user "graphifyy[all]"
```

## Register the OpenClaw skill

```bash
graphify install --platform claw      # registers the /graphify skill for OpenClaw (the "claw" platform)
graphify install                      # (Claude Code variant — not used on client boxes)
```

## Map / extract a folder (build the graph)

```bash
/graphify .                           # in the agent: map the current directory (semantic pass)
graphify extract ./folder             # headless CLI extraction (no IDE)
```

The output `graphify-out/` contains:
- `graph.html`  — clickable visual map
- `GRAPH_REPORT.md` — god-nodes, surprising connections, suggested questions
- `graph.json`  — queryable graph

## Query the graph

```bash
/graphify query "what connects auth to the database?"   # semantic search
/graphify path "UserService" "DatabasePool"             # shortest path between two nodes
/graphify explain "RateLimiter"                          # explain a node + its connections
```

## Free auto-rebuild hook (AST only — no model, no cost)

```bash
graphify hook install                 # post-commit + post-checkout hooks; re-runs the AST structure pass on every commit
```

The hook does the deterministic, local, FREE AST pass only. It does NOT run the semantic pass.

## Local Ollama backend (client's own model — free + private)

```bash
OLLAMA_BASE_URL=http://localhost:11434 \
OLLAMA_MODEL=deepseek-v4-pro:cloud \
graphify extract . --backend ollama

# Override the KV-cache context window if needed:
GRAPHIFY_OLLAMA_NUM_CTX=8192 graphify extract . --backend ollama
```

- `OLLAMA_BASE_URL` default: `http://localhost:11434`
- `OLLAMA_MODEL`    : auto-detect if unset; we set the client's configured model explicitly.
- **NEVER** set ANTHROPIC/OPENAI/etc. keys for a client's graph build — client's own model only.

## MCP server (optional — expose the graph as tools)

```bash
python -m graphify.serve graphify-out/graph.json
# tools exposed: query_graph, get_node, get_neighbors, shortest_path
```

## The two tiers (design summary)

| Pass | Engine | Trigger | Cost |
|---|---|---|---|
| AST structure | tree-sitter (local, deterministic) | every git commit (hook) | FREE |
| Semantic | the client's model (Ollama) | owner-triggered (`/graphify .`) | client's model time |
