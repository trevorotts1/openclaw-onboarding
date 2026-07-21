#!/usr/bin/env bash
# lib-backstop-conformance.sh — Skill 03 (agent-browser) — GK-28/U90 step (c):
# consumer conformance battery.
#
# WHY: Skill 44's Tier-4 fallback and Skill 6's browser_manager.sh assume
# agent-browser gives them ref-based click/fill, snapshot stability, and a
# guaranteed session close — but nothing tested those assumptions from the
# CONSUMER side (NOT-FOUND, GK-28 audit). This file is the single canonical
# implementation of that battery, shared by:
#   - qc-agent-browser.sh, which runs it (clean, real CLI when on PATH) as
#     part of every ordinary QC pass — "wired into Skill 3's QC".
#   - scripts/tests/backstop-conformance.test.sh, which runs it against a
#     capability-breakable STUB to fail-first-prove each leg actually bites.
#
# The five legs mirror the EXACT operations browser_manager.sh's own verb
# surface exposes to Skill 6 (`ensure|eval|open|snapshot|wait|find|fill`) and
# the argv shape 06-ghl-install-pages/tools/ghl_ab_executor.py independently
# verified live against agent-browser 0.27.0 (ref args are `@eN` positional —
# `fill @e2 "value"`, not `--ref/--value` flags; PINNED_AGENT_BROWSER = "0.27.0"
# there agrees with this skill's own agent-browser-cli.pin, GK-28/U90 step b):
#   1. open      — start a ref-based session against a known target.
#   2. snapshot  — returns interactive elements with stable refs (@e1, @e2…).
#   3. snapshot  — called AGAIN, same session, no DOM change: the SAME
#                  element must resolve to the SAME ref (snapshot stability —
#                  callers cache a ref across an open/act/verify sequence;
#                  an unstable ref would silently misdirect every fill/click
#                  issued after the first snapshot).
#   4. fill      — by ref, positional argv (`fill @eN "value"`), the exact
#                  form ghl_ab_executor.py's `AbExecutor.fill` ref-strategy
#                  path uses.
#   5. close     — guaranteed teardown, READ-BACK verified: zero NEW scoped
#                  Chromium processes (lib-scoped-chrome-scan.sh's proven
#                  reaper-style tripwire) survive close.
#
# CONTRACT
#   run_conformance_battery <session-name> [target-url]
#     Drives all five legs against whatever `agent-browser` is on PATH (real
#     CLI or a stub — this is exactly what makes it "runnable on any box").
#     [target-url] defaults to the bundled offline fixture
#     (scripts/tests/fixtures/conformance-fixture.html via file://) when this
#     lib is sourced from its normal location; override for testing.
#     Prints one line of evidence per leg. Returns 0 iff ALL FIVE legs pass,
#     1 if ANY leg fails (each failing leg's line is self-identifying, so a
#     caller can `grep` the specific leg that broke).
set -u

LIB_BACKSTOP_CONFORMANCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib-scoped-chrome-scan.sh
source "$LIB_BACKSTOP_CONFORMANCE_DIR/lib-scoped-chrome-scan.sh"

_conformance_default_target() {
  local fixture="$LIB_BACKSTOP_CONFORMANCE_DIR/tests/fixtures/conformance-fixture.html"
  if [ -f "$fixture" ]; then
    printf 'file://%s' "$fixture"
  else
    printf 'https://example.com/backstop-conformance-fixture'
  fi
}

# _conformance_pick_ref <snapshot-output>
# Prefers a ref on a line naming a textbox/input role (the fillable element);
# falls back to the first ref found at all. Prints the BARE ref token without
# the leading "@" (e.g. "e2") the way agent-browser's own `snapshot -i` output
# labels it (`ref=e2`) — callers must prepend "@" when passing it back to
# `fill`/`click`, matching ghl_ab_executor.py's `d["value"] = a` ref strategy
# (a already carries the "@" there because the CALLER's anchor string did).
_conformance_pick_ref() {
  local snap="$1" line ref
  line="$(printf '%s\n' "$snap" | grep -iE 'textbox|input' | head -1)"
  if [ -n "$line" ]; then
    ref="$(printf '%s\n' "$line" | grep -oE 'ref=e[0-9]+' | head -1 | sed 's/^ref=//')"
    [ -n "$ref" ] && { printf '%s' "$ref"; return 0; }
  fi
  printf '%s\n' "$snap" | grep -oE 'ref=e[0-9]+' | head -1 | sed 's/^ref=//'
}

