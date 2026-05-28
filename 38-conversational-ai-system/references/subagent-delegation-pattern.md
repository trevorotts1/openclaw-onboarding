<!--
Operator note: This file is a VERBATIM extraction from the source playbook
`openclaw-cloudflare-tunnel-prompt (1).md` (v5.14), lines 151–426 (Subagent
Delegation Pattern). No paragraphs were stripped, summarized, or reworded.
Do not edit content below this header without consulting the source playbook.
-->

## 🤝 SUBAGENT DELEGATION PATTERN (READ BEFORE SELF-ORIENTATION)

This playbook is long (~3,000 lines) and the work is intensive. The recommended execution pattern is a **two-agent split**: the main agent stays with the operator and acts as their UI, while a dedicated **install subagent** with a high-reasoning model executes Phases 0–6 of this playbook. The main agent does NOT execute the playbook itself; it delegates.

### When to use the subagent pattern (default: YES)

Use a subagent in nearly all cases. The exceptions are narrow:

- **Skip subagent ONLY IF** OpenClaw's `sessions_send` (or equivalent agent-to-agent dispatch) is unavailable on this install, OR if the operator explicitly requests single-agent execution.
- **In all other cases**, the main agent spawns a subagent and supervises.

### Subagent architecture

```
┌─────────────────────────────────────────────────────────────┐
│  MAIN AGENT                                                 │
│  (stays with operator, fast/cheap model, e.g. Gemini 3.1)   │
│                                                             │
│  Responsibilities:                                          │
│   • Welcome the operator, gather initial inputs             │
│   • Spawn install subagent with this full playbook          │
│   • Relay subagent's questions to operator                  │
│   • Relay operator's answers back to subagent               │
│   • Surface progress updates to operator every few steps    │
│   • Receive final summary from subagent and display         │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │ progress + questions + answers
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  INSTALL SUBAGENT                                           │
│  (executes the playbook, HIGH-reasoning model, fresh ctx)   │
│                                                             │
│  Responsibilities:                                          │
│   • Apply Teach Yourself Protocol to ingest this playbook   │
│   • Execute Phases 0 through 6 step by step                 │
│   • At each operator decision point, send question UP to    │
│     main agent (NOT directly to operator)                   │
│   • Maintain the Run Manifest                               │
│   • Publish progress updates after each phase checkpoint    │
│   • Send final summary up to main agent at QC pass          │
│                                                             │
│  Time budget: 45 minutes (with extension allowed)           │
└─────────────────────────────────────────────────────────────┘
```

### Subagent model selection

The install subagent does NOT use the conversational reply model (e.g., Gemini 3.1 Flashlight). It uses a heavy-reasoning, large-context-window model because:

- The playbook is ~3,000 lines — needs a high context window to ingest fully
- Setup involves long sequential reasoning across 11 steps + 7 phases + 7 checkpoints
- One-shot quality matters more than per-token latency
- Failure cost is high (broken setup is hours of debugging)

**Recommended install subagent models (in priority order):**

1. **`deepseek/deepseek-v4-pro`** via OpenRouter or Ollama Cloud, with thinking set to `max`. ~1M context, deep reasoning, best long-instruction following.
2. **`google/gemini-3.5-flash`** via OpenRouter. ~2M context, very fast, good reasoning. Best if budget is a concern.
3. **`ollama/deepseek-v4-flash`** with `thinking: max`. Free if Ollama Cloud is configured. Slightly less capable than Pro but workable.
4. **`anthropic/claude-opus-4-7`** via Anthropic API. Highest quality if available; most expensive.

Verify model availability against `openrouter.ai/models` and `ollama.com/library` at run-time (per Self-Orientation O.3) — newer models may have superseded these.

### Question-routing protocol

When the install subagent needs an operator decision (routing agent, model preferences, knowledge sources, etc.):

1. Subagent does NOT message the operator directly.
2. Subagent uses `sessions_send` (or equivalent) to post the question UP to the main agent with a structured payload:

