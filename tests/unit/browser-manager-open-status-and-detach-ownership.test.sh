#!/usr/bin/env bash
# Regression suite for 06-ghl-install-pages/tools/browser_manager.sh — T0-16 and
# T0-17. Both were places the manager reported a session state that did not exist.
#
#   T0-16 — `AB ... open ... || true` forced the open to succeed. If the browser
#     binary was absent, timed out, or returned any non-zero status, the failed
#     open was still counted toward the circuit-breaker window, bm_ensure returned
#     zero, and the `ensure` verb printed ENSURED. Every later reader, including
#     the breaker ledger, inherited a false session state.
#
#   T0-17 — `run-detached` ran bm_ensure in the PARENT and then printed that the
#     detached child owned the lock, lease, TTL and teardown. It did not: they
#     were all created in the parent shell, and when the parent reached end of
#     file its EXIT trap tore down the session the child was still using.
#
# Hermetic: a fake `agent-browser` on PATH, a scratch TMPDIR (so LOCKDIR and the
# breaker ledger are scratch) and a scratch HOME (so no onboarded root is found
# and PARK_DIR falls back into the scratch LOCKDIR). No network, no real browser,
# nothing outside the temp directory is read or written.
#
# Run: bash tests/unit/browser-manager-open-status-and-detach-ownership.test.sh

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BM="$REPO_ROOT/06-ghl-install-pages/tools/browser_manager.sh"
[ -f "$BM" ] || { echo "FATAL: browser_manager.sh not found at $BM" >&2; exit 1; }

PASS=0; FAIL=0
ok()   { echo "  ok   — $1"; PASS=$((PASS+1)); }
bad()  { echo "  FAIL — $1"; FAIL=$((FAIL+1)); }
check(){ if [ "$2" = "$3" ]; then ok "$1 ($2)"; else bad "$1 (want '$3', got '$2')"; fi; }

ROOT="$(mktemp -d "${TMPDIR:-/tmp}/bm-suite.XXXXXX")"
cleanup() { rm -rf "$ROOT"; }
trap cleanup EXIT

# ── fake agent-browser ────────────────────────────────────────────────────────
# One binary, two behaviours, selected by BM_TEST_OPEN_RC. Everything except
# `open` always succeeds so the manager's other calls (session list, close,
# state clear) behave normally.
mkfake() {
  local bindir="$1"
  mkdir -p "$bindir"
  cat > "$bindir/agent-browser" <<'FAKE'
#!/usr/bin/env bash
# Test double for agent-browser. Records every invocation, and fails `open` with
# the status the test asked for.
printf '%s\n' "$*" >> "${BM_TEST_CALLLOG:-/dev/null}"
verb=""
for a in "$@"; do
  case "$a" in
    --*|-*) continue ;;
    *) if [ -z "$verb" ]; then case "$a" in
         open|close|session|state|get|screenshot|console|eval|snapshot|wait|find|fill|--version) verb="$a" ;;
       esac; fi ;;
  esac
done
case " $* " in
  *" --version "*) echo "agent-browser 0.27.0"; exit 0 ;;
esac
case "$verb" in
  open)    exit "${BM_TEST_OPEN_RC:-0}" ;;
  session) echo "[]"; exit 0 ;;
  *)       exit 0 ;;
esac
FAKE
  chmod +x "$bindir/agent-browser"
}

# Run the manager verb in an isolated sandbox. Prints stdout+stderr; returns rc.
# $1 = sandbox name, $2 = open exit code, rest = manager argv
run_bm() {
  local name="$1" open_rc="$2"; shift 2
  local sb="$ROOT/$name"
  mkdir -p "$sb/tmp" "$sb/home" "$sb/bin"
  mkfake "$sb/bin"
  env -i \
    PATH="$sb/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
    HOME="$sb/home" \
    TMPDIR="$sb/tmp" \
    BM_TEST_OPEN_RC="$open_rc" \
    BM_TEST_CALLLOG="$sb/calls.log" \
    AGENT_BROWSER_HEADED=false \
    AB_OPEN_MAX_ATTEMPTS=2 \
    AB_OPEN_RETRY_BASE_S=0 \
    AB_DETACH_READY_TIMEOUT_S=20 \
    bash "$BM" "$@" 2>&1
}

sandbox_breaker_lines() {
  local sb="$ROOT/$1"
  local f
  f="$(ls "$sb/tmp/agent-browser/breaker/"*.count 2>/dev/null | head -1)"
  if [ -z "$f" ] || [ ! -f "$f" ]; then echo 0; return 0; fi
  /usr/bin/wc -l < "$f" | tr -d ' '
}

echo ""
echo "═══ browser_manager.sh — open status (T0-16) ═══"

# ── 1. A FAILED open must not report ENSURED, and must not count on the breaker
OUT="$(run_bm fail-open 3 ensure)"; RC=$?
check "failed open -> non-zero exit" "$( [ "$RC" -ne 0 ] && echo yes || echo no )" "yes"
case "$OUT" in
  *ENSURED*) bad "failed open printed ENSURED" ;;
  *)         ok  "failed open printed no ENSURED line" ;;
esac
case "$OUT" in
  *"browser open failed"*) ok "failed open reported the failure" ;;
  *)                       bad "failed open gave no failure line (got: ${OUT:0:160})" ;;
esac
check "failed open recorded 0 opens on the breaker" "$(sandbox_breaker_lines fail-open)" "0"

