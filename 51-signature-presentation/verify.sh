#!/usr/bin/env bash
# ==============================================================================
# verify.sh — Skill 51 (Signature Presentation) self-verification gate.
# ------------------------------------------------------------------------------
# READ-ONLY and IDEMPOTENT. Runs the skill's three fail-closed provers in
# --self-test mode (built-in VALID + VIOLATION fixtures) AND the library-register
# --check sanity (both SP roles registered in role-library/_index.json). Exits
# NONZERO on ANY failure so it can gate a merge / CI / a post-install check.
#
#   VERIFY (this file) is the third leg of install / wire / verify:
#     - INSTALL: the main installer's install_skill_51_signature_presentation()
#       copies this skill into the box (skill 23 is the prerequisite engine).
#     - WIRE:    the SOP-SLIDE-06 lockstep already installed the three SP phases
#       (P-SP-INTAKE / P-SP-STRUCTURE / P-SP-P3-HYGIENE) + _chk_sp_* wrappers into
#       the department engine — there is NO separate wire.sh for this skill.
#     - VERIFY:  this script + the three provers.
#
# Usage:  bash 51-signature-presentation/verify.sh
# Exit:   0 = all checks passed;  nonzero = at least one check failed.
# ==============================================================================
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SP_SCRIPTS="$SKILL_DIR/scripts"
# The AI Workforce Blueprint (skill 23) engine is a sibling of this skill both in
# the repo and on an installed box; resolve the register script relative to here.
REGISTER="$SKILL_DIR/../23-ai-workforce-blueprint/scripts/register-library-additions.py"
PY="${PYTHON:-python3}"
# Fleet boxes are Macs; default the platform hint if the caller did not set one.
export OPENCLAW_PLATFORM="${OPENCLAW_PLATFORM:-mac}"

fails=0
run() {
    # run "<label>" <cmd...> — prints PASS/FAIL, increments $fails on nonzero.
    local label="$1"; shift
    local log
    log="$("$@" 2>&1)"; local rc=$?
    if [ "$rc" -eq 0 ]; then
        printf '  [PASS] %s\n' "$label"
    else
        printf '  [FAIL] %s (rc=%s)\n' "$label" "$rc"
        printf '%s\n' "$log" | sed 's/^/         /'
        fails=$((fails + 1))
    fi
}

echo "== Skill 51 (Signature Presentation) :: verify.sh =="

# 1) The five fail-closed SP provers — built-in self-test fixtures.
#    prove_sp_routing is the claim/routing gate (AF-SP-TYPE-UNDECLARED) that closes
#    the "omit deck_type to skip every SP gate" bypass.
#    A10 / T0-12: intake_trace_check is the intake-CONVERSATION gate (AF-INTAKE-BATCH).
#    It was self-tested only in a separate CI job while this script — the skill's own
#    verification leg — never exercised it, and it was wired as advisory. It is now a
#    required preflight in the engine (_chk_sp_intake_trace), so verify.sh must fail
#    when its fixtures do not hold.
for p in prove_sp_routing prove_sp_intake prove_sp_structure prove_sp_no_pitch intake_trace_check; do
    if [ -f "$SP_SCRIPTS/$p.py" ]; then
        run "$p.py --self-test" "$PY" "$SP_SCRIPTS/$p.py" --self-test
    else
        printf '  [FAIL] %s.py missing at %s\n' "$p" "$SP_SCRIPTS"
        fails=$((fails + 1))
    fi
done

# 1a) SACRED-STRUCTURE PIN (F05) — the golden sha256 set in
#     scripts/sacred-structure-hashes.json is the U98/D1 "structure preserved"
#     half of blend voice governance. Before this check, NOTHING in verify.sh or
#     --prove ever READ that pin: it was generated once and enforced only by a
#     unit test that CI may not run on every box. A silent edit to MASTERDOC.md,
#     a frame template, sp_structure.json, or sp-8-questions.json weakened every
#     prover downstream without any gate noticing. This runs the pin comparison
#     fail-closed: missing pin, missing file, or ANY hash drift = FAIL.
if [ -f "$SP_SCRIPTS/blend_voice_governance.py" ]; then
    run "sacred-structure pin vs scripts/sacred-structure-hashes.json" \
        "$PY" "$SP_SCRIPTS/blend_voice_governance.py" --prove-pin
