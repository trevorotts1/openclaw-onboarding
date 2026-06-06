# Skill 43 — INSTRUCTIONS (Runtime Guide)

How the client's agent uses the knowledge graph at runtime.

---

## When to reach for the graph FIRST

If the owner asks any of these — and `graphify-out/` exists for the relevant folder — treat the question as a **graphify query first**, before grepping files or spawning explore sub-agents:

- "How is my workforce / company / codebase wired?"
- "What depends on / connects to / talks to X?"
- "Where does X live? What touches X?"
- "Show me the path from A to B."
- "What are the most important / most-connected pieces?"
- "What's orphaned / disconnected?"

Graphify is cheaper and more accurate than grepping for these structural questions. Grepping/exploring is the fallback only when the graph cannot answer.

## The three query commands

```bash
# Semantic search across the graph
/graphify query "what connects the billing department to sales?"

# Shortest path between two nodes
/graphify path "AI Workforce Blueprint" "Command Center"

# Explain a single node (what it is, what connects to it)
/graphify explain "department-naming-map.json"
```

(Headless equivalents and the MCP server are in `references/GRAPHIFY-COMMANDS.md`.)

## Reading the report

`graphify-out/GRAPH_REPORT.md` surfaces:
- **God-nodes** — the most-connected pieces = the most important parts of the company/codebase.
- **Surprising connections** — non-obvious relationships worth knowing.
- **Suggested questions** — good starting queries.

Use the report to orient before answering "what matters most here?" questions.

## The two tiers at runtime (do not confuse them)

- **AST hook (free, automatic):** runs on every git commit, keeps the STRUCTURAL graph current. You never trigger this manually — it just happens.
- **Semantic re-map (owner-triggered):** when the owner wants a fresh semantic pass after big changes, run `/graphify .` (or `graphify extract . --backend ollama` with the client's Ollama). **Never** auto-run the semantic pass on a schedule or per-commit — it uses the client's model time and must be owner-triggered.

## The model + no-co-mingling rules at runtime

- Any semantic re-map uses the **client's OWN model** (their Ollama / configured model). NEVER the operator's keys.
- The graph is **this client's**. Never query, seed, or share another client's `graphify-out/`. If a needed model/resource isn't available, STOP and surface it — never substitute. See `../NO-COMINGLING-RULE.md` and AGENTS.md N0.

## Staleness

If the graph looks stale (big structural changes since the last semantic map), tell the owner and offer an owner-triggered re-map — do not silently run it. The free AST hook keeps structure fresh; only the semantic layer needs the owner's go-ahead.
