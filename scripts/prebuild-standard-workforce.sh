#!/usr/bin/env bash
# prebuild-standard-workforce.sh — PHASE 2 orchestrator of the AI Workforce
# standard-first redesign (master plan 2026-08-04).
#
# THE STANDARD PREBUILD: materialize the FULL canonical department floor for a
# new client box at ONBOARDING (operator-triggered, BEFORE the interview), so
# the interview EDITS an already-built company instead of gathering a plan a
# later build creates. The engine is prebuild-standard-workforce.py in this
# directory; this wrapper exists so the operator-facing entry point matches
# the skill's .sh convention and so it can locate a python3 interpreter.
#
# CONTRACT (full detail in prebuild-standard-workforce.py's docstring):
#   1. CONSENT GATE — an explicit, provenanced OPERATOR consent record is
#      REQUIRED (ownerConsent shape: decision/source/decidedAt/decidedBy/
#      sessionId with source="operator-prebuild"). No record -> REFUSE,
#      fail-closed (exit 2). The prebuild runs before the owner has said
#      anything; the operator is the only honest consenting party.
#   2. interviewComplete already true -> REFUSE (exit 4).
#   3. buildType absent  -> consent authorizes setting "standard-first".
#      buildType legacy  -> REFUSE (exit 5) unless the consent decision is
#      the explicit "prebuild-and-convert-legacy".
#   4. Floor resolved LIVE from department-naming-map.json (never a hardcoded
#      count), materialized EXCLUSIVELY from templates/role-library/ via the
#      shipped materializers (materialize-missing-departments.py ->
#      floor-fill-driver.py -> create_role_workspaces).
#   5. Chosen artifact + Command Center seeding + board-join proof + state
#      write (departments[] status "prebuilt", agentRegistration "deferred").
#
# EXPLICITLY OUT (the engine never does these):
#   - agents.list registration (DEFERRED to interviewComplete for
#     confirmed-kept departments only — lazy registration).
#   - verticalPacks record (industry unknown pre-interview; the U107
#     derivation guard must see nothing declared).
#   - ANY LLM content authoring, ANY interviewProgress/interviewQc write,
#     ANY interviewComplete write (anti-fabrication).
#   - Skill-38 comms-automation handoff (suppressed on standardPrebuilt).
#   - ANY cron/hook/self-ping registration: ONE-SHOT by construction
#     (ZHC-BUILDOUT-EXPERIENCE.md:122-126: nothing that fires forever).
#
# NO-CO-MINGLING (binding — SKILL.md:41-43, NO-COMINGLING-RULE.md): this
# driver sources EXCLUSIVELY from templates/role-library/ via the shipped
# materializers. Copying from another client's tree is a hard violation; the
# engine never reads any other client path.
#
# USAGE
#   bash prebuild-standard-workforce.sh --operator-consent-file <consent.json> [engine args...]
#
#   DEFAULT IS DRY-RUN (the materializer's own dry-run): nothing mutates
#   until --apply is passed. Engine args:
#     --departments-dir <dir>    departments/ dir (SCRATCH canary runs MUST
#                                pass this + --build-state-file + --db — NEVER
#                                the operator's live tree / state / database)
#     --company-dir <dir>        ZHC company dir (default: parent of above)
#     --company-name <name>      company display name (CC seeding)
#     --company-slug <slug>      company slug (default: dir basename)
#     --build-state-file <json>  scratch build-state isolation
#     --db <mission-control.db>  explicit CC database for seeding + join proof
#     --apply                    actually mutate
#     --json                     machine-readable result
#
# EXIT CODES
#   0  success · 1  a step failed · 2  consent-gate refusal (fail-closed)
#   4  interviewComplete already true · 5  buildType lane refusal
#   7  board join verification failed (DRIFT / CANNOT-VOUCH / GATE-ERROR)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE="$SCRIPT_DIR/prebuild-standard-workforce.py"

if [ ! -f "$ENGINE" ]; then
  echo "[prebuild-standard-workforce] FATAL: engine not found at $ENGINE" >&2
  exit 1
fi

# Pick a python3: explicit override, then PATH python3, then PATH python.
PY="${WORKFORCE_PYTHON:-${PYTHON_BIN:-}}"
if [ -z "$PY" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PY="python3"
  elif command -v python >/dev/null 2>&1; then
    PY="python"
  else
    echo "[prebuild-standard-workforce] FATAL: no python3 interpreter found" >&2
    exit 1
  fi
fi

"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' || { echo "Python 3.9+ required" >&2; exit 1; }
export WORKFORCE_PYTHON="$PY"

# The engine is the single writer; this wrapper only validates entry and
# forwards. All consent/floor/materialization/state logic lives there so the
# .sh and the .py can never drift apart.
exec "$PY" "$ENGINE" "$@"
