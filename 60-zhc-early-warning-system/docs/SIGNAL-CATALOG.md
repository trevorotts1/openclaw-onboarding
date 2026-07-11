# Signal catalog (Skill 60) -- the living reference

The full detail behind the ten-signal summary table in `SKILL.md`. This is the
catalog referenced there ("full catalog in docs/SIGNAL-CATALOG.md"); if the two ever
disagree, this file is the detailed source and `SKILL.md`'s table is the digest.

Every signal is deterministic: a file read, a stat, a diff against a pinned baseline,
or arithmetic. Zero model calls, anywhere, ever (see `SKILL.md` doctrine item 1).

## Severities

- **P1** -- act now. Bypasses the daily alert batch cap; escalates to the Rescue
  Rangers channel if unacknowledged for 30 minutes (D4); a dead-man P1 (sentinel
  dark) escalates immediately.
- **P2** -- drift worth a look. Batched with the day's other P2/P3 alerts up to the
  per-box daily cap (4/day), except that a P1 always bypasses the batch.
- **P3** -- informational. Digest-line only (for example, a snapshot-pruning note).

## The ten signals

| # | Signal | Source of truth on the box | Threshold | Action |
|---|---|---|---|---|
| S1 | Model / provider config drift vs pinned baseline | `openclaw.json` model keys (`agents.defaults.model.primary`, `.model.fallbacks`, `.models`, `.subagents.model.primary`, `.subagents.model.fallbacks` -- the exact paths in `config/monitored-keys.json`), diffed each tick against `baseline.json` and on every `config.write` audit event | Any change = P2; a `claude-*` / `anthropic/*` / `us.anthropic.*` family id or a paid-tier marker (`:cloud` suffix, `openrouter`/`openai`/other metered slug from `config/signatures.json`) on a CLIENT box = P1 | Alert only -- client model choice is sovereign; the sentinel never acts. Operator confirms or reverts (`revert --to <ts>`). |
| S2 | Runtime fallback (ground truth, independent of what the config claims) | Session `*.trajectory.jsonl` per-event `provider` / `modelId` fields | An event's `provider`/`modelId` outside `baseline.json:model_allowlist` = P2; an Anthropic-family or paid-tier id out-of-allowlist on a CLIENT box = P1 | Alert only. Compares REALITY (what actually ran) against the config's claim, so a fallback chain silently resolving to a different provider than the config shows is caught even when S1 sees no config diff. |
| S3 | Context vs compaction | Live usage vs the effective ceiling, `contextWindow - softThresholdTokens` (SUBTRACTIVE; see `agents.defaults.compaction.memoryFlush.softThresholdTokens` in `config/monitored-keys.json`). Live usage is computed by `_context_usage()` in `ews_sentinel.py` off the newest session `*.trajectory.jsonl`'s latest event (an OPEN QUESTION-flagged candidate field list, verify-first against the canary box; an opt-in `openclaw session status --json` CLI probe is the documented fallback, OFF by default) | 70% of ceiling = note; 85% = handoff instruction; ceiling `<= 0` OR `softThresholdTokens >= contextWindow` = broken-config | **D5 nuance**: running-low (the 70%/85% cases) routes to the BOX'S OWN AGENT (Lane 1 -- a self-notice written to `box-agent-notices.jsonl`, consumable via `ews-entry.sh notices`) so it self-handles (memory flush / handoff) -- the operator is never paged for a box managing its own context. The operator IS alerted, as a P1, ONLY for the broken-config case (a guaranteed crash regardless of usage) -- only the operator can repair the number. **NARROW APPROVED EXCEPTION (Lane 2, `context.operator_self_notify`, default true):** on the OPERATOR's OWN box ONLY, an `S3|handoff` finding ALSO sends the operator one deduped, plain-language self-notice ("your assistant's working memory is N% full...") -- gated structurally on that box's own ledger `role` meta being `"operator"` in `ews_alert.py route_finding`, never on the config flag alone, so it can never fire on a client box. |
| S4 | Safety-cap raise (never-silently) | Enumerated cap keys (`agents.defaults.maxConcurrent`, `subagents.maxConcurrent`, `subagents.maxChildrenPerAgent`, `subagents.maxSpawnDepth`, and the access keys `channels.telegram.accounts.default.allowFrom`/`.dmPolicy`/`.groupPolicy`) vs baseline, cross-checked against the ledger's `baseline_stamps` table | Any RAISE with no matching approval stamp = P1; a lower value = P3 | **ALERT-ONLY fleet-wide (D2)** -- emits a working revert command; never auto-reverts unless the box has an explicit, documented, per-box `enforce_caps` opt-in (never a fleet default). An intended raise is cleared with `approve-baseline --key <path>`, which stamps the new value's hash, never rewrites the baseline silently. |
| S5 | Furnace / idle-burn (hybrid, billing-aware) | Heartbeat cadence/model (`agents.defaults.heartbeat.every`/`.model`), the cron inventory, idle-window paid-model activity, and the box's own resolved provider BILLING MODEL (`config/billing-models.json`) | A cadence tightened below the fleet floor = P2; a heartbeat model resolving to a paid `:cloud` or metered tier = P2; idle-window paid-model activity above the idle-event floor = P1 | **D9 nuance**: framed by billing type, never just "tokens." Subscription/allowance providers (Ollama Cloud, other `:cloud` tiers) -- wasted tokens burn the session/weekly USAGE ALLOWANCE (framed as "consuming usage allowance"); pay-per-token/metered providers (OpenRouter, other metered slugs) -- wasted tokens are DIRECT MONEY (framed as "spending metered dollars"). On-box detection runs first; a READ-ONLY provider usage/balance check escalates only when on-box flags something, and it never mutates an account or prints a credential value. |
| S6 | Config-write hygiene + reversibility | `~/.openclaw/logs/config-audit.jsonl` tail (persisted byte offset; `ts`/`argv`/`pid`/`ppid`/`previousHash`/`nextHash`/`existsBefore` per row) + an ownership `stat()` on the written file | A root-owned write = P1; a write whose `argv` carries none of `config/signatures.json`'s `known_writer_argv_tokens` = P2 (unknown writer) | Every write is snapshotted regardless of severity (`snapshots` table, revert command text recorded at write time), so recovery is always a copy-paste, never a lookup. Config writes run as the box user everywhere in this skill's own code; a root-owned write always originates OUTSIDE the sentinel. |
| S7 | Surfaces dark (gateway / dashboard / tunnel) | Local process/port probes + a build marker check | Gateway unreachable = P1 | The aggregator's dead-man switch (two missed hourly cycles) covers a box too broken to self-report even this signal. Recovery is the platform-sanctioned restart in `REPAIRS.md` item 2 -- printed, never auto-executed. |
| S8 | Secret leaked into transcript/log | New bytes only (per-log scan offset in the `offsets` table, so S8 never re-scans old, already-clean content), run through the reused Skill 59 secret-CLASS detector (`scan-no-secrets.sh` class pin: `provider_sk\|caf_pit\|google_api\|aws_akid\|slack_token\|github_pat\|private_key\|jwt\|bearer_literal`) | Any class hit = P1 | Value-free by construction -- the finding is `file:line` + CLASS only; the matched value is never stored, printed, or reproduced, not even partially, anywhere in the alert or the ledger. |
| S9 | Skills integrity drift / stale downgrade | The installed skills tree, hashed with the same algorithm `scripts/skill-content-hash.sh` (repo root) uses, compared against the pinned manifest | A hash mismatch with no matching version bump = P2 (drift); an installed version older than the pinned manifest version = P1 (regression) | This is also the self-defense mechanism for `config/signatures.json` itself (see `REPAIRS.md` item 5) -- a box-local hand-edit of any file this skill ships changes the tree hash and trips S9 on the very next tick, by design. |
| S10 | Cron / delivery drift | The box's `cron` array vs baseline (id + delivery mode per entry) | A cron entry not in baseline = P2; a `delivery:"announce"` (or any non-`silent`/non-operator delivery) cron bound to a non-operator chat = P1 | This is the `--no-deliver` client-spam trap: a cron that was meant to stay silent to the operator but got wired to announce into a client-facing chat. Cleared the same way as S4 -- fix the cron, then `approve-baseline` once the inventory is what you intend. |

## Two deliberate non-signals

Stated so nobody adds them later (`SKILL.md` doctrine, `config/monitored-keys.json`
header comment):

1. **The sentinel never reads another client's box, account, or credentials.** Every
   signal above operates on the box it runs on and nothing else. The operator-box
   aggregator collects only the tiny per-box digests each box already produces, over
   the fleet's existing sanctioned access paths -- it never pulls a raw config, a
   trajectory file, or a credential from a remote box.
2. **The sentinel never evaluates CONTENT quality.** Whether a deliverable, a
   generated chapter, an ad set, or any other work product is GOOD is entirely out of
   scope here -- that judgment belongs to the Quality Control protocol, a separate
   system. Skill 60 watches the MACHINE (config, runtime provider truth, process
   health, secrets, skills integrity, cron), never the WORK.
