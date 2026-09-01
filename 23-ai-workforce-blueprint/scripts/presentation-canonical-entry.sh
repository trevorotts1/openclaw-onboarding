#!/usr/bin/env bash
# presentation-canonical-entry.sh — SINGLE SOURCE (FIX 31, presentation rev2 waves).
# The runtime/deployed copy at 23-ai-workforce-blueprint/scripts/presentation-canonical-
# entry.sh — the path install.sh / update-skills.sh co-locate and SKILL.md names — is a
# BYTE-IDENTICAL GENERATED MIRROR of this file. Edit ONLY here, then re-cp the mirror;
# the two must never diverge (pre-FIX-31 the mirror carried only the legacy
# run_signature_deck.py dispatch, so following SKILL.md on a deployed box skipped the
# mechanical engine walk entirely). The department template materialization into
# $OC_WORKSPACE/departments/Presentations/scripts copies this same file.
#
# THE ONE SANCTIONED COMMAND TO BUILD A PRESENTATIONS DECK.
# ============================================================================
# Root-cause fix for the enforcement-surface gap (Fix 10 — entrypoint shell gate).
#
# The Presentations department's guardrails (kie.ai-only image path, 9,000-char
# prompt floor (PROMPT_CHAR_FLOOR=9000), the AF-OVERLAY-DELIVERED / kie-baked / image-QC battery, the
# GoHighLevel upload, the teleprompter bundle, the phase-attestation chain) all
# live INSIDE the canonical render path:
#
#       run_signature_deck.py  ->  build_deck.py
#
# Nothing at the runtime/agent layer used to force a deck THROUGH that path. A
# client agent could (and did) run hand-rolled `python3 working/phase4_driver.py`
# / `working/phase6_assemble.py` scripts that re-created the retired
# "skip kie.ai for hook slides + paste words on top in PowerPoint" pattern, and
# not a single guardrail fired because the thing that runs them was never run.
#
# This script closes that gap. It is the SINGLE governed entry point. Before it
# hands off to the canonical orchestrator it runs three fail-closed gates:
#
#   1. DEPS CHECK      — the runtime deps (soffice, pdftoppm, reportlab,
#                        python-pptx, pypdf) must be present, or the build refuses to
#                        start (exit 6, PRESENTATION_DEPS_MISSING). Mirrors the
#                        qc-completeness.sh dep gate so a deck cannot half-build.
#   2. BYPASS-SCAN     — refuse if any HAND-ROLLED renderer/assembler exists in
#                        the run directory: any non-canonical *.py that defines a
#                        slide canvas (Image.new for 2048x1152 — AF-LOCAL-CANVAS),
#                        a native PowerPoint text overlay (add_textbox /
#                        add_text_box), or a direct kie createTask outside
#                        build_deck.py (AF-CANONICAL-RENDER-BYPASS).
#   3. VERSION/HASH PIN— the deployed build_deck.py / run_signature_deck.py must
#                        be in lockstep with the SOP/manifest stack (sync_check.py,
#                        exit 4 on drift) and their content hash is computed and
#                        recorded. If a pin file is present the hash MUST match.
#
# A gate may be skipped ONLY by an explicit, LOGGED owner/founder approval token
# recorded in <run-dir>/working/checkpoints/process_manifest.json under
# "owner_skip_approval(s)" (approved:true + approved_by + reason, naming the exact
# gate code). Never silently; never by an agent's own choice.
#
# THE FORBIDDEN PATH:  python3 working/*.py   (the ungoverned, hand-rolled path)
# THE ONLY PATH:       bash presentation-canonical-entry.sh --run-dir ... \
#                           --slides slides.json --out out.pptx
#
# EXIT CODES
#   0  — gates passed; canonical orchestrator dispatched (its own exit is returned)
#   2  — usage error / canonical scripts not found
#   5  — BYPASS-SCAN tripped (hand-rolled renderer present, no owner skip)
#   6  — DEPS CHECK failed (PRESENTATION_DEPS_MISSING)
#   7  — VERSION/HASH PIN failed (renderer drift / hash mismatch, no owner skip)
#   8  — GHL MODULE CO-LOCATION failed (PRESENTATION_GHL_MODULE_MISSING, GATE 1b)
#   9  — ENGINE DISPATCH FAILED: the manifest-phase engine is installed but refused the
#        job (AF-DECK-TYPE-UNKNOWN / AF-ENGINE-NEW-FAILED / AF-ENGINE-COMPONENT-
#        MISSING). BLOCKING -- never a silent downgrade to run_signature_deck.py.
#        (See engine_fail() / fix/deck-type-routing-bypass.)
#   (3/4 propagate from run_signature_deck.py: 3 render fail, 4 kie balance abort)
# ============================================================================

set -uo pipefail

PROG="presentation-canonical-entry.sh"

die() { echo "FATAL [$PROG]: $*" >&2; exit 2; }
note() { echo "=== [$PROG] $* ==="; }

# fix/deck-type-routing-bypass: defined here (not down by the fallback's nonce
# handshake, where it used to live) because the engine-dispatch path ALSO
# calls this function, and it does so earlier in the script than the
# fallback's own handshake block. A function must be defined before its first
# call in bash -- it is NOT hoisted -- so leaving this definition below the
# engine path's call site meant `_mint_nonce: command not found` on EVERY
# successful engine dispatch (any presentation_type, not just the two the
# alias bug mis-routed), which then always died at "could not mint the
# front-door nonce" before a single phase ran. Reproduced against the real
# engine: state.json is created (job + manifest pinned) and the very
# next line fails this way. One definition, used by both the engine path and
# the legacy-fallback path below.
_mint_nonce() {
    if command -v python3 >/dev/null 2>&1; then
        python3 -c 'import secrets; print(secrets.token_hex(32))' 2>/dev/null && return 0
    fi
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex 32 2>/dev/null && return 0
    fi
    LC_ALL=C tr -dc 'a-f0-9' < /dev/urandom 2>/dev/null | head -c 64
    echo
}

usage() {
    cat >&2 <<EOF
$PROG — the ONE sanctioned command to build a Presentations deck.

USAGE:
  bash $PROG --run-dir DIR --slides slides.json --out out.pptx [options]

REQUIRED:
  --run-dir DIR       the deck run directory (contains working/)
  --slides FILE       slides.json (the deck spec)
  --out FILE          output .pptx path

OPTIONS:
  --phase ID          canonical phase to dispatch (default: P4-RENDER)
  --platform mac|vps  box-type override (default: auto-detect)
  --scripts-dir DIR   location of build_deck.py / run_signature_deck.py
                      (default: auto-detect; or set \$SCRIPTS_DIR)
  --intake-depth quick|in-depth
                      intake interview depth (FIX 30's standard_mode: the
                      deck-intake-questions.json order-8 question, stored as
                      pre_presentation_capture.STANDARD_MODE). Default: quick.
                      May also be set via PRESENTATION_INTAKE_DEPTH. This is
                      the INTERVIEW-DEPTH axis ONLY — it selects how much
                      optional detail the intake asks for and never changes
                      the 23-turn ceiling. It is deliberately distinct from
                      the run-mode flag, whose vocabulary is only
                      Ultra|Standard|Economy (FIX 11) — the two axes are
                      never interchangeable and never share a flag name.
  --plan              print the canonical phase plan and exit (gates still run)
  --adhoc             owner-authorized + logged escape (refused without the record)
  -h | --help         this help

There is NO other sanctioned way to build a deck. Running 'python3 working/*.py'
by hand is FORBIDDEN (the ungoverned path); skipping any gate requires a logged
owner approval token in working/checkpoints/process_manifest.json.
EOF
    exit 2
}

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------
RUN_DIR="" SLIDES="" OUT="" PHASE="P4-RENDER" PLATFORM="" SCRIPTS_DIR="${SCRIPTS_DIR:-}"
SCRIPTS_DIR_STATED="${SCRIPTS_DIR:+1}"  # set if the environment carried a value
PLAN=0 ADHOC=0 RESUME=0
# FIX 36(3) — intake-depth axis, deliberately SEPARATE from the run-mode axis.
# Run mode (FIX 38/FIX 11) is the --mode flag with the Ultra|Standard|Economy
# vocabulary. Intake depth (the interview_depth question's standard_mode
# subfield) is THIS flag: --intake-depth quick|in-depth (env
# PRESENTATION_INTAKE_DEPTH). The two vocabularies must never share a flag.
INTAKE_DEPTH="${PRESENTATION_INTAKE_DEPTH:-}"
INTAKE_DEPTH_STATED="${INTAKE_DEPTH:+1}"
while [ $# -gt 0 ]; do
    case "$1" in
        --run-dir)     RUN_DIR="${2:-}"; shift 2 ;;
        --slides)      SLIDES="${2:-}"; shift 2 ;;
        --out)         OUT="${2:-}"; shift 2 ;;
        --phase)       PHASE="${2:-}"; shift 2 ;;
        --platform)    PLATFORM="${2:-}"; shift 2 ;;
        --scripts-dir) SCRIPTS_DIR="${2:-}"; SCRIPTS_DIR_STATED=1; shift 2 ;;
        --intake-depth)
            INTAKE_DEPTH="${2:-}"; INTAKE_DEPTH_STATED=1; shift 2 ;;
        --plan)        PLAN=1; shift ;;
        --resume) RESUME=1; shift ;;
        --adhoc)       ADHOC=1; shift ;;
        -h|--help)     usage ;;
        *) die "unknown argument: $1 (run with --help)" ;;
    esac
