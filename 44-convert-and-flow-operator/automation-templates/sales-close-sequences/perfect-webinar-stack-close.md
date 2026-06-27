# Perfect Webinar STACK Close (+ Post-Webinar Follow-Up)

**id:** `perfect-webinar-stack-close` · **category:** sales-close-sequences
**Aliases:** the stack, stack slide, stack and close, perfect webinar close, trial closes, VSL stack close
**Source:** Expert Secrets (Brunson — Perfect Webinar, The Stack, Trial Closes, The One Thing) · Marketing Secrets Blackbook (Stack Don't Switch, Power of the Bonus, Urgency & Scarcity) · Copywriting Secrets (Edwards — offer block, guarantee, dollars-for-dimes)

> **The Stack** is Brunson's offer-reveal mechanism: reveal the offer one element at a time and **restate the entire cumulative value stack each time**, so the value pile grows in the audience's mind. When the price finally drops, it feels tiny — "sell dollars for dimes." It is the climax of the Perfect Webinar: *intro / big domino → 3 secrets (break false beliefs) → THE STACK → close.*

---

## TRIGGER
Registered → Attended (live or replay) → Watched to the offer/Stack timestamp (or VSL watched to price reveal).
**Exit:** purchase → buyer onboarding; cart/replay window expires → drop to nurture.

## CHANNELS
Webinar/VSL (the Stack is delivered live) · email (registration → show-up → replay → close) · SMS (reminders + cart-close) · replay page with countdown timer.

---

## THE STACK MECHANICS (the deliverable script)

**Stack-slide pattern:**
1. **Element 1 — Core offer:** "[Core] (value $X)"
2. **+ Element 2:** "(value $Y)" → restate: *"So far you get Core + Asset 2 = $X+$Y"*
3. **+ Element 3:** "(value $Z)" → restate the full cumulative total again
4. Keep stacking bonuses / tools / community / support — **restate the cumulative total every time**
5. **Final total** revealed (e.g. "Total real value: $N")
6. **Price reveal** far below total: *"but you won't pay $N… not even half… today it's just $P"*
7. **Guarantee** (risk reversal) → **urgency / fast-action bonus** that expires → **CTA**

**Trial closes (throughout, not just the end):** "Does that make sense?" · "Could you see yourself using this?" · **"If all this did was [one result], would it be worth $P?"** — a yes-ladder that makes the final ask a formality.

**The One Thing:** tie the whole offer back to the ONE big-domino belief — if they believe this one thing, they must buy. The Stack is the vehicle to it.

---

## THE SEQUENCE

| # | Stage | Channel | When | Beat |
|---|-------|---------|------|------|
| 1 | PRE — show-up | email + SMS | −3d → live | Indoctrination: confirm reg, build anticipation, tease the ONE secret. Reminders 24h/1h/live-now. Maximize show-up. |
| 2 | LIVE — the close | webinar/VSL | Day 0 | 3 secrets (break vehicle/internal/external false beliefs) → **THE STACK** → price reveal → guarantee → fast-action bonus + urgency → CTA. **Trial-close throughout.** |
| 3 | POST — same day | email + SMS | Day 0 | "Replay + offer is live" → replay page (countdown) + order page. Restate the Stack in writing. Catch no-shows. |
| 4 | POST — Logic recap | email | Day 1 | Written Stack recap: each element + value + "which means…", price anchor, guarantee, objections-as-bonuses. (Logic close.) |
| 5 | POST — Fear/urgency | email + SMS | Day 2 (T-24h) | Fast-action bonus expiring / cart closing in 24h; restate scarcity levers. |
| 6 | POST — close | email + SMS | Day 2 (T-3h, T-1h) | Final hours: replay comes down / bonus gone / price rises. Last-call. Conversion spike. |
| 7 | POST — branch | automation | Day 3 | Cart closed. Buyers → onboarding + ascend (Stack Don't Switch). Non-buyers → Seinfeld nurture / auto-webinar re-invite. |

---

## COPY PERSONA & SCRIPT
- **Primary:** Brunson — Perfect Webinar / **The Stack** / **Trial Closes** / The One Thing.
- **Supporting:** Edwards — offer block (what/how/when/how much), guarantee, dollars-for-dimes, single CTA, P.S. · Brunson **Power of the Bonus** (turn each objection into a bonus) + **Stack Don't Switch**.

---

## GHL BUILD (Skill 44 → GoHighLevel)
**Workflow:** `Perfect Webinar — Show-Up + Stack Close Follow-Up`

1. **Trigger:** `Form Submitted = webinar registration` → tag `webinar-reg-[event]`.
2. **PRE:** confirmation → reminder emails (24h, 1h) + SMS (1h, "we're live").
3. **Attendance tagging:** `attended-live` / `watched-to-stack` (watch% via webinar webhook) / `no-show`.
4. **POST:** same-day replay+offer (email/SMS) → Day1 Stack-recap (logic) → Day2 T-24h urgency → Day2 T-3h/T-1h close — **all gated to a fixed `cart-close-datetime`.**
5. **Replay page** = GHL funnel page with a **countdown timer wired to the same `cart-close-datetime`**; order page carries the written Stack + order bump + 1–2 OTOs.

**If/Else & Goals:**
- `attended-live` → shorter/hotter follow-up; `no-show` → "you missed it, replay 24h only."
- `watched-to-stack` (`saw-offer`) → straight to urgency cadence; `left-before-stack` → re-pitch offer in recap.
- **Purchase Goal** (`buyer-[offer]`) anywhere → exit, buyer onboarding + ascend, STOP close emails.
- Checkout started, not completed → fire `abandoned-cart-recovery`.

**The countdown timer (replay + order page) must read from the same `cart-close-datetime` as the Fear-phase waits** — that is what makes urgency real. When the timer hits zero, replay comes down and bonus/price genuinely change.

## INTEGRITY GUARDRAILS
Every Stack value real/defensible · fast-action bonus & cart-close genuinely honored · trial closes are honest yes-ladders, never claim an unprovable result.

## KPIs
Registration→show-up · show-up→offer-view (watch-to-stack) · offer-view→purchase · replay/cart-close revenue spike · order-bump + OTO take rate · revenue per registrant.
