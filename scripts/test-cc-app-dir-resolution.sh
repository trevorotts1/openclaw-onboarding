#!/usr/bin/env bash
# ============================================================================
# test-cc-app-dir-resolution.sh
#
# REGRESSION GUARD for APPDIR-01 in
# 32-command-center-setup/scripts/run-full-install.sh — a FALSE-SUCCESS defect.
#
# THE DEFECT (three lines, one failure mode):
#   1. DASHBOARD_DIR was hardcoded to ${HOME}/projects/command-center with NO
#      override of any kind — no flag, no env var.
#   2. The update.sh call site exported CC_APP_DIR="$DASHBOARD_DIR" and
#      CC_PORT="$DASHBOARD_PORT", CLOBBERING any ambient value the operator had
#      set, so pinning the env var could not rescue (1) either.
#   3. When that hardcoded path was not a git checkout, --update-only logged
#      `WARN ... .git not found — run full install first (skipping refresh)`
#      and FELL THROUGH THE ENTIRE PHASE — no build, no restart, no failure.
#
# CONSEQUENCE, proven on the operator Mac: ~/projects/command-center exists
# there as a non-git DATA directory (mission-control.db + backups) while the
# live install sits elsewhere. Phase 6 therefore deployed NOTHING and did not
# fail; on a box whose downstream gates are green the run ends 0. A fleet roll
# inherits this: boxes report success having deployed nothing.
#
# THE FIX:
#   * cc_resolve_dashboard_dir() — precedence --app-dir > $CC_APP_DIR > default,
#     and DASHBOARD_PORT honors an ambient $CC_PORT. Because DASHBOARD_DIR is
#     now DERIVED from CC_APP_DIR, the update.sh call site can no longer clobber
#     an operator pin — it propagates it.
#   * cc_validate_cc_checkout() — MIRRORS blackceo-command-center update.sh's
#     `_cc_validate_checkout` (git toplevel + origin slug + app structure +
#     package.json name). Uses `git rev-parse --show-toplevel`, so a linked
#     worktree (where .git is a FILE, not a directory) validates correctly —
#     the old `[[ -d .git ]]` test did not.
#   * cc_assert_update_only_checkout() — fail_install()s (exit 1) naming the
#     resolved path, the rejection reason, and the --app-dir remedy. Never a
#     silent skip.
#
# THIS TEST extracts the REAL functions verbatim (awk, function-name anchored so
# it survives line-number drift) from the REAL installer, and additionally runs
# the REAL installer end-to-end against a sandboxed HOME. No reimplementation of
# the logic under test.
#
#   T0  the fixed functions are present and extractable.
#   T1  TEETH — the OLD gate expression (`[[ ! -d "$DASHBOARD_DIR/.git" ]]` ->
#               warn -> continue) does NOT terminate on a decoy directory, and
#               ALSO misjudges a linked worktree. Proves the defect is real.
#   T2  static — the old skip-shape is GONE from the installer.
#   T3  --app-dir flag wins over $CC_APP_DIR and over the default.
#   T4  $CC_APP_DIR is honored when no flag is given (and NOT clobbered).
#   T5  neither set -> the historical default is preserved (no regression).
#   T6  $CC_PORT honored; unset -> 4000 (no regression).
#   T7  validator rejects a non-git decoy directory.
#   T8  validator rejects a git checkout whose origin is a DIFFERENT repo.
#   T9  validator rejects a SUBDIRECTORY of a valid checkout.
#   T10 validator ACCEPTS a valid checkout (proceeds normally).
#   T11 validator ACCEPTS a linked git worktree, where .git is a FILE.
#   T12 assert FAILS CLOSED (nonzero) on the decoy, and the message names the
#       resolved path, the reason, and --app-dir.
#   T13 assert PASSES on a valid checkout and canonicalizes DASHBOARD_DIR.
#   T14 END-TO-END: the REAL installer, --update-only, decoy at the default
#       path -> nonzero exit AND execution never reaches a later phase.
#   T15 END-TO-END: same, but --app-dir points at a valid checkout -> the gate
#       is passed (execution proceeds beyond it).
#
# Self-contained: bash + git. No network (all remotes are local paths), no
# gateway, no pm2, no credentials, no box is touched.
# ============================================================================
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
INSTALLER="$REPO_ROOT/32-command-center-setup/scripts/run-full-install.sh"

[ -f "$INSTALLER" ] || { echo "FATAL: installer not found at $INSTALLER"; exit 2; }

