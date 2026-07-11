# How to use the ZHC Early Warning System (Skill 60)

Operator-facing quick start. "ZHC" = Zero Human Company; spelled out here once and
never again below. The design contract is `SKILL.md`, the ten-signal reference is
`docs/SIGNAL-CATALOG.md`, and the failure runbook is `REPAIRS.md`. This document is
the friendly walkthrough; it never overrides those.

## What this is

A deterministic, zero-model-call sentinel that runs on every OpenClaw box and tells
YOU — the operator, never the client — the moment something on that box breaks or
drifts. It calls no model, ever: every check is a file read, a stat, a diff, or
arithmetic. It pins a per-box baseline the first time it installs, then watches ten
failure classes the fleet has actually suffered (silent model swaps, a runtime
fallback the config doesn't show, a compaction misconfig that will crash the box, a
safety cap raised with no sign-off, heartbeat/idle token burn, a root-owned config
write, a dark gateway or dashboard, a secret shape leaked into a log, a stale skills
downgrade, and a client-spamming announce cron). Every alert that touches config
carries a one-line revert command, ready to paste. It never changes a client box by
default — alert-only, everywhere, unless you have explicitly opted a single box in
(see "Caps are alert-only by default" below).

## The cadence: one cron, one aggregator

- **The box-local tick** — every 15 minutes, on every box, cron-driven, zero model
  calls, CPU-cheap only. This is the ONE cron this skill owns per box; nothing else
  runs on a shorter cycle.
- **The operator-box aggregator** — runs hourly, ONLY on your operator box. It pulls
  the tiny per-box digests over the fleet's existing sanctioned access paths (never
  config contents, never another box's credentials) and rolls them into one fleet
  digest. If a box has produced no fresh tick for two consecutive aggregator cycles,
  that box is "sentinel dark" and the aggregator raises a P1 on your behalf — see
  `REPAIRS.md` item 1.

## The companion verbs

Every command below routes through the one sanctioned entry point, run from the
skill directory:

```
bash 60-zhc-early-warning-system/ews-entry.sh tick
bash 60-zhc-early-warning-system/ews-entry.sh audit
bash 60-zhc-early-warning-system/ews-entry.sh install
bash 60-zhc-early-warning-system/ews-entry.sh verify
bash 60-zhc-early-warning-system/ews-entry.sh troubleshoot
bash 60-zhc-early-warning-system/ews-entry.sh approve-baseline --key <path>
bash 60-zhc-early-warning-system/ews-entry.sh revert --to <utc-ts>
bash 60-zhc-early-warning-system/ews-entry.sh cadence
bash 60-zhc-early-warning-system/ews-entry.sh fleet        # operator box only
```

- **`tick`** — runs one sentinel pass on this box right now, outside the cron. Use it
  after an install, after a manual config edit, or any time you want a fresh read
  without waiting up to 15 minutes.
- **`audit`** — read-only. Prints a diff table of the live config against the pinned
  baseline: nothing is written, nothing is alerted, nothing changes. Your first move
  whenever you want to *look* before deciding whether to act.
- **`install`** — one-time per box. Pins the baseline (`~/.openclaw/ews/baseline.json`,
  box user, 0600), registers the 15-minute cron, and creates the SQLite-WAL ledger.
  Safe to re-run; it never overwrites an existing baseline without `approve-baseline`.
- **`verify`** — the independent, failable drill battery (`verify.sh`). Every script's
  self-test plus an end-to-end `[DRILL]` message through the REAL alert path to your
  operator account, so you know the alert actually reaches you and not just that the
  code ran. Run this after every install and after any change to this skill.
- **`troubleshoot`** — the decision tree in `REPAIRS.md`, runnable. It inspects the box
  (cron present? gateway reachable? config ownership? ledger openable?) and prints
  which failure mode you're looking at plus the exact next command — it never takes
  a destructive action on its own.
- **`approve-baseline --key <path>`** — stamps an intended change so the sentinel stops
  alerting on it. See "Never-silently-raise" below.
- **`revert --to <utc-ts>`** — restores the config from the snapshot nearest that
  timestamp, writing as the box user (never root), then reads the file back to
  confirm the write took. Every P1 alert prints the exact revert line pre-filled with
  the right timestamp, so this is normally a copy-paste, not a lookup.
- **`cadence`** — shows the current self-update cadence (weekly, pinned, D8) and the
  recommender's advisory note, if any. It never changes the cadence itself; only an
  explicit operator `cadence set ...` writes a new history entry.
- **`fleet`** — operator box only. Runs the hourly aggregator pass on demand and
  prints the rolled-up fleet digest (dead-man boxes, open P1/P2/P3 counts per box,
  furnace notes). Running this on a client box is a usage error, by design.

## How to read an alert

Every alert you receive is plain language, in this shape:

```
[P1] box-example-01  S4 cap-raise  agents.defaults.subagents.maxConcurrent
measured: 64  baseline: 16  (unstamped raise)
revert: bash 60-zhc-early-warning-system/ews-entry.sh revert --to 2026-07-10T14:32:00Z
```

Every line in that shape is load-bearing:

- **Severity** — P1 (act now), P2 (drift worth a look), P3 (informational, e.g. a
  snapshot-pruning note). Only P1 bypasses the daily alert batch and only P1
  escalates to Rescue Rangers if it sits unacknowledged for 30 minutes.
