#!/usr/bin/env bash
# Contract test for scripts/self-update.sh. Runs the REAL script (no mocks of
# the script itself) inside a throwaway HOME/OPENCLAW_ROOT with stub curl, git,
# uname and macOS tools. Nothing leaves this machine; the real ~/.openclaw is
# never read or written.
#
# Asserts the things the operator watch depends on:
#   * FIRST stdout line is RUN_ID=ap-<ROLL>-<digits>-<pid>
#   * <root>/fleet-refresh/agent-pull-status.json exists, parses, mode 600
#   * it carries every 10.9 field and run_id equals the printed RUN_ID
#   * step order 999-setup -> 9router -> upgrade -> update
#   * a failed step does not stop the later steps (raw rc recorded)
#   * OpenClaw rc 78 is recorded raw; the content step still runs
#   * the content rollback (weekly rc 2) restores openclaw.json byte-identical
#   * the detached child is in its OWN SESSION and a second launch is a no-op
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/../self-update.sh"
[ -f "$SRC" ] || { echo "FAIL: $SRC not found" >&2; exit 1; }
PY="python3 -I"

T="$(mktemp -d "${TMPDIR:-/tmp}/self-update-contract.XXXXXX")" || exit 1
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/fix" "$T/tmp"

fail=0
ok()   { echo "ok - $*"; }
bad()  { echo "FAIL - $*"; fail=1; }

# ── stubs ────────────────────────────────────────────────────────────────────
cat > "$T/bin/curl" <<'EOF'
#!/usr/bin/env bash
[ "$1" = "--version" ] && { echo "curl 8.0.0"; exit 0; }
url=""; dest=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) dest="$2"; shift 2 ;;
    --max-time) shift 2 ;;
    -*) shift ;;
    *) url="$1"; shift ;;
  esac
done
[ -n "$url" ] && [ -n "$dest" ] || exit 2
src="$FIXTURES/$(basename "$url")"
[ -f "$src" ] || { echo "curl-stub: no fixture for $(basename "$url")" >&2; exit 22; }
cp "$src" "$dest"
EOF

# CAN012: self-update now PROVES the 999 checkout is origin/main, so the stub git
# hands every command to the real git, except that a clone of the GitHub URL is
# redirected to a local bare fixture remote (nothing leaves this machine).
REAL_GIT="$(command -v git)"
export REAL_GIT
R999="$T/remote999.git"; W999="$T/work999"
mkdir -p "$W999/.claude/skills/nine-router-setup/scripts/macos"
printf '%s\n' '#!/usr/bin/env bash' 'echo "[fixture] setup-macos $*"' 'exit 0' \
  > "$W999/.claude/skills/nine-router-setup/scripts/setup-macos.sh"
printf '%s\n' '#!/usr/bin/env bash' 'echo "[fixture] 9router-guards $*"' 'exit 0' \
  > "$W999/.claude/skills/nine-router-setup/scripts/macos/install-9router-guards.sh"
"$REAL_GIT" init -q --bare -b main "$R999"
( cd "$W999" && "$REAL_GIT" init -q -b main && "$REAL_GIT" add -A \
  && "$REAL_GIT" -c user.name=t -c user.email=t@t commit -q -m init \
  && "$REAL_GIT" push -q "$R999" main ) || { echo "FAIL: could not build the 999 fixture remote" >&2; exit 1; }
export R999
cat > "$T/bin/git" <<'EOF'
#!/usr/bin/env bash
if [ "$1" = "--version" ]; then echo "git version 2.0"; exit 0; fi
if [ "$1" = "clone" ]; then
  for last; do :; done
  exec "$REAL_GIT" clone -q "$R999" "$last"
fi
exec "$REAL_GIT" "$@"
EOF

cat > "$T/bin/uname" <<'EOF'
#!/usr/bin/env bash
case "$1" in -s) echo Darwin ;; -m) echo arm64 ;; *) echo Darwin ;; esac
EOF