PASS=0; FAIL=0
ok()  { printf '  \033[32m✓ PASS\033[0m — %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  \033[31m✗ FAIL\033[0m — %s\n' "$1"; FAIL=$((FAIL+1)); }
hdr() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# Extract ONE function verbatim, anchored by name (survives line-number drift).
extract_func() {
  local name="$1" file="$2"
  awk -v pat="^${name}\\\\(\\\\) \\\\{" '
    $0 ~ pat { p=1 }
    p { print }
    p && /^}/ { exit }
  ' "$file"
}

# A function that cannot be extracted is a FAILURE, not an abort: the suite
# keeps running so the report shows exactly which behaviours are missing (this
# is also what makes the guard measurable against a pre-fix revision, where
# none of these functions exist yet). Every dependent test then fails and the
# suite still exits nonzero, so name/shape drift is caught just as loudly.
FRAG="$(mktemp)"
hdr "T0 — the fixed functions are present and extractable"
MISSING=0
for fn in cc_resolve_dashboard_dir cc_repo_slug cc_validate_cc_checkout \
          cc_assert_update_only_checkout; do
  body="$(extract_func "$fn" "$INSTALLER")"
  if [ -z "$body" ]; then
    bad "T0: could not extract function '$fn' from the installer (missing, or name/shape drift)"
    MISSING=$((MISSING+1))
  else
    printf '%s\n\n' "$body" >> "$FRAG"
  fi
done
[ "$MISSING" -eq 0 ] && ok "T0: all 4 APPDIR-01 functions extracted verbatim from the real installer"

# The installer's module-level constants the extracted functions close over.
# Read them FROM the installer rather than hardcoding, so a change there is
# picked up here instead of silently diverging.
DASHBOARD_REPO_LINE="$(grep -m1 '^DASHBOARD_REPO=' "$INSTALLER")"
CC_PKG_NAME_LINE="$(grep -m1 '^CC_PKG_NAME=' "$INSTALLER")"
CC_MARKERS_LINE="$(grep -m1 '^CC_REQUIRED_MARKERS=' "$INSTALLER")"
for l in "$DASHBOARD_REPO_LINE" "$CC_PKG_NAME_LINE" "$CC_MARKERS_LINE"; do
  # Same posture as T0: absent constants are a reported failure, not an abort.
  [ -n "$l" ] || bad "T0: a module-level constant (DASHBOARD_REPO / CC_PKG_NAME / CC_REQUIRED_MARKERS) is missing from the installer"
done
{
  printf '%s\n%s\n%s\n' "$DASHBOARD_REPO_LINE" "$CC_PKG_NAME_LINE" "$CC_MARKERS_LINE"
  # log()/fail_install() stubs: the real ones write to $LOG_FILE and mutate the
  # jq state file, neither of which is under test here. fail_install's CONTRACT
  # (print the reason, exit nonzero) is preserved exactly — that contract is
  # what T12 asserts.
  printf 'log() { printf "%%s %%s\\n" "$1" "$2" >&2; }\n'
  printf 'fail_install() { printf "FAIL_INSTALL: %%s\\n" "$1" >&2; exit 1; }\n'
} >> "$FRAG"

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
# A bare local repo named blackceo-command-center.git, so a clone's origin slug
# normalizes to the same value the installer expects. No network.
make_cc_origin() {
  local root; root="$(mktemp -d)"
  local bare="$root/blackceo-command-center.git"
  git init --quiet --bare "$bare"
  local seed="$root/seed"
  git init --quiet "$seed"
  git -C "$seed" config user.email "t@example.test"
  git -C "$seed" config user.name "T"
  printf '{ "name": "mission-control", "version": "0.0.0" }\n' > "$seed/package.json"
  printf 'export default {};\n' > "$seed/next.config.mjs"
  mkdir -p "$seed/src"; printf 'x\n' > "$seed/src/index.ts"
  git -C "$seed" add -A >/dev/null 2>&1
  git -C "$seed" commit --quiet -m "seed" >/dev/null 2>&1
  git -C "$seed" branch -M main >/dev/null 2>&1
  git -C "$seed" remote add origin "$bare"
  git -C "$seed" push --quiet -u origin main >/dev/null 2>&1
  printf '%s %s' "$root" "$bare"
}

# A clone of that origin = a valid Command Center checkout.
make_cc_checkout() {
  local bare="$1" dest="$2"
  git clone --quiet "$bare" "$dest" >/dev/null 2>&1
  git -C "$dest" config user.email "t@example.test"
  git -C "$dest" config user.name "T"
}

