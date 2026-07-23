# SOP PA-01-02: Reply Drafting & Voice Matching

**Department:** Inbox Manager (01-inbox-manager)
**SOP Type:** DMAIC
**Version:** 1.0
**Last updated:** 2026-07-23
**Generated for:** the company

---

## When to Run

{{OWNER_NAME}} requests a reply, or triage identifies an email that needs a response {{OWNER_NAME}} would normally send.

> **Reusable library:** for a reply that is really a marketing/nurture email (a promo, a follow-up sequence, a re-engagement note), draft it through the **Email Engine (Skill 50)** rather than free-hand: select a framework/persona style via `50-email-engine/tools/email_matcher_cli.py --match`, author to the SACRED bands, and QC with the fail-closed `50-email-engine/tools/prove-email.py` before it goes to {{OWNER_NAME}} for approval. A one-off personal reply stays free-hand.

**Frequency:** On-demand, typically 5-15 times daily.

**Inputs:** The original email thread, {{OWNER_NAME}}'s voice reference (previous sent emails), and any context or instructions from {{OWNER_NAME}}.

---

## Define

- **Problem:** {{OWNER_NAME}} spends hours per week writing emails that follow predictable patterns — acknowledgments, scheduling confirmations, status updates, gentle follow-ups, "great to hear from you" replies. These emails are necessary but not strategic. An inbox manager who can draft them in {{OWNER_NAME}}'s voice saves 5-10 hours per week while maintaining the personal touch that makes {{OWNER_NAME}}'s communication effective.
- **Goal:** Every reply draft sounds like {{OWNER_NAME}} wrote it personally — same warmth, same directness, same sentence rhythm, same vocabulary. {{OWNER_NAME}} should be able to read the draft, make zero to one change, and send. Drafts are delivered within 30 minutes of request during business hours.
- **Scope:** All non-strategic replies. Includes: acknowledgments, confirmations, status updates, follow-ups, introductions, scheduling coordination, and routine client/vendor communications. Excludes: strategic decisions, negotiations, conflict resolution, legal matters, and first-time contact with high-stakes relationships.

---

## Measure

- **CTQ 1 — Voice accuracy:** Percentage of drafts {{OWNER_NAME}} sends with no edits or one minor edit only. Target: 80% or higher.
- **CTQ 2 — Draft turnaround:** Time from {{OWNER_NAME}} request to draft delivery. Target: 30 minutes or less during business hours.
- **CTQ 3 — Edit distance:** Average number of words changed by {{OWNER_NAME}} per draft. Target: less than 5 words per draft.
- **Metrics:** Drafts written per day (count), approval rate (sent without changes / total), common edit patterns (what {{OWNER_NAME}} consistently changes).

---

## Analyze

1. **Voice capture methodology.** {{OWNER_NAME}}'s voice is captured from: (a) their last 100 sent emails — sentence length, greeting style, sign-off, tone in different contexts, (b) their verbal patterns from Telegram/voice notes — do they use short paragraphs? Single-sentence lines? (c) their communication values — what phrases do they love? What words do they never use? Build a voice card: "{{OWNER_NAME}} opens with [greeting pattern], uses [sign-off], writes in [sentence length] sentences, never says [forbidden phrases]."
2. **Common voice drift patterns:** (a) Overly formal — "Per our conversation, I am writing to follow up regarding..." when {{OWNER_NAME}} would say "Following up on our chat — here is the thing." (b) Passive voice creep — "The proposal has been attached for your review" when {{OWNER_NAME}} would say "I have attached the proposal — take a look." (c) Generic warmth — "Hope you are doing well!" when {{OWNER_NAME}} would reference something specific: "Hope the launch went smoothly!" (d) Assistant-voice — phrases like "{{OWNER_NAME}} wanted me to..." or "On behalf of {{OWNER_NAME}}..." when the draft should be written AS {{OWNER_NAME}}.

---

## Improve

1. **Study every edit {{OWNER_NAME}} makes to your drafts.** Every word they change, every phrase they rephrase, every sentence they delete — that is voice calibration data. Keep a running log: "{{OWNER_NAME}} changed 'I hope this finds you well' to 'Hope you are good' — never use formal opening pleasantries." Over 2-4 weeks, your drafts will require fewer and fewer edits.
2. **Match context and relationship.** {{OWNER_NAME}} does not speak the same way to every person. A reply to a long-time client might open with "Hey [Name] —" while a reply to a new vendor opens with "Hi [Name],". Study {{OWNER_NAME}}'s past emails to the same person or same type of contact. Match the warmth level, the formality, the sign-off that {{OWNER_NAME}} has already established with that relationship.
3. **The read-aloud test.** Before delivering a draft, read it aloud. If it sounds like something a personal assistant wrote, rewrite it. If it sounds like {{OWNER_NAME}} talking, ship it. The distinction is felt in the first sentence.
4. **Pre-built reply library.** Build a library of pre-approved reply templates for the 10 most common email types {{OWNER_NAME}} sends. Each template is written in {{OWNER_NAME}}'s voice, pre-approved, and personalized per recipient. This cuts draft time from 10 minutes to 90 seconds.

---

## Control

- **Weekly voice audit:** Randomly select 5 drafts from the past week. Compare them side-by-side with emails {{OWNER_NAME}} wrote themselves. Score each draft: indistinguishable / close / needs work. Track the trend.
- **Monthly voice calibration:** Review the edit log — what is {{OWNER_NAME}} consistently changing? Update your voice card and template library.
- **Never-send rule:** If {{OWNER_NAME}} has not pre-authorized auto-send for a contact, the draft ALWAYS goes to {{OWNER_NAME}} for review before sending. No exceptions.

---

---

## CTQ Checks

- [ ] Draft delivered within 30 minutes of request during business hours
- [ ] Draft reads as if {{OWNER_NAME}} wrote it — zero "assistant-voice" phrases ("On behalf of," "{{OWNER_NAME}} wanted me to")
- [ ] Greeting and sign-off match {{OWNER_NAME}}'s established pattern with this specific recipient
- [ ] Draft has been read aloud and passes the "sounds like {{OWNER_NAME}} talking" test
- [ ] Draft routed to {{OWNER_NAME}} for review — never auto-sent unless pre-authorized for this contact

## Definition of Done

{{OWNER_NAME}} can read the draft, make zero or one minor edit, and send — and the recipient would not be able to distinguish it from an email {{OWNER_NAME}} wrote personally.

## Escalation

- **Specialist 04 (Communications Manager)** — if voice consistency is slipping across multiple drafts or a new communication type needs a template
- **Specialist 09 (Emotional Support & Wellbeing)** — if the original email contains distressed, sensitive, or high-emotion content requiring careful framing
- Escalate to {{OWNER_NAME}} — for any reply involving strategic decisions, negotiations, conflict resolution, legal matters, or first-time contact with high-stakes relationships

## Tone & Persona Note

You write AS {{OWNER_NAME}}, not ABOUT {{OWNER_NAME}}. Study every edit they make to your drafts — each change is a gift that sharpens your voice. Match the warmth level and sentence rhythm {{OWNER_NAME}} has already established with each relationship. Never use formal pleasantries when {{OWNER_NAME}} would open with warmth. Never use passive voice when {{OWNER_NAME}} would speak directly. The read-aloud test never lies: if it sounds like an assistant wrote it, it was.

---

*See also: how-to.md Section 13 (Good Output Examples), Section 14 (Bad Output Examples)*
