# Conversational AI System — Strategic Feature Roadmap

This document tracks the features built into the Convert and Flow conversational AI system, plus the remaining features under consideration.

**Audience:** the operator (system owner) and their AI agents reading this for context on what's done, what's coming, and why.

**Status legend:**
- ✅ **Implemented** — feature is live in v5.4
- 📋 **Documented** — design is finalized, ready to build
- 💡 **Under consideration** — concept is sound, design pending

**Last updated:** May 28, 2026 (aligned with v5.4 of the main playbook)

---

# Part 1 — Completed Features

All 18 features below are now implemented as setup steps in the main playbook (`openclaw-cloudflare-tunnel-prompt.md`).

## Round 1 — original strategic features (Features 1-13)

| # | Feature | Implemented in | Step |
|---|---|---|---|
| 1 | High-volume activity warning | v5.0 | 9.5 |
| 2 | Long-conversation pause with owner review | v5.0 | 9.5 |
| 3 | Bot-detection protocol | v5.0 | 9.5 |
| 4 | Sentiment monitoring and emotional escalation | v5.0 | 9.6 |
| 5 | PII scrubbing in conversation logs | v5.0 | 9.7 |
| 6 | Quiet hours | v5.0 | 9.8 |
| 7 | Compliance keyword detection | v5.0 | 9.9 |
| 8 | Multi-language detection and matching | v5.0 | 9.10 |
| 9 | Confidence threshold escalation | v5.0 | 9.11 |
| 10 | Conversation export on customer request | v5.0 | 9.12 |
| 11 | Conversational drift detection | v5.1 | 9.13 |
| 12 | Knowledge Sources system | v5.1 | 9.14 |
| 13 | Prompt injection protection | v5.2 | 9.15 |

## Round 2 features promoted to implemented in v5.3-5.4

| # | Feature | Implemented in | Step |
|---|---|---|---|
| 19 | Multi-channel operator notifications (Slack/Discord/Email/SMS/Webhook) | v5.3 | 9.16 |
| 20 | Conversation analytics dashboard (weekly + monthly) | v5.3 | 9.17 |
| 22 | Document generation actions (quotes/proposals/contracts) | v5.3 | 9.18 |
| 24 | Smart Booking system + calendar setup wizard (supersedes Feature 23) | v5.3 | 9.19 |
| 25 | Conversation Workflow Builder (3-layer architecture in v5.4) | v5.3 / v5.4 rebuild | 9.20 |

**Notes:**
- Feature 23 (Smart Unavailability) merged into Feature 24 (Smart Booking) in v5.3
- Feature 25 (Conversation Workflow Builder) was significantly upgraded in v5.4 to a 3-layer architecture covering Layer 0 (routing check), Layer 1 (GHL side with auto-tag creation + Workflow AI prompt + verification checklist), Layer 2 (OpenClaw playbook)

---

# Part 2 — Remaining Features (ordered by priority)

Sixteen features remain unimplemented. Build order reflects revenue impact and strategic value, with the Conversational Sales AI cluster slotted FIRST since sales-driven outcomes are the primary value driver for Convert and Flow's client base.

---

# Sales AI Cluster (Features 26-31) — TOP PRIORITY

## ✅ Feature 26 — Conversational Sales AI Best Practices Module (shipped in v5.7)

**Status:** Implemented in Step 9.23 of the main playbook.

**What it does:** The sales BRAIN. Six conversation phases (Open / Discover / Present / Handle Objections / Close / Follow Up). Three discovery frameworks (BANT, MEDDIC, SPICED) — operator picks per product. Six objection patterns with response templates. Buyer signal recognition. Pricing reveal timing rules. Trial-close phrasing. Honesty floor (never fabricate, never deceive, never false urgency). Reads client-specific content from `knowledgebases/sales/`. AGENTS.md Step 1.8 activates this layer when sales context detected.

## ✅ Feature 27 — Product Knowledge Layer (subsumed by Feature 38 in v5.6)

**Status:** Implemented as the `products/` typed knowledge base inside Feature 38 (Step 9.22).

## ✅ Feature 28 — Discount Code Generation (GHL + Stripe) (shipped in v5.10)

**Status:** Implemented in Step 9.26.

## ✅ Feature 29 — Intelligent Follow-up (shipped in v5.9)