# ── 2. A SUCCESSFUL open still reports ENSURED and counts exactly once
OUT="$(run_bm good-open 0 ensure)"; RC=$?
check "successful open -> exit 0" "$RC" "0"
case "$OUT" in
  *ENSURED*) ok "successful open printed ENSURED" ;;
  *)         bad "successful open lost its ENSURED line (got: ${OUT:0:160})" ;;
esac
check "successful open recorded exactly 1 open on the breaker" "$(sandbox_breaker_lines good-open)" "1"

# ── 3. The retry is bounded and really retries
OUT="$(run_bm retry 4 ensure)"; RC=$?
check "retried failure still exits non-zero" "$( [ "$RC" -ne 0 ] && echo yes || echo no )" "yes"
OPENS="$(/usr/bin/grep -c ' open ' "$ROOT/retry/calls.log" 2>/dev/null || echo 0)"
check "AB_OPEN_MAX_ATTEMPTS=2 produced exactly 2 open attempts" "$OPENS" "2"

echo ""
echo "═══ browser_manager.sh — detached ownership (T0-17) ═══"

# ── 4. The detached child, not the parent, holds the lease.
# The child sleeps; the parent prints DETACHED and exits. If the parent still
# owned the session its EXIT trap would tear the lease down — the pre-fix
# behaviour. The lease must still be on disk after the parent is gone.
SB="detach"
mkdir -p "$ROOT/$SB/tmp" "$ROOT/$SB/home" "$ROOT/$SB/bin"
mkfake "$ROOT/$SB/bin"
CHILD="$ROOT/$SB/child.sh"
cat > "$CHILD" <<CHILDEOF
#!/usr/bin/env bash
sleep 3
: > "$ROOT/$SB/child-finished"
CHILDEOF
chmod +x "$CHILD"

# NOTE: capture to a FILE, never `$( )`. The detached child inherits the
# parent's stdout, so a command substitution would block until the CHILD exits
# too — and this case is specifically about what is true while the child is
# still running.
env -i \
  PATH="$ROOT/$SB/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
  HOME="$ROOT/$SB/home" TMPDIR="$ROOT/$SB/tmp" \
  BM_TEST_OPEN_RC=0 BM_TEST_CALLLOG="$ROOT/$SB/calls.log" \
  AGENT_BROWSER_HEADED=false AB_DETACH_READY_TIMEOUT_S=20 \
  bash "$BM" run-detached -- bash "$CHILD" > "$ROOT/$SB/parent.out" 2>&1
RC=$?
OUT="$(cat "$ROOT/$SB/parent.out")"
check "run-detached -> exit 0" "$RC" "0"
case "$OUT" in
  *DETACHED*) ok "run-detached printed the ownership line" ;;
  *)          bad "run-detached printed no ownership line (got: ${OUT:0:200})" ;;
esac

# Parent has exited. Give it a moment, then look for the child's lease.
sleep 1
LEASES="$(ls "$ROOT/$SB/tmp/agent-browser/leases/"*.lease 2>/dev/null | /usr/bin/wc -l | tr -d ' ')"
check "the child's lease survives the parent's exit" "$LEASES" "1"
if [ -f "$ROOT/$SB/child-finished" ]; then
  bad "the child finished before the lease was checked — test raced, tighten the sleep"
else
  ok "the child was still running when the lease was checked"
fi

# Let the child finish and confirm IT tears the lease down on its own exit.
sleep 4
check "the child ran to completion" "$( [ -f "$ROOT/$SB/child-finished" ] && echo yes || echo no )" "yes"
LEASES_AFTER="$(ls "$ROOT/$SB/tmp/agent-browser/leases/"*.lease 2>/dev/null | /usr/bin/wc -l | tr -d ' ')"
check "the child tore its own lease down when it exited" "$LEASES_AFTER" "0"

# ── 5. A child that cannot acquire the session must not be announced as detached
mkdir -p "$ROOT/detach-fail/tmp" "$ROOT/detach-fail/home" "$ROOT/detach-fail/bin"
mkfake "$ROOT/detach-fail/bin"
env -i \
  PATH="$ROOT/detach-fail/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
  HOME="$ROOT/detach-fail/home" TMPDIR="$ROOT/detach-fail/tmp" \
  BM_TEST_OPEN_RC=5 BM_TEST_CALLLOG="$ROOT/detach-fail/calls.log" \
  AGENT_BROWSER_HEADED=false AB_OPEN_MAX_ATTEMPTS=1 AB_OPEN_RETRY_BASE_S=0 \
  AB_DETACH_READY_TIMEOUT_S=20 \
  bash "$BM" run-detached -- /bin/echo should-not-run > "$ROOT/detach-fail/parent.out" 2>&1
RC=$?
OUT="$(cat "$ROOT/detach-fail/parent.out")"
check "detach with a failing open -> non-zero exit" "$( [ "$RC" -ne 0 ] && echo yes || echo no )" "yes"
case "$OUT" in
  *DETACHED*) bad "a child that never acquired the session was announced as DETACHED" ;;
  *)          ok  "no DETACHED line for a child that never acquired the session" ;;
esac
case "$OUT" in
  *"could not acquire the session"*|*"exited before signalling readiness"*)
    ok "the failed detach said why" ;;
  *) bad "the failed detach gave no reason (got: ${OUT:0:200})" ;;
esac

echo ""
echo "═══ Result: $PASS passed | $FAIL failed ═══"
[ "$FAIL" -gt 0 ] && exit 1
exit 0
