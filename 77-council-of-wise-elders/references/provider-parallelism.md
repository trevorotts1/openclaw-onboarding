# Provider Parallelism Reference

How many agents may run at the same time on the client's provider plan.
This reference states the caps the agent applies before it fans work out.
It is operator-facing: it tells the operator and the agent what the
client's plan actually allows, and it never assumes a plan the client
has not stated.

## The caps

These are **parallel agent caps**: how many agents may be in flight at
one moment on that provider and plan. They are a property of the client's
paid plan, not of this skill, not of the model, and not of the box.

| Provider and plan | Agents in parallel |
|---|---|
| Ollama, 20/month plan | 3 |
| Ollama, 100+/month plan | 10 |
| Ollama, plan unknown | ask the client once (`OLLAMA_PLAN_REQUIRED`) |
| Agnes 3.0 Flash | unlimited |
| OpenRouter | unlimited |
| DeepSeek Direct | unlimited |

"Unlimited" means the provider plan imposes no parallel-agent cap. It
never means unlimited requests or unlimited spend: the session and
provider request ceilings still apply, and every request is still
counted.

## Asking once when the Ollama plan is unknown

The Ollama plan changes the cap by a factor of more than three, so it is
never guessed and never inferred from a model id, a key shape, a past
session, or a neighbour box. When the plan is unknown, the agent asks
the client exactly one question ("Which Ollama plan are you on, the
$20 one or the $100+ one?"), records the answer for that client, and
applies the matching cap. Until the answer exists the run reports
`OLLAMA_PLAN_REQUIRED` and plans as if the 3-agent cap applied; it never
plans as if the larger cap applied on the hope it is right.

## These caps are not the mode tables

The mode tables in the build and dispatch apparatus bound a different
thing: how many deliberation rounds a mode runs and how wide one wave may
be inside that mode.

| Mode | Rounds | Parallel wave | Request cap |
|---|---|---|---|
| light | 2 | 3 | 50 |
| medium | 4 | 3 | 50 |
| heavy | 10 | 10 | 100 |

Both rules are binding at once, and **the lower of the two applies**.
A heavy mode on an Ollama 20/month plan runs at most 3 agents in
parallel, because the provider cap is the tighter one. A light mode on
Agnes 3.0 Flash still runs at most 3 agents in parallel, because the
mode's wave width is the tighter one. Neither rule ever raises the
other.

## What the agent does at the cap

- It queues the remaining work and runs it in the next wave. It never
  oversubscribes in the hope a 429 will sort itself out.
- It reports the cap it applied and which rule set it (provider plan or
  mode), so the operator can see why a wave was narrow.
- A provider error that indicates the plan is being exceeded is reported
  as that, in plain words, and is never silently retried until it
  appears to pass. If the plan turns out to be smaller than the client
  stated, the caps table is corrected for that client before the next
  wave, not after the next failure.
- Sequential requests, retries, repair requests and reconciliation
  requests are not agents. They count against the request ceilings, not
  against the parallel-agent caps.

## Sourcing

The caps in this reference come from the operator's ruling of
2026-10-25. A change to a provider plan, a new provider, or a provider
that starts enforcing its own concurrency limit is recorded here first,
with its date, and only then applied. This file is the single statement
of the parallel caps; agent instructions point here rather than restating
the numbers.
