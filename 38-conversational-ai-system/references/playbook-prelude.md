<!-- OPERATOR HEADER -->
<!-- Skill 38 reference: VERBATIM extraction from openclaw-cloudflare-tunnel-prompt v5.14 (lines 25-149). -->
<!-- Contains: Terminology, Rules of Engagement (6 rules), Execution Order Map (7 phases). -->
<!-- Read this BEFORE executing any phase. The Rules of Engagement are gates, not suggestions. -->
<!-- Source: /Users/blackceomacmini/Downloads/openclaw-cloudflare-tunnel-prompt (1).md -->

## 🏷️ Terminology

This system has a few distinct components with distinct names. Getting them right matters:

- **Convert and Flow** = Christy's white-label version of GoHighLevel. It IS GHL, with Convert and Flow branding on top. Client-facing materials should refer to "Convert and Flow" rather than "GoHighLevel" when speaking to her clients. Functionally it's identical to GHL — same API endpoints (`services.leadconnectorhq.com`), same workflow builder, same Conversations system. The brand differs; the technology doesn't.

- **OpenClaw** = the AI agent platform that runs the conversational AI. Receives webhooks from Convert and Flow, processes them, replies via the installed GHL skill, takes actions like booking and invoicing.

- **The Conversational AI System** = the complete deployed setup. This is what this playbook builds — OpenClaw + Convert and Flow + the playbooks, protocols, and capabilities documents created during setup. There's no consumer-facing brand name for this whole stack; it's just "the conversational AI system" or "Christy's AI" when talking to a client.

When the agent is writing client-facing artifacts (Client Reference Sheet, communication playbooks, the overview PDF), it uses **Convert and Flow** to refer to the CRM layer. When writing AI-facing technical instructions (curl commands, API endpoints, JSON schemas), it uses **GHL** or **GoHighLevel** because those are the literal technical names at the API layer. Both refer to the same product — just different audiences.

---

## ⚖️ RULES OF ENGAGEMENT (READ THIS BEFORE TOUCHING ANYTHING)

These rules govern how the agent executes this playbook. They are not suggestions.

**Rule 1 — Follow the playbook to the letter.** Every step has been carefully designed, sequenced, and validated. The agent does not improvise, does not add steps "to be helpful," does not skip steps that seem redundant, and does not reorder steps for efficiency. Execute in the exact order specified.

**Rule 2 — Two and only two reasons to deviate.** The agent has explicit permission to adapt the playbook in exactly these cases, and only these cases:

  (a) **Documented OpenClaw schema change.** The agent has verified at `docs.openclaw.ai` and the OpenClaw GitHub `configuration-reference.md` that a field name, required parameter, or endpoint pattern has changed since this playbook was written. The agent must cite the doc URL and the specific change before adapting. Inference is not proof — only literal contradiction between the playbook and the current docs justifies a deviation.

  (b) **Unmet precondition on the client's machine.** A step's prerequisite isn't satisfied (e.g., the expected file doesn't exist, a command returns an unexpected error, an API key is missing). The agent stops, reports the unmet precondition to the operator, and waits for guidance before adapting.

**Rule 3 — No silent deviations.** Every deviation, however small, is logged to the Run Manifest with the reason, the doc evidence (if Rule 2a), and what was done instead. Future agents reading the manifest can audit what happened.