run_conformance_battery() {
  local session="${1:-backstop-conformance}"
  local target="${2:-$(_conformance_default_target)}"
  local RESULT=0
  local PRE_PIDS POST_PIDS LEAKED

  # NOTE (load-bearing): open/fill/close below are captured to a TEMP FILE,
  # never a command-substitution pipe. A real (or stubbed) `open` may
  # background a long-lived process that inherits stdout/stderr — under a
  # pipe, that blocks the capture until the backgrounded process exits (a
  # classic bash gotcha, proven the hard way while wiring this into
  # qc-agent-browser.sh — GK-28/U90). snapshot never backgrounds anything, so
  # $(...) is safe for legs 2/3.
  local _tmp
  echo "  [leg 1/5] open — ref-based session start"
  PRE_PIDS="$(_scoped_chrome_pids)"
  _tmp="$(mktemp)"
  agent-browser --headed false open --session "$session" "$target" >"$_tmp" 2>&1
  if [ $? -eq 0 ]; then
    echo "    OK open succeeded (session=$session target=$target)"
  else
    echo "    FAIL open FAILED: $(cat "$_tmp")"
    RESULT=1
  fi
  rm -f "$_tmp"

  echo "  [leg 2/5] snapshot returns a ref-based interactive element (@eN)"
  local SNAP1 REF1
  SNAP1="$(agent-browser --headed false snapshot --session "$session" -i 2>&1)"
  REF1="$(_conformance_pick_ref "$SNAP1")"
  if [ -n "$REF1" ]; then
    echo "    OK snapshot returned a ref-based element (ref=$REF1)"
  else
    echo "    FAIL snapshot did NOT return any ref-based element (@eN); output: $SNAP1"
    RESULT=1
  fi

  echo "  [leg 3/5] snapshot stability — SAME ref across two calls, no DOM change"
  local SNAP2 REF2
  SNAP2="$(agent-browser --headed false snapshot --session "$session" -i 2>&1)"
  REF2="$(_conformance_pick_ref "$SNAP2")"
  if [ -n "$REF1" ] && [ "$REF1" = "$REF2" ]; then
    echo "    OK ref is stable across repeated snapshots (ref=$REF1 both times)"
  else
    echo "    FAIL ref is NOT stable across repeated snapshots (first=$REF1, second=$REF2)"
    RESULT=1
  fi

  echo "  [leg 4/5] fill by ref — positional argv (fill @ref value), READ-BACK verified"
  # READ-BACK (not exit status alone). A tool that accepts the fill argv, exits 0
  # and mutates NOTHING is indistinguishable from a working one if only $? is
  # checked — and that is precisely the capability Skill 44's Tier-4 fallback and
  # Skill 6's browser_manager.sh depend on. The written value is read back with
  # `get value`, which agent-browser 0.27.0 (this skill's pin) prints on stdout
  # as the bare value; an unfilled element returns empty. The value carries a
  # per-run nonce so a stale value from an earlier run can never satisfy it.
  local FILL_VALUE="backstop-conformance-value-$$-${RANDOM}"
  local READBACK
  if [ -n "$REF1" ]; then
    _tmp="$(mktemp)"
    agent-browser --headed false fill --session "$session" "@$REF1" "$FILL_VALUE" >"$_tmp" 2>&1
    if [ $? -eq 0 ]; then
      READBACK="$(agent-browser --headed false get value "@$REF1" --session "$session" 2>/dev/null | head -1)"
      READBACK="${READBACK%$'\r'}"
      if [ "$READBACK" = "$FILL_VALUE" ]; then
        echo "    OK fill by ref succeeded and the field READ BACK the written value (@$REF1)"
      else
        echo "    FAIL fill by ref reported success but the field did NOT hold the written value (@$REF1): wrote '$FILL_VALUE', read back '$READBACK'"
        RESULT=1
      fi
    else
      echo "    FAIL fill by ref FAILED (@$REF1): $(cat "$_tmp")"
      RESULT=1
    fi
    rm -f "$_tmp"
  else
    echo "    FAIL fill by ref FAILED: no ref available from leg 2 to fill"
    RESULT=1
  fi

  echo "  [leg 5/5] guaranteed close — read-back: zero leaked scoped processes"
  agent-browser --headed false close --session "$session" >/dev/null 2>&1 || true
  sleep 1
  POST_PIDS="$(_scoped_chrome_pids)"
  LEAKED="$(_new_pids "$PRE_PIDS" "$POST_PIDS")"
  LEAKED="$(printf '%s' "$LEAKED" | sed '/^$/d')"
  if [ -z "$LEAKED" ]; then
    echo "    OK close is read-back-verified clean (zero processes this battery spawned remain)"
  else
    echo "    FAIL close did NOT clean up — leaked pid(s): $(printf '%s' "$LEAKED" | tr '\n' ' ')"
    RESULT=1
  fi

  return $RESULT
}

