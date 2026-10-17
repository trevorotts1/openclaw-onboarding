# Browser Engine Contract (Amendments 5 and 5B)

How this skill's browser work is described, so the words mean the same
thing on every harness. Skill 6's session rules are the floor; where this
contract and Skill 6 differ, the contract's terms govern how THIS skill's
stages and receipts speak, without changing Skill 6.

## The contract terms

Every browser operation in a stage is expressed in these terms:

- **launch**: start or attach a browser session for one named job. A
  session is never shared with another stage or another run.
- **seed**: prepare the session's starting state: the target URL, any
  sign-in state the stage is authorized to use, and the viewport set the
  stage's checks require (desktop and mobile for delivery stages).
- **act**: perform the stage's interactions: navigations, clicks, form
  fills, uploads. Every act that a receipt claims is an act the session
  actually performed.
- **capture**: record evidence from the live session: screenshots under
  the stage's named evidence paths, the final URL, and the observed state
  the receipt reports (rendered product and price, open pop-up, visible
  form).
- **teardown**: close the session's pages and contexts when the stage's
  work ends.
- **reap**: verify nothing the stage launched is still running, and
  account for it. A stage does not close with unaccounted browser work
  (the teardown and hygiene gate is Item 33; this contract supplies the
  vocabulary its receipts use).

Sessions are ISOLATED and NAMED: each launch carries the run's stage name,
and receipts that cite browser work name the session that did it.

## Engine bindings

Engine names below are **DRAFT-PENDING-LANDING**: they name the engines as
Skill 6's updated text will describe them once its change lands (draft PR
#1990 on the onboarding repo, NOT merged). The contract terms above do not
depend on any engine name and do not change when the landing completes.

| Harness | Primary | Fallback lanes |
|---|---|---|
| OpenClaw | OpenClaw Chrome extension (DRAFT-PENDING-LANDING) | agent-browser CLI; Playwright as escape hatch |
| Claude Code | agent-browser CLI | Playwright and Chrome DevTools MCP lanes where the harness provides them |

Why the bindings differ: the OpenClaw Chrome extension drives the
operator's real, signed-in Chrome, which is where GHL and Vercel sessions
already live on that harness; the Claude Code harness has no such
extension surface, so its binding rides the agent-browser CLI. When Skill
6's engine text lands, Items 32 and 33 re-read their session language
against the extension session model: an invariant that cannot hold
literally (a per-run isolated profile, for example, where the engine
attaches to the operator's real browser) gets an extension-accurate
restatement in the receipt, never a silent exception. The gate rule
survives either way: no stage closes with unaccounted browser work.
