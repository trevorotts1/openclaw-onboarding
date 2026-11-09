#!/usr/bin/env bash
# Big Fleet Roll 2026-10 regression test for scripts/self-update.sh (v1.3.0) and
# shared-utils/git_ff_sync.sh. Real script, real git, scratch bare remote, stub
# curl/uname/caffeinate. Nothing leaves this machine; the real ~/.openclaw,
# ~/999-setup and ~/.claude are never read or written.
#
#   item 10  The roll's own operator escalation must not be sent (it can land in the
#            Rescue Rangers group and wake a paid agent). self-update.sh exports the
#            roll to its children, update-skills.sh holds the note in a file, and the
#            note reaches the WATCHER through the status file (error_tail, plus
#            stuck_reason when the job failed). A note left by an earlier run is never
#            read as this run's, and the headline is redacted like the log tail.
#   #20/#28  Before the 9Router guards run, the delivered ~/.claude/skills/nine-router-
#            setup copy is compared with the verified 999-setup copy and stamped. The
#            guards always run from the 999-setup copy; a stale delivered copy is named
#            in the log and the stamp and is NOT modified.
#   #26      A SHALLOW 999-setup clone is deepened (git fetch --unshallow) before any
#            ancestry check. Reproduced on a shallow-preserving fixture: after a
#            depth-1 fetch the clone's HEAD is cut off from origin/main, so
#            `merge-base` finds nothing and rev-list calls one merged commit unmerged;
#            git_ff_sync.sh then refuses ("left untouched"). Deepened, the same clone
#            syncs. A failed unshallow fails closed and names itself.
#
# SELF_UPDATE_SRC=<path> runs a different copy of self-update.sh (mutation proof).
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="${SELF_UPDATE_SRC:-$HERE/../self-update.sh}"
FFSYNC_SRC="$HERE/../../shared-utils/git_ff_sync.sh"
[ -f "$SRC" ] && [ -f "$FFSYNC_SRC" ] || { echo "FAIL: missing $SRC or $FFSYNC_SRC" >&2; exit 1; }
G="$(command -v git)"
PY="python3 -I"

T="$(mktemp -d "${TMPDIR:-/tmp}/self-update-bfr.XXXXXX")" || exit 1
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/fix" "$T/fix-old" "$T/tmp"
fail=0
ok()  { echo "ok - $*"; }
bad() { echo "FAIL - $*"; fail=1; }
gg() { "$G" -c user.name=t -c user.email=t@t -c commit.gpgsign=false "$@"; }

# ── stubs ────────────────────────────────────────────────────────────────────
cat > "$T/bin/curl" <<'EOF'
#!/usr/bin/env bash
[ "$1" = "--version" ] && { echo "curl 8.0.0"; exit 0; }
url=""; dest=""; wfmt=""
while [ "$#" -gt 0 ]; do
  case "$1" in -o) dest="$2"; shift 2 ;; -w) wfmt="$2"; shift 2 ;; --max-time|-m) shift 2 ;; -*) shift ;; *) url="$1"; shift ;; esac
done
case "$url" in
  */healthz)    [ -n "$wfmt" ] && printf '%s' "${HEALTHZ_CODE:-503}"; exit 0 ;;
  */api/health) exit 22 ;;
esac
[ -n "$url" ] && [ -n "$dest" ] || exit 2
if [ "$(basename "$url")" = git_ff_sync.sh ]; then src="${FIXTURES_GIT:-$FIXTURES}/git_ff_sync.sh"; else src="$FIXTURES/$(basename "$url")"; fi
[ -f "$src" ] || { echo "curl-stub: no fixture for $(basename "$url")" >&2; exit 22; }
cp "$src" "$dest"
EOF
printf '%s\n' '#!/usr/bin/env bash' 'case "$1" in -s) echo Darwin ;; -m) echo arm64 ;; *) echo Darwin ;; esac' > "$T/bin/uname"
printf '%s\n' '#!/usr/bin/env bash' 'if [ "$1" = "--version" ]; then echo "git version 2.0"; exit 0; fi' \
  'if [ "$1" = "clone" ]; then echo "git-stub: clone refused in tests" >&2; exit 1; fi' 'exec "$REAL_GIT" "$@"' > "$T/bin/git"
