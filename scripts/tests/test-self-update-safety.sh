#!/usr/bin/env bash
# Safety-contract test for scripts/self-update.sh — the fixes that keep a box
# from being left dark or mis-reported. Runs the REAL script in a throwaway
# HOME/OPENCLAW_ROOT with stub curl/git/uname/caffeinate. Nothing leaves this
# machine; the real ~/.openclaw is never read or written.
#
# Covers, one case per finding:
#   MAC-7  HUP/INT/TERM STOPS the job (exit 143) and still releases the lock
#   MAC-9  PATH reaches the 999-managed node dir, so the 9Router guards resolve node
#   NB2/MAC-6/modeB.B11  failed steps probe /healthz + 9Router health and write
#                        step_rollbacks / needs_host_restart
#   critic.C12  config backup restored on a non-zero content step (not only rc 2)
#   hostinger.H11  config backup deleted after a clean run
#   own-backups    (v1.5.0) the config copy AND the skills snapshot the content step wrote are
#                  deleted only when the final status says success; kept on a failed step, a
#                  rollback, a pending host restart and a deferral; nothing else is touched
#   hostinger.H7 / critic.C8  Docker writes needs_host_restart, never "rolled back"
#   critic.C9  the detached child is wrapped in caffeinate -dimsu on macOS
#   neverBroken.NB12  the no-snapshot fallback transport is a FAILED step
#   critic.C15  the status-field citation is SKILL.md section 18.2, not a line
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/../self-update.sh"
FFSYNC_SRC="$HERE/../../shared-utils/git_ff_sync.sh"
[ -f "$SRC" ] || { echo "FAIL: $SRC not found" >&2; exit 1; }
PY="python3 -I"
G="$(command -v git)"

T="$(mktemp -d "${TMPDIR:-/tmp}/self-update-safety.XXXXXX")" || exit 1
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/fix" "$T/tmp"
fail=0
ok()  { echo "ok - $*"; }
bad() { echo "FAIL - $*"; fail=1; }

# ── stubs ────────────────────────────────────────────────────────────────────
cat > "$T/bin/curl" <<'EOF'
#!/usr/bin/env bash
[ "$1" = "--version" ] && { echo "curl 8.0.0"; exit 0; }
url=""; dest=""; wfmt=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) dest="$2"; shift 2 ;;
    -w) wfmt="$2"; shift 2 ;;
    --max-time|-m) shift 2 ;;
    -*) shift ;;
    *) url="$1"; shift ;;
  esac
done
case "$url" in
  */healthz)    [ -n "$wfmt" ] && printf '%s' "${HEALTHZ_CODE:-503}"; exit 0 ;;
  */api/health) [ "${NR_HEALTH:-0}" = 1 ] && exit 0 || exit 22 ;;
esac
[ -n "$url" ] && [ -n "$dest" ] || exit 2
src="$FIXTURES/$(basename "$url")"
[ -f "$src" ] || { echo "curl-stub: no fixture for $(basename "$url")" >&2; exit 22; }
cp "$src" "$dest"
EOF

# Real git, except a GitHub clone refuses: no test may reach the network.
REAL_GIT="$G"; export REAL_GIT
cat > "$T/bin/git" <<'EOF'
#!/usr/bin/env bash
if [ "$1" = "--version" ]; then echo "git version 2.0"; exit 0; fi
if [ "$1" = "clone" ]; then echo "git-stub: clone refused in tests" >&2; exit 1; fi
exec "$REAL_GIT" "$@"
EOF

cat > "$T/bin/uname" <<'EOF'
#!/usr/bin/env bash
case "$1" in -s) echo Darwin ;; -m) echo arm64 ;; *) echo Darwin ;; esac
EOF

# critic.C9: record the argv the wrapper was given, then exec it so the child is
# the same pid the launcher reports.
cat > "$T/bin/caffeinate" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" > "$CAFFEINATE_LOG"
while [ "$#" -gt 0 ]; do case "$1" in -*) shift ;; *) break ;; esac; done
exec "$@"
EOF