done

# FIX 36(3) — validate the intake-depth vocabulary HERE, loudly, before any
# gate runs. Legal values are exactly quick|in-depth (case-insensitive). A
# run-mode value (Ultra/Standard/Economy) passed to this flag is the exact
# collision the spec forbids: refuse it with the message naming both axes.
case "$(printf '%s' "$INTAKE_DEPTH" | tr '[:upper:]' '[:lower:]')" in
    "")          INTAKE_DEPTH="QUICK" ;;
    quick)       INTAKE_DEPTH="QUICK" ;;
    in-depth)    INTAKE_DEPTH="IN-DEPTH" ;;
    in_depth)    INTAKE_DEPTH="IN-DEPTH" ;;   # tolerated shell-friendly spelling
    ultra|standard|economy)
        die "--intake-depth got run-mode vocabulary '$INTAKE_DEPTH'. The intake-depth \
axis (FIX 30's standard_mode) accepts ONLY quick|in-depth; the run-mode axis \
(FIX 11) is Ultra|Standard|Economy and is deliberately a DIFFERENT flag. The \
two vocabularies are never interchangeable."
        ;;
    *)
        die "--intake-depth: invalid value '$INTAKE_DEPTH'. Allowed: quick|in-depth \
(env PRESENTATION_INTAKE_DEPTH). Default: quick."
        ;;
esac
case "$INTAKE_DEPTH" in
    *d*|*D*) INTAKE_DEPTH="IN-DEPTH" ;;
esac

