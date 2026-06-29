#!/usr/bin/env bash
# deck-build-guard.sh — front-door interceptor for the Presentations department.
#
# PURPOSE: Deny hand-rolled deck builds and enforce the intake-interview precondition.
#
# INVOCATION PATHS (two, both required — they are complementary):
#
# (a) GATE-0 inside presentation-canonical-entry.sh:
#     presentation-canonical-entry.sh calls this guard at the very top, before its own
#     GATE 1/2/3 chain, to self-screen the run directory for hand-rolled artifacts and
#     the interview-ledger-complete precondition. This closes the enforcement gap even
#     for the one sanctioned door — it polices itself.
#
# (b) Operator before_tool_call gateway plugin hook:
#     An operator can wire this script as a gateway-level before_tool_call plugin so
#     every exec command the Presentations agent attempts is intercepted. This is the
#     right wiring point for fleet-wide enforcement; see docs.openclaw.ai/gateway/hooks.
#
# NOTE — tools.exec.preExec IS NOT A VALID KEY in OpenClaw:
#     The AgentEntry tools schema is additionalProperties:false; allowed sub-keys are
#     allow/alsoAllow/byProvider/codeMode/deny/elevated/exec/fs/loopDetection/message/
#     profile/sandbox/toolsBySender. The 'exec' key is an on/off tool toggle, NOT a
#     per-command-pattern denylist. Writing tools.exec.preExec into openclaw.json breaks
#     'openclaw config validate' fleet-wide and can freeze gateways. DO NOT use it.
#     Front-door enforcement is achieved via (a) making canonical-entry the ONLY
#     documented build route and (b) canonical-entry self-screening via GATE-0 above.
#
# COMMAND SOURCE (priority order):
#   1. $OPENCLAW_EXEC_CMD   — set by presentation-canonical-entry.sh for the GATE-0 call
#   2. stdin JSON           — gateway plugin hook delivers {tool_input:{command:...}}
#                            or {command:...}; parsed defensively with python3 then grep
#   3. "$*" / argv          — fallback for direct invocation
#
# EXIT CODES:
#   0 — allow (command is permitted)
#   2 — DENY  (OpenClaw's documented before_tool_call deny exit code)
#
# set -uo pipefail is intentional: unset-variable and pipeline errors abort the guard.
# ============================================================================

set -uo pipefail

# ---------------------------------------------------------------------------
# Resolve the command to inspect
# ---------------------------------------------------------------------------
CMD="${OPENCLAW_EXEC_CMD:-}"

if [ -z "$CMD" ]; then
    # Try stdin (JSON from gateway plugin hook)
    if [ ! -t 0 ]; then
        STDIN_DATA="$(cat 2>/dev/null || true)"
        if [ -n "$STDIN_DATA" ]; then
            # Try python3 JSON parse first (most reliable)
            if command -v python3 >/dev/null 2>&1; then
                CMD="$(echo "$STDIN_DATA" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    # Support {tool_input:{command:...}} and {command:...}
    v = (data.get('tool_input') or {}).get('command') or data.get('command') or ''
    print(str(v))
except Exception:
    pass
" 2>/dev/null || true)"
            fi
            # Fallback: grep for the command field value
            if [ -z "$CMD" ]; then
                CMD="$(printf '%s\n' "$STDIN_DATA" | \
                    grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | \
                    sed 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/' 2>/dev/null || true)"
            fi
        fi
    fi
fi

# Final fallback: positional arguments
[ -z "$CMD" ] && CMD="$*"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
deny() {
    echo "DENY [deck-build-guard]: $1" >&2
    echo "The ONLY sanctioned deck build is: bash presentation-canonical-entry.sh --run-dir … --slides … --out …" >&2
    exit 2
}

# is_canonical: true when the command invokes presentation-canonical-entry.sh
is_canonical() {
    case "$CMD" in
        *presentation-canonical-entry.sh*) return 0 ;;
    esac
    return 1
}

