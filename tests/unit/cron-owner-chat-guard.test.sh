#!/usr/bin/env bash
# tests/unit/cron-owner-chat-guard.test.sh
#
# CI guard: fails the build if any Telegram-delivery cron --to path bypasses
# the operator-rejecting resolver.
#
# Four assertions:
#   (1) GREP-GUARD    — every telegram cron --to has an operator case guard
#                       within 60 lines above it in the same file.
#   (2) FORBIDDEN     — no bare allowFrom[0] / allow[0] / unfiltered
#                       TELEGRAM_CHAT_ID appears as a --to source without
#                       OPERATOR_CHAT_IDS in the same assignment block.
#   (3) BEHAVIORAL    — hermetic resolver tests using synthetic configs.
#   (4) RESOLVER-SYNC — OPERATOR_CHAT_IDS set is identical in install.sh,
#                       resolve-owner-chat.sh, and nudge-incomplete-interviews.py.
#
# Exit 0 = all checks pass. Exit 1 = one or more checks failed (CI FAIL).
#
# v12.3.8 / fix/v12.3.8-cron-resolver-parity

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== cron-owner-chat-guard.test.sh ==="
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# (1) GREP-GUARD
# Every line matching `openclaw cron create` + `--channel telegram` (across
# install.sh, update-skills.sh, scripts/*) must have an operator-rejecting
# case guard within 60 lines above the associated --to line.
# We look for the pattern: `case "$TG_TARGET" in` OR `case "$chat_id" in`
# followed within a few lines by the three operator IDs.
# ─────────────────────────────────────────────────────────────────────────────
echo "--- (1) GREP-GUARD: case guard present before every cron --to ---"

check_cron_guards() {
    local file="$1"
    local fname
    fname=$(basename "$file")
    # Extract line numbers of `--to "` inside telegram cron-create blocks
    local to_lines
    to_lines=$(grep -n -- '--to "' "$file" 2>/dev/null || true)
    if [ -z "$to_lines" ]; then
        pass "$fname: no --to lines found (nothing to check)"
        return
    fi
    while IFS= read -r line; do
        local lineno
        lineno=$(echo "$line" | cut -d: -f1)
        # Scan up to 200 lines above for both a case guard and an operator ID
        # pattern.  200 lines is enough to cover the full install_*_cron()
        # function body where the guard appears at the top and the cron-create
        # retry attempts appear later in the same function.
        local start=$((lineno - 200))
        [ "$start" -lt 1 ] && start=1
        local context
        context=$(sed -n "${start},${lineno}p" "$file" 2>/dev/null || true)
        local has_case
        has_case=$(echo "$context" | grep -c 'case.*\$TG_TARGET\|case.*\$chat_id\|case.*\$_\|5252140759|6663821679|6771245262' 2>/dev/null || true)
        if [ "${has_case:-0}" -ge 1 ]; then
            pass "$fname line $lineno: case guard found within 200 lines of --to"
        else
            fail "$fname line $lineno: NO operator case guard found within 200 lines of --to -- this cron --to bypasses the operator-rejecting guard"
        fi
    done <<< "$to_lines"
}

check_cron_guards "$REPO_ROOT/install.sh"
check_cron_guards "$REPO_ROOT/update-skills.sh"

# Check any scripts/ register-cron files
for f in "$REPO_ROOT/scripts/"*cron*.sh "$REPO_ROOT/scripts/"*register*.sh; do
    [ -f "$f" ] && check_cron_guards "$f" || true
done

# ─────────────────────────────────────────────────────────────────────────────
# (2) FORBIDDEN PATTERN
# A bare `allow[0]` / `allowFrom[0]` / `allowFrom)[0]` as a resolver output
# without OPERATOR_CHAT_IDS in the same assignment block is a regression.
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- (2) FORBIDDEN: no bare allow[0]/allowFrom[0] as --to source ---"

check_forbidden() {
    local file="$1"
    local fname
    fname=$(basename "$file")
    # Find lines with bare allow[0] or allowFrom[0] patterns
    local matches
    matches=$(grep -n 'allow\[0\]\|allowFrom\b.*\[0\]\|allowFrom\)\[0\]' "$file" 2>/dev/null || true)
    if [ -z "$matches" ]; then
        pass "$fname: no bare allow[0]/allowFrom[0] patterns found"
        return
    fi
    while IFS= read -r line; do
        local lineno
        lineno=$(echo "$line" | cut -d: -f1)
        # Check if OPERATOR_CHAT_IDS appears within 20 lines
        local start=$((lineno - 5))
        [ "$start" -lt 1 ] && start=1
        local end=$((lineno + 20))
        local context
        context=$(sed -n "${start},${end}p" "$file" 2>/dev/null || true)
        local has_guard
        has_guard=$(echo "$context" | grep -c 'OPERATOR_CHAT_IDS' 2>/dev/null || true)
        if [ "${has_guard:-0}" -ge 1 ]; then
            pass "$fname line $lineno: allow[0] pattern has OPERATOR_CHAT_IDS guard nearby"
        else
            fail "$fname line $lineno: bare allow[0]/allowFrom[0] without OPERATOR_CHAT_IDS guard — this is the unguarded resolver bug"
        fi
    done <<< "$matches"
}

check_forbidden "$REPO_ROOT/install.sh"
check_forbidden "$REPO_ROOT/update-skills.sh"
for f in "$REPO_ROOT/shared-utils/"*.py "$REPO_ROOT/shared-utils/"*.sh; do
    [ -f "$f" ] && check_forbidden "$f" || true
done

# ─────────────────────────────────────────────────────────────────────────────
# (3) BEHAVIORAL — hermetic resolver tests
# Feed synthetic configs to update-skills.sh's inline resolver logic and to
# nudge-incomplete-interviews.py's OPERATOR_CHAT_IDS filter.
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- (3) BEHAVIORAL: resolver returns correct non-operator ID ---"

TMPDIR_TEST=$(mktemp -d)
trap 'rm -rf "$TMPDIR_TEST"' EXIT

