#!/usr/bin/env bash
# ============================================================================
# Regression suite for two live-canary updater traps in update-skills.sh
# (found 2026-07-19 by a canary run against a real box).
#
#   TRAP 1 — the documented OpenClaw 2026.7.1 pre-clear
#              mv ~/.clawdbot ~/.clawdbot.bak-pre-2026.7.1
#            is UNSAFE on any box where ~/.clawdbot is still a LIVE workspace
#            root (e.g. ~/.openclaw/workspace is a symlink INTO it, or
#            openclaw.json declares agent workspaces under it). Blindly moving
#            it dangles those symlinks and orphans the declared workspaces.
#            The fix makes the pre-clear opt-in AND two-pass: it detects across
#            every candidate root first, mutates nothing, and refuses with
#            exit 3 if ANY live signal fires anywhere.
#
#   TRAP 3 — the Command Center bootstrap branch fired whenever
#            "$HOME/projects/command-center/.git" was absent and a build-state
#            contactEmail happened to be set. On a box whose CC lives at a
#            non-canonical path that clones a SECOND Command Center and, via
#            run-full-install.sh:1215-1218, pm2-deletes the running board and
#            restarts from the fresh clone — outage plus a divergent
#            mission-control.db. The fix requires absence proven three
#            independent ways (no valid checkout, no pm2 app, port unbound)
#            and refuses a poisoned canonical path outright.
#
# METHOD. Like scripts/test-cc-update-only-credential-and-git-sync.sh, this
# suite does NOT reimplement any logic: it extracts the real blocks VERBATIM
# from update-skills.sh between the TRAP1-PRECLEAR / TRAP3-CC-* markers and
# sources them. If those markers drift or vanish the suite fails loudly (exit
# 2) rather than silently testing nothing.
#
# SAFETY. Every case runs against mktemp -d roots with HOME repointed, and
# pm2/lsof stubbed. Nothing real is read or written: no SSH, no network, no
# clone, no touching the operator's ~/.openclaw, ~/.clawdbot or any box.
# ============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
TARGET="$REPO/update-skills.sh"

PASS=0; FAIL=0
ok()  { printf '  \033[32m✓ PASS\033[0m — %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  \033[31m✗ FAIL\033[0m — %s\n' "$1"; FAIL=$((FAIL+1)); }
hdr() { printf '\n\033[1m%s\033[0m\n' "$1"; }

[ -f "$TARGET" ] || { echo "FATAL: $TARGET not found"; exit 2; }

# --- verbatim extraction between markers ------------------------------------
extract_block() {
  # $1 = marker basename, e.g. TRAP1-PRECLEAR
  awk -v b=">>> $1-BEGIN" -v e="<<< $1-END" '
    index($0, b) { p=1; next }
    index($0, e) { p=0 }
    p { print }
  ' "$TARGET"
}

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

for m in TRAP1-PRECLEAR TRAP3-CC-GUARD-HELPERS TRAP3-CC-BOOTSTRAP-BRANCH; do
  extract_block "$m" > "$WORK/$m.inc"
  if [ ! -s "$WORK/$m.inc" ]; then
    echo "FATAL: marker block '$m' not found in update-skills.sh (marker drift?)"
    exit 2
  fi
done

# The trap-3 blocks live INSIDE main(), so they are indented and reference
# main()-local state. Wrap them in a function to source them standalone.
{
  echo 'cc_guard_block() {'
  cat "$WORK/TRAP3-CC-GUARD-HELPERS.inc"
  cat "$WORK/TRAP3-CC-BOOTSTRAP-BRANCH.inc"
  echo '}'
} > "$WORK/cc-guard.sh"

bash -n "$WORK/TRAP1-PRECLEAR.inc" || { echo "FATAL: extracted TRAP1 block does not parse"; exit 2; }
bash -n "$WORK/cc-guard.sh"        || { echo "FATAL: extracted TRAP3 block does not parse"; exit 2; }

