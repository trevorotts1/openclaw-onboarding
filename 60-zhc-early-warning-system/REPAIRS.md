# ZHC Early Warning System -- REPAIRS (known failure modes + decision tree)

Operator runbook for when the sentinel itself misbehaves, or when it correctly
alerted on something that needs a human decision. This mirrors the troubleshoot
decision tree (`ews-entry.sh troubleshoot` runs this same logic against the live
box); read it here first, or let the command point you at the right row.

"ZHC" = Zero Human Company, spelled out once (see `SKILL.md`). Nothing below ever
prints a secret value, ever hand-edits signature data on a box, or auto-changes a
client box without an explicit per-box opt-in (D2). Config writes always run as the
box user, never root.

## 1. Sentinel dark (no fresh tick for two aggregator cycles)

The operator-box aggregator raises this as a P1 when a box has not produced a fresh
tick in two consecutive hourly cycles (D3/D4). Work the checks in order; stop at the
first one that explains it.

1. **Is the cron present on the box?** `bash 60-zhc-early-warning-system/ews-entry.sh
   troubleshoot` inspects the box's cron inventory for the `ews-tick` entry. If it is
   missing, re-register it: `bash 60-zhc-early-warning-system/ews-entry.sh install`
   (safe to re-run; it will not touch an existing baseline).
2. **Cron present but not firing?** Run a manual tick to see the real error instead of
   guessing: `bash 60-zhc-early-warning-system/ews-entry.sh tick`. Read the output —
   most manual-tick failures point straight at step 3 or step 4.
3. **Ledger unreadable (SQLite-WAL corruption or a stale lock)?** The ledger is the
   single-writer state store (`~/.openclaw/ews/ews.db`, VPS `/data/.openclaw/ews/ews.db`).
   `troubleshoot` opens it read-only and reports the failure class. If the WAL file is
   recoverable, `ews_ledger.py` recovers it in place on the next open; if it is not
   (corrupted beyond a checkpoint), rotate it: move the broken `ews.db*` files aside
   with a timestamp suffix and re-run `install`, which recreates a fresh ledger and
   re-pins the baseline from the box's current config. A rotated ledger loses history,
   not doctrine — the new baseline is exactly what the box is running today.
4. **Gateway send test** — the tick may be running clean but the alert never leaves the
   box. `verify.sh` sends a real `[DRILL]` message through the actual alert path to
   your operator account; if that drill never arrives, you are looking at failure mode
   2 below (gateway down), not a sentinel bug.

## 2. Gateway down (S7 -- surfaces dark)

The sentinel detects an unreachable gateway/dashboard/tunnel by local process and
port probes plus a build marker; it never diagnoses WHY the gateway is down beyond
that. Recovery is a PLATFORM-SANCTIONED restart only — `troubleshoot` PRINTS the
exact restart command for the box's platform; it never runs it for you. You execute
it on your own word.

- **Mac (MASTER-only)**: `launchctl kickstart` first; if that does not bring the
  gateway back, `launchctl stop` then let the supervisor restart it, falling back to
  a manual `launchctl` bootstrap. Before either step, clean up any orphaned process
  still bound to the gateway's port — a stale listener on the same port is the most
  common reason a kickstart looks like it worked but the gateway still does not
  answer. This restart path is MASTER-only; do not run it from a non-master box.
- **VPS**: `docker compose up -d` — never `docker compose restart`. `restart` reuses
  the container's already-loaded environment and silently skips `env_file`, which is
  exactly how a VPS gateway comes back up with a stale or missing credential and
  looks "restarted" while still broken. `up -d` reloads the compose environment
  correctly.

Both restart paths are printed by `troubleshoot`, never executed automatically, and
never executed on a client box without the same operator word this whole system
requires everywhere else.

## 3. Config owned by root

The gateway freezing because a config file got written as root (instead of the box
user, `node` on VPS) is the exact S6 incident this system exists to catch. Every
config-touching path in this skill already refuses to run as root, so this failure
mode means something OUTSIDE the sentinel wrote the file.

1. Confirm ownership: `troubleshoot` stats the config file and reports the owning
   user by label (never a UID leak into a client-facing surface, but this is
   operator-only output regardless).