REAL_GIT="$G"; export REAL_GIT
for n in claude osascript shasum tar security xcode-select caffeinate; do printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$T/bin/$n"; done
chmod 700 "$T/bin/"*

# what main serves: the roll fixtures. The weekly-full-update stub records the roll
# env it was handed and, when asked, plays update-skills.sh holding its operator note.
cat > "$T/fix/weekly-full-update.sh" <<'EOF'
#!/usr/bin/env bash
{ echo "ROLL=${SELF_UPDATE_ROLL_ID-UNSET}"; echo "RUN=${SELF_UPDATE_RUN_ID-UNSET}"; echo "ESC=${SELF_UPDATE_ESCALATION_FILE-UNSET}"; } > "${ENVLOG:-/dev/null}"
if [ -n "${HOLD_NOTE:-}" ] && [ -n "${SELF_UPDATE_ESCALATION_FILE:-}" ]; then printf '%s\n' "$HOLD_NOTE" > "$SELF_UPDATE_ESCALATION_FILE"; fi
exit "${WEEKLY_RC:-0}"
EOF
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$T/fix/oc-atomic-upgrade.sh"
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$T/fix/oc-schema-migrate.py"
printf 'raise SystemExit(1)\n' > "$T/fix/oc-supervisor-install.py"
cp "$FFSYNC_SRC" "$T/fix/git_ff_sync.sh"
# the PRE-FIX git_ff_sync.sh: the same file without the shallow guard
awk '/is-shallow-repository/{skip=1} skip&&/^    fi$/{skip=0; next} !skip' "$FFSYNC_SRC" > "$T/fix-old/git_ff_sync.sh"
cmp -s "$FFSYNC_SRC" "$T/fix-old/git_ff_sync.sh" && { echo "FAIL: git_ff_sync.sh has no shallow guard to strip (fix missing)" >&2; exit 1; }
grep -q 'rev-list --count "origin/$def..HEAD"' "$T/fix-old/git_ff_sync.sh" || { echo "FAIL: stripped copy lost the ancestry check" >&2; exit 1; }
chmod 700 "$T/fix/"* "$T/fix-old/"*

# ── fixture 999 remote ───────────────────────────────────────────────────────
R="$T/remote999.git"; W="$T/w999"
GD=".claude/skills/nine-router-setup/scripts"
mkdir -p "$W/$GD/macos"
printf '%s\n' '#!/usr/bin/env bash' 'echo "[fixture] setup-macos $*"' 'exit 0' > "$W/$GD/setup-macos.sh"
cat > "$W/$GD/macos/install-9router-guards.sh" <<'EOF'
#!/usr/bin/env bash
# #20: say which copy of the skill this guard run came from.
echo "GUARD_FROM=$(cd -P "$(dirname "$0")/../.." && pwd -P)" >> "${GUARD_LOG:-/dev/null}"
echo "[fixture] 9router-guards ran: $*"
exit 0
EOF
printf '1.0\n' > "$W/.claude/skills/nine-router-setup/VERSION"
"$G" init -q --bare -b main "$R"
( cd "$W" && "$G" init -q -b main && gg add -A && gg commit -q -m v1 \
  && "$G" push -q "$R" main && "$G" checkout -q -b batch/old && "$G" push -q -u "$R" batch/old ) || { echo "FAIL: fixture build" >&2; exit 1; }

# every shallow clone is made now, at v1; the remote advances afterwards
SHALLOWS="s1 s2 s3 s4 d1 d2"
for _c in $SHALLOWS; do
  "$G" clone -q --depth 1 --no-single-branch "file://$R" "$T/clone-$_c" && "$G" -C "$T/clone-$_c" checkout -q batch/old \
    || { echo "FAIL: shallow clone $_c" >&2; exit 1; }
