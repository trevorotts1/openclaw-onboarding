#!/usr/bin/env bash
# tests/unit/hardening-bounded-brew-and-whisper-probe.test.sh
# -----------------------------------------------------------------------------
# CI guard for three defects in the Mac install-hardening step, all proven live
# on client Macs on 2026-09-17.
#
# DEFECT A -- PERMANENT FALSE NEGATIVE IN THE WHISPER PROBE.
#   scripts/install-hardening.sh probed `command -v whisper-cpp || command -v
#   whisper`. The Homebrew FORMULA is named whisper-cpp (keg whisper.cpp), but
#   the BINARIES it installs are whisper-cli, whisper-server, whisper-bench,
#   whisper-stream, whisper-command, whisper-quantize, whisper-talk-llama,
#   whisper-lsp, whisper-vad-speech-segments. Verified against an installed keg
#   (whisper.cpp 1.9.2, `brew list whisper-cpp`): there is NO binary named
#   whisper-cpp and NO binary named whisper. A bare `whisper` on PATH comes from
#   the SEPARATE openai-whisper formula, which most client boxes do not have.
#   So on a box that ALREADY had whisper-cpp installed the probe always failed,
#   `need` gained whisper-cpp every pass, and `brew install whisper-cpp`
#   re-fired on every roll, forever.
#
# DEFECT B -- UNBOUNDED, INTERACTIVE BREW.
#   `brew install "$pkg" >/dev/null 2>&1` ran with inherited stdin and no time
#   limit. A dependency postinstall wedged in a pseudo-terminal read loop and
#   never returned: three generations of orphaned Ruby processes, one pegging a
#   core for two days. install-hardening.sh never returned, so the updater's
#   EXIT trap never fired and the update lock was held for days.
#
# DEFECT C -- A BUFFERED LOG THAT HIDES THE HANG.
#   update-skills.sh ran `bash "$_HARDENING" 2>&1 | tail -5 || true`. `tail`
#   emits nothing until the producer exits, so a hang produced a roll log that
#   simply STOPPED with no hardening lines at all. Nothing distinguished a hang
#   from a quiet success.
#
# WHAT THIS TEST PROVES.
#   A1  the whisper probe checks whisper-cli (current binary name) FIRST.
#   A2  LIVE: with only `whisper-cli` on PATH the backfill does NOT queue
#       whisper-cpp. This is the false negative itself, measured.
#   A3  LIVE ANTI-VACUITY: with NO whisper binary on PATH it DOES queue it.
#   B1  brew runs non-interactive (NONINTERACTIVE, HOMEBREW_NO_AUTO_UPDATE,
#       HOMEBREW_NO_INSTALL_CLEANUP) with stdin from /dev/null.
#   B2  LIVE: a brew that hangs forever is killed and reported as a timeout,
#       within the configured bound.
#   B3  LIVE: the helper process the hung brew forked is killed too. An orphan
#       left pegging a core is the original incident.
#   B4  LIVE: the caller survives. A process-group kill that took out the
#       updater would be a worse bug than the hang.
#   B5  LIVE: success returns 0 and a real failure returns the real exit code,
#       so the bound never launders a failure into a success.
#   B6  LIVE: a brew that reads stdin gets EOF instead of blocking.
#   B7  the timeout is configurable and defaults to 600 s.
#   C1  update-skills.sh no longer pipes the hardening step into `tail`.
#   C2  it prints a [hardening] started marker BEFORE the work and a
#       [hardening] finished rc= marker after, and streams through `tee`.
#
# The LIVE legs (A2, A3, B2-B6) run the REAL functions out of the shipped
# script, sourced, against a stub `brew` on a sandbox PATH. Nothing installs
# anything, no network, no real Homebrew call, no ~/.openclaw access.
# Itself bash 3.2-safe: no associative arrays, no mapfile, no case modifiers.
#
# Run: bash tests/unit/hardening-bounded-brew-and-whisper-probe.test.sh
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).
# -----------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HARDENING="$REPO_ROOT/scripts/install-hardening.sh"
UPDATER="$REPO_ROOT/update-skills.sh"

