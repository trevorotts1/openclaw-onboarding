# FURNACE PREVENTION AND TOKEN-BURN DESIGN
## Podcast Production Engine — Cost Guardrail Specification v1.0
### Status: DESIGN — implementable directly by /goal build agents

Source docs: `<OPERATOR_HOME>/Downloads/PODCAST_EPISODE_GENERATION_SYSTEM.md` (behavior spec) and `<OPERATOR_HOME>/Downloads/CLAUDE_CODE_BUILD_BRIEF.md` (build brief). This document closes the cost gaps those docs leave open and turns operator furnace doctrine into enforceable code.

---

## 0. DOCTRINE (why this document exists)

The fleet has already been burned once: a 6-hour heartbeat across many agents plus dozens of crons fired real `:cloud` turns through the signed-in local Ollama daemon and silently billed Ollama Cloud. Every recurring process in this skill is therefore treated as a furnace until proven bounded. Design rules baked into everything below:

1. **Recurring work must be metered, capped, and inventoried.** If a cron, poller, or heartbeat cannot state its worst-case daily cost, it does not ship.
2. **A signed-in Ollama daemon bills Ollama Cloud on ANY `:cloud` turn.** Health checks never take a model turn when a balance endpoint exists.
3. **Model tiering:** Opus 4.8 is a BUILD-TIME thinking tool only. The shipped client runtime routes all content work to Kimi 2.6 / GLM 5.2 on Ollama Cloud, then OpenRouter equivalents, then Gemini 3.1 Flash Lite. Client skills NEVER use Anthropic/Claude models. This is enforced by a build gate, not by prose.
4. **Enforcement, not description.** Every rule below names a script, a config key, a threshold, and the exact enforcement point.

Known gaps in the source docs that this design closes: no per-episode cost ceiling; the QC 3-strike loop implies re-running the FULL writing protocol (up to 3x episode cost); no cap on web-research calls; a daily 6:00 AM credit smoke test, queue pollers, and dashboard polling that can each become a furnace; no alert dedup (a downed Fish Audio with 20 queued jobs would storm the founder with 20 Telegram messages).

---

## 1. GUARDRAIL 1 — DAILY CREDIT SMOKE TEST IS DIRT CHEAP

**Script:** `scripts/podcast-smoke-test.py` (invoked by one cron per client)
**Hard budget:** the entire daily smoke test run must cost at most `smoke_test.max_cost_usd = 0.01`. It NEVER generates an image, NEVER synthesizes audio, NEVER writes an episode, NEVER runs the pipeline.

Per-service check order (cheapest method first, model turn is last resort):

| Service | Method 1 (free) | Method 2 (fallback, near-zero) | FORBIDDEN |
|---|---|---|---|
| Ollama Cloud | Account/usage/credits API endpoint via HTTPS with the API key (no daemon turn) | 1-prompt call on the CHEAPEST listed model with `num_predict: 1` (or `max_tokens: 1`), timeout 15s | `ollama run` against the signed-in daemon; any prompt without an output-token cap |
| OpenRouter | `GET /api/v1/key` (returns limit + usage, costs nothing) | none needed | any completion call |
| Kie.ai | Credit/account query endpoint (Kie.ai exposes remaining-credit lookup) | HTTPS reachability check (status code only) | any image generation task |
| Fish Audio | Wallet/credit/balance API endpoint | HTTPS reachability check | any text-to-speech synthesis |
| Perplexity (if wired) | HTTPS reachability check only | none | any search call |

Rules:
- The build agent verifies each provider's current balance-endpoint path against live docs at build time and pins it in `config/smoke-endpoints.json` so the runtime never guesses.
- If a provider exposes NO balance endpoint, Method 2 applies with the hard output cap. If even Method 2 would exceed the run budget, mark that provider `UNKNOWN` and skip; do not spend to find out.
- Result is written to `state/health.json` (`{service: {status: PASS|FAIL|UNKNOWN, checked_at, detail}}`). Every FAIL routes through `alert-dedup.py` (Guardrail 7); it is never a raw Telegram send.
- The same single run performs the credit-out queue age check and drain trigger (Guardrail 6) so no second cron exists.
- Self-metering: the script logs its own cost estimate to the daily ledger; if a run ever exceeds `$0.01`, it alerts the operator (not the client) with reason `smoke_test_overspend` — that is the canary that someone wired a render into the health check.