for n in claude osascript shasum tar security xcode-select; do
  printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$T/bin/$n"
done
chmod 700 "$T/bin/"*

# ── 999 fixture remote (for the PATH case) ───────────────────────────────────
R999="$T/remote999.git"; W999="$T/w999"
GD=".claude/skills/nine-router-setup/scripts"
mkdir -p "$W999/$GD/macos"
printf '%s\n' '#!/usr/bin/env bash' 'echo "[fixture] setup-macos $*"' 'exit 0' > "$W999/$GD/setup-macos.sh"
cat > "$W999/$GD/macos/install-9router-guards.sh" <<'EOF'
#!/usr/bin/env bash
# MAC-9: the real guards resolve node from /opt/homebrew/bin, /usr/local/bin and
# PATH only — never from the 999 tree — so on a Mac with 999-managed node and a
# narrow launchd PATH they fail with "no node binary resolvable". The job must
# put the 999-managed node dir on PATH itself. Asserted only when the case asks.
if [ "${REQUIRE_999_NODE:-0}" = 1 ]; then
  want="$HOME/.local/share/999/node/current/bin"
  case ":$PATH:" in
    *":$want:"*) ;;
    *) echo "[fixture] MISSING_999_NODE_DIR ($want not on PATH)" >&2; exit 5 ;;
  esac
  n="$(command -v node 2>/dev/null)"
  case "$n" in
    "$want"/*) echo "[fixture] NODE_FROM_999: $n" ;;
    *) echo "[fixture] NODE_NOT_FROM_999: ${n:-none}" >&2; exit 6 ;;
  esac
fi
exit 0
EOF
"$G" init -q --bare -b main "$R999"
( cd "$W999" && "$G" init -q -b main && "$G" add -A \
  && "$G" -c user.name=t -c user.email=t@t commit -q -m init \
  && "$G" push -q "$R999" main ) || { echo "FAIL: 999 fixture build" >&2; exit 1; }
cp "$FFSYNC_SRC" "$T/fix/git_ff_sync.sh"

mkfx() {  # oc_rc weekly_rc [weekly_body_extra]
  printf '%s\n' '#!/usr/bin/env bash' 'echo "[fixture] oc-atomic-upgrade $*"' "exit $1" \
    > "$T/fix/oc-atomic-upgrade.sh"
  printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$T/fix/oc-schema-migrate.py"
  printf 'raise SystemExit(1)\n' > "$T/fix/oc-supervisor-install.py"
  { printf '%s\n' '#!/usr/bin/env bash' 'sleep "${WEEKLY_SLEEP:-0}"'
    [ -n "${3:-}" ] && printf '%s\n' "$3"
    printf '%s\n' 'if [ -n "${WEEKLY_EDIT:-}" ]; then echo CHANGED > "$WEEKLY_EDIT"; fi'
    printf 'exit %s\n' "$2"; } > "$T/fix/weekly-full-update.sh"
  chmod 700 "$T/fix/"*
}

seed_root() {  # case_dir
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
  printf '{"gateway":{"port":18789}}\n' > "$C/root/openclaw.json"
  # A verified 999 checkout at origin/main, so the 999 step is a pass unless a
  # case is specifically about it.
  "$G" clone -q "$R999" "$C/home/999-setup" || { echo "FAIL: could not seed 999 checkout" >&2; exit 1; }
}

run_fg() {  # case_dir [extra env via RUNPATH?] — caller sets env before the call
  C="$1"
  OUT="$C/out.txt"
  PATH="${RUNPATH:-$T/bin:$PATH}" HOME="$C/home" OPENCLAW_ROOT="$C/root" FIXTURES="$T/fix" \
    TMPDIR="$T/tmp" CAFFEINATE_LOG="$T/caffeinate.args" \
    bash "$SRC" --roll-id "roll-${C##*/}" \
      --openclaw-target 2026.10.4 --ninerouter-target 0.5.50 --foreground \
      > "$OUT" 2>&1
  echo $?
}

