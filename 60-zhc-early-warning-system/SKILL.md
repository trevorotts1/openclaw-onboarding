---
name: zhc-early-warning-system
description: The fleet Early Warning System, a deterministic, zero-model-call sentinel that runs on every OpenClaw box and tells the OPERATOR (never the client) the moment something breaks or drifts. It pins a per-box baseline, tails the native config-audit event stream, and detects ten failure classes the fleet has actually suffered - a silent model or paid-provider downgrade, a runtime fallback the config never shows, a subtractive compaction misconfig that will crash the box, a safety-cap raised without sign-off, heartbeat/idle furnace token-burn in BOTH subscription and metered billing, a root-owned config write that freezes the gateway, a dark dashboard or tunnel, a secret shape leaked into a transcript, a stale skills downgrade, and a client-spamming announce cron. Every config write is snapshotted with a one-line revert command placed in the operator's hand; it never auto-changes a client box by default (alert-only fleet-wide). One skill directory holds BOTH the per-box sentinel and the companion that can audit, install, verify, and troubleshoot the sentinel on any box, plus the operator-box aggregator with a dead-man switch for boxes too broken to self-report. Zero model calls, one cron, CPU-cheap, operator-verbose and client-silent by construction. Trigger with "audit the early warning system", "why did the model switch", "install the sentinel", "did a safety cap get raised", "check for idle token burn", "verify the early warning system", "run the fleet digest", or "revert the last config change".
version: 0.1.0
---

# ZHC Early Warning System (Skill 60)

"ZHC" = Zero Human Company. Spelled out once; the skill's surfaces never use the
acronym unprompted. This skill watches the MACHINE, not the work: it is a
deterministic sentinel on every fleet box that makes "something changed" a
computable fact and hands the operator a revert command at the moment of the
alert. It is not a model router, not a config manager, not a client-facing
anything, and (by default) not an auto-healer.

> The fleet's failure-discovery mechanism today is: the operator notices, or the
> client notices first. Both are too late, and the second one breaks move-in-
> silence by definition. This system moves discovery to minutes, silently, to the
> operator only.

## The binding doctrine (every code path honors these)

1. ZERO model calls, ever, anywhere in the sentinel. Every check is deterministic
   file / stat / diff / arithmetic work. The heartbeat token-burn trap does not
   apply because there is no model turn to bill. `guard-no-anthropic-runtime.py`
   still ships and rides the merge gate, statically, because a future contributor
   might be tempted to add an LLM-judged anomaly check. They must not: deterministic
   or it does not ship.
2. OPERATOR-ONLY, CLIENT-SILENT, STRUCTURALLY. Every alert routes through the box's
   OWN OpenClaw gateway to the OPERATOR account, with `deliver:false` semantics on
   any agent-loop injected event. The client's bot, chats, and Telegram account are
   never recipients. Move in silence toward clients is structural here, not policy.
3. NEVER print, echo, grep, or paste a secret VALUE. Credentials are reported by
   LABEL and POSTURE only (SET / NOT SET / signed-in / signed-out). A leaked-secret
   finding reports file:line and CLASS only; the value is never reproduced, not even
   partially.
4. CONFIG WRITES RUN AS THE BOX USER, never root (`node` on VPS, wrapped in
   `docker exec -u node`). A root-owned config freezes the gateway - the exact S6
   incident this system exists to catch. Every config-touching path refuses to run
   as root.
5. NEVER commingle clients. The sentinel reads only its OWN box; it never reads or
   probes another client's box, account, or credentials. The aggregator collects
   tiny digests over the fleet's existing sanctioned access paths, never config
   contents.
6. NEVER silently change a client's chosen model (S1/S2 alert; they never act -
   client model choice is sovereign) and NEVER auto-change a client box by default:
   safety-cap enforcement is ALERT-ONLY fleet-wide (D2). Auto-revert (`enforce_caps`)
   exists as code but defaults OFF everywhere; it is a per-box opt-in only.
7. NOTHING Anthropic-family runs at runtime. The sentinel calls no model at all, so
   the rule is satisfied vacuously at runtime AND enforced statically over every
   shipped file. NEVER ship a `claude-*` / `anthropic/*` / `us.anthropic.*` runtime
   identifier; the signature catalog names those families only as deny data.
8. CANARY, THEN HOLD. The full install plus drill battery is proven on the OPERATOR
   box first; fleet rollout is HELD at repo-only until the operator's explicit word.
   A repo merge is not a roll. The system obeys the laws it enforces.

## Reuse before rebuild (this skill integrates, it does not reinvent)

| Fleet asset reused | What Skill 60 does with it |
|---|---|
| Native `~/.openclaw/logs/config-audit.jsonl` | The sentinel TAILS this event stream from a persisted byte offset; it does not invent a config watcher. Every `config.write` row already carries `ts`, `argv`, `pid`, `ppid`, `previousHash`, `nextHash`, `existsBefore`. |
| Session `*.trajectory.jsonl` (`modelId`/`provider` per event) | Ground truth for S2 runtime-fallback detection, independent of what the config claims. |
| Skill 58 `alert-dedup.py` pattern | Operator-only gateway send, per-class dedup windows, storm cap. Reused, not rebuilt (`ews_alert.py`). |
| Skill 58 `guard-cron-inventory.py` pattern | One-cron / no-heartbeat / no-poller inventory law and the cadence-bound math. |
| Skill 59 four-scanner merge-gate family | `guard-no-anthropic-runtime.py`, `scan-no-secrets.sh`, `scan-no-client-identifiers.sh`, `scan-no-json-exports.sh`, same 0/1/2/3/4 exit contract and value-free doctrine. |
| `scripts/skill-content-hash.sh` (repo root) | Auto-picks up `60-*` as a hashed skill dir; the update stamp gate covers Skill 60 with no extra wiring. Also the algorithm S9 uses to detect local skills drift / stale downgrade. |
| Skill 59 single-writer ledger pattern | One SQLite-WAL writer (`ews_ledger.py`); every other script goes through it. |

