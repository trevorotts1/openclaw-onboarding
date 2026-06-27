# 3 Closes Broadcast Mini-Campaign — Emotion / Logic / Fear Ascension Push

**id:** `value-broadcast-3-closes-campaign` · **category:** engagement-broadcast
**aliases:** 3 closes · emotion-logic-fear · ascension broadcast · offer-push mini-campaign · value-ladder broadcast promo
**source:** Funnel Hacker's Cookbook **#24 Follow-Up Funnel** (3 Closes: *Emotion → Logic → Fear*) · DotCom Secrets Star/Story/Solution closes · Copywriting Secrets (honest scarcity, Ten Reasons)

> A **promo mini-campaign** dropped on top of the daily Seinfeld cadence to push the engaged list toward one offer (new product, open cart, event, ascension). Uses the **3 Closes** the Follow-Up Funnel runs leads through: **Emotion → Logic → Fear.**

## TRIGGER
A scheduled **promo window** to the `seinfeld-broadcast` segment. GHL: `Tag Added: promo-{offer}` (or scheduled start). Runs ~5–7 days, layered over the daily broadcast.

## CHANNELS
Email (primary) · SMS (on the Fear/urgency close) · retargeting (optional).

## SEQUENCE — 3 (+1) emails
| # | Close | Body framework | Delay |
|---|---|---|---|
| 1 | **EMOTION** | Seinfeld story → emotional offer. Future pacing + the **If-All anchor**: *"If all this did was ___, would it be worth it?"* — both toward-pleasure & away-from-pain. | Day 0 |
| 2 | **LOGIC** | Value stack · **fake-price → real-price** ("dollars for dimes") · crazy-named **guarantee** (reverse risk) · social proof / case studies · ease + speed + "so" benefits. | +2 days |
| 3 | **FEAR** | **Real** scarcity (cart closes / seats left / price rises / offer pulled) + **takeaway selling** (*"it doesn't matter to us if you join or not…"*). Honor the deadline — fake urgency backfires. **+ SMS.** | +2 days |
| 4 | *(optional)* Post-deadline | Cart-closed note + down-sell / wait-list. | +1 day |

**Branch:** purchased at any step → exit + tag `buyer` (stop sending promo).

## COPY PERSONA + SCRIPT
Brunson Star/Story/Solution closes mapped to the 3 Closes — Emotional/If-All (#27), Guarantee/Logic (#29), Scarcity (#30) + Takeaway (#34) — with Edwards' Ten Reasons, dollars-for-dimes framing, and the **honest-scarcity non-negotiable**.

## GHL BUILD (Skill 44)
A **real GHL Workflow** (this one IS sequenced, unlike the daily broadcast):
- **Trigger:** `Tag Added: promo-{offer}` on the broadcast Smart List.
- **Actions:** Send Email (Emotion) → Wait 2d → **If/Else purchased?** (order tag / opportunity stage) → Send Email (Logic) → Wait 2d → **If/Else purchased?** → Send Email (Fear) **+ Send SMS** → **Wait-until** deadline date → Remove Tag `promo-{offer}`.
- **Goal event:** *Purchase made* exits the workflow immediately (configure Goal/If-Else on opportunity stage or order tag).
- Set action **order + parentKey before first save** (Skill 44 reliability). Suppress from competing promos while in-campaign.

## KPIs
Campaign conversion · revenue per recipient · open/click **by close type** · unsubscribe-spike guard (over-promotion).

## FAITHFULNESS
The **3 Closes (Emotion → Logic → Fear)** is stated in Funnel Hacker's Cookbook #24. The close mechanics (If-All anchor, fake/real price, crazy-named guarantee, scarcity, takeaway) are the Star/Story/Solution closes from DotCom Secrets; honest-scarcity is an Edwards rule. The 3-email cadence + GHL workflow are the Skill-44 operationalization; exact day-gaps are a sensible default, **not** a fixed book number.
