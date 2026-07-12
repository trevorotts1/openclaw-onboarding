#!/usr/bin/env bash
# Skill 23 department-decision writer (PRD P0-2 / P1-1).
#
# WHY THIS EXISTS: the interview records an owner's per-department YES / NO / LATER
# choice into canonicalReconciliation.decisions. A NO (opt-out) is only HONORED by
# the build enforcer (_canonical_decline_set in build-workforce.py, and the mirror
# declined_set in department-floor.py) when it carries an attributable owner-decision
# record — the OBJECT form {decision, source, decidedAt, decidedBy}. A bare string
# `decisions[<id>]="no"` (no provenance) is REJECTED and the department is force-added
# back, so the owner's opt-out is silently discarded and a smaller shop gets over-built.
# This helper writes the PROVENANCED object form the enforcer accepts, so a decline is
# actually honored. It mirrors the style/robustness of update-interview-state.sh
# (atomic write, jq --arg only — never string interpolation).
#
# The produced shape (accepted by _canonical_decline_set for a "no"):
#   .canonicalReconciliation.decisions[<dept>] = {
#     "decision":  "yes" | "no" | "later",
#     "source":    "owner-interview",
#     "decidedAt": "<ISO8601 UTC now>",
#     "decidedBy": "<ownerId>",
#     "sessionId": "<sessionId>"
#   }
# YES/LATER are written in the same object form (never bare strings) so the map is
# uniform and auditable; only a "no" is provenance-gated, but writing all three as
# objects keeps every decision attributable. No downstream reader string-compares a
# "yes"/"later" value (verified against build-workforce.py + department-floor.py), so
# the object form is safe for every decision type.
#
# OPT-OUT LOSS WARNING (P2-05 step 1): a "no" for a FLOOR department is an opt-out
# that costs the owner guaranteed functionality. Before such a decline is written,
# this helper ECHOES the department's one-line loss_warning (single source:
# department-naming-map.json, read via department-loss-warning.py) and REQUIRES
# --confirm-loss. Without the flag the decline is NOT written (exit 2) — the
# interview must show the warning and get an explicit confirmation first. The
# acknowledged warning is stamped into the decision object (lossWarning +
# lossWarningAck) alongside the four provenance fields canonical_decline.py
# requires, so the confirmation is itself auditable. A "no" for a NON-floor dept
# (a keyword-matched industry extra or a custom dept) has no loss_warning and is
# written directly — declining it costs no guaranteed floor functionality.
#
# Usage:
#   record-dept-decision.sh --dept <id> --decision yes|no|later \
#       --source owner-interview --by <ownerId> --session <sessionId> [--state <path>]
#   record-dept-decision.sh --dept <id> --decision no --confirm-loss \
#       --source owner-interview --by <ownerId> --session <sessionId>
#
# Idempotent: re-running for the same dept OVERWRITES that dept's decision object.
set -euo pipefail

# ── Parse flags ──────────────────────────────────────────────────────────────
DEPT=""
DECISION=""
SOURCE="owner-interview"
BY=""
SESSION=""
STATE_OVERRIDE=""
CONFIRM_LOSS=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dept)         DEPT="$2"; shift 2 ;;
    --decision)     DECISION="$2"; shift 2 ;;
    --source)       SOURCE="$2"; shift 2 ;;
    --by)           BY="$2"; shift 2 ;;
    --session)      SESSION="$2"; shift 2 ;;
    --state)        STATE_OVERRIDE="$2"; shift 2 ;;
    --confirm-loss) CONFIRM_LOSS=1; shift 1 ;;
    *) echo "unknown flag: $1" >&2; exit 1 ;;
  esac
done

# ── Validate required args ───────────────────────────────────────────────────
if [ -z "$DEPT" ]; then
  echo "ERROR: --dept <canonical_id> is required" >&2; exit 1
fi
DECISION_LC=$(printf '%s' "$DECISION" | tr '[:upper:]' '[:lower:]')
case "$DECISION_LC" in
  yes|no|later) ;;
  *) echo "ERROR: --decision must be one of yes|no|later (got '$DECISION')" >&2; exit 1 ;;
