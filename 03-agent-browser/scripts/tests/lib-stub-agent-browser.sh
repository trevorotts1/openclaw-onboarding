#!/usr/bin/env bash
# lib-stub-agent-browser.sh — shared stub-CLI builder for the P3-06 QC tests
# (+ GK-28/U90's backstop conformance battery, which reuses this same stub).
#
# Writes a fake `agent-browser` executable into a scratch bin dir that mimics
# just enough of the real CLI's surface for qc-agent-browser.sh's Step-4
# section (and lib-backstop-conformance.sh's battery) to exercise their logic
# without a real Chrome download in CI:
#   --help                     prints something matching the existing check
#   [--headed <bool>] open <url>
#                              spawns a background stand-in process whose
#                              argv0 + command line look like a scoped
#                              Chromium (matches qc-agent-browser.sh's
#                              _scoped_chrome_pids grep, same shape as
#                              scripts/agent-browser-reaper.sh's own tripwire)
#   [--headed <bool>] snapshot -i
#                              prints a fake @e1-style ref line
#   [--headed <bool>] close    LEAK_MODE=1 -> does NOT kill the stand-in
#                              (simulates a leaked session);
#                              LEAK_MODE=0 (default) -> kills it (clean close)
#
# GK-28/U90 NOTE: `--headed <bool>` is stripped as an OPTIONAL leading global
# flag before verb dispatch, regardless of which verb follows. Two real,
# valid callers use two different conventions here — INSTALL.md's own Step-4
# example prefixes ONLY `open` with `--headed false` (`open` then bare
# `snapshot`/`close`), while 06-ghl-install-pages/tools/browser_manager.sh's
# AB() prefixes EVERY verb with `--headed false` (open/snapshot/fill/close
# alike). Before this fix the stub only recognized the flag ahead of `open`
# and silently no-op'd (fell to a bare `exit 0`) for `--headed false
# snapshot`/`--headed false close`/`--headed false fill` — invisible to the
# Step-4-only callers, but it made every OTHER verb in
# lib-backstop-conformance.sh's battery (which mirrors browser_manager.sh's
# always-prefixed convention) silently return empty output. Stripping the
# flag once, up front, makes both calling conventions dispatch identically.
#
# USAGE
#   source lib-stub-agent-browser.sh
#   build_stub_agent_browser <bin-dir> <pidfile-path> [leak_mode:0|1]
build_stub_agent_browser() {
  local bin_dir="$1" pidfile="$2" leak_mode="${3:-0}"
  mkdir -p "$bin_dir"
  cat > "$bin_dir/agent-browser" <<STUBEOF
#!/usr/bin/env bash
PIDFILE="$pidfile"
LEAK_MODE="$leak_mode"

# Strip an optional leading "--headed <bool>" global flag so verb dispatch
# below is uniform regardless of which real calling convention was used.
if [[ "\$1" == "--headed" ]]; then
  shift 2
fi

case "\$1" in
  --help) echo "agent-browser usage help"; exit 0 ;;
  open)
    ( exec -a "chrome --user-data-dir=/tmp/agent-browser-chrome-\$\$-stub" sleep 300 ) </dev/null >/dev/null 2>&1 &
    disown \$! 2>/dev/null || true
    echo "\$!" > "\$PIDFILE"
    exit 0 ;;
  snapshot) echo '- heading "Example Domain" [level=1, ref=e1]'; exit 0 ;;
  close)
    if [[ "\$LEAK_MODE" != "1" ]]; then
      [[ -s "\$PIDFILE" ]] && kill -TERM "\$(cat "\$PIDFILE")" 2>/dev/null
    fi
    # LEAK_MODE=1: intentionally does NOT kill -- simulates a leaked session.
    exit 0 ;;
  *) exit 0 ;;
esac
STUBEOF
  chmod +x "$bin_dir/agent-browser"
}

# kill_stub_pidfile <pidfile-path> -- best-effort cleanup so a test failure
# never leaves a background stand-in process running past the test.
kill_stub_pidfile() {
  local pidfile="$1"
  [[ -s "$pidfile" ]] && kill -9 "$(cat "$pidfile")" 2>/dev/null
  rm -f "$pidfile"
}

# kill_all_agent_browser_chrome_stubs -- GK-28/U90: best-effort sweep of EVERY
# scoped Chromium test stand-in this stub type could have spawned, by
# user-data-dir pattern, regardless of which specific pidfile tracked it.
#
# WHY THIS EXISTS: since GK-28/U90 wired the backstop conformance battery
# into every qc-agent-browser.sh run alongside the pre-existing Step-4 smoke
# test, a SINGLE qc run now does TWO independent open/close cycles against
# the SAME stub binary -- which tracks its most recent stand-in in ONE
# shared pidfile. A test that deliberately leaks a process from the FIRST
# cycle (a leak-mode fixture, to prove the assert-not-warn gate) has that
# pidfile entry silently overwritten by the SECOND cycle's own `open`,
# orphaning the leaked process past any single kill_stub_pidfile call. A
# scoped pattern sweep is the only reliable cleanup once two cycles share one
# stub. Never matches a real Chrome/Chromium process (the pattern requires
# the exact "agent-browser-chrome-<pid>-<tag>" user-data-dir this stub always
# writes).
kill_all_agent_browser_chrome_stubs() {
  local pids
  pids="$(ps -axww -o pid=,command= 2>/dev/null \
    | grep -E 'user-data-dir=/tmp/agent-browser-chrome-[0-9]+-[a-z-]+' \
    | grep -vi grep \
    | awk '{print $1}')"
  [ -n "$pids" ] && kill -9 $pids 2>/dev/null
  return 0
}
