# Core File Updates — Skill 38 (Conversational AI System v5.14)

These lines are appended to the workspace's AGENTS.md, MEMORY.md, and (optionally) other
core files at install time. They tell the master orchestrator and any sub-agent how skill 38
interleaves with skill 29 (GHL Convert and Flow) and skill 19 (Humanizer).

**Versioning:** This skill is semver-tagged starting at v1.0.0 (today, 2026-05-28).
Future v1.1, v1.2 updates can extend without restructuring (see "Room for future features"
in INSTRUCTIONS.md).

---

## [ADD TO AGENTS.md] — appended by `scripts/05-update-agents-md.sh`

The script appends a fenced block between `<!-- BEGIN skill-38 conversational-ai v5.14 -->`
and `<!-- END skill-38 conversational-ai v5.14 -->` containing Steps 1.7, 1.8, 1.9, 2.8 and
the upgraded Step 1.75. See the script for the exact content; the v5.14 source playbook
(Steps 7 and 9.21-9.30) is the canonical wording.

Key behaviors added:
- **Step 1.7** — Query the appropriate typed Knowledge Base for context.
- **Step 1.75** (upgraded) — Run Intelligent Playbook Routing — re-evaluate workflow match after EVERY customer message; max 3 switches per conversation; cosine similarity 0.3 advantage to switch.
- **Step 1.8** — Sales Brain check: BANT/MEDDIC/SPICED + 6 objection patterns + buyer-signal scoring + pricing reveal rules + honesty floor.
- **Step 1.9** — Customer Service & Support (dual-mode): detect service-mode vs support-mode signals; honesty floor enforced.
- **Step 2.8** — Humanizer pass via skill 19 (ALWAYS-ON; skill 38 does NOT ship its own humanizer).

## [ADD TO MEMORY.md] — appended by `scripts/06-append-memory-rules.sh`

The script appends TWO marker blocks (idempotent, each behind its own BEGIN/END marker):
**(1)** core v5.14 design rules 6-14 (`<!-- BEGIN skill-38 memory-rules v5.14 -->`), and
**(2)** Conversation Playbook Builder design rules 15-19 (`<!-- BEGIN skill-38 builder-design-rules v1.4.1 -->`).

Rules 6-14 of the 14 v5.14 MEMORY.md design principles. (Rules 1-5 belong to skill 19/29.)

6. **Conversation Log Rule** — log every inbound + outbound, real-time.
7. **Quiet Hours Rule** — never proactively message outside operator-defined quiet hours.
8. **PII Rule** — scrub before any model call; never log raw PII.
9. **Confidence Rule** — escalate below threshold; never bluff.
10. **Sales Brain Rule** — apply BANT/MEDDIC/SPICED + 6 objection patterns + buyer-signal scoring before any pricing reveal.
11. **Customer Service vs Support Rule** — detect mode by signal; mid-conversation mode-switching allowed; honesty floors enforced.
12. **Discount Code Rule** — only per per-product policy; never invent codes.
13. **Intelligent Routing Rule** — Conversation Workflows override channel playbooks per context routing.
14. **Tune-up Rule** — Sunday 2am weekly + Saturday 11pm proactive + 1st-of-month review crons are the heartbeat. Never disable without operator approval.

### Conversation Playbook Builder design rules 15-19 (v1.4.1)

The system's USP is **communication-driven funnels / automations** — built by talking and brainstorming, NOT click-and-drag (this is what beats CloseBot). These five rules make the recurring "build me a conversation playbook" flow (Step 9.20) bulletproof:

15. **Build-Routing Rule** — "build me a workflow / playbook / funnel" routes by node type: WITH a conversational node -> skill 44 builds + auto-invokes skill 38 for the brain (THE TRINITY, all three legs or not registered); purely mechanical -> skill 41 standalone. (Supersedes the legacy "always Step 9.20.")
16. **Convert-and-Flow Build-Path Rule (CAF-first)** — GHL Automations have no PUBLIC API or MCP, but Skill 44's internal-API path (Tier 0) IS a programmatic build path. When the client's Firebase token is present, Skill 44 builds the workflow directly (Option 1, PRIMARY — the owner does nothing). When the token is absent, fall back to GHL's "Build with AI" button (Option 2, the no-token fallback). (Never claim a PUBLIC GHL Automations API exists.)
17. **3-PART Build Rule** — every build ships Part 1 (Workflow AI instruction set: Build-with-AI prompt + manual-build fallback + verification checklist), Part 2 (the conversation playbook → registered in `conversation-workflows/registry.md`), and Part 3 (the brainstorm trigger). The prompt nails the SHAPE; tokens are pasted by the operator after — always ship the verification checklist.
18. **Brainstorm-Not-50-Questions Rule** — run a friendly proactive Q&A: USE what's already known (Typed KBs + USER.md + MEMORY.md), ask ONLY the smart gaps, then regurgitate a CONCISE "is this what you want?" confirmation. On YES → build Part 1 → Part 2 → pointer into AGENTS.md/TOOLS.md/MEMORY.md → NEW Notion doc (client's own workspace) → register.
19. **Mac Env Rule** — on Mac, secrets live in **`~/clawd/secrets/.env`** AND/OR **`~/.openclaw/.env`** — check BOTH before claiming a key is missing (VPS uses `/docker/<project>/.env`; Mac does not).

