#!/usr/bin/env bash
# routing-mode.sh (RF-014) -- the routing safety switch an owner can use in words.
#
#   routing-mode.sh status                 what mode, is routing safe, what happened
#   routing-mode.sh set auto|shadow|legacy|off|model
#   routing-mode.sh reset                  release default again, tripwire re-armed
#   routing-mode.sh threshold [N]          failures in a row before the tripwire flips
#
# `set` writes the box's mode store ($OC_CONFIG/decision-engine-mode.conf) through
# shared-utils/routing_switch.py -- the SAME rules scripts/decision-engine-mode.py
# reads with (env > file > release default). It never edits openclaw.json, never
# touches anything else, and an `openclaw gateway restart` is never required: every
# consumer reads the store fresh on each decision (KIL-001).
#
# Modes:
#   auto    JEV decides where it can (release default)
#   shadow  same decisions as auto would make, JEV comparison logged, never adopted
#   legacy  the old way -- no JEV traffic at all
#   off     emergency JEV kill switch -- no JEV traffic at all
#   model   like auto, plus: when rules and JEV cannot place a task, THIS box's own
#           default model picks the department (never a hardcoded model; if the box
#           has no usable default model, that task goes the legacy way and it is logged)
#
# The tripwire (same module): N JEV routing failures in a row and the box flips
# ITSELF to legacy, writes state/routing-tripwire.flag + a routing-events.jsonl
# line, and stays there until the owner switches back. A box whose owner pinned a
# mode (any `set`, including back to auto) is never flipped.
#
# WHAT THE OWNER SAYS -> WHAT THE AGENT RUNS (plain words, no jargon):
#   "switch routing to the old way"     -> set legacy
#   "turn routing back on"              -> set auto (or: reset)
#   "turn the decision engine off"      -> set off      (emergency kill switch)
#   "let my own model route"            -> set model
#   "just watch it, don't change anything" -> set shadow
#   "is routing working?"                -> status
#
# Exit: 0 = ok/deliberate no-op   1 = the request could not be carried out
#       2 = usage                 3 = the mode store is CORRUPT (values above show why)
set -uo pipefail

USAGE="usage: routing-mode.sh status|set auto|shadow|legacy|off|model|reset|threshold [N]
env: OC_CONFIG (dir or openclaw.json path, default ~/.openclaw)"

command -v python3 >/dev/null 2>&1 || { echo "routing-mode: python3 not found -- cannot act" >&2; exit 1; }

# The switch module ships with shared-utils (the tree the updater already refreshes
# and the bridge imports from). A newer repo checkout next to this script wins, so a
# maintainer can test a fix from the clone before the box is updated.
_ONB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for _CANON in "$_ONB_DIR/shared-utils" "${OPENCLAW_SKILLS_DIR:-}/shared-utils" \
              "${OC_PERSISTENT_SCRIPTS_DIR:-}/../skills/shared-utils"; do
  [ -n "${_CANON%/}" ] && [ -f "$_CANON/routing_switch.py" ] && { _SU_DIR="$_CANON"; break; }
done
[ -n "${_SU_DIR:-}" ] || _SU_DIR="$(ls -d "${OC_CONFIG:-$HOME/.openclaw}/skills/shared-utils" \
                                      /data/.openclaw/skills/shared-utils 2>/dev/null | head -1)"
[ -n "${_SU_DIR:-}" ] && [ -f "$_SU_DIR/routing_switch.py" ] || {
  echo "routing-mode: routing_switch.py not found (looked beside this script, then in the installed shared-utils)" >&2
  echo "  fix: update the box (update-skills.sh) so shared-utils carries it, or run this from an onboarding checkout" >&2
  exit 3
}

OC_ROOT_PY="$( [ -n "${OC_CONFIG:-}" ] && printf '%s' "$OC_CONFIG" || printf '%s' '' )"

CMD="${1:-}"; shift || true
_arg="${1:-}"

