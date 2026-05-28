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

- Skill 17, 18, 31, 29, 19 SOUL/IDENTITY/AGENTS files — left untouched per Christy.
- Operator's existing TOOLS.md, SOUL.md, IDENTITY.md, USER.md, HEARTBEAT.md — only AGENTS.md and MEMORY.md are appended to, behind clear `<!-- BEGIN/END skill-38 -->` markers, with backups before any edit.
