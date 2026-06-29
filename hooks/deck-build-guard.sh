#!/usr/bin/env bash
# deck-build-guard.sh — FRONT-DOOR DECK-BUILD INTERCEPTOR (FIX B).
#
# Makes the canonical build the ONLY physically-possible path for a Presentations
# deck. The whole guardrail stack (intake gate, kie-only render, 9,000-char prompt
# floor, image-QC battery, phase-attestation chain, no-skip proof) lives INSIDE the
# canonical path:
#
#       presentation-canonical-entry.sh -> run_signature_deck.py -> build_deck.py
#
# An agent that hand-rolls `python3 working/phase4_*.py`, calls build_deck.py /
# run_signature_deck.py directly, or fabricates a slide canvas / native pptx text /
# direct kie createTask, bypasses EVERY guardrail because the thing that runs those
# was never run. This interceptor refuses those commands at the door.
#
# ── SHIPPED MODE (OQ-1, verified against the live repo/gateway) ───────────────
# The OpenClaw gateway does NOT expose an openclaw.json exec command-gate: `tools.exec`
# is a security/ask policy only, `agents.defaults.tools.exec` is an INVALID key, and
# the per-agent AgentEntry.tools schema (additionalProperties:false) cannot pattern-
# match commands. The genuinely-supported pre-exec command-gate is the CLAUDE-CODE
# PreToolUse hook (the same mechanism hooks/ceo-intent-gate.sh uses). So this guard
# ships as:
#   (1) a Claude-Code PreToolUse hook (stdin JSON event -> permissionDecision), wired
#       via the box's settings.json hooks.PreToolUse where that path exists; AND
#   (2) a standalone exec-wrapper (--cmd "...": exit 0 allow / exit 13 deny) for a
#       gateway-side wrapper alias.
# On a pure-OpenClaw box with neither, the FALLBACK enforcement is the always-on
# presentation-canonical-entry.sh GATE 2 (bypass-scan) + GATE 0 (intake-complete) —
# no regression (the agent must still run the wrapper, but the wrapper is the only
# sanctioned build command and TOOLS.md names it as the one tool).
#
# DECISION RULES (applied to the exec/Bash command string):
#   ALLOW  — the command runs presentation-canonical-entry.sh (the ONE front door),
#            OR it is not a deck-build command at all.
#   DENY   — raw `python3 .../working/*.py`; a DIRECT build_deck.py / run_signature_
#            deck.py invocation NOT via the canonical entry; an ad-hoc python-pptx
#            assembler (Presentation()/add_textbox), a local Pillow slide canvas
#            (Image.new ... 2048 ... 1152), or a direct kie createTask.
#   DENY   — a canonical build dispatched while the intake ledger is NOT complete
#            (best-effort: when --run-dir is parseable and its intake_ledger.json is
#            not complete — ties FIX B to the FIX D intake state machine).
#
# PreToolUse protocol (Claude-Code path), identical to ceo-intent-gate.sh:
#   stdin  = JSON event { "hook_event_name":"PreToolUse","tool_name":"...",
#                         "tool_input":{ "command":"..." }, ... }
#   stdout = JSON decision (hookSpecificOutput.permissionDecision deny|allow)
#   exit 0 = decision is in stdout; a non-matching command exits 0 silently (allow).
#
# Install: scripts/verify-wiring.sh --dept presentations asserts this guard is present
# and (where the Claude-Code path exists) wired into settings.json hooks.PreToolUse.

set -uo pipefail

PROG="deck-build-guard.sh"
DENY_EXIT=13   # standalone/wrapper mode: 0=allow, 13=deny (the documented contract)

# ── Standalone / wrapper mode: --cmd "COMMAND" (no stdin event) ───────────────
MODE="hook"
CMD=""
RUN_DIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --cmd)     MODE="cmd"; CMD="${2:-}"; shift 2 ;;
    --run-dir) RUN_DIR="${2:-}"; shift 2 ;;
    -h|--help) sed -n '1,40p' "$0"; exit 0 ;;
    *) shift ;;
  esac
done

# ── Hook mode: read the PreToolUse event from stdin and extract the command ───
if [ "$MODE" = "hook" ]; then
  EVENT_JSON="$(cat 2>/dev/null || true)"
  if [ -z "$EVENT_JSON" ]; then
    exit 0   # no event -> nothing to gate (allow)
  fi
  if command -v python3 >/dev/null 2>&1; then
    CMD="$(printf '%s' "$EVENT_JSON" | python3 -c '
import json,sys
try:
    e=json.load(sys.stdin)
