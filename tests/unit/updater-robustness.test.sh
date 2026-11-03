#!/usr/bin/env bash
# tests/unit/updater-robustness.test.sh
#
# CI guard for three updater defects that all reproduced on the pre-fix commit:
#
#   (A) update-skills.sh's workspace resolver blamed scripts/onboarding-state.sh
#       for being "absent from this bundle" although the file ships in the repo.
#       The resolver is first called by the write pre-flight, ~1550 lines before
#       the run sources that shim, so obs_resolve_workspace() was undefined every
#       time. It must load the shim when it is reachable and, when it genuinely
#       cannot, say what it checked instead of naming a cause it never verified.
#   (B) shared-utils/lib-frontdoor.sh and shared-utils/git_ff_sync.sh ran git with
#       no deadline. One `git -C <checkout> config --get remote.origin.url` blocked
#       in getcwd wedged a whole update for hours. Every git call must be bounded,
#       a stalled checkout must be skipped with a named line, and the stalled child
#       must not outlive the call.
#   (C) the documented update entrypoint piped curl into bash, so a mid-stream
#       receive failure (rc 56/18) executed the partial script that already
#       arrived. It must fetch to a temp file and run the script only on success.
#
# Exit 0 = all checks pass. Exit 1 = one or more checks failed.
#
# Runs offline: the entrypoint repro uses a loopback HTTP server.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/oc-updater-robustness.XXXXXX")"
SRV_PID=""
cleanup() {
  [ -z "$SRV_PID" ] || kill "$SRV_PID" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT

UPDATE="$REPO_ROOT/update-skills.sh"
FRONTDOOR="$REPO_ROOT/shared-utils/lib-frontdoor.sh"
FFSYNC="$REPO_ROOT/shared-utils/git_ff_sync.sh"

# ── helpers ─────────────────────────────────────────────────────────────────
# Print one function by name from a shell file (top-level definitions end with a
# column-0 "}").
extract_fn() {
  awk -v n="$2" '$0 == n "() {" {f=1} f {print} f && /^}$/ {exit}' "$1"
}

# ── (A) workspace resolver ──────────────────────────────────────────────────
echo "(A) workspace resolver: shim load + honest reason"

if grep -q 'absent from this bundle' "$UPDATE"; then
  fail "A1 the FALLBACK line no longer claims a cause it never checked"
else
  pass "A1 the FALLBACK line no longer claims a cause it never checked"
fi

if extract_fn "$UPDATE" "_oc_load_state_shim" >"$WORK/shim_fn.sh" \
   && [ -s "$WORK/shim_fn.sh" ] \
   && extract_fn "$UPDATE" "oc_resolve_workspace_announced" >>"$WORK/shim_fn.sh" \
   && [ -s "$WORK/shim_fn.sh" ]; then
  pass "A2 resolver functions are extractable for a functional run"
else
  fail "A2 resolver functions are extractable for a functional run"
fi

if [ -s "$WORK/shim_fn.sh" ]; then
  # A bundle that DOES carry the shim, resolved the way the updater calls it
  # with BASH_SOURCE[0] empty (the documented piped entrypoint).
  BUNDLE="$WORK/bundle"
  mkdir -p "$BUNDLE/scripts"
  cp "$REPO_ROOT/scripts/onboarding-state.sh" "$BUNDLE/scripts/"
  cp "$REPO_ROOT/lib-onboarding-state.sh" "$BUNDLE/"
  mkdir -p "$WORK/home-a/.openclaw"
  printf '%s\n' '{"agents":{"entries":{"main":{"workspace":"'"$WORK"'/home-a/ws"}}}}' \
    >"$WORK/home-a/.openclaw/openclaw.json"
  mkdir -p "$WORK/home-a/ws"

  OUT_A="$(
    env -u BASH_SOURCE HOME="$WORK/home-a" ONBOARDING_DIR="$BUNDLE" \
      _SCRIPT_DIR="$WORK/not-the-bundle" \
      bash -c 'unset BASH_SOURCE 2>/dev/null || true; . "$1"; oc_resolve_workspace_announced "test"; ' _ "$WORK/shim_fn.sh" 2>&1
  )" || true
  if printf '%s' "$OUT_A" | grep -q 'resolved via: obs_resolve_workspace() from the onboarding-state.sh shim'; then
    pass "A3 with the shim in the bundle the resolver uses obs_resolve_workspace()"
  else
    fail "A3 with the shim in the bundle the resolver uses obs_resolve_workspace()"
    printf '%s\n' "$OUT_A" | sed 's/^/      /'
  fi
  if printf '%s' "$OUT_A" | grep -q 'absent from this bundle'; then
    fail "A4 the emitted line does not contain 'absent from this bundle'"
  else
    pass "A4 the emitted line does not contain 'absent from this bundle'"
  fi

  # Regression: nothing reachable, no config -> refuse to guess, honest reason.
  # Run from an empty directory so the resolver's $PWD candidate cannot see the
  # repo's own shim.
  mkdir -p "$WORK/home-b"
  OUT_B="$(
    cd "$WORK/home-b" && env -u BASH_SOURCE HOME="$WORK/home-b" ONBOARDING_DIR="$WORK/nothing-here" \
      _SCRIPT_DIR="$WORK/nothing-here" \
      bash -c 'unset BASH_SOURCE 2>/dev/null || true; . "$1"; oc_resolve_workspace_announced "test"; ' _ "$WORK/shim_fn.sh" 2>&1
  )" || true
  if printf '%s' "$OUT_B" | grep -q 'WORKSPACE UNRESOLVED'; then
    pass "A5 with no shim and no config it still refuses to guess"
  else
    fail "A5 with no shim and no config it still refuses to guess"
  fi
  if printf '%s' "$OUT_B" | grep -q '\[workspace\].*->'; then
    fail "A6 it does not print a resolved workspace it did not resolve"
  else
    pass "A6 it does not print a resolved workspace it did not resolve"
  fi
  if printf '%s' "$OUT_B" | grep -q 'absent from this bundle'; then
    fail "A7 the refusal does not claim 'absent from this bundle'"
  else
    pass "A7 the refusal does not claim 'absent from this bundle'"
  fi