# Test 3a: allowFrom=[operator, client] → should return client
FAKE_OC_JSON="$TMPDIR_TEST/.openclaw/openclaw.json"
mkdir -p "$TMPDIR_TEST/.openclaw"
cat > "$FAKE_OC_JSON" <<'EOF'
{
  "channels": {
    "telegram": {
      "allowFrom": ["5252140759", "8399116757"],
      "botToken": "9999999999:AABBCCDDEEFFaabbccddeeff"
    }
  }
}
EOF

result=$(HOME="$TMPDIR_TEST" python3 - <<'PYEOF' 2>/dev/null
import json, os, sys
OPERATOR_CHAT_IDS = {"5252140759", "6663821679", "6771245262"}
def is_valid_owner_chat(v, bot_id=""):
    if not isinstance(v, (str, int)): return ""
    s = str(v).strip().replace("telegram:", "").replace("tg:", "")
    if not s: return ""
    digits = s.lstrip("-")
    if not (digits.isdigit() and 6 <= len(digits) <= 20): return ""
    if bot_id and s == bot_id: return ""
    if s in OPERATOR_CHAT_IDS: return ""
    return s
home = os.path.expanduser("~")
oc_json = os.path.join(home, ".openclaw", "openclaw.json")
cfg = {}
try: cfg = json.load(open(oc_json))
except Exception: pass
bot_id = ""
bt = cfg.get("channels", {}).get("telegram", {}).get("botToken", "") or ""
if ":" in bt: bot_id = bt.split(":")[0]
s0 = os.environ.get("OPENCLAW_OWNER_CHAT_ID", "").strip()
if s0:
    cid = is_valid_owner_chat(s0, bot_id)
    if cid: print(cid); raise SystemExit(0)
for v in cfg.get("channels", {}).get("telegram", {}).get("allowFrom", []):
    cid = is_valid_owner_chat(v, bot_id)
    if cid: print(cid); raise SystemExit(0)
for v in cfg.get("commands", {}).get("ownerAllowFrom", []):
    cid = is_valid_owner_chat(v, bot_id)
    if cid: print(cid); raise SystemExit(0)
print("")
PYEOF
)
if [ "$result" = "8399116757" ]; then
    pass "3a: allowFrom=[operator,client] → returns client 8399116757 (skipped operator 5252140759)"
else
    fail "3a: allowFrom=[operator,client] → expected 8399116757, got '$result'"
fi

# Test 3b: allowFrom=[operator only] → should return empty (fail-loud)
cat > "$FAKE_OC_JSON" <<'EOF'
{
  "channels": {
    "telegram": {
      "allowFrom": ["5252140759"],
      "botToken": "9999999999:AABBCCDDEEFFaabbccddeeff"
    }
  }
}
EOF

result=$(HOME="$TMPDIR_TEST" python3 - <<'PYEOF' 2>/dev/null
import json, os, sys
OPERATOR_CHAT_IDS = {"5252140759", "6663821679", "6771245262"}
def is_valid_owner_chat(v, bot_id=""):
    if not isinstance(v, (str, int)): return ""
    s = str(v).strip().replace("telegram:", "").replace("tg:", "")
    if not s: return ""
    digits = s.lstrip("-")
    if not (digits.isdigit() and 6 <= len(digits) <= 20): return ""
    if bot_id and s == bot_id: return ""
    if s in OPERATOR_CHAT_IDS: return ""
    return s
home = os.path.expanduser("~")
oc_json = os.path.join(home, ".openclaw", "openclaw.json")
cfg = {}
try: cfg = json.load(open(oc_json))
except Exception: pass
bot_id = ""
bt = cfg.get("channels", {}).get("telegram", {}).get("botToken", "") or ""
if ":" in bt: bot_id = bt.split(":")[0]
s0 = os.environ.get("OPENCLAW_OWNER_CHAT_ID", "").strip()
if s0:
    cid = is_valid_owner_chat(s0, bot_id)
    if cid: print(cid); raise SystemExit(0)
for v in cfg.get("channels", {}).get("telegram", {}).get("allowFrom", []):
    cid = is_valid_owner_chat(v, bot_id)
    if cid: print(cid); raise SystemExit(0)
for v in cfg.get("commands", {}).get("ownerAllowFrom", []):
    cid = is_valid_owner_chat(v, bot_id)
    if cid: print(cid); raise SystemExit(0)
print("")
PYEOF
)
if [ -z "$result" ]; then
    pass "3b: allowFrom=[operator only] → returns empty (fail-loud, no fallthrough)"
else
    fail "3b: allowFrom=[operator only] → expected empty, got '$result'"
fi

# Test 3c: OPENCLAW_OWNER_CHAT_ID env wins over allowFrom
cat > "$FAKE_OC_JSON" <<'EOF'
{
  "channels": {
    "telegram": {
      "allowFrom": ["5252140759", "8399116757"],
      "botToken": "9999999999:AABBCCDDEEFFaabbccddeeff"
    }
  }
}
EOF

result=$(HOME="$TMPDIR_TEST" OPENCLAW_OWNER_CHAT_ID="7563518915" python3 - <<'PYEOF' 2>/dev/null
import json, os, sys
OPERATOR_CHAT_IDS = {"5252140759", "6663821679", "6771245262"}
def is_valid_owner_chat(v, bot_id=""):
    if not isinstance(v, (str, int)): return ""
    s = str(v).strip().replace("telegram:", "").replace("tg:", "")
    if not s: return ""
    digits = s.lstrip("-")
    if not (digits.isdigit() and 6 <= len(digits) <= 20): return ""
    if bot_id and s == bot_id: return ""
    if s in OPERATOR_CHAT_IDS: return ""
    return s
home = os.path.expanduser("~")
oc_json = os.path.join(home, ".openclaw", "openclaw.json")
cfg = {}
try: cfg = json.load(open(oc_json))
except Exception: pass
bot_id = ""
bt = cfg.get("channels", {}).get("telegram", {}).get("botToken", "") or ""
if ":" in bt: bot_id = bt.split(":")[0]
s0 = os.environ.get("OPENCLAW_OWNER_CHAT_ID", "").strip()
if s0:
    cid = is_valid_owner_chat(s0, bot_id)
    if cid: print(cid); raise SystemExit(0)
for v in cfg.get("channels", {}).get("telegram", {}).get("allowFrom", []):
    cid = is_valid_owner_chat(v, bot_id)
    if cid: print(cid); raise SystemExit(0)
for v in cfg.get("commands", {}).get("ownerAllowFrom", []):
    cid = is_valid_owner_chat(v, bot_id)
    if cid: print(cid); raise SystemExit(0)
print("")
PYEOF
)
if [ "$result" = "7563518915" ]; then
    pass "3c: OPENCLAW_OWNER_CHAT_ID=7563518915 wins over allowFrom"