**Rule 4 — Stop at hard failures.** If a step fails irrecoverably (Cloudflare API returns 403 with no recovery path, OpenClaw config validation rejects the new block, the tunnel doesn't connect after 3 retries), the agent STOPS, restores any backups taken, reports the failure, and waits. The agent does NOT keep going hoping the next step compensates.

**Rule 5 — Verify before acting on irreversible changes.** Before any operation that's hard to undo (DNS record creation, cron job registration, config file writes), the agent does a dry-run check OR confirms with the operator. Backups must exist before any config edit.

**Rule 6 — The QC checkpoints are gates, not suggestions.** Mid-execution QC checkpoints (after each phase) must pass before moving to the next phase. A failed checkpoint means stop, report, and wait for operator decision.

---

## 🗺️ EXECUTION ORDER MAP

The full playbook is sequenced into seven phases. Each phase has specific steps and ends with a mini-QC checkpoint. The final phase is the full QC + hand-off.

```
┌──────────────────────────────────────────────────────────────────┐
│ PHASE 0 — Orient                                                 │
│   O.1  Apply Teach Yourself Protocol                             │
│   O.2  Save playbook to master files folder                      │
│   O.3  Verify OpenClaw version + schema + model freshness        │
│   O.4  Execute Backup Protocol                                   │
│   O.5  Locate secrets env file                                   │
│   O.6  Verify Dreaming + Embeddings config (v5.3)                │
│   O.7  Seed design principles into MEMORY.md (v5.4)              │
│   Initialize Run Manifest                                        │
│   Pre-flight checklist                                           │
│   ✅ Checkpoint A — Orientation complete                          │
├──────────────────────────────────────────────────────────────────┤
│ PHASE 1 — Build network plumbing                                 │
│   Step 1  Create Cloudflare tunnel + DNS CNAME                   │
│   Step 2  Install cloudflared as persistent service + restart    │
│   ✅ Checkpoint B — Tunnel verified end-to-end                    │
├──────────────────────────────────────────────────────────────────┤
│ PHASE 2 — Configure OpenClaw                                     │
│   Step 3   Configure hooks.mappings for GHL inbound              │
│   Step 3.5 Model selection wizard (real-time, async, batch)      │
│   Step 4   End-to-end test through public tunnel                 │
│   ✅ Checkpoint C — OpenClaw responds to inbound webhooks         │
├──────────────────────────────────────────────────────────────────┤
│ PHASE 3 — Persist credentials + deliverables                     │
│   Step 5  Save secrets to env file                               │
│   Step 6  Generate Client Reference Sheet                        │
│   ✅ Checkpoint D — Operator has copy-paste materials             │
├──────────────────────────────────────────────────────────────────┤
│ PHASE 4 — Install agent behavior                                 │
│   Step 7  Install classification rules into AGENTS.md            │
│   Step 8  Scaffold 8 channel communication playbooks             │
│   Step 9  Set up conversation log system                         │
│   Step 9.5  Install conversational safeguards (3 guardrails)     │
│   ✅ Checkpoint E — Agent is safety-ready and memory-ready        │
├──────────────────────────────────────────────────────────────────┤
│ PHASE 5 — Install advanced features (v5.0+)                     │
│   Step 9.6   Sentiment monitoring                                │
│   Step 9.7   PII scrubbing                                       │
│   Step 9.8   Quiet hours                                         │
│   Step 9.9   Compliance keyword detection                        │
│   Step 9.10  Multi-language detection                            │
│   Step 9.11  Confidence threshold escalation                     │
│   Step 9.12  Conversation export on customer request             │
│   Step 9.13  Conversational drift detection (v5.1)               │
│   Step 9.14  Knowledge Sources system (v5.1)                     │
│   Step 9.15  Prompt injection protection (v5.2)                  │
│   Step 9.16  Multi-channel operator notifications (v5.3)         │
│   Step 9.17  Conversation analytics dashboard (v5.3)             │
│   Step 9.18  Document generation actions (v5.3)                  │
│   Step 9.19  Smart Booking system + calendar setup (v5.3)        │
│   Step 9.20  Conversation Workflow Builder (v5.3)                │
│   Step 9.21  Humanizer Skill (always-on, v5.5)                   │
│   Step 9.22  Typed Knowledge Bases (v5.6)                        │
│   Step 9.23  Sales AI Brain (v5.7)                               │
│   Step 9.24  Web Scraper for Knowledge Bases (v5.8)              │
│   Step 9.25  Intelligent Follow-up (v5.9)                        │
│   Step 9.26  Discount Code Generation (GHL+Stripe, v5.10)        │
│   Step 9.27  Stripe Integration (full, v5.10)                    │
│   Step 9.28  Customer Journey Templates Library (v5.11)          │
│   Step 9.29  Business-Logic Workflow Suggestions (v5.11)         │
│   Step 9.30  Customer Service & Support (dual-mode, v5.12)       │
│   Step 9.31  Shopify Integration (v5.12)                         │
│   Step 9.32  Weekly Tune-up (v5.12)                              │
│   Step 9.33  Intelligent Playbook Routing (v5.13)                │
│   Step 9.34  Proactive Features Suite (v5.13)                    │
│   Step 9.35  Monthly Comprehensive Review (v5.14)                │
│   Step 9.36  Model Version Freshness Checker (v5.14)             │
│   ✅ Checkpoint F — Advanced features active                      │
├──────────────────────────────────────────────────────────────────┤
│ PHASE 6 — Document agent capabilities                            │
│   Step 10  Create Agent Capabilities Playbook                    │
│   ✅ Checkpoint G — Capabilities documented                       │
├──────────────────────────────────────────────────────────────────┤
│ PHASE 7 — Full QC + hand-off                                     │
│   Step 11  Pre-handoff QC protocol (full checklist)              │
│   Final Run Manifest seal                                        │
│   Final chat summary to operator                                 │
└──────────────────────────────────────────────────────────────────┘
```

The agent does NOT skip ahead. Each checkpoint must pass before the next phase begins. If a checkpoint fails, the agent stops and reports.

---
