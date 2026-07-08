# SOP-ANTHOLOGY-05: ANTHOLOGY CREDIT HEALTH AND QUEUE

**Cluster:** Anthology-Craft Rules (`universal-sops/anthology-craft/`)
**Skill:** 59-anthology-engine (the Anthology Engine)
**Owning role:** anthology-producer-orchestrator (run owner), supported by the operator on funding decisions
**Stage:** cross-cutting, the daily loop heartbeat plus every insufficient-credits or lost-callback hold
**Produces:** the daily health record, cron-inventory proofs, hold and resume events on the ledger, aged-out notices
**Enforcement pointer:** the smoke test plus `guard-cron-inventory.py`, together this SOP's enforcement pointer: `59-anthology-engine/scripts/anthology-smoke-test.py` (self-metering at or under one cent per run, the funded-reachability probe, the hold-queue age tick and drain trigger) AND `59-anthology-engine/scripts/guard-cron-inventory.py` (exactly one recurring engine job, daily cadence, no heartbeat, and, via its `--sweep` mode, a fleet-wide sweep for a departed producer's leftover jobs), with founder notices routed only through `alert-dedup.py`.

---

## 0. WHY THIS SOP EXISTS

The fleet has been burned once already: a signed-in local daemon plus dozens of crons silently billed a cloud account. Every recurring process in this engine is therefore treated as a furnace until proven bounded. This SOP is the procedure that keeps every paid provider (the GLM 5.2 chain, OpenRouter, Gemini, Minimax, the optional DeepSeek or Kimi tier, and Kie.ai for covers) proven funded and reachable at a cost of at most one cent per producer per day, keeps every credit-out or callback-lost participant HELD rather than lost, and keeps founder alerts from storming.

This SOP is NOT the content quality gate. Deliverable quality is governed by SOP-ANTHOLOGY-03 (Gate B, the strike gate). Credit health governs whether the engine can run at all, never whether a chapter is good.

## 1. THE ONE CRON, AND WHY THERE IS EXACTLY ONE

This engine ships with exactly ONE recurring job per producer: the daily tick, `anthology-smoke-test.py run`, scheduled once daily (default 08:00, configurable at provisioning) with per-producer jitter so a fleet of producers never stampedes a provider at the same second.

FORBIDDEN, and enforced, never merely advised: no heartbeat entry for this skill, ever; no standalone credit-out queue poller (a held participant is a ledger row, not a process); no per-job watchers; no dashboard-driven computation (viewing the Anthology board triggers nothing and costs zero dollars); no second anthology cron of any kind, and no sub-daily cadence. The cron is created with the no-deliver flag so it never announces into a client chat; the known command-line drift defaults a bare cron-add to announce mode, and `guard-cron-inventory.py` fails loudly if any anthology cron is found in announce mode or at any cadence other than daily.

## 2. WHAT THE DAILY SMOKE TEST DOES (and never does)

`anthology-smoke-test.py` probes ONLY balance and metadata endpoints, never a generation endpoint, so its total spend is provably at or under one cent, every probe a zero-generation-token read:

- Ollama Cloud: `GET https://ollama.com/api/tags`, 200 plus non-empty models means funded.
- OpenRouter: `GET https://openrouter.ai/api/v1/key`, 200 plus a positive or unlimited remaining limit means funded.
- Gemini: the models list endpoint with the key in a header, 200 plus non-empty models means funded.
- Minimax: the token-plan-remains endpoint (optional tier), 200 plus a positive remainder means funded.
- Kie.ai: the chat-credit endpoint, 200 with a positive balance means funded; 402 means unfunded.

The transport refuses any URL not on the pinned balance-endpoint allowlist, so a generation call cannot happen by accident; a provider with no pinned endpoint is marked UNKNOWN and skipped rather than spent on; a provider that needs a key but has none is reported NOT SET, the value never read into output. The result writes to a daily health record as one status per service (PASS, FAIL, or UNKNOWN) with a checked-at timestamp; the Anthology board reads this record, it never recomputes health. STDLIB ONLY, zero third-party dependencies, calls NO model.

## 3. THE HOLD QUEUE: HOLD, RESUME, AGE OUT

A delayed participant is acceptable; a lost participant is not. Any insufficient-credits or unfunded-provider error moves the participant to `held` with its exact pre-hold cursor and hold reason preserved (credit_out or callback_lost; strike_out is the third hold reason but is a content decision, never resumed here), through the sole writer `anthology_state.py hold`. `hold_queue.py` holds NO state of its own and never writes the ledger directly; it reads the local SQLite mirror read-only to enumerate the queue and compute ages, and shells the writer for `hold` and `resume`.