```json
{
  "type": "operator_question",
  "subagent_session_id": "<id>",
  "phase": "<current phase>",
  "step": "<current step>",
  "question": "<the question text the operator should see>",
  "options": ["<option 1>", "<option 2>", "..."]
}
```

3. Main agent receives this, displays it to the operator in conversational form.
4. Operator answers the main agent.
5. Main agent posts the answer DOWN to the subagent with:

```json
{
  "type": "operator_answer",
  "subagent_session_id": "<id>",
  "answer": "<the operator's answer>"
}
```

6. Subagent continues execution.

### Progress update protocol

After each phase checkpoint passes (A through G), the subagent posts a brief progress update UP to the main agent:

```json
{
  "type": "progress_update",
  "subagent_session_id": "<id>",
  "phase_completed": "Phase 2",
  "checkpoint": "C — OpenClaw responds to inbound webhooks",
  "elapsed_minutes": 18,
  "summary": "Tunnel built, OpenClaw configured, end-to-end test passed. Moving to credentials persistence."
}
```

Main agent displays a concise version to the operator: "✓ Phase 2 complete (18 min) — OpenClaw is now receiving webhooks. Moving to next phase."

### Time budget

- **Soft target:** 45 minutes for Phases 0–6
- **Hard limit:** 90 minutes — at that point the subagent must report what's incomplete and either request an extension or hand control back to the main agent
- **Per-phase soft targets** (subagent self-monitors):
  - Phase 0 (Orient): 3-5 minutes
  - Phase 1 (Network plumbing): 8-12 minutes
  - Phase 2 (OpenClaw config): 8-12 minutes
  - Phase 3 (Credentials + deliverables): 3-5 minutes
  - Phase 4 (Agent behavior): 5-8 minutes
  - Phase 5 (Advanced features): 6-10 minutes
  - Phase 6 (Capabilities playbook): 3-5 minutes

If a phase runs >2x its soft target, subagent reports a slowdown and surfaces what's taking time.

### Failure escalation

If the install subagent encounters a hard failure (per Rules of Engagement Rule 4):

1. Subagent restores backups taken so far
2. Subagent posts a failure report UP to main agent with: phase, step, error, what was restored, what's still in a partial state
3. Main agent displays this to operator and asks: "Should I retry the failing step, roll back the entire setup, or get me a human?"
4. Operator's answer flows back down. Subagent acts accordingly.

### Spawning the subagent (main agent's only Phase 0 task)

When the main agent receives this playbook from the operator, it does NOT begin execution. Instead, it walks through this exact sequence:

**Step 1 — Greet operator, confirm intent**

```
"Hi! I see you want to install or upgrade the Convert and Flow AI
system. I'll walk you through it. Before we start, a quick question
about HOW you want me to handle this."
```

**Step 2 — Ask: subagent or main agent? (EXPLICIT CHOICE)**

```
"This installation is a multi-step process (about 45 minutes). You
have two options for how I run it:

  1. RECOMMENDED — Spawn a high-reasoning subagent to handle the
     installation. I'll stay here with you as the UI: routing
     questions to you, showing you progress every 10 minutes, and
     handing back the final summary. The subagent gets a fresh
     context with a heavy model so it can think deeply through
     each step.

  2. I'll handle it myself in our current conversation. Simpler, but
     it consumes our context window — you may need to clear it
     first.

Which do you prefer? (I recommend option 1.)"
```

Wait for operator answer. Capture as `EXECUTION_MODE` = `subagent` or `main-agent`.

**Step 3 — Context window capability check (BOTH paths)**

The main agent inspects the current conversation context and decides whether the model has room to complete the installation.