# ============================================================================
# TRAP 1 — .clawdbot pre-clear
# ============================================================================
t1_run() {
  # $1 = fixture builder fn, $2 = mode. Caller must set T1_TMP first: command
  # substitution runs this in a subshell, so an assignment here would be lost.
  local builder="$1" mode="$2" TMP="$T1_TMP"
  "$builder" "$TMP"
  (
    export HOME="$TMP"
    export OC_CONFIG="$TMP/.openclaw"
    # shellcheck source=/dev/null
    source "$WORK/TRAP1-PRECLEAR.inc"
    preclear_2026_7_1 "$mode" 2>&1
  )
}

# LIVE box: ~/.openclaw/workspace is a symlink into ~/.clawdbot/workspace.
fx_live() {
  local r="$1"
  mkdir -p "$r/.openclaw" "$r/.clawdbot/workspace/agent-a"
  ln -s "$r/.clawdbot/workspace" "$r/.openclaw/workspace"
  printf '{"agents":{}}\n' > "$r/.openclaw/openclaw.json"
  mkdir -p "$r/.openclaw/plugins"; printf '{}\n' > "$r/.openclaw/plugins/installs.json"
}
# REFERENCE-ONLY box: no symlink, cold mtimes, but openclaw.json still names it.
fx_refonly() {
  local r="$1"
  mkdir -p "$r/.openclaw" "$r/.clawdbot"
  printf '{"agents":{"a":{"workspace":"%s/.clawdbot/ws"}}}\n' "$r" > "$r/.openclaw/openclaw.json"
  touch -t 202001010000 "$r/.clawdbot" 2>/dev/null || true
}
# TRUE RELIC: nothing references it, nothing recent inside.
fx_relic() {
  local r="$1"
  mkdir -p "$r/.openclaw/plugins" "$r/.clawdbot"
  printf '{"agents":{}}\n' > "$r/.openclaw/openclaw.json"
  printf '{}\n' > "$r/.openclaw/plugins/installs.json"
  touch -t 202001010000 "$r/.clawdbot" 2>/dev/null || true
}
# CLEAN box: no relics at all.
fx_clean() {
  local r="$1"
  mkdir -p "$r/.openclaw"
  printf '{"agents":{}}\n' > "$r/.openclaw/openclaw.json"
}

hdr "TRAP 1 / CASE 1 — LIVE .clawdbot (symlinked workspace) must REFUSE"
T1_TMP="$(mktemp -d)"; out="$(t1_run fx_live check)"; rc=$?
[ "$rc" = "3" ] && ok "exit 3 (refused)" || bad "expected exit 3, got $rc"
echo "$out" | grep -q "PRE-CLEAR REFUSED" && ok "loud refusal printed" || bad "no refusal banner"
[ -d "$T1_TMP/.clawdbot" ] && ok ".clawdbot still present (nothing moved)" || bad ".clawdbot was moved"

hdr "TRAP 1 / CASE 2 — LIVE box in APPLY mode still must not move anything"
T1_TMP="$(mktemp -d)"; out="$(t1_run fx_live apply)"; rc=$?
[ "$rc" = "3" ] && ok "exit 3 (refused in apply mode)" || bad "expected exit 3, got $rc"
[ -d "$T1_TMP/.clawdbot" ] && ok ".clawdbot still present" || bad ".clawdbot was moved in apply mode"
# shellcheck disable=SC2144
if ls -d "$T1_TMP"/.clawdbot.bak-* >/dev/null 2>&1; then bad "a .bak was created on a refused run"; else ok "no .bak created"; fi
[ -f "$T1_TMP/.openclaw/plugins/installs.json" ] && ok "installs.json half untouched on refusal" || bad "installs.json moved despite refusal"

