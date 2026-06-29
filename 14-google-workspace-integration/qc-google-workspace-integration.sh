#!/usr/bin/env bash
# Skill 14 — Google Workspace Integration (gws CLI) — Install QC
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR="$(dirname "$0")"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { export SECRETS_ENV="$HOME/.openclaw/secrets/.env" WORKSPACE="$HOME/clawd" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"; }
fi
resolve_platform_paths
red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }

if [ -f "$SECRETS_ENV" ]; then set +u; set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a; set -u; fi
: "${GOOGLE_APPLICATION_CREDENTIALS:=}"

# v16.1.9 — Pin the gws file keyring backend so any auth probe we DO run uses the
# on-disk key DETERMINISTICALLY and never silently falls back to an OS keychain it
# cannot unlock in a headless session (the v16.1.x credential-wipe vector). This
# only sets the var when UNSET — it never overrides a value the client already
# exported in a dotfile/secrets.env, and it never drops it.
: "${GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND:=file}"; export GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND

echo ""
echo "═══ Skill 14 — Google Workspace Integration — Install QC ═══"
echo ""
assert "Skill 14 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/14-google-workspace-integration\" ]"
assert "gws CLI installed (replaces legacy google-api.js + gog)" "command -v gws"
# ── CREDENTIAL-SAFE gws auth probe (v16.1.9) ─────────────────────────────────
# DO NOT run a bare `gws auth status` here. PROVEN root cause of the v16.1.x
# Google Workspace credential wipe: when `gws auth status` runs in a HEADLESS /
# non-interactive context — the onboarding verification gate runs this QC as
# `bash qc-*.sh >/dev/null 2>&1` with no TTY (lib-onboarding-state.sh
# oc_gate_skill), driven by the watchdog/resume crons and the update path — and
# gws cannot decrypt its file keyring, gws's OWN known failure mode REWRITES
# ~/.config/gws/credentials.enc to credential_source:"none", erasing every
# account's OAuth. This repo never deletes, moves, chmods or rewrites that file;
# this single bare call was the ONLY trigger surface. So gate the probe to run
# ONLY when gws can safely decrypt (an interactive TTY, or an explicit operator
# opt-in OC_GWS_AUTH_PROBE=1) AND credentials are actually present; otherwise SKIP
# (warn) and leave the credential store BYTE-UNTOUCHED. Combined with the file
# keyring backend pin above, a probe we DO make can no longer silently self-clear.
gws_creds_present() {
  [ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ] || ls "$HOME"/.config/gws/credentials* >/dev/null 2>&1
}
if { [ -t 0 ] || [ "${OC_GWS_AUTH_PROBE:-}" = "1" ]; } && gws_creds_present; then
  warn_only "gws authenticated" "gws auth status 2>&1 | grep -qiE 'authenticated|active|logged'"
else
  yellow "  ⚠ SKIP — gws auth status NOT run (headless or no decryptable creds present); credential store left BYTE-UNTOUCHED"
  WARN=$((WARN+1))
fi
warn_only "GOOGLE_APPLICATION_CREDENTIALS OR plain credentials present" \
  "[ -n \"$GOOGLE_APPLICATION_CREDENTIALS\" ] || ls $HOME/.config/gws/credentials* 2>/dev/null | head -1 | grep -q ."
warn_only "SKILL.md uses 'gws' not legacy 'google-api.js'" "grep -qi 'gws' \"$SKILLS_DIR_DEFAULT/14-google-workspace-integration/SKILL.md\" 2>/dev/null"
assert "Node.js installed" "command -v node"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 14 QC FAILED"; exit 1; } || { green "Skill 14 QC PASS"; exit 0; }
