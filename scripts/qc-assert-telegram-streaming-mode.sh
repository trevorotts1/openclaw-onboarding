#!/usr/bin/env bash
# =============================================================================
# qc-assert-telegram-streaming-mode.sh
#
# HEALTH SWEEP (report-only, never mutates): does this box stream Telegram
# previews in `partial` mode?
#
# WHY IT MATTERS. In `partial` mode the gateway sends a preview message and then
# edits it as tokens arrive, and every inter-tool narration block can surface as
# its own Telegram message. One turn that narrates a hunt across a dozen tool
# calls reads to the client as a dozen separate messages — which is exactly what
# made a single looping turn look like eleven on a client box. `partial` does not
# CAUSE the loop (see N40 for that); it is the amplifier that turns an invisible
# loop into a visible spam burst.
#
# ⛔ THE TRAP THIS GATE EXISTS TO CLOSE: ABSENT IS NOT SAFE.
# `channels.telegram.streaming.mode` DEFAULTS TO "partial" when the key is
# absent — confirmed in the installed runtime, where the Telegram resolver is
# `resolveChannelPreviewStreamMode(params, "partial")`. So a box that never
# configured streaming IS on partial. This repo contains zero `streaming` writes,
# which means the roll never sets it, which means the fleet-wide default is the
# amplifying mode. Reading the key and finding nothing is a POSITIVE finding
# here, not a clean result.
#
# ⛔ AND `openclaw config get` CANNOT ANSWER THIS. It reports FILE contents, not
# effective config: a legal-but-unwritten key exits 1 with "Config path not
# found", identical to a bogus path. It cannot distinguish "absent (therefore
# partial)" from "explicitly off". This gate therefore reads openclaw.json
# directly — the same choice the fleet validation harness makes for runRetries.
#
# Exit codes:
#   0  — checked: streaming mode is NOT partial (explicitly off/block/progress)
#   1  — checked: this box streams in PARTIAL — either set explicitly, or
#        DEFAULTED by an absent key (both are reported, and distinguished)
#   2  — usage error
#   3  — UNDETERMINED: the instrument itself is absent (config not found,
#        unreadable, or unparseable) — this NEVER collapses into exit 0
#
# This gate REPORTS. It never writes config. Changing a client's streaming mode
# is a client-visible behaviour change and belongs to the operator, not a sweep.
#
# Config resolution (first that applies wins):
#   1. an explicit path passed as $1
#   2. $SMOKE_OC_CONFIG (parity with the other config gates in this family)
#   3. the LIVE box config — /data/.openclaw/openclaw.json on a VPS (detected by
#      the presence of /data/.openclaw), else $HOME/.openclaw/openclaw.json
#
# Wired in:
#   Not yet wired into scripts/qc-system-integrity.sh or the fleet validation
#   harness — this is a new report-only sweep; wiring it into an aggregator (and
#   deciding whether a `partial` box is a WARN or a FAIL fleet-wide) is a
#   separate, operator-facing decision.
# =============================================================================

set -uo pipefail

QUIET=0
CONFIG_ARG=""

_pass() { [ "$QUIET" = "0" ] && printf '[qc-telegram-streaming] PASS  %s\n' "$*"; return 0; }
_fail() { printf '[qc-telegram-streaming] FAIL  %s\n' "$*" >&2; return 0; }
_info() { [ "$QUIET" = "0" ] && printf '[qc-telegram-streaming] INFO  %s\n' "$*"; return 0; }
_undetermined() { printf '[qc-telegram-streaming] UNDETERMINED  %s\n' "$*" >&2; return 0; }

while [ $# -gt 0 ]; do
  case "$1" in
    --quiet) QUIET=1; shift ;;
    -h|--help)
      sed -n '1,52p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    --*) echo "Unknown arg: $1" >&2; exit 2 ;;
    *)
      if [ -n "$CONFIG_ARG" ]; then
        echo "Unknown arg: $1" >&2
        exit 2
      fi
      CONFIG_ARG="$1"
      shift
      ;;
  esac
done

if [ -d "/data/.openclaw" ]; then
  LIVE_DEFAULT="/data/.openclaw/openclaw.json"
else
  LIVE_DEFAULT="$HOME/.openclaw/openclaw.json"
fi

OC_CONFIG="$CONFIG_ARG"
[ -z "$OC_CONFIG" ] && OC_CONFIG="${SMOKE_OC_CONFIG:-}"
[ -z "$OC_CONFIG" ] && OC_CONFIG="$LIVE_DEFAULT"

_info "config: $OC_CONFIG"

if [ ! -f "$OC_CONFIG" ]; then
  _undetermined "config file not found: $OC_CONFIG — the streaming-mode invariant DID NOT RUN. This is not a pass: no config was inspected."
  exit 3
fi
if ! command -v python3 >/dev/null 2>&1; then
  _undetermined "python3 is not on PATH — the streaming-mode invariant DID NOT RUN."
  exit 3
fi