PASS=0
FAIL=0
ok()  { printf '  ok   %s\n' "$1"; PASS=$((PASS + 1)); }
bad() { printf '  FAIL %s\n' "$1"; FAIL=$((FAIL + 1)); }
note() { printf '  --   %s\n' "$1"; }
hdr() { printf '\n== %s ==\n' "$1"; }

for f in "$HARDENING" "$UPDATER"; do
  if [ ! -f "$f" ]; then
    echo "FATAL: not found: $f" >&2
    exit 1
  fi
done

SANDBOX="$(mktemp -d)"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT
mkdir -p "$SANDBOX/bin"

# -----------------------------------------------------------------------------
hdr "A -- the whisper probe"
# -----------------------------------------------------------------------------
if grep -q 'command -v whisper-cli' "$HARDENING"; then
  ok "A1a: the probe checks whisper-cli"
else
  bad "A1a: the probe does NOT check whisper-cli (the binary the formula installs)"
fi
# whisper-cli must be checked BEFORE the stale names, so the current binary is
# what decides.
# Comments in this file QUOTE the old broken probe verbatim, so strip comments
# before judging order. A structural check that reads its own documentation is
# not a structural check.
A1_ORDER="$(sed 's/#.*$//' "$HARDENING" | grep -n 'command -v whisper' | head -1)"
case "$A1_ORDER" in
  *whisper-cli*) ok "A1b: whisper-cli is probed first" ;;
  *)             bad "A1b: whisper-cli is not the first whisper probe: $A1_ORDER" ;;
esac

# --- LIVE legs. Stub PATH, real functions. -----------------------------------
cat > "$SANDBOX/bin/brew" <<'BREWEOF'
#!/bin/bash
# stub brew for the hardening tests. Never touches Homebrew.
case "${2:-}" in
  hangpkg)
    # a dependency postinstall that forks a helper then blocks forever
    bash -c 'while :; do sleep 300; done' &
    echo "$!" > "$STUB_BREW_CHILD_PIDFILE"
    while :; do sleep 300; done
    ;;
  stdinpkg)
    # exits 3 if it ever receives a line; records the env it was given
    if read -r _line; then exit 3; fi
    printf 'NONINTERACTIVE=%s NO_AUTO_UPDATE=%s NO_CLEANUP=%s\n' \
      "${NONINTERACTIVE:-unset}" "${HOMEBREW_NO_AUTO_UPDATE:-unset}" \
      "${HOMEBREW_NO_INSTALL_CLEANUP:-unset}" > "$STUB_BREW_ENVFILE"
    exit 0
    ;;
  okpkg)   echo "$2" >> "$STUB_BREW_CALLS"; exit 0 ;;
  failpkg) exit 17 ;;
esac
echo "${2:-}" >> "$STUB_BREW_CALLS"
exit 0
BREWEOF
chmod +x "$SANDBOX/bin/brew"

# A whisper-cli that exists but is never executed (command -v only).
printf '#!/bin/bash\nexit 0\n' > "$SANDBOX/bin/whisper-cli"
printf '#!/bin/bash\nexit 0\n' > "$SANDBOX/bin/yt-dlp"
printf '#!/bin/bash\nexit 0\n' > "$SANDBOX/bin/ffmpeg"
chmod +x "$SANDBOX/bin/whisper-cli" "$SANDBOX/bin/yt-dlp" "$SANDBOX/bin/ffmpeg"

# Isolated PATH. Prepending the sandbox is NOT enough: this very box has a
# `whisper` from the separate openai-whisper formula in /opt/homebrew/bin, which
# would satisfy the probe and make the anti-vacuity leg silently vacuous. Drop
# Homebrew from PATH entirely and keep only the system directories the stubs
# and the script actually need.
ISO_PATH="$SANDBOX/bin:/usr/bin:/bin:/usr/sbin:/sbin"

export STUB_BREW_CHILD_PIDFILE="$SANDBOX/child.pid"
export STUB_BREW_ENVFILE="$SANDBOX/env.out"
export STUB_BREW_CALLS="$SANDBOX/calls.txt"
: > "$STUB_BREW_CALLS"