esac
# decidedBy is REQUIRED: the enforcer treats a "no" whose decidedBy is empty as
# missing provenance and IGNORES it (dept force-added back). Reject an empty --by
# up front so a decline can never be recorded in an un-honorable shape.
if [ -z "$BY" ]; then
  echo "ERROR: --by <ownerId> is required (provenance: an empty decidedBy makes a 'no' unhonored)" >&2; exit 1
fi
if [ -z "$SOURCE" ]; then
  echo "ERROR: --source must be non-empty (provenance field)" >&2; exit 1
fi

command -v jq >/dev/null 2>&1 || { echo "ERROR: jq not found on PATH" >&2; exit 1; }

# ── Resolve state file path (mirror update-interview-state.sh) ────────────────
if [ -n "$STATE_OVERRIDE" ]; then
  STATE="$STATE_OVERRIDE"
else
  if [ -d /data/.openclaw/workspace ]; then
    STATE_DIR=/data/.openclaw/workspace
  elif [ -d "$HOME/.openclaw/workspace" ]; then
    STATE_DIR="$HOME/.openclaw/workspace"
  else
    echo "ERROR: cannot find .openclaw/workspace directory (pass --state <path> to override)" >&2
    exit 1
  fi
  STATE="$STATE_DIR/.workforce-build-state.json"
fi

if [ ! -f "$STATE" ]; then
  echo "ERROR: state file does not exist at $STATE" >&2
  exit 1
fi

# ── Validate --dept against the canonical id list + recorded customs ──────────
# Issue #2: a decline keyed by a display name ("Video") or an underscore variant
# ("billing_finance") used to be stored raw and then IGNORED by the builder (which
# tested a raw `cid in declined`), silently over-provisioning the box. The shared
# normalizer closes that at read time, but we ALSO reject an unknown / misspelled
# dept id here so a decline can never be recorded against a non-existent department
# and vanish. Accepted ids: the live canonical floor (mandatory + universal-primary
# from list-canonical-departments.py) + any custom dept already recorded in the
# build-state (customKeeps / clientCustoms) + any dept already carrying a decision
# (so re-recording is always allowed). Comparison is normalization-insensitive.
SCRIPT_DIR_RD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPT_VALIDATION="$(python3 - "$SCRIPT_DIR_RD" "$STATE" "$DEPT" 2>/dev/null <<'PYVAL'
import sys, os, json, re, subprocess
scripts_dir, state_path, dept = sys.argv[1], sys.argv[2], sys.argv[3]
norm = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())
ids = set()
try:
    out = subprocess.run(
        ["python3", os.path.join(scripts_dir, "list-canonical-departments.py"), "--json"],
        capture_output=True, text=True, timeout=30)
    d = json.loads(out.stdout)
    for x in d.get("mandatory", []) or []:
        ids.add(norm(x.get("id")))
    for x in d.get("universal_primary_vertical", []) or []:
        ids.add(norm(x.get("id")))
except Exception:
    pass
# If the canonical list could not be loaded at all, do NOT block recording.
if not ids:
    print("SKIP")
    sys.exit(0)
try:
    st = json.load(open(state_path))
    recon = st.get("canonicalReconciliation", {}) or {}
    for key in ("customKeeps", "clientCustoms", "covered"):
        for c in recon.get(key, []) or []:
            ids.add(norm(c))
    for c in st.get("customKeeps", []) or []:
        ids.add(norm(c))
    for c in (recon.get("decisions", {}) or {}):
        ids.add(norm(c))
except Exception:
    pass
if norm(dept) in ids:
    print("OK")
else:
    print("NOMATCH")
    sys.stderr.write("known dept ids: " + ", ".join(sorted(x for x in ids if x)) + "\n")
PYVAL
)"
case "$DEPT_VALIDATION" in
  OK|SKIP) : ;;
  *)
    echo "ERROR: --dept '$DEPT' is not a known canonical or recorded-custom department id." >&2
    echo "       Recording a decline against an unknown/misspelled dept would silently vanish (over-build)." >&2
    echo "       Run: python3 $SCRIPT_DIR_RD/list-canonical-departments.py   to see valid ids." >&2
    exit 1 ;;
