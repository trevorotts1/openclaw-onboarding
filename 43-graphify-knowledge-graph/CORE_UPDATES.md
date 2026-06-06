# Skill 43 — CORE_UPDATES

What this skill appends to the client's workspace core files. Apply once on install.

---

## AGENTS.md (append)

```markdown
## Graphify Knowledge Graph (Skill 43)

Graphify is installed at `~/.openclaw/skills/43-graphify-knowledge-graph/`
(VPS: `/data/.openclaw/skills/43-graphify-knowledge-graph/`). It maintains a queryable
knowledge graph of THIS client's OWN workforce/codebase in `graphify-out/`.

GRAPH-FIRST RULE: when the owner asks how something is wired / what depends on what /
where something lives / what's most important / what's orphaned — and `graphify-out/`
exists — use the graph FIRST:
  /graphify query "..."        — semantic search
  /graphify path A B           — shortest path between two nodes
  /graphify explain X          — explain a node + its connections
Only grep or spawn explore agents if the graph cannot answer.

TWO TIERS — do not confuse:
  • AST structure pass = FREE + AUTOMATIC on every git commit (graphify hook). Never run manually.
  • Semantic re-map  = OWNER-TRIGGERED ONLY (/graphify .). Uses the CLIENT'S OWN model
    (their Ollama / configured model — NEVER the operator's keys). Never schedule or
    auto-run the semantic pass; it costs the client's model time.

NO CO-MINGLING: the graph is THIS client's. Never query/seed/share another client's
graphify-out/. If the client's own model isn't available, STOP and surface it — never
substitute the operator's keys or another client's model. See ../NO-COMINGLING-RULE.md
and AGENTS.md N0.
```

## TOOLS.md (append)

```markdown
## Graphify (Skill 43)

- Map ONCE with the client's own Ollama (free + private):
    OLLAMA_BASE_URL=http://localhost:11434 OLLAMA_MODEL=deepseek-v4-pro:cloud \
      graphify extract . --backend ollama
- Free auto-rebuild hook (AST only, no model cost): `graphify hook install`
- Query: `/graphify query "..."` | `/graphify path A B` | `/graphify explain X`
- Verify install: `bash ~/.openclaw/skills/43-graphify-knowledge-graph/scripts/verify-graphify-install.sh`
  (VPS: `/data/.openclaw/skills/43-graphify-knowledge-graph/scripts/verify-graphify-install.sh`)
- NEVER use the operator's API keys for the semantic pass. Client's own model only.
```

## MEMORY.md (append — once the workforce is mapped)

```markdown
Graphify: workforce mapped [YYYY-MM-DD] | model: <client-ollama-model> | graphify-out/ live | AST hook ON | Skill 43
```

Update the date and model as the owner re-maps.