json() {  # file key -> scalar / bool / sorted dict
  $PY -c '
import json, sys
d = json.load(open(sys.argv[1]))
v = d.get(sys.argv[2], "")
if isinstance(v, bool):
    print("true" if v else "false")
elif isinstance(v, (dict, list)):
    print(json.dumps(v, sort_keys=True))
else:
    print("" if v is None else v)
' "$1" "$2" 2>/dev/null
}

ST() { printf '%s/root/fleet-refresh/agent-pull-status.json' "$1"; }

# ══ MAC-7: a stop signal STOPS the job and still releases the lock ═══════════
mkfx 0 0
A="$T/mac7"; seed_root "$A"
PATH="$T/bin:$PATH" HOME="$A/home" OPENCLAW_ROOT="$A/root" FIXTURES="$T/fix" TMPDIR="$T/tmp" \
  WEEKLY_SLEEP=3 bash "$SRC" --roll-id roll-mac7 --openclaw-target 2026.10.4 \
  --ninerouter-target 0.5.50 --foreground > "$A/out.txt" 2>&1 &
JPID=$!
i=0
while [ "$i" -lt 60 ]; do grep -q 'STEP update' "$A/out.txt" 2>/dev/null && break; sleep 1; i=$((i+1)); done
kill -TERM "$JPID" 2>/dev/null
wait "$JPID" 2>/dev/null; RC=$?
[ "$RC" = "143" ] && ok "MAC-7: TERM stops the job with exit 143" || bad "MAC-7: exit $RC (want 143)"
[ ! -d "$A/root/fleet-refresh/agent-pull.lock" ] && ok "MAC-7: lock released by the EXIT trap" \
  || bad "MAC-7: lock left behind after a stop signal"
PH="$(json "$(ST "$A")" phase)"
[ "$PH" != "done" ] && ok "MAC-7: job did not continue to done (phase=$PH)" \
  || bad "MAC-7: job ran to done after a stop signal"

# ══ MAC-9: PATH reaches the 999-managed node dir ════════════════════════════
# Restricted PATH deliberately excludes /usr/local/bin and /opt/homebrew/bin, so
# node resolves ONLY if self-update.sh adds the 999 dir itself.
mac9_case() {  # case_dir with_node(1|0) -> prints 9router step code
  C="$1"
  [ "$2" = 1 ] && { mkdir -p "$C/home/.local/share/999/node/current/bin"
    printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$C/home/.local/share/999/node/current/bin/node"
    chmod 700 "$C/home/.local/share/999/node/current/bin/node"; }
  PATH="$T/bin:/usr/bin:/bin" HOME="$C/home" OPENCLAW_ROOT="$C/root" FIXTURES="$T/fix" \
    TMPDIR="$T/tmp" REQUIRE_999_NODE=1 \
    bash "$SRC" --roll-id "roll-${C##*/}" --openclaw-target 2026.10.4 \
    --ninerouter-target 0.5.50 --foreground > "$C/out.txt" 2>&1
  $PY -c 'import json,sys
try: print(json.load(open(sys.argv[1]))["step_exit_codes"].get("9router"))
except Exception: print("?")' "$(ST "$C")" 2>/dev/null
}
mkfx 0 0
N="$T/mac9a"; seed_root "$N"
M9A="$(mac9_case "$N" 1)"
[ "$M9A" = "0" ] && ok "MAC-9: 9Router guards resolved the 999-managed node (rc 0)" \
  || bad "MAC-9: 9Router guards still could not resolve node (rc $M9A)"
N2="$T/mac9b"; seed_root "$N2"
M9B="$(mac9_case "$N2" 0)"
[ "$M9B" != "0" ] && ok "MAC-9 control: without the 999 node dir the guards fail (rc $M9B — test discriminates)" \
  || bad "MAC-9 control: guards passed with no node at all — the check proves nothing"

