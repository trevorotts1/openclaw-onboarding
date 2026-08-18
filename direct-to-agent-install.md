# Direct-to-Agent OpenClaw Install

**For:** Users who don't want to (or can't) run the terminal `curl ... | bash` command.
**Purpose:** Lets the user paste a single block of instructions directly to their agent (Telegram, OpenClaw dashboard, or any other agent surface) and have the agent perform the entire onboarding without ever touching a terminal.
**Pairs with:** `install.sh` (terminal path). Same end state. Triple-fire trigger (N22) fires on this path too.

---

## How to use

1. Open your agent surface (Telegram chat with your OpenClaw agent, or the OpenClaw dashboard chat).
2. Copy the ENTIRE block under "BEGIN AGENT INSTRUCTIONS" below.
3. Paste it as a single message to your agent.
4. The agent will follow the steps to install OpenClaw on your machine end-to-end.
5. Reply to any questions it asks (it may need your Telegram chat ID for pairing, etc.).

The agent is doing the same work `install.sh` would have done in your terminal — just from inside your agent.

---

## BEGIN AGENT INSTRUCTIONS

You are about to install or update OpenClaw Onboarding via the direct-to-agent path (no terminal). Follow these steps in order. Do NOT skip steps. Do NOT improvise.

### 0. Pre-flight — detect platform
Determine whether the target host is:
- **Mac:** `~/.openclaw/`, `~/clawd/`, `~/Downloads/openclaw-master-files/` apply.
- **VPS Hostinger Docker:** `/data/.openclaw/`, `/data/.openclaw/workspace/`, `/data/.openclaw/master-files/` apply.

For the rest of these instructions, substitute the correct paths for the detected platform.

### 1. Confirm capacity envelope
Verify the runtime allows:
- `maxSpawnDepth` ≥ 4
- `maxChildren` ≥ 20
- `maxConcurrent` ≥ 100
- `thinking` = "high"
- Wave concurrency cap: Mac ≤ 10 worker sub-agents, VPS ≤ 5

If any value is lower, halt and ask the user whether to proceed at reduced parallelism.

### 2. Pre-flight web research (N15)
Run the equivalent of `bash scripts/web-research-preflight.sh` — fetch:
- `https://docs.openclaw.ai/` (canonical settings reference)
- `https://ollama.com/library/<model>` for every `ollama/*` model in `openclaw.json`
- `https://openrouter.ai/<vendor>/<model>` for every `openrouter/*` model in `openclaw.json`

Write the consolidated result to `<config-root>/preflight-research.json`. If docs.openclaw.ai disagrees with the bootstrap/sub-agent settings below, **docs win** — log the discrepancy as a P1 ticket but use the docs values.

### 3. Bootstrap + sub-agent settings (N11, N12, N13)
Confirm or set:
- `bootstrap.maxChars = 200000`
- `bootstrap.maxTotalChars = 400000`
- `subagents.maxSpawnDepth = 4`
- `subagents.maxChildren = 20`
- `subagents.maxConcurrent = 100`
- `thinking = "high"` (every agent — orchestrator, sub-agent, QC)

### 4. Canonical workspace files
At workspace root, create or update:
- `USER.md` (owner profile + Behavioral Identity Profile)
- `AGENTS.md` (company-wide rules — symlinked into every per-role workspace)
- `TOOLS.md` (company-wide tool registry — symlinked)
- `SOUL.md` (company mission/beliefs)

### 5. Download skill files from GitHub
Fetch the latest skill bundle from the unified repo (auto-detects Mac vs VPS):
- Mac + VPS: `https://github.com/trevorotts1/openclaw-onboarding`

Place every skill folder under `<skills-dir>/`. Place root files (`Start Here.md`, `INSTALL-CONTRACT.md`, `AGENTS.md`, `cron-prompt.txt`, `check-updates.sh`, `force-update.sh`, etc.) at `<config-root>/`. Place `shared-utils/` under `<skills-dir>/shared-utils/`.

This delivery INCLUDES the Podcast Production Engine (skill 58) activation layer. Verify that all three of these files exist under `<skills-dir>/58-podcast-production-engine/scripts/` after the download:

- `register-podcast-hook.sh`
- `install-podcast-department.sh`
- `webhook/intake_handler.py` (the deterministic first step of the route's controllerId runbook)

If any one is missing, the download is incomplete: re-fetch the skill bundle before continuing. A box without these files can never activate a client podcast intake, and that failure is silent until an episode is missed. There is NO controller daemon and NO scheduler daemon in this design (the podcast department agent advances each flow in its own turn); the only recurring podcast cron is the daily smoke test (podcast-smoke-test.py via openclaw cron), so no controller or scheduler file should exist here.

### 6. Read the rules (N3, N4)
Before installing ANY skill, read every file in:
- `<skills-dir>/Start Here.md`
- `<config-root>/INSTALL-CONTRACT.md` (Rule 0: wave concurrency cap; Rule 1: read all .md before acting; etc.)
- `<config-root>/AGENTS.md` (N2 / N5 / N8 hard rules)

### 7. Install skills in waves
For each wave, BEFORE spawning sub-agents, gate with:

```
bash <skills-dir>/check-wave-concurrency.sh --proposed <N> --reason "wave-N-skill-install"
```

Exit 0 → spawn allowed. Exit 1 → reduce N or split the wave.

For each skill in the wave:
1. Spawn a dedicated worker sub-agent (non-Anthropic per N1 — use `select_model.py` purpose_tier="installer-subagent" to pick the model)
2. The orchestrator passes the FULL TEXT of the skill's `SKILL.md`, `INSTALL.md`, `QC.md`, every `.py`/`.sh` in `scripts/` to the worker (N8)
3. Worker reads all files, then executes `INSTALL.md` steps in declared order (N3, N4)
4. Worker exits with structured status
5. Independent QC sub-agent (different from worker per N5) runs:
   ```
   bash <skills-dir>/qc-agent.sh <skill-folder-name>
   ```
   Exit 0 + rubric ≥ 8.5 = PASS. Below 8.5 → reinstall (max 5 retry loops per N6).

### 8. Run system integrity check
After all waves complete:

```
bash <config-root>/skills/qc-system-integrity.sh
```

Must exit 0.

### 9. Verify the podcast activation layer (skill 58)

The Podcast Production Engine ships an activation layer: the inbound hook
registration, the deterministic intake handler (the first step of the route's
controllerId runbook), and the per-client department install. The design is
NO-DAEMON: the podcast department agent advances each flow in its own turn,
there is no controller daemon and no scheduler daemon, and the only recurring
podcast cron is the daily smoke test (podcast-smoke-test.py via openclaw
cron). Every install path (this one and the terminal `install.sh`) delivers
these three scripts, and Step 5 above checks they exist. This step verifies
the install actually landed, so a client podcast intake can never silently go
missing on this box.

1. Confirm all three files exist under `<skills-dir>/58-podcast-production-engine/scripts/`:

   - `register-podcast-hook.sh`
   - `install-podcast-department.sh`
   - `webhook/intake_handler.py`

   If any file is missing, re-download the skill bundle (Step 5) and re-check
   before continuing.

2. Run the activation health guard:

```
python3 <skills-dir>/58-podcast-production-engine/scripts/guard-activation-health.py
```

   The guard inspects the three activation artifacts plus the no-daemon box
   checks (route binding shape, department agent materialization, intake env
   secrets presence, no poller cron) and reports a pass when the layer is
   complete. A failing guard means the activation layer is absent or damaged;
   do not proceed to the interview until the health check passes.

3. Note: this step verifies that the activation layer is INSTALLED. It does
   not activate a client. Activation is per-client and happens inside
   `provision-podcast-client.sh` (skill 58 scripts), which invokes
   `install-podcast-department.sh` and `register-podcast-hook.sh` for one
   client slug at a time. A fresh box with no clients yet is expected to
   verify clean here with zero activated clients.

### 10. Run AI Workforce Interview (Skill 23)
Drive Skill 23 in interactive mode (or non-interactive with a saved config) to build the ZHC structure under `<workspace>/zero-human-company/<company-slug>/`.

### 11. Build per-role workspaces
For each department in the interview output:

```
python3 <skills-dir>/23-ai-workforce-blueprint/scripts/create_role_workspaces.py \
  --dept-path <workspace>/zero-human-company/<slug>/departments/<dept> \
  --roles-json <roles.json>
```

This creates the 7-file role layout (4 unique + 3 symlinks + how-to.md) AND the SOP/ subfolder AND writes `governing-personas.md` at department level.

### 12. Install Sunday cron
Install the weekly update-check cron at `0 3 * * 0` (3am Sunday).

**Register it SILENT — no `--channel`, no `--to`, no `--announce`:**

```
openclaw cron create --name weekly-onboarding-update --agent main \
  --cron "0 3 * * 0" --tz America/New_York \
  --session main --system-event "$(cat <config-root>/cron-prompt.txt)"
```

On CLI builds older than 2026.6.11, `--session main --system-event` is not
accepted; use `--session-target main --message "$(cat <config-root>/cron-prompt.txt)"`
instead. (`install.sh` probes `openclaw cron add --help` and picks the accepted
form automatically — this manual path has to choose.)

> **Do NOT add `--channel telegram --to <chat_id>` here.** That was the original
> wiring on this page and it is the bug. `cron-prompt.txt` already delivers its
> own messages deliberately, with `openclaw message send`, to a chat resolved by
> `resolve_owner_chat_id` (which rejects operator IDs). Adding cron-level
> delivery on top gives the job TWO independent delivery paths: the scheduler
> auto-delivers whatever the agent's final turn text happens to be — which, per
> the prompt's own "wait for the client's reply, do not exit" rule, is routinely
> a partial or internal status line, not the composed summary — while the real
> deliverable goes out separately. The run still reports success. That is how a
> fully-generated client deliverable gets silently lost.
>
> `install.sh` registers this cron SILENT and actively detects-and-deletes the
> old `--announce --channel telegram --to <client-chat-id>` wiring on
> already-provisioned boxes (see its CRON REWRITE MIGRATION block). A box
> onboarded from this page must land in the same state, not the one the
> installer exists to undo.
>
> Rule of thumb for every cron on a box: **exactly one delivery path.** Either
> the cron delivers (and the prompt must never self-send), or the cron is silent
> (and the prompt's own `message send` is the only delivery). Never both, and
> never a prompt that names a raw topic/chat id inline instead of resolving it.

### 13. Triple-fire confirmation
Confirm the install kickoff fired on all three channels:
- **Telegram:** message sent to paired chat
- **AGENTS.md flag:** marker written at `<config-root>/AGENTS.md` confirming onboarding kickoff
- **This reply:** the agent's reply to the user with a summary

### 14. Reply with summary
Reply to the user with:
- Total skills installed (target: 33)
- QC pass/fail count per wave
- Podcast activation layer status (the Step 9 health-guard result: all three activation scripts present and guard-activation-health.py passing)
- ZHC location
- Active department list
- Master Orchestrator agent ID
- Any P0 issues discovered during install

### Hard rules (apply throughout)
- No shortcuts. Read every .md and every script before acting on it.
- No self-QC. The agent that installs cannot also QC.
- All sub-agents non-Anthropic (Ollama Cloud → OpenRouter → Gemini).
- Persona governance on EVERY non-mechanical task.
- Master Orchestrator does NO work — sub-agents do work.

## END AGENT INSTRUCTIONS

---

## Comparison to the terminal `install.sh` path

| Step | Terminal install.sh | Direct-to-agent (this doc) |
|------|---------------------|----------------------------|
| Detect platform | bash conditionals | agent reads platform |
| Web research pre-flight | scripts/web-research-preflight.sh | agent fetches the same URLs |
| Settings config | install.sh writes openclaw.json | agent writes openclaw.json |
| Skill download | install.sh git/curl clones | agent git/curl clones |
| Podcast activation delivery | Step 5 wholesale copy + per-file presence guarantee | Step 5 file check (three activation scripts) |
| Podcast activation verify | scripts/audit-podcast-activation.sh | Step 9 guard-activation-health.py |
| Wave install + QC | install.sh + qc-agent.sh | agent invokes same scripts |
| Triple-fire kickoff | fire_install_kickoff_triplet() | agent sends Telegram + writes AGENTS.md flag + replies in chat |

**Same end state. Different driver.** The terminal path is faster for power users; the direct-to-agent path is for users who never want to open a terminal.

---

## When to use which

- **Terminal:** First install on a fresh Mac or VPS, or when you want a verifiable log file (`$LOG_FILE` written by install.sh).
- **Direct-to-agent:** Subsequent updates, or when the user isn't comfortable with terminal, or when the user is updating from inside Telegram on mobile.
- **Sunday cron:** Same direct-to-agent flow runs automatically via `cron-prompt.txt` every Sunday at 03:00.

---

**This document is the canonical direct-to-agent install spec.** Any agent receiving these instructions should follow them exactly. The instructions are versioned with the repo — re-fetch from GitHub `main` for the latest.

Versioned by: openclaw-onboarding (unified Mac + VPS repo).