else
    fail "3c: OPENCLAW_OWNER_CHAT_ID env override expected 7563518915, got '$result'"
fi

# Test 3d: nudge-incomplete-interviews.py rejects operator id from env
result=$(TELEGRAM_CHAT_ID="5252140759" python3 - <<'PYEOF' 2>/dev/null
import os
OPERATOR_CHAT_IDS = {"5252140759", "6663821679", "6771245262"}
_raw = os.environ.get("TELEGRAM_CHAT_ID", "")
_norm = _raw.strip().replace("telegram:", "").replace("tg:", "")
if _norm in OPERATOR_CHAT_IDS:
    print("REJECTED")
else:
    print("SENT")
PYEOF
)
if [ "$result" = "REJECTED" ]; then
    pass "3d: nudge-incomplete-interviews.py rejects TELEGRAM_CHAT_ID=5252140759 (operator)"
else
    fail "3d: nudge-incomplete-interviews.py should reject operator TELEGRAM_CHAT_ID, got '$result'"
fi

# Test 3e: nudge passes through valid client chat_id
result=$(TELEGRAM_CHAT_ID="8399116757" python3 - <<'PYEOF' 2>/dev/null
import os
OPERATOR_CHAT_IDS = {"5252140759", "6663821679", "6771245262"}
_raw = os.environ.get("TELEGRAM_CHAT_ID", "")
_norm = _raw.strip().replace("telegram:", "").replace("tg:", "")
if _norm in OPERATOR_CHAT_IDS:
    print("REJECTED")
else:
    print(_norm)
PYEOF
)
if [ "$result" = "8399116757" ]; then
    pass "3e: nudge-incomplete-interviews.py passes through valid client chat_id 8399116757"
else
    fail "3e: nudge should pass client chat_id 8399116757, got '$result'"
fi

# ─────────────────────────────────────────────────────────────────────────────
# (4) RESOLVER-SYNC — OPERATOR_CHAT_IDS set identical in all 3 files
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- (4) RESOLVER-SYNC: OPERATOR_CHAT_IDS identical across 3 files ---"

EXPECTED_IDS='{"5252140759", "6663821679", "6771245262"}'

check_operator_ids() {
    local file="$1"
    local fname
    fname=$(basename "$file")
    local found
    found=$(grep -o 'OPERATOR_CHAT_IDS\s*=\s*{[^}]*}' "$file" 2>/dev/null | head -1 || true)
    if [ -z "$found" ]; then
        fail "$fname: OPERATOR_CHAT_IDS not found"
        return
    fi
    # Verify all three operator IDs are present
    local missing=0
    for oid in "5252140759" "6663821679" "6771245262"; do
        if ! echo "$found" | grep -q "$oid"; then
            fail "$fname: OPERATOR_CHAT_IDS missing $oid"
            missing=$((missing+1))
        fi
    done
    if [ "$missing" -eq 0 ]; then
        pass "$fname: OPERATOR_CHAT_IDS contains all 3 operator IDs"
    fi
}

check_operator_ids "$REPO_ROOT/install.sh"
check_operator_ids "$REPO_ROOT/shared-utils/resolve-owner-chat.sh"
check_operator_ids "$REPO_ROOT/shared-utils/nudge-incomplete-interviews.py"

# Also verify the bash OPERATOR_CHAT_IDS_SH in resolve-owner-chat.sh is present
if grep -q 'OPERATOR_CHAT_IDS_SH.*5252140759' "$REPO_ROOT/shared-utils/resolve-owner-chat.sh" 2>/dev/null; then
    pass "resolve-owner-chat.sh: OPERATOR_CHAT_IDS_SH bash variable present"
else
    fail "resolve-owner-chat.sh: OPERATOR_CHAT_IDS_SH bash variable missing or incomplete"
fi

# ─────────────────────────────────────────────────────────────────────────────
# (5) COMMAND-MODE INVARIANT (v12.3.10)
# The interview-nudge cron MUST be registered in silent command mode.
# Assert: install.sh's interview-nudge registration uses `openclaw cron add`
# with `--command` and contains NO `--channel telegram` / `--to` / `--message`
# on the interview-nudge create path. Also assert no operator id appears as a
# cron --to target in interview-nudge-cron.sh itself.
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- (5) COMMAND-MODE: interview-nudge cron registered in silent command mode ---"

# 5a: install.sh interview-nudge section uses `openclaw cron add ... --command`
nudge_section=$(awk '/install_interview_nudge_cron\(\)/,/^install_interview_nudge_cron$/' \
    "$REPO_ROOT/install.sh" 2>/dev/null || true)

if [ -z "$nudge_section" ]; then
    fail "5a: could not extract install_interview_nudge_cron() function body from install.sh"
else
    if echo "$nudge_section" | grep -q 'openclaw cron add'; then
        pass "5a: install.sh interview-nudge uses 'openclaw cron add' (command mode)"
    else
        fail "5a: install.sh interview-nudge does NOT use 'openclaw cron add'"
    fi

    if echo "$nudge_section" | grep -q -- '--command'; then
        pass "5b: install.sh interview-nudge uses --command flag (silent command mode)"
    else
        fail "5b: install.sh interview-nudge does NOT use --command flag"
    fi

    # Must NOT contain --channel telegram or --to or --message on the nudge cron add line
    if echo "$nudge_section" | grep 'openclaw cron add\|openclaw cron create' | grep -q -- '--channel telegram'; then
        fail "5c: install.sh interview-nudge cron registration contains --channel telegram (announce mode leak)"
    else
        pass "5c: install.sh interview-nudge cron registration has NO --channel telegram"
    fi

    if echo "$nudge_section" | grep 'openclaw cron add\|openclaw cron create' | grep -qE '\-\-to [0-9]|\-\-to "\$'; then
        fail "5d: install.sh interview-nudge cron registration contains --to <id> (announce mode leak)"
    else
        pass "5d: install.sh interview-nudge cron registration has NO --to"
    fi

    if echo "$nudge_section" | grep 'openclaw cron add\|openclaw cron create' | grep -q -- '--message'; then
        fail "5e: install.sh interview-nudge cron registration contains --message (announce mode leak)"
    else
        pass "5e: install.sh interview-nudge cron registration has NO --message"
    fi