# ══ NB2 / MAC-6 / modeB.B11 + critic.C12 + H11: health proof, rollbacks ══════
# rc 70 with a gateway that will not answer: needs_host_restart + a rollback row.
mkfx 70 0
B="$T/h70"; seed_root "$B"
RB="$(HEALTHZ_CODE=503 run_fg "$B")"
SB="$(ST "$B")"
[ "$RB" = "20" ] && ok "NB2: upgrade rc 70 still exits 20" || bad "NB2: exit $RB (want 20)"
[ "$(json "$SB" needs_host_restart)" = "true" ] && ok "modeB.B11: rc-70 path writes needs_host_restart" \
  || bad "modeB.B11: needs_host_restart not written on rc 70"
case "$(json "$SB" step_rollbacks)" in
  *'"step": "upgrade"'*) ok "modeB.B11: step_rollbacks records the upgrade step" ;;
  *) bad "modeB.B11: step_rollbacks missing an upgrade row: $(json "$SB" step_rollbacks)" ;;
esac

# content rc 1 with the gateway DOWN: config restored, health unproven -> marker.
mkfx 0 1
C1="$T/c12"; seed_root "$C1"
BEFORE="$(cksum < "$C1/root/openclaw.json")"
RC1="$(HEALTHZ_CODE=503 run_fg "$C1")"
AFTER="$(cksum < "$C1/root/openclaw.json")"
[ "$BEFORE" = "$AFTER" ] && ok "critic.C12: non-zero content step (rc 1) restored openclaw.json" \
  || bad "critic.C12: openclaw.json not restored on rc 1"
[ "$RC1" = "1" ] && ok "critic.C12: exit is the content rc (1)" || bad "critic.C12: exit $RC1"
[ "$(json "$(ST "$C1")" needs_host_restart)" = "true" ] \
  && ok "NB2: unproven /healthz after the restore writes needs_host_restart" \
  || bad "NB2: needs_host_restart not written after an unproven rollback"
case "$(json "$(ST "$C1")" step_rollbacks)" in
  *'"step": "content-config"'*) ok "NB2: step_rollbacks records the config restore" ;;
  *) bad "NB2: no content-config rollback row" ;;
esac

# content rc 2 with the gateway LIVE: the config is NOT restored under it.
mkfx 0 2
C2="$T/live"; seed_root "$C2"
BEFORE="$(cksum < "$C2/root/openclaw.json")"
HEALTHZ_CODE=200 WEEKLY_EDIT="$C2/root/openclaw.json" run_fg "$C2" >/dev/null
AFTER="$(cksum < "$C2/root/openclaw.json")"
[ "$BEFORE" != "$AFTER" ] && ok "MAC-6: no cp restore while the gateway answers 200" \
  || bad "MAC-6: config was overwritten under a live gateway"
[ "$(json "$(ST "$C2")" needs_host_restart)" = "true" ] \
  && ok "MAC-6: kept-backup case raises needs_host_restart" \
  || bad "MAC-6: needs_host_restart not raised when the backup is kept"
ls "$C2/root/fleet-refresh"/openclaw.json.pre-* >/dev/null 2>&1 \
  && ok "H11/C12: mode-600 backup kept for the human when it cannot be applied" \
  || bad "H11: backup deleted though the restore never happened"

# clean run: the backup is deleted (no secret-bearing copy left behind).
mkfx 0 0
D="$T/h11"; seed_root "$D"
RD="$(run_fg "$D")"
[ "$RD" = "0" ] && ok "H11: clean run exits 0" || bad "H11: exit $RD (want 0)"
ls "$D/root/fleet-refresh"/openclaw.json.pre-* >/dev/null 2>&1 \
  && bad "H11: config copy left behind after a clean run" \
  || ok "H11: config copy deleted after a clean run"
[ "$(json "$(ST "$D")" needs_host_restart)" = "false" ] && ok "happy path: needs_host_restart false" \
  || bad "happy path: needs_host_restart true on a clean run"

