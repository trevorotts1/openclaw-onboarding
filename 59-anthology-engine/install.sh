#!/usr/bin/env bash
# 59-anthology-engine/install.sh -- per-box install bootstrap.
# ----------------------------------------------------------------------------
# Resolves this box for the Anthology Engine, as the NODE USER (never root):
#   1. dependency check (verify-deps.sh)
#   2. resolve the engine tier map (preflight.sh) into model-map.json
#   3. credential labels present -- SET or NOT SET only, never a value
#      (delegates to scripts/caf_credential_gate.py when present)
#   4. webhook route + the ONE daily cron tick + Drive-root reachability
#      (delegates to scripts/provision-anthology-client.sh when present)
# Heavy provisioning lives in provision-anthology-client.sh (W2.6); this script
# is the thin bootstrap that runs what is present and NAMES what is pending.
#
# Exit 0 = box ready (or ready-pending-provisioning, clearly reported);
#          2 = a named hard prerequisite is missing.
set -uo pipefail  # Intentional: no -e; exit codes handled explicitly per house contract (ENGINE-MANIFEST.json rows 30-32)
# Accepted as a no-op: update-skills.sh passes this to every installer;
# installers that do not parse it must not fail the roll.
[ "${1:-}" = "--idempotent" ] && shift
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS="$SELF_DIR/scripts"
note() { echo "=== [install.sh] $* ==="; }

# Guard against a root run (a root-owned config file freezes the gateway).
if [ "$(id -u)" = "0" ]; then
    echo "REFUSING: install.sh must run as the NODE USER, never root (a root-owned config freezes the gateway)." >&2
    exit 2
fi

note "STEP 1/4 -- dependency check"
# PyMuPDF (fitz) is a HARD dependency of the output-side font-floor gate
# (scripts/guard-font-floor.py exits 3 EX_DEP without it, leaving the 14pt floor
# silently unenforced). Install it best-effort into the SAME interpreter the gate
# runs under, BEFORE verify-deps.sh -- which then HARD-asserts fitz so this
# bootstrap aborts loud below if it is still missing.
if command -v python3 >/dev/null 2>&1 && ! python3 -c "import fitz" >/dev/null 2>&1; then
    note "installing PyMuPDF (fitz) for the font-floor gate"
    python3 -m pip install --user --break-system-packages --quiet PyMuPDF >/dev/null 2>&1 \
        || python3 -m pip install --user --quiet PyMuPDF >/dev/null 2>&1 \
        || echo "  (PyMuPDF install attempt failed; verify-deps.sh will name it as a hard prerequisite)"
fi
if [ -f "$SELF_DIR/verify-deps.sh" ]; then
    bash "$SELF_DIR/verify-deps.sh" || { echo "MISSING PREREQUISITE: python3 and/or PyMuPDF/fitz (see verify-deps.sh)"; exit 2; }
else
    command -v python3 >/dev/null 2>&1 || { echo "MISSING PREREQUISITE: python3"; exit 2; }
    python3 -c "import fitz" >/dev/null 2>&1 || { echo "MISSING PREREQUISITE: PyMuPDF/fitz (the font-floor gate cannot run)"; exit 2; }
fi

note "STEP 2/4 -- resolve the engine tier map (preflight.sh)"
if [ -f "$SELF_DIR/preflight.sh" ]; then
    bash "$SELF_DIR/preflight.sh" || { echo "MISSING PREREQUISITE: a clean model-map (preflight failed)"; exit 2; }
else
    echo "  (preflight.sh missing; cannot resolve the tier map)"; exit 2
fi

note "STEP 3/4 -- credential labels (SET or NOT SET only, never a value)"
if [ -f "$SCRIPTS/caf_credential_gate.py" ]; then
    GATE_RC=0
    python3 "$SCRIPTS/caf_credential_gate.py" || GATE_RC=$?
    case "$GATE_RC" in
        0)
            # gate passed
            ;;
        4)
            echo "HARD-STOP: credential gate flagged an INLINE_EXPOSURE in a file -- review the gate output above, remove the exposed value, then re-run install.sh." >&2
            exit 2
            ;;
        2)
            echo "NOT READY: credential gate reported missing required labels -- see the gate output above. Resolve missing labels before re-running install.sh." >&2
            exit 2
            ;;
        *)
            echo "NOT READY: credential gate exited with unexpected code $GATE_RC -- see the gate output above." >&2
            exit 2
            ;;
    esac
else
    echo "  PENDING: scripts/caf_credential_gate.py (W2.3) not present yet; credential resolution deferred to provisioning."
fi

note "STEP 4/4 -- webhook route, the ONE daily cron tick, Drive-root reachability"
if [ -f "$SCRIPTS/provision-anthology-client.sh" ]; then
    echo "  provision-anthology-client.sh is present; run it to complete per-box provisioning:"
    echo "    bash $SCRIPTS/provision-anthology-client.sh"
else
    echo "  PENDING: scripts/provision-anthology-client.sh (W2.6) not present yet; route + cron + Drive root are set at provisioning."
fi

note "ready-PENDING-provisioning: bootstrap complete -- NOW RUN provision-anthology-client.sh"
exit 0