for n in claude osascript shasum tar security xcode-select; do
  printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$T/bin/$n"
done
chmod 700 "$T/bin/"*

mkfx() {  # oc_rc weekly_rc
  printf '%s\n' '#!/usr/bin/env bash' 'echo "[fixture] oc-atomic-upgrade $*"' "exit $1" \
    > "$T/fix/oc-atomic-upgrade.sh"
  printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$T/fix/oc-schema-migrate.py"
  printf '%s\n' '#!/usr/bin/env bash' 'sleep "${WEEKLY_SLEEP:-0}"' \
    'if [ -n "${WEEKLY_EDIT:-}" ]; then echo CHANGED > "$WEEKLY_EDIT"; fi' \
    "exit $2" > "$T/fix/weekly-full-update.sh"
  chmod 700 "$T/fix/"*
}

seed_root() {  # case_dir run_id_case
  C="$1"
  mkdir -p "$C/home" "$C/root/secrets" "$C/root/skills" \
           "$C/root/npm-global/lib/node_modules/openclaw" \
           "$C/home/.local/share/999/npm/lib/node_modules/9router"
  printf 'v78.0.0\n' > "$C/root/skills/.onboarding-version"
  printf '{"name":"openclaw","version":"2026.10.3"}\n' \
    > "$C/root/npm-global/lib/node_modules/openclaw/package.json"
  printf '{"name":"9router","version":"0.5.50"}\n' \
    > "$C/home/.local/share/999/npm/lib/node_modules/9router/package.json"
  printf 'OLLAMA_CLOUD_API_KEY=test-ollama-value-123\nDEEPSEEK_API_KEY=test-deepseek-value-456\n' \
    > "$C/root/secrets/.env"
  chmod 600 "$C/root/secrets/.env"
  printf '{"assistant":{"provider":"x"}}\n' > "$C/root/openclaw.json"
}

run_fg() {  # case_dir
  C="$1"
  OUT="$C/out.txt"
  PATH="$T/bin:$PATH" HOME="$C/home" OPENCLAW_ROOT="$C/root" FIXTURES="$T/fix" \
    TMPDIR="$T/tmp" bash "$SRC" --roll-id "roll-${C##*/}" \
      --openclaw-target 2026.10.4 --ninerouter-target 0.5.50 --foreground \
      > "$OUT" 2>&1
  echo $?
}

json() {  # file key -> scalar verbatim; dicts as sorted JSON; bools true/false
  $PY -c '
import json, sys
d = json.load(open(sys.argv[1]))
v = d.get(sys.argv[2], "")
if isinstance(v, bool):
    print("true" if v else "false")
elif isinstance(v, dict):
    print(json.dumps(v, sort_keys=True))
else:
    print("" if v is None else v)
' "$1" "$2" 2>/dev/null
}
has_field() {  # file key
  $PY -c 'import json,sys; d=json.load(open(sys.argv[1])); raise SystemExit(0 if sys.argv[2] in d else 1)' "$1" "$2" 2>/dev/null
}

REQUIRED="run_id roll_id phase started_utc updated_utc finished_utc step_exit_codes stamp_before stamp_after openclaw_before openclaw_after ninerouter_before ninerouter_after rolled_back needs_host_restart stuck_reason error_tail"

# ── CASE A: happy path, foreground ───────────────────────────────────────────
mkfx 0 0
A="$T/a"; seed_root "$A"
RC="$(run_fg "$A")"
ST="$A/root/fleet-refresh/agent-pull-status.json"
FIRST="$(head -n1 "$A/out.txt")"
case "$FIRST" in
  RUN_ID=ap-roll-a-[0-9]*-[0-9]*) ok "first stdout line is $FIRST" ;;
  *) bad "first stdout line is not RUN_ID=ap-...: $FIRST" ;;