# ══ own-backups (v1.5.0): delete this run's backups only on a fully successful run ═══
# The content step (the weekly stub) writes a skills-rollback snapshot under ~/Downloads/openclaw-backups and
# a one-time skills-backup copy under <root>/backups, one second after self-update.sh marked the step. Also
# created AFTER the mark but NOT snapshots: a differently named dir and a symlink wearing a snapshot name
# that points at a real dir. Created BEFORE the run: an older snapshot. None of those three may ever go.
SNAPSTUB='sleep 1; B="$HOME/Downloads/openclaw-backups"; mkdir -p "$B/skills-rollback-20261029-120000" "$OPENCLAW_ROOT/backups/skills-backup-20261029-120001" "$B/client-notes-20261029-120002" "$HOME/real-dir"; echo p > "$B/skills-rollback-20261029-120000/local-changes.patch"; ln -s "$HOME/real-dir" "$B/skills-rollback-20261029-120003"'
seed_snaps() {  # case_dir
  mkdir -p "$1/home/Downloads/openclaw-backups/skills-rollback-20251001-000000"
  touch -t 202510010000 "$1/home/Downloads/openclaw-backups/skills-rollback-20251001-000000"
}
snap_state() {  # case_dir -> "new=<n> backupcopy=<n> old=<n> notes=<n> link=<n> target=<n> cfg=<n>"
  _s="$1"; _b="$_s/home/Downloads/openclaw-backups"
  _n=0; [ -e "$_b/skills-rollback-20261029-120000" ] && _n=1
  _c=0; [ -e "$_s/root/backups/skills-backup-20261029-120001" ] && _c=1
  _o=0; [ -e "$_b/skills-rollback-20251001-000000" ] && _o=1
  _k=0; [ -e "$_b/client-notes-20261029-120002" ] && _k=1
  _l=0; [ -L "$_b/skills-rollback-20261029-120003" ] && _l=1
  _t=0; [ -d "$_s/home/real-dir" ] && _t=1
  _f=$(ls "$_s/root/fleet-refresh"/openclaw.json.pre-* 2>/dev/null | wc -l | tr -d ' ')
  echo "new=$_n backupcopy=$_c old=$_o notes=$_k link=$_l target=$_t cfg=$_f"
}

# success: both deleted, everything else untouched, every deletion logged by path
mkfx 0 0 "$SNAPSTUB"
OB1="$T/ob-ok"; seed_root "$OB1"; seed_snaps "$OB1"
ROB1="$(HEALTHZ_CODE=200 run_fg "$OB1")"
[ "$ROB1" = "0" ] && ok "own-backups: clean run exits 0" || bad "own-backups: clean run exit $ROB1 (want 0)"
[ "$(snap_state "$OB1")" = "new=0 backupcopy=0 old=1 notes=1 link=1 target=1 cfg=0" ] \
  && ok "own-backups: success deletes the config copy and both run snapshots; the older snapshot, the other dir and the symlink survive" \
  || bad "own-backups: success state was '$(snap_state "$OB1")'"
[ "$(json "$(ST "$OB1")" phase)" = "done" ] && [ -n "$(json "$(ST "$OB1")" finished_utc)" ] \
  && ok "own-backups: the final status (phase done, finished) is on disk" || bad "own-backups: final status missing"
[ "$(grep -c 'backup: deleted ' "$OB1/out.txt")" = "3" ] \
  && grep -q "backup: deleted .*openclaw.json.pre-ap-" "$OB1/out.txt" \
  && grep -q "backup: deleted $OB1/home/Downloads/openclaw-backups/skills-rollback-20261029-120000" "$OB1/out.txt" \
  && grep -q "backup: deleted $OB1/root/backups/skills-backup-20261029-120001" "$OB1/out.txt" \
  && ok "own-backups: each of the 3 deletions is logged by path" || bad "own-backups: deletion log lines: $(grep 'backup: ' "$OB1/out.txt")"
grep 'backup: ' "$OB1/out.txt" | grep -q 'test-ollama-value\|test-deepseek-value' \
  && bad "own-backups: a key value reached the log" || ok "own-backups: no key value in the deletion log"