hdr "TRAP 1 / CASE 3 — reference-only (cold mtimes) must STILL refuse"
T1_TMP="$(mktemp -d)"; out="$(t1_run fx_refonly apply)"; rc=$?
[ "$rc" = "3" ] && ok "exit 3 (openclaw.json reference alone is sufficient)" || bad "expected exit 3, got $rc"
[ -d "$T1_TMP/.clawdbot" ] && ok ".clawdbot still present" || bad ".clawdbot was moved"
echo "$out" | grep -q "path reference(s) under .clawdbot" && ok "reference evidence cited" || bad "reference not cited"
echo "$out" | grep -q "\.clawdbot/ws" && bad "LEAK: matched value echoed" || ok "matched values withheld (count only)"

hdr "TRAP 1 / CASE 4 — true relic in APPLY mode is renamed, never deleted"
T1_TMP="$(mktemp -d)"; out="$(t1_run fx_relic apply)"; rc=$?
[ "$rc" = "0" ] && ok "exit 0" || bad "expected exit 0, got $rc"
[ -d "$T1_TMP/.clawdbot" ] && bad ".clawdbot not moved" || ok ".clawdbot moved"
# shellcheck disable=SC2144
if ls -d "$T1_TMP"/.clawdbot.bak-pre-2026.7.1-* >/dev/null 2>&1; then ok "renamed to .bak (not deleted)"; else bad "no .bak — relic may have been deleted"; fi

hdr "TRAP 1 / CASE 5 — check mode on a true relic mutates NOTHING"
T1_TMP="$(mktemp -d)"; out="$(t1_run fx_relic check)"; rc=$?
[ "$rc" = "0" ] && ok "exit 0" || bad "expected exit 0, got $rc"
[ -d "$T1_TMP/.clawdbot" ] && ok ".clawdbot untouched in check mode" || bad "check mode moved .clawdbot"

hdr "TRAP 1 / CASE 6 — clean box reports nothing to do"
T1_TMP="$(mktemp -d)"; out="$(t1_run fx_clean apply)"; rc=$?
[ "$rc" = "0" ] && ok "exit 0" || bad "expected exit 0, got $rc"
echo "$out" | grep -q "nothing to do" && ok "reported nothing to do" || bad "no 'nothing to do'"

# ============================================================================
# TRAP 3 — Command Center bootstrap guard
# ============================================================================
STUB="$WORK/stub"; mkdir -p "$STUB"
cat > "$STUB/pm2" <<'EOS'
#!/usr/bin/env bash
[ "$1" = "jlist" ] && { printf '%s' "${FAKE_PM2_JLIST:-[]}"; exit 0; }
exit 0
EOS
cat > "$STUB/lsof" <<'EOS'
#!/usr/bin/env bash
exit "${FAKE_PORT_BOUND_RC:-1}"
EOS
chmod +x "$STUB/pm2" "$STUB/lsof"

make_checkout() {
  local dir="$1" remote="$2"
  mkdir -p "$dir"
  git -C "$dir" init -q 2>/dev/null
  git -C "$dir" config user.name Fixture
  git -C "$dir" config user.email fixture@example.invalid
  git -C "$dir" remote add origin "$remote" 2>/dev/null
  printf '{"name":"mission-control"}\n' > "$dir/package.json"
  git -C "$dir" add package.json
  git -C "$dir" commit -qm fixture
  git -C "$dir" branch -M main
  git -C "$dir" update-ref refs/remotes/origin/main HEAD
  git -C "$dir" symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
}

t3_run() {
  # $1 = pre-build hook (shell string). Caller must set T3_BOX first (see
  # t1_run: command substitution subshells any assignment made in here).
  local hook="$1" BOX="$T3_BOX"
  mkdir -p "$BOX/skills/32-command-center-setup/scripts"
  # stub installer: records argv, exit code controlled by FAKE_INSTALLER_EXIT.
  # When FAKE_SKIP_INSTALLER=1 the installer is NOT created (exercises the
  # no-installer exit-2 path).
  if [ "${FAKE_SKIP_INSTALLER:-0}" != "1" ]; then
    cat > "$BOX/skills/32-command-center-setup/scripts/run-full-install.sh" <<'EOS'
#!/usr/bin/env bash
echo "INSTALLER_INVOKED args=$*" >> "${INSTALLER_LOG:-$HOME/invocations}"
exit "${FAKE_INSTALLER_EXIT:-0}"
EOS
    chmod +x "$BOX/skills/32-command-center-setup/scripts/run-full-install.sh"
  fi
  : > "$BOX/invocations"
  (
    export HOME="$BOX"
    export PATH="$STUB:$PATH"
    export SKILLS_DIR="$BOX/skills"
    export LOG_FILE="$BOX/log"
    export OC_WORKSPACE_DEFAULT="$BOX/.openclaw/workspace"
    export INSTALLER_LOG="$BOX/invocations"
    eval "$hook"
    # shellcheck source=/dev/null
    source "$WORK/cc-guard.sh"
    cc_guard_block 2>&1
  )
}