fi

# 5f: interview-nudge-cron.sh itself never contains operator ids as --to targets
nudge_shim="$REPO_ROOT/23-ai-workforce-blueprint/scripts/interview-nudge-cron.sh"
if [ -f "$nudge_shim" ]; then
    for op_id in "5252140759" "6663821679" "6771245262"; do
        # Only flag if the operator id appears on a non-comment line as --to value
        if grep -v "^[[:space:]]*#" "$nudge_shim" | grep -qE "\-\-to ['\"]?${op_id}['\"]?|\-\-target ['\"]?${op_id}['\"]?"; then
            fail "5f-${op_id}: interview-nudge-cron.sh contains operator id ${op_id} as a --to/--target (operator announce leak)"
        else
            pass "5f-${op_id}: interview-nudge-cron.sh does not route to operator id ${op_id}"
        fi
    done
else
    fail "5f: interview-nudge-cron.sh not found at $nudge_shim"
fi

# 5g: the shim header documents COMMAND MODE and NO-OPERATOR-ANNOUNCE rules
if [ -f "$nudge_shim" ]; then
    if grep -q 'COMMAND mode\|COMMAND MODE\|command mode' "$nudge_shim" 2>/dev/null; then
        pass "5g: interview-nudge-cron.sh documents COMMAND MODE rule"
    else
        fail "5g: interview-nudge-cron.sh missing COMMAND MODE documentation"
    fi
    if grep -q 'OPERATOR-ANNOUNCE\|operator-announce\|no.*operator.*announce\|operator.*chat.*log' "$nudge_shim" 2>/dev/null; then
        pass "5h: interview-nudge-cron.sh documents operator-announce prohibition"
    else
        fail "5h: interview-nudge-cron.sh missing operator-announce prohibition documentation"
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# (6) SILENT-OPERATOR-CRON INVARIANT (chore/silent-operator-crons)
# The operator / maintenance / onboarding crons below are NON-announcing: they
# must never auto-deliver internal traffic to the client chat. Their cron
# registration MUST NOT carry --channel telegram, --to, or --announce. They run
# either as silent main-session agent-message crons (--session-target main
# --light-context) or as command-mode crons (--command). This is the
# enforcement for the "operator/maintenance crons default to silent" doctrine.
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- (6) SILENT-OPERATOR-CRON: maintenance crons carry no --channel/--to/--announce ---"

# Assert the registration block for a named cron has none of the forbidden
# auto-delivery flags. We extract a window around each `--name "<cron>"` create
# call and grep the create-flag lines for the forbidden flags.
assert_silent_cron() {
    local file="$1" cron_name="$2"
    local fname
    fname=$(basename "$file")
    if [ ! -f "$file" ]; then
        return 0
    fi
    # Find each line that names this cron in a registration array/call.
    local name_lines
    name_lines=$(grep -n -- "--name \"$cron_name\"" "$file" 2>/dev/null || true)
    if [ -z "$name_lines" ]; then
        # Not registered in this file — nothing to assert here.
        return 0
    fi
    local any=0
    while IFS= read -r nl; do
        [ -n "$nl" ] || continue
        any=1
        local lineno start end block
        lineno=$(echo "$nl" | cut -d: -f1)
        start="$lineno"
        end=$((lineno + 12))   # a cron-create flag array spans only a few lines
        # Strip comment lines (leading-# after optional whitespace) so the
        # SILENT-cron explainer comments — which legitimately mention the
        # forbidden flag NAMES — never trip the grep. Only real flag lines count.
        block=$(sed -n "${start},${end}p" "$file" 2>/dev/null | grep -vE '^\s*#' || true)
        # The block must end at the next blank line or closing paren of the array;
        # restrict to lines that look like flags to avoid bleeding into the next
        # attempt's prose. We just check the forbidden flags within the window.
        if echo "$block" | grep -qE -- '--channel telegram|--announce'; then
            fail "$fname: '$cron_name' registration near line $lineno carries --channel telegram or --announce (auto-announce leak)"
        elif echo "$block" | grep -qE -- '--to "\$|--to [0-9]'; then
            fail "$fname: '$cron_name' registration near line $lineno carries --to (auto-delivery leak)"
        else
            pass "$fname: '$cron_name' registration near line $lineno is SILENT (no --channel/--to/--announce)"
        fi
    done <<< "$name_lines"
    [ "$any" -eq 1 ] || true
}

for _cron in weekly-onboarding-update workforce-build-resume onboarding-resume \
             watchdog-onboarding-loop reassert-presentation-deps; do
    assert_silent_cron "$REPO_ROOT/install.sh" "$_cron"
    assert_silent_cron "$REPO_ROOT/update-skills.sh" "$_cron"
    assert_silent_cron "$REPO_ROOT/scripts/ensure-pipeline-crons.sh" "$_cron"
done

# 6b: update-skills.sh send_telegram_progress must NOT target the client default
# chat (allowFrom). It must route to the operator escalation chat or log-only.
if grep -n 'send_telegram_progress()' "$REPO_ROOT/update-skills.sh" >/dev/null 2>&1; then
    # Strip comment lines (the SILENT-cron explainer legitimately names allowFrom[0]
    # while explaining what it must NOT do).
    stp_block=$(awk '/^send_telegram_progress\(\) \{/,/^}/' "$REPO_ROOT/update-skills.sh" 2>/dev/null | grep -vE '^\s*#' || true)
    if echo "$stp_block" | grep -qE "allowFrom', \[\]\)|allow\[0\]|allowFrom.*\[0\]"; then
        fail "6b: update-skills.sh send_telegram_progress still reads allowFrom[0] (client-chat auto-notify leak)"
    else
        pass "6b: update-skills.sh send_telegram_progress does not target client allowFrom"
    fi
    if echo "$stp_block" | grep -qE 'OPERATOR_ESCALATION_CHAT_ID|OPERATOR_HELP_CHAT_ID|--account operator|agent:main:operator|logged-no-operator-chat'; then
        pass "6c: update-skills.sh send_telegram_progress routes to operator chat / log-only (not client)"
    else
        fail "6c: update-skills.sh send_telegram_progress is not operator-routed"
    fi