---

## 2. GUARDRAIL 2 — DASHBOARD READS PERSISTED STATE, NEVER RECOMPUTES

**Data source:** `state/episodes/<episode_id>.json` (one persisted record per submission) plus `state/ledger/<YYYY-MM-DD>.json` (daily cost ledger). Written write-through by the pipeline at every stage transition via `scripts/podcast-episode-state.py` (subcommands: `create`, `set-stage`, `set-links`, `set-queue`, `get`, `list`).

Episode record schema (minimum):

```json
{
  "episode_id": "…", "client": "…", "contact_id": "…",
  "submitter": {"first_name": "…", "last_name": "…", "email": "…", "phone": "…"},
  "mode": "personal|interview", "style": "…",
  "stage": "received|researching|writing|qc|art|audio|publishing|enrolling|complete|queued|cost_hold|aged_out|failed_qc",
  "queue": {"held": false, "reason": null, "held_since": null, "age_days": 0},
  "qc": {"attempts": 0, "last_failures": []},
  "cost": {"usd_estimate": 0.0, "llm_tokens": 0, "research_calls": 0, "image_gens": 0, "tts_chars": 0},
  "links": {"podbean": null, "package_doc": null, "speech_doc": null, "book_teaser": null},
  "timestamps": {"received": "…", "updated": "…", "completed": null}
}
```

Enforcement:
- The dashboard (Cloudflare-hosted per the build brief) is a static front end plus a dumb read-only endpoint over these files (or a SQLite mirror of them). It contains ZERO model-provider SDK imports, ZERO OpenClaw agent invocations, ZERO pipeline calls. Viewing the dashboard costs $0.00 in model spend, always.
- Client browser auto-refresh interval floor: `polling.dashboard_min_refresh_seconds = 60`. The endpoint sets `Cache-Control: max-age=30`. No websockets, no server push, no background workers.
- Status is never derived by re-running any stage. If a record is missing, the dashboard shows "unknown", it does not trigger a run.
- Build gate: `guard-no-anthropic-runtime.py` (Guardrail 5) also scans the dashboard directory and FAILS the build if it finds any model-provider import, any completion/generation endpoint URL, or any call into the pipeline scripts.

---

## 3. GUARDRAIL 3 — PER-EPISODE AND PER-CLIENT-PER-DAY COST CEILINGS

**Script:** `scripts/podcast-cost-ledger.py` — the single metering choke point. Every billable call in the pipeline (LLM turn, web-research call, Kie.ai task, Fish Audio synthesis) goes through its wrapper: `precheck` BEFORE the call (would this exceed a ceiling?), `record` AFTER (actual units consumed).

Unit prices live in `config/cost-model.json` (a static price table the build agent fills from current provider pricing and the operator can restamp). Call sites meter UNITS (tokens, calls, images, TTS characters); the ledger converts to dollars. Prices drifting never requires code changes.

Config keys and defaults (all under `podcast_engine.limits` in the skill config; per-client overridable):

| Key | Default | Meaning |
|---|---|---|
| `per_episode_cost_usd_soft` | 2.50 | Warn: log + one deduped operator notice; run continues |
| `per_episode_cost_usd_hard` | 5.00 | HALT: episode moves to `cost_hold` (state preserved like the credit-out queue), founder alerted once via dedup |
| `per_client_daily_cost_usd_hard` | 15.00 | New billable calls for this client refuse until next local day; in-flight episode finishes its current stage then holds |
| `per_client_daily_episode_cap` | 3 | Episode 4+ of the day is QUEUED to next day (never dropped), one digest notice |
| `llm_tokens_per_episode_hard` | 400000 | Total content-model tokens across ALL passes and ALL QC attempts combined |
| `llm_max_output_tokens_per_call` | 8000 | Per-call output cap passed to the provider on every content call |