else
  fail "A3 with the shim in the bundle the resolver uses obs_resolve_workspace()"
  fail "A4 the emitted line does not contain 'absent from this bundle'"
  fail "A5 with no shim and no config it still refuses to guess"
  fail "A6 it does not print a resolved workspace it did not resolve"
  fail "A7 the refusal does not claim 'absent from this bundle'"
fi

# ── (B) bounded git ────────────────────────────────────────────────────────
echo "(B) bounded git: static + functional hang"

FD_UNBOUNDED="$(grep -cE '(^|[^[:alnum:]_])git -C' "$FRONTDOOR" || true)"
if [ "$FD_UNBOUNDED" = "0" ] && grep -q 'alarm shift' "$FRONTDOOR"; then
  pass "B1 every git call in lib-frontdoor.sh goes through the bounded wrapper"
else
  fail "B1 every git call in lib-frontdoor.sh goes through the bounded wrapper (bare 'git -C' lines: $FD_UNBOUNDED)"
fi

FF_LOOSE="$(grep -E '(^|[^[:alnum:]_])git -C' "$FFSYNC" | grep -vc 'g() {' || true)"
if [ "$FF_LOOSE" = "0" ] && grep -q 'alarm shift' "$FFSYNC"; then
  pass "B2 every git call in git_ff_sync.sh goes through the bounded wrapper"
else
  fail "B2 every git call in git_ff_sync.sh goes through the bounded wrapper (bare lines: ${FF_LOOSE:-?})"
fi

# Functional hang: a 999-setup checkout on the candidate list, and a `git` on
# PATH whose first call never returns. frontdoor_update_999 must RETURN, name the
# skip, and leave no child behind.
FIX="$WORK/home-hang"
mkdir -p "$FIX/Documents/999-setup/.git" \
         "$FIX/Documents/999-setup/CONTROL" \
         "$FIX/Documents/999-setup/.claude/skills/nine-router-setup/scripts" \
         "$WORK/fakebin"
for f in AGENT_INSTALL.md CONTROL/bundled-skills.txt \
         .claude/skills/nine-router-setup/scripts/setup-macos.sh; do
  : >"$FIX/Documents/999-setup/$f"
done
cat >"$WORK/fakebin/git" <<'FAKEGIT'
#!/bin/sh
echo $$ >"$GIT_PID_FILE"
exec sleep 300
FAKEGIT
chmod +x "$WORK/fakebin/git"