# ---------------------------------------------------------------------------
# FIX 36(3) — stamp_intake_depth: persist the resolved intake-depth into
# working/copy/intake.json's pre_presentation_capture.STANDARD_MODE (the exact
# storeTarget deck-intake-questions.json order-8 declares for FIX 30's
# standard_mode subfield). Read-modify-write so an answer captured during the
# interview is never clobbered; the CLI/env flag is an explicit override and
# wins, with the prior value recorded in the audit note. Write failure is
# logged but never blocks (depth tunes optional detail, not a quality gate).
stamp_intake_depth() {
    local depth="$1"
    command -v python3 >/dev/null 2>&1 || { note "intake-depth not stamped (no python3)"; return 0; }
    DEPTH="$depth" INTAKE_COPY="$RUN_DIR/working/copy/intake.json" python3 - <<'PY' || note "intake-depth stamp: non-fatal write failure (logged, build continues)"
import json, os, time
p = os.environ["INTAKE_COPY"]
depth = os.environ["DEPTH"]
obj = {}
try:
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        if isinstance(loaded, dict):
            obj = loaded
except Exception as exc:
    print(f"  [intake-depth] could not read {p} ({exc}) — starting a fresh capture block")
cap = obj.get("pre_presentation_capture")
if not isinstance(cap, dict):
    cap = {}
prior = cap.get("STANDARD_MODE")
cap["STANDARD_MODE"] = depth
obj["pre_presentation_capture"] = cap
try:
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
    os.replace(tmp, p)
    audit = obj.get("depth_audit")
    if not isinstance(audit, list):
        audit = []
    audit.append({"field": "pre_presentation_capture.STANDARD_MODE",
                  "value": depth, "prior": prior,
                  "source": "canonical-entry --intake-depth/PRESENTATION_INTAKE_DEPTH",
                  "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    obj["depth_audit"] = audit
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
    os.replace(tmp, p)
    print(f"  [intake-depth] pre_presentation_capture.STANDARD_MODE={depth}"
          f" (prior: {prior!r}) -> {p}")
except Exception as exc:
    print(f"  [intake-depth] stamp failed ({exc}) — non-fatal, build proceeds")
PY
}

[ -n "$RUN_DIR" ] || usage
[ -d "$RUN_DIR" ] || die "--run-dir not found: $RUN_DIR"
RUN_DIR="$(cd "$RUN_DIR" && pwd)"
stamp_intake_depth "$INTAKE_DEPTH"
if [ "$PLAN" -eq 0 ] && [ "$RESUME" -eq 0 ]; then
    [ -n "$SLIDES" ] || die "--slides is required (use --plan to inspect only)"
    [ -f "$SLIDES" ] || die "slides.json not found: $SLIDES"
    [ -n "$OUT" ] || die "--out is required to build a deck"
fi

# ---------------------------------------------------------------------------
# FIX-23(b) — CANONICAL-ENTRY ATTEMPT CAP (loop-breaker; Error 4/5 residual).
# The sanctioned door can legitimately fail transiently (a drifted stack, a
# missing GHL sibling). What must NEVER happen is the door failing and the
# agent "engineering around it" by writing a custom driver (the ungoverned
# path, AF-CANONICAL-RENDER-BYPASS) — the exact Error-5 behavior this loop
# exists to stop. Cap canonical-entry invocations per run dir at 3; the 4th
# invocation dies with an explicit message naming the sanctioned recovery path
# (open a maintenance ticket / apply the sync + GHL fix) instead of letting the
# agent improvise. --plan (read-only inspection) is EXEMPT: inspecting a run
# dir must never consume its entry budget.
# ---------------------------------------------------------------------------
if [ "$PLAN" -eq 0 ]; then
    _ATTEMPT_FILE="$RUN_DIR/working/checkpoints/.canonical-entry-attempts"
    mkdir -p "$(dirname "$_ATTEMPT_FILE")"
    _ATTEMPTS=$(( $(cat "$_ATTEMPT_FILE" 2>/dev/null | tr -d ' ') + 1 ))
    echo "$_ATTEMPTS" > "$_ATTEMPT_FILE"
    if [ "$_ATTEMPTS" -gt 3 ]; then
        die "canonical entry attempted $_ATTEMPTS times (>3). Do NOT write a custom driver. The sanctioned door is failing — open a maintenance ticket, apply the sync/ghl fix, then retry."
    fi
fi

# ---------------------------------------------------------------------------
# Locate the canonical render scripts (single source of truth).
# Resolution is EXPLICIT. There are exactly two accepted sources, in this order:
#   1. --scripts-dir DIR  (or $SCRIPTS_DIR)      — the caller states it
#   2. the materialized department's scripts dir — the ONE default
# Nothing else. The previous seven-candidate search accepted the skills-TEMPLATE copy
# (candidate 3, $SELF_DIR/../templates/role-library/presentations/scripts) whenever the
# script ran from the skills tree, and the materialized department path was not among the
# seven at all. Measured 2026-07-25: the same byte-identical build_deck.py runs under
# manifest v25 from the template dir (sync_check exit 0) and v18 from the department dir
# (sync_check exit 4, 79 drift items). A guess here silently invalidates GATE 1b, GATE 3
# and every downstream attestation.
# ---------------------------------------------------------------------------
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OC_WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"
DEPT_SCRIPTS_DEFAULT="$OC_WORKSPACE/departments/Presentations/scripts"

resolve_scripts_dir() {
    local c
    for c in "$SCRIPTS_DIR" "$DEPT_SCRIPTS_DEFAULT"; do
        [ -n "$c" ] || continue
        if [ -f "$c/build_deck.py" ] && [ -f "$c/run_signature_deck.py" ]; then
            (cd "$c" && pwd); return 0
        fi
        [ -n "$SCRIPTS_DIR" ] && [ "$c" = "$SCRIPTS_DIR" ] && return 2   # stated but wrong
    done
    return 1
}
SCRIPTS_DIR_RC=0
SCRIPTS_DIR="$(resolve_scripts_dir)" || SCRIPTS_DIR_RC=$?
if [ "$SCRIPTS_DIR_RC" -eq 2 ]; then
    die "--scripts-dir / $SCRIPTS_DIR was set but does not hold both build_deck.py and \
run_signature_deck.py. Refusing to autodetect — a wrong scripts directory silently \
invalidates GATE 1b, GATE 3 and every phase attestation. Point it at the materialized \
department: --scripts-dir $DEPT_SCRIPTS_DEFAULT"
elif [ "$SCRIPTS_DIR_RC" -ne 0 ]; then
    die "canonical scripts (build_deck.py + run_signature_deck.py) not found at the \
materialized department ($DEPT_SCRIPTS_DEFAULT). Refusing to autodetect. Either \
materialize the Presentations department, or state the directory explicitly: \
--scripts-dir DIR"
fi
BUILD_DECK="$SCRIPTS_DIR/build_deck.py"
RUNNER="$SCRIPTS_DIR/run_signature_deck.py"
if [ -n "${SCRIPTS_DIR_STATED:-}" ]; then
    note "canonical scripts: $SCRIPTS_DIR  (source: --scripts-dir / $SCRIPTS_DIR)"
else
    note "canonical scripts: $SCRIPTS_DIR  (source: materialized department default)"
fi

# Refuse the skills-template directory by name, even when it is stated.
case "$SCRIPTS_DIR" in
    */templates/role-library/presentations/scripts)
        die "refusing to run against the skills-TEMPLATE copy ($SCRIPTS_DIR). That tree \
carries its own manifest and is not the governed department. Use \
--scripts-dir $DEPT_SCRIPTS_DEFAULT" ;;
esac

PROC_MANIFEST="$RUN_DIR/working/checkpoints/process_manifest.json"

# ---------------------------------------------------------------------------
# owner_skip_approval — a gate is skippable ONLY by a logged owner token.
# Reads <run-dir>/working/checkpoints/process_manifest.json and returns 0 iff a
# well-formed approval (approved:true + approved_by + reason) names the gate.
# Accepts: top-level "owner_skip_approvals":[...], "owner_skip_approval":{...} or
# [...] (list), with each record carrying "gate"/"gate_code"/"code".
# ---------------------------------------------------------------------------
owner_skip_approved() {
    local gate="$1"
    [ -f "$PROC_MANIFEST" ] || return 1
    command -v python3 >/dev/null 2>&1 || return 1
    GATE="$gate" PM="$PROC_MANIFEST" python3 - <<'PY'
import json, os, sys
gate = os.environ["GATE"]
try:
    obj = json.load(open(os.environ["PM"]))
except Exception:
    sys.exit(1)
recs = []
for key in ("owner_skip_approvals", "owner_skip_approval"):
    v = obj.get(key) if isinstance(obj, dict) else None
    if isinstance(v, list):
        recs += v
    elif isinstance(v, dict):
        recs.append(v)
for r in recs:
    if not isinstance(r, dict):
        continue
    code = str(r.get("gate") or r.get("gate_code") or r.get("code") or "").strip()
    if code not in (gate, "*"):
        continue
    if (r.get("approved") is True or r.get("owner_approved") is True) \
       and str(r.get("approved_by", "")).strip() \
       and str(r.get("reason", "")).strip():
        sys.exit(0)
sys.exit(1)
PY
}

# ---------------------------------------------------------------------------
# _record_dep_gate_bypassed — append a dep_gate_bypassed audit record to
# working/checkpoints/process_manifest.json (FIX-PRES-01). Every honored skip of
# the runtime-deps gate — a test-context env bypass OR a logged owner token —
# leaves a durable, timestamped trail so a bypass is never silent. Never fatal:
# a manifest it cannot write is logged, not raised.
# ---------------------------------------------------------------------------
_record_dep_gate_bypassed() {
    local via="$1" reason="${2:-}"
    command -v python3 >/dev/null 2>&1 || return 0
    VIA="$via" REASON="$reason" PM="$PROC_MANIFEST" python3 - <<'PY' || true
import json, os, time
pm = os.environ["PM"]
rec = {
    "gate": "PRESENTATION_DEPS_MISSING",
    "via": os.environ.get("VIA", ""),
    "reason": os.environ.get("REASON", ""),
    "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
}
try:
    os.makedirs(os.path.dirname(pm), exist_ok=True)
    obj = {}
    if os.path.exists(pm):
        try:
            obj = json.load(open(pm))
            if not isinstance(obj, dict):
                obj = {"_prior": obj}
        except Exception:
            obj = {}
    lst = obj.get("dep_gate_bypassed")
    if not isinstance(lst, list):
        lst = []
    lst.append(rec)
    obj["dep_gate_bypassed"] = lst
    tmp = pm + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(obj, fh, indent=2)
    os.replace(tmp, pm)
    print(f"  [dep_gate_bypassed] recorded ({rec['via']}) in {pm}")
except Exception as exc:  # noqa: BLE001 — an audit-write failure never blocks the run
    print(f"  [dep_gate_bypassed] could not record ({exc}) — non-fatal")
PY
}

# A gate that tripped: honor a logged owner skip, else fail-closed with the code.
gate_fail() {
    local code="$1" exitcode="$2"; shift 2
    if owner_skip_approved "$code"; then
        echo "!! [$PROG] $code tripped but OWNER-APPROVED skip is logged in" >&2
        echo "!! process_manifest.json (owner_skip_approval). Proceeding under owner authority." >&2
        return 0
    fi
    echo >&2
    printf '!%.0s' {1..78} >&2; echo >&2
    echo "GATE FAILED [$code]: $*" >&2
    echo "This gate may be skipped ONLY by a logged owner approval token in" >&2
    echo "  $PROC_MANIFEST" >&2
    echo "  (owner_skip_approval: {gate:\"$code\", approved:true, approved_by, reason})." >&2
    printf '!%.0s' {1..78} >&2; echo >&2
    exit "$exitcode"
}

# trace_fail — the intake-TRACE evidence gate has NO owner override (FIX-3).
# The transcript is EVIDENCE that a real one-at-a-time conversation happened; a
# gate you can waive is a gate a hand-written ledger can skip. Distinguishes the
# trace gate from every waivable gate above.
trace_fail() {
    local code="$1" exitcode="$2"; shift 2
    echo >&2
    printf '!%.0s' {1..78} >&2; echo >&2
    echo "GATE FAILED [$code]: $*" >&2
    echo "This gate is the intake-CONVERSATION EVIDENCE gate and has NO owner override:" >&2
    echo "the intake transcript is proof the interview was CONDUCTED, not a skippable" >&2
    echo "permission. Run the real interview (deck-intake-driver.py --signature" >&2
    echo "  --next/--answer) so the driver writes the transcript itself." >&2
    printf '!%.0s' {1..78} >&2; echo >&2
    exit "$exitcode"
}

# ===========================================================================
# GATE 0 — INTAKE-LEDGER CHECK (fail-closed)
# The intake interview (deck-intake-driver.py) must be complete before any
# deck build runs. Read-only --plan inspection is exempt. The only waiver is
# a logged owner_skip_approval token for gate INTAKE-INTERVIEW.
#
# Formerly delegated to deck-build-guard.sh (retired U025). The guard's
# allow-list reduced to this one check on the canonical path; the rest of
# the guard was unreachable from the door. Relocated here so the door owns
# its own front-door precondition and the silent-skip `else` branch is gone.
# ===========================================================================
note "GATE 0 — INTAKE-LEDGER CHECK"

# owner_skip_intake — ported verbatim from deck-build-guard.sh:177-207.
# Returns 0 iff a logged owner approval waives the intake-interview gate
# (gate code INTAKE-INTERVIEW, AF-INTAKE-INTERVIEW, or *), read from
# process_manifest.json. Non-empty approved_by and reason are mandatory to
# prevent an agent from self-issuing a waiver.
owner_skip_intake() {
    local run_dir="$1"
    local pm="$run_dir/working/checkpoints/process_manifest.json"
    [ -f "$pm" ] || return 1
    command -v python3 >/dev/null 2>&1 || return 1
    PM="$pm" python3 - <<'PY'
import json, os, sys
try:
    obj = json.load(open(os.environ["PM"]))
except Exception:
    sys.exit(1)
recs = []
for key in ("owner_skip_approvals", "owner_skip_approval"):
    v = obj.get(key) if isinstance(obj, dict) else None
    if isinstance(v, list):
        recs += v
    elif isinstance(v, dict):
        recs.append(v)
WANT = {"INTAKE-INTERVIEW", "AF-INTAKE-INTERVIEW", "*"}
for r in recs:
    if not isinstance(r, dict):
        continue
    code = str(r.get("gate") or r.get("gate_code") or r.get("code") or r.get("af_code") or "").strip().upper()
    if code not in WANT:
        continue
    if (r.get("approved") is True or r.get("owner_approved") is True) \
       and str(r.get("approved_by", "")).strip() and str(r.get("reason", "")).strip():
        sys.exit(0)
sys.exit(1)
PY
}

# check_intake_ledger — ported from deck-build-guard.sh:213-256.
# Fail-closed on an absent or incomplete intake ledger. --plan is exempt
# (uses the entry script's own PLAN variable — strictly better than the
# guard's command-string pattern match). The only waiver is owner_skip_intake.
check_intake_ledger() {
    local run_dir="$1"
    [ -n "$run_dir" ] || return 0
    # --plan inspection is read-only; never blocked on the interview.
    # Uses the entry script's own PLAN variable rather than re-parsing
    # the command string. This catches --plan=1 and trailing-newline forms
    # that the guard's pattern match would miss.
    [ "$PLAN" -eq 1 ] && return 0
    _INTAKE_LEDGER="$run_dir/working/interview/intake_ledger.json"
    if [ ! -f "$_INTAKE_LEDGER" ]; then
        if owner_skip_intake "$run_dir"; then
            echo "!! [$PROG] GATE 0: intake ledger ABSENT but an OWNER-APPROVED skip is logged (INTAKE-INTERVIEW); proceeding under owner authority." >&2
            note "  GATE 0 PASSED (owner-approved skip)"
            return 0
        fi
        gate_fail "INTAKE-INTERVIEW" 5 "intake ledger missing ($_INTAKE_LEDGER) — run the Brainstorming Buddy interview (deck-intake-driver.py --next/--answer/--complete) before building. Owner override: log an owner_skip_approval for gate INTAKE-INTERVIEW (approved:true, approved_by, reason) in working/checkpoints/process_manifest.json."
    fi
    if command -v python3 >/dev/null 2>&1; then
        local complete
        complete="$(python3 -c "
import json, sys
try:
    d = json.load(open('$_INTAKE_LEDGER'))
    print('yes' if (d.get('status') == 'complete' or d.get('complete') is True or str(d.get('complete','')).strip().lower() == 'true') else '')
except Exception:
    print('')
" 2>/dev/null || true)"
        if [ -z "$complete" ]; then
            if owner_skip_intake "$run_dir"; then
                echo "!! [$PROG] GATE 0: intake ledger INCOMPLETE but an OWNER-APPROVED skip is logged (INTAKE-INTERVIEW); proceeding." >&2
                note "  GATE 0 PASSED (owner-approved skip)"
                return 0
            fi
            gate_fail "INTAKE-INTERVIEW" 5 "intake interview not complete ($_INTAKE_LEDGER status is not 'complete'). Finish the deck-intake interview with deck-intake-driver.py --complete before building. Owner override: owner_skip_approval gate INTAKE-INTERVIEW in working/checkpoints/process_manifest.json."
        fi
    else
        # python3 absent: parse crudely with grep
        if ! grep -qE '"status"[[:space:]]*:[[:space:]]*"complete"|"complete"[[:space:]]*:[[:space:]]*true' "$_INTAKE_LEDGER" 2>/dev/null; then
            if owner_skip_intake "$run_dir"; then
                echo "!! [$PROG] GATE 0: intake ledger incomplete but OWNER-APPROVED skip logged; proceeding." >&2
                note "  GATE 0 PASSED (owner-approved skip)"
                return 0
            fi
            gate_fail "INTAKE-INTERVIEW" 5 "intake interview not complete ($_INTAKE_LEDGER). Complete the deck-intake interview with deck-intake-driver.py --complete before building."
        fi
    fi
    note "  GATE 0 PASSED"
    return 0
}

check_intake_ledger "$RUN_DIR"

# ===========================================================================
# GATE 0b — INTAKE-TRACE CHECK (FIX-3: intake must be a REAL conversation)
# ---------------------------------------------------------------------------
# The intake LEDGER (GATE 0 above) proves the interview was COMPLETED. It does
# NOT prove the interview was CONDUCTED — a hand-written intake_ledger.json with
# invented answers (ERROR 3 of the 2026-08-06 E2E audit: the agent deleted the
# driver's ledger and hand-wrote it in python) satisfies GATE 0 with zero
# conversation. The TRANSCRIPT is the evidence that a real one-at-a-time
# conversation happened: deck-intake-driver.py --signature's turn-gate writes it
# mechanically as a SIGNED DRIVER ENVELOPE.
#
# This gate requires working/interview/intake_transcript.json to exist AND be
# non-trivial. It is NOT owner-skippable: the transcript is EVIDENCE, not a
# gate you can waive (FIX-PLAN-OPUS Error 3 fix 1: "only the ledger may have an
# owner waiver; the trace is evidence, not a gate you can waive"). A hand-written
# intake_ledger.json with no transcript FAILS the build.
#
# Fail-closed: absent file, empty file, or a sub-200-byte placeholder all fail
# with INTAKE-TRACE-MISSING. --plan (read-only inspection) is exempt exactly as
# GATE 0 is. A signature-presentation intake (intake.json deck_type ==
# signature_presentation) is additionally held to the signed driver-envelope
# requirement by the engine's P-SP-INTAKE-TRACE preflight (AF-INTAKE-BATCH).
# ===========================================================================
note "GATE 0b — INTAKE-TRACE CHECK (intake_transcript.json required; NO owner override)"
check_intake_trace() {
    local run_dir="$1"
    [ -n "$run_dir" ] || return 0
    [ "$PLAN" -eq 1 ] && return 0
    _INT_TRACE="$run_dir/working/interview/intake_transcript.json"
    if [ ! -f "$_INT_TRACE" ]; then
        trace_fail "INTAKE-TRACE-MISSING" 5 "intake_transcript.json missing ($_INT_TRACE) — the intake interview must be a REAL conversation (deck-intake-driver.py --signature --next/--answer). A hand-written intake_ledger.json is NOT an interview. This gate has NO owner override: the trace is evidence of the conversation, not a skippable gate."
    fi
    if command -v python3 >/dev/null 2>&1; then
        local _trace_bytes
        _trace_bytes="$(python3 -c "
import json, sys
p = '$run_dir/working/interview/intake_transcript.json'
try:
    with open(p, encoding='utf-8') as f:
        raw = f.read()
except OSError:
    print('0'); sys.exit(0)
print('%d' % len(raw.strip()))
" 2>/dev/null)"
        _trace_bytes="$(printf '%s' "$_trace_bytes" | tr -d ' ')"
        if [ -z "$_trace_bytes" ] || [ "$_trace_bytes" -lt 200 ]; then
            trace_fail "INTAKE-TRACE-MISSING" 5 "intake_transcript.json is ${_trace_bytes:-0} bytes — a real one-at-a-time intake conversation produces a multi-KB transcript. Run deck-intake-driver.py --signature --next/--answer/--complete and do NOT hand-write the transcript. No owner override for the trace."
        fi
    else
        # python3 absent: size-only fallback.
        local _sz
        _sz="$(wc -c < "$_INT_TRACE" 2>/dev/null | tr -d ' ')"
        [ -n "$_sz" ] && [ "$_sz" -ge 200 ] || trace_fail "INTAKE-TRACE-MISSING" 5 "intake_transcript.json is ${_sz:-0} bytes — a real interview produces a multi-KB transcript. No owner override for the trace."
    fi
    note "  GATE 0b PASSED (intake transcript present and non-trivial)"
    return 0
}

check_intake_trace "$RUN_DIR"

# ===========================================================================
# GATE 1 — DEPS CHECK (the four runtime deps; exit 6 PRESENTATION_DEPS_MISSING)
# ===========================================================================
note "GATE 1/3 — DEPS CHECK (soffice, pdftoppm, reportlab, python-pptx, pypdf)"
# FIX-PRES-01: the bare env short-circuit that used to sit at the TOP of this
# function (`QC_SKIP_PRESENTATION_DEPS=1 -> return 0`) was a live process-skip
# vector — any agent could export it, sail past GATE 1, burn the full Kie render
# budget, then die at PPTX/PDF. It is REMOVED. A LIVE run may skip this gate ONLY
# via a logged owner_skip_approval token (handled at the call site below). The env
# var is honored ONLY in a TEST context — a `.test-context` marker file the harness
# drops in the run dir — and every honored bypass is recorded as a
# dep_gate_bypassed entry in process_manifest.json so no skip is ever silent.
_TEST_CONTEXT_MARKER="$RUN_DIR/working/checkpoints/.test-context"
deps_check() {
    if [ "${QC_SKIP_PRESENTATION_DEPS:-0}" = "1" ]; then
        if [ -f "$_TEST_CONTEXT_MARKER" ]; then
            echo "  SKIP: QC_SKIP_PRESENTATION_DEPS=1 honored — test-context marker present ($_TEST_CONTEXT_MARKER)"
            _record_dep_gate_bypassed "env:QC_SKIP_PRESENTATION_DEPS" "test-context marker present"
            return 0
        fi
        echo "  NOTE: QC_SKIP_PRESENTATION_DEPS=1 IGNORED on a live run (no test-context marker)." >&2
        echo "        To skip a live run, log an owner_skip_approval token for PRESENTATION_DEPS_MISSING in" >&2
        echo "        $PROC_MANIFEST." >&2
    fi
    local missing=()
    command -v soffice  >/dev/null 2>&1 || missing+=("soffice (LibreOffice/libreoffice-impress)")
    command -v pdftoppm >/dev/null 2>&1 || missing+=("pdftoppm (poppler/poppler-utils)")
    if command -v python3 >/dev/null 2>&1; then
        python3 -c "import reportlab, pptx" >/dev/null 2>&1 \
            || missing+=("python(reportlab+python-pptx)")
        # Feature L2-D (P8.25-WORKBOOK): pypdf is a REAL runtime dep of the workbook
        # phase (workbook_builder.py reads the assembled PDF back with pypdf to prove
        # the AcroForm fields + /NeedAppearances survived before it may upload). It is
        # NOT gated by the pdf_export/guide phase's own checks, so it must be gated
        # here so a box without pypdf fails the dep gate BEFORE the workbook phase runs
        # (owner-token skippable via PRESENTATION_DEPS_MISSING exactly like the other
        # deps).
        python3 -c "import pypdf" >/dev/null 2>&1 \
            || missing+=("python(pypdf)")
    else
        missing+=("python3")
    fi
    # Feature L2-G (P9.6-WEBINAR-VIDEO): ffmpeg is a REAL runtime dep of the webinar
    # phase (build_webinar_video.py -> webinar_ffmpeg.py renders the Ken Burns + xfade
    # slideshow + muxes the audio). It is NOT gated by the audio phase's own check, so
    # it must be gated here so a box without ffmpeg fails the dep gate BEFORE the
    # webinar phase runs (owner-token skippable via PRESENTATION_DEPS_MISSING exactly
    # like the other deps).
    command -v ffmpeg >/dev/null 2>&1 || missing+=("ffmpeg (webinar video render; brew install ffmpeg)")
    command -v ffprobe >/dev/null 2>&1 || missing+=("ffprobe (webinar video probe; part of ffmpeg)")
    if [ "${#missing[@]}" -gt 0 ]; then
        # FIX-PRES-09(iv): event-shaped reassert. On a VPS the runtime deps do not
        # survive a Docker force-recreate; rather than lean solely on a periodic
        # cron, self-heal HERE on the GATE-1 failure path — run the idempotent
        # reassert script ONCE, then re-check, before failing the run.
        local _reassert="/data/.openclaw/scripts/reassert-presentation-deps.sh"
        if [ "${OPENCLAW_PLATFORM:-}" = "vps" ] && [ -x "$_reassert" ] \
           && [ "${_DEPS_REASSERT_TRIED:-0}" != "1" ]; then
            _DEPS_REASSERT_TRIED=1
            echo "  GATE-1 deps missing on VPS — running event-shaped reassert once ($_reassert)…" >&2
            bash "$_reassert" >&2 2>&1 || true
            deps_check
            return $?
        fi
        echo "PRESENTATION_DEPS_MISSING: ${missing[*]}" >&2
        return 6
    fi
    echo "  OK: all runtime deps present"
    return 0
}
deps_check || {
    rc=$?
    if owner_skip_approved "PRESENTATION_DEPS_MISSING"; then
        echo "!! [$PROG] deps missing but OWNER-APPROVED skip logged; proceeding." >&2
        _record_dep_gate_bypassed "owner_skip_approval:PRESENTATION_DEPS_MISSING" \
            "owner-approved skip token honored at GATE 1"
    else
        exit "$rc"
    fi
}

# ===========================================================================
# GATE 1b — SKILL-48 GHL MODULE CO-LOCATION (FIX-PRES-03 / FIX-23(d))
# ghl_media.py re-exports Skill-48 helpers; delivery_gate.py requires the
# resulting pptx_ghl_media_id. If the module is absent, a deck renders on PAID
# Kie credits and then dies at delivery. Assert importability HERE, before any
# render spend. Owner-token skippable (PRESENTATION_GHL_MODULE_MISSING).
#
# FIX-23(d) — import with the RENDER interpreter and surface the REAL import
# error. The pre-fix check swallowed stderr, so a box where ghl_media.py was
# present but its Skill-48 dependency was missing failed with a generic
# "not importable" — the agent could not tell it was a co-location problem and
# self-engineered around the door. Now:
#   * the import runs under the SAME interpreter that will run the renderer
#     (python3, with $SCRIPTS_DIR on PYTHONPATH — identical to build_deck),
#   * the real import error is printed so a Skill-48 co-location gap is
#     diagnosable ("canonical ghl_media.py not found ... install the
#     Skill-48 sibling"),
#   * ghl_media.py itself now also resolves the sibling from the OpenClaw
#     skills tree (~/.openclaw/skills or /data/.openclaw/skills) and a
#     co-located _skill48_ghl_media.py copy, so a materialized department
#     works without a manual symlink.
# ===========================================================================
note "GATE 1b/3 — SKILL-48 GHL MODULE CO-LOCATION (ghl_media importable)"
ghl_module_check() {
    command -v python3 >/dev/null 2>&1 || {
        echo "  (python3 absent; GHL module check skipped)"; return 0; }
    local _ghl_err
    _ghl_err="$(PYTHONPATH="$SCRIPTS_DIR${PYTHONPATH:+:$PYTHONPATH}" \
        python3 -c "import ghl_media" 2>&1)" && {
        echo "  OK: ghl_media importable from $SCRIPTS_DIR"
        return 0
    }
    # Import failed — show the REAL error (usually ghl_media's own
    # FileNotFoundError naming the missing Skill-48 sibling).
    echo "PRESENTATION_GHL_MODULE_MISSING: ghl_media import failed under the render interpreter:" >&2
    printf '%s\n' "$_ghl_err" | sed 's/^/    import> /' >&2
    if [ -f "$SCRIPTS_DIR/ghl_media.py" ]; then
        echo "    ghl_media.py is present at $SCRIPTS_DIR but not importable — its Skill-48 dependency co-location is missing." >&2
        echo "    Fix: install the Skill-48 sibling (48-facebook-ad-generator) so its tools/ghl_media.py resolves," >&2
        echo "    or run the materializer to co-locate _skill48_ghl_media.py next to this module." >&2
    else
        echo "    ghl_media.py not found at $SCRIPTS_DIR (Skill-48 co-location missing)." >&2
    fi
    return 8
}
ghl_module_check || {
    rc=$?
    if owner_skip_approved "PRESENTATION_GHL_MODULE_MISSING"; then
        echo "!! [$PROG] ghl_media missing but OWNER-APPROVED skip logged; proceeding." >&2
    else
        exit "$rc"
    fi
}

# ===========================================================================
# GATE 2 — BYPASS-SCAN (refuse hand-rolled renderers in the run directory)
# AF-LOCAL-CANVAS / AF-CANONICAL-RENDER-BYPASS
# ===========================================================================
note "GATE 2/3 — BYPASS-SCAN (hand-rolled renderer detection in $RUN_DIR)"
bypass_scan() {
    command -v python3 >/dev/null 2>&1 || { echo "  (python3 absent; scan skipped)"; return 0; }
    RUN_DIR="$RUN_DIR" SCRIPTS_DIR="$SCRIPTS_DIR" python3 - <<'PY'
import os, re, sys
run_dir = os.path.realpath(os.environ["RUN_DIR"])
scripts_dir = os.path.realpath(os.environ["SCRIPTS_DIR"])
CANON = {"build_deck.py", "run_signature_deck.py", "build_teleprompter.py",
         "kie_generate.py", "presentation-canonical-entry.sh",
         "build_webinar_video.py", "workbook_builder.py"}

# Slide canvas at the 16:9 2K deck dimensions: Image.new(...2048...1152...)
re_canvas = re.compile(r"Image\.new\s*\([^)]*\b2048\b[^)]*\b1152\b", re.S)
re_canvas2 = re.compile(r"Image\.new\s*\([^)]*\b1152\b[^)]*\b2048\b", re.S)
# Native PowerPoint on-slide text overlay
re_textbox = re.compile(r"\badd_text(?:_)?box\s*\(")
# Direct kie createTask outside build_deck.py
re_createtask = re.compile(r"createTask|api\.kie\.ai/api/v1/[A-Za-z0-9/_-]*", re.I)

findings = []
for root, dirs, files in os.walk(run_dir):
    # never scan inside the canonical scripts dir if it nests under run_dir
    if os.path.realpath(root) == scripts_dir:
        dirs[:] = []
        continue
    for fn in files:
        if not fn.endswith(".py"):
            continue
        if fn in CANON:
            continue
        path = os.path.join(root, fn)
        if os.path.realpath(path).startswith(scripts_dir + os.sep):
            continue
        try:
            src = open(path, "r", errors="replace").read()
        except Exception:
            continue
        rel = os.path.relpath(path, run_dir)
        if re_canvas.search(src) or re_canvas2.search(src):
            findings.append(("AF-LOCAL-CANVAS", rel,
                             "defines a 2048x1152 slide canvas via Image.new "
                             "(local Pillow render bypassing kie.ai)"))
        if re_textbox.search(src):
            findings.append(("AF-CANONICAL-RENDER-BYPASS", rel,
                             "calls add_textbox/add_text_box (native on-slide text "
                             "overlay — only the canonical assembler may emit pictures)"))
        if re_createtask.search(src):
            findings.append(("AF-CANONICAL-RENDER-BYPASS", rel,
                             "issues a direct kie createTask outside build_deck.py"))

if not findings:
    print("  OK: no hand-rolled renderer/assembler found in the run directory")
    sys.exit(0)

print("  HAND-ROLLED RENDERER(S) DETECTED:", file=sys.stderr)
codes = set()
for code, rel, why in findings:
    print(f"    [{code}] {rel}: {why}", file=sys.stderr)
    codes.add(code)
# exit 10 + signal which family tripped (caller maps to AF code + owner-skip)
# encode the dominant code on the LAST line for the bash caller to read
print("BYPASS_CODES=" + ",".join(sorted(codes)), file=sys.stderr)
sys.exit(5)
PY
}
SCAN_OUT="$(bypass_scan 2>&1)"; SCAN_RC=$?
printf '%s\n' "$SCAN_OUT"
if [ "$SCAN_RC" -eq 5 ]; then
    # Determine which AF codes tripped and require a logged owner skip for EACH.
    CODES="$(printf '%s\n' "$SCAN_OUT" | sed -n 's/^BYPASS_CODES=//p' | tr ',' ' ')"
    [ -n "$CODES" ] || CODES="AF-CANONICAL-RENDER-BYPASS"
    for c in $CODES; do
        if ! owner_skip_approved "$c"; then
            gate_fail "$c" 5 "a hand-rolled renderer/assembler is present in $RUN_DIR. \
The ONLY sanctioned render path is build_deck.py via run_signature_deck.py. Delete the \
hand-rolled script(s) above and re-run the canonical command."
        fi
    done
    echo "!! [$PROG] bypass-scan findings are all OWNER-APPROVED-skipped; proceeding." >&2
fi

# ===========================================================================
# GATE 3 — VERSION/HASH PIN (renderer lockstep + content hash)
# ===========================================================================
note "GATE 3/3 — VERSION/HASH PIN (renderer lockstep + content hash)"
version_hash_pin() {
    # (a) Lockstep: the Python renderer must not have drifted from the SOP/manifest
    #     stack. sync_check.py exits 0 in sync, 4 on drift.
    #
    # FIX-23(a) — DRIFT CLASSIFICATION (Error 5 root cause). GATE 3 used to lump
    # every sync_check drift item into ONE fatal AF-CANONICAL-RENDER-BYPASS. That
    # bricked the sanctioned door on library-only maintenance debt: the box's role
    # roster (A5 undeclared roles / A6 owning_role -> missing .md) drifted and the
    # agent could not render through the governed path, so it engineered around the
    # door with a custom driver. Now:
    #   * A5/A6 drift = SOP-library maintenance debt. It does NOT change render
    #     correctness (phase order, produces_artifact, preflight wiring all live in
    #     the render-path classes). GATE 3 PROCEEDS when the ONLY drift is A5/A6,
    #     and writes a sync_drift_deferred CC event so the debt is surfaced, never
    #     hidden (the drift is still reported in the log + event).
    #   * Any OTHER drift class (A1-A4/A7/A8, B*, C*, D*, E*, V*) is render-path:
    #     it means the actual renderer has drifted from the manifest/ruleset and
    #     the door FAILS CLOSED exactly as before.
    if [ -f "$SCRIPTS_DIR/sync_check.py" ] && command -v python3 >/dev/null 2>&1; then
        if python3 "$SCRIPTS_DIR/sync_check.py" --json >/tmp/_pce_sync.$$ 2>&1; then
            echo "  OK: sync_check.py — renderer in lockstep with the SOP/manifest stack"
            rm -f /tmp/_pce_sync.$$
        else
            # sync_check exited 4 (drift). Classify: only A5/A6 (library-only) -> proceed evented.
            # NOTE: the temp path is passed via env var because the heredoc is
            # QUOTED ('PY') and bash does not expand $$ inside it.
            if _PCE_SYNC_TMP="/tmp/_pce_sync.$$" python3 - <<'PY'
import json, os, sys
try:
    d = json.load(open(os.environ["_PCE_SYNC_TMP"]))
except Exception:
    sys.exit(1)  # unreadable/parse error -> treat as fatal (fail closed)
drift = d.get("drift", [])
# A5/A6 are library-only (role roster / owning_role mapping) — NON-blocking.
# sync_check emits class "A5/A6" for library-only, "render_path" for everything
# else. Block iff ANY item is NOT library-only.
blocking = [x for x in drift if x.get("class") != "A5/A6"]
if blocking:
    sys.exit(1)  # real render-path drift -> the gate fails below
sys.exit(0)      # library-only drift -> proceed, evented
PY
            then
                sed 's/^/    sync_check> /' /tmp/_pce_sync.$$ >&2 || true
                echo "  OK: render-path lockstep clean (library-only A5/A6 drift deferred, logged)"
                python3 - <<'PY' || true
# write a CC event so the drift debt is surfaced, not hidden
import json, os, urllib.request
try:
    from cc_board import cc_post
    cc_post("/api/events", {"type": "sync_drift_deferred",
       "message": "sync_check library-only drift (A5/A6) deferred on canonical render", "severity": "warn"})
except Exception:
    pass
PY
                rm -f /tmp/_pce_sync.$$
            else
                sed 's/^/    sync_check> /' /tmp/_pce_sync.$$ >&2 || true
                rm -f /tmp/_pce_sync.$$
                return 4
            fi
        fi
    else
        echo "  (sync_check.py absent; lockstep check skipped)"
    fi

    # (b) Content hash of the canonical renderer pair. If a pin file exists next to
    #     the scripts (CANONICAL-RENDERER-PIN.sha256, owned by the fleet sync), the
    #     deployed hash MUST match it. Otherwise the computed hash is recorded.
    local computed=""
    if command -v sha256sum >/dev/null 2>&1; then
        computed="$(cat "$BUILD_DECK" "$RUNNER" | sha256sum | awk '{print $1}')"
    elif command -v shasum >/dev/null 2>&1; then
        computed="$(cat "$BUILD_DECK" "$RUNNER" | shasum -a 256 | awk '{print $1}')"
    else
        echo "  (no sha256 tool; hash pin skipped)"
        return 0
    fi
    echo "  renderer hash (sha256 of build_deck.py+run_signature_deck.py): $computed"
    local pin="$SCRIPTS_DIR/CANONICAL-RENDERER-PIN.sha256"
    if [ -f "$pin" ]; then
        local expected
        expected="$(tr -d ' \t\n' < "$pin")"
        if [ -n "$expected" ] && [ "$expected" != "$computed" ]; then
            echo "  PIN MISMATCH: deployed renderer hash != pinned head" >&2
            echo "    expected: $expected" >&2
            echo "    computed: $computed" >&2
            return 7
        fi
        echo "  OK: renderer hash matches the pinned head ($pin)"
    else
        echo "  (no CANONICAL-RENDERER-PIN.sha256; hash recorded, not enforced)"
    fi
    return 0
}
version_hash_pin; VHP_RC=$?
if [ "$VHP_RC" -ne 0 ]; then
    if [ "$VHP_RC" -eq 4 ]; then
        gate_fail "AF-CANONICAL-RENDER-BYPASS" 7 "renderer/SOP lockstep drift (sync_check.py exit 4): \
the deployed build_deck.py has drifted from the SOP/manifest stack. Re-sync to the pinned \
governed version before building."
    else
        gate_fail "AF-CANONICAL-RENDER-BYPASS" 7 "renderer hash does not match the pinned governed \
head. Re-sync the canonical build_deck.py / run_signature_deck.py to the fleet-pinned version."
    fi
fi

# ===========================================================================
# WORK-ITEM-02: All gates passed -- dispatch through the PRESENTATION ENGINE.
#
# BEFORE (the old path): hand off to run_signature_deck.py, which dispatched only
#   2 of ~20+ phases (P4-RENDER and P9.5-NOTES-SYNC). Every other phase was an
#   agent invitation with no mechanical executor.
#
# AFTER (this change): dispatch through presentation_job.py (the engine), which
#   walks ALL manifest phases in order (count derived from the canonical
#   PIPELINE-MANIFEST.json), refuses to skip, runs 6 fail-closed
#   gates in close(), and posts progress to the CC board at every phase boundary.
#   The engine has 18 modules + 552 passing tests and was built between
#   2026-07-25 and 2026-08-07 -- it was simply never wired until now.
#
# fix/deck-type-routing-bypass: this block used to build the engine's --new
# intake JSON with its OWN inline copy of the deck-type "legal" set -- one
# that accidentally listed "standard" and "signature_presentation" (the two
# values that need translating) as members of ITS OWN legal set, so the
# alias remap that would have fixed them never ran. That mismatched intake
# then made the engine's REAL (narrower) check reject it, `--new` failed,
# and this script fell through to the FALLBACK below WHILE REPORTING SUCCESS
# (2 legacy phases only, close() never called, all 6 fail-closed gates skipped).
# The same block also string-interpolated ledger-controlled values (client
# name) directly into python SOURCE text -- a client name containing a
# single quote broke the literal, the SyntaxError was swallowed by
# `2>/dev/null || true`, and the door fell through the exact same way. Both
# holes are closed by replacing this block with ONE call to the shared
# resolver (presentation_job/resolve_intake.py), which shares its deck-type
# vocabulary with the engine, the poll, and the launcher (see vocab.py) and
# never formats untrusted content into source -- ledger values are read with
# json.load() and written with json.dump(), full stop.
#
# The old run_signature_deck.py call is retained as FALLBACK -- but ONLY for
# when the engine component itself is missing from this box (ENGINE_ENTRY
# does not exist). That is an "not installed here" case and announces itself
# loudly + records that it ran (see the `else` branch below). If the engine
# IS present and refuses the job for ANY reason, that is now a blocking
# failure (engine_fail, exit 9) -- it NEVER falls through to the legacy
# runner while reporting success. A downgrade the operator cannot see is
# the disease this rewrite exists to cure.
# ===========================================================================
ENGINE_ENTRY="$SCRIPTS_DIR/presentation_job.py"
RESOLVE_INTAKE="$SCRIPTS_DIR/presentation_job/resolve_intake.py"
INTAKE_LEDGER="$RUN_DIR/working/interview/intake_ledger.json"

# engine_fail: the engine is PRESENT but refused the job. Loud, blocking,
# distinct from gate_fail() above (no owner-skip -- there is no rational
# "skip" for a nonsensical deck type or a broken engine job; the fix is to
# correct the intake and re-run, not to route around this check).
engine_fail() {
    local code="$1" exitcode="$2"; shift 2
    echo >&2
    printf '!%.0s' {1..78} >&2; echo >&2
    echo "ENGINE DISPATCH FAILED [$code]: $*" >&2
    echo "presentation_job.py (the manifest-phase engine) is installed on this box but" >&2
    echo "refused this job. This is a BLOCKING failure -- it does NOT fall back to" >&2
    echo "the legacy runner, and it is never reported as success." >&2
    printf '!%.0s' {1..78} >&2; echo >&2
    exit "$exitcode"
}

# ---------------------------------------------------------------------------
# FIX 36(5) — the displayed phase count is DERIVED from the canonical
# PIPELINE-MANIFEST.json, never a stale hardcoded number. Resolution mirrors
# manifest_source.resolve_manifest(): the installed dept copy (sops/ with
# MANIFEST-SOURCE.txt), the cluster copy walked up from SCRIPTS_DIR, then the
# installed sops/ file itself. A missing/unparseable manifest prints '?'
# (loud absence, not a fabricated number).
# ---------------------------------------------------------------------------
_PHASE_COUNT=""
for _mc in "$SCRIPTS_DIR/../sops/PIPELINE-MANIFEST.json" \
           "$(cd "$SCRIPTS_DIR" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null)/universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json"; do
    [ -n "$_mc" ] || continue
    [ -f "$_mc" ] || continue
    _PHASE_COUNT="$(python3 -c "
import json
m = json.load(open('$_mc'))
print(len(m.get('phases', [])))
" 2>/dev/null)" && [ -n "$_PHASE_COUNT" ] && break
    _PHASE_COUNT=""
done
if [ -z "$_PHASE_COUNT" ]; then
    # FIX 36(5): last resort — the canonical resolver (manifest_source.py),
    # same resolution order sync_check documents (sops/ sibling first, then
    # the cluster copy), so a partial install never shows a stale count.
    _PHASE_COUNT="$(python3 - "$SCRIPTS_DIR" <<'PY' 2>/dev/null || true
import sys
from pathlib import Path
here = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(here))
try:
    from manifest_source import resolve_manifest
    print(resolve_manifest(here)[0])