Enforcement points:
1. **Pre-call:** the model/tool wrappers refuse any call whose estimate would cross a hard ceiling; refusal returns a typed `CostCeilingExceeded` result the pipeline maps to `cost_hold`.
2. **Stage boundaries:** `podcast-episode-state.py set-stage` calls `podcast-cost-ledger.py summary` and enforces the soft-warn.
3. **Release path:** a `cost_hold` episode resumes only when the founder replies approval (or the operator sets a one-episode override key `podcast_engine.limits.override_episode_id`), consistent with the zero-lost-episodes rule: held, never dropped.
4. Expected real cost of a healthy 10-minute episode is well under $1.50 (roughly 14,000 TTS characters, one 1K image, one research pass, one write cycle), so these ceilings only trip on runaway loops — which is exactly their job.

---

## 4. GUARDRAIL 4 — QC RE-RUN CAP AND WEB-RESEARCH CAP

**Script:** `scripts/qc-attempt-gate.py` — owns the persisted `qc.attempts` counter. The 3-strike cap from the spec stays (hard stop at 3, founder notified with failing checks and best draft). This design bounds what each strike COSTS:

- **Research runs ONCE.** The research package (improved answers, power statements, case studies) is frozen into the episode record after Step 3. QC failure attempts 2 and 3 REUSE it. Steps 3–5 (research, sizing, blueprint) are never re-executed on a QC retry. Sole exception: a Tier 1 check 12 (fabrication) failure unlocks one supplemental research pass of at most `web_research_bonus_on_fabrication_fail = 4` calls, once per episode.
- **Retries are TARGETED, not full rewrites.** Attempt 2 and 3 revise only the sections/dimensions that failed (the gate passes the failure list into the revision prompt). A full Step 6–8 rewrite is permitted only on attempt 2 if more than 4 rubric dimensions failed; attempt 3 is always targeted. Worst case is therefore roughly 1.6x single-write cost, not 3x.
- **Tier 1 is deterministic, not LLM.** `scripts/qc-tier1-mechanical.py` checks em dash, triple backticks, markdown, labels, title placement, speakable characters, tag syntax, tag-excluded word count, forbidden names, forbidden word by style, intake contamination — pure string/regex/counting at $0.00. Only fabrication, mode perspective, and pronoun correctness use an LLM check, routed to the CHEAP tier (Gemini 3.1 Flash Lite or GLM 5.2). Tier 2 rubric scoring runs on the mid tier, never on the primary creative model with high thinking.
- **Web-research cap:** `web_research_calls_per_episode = 12` (covers 3 case studies at ~3 queries each plus verification), enforced by the research-tool wrapper through `podcast-cost-ledger.py precheck`. Call 13 returns a typed refusal; the writer proceeds with what it has (the spec already prefers fewer honest case studies over padded ones).
- All attempts draw from the ONE shared `llm_tokens_per_episode_hard` budget (Guardrail 3), so even a pathological retry loop cannot spend past the ceiling.
- Book teaser (interview mode) gets one write plus at most one revision; it shares the episode token budget.

---

## 5. GUARDRAIL 5 — RUNTIME MODEL TIERING + ANTHROPIC BUILD GATE

Runtime routing config (shipped in the skill):

```yaml
podcast_engine:
  models:
    content:            # in strict priority order, high thinking on 1 and 2
      - ollama-cloud/kimi-2.6
      - ollama-cloud/glm-5.2
      - openrouter/<kimi-2.6-equivalent>   # build agent pins exact current OpenRouter ids
      - openrouter/<glm-5.2-equivalent>
      - gemini-3.1-flash-lite              # final fallback
    qc_judge:           # rubric + semantic Tier 1 checks (cheap tier)
      - gemini-3.1-flash-lite
      - ollama-cloud/glm-5.2
    deny_patterns: ["claude", "anthropic", "us.anthropic", "opus", "sonnet", "haiku"]
```

- The router refuses any model id matching `deny_patterns` — including the spec's "select a suitable replacement" branch. A substitution that matches the deny list is a hard error, never a fallback. Substitutions are logged in the delivery report per the spec.
- Opus 4.8 and other Anthropic models are BUILD-TIME only (Claude Code doing the build). Nothing Anthropic ships inside the skill's runtime files.

