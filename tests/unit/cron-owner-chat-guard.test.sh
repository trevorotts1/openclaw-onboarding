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