START=$(date +%s)
HANG_OUT="$WORK/hang.out"
perl -e 'alarm shift; exec @ARGV' 70 \
  env HOME="$FIX" PATH="$WORK/fakebin:$PATH" GIT_PID_FILE="$WORK/hung.pid" \
      FD_GIT_TIMEOUT=3 OPENCLAW_ROOT="$FIX/.openclaw" \
  bash -c '. "$1"; frontdoor_update_999' _ "$FRONTDOOR" >"$HANG_OUT" 2>&1 || true
ELAPSED=$(($(date +%s) - START))

if [ "$ELAPSED" -lt 60 ]; then
  pass "B3 a never-returning git makes frontdoor_update_999 return (${ELAPSED}s)"
else
  fail "B3 a never-returning git makes frontdoor_update_999 return (${ELAPSED}s)"
fi
if grep -q 'git did not answer' "$HANG_OUT"; then
  pass "B4 the stalled checkout is skipped with a named line"
else
  fail "B4 the stalled checkout is skipped with a named line"
  sed 's/^/      /' "$HANG_OUT" || true
fi
if [ -f "$WORK/hung.pid" ] && kill -0 "$(cat "$WORK/hung.pid")" 2>/dev/null; then
  kill -KILL "$(cat "$WORK/hung.pid")" 2>/dev/null || true
  fail "B5 the stalled git child does not survive the call"
else
  pass "B5 the stalled git child does not survive the call"
fi

# Control: healthy git on the same shape still completes and reports as today.
CTRL="$WORK/home-ok"
REPO_OK="$CTRL/Documents/999-setup"
mkdir -p "$REPO_OK" "$CTRL" "$WORK/trevorotts1"
git init --quiet --bare "$WORK/trevorotts1/999-setup"
git init --quiet -b main "$REPO_OK"
mkdir -p "$REPO_OK/CONTROL" "$REPO_OK/.claude/skills/nine-router-setup/scripts"
: >"$REPO_OK/AGENT_INSTALL.md"
: >"$REPO_OK/CONTROL/bundled-skills.txt"
: >"$REPO_OK/.claude/skills/nine-router-setup/scripts/setup-macos.sh"
git -C "$REPO_OK" -c user.name=t -c user.email=t@t add -A
git -C "$REPO_OK" -c user.name=t -c user.email=t@t commit --quiet -m fixture
git -C "$REPO_OK" remote add origin "file://$WORK/trevorotts1/999-setup"
git -C "$REPO_OK" push --quiet -u origin main

CTRL_OUT="$WORK/control.out"
perl -e 'alarm shift; exec @ARGV' 70 \
  env HOME="$CTRL" PATH="$PATH" FD_GIT_TIMEOUT=20 NINEROUTER_PORT=1 OPENCLAW_ROOT="$CTRL/.openclaw" \
  bash -c '. "$1"; frontdoor_update_999' _ "$FRONTDOOR" >"$CTRL_OUT" 2>&1 || true
if grep -q 'already current' "$CTRL_OUT" && ! grep -q 'git did not answer' "$CTRL_OUT"; then
  pass "B6 healthy git on the same fixture still completes and reports today"
else
  fail "B6 healthy git on the same fixture still completes and reports today"
  sed 's/^/      /' "$CTRL_OUT" || true
fi

# ── (C) documented entrypoints ─────────────────────────────────────────────
echo "(C) documented entrypoints: fetch to temp, run only on success"

PIPE_LINES=$(cat "$REPO_ROOT/UPDATE-PLAYBOOK.md" "$REPO_ROOT/ONBOARDING-TRIGGERS.md" \
  | grep -c 'update-skills\.sh | bash' || true)
if [ "${PIPE_LINES:-0}" = "0" ]; then
  pass "C1 no documented update entrypoint pipes curl into bash"
else
  fail "C1 no documented update entrypoint pipes curl into bash (found $PIPE_LINES)"
fi