## The ten detection signals (full catalog in docs/SIGNAL-CATALOG.md)

| # | Signal | Source of truth | Default severity |
|---|---|---|---|
| S1 | Model / provider config drift vs pinned baseline | `openclaw.json` model keys, diffed each tick | P2, P1 on a client box for a `claude-*` / `anthropic/*` / paid-tier change |
| S2 | Runtime fallback (ground truth) | trajectory `modelId`/`provider` per event | P2, P1 for out-of-allowlist paid/Anthropic-family on a client box |
| S3 | Context vs compaction | live usage vs effective ceiling (contextWindow minus SUBTRACTIVE `softThresholdTokens`) | broken-config = P1 to OPERATOR; running-low = to the BOX'S OWN agent (D5), not the operator |
| S4 | Safety-cap raise (never-silently) | enumerated cap keys vs baseline + approval stamp | P1 on an unstamped RAISE; ALERT-ONLY (D2), emits a revert |
| S5 | Furnace / idle-burn (hybrid, billing-aware) | heartbeat cadence/model, cron inventory, idle paid-model activity, per-box BILLING MODEL | P1 idle burn; framed as usage-consumed vs dollars-spent per billing type (D9) |
| S6 | Config-write hygiene + reversibility | `config-audit.jsonl` tail + ownership stat | P1 root-owned; SNAPSHOT on every write |
| S7 | Surfaces dark (gateway / dashboard / tunnel) | local process/port probes + build marker | P1 gateway unreachable; dead-man covers a box that cannot speak |
| S8 | Secret leaked into transcript/log | new bytes scanned with the secret-CLASS detector | P1, value-free (file:line + class only) |
| S9 | Skills integrity drift / stale downgrade | installed tree hashed vs pinned manifest | P2 drift, P1 version regression |
| S10 | Cron / delivery drift | `cron` entries vs baseline | P2 new cron, P1 announce cron on a non-operator chat |

Two deliberate NON-signals, stated so nobody adds them later: (a) the sentinel
never reads another client's box, account, or credentials; (b) the sentinel never
evaluates CONTENT quality - that is the Quality Control protocol's job.

## Single-writer state vocabulary

`~/.openclaw/ews/ews.db` (VPS `/data/.openclaw/ews/ews.db`), SQLite WAL, written
ONLY by `ews_ledger.py`. Tables: `events` (signal, severity, key path or file:line,
class, tick ts, ack state), `offsets` (config-audit byte offset, per-log scan
offsets so S8 reads only NEW bytes), `snapshots` (path, ts, sha256, trigger event
id, revert command text), `baseline_stamps` (S4 approval records), `digests`
(what was sent when, for dedup). The pinned baseline is `~/.openclaw/ews/baseline.json`
(0600, box user); reality is diffed against it and never silently becomes it.

## Enforcement pointers (a rule without a gate is a suggestion)

| Rule (from the spec) | The script/gate that enforces it |
|---|---|
| Never silently raise a safety limit | `ews_baseline.py` approval stamp + `ews_sentinel.py` S4 (unstamped raise = P1) |
| Configuration changes are backed up and reversible | `ews_snapshot.py` (snapshot on every write) + `ews_revert.py` (restore as box user, byte read-back) |
| Model / fallback switches are detected | `ews_sentinel.py` S1 (config) + S2 (trajectory ground truth) |
| A handoff is requested while context remains | `ews_sentinel.py` S3 (70/85% thresholds; running-low to the box's own agent, D5) |
| Operator-only, never client-facing | `ews_alert.py` (gateway-only, operator account, dedup, `deliver:false`) |
| Zero Anthropic at runtime | vacuous at runtime + `guard-no-anthropic-runtime.py` at the merge gate |
| No secret value ever printed | `scan-no-secrets.sh` class detector reused everywhere; alerts carry class only |
| Config as the box user, never root | root-refusal in every config-touching path; `docker exec -u node` on VPS |
| One cron, zero model calls | `guard-cron-inventory.py` pattern; `thresholds.json` owns the 15-minute cadence |
| Weekly cadence, pinned | `ews_cadence.py` (recommends only; default never self-changes, D8) |

## Entry and verify

    bash 60-zhc-early-warning-system/ews-entry.sh tick            # one sentinel tick
    bash 60-zhc-early-warning-system/ews-entry.sh audit           # read-only diff table
    bash 60-zhc-early-warning-system/ews-entry.sh --self-test     # every script self-test
    bash 60-zhc-early-warning-system/verify.sh                    # drill battery (failable proof)

The sentinel tick and every companion command route through the ONE sanctioned
entry (`ews-entry.sh`). Every script implements `--self-test` (deterministic, no
network, no model). `verify.sh` is the independent, failable end-to-end proof,
including a `[DRILL]` message through the REAL alert path to the operator account.
