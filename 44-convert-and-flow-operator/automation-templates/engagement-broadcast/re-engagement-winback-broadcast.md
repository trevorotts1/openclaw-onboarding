# Re-Engagement / Win-Back Broadcast — Cold Subscriber Reactivation

**id:** `re-engagement-winback-broadcast` · **category:** engagement-broadcast
**aliases:** win-back · re-engagement · reactivation · sunset campaign · lapsed-subscriber broadcast · list cleaning · "are we breaking up" email
**source:** DotCom Secrets **Secret #6** (Us vs Them, Secret Telling, polarity) · **Secret #8** (daily mailing keeps the relationship alive) · Copywriting Secrets (Takeaway/FOMO close; *"9 of 10 buy out of dissatisfaction"*)

> Keeps the engaged broadcast list **healthy**: revives subscribers who stopped opening, and **sunsets** the truly dead ones to protect deliverability of the daily Seinfeld sends.

## TRIGGER
Subscriber on the broadcast segment goes **cold** — no open/click in **30 days** (escalates at 60). GHL: when `last_email_open` > 30 days → `Tag Added: cold-30d`.

## CHANNELS
Email (primary) · one SMS nudge on the final takeaway · suppression (final state).

## SEQUENCE — short win-back drip
| # | Beat | Angle / body | Delay | Branch |
|---|---|---|---|---|
| 1 | **"Are we breaking up?"** | Curiosity + **Us vs Them** line-in-the-sand: *"Still a do-er… or a talker?"* Secret-telling hook. One CTA = click to stay. | Day 0 | open/click → **re-engaged** exit |
| 2 | **Best-of value + biggest win** | Your single most entertaining story + strongest offer; future-pace the result they joined for. | +3 days | open/click → re-engaged exit |
| 3 | **Takeaway / sunset** | Honest takeaway: *"I'll take you off unless you click below."* One CTA. **+ SMS.** | +3 days | no response → **sunset** |

## COPY PERSONA + SCRIPT
Brunson **polarity / Us vs Them** ("talkers vs do-ers") + **Secret Telling** storylines, with Edwards **Takeaway/FOMO** close and the *"people buy out of dissatisfaction"* frame (remind them their situation hasn't changed).

## GHL BUILD (Skill 44)
A real **GHL Workflow** (sequenced, with a Goal exit + sunset suppression):
- **Trigger:** `Tag Added: cold-30d` (set by a scheduled workflow checking `last_email_open`, or a GHL engagement filter).
- **Actions:** Send Email 1 → Wait 3d → **Goal: Opened/Clicked → re-engaged** (remove `cold-30d`, keep `seinfeld-broadcast`, exit) → Send Email 2 → Wait 3d → Goal check → Send Email 3 **+ SMS** → Wait 2d → if still silent: **Add Tag `sunset` + Remove Tag `seinfeld-broadcast`** (drops them from the daily Smart List) + remove from broadcast.
- **Goal:** `Email Opened` / `Link Clicked` re-routes to re-engaged and clears the cold tag at any step.
- Set action **order + parentKey before first save**.

## KPIs
Reactivation rate · deliverability lift after sunset · win-back revenue · active-vs-sunset list ratio.

## FAITHFULNESS
Copy **angles** (Us vs Them, Secret Telling, takeaway, "buy out of dissatisfaction") are from the books. The **trigger (no-open-30d)** and **sunset suppression** are standard deliverability practice **DERIVED** from the books' "email daily or lose money" + polarity/takeaway principles — flagged as derived, **not** a verbatim Brunson sequence.
