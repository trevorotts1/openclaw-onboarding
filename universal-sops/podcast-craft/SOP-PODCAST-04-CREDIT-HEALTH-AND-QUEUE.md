# SOP-PODCAST-04: CREDIT HEALTH AND QUEUE

**Cluster:** Podcast-Craft Rules (`universal-sops/podcast-craft/`)
**Skill:** 58-podcast-production-engine (the Podcast Production Engine)
**Owning role:** director-of-podcast (run owner), supported by the operator on funding decisions
**Stage:** cross-cutting (the daily loop heartbeat plus every insufficient-credits hold)
**Produces:** `state/health.json`, the daily cost ledger line, credit-out queue holds and resumes, aged-out notices
**Enforcement pointer:** `58-podcast-production-engine/scripts/guard-cron-inventory.py` (exactly one cron per client, no heartbeat, no sub-daily cadence, no announce-mode chat spam, churn sweep) AND `58-podcast-production-engine/scripts/podcast-smoke-test.py` self-metering (run budget at or under 0.01 dollars, the overspend canary, the 60-day age-out, the drain trigger), with founder notices routed only through `58-podcast-production-engine/scripts/alert-dedup.py`.

---

## 0. WHY THIS SOP EXISTS

The fleet has been burned once already: a six-hour heartbeat across many agents plus dozens of crons fired real paid model turns through a signed-in local daemon and silently billed a cloud account. Every recurring process in this engine is therefore treated as a furnace until proven bounded. This SOP is the procedure that keeps the paid services (the content models, Kie.ai cover art, Fish Audio synthesis) proven funded and reachable at a cost of at most one cent per client per day, keeps every credit-out episode HELD rather than lost, ages the queue out at a hard sixty-day maximum, and keeps founder alerts from storming. A standard operating procedure without a gate is a suggestion, so every rule below names the script, the threshold, and the enforcement point that proves it.

This SOP is NOT the episode quality gate. Episode deliverability is governed by SOP-PODCAST-05 (the sixteen Tier 1 hard fails plus the ten-dimension rubric at eight or higher plus the three-strike cap). Credit health governs whether the engine can run at all, never whether an episode is good.

## 1. THE ONE CRON, AND WHY THERE IS EXACTLY ONE

This engine ships with exactly ONE recurring job per client: the daily credit smoke test, `podcast-smoke-test.py`, scheduled once daily at 6:00 AM in the client timezone with a per-client random jitter of up to fifteen minutes so a fleet of clients never stampedes a provider at the same second.

FORBIDDEN, and enforced, never merely advised:

- No heartbeat entry for this skill, ever. The skill is never added to any agent heartbeat list.
- No standalone credit-out queue poller. A held job is a JSON record, not a process.
- No per-job watchers.
- No dashboard-driven computation. Viewing the dashboard triggers nothing and costs zero dollars in model spend.
- No second podcast cron of any kind, and no sub-daily cadence.

The cron is created with the no-deliver flag so it does not announce into the client chat. The known command-line drift defaults a bare cron-add to announce mode and spams the chat; the provisioning script always passes the no-deliver flag, and `guard-cron-inventory.py` fails loudly if any podcast cron is found in announce mode.

## 2. WHAT THE DAILY SMOKE TEST DOES (AND NEVER DOES)

`podcast-smoke-test.py` probes ONLY the pinned balance and reachability endpoints in `config/smoke-endpoints.json`. It NEVER generates an image, NEVER synthesizes audio, NEVER writes an episode, NEVER takes a model turn, and NEVER runs the pipeline. Its entire run must cost at most `smoke_test.max_cost_usd` (default 0.01 dollars).

Per-service check order is cheapest method first, and a model turn is never the method:

- Ollama Cloud: the account credit or usage endpoint over HTTPS with the key in a request header only; never a daemon turn.
- OpenRouter: the key endpoint that returns limit and usage and costs nothing.
- Kie.ai: the remaining-credit lookup, else an HTTPS reachability check (status code only).
- Fish Audio: the wallet or balance endpoint, else an HTTPS reachability check. The free tier is never probed and never used for anything client-related.

Rules the script enforces in code:

- The runtime never guesses an endpoint. A provider with no pinned endpoint is marked UNKNOWN and skipped rather than spent on. A provider that needs a key but has none is marked with a key-not-set detail and reported as NOT SET; the value is never read into output.
- The result is written to `state/health.json` as one status per service (PASS, FAIL, or UNKNOWN) with a checked-at timestamp and a short detail. The dashboard reads this file; it never recomputes health.
- Self-metering: the run records its own probe cost through the cost ledger (the single source of price truth). If a run ever crosses the run budget, the script exits with the overspend canary code and routes a canary notice to the OPERATOR, never the client. That canary is the signal that someone wired a paid call into the health check.

## 3. THE CREDIT-OUT QUEUE: HOLD, RESUME, AGE OUT

A delayed episode is acceptable. A lost episode is not. Any insufficient-credits or unfunded-service error moves the episode to a held state (`queued`, `cost_hold`, or `credit_out`) with its full payload and partial state preserved, and the pipeline records the transition through the sole writer `podcast_state.py`. The job resumes from its recorded stage; nothing is ever silently dropped.

The queue is examined at exactly two moments, never by a dedicated poller:

