# RR-W4-EWS-RR005-RR016 — Repair Evidence (ONB ONLY)

Branch: `rr/w4-ews-rr005-rr016` off ONB `origin/main` base `15d6178890e0012c92768829f487fd454e93e03c`.
Scope: Skill-60 EWS files + two new batteries + frozen evidence. No FLEET writes. No CC writes.

## Task A — RR-005 (P0): failed EWS escalations stay pending

Source: `60-zhc-early-warning-system/scripts/ews_alert.py` (`escalate`), `60-zhc-early-warning-system/scripts/ews_ledger.py`.
Transport reused: `scripts/lib/rescue_admission.py` (canonical client, untouched — zero diff). No second send implementation.

What changed:
- `ews_ledger.py`: new `escalation_state` table (`operation_id` PRIMARY KEY, `source/box/signal/event_id/dedup_key`, `attempt`, `next_attempt_at`, `last_error`, `receipt_status/receipt_ticket_id/receipt_digest`, `outcome`, `updated_at`) + `get_escalation` / `record_escalation_attempt` / `reconcile_escalation`. Attempt counter increments per resend; `next_attempt_at` set on retryable uncertainty; stored separately from `events.ack_state` (incident resolution).
- `ews_alert.py`: dry-run branch moved BEFORE every ledger mutation and network action (empty sweep returns early; non-empty sweep returns `dry_run` items with zero writes, zero POST, zero group message). Each stale event reconciles its stable operation id (`_stable_operation_id`, same inputs as the client so intake folds replays) before resending: an already-accepted row returns the stored receipt instead of re-posting, so a response lost after a real admission recovers the same ticket. Only a validated durable receipt (`admitted`/`replay` via `C.admission_is_ack_eligible`) marks the event `escalated`. Outcome vocabulary per item: `attempted` (transport/429/5xx/timeout/undetermined, retryable, `next_attempt_at` set), `accepted` (receipt), `deferred` (owned setup fault `no_enrollment`/`client_unavailable`, retryable after repair), `failed` (terminal policy `refused`), `dry_run`. `escalate_exit_code` returns 1 on `attempted`/`failed`, else 0; CLI `escalate` exits nonzero on operational failure.
- Missing config stays an owned recoverable setup fault (`client_unavailable`, event OPEN, row with `last_error`).

Battery: `tests/unit/rr005_escalation_pending.test.py` — 31 checks PASS on fix, exit 0:
rerun-failure (OPEN + attempt/next_attempt_at/last_error row + exit 1, retry accepts same op); no-target retryable; dryrun zero mutations/network + exit 0; lost-response recovery reuses stable operation id and same ticket; malformed-200/401(policy refusal, outcome failed)/429/timeout never consume; missing-config deferred; refusal nonzero exit.

Discrimination: same battery on clean base errors (`no such table: escalation_state`), exit 1 — new contract absent on base.

## Task B — RR-016 (P1): dead sentinel detected even when old file readable

Source: `60-zhc-early-warning-system/scripts/ews_fleet.py` (ingest/cycle/health), digest producer `60-zhc-early-warning-system/scripts/ews_companion.sh`.

What changed:
- `cmd_ingest` persists `collector_seen_at` (this successful read) separately from `sentinel_tick_at` (what the sentinel proved) and `last_verified_progress_at` (newest advancing tick). Successful reads stamp ONLY the collector field. Boot/sequence provenance (`boot_id`/`tick_seq` + `last_boot_id`/`last_tick_seq` snapshots) tracked where the digest provides them; `last_tick_ts` kept as compat alias.
- `_sentinel_health` decides from TICK AGE + PROGRESS across real-time intervals (horizon = `dead_man_cycles × cycle_minutes` from `thresholds.json`): HEALTHY (fresh), STALE (valid but older than horizon), UNKNOWN (missing/malformed/naive timestamp), DEGRADED (future beyond 5-min skew allowance, tick regression, sequence regression, boot-id change). Collector silence for a full horizon is STALE. `collector_seen_at` never feeds the verdict.
- `cmd_cycle` fires dead-man from that verdict, dedups by box + stale episode (`deadman|<box>|<tick>`, legacy box-only key kept for the missing-tick path), one admission per episode with same-episode re-observations journaled as `deadman_episode_seen` (no repost). Recovery requires a new verified tick (clears dark, advances verified epoch). Recovery work goes through the canonical admission stub path with durable receipts (event acked only on `admitted`/`replay`).
- `cmd_digest` exposes `sentinel_tick_at/collector_seen_at/last_verified_progress_at/sentinel_health`. Companion `--json` digest adds `sentinel_tick_at` (+ compat `last_tick_ts`).

Battery: `tests/unit/rr016_tick_health.test.py` — 15 checks PASS on fix, exit 0:
old digest stale through re-collections (1 incident/1 post per episode); fresh advancing healthy, no post; collector outage dark; sentinel-only outage dark with collector/tick separated; reboot DEGRADED; malformed UNKNOWN then recovery on new tick; future skew DEGRADED; rapid cycles one incident then recoverable; missing tick UNKNOWN.

Discrimination: same battery on clean base: 5 ok / 10 FAIL, exit 1 (base re-collects ancient tick as healthy, no separation/validation/episode logic).

## Regression + scope controls

- `ews_ledger --self-test` exit 0, `ews_common --self-test` exit 0, `ews_alert --self-test` exit 0, `ews_fleet --self-test` exit 0, `rescue_admission --self-test` exit 0 (39 checks), `ews_companion --self-test` exit 0.
- Pre-existing `tests/rescue/RR-015/test_rescue_admission_client.py`: exit 1 with exactly one failing assertion, `dead-man event escalated on receipt`. Cause: that battery ingests an ANCIENT tick (`2000-01-01`) and queries the legacy box-only dedup key `deadman|box-dm-one`; under the RR-016 repair the ancient tick is correctly STALE and the event is keyed per episode (`deadman|box-dm-one|2000-01-01T00:00:00+00:00`) — verified: exactly ONE admission post, event `escalated` under the episode key. Required RR-015-owner battery update: query `dedup_key LIKE 'deadman|box-dm-one%'`. All other RR-015 assertions pass (66 ok). No RR-015 source behavior regressed (admission paths, receipt gating, journaling unchanged).
- `git diff --name-only base..branch`: `60-zhc-early-warning-system/scripts/ews_alert.py`, `ews_companion.sh`, `ews_fleet.py`, `ews_ledger.py`, `tests/unit/rr005_escalation_pending.test.py`, `tests/unit/rr016_tick_health.test.py`, `run/w4/ews-lane/rr005-rr016/*`. Untouched: `scripts/lib/rescue_admission.py` (zero diff), no `box_enrolled`/`box_enrollment_reason` carry hunks, none of `65-rescue-receiver/rescue-poll.sh`, `wire.sh`, `update-skills`, `skill-version.txt`, `CHANGELOG.md`, `SKILL.md`, `shared-utils/rescue-supervise.py`, `tests/rescue/RR-025/*`, `tests/rescue/RR-026/*`, `.github/workflows/rescue-rangers-rr025-rr026-gates.yml`, `tests/unit/rr027-*`, `tests/unit/update-skills-*`.
- Headless only. No secret value printed. No holding-pen writes. No merge/tag/publish.

Full log: `run/w4/ews-lane/rr005-rr016/QC-BATTERY.out`.