hdr "TRAP 3 / CASE 1 — CC at NON-CANONICAL path: must NOT clone a second one"
export _CC_SLUG=acme _CC_COMPANY=Acme _CC_EMAIL=a@b.co FAKE_PM2_JLIST='[]' FAKE_PORT_BOUND_RC=1
T3_BOX="$(mktemp -d)"; out="$(t3_run 'make_checkout "$HOME/blackceo-command-center" https://github.com/trevorotts1/blackceo-command-center.git')"
grep -q 'INSTALLER_INVOKED args=--update-only --app-dir .*blackceo-command-center acme Acme' "$T3_BOX/invocations" \
  && ok "existing non-canonical checkout refreshed in place via --app-dir" \
  || bad "non-canonical checkout was not passed to the update-only installer"
grep -q 'INSTALLER_INVOKED args=acme Acme' "$T3_BOX/invocations" && bad "FULL install invoked — a SECOND CC would be cloned" || ok "no FULL install invoked (no second clone)"
echo "$out" | grep -q "non-canonical path" && ok "non-canonical checkout detected and reported" || bad "non-canonical path not reported"

hdr "TRAP 3 / CASE 2 — no checkout, but pm2 already runs the board"
export FAKE_PM2_JLIST='[{"name":"mission-control"}]' FAKE_PORT_BOUND_RC=1
T3_BOX="$(mktemp -d)"; out="$(t3_run 'true')"
grep -q 'INSTALLER_INVOKED' "$T3_BOX/invocations" && bad "installer invoked despite a running pm2 app" || ok "installer not invoked"
echo "$out" | grep -q "SKIPPED" && ok "skip reason stated (pm2)" || bad "no skip message"

hdr "TRAP 3 / CASE 3 — no checkout, no pm2, but the port is already bound"
export FAKE_PM2_JLIST='[]' FAKE_PORT_BOUND_RC=0
T3_BOX="$(mktemp -d)"; out="$(t3_run 'true')"
grep -q 'INSTALLER_INVOKED' "$T3_BOX/invocations" && bad "installer invoked despite a bound port" || ok "installer not invoked"
echo "$out" | grep -q "SKIPPED" && ok "skip reason stated (port)" || bad "no skip message"

hdr "TRAP 3 / CASE 4 — CONTROL: genuinely CC-less box must STILL bootstrap"
export FAKE_PM2_JLIST='[]' FAKE_PORT_BOUND_RC=1
T3_BOX="$(mktemp -d)"; out="$(t3_run 'true')"
echo "$out" | grep -q "not present on this box" && ok "bootstrap announced" || bad "bootstrap did not announce"
grep -q 'INSTALLER_INVOKED args=acme Acme a@b.co' "$T3_BOX/invocations" && ok "FULL install invoked with all 3 args (no over-blocking)" || bad "full install not invoked"