The queue is examined at exactly two moments, never by a dedicated poller: inside the daily smoke-test run (the AGE TICK and the DRAIN TRIGGER fire in the same single run so a second cron is never needed), and event-driven when the operator marks credits restored. The clearance policy: credit_out clears when ANY model-chain provider (ollama-cloud, openrouter, gemini, minimax) is funded and reachable, since the router will walk the chain and one funded tier justifies the retry; callback_lost clears when Kie.ai is reachable; strike_out NEVER auto-resumes, it stays held and surfaced until an operator explicitly clears it. When neither a funded set nor an explicit clear list is passed, the tick is CONSERVATIVE: it ages and reports, and resumes nothing, never blind thrashing.

## 4. ALERT DEDUP: ONE FOUNDER, NEVER A STORM

Every founder notice from this loop routes through `alert-dedup.py`, the sole path to the founder alert channel for this skill; pipeline and smoke-test code never send a chat message directly and never go around the OpenClaw gateway. A client chat target is structurally never used. Alerts are keyed producer plus service plus failure class; the first occurrence sends immediately, a repeat inside the dedup window is suppressed and the counter updates in place, window expiry while still failing sends one updated digest, and recovery sends one recovery message when the service flips back to PASS. MOVE IN SILENCE.

## 5. THE WORST-CASE NUMBER THIS SOP GUARANTEES

An idle producer (no active participants) spends at most one cent per day: the single balance-only smoke test. Runaway spend on an active run is bounded separately, by `anthology-cost-ledger.py`'s per-deliverable token ceiling shared across every internal QC attempt (SOP-ANTHOLOGY-03); this SOP owns only the recurring-job side of the furnace, never the per-deliverable content spend.

## 6. CHURN: A DEPARTED PRODUCER LEAVES ZERO RECURRING JOBS

An orphaned cron on a dead producer is the purest furnace there is. When a producer leaves, `revoke-anthology-client.sh` removes the daily tick as its own step R8, disables the intake webhook route, and archives the ledger rows; `guard-cron-inventory.py --sweep --producer-id <id> --roster <active-roster.json>` (an inline `--roster-id <id>`, repeatable, works too, without a roster file) doubles as the fleet check, reporting an off-roster producer's surviving daily tick as a CRON-ORPHAN violation (exit 4) -- or, run with no `--producer-id` over an aggregated multi-producer inventory, judging every engine-owned job by its own identity against that same roster. The revocation procedure itself is owned by the fleet Cloudflare Access Revocation Runbook's Anthology blades (`docs/OPERATOR-MAINTENANCE.md`); this SOP owns only the standing guarantee that a healthy producer runs exactly one cron and a churned producer runs none.

## 7. OPERATOR RUNBOOK (the daily and on-demand checks)

Prove the loop is bounded on a box, offline and free of secrets, with the smoke test's own self-test mode: a green self-test proves the health record is written, an unset-key provider is marked UNKNOWN, the run cost estimate is zero on free probes, an old held participant ages out, a recovered service drains a held participant, and the recovery and aged-out alerts are enqueued, never sent. Prove the cron inventory is exactly one, once daily, no heartbeat, no announce, by running `guard-cron-inventory.py` against the producer's inventory; a nonzero exit means a second anthology cron, a heartbeat entry, a sub-daily cadence, or an announce-mode cron was found, fix it before the box is trusted. Sweep the fleet for orphaned churn crons with the same guard's `--sweep` mode (`guard-cron-inventory.py --sweep --producer-id <id> --roster <active-roster.json>`, or `--roster-id <id>` inline without a roster file): any engine-owned recurring cron whose producer is not on the active roster reports CRON-ORPHAN and a nonzero exit. Never run any standalone completeness or health script that emits a client-facing message during maintenance; the founder path is alert dedup and nothing else.

## 8. DEFINITION OF DONE FOR CREDIT HEALTH

Credit health is proven, not claimed, only when: the daily tick fires exactly once per producer at daily cadence with no heartbeat and no announce mode; the smoke test's per-run cost stays at or under one cent; a held participant ages, drains, and resumes correctly through the sole writer; every founder alert is deduped and never storms; and a churned producer, once revoked, shows zero recurring jobs under `guard-cron-inventory.py --expect zero`.