**Build gate:** `scripts/guard-no-anthropic-runtime.py`
- Runs in the repo QC pipeline (same gate family as the existing G-gates) on every merge touching the podcast skill.
- Scans every SHIPPED runtime file of the skill (skill markdown, prompts, `.py`, `.sh`, `.json`, `.yaml`, dashboard source) for: `claude-` model ids, `anthropic` (provider slug, package import, or API host), `us.anthropic`, `@anthropic-ai`, `ANTHROPIC_API_KEY`, and `api.anthropic.com`.
- Exit non-zero with the offending file and line = BUILD FAILS, no merge. Allowlist file `config/anthropic-guard-allow.json` exists only for documentation files explicitly marked non-runtime; the runtime directories accept no allowlist entries.
- Companion check in the same script: asserts the routing config's `content` list is non-empty, contains no denied ids, and that `thinking: high` is set only on Kimi 2.6 / GLM 5.2 entries (Flash Lite runs default thinking — paying for high reasoning on the fallback is its own small furnace).

---

## 6. GUARDRAIL 6 — BOUNDED CRONS AND POLLERS (NO HEARTBEAT, CLEAN CHURN)

**Inventory rule: this skill ships with exactly ONE recurring job per client.**

| Recurring job | Cadence | Cost bound |
|---|---|---|
| `podcast-smoke-test.py` | Once daily, 6:00 AM client timezone, with a per-client random jitter of up to 15 minutes (stops a fleet-wide provider stampede) | ≤ $0.01/day (Guardrail 1) |

Explicitly FORBIDDEN (enforced, not advised):
- No heartbeat entry for this skill, ever. The skill must not be added to any agent heartbeat list.
- No standalone credit-out queue poller. The queue is examined at exactly two moments: (a) inside the daily smoke-test run — age check (auto-drop at `queue_max_hold_days = 60` with an aged-out founder notice through dedup) and drain trigger when a previously FAILED service flips to PASS; (b) event-driven, when an operator/founder marks credits restored. Zero extra crons.
- No per-job watchers. A held job is a JSON record, not a process.
- No dashboard-driven computation (Guardrail 2). Dashboard views trigger nothing.

In-run polling bounds (these are loops inside one episode run, not crons):
- Kie.ai async image job: poll status with backoff `polling.kie_backoff_schedule = [5,10,20,40,60]` seconds (then stay at 60s), total timeout `polling.kie_poll_timeout_seconds = 600`. On timeout: counts as one failed attempt against `image_gen_attempts_max = 3`, then the episode holds and alerts (deduped). Never poll faster than 5s, never poll forever.
- Fish Audio synthesis: `tts_synth_attempts_max = 2` per segment; segment-join via ffmpeg is local and free.
- Podbean / GoHighLevel (Convert and Flow) calls: bounded retries (3, exponential backoff), no polling loops.

**Cron audit gate:** `scripts/guard-cron-inventory.py`
- Runs at provisioning time and inside the repo QC gate. Asserts: per client, the number of crons matching this skill's namespace is exactly 1; its schedule parses to once daily; its delivery mode does not announce into the client chat (pass `--no-deliver` on creation — the known CLI drift defaults `cron add --command` to announce and spams the chat).
- Fails loudly if any second podcast cron, heartbeat entry, or sub-daily schedule is found.

**Churn cleanup:** `scripts/revoke-podcast-client.sh <client>`
- One command run when a client leaves: removes the client's smoke-test cron, disables/removes the inbound webhook mapping, revokes dashboard access at Cloudflare (per the brief's revocation path), marks any queued jobs `aged_out` with a founder notice, and archives the client's `state/` directory. A churned client must leave ZERO recurring jobs behind — an orphaned cron on a dead client is the purest furnace there is.
- `guard-cron-inventory.py --sweep` doubles as the fleet check: any podcast cron belonging to a client not in the active roster is reported.

---

## 7. GUARDRAIL 7 — ALERT DEDUP (NO FOUNDER STORMS)

**Script:** `scripts/alert-dedup.py` — the ONLY path to the founder's alert channel for this skill. Pipeline code never sends Telegram directly (and always through the OpenClaw gateway, never around it).