done
( cd "$W" && "$G" checkout -q main && : > FIXED && gg add -A && gg commit -q -m v2 \
  && "$G" push -q "$R" main && "$G" push -q "$R" --delete batch/old ) || { echo "FAIL: fixture advance" >&2; exit 1; }
MAIN="$("$G" -C "$R" rev-parse main)"
# the cut: a depth-1 fetch of main (what the roll's onboarding copy gets every run)
# leaves HEAD (v1) unreachable from origin/main (v2): an "unrelated root".
for _c in $SHALLOWS; do
  "$G" -C "$T/clone-$_c" fetch -q --depth 1 origin +refs/heads/main:refs/remotes/origin/main || { echo "FAIL: cut $_c" >&2; exit 1; }
done

# ── helpers ──────────────────────────────────────────────────────────────────
seed_root() {  # case_dir [999 clone to move into place]
  C="$1"
  mkdir -p "$C/home" "$C/root/secrets" "$C/root/skills" \
           "$C/root/npm-global/lib/node_modules/openclaw" "$C/home/.local/share/999/npm/lib/node_modules/9router"
  printf 'v78.0.0\n' > "$C/root/skills/.onboarding-version"
  printf '{"name":"openclaw","version":"2026.10.3"}\n' > "$C/root/npm-global/lib/node_modules/openclaw/package.json"
  printf '{"name":"9router","version":"0.5.50"}\n' > "$C/home/.local/share/999/npm/lib/node_modules/9router/package.json"
  printf 'OLLAMA_CLOUD_API_KEY=test-ollama-value-123\nDEEPSEEK_API_KEY=test-deepseek-value-456\n' > "$C/root/secrets/.env"
  chmod 600 "$C/root/secrets/.env"
  printf '{"gateway":{"port":18789}}\n' > "$C/root/openclaw.json"
  if [ -n "${2:-}" ]; then mv "$2" "$C/home/999-setup"; else "$G" clone -q "$R" "$C/home/999-setup" || { echo "FAIL: seed 999" >&2; exit 1; }; fi
}
run_su() {  # case_dir [ENV=val ...] -> exit code
  C="$1"; shift
  env PATH="$T/bin:$PATH" HOME="$C/home" OPENCLAW_ROOT="$C/root" FIXTURES="$T/fix" TMPDIR="$T/tmp" \
    ENVLOG="$C/env.log" GUARD_LOG="$C/guard.log" "$@" \
    bash "$SRC" --roll-id "roll-${C##*/}" --openclaw-target 2026.10.4 --ninerouter-target 0.5.50 --foreground > "$C/out.txt" 2>&1
  echo $?
}
ST() { printf '%s/root/fleet-refresh/agent-pull-status.json' "$1"; }
json() {  # file key -> scalar
  $PY -c 'import json,sys
d=json.load(open(sys.argv[1])); v=d.get(sys.argv[2],"")
print(json.dumps(v,sort_keys=True) if isinstance(v,(dict,list)) else ("" if v is None else v))' "$1" "$2" 2>/dev/null
}
steps() { $PY -c 'import json,sys; d=json.load(open(sys.argv[1]))["step_exit_codes"]; print(d.get("999-setup"), d.get("9router"))' "$(ST "$1")" 2>/dev/null; }
tree_sum() { ( cd "$1" && find . -type f | LC_ALL=C sort | xargs cksum | cksum ); }

# ══ item 10: the roll's operator escalation is held for the watcher ══════════
A1="$T/a1"; seed_root "$A1"
RA1="$(run_su "$A1" WEEKLY_RC=0 "HOLD_NOTE=✅ OpenClaw skill update 27.1.69 verified-installed. DEEPSEEK_API_KEY=abc123secretvalue")"
[ "$RA1" = 0 ] && ok "A1: clean run with a held note exits 0" || bad "A1: exit $RA1"
grep -q '^ROLL=roll-a1$' "$A1/env.log" && grep -q '^RUN=ap-roll-a1-' "$A1/env.log" \
  && grep -q "^ESC=$A1/root/fleet-refresh/operator-escalation-held.txt\$" "$A1/env.log" \
  && ok "A1: the content step is handed SELF_UPDATE_ROLL_ID, SELF_UPDATE_RUN_ID (ap-*) and the escalation file" \
  || bad "A1: roll env missing in the content step: $(tr '\n' ' ' < "$A1/env.log")"