case "$CMD" in
  status|set|reset|threshold) : ;;
  *) echo "$USAGE" >&2; exit 2 ;;
esac

# threshold [N]: read/set the failure threshold (persisted in routing-tripwire.conf).
if [ "$CMD" = "threshold" ]; then
  if [ -n "$_arg" ]; then
    case "$_arg" in ''|*[!0-9]*) echo "threshold: N must be a whole number >= 1" >&2; exit 2 ;; esac
    [ "$_arg" -ge 1 ] || { echo "threshold: N must be a whole number >= 1" >&2; exit 2; }
    export OPENCLAW_ROUTING_TRIPWIRE_FAILURES="$_arg"
    python3 - "$_SU_DIR" "$OC_ROOT_PY" set-threshold "$_arg" <<'PY' || exit 1
import os, sys
sys.path.insert(0, sys.argv[1])
import routing_switch as rs
root = rs.oc_root(sys.argv[2] or None)
if not root.is_dir():
    print("routing-mode: no OpenClaw root at %s -- nothing written" % root, file=sys.stderr); sys.exit(1)
try:
    (root / rs.THRESHOLD_STORE).write_text("%s\n" % int(sys.argv[3]), encoding="utf-8")
except OSError as e:
    print("routing-mode: cannot write %s: %s" % (root / rs.THRESHOLD_STORE, e), file=sys.stderr); sys.exit(1)
print("routing-mode: tripwire threshold set to %s (stored in %s)" % (sys.argv[3], root / rs.THRESHOLD_STORE))
PY
  fi
  export OPENCLAW_ROUTING_NO_RECORD=1
  python3 - "$_SU_DIR" "$OC_ROOT_PY" <<'PY' || exit 1
import json, sys
sys.path.insert(0, sys.argv[1])
import routing_switch as rs
st = rs.status(rs.oc_root(sys.argv[2] or None))
print("routing-mode: threshold %s (env OPENCLAW_ROUTING_TRIPWIRE_FAILURES wins)" % st["threshold"])
PY
  exit 0
fi

export OPENCLAW_ROUTING_NO_RECORD=1   # a status/set/reset never counts as an outcome

if [ "$CMD" = "set" ]; then
  case "$_arg" in
    auto|shadow|legacy|off|model) : ;;
    *) echo "routing-mode: set needs one of auto|shadow|legacy|off|model (got '${_arg:-}')" >&2
       echo "  words that map here: 'switch routing to the old way' -> legacy; 'turn routing back on' -> auto; 'turn the decision engine off' -> off; 'let my own model route' -> model" >&2
       exit 2 ;;
  esac
fi

python3 - "$_SU_DIR" "$OC_ROOT_PY" "$CMD" "${_arg:-}" <<'PY'
import os, sys
sys.path.insert(0, sys.argv[1])
import routing_switch as rs

root = rs.oc_root(sys.argv[2] or None)
cmd, arg = sys.argv[3], sys.argv[4]

try:
    st = rs.status(root)