# a failed step (OpenClaw upgrade rc 1, content ok, gateway healthy): kept
mkfx 1 0 "$SNAPSTUB"
OB2="$T/ob-failstep"; seed_root "$OB2"; seed_snaps "$OB2"
ROB2="$(HEALTHZ_CODE=200 run_fg "$OB2")"
[ "$ROB2" = "1" ] && ok "own-backups: a failed upgrade step exits with its code (1)" || bad "own-backups: failed-step exit $ROB2 (want 1)"
[ "$(snap_state "$OB2")" = "new=1 backupcopy=1 old=1 notes=1 link=1 target=1 cfg=1" ] \
  && ok "own-backups: any failed step keeps the config copy and the snapshots" \
  || bad "own-backups: failed-step state was '$(snap_state "$OB2")'"
grep -q 'backup: deleted' "$OB2/out.txt" && bad "own-backups: a deletion was logged on a failed run" || ok "own-backups: no deletion logged on a failed run"

# a rollback (content rc 2 while the gateway is live): rolled_back + needs_host_restart, kept
mkfx 0 2 "$SNAPSTUB"
OB3="$T/ob-rolled"; seed_root "$OB3"; seed_snaps "$OB3"
HEALTHZ_CODE=200 run_fg "$OB3" >/dev/null
[ "$(json "$(ST "$OB3")" rolled_back)" = "true" ] && ok "own-backups: control: this run reports rolled_back" || bad "own-backups: control: rolled_back not true"
[ "$(snap_state "$OB3")" = "new=1 backupcopy=1 old=1 notes=1 link=1 target=1 cfg=1" ] \
  && ok "own-backups: rolled_back keeps the config copy and the snapshots" \
  || bad "own-backups: rolled-back state was '$(snap_state "$OB3")'"

# a host restart still owed, though every step passed (exit 0): kept
mkfx 0 0 "$SNAPSTUB"
OB4="$T/ob-restart"; seed_root "$OB4"; seed_snaps "$OB4"
mkdir -p "$OB4/root/fleet-refresh"; echo "owed by an earlier run" > "$OB4/root/fleet-refresh/needs_host_restart"
ROB4="$(HEALTHZ_CODE=200 run_fg "$OB4")"
[ "$ROB4" = "0" ] && [ "$(json "$(ST "$OB4")" needs_host_restart)" = "true" ] \
  && ok "own-backups: control: exit 0 with needs_host_restart true" || bad "own-backups: control: exit $ROB4, needs_host_restart '$(json "$(ST "$OB4")" needs_host_restart)'"
[ "$(snap_state "$OB4")" = "new=1 backupcopy=1 old=1 notes=1 link=1 target=1 cfg=1" ] \
  && ok "own-backups: needs_host_restart keeps the config copy and the snapshots" \
  || bad "own-backups: needs-restart state was '$(snap_state "$OB4")'"

# the content step deferred (exit 75): nothing proven, kept
mkfx 0 75 "$SNAPSTUB"
OB5="$T/ob-deferred"; seed_root "$OB5"; seed_snaps "$OB5"
ROB5="$(HEALTHZ_CODE=200 run_fg "$OB5")"
[ "$ROB5" = "75" ] && ok "own-backups: control: a deferred content step exits 75" || bad "own-backups: deferred exit $ROB5 (want 75)"
[ "$(snap_state "$OB5")" = "new=1 backupcopy=1 old=1 notes=1 link=1 target=1 cfg=1" ] \
  && ok "own-backups: a deferred run keeps the config copy and the snapshots" \
  || bad "own-backups: deferred state was '$(snap_state "$OB5")'"

# ══ hostinger.H7 / critic.C8: Docker defers to the host, never claims a rollback ══
mkfx 0 2
E="$T/docker"; seed_root "$E"
BEFORE="$(cksum < "$E/root/openclaw.json")"
RE="$(SELF_UPDATE_DOCKER=1 WEEKLY_EDIT="$E/root/openclaw.json" HEALTHZ_CODE=200 run_fg "$E")"
SE="$(ST "$E")"
AFTER="$(cksum < "$E/root/openclaw.json")"
[ "$(json "$SE" rolled_back)" = "false" ] && ok "H7: Docker never reports rolled_back" \
  || bad "H7: Docker reported rolled_back"