# A directory that is NOT a git repo but looks plausible — the exact operator-box
# shape: a data directory sitting on the default path.
make_decoy() {
  local d="$1"; mkdir -p "$d"
  printf 'sqlite-ish\n' > "$d/mission-control.db"
  mkdir -p "$d/backups"
}

# Run one extracted function in a subshell with a wired environment.
# Everything the function needs is set explicitly; nothing leaks from this shell.
run_resolve() {  # run_resolve <home> <app_dir_flag_set> <app_dir_flag> <cc_app_dir> <cc_port>
  ( set -u
    HOME="$1"; APP_DIR_FLAG_SET="$2"; APP_DIR_FLAG="$3"
    if [ -n "$4" ]; then CC_APP_DIR="$4"; else unset CC_APP_DIR 2>/dev/null || true; fi
    if [ -n "$5" ]; then CC_PORT="$5"; else unset CC_PORT 2>/dev/null || true; fi
    # shellcheck disable=SC1090
    source "$FRAG"
    cc_resolve_dashboard_dir
    printf '%s|%s|%s|%s\n' "$DASHBOARD_DIR" "$DASHBOARD_DIR_SOURCE" "$DASHBOARD_DIR_PINNED" "$DASHBOARD_PORT"
  )
}

run_validate() {  # run_validate <candidate> -> prints "rc|reason|path"
  ( set -u
    # shellcheck disable=SC1090
    source "$FRAG"
    if cc_validate_cc_checkout "$1"; then
      printf '0||%s\n' "$CC_CANDIDATE_PATH"
    else
      printf '1|%s|\n' "$CC_CANDIDATE_REASON"
    fi
  )
}

# ============================================================================
# T1 — TEETH: the OLD gate shape does not terminate, and misreads a worktree
# ============================================================================
hdr "T1 — teeth: the pre-fix gate shape skips silently instead of failing"
ROOT="$(mktemp -d)"
make_decoy "$ROOT/decoy"
# This is the ORIGINAL line, verbatim in shape, as it stood on the defective
# revision. Reproduced here (not extracted) precisely because the fix deleted
# it — T2 below asserts it never comes back.
old_gate_reached_the_end=0
DASHBOARD_DIR="$ROOT/decoy"
if [ ! -d "$DASHBOARD_DIR/.git" ]; then
  : "WARN: .git not found — run full install first (skipping refresh)"
else
  : "would deploy"
fi
old_gate_reached_the_end=1   # <- reached unconditionally: the skip is not fatal
T1A=0; [ "$old_gate_reached_the_end" -eq 1 ] && T1A=1

# And the same `-d` test misjudges a LINKED WORKTREE, where .git is a FILE.
read -r OROOT OBARE <<EOF
$(make_cc_origin)
EOF
make_cc_checkout "$OBARE" "$ROOT/main-checkout"
git -C "$ROOT/main-checkout" worktree add --quiet --detach "$ROOT/wt" >/dev/null 2>&1
T1B=0
if [ -f "$ROOT/wt/.git" ] && [ ! -d "$ROOT/wt/.git" ]; then T1B=1; fi

if [ "$T1A" -eq 1 ] && [ "$T1B" -eq 1 ]; then
  ok "T1: old shape continues past a decoy (no failure) AND '-d .git' is false for a real linked worktree — both defects real"
else
  bad "T1: could not reproduce the pre-fix behaviour (continued=$T1A worktree-git-is-file=$T1B) — harness broken"
fi
rm -rf "$ROOT" "$OROOT"

# ============================================================================
# T2 — static: the silent-skip shape is gone from the installer
# ============================================================================
hdr "T2 — static: the old '.git not found ... skipping refresh' skip is gone"
T2BAD=0
grep -q 'skipping refresh' "$INSTALLER" && {
  bad "T2: the old 'skipping refresh' silent-skip message is still present"; T2BAD=1; }
# The `-d $DASHBOARD_DIR/.git` test is legitimate in ONE place — the FULL-INSTALL
# branch, where "no .git" means "clone it here" rather than "skip silently".
# Assert it survives exactly once, in code (not a comment), and that the branch
# it guards really is the clone. Any second occurrence means the update-only
# skip has crept back.
GATE_HITS="$(grep -n '^[^#]*\[\[ ! -d "\$DASHBOARD_DIR/\.git" \]\]' "$INSTALLER" | cut -d: -f1)"
GATE_COUNT="$(printf '%s' "$GATE_HITS" | grep -c . )"
if [ "$GATE_COUNT" -ne 1 ]; then
  bad "T2: expected exactly 1 non-comment '-d \$DASHBOARD_DIR/.git' gate (the clone gate), found $GATE_COUNT"
  T2BAD=1