else
    printf '  [FAIL] blend_voice_governance.py missing at %s — sacred-structure pin cannot be checked\n' "$SP_SCRIPTS"
    fails=$((fails + 1))
fi

# 1b) ENGINE WIRE-PRESENCE — Skill 51 has NO build path of its own; its gates only
#     bite when the Skill-23 presentations engine (build_deck.py) DEFINES + REGISTERS
#     the four _chk_sp_* wrappers (the claim gate + the three sacred gates). When the
#     engine is co-located, assert the wiring landed — FAIL (not warn) if it did not
#     (a stale skill-23 copy / a box where the SOP-SLIDE-06 lockstep never ran would
#     otherwise pass verify.sh while ZERO SP enforcement exists at runtime).
# The GOVERNED engine is the materialized department, not the skills template. Until
# U006 co-locates the entry script this file may run from either place, so resolve both
# and say which one is being verified. Measured 2026-07-25: the template tree carries
# manifest v25 (5 P-SP phases, 16 AF-SP codes) while the materialized department carried
# v18 (0 and 0) — and this script printed RESULT: PASS against the template.
OC_WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"
DEPT_DIR="$OC_WORKSPACE/departments/Presentations"
TEMPLATE_ENGINE="$SKILL_DIR/../23-ai-workforce-blueprint/templates/role-library/presentations/scripts/build_deck.py"
if [ -f "$DEPT_DIR/scripts/build_deck.py" ]; then
    ENGINE="$DEPT_DIR/scripts/build_deck.py"; ENGINE_SRC="materialized department"
else
    ENGINE="$TEMPLATE_ENGINE";               ENGINE_SRC="skills template (department not materialized)"
fi
echo "  engine under verification: $ENGINE  ($ENGINE_SRC)"
if [ -f "$ENGINE" ]; then
    run "engine wire-presence (P-SP gates wired into build_deck.py)" \
        "$PY" "$SP_SCRIPTS/prove_sp_routing.py" --check-wiring "$ENGINE"
else
    # SK2-08: FAIL (not WARN). Skill 51 has NO build path of its own — its gates
    # bite ONLY when the Skill-23 presentations engine (build_deck.py) is present
    # AND has the four _chk_sp_* wrappers wired. A missing engine means ZERO SP
    # enforcement at runtime, so a WARN-and-pass here would certify a box on which
    # the skill is completely unwired. skill 23 is the declared prerequisite engine.
    printf '  [FAIL] engine build_deck.py NOT co-located at %s — ' "$ENGINE"
    printf 'skill 23 (prerequisite presentations engine) is absent; SP enforcement is unwired.\n'
    fails=$((fails + 1))
fi

# 1c) LOCKSTEP CHECKER — the one thing that reads the MANIFEST the engine will
#     actually obey. Without it this script can certify a box whose manifest
#     declares none of the skill's phases. sync_check exits 0 in sync, 4 on drift,
#     2 when it cannot run.
SYNC="$(dirname "$ENGINE")/sync_check.py"
if [ -f "$SYNC" ]; then
    run "sync_check.py lockstep (engine tree: $ENGINE_SRC)" "$PY" "$SYNC"
else
    printf '  [FAIL] sync_check.py NOT found beside the engine at %s — ' "$(dirname "$ENGINE")"
    printf 'the lockstep state of the manifest this engine obeys cannot be established.\n'
    fails=$((fails + 1))
fi