except Exception as exc:  # noqa: BLE001 -- a broken store must still answer, loudly
    print("routing-mode: CANNOT TELL -- %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
    sys.exit(3)

if cmd == "status":
    names = {"auto": "JEV decides where it can (release default)",
             "shadow": "watching only: JEV is logged, never adopted",
             "legacy": "the old way: no JEV traffic",
             "off": "emergency kill switch: no JEV traffic",
             "model": "like auto + the box's own default model picks when rules cannot"}
    print("OpenClaw root : %s" % st["root"])
    print("routing mode  : %s%s" % (st["mode"], "" if st["valid"] else
          "  <-- CORRUPT (not one of %s)" % "|".join(rs.mode_names())))
    print("what that is  : %s" % names.get(st["mode"],
          "unknown -- the store holds a value no reader accepts"))
    print("chosen by     : %s%s" % (st["source"], " (pinned: the tripwire will not touch it)"
          if st["safetyNet"] == "pinned" else
          " (safety net armed: %s routing failures in a row flip it to legacy)" % st["threshold"]))
    if st["safetyNet"] == "tripped":
        print("TRIPWIRE      : TRIPPED -- the box flipped itself to legacy (%s failures in a row; last: %s)" % (
              st["consecutiveFailures"], st.get("lastFailureReason") or "unknown"))
        print("                routing-events.jsonl and routing-tripwire.flag carry the details; Rescue Rangers can see the flag")
        print("                switch back: routing-mode.sh set auto   (or set model / set legacy / reset)")
    elif st["consecutiveFailures"]:
        print("tripwire      : %s of %s consecutive JEV routing failures (last: %s)" % (
              st["consecutiveFailures"], st["threshold"], st.get("lastFailureReason") or "unknown"))
    else:
        print("tripwire      : armed, no recorded failures")
    if st["mode"] == "model" and "defaultModel" in st:
        print("default model : %s%s" % (st["defaultModel"] or "none resolves -- model mode falls back to legacy",
              " (%s/openclaw.json)" % st["root"]))
    ev = st.get("flag") or {}
    if st.get("lastEvent"):
        le = st["lastEvent"]
        print("last event    : %s at %s%s" % (le.get("event"), le.get("ts"),
              (" -- " + str(le.get("reason"))) if le.get("reason") else ""))
    if st["mode"] in ("legacy", "off"):
        print("reminder      : JEV is NOT routing on this box; tasks land via the old path. turn it back on: routing-mode.sh set auto")
    # A corrupt store is REPORTED here, but it cannot pass: the same rc 3 contract
    # as every other subcommand ("cannot tell" is never a pass).
    sys.exit(0 if st["valid"] else 3)

if not st["valid"]:
    print("routing-mode: the mode store is CORRUPT (%r) -- refusing to act on an unknown value." % st["mode"], file=sys.stderr)
    print("  fix: routing-mode.sh reset   (accepts the release default and re-arms the safety net), or write one word to %s" % (root / rs.STORE), file=sys.stderr)
    sys.exit(3)

env_mode = (os.environ.get(rs.ENV) or "").strip()

if cmd == "set":
    if env_mode:
        print("routing-mode: $%s=%s is set and OUTRANKS the store -- the file was not written." % (rs.ENV, env_mode), file=sys.stderr)
        print("  fix: unset %s, then run set %s again. (The store now holds the requested value; it takes over when the variable is gone.)" % (rs.ENV, arg), file=sys.stderr)
    try:
        res = rs.set_mode(root, arg)
    except (ValueError, FileNotFoundError) as exc:
        print("routing-mode: %s" % exc, file=sys.stderr)
        sys.exit(1)
    print("routing-mode: routing mode -> %s (was %s; written to %s)" % (res["mode"], res["previous"], root / rs.STORE))
    if res["envOverrides"]:
        print("  NOTE: $%s is set and still outranks the file until it is unset." % rs.ENV)
    print("  takes effect now -- no gateway restart needed (every consumer reads the store fresh)")
elif cmd == "reset":
    if not (root / rs.STORE).is_file():
        print("routing-mode: nothing to reset -- no mode store (release default %r already applies)" % rs.RELEASE_DEFAULT)
        sys.exit(0)
    res = rs.reset(root)
    print("routing-mode: mode store removed -- release default %r applies again (was %s); safety net re-armed" % (res["mode"], res["previous"]))
    if res["envOverrides"]:
        print("  NOTE: $%s is set and still outranks everything until it is unset." % rs.ENV)
else:
    print(USAGE_LINE, file=sys.stderr); sys.exit(2)

if arg == "off":
    print("  reminder: 'off' is the emergency JEV kill switch -- no JEV traffic until you switch back")
if arg in ("auto", "model"):
    print("  words for your agent: 'turn routing back on'")
PY
rc=$?
[ $rc -eq 0 ] && [ "$CMD" != "status" ] && [ -n "${1:-}" ] || true
exit $rc