except Exception:
    pass
PY
)"
    [ -n "$_PHASE_COUNT" ] && _PHASE_COUNT="$(python3 -c "
import json
m = json.load(open('$_PHASE_COUNT'))
print(len(m.get('phases', [])))
" 2>/dev/null)"
fi
_PHASE_COUNT="${_PHASE_COUNT:-?}"

if [ "$PLAN" -eq 1 ]; then
    # --plan is read-only inspection: show what WOULD run, don't launch.
    note "ALL GATES PASSED -- plan mode: engine WOULD be dispatched"
    # FIX 36(5): the phase count comes from the canonical manifest, never a
    # hardcoded number.
    echo "  Manifest phases: $_PHASE_COUNT"
    if [ "$RESUME" -eq 0 ]; then
    echo "  Would run:  python3 $ENGINE_ENTRY --new --run-dir $RUN_DIR"
    fi
    echo "  Then:       python3 $ENGINE_ENTRY --run --run-dir $RUN_DIR"
    echo "  All phases walked mechanically. 6 fail-closed gates at close()."
    exit 0
fi

if [ -f "$ENGINE_ENTRY" ] && command -v python3 >/dev/null 2>&1; then
    note "ALL GATES PASSED -- dispatching the presentation engine (all $_PHASE_COUNT manifest phases, mechanical)"

    # Step 1: Resolve the intake ledger into the engine's --new intake JSON
    # through the ONE shared resolver (single-sourced deck-type vocabulary,
    # zero string-interpolation of ledger content into python source -- see
    # presentation_job/resolve_intake.py and vocab.py). An unresolvable
    # deck type is a loud, blocking failure -- never caught and defaulted.
    _ENGINE_INTAKE_TMP="$RUN_DIR/working/checkpoints/.engine-intake.json"
    mkdir -p "$(dirname "$_ENGINE_INTAKE_TMP")"
    if [ ! -f "$RESOLVE_INTAKE" ]; then
        engine_fail "AF-ENGINE-COMPONENT-MISSING" 9 "presentation_job.py is present at \
$ENGINE_ENTRY but its resolver $RESOLVE_INTAKE is not -- this is a broken/partial \
engine install, not a genuinely absent one, so this does NOT fall back to \
run_signature_deck.py. Re-sync the Presentations department."
    fi
    _RESOLVE_DEPTH_ARGS=""
    if [ -n "$INTAKE_DEPTH" ]; then
        _RESOLVE_DEPTH_ARGS="--intake-depth $INTAKE_DEPTH"
    fi
    _RESOLVE_OUT="$(python3 "$RESOLVE_INTAKE" --ledger "$INTAKE_LEDGER" \
        --out "$_ENGINE_INTAKE_TMP" --source canonical-entry $_RESOLVE_DEPTH_ARGS 2>&1)"
    _RESOLVE_RC=$?
    if [ "$_RESOLVE_RC" -eq 5 ]; then
        engine_fail "AF-INTAKE-DEPTH-INVALID" 9 "$_RESOLVE_OUT"
    fi
    if [ "$_RESOLVE_RC" -ne 0 ]; then
        engine_fail "AF-DECK-TYPE-UNKNOWN" 9 "$INTAKE_LEDGER did not resolve to a legal \
presentation_type: $_RESOLVE_OUT"
    fi
    note "$_RESOLVE_OUT"

    # Step 2: Create the engine job (state.json).
    # This is idempotent -- if state.json already exists, the engine refuses to overwrite.
    _CREATE_OUT="$(python3 "$ENGINE_ENTRY" --new --run-dir "$RUN_DIR" --intake "$_ENGINE_INTAKE_TMP" 2>&1)"
    _CREATE_RC=$?
    if [ "$_CREATE_RC" -ne 0 ]; then
        # state.json may already exist from a prior run -- that's OK, reuse it.
        # Any OTHER --new failure, with the engine PRESENT, is now a BLOCKING
        # failure -- it no longer falls through to the legacy runner.
        if [ -f "$RUN_DIR/state.json" ]; then
            note "Engine state already exists in $RUN_DIR (reusing existing job)"
        else
            engine_fail "AF-ENGINE-NEW-FAILED" 9 "presentation_job.py --new exited \
$_CREATE_RC and wrote no state.json:
$_CREATE_OUT"
        fi
    fi

    # Step 3: Run the engine. This walks every manifest phase (count derived
    # from PIPELINE-MANIFEST.json, never a hardcoded number), refuses to skip,
    # runs 6 fail-closed gates in close(), and posts progress to the CC board.
    # Returns the engine's exit code directly to the caller.
    note "Engine run starting -- $_PHASE_COUNT manifest phases, all mechanically enforced"
    _ENGINE_RUN_CMD=(python3 "$ENGINE_ENTRY" --run --run-dir "$RUN_DIR")

    # Re-apply the front-door nonce + env so the render phases still gate correctly
    NONCE_DIR="$RUN_DIR/working/checkpoints"
    NONCE_FILE="$NONCE_DIR/.canonical-entry-nonce"
    mkdir -p "$NONCE_DIR"
    OC_DECK_ENTRY_NONCE="$(_mint_nonce)"
    [ -n "$OC_DECK_ENTRY_NONCE" ] || die "could not mint the front-door nonce"
    ( umask 077; printf '%s' "$OC_DECK_ENTRY_NONCE" > "$NONCE_FILE" )
    chmod 600 "$NONCE_FILE" 2>/dev/null || true
    export OC_DECK_ENTRY_NONCE
    export OC_DECK_CANONICAL_ENTRY=1
    export KIE_PROMPT_GATE="${KIE_PROMPT_GATE:-presentations}"
    # F16 — U047 Rule 3.5 staging is OVER: canonical runs enforce the three
    # pixel-level gates (AF-TEXT-OVERFLOW / AF-SPELLING / AF-TYPE-SIZE-MEASURED)
    # by default; only an explicit PRESENTATION_SLIDE_GEOMETRY_ENFORCE=0 opts out.
    export PRESENTATION_SLIDE_GEOMETRY_ENFORCE="${PRESENTATION_SLIDE_GEOMETRY_ENFORCE:-1}"
    trap 'rm -f "$NONCE_FILE" 2>/dev/null || true' EXIT INT TERM HUP

    note "run: ${_ENGINE_RUN_CMD[*]}"
    "${_ENGINE_RUN_CMD[@]}"
    _ENGINE_RC=$?
    rm -f "$NONCE_FILE" "$_ENGINE_INTAKE_TMP" 2>/dev/null || true
    exit "$_ENGINE_RC"