- **Box name + signal + key path** — which box, which of the ten signals (S1-S10, see
  `docs/SIGNAL-CATALOG.md`), and the exact dot-path into `openclaw.json` that moved,
  when the signal is config-shaped.
- **Class** — model / cap / furnace / access / cron / compaction / config-write /
  gateway / secret / skills — so you know the flavor of the problem at a glance.
  Where a secret is involved, the class is all you ever get; the value is never
  printed, echoed, or reproduced, not even partially.
- **Measured vs threshold (or baseline)** — the actual number or value next to the
  number or value it drifted from, so you can see the size of the change without
  opening a file.
- **The revert line** — a ready-to-run command, already filled in with the right
  snapshot timestamp. You are never sent hunting for what to paste.

## The never-silently-raise rule

Nothing on a box's safety caps (`agents.defaults.maxConcurrent`,
`subagents.maxConcurrent`, `maxChildrenPerAgent`, `maxSpawnDepth`, the Telegram
`allowFrom`/`dmPolicy`/`groupPolicy` access keys) is allowed to move upward without
your explicit sign-off. If one of these keys is raised and there is no matching
approval stamp in the ledger, the sentinel fires a P1 with a working revert line —
every time, no exceptions. When the raise really was intentional (you widened a
concurrency ceiling on purpose, for instance), stamp it BEFORE or immediately after
you make the change:

```
bash 60-zhc-early-warning-system/ews-entry.sh approve-baseline --key agents.defaults.subagents.maxConcurrent
```

This records the new value's hash in the ledger's `baseline_stamps` table with your
operator identity and a timestamp. The next tick sees the stamp, treats the raise as
sanctioned, and goes quiet on that key going forward — the baseline itself is never
silently rewritten to match reality; it only ever moves through this stamp.

## Caps are alert-only by default

`thresholds.json` locks `caps.enforce_caps_default = false` fleet-wide (decision D2).
That means the sentinel NEVER auto-reverts a cap raise on its own, on any box, ever,
by default — it alerts and hands you the revert command, and you decide. Auto-revert
(`enforce_caps`) exists in code but ships OFF everywhere. Opting a single box into it
is a documented, per-box, operator-initiated choice — it is never a fleet-wide
setting and it is never flipped by an automated rollout. If you want a specific box
to self-revert an unstamped cap raise, that is a conversation with the operator
first, then a scoped per-box config entry, never a default change to this skill.

## The D5 context rule

Running low on context is normal and NOT your problem most of the time. When a box's
live usage crosses 70% of its effective context ceiling, that box's OWN agent gets a
note; at 85% it gets a handoff instruction (memory flush / compaction). Both of those
stay local to the box — you are not paged for a box quietly managing its own context.
You ARE paged, as a P1, for exactly one case: a BROKEN configuration that guarantees
a crash no matter what the agent does — the effective ceiling computes to zero or
negative, or `softThresholdTokens` is set at or above the box's own context window.
That is not a "running low" note; it is a "this box cannot function until you fix the
number" alert, because only you can repair a config value.

**One narrow, approved exception — your OWN box only.** On the operator box you are
reading this on (never a client box), an 85%-handoff finding ALSO sends you one
plain-language self-notice — "your assistant's working memory is N% full, it will
wrap up cleanly and start a fresh session" — because on that one box the finding's
subject and the reader are the same person: it is your own session's health, not an
ops alert about someone else's box. It is gated in code on that box's own role
being `operator`, not just a config flag, so it structurally cannot fire on a client
box; turn it off with `context.operator_self_notify: false` in `thresholds.json` if
you don't want it. The self-notice the box's OWN agent gets (the normal D5 case
above) is readable with `bash ews-entry.sh notices` (add `--peek` to read without
consuming it).

## The D9 furnace/billing framing

An idle-burn alert always tells you what kind of waste you're looking at, because the
same wasted tokens mean different things depending on how the box's provider bills:

- **Subscription / usage-allowance providers** (Ollama Cloud and other `:cloud`
  tiers) — wasted tokens consume the session/weekly USAGE ALLOWANCE, not dollars.
  The alert says "consuming usage allowance" because the risk is throttling or a
  hard stop mid-task, not an invoice line.
- **Pay-per-token / metered providers** (OpenRouter, direct paid APIs) — wasted
  tokens are DIRECT MONEY. The alert says "spending metered dollars."

On-box detection runs first, always; the read-only provider usage/balance check only
fires when the on-box signal already flagged something, it never mutates a provider
account, and it never prints a credential value — only usage-consumed vs
balance-remaining, by posture.

## Snapshots and the weekly cadence

- **D7 — retention**: every config write is snapshotted. The sentinel keeps the
  LARGER of 60 snapshots or 45 days of history; pruning older snapshots is a P3 line
  in the digest, never silent, never a surprise.
- **D8 — cadence, weekly, pinned**: this skill's own self-update check starts weekly
  and stays weekly. The recommender may print an advisory note in the digest (for
  example, "drift velocity suggests monthly would be safe"), but the default cadence
  never changes itself. Only an explicit `cadence set ...` from you writes a new
  history entry.

## Canary, then hold

The full install plus the drill battery is proven on your OWN operator box first.
Fleet rollout is held at repo-only until you give the explicit word — a repo merge is
not a roll. Do not install this on a client box before it has passed `verify` clean
on your box; the system obeys the same discipline it enforces on everything else.
