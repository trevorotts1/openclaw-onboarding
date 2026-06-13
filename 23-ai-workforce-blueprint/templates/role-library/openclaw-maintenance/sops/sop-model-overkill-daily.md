# SOP Mirror -- Cost / Model Optimizer Specialist

**SOP ID:** `SOP-MAINT-MODEL-OVERKILL`
**Source:** openclaw-maintenance/cost-model-optimizer-specialist.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Cadence:** Daily
**Owner:** Cost / Model Optimizer Specialist (R2)
**Cross-cutting references:** SOP-MAINT-RESCUE-RANGERS-ESCALATION (S5), SOP-MAINT-PROACTIVE-FIX-GUARDRAIL (S6)

---

## 9. Standard Operating Procedures

### SOP 9.1 -- Daily Model Audit

**When to run:** Once daily, lightweight read-only scan of the box's model routing config.

**Inputs:**
- `openclaw.json` (agents config, model assignments per agent)
- Active workflow / cron definitions (model assigned per workflow node)
- Provider registry: what models are available on this box at zero/low cost (Ollama Cloud free tier, OpenRouter models the box is already credentialed for)

**Steps:**
1. Read every `agents[id].model` entry in `openclaw.json`. Build a list: agent_id -> current_model -> task_type (mechanical/search/build/converse/summarize).
2. For each agent, classify the task type based on the agent's playbook or role file description:
   - **Mechanical / administrative / poll / notify:** Haiku-class (cheapest). Any Opus or Sonnet here is overkill.
   - **Build / code generation / structured output:** Sonnet-class appropriate.
   - **Strategic think / complex analysis:** Opus-class appropriate only when explicitly designed.
3. Flag any agent where the assigned model class EXCEEDS the task type by >= 1 tier (e.g., Opus doing mechanical polling = definite overkill; Sonnet doing a heartbeat cron ping = overkill).
4. Flag any agent using a paid-API model when a free-tier equivalent is available on this box for the same task class (e.g., using OpenRouter paid Sonnet when Ollama Cloud deepseek-v4-pro:cloud can do the same mechanical task).
5. Check for by-design free-tier primaries (per memory `feedback-no-fable-token-furnace.md` and `ollama-cloud-is-valid-provider-id.md`): NEVER flag these as overkill even if they appear "high-tier" -- the design intent is free. Preserve free-tier primaries.
6. If NO overkill findings: log a clean-sweep entry and exit silently.
7. If findings: proceed to SOP 9.2.

**Outputs:**
- `working/maintenance/model-audit/audit-YYYYMMDD.json` (only written when findings exist; clean sweeps are silent)

**Hand to:** SOP 9.2 on findings; S5 for ambiguous by-design assignments. **Failure mode:** Cannot read `openclaw.json`: alert via Rescue Rangers (S5) and do not proceed.

---

### SOP 9.2 -- Right-Sizing Decision and Proposal

**When to run:** Immediately after SOP 9.1 identifies overkill assignments.

**Inputs:**
- `working/maintenance/model-audit/audit-YYYYMMDD.json`
- Provider docs (verify model availability and capability before proposing a swap)

**Steps:**
1. For each flagged agent, identify the cheapest model already available on this box that can handle the task. NEVER propose a model the box is not already credentialed for -- no new provider keys, no new subscriptions.
2. Write a proposed swap: `{ agent_id, current_model, proposed_model, task_type, reason, savings_estimate }`.
3. Determine the tier of the change per SOP-MAINT-PROACTIVE-FIX-GUARDRAIL (S6):
   - Tier 1 (auto-apply): model swap that is clearly mechanical and the replacement is free-tier / same-capability (e.g., a heartbeat cron from Sonnet to Haiku).
   - Tier 2 (apply + notify): any swap involving a non-trivial agent where the replacement has been doc-verified.
   - Tier 3 (propose + hold): any swap touching the main agent persona, a by-design free-tier primary, or a model the operator explicitly configured.
4. Apply Tier 1/2 swaps using `openclaw config set agents.<id>.model <new_model>` OR a JSON deep-merge (per the 8-layer memory activation pattern in memory: `openclaw-memory-activation-pattern.md`).
5. Run `openclaw config validate` after EVERY config edit. If validation fails, restore the backup immediately (S6 guardrail).
6. Notify operator via `openclaw message send --channel telegram` with the swap list and savings estimate. One message per daily audit cycle -- not per agent.

**Outputs:**
- Applied model swaps (Tier 1/2)
- Pending Tier 3 proposals in `working/maintenance/model-audit/pending-proposals.json`
- Operator notification

**Hand to:** SOP 9.3 (post-swap verification); S5 for Tier 3 proposals. **Failure mode:** Config validate fails after swap: restore backup, escalate to Rescue Rangers.

---

### SOP 9.3 -- Post-Swap Verification

**When to run:** After any model swap is applied.

**Steps:**
1. Dispatch a real live turn to the affected agent (one minimal test message).
2. Confirm the agent responds correctly with the new model (check response quality matches task class).
3. If response quality is degraded: revert the swap (restore prior model), update the ledger as REVERTED, and flag the task as Tier 3 for operator decision.
4. Update `working/maintenance/model-audit/audit-YYYYMMDD.json` with `verified_at` and `outcome: applied|reverted`.

**Outputs:** Updated audit entry. **Hand to:** S5 if revert was necessary. **Failure mode:** Cannot dispatch a live turn (gateway unreachable): escalate to SOP-MAINT-UPTIME (S4) first, then retry.

---

### SOP 9.4 -- By-Design Free-Tier Primary Protection

**When to run:** Before applying ANY model swap -- this is a pre-flight check embedded in SOP 9.2 Step 5.

**Steps:**
1. Check if the agent's current model matches any of these protected patterns:
   - `ollama-cloud/*:cloud` models where `models.providers.ollama.baseUrl = https://ollama.com` (free Ollama Cloud tier -- by-design primary per `ollama-cloud-is-valid-provider-id.md`)
   - Any model the operator's AGENTS.md or SOUL.md explicitly names as the primary agent model.
2. If the model is a by-design free-tier primary: MARK AS PROTECTED. Do NOT propose a swap. Log it as `protected_primary` in the audit entry.
3. If it is NOT protected: proceed with SOP 9.2 normally.

**Outputs:** Protected-primary flag in audit entry. **Hand to:** SOP 9.2. **Failure mode:** Cannot determine if model is by-design: mark as Tier 3 (propose only; never auto-change an ambiguous primary).

---
