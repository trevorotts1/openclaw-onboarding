#!/usr/bin/env bash
# 23-ai-workforce-blueprint/scripts/presentation-canonical-entry.sh
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
#   1. DEPS CHECK      — the four runtime deps (soffice, pdftoppm, reportlab,
#                        python-pptx) must be present, or the build refuses to
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
#   (3/4 propagate from run_signature_deck.py: 3 render fail, 4 kie balance abort)
# ============================================================================

set -uo pipefail

PROG="presentation-canonical-entry.sh"

die() { echo "FATAL [$PROG]: $*" >&2; exit 2; }
note() { echo "=== [$PROG] $* ==="; }

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
PLAN=0 ADHOC=0
while [ $# -gt 0 ]; do
    case "$1" in
        --run-dir)     RUN_DIR="${2:-}"; shift 2 ;;
        --slides)      SLIDES="${2:-}"; shift 2 ;;
        --out)         OUT="${2:-}"; shift 2 ;;
        --phase)       PHASE="${2:-}"; shift 2 ;;
        --platform)    PLATFORM="${2:-}"; shift 2 ;;
        --scripts-dir) SCRIPTS_DIR="${2:-}"; shift 2 ;;
        --plan)        PLAN=1; shift ;;
        --adhoc)       ADHOC=1; shift ;;
        -h|--help)     usage ;;
        *) die "unknown argument: $1 (run with --help)" ;;
    esac
done

[ -n "$RUN_DIR" ] || usage
[ -d "$RUN_DIR" ] || die "--run-dir not found: $RUN_DIR"
RUN_DIR="$(cd "$RUN_DIR" && pwd)"
if [ "$PLAN" -eq 0 ]; then
    [ -n "$SLIDES" ] || die "--slides is required (use --plan to inspect only)"
    [ -f "$SLIDES" ] || die "slides.json not found: $SLIDES"
    [ -n "$OUT" ] || die "--out is required to build a deck"
fi

# ---------------------------------------------------------------------------
# Locate the canonical render scripts (single source of truth).
# Works on the repo/operator box AND a materialized client box.
# ---------------------------------------------------------------------------
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
resolve_scripts_dir() {
    local c
    for c in \
        "$SCRIPTS_DIR" \
        "$SELF_DIR" \
        "$SELF_DIR/../templates/role-library/presentations/scripts" \
        "$RUN_DIR/departments/Presentations/scripts" \
        "$RUN_DIR/../scripts" \
        "$RUN_DIR/scripts" \
        "$HOME/departments/Presentations/scripts" \
    ; do
        [ -n "$c" ] || continue
        if [ -f "$c/build_deck.py" ] && [ -f "$c/run_signature_deck.py" ]; then
            (cd "$c" && pwd); return 0
        fi
    done
    return 1
}
SCRIPTS_DIR="$(resolve_scripts_dir)" || die \
    "canonical scripts (build_deck.py + run_signature_deck.py) not found. \
Pass --scripts-dir DIR or set \$SCRIPTS_DIR to the Presentations scripts directory."
BUILD_DECK="$SCRIPTS_DIR/build_deck.py"
RUNNER="$SCRIPTS_DIR/run_signature_deck.py"
note "canonical scripts: $SCRIPTS_DIR"

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

# ===========================================================================
# GATE 0 — FRONT-DOOR SELF-SCREEN via deck-build-guard.sh
# Checks: (a) hand-rolled artifacts in the run directory, (b) interview-ledger
# completeness. Even the one sanctioned door self-polices.
# deck-build-guard.sh lives beside this script in the same scripts directory.
# ===========================================================================
GUARD="$SELF_DIR/deck-build-guard.sh"
if [ -f "$GUARD" ]; then
    note "GATE 0 — FRONT-DOOR SELF-SCREEN (deck-build-guard.sh)"
    # Pass the canonical-entry command so the guard can extract --run-dir and
    # check the intake ledger, while recognizing this is the sanctioned route.
    GUARD_RC=0
    # Pass --plan through so the guard exempts read-only plan inspection from the
    # fail-closed intake-ledger requirement (a real build must have a complete ledger).
    _GUARD_CMD="bash $SELF_DIR/presentation-canonical-entry.sh --run-dir $RUN_DIR"
    [ "$PLAN" -eq 1 ] && _GUARD_CMD="$_GUARD_CMD --plan"
    OPENCLAW_EXEC_CMD="$_GUARD_CMD" \
        bash "$GUARD" 2>&1 || GUARD_RC=$?
    if [ "$GUARD_RC" -ne 0 ]; then
        echo "FATAL [$PROG]: GATE 0 — deck-build-guard.sh denied this run (exit $GUARD_RC)." >&2
        echo "  Fix the reported condition (see output above) and re-run." >&2
        echo "  The ONLY sanctioned deck build is: bash presentation-canonical-entry.sh --run-dir … --slides … --out …" >&2
        exit "$GUARD_RC"
    fi
    note "  GATE 0 PASSED"