Mechanics:
- Every alert carries a key: `client + service + failure_class` (e.g. `stbob + fish_audio + insufficient_credits`).
- State in `state/alerts.json`: `{key: {first_seen, last_sent, count, affected_episodes: []}}`.
- **First occurrence:** send immediately, including how many jobs are affected ("Fish Audio out of credits. 1 episode queued.").
- **Repeat within the window** (`alerts.dedup_window_hours = 6`): suppressed; the counter and affected-episode list update in place. So a downed Fish Audio with 20 queued jobs produces ONE alert, not 20.
- **Window expiry while still failing:** send one UPDATED digest ("still down, now 14 episodes queued, oldest 2 days").
- **Recovery:** one recovery message when the smoke test flips the service back to PASS and the queue drains ("Fish Audio restored, 14 queued episodes resuming"), then the key clears.
- **Global storm cap:** `alerts.max_founder_alerts_per_client_per_day = 4`; beyond that, everything collapses into a single end-of-day digest per client. Exception: QC three-strike notices and `cost_hold` notices always send (they are decision requests, not status), but they still dedup per episode — one message per episode per event, never repeats.
- Aged-out (60-day) drops, daily-cap deferrals, and soft-ceiling warnings are digest-class by default.

---

## 8. CONSOLIDATED CONFIG BLOCK (single source, per-client overridable)

```yaml
podcast_engine:
  limits:
    per_episode_cost_usd_soft: 2.50
    per_episode_cost_usd_hard: 5.00
    per_client_daily_cost_usd_hard: 15.00
    per_client_daily_episode_cap: 3
    llm_tokens_per_episode_hard: 400000
    llm_max_output_tokens_per_call: 8000
    web_research_calls_per_episode: 12
    web_research_bonus_on_fabrication_fail: 4
    qc_max_attempts: 3
    image_gen_attempts_max: 3
    tts_synth_attempts_max: 2
    queue_max_hold_days: 60
  polling:
    kie_backoff_schedule: [5, 10, 20, 40, 60]
    kie_poll_timeout_seconds: 600
    dashboard_min_refresh_seconds: 60
  smoke_test:
    cron_local_time: "06:00"
    jitter_minutes: 15
    max_cost_usd: 0.01
  alerts:
    dedup_window_hours: 6
    max_founder_alerts_per_client_per_day: 4
  models:
    content: [ollama-cloud/kimi-2.6, ollama-cloud/glm-5.2, openrouter/<kimi-eq>, openrouter/<glm-eq>, gemini-3.1-flash-lite]
    qc_judge: [gemini-3.1-flash-lite, ollama-cloud/glm-5.2]
    deny_patterns: [claude, anthropic, us.anthropic, opus, sonnet, haiku]
```

## 9. SCRIPT MANIFEST AND ENFORCEMENT MATRIX

| Script | Enforcement point | Fails/blocks when |
|---|---|---|
| `podcast-smoke-test.py` | Daily cron (the only cron) | Provider FAIL → deduped alert; own cost > $0.01 → operator canary alert |
| `podcast-cost-ledger.py` | Wrapper around every billable call; stage boundaries | Hard ceilings, daily caps, token budget, research-call cap |
| `podcast-episode-state.py` | Every stage transition; dashboard's only data source | Missing record = dashboard shows unknown, never recomputes |
| `qc-attempt-gate.py` | Before each QC revision cycle | Attempt > 3; non-targeted retry; research re-run without a fabrication failure |
| `qc-tier1-mechanical.py` | QC Step 9, before any LLM judging | Any Tier 1 mechanical check, at $0.00 |
| `guard-no-anthropic-runtime.py` | Repo QC gate on merge; provisioning | Any Anthropic model id/provider/env key/host in shipped runtime or dashboard |
| `guard-cron-inventory.py` | Provisioning; repo QC gate; `--sweep` fleet audit | >1 podcast cron per client; sub-daily cadence; heartbeat entry; orphaned churn crons; announce-mode cron |
| `alert-dedup.py` | Sole founder-alert path | Duplicate alerts within window; >4 alerts/client/day collapse to digest |
| `revoke-podcast-client.sh` | Client churn | Leaves zero crons, zero webhook, zero dashboard access behind |

**Worst-case daily spend with all guardrails active (per client):** smoke test $0.01 + 3 episodes × $5.00 hard ceiling = $15.01, bounded by the $15.00 daily cap forcing the third episode's tail into hold. Idle client (no submissions): $0.01/day. That is the number this design exists to guarantee.
