# Skill 43 — EXAMPLES (Worked Flows)

Universal placeholders only. No real client data. All commands run ON THE CLIENT BOX.

---

## Example 1 — One-time install + map (at onboarding)

```bash
# 1. Install graphify on the client box
uv tool install "graphifyy[all]"        # VPS fallback: pip3 install --user "graphifyy[all]" --break-system-packages

# 2. Register the OpenClaw skill + wire AGENTS.md
graphify install --platform claw
cd ~/.openclaw/workspace                 # VPS: cd /data/.openclaw/workspace
graphify claw install

# 3. Install the FREE AST auto-rebuild hook (from inside the git workspace)
graphify hook install
graphify hook status

# 4. Map the client's OWN workforce ONCE, on the CLIENT'S OWN model
graphify . --backend ollama --model deepseek-v4-pro:cloud
```

Result: `graphify-out/graph.html` + `graph.json` + `GRAPH_REPORT.md` in the workspace.

## Example 2 — Owner asks: "Which department owns the billing flow?"

Graph already exists, so query it — do NOT rebuild:

```bash
graphify query "which department owns the billing flow?"
```

Answer the owner concisely. If the relationship the graph returns is `INFERRED`, say so ("the graph infers Billing → Finance Dept; not directly stated in the SOPs").

## Example 3 — Owner asks: "Trace a lead from intake to close"

```bash
graphify query "trace a lead from intake to close" --budget 1500
```

Or, for the precise relationship between two named nodes:

```bash
graphify path "Lead Intake" "Command Center"
```

## Example 4 — Code changed and was committed

Nothing to do. The FREE post-commit AST hook already re-ran structural extraction on the
changed files and rebuilt `graph.json`. Just query as usual. (No tokens spent.)

## Example 5 — Owner asks for a fresh DEEP re-read after big SOP changes

The semantic pass is owner-triggered and runs on the client's own model:

```bash
cd ~/.openclaw/workspace                 # VPS: /data/.openclaw/workspace
graphify . --backend ollama --model deepseek-v4-pro:cloud
```

NEVER do this on your own initiative or on a schedule — it costs the client's own model tokens.

## Example 6 — Owner has no usable model of their own

STOP. Tell the owner the semantic map needs their own model (their Ollama / configured model)
and cannot proceed. Do NOT substitute an operator API key, and do NOT map their workforce into
another client's graph (NO-COMINGLING-RULE.md / AGENTS.md N29). The FREE AST structural graph
can still be built (`graphify update .`) without any model.