else
    # The engine component is genuinely absent from this box -- the ONE
    # legitimate reason to fall back. Announce it unmistakably (not a
    # one-line `note`) and record that it ran, so a fleet of boxes quietly
    # running the legacy 2-phase path is visible, never just archived.
    echo "!! [$PROG] ================================================================" >&2
    echo "!! [$PROG] ANNOUNCED FALLBACK: presentation_job.py NOT FOUND at" >&2
    echo "!! [$PROG]   $ENGINE_ENTRY" >&2
    echo "!! [$PROG] The mechanical manifest-phase engine is not installed on this box." >&2
    echo "!! [$PROG] Falling back to the LEGACY run_signature_deck.py runner --" >&2
    echo "!! [$PROG] 2 of ~20 phases. This is NOT a full build. Install/update the" >&2
    echo "!! [$PROG] Presentations department to get the mechanical engine." >&2
    echo "!! [$PROG] ================================================================" >&2
    _FALLBACK_RECORD="$RUN_DIR/working/checkpoints/.fallback-legacy-runner-used"
    mkdir -p "$(dirname "$_FALLBACK_RECORD")" 2>/dev/null || true
    printf '%s reason=engine_component_missing engine_entry=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$ENGINE_ENTRY" >> "$_FALLBACK_RECORD" 2>/dev/null || true