```python
# Pseudocode for the main agent's reasoning:
playbook_token_estimate = 120_000  # ~4,800+ lines markdown as of v5.4 — this number grows with each version; agent should check current line count and re-estimate
current_context_used = <main agent estimates from session>
context_window_max = <known per model: gemini-3.1-flashlight=1M, gemini-3.5-flash=2M, etc.>
headroom_needed = playbook_token_estimate + 50_000  # buffer for execution

if EXECUTION_MODE == "main-agent":
    if (context_window_max - current_context_used) < headroom_needed:
        # Not enough room
        recommend_new_session = True
```

If `EXECUTION_MODE = main-agent` AND context is too tight, the main agent says:

```
"Before we start: I've checked my current context window and there
isn't enough room to safely run the full installation in this
conversation. I'd like you to run /new to start a fresh session,
then paste the playbook back to me there. /new is safer than
/compact because /compact can compress the playbook's instructions
and cause execution errors.

After you run /new and paste the playbook back, I'll pick up where
we left off."
```

If `EXECUTION_MODE = subagent`, this check still happens BUT the recommendation is different: "I have enough room to manage the subagent. The subagent will get its own fresh context, so /new isn't needed."

**Step 4 — Verify subagent model availability (subagent path only)**

```
"I'll spawn the install subagent. My default recommendation is
deepseek/deepseek-v4-pro with thinking set to 'max' (deep reasoning,
large context). Alternatives:
   - gemini-3.5-flash via OpenRouter (faster, slightly less deep)
   - ollama/deepseek-v4-flash with thinking:max (free if Ollama
     Cloud is configured)
   - claude-opus-4-7 via Anthropic API (highest quality, highest cost)

Stick with the default, or pick another?"
```

Verify the chosen model exists in the OpenClaw config and has an API key available. If not, prompt for the missing credential before spawning.

**Step 5 — Spawn the subagent (subagent path) OR begin executing (main-agent path)**

If subagent: spawn via `sessions_send` with a fresh session passing the full playbook, the system prompt, the chosen model, and the heartbeat configuration (see below).

If main-agent: begin with Self-Orientation Step O.1.

**Step 6 — Begin the relay loop (subagent path)**

Main agent now listens for two streams:
- **From subagent:** questions, progress updates, heartbeats, completion, failure
- **From operator:** answers, redirects, abort signals

Main agent routes between them.

**Step 7 — On subagent completion: display final summary, end**

When subagent posts the sealed Run Manifest, the main agent displays the final summary (Part 4 of this playbook) to the operator and ends the relay loop.

### 10-minute heartbeat protocol (subagent path)

The subagent must report progress every 10 minutes regardless of phase boundaries. This prevents the operator from sitting in silence during long phases.

**Heartbeat structure:**

```json
{
  "type": "heartbeat",
  "subagent_session_id": "<id>",
  "elapsed_minutes": <minutes since spawn>,
  "current_phase": "<Phase N: name>",
  "current_step": "<Step N.N: name>",
  "step_progress_summary": "<one sentence — what's happening right now>",
  "expected_next_milestone": "<one sentence — what's next>"
}
```

**Main agent action on heartbeat:**

Display to operator in conversational form: "Still working — at [elapsed] min, [current step], [progress summary]. Next: [next milestone]."

**Heartbeat termination (HARD CAP at 90 minutes):**

The heartbeat stops automatically when ANY of these conditions occurs:
- The subagent completes successfully (Run Manifest sealed)
- The subagent reports a hard failure
- The subagent reaches the 90-minute hard limit (per the Time Budget section above)
- The operator issues an abort signal

The heartbeat MUST NOT continue past 90 minutes. If the 90-minute hard limit is reached without completion, the main agent stops the heartbeat, asks the operator whether to grant an extension (one-time 15-minute extension allowed) or abort the run, and acts accordingly. The heartbeat does not silently persist indefinitely.

### Subagent's first action upon spawn

The install subagent, upon receiving this playbook as its initial context, begins with Self-Orientation Step O.1 (Teach Yourself Protocol). It does NOT skip the orientation phase. The subagent is a fresh context and must orient itself the same way a standalone agent would.

---