**Status:** Implemented in Step 9.25.

## ✅ Feature 30 — Stripe Integration (full) (shipped in v5.10)

**Status:** Implemented in Step 9.27.

## ✅ Feature 31 — Shopify Integration (shipped in v5.12)

**Status:** Implemented in Step 9.31.

---

# Cross-Cutting Conversational AI Features (Features 32-34)

## ✅ Feature 32 — Humanizer Skill Integration (shipped in v5.5)

**Status:** Implemented in Step 9.21. ALWAYS-ON via skill 19. Bans Tier 1 AI vocabulary (delve, tapestry, vibrant, crucial, robust, seamless, etc.). Bypassed for compliance messages and pure technical communications. Skill 38 does NOT ship its own humanizer; references skill 19.

## ✅ Feature 33 — Intelligent Playbook Routing (shipped in v5.13)

**Status:** Implemented in Step 9.33. Cosine similarity 0.3 advantage to switch. Max 3 switches per conversation.

## ✅ Feature 34 — Proactive Features Suite (shipped in v5.13)

**Status:** Implemented in Step 9.34. Seven sub-features on a single Saturday 11pm cron.

---

# System Health & Tuning Cluster (Features 35-37)

## ✅ Feature 35 — Weekly Conversation AI Tune-up (shipped in v5.12)

**Status:** Implemented in Step 9.32. Sunday 2am cron.

## ✅ Feature 36 — Monthly Comprehensive Playbook Review (shipped in v5.14)

**Status:** Implemented in Step 9.35. 1st-of-month 9am audit.

## ✅ Feature 37 — Model Version Freshness Checker (shipped in v5.14)

**Status:** Implemented in Step 9.36. Bundled into Saturday 11pm.

---

# Knowledge Architecture Cluster (Features 38-39)

## ✅ Feature 38 — Typed Knowledge Bases (shipped in v5.6)

**Status:** Implemented in Step 9.22. Four bases: business/, products/, sales/, conversations/.

## ✅ Feature 39 — Web Scraper for Knowledge Base Building (shipped in v5.8)

**Status:** Implemented in Step 9.24. Default extraction model: minimax/minimax-2.7. Cost-estimated; hard cap $5 double-confirm, $25 refused.

---

# Customer Experience Cluster (Features 40-42)

## ✅ Feature 40 — Customer Service & Support Playbooks (dual-mode) (shipped in v5.12)

**Status:** Implemented in Step 9.30.

## ✅ Feature 41 — Business-Logic Workflow Suggestions (shipped in v5.11)

**Status:** Implemented in Step 9.29.

## ✅ Feature 42 — Customer Journey Templates Library (shipped in v5.11)

**Status:** Implemented in Step 9.28. 8 business types; coach fully detailed; others stubbed.

---

# Remaining Round 2 Features (lower priority — DEFERRED, NOT in v5.14)

## 📋 Feature 14 — Voice/Phone Integration
## 📋 Feature 15 — Proactive Outreach Campaigns
## 📋 Feature 16 — A/B Testing of Reply Variants
## 📋 Feature 17 — Customer Segmentation Awareness
## 📋 Feature 18 — Webhook Chaining (downstream triggers)
## 📋 Feature 21 — Multi-Tenant Agent Isolation

These six are explicitly NOT implemented in v5.14 and NOT in skill 38. The skill's structure
(numbered scripts, protocols/ folder, references/) leaves room for them to be added later
without restructuring.

---

# Part 3 — What's NOT on the roadmap

- Customer satisfaction surveys (low signal; sentiment monitoring covers this)
- Chatbot-style FAQ matcher (Convert and Flow snippets cover this)
- In-conversation upselling without consent (bad UX)
- Auto-translation of agent's reply (superseded by Feature 8)

---

# Implementation status (skill 38)

**Shipped in skill 38 (v5.14):** All ✅ features above. Skill 38 packages 27 protocol files (humanizer-protocol.md intentionally NOT shipped — skill 19 owns it).

**Pending (NOT in skill 38):** F14, F15, F16, F17, F18, F21.

---

# Portability statement

All features are platform-neutral. The protocols are markdown instruction documents. If
a client migrates from OpenClaw to another conversational AI platform, these protocols
travel intact.
