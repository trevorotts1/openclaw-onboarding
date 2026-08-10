# Direct-to-Agent Update Message Template
# Version 3.0 | 2026-07-31 (v21.5.0)
#
# Copy-paste this to any client's agent on Telegram via Skill 15 (BlackCEO Management).
# Kept in sync with `version` at repo root.
#
# WHY THIS IS ONE DETERMINISTIC COMMAND, NOT A PLAYBOOK (coverage-audit Bug G,
# 2026-07-30): the old body told the receiving agent to fetch the repo and
# interpret a 32 KB prose playbook (UPDATE-PLAYBOOK.md) itself. Fanned out to
# N agents, that produces N divergent interpretations. This message must
# never ask an agent to read, improvise on, or summarise a playbook — it runs
# the one script that already contains every step, gate, and rollback.

---

There is an update available for your OpenClaw / BlackCEO system. The latest version is **v22.0.7**.

Run exactly this command. Do not read a playbook, do not improvise, do not summarise:

```
bash <(curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/update-skills.sh)
```

When it finishes, report back — as proof of completion, not a summary:

1. The contents of `~/.openclaw/skills/.onboarding-version` (on a VPS/Contabo box: `/data/.openclaw/skills/.onboarding-version`).
2. The last 20 lines of the command's output.