fi

# ===========================================================================
# FALLBACK: the old 2-of-20 path. Runs only when the engine is unavailable.
# ===========================================================================
note "FALLBACK: dispatching the legacy orchestrator (run_signature_deck.py -- 2 of ~20 phases)"
cmd=(python3 "$RUNNER" --run-dir "$RUN_DIR")
cmd+=(--slides "$SLIDES" --out "$OUT" --phase "$PHASE")
[ -n "$PLATFORM" ] && cmd+=(--platform "$PLATFORM")
[ "$ADHOC" -eq 1 ] && cmd+=(--adhoc)
note "run: ${cmd[*]}"

# ===========================================================================
# FRONT-DOOR NONCE HANDSHAKE (FALLBACK PATH) -- required by run_signature_deck.py
# and build_deck.py. Also used by the engine path above when state.json exists.
# ===========================================================================
# They both exit 2 unless the exported OC_DECK_ENTRY_NONCE matches the run-scoped
# 0600 file this script mints below. This SUPERSEDES the retired
# OC_DECK_CANONICAL_ENTRY / OC_DECK_ALLOW_DIRECT env markers, which shipped in
# box-visible comments and were forgeable by any model that read the repo. A random
# per-run nonce cannot be conjured from shipped source; it is consumed (deleted)
# after the run so a stale env value can never be replayed.
# ===========================================================================
NONCE_DIR="$RUN_DIR/working/checkpoints"
NONCE_FILE="$NONCE_DIR/.canonical-entry-nonce"
mkdir -p "$NONCE_DIR"