esac
[ -f "$ST" ] && ok "status JSON exists" || bad "no status JSON at $ST"
[ "$RC" = "0" ] && ok "exit 0" || bad "exit $RC (want 0)"
$PY - "$ST" <<'PY' && ok "JSON parses" || bad "JSON does not parse"
import json,sys; json.load(open(sys.argv[1]))
PY
for f in $REQUIRED; do
  has_field "$ST" "$f" && ok "field $f" || bad "missing field $f"
done
RP="$(sed -n 's/^RUN_ID=//p' "$A/out.txt" | head -n1)"
[ -n "$RP" ] && [ "$(json "$ST" run_id)" = "$RP" ] \
  && ok "run_id matches RUN_ID=$RP" || bad "run_id does not match RUN_ID"
[ "$(json "$ST" step_exit_codes)" = '{"999-setup": 0, "9router": 0, "update": 0, "upgrade": 0}' ] \
  && ok "step_exit_codes all zero in order" \
  || bad "step_exit_codes: $(json "$ST" step_exit_codes)"
[ -n "$(json "$ST" finished_utc)" ] && ok "finished_utc set" || bad "finished_utc empty"
[ "$(json "$ST" stamp_before)" = "v78.0.0" ] && ok "stamp_before" || bad "stamp_before"
[ "$(json "$ST" openclaw_before)" = "2026.10.3" ] && ok "openclaw_before" || bad "openclaw_before"
[ "$(json "$ST" ninerouter_before)" = "0.5.50" ] && ok "ninerouter_before" || bad "ninerouter_before"
[ "$(perl -e 'printf "%04o", (stat($ARGV[0]))[2] & 07777' "$ST")" = "0600" ] \
  && ok "status mode 600" || bad "status mode not 600"
ORDER="$(grep -o 'STEP [a-z0-9-]*' "$A/out.txt" | head -4 | tr '\n' ' ')"
[ "$ORDER" = "STEP 999-setup STEP 9router STEP upgrade STEP update " ] \
  && ok "step order: $ORDER" || bad "step order: $ORDER"
AP="$A/home/.config/blackceo-999/api-docs.md"
grep -qx 'OLLAMA_API_KEY=test-ollama-value-123' "$AP" 2>/dev/null \
  && ok "alias written under canonical OLLAMA_API_KEY" || bad "api-docs canonical name missing"
grep -q 'OLLAMA_CLOUD_API_KEY' "$AP" 2>/dev/null && bad "alias name leaked into api-docs" \
  || ok "alias name not written"
grep -q 'test-ollama-value-123' "$A/out.txt" "$A/root/self-update/"*.log 2>/dev/null \
  && bad "key VALUE appeared in output/log" || ok "key value never printed"
[ "$(perl -e 'printf "%04o", (stat($ARGV[0]))[2] & 07777' "$AP")" = "0600" ] \
  && ok "api-docs mode 600" || bad "api-docs mode not 600"

# ── CASE B: OpenClaw rc 78 must not stop the content step ────────────────────
mkfx 78 0
B="$T/b"; seed_root "$B"
RB="$(run_fg "$B")"
SB="$B/root/fleet-refresh/agent-pull-status.json"
[ "$(json "$SB" step_exit_codes)" = '{"999-setup": 0, "9router": 0, "update": 0, "upgrade": 78}' ] \
  && ok "upgrade 78 recorded raw; update still ran" \
  || bad "step_exit_codes: $(json "$SB" step_exit_codes)"
[ "$RB" = "78" ] && ok "final exit is first failed step (78)" || bad "exit $RB (want 78)"
grep -q 'STEP update' "$B/out.txt" && ok "log shows STEP update" || bad "content step skipped"

