# The one money question (FU-ONE-SPEND-QUESTION)

Status: normative for both distributions (Skill 75 / 999 twin). This file is
byte-identical in both. It is the money rule that `choice-card-spec.md`
section 2 and `SKILL.md` intake text defer to; where either of those still
says the story questions include "spending authority" or "approve the price",
this file governs.

The client is asked about money exactly once: question 5, `SPEND LIMIT`, where
the real price is on screen. The story questions (`intake.py`) never mention
spend, budget or cost, and the freed slot goes to the next needed story
question. Wording:

    How much are you OK spending on this ad?
    1. $<card price> - the price shown above (includes a 20% allowance for redoing shots)
    2. A different limit - reply with a dollar amount, like $25

When the brief or the weekly planner (`smp/initial_questions`) already gave a
limit, it is option 1 ("Your limit: $X - from your brief") and the card price
is option 2; the client still confirms by replying. `<card price>` is the
card's total with the 20% allowance (`spending_limit_usd`); pass it as
`factory.py card --step --price <usd> [--limit <usd>]`. Spending authority is
never defaulted: no reply, or a reply that is not an option or a dollar amount,
records nothing and nothing is spent. The recap repeats the chosen limit.

Story questions (`scripts/core/intake_preflight/intake.py`): offer,
audience and action, then only when needed the exact website address or the
placement and format. Never money. The three-question cap applies to these.
Test: `scripts/core/choice_card/intake_card/test_one_spend_question.py`.