# is_deck_run_dir: true when the command targets a deck run directory
is_deck_run_dir() {
    case "$CMD" in
        *working/*|*renders/*|*slides.json*|*.pptx*) return 0 ;;
    esac
    return 1
}

# extract_run_dir: parse --run-dir <DIR> from CMD
extract_run_dir() {
    echo "$CMD" | python3 -c "
import re, sys
m = re.search(r'--run-dir[=\s]+([^\s]+)', sys.stdin.read())
print(m.group(1) if m else '')
" 2>/dev/null || true
}

# check_intake_ledger: returns 0 if intake is complete or ledger absent,
#                      exits 2 (deny) if ledger exists and status != complete
check_intake_ledger() {
    local run_dir="$1"
    [ -n "$run_dir" ] || return 0
    local ledger="$run_dir/working/interview/intake_ledger.json"
    [ -f "$ledger" ] || return 0  # no ledger = not started = allow (intake not yet begun)
    if command -v python3 >/dev/null 2>&1; then
        local status complete
        status="$(python3 -c "
import json, sys
try:
    d = json.load(open('$ledger'))
    print(d.get('status',''))
except Exception:
    print('')
" 2>/dev/null || true)"
        complete="$(python3 -c "
import json, sys
try:
    d = json.load(open('$ledger'))
    print('true' if d.get('complete') is True or d.get('complete') == 'true' else '')
except Exception:
    print('')
" 2>/dev/null || true)"
        if [ "$status" != "complete" ] && [ -z "$complete" ]; then
            deny "intake interview not complete (working/interview/intake_ledger.json status='$status'). Complete the deck-intake interview with deck-intake-driver.py before building."
        fi
    else
        # python3 absent: parse crudely with grep
        if ! grep -qE '"status"\s*:\s*"complete"' "$ledger" 2>/dev/null; then
            deny "intake interview not complete (working/interview/intake_ledger.json). Complete the deck-intake interview with deck-intake-driver.py before building."
        fi
    fi
    return 0
}

# ---------------------------------------------------------------------------
# ALLOW LIST — canonical-entry always passes the hand-rolled deny checks.
# (The intake-ledger check still applies even to canonical-entry.)
# ---------------------------------------------------------------------------
if is_canonical; then
    # Canonical-entry is the only allowed build route; skip hand-rolled deny rules.
    # Still check intake ledger so the one door self-polices.
    RUN_DIR_VAL="$(extract_run_dir)"
    check_intake_ledger "$RUN_DIR_VAL"
    exit 0
fi

# ---------------------------------------------------------------------------
# DENY RULE 1 — raw working/*.py (the ungoverned hand-rolled path)
# ---------------------------------------------------------------------------
case "$CMD" in
    *python3*working/*.py*|*python\ *working/*.py*)
        deny "raw 'python3 working/*.py' / 'python working/*.py' is the ungoverned hand-rolled path. Every deck build must go through presentation-canonical-entry.sh." ;;
    # Also catch: python3 path/to/working/something.py
    *python*)
        case "$CMD" in
            */working/*.py*)
                deny "raw invocation of a working/*.py script is the ungoverned hand-rolled path. Every deck build must go through presentation-canonical-entry.sh." ;;
        esac ;;
esac

# ---------------------------------------------------------------------------
# DENY RULE 2 — direct build_deck.py invocation
# ---------------------------------------------------------------------------
case "$CMD" in
    *build_deck.py*)
        deny "direct build_deck.py invocation is forbidden. presentation-canonical-entry.sh is the ONE sanctioned command; it dispatches run_signature_deck.py -> build_deck.py after all gate checks." ;;
esac

# ---------------------------------------------------------------------------
# DENY RULE 3 — direct run_signature_deck.py invocation
# ---------------------------------------------------------------------------
case "$CMD" in
    *run_signature_deck.py*)
        deny "direct run_signature_deck.py invocation is forbidden. Always invoke via presentation-canonical-entry.sh." ;;
esac

# ---------------------------------------------------------------------------
# DENY RULES 4-6 — only when the command targets a deck run directory
# ---------------------------------------------------------------------------
if is_deck_run_dir; then
    case "$CMD" in
        *add_textbox*|*add_text_box*)
            deny "python-pptx text overlay (add_textbox / add_text_box) in a deck run directory. Only the canonical assembler (build_deck.py via canonical-entry) may write PPTX; slide text must be baked into KIE images." ;;
    esac
    case "$CMD" in
        *"Image.new"*2048*|*"Image.new"*1152*)
            deny "local 2048x1152 Pillow canvas (Image.new) in a deck run directory. Slide images must be generated via KIE.ai through the canonical build path." ;;
    esac
    case "$CMD" in
        *createTask*|*"api.kie.ai"*)
            deny "direct kie createTask / api.kie.ai call in a deck run directory. KIE calls must go through build_deck.py via the canonical entry." ;;
    esac

    # Intake ledger check for non-canonical commands targeting a run dir
    RUN_DIR_VAL="$(extract_run_dir)"
    # If --run-dir not in cmd, try to infer from path segments
    if [ -z "$RUN_DIR_VAL" ]; then
        RUN_DIR_VAL="$(echo "$CMD" | grep -o '[^ ]*working[^ ]*' | sed 's|/working/.*||' | head -1 || true)"
    fi
    check_intake_ledger "$RUN_DIR_VAL"
fi

# ---------------------------------------------------------------------------
# Everything else is allowed
# ---------------------------------------------------------------------------
exit 0