# 1d) MANIFEST PHASE + AUTOFALL DECLARATION. Assert the five P-SP phases and at
#     least 16 AF-SP codes are declared in the manifest the engine will obey.
#     The 16 is a floor, measured at 16 in canonical v25 on 2026-07-25, written
#     as `< 16` so a future manifest that adds a seventeenth code does not break.
SP_PHASES="P-SP-CLAIM P-SP-INTAKE P-SP-INTAKE-TRACE P-SP-STRUCTURE P-SP-P3-HYGIENE"
_assert_sp_manifest() {
    ENGINE_DIR="$(dirname "$ENGINE")" SP_PHASES="$SP_PHASES" "$PY" - <<'PY'
import json, os, sys
from pathlib import Path
here = Path(os.environ["ENGINE_DIR"])
pres = here.parent
cand = [pres / "sops" / "PIPELINE-MANIFEST.json", pres / "PIPELINE-MANIFEST.json"]
root = here
for _ in range(12):
    p = root / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
    if p.is_file():
        cand.insert(0, p); break
    if root.parent == root: break
    root = root.parent
m = None
for c in cand:
    if c.is_file():
        m = json.loads(c.read_text()); src = c; break
if m is None:
    print("no PIPELINE-MANIFEST.json resolvable from", here, file=sys.stderr); sys.exit(2)
ids = {p["id"] for p in m["phases"]}
codes = {a["code"] for a in m["autofails"]}
want_phases = set(os.environ["SP_PHASES"].split())
sp_codes = {c for c in codes if c.startswith("AF-SP-")}
bad = 0
missing = sorted(want_phases - ids)
if missing:
    print(f"manifest {src} (version {m['manifest_version']}) declares "
          f"{len(want_phases & ids)}/{len(want_phases)} P-SP phases; missing: {missing}",
          file=sys.stderr); bad = 1
if len(sp_codes) < 16:
    print(f"manifest {src} (version {m['manifest_version']}) declares {len(sp_codes)}/16 "
          f"AF-SP-* autofail codes", file=sys.stderr); bad = 1
if bad: sys.exit(1)
print(f"manifest {src} version {m['manifest_version']}: "
      f"{len(want_phases)}/{len(want_phases)} P-SP phases, {len(sp_codes)} AF-SP-* codes")
PY
}
# run() swallows a passing check's stdout (verify.sh:33-45 prints $log only on failure),
# so emit the manifest summary unconditionally before grading it.
_assert_sp_manifest | sed 's/^/         /' || true
run "SP phases + AF-SP codes declared in the engine's manifest" _assert_sp_manifest

# 1e) PROVER RESOLVABILITY. Assert each of the five provers is resolvable the way
#     build_deck.py's _sp_prover resolves them: its own scripts dir OR the sibling
#     51-signature-presentation/scripts/. Do NOT assert they were copied.
for p in prove_sp_routing prove_sp_intake prove_sp_structure prove_sp_no_pitch intake_trace_check; do
    if [ -f "$(dirname "$ENGINE")/$p.py" ] || [ -f "$SP_SCRIPTS/$p.py" ]; then
        printf '  [PASS] %s.py resolvable by _sp_prover\n' "$p"
    else
        printf '  [FAIL] %s.py resolvable from NEITHER %s NOR %s — _sp_prover returns None and every SP gate is treated as BLOCKED\n' \
            "$p" "$(dirname "$ENGINE")" "$SP_SCRIPTS"
        fails=$((fails + 1))
    fi
done

# 2) library-register --check sanity: both SP roles are registered in _index.json.
if [ -f "$REGISTER" ]; then
    run "register-library-additions.py --check" "$PY" "$REGISTER" --check
else
    # SK2-08: FAIL (not WARN) — same rationale. The register script is part of the
    # Skill-23 engine; its absence means the SP roles were never registered, so the
    # skill cannot enforce anything.
    printf '  [FAIL] register-library-additions.py NOT found at %s — ' "$REGISTER"
    printf 'skill 23 engine is not co-located; SP roles are unregistered.\n'
    fails=$((fails + 1))
fi

# 3) FIX-14 regression guard — MC_API_TOKEN / MISSION_CONTROL_URL wired into the
#    agent runtime env (Error 8 / D-8). check_agent_env.py lives in the Skill-23
#    presentations engine's scripts dir (the same tree the canonical runner reads
#    `_agent_env` from). Two checks:
#      3a. Self-test (always, CI-safe): the probe's own fixture matrix must pass —
#          a regression in the PROBE itself is caught even when no real box env is
#          present.
#      3b. Live probe (only when a real engine scripts dir + a real box are
#          present): check_agent_env.py must exit 0. In CI there is no materialized
#          department and no gateway env, so the live probe is not run there — but
#          on a box the probe is the exact preflight the canonical runner enforces
#          at Phase-0, and verify.sh must hold it to the same bar.
FIX14_SCRIPTS="$(dirname "$ENGINE")"
if [ -f "$FIX14_SCRIPTS/check_agent_env.py" ]; then
    run "FIX-14 check_agent_env.py --self-test (probe fixture matrix)" \
        "$PY" "$FIX14_SCRIPTS/check_agent_env.py" --self-test
    # Live probe: only when this run has a real process env (not a bare CI
    # sandbox). The probe itself fails closed when the gateway env is absent, so a
    # box that dropped the token FAILS here — the exact 15-day regression.
    if [ -n "${MC_API_TOKEN:-}" ] || [ -f "$HOME/.openclaw/service-env/ai.openclaw.gateway.env" ]; then
        run "FIX-14 check_agent_env.py (MC_API_TOKEN + MISSION_CONTROL_URL in runtime env)" \
            "$PY" "$FIX14_SCRIPTS/check_agent_env.py"
    else
        printf '  [SKIP] FIX-14 live probe: no gateway env and no MC_API_TOKEN in this process env (CI sandbox); self-test above still ran\n'
    fi
