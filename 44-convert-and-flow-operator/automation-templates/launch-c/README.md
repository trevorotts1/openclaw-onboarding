# Launch C — Onboarding + Review/Referral

Lane AC-1 (WF-AUTO-C) files for spec §3.3 family **Onboarding + review/referral**.

| File | Workflow | Trigger | Ends at |
|---|---|---|---|
| `onboarding-first-hour-day-week.json` / `.md` | LC — Onboarding: First Hour, Day 1, Week 1 | Tag Added `purchase-onboard-ready` | `review-eligible` or `onboard-help-needed` |
| `review-referral-ask.json` / `.md` | LC — Review Ask → Referral Ask | Tag Added `review-eligible` | `referral-asked` or `advocacy-closed-no-ask` |

**Template start:** `membership-stick-retention` (Phase A onboarding + advocacy cut; membership-only mechanics excluded).
**Build rail:** Skill 44 engine — per `launch-ghl-probe/GHL-CAPABILITY-NOTE.md`. Purchase trigger is not auto-built; the lane uses a Tag Added trigger set by the post-sale family (patch-trigger only as fallback). `review_request` is a verified action. **Draft only.**

**Contract mapping:** `family: onboarding_review`, `unit_id: auto_onboarding_review`, `template: membership-stick-retention`, `build_rail: skill44_engine`, `draft_only: true`, `waits_for: [auto_post_sale, email_welcome_access, page_thank_you]`.

**Integrator-only lines these files need (not edited by this lane):**
- `44-convert-and-flow-operator/automation-templates/README.md` — a launch-lane note pointing at `launch-a/`, `launch-b/`, `launch-c/` (the 28-template count stays 28; launch lanes are separate).
- `44-convert-and-flow-operator/SKILL.md`, `CHANGELOG.md`, `skill-version.txt` — release bookkeeping after integration.
- `_matcher/catalog-index.json` and `_links/funnel-to-automation.json` — unchanged unless the integrator chooses to index launch lanes; these files are not launch templates in the 28-template library.

**Guards:** no sends, no live switch, no client account touched; purchase stops promotional messaging; SMS opt-in with STOP; review ask unfiltered and unincentivised; referral asks use real terms or a named introduction.