esac

# ── Opt-out loss warning gate (P2-05 step 1) ─────────────────────────────────
# For a floor-department decline, ECHO the loss_warning and REQUIRE --confirm-loss.
# The warning text is looked up from the single source (department-naming-map.json
# via department-loss-warning.py); a floor dept returns rc=0 + the text, a
# non-floor dept returns rc=3 + no text (no confirmation required).
LOSS_WARNING=""
if [ "$DECISION_LC" = "no" ]; then
  LOSS_READER="$SCRIPT_DIR_RD/department-loss-warning.py"
  if [ -f "$LOSS_READER" ]; then
    if LOSS_WARNING="$(python3 "$LOSS_READER" --dept "$DEPT" 2>/dev/null)" && [ -n "$LOSS_WARNING" ]; then
      # This is a FLOOR department — opt-out costs guaranteed functionality.
      if [ "$CONFIRM_LOSS" -ne 1 ]; then
        echo "─────────────────────────────────────────────────────────────" >&2
        echo "OPT-OUT WARNING for '$DEPT' — here's what you lose without it:" >&2
        echo "  $LOSS_WARNING" >&2
        echo "" >&2
        echo "This is a guaranteed floor department. Declining it is your call" >&2
        echo "(opt-out is sovereign), but it must be CONFIRMED. If the owner still" >&2
        echo "wants to skip it, re-run this command WITH --confirm-loss:" >&2
        echo "  record-dept-decision.sh --dept $DEPT --decision no --confirm-loss \\" >&2
        echo "    --source $SOURCE --by <ownerId> --session <sessionId>" >&2
        echo "The decline was NOT recorded (department stays in the floor until confirmed)." >&2
        echo "─────────────────────────────────────────────────────────────" >&2
        exit 2
      fi
      # Confirmed: surface the acknowledged warning for the operator log.
      echo "opt-out CONFIRMED for '$DEPT' (owner accepts losing: $LOSS_WARNING)"
    fi
  fi
fi

# ── Write the provenanced decision object atomically ─────────────────────────
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TMP="$STATE.tmp.$$"

# All dynamic values pass through jq --arg (never string interpolation into the
# filter), so a dept id / owner id / session id can never break or inject into the
# JSON. setpath-via-[$dept] handles an arbitrary dept key safely.
# For a confirmed floor-dept decline, also stamp the acknowledged loss warning
# (lossWarning + lossWarningAck=true) INTO the decision object. These are extra
# audit fields ALONGSIDE the four provenance fields canonical_decline.py requires
# (decision/source/decidedAt/decidedBy) — they never affect whether the decline
# is honored, they record that the owner was shown, and accepted, the loss.
# LOSS_ACK is "true" only when a floor warning was shown AND confirmed.
if [ -n "$LOSS_WARNING" ] && [ "$CONFIRM_LOSS" -eq 1 ] && [ "$DECISION_LC" = "no" ]; then
  LOSS_ACK="true"
else
  LOSS_ACK="false"
fi

jq \
  --arg dept "$DEPT" \
  --arg decision "$DECISION_LC" \
  --arg source "$SOURCE" \
  --arg by "$BY" \
  --arg session "$SESSION" \
  --arg now "$NOW" \
  --arg lossWarning "$LOSS_WARNING" \
  --argjson lossAck "$LOSS_ACK" '
    (if (.canonicalReconciliation | type) != "object" then .canonicalReconciliation = {} else . end)
    | (if (.canonicalReconciliation.decisions | type) != "object" then .canonicalReconciliation.decisions = {} else . end)
    | .canonicalReconciliation.decisions[$dept] = (
        {
          "decision":  $decision,
          "source":    $source,
          "decidedAt": $now,
          "decidedBy": $by,
          "sessionId": $session
        }
        + (if $lossAck then {"lossWarning": $lossWarning, "lossWarningAck": true} else {} end)
      )
  ' "$STATE" > "$TMP"
mv -f "$TMP" "$STATE"

echo "recorded decision: dept=$DEPT decision=$DECISION_LC source=$SOURCE by=$BY session=$SESSION at=$NOW -> $STATE"
