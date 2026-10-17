# Council Scoring Reference

How seat scores become a recommendation, per the build directive's
scoring contract. Worked fixtures below are the directive's own golden
examples; they are arithmetic references, not council results.

## Scale and coverage

- Each seat scores each option on a 0 to 10 scale, or abstains with a
  stated reason. A missing score is null. Null is never scored as zero.
- Weighted coverage is the share of total seat weight that actually
  scored. A GO-style overall label requires at least 80 percent
  weighted coverage AND no unresolved critical-domain abstention.
  Anything less is presented with conditions, never rounded up.
- A timeout is not an abstention, and an abstention is not a zero.
- Near tie: when the top two options are within 0.25, the result is
  presented as a near tie with the deciding conditions named.

## Golden fixtures (directive arithmetic)

Seat weights in roster order: [2, 3, 2, 3, 3, 2, 3, 2, 2], total 22.

- **Option A.** Scores [8, 7, 6, 5, 4, 9, 3, 10, 2]. Weighted sum 132.
  Score 132 / 22 = 6.0.
- **Option B.** Scores [6, 8, 7, 9, 10, 5, 9, 4, 8]. Weighted sum 168.
  Display score 168 / 22 = 7.6 (7.636 shown rounded). Spread between
  highest and lowest seat score: 3.
- **Option C.** Scores [5, 6, null, 8, 7, 4, 6, 9, 3]. Weighted sum 145
  over the scoring seats only; display score 6.6. Because one seat
  abstained, coverage is below 100 percent, and if that abstention is
  in a critical domain for this decision, no GO-style label may be
  issued for Option C regardless of the number.

## Presentation rules

- Show the full scorecard in the report (see report-template.md),
  including abstentions and their reasons.
- Show each option's score, its coverage, and the strongest objection
  beside it. Never show a bare number as the verdict.
- When coverage or a critical abstention blocks a GO-style label, say
  exactly that, in those terms, on the verdict page.