hdr "TRAP 3 / CASE 5 — poisoned canonical path (foreign git repo) must REFUSE"
# run-full-install.sh:1132 only clones when .git is ABSENT; with a foreign repo
# present it skips the clone, git-syncs that repo and deploys it AS the Command
# Center. Refusing loudly is the only safe outcome.
export FAKE_PM2_JLIST='[]' FAKE_PORT_BOUND_RC=1
T3_BOX="$(mktemp -d)"; out="$(t3_run 'make_checkout "$HOME/projects/command-center" https://github.com/someone/unrelated.git')"
echo "$out" | grep -q "REFUSED" && ok "loud refusal printed" || bad "no refusal — foreign repo would be adopted as the CC"
grep -q 'INSTALLER_INVOKED' "$T3_BOX/invocations" && bad "installer invoked against a foreign repo" || ok "installer not invoked"

hdr "TRAP 3 / CASE 6 — empty contactEmail is NOT what gates safety"
# The original bug: bootstrap fired on (!-d canonical/.git && -n contactEmail).
# An empty email must defer on INPUT grounds, and a populated one must never by
# itself authorise clobbering an existing board (covered by CASE 1).
export _CC_EMAIL="" FAKE_PM2_JLIST='[]' FAKE_PORT_BOUND_RC=1
T3_BOX="$(mktemp -d)"; out="$(t3_run 'true')"
echo "$out" | grep -q "missing company/email" && ok "deferred on missing install args, reason stated" || bad "no clear deferral message"
grep -q 'INSTALLER_INVOKED' "$T3_BOX/invocations" && bad "installer invoked without required args" || ok "installer not invoked"

hdr "TRAP 3 / CASE 7 — CC exists, refresh-installer FAILS (U005 exit-2 advisory)"
export FAKE_PM2_JLIST='[]' FAKE_PORT_BOUND_RC=1 FAKE_INSTALLER_EXIT=1
T3_BOX="$(mktemp -d)"; out="$(t3_run 'make_checkout "$HOME/projects/command-center" https://github.com/trevorotts1/blackceo-command-center.git')"; rc=$?
[ "$rc" = "2" ] && ok "exit 2 (CC refresh failed, content current)" || bad "expected exit 2, got $rc"
echo "$out" | grep -q "ADVISORY: skills CONTENT is current" && ok "advisory line emitted (parseable pattern)" || bad "advisory line missing"
echo "$out" | grep -q "refresh FAILED" && ok "refresh-failure reason stated" || bad "no refresh-failure reason"

hdr "TRAP 3 / CASE 8 — no CC, bootstrap-installer FAILS (U005 exit-2 advisory)"
export _CC_SLUG=acme _CC_COMPANY=Acme _CC_EMAIL=a@b.co FAKE_PM2_JLIST='[]' FAKE_PORT_BOUND_RC=1 FAKE_INSTALLER_EXIT=1
T3_BOX="$(mktemp -d)"; out="$(t3_run 'true')"; rc=$?
[ "$rc" = "2" ] && ok "exit 2 (bootstrap failed, content current)" || bad "expected exit 2, got $rc"
echo "$out" | grep -q "ADVISORY: skills CONTENT is current" && ok "advisory line emitted (parseable pattern)" || bad "advisory line missing"
echo "$out" | grep -q "bootstrap FAILED" && ok "bootstrap-failure reason stated" || bad "no bootstrap-failure reason"

hdr "TRAP 3 / CASE 9 — CC exists but installer script MISSING (U005 exit-2 advisory)"
export FAKE_PM2_JLIST='[]' FAKE_PORT_BOUND_RC=1 FAKE_SKIP_INSTALLER=1
T3_BOX="$(mktemp -d)"; out="$(t3_run 'make_checkout "$HOME/projects/command-center" https://github.com/trevorotts1/blackceo-command-center.git')"; rc=$?
[ "$rc" = "2" ] && ok "exit 2 (installer missing, content current)" || bad "expected exit 2, got $rc"
echo "$out" | grep -q "ADVISORY: skills CONTENT is current" && ok "advisory line emitted (parseable pattern)" || bad "advisory line missing"
echo "$out" | grep -q "installer missing" && ok "installer-missing reason stated" || bad "no installer-missing reason"

printf '\n=========================================\n'
printf 'TRAPS 1+3 REGRESSION SUITE: PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
printf '=========================================\n'
[ "$FAIL" -eq 0 ]