case "$(json "$(ST "$A1")" error_tail)" in
  *"[operator escalation held for the watcher, NOT sent]"*"verified-installed"*) ok "A1: the held headline reaches the status file error_tail" ;;
  *) bad "A1: error_tail lacks the held headline" ;;
esac
json "$(ST "$A1")" error_tail | grep -q 'abc123secretvalue' && bad "A1: a key value leaked into error_tail" || ok "A1: the headline is redacted like the log tail"
[ -z "$(json "$(ST "$A1")" stuck_reason)" ] && ok "A1: a successful run does not become a stuck_reason" || bad "A1: stuck_reason on a clean run: $(json "$(ST "$A1")" stuck_reason)"

A2="$T/a2"; seed_root "$A2"
RA2="$(run_su "$A2" WEEKLY_RC=1 "HOLD_NOTE=⏳ OpenClaw skill update 27.1.69: files synced, NOT all verified yet.")"
[ "$RA2" = 1 ] && ok "A2: failed content step exits 1" || bad "A2: exit $RA2"
SR2="$(json "$(ST "$A2")" stuck_reason)"
case "$SR2" in
  *"update exited 1"*"operator escalation held for the watcher (not sent)"*"NOT all verified yet"*) ok "A2: a failed job carries the held headline in stuck_reason" ;;
  *) bad "A2: stuck_reason: $SR2" ;;
esac

A3="$T/a3"; seed_root "$A3"; mkdir -p "$A3/root/fleet-refresh"
printf 'OLD NOTE FROM LAST ROLL\n' > "$A3/root/fleet-refresh/operator-escalation-held.txt"
RA3="$(run_su "$A3" WEEKLY_RC=0)"
json "$(ST "$A3")" error_tail | grep -q 'OLD NOTE FROM LAST ROLL' && bad "A3: an earlier run's note was read as this run's" \
  || ok "A3: a stale note from an earlier run is cleared at start"
[ ! -e "$A3/root/fleet-refresh/operator-escalation-held.txt" ] && ok "A3: no held file when nothing was held" || bad "A3: held file survived"
json "$(ST "$A3")" error_tail | grep -q 'operator escalation held' && bad "A3: error_tail names a hold that never happened" || ok "A3: no hold line when nothing was held"

# ══ #20 / #28: guards run from the 999-setup copy; the delivered copy is compared and stamped ══
nine_case() {  # name how(link|copy|none|mixed) -> runs a clean job; sets C, D
  C="$T/$1"; seed_root "$C"
  mkdir -p "$C/home/.claude/skills"
  D="$C/home/.claude/skills/nine-router-setup"; S999="$C/home/999-setup/.claude/skills/nine-router-setup"
  case "$2" in
    link)    ln -s "$S999" "$D" ;;
    copy)    cp -R "$S999" "$D" ;;
    none)    : ;;
    mixed)   ln -s "$S999" "$D"; mkdir -p "$C/home/.claude-nine/skills" && cp -R "$S999" "$C/home/.claude-nine/skills/nine-router-setup" \
               && printf 'drift\n' >> "$C/home/.claude-nine/skills/nine-router-setup/VERSION" ;;
  esac
  RN="$(run_su "$C" WEEKLY_RC=0)"
}
EXP999() { ( cd -P "$1/home/999-setup" && pwd -P ); }

