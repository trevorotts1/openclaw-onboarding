# Skill 43 — INSTALL (One-Time Setup)

The skill folder ships with the onboarding package — `install.sh` / `update-skills.sh` copy every `NN-slug/` folder verbatim, so `43-graphify-knowledge-graph/` lands at:
- Mac: `~/.openclaw/skills/43-graphify-knowledge-graph/`
- VPS: `/data/.openclaw/skills/43-graphify-knowledge-graph/`

No separate download step for the skill folder. This file covers installing graphify itself, registering the OpenClaw skill, the **one-time** map of the client's workforce, the free auto-rebuild hook, and wiring `/graphify`.

> All commands below are verified against https://github.com/safishamsi/graphify and the walkthrough reference in `references/GRAPHIFY-COMMANDS.md`. Do not invent flags — use the reference.

---

## 🔴 NO CO-MINGLING (read before Step 3)

The map is built from **THIS client's OWN** workspace using **THIS client's OWN** model. NEVER point graphify at another client's workspace, and NEVER use the operator's API keys for the semantic pass. If the client's own model/Ollama is not ready, **STOP and WAIT** — see `../NO-COMINGLING-RULE.md` and AGENTS.md N0.

---

## 1. Prerequisites

| Requirement | Status | Why |
|---|---|---|
| `uv` installed (or `pipx`/`pip3`) | **Required** | To install graphify. Mac: `brew install uv`. |
| Skill 23 (AI Workforce Blueprint) built | **Recommended** | The default thing to map is the client's `zero-human-company/<slug>/` workforce. Without it, map a code/docs folder instead. |
| Client's OWN model available | **Required for the semantic pass** | Their local Ollama (preferred — free + private) or their configured model. NEVER the operator's keys. |
| `git` repo for the mapped folder | **Recommended** | Required for the free AST auto-rebuild hook (`graphify hook install`). |

## 2. Install graphify + register the OpenClaw skill

```bash
# 2.1 — Install graphify (PyPI package is "graphifyy" — double-y; CLI is "graphify").
#       The [all] extra pulls in every optional extractor (docs/audio/etc.).
uv tool install "graphifyy[all]"
#   Fallbacks if uv is unavailable:
#     pipx install "graphifyy[all]"        # OR
#     pip3 install --user "graphifyy[all]"

# 2.2 — Register the OpenClaw skill so the client's agent can drive graphify from natural language.
graphify install --platform claw
```

`graphify install --platform claw` registers the `/graphify` skill for OpenClaw (the claw platform), so the agent learns the `query` / `path` / `explain` commands and uses them automatically.

## 3. Map the client's workforce ONCE — with the CLIENT'S OWN model

Pick the target to map. Default = the client's workforce tree; otherwise a code/docs folder.

```bash
# Resolve the client's workforce dir (Mac shown; VPS uses /data/.openclaw/...).
# Use the ACTIVE client's slug — never another client's.
WORKFORCE="$HOME/.openclaw/workspace/zero-human-company/<slug>"   # Mac
# VPS: WORKFORCE="/data/.openclaw/workspace/zero-human-company/<slug>"

cd "$WORKFORCE"

# 3.1 — Map ONCE using the client's OWN local Ollama (free + private).
#       deepseek-v4-pro:cloud via their Ollama, or whatever the client has configured.
#       NEVER the operator's keys.
OLLAMA_BASE_URL="http://localhost:11434" \
OLLAMA_MODEL="deepseek-v4-pro:cloud" \
graphify extract . --backend ollama
```

This is the **one-time semantic pass**. It writes `graphify-out/` (`graph.html`, `GRAPH_REPORT.md`, `graph.json`) into the mapped folder.

> The semantic re-map is **owner-triggered only**. Do NOT schedule it or run it on every commit — that would burn the client's model time. To re-map later (after big changes), the owner runs `/graphify .` again (or the `graphify extract . --backend ollama` line above).

> If the client's Ollama is not running / not configured: **STOP**. Do NOT substitute the operator's keys or another client's model. Surface the gap and wait. (You can still install the FREE AST hook in Step 4 — it needs no model.)

## 4. Install the FREE auto-rebuild hook (AST only — no model, no cost)

```bash
cd "$WORKFORCE"   # must be a git repo
graphify hook install
```

This installs post-commit / post-checkout git hooks that re-run the **AST structure pass only** on every commit — deterministic, local, **free**. The structural graph stays current between owner-triggered semantic re-maps. (The semantic pass is NOT part of the hook.)

## 5. Wire `/graphify` so the agent uses the graph for codebase/workforce questions

`graphify install --platform claw` (Step 2.2) already registers the skill. Confirm the agent reaches for it FIRST on codebase/workforce questions by applying CORE_UPDATES.md (AGENTS.md + TOOLS.md). The rule the agent must learn:

> When the owner asks how something is wired / what depends on what / where something lives — and `graphify-out/` exists — treat it as a **graphify query first** (`/graphify query "..."`, `/graphify path A B`, `/graphify explain X`) before grepping or spawning explore agents.

## 6. Verify

```bash
bash ~/.openclaw/skills/43-graphify-knowledge-graph/scripts/verify-graphify-install.sh
# VPS: bash /data/.openclaw/skills/43-graphify-knowledge-graph/scripts/verify-graphify-install.sh
```

Checks: graphify CLI present, claw skill registered, `graphify-out/graph.json` exists for the mapped folder, and the hook is installed. Then run the full install QC:

```bash
bash ~/.openclaw/skills/43-graphify-knowledge-graph/qc-graphify-knowledge-graph.sh
```

## 7. Core file updates

Apply the appends in CORE_UPDATES.md to the workspace's AGENTS.md, TOOLS.md, and MEMORY.md.