if [ "$(uname -s)" != "Darwin" ]; then
  note "A2/A3/B2-B6: harden_skill22_media_tools and the watchdog are Darwin-only;"
  note "this runner is $(uname -s), so the LIVE legs are UNDETERMINED and skipped."
  note "The static legs (A1, B1, B7, C1, C2) still gate the fix on every runner."
else
  # A2 -- with whisper-cli present, whisper-cpp must NOT be queued.
  (
    PATH="$ISO_PATH"
    export PATH
    # shellcheck disable=SC1090
    . "$HARDENING"
    harden_skill22_media_tools
  ) > "$SANDBOX/a2.out" 2>&1
  if grep -q 'whisper-cpp' "$SANDBOX/calls.txt" 2>/dev/null; then
    bad "A2: brew install whisper-cpp fired even though whisper-cli is installed"
  else
    ok "A2: whisper-cli present -> whisper-cpp is NOT reinstalled (false negative gone)"
  fi

  # A3 -- anti-vacuity: with NO whisper binary at all it MUST be queued.
  rm -f "$SANDBOX/bin/whisper-cli"
  : > "$STUB_BREW_CALLS"
  (
    PATH="$ISO_PATH"
    export PATH
    # shellcheck disable=SC1090
    . "$HARDENING"
    harden_skill22_media_tools
  ) > "$SANDBOX/a3.out" 2>&1
  if grep -q 'whisper-cpp' "$SANDBOX/calls.txt" 2>/dev/null; then
    ok "A3: no whisper binary -> whisper-cpp IS queued (the probe still detects)"
  else
    bad "A3: a genuinely missing whisper-cpp was NOT queued -- the probe is now blind"
  fi
fi

# -----------------------------------------------------------------------------
hdr "B -- bounded, non-interactive brew"
# -----------------------------------------------------------------------------
for tok in 'NONINTERACTIVE=1' 'HOMEBREW_NO_AUTO_UPDATE=1' 'HOMEBREW_NO_INSTALL_CLEANUP=1'; do
  if grep -q "$tok" "$HARDENING"; then
    ok "B1: $tok is set for brew"
  else
    bad "B1: $tok is MISSING -- brew can prompt or self-update under the bound"
  fi
done
if grep -q 'brew install "\$pkg" </dev/null' "$HARDENING"; then
  ok "B1: brew stdin is /dev/null"
else
  bad "B1: brew stdin is not redirected from /dev/null"
fi
if grep -q 'HARDENING_BREW_TIMEOUT_SECS:-600' "$HARDENING"; then
  ok "B7: the timeout is env-overridable and defaults to 600 s"
else
  bad "B7: no HARDENING_BREW_TIMEOUT_SECS default of 600"
fi