else
  if ! sed -n "${GATE_HITS},$((GATE_HITS+3))p" "$INSTALLER" | grep -q 'git clone'; then
    bad "T2: the surviving '-d .git' gate at line $GATE_HITS does not guard a git clone — a silent skip may have returned"
    T2BAD=1
  fi
fi
[ "$T2BAD" -eq 0 ] && ok "T2: 'skipping refresh' gone; the single surviving -d gate (line $GATE_HITS) is the full-install clone gate"

# ============================================================================
# T3–T6 — precedence and the anti-clobber contract
# ============================================================================
hdr "T3 — --app-dir flag beats \$CC_APP_DIR and the default"
FAKE_HOME="$(mktemp -d)"
OUT="$(run_resolve "$FAKE_HOME" true "/pin/from/flag" "/pin/from/env" "")"
DIR="${OUT%%|*}"; REST="${OUT#*|}"; SRC="${REST%%|*}"
if [ "$DIR" = "/pin/from/flag" ] && [ "$SRC" = "--app-dir flag" ]; then
  ok "T3: --app-dir wins (dir=$DIR source=$SRC)"
else
  bad "T3: expected /pin/from/flag via '--app-dir flag', got dir=$DIR source=$SRC"
fi

hdr "T4 — \$CC_APP_DIR honored when no flag is given, and NOT clobbered"
OUT="$(run_resolve "$FAKE_HOME" false "" "/pin/from/env" "")"
DIR="${OUT%%|*}"; REST="${OUT#*|}"; SRC="${REST%%|*}"; REST="${REST#*|}"; PINNED="${REST%%|*}"
if [ "$DIR" = "/pin/from/env" ] && [ "$SRC" = "CC_APP_DIR env" ] && [ "$PINNED" = "true" ]; then
  ok "T4: \$CC_APP_DIR survives resolution (dir=$DIR source=$SRC pinned=$PINNED)"
else
  bad "T4: expected /pin/from/env via 'CC_APP_DIR env' pinned=true, got dir=$DIR source=$SRC pinned=$PINNED"
fi

hdr "T5 — neither set: the historical default is preserved"
OUT="$(run_resolve "$FAKE_HOME" false "" "" "")"
DIR="${OUT%%|*}"; REST="${OUT#*|}"; SRC="${REST%%|*}"; REST="${REST#*|}"; PINNED="${REST%%|*}"
if [ "$DIR" = "$FAKE_HOME/projects/command-center" ] && [ "$SRC" = "default" ] && [ "$PINNED" = "false" ]; then
  ok "T5: default preserved (dir=\$HOME/projects/command-center source=default pinned=false)"
else
  bad "T5: expected \$HOME/projects/command-center via 'default' pinned=false, got dir=$DIR source=$SRC pinned=$PINNED"
fi

hdr "T6 — \$CC_PORT honored; unset falls back to 4000"
OUT="$(run_resolve "$FAKE_HOME" false "" "" "4310")"; PORT="${OUT##*|}"
OUT2="$(run_resolve "$FAKE_HOME" false "" "" "")";    PORT2="${OUT2##*|}"
if [ "$PORT" = "4310" ] && [ "$PORT2" = "4000" ]; then
  ok "T6: CC_PORT=4310 honored; unset -> 4000 (no regression)"
else
  bad "T6: expected 4310 then 4000, got $PORT then $PORT2"
fi
rm -rf "$FAKE_HOME"

# ============================================================================
# T7–T11 — the validator (mirrors update.sh's _cc_validate_checkout)
# ============================================================================
ROOT="$(mktemp -d)"
read -r OROOT OBARE <<EOF
$(make_cc_origin)
EOF

hdr "T7 — validator rejects a non-git decoy (the operator-box shape)"
make_decoy "$ROOT/decoy"
OUT="$(run_validate "$ROOT/decoy")"; RC="${OUT%%|*}"; REASON="$(printf '%s' "$OUT" | cut -d'|' -f2)"
if [ "$RC" = "1" ] && printf '%s' "$REASON" | grep -q 'not a git checkout'; then
  ok "T7: rejected — $REASON"
