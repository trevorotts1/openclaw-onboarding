# Provider Parallelism Reference

How many provider calls the agent may have in flight at one moment. Two
rules bound it: what the client's provider plan allows, and what the
council size allows. This page mirrors the code in
`runtime/src/providers/parallel.ts` and
`runtime/src/contracts/modes.ts`; where the two disagree, the code is
right.

## Provider ceilings

These are parallel-call ceilings on the provider route. They are a
property of the client's paid plan, not of this skill, not of the model,
and not of the box.

| Provider and plan | Provider ceiling |
|---|---|
| Ollama, $20/month plan | 3 |
| Ollama, $100+/month plan | 10 |
| Ollama, plan unknown | no number; returns `OLLAMA_PLAN_REQUIRED` (ask once) |
| Agnes 3.0 Flash | uncapped |
| OpenRouter | uncapped |
| DeepSeek Direct | uncapped |
| any other direct paid route | uncapped |

"Uncapped" means the provider contributes no parallel-call limit. It never
means unlimited requests or unlimited spend: the size's request cap still
applies, and every request is still counted.

The route is classified from a normalised slug (lowercase, punctuation
collapsed to `-`). `ollama` and every `ollama-*` variant, including
`ollama-cloud`, carry the plan cap. `openrouter*`, `agnes*`, and
`deepseek*` / `deepseekdirect` are recognised as their own providers.
Anything unrecognised is uncapped by default and never raises the Ollama
plan question.

## Asking once when the Ollama plan is unknown

The plan changes the ceiling by more than a factor of three, so it is
never guessed. A plan value is read as a monthly price by stripping
everything except digits and decimal points:

- `20`, `'20'`, `'$20/mo'` read as 20 and get 3.
- `100`, `'100+'`, `200`, `'$100/mo'`, `'100 per month'` read as 100 or
  more and get 10.
- `null`, `undefined`, `''`, `'free'`, `'unknown'`, and prices that match
  no tier (`'50'`, `35`, `'19.99'`) are unknown.

An unknown plan returns the typed refusal `OLLAMA_PLAN_REQUIRED` and no
number at all. `OLLAMA_PLAN_QUESTION` is the single question the client is
asked, naming both plans. Until it is answered the run has no Ollama
parallel limit to apply; it never plans as though the larger ceiling
applied.

## The mode table

`MODE_ROUND_POLICY` in `runtime/src/contracts/modes.ts` holds these
numbers. `MODE_SEATS` is the roster length, nine.

| Mode | Rounds | Wave width (`max_concurrent_calls`) | Request cap (`max_provider_requests`) |
|---|---|---|---|
| light | 2 (fixed) | 3 | 50 |
| medium | 1 to 4 (maximum 4) | 9 | 50 |
| heavy | 3 to 10 (maximum 10) | 9 | 100 |

Medium and heavy both take their wave width from `MODE_SEATS`, so their
wave width is nine, not ten. A council wave can never exceed the nine
seats anyway, because the panel bounds it.

## The combined rule

The effective number of calls in flight is the minimum of three bounds:

```
min(provider ceiling, panel size, mode wave width)
```

- Panel size is nine for a council sitting (`MODE_SEATS`).
- Mode wave width is 3 for light, 9 for medium and heavy.
- A provider ceiling exists only for Ollama: 3 on the $20 plan, 10 on the
  $100+ plan. Every other route contributes no ceiling.
- An unknown Ollama plan produces no number at all: the call returns
  `OLLAMA_PLAN_REQUIRED`.

`parallelLimitFor({ providerSlug, ollamaPlan, panelSize, waveWidth? })`
computes it exactly this way:

- A non-Ollama route returns `min(panel, modeCap)`.
- An Ollama route returns `min(planCap, panel, modeCap)`.
- `modeCap` is `max(1, waveWidth)`; when `waveWidth` is omitted it is the
  panel size instead, so the mode adds no cap and the panel alone bounds
  the call.
- The panel size is floored and clamped at zero; a non-finite panel size
  becomes 0.

The result is either `{ ok: true, limit: number }` or
`{ ok: false, code: 'OLLAMA_PLAN_REQUIRED' }`. The function returns the
number only; it does not report which of the three bounds was tightest.

## Worked combinations

| Route and plan | Light | Medium | Heavy |
|---|---|---|---|
| Ollama, $20/month | 3 | 3 | 3 |
| Ollama, $100+/month | 3 | 9 | 9 |
| Agnes 3.0 Flash | 3 | 9 | 9 |
| OpenRouter | 3 | 9 | 9 |
| DeepSeek Direct | 3 | 9 | 9 |
| Any other direct paid route | 3 | 9 | 9 |
| Ollama, plan unknown | `OLLAMA_PLAN_REQUIRED` | `OLLAMA_PLAN_REQUIRED` | `OLLAMA_PLAN_REQUIRED` |

Two consequences worth stating plainly:

- On an uncapped route, medium and heavy run all nine seats at once. The
  old idea of a three-call medium wave is not what the code does.
- The provider ceiling can bind before the panel does. With a panel of
  twelve and no wave width, the Ollama $100+ plan returns 10, and the
  $20 plan returns 3.

## What the limit does not cover

The parallel limit bounds simultaneous calls only. It says nothing about
how many provider requests a session may make; that is the size's own
`max_provider_requests` cap in the table above. This module computes no
request count.

## Where these numbers live

The provider table is in `runtime/src/providers/parallel.ts`; the mode
table is in `runtime/src/contracts/modes.ts`. A change to a client plan or
to a size's policy is made in that code first and copied here after, so
this page never states a cap the runtime does not compute.
