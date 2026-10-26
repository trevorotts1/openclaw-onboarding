# Council Mode Selection Reference

The council runs in one of three sizes: light, medium, or heavy. A size
sets how many rounds the council sits, how many provider calls it issues
at once, and the session's provider-request cap. A size never changes who
sits: all nine advisors deliberate in every council size, and consensus is
still seven of nine.

The selection mechanism below is `selectMode` in
`runtime/src/flow/mode-select.ts`. What each size then does is
`MODE_ROUND_POLICY` in `runtime/src/contracts/modes.ts`; the selector does
not reinterpret it.

## The selector

One function chooses the size:

```
selectMode(question, explicitMode?) -> { mode, source, reason }
```

- `mode` is `light`, `medium`, or `heavy`.
- `source` is `client` when the client named a size, `auto` when the
  system classified the question.
- `reason` is a fixed-format line. For a client choice it is
  `client selected <mode>`. For an automatic choice it is
  `complexity score <n> (stakes <a>, breadth <b>, ambiguity <c>) selected
  <mode>`.

`selectMode` is text arithmetic only: no randomness, no clock, no model
call, no network, and no client context. The same question always returns
the same size. In the wired convene flow
(`runtime/src/flow/convene-flow.ts`) the permitted-context brief is
assembled first, then the size is resolved from the decision text alone,
then deliberation runs. The resolved `{ mode, source, reason }` travels
both as `modeSelection` on the convene result and as `mode_selection` on
the session record, so the client can always see why the council sat as
long as it did.

## The client's explicit mode always wins

An explicit instruction to run a particular size overrides the automatic
choice, always and without exception. Two layers enforce it:

- `selectMode` itself trims and lowercases `explicitMode`. When the result
  is `light`, `medium`, or `heavy` it returns that size with
  `source: 'client'` and scores nothing. Any other value is treated as
  absent and the question is classified automatically. This is the
  unit-tested behaviour of the function in isolation.
- The convene flow validates before calling it: `input.mode` must be
  exactly `light`, `medium`, or `heavy`. Any other explicit value is
  refused by name with `INVALID_MODE: "<value>" is not a council size;
  expected one of light, medium, heavy.` It is never silently replaced by
  an automatic pick, because that would override the client's choice.

The convene flow's check is an exact match on the three lowercase names.
The selector's own trim and lowercase do not run for values the flow has
already refused.

### The seven session modes

The stored session `mode` enum has seven values: `full`, `selected`,
`quick`, `consult`, `light`, `medium`, `heavy` (`SESSION_MODES` in
`runtime/src/contracts/enums.ts`), and the session schema accepts all
seven (`sessionSpecSchema` in `runtime/src/contracts/schemas.ts`). Seat
counts are fixed by that schema:

| Session `mode` | Seats required |
|---|---|
| `full` | all nine |
| `consult` | exactly one |
| `selected` | two to eight |
| `light`, `medium`, `heavy` | all nine |

The four older modes keep their own behaviour and their own protocol
(`references/protocol.md`), and neither `MODE_ROUND_POLICY` nor the
selector reinterprets them. The automatic selector only ever returns
`light`, `medium`, or `heavy`, and it performs no phrase translation:
`full`, `selected`, `quick`, and `consult` are not sizes it accepts.

## How the automatic choice is made

The choice is deterministic. `scoreComplexity` lowercases the question,
adds three buckets, and reads the total off two thresholds. Scores are
small integers; the maximum possible total is 37.

| Bucket | What scores | Points | Cap |
|---|---|---|---|
| stakes | each distinct high-impact term present | +4 | 16 |
| breadth | each distinct domain group present | +2 | 8 |
| breadth | each `?`, `!`, `;`, or `.` followed by a space or the end of the question | +1 | 4 |
| ambiguity | each distinct hedge or choice marker present | +1 | 3 |
| ambiguity | each distinct list connector present | +1 | 2 |
| ambiguity | question longer than 60 words, or longer than 150 words | +2, or +4 when over 150 (the +4 replaces the +2) | 4 |

The buckets add independently, so the same word can score in two of them
(for example `contract` is both a stake term and a contract/legal domain
word).

Matching rules that keep the arithmetic honest:

- Matching is whole-word and case-insensitive, after the question is
  lowercased. Multi-word entries are phrases (`lay off`, `should we`,
  `pros and cons`).
- Only the listed spellings score. The term lists carry their own
  inflections (`fire` and `fired`, `sue` and `sued`, `regulator` and
  `regulators`, `cost` and `costs`, `feature` and `features`), so an
  inflection that is not listed does not match. `hire` does not match
  `hired`; `hiring` is listed separately.
- There is no negation handling. A negated stake still scores: a question
  saying `we will not hire` contains the stake term `hire`. Negation
  appears only in the ambiguity markers `not sure`, `don't know`, and
  `do not know`.
- Each list entry scores at most once per question, which is what
  "distinct" means. A domain group scores once however many of its words
  appear.
- A period only counts as a sub-question mark when it is followed by a
  space or ends the question; `?`, `!`, and `;` always count.
- Word count is whitespace-separated tokens of the lowercased text, so
  punctuation stays attached to its word.

The term arrays live in `runtime/src/flow/mode-select.ts`:

- Stakes: about sixty high-impact terms, including `lawsuit`,
  `litigation`, `sue`, `legal`, `liability`, `regulator`, `compliance`,
  `contract`, `terminate`, `fire`, `layoff`, `hire`, `acquisition`,
  `merger`, `investor`, `valuation`, `debt`, `loan`, `bankruptcy`,
  `shutdown`, `resignation`, `divorce`, `custody`, `health`, `surgery`,
  `death`, `safety`, `security`, `breach`, `fraud`, `tax`, `audit`,
  `retirement`, `mortgage`, `patent`, `penalty`, and `privacy`.
- Domains: thirteen word groups, one point value per group present:
  money and finance; contract and legal; people and hiring;
  product and roadmap; engineering and infrastructure; security and data;
  brand and marketing; customers and sales; vendors and procurement;
  property and office; health and medical; family; education and training.
- Ambiguity markers: `should i`, `should we`, `which`, `whether`,
  `option`, `options`, `unclear`, `unsure`, `not sure`, `don't know`,
  `do not know`, `torn`, `confused`, `help me`, `what if`,
  `thinking about`, `considering`, `choosing between`, `tradeoff`,
  `trade-off`, `pros and cons`.
- List connectors: `and`, `or`, `versus`, `vs`, `plus`, `also`, `both`,
  `either`.

The bands are:

| Total score | Mode |
|---|---|
| 0 to 4 | light |
| 5 to 13 | medium |
| 14 to 37 | heavy |

The edges are literal: 4 is light, 5 is medium, 13 is medium, 14 is
heavy. Nothing is rounded toward a cheaper sitting.

## Thin or empty input

`selectMode` does not refuse thin input. An empty question matches
nothing, scores 0, and returns light with `source: 'auto'`. There is no
typed error for a thin question in this path. The only refusal in the
mode path is `INVALID_MODE` for an explicit value that is not a council
size.

## What each size does

`MODE_ROUND_POLICY` in `runtime/src/contracts/modes.ts` is the source of
truth. `MODE_SEATS` is the roster length, nine, and every row uses it.

| Mode | Seats | Rounds | Wave width (`max_concurrent_calls`) | Request cap (`max_provider_requests`) |
|---|---|---|---|---|
| light | 9 | exactly 2 (minimum 2, maximum 2, never stops early) | 3 | 50 |
| medium | 9 | 1 to 4 (minimum 1, maximum 4, stop rule from round 1) | 9 | 50 |
| heavy | 9 | 3 to 10 (minimum 3, maximum 10, stop rule from round 3) | 9 | 100 |

- Light is fixed at 2 rounds: `stop_from_round` is null, so no consensus
  stop rule applies.
- Medium may stop from round 1, heavy from round 3, and neither runs past
  its maximum.
- The highest advisor-card round number is 10 (`MAX_ADVISOR_ROUND`).
- The wave width is one bound on concurrency, not the final number. The
  effective concurrency is the minimum of the provider ceiling, the nine
  seat panel, and the wave width; `references/provider-parallelism.md`
  states that rule.
- The request cap is the size's own spending limit; no other per-size
  limit is declared in this policy.

## Consensus is unchanged

Seven of the nine seats must share the same top option, and that option's
mean score must lead the runner-up by at least 1.5 points, before the
consensus stop rule may end a sitting early (`CONSENSUS_MIN_SEATS` and
`CONSENSUS_LEAD` in `runtime/src/contracts/modes.ts`, applied by
`evaluateConsensusStop` in `runtime/src/protocol/consensus.ts`). A tie
for a seat's highest score, an abstention, a non-advisor card, or a card
with no scores gives that seat no top option. The measure is unweighted
and deterministic. It is identical in every size: a size decides when the
rule may fire, never how many votes are needed.

## Mode is rounds and concurrency, never seat count

All nine advisory seats are seated in every council size. Light does not
mean three advisors: it is the full nine answering in two rounds, with
only three provider calls in flight at a time, which makes it cheaper in
wall-clock bursts rather than smaller in scope. The session schema
enforces the seat count for `light`, `medium`, and `heavy` as all nine.
Any presentation of a council sitting names all nine seats and their
output in every size.

## Worked examples

Each score below follows the table above. The first four questions are
the fixtures pinned by `runtime/src/flow/mode-select.test.ts`.

| Question in one line | Score | Breakdown | Mode |
|---|---|---|---|
| "What time is the council meeting?" | 1 | breadth 1 (one question mark) | light |
| "Should I rename the newsletter?" | 4 | breadth 3 (newsletter domain + question mark), ambiguity 1 (`should i`) | light, at the top of the band |
| "Should we renegotiate the vendor contract pricing before the renewal, or wait?" | 13 | stakes 4 (`contract`), breadth 7 (three domain groups plus question mark), ambiguity 2 (`should we`, `or`) | medium, at the top of the band |
| "Our company faces a lawsuit over a data breach; should we terminate the vendor contract, notify regulators, and lay off the security team while we negotiate the acquisition?" | 26 | stakes 16 (eight distinct stake terms, counted to the cap of four), breadth 8 (three domain groups plus semicolon and question mark), ambiguity 2 (`should we`, `and`) | heavy |
| "Run this on heavy." | not scored | client choice | heavy, source `client` |

## Related references

`references/protocol.md` for the rounds and the older four modes,
`references/provider-parallelism.md` for the concurrency minimum,
`references/model-routing.md` for the route and the request accounting,
`references/scoring.md` for how seat scores become a recommendation.
