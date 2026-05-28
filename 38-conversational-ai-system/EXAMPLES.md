# Skill 38 — Conversational AI System: Examples

Five example operator interactions that show the skill in action.

## Example 1 — Customer asks pricing in first message

**Channel:** SMS via Convert and Flow inbound webhook
**Inbound:** "Hey how much is your 3-month coaching package?"

**Agent's internal protocol stack (in order):**
1. `pii-scrubbing-protocol.md` — input scanned (no PII detected).
2. `prompt-injection-protection-protocol.md` — input cleared.
3. `confidence-threshold-protocol.md` — high confidence (direct product question).
4. AGENTS.md Step 1.7 — query Product Knowledge base for 3-month coaching package.
5. AGENTS.md Step 1.8 — Sales Brain activated (`sales-best-practices-protocol.md`).
6. Pricing reveal rule applies: customer explicitly asked price in first message → answer directly BUT qualify their need in the same response.
7. AGENTS.md Step 1.75 — `intelligent-routing-protocol.md` checks: this matches `pricing-inquiry` Conversation Workflow.
8. AGENTS.md Step 2 — draft reply.
9. AGENTS.md Step 2.8 — `humanizer` skill 19 applied (always-on).
10. Send.

**Outbound:** "Three-month coaching is $1,997. Quick question so I can make sure it's the right fit — what's the main thing you're trying to work on right now?"

## Example 2 — Customer goes quiet after pricing reveal

**Channel:** Email
**Context:** 48 hours since pricing was quoted; no reply.

**Cron fires:** `intelligent-followup-protocol.md` detects stall.

- T1 (now, 24 hours post-stall): soft check-in via email — "just making sure you got my last message, any questions I can answer?"
- T2 (48 hours): value-add touch (relevant case study).
- T3 (Day 7): direct ask — "is there something specific holding you back?"
- T4 (Day 14): final touch with optional discount per `discount-code-protocol.md` policy. If product allows up to 15% off, agent generates a one-time GHL coupon (per `references/ghl-coupons-api.md`).
- T5 (Day 30): release. Tag contact as `cold-lead` and stop following up.

## Example 3 — Customer says "this isn't working" mid-conversation

**Channel:** Live Chat
**Context:** Was a service-mode conversation ("how do I update my address"); customer pivoted.

`customer-service-support-protocol.md` detects support-mode signal ("not working").

- Mode switch logged (service → support) for retention analytics.
- Tone shifts: acknowledges frustration FIRST, then troubleshooting.
- Sentiment monitor (per `sentiment-monitoring-protocol.md`) triggers heightened watching.
- Honesty floor enforced: agent does NOT promise a refund without operator approval; it offers a callback OR escalation.

## Example 4 — Saturday 11pm proactive scan finds a workflow gap

**Cron fires:** `proactive-suggestions-protocol.md`.

Pattern detected: 7 customers this week asked about "1-on-1 coaching pricing" but the operator has no `1on1-pricing-inquiry` workflow.

Sunday morning report to operator: "I've seen 7 customers ask about 1-on-1 coaching pricing this week with no matching workflow. Want me to draft one based on your 3-month workflow's structure? Reply YES / NO / DEFER."

Operator replies YES. Agent uses Conversation Workflow Builder (skill 29's 3-layer architecture) to scaffold the new workflow, then escalates final review back to the operator before activating it.

## Example 5 — Sunday 2am model freshness check finds a newer model

**Cron fires:** `model-version-freshness-protocol.md`.

DeepSeek V4 Pro thinking:max — current installed. Check finds DeepSeek V4.1 Pro available.

Categorization: MINOR (incremental improvement). Suggestion sent to operator via the weekly tune-up report.

Operator replies YES to update. Agent:
1. Backs up current `openclaw.json`.
2. Updates primary model reference.
3. Sends a synthetic test message through the new model.
4. If test passes → notifies "Updated successfully."
5. If test fails → ROLLS BACK and notifies with the failure reason. Never silently switches.

Per the v5.14 rule: never auto-update primary models. ALWAYS ask. ALWAYS test. ALWAYS rollback on failure.