else
    note "  GATE 0 — deck-build-guard.sh not found at $GUARD; self-screen skipped"
fi

# ===========================================================================
# GATE 1 — DEPS CHECK (the four runtime deps; exit 6 PRESENTATION_DEPS_MISSING)
# ===========================================================================
note "GATE 1/3 — DEPS CHECK (soffice, pdftoppm, reportlab, python-pptx)"
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
    else
        missing+=("python3")
    fi
    if [ "${#missing[@]}" -gt 0 ]; then
        # FIX-PRES-09(iv): event-shaped reassert. On a VPS the four deps do not
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
    echo "  OK: all four runtime deps present"
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
# GATE 1b — SKILL-48 GHL MODULE CO-LOCATION (FIX-PRES-03)
# ghl_media.py re-exports Skill-48 helpers; delivery_gate.py requires the
# resulting pptx_ghl_media_id. If the module is absent, a deck renders on PAID
# Kie credits and then dies at delivery. Assert importability HERE, before any
# render spend. Owner-token skippable (PRESENTATION_GHL_MODULE_MISSING).
# ===========================================================================
note "GATE 1b/3 — SKILL-48 GHL MODULE CO-LOCATION (ghl_media importable)"
ghl_module_check() {
    command -v python3 >/dev/null 2>&1 || {
        echo "  (python3 absent; GHL module check skipped)"; return 0; }
    if PYTHONPATH="$SCRIPTS_DIR${PYTHONPATH:+:$PYTHONPATH}" \
        python3 -c "import ghl_media" >/dev/null 2>&1; then
        echo "  OK: ghl_media importable from $SCRIPTS_DIR"
        return 0
    fi
    # Fall back to a resolved-path existence check (import can fail for a reason
    # other than absence, e.g. a transitive dep) so the message is accurate.
    if [ -f "$SCRIPTS_DIR/ghl_media.py" ]; then
        echo "PRESENTATION_GHL_MODULE_MISSING: ghl_media.py is present at $SCRIPTS_DIR but not importable (check its Skill-48 dependency co-location)." >&2
    else
        echo "PRESENTATION_GHL_MODULE_MISSING: ghl_media.py not found at $SCRIPTS_DIR (Skill-48 co-location missing)." >&2
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
         "kie_generate.py", "presentation-canonical-entry.sh"}

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
    if [ -f "$SCRIPTS_DIR/sync_check.py" ] && command -v python3 >/dev/null 2>&1; then
        if python3 "$SCRIPTS_DIR/sync_check.py" >/tmp/_pce_sync.$$ 2>&1; then
            echo "  OK: sync_check.py — renderer in lockstep with the SOP/manifest stack"
        else
            sed 's/^/    sync_check> /' /tmp/_pce_sync.$$ >&2 || true
            rm -f /tmp/_pce_sync.$$
            return 4
        fi
        rm -f /tmp/_pce_sync.$$
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
# All gates passed — hand off to the CANONICAL ORCHESTRATOR.
# run_signature_deck.py enforces the phase-attestation chain and calls build_deck.py
# for the render. We never call build_deck.py directly and never touch its path.
# ===========================================================================
note "ALL GATES PASSED — dispatching the canonical orchestrator (run_signature_deck.py)"
cmd=(python3 "$RUNNER" --run-dir "$RUN_DIR")
if [ "$PLAN" -eq 1 ]; then
    cmd+=(--plan)
    [ -n "$SLIDES" ] && cmd+=(--slides "$SLIDES")
else
    cmd+=(--slides "$SLIDES" --out "$OUT" --phase "$PHASE")
fi
[ -n "$PLATFORM" ] && cmd+=(--platform "$PLATFORM")
[ "$ADHOC" -eq 1 ] && cmd+=(--adhoc)
note "run: ${cmd[*]}"

# ===========================================================================
# FRONT-DOOR NONCE HANDSHAKE — required by run_signature_deck.py and build_deck.py.
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
OC_DECK_ENTRY_NONCE="$(_mint_nonce)"
[ -n "$OC_DECK_ENTRY_NONCE" ] || die "could not mint the front-door nonce (no python3/openssl/urandom available). Refusing to build."

# Write 0600 BEFORE exporting (umask 077 guarantees no group/other bits on create).
( umask 077; printf '%s' "$OC_DECK_ENTRY_NONCE" > "$NONCE_FILE" )
chmod 600 "$NONCE_FILE" 2>/dev/null || true
export OC_DECK_ENTRY_NONCE
# Legacy marker kept for informational/back-compat wiring only — it is NO LONGER
# sufficient on its own; the nonce above is the real gate.
export OC_DECK_CANONICAL_ENTRY=1

# Consume/rotate the nonce on ANY exit (normal or signal) so it can never be replayed.
trap 'rm -f "$NONCE_FILE" 2>/dev/null || true' EXIT INT TERM HUP

"${cmd[@]}"
_rc=$?
rm -f "$NONCE_FILE" 2>/dev/null || true
exit "$_rc"