DOC_LINES="$(
  cat "$REPO_ROOT/UPDATE-PLAYBOOK.md" "$REPO_ROOT/ONBOARDING-TRIGGERS.md" \
    | grep 'update-skills\.sh' | grep 'raw\.githubusercontent\.com' || true
)"
DOC_BAD=0
DOC_N=0
while IFS= read -r line; do
  [ -n "$line" ] || continue
  DOC_N=$((DOC_N + 1))
  case "$line" in
    *--max-time*) : ;;
    *) DOC_BAD=$((DOC_BAD + 1)) ;;
  esac
  case "$line" in
    *--retry*) : ;;
    *) DOC_BAD=$((DOC_BAD + 1)) ;;
  esac
  case "$line" in
    *-o\ \"\$t\"*) : ;;
    *) DOC_BAD=$((DOC_BAD + 1)) ;;
  esac
done <<EOF
$DOC_LINES
EOF
if [ "$DOC_N" -eq 5 ] && [ "$DOC_BAD" -eq 0 ]; then
  pass "C2 all 5 documented update entrypoints use --max-time, a bounded retry and a temp file"
else
  fail "C2 all 5 documented update entrypoints use --max-time, a bounded retry and a temp file (lines=$DOC_N bad=$DOC_BAD)"
fi

# Functional repro: same documented command against a server that declares a
# Content-Length and closes mid-body. Zero bytes of the partial script may run.
DOC_LINE="$(grep -m1 'curl .*update-skills\.sh' "$REPO_ROOT/UPDATE-PLAYBOOK.md" | sed 's/^ *//' || true)"
[ -n "$DOC_LINE" ] || DOC_LINE="$(grep -m1 'update-skills\.sh' "$REPO_ROOT/UPDATE-PLAYBOOK.md" | sed 's/^ *//' || true)"
RAW_URL='https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/update-skills.sh'

cat >"$WORK/server.py" <<'PYSRV'
import http.server, socketserver, sys
MODE = sys.argv[1]
BODY = b'echo ran > "$MARK"\n'
if MODE == "full":
    BODY += b'echo complete\n'

class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/x-shellscript")
        if MODE == "trunc":
            self.send_header("Content-Length", str(len(BODY) + 4096))
        else:
            self.send_header("Content-Length", str(len(BODY)))
        self.end_headers()
        self.wfile.write(BODY)
        self.wfile.flush()
        if MODE == "trunc":
            self.close_connection = True

    def log_message(self, *a):
        pass

with socketserver.TCPServer(("127.0.0.1", 0), H) as s:
    print(s.server_address[1], flush=True)
    s.serve_forever()
PYSRV

serve_and_get_port() {
  rm -f "$WORK/port"
  python3 -I "$WORK/server.py" "$1" >"$WORK/port" 2>"$WORK/server.err" &
  SRV_PID=$!
  local i=0
  while [ ! -s "$WORK/port" ] && [ "$i" -lt 100 ]; do
    sleep 0.1
    i=$((i + 1))
  done
  cat "$WORK/port" 2>/dev/null || true
}

run_doc_line() {   # $1 = mode, $2 = marker path
  local port line
  port="$(serve_and_get_port "$1")"
  [ -n "$port" ] || { echo "no-port"; return 1; }
  line="${DOC_LINE//$RAW_URL/http://127.0.0.1:$port/update-skills.sh}"
  ( cd "$WORK" && MARK="$2" perl -e 'alarm shift; exec @ARGV' 120 bash -c "$line" ) \
    >"$WORK/run-$1.out" 2>&1
  local rc=$?
  kill "$SRV_PID" 2>/dev/null || true
  wait "$SRV_PID" 2>/dev/null || true
  SRV_PID=""
  return "$rc"
}

rm -f "$WORK/mark-full" "$WORK/mark-trunc"
run_doc_line full "$WORK/mark-full" || true
if [ -f "$WORK/mark-full" ]; then
  pass "C3 control: a complete download runs the script"
else
  fail "C3 control: a complete download runs the script"
  sed 's/^/      /' "$WORK/run-full.out" || true
fi

run_doc_line trunc "$WORK/mark-trunc" || true
if [ -f "$WORK/mark-trunc" ]; then
  fail "C4 a truncated download executes zero bytes of the partial script"
  sed 's/^/      /' "$WORK/run-trunc.out" || true
else
  pass "C4 a truncated download executes zero bytes of the partial script"
fi

# ── summary ────────────────────────────────────────────────────────────────
echo ""
echo "  $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
