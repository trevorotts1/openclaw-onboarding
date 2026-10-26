# Council Mode Selection Reference

The council runs in one of three modes: light, medium, or heavy. A mode
sets how many rounds the council sits and how many provider calls it
issues at once. A mode never changes who sits: all nine advisors
deliberate in every mode, and consensus is still seven of nine.

## The selector

One function chooses the mode:

```
selectMode(question, explicitMode) -> { mode, source, reason }
```

- `mode` is `light`, `medium`, or `heavy`.
- `source` is `client` when the client named a mode, `auto` when the
  system chose one.
- `reason` is one short sentence a person can read, naming what drove
  the choice.
- `explicitMode` is the client's own choice. When it is given, it wins
  verbatim and nothing is scored.

The mode is chosen once, before the brief is prepared and before any
provider request is spent, and it is recorded on the session. It never
changes silently mid-sitting; a change is an explicit client control.
The chosen mode, its `source`, and its `reason` are reported with the
session, so the client can always see why the council sat as long as it
did.

## The client's choice always wins

An explicit instruction to run a particular mode overrides the
automatic choice, always and without exception: "run this on heavy",
"keep it light", "light mode". The selector returns that exact mode
with `source: client`. It does not re-score the question, does not
argue with the client, and does not accept an explicit mode outside the
three names. When the client names no mode, the system chooses
automatically - that is the default path, and it is the common one.

## How the automatic choice is made

The choice is deterministic. The selector scores the question on six
signals, sums the points, and reads the total off the threshold bands.
The same question with the same features always returns the same mode:
no randomness, no model judgement, no network call, no hidden
preference for a shorter or longer council.

| Signal | What it reads | Points |
|---|---|---|
| Decisions | distinct decisions asked, or alternatives compared: one 0, two 8, three or more 16 | 0-16 |
| Exposure | an irreversible or high-stakes domain is named - a contract, a legal or regulatory matter, safety or health, hiring or firing, reputation, or committing or deleting a resource: none 0, one 12, two or more 24 | 0-24 |
| Stakeholders | parties who bear the outcome: one 0, two or three 8, four or more 16 | 0-16 |
| Horizon | how long the outcome binds: under a month 0, one to twelve months 8, over a year or open-ended 16 | 0-16 |
| Stated gaps | the question says a material fact is unknown or conditional ("we do not know X yet", "it depends on Y"): none 0, one or two 8, three or more 16 | 0-16 |
| Size | length of the question plus explicit sub-questions: under 40 words and none 0, 40 to 150 words or one or two 6, over 150 words or three or more 12 | 0-12 |

Total range is 0 to 100. The bands are:

| Total score | Mode |
|---|---|
| 0 to 29 | light |
| 30 to 59 | medium |
| 60 to 100 | heavy |

Rules that keep the arithmetic honest:

- A score sitting exactly on a band edge (30 or 60) takes the higher
  mode. A question is never rounded down into a cheaper sitting.
- Points are awarded for what the question states, not for what the
  council suspects. A risk the question does not state scores nothing.
- `reason` names the two highest-scoring signals and the total, for
  example "score 44: hiring exposure and four-plus stakeholders". It
  never cites a signal that scored zero.
- A question too thin to score (empty or unreadable) is refused as a
  typed error, never quietly run as light.

## The mode table

| Mode | Rounds | Concurrency | Session request cap |
|---|---|---|---|
| light | 2 rounds, both always run | at most 3 provider calls in parallel, issued as waves of 3 | 50 |
| medium | up to 4 rounds | the full council, bounded by the provider and the session cap | 50 |
| heavy | up to 10 rounds | the full council, bounded by the provider and the session cap | 100 |

- Light is 2 rounds and no stop rule: the two rounds always run.
- Medium may stop early from round 1 by the consensus rule.
- Heavy runs at least 3 rounds, may stop from round 3, and never runs
  past round 10.
- The request cap is the only enforced spending limit. The cap is per
  session, and it counts every provider request, including retries and
  repairs. A sitting that reaches its cap reports the cap, never a
  fabricated completion.

## Consensus is unchanged

Seven of the nine advisors must share the same top option, with the
leading option ahead of the runner-up by the fixed lead, before the
consensus stop rule may end a sitting early. This is identical in every
mode. A mode decides how many rounds are allowed, never how many votes
are needed.

## Mode is rounds and concurrency, never seat count

All nine advisory seats are seated in every mode. Light does not mean
three advisors, and it is not a reduced council: it is the full nine
answering in two rounds, with only three provider calls in flight at a
time, which makes it cheaper in wall-clock bursts rather than smaller in
scope. Concurrency limits how fast the nine answer; it never limits who
answers. Any presentation of a council sitting names all nine seats and
their output in every mode.

The four older mode names in `references/protocol.md` (full council,
quick council, named-seat consult, rerun) keep their own meaning and are
not reinterpreted here. Light, medium, and heavy govern the rounds and
concurrency of a council sitting.

## Worked examples

| Question in one line | Score | Mode | Why |
|---|---|---|---|
| "Should I rename our newsletter?" | 0 | light | one decision, no exposure, one stakeholder, nothing unknown |
| "Should we hire a second editor this quarter, and can we afford the ramp?" | 36 | medium | two decisions (8), hiring exposure (12), two stakeholders (8), a quarter horizon (8) |
| "We do not know the penalty terms yet. Should we sign the three-year venue contract, drop the two smaller cities, and move the staff now?" | 68 | heavy | three decisions (16), contract exposure (12), four-plus stakeholders (16), a three-year horizon (16), one stated gap (8) |
| "Run this on heavy." | not scored | heavy, source `client` | the client named the mode; nothing is scored |

## Related references

`references/protocol.md` for the rounds themselves,
`references/model-routing.md` for the route and the request accounting,
`references/scoring.md` for how seat scores become a recommendation.