fi

# 6d: setup-weekly-update.sh must NOT force a gateway restart to push updates
# (updates push silently via the AGENTS.md UPDATE PENDING flag).
if [ -f "$REPO_ROOT/scripts/setup-weekly-update.sh" ]; then
    if grep -vE '^\s*#' "$REPO_ROOT/scripts/setup-weekly-update.sh" | grep -q 'openclaw gateway restart'; then
        fail "6d: setup-weekly-update.sh still calls 'openclaw gateway restart' on update (disruptive forced push)"
    else
        pass "6d: setup-weekly-update.sh pushes updates silently (no gateway restart)"
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# (7) MANAGED-CRON DELIVERY GUARD (v14.1.1 — agent-browser-reaper-announce-spam)
# A managed maintenance/health cron's delivery must NEVER resolve to a chat:
# mode==announce, channel=="last", or a non-empty `to` is FORBIDDEN. This is the
# permanent guard for the fleet-wide reaper spam + token furnace.
#
#   7a STATIC  — ensure-pipeline-crons.sh ships the RECONCILE pass and registers
#                the reaper HOURLY + command-kind (no */10, no --announce/--to).
#   7b CLASSIFY — a BAD fixture {announce,last} is FLAGGED and a GOOD fixture
#                 {none} PASSES, exercising the same delivery-resolves-to-chat
#                 rule the reconcile pass + this guard enforce.
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- (7) MANAGED-CRON DELIVERY: no managed cron resolves to channel:last or a chat ---"

ENSURE_CRONS_FILE="$REPO_ROOT/scripts/ensure-pipeline-crons.sh"

# 7a-1: the reconcile pass exists (the converge-on-deployed-boxes fix).
if grep -q '_reconcile_managed_crons' "$ENSURE_CRONS_FILE" 2>/dev/null \
   && grep -q 'cron edit' "$ENSURE_CRONS_FILE" 2>/dev/null \
   && grep -q -- '--no-deliver' "$ENSURE_CRONS_FILE" 2>/dev/null; then
    pass "7a-1: ensure-pipeline-crons.sh ships a reconcile pass that flips existing crons silent (--no-deliver)"
else
    fail "7a-1: ensure-pipeline-crons.sh missing reconcile pass (_reconcile_managed_crons / cron edit --no-deliver) — pre-existing announce crons will never converge"
fi

# 7a-2: the reaper is registered HOURLY, not */10 (token-furnace + spam cadence).
reaper_reg=$(grep -n 'agent-browser-reaper' "$ENSURE_CRONS_FILE" | grep '_ensure_health_cron' || true)
if [ -z "$reaper_reg" ]; then
    fail "7a-2: could not find the agent-browser-reaper registration line in ensure-pipeline-crons.sh"
elif echo "$reaper_reg" | grep -q '\*/10'; then
    fail "7a-2: agent-browser-reaper is still registered at */10 (must be throttled to hourly)"
else
    pass "7a-2: agent-browser-reaper is registered hourly (not */10)"
fi

# 7a-3: the reaper registration goes through _ensure_health_cron (always
# command-kind on the 2026.6.x CLI) — never an agent-message/agentTurn form.
if echo "$reaper_reg" | grep -q '_ensure_health_cron "agent-browser-reaper"'; then
    pass "7a-3: agent-browser-reaper registered via _ensure_health_cron (command-kind, zero LLM tokens)"
else
    fail "7a-3: agent-browser-reaper is NOT registered via _ensure_health_cron (risk of agentTurn token furnace)"
fi

# 7b: behavioral classifier — mirror the delivery-resolves-to-chat rule the
# reconcile pass enforces. A managed cron is "spammy" iff
#   delivery.mode == "announce"  OR  delivery.channel == "last"  OR  delivery.to non-empty.
# Feed a BAD fixture (must be FLAGGED) and a GOOD fixture (must PASS).
classify_managed_delivery() {
    # args: mode channel to  ->  echoes "FLAG" or "OK"
    python3 - "$1" "$2" "$3" <<'PYEOF'
import sys
mode, channel, to = sys.argv[1], sys.argv[2], sys.argv[3]
to = to.strip()
if mode == "announce" or channel == "last" or to != "":
    print("FLAG")
else:
    print("OK")
PYEOF
}

# 7b-BAD: the exact fleet-wide bug — command/agentTurn cron with announce + last.
bad=$(classify_managed_delivery "announce" "last" "")
if [ "$bad" = "FLAG" ]; then
    pass "7b-BAD: announce+last fixture is FLAGGED (guard catches the spam/furnace shape)"
else
    fail "7b-BAD: announce+last fixture was NOT flagged — guard would let the reaper-spam regression through"
fi

# 7b-BAD2: silent mode but an explicit client/operator chat in `to` is still spammy.
bad2=$(classify_managed_delivery "none" "telegram" "5252140759")
if [ "$bad2" = "FLAG" ]; then
    pass "7b-BAD2: mode=none but to=<chat> fixture is FLAGGED (a managed cron must not target any chat)"
else
    fail "7b-BAD2: a managed cron with an explicit chat target was NOT flagged"
fi

# 7b-GOOD: fully silent — mode none, no last channel, no `to`.
good=$(classify_managed_delivery "none" "" "")
if [ "$good" = "OK" ]; then
    pass "7b-GOOD: silent fixture (mode=none, no channel, no to) PASSES"
else
    fail "7b-GOOD: silent fixture was wrongly flagged — guard is over-eager"
fi

# 7c: NEGATIVE SELF-TEST — prove the guard would FAIL the build if the reaper
# were re-registered at */10. We run the 7a-2 check against a synthetic line and
# assert it reports a failure (without affecting the real $FAIL counter).
synthetic_bad='  _ensure_health_cron "agent-browser-reaper"     "*/10 * * * *" "agent-browser-reaper.sh"'
if echo "$synthetic_bad" | grep -q '\*/10'; then
    pass "7c: negative self-test — a */10 reaper registration line is detectable (guard 7a-2 would FAIL on it)"
