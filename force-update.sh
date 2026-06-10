#!/usr/bin/env bash
# ============================================================
#  OpenClaw Onboarding — Force Update (READ + APPLY)
#  For users whose computer was OFF during the Sunday 3am cron and need to
#  pull the latest update manually. Combines check-updates.sh with the apply
#  flow and fires the same triple-fire trigger (Telegram + agents.md flag +
#  terminal fallback) so the user is never stranded.
#
#  Run via:
#    curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/force-update.sh | bash
#  Or directly:
#    bash ~/.openclaw/skills/force-update.sh
#
#  v10.8.0 — P0-6 fix for Sunday Update regression.
# ============================================================
set -u
SCRIPT_VERSION="1.0.0"

# ----------------------------------------------------------
# Detect platform
# ----------------------------------------------------------
if [ -d "/data/.openclaw" ]; then
  PLATFORM="vps"
  REPO_NAME="openclaw-onboarding-vps"
  SKILLS_DIR="/data/.openclaw/skills"
  WORKSPACE="/data/.openclaw/workspace"
  AGENTS_MD="/data/.openclaw/AGENTS.md"
else
  PLATFORM="mac"
  REPO_NAME="openclaw-onboarding"
  SKILLS_DIR="$HOME/.openclaw/skills"
  WORKSPACE="$HOME/clawd"
  AGENTS_MD="$HOME/.openclaw/AGENTS.md"
fi

GH_RAW="https://raw.githubusercontent.com/trevorotts1/${REPO_NAME}/main"
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

echo "[force-update] platform=$PLATFORM repo=$REPO_NAME at $(ts)" >&2

# ----------------------------------------------------------
# 1. Run check-updates.sh and capture its JSON
# ----------------------------------------------------------
CHECK_TMP=$(mktemp)
if ! curl -fsSL --max-time 30 "${GH_RAW}/check-updates.sh" | bash > "$CHECK_TMP" 2>/dev/null; then
  echo "[force-update] ERROR: check-updates.sh failed — cannot determine update state" >&2
  echo "{\"ok\": false, \"error\": \"check-updates.sh failed\"}"
  exit 1
fi

LATEST_VERSION=$(python3 -c "import json,sys; print(json.load(open('$CHECK_TMP')).get('latest_version', ''))" 2>/dev/null || echo "")
LOCAL_VERSION=$(python3 -c "import json,sys; print(json.load(open('$CHECK_TMP')).get('local_version', ''))" 2>/dev/null || echo "")
HAS_UPDATE=$(python3 -c "import json,sys; print(str(json.load(open('$CHECK_TMP')).get('has_repo_update', False)).lower())" 2>/dev/null || echo "false")
HAS_SKILL_UPDATES=$(python3 -c "import json,sys; print(str(json.load(open('$CHECK_TMP')).get('has_skill_updates', False)).lower())" 2>/dev/null || echo "false")

echo "[force-update] local=$LOCAL_VERSION latest=$LATEST_VERSION has_repo_update=$HAS_UPDATE has_skill_updates=$HAS_SKILL_UPDATES" >&2

# ----------------------------------------------------------
# 2. If no update available, exit cleanly
# ----------------------------------------------------------
if [ "$HAS_UPDATE" != "true" ] && [ "$HAS_SKILL_UPDATES" != "true" ]; then
  cat <<EOF
{
  "ok": true,
  "action": "noop",
  "message": "No update available. You are on $LATEST_VERSION (latest).",
  "platform": "$PLATFORM",
  "local_version": "$LOCAL_VERSION",
  "latest_version": "$LATEST_VERSION"
}
EOF
  rm -f "$CHECK_TMP"
  exit 0
fi

# ----------------------------------------------------------
# 3. TRIPLE-FIRE TRIGGER (N22): Telegram + agents.md flag + terminal fallback
#    All three fire on update detection, not "any one of three."
# ----------------------------------------------------------

# 3a. Telegram message
TELEGRAM_FIRED="false"
TG_FAIL_REASON=""
if command -v openclaw >/dev/null 2>&1; then
  TG_MSG="🛠️  OpenClaw force-update detected new version
Local: ${LOCAL_VERSION:-(none)} → Latest: ${LATEST_VERSION}
Platform: ${PLATFORM}

To apply the update, paste these instructions to your agent OR follow the terminal block printed by this script."
  if openclaw message send --message "$TG_MSG" 2>/dev/null; then
    TELEGRAM_FIRED="true"
  else
    TG_FAIL_REASON="openclaw message send failed (likely Telegram not paired or scopes missing)"
  fi
else
  TG_FAIL_REASON="openclaw CLI not on PATH"
fi
echo "[force-update] telegram fired=$TELEGRAM_FIRED reason=${TG_FAIL_REASON:-ok}" >&2

# 3b. Drop install-pending flag in AGENTS.md (N22 sub-rule)
FLAG_FIRED="false"
FLAG_FAIL_REASON=""
if [ -d "$(dirname "$AGENTS_MD")" ]; then
  # Append to or create AGENTS.md; idempotent (only adds if not present)
  FLAG_MARKER="<!-- OPENCLAW_UPDATE_PENDING:$LATEST_VERSION -->"
  if [ -f "$AGENTS_MD" ] && grep -qF "$FLAG_MARKER" "$AGENTS_MD" 2>/dev/null; then
    FLAG_FIRED="true"  # already present
  else
    {
      echo ""
      echo "$FLAG_MARKER"
      echo "## OpenClaw update pending: $LATEST_VERSION (from ${LOCAL_VERSION:-unknown})"
      echo "Detected at $(ts) via force-update.sh."
      echo "Run the install instructions in the printed terminal block below to apply."
      echo "<!-- OPENCLAW_UPDATE_PENDING_END -->"
    } >> "$AGENTS_MD" 2>/dev/null && FLAG_FIRED="true" \
                                  || FLAG_FAIL_REASON="could not write $AGENTS_MD"
  fi
