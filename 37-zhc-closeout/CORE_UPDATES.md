# Core File Updates — Skill 37

These lines are appended to the workspace `AGENTS.md` at install time. They tell the master orchestrator (and any sub-agent) when and how to fire Skill 37.

## [ADD TO AGENTS.md]

```markdown
## Skill 37 — ZHC Closeout (BINDING — added 2026-05-23 for v10.14.17)

After Skill 23 finishes writing all departments (i.e., when you set
`buildCompletedAt` in `.workforce-build-state.json`), you MUST:

1. Set `closeoutStatus: "pending"` in the same state file, atomic write.
2. Then either:
   a. Immediately invoke `~/.openclaw/skills/37-zhc-closeout/scripts/run-closeout.sh`
      yourself (preferred — same session, lowest latency for the owner), OR
   b. Stop the session and trust the workforce-build-resume cron to pick up
      the dirty state on its next 15-min fire.

Both paths are valid. (a) is faster; (b) is safer if you're near a token limit
or unsure you can complete the closeout in this session.

Do NOT send a "build complete!" message to the owner directly. The owner
hears nothing from you between interview-end and Step 6 of the closeout.
Skill 37 Step 6 is the ONLY owner-facing communication. This is intentional
— it makes the celebration big, not bitty.

If you observe `closeoutStatus == "failed"` in the state file:
- Check `closeoutFailureReason` for the specific step that failed.
- The resume cron will try to recover on its next fire.
- If you've been seeing the same failure for 3+ cron fires (check resumeAttempts
  trend), escalate to Trevor's chat: 5252140759.

The full pipeline is in `~/.openclaw/skills/37-zhc-closeout/INSTRUCTIONS.md`.
Read it before you ever touch closeout state.
```

## [ADD TO MEMORY.md]

Nothing. The closeout is a one-shot operation per client — there is nothing the agent needs to "remember" beyond what's in the state file.

## [ADD TO TOOLS.md]

```markdown
### Skill 37 — ZHC Closeout

**Entry point:** `~/.openclaw/skills/37-zhc-closeout/scripts/run-closeout.sh`

**Sub-scripts:**
- `scripts/generate-infographics.sh structure|workflow "<prompt>"` — KIE.AI image generation
- `scripts/generate-celebration-video.sh "<prompt>"` — KIE.AI Veo 3.1 video
- `scripts/create-notion-closeout.sh` — Notion page-tree creation
- `scripts/send-telegram-celebration.sh` — 6-message Telegram delivery

**Trigger:** Auto-fires when `.workforce-build-state.json` has `buildCompletedAt`
set AND `closeoutStatus` is not "done" or "sent". Either invoked inline by the
master orchestrator OR by the workforce-build-resume cron's dirty-state
detection (v10.14.17+).

**Env vars required:** KIE_API_KEY, NOTION_API_TOKEN.

**Cost cap:** ~$0.60 in KIE credits per client closeout. No Notion or Telegram
cost.
```
