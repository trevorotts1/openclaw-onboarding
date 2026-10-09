# The one money question (FU-ONE-SPEND-QUESTION)

Status: normative for both distributions (Skill 75 / 999 twin). This file is
byte-identical in both. It is the money rule that `choice-card-spec.md`
section 2 and `SKILL.md` intake text defer to; where either of those still
says the story questions include "spending authority" or "approve the price",
this file governs.

The client is asked about money exactly once: question 5, `BUDGET`, where the
real price is on screen. The story questions (`intake.py`) never mention spend,
budget or cost, and the freed slot goes to the next needed story question. It is
a video, not an ad. Wording:

    What's the most you want to spend on this video?
    1. $<price> - the estimated price for your video, including a 20% allowance for redoing shots (recommended)
    2. A different maximum - reply with a dollar amount, like $25

When the brief or the weekly planner (`smp/initial_questions`) already gave a
maximum, it is option 1 and the price is option 2; the client still confirms by
replying:

    1. Your max: $<limit> - from your brief (recommended)
    2. $<price> - the estimated price for your video, including a 20% allowance for redoing shots
    3. A different maximum - reply with a dollar amount, like $25

When `--limit` overrides (the number did not come from the brief), option 1 reads
`Your max: $<limit>` with no "from your brief". `<price>` is the card's total
with the 20% allowance (`spending_limit_usd`); pass it as
`factory.py card --step --price <usd>`. The maximum is picked up on its own from
`--brief`, `--brief-file` or `--summary-file` (`budget_minor` or the summary's
`generation_ceiling`, US dollars only); `--limit <usd>` overrides it. With no
price and no maximum, no option is marked recommended, the closing line does not
offer "all recommended", and the question reads: "What's the most you want to
spend on this video? Reply with a dollar amount, like $25." Spending authority
is never defaulted: no reply, or a reply that is not an option or a dollar
amount, records nothing and nothing is spent. The recap line is
`Budget: up to $<amount>`.

Story questions (`scripts/core/intake_preflight/intake.py`): offer,
audience and action, then only when needed the exact website address or the
placement and format. Never money. The three-question cap applies to these.
Test: `scripts/core/choice_card/intake_card/test_one_spend_question.py`.
