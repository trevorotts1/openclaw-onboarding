#!/usr/bin/env bash
# vps-startup-gateway-first.test.sh -- D08: the Hostinger and Contabo container start-up
# templates (platform/vps/{hostinger,contabo}/container-startup.sh) must
#   1. call wait-gateway-owner-stale.sh right before the final exec,
#   2. start pm2 resurrect and the GHL MCP autostart only after the gateway answers /healthz 200,
#      and never run the openclaw CLI before that (2026.10.1 offline-maintenance lock race),
#   3. (Contabo) relink 999-setup, .claude, .local into <root>/persist-home, idempotently,
#   4. (Hostinger) call hostinger-wrapper-patch.py if present, fail-soft.
# Hermetic: fake node/pm2/openclaw on PATH, a fake gateway on a free loopback port, temp dirs.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 9
REPO="$PWD"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   - %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL - %s\n' "$1"; }
TMP="$(mktemp -d "${TMPDIR:-/tmp}/vps-startup-XXXXXX")"; trap 'rm -rf "$TMP"' EXIT
# CT_UNDER_TEST points the Contabo assertions at another copy of the template (see the
# negative-control block at the end); CI leaves it unset and tests the repo's own file.
CT="${CT_UNDER_TEST:-$REPO/platform/vps/contabo/container-startup.sh}"
HG="$REPO/platform/vps/hostinger/container-startup.sh"
WAIT="$REPO/platform/vps/wait-gateway-owner-stale.sh"
HWP="$REPO/platform/vps/hostinger/hostinger-wrapper-patch.py"

free_port() { python3 -I -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])'; }

# Fake gateway: starts listening after $2 seconds, then logs "healthz-up" to events file $1.
fake_gateway() { # events delay port
  python3 -I - "$1" "$2" "$3" <<'PY' &
import sys, time, http.server
ev, delay, port = sys.argv[1], float(sys.argv[2]), int(sys.argv[3])
time.sleep(delay)
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == "/healthz" else 404); self.end_headers(); self.wfile.write(b'{"ok":true}')
    def log_message(self, *a): pass
srv = http.server.HTTPServer(("127.0.0.1", port), H)
open(ev, "a").write("healthz-up\n")
srv.timeout = 1
end = time.time() + 40
while time.time() < end: srv.handle_request()
PY
  GW_PID=$!
}