# _mint_nonce is defined near the top of this script (shared with the engine
# dispatch path above).
OC_DECK_ENTRY_NONCE="$(_mint_nonce)"
[ -n "$OC_DECK_ENTRY_NONCE" ] || die "could not mint the front-door nonce (no python3/openssl/urandom available). Refusing to build."

# Write 0600 BEFORE exporting (umask 077 guarantees no group/other bits on create).
( umask 077; printf '%s' "$OC_DECK_ENTRY_NONCE" > "$NONCE_FILE" )
chmod 600 "$NONCE_FILE" 2>/dev/null || true
export OC_DECK_ENTRY_NONCE
# Legacy marker kept for informational/back-compat wiring only — it is NO LONGER
# sufficient on its own; the nonce above is the real gate.
export OC_DECK_CANONICAL_ENTRY=1

# FIX P3-01(c)4 — close the kie_generate.py / kie-slide-submitter.js side door:
# both are SHARED scripts (also reused by Skills 06/47/49/59 for non-presentations
# image work), so their full 9,000-18,000-char rich-prompt floor gate is opt-in via
# KIE_PROMPT_GATE=presentations (see prompt_gate.py / kie_generate.py). This entry
# point IS the presentations context — force the full gate on for the ENTIRE process
# tree it spawns so a Mode-B reference-image call made anywhere inside a canonical
# deck run (build_deck.py's own submit_task already always gates; this covers the
# standalone kie_generate.py / kie-slide-submitter.js helper paths too) can never run
# ungated. Never overrides an explicit caller override to something stricter; only
# sets the default when unset.
export KIE_PROMPT_GATE="${KIE_PROMPT_GATE:-presentations}"

# F16 — U047 Rule 3.5 staging is OVER: canonical runs enforce the three
# pixel-level gates (AF-TEXT-OVERFLOW / AF-SPELLING / AF-TYPE-SIZE-MEASURED)
# by default; only an explicit PRESENTATION_SLIDE_GEOMETRY_ENFORCE=0 opts out.
export PRESENTATION_SLIDE_GEOMETRY_ENFORCE="${PRESENTATION_SLIDE_GEOMETRY_ENFORCE:-1}"

# Consume/rotate the nonce on ANY exit (normal or signal) so it can never be replayed.
trap 'rm -f "$NONCE_FILE" 2>/dev/null || true' EXIT INT TERM HUP

"${cmd[@]}"
_rc=$?
rm -f "$NONCE_FILE" 2>/dev/null || true
exit "$_rc"