# build_conformance_stub <bin-dir> <pidfile-path> <state-dir> [break-capability]
#   break-capability: "" (clean) | open | snapshot | snapshot_stability | fill
#                     | fill_noop | close
# `fill_noop` is the SILENT one: the stub accepts the fill argv, prints FILLED
# and exits 0 while mutating nothing. A battery that checks only exit status
# cannot tell it from a working CLI — leg 4's read-back is what catches it.
# Writes a fake `agent-browser` into <bin-dir> that mimics just enough of the
# real CLI's argv shape (positional ref fill, `-i` snapshot with `ref=eN`
# annotations, a scoped Chromium stand-in on `open`) for run_conformance_battery
# to exercise all five legs without a real browser. When [break-capability] is
# set, that ONE leg's underlying operation is deliberately broken — this is
# what proves the battery is fail-closed (a battery that can never fail on a
# broken CLI is worthless).
build_conformance_stub() {
  local bin_dir="$1" pidfile="$2" state_dir="$3" brk="${4:-}"
  mkdir -p "$bin_dir" "$state_dir"
  cat > "$bin_dir/agent-browser" <<STUBEOF
#!/usr/bin/env bash
PIDFILE="$pidfile"
STATEDIR="$state_dir"
BREAK="$brk"

verb=""
for a in "\$@"; do
  case "\$a" in
    open|snapshot|fill|close|find|get) verb="\$a"; break ;;
  esac
done

case "\$verb" in
  open)
    if [ "\$BREAK" = "open" ]; then
      echo "ERROR: open capability broken (fixture)" >&2
      exit 1
    fi
    ( exec -a "chrome --user-data-dir=/tmp/agent-browser-chrome-\$\$-conf-stub" sleep 300 ) </dev/null >/dev/null 2>&1 &
    disown \$! 2>/dev/null || true
    echo "\$!" > "\$PIDFILE"
    echo "OPENED"
    exit 0
    ;;
  snapshot)
    if [ "\$BREAK" = "snapshot" ]; then
      echo "no interactive elements here"
      exit 0
    fi
    if [ "\$BREAK" = "snapshot_stability" ]; then
      # Returns a DIFFERENT ref every call -- simulates an unstable ref.
      echo "- heading \"Skill 3 backstop-conformance fixture\" [level=1, ref=e\$RANDOM]"
      echo "- textbox \"fill me\" [ref=e\$RANDOM]"
      echo "- button \"Submit\" [ref=e\$RANDOM]"
      exit 0
    fi
    echo "- heading \"Skill 3 backstop-conformance fixture\" [level=1, ref=e1]"
    echo "- textbox \"fill me\" [ref=e2]"
    echo "- button \"Submit\" [ref=e3]"
    exit 0
    ;;
  fill)
    if [ "\$BREAK" = "fill" ]; then
      echo "ERROR: fill capability broken (fixture)" >&2
      exit 1
    fi
    # Locate the @ref and the value that follows it (positional argv, the shape
    # ghl_ab_executor.py verified live: fill @eN "value").
    ref=""; val=""; nextval=0
    for a in "\$@"; do
      if [ "\$nextval" = "1" ]; then val="\$a"; nextval=0; continue; fi
      case "\$a" in
        @*) ref="\${a#@}"; nextval=1 ;;
      esac
    done
    # BREAK=fill_noop: accept the argv, report success, MUTATE NOTHING. This is
    # the tool leg 4 could not previously detect.
    if [ "\$BREAK" != "fill_noop" ] && [ -n "\$ref" ]; then
      mkdir -p "\$STATEDIR"
      printf '%s' "\$val" > "\$STATEDIR/\$ref.value"
    fi
    echo "FILLED"
    exit 0
    ;;
  get)
    # get value @eN -- mirrors the real CLI: prints the stored value on stdout,
    # nothing at all for an element that was never filled. (No backticks in this
    # heredoc: it is UNQUOTED, so backticks would be run at generation time.)
    ref=""
    for a in "\$@"; do
      case "\$a" in
        @*) ref="\${a#@}" ;;
      esac
    done
    if [ -n "\$ref" ] && [ -f "\$STATEDIR/\$ref.value" ]; then
      cat "\$STATEDIR/\$ref.value"
    fi
    echo ""
    exit 0
    ;;
  close)
    if [ "\$BREAK" = "close" ]; then
      # Intentionally does NOT kill the stand-in -- simulates a leaked session.
      exit 0
    fi
    [ -s "\$PIDFILE" ] && kill -TERM "\$(cat "\$PIDFILE")" 2>/dev/null
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
STUBEOF
  chmod +x "$bin_dir/agent-browser"
}