C="$T/n-stale"; seed_root "$C"; mkdir -p "$C/home/.claude/skills"; D_S="$C/home/.claude/skills/nine-router-setup"
mkdir -p "$D_S/scripts" && printf 'OLD INSTALLER Oct 7\n' > "$D_S/SKILL.md" && printf 'old\n' > "$D_S/scripts/old.sh"
BEFORE_S="$(tree_sum "$D_S")"
RN="$(run_su "$C" WEEKLY_RC=0)"
case "$(cat "$C/guard.log" 2>/dev/null)" in "GUARD_FROM=$(EXP999 "$C")/.claude/skills/nine-router-setup") ok "N1: guards ran from the 999-setup copy" ;; *) bad "N1: guards ran from: $(cat "$C/guard.log" 2>/dev/null)" ;; esac
grep -q "WARN 9router: delivered nine-router-setup copy differs from the verified 999-setup copy (stale: $D_S)" "$C/out.txt" \
  && ok "N1: the stale delivered copy is named in the log" || bad "N1: no stale-copy warning: $(grep 'nine-router-setup' "$C/out.txt" | head -2)"
STAMP="$C/root/fleet-refresh/nine-router-setup.stamp"
grep -q '^delivered=stale$' "$STAMP" && grep -q "^stale_copies=$D_S\$" "$STAMP" && grep -q '^999_head=[0-9a-f]\{40\}$' "$STAMP" \
  && ok "N1: the stamp records delivered=stale, the stale path and the verified 999 head" || bad "N1: stamp: $(cat "$STAMP" 2>/dev/null | tr '\n' ' ')"
[ "$(tree_sum "$D_S")" = "$BEFORE_S" ] && ok "N1: the stale delivered copy was not modified (nothing copied over it, nothing deleted)" || bad "N1: delivered copy changed"
[ "$(steps "$C")" = "0 0" ] && ok "N1: a stale delivered copy is a warning, not a failed step" || bad "N1: step codes $(steps "$C")"
case "$(ls -l "$STAMP" | cut -c1-10)" in -rw-------) ok "N1: stamp is mode 600" ;; *) bad "N1: stamp mode" ;; esac

nine_case n-link link
grep -q 'delivered nine-router-setup copy matches the verified 999-setup copy' "$C/out.txt" && grep -q '^delivered=same$' "$C/root/fleet-refresh/nine-router-setup.stamp" \
  && ok "N2: a delivered symlink to the 999-setup copy matches" || bad "N2: symlink case: $(grep 'nine-router-setup' "$C/out.txt" | head -2)"
nine_case n-copy copy
grep -q 'delivered nine-router-setup copy matches the verified 999-setup copy' "$C/out.txt" && grep -q '^delivered=same$' "$C/root/fleet-refresh/nine-router-setup.stamp" \
  && ok "N3: an identical delivered copy matches" || bad "N3: identical copy case: $(grep 'nine-router-setup' "$C/out.txt" | head -2)"
nine_case n-none none
grep -q 'no delivered nine-router-setup copy' "$C/out.txt" && ok "N4: no delivered copy is stated, guards still run from the 999-setup copy" || bad "N4: absent case"
nine_case n-mixed mixed
grep -q "stale: $C/home/.claude-nine/skills/nine-router-setup);" "$C/out.txt" && ! grep -q "stale:.*$C/home/.claude/skills" "$C/out.txt" \
  && ok "N5: only the drifted ~/.claude-nine copy is reported stale; the linked ~/.claude copy is not" || bad "N5: mixed case: $(grep 'WARN 9router' "$C/out.txt" | head -2)"

# ══ #26: a shallow 999-setup clone is deepened before any ancestry check ═════
shallow_state() {  # clone -> "shallow=<bool> mergebase=<n|none> unmerged=<n>"
  printf 'shallow=%s mergebase=%s unmerged=%s' "$("$G" -C "$1" rev-parse --is-shallow-repository)" \
    "$("$G" -C "$1" merge-base HEAD origin/main 2>/dev/null | cut -c1-7 | grep . || echo none)" \
    "$("$G" -C "$1" rev-list --count origin/main..HEAD 2>/dev/null)"
}
PRE="$(shallow_state "$T/clone-s1")"
[ "$PRE" = "shallow=true mergebase=none unmerged=1" ] \
  && ok "S0: fixture reproduces the defect (shallow, no merge-base, a merged commit counted as unmerged)" || bad "S0: fixture state: $PRE"