else
  FLAG_FAIL_REASON="AGENTS.md parent directory $(dirname "$AGENTS_MD") does not exist"
fi
echo "[force-update] agents.md flag fired=$FLAG_FIRED reason=${FLAG_FAIL_REASON:-ok}" >&2

# 3c. Terminal fallback — ALWAYS print, even if 3a + 3b succeeded
cat <<EOF

═══════════════════════════════════════════════════════════════════════
  OpenClaw Update Detected — Apply Instructions
═══════════════════════════════════════════════════════════════════════

  Local version:  ${LOCAL_VERSION:-(none)}
  Latest version: ${LATEST_VERSION}
  Platform:       ${PLATFORM}
  Repo:           https://github.com/trevorotts1/${REPO_NAME}

Even if Telegram and the AGENTS.md flag fired correctly, here are the
instructions you can copy-paste directly to your agent to start the
update process:

──────────────────────────────────────────────────────────────────────
  Paste this block to your OpenClaw agent (Telegram or dashboard):

  Apply OpenClaw onboarding update ${LATEST_VERSION}.

  Procedure:
  1. Read ${GH_RAW}/Start Here.md end to end.
  2. Read ${GH_RAW}/INSTALL-CONTRACT.md end to end.
  3. Read ${GH_RAW}/CHANGELOG.md (top entry only) to know what's in
     this release.
  4. For each updated skill listed in the check-updates JSON above:
     - cd ${SKILLS_DIR}/<skill-folder>
     - Read SKILL.md + INSTALL.md + QC.md + CORE_UPDATES.md
     - Follow INSTALL.md and CORE_UPDATES.md step-by-step
     - Run qc-*.sh and ensure exit 0
     - Independent QC sub-agent scores against QC.md rubric (gate ≥ 8.5)
  5. After all skills updated, bump ${SKILLS_DIR}/.onboarding-version
     to ${LATEST_VERSION}.
  6. Reply with a one-paragraph summary of what changed and any
     skills that failed QC.

  Hard rules:
  - No shortcuts. Read every file before acting on it.
  - No self-QC. The agent that installs cannot also QC.
  - Max 10 concurrent sub-agents on Mac, max 5 on VPS.
  - All sub-agents non-Anthropic.
──────────────────────────────────────────────────────────────────────

Or from a terminal that already has the repo cloned locally:
  bash ${SKILLS_DIR}/update-skills.sh
  (this requires that update-skills.sh is already installed via the
   previous onboarding run.)

═══════════════════════════════════════════════════════════════════════
EOF

# ----------------------------------------------------------
# 3d. PRD 1.10: run migrate-zhc-to-master-files.sh --dry-run automatically
#     on every update so the operator sees the migration manifest.
#     --apply only runs on operator confirmation (never autonomously).
# ----------------------------------------------------------
MIGRATE_SCRIPT="$SKILLS_DIR/scripts/migrate-zhc-to-master-files.sh"
if [ -f "$MIGRATE_SCRIPT" ]; then
  echo ""
  echo "═══════════════════════════════════════════════════════════════════════"
  echo "  PRD 1.10: ZHC Migration Manifest (dry-run — nothing will move)"
  echo "═══════════════════════════════════════════════════════════════════════"
  bash "$MIGRATE_SCRIPT" --dry-run 2>&1 || true
  echo ""
  echo "  To migrate, run: bash $MIGRATE_SCRIPT --apply"
  echo "  (Operator confirmation required before passing --apply)"
  echo "═══════════════════════════════════════════════════════════════════════"
  echo ""
  # Telegram the manifest summary to the operator
  if [ "$TELEGRAM_FIRED" = "true" ] && command -v openclaw >/dev/null 2>&1; then
    MANIFEST_SUMMARY=$(bash "$MIGRATE_SCRIPT" --dry-run 2>/dev/null | grep -E 'noop|simple move|conflict|companies found' | head -5 || true)
    if [ -n "$MANIFEST_SUMMARY" ]; then
      openclaw message send --message "📋 ZHC Migration manifest (dry-run):

$MANIFEST_SUMMARY

Run --apply to migrate: bash ~/.openclaw/skills/scripts/migrate-zhc-to-master-files.sh --apply" 2>/dev/null || true
    fi
  fi
fi

# ----------------------------------------------------------
# 4. Emit the final JSON status (for the cron / dispatcher to parse)
# ----------------------------------------------------------
cat <<EOF

{
  "ok": true,
  "action": "trigger-fired",
  "platform": "$PLATFORM",
  "local_version": "$LOCAL_VERSION",
  "latest_version": "$LATEST_VERSION",
  "triggers": {
    "telegram":       $([ "$TELEGRAM_FIRED" = "true" ] && echo true || echo false),
    "agents_md_flag": $([ "$FLAG_FIRED" = "true" ] && echo true || echo false),
    "terminal_fallback": true
  },
  "next_step": "Apply the update by pasting the instruction block above to your agent, OR run the terminal command shown in the printed block."
}
EOF

rm -f "$CHECK_TMP"
exit 0