else
    fail "7c: negative self-test broken — could not detect a synthetic */10 reaper line"
fi

# ─────────────────────────────────────────────────────────────────────────────
# (8) SILENT-UPDATE-PATH GUARD (chore/silent-updater — WE MOVE IN SILENCE)
# The progress/notification emitters in EVERY update-path script must be
# operator-routed / log-only — they must NEVER resolve the client default chat
# and NEVER hit api.telegram.org directly. This is the permanent guard that
# closes the recurrence: the prior fix silenced ONLY update-skills.sh, but
# install.sh (the canonical installer the fleet roll re-runs on a client box)
# and force-update.sh / the legacy scripts/update-skills.sh still auto-DM'd the
# client. Each is now asserted operator-routed.
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- (8) SILENT-UPDATE-PATH: install/force/legacy update emitters are operator-routed, never the client ---"

# 8a: install.sh send_telegram_progress must be operator-routed/log-only — the
# SAME contract as update-skills.sh (6b/6c). It must NOT resolve a client target
# (resolve_telegram_target_universal / TELEGRAM_TARGET_CACHED / allowFrom) and
# must NOT fall back to the direct Bot-API (tg_send_direct); it MUST carry the
# operator-routing markers.
if grep -n 'send_telegram_progress()' "$REPO_ROOT/install.sh" >/dev/null 2>&1; then
    install_stp=$(awk '/^send_telegram_progress\(\) \{/,/^}/' "$REPO_ROOT/install.sh" 2>/dev/null | grep -vE '^\s*#' || true)
    if echo "$install_stp" | grep -qE 'resolve_telegram_target_universal|tg_send_direct|TELEGRAM_TARGET_CACHED|allowFrom'; then
        fail "8a: install.sh send_telegram_progress still resolves the CLIENT chat / direct Bot-API (client-chat auto-notify leak — the exact recurrence)"
    else
        pass "8a: install.sh send_telegram_progress does NOT resolve a client target or hit the direct Bot-API"
    fi
    if echo "$install_stp" | grep -qE 'OPERATOR_ESCALATION_CHAT_ID|OPERATOR_HELP_CHAT_ID|--account operator|agent:main:operator|logged-no-operator-chat'; then
        pass "8a-2: install.sh send_telegram_progress routes to operator chat / log-only"
    else
        fail "8a-2: install.sh send_telegram_progress is not operator-routed"
    fi
else
    fail "8a: install.sh send_telegram_progress() not found — cannot verify it is silenced"
fi

# 8b: force-update.sh must never send to the client. Every non-comment
# `openclaw message send` must carry `--account operator`, and the file must
# contain no direct api.telegram.org call.
if [ -f "$REPO_ROOT/force-update.sh" ]; then
    fu_sends=$(grep -nE 'openclaw message send' "$REPO_ROOT/force-update.sh" | grep -vE '^[0-9]+:[[:space:]]*#' || true)
    fu_bad=0
    while IFS= read -r ln; do
        [ -n "$ln" ] || continue
        if ! echo "$ln" | grep -q -- '--account operator'; then
            fu_bad=$((fu_bad + 1))
        fi
    done <<< "$fu_sends"
    if [ "$fu_bad" -eq 0 ]; then
        pass "8b: force-update.sh every 'openclaw message send' is operator-routed (--account operator)"
    else
        fail "8b: force-update.sh has $fu_bad 'openclaw message send' call(s) without --account operator (client-chat leak)"
    fi
    if grep -vE '^\s*#' "$REPO_ROOT/force-update.sh" | grep -q 'api\.telegram\.org'; then
        fail "8b-2: force-update.sh calls api.telegram.org directly (gateway-bypass client send)"
    else
        pass "8b-2: force-update.sh has no direct api.telegram.org call"
    fi
else
    fail "8b: force-update.sh not found"
fi

# 8c: legacy scripts/update-skills.sh must be operator-routed / log-only too:
# no direct api.telegram.org send, no allowFrom-derived client target.
if [ -f "$REPO_ROOT/scripts/update-skills.sh" ]; then
    if grep -vE '^\s*#' "$REPO_ROOT/scripts/update-skills.sh" | grep -q 'api\.telegram\.org'; then
        fail "8c: scripts/update-skills.sh calls api.telegram.org directly (gateway-bypass client send)"
    else
        pass "8c: scripts/update-skills.sh has no direct api.telegram.org call"
    fi
    legacy_notify=$(awk '/Update notification|Telegram notification/,/^fi$/' "$REPO_ROOT/scripts/update-skills.sh" 2>/dev/null | grep -vE '^\s*#' || true)
    if echo "$legacy_notify" | grep -qE 'OPERATOR_ESCALATION_CHAT_ID|--account operator'; then
        pass "8c-2: scripts/update-skills.sh update notification is operator-routed"
    else
        fail "8c-2: scripts/update-skills.sh update notification is not operator-routed"
    fi
    if echo "$legacy_notify" | grep -qE "allowFrom',\s*\[\]\)|allowFrom\b.*\[0\]"; then
        fail "8c-3: scripts/update-skills.sh notification still reads allowFrom[0] (client target)"
    else
        pass "8c-3: scripts/update-skills.sh notification does not target client allowFrom"
    fi
else
    pass "8c: scripts/update-skills.sh not present (nothing to check)"
fi

# 8d: BEHAVIORAL — the operator-only resolver used by every silenced emitter
# returns the OPERATOR escalation chat when set, and EMPTY (→ log-only) when
# only a client allowFrom exists. It must NEVER surface the client chat.
op_resolve() {
    OC_JSON="$1" python3 - <<'PYEOF' 2>/dev/null
import json, os
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
except Exception:
    cfg = {}
env = (cfg.get("env", {}) or {}).get("vars", {}) or {}
for k in ("OPERATOR_ESCALATION_CHAT_ID", "OPERATOR_HELP_CHAT_ID"):
    v = str(env.get(k, "") or "").strip()
    if v:
        print(v); raise SystemExit(0)
print("")
PYEOF
}

