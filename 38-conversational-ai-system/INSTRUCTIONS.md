# Skill 38 — Conversational AI System: Operator Instructions

These instructions walk an operator through the v5.14 conversational AI setup on a fresh OpenClaw install. The full source playbook lives at `references/v5.14-source-playbook.md` (8,797 lines, verbatim from Christy's v5.14 work). Treat that file as the canonical source of truth. This INSTRUCTIONS.md is the navigational guide — it tells you which Phase to do when and which file owns the detail.

> **Read first:**
> 1. `SKILL.md` (you read it)
> 2. `INSTALL.md` (prerequisites + scripts run order)
> 3. `references/conversational-ai-strategic-roadmap.md` (✅ shipped vs 📋 pending)
> 4. `references/v5.14-source-playbook.md` — the entire thing, in order. Pay special attention to Phase 0 Self-orientation (Steps O.1-O.7), Phase 5 (Steps 9.5-9.36 — the bulk of v5.14), and the Phase 7 Checkpoint F final verification.
> 5. `CORE_UPDATES.md` (what gets appended to workspace AGENTS.md + MEMORY.md)
>
> Per N3, read before act. Per N4, follow steps in declared order. **Do NOT skip a step because "skill X already does something similar."** Christy has reviewed the existing skills and made the call: v5.14's versions ship in full (see SKILL.md for the only intentional exception — humanizer-protocol.md is NOT shipped; skill 19 owns it).

---

## Phase 0 — Self-orientation (Steps O.1 through O.7)

Source: `references/v5.14-source-playbook.md` lines covering Phase 0 (Steps O.1-O.7).

Key automation in skill 38:

- `scripts/00-verify-prerequisites.sh` — Step O.1 prerequisite verification (skills 05, 10, 19, 29).
- `scripts/01-locate-master-files-folder.sh` — Step O.2 hardened semantic master-folder discovery. If multiple candidates exist, disambiguate; only CREATE a new folder as a last resort with operator approval.

After Phase 0: you have `MASTER_FILES_DIR` set, prerequisites verified, embeddings configured per O.6.

## Phase 1 — Build Network Plumbing (Steps 1-2)

Source: `references/v5.14-source-playbook.md` Steps 1-2 + `references/cloudflare-tunnel-troubleshooting.md` (failure-mode map).

- Step 1 — Create the Cloudflare tunnel via API (remotely-managed; per-tunnel connector token).
- Step 2 — Install cloudflared as a persistent system service (Mac: launchd via `sudo cloudflared service install <TOKEN>`. Linux: systemd post-install of apt package).
- Checkpoint B — tunnel verified end-to-end.

Skill 38 does NOT manage cloudflared installation; that's Phase 1 of the playbook itself. Skill 38 builds the BRAIN that sits behind the tunnel.

## Phase 2 — Configure OpenClaw (Steps 3 through 4)

Source: `references/v5.14-source-playbook.md` Steps 3, 3.5, 4.

- Step 3 — Configure OpenClaw's `hooks.mappings` for GHL inbound.
- Step 3.5 — Model selection wizard (REAL-TIME vs ASYNC tier). Recommend HIGHEST-REASONING available (DeepSeek V4 Pro thinking:max, Kimi 2.6+, etc. — see source playbook for the current recommendation list).
- Step 4 — End-to-end test through the public tunnel.
- Checkpoint C — OpenClaw responds to inbound webhooks.

## Phase 3 — Persist Credentials + Deliverables (Steps 5-6)

Source: `references/v5.14-source-playbook.md` Steps 5-6.

- Step 5 — Save secrets to the env file (per the v5.14 playbook block).
- Step 6 — Generate the Client Reference Sheet (Notion-first; fall back to markdown if no Notion).
- Checkpoint D — operator has copy-paste materials.

## Phase 4 — Install Agent Behavior (Steps 7-9)

Source: `references/v5.14-source-playbook.md` Steps 7, 8, 9.

- Step 7 — Install inbound message classification rules into AGENTS.md (skill 38's `scripts/05-update-agents-md.sh` handles part of this; the channel-classifying body is in the playbook).
- Step 8 — Scaffold the eight channel communication playbooks in Notion (SMS, Email, FB DM, FB Comments, Instagram DM, LinkedIn, Live Chat, All-in-One Chat).
- Step 9 — Set up the conversation log system. Owned by `protocols/conversation-log-protocol.md` (verbatim from playbook).

## Phase 5 — Install Advanced Features (Steps 9.5 through 9.36) — THE BULK OF v5.14

This is where the 27 protocols ship. The mapping table:

| Step | Protocol file in `protocols/` |
|---|---|
| 9.5  | `conversational-safeguards.md` (high-volume, long-conversation pause, bot-detection) |
| 9.6  | `sentiment-monitoring-protocol.md` |
| 9.7  | `pii-scrubbing-protocol.md` |
| 9.8  | Quiet Hours (smaller artifact in master-files folder, not a separate protocol file) |
| 9.9  | Compliance Keyword Detection (smaller artifact) |
| 9.10 | Multi-Language Detection (Section 7 of agent-capabilities-playbook.md, not a separate protocol file) |
| 9.11 | `confidence-threshold-protocol.md` |
| 9.12 | `conversation-export-protocol.md` |
| 9.13 | `drift-detection-protocol.md` |
| 9.14 | `knowledge-source-protocol.md` (older v5.1; preserved alongside v5.6's typed-knowledge-bases-protocol.md) |
| 9.15 | `prompt-injection-protection-protocol.md` |
| 9.16 | `notification-routing-protocol.md` |
| 9.17 | `conversation-analytics-protocol.md` |
| 9.18 | `document-generation-protocol.md` |
| 9.19 | `smart-booking-protocol.md` |
| 9.20 | Conversation Workflow Builder 3-layer (covered across `intelligent-routing-protocol.md` + GHL workflow registry; not a separate protocol file) |
| 9.21 | **Humanizer** — skill 19 (NOT shipped here; ALWAYS-ON via skill 38's AGENTS.md Step 2.8) |
| 9.22 | `typed-knowledge-bases-protocol.md` |
| 9.23 | `sales-best-practices-protocol.md` + `references/sales-frameworks-deep-dive.md` |
| 9.24 | `web-scraper-protocol.md` |
| 9.25 | `intelligent-followup-protocol.md` (the 10 touchpoints; first 5 in first 72 hours) |
| 9.26 | `discount-code-protocol.md` + `references/ghl-coupons-api.md` + `references/stripe-coupons-api.md` |
| 9.27 | `stripe-integration-protocol.md` + `references/stripe-webhooks-reference.md` (operator opt-in via `scripts/07-stripe-setup-wizard.sh`) |
| 9.28 | Customer Journey Templates — `templates/journey-templates/` (coach + 7 stubs + `registry.md`) |
| 9.29 | `business-logic-workflow-suggestions-protocol.md` |
| 9.30 | `customer-service-support-protocol.md` (dual-mode) |
| 9.31 | `shopify-integration-protocol.md` + `references/shopify-graphql-reference.md` (operator opt-in via `scripts/08-shopify-setup-wizard.sh`) |
| 9.32 | `weekly-tune-up-protocol.md` (Sunday 2am cron via `scripts/04-register-crons.sh`) |
| 9.33 | `intelligent-routing-protocol.md` |
| 9.34 | `proactive-suggestions-protocol.md` (Saturday 11pm cron) |
| 9.35 | `monthly-comprehensive-review-protocol.md` (1st-of-month cron) |
| 9.36 | `model-version-freshness-protocol.md` (bundled into Saturday 11:30pm cron) |

## Phase 6 — Document Agent Capabilities (Step 10)

Source: `references/v5.14-source-playbook.md` Step 10.

Generates the agent-capabilities-playbook.md the operator references during day-to-day use.

## Phase 7 — Full QC + Hand-off (Step 11)

Source: `references/v5.14-source-playbook.md` Step 11 (Checkpoint F).

Full pre-handoff QC checklist. Do NOT declare done until every item passes. Refer to the playbook for the checklist contents — verbatim, no summarization, no condensation.

---

## Cron schedule shipped by skill 38

| Cron | Schedule | What it runs |
|---|---|---|
| `weekly-tune-up` | `0 2 * * 0` (Sunday 2am) | `protocols/weekly-tune-up-protocol.md` |
| `proactive-suggestions-scan` | `0 23 * * 6` (Saturday 11pm) | `protocols/proactive-suggestions-protocol.md` |
| `model-version-freshness` | `30 23 * * 6` (Saturday 11:30pm) | `protocols/model-version-freshness-protocol.md` |
| `monthly-comprehensive-review` | `0 3 1 * *` (1st of month 3am) | `protocols/monthly-comprehensive-review-protocol.md` |

Sunday 2am is intentional: it runs BEFORE Dreaming's 3am nightly pass, so the tune-up gets the freshest week of data without conflicting with consolidation.

---

## Hard rules (NON-NEGOTIABLE)

- **Honesty floor** (per `sales-best-practices-protocol.md` + `customer-service-support-protocol.md`): never fabricate, never deceive, never false urgency, never promise refunds/exceptions without operator approval.
- **Cost caps** (per `web-scraper-protocol.md`): scrapes estimated over $5 require double-confirmation; over $25 are refused.
- **Operator approval requirements** (per `model-version-freshness-protocol.md`): never auto-update primary models. Always surface, always ask, always wait for YES/NO/DEFER.
- **Allow-list actions** (numbered 1-17 in the playbook): the agent's actions are gated to this list. Adding a new action requires updating both AGENTS.md and the relevant protocol file.

## Room for future features (per the strategic roadmap)

The roadmap shows 6 features pending after v5.14 (F14 Voice, F15 Proactive Outreach Campaigns, F16 A/B Testing, F17 Segmentation, F18 Webhook Chaining, F21 Multi-Tenant Isolation). The skill's structure is designed to absorb them without restructuring:

- `scripts/` folder is numbered 00-08 with room to grow (09 voice-setup, 10 outreach-campaigns, etc.).
- `protocols/` folder lists by name, not number — new protocols slot in alphabetically without reflow.
- `references/` accommodates new deep-dives without disturbing existing ones.
- `CORE_UPDATES.md` is semver-tagged at v1.0 so future v1.1/v1.2 land naturally.

Do NOT try to implement any of the pending features inside skill 38. They are explicitly out of scope for v5.14.
