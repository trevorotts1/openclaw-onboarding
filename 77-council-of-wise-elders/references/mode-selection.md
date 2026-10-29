# Council Mode Selection Reference

The council runs in one of three sizes: light, medium, or heavy. A size
sets how many rounds the council sits, how many provider calls it issues
at once, and the session's provider-request cap. A size never changes who
sits: all nine advisors deliberate in every council size, and consensus is
still seven of nine.

## Which modules choose the mode

Two shipped modules matter, and only one of them runs on a live convene:

- `runtime/src/flow/mode-select.ts` - `selectMode(question, explicitMode?)`.
  The one selector: one question in, one `{ mode, source, reason }` out.
- `runtime/src/service/driver.ts` - `resolveModeSelection(explicit,
  question)`. The resolver the shipped convene service calls; for a question
  with text it delegates to `selectMode`. `driver.ts` is imported by
  `runtime/src/service/composition.ts` and the service barrel, and its
  convene build is where a live session's mode is resolved.

`runtime/src/flow/convene-flow.ts` also calls `selectMode`, but no `src`
module imports it - only its own test (`src/flow/convene-flow-mode.test.ts`)
does. It is a flow module on its own test path, not the path a shipped
convene takes.

Where the provenance surfaces:

- The convene **response** carries `mode_selection` (the driver's
  `ModeSelection`, declared at `driver.ts:120-124` and returned at
  `driver.ts:696`), so the client sees the mode, the source and the reason.
- The persisted **session record** carries the chosen mode as `spec.mode`.
  It carries no `mode_selection`: the session spec schema is strict and
  rejects that unknown key.
- `convene-flow.ts:260` attaches `mode_selection` to the session object it
  returns, in that module only.

`selectMode` imports nothing but the mode enum. It is text arithmetic: no
randomness, no clock, no model call, no network, no client context. The
same question always returns the same size; three consecutive calls on one
question are byte-identical. What each size then does is
`MODE_ROUND_POLICY` in `runtime/src/contracts/modes.ts`; neither the
selector nor the resolver reinterprets it.

## The selector

```
selectMode(question, explicitMode?) -> { mode, source, reason }
```

- `mode` is `light`, `medium`, or `heavy`. An automatic choice always
  returns one of these three; a client choice is the council size the
  client's mode maps to.
- `source` is `client` when the client named a mode, `auto` when the
  system classified the question.