# The python source is written to a temp file first, THEN run via a plain
# `python3 "$file" ...` command substitution — never a heredoc directly inside
# `$(...)`. bash 3.2 (macOS stock /bin/bash, 3.2.57) mis-scans parens in that
# nesting and aborts at PARSE time. Same two-step, same reason, as
# scripts/qc-assert-legacy-agents-list.sh.
QC_PY="$(mktemp "${TMPDIR:-/tmp}/qc-telegram-streaming.XXXXXX.py")"
cat > "$QC_PY" <<'PYEOF'
import io
import json
import sys

path = sys.argv[1]
try:
    with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
        cfg = json.load(fh)
except ValueError as exc:
    print("UNDETERMINED|%s is not parseable JSON (%s)" % (path, exc))
    sys.exit(0)
except (IOError, OSError) as exc:
    print("UNDETERMINED|could not read %s (%s)" % (path, type(exc).__name__))
    sys.exit(0)

if not isinstance(cfg, dict):
    print("UNDETERMINED|%s does not contain a JSON object at the top level" % path)
    sys.exit(0)

channels = cfg.get("channels")
if channels is not None and not isinstance(channels, dict):
    print("UNDETERMINED|channels is present but is not an object in %s" % path)
    sys.exit(0)
telegram = (channels or {}).get("telegram")
if telegram is not None and not isinstance(telegram, dict):
    print("UNDETERMINED|channels.telegram is present but is not an object in %s"
          % path)
    sys.exit(0)
tg = telegram or {}

# Resolution order mirrors the runtime resolver exactly:
#   streaming.mode -> bare streaming string -> legacy streamMode
#   -> boolean streaming (true->partial, false->off) -> DEFAULT "partial"
VALID = ("off", "partial", "block", "progress")

def norm(v):
    if isinstance(v, str) and v.strip().lower() in VALID:
        return v.strip().lower()
    return None

streaming = tg.get("streaming")
mode = None
source = None

if isinstance(streaming, dict):
    mode = norm(streaming.get("mode"))
    if mode:
        source = "channels.telegram.streaming.mode"
if mode is None:
    mode = norm(streaming)
    if mode:
        source = "channels.telegram.streaming (bare string)"
if mode is None:
    mode = norm(tg.get("streamMode"))
    if mode:
        source = "channels.telegram.streamMode (legacy)"
if mode is None and isinstance(streaming, bool):
    mode = "partial" if streaming else "off"
    source = "channels.telegram.streaming (boolean %s)" % str(streaming).lower()
if mode is None:
    # THE LOAD-BEARING BRANCH. No key anywhere -> the runtime default applies.
    mode = "partial"
    source = "DEFAULT (no streaming key set anywhere)"

if mode == "partial":
    print("FAIL|%s|%s" % (mode, source))
else:
    print("PASS|%s|%s" % (mode, source))
PYEOF

ANALYSIS="$(python3 "$QC_PY" "$OC_CONFIG" 2>&1)"
PY_RC=$?
rm -f "$QC_PY"

if [ "$PY_RC" -ne 0 ]; then
  _undetermined "python3 analysis failed (rc=$PY_RC) against $OC_CONFIG — the invariant DID NOT RUN. Output: ${ANALYSIS:-<empty>}"
  exit 3
fi
if [ -z "$ANALYSIS" ]; then
  _undetermined "python3 analysis produced no output for $OC_CONFIG — treating as instrument-absent rather than a silent pass."
  exit 3
fi

KIND="${ANALYSIS%%|*}"
REST="${ANALYSIS#*|}"
MODE="${REST%%|*}"
SOURCE="${REST#*|}"

case "$KIND" in
  PASS)
    _pass "$OC_CONFIG — Telegram streaming mode is '$MODE' (from $SOURCE); inter-tool narration will not fan out into separate client messages."
    exit 0
    ;;
  FAIL)
    _fail "$OC_CONFIG — this box streams Telegram in PARTIAL mode (from $SOURCE). Every inter-tool narration block can surface as its OWN Telegram message, so a single long turn reads to the client as many messages."
    if [ "$SOURCE" = "DEFAULT (no streaming key set anywhere)" ]; then
      echo "NOTE: the key is ABSENT, not set to partial. Absent IS partial — the runtime" >&2
      echo "  default for Telegram is 'partial'. This repo writes no streaming key, so every" >&2
      echo "  box that was never hand-configured is in this state." >&2
    fi
    echo "REPORT-ONLY: this gate does not change client config. A streaming-mode change is" >&2
    echo "  client-visible behaviour and belongs to the operator. Valid modes are" >&2
    echo "  off | partial | block | progress; 'progress' keeps ONE editable status draft for" >&2
    echo "  tool progress and sends the final answer as a single message, and 'off' suppresses" >&2
    echo "  generic tool chatter entirely." >&2
    exit 1
    ;;
  UNDETERMINED)
    _undetermined "$MODE"
    exit 3
    ;;
  *)
    _undetermined "unrecognised analyzer verdict ${KIND:-<empty>} for $OC_CONFIG — refusing to call that a pass."
    exit 3
    ;;
esac