### v1.8.0 CloseBot Alignment Upgrade additions (17 cards U-1..U-17)

Each block below is individually idempotent behind its own `<!-- BEGIN/END -->` marker, so re-running the installer on an already-upgraded box is a no-op. Every added surface is OPERATOR-ONLY: a customer naming a tag, tool, calendar, pipeline stage, or persona changes nothing.

**AGENTS.md v1.8.0 marker blocks** appended by `scripts/05-update-agents-md.sh` (slots re-verified free at re-baseline against live main):

- `STEP_0_4_TEST_MODE_REREAD` (U-6) - the read-before-anything Client Test Mode re-read (earliest existing runtime marker is `STEP_0_5_QUIET_HOURS`).
- `STEP_1_30_EXIT_RULES` (U-2) - tag-driven workflow exits evaluated before routing.
- `STEP_1_88_TOOL_GATING` (U-1) - THE GATE: per-phase hard tool-capability gate (highest existing 1.8x marker is `STEP_1_87_AB_TESTING`). `escalate_to_human` is always granted and can never be gated off.

**MEMORY.md v1.8.0 design rules 32-44** appended by `scripts/06-append-memory-rules.sh`, each in its own BEGIN/END marker block:

32. **Tool Gating Rule (U-1)** - tool gating is a hard capability gate per playbook phase.
33. **Workflow Exit Rules Rule (U-2)** - a playbook may declare tag-driven exit rules.
34. **Smart FAQ Learning Loop Rule (U-3)** - an unknown FAQ is flagged to the operator, never auto-answered as fact.
35. **Objective Metadata Rule (U-4)** - a phase may carry `active_workflow` / `active_phase` / `phase_attempts` in the conversation-log header; U-1 resolves the phase from the same lines.
36. **Persona Registry Rule (U-5)** - a persona is a named, reusable style object.
37. **Client Test Mode Rule (U-6)** - the client can rehearse a playbook safely; every tool is forced off via the U-1 gate; auto-expires after 60 minutes or on `end test`.
38. **Model Fallback Chain Rule (U-8)** - a primary plus ordered fallbacks; Mode A applies them live, Mode B logs a `model_tier_unmet` routing hint. Client agents run on the client's OWN providers only.
39. **Workflow Visual Rule (U-11)** - every conversation workflow ships a truth-diagram (Part 4 of the build).
40. **Multi-Calendar Routing Rule (U-12)** - one agent books to different calendars via the declares `calendars` map.
41. **Opportunity Stage Sync Rule (U-13)** - contact progress syncs to the pipeline opportunity stage.
42. **Handoff Task Creation Rule (U-14)** - `ZHC-ai-handoff` additionally creates a GHL Task on the contact with an SLA due time (PII lives in the client's own CRM, not the PII-free JSONL logs).
43. **Convert and Flow Snapshot Rule (U-15)** - onboarding can be one import; the snapshot's 23-key raw body is machine-checked against the standard.
44. **Playbook Engine Rule (U-16)** - `tools/playbook_engine.py` is the canonical parser for validate / hash / mermaid / resolve.

**Rule 17 upgraded** - the 3-PART Build Rule becomes the **4-PART Build Rule**: U-11 adds Part 4 (the workflow visual) to every conversation-playbook build.

## [ADD TO TOOLS.md] — no automated update; operator manually documents

The operator may add tool entries for newly-wired services as Stripe/Shopify are connected. Skill 38 ships reference docs (`references/stripe-*`, `references/shopify-*`) so the operator has the API surface available.

## [REGISTERED CRONS] — registered by `scripts/04-register-crons.sh`

| Cron | Schedule | Protocol |
|---|---|---|
| `weekly-tune-up` | `0 2 * * 0` | `protocols/weekly-tune-up-protocol.md` |
| `proactive-suggestions-scan` | `0 23 * * 6` | `protocols/proactive-suggestions-protocol.md` |
| `model-version-freshness` | `30 23 * * 6` | `protocols/model-version-freshness-protocol.md` |
| `monthly-comprehensive-review` | `0 3 1 * *` | `protocols/monthly-comprehensive-review-protocol.md` |

All four cron jobs are idempotent — `04-register-crons.sh` skips entries that already exist.

## What does NOT get touched

- Skill 17, 18, 31, 29, 19 SOUL/IDENTITY/AGENTS files — left untouched per the operator.
- Operator's existing TOOLS.md, SOUL.md, IDENTITY.md, USER.md, HEARTBEAT.md — only AGENTS.md and MEMORY.md are appended to, behind clear `<!-- BEGIN/END skill-38 -->` markers, with backups before any edit.