else
  bad "T7: expected rejection 'not a git checkout', got rc=$RC reason='$REASON'"
fi

hdr "T8 — validator rejects a git checkout whose origin is a DIFFERENT repo"
OTHER="$ROOT/other-repo.git"; git init --quiet --bare "$OTHER"
git clone --quiet "$OBARE" "$ROOT/wrong-origin" >/dev/null 2>&1
git -C "$ROOT/wrong-origin" remote set-url origin "$OTHER"
OUT="$(run_validate "$ROOT/wrong-origin")"; RC="${OUT%%|*}"; REASON="$(printf '%s' "$OUT" | cut -d'|' -f2)"
if [ "$RC" = "1" ] && printf '%s' "$REASON" | grep -q 'different repo'; then
  ok "T8: rejected — $REASON"
else
  bad "T8: expected rejection 'different repo', got rc=$RC reason='$REASON'"
fi

hdr "T9 — validator rejects a SUBDIRECTORY of a valid checkout"
make_cc_checkout "$OBARE" "$ROOT/valid"
OUT="$(run_validate "$ROOT/valid/src")"; RC="${OUT%%|*}"; REASON="$(printf '%s' "$OUT" | cut -d'|' -f2)"
if [ "$RC" = "1" ] && printf '%s' "$REASON" | grep -q 'not a checkout root'; then
  ok "T9: rejected — $REASON"
else
  bad "T9: expected rejection 'not a checkout root', got rc=$RC reason='$REASON'"
fi

hdr "T10 — validator ACCEPTS a valid checkout"
OUT="$(run_validate "$ROOT/valid")"; RC="${OUT%%|*}"; VPATH="${OUT##*|}"
VALID_PHYS="$(cd "$ROOT/valid" && pwd -P)"
if [ "$RC" = "0" ] && [ "$VPATH" = "$VALID_PHYS" ]; then
  ok "T10: accepted and canonicalized to the physical path"
else
  bad "T10: expected acceptance with phys=$VALID_PHYS, got rc=$RC path=$VPATH"
fi

hdr "T11 — validator ACCEPTS a linked worktree (.git is a FILE, not a dir)"
git -C "$ROOT/valid" worktree add --quiet --detach "$ROOT/linked" >/dev/null 2>&1
if [ ! -f "$ROOT/linked/.git" ]; then
  bad "T11: fixture is not a linked worktree (.git is not a file) — harness broken"
else
  OUT="$(run_validate "$ROOT/linked")"; RC="${OUT%%|*}"; REASON="$(printf '%s' "$OUT" | cut -d'|' -f2)"
  LINKED_PHYS="$(cd "$ROOT/linked" && pwd -P)"; VPATH="${OUT##*|}"
  if [ "$RC" = "0" ] && [ "$VPATH" = "$LINKED_PHYS" ]; then
    ok "T11: linked worktree accepted — the old '-d .git' test would have rejected it"
  else
    bad "T11: expected acceptance of the linked worktree, got rc=$RC reason='$REASON'"
  fi
fi

# ============================================================================
# T12–T13 — the fail-closed assertion
# ============================================================================
hdr "T12 — assert FAILS CLOSED on the decoy, with a diagnosable message"
ASSERT_OUT="$(
  ( set -u
    DASHBOARD_DIR="$ROOT/decoy"; DASHBOARD_DIR_SOURCE="default"; DASHBOARD_DIR_PINNED=false
    # shellcheck disable=SC1090
    source "$FRAG"
    cc_assert_update_only_checkout
    echo "REACHED_NEXT_LINE"
  ) 2>&1
)"; ARC=$?
T12BAD=0
[ "$ARC" -eq 0 ] && { bad "T12: assert exited 0 on a decoy — this is the false green"; T12BAD=1; }
printf '%s' "$ASSERT_OUT" | grep -q 'REACHED_NEXT_LINE' && { bad "T12: execution continued past the assert"; T12BAD=1; }
printf '%s' "$ASSERT_OUT" | grep -q "$ROOT/decoy"        || { bad "T12: message does not name the resolved path"; T12BAD=1; }
printf '%s' "$ASSERT_OUT" | grep -q 'not a git checkout' || { bad "T12: message does not give the rejection reason"; T12BAD=1; }
printf '%s' "$ASSERT_OUT" | grep -q -- '--app-dir'       || { bad "T12: message does not state the --app-dir remedy"; T12BAD=1; }
[ "$T12BAD" -eq 0 ] && ok "T12: exit=$ARC, execution stopped, message names path + reason + --app-dir remedy"