else
    printf '  [FAIL] FIX-14 check_agent_env.py NOT found at %s — ' "$FIX14_SCRIPTS"
    printf 'the FIX-14 regression guard is unwired; a box whose token was dropped from the gateway env would silently 401 every CC write.\n'
    fails=$((fails + 1))
fi

# 4) FIX-19 regression guard — right-size tool results (D18). read_slice.py is
#    the engine's sliced-read path: a whole-file read of a 34-102KB SOP/role file
#    returns a tool result the harness truncates ([tool-result-truncation] fired
#    33x in the 2026-08-06 E2E). This check proves (a) the tool's own hermetic
#    fixture battery passes and (b) a real large SOP read through the sliced path
#    returns only the requested slice with a truncation counter of 0.
FIX19_SCRIPTS="$(dirname "$ENGINE")"
if [ -f "$FIX19_SCRIPTS/read_slice.py" ]; then
    run "FIX-19 read_slice.py --self-test (sliced-read fixture battery)" \
        "$PY" "$FIX19_SCRIPTS/read_slice.py" --self-test
    # Live sliced read of a known 34-102KB SOP through the sliced-read path —
    # QC gate for FIX-19: result returns only the requested slice; truncation
    # counter = 0. Hermetic (reads a tracked SOP file), CI-safe.
    run "FIX-19 sliced read of a large SOP returns only the slice (truncation_events=0)" \
        "$PY" -c "
import sys
sys.path.insert(0, '$FIX19_SCRIPTS')
import read_slice as rs
r = rs.read_slice('qc-specialist-presentations-sops.md', lines=(262, 270))
assert r['total_bytes'] > 100_000, r
assert r['returned_bytes'] < 4000, r
assert r['truncation_events'] == 0, r
assert r['slice']['lines'] == [262, 270], r
print('sliced read OK: returned %dB of %dB, truncation_events=%s' % (
    r['returned_bytes'], r['total_bytes'], r['truncation_events']))
"
else
    printf '  [FAIL] FIX-19 read_slice.py NOT found at %s — ' "$FIX19_SCRIPTS"
    printf 'the sliced-read path is unwired; an agent reading a whole 34-102KB SOP would truncate its tool result (D18).\n'
    fails=$((fails + 1))
fi


# 4) FIX-18 tool-schema hardening (Error 10 / D17) — normalized schema hint +
#    5-strike AF-TOOL-SCHEMA-LOOP loop alert. tool_schema_validator.py lives in
#    the Skill-23 presentations engine's scripts dir (the same tree the canonical
#    runner reads `_tool_schema` from). The self-test matrix is CI-safe: it proves
#    the string-args failure, the path/file trap, the normalized hint, and that 5
#    consecutive failures write the loop event — a regression in the VALIDATOR
#    itself is caught even when no run dir is present.
FIX18_SCRIPTS="$(dirname "$ENGINE")"
if [ -f "$FIX18_SCRIPTS/tool_schema_validator.py" ]; then
    run "FIX-18 tool_schema_validator.py --self-test (normalized hint + 5-strike event)" \
        "$PY" "$FIX18_SCRIPTS/tool_schema_validator.py" --self-test
else
    printf '  [FAIL] FIX-18 tool_schema_validator.py NOT found at %s — ' "$FIX18_SCRIPTS"
    printf 'the FIX-18 tool-schema hardening is unwired; a model that loops on malformed tool args would burn turns unchecked.\n'
    fails=$((fails + 1))
fi

echo "=================================================="
if [ "$fails" -eq 0 ]; then
    echo "RESULT: PASS — all Skill 51 self-verification checks green."
    exit 0
fi
echo "RESULT: FAIL — $fails check(s) failed."
exit 1