# S1: self-update + the fixed git_ff_sync.sh
S1="$T/s1"; seed_root "$S1" "$T/clone-s1"
RS1="$(run_su "$S1" WEEKLY_RC=0)"
[ "$RS1" = 0 ] && [ "$(steps "$S1")" = "0 0" ] && ok "S1: shallow, cut 999 clone: 999-setup and 9router both pass" || bad "S1: exit $RS1 steps $(steps "$S1")"
grep -q 'is a SHALLOW clone - running git fetch --unshallow before any ancestry check' "$S1/out.txt" && ok "S1: the log says the clone was deepened" || bad "S1: no unshallow line"
[ "$("$G" -C "$S1/home/999-setup" rev-parse --is-shallow-repository)" = false ] && ok "S1: the clone is no longer shallow" || bad "S1: still shallow"
[ "$("$G" -C "$S1/home/999-setup" rev-parse HEAD)" = "$MAIN" ] && ok "S1: the checkout is at origin/main" || bad "S1: HEAD is not origin/main"

# S2: self-update's OWN guard, with the PRE-FIX git_ff_sync.sh served by main
S2="$T/s2"; seed_root "$S2" "$T/clone-s2"
RS2="$(run_su "$S2" WEEKLY_RC=0 FIXTURES_GIT="$T/fix-old")"
[ "$RS2" = 0 ] && [ "$(steps "$S2")" = "0 0" ] && ok "S2: self-update.sh deepens the clone itself (pre-fix git_ff_sync.sh also passes)" || bad "S2: exit $RS2 steps $(steps "$S2"): $(grep 'FAIL 999' "$S2/out.txt" | head -1)"

# S3: failed unshallow fails closed and names itself; 9router is refused
"$G" -C "$T/clone-s3" remote set-url origin "$T/does-not-exist.git"
S3="$T/s3"; seed_root "$S3" "$T/clone-s3"
RS3="$(run_su "$S3" WEEKLY_RC=0)"
[ "$(steps "$S3")" = "23 24" ] && [ "$RS3" = 23 ] && ok "S3: an unshallow that cannot reach the remote fails 999-setup (23) and refuses 9router" || bad "S3: exit $RS3 steps $(steps "$S3")"
grep -q 'FAIL: git fetch --unshallow failed' "$S3/out.txt" && grep -q 'shallow clone and git fetch --unshallow failed' "$S3/out.txt" \
  && ok "S3: the failure says it is a fetch problem, not an unrelated history" || bad "S3: failure not named"
[ -s "$S3/guard.log" ] && bad "S3: guards ran from an unverified checkout" || ok "S3: guards never ran"

# git_ff_sync.sh direct: pre-fix control, then the fix
OLD_OUT="$(sh "$T/fix-old/git_ff_sync.sh" "$T/clone-d1" 2>&1)"; OLD_RC=$?
[ "$OLD_RC" = 3 ] && echo "$OLD_OUT" | grep -q '1 commit(s) are not in origin/main; left untouched' \
  && ok "D1 control: pre-fix git_ff_sync.sh refuses a cut shallow clone (rc 3, 'left untouched' - the false verdict)" || bad "D1 control: rc $OLD_RC: $OLD_OUT"
NEW_OUT="$(sh "$FFSYNC_SRC" "$T/clone-d2" 2>&1)"; NEW_RC=$?
[ "$NEW_RC" = 0 ] && echo "$NEW_OUT" | grep -q 'switched batch/old -> main' && [ "$("$G" -C "$T/clone-d2" rev-parse HEAD)" = "$MAIN" ] \
  && ok "D2: fixed git_ff_sync.sh deepens first and syncs the same clone (rc 0, on main)" || bad "D2: rc $NEW_RC: $NEW_OUT"

[ "$fail" -eq 0 ] && { echo "PASS: self-update Big Fleet Roll fixes (item 10, #20, #26)"; exit 0; }
echo "FAIL: self-update Big Fleet Roll fixes (item 10, #20, #26)"; exit 1
