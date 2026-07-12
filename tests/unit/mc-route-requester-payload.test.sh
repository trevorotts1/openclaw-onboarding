#!/usr/bin/env bash
# tests/unit/mc-route-requester-payload.test.sh
#
# P1-04 (trust engine) — the signed router helper mc-route.sh must pass the
# ORIGINATING client chat id through to the Command Center ingest payload so the
# report-back loop can acknowledge/progress/done back to the client — but ONLY
# when MC_ROUTE_REQUESTER_CHAT_ID is set. An operator/internal route (no chat id)
# must NOT carry requester_chat_id, or the box would try to "report back" to a
# phantom chat.
#
# The three shipped copies of the helper are KEEP-IN-SYNC:
#   • scripts/mc-route.sh                     (the source of truth, run here)
#   • the stamped block in apply-fleet-standards.sh
#   • the stamped block in apply-routing-fix.sh
# The install-doc/consistency tests already assert those three stay byte-aligned;
# this test drives the REAL scripts/mc-route.sh end-to-end with a stubbed `curl`
# that captures the exact JSON body the helper would POST.
#
# Assertions (payload captured from the real helper):
#   (A) NO MC_ROUTE_REQUESTER_CHAT_ID           -> payload OMITS requester_chat_id + requester_channel
#   (B) MC_ROUTE_REQUESTER_CHAT_ID set          -> payload carries requester_chat_id + requester_channel:telegram
#   (C) chat id + MC_ROUTE_REQUESTER_CHANNEL     -> the named channel passes through
#   (D) whitespace-only chat id                  -> stripped to empty -> OMITTED (never report on a phantom chat)
#
# FAIL-FIRST: against the pre-P1-04 helper (no REQUESTER_* handling) assertion B/C
# would find no requester_chat_id in the payload and fail. With the fix they pass.

set -uo pipefail

PASS=0
FAIL=0
ERRORS=()

ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); ERRORS+=("$1"); }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MC_ROUTE="$REPO_ROOT/scripts/mc-route.sh"

echo ""
echo "=== mc-route.sh requester chat-id payload guard (P1-04 trust engine) ==="
echo ""

if [ ! -f "$MC_ROUTE" ]; then
  echo "  FAIL: scripts/mc-route.sh not found at $MC_ROUTE"
  exit 1
fi

# ── Hermetic sandbox: a stub `curl` that captures the POSTed body, an empty HOME
#    so the helper's secret resolution reads NO real dotenv store. ──────────────
WORK="$(mktemp -d "${TMPDIR:-/tmp}/mc-route-test.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
CAPTURE="$WORK/captured-body.json"

mkdir -p "$WORK/bin" "$WORK/home"
cat > "$WORK/bin/curl" <<STUB
#!/usr/bin/env bash
# Stub curl: find the --data-binary @<file> argument, copy its contents to the
# capture path, and emit a fake 200 in the exact "body\n%{http_code}" shape the
# real helper's -w format produces so its success loop breaks on the first try.
CAP="$CAPTURE"
prev=""
for a in "\$@"; do
  case "\$a" in
    @*) cp "\${a#@}" "\$CAP" 2>/dev/null || true ;;
  esac
  case "\$prev" in
    --data-binary|-d|--data) case "\$a" in @*) cp "\${a#@}" "\$CAP" 2>/dev/null || true ;; esac ;;
  esac
  prev="\$a"
done
printf '{"ok":true,"task_id":"stub"}\n200'
STUB
chmod +x "$WORK/bin/curl"

# Run the real helper with the stub curl first on PATH and a clean HOME.
run_helper() {
  rm -f "$CAPTURE"
  env PATH="$WORK/bin:$PATH" HOME="$WORK/home" \
      MC_ROUTE_INGEST_URL="http://127.0.0.1:4000/api/tasks/ingest" \
      "$@" \
      bash "$MC_ROUTE" sales "Test task" "a client asked for this" >/dev/null 2>&1 || true
}

# ── (A) no chat id -> requester fields OMITTED ───────────────────────────────
echo "--- (A) no MC_ROUTE_REQUESTER_CHAT_ID -> requester fields omitted ---"
run_helper
if [ ! -f "$CAPTURE" ]; then
  fail "(A) helper produced no captured payload (stub curl not invoked)"
elif grep -q 'requester_chat_id' "$CAPTURE"; then
  fail "(A) payload MUST NOT contain requester_chat_id when the env var is unset"
  echo "      captured: $(cat "$CAPTURE")"
else
  ok "(A) payload omits requester_chat_id for an operator/internal route"
fi

# ── (B) chat id set -> requester_chat_id + default channel telegram ──────────
echo "--- (B) MC_ROUTE_REQUESTER_CHAT_ID set -> requester_chat_id + channel telegram ---"
run_helper MC_ROUTE_REQUESTER_CHAT_ID="987654321"
if [ ! -f "$CAPTURE" ]; then
  fail "(B) helper produced no captured payload"
else
  body="$(cat "$CAPTURE")"
  # LLM-of-content is not needed here: this asserts exact JSON key/value tokens
  # emitted by the helper (navigation/structure), which is grep's legitimate role.
  if printf '%s' "$body" | grep -q '"requester_chat_id":"987654321"'; then
    ok "(B) payload carries requester_chat_id verbatim"
  else
    fail "(B) payload MUST carry requester_chat_id:987654321 when set — got: $body"
  fi
  if printf '%s' "$body" | grep -q '"requester_channel":"telegram"'; then
    ok "(B) payload defaults requester_channel to telegram"
  else
    fail "(B) payload MUST default requester_channel to telegram — got: $body"
  fi
fi

# ── (C) explicit channel passes through ──────────────────────────────────────
echo "--- (C) MC_ROUTE_REQUESTER_CHANNEL passes through ---"
run_helper MC_ROUTE_REQUESTER_CHAT_ID="111" MC_ROUTE_REQUESTER_CHANNEL="ceo-chat"
if printf '%s' "$(cat "$CAPTURE" 2>/dev/null)" | grep -q '"requester_channel":"ceo-chat"'; then
  ok "(C) an explicit requester_channel passes through unchanged"
else
  fail "(C) explicit requester_channel MUST pass through — got: $(cat "$CAPTURE" 2>/dev/null)"
fi

# ── (D) whitespace-only chat id -> omitted ───────────────────────────────────
echo "--- (D) whitespace-only chat id -> stripped -> omitted ---"
run_helper MC_ROUTE_REQUESTER_CHAT_ID="   "
if grep -q 'requester_chat_id' "$CAPTURE" 2>/dev/null; then
  fail "(D) a whitespace-only chat id MUST be stripped and omitted — got: $(cat "$CAPTURE")"
else
  ok "(D) whitespace-only chat id is stripped away (never report on a phantom chat)"
fi

echo ""
echo "=== mc-route requester payload guard: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "Failures:"
  for e in "${ERRORS[@]}"; do echo "  - $e"; done
  exit 1
fi
exit 0