- `reason` is a fixed-format line, in five shapes:
  1. automatic: `complexity score <n> (stakes <a>, breadth <b>, ambiguity
     <c>) selected <mode>`
  2. client choice of `light`, `medium`, `heavy`: `client selected <mode>`
  3. client choice of `full`, `selected`, `quick`, `consult`: `client
     selected <mode> (council size <size>)` - for example
     `client selected quick (council size light)`
  4. the driver's client choice, for any of the seven values: `client
     selected <mode>`, verbatim, with no size suffix - the driver returns
     the client's mode unchanged and never maps it
  5. the driver, with no explicit mode and no question text: `no question
     text to classify; defaulted to medium`

## The client's explicit mode always wins

An explicit instruction to run a particular mode overrides the automatic
choice, always and without exception. Both shipped entry points honour it.
All seven canonical session modes are accepted, and each is mapped to the
council size it deliberates at:

| Explicit value | `selectMode` size | `selectMode` reason | Driver `mode` / reason |
|---|---|---|---|
| `full` | heavy | `client selected full (council size heavy)` | `full` / `client selected full` |
| `selected` | medium | `client selected selected (council size medium)` | `selected` / `client selected selected` |
| `quick` | light | `client selected quick (council size light)` | `quick` / `client selected quick` |
| `consult` | light | `client selected consult (council size light)` | `consult` / `client selected consult` |
| `light` | light | `client selected light` | `light` / `client selected light` |
| `medium` | medium | `client selected medium` | `medium` / `client selected medium` |
| `heavy` | heavy | `client selected heavy` | `heavy` / `client selected heavy` |

Layer notes, all measured:

- `selectMode` alone trims and lowercases the explicit value, so `FULL`,
  `FuLl` and `  quick  ` are honoured (measured: `FULL` → heavy, source
  `client`; `  quick  ` → light, source `client`).
- The driver's `resolveModeSelection` passes an explicit value through
  verbatim (measured: `FULL` → mode `FULL`, reason `client selected FULL`;
  `  quick  ` → mode `  quick  `). Its `explicit` parameter is typed
  `SessionMode`, so an out-of-enum value is a type error at the boundary,
  and a value that reaches a session anyway fails `sessionSpecSchema` at
  path `mode` (`invalid_value`: `Invalid option: expected one of
  "full"|"selected"|"quick"|"consult"|"light"|"medium"|"heavy"`) - it is
  not a runtime fallback.
- A value outside `SESSION_MODES` is not a mode for `selectMode`: it falls
  through to the automatic classification, whose score belongs to the
  question and not to the explicit value (measured with explicit `bogus`:
  question `bogus` → source `auto`, score 0, light; question `?` → source
  `auto`, score 1, light; empty question → source `auto`, score 0, light).
- `convene-flow.ts` is stricter than both: an explicit value that is not a
  council size is refused with `INVALID_MODE: "<value>" is not a council
  size; expected one of light, medium, heavy.` That refusal lives only in
  that module.

### Seat counts are set by the session schema

`SESSION_MODES` in `runtime/src/contracts/enums.ts` has seven values and
`sessionSpecSchema` in `runtime/src/contracts/schemas.ts` accepts all
seven. The seat rules it enforces, measured by validating 1, 2 and 9 seats
in every mode:

| Session `mode` | Seats the schema requires |
|---|---|
| `full` | all nine |
| `consult` | exactly one |
| `selected` | two to eight |
| `light`, `medium`, `heavy` | all nine |
| `quick` | no seat-count rule - 1, 2 and 9 seats all validate |

### What the four older modes do

`full`, `selected`, `quick` and `consult` keep their own behaviour and
their own protocol (`references/protocol.md`). `isCouncilSize()` is false
for them, so the driver gives them the older modes' fixed ceilings -
`max_provider_requests` 50, `max_output_repairs` 9, `max_transport_retries`
8 - a `rounds` of `null`, and a concurrency limit of 1. No wave width is
taken from `MODE_ROUND_POLICY` for them.

The schema then constrains the panel. A convene with `consult` and no
explicit `seat_ids` defaults to all nine seats (`driver.ts:431`,
`:464-466`) and is refused by `validateSessionSpec` (`:498-501`) with
`consult mode requires exactly one seat`; `selected` is refused the same
way unless two to eight seats are supplied. (This is a code reading plus a
schema probe, not a convene run.)

## How the automatic choice is made

The choice is deterministic. `scoreComplexity` lowercases the question,
adds three buckets, and reads the total off two thresholds. Scores are
small integers; the maximum possible total is 37.

| Bucket | What scores | Points | Cap |
|---|---|---|---|
| stakes | each distinct high-impact term present | +4 | 16 |
| breadth | each distinct domain group present | +2 | 8 |
| breadth | each `?`, `!`, or `;`, plus each `.` followed by a space or the end of the question | +1 | 4 |
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
- Stake matching is negation-aware. The negators are exactly `no`, `not`,
  `without`, `zero`, `never`. A stake term is suppressed when a negator
  appears within the four words immediately before it in the same clause;
  `.`, `,`, `;`, `!`, `?` start a new clause.
- Only the stakes bucket is negated. Domain groups, sub-question marks,
  ambiguity markers, connectors and length are counted whether or not the
  clause is negated.
- The rule is positional, not grammatical: it can suppress a stake in
  "no legal risk but a big contract dispute" style sentences depending on
  word position, and it can miss a negation carried by a word outside the
  four-word window.
- The term lists are seeds. For each listed term the matcher generates the
  term itself, `+s`, `+es`, `+ed`, `+ing`; for a term ending in `e`, also
  the e-stem `+ing` and `+ed`; for a term ending in `y`, also `-ies` and
  `-ied`. Matching is whole-word and case-insensitive after lowercasing.
- Consequences: `hire` matches `hired` and `hiring`; `sue` matches `suing`
  and `sued`; `lawsuit` matches `lawsuits`; `liability` matches
  `liabilities`.
- Each list entry scores at most once per question, which is what
  "distinct" means. A domain group scores once however many of its words
  appear.
- A period only counts as a sub-question mark when it is followed by a
  space or ends the question; `?`, `!`, and `;` always count.
- Word count is whitespace-separated tokens of the lowercased text, so
  punctuation stays attached to its word.

Negation, measured:

| Question | Score | Result |
|---|---|---|
| `we will not hire anyone` | 2 (stakes 0, breadth 2, ambiguity 0) | light |
| `we will hire anyone` | 6 (stakes 4, breadth 2, ambiguity 0) | medium |
| `no legal risk` | 2 (stakes 0, breadth 2, ambiguity 0) | light |
| `we go without a contract` | 2 (stakes 0, breadth 2, ambiguity 0) | light |
| `we were never sued` | 0 (stakes 0, breadth 0, ambiguity 0) | light |
| `we will not hire, we will fire people` | 6 (stakes 4, breadth 2, ambiguity 0) | medium - the comma ends the clause, so `fire` is scoped only by its own clause |

Inflections, measured: `we hired someone` and `we hire someone` both score
6 (stakes 4, breadth 2, ambiguity 0) and select medium; `we are suing them`
scores 4 (stakes 4, breadth 0, ambiguity 0) and selects light; `two
lawsuits` scores 6 and selects medium; `the costs are high` scores 2
(domain only) and selects light, because `cost` is a domain seed, not a
stake seed.

The term arrays live in `runtime/src/flow/mode-select.ts`:

- Stakes: 62 high-impact terms, including `lawsuit`, `litigation`, `sue`,
  `legal`, `liability`, `regulator`, `compliance`, `contract`, `terminate`,
  `fire`, `layoff`, `hire`, `acquisition`, `merger`, `investor`,
  `valuation`, `debt`, `loan`, `bankruptcy`, `shutdown`, `resignation`,
  `divorce`, `custody`, `health`, `surgery`, `death`, `safety`, `security`,
  `breach`, `fraud`, `tax`, `audit`, `retirement`, `mortgage`, `patent`,
  `penalty`, and `privacy`.
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

Both shipped paths answer, and they answer differently. Name the path,
never just the function:

- **`selectMode`:** an empty or whitespace-only question matches nothing,
  scores 0, and returns `light`, source `auto`, reason
  `complexity score 0 (stakes 0, breadth 0, ambiguity 0) selected light`.
  There is no typed error for a thin question in this path.
- **The shipped convene driver (`runtime/src/service/driver.ts`,
  `resolveModeSelection`):** with no explicit mode and no question text it
  returns `medium`, source `auto`, reason
  `no question text to classify; defaulted to medium`. That is the mode a
  live convene resolves for a blank question, and it is pinned by
  `tests/mode-autoselect-live.test.ts:161-168`.

Reachability, stated exactly: the driver resolves the mode before brief
validation. An empty string is then refused by `decisionBriefSchema`
(`question` requires at least one character), so no session is created; a
whitespace-only question passes that check and convenes at `medium`.

The only typed refusal in the mode path itself is `INVALID_MODE` in
`convene-flow.ts` for an explicit value that is not a council size.

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

## Mode is rounds and concurrency, not a smaller panel

For the three council sizes, all nine advisory seats deliberate in
`light`, `medium` and `heavy`, and the session schema enforces nine for
each. Light does not mean three advisors: it is the full nine answering in
two rounds, with only three provider calls in flight at a time, which
makes it cheaper in wall-clock bursts rather than smaller in scope. Any
presentation of a council sitting names all nine seats and their output in
every council size. The four older session modes are not council sizes and
carry their own seat rules, above.

## Worked examples

Each score below follows the table above. The first four questions are
the fixtures pinned by `runtime/src/flow/mode-select.test.ts`.

| Question in one line | Score | Breakdown | Mode |
|---|---|---|---|
| "What time is the council meeting?" | 1 | breadth 1 (one question mark) | light |
| "Should I rename the newsletter?" | 4 | breadth 3 (newsletter domain + question mark), ambiguity 1 (`should i`) | light, at the top of the band |
| "Should we renegotiate the vendor contract pricing before the renewal, or wait?" | 13 | stakes 4 (`contract`), breadth 7 (three domain groups plus question mark), ambiguity 2 (`should we`, `or`) | medium, at the top of the band |
| "Our company faces a lawsuit over a data breach; should we terminate the vendor contract, notify regulators, and lay off the security team while we negotiate the acquisition?" | 28 | stakes 16 (capped at four distinct stake terms), breadth 10 (four domain groups - contract/legal, people/hiring, security/data, vendors/procurement - plus semicolon and question mark), ambiguity 2 (`should we`, `and`) | heavy |
| "Run this on heavy." | not scored | client choice | heavy, source `client` |

The maximum possible total is 37: stakes 16, breadth 12 (8 for the domain
groups plus 4 for the sub-question marks), and ambiguity 9 (3 markers, 2
connectors, 4 length).

The band edges are literal. Measured at both edges: "Should I rename the
newsletter?" scores 4 and selects light; "Should we renegotiate the vendor
contract pricing before the renewal, or wait?" scores 13 and selects
medium; 14 is the heavy threshold.

## Related references

`references/protocol.md` for the rounds and the older four modes,
`references/provider-parallelism.md` for the concurrency minimum,
`references/model-routing.md` for the route and the request accounting,
`references/scoring.md` for how seat scores become a recommendation.