1. Inside the daily smoke-test run. It performs the AGE CHECK and the DRAIN TRIGGER in the same single run so no second cron is ever needed:
   - AGE-OUT: a held episode that has waited `queue_max_hold_days` (default 60) or longer is aged out. The smoke test emits an age-out queue event for the sole state writer to apply (moving the stage to `aged_out`) and routes one digest-class founder notice through alert dedup. Never a silent drop.
   - DRAIN: when a paid service that a held job was waiting on flips from FAIL back to PASS between runs, the smoke test emits a drain event that releases the hold so the pipeline can resume. Service-name matching is separator-insensitive, so a hold reason of `fish_audio` still matches a service pinned as `fish-audio`.
2. Event-driven, when the operator or founder marks credits restored. A `cost_hold` episode resumes only on founder approval or a one-episode operator override key, consistent with the zero-lost-episodes rule.

The smoke test respects the single-writer contract: it reads episode records read-only and hands every state change to `podcast_state.py` (or a durable queue-event spool that the writer drains), never writing episode records itself. It refuses to write state as root; state is owned by the node user so the gateway user owns podcast state.

## 4. ALERT DEDUP: ONE FOUNDER, NEVER A STORM

Every founder notice from this loop routes through `alert-dedup.py`, the sole path to the founder alert channel for this skill. Pipeline and smoke-test code never send a chat message directly and never go around the OpenClaw gateway. Every send targets the founder or operator channel only; a client chat target is structurally never used. MOVE IN SILENCE.

The dedup mechanics that keep twenty queued jobs from becoming twenty messages:

- KEY: every alert is keyed client plus service plus failure class. Decision-class alerts add the episode id so they dedup per episode.
- FIRST OCCURRENCE: send immediately, including how many episodes are affected.
- REPEAT INSIDE THE WINDOW (`alerts.dedup_window_hours`, default 6): suppressed; the counter and the affected-episode list update in place. A downed Fish Audio with twenty queued jobs produces ONE alert, not twenty.
- WINDOW EXPIRY WHILE STILL FAILING: one updated digest ("still down, now N episodes queued, oldest X days").
- RECOVERY: one recovery message when the smoke test flips the service back to PASS and the queue drains, then the key clears.
- STORM CAP (`alerts.max_founder_alerts_per_client_per_day`, default 4): beyond the cap, status-class alerts collapse into a single end-of-day digest per client. Decision-class notices (a QC three-strike stop from SOP-PODCAST-05, a `cost_hold` halt) ALWAYS send because they are decision requests, not status, but they still dedup per episode so one event is one message.
- DIGEST-CLASS by default: aged-out drops, daily-cap deferrals, and soft-ceiling warnings accumulate and flush once per day.

## 5. THE WORST-CASE NUMBER THIS SOP GUARANTEES

An idle client (no submissions) spends 0.01 dollars per day: the single free-probe smoke test. A fully loaded client is bounded by the furnace ceilings (soft 2.50 and hard 5.00 dollars per episode, 15.00 dollars per client per day, three episodes per client per day), so the worst-case daily spend with every guardrail active is 15.01 dollars, with the day cap forcing the tail of the third episode into hold. Those ceilings are metered by `podcast-cost-ledger.py`; this SOP owns only the recurring-job side of the furnace.

## 6. CHURN: A DEPARTED CLIENT LEAVES ZERO RECURRING JOBS

An orphaned cron on a dead client is the purest furnace there is. When a client leaves, `revoke-podcast-client.sh` removes the client's smoke-test cron, disables the inbound webhook mapping, revokes dashboard access at Cloudflare, marks any queued jobs aged out with a founder notice, and archives the client state directory. `guard-cron-inventory.py --sweep` doubles as the fleet check: any podcast cron belonging to a client not on the active roster is reported. The revocation procedure itself is owned by SOP-PODCAST-03 (Revocation and Churn); this SOP owns the standing guarantee that a healthy client runs exactly one cron and a churned client runs none.

## 7. OPERATOR RUNBOOK (THE DAILY AND ON-DEMAND CHECKS)

- Prove the loop is bounded on a box, offline and free of secrets:

      python3 58-podcast-production-engine/scripts/podcast-smoke-test.py --self-test

  A green self test proves health is written, an unset-key provider is marked UNKNOWN, the run cost estimate is zero on free probes, an old held episode ages out, a recovered service drains a held episode, and the recovery and aged-out alerts are enqueued (never sent).

- Prove the cron inventory is exactly one, once daily, no heartbeat, no announce:

      python3 58-podcast-production-engine/scripts/guard-cron-inventory.py --client <slug>

  A nonzero exit means a second podcast cron, a heartbeat entry, a sub-daily cadence, or an announce-mode cron was found; fix it before the box is trusted.

- Sweep the fleet for orphaned churn crons:

      python3 58-podcast-production-engine/scripts/guard-cron-inventory.py --sweep

Never run any standalone completeness or health script that emits a client-facing message during maintenance. The founder path is alert dedup and nothing else.

## 8. ENFORCEMENT POINTER (BINDING)

- Recurring-job discipline: `58-podcast-production-engine/scripts/guard-cron-inventory.py` at provisioning time and in the repo QC gate. Fails when more than one podcast cron exists per client, when the cadence is sub-daily, when a heartbeat entry is present, when the cron announces into the client chat, or (with `--sweep`) when an orphaned churn cron survives on a client not on the active roster.
- Cost floor of the loop: `58-podcast-production-engine/scripts/podcast-smoke-test.py`, which self-meters every run to the daily ledger and fires the overspend canary to the operator (exit code 5) if a run ever crosses the run budget, and which owns the sixty-day age-out and the drain trigger in that same single run.
- The only founder path: `58-podcast-production-engine/scripts/alert-dedup.py`, which keys, windows, storm-caps, and recovers alerts and routes every send through the OpenClaw gateway to the operator channel only.
- Without these gates this document would be only a suggestion.
