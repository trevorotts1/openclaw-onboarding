# Skill 37 — One-Time Install

This skill is auto-installed by the OpenClaw `install.sh` Step 14 starting at v10.14.17. If you're reading this on a fresh box, install.sh has already done the work and you don't need to do anything manual. The notes below are for hot-patches and verification.

## What install.sh Step 14 Does

1. Copies `37-zhc-closeout/` into `$SKILLS_DIR/37-zhc-closeout/`.
2. `chmod +x` on every file under `scripts/`.
3. Verifies prerequisite env vars are set (warns + continues if not — the skill no-ops cleanly when env vars are missing).
4. Registers the skill in the workspace manifest (idempotent — skip if entry exists).

No new cron job is created here. Skill 37 piggy-backs on the existing `workforce-build-resume` cron from v10.14.16, which is extended in v10.14.17 to also fire on dirty closeout state.

## Required Environment Variables

| Var | Required? | Where it's set | Purpose |
|-----|-----------|----------------|---------|
| `KIE_API_KEY` | YES | `/docker/<project>/.env` (VPS) or `~/.openclaw/config/.env` (Mac) | KIE.AI calls (images + video) |
| `NOTION_API_TOKEN` | YES | Same | Notion page-tree creation |
| `NOTION_API_VERSION` | RECOMMENDED | Same | Defaults to `2022-06-28` |
| `NOTION_CLOSEOUT_PARENT_PAGE_ID` | OPTIONAL | Same | If unset, the script auto-discovers a parent page |
| `OPENCLAW_TREVOR_CHAT` | OPTIONAL | Same | Escalation target if closeout fails 3+ times |

## Manual Hot-Patch (For Existing Boxes Pre-v10.14.17)

If a box was installed pre-v10.14.17 and needs Skill 37 added without a full re-install:

```bash
curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding-vps/main/update-skills.sh | bash
```

`update-skills.sh` pulls the latest skills bundle and refreshes `$SKILLS_DIR`. The next cron fire of `workforce-build-resume` (within 15 min) will pick up Skill 37's new closeout dirty-state detection automatically.

## Verification After Install

```bash
# 1. Skill files present
ls /data/.openclaw/skills/37-zhc-closeout/

# 2. Scripts executable
ls -l /data/.openclaw/skills/37-zhc-closeout/scripts/

# 3. Env vars present
printenv KIE_API_KEY | head -c 8 && echo "..."
printenv NOTION_API_TOKEN | head -c 8 && echo "..."

# 4. Workforce-build-resume cron is installed
openclaw cron list | grep workforce-build-resume

# 5. Schema includes closeoutStatus
jq '.properties.closeoutStatus' /data/.openclaw/skills/23-ai-workforce-blueprint/build-state-schema.json
```

If any of those return empty / missing, re-run `update-skills.sh`.

## Cost Cap Configuration

By default the skill uses cost-conscious model choices:
- Images: `gpt-image-1` (~$0.04 each)
- Video: `veo3_fast` (~$0.40)

To force the higher-quality alternatives, set in the container env BEFORE the closeout fires:
- `ZHC_IMAGE_MODEL=nano-banana-pro` — overrides gpt-image-1
- `ZHC_VIDEO_MODEL=veo3` — overrides veo3_fast (Veo 3.1 Quality, ~$0.80)

Worst-case cost per client closeout: ~$0.60 in KIE credits.

## Uninstall (Emergency Only)

To disable Skill 37 without removing it:

```bash
# 1. Set closeoutStatus to "done" on any in-flight state files (won't re-fire)
jq '.closeoutStatus = "done"' /data/.openclaw/workspace/.workforce-build-state.json > /tmp/s.json && mv /tmp/s.json /data/.openclaw/workspace/.workforce-build-state.json

# 2. Remove the skill dir
rm -rf /data/.openclaw/skills/37-zhc-closeout/
```

The workforce-build-resume cron will no-op gracefully if the skill files are missing.

## Known Issues

None at first ship of v1.0.0. File any issues at https://github.com/trevorotts1/openclaw-onboarding-vps/issues.
