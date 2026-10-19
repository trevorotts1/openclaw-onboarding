#!/usr/bin/env bash
# CAN012 regression: self-update.sh's 999-setup step must bring ITS checkout to
# origin/main (safe git_ff_sync.sh semantics), verify HEAD == origin/main (and the
# --999-sha pin), and the 9router step must refuse to run guard code from a
# checkout that was not verified.
#
# Reproduces the roll-20261019 canary: the checkout sits on a local branch whose
# upstream was deleted on the remote after the merge, and origin/main carries the
# FIXED guard. The stub guard exits 4 (like the stale guard did) unless the
# checkout it runs from contains FIXED. Old self-update.sh: 999-setup "OK", stale
# guard runs, 9router rc 4. Fixed: checkout moves to main, guard passes.
#
# Real self-update.sh, real git, scratch bare remote. Nothing leaves this machine;
# the real ~/.openclaw, ~/999-setup and persist-home are never read or written.
# SELF_UPDATE_SRC=<path> runs a different copy of the script (mutation proof).
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="${SELF_UPDATE_SRC:-$HERE/../self-update.sh}"
FFSYNC_SRC="$HERE/../../shared-utils/git_ff_sync.sh"
[ -f "$SRC" ] && [ -f "$FFSYNC_SRC" ] || { echo "FAIL: missing $SRC or $FFSYNC_SRC" >&2; exit 1; }
G="$(command -v git)"
PY="python3 -I"

T="$(mktemp -d "${TMPDIR:-/tmp}/self-update-999sync.XXXXXX")" || exit 1
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/fix" "$T/tmp"
fail=0
ok()  { echo "ok - $*"; }
bad() { echo "FAIL - $*"; fail=1; }

# ── stubs (curl serves fixtures; git is the REAL git; macOS tools are no-ops) ──
cp "$FFSYNC_SRC" "$T/fix/git_ff_sync.sh"   # what main serves at shared-utils/git_ff_sync.sh
cat > "$T/bin/curl" <<'EOF'
#!/usr/bin/env bash
[ "$1" = "--version" ] && { echo "curl 8.0.0"; exit 0; }
url=""; dest=""
while [ "$#" -gt 0 ]; do
  case "$1" in -o) dest="$2"; shift 2 ;; --max-time) shift 2 ;; -*) shift ;; *) url="$1"; shift ;; esac
done
[ -n "$url" ] && [ -n "$dest" ] || exit 2
src="$FIXTURES/$(basename "$url")"
[ -f "$src" ] || { echo "curl-stub: no fixture for $(basename "$url")" >&2; exit 22; }
cp "$src" "$dest"
EOF
printf '%s\n' '#!/usr/bin/env bash' 'case "$1" in -s) echo Darwin ;; -m) echo arm64 ;; *) echo Darwin ;; esac' > "$T/bin/uname"
for n in claude osascript shasum tar security xcode-select; do printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$T/bin/$n"; done
chmod 700 "$T/bin/"*
for n in oc-atomic-upgrade.sh weekly-full-update.sh; do printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$T/fix/$n"; done
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$T/fix/oc-schema-migrate.py"

gg() { "$G" -c user.name=t -c user.email=t@t -c commit.gpgsign=false "$@"; }

# ── fixture 999 remote: v1 = stale guard code, then main gains FIXED ───────────
R="$T/remote.git"; W="$T/work"
GD=".claude/skills/nine-router-setup/scripts"
mkdir -p "$W/$GD/macos"
printf '%s\n' '#!/usr/bin/env bash' 'echo "[fixture] setup-macos $*"' 'exit 0' > "$W/$GD/setup-macos.sh"
cat > "$W/$GD/macos/install-9router-guards.sh" <<'EOF'
#!/usr/bin/env bash
top="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
if [ -f "$top/FIXED" ]; then echo "[fixture] 9router-guards FIXED code ran: $*"; exit 0; fi
echo "[fixture] 9router-guards STALE code ran: MISSING EDIT6/EDIT7"; exit 4
EOF
"$G" init -q --bare -b main "$R"
( cd "$W" && "$G" init -q -b main && gg add -A && gg commit -q -m v1 \
  && "$G" push -q "$R" main && "$G" checkout -q -b batch/old && "$G" push -q -u "$R" batch/old ) || { echo "FAIL: fixture build" >&2; exit 1; }

mkcase() {  # name -> prints HOME dir; a persist-home clone on batch/old with a GONE upstream
  C="$T/$1"; H="$C/home"; CK="$C/root/persist-home/999-setup"
  mkdir -p "$H/.9router" "$C/root/skills" "$C/root/secrets" "$C/root/npm-global/lib/node_modules/openclaw"
  printf 'v1\n' > "$C/root/skills/.onboarding-version"
  printf '{"name":"openclaw","version":"2026.10.3"}\n' > "$C/root/npm-global/lib/node_modules/openclaw/package.json"
  printf '{}\n' > "$C/root/openclaw.json"
  "$G" clone -q "$R" "$CK" && "$G" -C "$CK" checkout -q batch/old   # tracks origin/batch/old
}
for _c in a b c d; do mkcase $_c; done
# main moves on (merged fix) and the merged branch is deleted on the remote
( cd "$W" && "$G" checkout -q main && : > FIXED && gg add -A && gg commit -q -m fixed \
  && "$G" push -q "$R" main && "$G" push -q "$R" --delete batch/old ) || { echo "FAIL: fixture advance" >&2; exit 1; }