[ "$(json "$SE" needs_host_restart)" = "true" ] && ok "H7: Docker writes needs_host_restart" \
  || bad "H7: Docker did not write needs_host_restart"
[ "$BEFORE" != "$AFTER" ] && ok "H7: Docker leaves the content step's own state; no in-container restore" \
  || bad "H7: Docker restored config in-container"
grep -q 'Docker — needs_host_restart written' "$E/out.txt" && ok "C8: log states the host restart is required" \
  || bad "C8: log does not record the host-restart deferral"

# ══ critic.C9: the detached child is wrapped in caffeinate -dimsu ════════════
mkfx 0 0
F="$T/caff"; seed_root "$F"
OUTF="$F/launch.txt"
rm -f "$T/caffeinate.args"
PATH="$T/bin:$PATH" HOME="$F/home" OPENCLAW_ROOT="$F/root" FIXTURES="$T/fix" TMPDIR="$T/tmp" \
  CAFFEINATE_LOG="$T/caffeinate.args" WEEKLY_SLEEP=2 \
  bash "$SRC" --roll-id roll-caff --openclaw-target 2026.10.4 --ninerouter-target 0.5.50 \
    --launch-epoch "$(( $(date +%s) - 300 ))" > "$OUTF" 2>&1
[ -f "$T/caffeinate.args" ] && ok "C9: the detached child was started under caffeinate" \
  || bad "C9: no caffeinate wrapper was used on macOS"
grep -q -- '-dimsu' "$T/caffeinate.args" 2>/dev/null && ok "C9: wrapper flags are -dimsu" \
  || bad "C9: caffeinate flags: $(cat "$T/caffeinate.args" 2>/dev/null)"
i=0
while [ "$i" -lt 40 ]; do
  [ -n "$(json "$(ST "$F")" finished_utc)" ] && break; sleep 1; i=$((i+1))
done
[ -n "$(json "$(ST "$F")" finished_utc)" ] && ok "C9: wrapped child still finished" \
  || bad "C9: wrapped child never finished"

# ══ neverBroken.NB12: the fallback transport is a FAILED step ════════════════
mkfx 0 0 'echo "WARNING: no usable onboarding copy (could not create x) — falling back to the root updater fetched from main (same FULL path per OCT4 #10; narrower transport only, no snapshot/rollback machinery around it)"'
H="$T/nb12"; seed_root "$H"
RH="$(run_fg "$H")"
[ "$RH" = "21" ] && ok "NB12: fallback transport exits as a failed step (21)" \
  || bad "NB12: exit $RH (want 21)"
grep -q 'no-snapshot fallback transport' "$H/out.txt" && ok "NB12: refusal is named in the log" \
  || bad "NB12: no refusal line for the fallback transport"

# ══ agent-pull.md 6.1: the named safety-net guard exists and refuses ═════════
mkfx 0 0
I="$T/net"; seed_root "$I"
rm -rf "$I/home/999-setup"   # no checkout anywhere, and the git stub refuses to clone
run_fg "$I" >/dev/null
if json "$(ST "$I")" step_exit_codes | grep -q '"999-setup": 23'; then
  ok "safety net: missing managed clone fails 999-setup (23)"
else
  bad "safety net: 999-setup code: $(json "$(ST "$I")" step_exit_codes)"
fi
grep -q 'REFUSED: managed clone unavailable; safety net required' "$I/out.txt" \
  && ok "safety net: FLEET_REQUIRE_SAFETY_NET refusal is emitted" \
  || bad "safety net: refusal string missing"

# ══ critic.C15: the citation names a section, not a drifting line ════════════
grep -q 'SKILL.md section 18.2' "$SRC" && ok "C15: status fields cite SKILL.md section 18.2" \
  || bad "C15: citation is not the section reference"
grep -q 'SKILL.md:362' "$SRC" && bad "C15: stale SKILL.md:362 line citation still present" \
  || ok "C15: no line-number citation for the status fields"

[ "$fail" -eq 0 ] && { echo "PASS: self-update safety contract"; exit 0; }
echo "FAIL: self-update safety contract"; exit 1