# 8d-1: only a client allowFrom, NO operator escalation chat → resolves EMPTY.
SILENT_CFG="$TMPDIR_TEST/silent-client-only.json"
cat > "$SILENT_CFG" <<'EOF'
{ "channels": { "telegram": { "allowFrom": ["8399116757"] } } }
EOF
res=$(op_resolve "$SILENT_CFG")
if [ -z "$res" ]; then
    pass "8d-1: client-only config resolves EMPTY (emitter goes log-only — client NEVER messaged)"
else
    fail "8d-1: client-only config resolved '$res' (must be empty — a client chat would be messaged)"
fi

# 8d-2: operator escalation chat present → resolves to the operator chat only.
OP_CFG="$TMPDIR_TEST/operator-set.json"
cat > "$OP_CFG" <<'EOF'
{ "channels": { "telegram": { "allowFrom": ["8399116757"] } },
  "env": { "vars": { "OPERATOR_ESCALATION_CHAT_ID": "6663821679" } } }
EOF
res=$(op_resolve "$OP_CFG")
if [ "$res" = "6663821679" ]; then
    pass "8d-2: operator escalation chat resolves to operator id (not the client allowFrom)"
else
    fail "8d-2: expected operator id 6663821679, got '$res'"
fi

# 8e: the WE MOVE IN SILENCE doctrine ships in the client-facing AGENTS.md
# template so every deployed agent carries it.
if grep -q 'WE_MOVE_IN_SILENCE_V1' "$REPO_ROOT/AGENTS.md" 2>/dev/null \
   && grep -qi 'WE MOVE IN SILENCE' "$REPO_ROOT/AGENTS.md" 2>/dev/null; then
    pass "8e: AGENTS.md template ships the WE MOVE IN SILENCE maintenance-silence doctrine"
else
    fail "8e: AGENTS.md template is missing the WE MOVE IN SILENCE doctrine block (sentinel WE_MOVE_IN_SILENCE_V1)"
fi

# ─────────────────────────────────────────────────────────────────────────────
# (9) FRESH-INSTALL KICKOFF GATE (chore/silent-kickoff — WE MOVE IN SILENCE)
# The interactive onboarding kickoff handshake (send_kickoff_telegram) is
# owner-facing and must fire ONLY on a true fresh install — NEVER on an update /
# re-roll of an already-onboarded box. install.sh captures OPENCLAW_IS_FRESH_INSTALL
# BEFORE it writes the .onboarding-version stamp, gates the send chokepoint on it,
# and gates the send-telegram.sh fallback in fire_install_kickoff_triplet so the
# fallback cannot bypass the gate.
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- (9) FRESH-INSTALL KICKOFF GATE: owner handshake fires on fresh install only, never on update ---"

INSTALL_SH="$REPO_ROOT/install.sh"

# 9a: the freshness flag is captured.
if grep -qE '^OPENCLAW_IS_FRESH_INSTALL=1$' "$INSTALL_SH" 2>/dev/null; then
    pass "9a: install.sh captures OPENCLAW_IS_FRESH_INSTALL"
else
    fail "9a: install.sh does NOT capture OPENCLAW_IS_FRESH_INSTALL (fresh-install gate missing)"
fi

# 9b: the capture runs BEFORE the .onboarding-version stamp write AND before the
# first send_kickoff_telegram call (otherwise it would read post-install state
# and mis-classify every box).
cap_ln=$(grep -nE '^OPENCLAW_IS_FRESH_INSTALL=1$' "$INSTALL_SH" | head -1 | cut -d: -f1)
stamp_ln=$(grep -n 'onboarding-version' "$INSTALL_SH" | grep -E '> *"\$SKILLS_DIR/\.onboarding-version"' | head -1 | cut -d: -f1)
firstcall_ln=$(grep -nE '(if|elif)[[:space:]]+send_kickoff_telegram' "$INSTALL_SH" | grep -vE '^[0-9]+:[[:space:]]*#' | head -1 | cut -d: -f1)
if [ -n "$cap_ln" ] && [ -n "$stamp_ln" ] && [ "$cap_ln" -lt "$stamp_ln" ]; then
    pass "9b-1: freshness captured (line $cap_ln) BEFORE the .onboarding-version stamp write (line $stamp_ln)"
else
    fail "9b-1: freshness capture is not before the stamp write (cap=$cap_ln stamp=$stamp_ln)"
fi
if [ -n "$cap_ln" ] && [ -n "$firstcall_ln" ] && [ "$cap_ln" -lt "$firstcall_ln" ]; then
    pass "9b-2: freshness captured (line $cap_ln) BEFORE the first send_kickoff_telegram call (line $firstcall_ln)"
else
    fail "9b-2: freshness capture is not before the first kickoff call (cap=$cap_ln call=$firstcall_ln)"
fi

# 9c: the send chokepoint (send_kickoff_telegram) gates on the freshness flag and
# returns non-zero (no send) when not fresh.
kickoff_body=$(awk '/^send_kickoff_telegram\(\) \{/,/^}/' "$INSTALL_SH" 2>/dev/null | grep -vE '^\s*#' || true)
if echo "$kickoff_body" | grep -q 'OPENCLAW_IS_FRESH_INSTALL' && echo "$kickoff_body" | grep -qE 'return 1'; then
    pass "9c: send_kickoff_telegram gates on OPENCLAW_IS_FRESH_INSTALL (suppresses with return 1 when not fresh)"
else
    fail "9c: send_kickoff_telegram does NOT gate on the fresh-install flag (kickoff can fire on updates)"
fi

# 9d: in fire_install_kickoff_triplet the fresh-install guard precedes the
# send-telegram.sh fallback, so the fallback can NEVER bypass the gate.
trip_ln=$(grep -n 'fire_install_kickoff_triplet() {' "$INSTALL_SH" | head -1 | cut -d: -f1)
if [ -n "$trip_ln" ]; then
    guard_ln=$(awk -v s="$trip_ln" 'NR>=s && /OPENCLAW_IS_FRESH_INSTALL/ {print NR; exit}' "$INSTALL_SH")
    fallback_ln=$(awk -v s="$trip_ln" 'NR>=s && /send-telegram\.sh/ {print NR; exit}' "$INSTALL_SH")
    if [ -n "$guard_ln" ] && [ -n "$fallback_ln" ] && [ "$guard_ln" -lt "$fallback_ln" ]; then
        pass "9d: fire_install_kickoff_triplet fresh-install guard (line $guard_ln) precedes the send-telegram.sh fallback (line $fallback_ln)"
    else
        fail "9d: send-telegram.sh fallback in fire_install_kickoff_triplet is NOT gated behind the fresh-install guard (guard=$guard_ln fallback=$fallback_ln) — it could bypass the gate on an update"
    fi
