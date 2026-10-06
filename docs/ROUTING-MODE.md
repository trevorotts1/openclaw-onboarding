# ROUTING-MODE — the routing safety switch (RF-014)

One command decides HOW this box routes tasks. Every reading of the mode happens
fresh at decision time, so flipping it needs **no gateway restart** — the same
live-flip property the decision-engine kill switch (KIL-001) already has.

```
bash scripts/routing-mode.sh status
bash scripts/routing-mode.sh set auto|shadow|legacy|off|model
bash scripts/routing-mode.sh reset
bash scripts/routing-mode.sh threshold [N]
```

## The five modes

| Mode | What the box does |
|---|---|
| `auto` | JEV (the decision engine) places tasks where it can. Release default. |
| `shadow` | Same decisions `auto` would make, no JEV adoption; JEV runs comparison-only and is logged. |
| `legacy` | The old way. Zero JEV traffic. |
| `off` | Emergency JEV kill switch. Zero JEV traffic. |
| `model` | Like `auto`, PLUS: when rules and JEV cannot place a task, **this box's own default model** picks the department from this box's department list. Never a hardcoded model: the id is read from this box's `openclaw.json` (`agents.defaults.model.primary`, then the main agent, then the defaults' fallbacks). Anthropic ids and free-tier ids do not count as a usable default. If no default resolves, that task goes the `legacy` way and the fallback is logged (`routing-events.jsonl`). |

## What the owner says -> what runs

| The owner says | Run |
|---|---|
| "switch routing to the old way" | `routing-mode.sh set legacy` |
| "turn routing back on" | `routing-mode.sh set auto` |
| "turn the decision engine off" | `routing-mode.sh set off` |
| "let my own model route" | `routing-mode.sh set model` |
| "just watch it, don't change anything" | `routing-mode.sh set shadow` |
| "is routing working?" | `routing-mode.sh status` |

## Which engine decides: the Jev model, else the local engine

JEV now calls the Jev model. In `auto` and `model` mode, for any message the released
packs do not already answer word for word, the bridge asks the Jev model one question
for the message type and one for the department, using the first path that exists:

1. **The box's own Jev key** (`TYPESAFE_API_KEY`, or `JEV_API_KEY`, or `JEV_TYPESAFE_API_KEY`). Preferred.
2. **Else the box's OpenRouter key** (`OPENROUTER_API_KEY`): the same Jev model, reached through OpenRouter.
3. **Else the local engine**, exactly as it behaved before. Also used when Jev errors,
   times out, answers badly, or is not sure (top probability under 0.6). The bridge never fails
   because of Jev.

`legacy`, `off` and `shadow` send nothing to anyone. Keys are read from this box's own
stores only (process environment, `$OC_CONFIG/secrets/.env`, `$OC_CONFIG/.env`,
`openclaw.json` `env.vars`); placeholders never count; key values are never logged.

**Spending:** there is no budget limit and no budget store. The default spending rule allows
spend and transmit for the Jev decision purpose (Jev costs about 4 cents per million tokens).

**Time:** Command Center kills the bridge after 3 seconds. The whole Jev attempt is capped at
2.2 seconds (own key gets up to 1.2 s, OpenRouter gets what is left), so the local engine
always has room to answer.

**Seeing which path ran, without noise:** `routing-check.sh` prints one `routing-jev-path`
line (`own-key`, `openrouter` or `local-only`, from key names only). The bridge also writes a
`jev_path` line to `routing-events.jsonl` only when the path CHANGES, not per decision. Nothing
is sent to anyone and nothing new is scheduled; the line appears whenever the existing health
check already runs.

## The tripwire (automatic, never touches an owner's choice)

When JEV routing fails **N times in a row** (default 5; `routing-mode.sh threshold N`
or `$OPENCLAW_ROUTING_TRIPWIRE_FAILURES`, minimum 1), an unpinned box flips ITSELF
to `legacy`, writes a clear event, and stays there until the owner switches back:

- `$OC_CONFIG/routing-tripwire.flag` — one JSON line, same shape as the Rescue
  Rangers `rr-intake-auth.flag` (`{"class":"ROUTING_TRIPWIRE_TRIPPED",...}`,
  with `remedy`). Health check and Rescue Rangers read the flag; no flag file
  means nothing is wrong right now (the absence of a flag is not a claim that
  routing works).
- `$OC_CONFIG/routing-events.jsonl` — append-only: `tripwire_tripped`,
  `mode_set`, `mode_reset`, `model_mode_fallback_legacy`. No task text, no secrets.
- The mode file carries a `# set-by: tripwire` marker on line 2, so every reader
  can tell a tripped box from an owner-pinned one.

**A box whose owner explicitly chose a mode is NEVER flipped** — that is every
`set` (any value), any env pin (`$OPENCLAW_DECISION_ENGINE_MODE`), and any box
with a mode file that the tripwire did not write. The tripwire only acts on a box
running the release default. A successes reset the failure counter but never
un-trip a box; only the owner does that (`set …` pin or `reset`).

## The store, unchanged

`$OC_CONFIG/decision-engine-mode.conf` — one word, first line (`auto shadow legacy
off model`). `scripts/decision-engine-mode.py` stays the referee: after any
`set`, the install/update receipt (`--assert-preserved`) still honours the stored
value, and updates never overwrite it (preserve-by-construction, A62).

## Health gate (part d)

`scripts/health/routing-check.sh` is the routing half of the box health check,
the companion to `scripts/health/library-gate-check.sh` (RF-011). Read-only,
never writes, never sends. Prints one verdict per line:

- `routing-mode` — which mode and WHO chose it (env / store / default / tripped);
- `routing-tripwire` — armed / tripped (flag path named for Rescue Rangers) / how close;
- `routing-jev-path`: which path the Jev model would use (`own-key` / `openrouter` /
  `local-only`), from key NAMES only, never values;
- `routing-works` — the installed bridge answers a capability probe (2 s cap);
  in `model` mode, whether the box's default model resolves. `off`/`legacy` is an
  honest WARN (owner chose it), a corrupt store FAILS, "cannot tell" is never a pass.

Exit 0 = no failure (warnings allowed), 1 = at least one FAIL, 5 = cannot tell.

## One Command Center note

Command Center validates the bridge's mode word with its own `VALID_MODES`
list (`src/lib/decision-engine/live.ts`). Until Command Center's list learns
`model`, a box set to `model` is treated there as `off` — the box routes safely
(no JEV), but CC will not call the bridge in model mode. Ship the Command Center
enum update in the paired release, then `model` works end to end.

## Files

| File | Role |
|---|---|
| `shared-utils/routing_switch.py` | the ONE writer: store, tripwire, events, flag |
| `shared-utils/model_route.py` | `model` mode pick: own-default-model resolution + the ask |
| `shared-utils/jev_live.py` | the Jev chain for the bridge: own key, else OpenRouter, over the existing ladder; unlimited-spend default rule |
| `shared-utils/decision-engine.py` | asks the Jev chain first, keeps the local engine as the answer when it fails; counts outcomes (auto/model only) and calls the model pick when rules cannot place a task |
| `scripts/routing-mode.sh` | owner switch (`status` / `set` / `reset` / `threshold`) |
| `scripts/health/routing-check.sh` | health-gate companion check |
| `tests/unit/routing-mode-switch.test.sh` | the shell suite (fixture boxes, real scripts) |
| `tests/unit/test_rf014_model_mode.py` | the bridge seams in-process |
| `tests/unit/test_jev_live_chain.py` | the Jev chain, offline with fake transports |