#!/usr/bin/env bash
# lib-stub-agent-browser.sh — shared stub-CLI builder for the P3-06 QC tests.
#
# Writes a fake `agent-browser` executable into a scratch bin dir that mimics
# just enough of the real CLI's surface for qc-agent-browser.sh's Step-4
# section to exercise its logic without a real Chrome download in CI:
#   --help                    prints something matching the existing check
#   --headed false open <url> spawns a background stand-in process whose
#                              argv0 + command line look like a scoped
#                              Chromium (matches qc-agent-browser.sh's
#                              _scoped_chrome_pids grep, same shape as
#                              scripts/agent-browser-reaper.sh's own tripwire)
#   snapshot -i                prints a fake @e1-style ref line
#   close                      LEAK_MODE=1 -> does NOT kill the stand-in
#                              (simulates a leaked session);
#                              LEAK_MODE=0 (default) -> kills it (clean close)
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
case "\$1" in
  --help) echo "agent-browser usage help"; exit 0 ;;
  --headed)
    shift 2
    if [[ "\${1:-}" == "open" ]]; then
      ( exec -a "chrome --user-data-dir=/tmp/agent-browser-chrome-\$\$-stub" sleep 300 ) &
      echo "\$!" > "\$PIDFILE"
      exit 0
    fi
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