2. `chown` the file back to the box user (`node` on VPS, wrapped in
   `docker exec -u node`, never a bare host-level root chown into a running
   container's volume).
3. Validate the config parses and the gateway can read it: `bash
   60-zhc-early-warning-system/ews-entry.sh audit` (read-only; confirms the file is
   sane before you touch the process).
4. Restart the gateway using the platform-sanctioned path in item 2 above.

## 4. Baseline disputed ("that change was intended")

This is not a bug — it is the never-silently-raise rule working as designed. If a
cap raise, an access widen, or a model/provider change was YOUR intentional decision,
stamp it so the sentinel stops re-alerting on the same value:

```
bash 60-zhc-early-warning-system/ews-entry.sh approve-baseline --key <path>
```

The stamp is per-key, per-value-hash, and recorded with your operator identity and a
timestamp in the ledger's `baseline_stamps` table (spec 4.2). It never rewrites
`baseline.json` silently to match reality — the baseline only ever moves through an
explicit stamp, so the audit trail always shows who approved what and when.

## 5. False-positive signature

Signatures (`config/signatures.json` — the Anthropic-family deny prefixes, the
paid-tier markers, the known-writer argv tokens) are DATA, not code you tune on a
box. If a signature is producing a false positive (a legitimate writer argv token
missing from the known-writer allowlist, for example), the fix ships through the
repo and a sanctioned rollout — never a hand-edit on the live box. A hand-edited
signature file changes the installed tree's hash against the pinned manifest, which
trips S9 (skills-integrity drift) on the very next tick — the system catches its own
tampering by construction. File the fix against `signatures.json` in the repo,
update the catalog, and let the normal skill-update path carry it to the fleet.

## 6. Everything on fire

When a box is in a state you do not trust enough to work through the rows above one
at a time, restore known-good and get help:

```
bash 60-zhc-early-warning-system/ews-entry.sh revert --to <last-green-snapshot-utc-ts>
```

Find the last-green timestamp from `bash 60-zhc-early-warning-system/ews-entry.sh
audit` (it lists recent snapshots) or from the most recent alert that still looked
healthy. `revert` restores as the box user, never root, and reads the file back to
confirm the write took before it reports success. Then escalate on the Rescue
Rangers channel with the output of `bash 60-zhc-early-warning-system/ews-entry.sh
audit` attached — the audit output is read-only and safe to paste; it never carries a
secret value or another client's data.

## Signal -> most-likely repair

| # | Signal | Most-likely repair |
|---|---|---|
| S1 | Model / provider config drift vs baseline | If intended: item 4 (approve-baseline). If not: revert the key via item 6's `revert --to`, then confirm the box's provider config with the box's own agent. |
| S2 | Runtime fallback (trajectory ground truth) | Check the provider that's actually resolving at runtime (`troubleshoot` prints it); usually a missing/expired credential on the box triggering a silent fallback chain — fix the credential, not the sentinel. |
| S3 | Context vs compaction (broken-config case only; running-low never reaches you, D5) | Fix the arithmetic: `softThresholdTokens` must be well below the box's context window. Edit, then `approve-baseline --key agents.defaults.compaction.memoryFlush.softThresholdTokens`. |
| S4 | Safety-cap raise, unstamped | Item 4 if intended; item 6's `revert` if not. |
| S5 | Furnace / idle-burn | Check heartbeat cadence/model against the fleet floor and the box's billing type (see `HOW-TO-USE.md`'s D9 section); tighten the cadence or fix the heartbeat model, then `approve-baseline` if the new value is intentional. |
| S6 | Config-write hygiene (root-owned, unknown writer) | Item 3 (root-owned) or confirm the writer argv against `signatures.json`'s known-writer list — an unknown writer is item 5 territory only if the writer itself should be added to the allowlist. |
| S7 | Surfaces dark (gateway/dashboard/tunnel) | Item 2. |
| S8 | Secret leaked into transcript/log | Rotate the leaked credential immediately (out of band, never through this skill), then confirm the new bytes are clean on the next tick. The alert never carries the value — treat the CLASS + file:line as the complete finding. |
| S9 | Skills integrity drift / stale downgrade | Run the sanctioned skill-update path (never a box-local file edit); if the drift was a deliberate signature-catalog change, that is item 5's repo-first discipline. |
| S10 | Cron / delivery drift (announce to non-operator) | Remove or correct the offending cron entry (`--no-deliver` for anything not meant for the client, or delete the cron if it should not exist), then `approve-baseline` once the cron inventory is what you intend it to be. |
