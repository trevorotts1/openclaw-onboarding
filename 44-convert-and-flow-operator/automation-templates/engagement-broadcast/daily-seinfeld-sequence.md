# Daily Seinfeld Sequence — Ongoing Entertainment Broadcast Engine

**id:** `daily-seinfeld-sequence` · **category:** engagement-broadcast
**aliases:** Seinfeld emails · Daily Seinfeld Sequence · email about nothing · ongoing engagement emails · 90/10 entertainment emails · daily value broadcast · broadcast list emails
**source:** DotCom Secrets **Secret #8 (Daily Seinfeld Sequence)** + **Secret #6 (Attractive Character)** · Funnel Hacker's Cookbook **#24 Follow-Up Funnel** · Copywriting Secrets (Stealth/Columbo close)

> This is the flagship of the category. After a new subscriber bonds with the Attractive Character through the 5-email **Soap Opera Sequence** (a welcome autoresponder — handled by a sibling category), they graduate here: an **ongoing, daily, one-off broadcast** that is 90% entertainment / 10% content and ties every story back to an offer.

---

## TRIGGER
- **Primary:** Subscriber **completed the Soap Opera Sequence** → tag `soap-opera-complete` applied → contact is **graduated into the broadcast segment**. Book: *"After someone has completed your SOAP series, they should be moved to a broadcast list where they will only get the Seinfeld email that you send out that day."*
- **Secondary:** Any new buyer or already-engaged lead added directly to the `seinfeld-broadcast` segment.

## CHANNELS
Email (primary, **daily**) · Blog (repurpose the email body verbatim — book: *"I always tell them simply to copy and paste their daily Seinfeld email"*) · SMS teaser (optional).

## CADENCE & RATIO
- **One broadcast per day, perpetual.** Each send is a **one-off** tied to what's happening in the AC's life *that day* — NOT a pre-lined sequence. Book: *"if I don't email my list every day, I lose money every day."*
- **90% entertainment / 10% content.** Book: switching from 100% content to 90% entertainment made *"opens, clicks, and sales all skyrocket."*

## SEQUENCE — the Hook → Story → Offer of each daily email
| Beat | Purpose | Subject / Body |
|---|---|---|
| **1. HOOK** | Earn the open (8/10 only read the subject) | Curiosity / open loop. Real examples: `[True Story] He FLUSHED $20 million down the toilet today` · `Jiu Jitsu is like wrestling for old, fat guys (and other marketing stuff)` |
| **2. STORY (about nothing)** | Bond + entertain daily | A random entertaining episode. Prompt menu (book): embarrassing moment · surviving the holidays · vacation planning · a purchase you regret · a purchase you adore · what made you rage yesterday that you laugh about today · crazy kid/dog antics · a funny past lesson. Show **flaws + polarity**. One–two sentences per line, white space, no long paragraphs. |
| **3. OFFER (tie-back)** | Make money | **Stealth/Columbo pivot** — *"So, why do I tell you this?…"* — bridge the lesson to the offer with *"which means…"* + ≥1 Reason People Buy. **Single CTA.** P.S. for personality / honest reason to act. Book: *"EVERY EMAIL and each story must be tied back into some type of offer."* |

## COPY PERSONA + SCRIPT
- **Brunson Attractive Character / Seinfeld voice** — pick an identity (Leader / Adventurer / Reporter / **Reluctant Hero**); 90/10 entertainment.
- **Jim Edwards (Copywriting Secrets)** supplies the Stealth/Columbo close, curiosity subject families, the you/your pronoun audit, and "which means…" + the Ten Reasons People Buy.
- **6 storylines** to draw from: Loss & Redemption · Us vs Them · Before & After · Amazing Discovery · Secret Telling · Third-Person Testimonial.

## GHL BUILD (Skill 44)
**CRITICAL, faithful nuance:** Seinfeld emails are **BROADCASTS, not autoresponders** — *"Seinfeld emails are typically not lined up in a sequence that everyone has to go through."* So in GoHighLevel they are **daily one-off Email Campaigns sent to a Smart List**, NOT a Workflow drip. The only thing Skill 44 *automates* is segment membership.

1. **Graduation Workflow** (the automation that IS built)
   - Trigger: `Tag Added: soap-opera-complete` (or Workflow-finished from the Soap Opera workflow).
   - Actions (set order + parentKey before first save): **Add Tag** `seinfeld-broadcast` → **Add Tag** `engaged` → **Remove Tag** `soap-opera-active` → **Update field** `broadcast_start_date = today`.
   - No email steps. Membership only.
2. **Broadcast Segment** — Smart List: `Tag = seinfeld-broadcast AND unsubscribed = false AND NOT tag sunset`.
3. **Daily Send** — Marketing ▸ Emails ▸ **Email Campaign (Broadcast)** to the Smart List, composed that day (or batch-scheduled). Uses the reusable **`seinfeld-broadcast-email`** shell.
4. **Blog repurpose** — optional webhook/Zap pushing the same body to the blog.
5. **Tracking** — GHL logs Opened/Clicked → write `last_email_open` for the win-back template.

## KPIs
Daily open rate · click rate · revenue per send · unsubscribe rate · CTA-attributed sales.

## FAITHFULNESS
Cadence, 90/10 ratio, Hook-Story-Offer, broadcast≠autoresponder, "move to a broadcast list," blog repurpose, formatting rules, story-prompt menu, and both example subject lines are **verbatim concepts from DotCom Secrets Secret #8**. AC identities/flaws/polarity/storylines are from Secret #6. GHL mechanics are the standard Skill-44 mapping.