# ── CASE C: weekly rc 2 rolls back and restores openclaw.json ───────────────
mkfx 0 2
C="$T/c"; seed_root "$C"
BEFORE="$(cksum < "$C/root/openclaw.json")"
RC="$(WEEKLY_EDIT="$C/root/openclaw.json" run_fg "$C")"
AFTER="$(cksum < "$C/root/openclaw.json")"
SC="$C/root/fleet-refresh/agent-pull-status.json"
[ "$BEFORE" = "$AFTER" ] && ok "openclaw.json restored byte-identical" || bad "openclaw.json changed"
[ "$(json "$SC" rolled_back)" = "true" ] && ok "rolled_back true" || bad "rolled_back false"
[ "$(json "$SC" step_exit_codes)" = '{"999-setup": 0, "9router": 0, "update": 2, "upgrade": 0}' ] \
  && ok "update rc 2 recorded" || bad "step_exit_codes: $(json "$SC" step_exit_codes)"
[ "$RC" = "2" ] && ok "exit 2" || bad "exit $RC (want 2)"

# ── CASE D: detached child in its own session; second launch is a no-op ──────
mkfx 0 0
D="$T/d"; seed_root "$D"
mkdir -p "$D/home/.local/bin"
OUT1="$D/launch1.txt"
PATH="$T/bin:$PATH" HOME="$D/home" OPENCLAW_ROOT="$D/root" FIXTURES="$T/fix" \
  TMPDIR="$T/tmp" WEEKLY_SLEEP=6 \
  bash "$SRC" --roll-id roll-d --openclaw-target 2026.10.4 --ninerouter-target 0.5.50 \
    --launch-epoch "$(( $(date +%s) - 300 ))" > "$OUT1" 2>&1
R1=$?
L1="$(head -n1 "$OUT1")"
case "$L1" in
  RUN_ID=ap-roll-d-[0-9]*-[0-9]*) ok "detached launcher printed $L1" ;;
  *) bad "detached launcher first line: $L1" ;;
esac
[ "$R1" = "0" ] && ok "launcher exit 0" || bad "launcher exit $R1"
LOCK="$D/root/fleet-refresh/agent-pull.lock"
PID="$(cat "$LOCK/pid" 2>/dev/null)"
if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  ok "child pid $PID alive"
  $PY - "$PID" <<'PY' && ok "child is in its OWN session and its own group" \
    || bad "child is not in its own session/group"
import os,sys
c=int(sys.argv[1]); me=os.getpid()
raise SystemExit(0 if os.getsid(c)!=os.getsid(me) and os.getpgid(c)==c else 1)
PY
else
  bad "no live child pid in the lock"
fi
# second launch while the first child is alive
OUT2="$D/launch2.txt"
PATH="$T/bin:$PATH" HOME="$D/home" OPENCLAW_ROOT="$D/root" FIXTURES="$T/fix" \
  TMPDIR="$T/tmp" bash "$SRC" --roll-id roll-d --openclaw-target 2026.10.4 \
    --ninerouter-target 0.5.50 > "$OUT2" 2>&1
R2=$?
L2="$(head -n1 "$OUT2")"
[ "$R2" = "0" ] && ok "second launch exit 0" || bad "second launch exit $R2"
[ "$L2" = "$L1" ] && ok "second launch printed the existing $L2" \
  || bad "second launch printed $L2 (want $L1)"
# wait for the child to finish and release the lock
i=0
while [ "$i" -lt 40 ]; do
  [ -n "$(json "$D/root/fleet-refresh/agent-pull-status.json" finished_utc)" ] && break
  sleep 1; i=$((i+1))
done
[ -n "$(json "$D/root/fleet-refresh/agent-pull-status.json" finished_utc)" ] \
  && ok "detached child wrote finished_utc" || bad "detached child never finished"
# finish() writes the status, then the process exits and its trap drops the lock.
i=0
while [ -d "$LOCK" ] && [ "$i" -lt 10 ]; do sleep 1; i=$((i+1)); done
[ ! -d "$LOCK" ] && ok "lock released" || bad "lock still present after finish"

[ "$fail" -eq 0 ] && { echo "PASS: self-update contract"; exit 0; }
echo "FAIL: self-update contract"; exit 1
