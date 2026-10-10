#!/usr/bin/env bash
# Skill 07 — KIE Setup — Install QC
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
: "${KIE_API_KEY:=}"
# Credential stores: secrets/.env was the only one read; also read ~/.openclaw/.env and openclaw.json env.vars.
if declare -F oc_fill_from_env_stores >/dev/null 2>&1; then oc_fill_from_env_stores KIE_API_KEY; fi

echo ""
echo "═══ Skill 07 — KIE Setup — Install QC ═══"
echo ""
assert "Skill 07 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/07-kie-setup\" ]"
assert "KIE_API_KEY set" "[ -n \"$KIE_API_KEY\" ]"
assert "Secrets file chmod 600" "[ \"\$(stat -c %a \"$SECRETS_ENV\" 2>/dev/null || stat -f %A \"$SECRETS_ENV\" 2>/dev/null)\" = '600' ]"
# KIE_QC_OFFLINE=1 skips every network call (the live credit probe). The adapter checks below never use the network.
CREDIT_OK=0
if [ "${KIE_QC_OFFLINE:-0}" = 1 ]; then
  yellow "  - skipped (KIE_QC_OFFLINE=1): live credit probe"
else
  RESP=$(curl -sS -m 10 -H "Authorization: Bearer $KIE_API_KEY" "https://api.kie.ai/api/v1/chat/credit" 2>/dev/null)
  case "$RESP" in *'"code":200'*|*'"code": 200'*) CREDIT_OK=1 ;; esac
  warn_only "kie.ai API responds (body code 200)" "[ \"$CREDIT_OK\" = 1 ]"
fi
# Skill 74 adapter health, HERMETIC: presence plus `health --json` against a dead localhost port with a
# throwaway placeholder key (never the real key), so no request leaves this machine. A parseable result
# naming the adapter proves it runs; the placeholder makes the call fail fast, which is expected.
ADAPTER=""
for c in "$SKILL_DIR/../74-kie-live-adapter" "$SKILLS_DIR_DEFAULT/74-kie-live-adapter"; do
  [ -f "$c/scripts/kie_live_adapter.py" ] && { ADAPTER="$c/scripts/kie_live_adapter.py"; break; }
done
warn_only "Skill 74 adapter present (74-kie-live-adapter/scripts/kie_live_adapter.py)" "[ -n \"$ADAPTER\" ]"
if [ -n "$ADAPTER" ]; then
  QCTMP="$(mktemp -d)"
  HJ="$(KIE_API_KEY=qc-placeholder KIE_LIVE_API_BASE=http://127.0.0.1:9 KIE_LIVE_ADAPTER_MODE=shadow KIE_LIVE_CACHE_DIR="$QCTMP" KIE_LIVE_RECEIPT_DIR="$QCTMP/r" PYTHONDONTWRITEBYTECODE=1 python3 "$ADAPTER" health --json 2>/dev/null)"
  rm -rf "$QCTMP"
  warn_only "Skill 74 health --json runs and names the adapter (hermetic, no network)" "printf '%s' \"\$HJ\" | python3 -c 'import json,sys; assert json.load(sys.stdin)[\"adapter\"]==\"74-kie-live-adapter\"'"
fi
warn_only "common rules file present (references/kie-common-rules.md)" "[ -f \"$SKILL_DIR/references/kie-common-rules.md\" ]"
warn_only "official agent docs digest present (references/kie-official-agent-docs-digest.md)" "[ -f \"$SKILL_DIR/references/kie-official-agent-docs-digest.md\" ]"
warn_only "TOOLS.md references kie.ai" "grep -qi 'kie' \"$WORKSPACE/TOOLS.md\" 2>/dev/null"

# ── Report-only box findings (never mutate) ─────────────────────────────────
# Rule 14 (kie-common-rules.md, 2026-10-09): the vendor skills are never
# installed on a box, and no coding agent is pointed at api.kie.ai/anthropic.
# These two checks only PRINT what they find. They delete nothing, edit
# nothing, and never fail the QC. An operator acts on the report.
echo ""
echo "── Report-only box findings (nothing is changed) ──"
FOUND_HITS=0
# (a) Vendor skill folders, if present
for d in "$HOME/.openclaw/skills" "$HOME/.agents/skills" "$HOME/.claude/skills" "$HOME/.claude-nine/skills"; do
  for s in kie-models kie-chat-agents; do
    if [ -d "$d/$s" ]; then
      yellow "  ⚠ FINDING: vendor skill folder present: $d/$s (never install npx skills add https://kie.ai; report, do not remove)"
      FOUND_HITS=$((FOUND_HITS+1))
    fi
  done
done
# (b) settings.json env pointing a coding agent at KIE, if present
for f in "$HOME/.claude/settings.json" "$HOME/.claude-nine/settings.json"; do
  if [ -f "$f" ] && command -v python3 >/dev/null 2>&1; then
    HIT="$(SETTINGS_FILE="$f" python3 - <<'PY' 2>/dev/null || true
import json, os
try:
    cfg = json.load(open(os.environ["SETTINGS_FILE"]))
    env = cfg.get("env") or {}
    base = str(env.get("ANTHROPIC_BASE_URL") or "")
    if "api.kie.ai" in base:
        print(os.environ["SETTINGS_FILE"])
except Exception:
    pass
PY
)"
    if [ -n "$HIT" ]; then
      yellow "  ⚠ FINDING: settings env points at KIE: $HIT (ANTHROPIC_BASE_URL contains api.kie.ai; report, do not edit)"
      FOUND_HITS=$((FOUND_HITS+1))
    fi
  fi
done
if [ "$FOUND_HITS" -eq 0 ]; then
  green "  ✓ no vendor skill folders, no KIE chat-provider settings (report-only scan clean)"
fi

echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 07 QC FAILED"; exit 1; } || { green "Skill 07 QC PASS"; exit 0; }