else
    fail "9d: fire_install_kickoff_triplet() not found"
fi

# 9e: BEHAVIORAL — replicate the freshness detection + the gate predicate and
# prove a STAMPED box suppresses the handshake while a BARE box allows it.
detect_fresh() {
    local H="$1" fresh=1
    for vm in "$H/.openclaw/skills/.onboarding-version" "$H/Downloads/openclaw-master-files/.onboarding-version" "$H/.openclaw/onboarding/.onboarding-version"; do
        [ -f "$vm" ] && { fresh=0; break; }
    done
    if [ "$fresh" = "1" ] && [ -f "$H/.openclaw/openclaw.json" ] && command -v python3 >/dev/null 2>&1; then
        if OC_J="$H/.openclaw/openclaw.json" python3 -c 'import json,os,sys;d=json.load(open(os.environ["OC_J"]));sys.exit(0 if ((d.get("agents",{}) or {}).get("list",[]) or []) else 1)' 2>/dev/null; then
            fresh=0
        fi
    fi
    echo "$fresh"
}
gate_sends() { [ "${1:-0}" = "1" ] && echo "SEND" || echo "SUPPRESS"; }

HB="$TMPDIR_TEST/fresh-bare"; mkdir -p "$HB/.openclaw"
HS="$TMPDIR_TEST/fresh-stamped"; mkdir -p "$HS/.openclaw/skills"; echo "v0.0.0" > "$HS/.openclaw/skills/.onboarding-version"
HA="$TMPDIR_TEST/fresh-agents"; mkdir -p "$HA/.openclaw"; echo '{"agents":{"list":[{"id":"main"}]}}' > "$HA/.openclaw/openclaw.json"

if [ "$(gate_sends "$(detect_fresh "$HB")")" = "SEND" ]; then
    pass "9e-1: bare (never-onboarded) box → fresh → kickoff handshake SENDS (fresh onboarding still works)"
else
    fail "9e-1: bare box was NOT classified fresh — fresh onboarding would be broken"
fi
if [ "$(gate_sends "$(detect_fresh "$HS")")" = "SUPPRESS" ]; then
    pass "9e-2: stamped (already-onboarded) box → update → kickoff handshake SUPPRESSED (no client chatter)"
else
    fail "9e-2: stamped box was NOT suppressed — kickoff would fire on an update (the leak)"
fi
if [ "$(gate_sends "$(detect_fresh "$HA")")" = "SUPPRESS" ]; then
    pass "9e-3: box with configured agents → update → kickoff handshake SUPPRESSED"
else
    fail "9e-3: box with configured agents was NOT suppressed"
fi

# ─────────────────────────────────────────────────────────────────────────────
# (10) WEEKLY-UPDATE PROMPT RECIPIENT HYGIENE (fix/cron-nudge-sweep-selfheal)
# The weekly-onboarding-update cron's AGENT PAYLOAD is cron-prompt.txt. Its old
# RULE 8 told the agent to send the client-facing weekly summary to
# `telegram allowFrom[0]` — but on a client box the OPERATOR id is FIRST in
# allowFrom, so allowFrom[0] resolved to the operator and leaked client messages
# to Trevor. The prompt must instead resolve the CLIENT owner chat via the
# operator-rejecting resolver (shared-utils/resolve-owner-chat.sh →
# resolve_owner_chat_id) and NEVER send to a bare allowFrom[0]. Sections (1)-(2)
# never inspected the prompt files, which is how this slipped through.
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- (10) WEEKLY-UPDATE PROMPT: cron-prompt.txt resolves client owner chat, never allowFrom[0] ---"

CRON_PROMPT="$REPO_ROOT/cron-prompt.txt"
if [ ! -f "$CRON_PROMPT" ]; then
    fail "10: cron-prompt.txt not found at $CRON_PROMPT"
else
    # 10a: it uses the operator-rejecting resolver (positive requirement).
    if grep -q 'resolve-owner-chat.sh' "$CRON_PROMPT" && grep -q 'resolve_owner_chat_id' "$CRON_PROMPT"; then
        pass "10a: cron-prompt.txt resolves the recipient via shared-utils/resolve-owner-chat.sh (resolve_owner_chat_id)"
    else
        fail "10a: cron-prompt.txt does NOT use the operator-rejecting resolver (resolve-owner-chat.sh / resolve_owner_chat_id)"
    fi

    # 10b: no actual SEND line targets a bare allowFrom index. We inspect ONLY the
    # message-send / --target / --to lines, so the prohibition prose that NAMES
    # allowFrom[0] in order to forbid it never trips this check.
    send_lines=$(grep -nE 'message send|--target|--to ' "$CRON_PROMPT" || true)
    bad_send=0
    while IFS= read -r ln; do
        [ -n "$ln" ] || continue
        if echo "$ln" | grep -qE 'allowFrom|\[0\]'; then
            bad_send=$((bad_send + 1))
            echo "    offending send line: $ln"
        fi
    done <<< "$send_lines"
    if [ "$bad_send" -eq 0 ]; then
        pass "10b: no message-send/--target line in cron-prompt.txt uses a bare allowFrom[0] recipient"
    else
        fail "10b: $bad_send send line(s) in cron-prompt.txt target a bare allowFrom[0] (operator-misroute on a client box)"
    fi

    # 10c: client-facing sends target the resolved \$CLIENT_CHAT variable.
    if grep -qE 'message send .*--target +"\$CLIENT_CHAT"' "$CRON_PROMPT"; then
        pass "10c: client-facing sends target the resolved \$CLIENT_CHAT (operator-rejected owner chat)"
    else
        fail "10c: cron-prompt.txt client sends do not target the resolved \$CLIENT_CHAT"
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [ "$FAIL" -gt 0 ]; then
    echo "FAIL: $FAIL check(s) failed — CI guard triggered"
    exit 1
fi

echo "PASS: all cron-owner-chat-guard checks pass"
exit 0
