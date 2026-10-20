# Direct-to-Agent Update Message Template
# Version 3.1 | 2026-10-17
# Repo version at last roll: **v27.1.54** (kept in sync with `version` at repo root)
#
# Copy-paste this to any client's agent on Telegram via Skill 15 (BlackCEO Management).
#
# WHY THIS IS ONE DETERMINISTIC SCRIPT, NOT A PLAYBOOK (coverage-audit Bug G,
# 2026-07-30): the old body told the receiving agent to fetch the repo and
# interpret a 32 KB prose playbook (UPDATE-PLAYBOOK.md) itself. Fanned out to
# N agents, that produces N divergent interpretations. This message must
# never ask an agent to read, improvise on, or summarise a playbook — it runs
# the one script that already contains every step, gate, and rollback.
#
# R7 (2026-10-17): the trigger now requires the script's EXIT CODE as the first
# reported fact. A version stamp and a log tail can both look healthy while the
# update failed; the exit code cannot.

<!-- agent-pull-fix: R7 -->

---

There is an update available for your OpenClaw / BlackCEO system. The latest version is **v27.1.54**; the operator supplies the target OpenClaw version `<V>` and the roll id `<ROLL_ID>`.

This release pairs with Command Center v7.6.112. Presentations pipeline hardening, interview reliability (ILJ), provider-routing and Rescue Rangers hardening have landed, with native Linux and Docker topologies supported on Hostinger and Contabo.

Run exactly this two-line form, substituting the operator's `<V>` and `<ROLL_ID>`. Do not read a playbook, do not improvise, do not run any other updater:

```
curl -fsSL <SELF_UPDATE_URL> -o /tmp/openclaw-self-update-<ROLL_ID>.sh
bash /tmp/openclaw-self-update-<ROLL_ID>.sh --roll-id <ROLL_ID> --openclaw-target <V> [--ninerouter-target <V>]
```

Run the second command detached (for example `nohup … &`) so it survives your session. On a Mac the operator also passes `--ninerouter-target <V>`; on Linux/Docker it is omitted. If your topology uses the container path, apply the same arguments to the script inside the container instead; do not substitute a different updater.

When it finishes, report back in this exact order — these are proof of completion, not a summary:

1. **The script's EXIT CODE first.** Quote the numeric exit code by itself. A version stamp or a healthy-looking log tail is not a substitute.
2. `<root>/self-update/<ROLL_ID>.status` — the status-file path and its last line.
3. The last 20 lines of `<root>/self-update/<ROLL_ID>.log`.
4. The resulting OpenClaw version, read from `~/.openclaw/skills/.onboarding-version` (on a VPS/Contabo box: `/data/.openclaw/skills/.onboarding-version`).

Rules:

- Never improvise the update. Never run a different updater, a manual `git pull`, or a hand-assembled sequence of steps.
- Never message the client about the update. Report to the operator only.
- Never print, echo, or paste any secret value — no tokens, keys, or env-file contents.
- **On a non-zero exit, stop.** Do not retry, do not roll back, do not attempt a repair. Report the exit code and the evidence above, and the operator takes over.