except Exception:
    print(""); sys.exit(0)
ti=e.get("tool_input") or {}
# exec/Bash tools carry the command under tool_input.command (or .cmd/.script)
print(ti.get("command") or ti.get("cmd") or ti.get("script") or "")
' 2>/dev/null)"
  fi
fi

# Nothing to inspect -> allow.
[ -n "${CMD:-}" ] || { [ "$MODE" = "cmd" ] && exit 0 || exit 0; }

# ── Decision helpers ──────────────────────────────────────────────────────────
emit_deny() {
  local reason="$1"
  if [ "$MODE" = "cmd" ]; then
    echo "DENY [$PROG]: $reason" >&2
    exit "$DENY_EXIT"
  fi
  # Claude-Code PreToolUse deny (JSON on stdout, exit 0).
  printf '%s\n' "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"$reason\"}}"
  exit 0
}
emit_allow() {
  if [ "$MODE" = "cmd" ]; then
    echo "ALLOW [$PROG]" >&2
  fi
  exit 0
}

REDIRECT="Build the deck the ONE sanctioned way: bash presentation-canonical-entry.sh --run-dir <DIR> --slides slides.json --out out.pptx. That single front door runs the intake gate, the kie-only render, the 9,000-char prompt floor, the image-QC battery, the phase-attestation chain, and the no-skip proof. Hand-rolled working/*.py, a direct build_deck.py / run_signature_deck.py call, an ad-hoc python-pptx assembler, a local Pillow slide canvas, or a direct kie createTask bypasses every guardrail and is refused."

# 1. If the command goes through the canonical front door, ALLOW (optionally check intake).
case "$CMD" in
  *presentation-canonical-entry.sh*)
    # Best-effort intake-complete gate: if a --run-dir is present and its intake
    # ledger is not complete, deny (the FIX D intake state machine must finish first).
    RD="$RUN_DIR"
    if [ -z "$RD" ]; then
      RD="$(printf '%s' "$CMD" | sed -n 's/.*--run-dir[ =]\{1,\}\([^ ]*\).*/\1/p' | head -1)"
    fi
    if [ -n "$RD" ] && command -v python3 >/dev/null 2>&1; then
      LEDGER="$RD/working/checkpoints/intake_ledger.json"
      if [ -f "$LEDGER" ]; then
        if ! python3 -c "import json,sys; sys.exit(0 if json.load(open('$LEDGER')).get('complete') is True else 1)" 2>/dev/null; then
          emit_deny "The deck intake is not complete. Finish the one-question-at-a-time intake first (deck-intake-driver.py --next / --answer / --confirm / --complete), then build. The build is blocked until intake_ledger.json is complete."
        fi
      fi
    fi
    emit_allow
    ;;
esac

# 2. Forbidden raw-build signatures (the ungoverned paths).
#    a) python invoking a hand-rolled script under a working/ dir
if printf '%s' "$CMD" | grep -Eq 'python[0-9.]*[[:space:]]+[^|;&]*working/[^[:space:]|;&]*\.py'; then
  emit_deny "Hand-rolled working/*.py renderer/assembler. $REDIRECT"
fi
#    b) a DIRECT build_deck.py / run_signature_deck.py invocation (not via the wrapper)
if printf '%s' "$CMD" | grep -Eq 'python[0-9.]*[[:space:]]+[^|;&]*(build_deck|run_signature_deck)\.py'; then
  emit_deny "Direct build_deck.py / run_signature_deck.py invocation. $REDIRECT"
fi
#    c) ad-hoc python-pptx native assembler (Presentation()/add_textbox/add_text_box)
if printf '%s' "$CMD" | grep -Eq 'add_text_?box|pptx\.Presentation\(|from pptx import'; then
  emit_deny "Ad-hoc python-pptx native-text assembler. $REDIRECT"
fi
#    d) local Pillow slide canvas at the 16:9 2K deck dimensions
if printf '%s' "$CMD" | grep -Eq 'Image\.new[^)]*2048[^)]*1152|Image\.new[^)]*1152[^)]*2048'; then
  emit_deny "Local Pillow slide canvas (bypasses the kie-only render). $REDIRECT"
fi
#    e) a direct kie createTask outside build_deck.py
if printf '%s' "$CMD" | grep -Eq 'createTask|api\.kie\.ai/api/v1/jobs/createTask'; then
  emit_deny "Direct kie createTask (only build_deck.py may talk to kie.ai). $REDIRECT"
fi

# 3. Not a deck-build command -> allow.
emit_allow