if [ "$(uname -s)" = "Darwin" ]; then
  B_OUT="$SANDBOX/b.out"
  (
    PATH="$ISO_PATH"
    export PATH
    # shellcheck disable=SC1090
    . "$HARDENING"
    HARDENING_BREW_TIMEOUT_SECS=3

    MYPID=$$
    T0=$(date +%s)
    _brew_install_bounded hangpkg
    echo "HANG_RC=$?"
    T1=$(date +%s)
    echo "HANG_ELAPSED=$((T1 - T0))"
    sleep 1
    CPID="$(cat "$STUB_BREW_CHILD_PIDFILE" 2>/dev/null || echo '')"
    if [ -n "$CPID" ] && kill -0 "$CPID" 2>/dev/null; then
      echo "CHILD=ALIVE"
      kill -9 "$CPID" 2>/dev/null || true
    else
      echo "CHILD=REAPED"
    fi
    if kill -0 "$MYPID" 2>/dev/null; then echo "CALLER=ALIVE"; else echo "CALLER=DEAD"; fi

    _brew_install_bounded okpkg;   echo "OK_RC=$?"
    _brew_install_bounded failpkg; echo "FAIL_RC=$?"
    _brew_install_bounded stdinpkg; echo "STDIN_RC=$?"
  ) > "$B_OUT" 2>&1

  bget() { grep -m1 "^$1=" "$B_OUT" 2>/dev/null | cut -d= -f2; }

  if [ "$(bget HANG_RC)" = "124" ]; then
    ok "B2a: a hung brew returns 124 (timeout), not a hang"
  else
    bad "B2a: hung brew returned '$(bget HANG_RC)', expected 124"
  fi
  _ELAPSED="$(bget HANG_ELAPSED)"
  case "$_ELAPSED" in
    ''|*[!0-9]*) bad "B2b: no elapsed measurement" ;;
    *) if [ "$_ELAPSED" -ge 3 ] && [ "$_ELAPSED" -le 20 ]; then
         ok "B2b: killed after ${_ELAPSED}s with a 3s bound (bounded, not unbounded)"
       else
         bad "B2b: elapsed ${_ELAPSED}s is outside the 3s bound plus grace"
       fi ;;
  esac
  if grep -q 'timed out after' "$B_OUT"; then
    ok "B2c: the timeout is logged, never silent"
  else
    bad "B2c: the timeout was not logged"
  fi
  if [ "$(bget CHILD)" = "REAPED" ]; then
    ok "B3: the helper the hung brew forked was killed too (no orphan)"
  else
    bad "B3: the forked helper SURVIVED -- this is the core-pegging orphan"
  fi
  if [ "$(bget CALLER)" = "ALIVE" ]; then
    ok "B4: the caller survived the kill (no process-group friendly fire)"
  else
    bad "B4: the caller was killed -- the watchdog took out its own updater"
  fi
  if [ "$(bget OK_RC)" = "0" ]; then
    ok "B5a: a successful brew returns 0"
  else
    bad "B5a: a successful brew returned '$(bget OK_RC)'"
  fi
  if [ "$(bget FAIL_RC)" = "17" ]; then
    ok "B5b: a real failure returns its real exit code (not laundered to 0)"
  else
    bad "B5b: a failing brew returned '$(bget FAIL_RC)', expected 17"
  fi
  if [ "$(bget STDIN_RC)" = "0" ]; then
    ok "B6a: a brew that reads stdin gets EOF and completes"
  else
    bad "B6a: a brew reading stdin returned '$(bget STDIN_RC)' (3 = it got input)"
  fi
  if grep -q 'NONINTERACTIVE=1 NO_AUTO_UPDATE=1 NO_CLEANUP=1' "$STUB_BREW_ENVFILE" 2>/dev/null; then
    ok "B6b: brew actually received all three non-interactive env vars"
  else
    bad "B6b: brew did not receive the non-interactive env: $(cat "$STUB_BREW_ENVFILE" 2>/dev/null)"
  fi
fi

# -----------------------------------------------------------------------------
hdr "C -- the hardening step streams instead of buffering"
# -----------------------------------------------------------------------------
# Strip comments first: the fix's own comment quotes the old broken call.
if sed 's/#.*$//' "$UPDATER" | grep -q '_HARDENING" 2>&1 | tail'; then
  bad "C1: update-skills.sh still pipes the hardening step into tail (buffered; a hang is invisible)"
else
  ok "C1: the hardening step is no longer piped into tail"
fi
if grep -q '\[hardening\] started' "$UPDATER"; then
  ok "C2a: a [hardening] started marker is printed before the work"
else
  bad "C2a: no [hardening] started marker -- a hang leaves no trace of entry"
fi
if grep -q '\[hardening\] finished rc=' "$UPDATER"; then
  ok "C2b: a [hardening] finished rc= marker closes the bracket"
else
  bad "C2b: no [hardening] finished rc= marker"
fi
if grep -q 'tee -a "\$_HARDENING_LOG"' "$UPDATER"; then
  ok "C2c: hardening output streams through tee (visible while it runs)"
else
  bad "C2c: hardening output does not stream through tee"
fi

# -----------------------------------------------------------------------------
printf '\n----------------------------------------\n'
printf 'hardening-bounded-brew-and-whisper-probe: %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