hdr "T13 — assert PASSES on a valid checkout and canonicalizes DASHBOARD_DIR"
ASSERT_OUT="$(
  ( set -u
    DASHBOARD_DIR="$ROOT/valid"; DASHBOARD_DIR_SOURCE="--app-dir flag"; DASHBOARD_DIR_PINNED=true
    # shellcheck disable=SC1090
    source "$FRAG"
    cc_assert_update_only_checkout
    printf 'RESOLVED=%s\n' "$DASHBOARD_DIR"
  ) 2>/dev/null
)"; ARC=$?
if [ "$ARC" -eq 0 ] && [ "$ASSERT_OUT" = "RESOLVED=$VALID_PHYS" ]; then
  ok "T13: proceeds normally (exit 0) with DASHBOARD_DIR canonicalized to $VALID_PHYS"
else
  bad "T13: expected exit 0 and RESOLVED=$VALID_PHYS, got exit=$ARC out='$ASSERT_OUT'"
fi

# ============================================================================
# T14–T15 — END-TO-END against the REAL installer
# ============================================================================
# A sandboxed HOME with an .openclaw root is all --update-only needs to reach
# phase 6: preflight is WARN-only in this mode, phase 1 and lock-assert are
# both skipped. Nothing outside the sandbox is read or written; no box is
# touched; no network is used.
run_installer() {  # run_installer <home> [extra args...]
  local home="$1"; shift
  mkdir -p "$home/.openclaw/workspace"
  ( HOME="$home" bash "$INSTALLER" --update-only "$@" 2>&1 )
}

hdr "T14 — end-to-end: decoy at the default path -> nonzero AND phase 6 is terminal"
E2E_HOME="$(mktemp -d)"
make_decoy "$E2E_HOME/projects/command-center"
OUT="$(run_installer "$E2E_HOME")"; ERC=$?
T14BAD=0
[ "$ERC" -eq 0 ] && { bad "T14: real installer exited 0 with nothing deployed — the false green is back"; T14BAD=1; }
# The defining symptom of the defect was not the final exit code (downstream
# gates dominate that on a bare sandbox) but that phase 6 SKIPPED and execution
# flowed onward. On the defective revision this run reached phase 7; it must not.
printf '%s' "$OUT" | grep -q 'phase=7' && { bad "T14: execution continued past phase 6 (reached phase 7) — the skip is still not fatal"; T14BAD=1; }
printf '%s' "$OUT" | grep -q 'refusing to run against an unvalidated directory' \
  || { bad "T14: the fail-closed message was not emitted"; T14BAD=1; }
[ "$T14BAD" -eq 0 ] && ok "T14: exit=$ERC, phase 6 terminal (never reached phase 7), fail-closed message emitted"
rm -rf "$E2E_HOME"

hdr "T15 — end-to-end: --app-dir at a valid checkout -> the gate is PASSED"
E2E_HOME="$(mktemp -d)"
make_decoy "$E2E_HOME/projects/command-center"   # default path is still a decoy
make_cc_checkout "$OBARE" "$E2E_HOME/real-cc"
# The gate canonicalizes to the PHYSICAL path (on macOS /var is a symlink to
# /private/var), so compare against that, not the raw mktemp path.
E2E_CC_PHYS="$(cd "$E2E_HOME/real-cc" && pwd -P)"
OUT="$(run_installer "$E2E_HOME" --app-dir "$E2E_HOME/real-cc")"
T15BAD=0
printf '%s' "$OUT" | grep -q 'refusing to run against an unvalidated directory' \
  && { bad "T15: --app-dir was not honored — the gate rejected a valid checkout"; T15BAD=1; }
printf '%s' "$OUT" | grep -q "resolved Command Center checkout at $E2E_CC_PHYS" \
  || { bad "T15: the gate did not report resolving the --app-dir path"; T15BAD=1; }
printf '%s' "$OUT" | grep -q 'source: --app-dir flag' \
  || { bad "T15: the resolution source was not reported as the --app-dir flag"; T15BAD=1; }
[ "$T15BAD" -eq 0 ] && ok "T15: --app-dir honored end-to-end; phase 6 proceeded against the pinned checkout"
rm -rf "$E2E_HOME"

rm -rf "$ROOT" "$OROOT"
rm -f "$FRAG"

# ── summary ──────────────────────────────────────────────────────────────────
printf '\n\033[1m%d passed, %d failed\033[0m\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