# mk_box <name>: fake bin dir + events file. node/pm2/openclaw only record to events.
mk_box() {
  B="$TMP/$1"; mkdir -p "$B/bin"; EV="$B/events"; : > "$EV"
  printf '#!/bin/sh\necho exec-node >> %s\n' "$EV" > "$B/bin/node"
  printf '#!/bin/sh\necho "pm2 $1" >> %s\nexit 1\n' "$EV" > "$B/bin/pm2"
  printf '#!/bin/sh\necho openclaw-cli >> %s\n' "$EV" > "$B/bin/openclaw"
  printf '#!/bin/sh\necho wait-script >> %s\nexit 0\n' "$EV" > "$B/wait.sh"
  chmod +x "$B"/bin/* "$B/wait.sh"
}
line_of() { grep -n -m1 -x -- "$1" "$EV" | cut -d: -f1; }
wait_for() { local i; for i in $(seq 1 150); do grep -q -x -- "$1" "$EV" && return 0; sleep 0.1; done; return 1; }

# ---------------------------------------------------------------- Contabo
mk_box ct1; OC="$B/home/.openclaw"; mkdir -p "$OC/scripts"
printf '#!/bin/sh\necho autostart >> %s\nopenclaw mcp list\n' "$EV" > "$OC/scripts/ghl-mcp-autostart.sh"
PORT=$(free_port); fake_gateway "$EV" 3 "$PORT"
HOME="$B/home" OPENCLAW_ROOT="$OC" PATH="$B/bin:/usr/bin:/bin" OPENCLAW_GATEWAY_PORT="$PORT" \
  GW_READY_CAP=30 GW_WAIT_SCRIPT="$B/wait.sh" bash "$CT" >/dev/null 2>&1
rc=$?
[ "$rc" = 0 ] && ok "contabo: template exits 0" || bad "contabo: rc=$rc"
w=$(line_of wait-script); x=$(line_of exec-node)
[ -n "$w" ] && [ -n "$x" ] && [ "$w" -lt "$x" ] && ok "contabo: wait-gateway-owner-stale runs before the final exec" || bad "contabo: wait not before exec ($(tr '\n' ' ' < "$EV"))"
wait_for "pm2 resurrect"; sleep 0.3
u=$(line_of healthz-up); r=$(line_of "pm2 resurrect"); a=$(line_of autostart); c=$(line_of openclaw-cli)
[ -n "$u" ] && [ -n "$r" ] && [ "$u" -lt "$r" ] && ok "contabo: pm2 resurrect only after /healthz 200" || bad "contabo: pm2 before gateway ($(tr '\n' ' ' < "$EV"))"
# W07 retirement: the template no longer invokes the community autostart at
# all, so the ordering question is moot. Assert the stronger fact instead.
if [ -z "$a" ]; then ok "contabo: community autostart never invoked (retired)"; else bad "contabo: community autostart still invoked ($(tr '\n' ' ' < "$EV"))"; fi
if [ -z "$c" ]; then ok "contabo: no openclaw CLI call at all (autostart retired)"; elif [ -n "$u" ] && [ "$u" -lt "$c" ]; then ok "contabo: no openclaw CLI call before /healthz 200"; else bad "contabo: CLI before gateway ($(tr '\n' ' ' < "$EV"))"; fi
kill "$GW_PID" 2>/dev/null; wait "$GW_PID" 2>/dev/null

# gateway never answers: the cap ends the wait, pm2 still resurrects, the CLI-calling autostart is skipped
mk_box ct2; OC="$B/home/.openclaw"; mkdir -p "$OC/scripts"
printf '#!/bin/sh\necho autostart >> %s\nopenclaw mcp list\n' "$EV" > "$OC/scripts/ghl-mcp-autostart.sh"
PORT=$(free_port)
HOME="$B/home" OPENCLAW_ROOT="$OC" PATH="$B/bin:/usr/bin:/bin" OPENCLAW_GATEWAY_PORT="$PORT" GW_READY_CAP=0 bash "$CT" >/dev/null 2>&1
wait_for "pm2 resurrect"; sleep 0.5
grep -q -x "pm2 resurrect" "$EV" && ok "contabo: pm2 resurrect still runs when the cap passes" || bad "contabo: no pm2 after cap"
if grep -q -x -e autostart -e openclaw-cli "$EV"; then bad "contabo: autostart/CLI ran without a healthy gateway"; else ok "contabo: autostart (CLI) skipped when the gateway never answered"; fi

# persist-home relink: real dirs merged without overwrite, links made, second run is a no-op.
# .claude/a DIFFERS between the live folder and the persistent copy, so .claude is the
# conflict case (see the dedicated blocks below): it must be refused and kept, not linked.
mk_box ct3; H="$B/home"; OC="$H/.openclaw"; mkdir -p "$OC/persist-home/.claude" "$H/999-setup" "$H/.claude" "$H/.local/lib"
echo repo > "$H/999-setup/README"; echo layer > "$H/.claude/a"; echo layer-only > "$H/.claude/b"; echo persisted > "$OC/persist-home/.claude/a"; echo pkg > "$H/.local/lib/p"
run_ct3() { HOME="$H" OPENCLAW_ROOT="$OC" PATH="$B/bin:/usr/bin:/bin" GW_READY_CAP=0 bash "$CT" >/dev/null 2>&1; }
run_ct3; rc1=$?
ok_links=1
for n in 999-setup .local; do [ -L "$H/$n" ] && [ "$(readlink "$H/$n")" = "$OC/persist-home/$n" ] || ok_links=0; done
[ "$rc1" = 0 ] && [ "$ok_links" = 1 ] && ok "contabo: 999-setup, .local linked into persist-home" || bad "contabo: relink failed (rc=$rc1)"
[ ! -L "$H/.claude" ] && [ -d "$H/.claude" ] && [ -f "$OC/persist-home/.claude/a" ] && [ -f "$H/.claude/a" ] \
  && ok "contabo: a differing file refuses that folder's relink and keeps both copies" || bad "contabo: conflict destroyed a copy or was linked anyway"
[ "$(cat "$H/999-setup/README")" = repo ] && [ "$(cat "$H/.local/lib/p")" = pkg ] && [ "$(cat "$H/.claude/b")" = layer-only ] && ok "contabo: real folder contents preserved through the link" || bad "contabo: contents lost"
[ "$(cat "$OC/persist-home/.claude/a")" = persisted ] && [ "$(cat "$H/.claude/a")" = layer ] && ok "contabo: existing persistent file is not overwritten (content-verified merge)" || bad "contabo: persistent file overwritten"
[ -f "$OC/logs/persist-home-conflict.log" ] && grep -q 'CONFLICT' "$OC/logs/persist-home-conflict.log" \
  && ok "contabo: the conflict is written to logs/persist-home-conflict.log" || bad "contabo: conflict not logged"
before=$(cd "$OC/persist-home" && find . | sort | tr '\n' ' '); run_ct3; rc2=$?
after=$(cd "$OC/persist-home" && find . | sort | tr '\n' ' ')
[ "$rc2" = 0 ] && [ "$before" = "$after" ] && [ "$(readlink "$H/999-setup")" = "$OC/persist-home/999-setup" ] \
  && [ ! -L "$H/.claude" ] && [ "$(cat "$H/.claude/a")" = layer ] && [ "$(cat "$OC/persist-home/.claude/a")" = persisted ] && ok "contabo: relink is idempotent" || bad "contabo: second run changed state"

# --- conflict-preserving relink, one discriminating case per block -----------------------
# run_ct <boxname>: run the template on that box's fake HOME/root.
run_ct() { HOME="$1/home" OPENCLAW_ROOT="$1/home/.openclaw" PATH="$1/bin:/usr/bin:/bin" GW_READY_CAP=0 bash "$CT" >/dev/null 2>&1; }

# (1) IDENTICAL same-path file everywhere -> all five entries relink.
mk_box ct4; H="$B/home"; OC="$H/.openclaw"
mkdir -p "$H/999-setup" "$H/.claude" "$H/.local" "$H/.agent-browser" "$H/Downloads/openclaw-master-files"
for n in 999-setup .claude .local .agent-browser Downloads/openclaw-master-files; do mkdir -p "$OC/persist-home/$n"; echo same > "$H/$n/f"; echo same > "$OC/persist-home/$n/f"; done
run_ct "$B"
all5=1
for n in 999-setup .claude .local .agent-browser Downloads/openclaw-master-files; do
  [ -L "$H/$n" ] && [ "$(readlink "$H/$n")" = "$OC/persist-home/$n" ] || all5=0
done
[ "$all5" = 1 ] && ok "contabo: identical files relink all five entries (incl. nested Downloads, .agent-browser)" || bad "contabo: not all five entries relinked"
[ "$(cat "$H/Downloads/openclaw-master-files/f")" = same ] && ok "contabo: master-files content readable through the nested link" || bad "contabo: nested link unreadable"
[ ! -e "$OC/logs/persist-home-conflict.log" ] && ok "contabo: a clean merge writes no conflict log" || bad "contabo: conflict log written on a clean run"

# (2) MISSING in the persistent copy -> the live file is copied across, then the folder links.
mk_box ct5; H="$B/home"; OC="$H/.openclaw"
mkdir -p "$H/999-setup" "$OC/persist-home/999-setup" "$H/.claude" "$H/.local" "$H/.agent-browser" "$H/Downloads/openclaw-master-files"
echo live-only > "$H/999-setup/new"; echo old > "$OC/persist-home/999-setup/old"
run_ct "$B"
[ -L "$H/999-setup" ] && [ "$(cat "$OC/persist-home/999-setup/new")" = live-only ] && [ "$(cat "$OC/persist-home/999-setup/old")" = old ] \
  && ok "contabo: a file absent from the persistent copy is carried across (both files kept)" || bad "contabo: live-only file lost or folder not linked"

# (3) DIFFERING same-path file -> CONFLICT: no link, both copies kept, boot still ends at the exec.
mk_box ct6; H="$B/home"; OC="$H/.openclaw"
mkdir -p "$H/.claude" "$OC/persist-home/.claude"
echo live-new > "$H/.claude/state"; echo persist-old > "$OC/persist-home/.claude/state"
run_ct "$B"; rc6=$?
[ "$rc6" = 0 ] && grep -q -x exec-node "$EV" && ok "contabo: a conflict is fail-soft (rc=0, gateway exec still reached)" || bad "contabo: conflict aborted boot (rc=$rc6)"
[ ! -L "$H/.claude" ] && [ -d "$H/.claude" ] && ok "contabo: a conflicting folder is not relinked (crash-loop avoided)" || bad "contabo: conflicting folder was linked anyway"
[ "$(cat "$H/.claude/state")" = live-new ] && [ "$(cat "$OC/persist-home/.claude/state")" = persist-old ] \
  && ok "contabo: a differing file keeps BOTH copies (live kept, persistent not overwritten)" || bad "contabo: a differing file was destroyed"
grep -q 'CONFLICT ./state' "$OC/logs/persist-home-conflict.log" 2>/dev/null \
  && ok "contabo: the conflicting path is named in logs/persist-home-conflict.log" || bad "contabo: conflict path not logged"
# idempotent: a second boot repeats the refusal and still destroys nothing
run_ct "$B"
[ "$(cat "$H/.claude/state")" = live-new ] && [ "$(cat "$OC/persist-home/.claude/state")" = persist-old ] && [ ! -L "$H/.claude" ] \
  && ok "contabo: a second boot with the same conflict is idempotent" || bad "contabo: second conflicting boot changed state"

# (4) NESTED Downloads entry: the parent folder is created and only that subfolder is linked.
mk_box ct7; H="$B/home"; OC="$H/.openclaw"
mkdir -p "$H/Downloads/openclaw-master-files" "$OC/persist-home/Downloads/openclaw-master-files"
echo corpus > "$H/Downloads/openclaw-master-files/x.md"; echo corpus > "$OC/persist-home/Downloads/openclaw-master-files/x.md"
mkdir -p "$H/Downloads/other"; echo keep > "$H/Downloads/other/keep"
run_ct "$B"
[ -L "$H/Downloads/openclaw-master-files" ] && [ -d "$H/Downloads" ] && [ ! -L "$H/Downloads" ] \
  && ok "contabo: nested Downloads/openclaw-master-files links without linking its parent" || bad "contabo: nested Downloads entry not relinked"
[ -f "$H/Downloads/other/keep" ] && [ ! -L "$H/Downloads/other" ] && ok "contabo: unrelated sibling under Downloads is untouched" || bad "contabo: a Downloads sibling was moved or linked"

# (5) MISSING live entry but an empty persistent copy: the link is made, nothing to merge.
mk_box ct8; H="$B/home"; OC="$H/.openclaw"
mkdir -p "$OC/persist-home/999-setup"
run_ct "$B"
[ -L "$H/999-setup" ] && ok "contabo: an entry absent from the live layer is linked from the persistent copy" || bad "contabo: absent live entry not linked"

# ---------------------------------------------------------------- Hostinger
mk_box hg1; D="$B/data"; mkdir -p "$D/.openclaw/scripts"
printf '#!/usr/bin/env python3\nopen("%s","a").write("patcher\\n")\nraise SystemExit(1)\n' "$EV" > "$D/.openclaw/scripts/hostinger-wrapper-patch.py"
PORT=$(free_port); fake_gateway "$EV" 3 "$PORT"
HOME="$D" OPENCLAW_DATA="$D" PATH="$B/bin:/usr/bin:/bin" OPENCLAW_GATEWAY_PORT="$PORT" GW_READY_CAP=30 GW_WAIT_SCRIPT="$B/wait.sh" bash "$HG" >/dev/null 2>&1
rc=$?
[ "$rc" = 0 ] && ok "hostinger: template exits 0 even when the patcher fails (fail-soft)" || bad "hostinger: rc=$rc"
p=$(line_of patcher); w=$(line_of wait-script); x=$(line_of exec-node)
[ -n "$p" ] && [ -n "$w" ] && [ -n "$x" ] && [ "$p" -lt "$x" ] && [ "$w" -lt "$x" ] && ok "hostinger: patcher and wait-gateway-owner-stale both run before the final exec" || bad "hostinger: order ($(tr '\n' ' ' < "$EV"))"
wait_for "pm2 resurrect"; sleep 0.3
u=$(line_of healthz-up); r=$(line_of "pm2 resurrect")
[ -n "$u" ] && [ -n "$r" ] && [ "$u" -lt "$r" ] && ok "hostinger: pm2 resurrect only after /healthz 200" || bad "hostinger: pm2 before gateway ($(tr '\n' ' ' < "$EV"))"
kill "$GW_PID" 2>/dev/null; wait "$GW_PID" 2>/dev/null
# no patcher present: the template just continues
mk_box hg2; D="$B/data"; mkdir -p "$D"
HOME="$D" OPENCLAW_DATA="$D" PATH="$B/bin:/usr/bin:/bin" GW_READY_CAP=0 GW_WAIT_SCRIPT="$B/wait.sh" bash "$HG" >/dev/null 2>&1
[ "$?" = 0 ] && grep -q -x exec-node "$EV" && ok "hostinger: no patcher present is fine" || bad "hostinger: failed without a patcher"

# installer copies the wait script and the patcher beside container-startup.sh
mk_box hg3; P="$B/openclaw-x"; mkdir -p "$P"
printf 'services:\n  openclaw:\n    image: ghcr.io/hostinger/hvps-openclaw:latest\n    volumes:\n      - ./data:/data\n' > "$P/docker-compose.yml"
PATH="$B/bin:/usr/bin:/bin" bash "$REPO/platform/vps/hostinger/install-startup-hook.sh" "$P" >/dev/null 2>&1
S="$P/data/.openclaw/scripts"
[ -x "$S/wait-gateway-owner-stale.sh" ] && [ -x "$S/hostinger-wrapper-patch.py" ] && [ -f "$S/container-startup.sh" ] && ok "hostinger: install-startup-hook copies the wait script and the patcher" || bad "hostinger: installer did not copy ($(ls "$S" 2>&1 | tr '\n' ' '))"

# ---------------------------------------------------------------- wait script
mk_box w1; LK="$B/locks"; mkdir -p "$LK"; export OPENCLAW_ROOT="$B/oc"
t0=$(date +%s); GW_WAIT_LOCKDIR="$LK" GW_WAIT_STALE=5 GW_WAIT_CAP=20 bash "$WAIT"; rc=$?; t1=$(date +%s)
[ "$rc" = 0 ] && [ $((t1-t0)) -le 1 ] && ok "wait script: no lock file means no wait" || bad "wait script: no-lock case ($((t1-t0))s rc=$rc)"
touch "$LK/state.lock"
t0=$(date +%s); GW_WAIT_LOCKDIR="$LK" GW_WAIT_STALE=5 GW_WAIT_CAP=20 bash "$WAIT"; rc=$?; t1=$(date +%s)
[ "$rc" = 0 ] && [ $((t1-t0)) -ge 3 ] && [ $((t1-t0)) -le 10 ] && ok "wait script: a fresh heartbeat is waited out until it is stale ($((t1-t0))s)" || bad "wait script: fresh-lock case ($((t1-t0))s rc=$rc)"
( for _ in $(seq 1 12); do touch "$LK/state.lock"; sleep 1; done ) & TOUCH_PID=$!
t0=$(date +%s); GW_WAIT_LOCKDIR="$LK" GW_WAIT_STALE=50 GW_WAIT_CAP=4 bash "$WAIT"; rc=$?; t1=$(date +%s)
[ "$rc" = 0 ] && [ $((t1-t0)) -ge 4 ] && [ $((t1-t0)) -le 9 ] && ok "wait script: a live owner hits the cap and still exits 0 ($((t1-t0))s)" || bad "wait script: cap case ($((t1-t0))s rc=$rc)"
kill "$TOUCH_PID" 2>/dev/null; wait "$TOUCH_PID" 2>/dev/null
unset OPENCLAW_ROOT
if grep -v '^[[:space:]]*#' "$WAIT" | grep -Eq '(^|[^-/[:alnum:]_.])openclaw[[:space:]]'; then bad "wait script calls the openclaw CLI"; else ok "wait script never runs the openclaw CLI"; fi

# ---------------------------------------------------------------- wrapper patcher: auth-profiles fragment
if command -v node >/dev/null 2>&1; then
  F="$TMP/server.mjs"
  printf 'const d=require("fs"),q="%s/auth-profiles.json",t={};\nd.writeFileSync(q,JSON.stringify(t,null,2));\n' "$TMP" > "$F"
  HWP_TARGET="$F" HWP_LOG="$TMP/hwp.log" python3 -I "$HWP" >/dev/null 2>&1; rc=$?
  if [ "$rc" = 0 ] && ! grep -q 'writeFileSync(q' "$F" && grep -q 'void 0' "$F"; then ok "patcher: the auth-profiles.json re-create is neutralised"; else bad "patcher: fragment not applied (rc=$rc)"; fi
  HWP_TARGET="$F" HWP_LOG="$TMP/hwp.log" python3 -I "$HWP" >/dev/null 2>&1
  grep -q 'already patched' "$TMP/hwp.log" && ok "patcher: second run is idempotent" || bad "patcher: not idempotent"
else
  ok "patcher: node not installed here, fragment test skipped"
fi

printf '[vps-startup-gateway-first] %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" = 0 ]