MAIN="$("$G" -C "$R" rev-parse main)"

run() {  # case_dir [extra self-update args] -> exit code on stdout
  C="$1"; shift
  PATH="$T/bin:$PATH" HOME="$C/home" OPENCLAW_ROOT="$C/root" FIXTURES="$T/fix" TMPDIR="$T/tmp" \
    bash "$SRC" --roll-id "r-${C##*/}" --openclaw-target 2026.10.4 --ninerouter-target 0.5.104 \
      --foreground "$@" > "$C/out.txt" 2>&1
  rc=$?
  cat "$C/root/self-update/"*.log >> "$C/out.txt" 2>/dev/null   # guard output goes to the roll log
  echo $rc
}
steps() { $PY -c 'import json,sys; d=json.load(open(sys.argv[1]))["step_exit_codes"]; print(d.get("999-setup"), d.get("9router"))' \
  "$1/root/fleet-refresh/agent-pull-status.json" 2>/dev/null; }

# ── A: gone upstream, clean, 0 unmerged -> moved to main, guards run FIXED code ─
C="$T/a"; CK="$C/root/persist-home/999-setup"; RA="$(run "$C")"
[ "$(steps "$C")" = "0 0" ] && ok "A: 999-setup 0 and 9router 0" || bad "A: step codes: $(steps "$C") (want 0 0)"
[ "$("$G" -C "$CK" rev-parse HEAD)" = "$MAIN" ] && ok "A: checkout HEAD == origin/main" \
  || bad "A: checkout HEAD $("$G" -C "$CK" rev-parse --short HEAD) is not origin/main"
[ "$("$G" -C "$CK" symbolic-ref --short HEAD 2>/dev/null)" = main ] && ok "A: checkout is on main" || bad "A: not on main"
[ -n "$("$G" -C "$CK" branch --list batch/old)" ] && ok "A: old branch kept (never deleted)" || bad "A: old branch deleted"
grep -q 'FIXED code ran' "$C/out.txt" && ok "A: guards ran the FIXED code" || bad "A: guards did not run fixed code"
grep -q 'STALE code ran' "$C/out.txt" && bad "A: STALE guard code ran" || ok "A: stale guard code never ran"

# ── B: gone upstream + 1 unmerged commit -> step FAILS loudly, nothing moved ───
C="$T/b"; CK="$C/root/persist-home/999-setup"; ( cd "$CK" && : > mine && gg add -A && gg commit -q -m "local work" )
HB="$("$G" -C "$CK" rev-parse HEAD)"; RB="$(run "$C")"
[ "$(steps "$C")" = "23 24" ] && ok "B: 999-setup 23, 9router 24 (refused)" || bad "B: step codes: $(steps "$C")"
[ "$RB" = 23 ] && ok "B: exit is the first failed step (23)" || bad "B: exit $RB (want 23)"
grep -q 'FAIL 999-setup' "$C/out.txt" && grep -q 'branch=batch/old unmerged_commits=1' "$C/out.txt" \
  && ok "B: failure names branch and unmerged count" || bad "B: failure line missing branch/unmerged count"
grep -q 'OK 999-setup' "$C/out.txt" && bad "B: logged OK 999-setup" || ok "B: no OK 999-setup line"
grep -q '9router-guards' "$C/out.txt" && bad "B: guards ran from an unverified checkout" || ok "B: guards never ran"
grep -q 'REFUSED 9router' "$C/out.txt" && ok "B: 9router step refused" || bad "B: no REFUSED 9router line"
[ "$("$G" -C "$CK" rev-parse HEAD)" = "$HB" ] && [ "$("$G" -C "$CK" symbolic-ref --short HEAD)" = batch/old ] \
  && ok "B: checkout and local commit untouched" || bad "B: checkout was modified"

# ── C: pin ------------------------------------------------------------------
C="$T/c"; CK="$C/root/persist-home/999-setup"; RC="$(run "$C" --999-sha "${MAIN:0:12}")"
[ "$(steps "$C")" = "0 0" ] && ok "C: matching pin accepted" || bad "C: matching pin: $(steps "$C")"
C="$T/d"; CK="$C/root/persist-home/999-setup"; RD="$(run "$C" --999-sha 1234567abcdef)"
[ "$(steps "$C")" = "23 24" ] && grep -q 'not the pinned 999-setup sha' "$C/out.txt" \
  && ok "D: wrong pin fails 999-setup and refuses 9router" || bad "D: wrong pin: $(steps "$C")"

[ "$fail" -eq 0 ] && { echo "PASS: self-update 999 sync (CAN012)"; exit 0; }
echo "FAIL: self-update 999 sync (CAN012)"; exit 1
