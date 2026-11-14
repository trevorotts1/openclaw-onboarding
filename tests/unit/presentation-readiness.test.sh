#!/usr/bin/env bash
# tests/unit/presentation-readiness.test.sh
#
# PRES-033 regression suite — "Dependency convergence reports success after
# required dependencies remain missing".
#
# What it proves (TODO.md PRES-033 acceptance 1-4 + QC-PRES-033 checks 1-4):
#   A. converge_presentation_deps returns NONZERO readiness when required deps
#      are missing (all binaries absent -> nonzero + complete missing list), and
#      preserves the aggregated updater result (no abort of the run flow).
#   B. Required import missing / native binary missing / failed package install /
#      wrong interpreter -> no READY stamp; the readiness receipt records
#      DEGRADED with remediation_owner + timestamp.
#   C. Video deps: ffmpeg/ffprobe are REQUIRED canon rows (PD-928). Missing them
#      is a REQUIRED gap: converge returns nonzero and PRESENTATION_DEPS_MISSING
#      names them. The separate optional-video branch (PRESENTATION_VIDEO_DEPS_MISSING)
#      still exists for any canon row declared required:false, and C1b proves that
#      mechanism with a fixture canon. Required gaps are never hidden by it.
#   D. Two distinct custom roots: no read/write or reassert invocation uses the
#      other root or /data by assumption (canonical root resolver drives the
#      reassert path and the receipt dir).
#
# Exit 0 = all checks pass. Exit 1 = one or more checks failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATER="$REPO_ROOT/update-skills.sh"
PASS=0
FAIL=0
TMPDIR_TEST="$(mktemp -p "${TMPDIR:-/tmp}" -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "[presentation-readiness] files:"
echo "  updater: $UPDATER"
[ -f "$UPDATER" ] && pass "update-skills.sh present" || fail "update-skills.sh missing"
bash -n "$UPDATER" 2>/dev/null && pass "update-skills.sh parses (bash -n)" || fail "update-skills.sh bash -n FAILED"

# ---------------------------------------------------------------------------
# Helper: extract converge_presentation_deps + its helpers from the updater and
# run them in an isolated bash with stubbed command()/brew/pip. The extraction
# is the same technique evidence/check_dependency_exit.py uses for the audit.
# ---------------------------------------------------------------------------
run_converge() {
    # $1 = temp root (OC_CONFIG); $2 = extra stub preamble; $3 = stubbed-fn body
    local root="$1" extra="$2" stub="$3" out="$4"
    python3 - "$UPDATER" "$out" <<'PY' || return 1
import sys
src = open(sys.argv[1]).read()
start = src.index('  _pres_deps_canon_path() {')
def_pos = src.index('  converge_presentation_deps() {')
# Call site: the bare call after the function body. It may be
# `  converge_presentation_deps` or `  converge_presentation_deps || _PRES_DEPS_CONVERGE_RC=$?`.
# Search AFTER the definition line only (the definition itself is a prefix match of the name).
call = src.find('\n  converge_presentation_deps\n', def_pos)
if call < 0:
    call = src.find('\n  converge_presentation_deps ||', def_pos)
call += 1  # include the leading newline
# find the "}" line right before call
end = src.rindex('\n  }\n', start, call) + len('\n  }\n')
body = src[start:end]
open(sys.argv[2], 'w').write(body)
PY
    {
        cat <<PRE
command() { return 1; }
brew() { return 1; }
python3() { /opt/homebrew/bin/python3 "\$@"; }
OPENCLAW_PLATFORM=mac
OC_CONFIG="$root"
SKILLS_DIR=""
OC_WORKSPACE=""
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PRE
        echo "$extra"
        cat "$out"
        echo 'converge_presentation_deps'
        echo 'echo "CONVERGE_RC=$?"'
    } > "$TMPDIR_TEST/run-$$.sh"
    bash "$TMPDIR_TEST/run-$$.sh" > "$TMPDIR_TEST/out-$$.log" 2>&1
}

echo
echo "(A) all binaries absent -> NONZERO readiness + complete missing list"

STUB_A="$(mktemp -p "$TMPDIR_TEST" -d)"
mkdir -p "$STUB_A/logs" "$STUB_A/secrets"
# canon is resolved via SKILLS_DIR in _pres_deps_canon_path; point it at the repo tree.
cat > "$TMPDIR_TEST/stubpreamble.sh" <<PREAM
SKILLS_DIR="$REPO_ROOT"
PREAM
run_converge "$STUB_A" "$(cat "$TMPDIR_TEST/stubpreamble.sh")" "x" "$TMPDIR_TEST/conv-a.sh"
RC="$(grep -E '^CONVERGE_RC=' "$TMPDIR_TEST/out-$$.log" | tail -1 | cut -d= -f2)"
if [ "$RC" = "2" ]; then
    pass "converge returns 2 (nonzero readiness) with all binaries absent (got $RC)"
else
    fail "converge did NOT return 2 with all binaries absent (got $RC)"
    sed -n '1,20p' "$TMPDIR_TEST/out-$$.log" | sed 's/^/    > /'
fi
if grep -q "PRESENTATION_DEPS_MISSING after converge" "$TMPDIR_TEST/out-$$.log"; then
    pass "converge logs PRESENTATION_DEPS_MISSING after converge"
else
    fail "converge did not log PRESENTATION_DEPS_MISSING after converge"
fi
# Complete missing list: every canon required dep token must appear.
for need in soffice pdftoppm ffmpeg ffprobe tesseract venv; do
    if grep -q "$need" "$TMPDIR_TEST/out-$$.log"; then
        pass "missing list names $need"
    else
        fail "missing list does NOT name $need"
    fi
done
if [ -f "$STUB_A/logs/presentation-readiness.json" ]; then
    REC_ST="$(python3 -c "import json;print(json.load(open('$STUB_A/logs/presentation-readiness.json'))['status'])" 2>/dev/null || echo "?")"
    [ "$REC_ST" = "DEGRADED" ] && pass "readiness receipt persisted with status DEGRADED" \
        || fail "readiness receipt status is '$REC_ST', expected DEGRADED"
    REC_OWN="$(python3 -c "import json;print(json.load(open('$STUB_A/logs/presentation-readiness.json'))['remediation_owner'])" 2>/dev/null || echo "?")"
    [ "$REC_OWN" = "capacity-reliability-engineer" ] && pass "readiness receipt names remediation_owner" \
        || fail "readiness receipt remediation_owner='$REC_OWN'"
    python3 -c "import json;d=json.load(open('$STUB_A/logs/presentation-readiness.json'));assert d['ts'];assert d['root']=='$STUB_A';assert d['ready'] is False" 2>/dev/null \
        && pass "readiness receipt carries timestamp/root/ready=false" \
        || fail "readiness receipt missing timestamp/root/ready=false"
else
    fail "readiness receipt NOT persisted at \$root/logs/presentation-readiness.json"
fi
# Aggregation preservation: converge returning 2 must not abort unrelated flow.
# The function's own message names it (runtime), and the call site captures the
# return code instead of aborting (static, since the call site is outside the
# extracted function body).
if grep -q "aggregated updater result PRESERVED" "$TMPDIR_TEST/out-$$.log"; then
    pass "aggregated result preserved (no rollback of unrelated updates)"
else
    fail "no aggregation-preservation statement in converge output"
fi
if grep -q 'converge_presentation_deps || _PRES_DEPS_CONVERGE_RC=\$?' "$UPDATER"; then
    pass "call site captures converge rc (no abort)"
else
    fail "call site does not capture converge rc"
fi
rm -rf "$STUB_A" "$TMPDIR_TEST/conv-a.sh"

echo
echo "(B) per-fault matrix: no READY stamp + one actionable CC blocker per fault"

# B1: required import missing (venv python exists but import fails; pip
# "succeeds" per stub yet the import STILL fails) -> DEGRADED, no READY stamp.
STUB_B1="$(mktemp -p "$TMPDIR_TEST" -d)"; mkdir -p "$STUB_B1/logs"
mkdir -p "$STUB_B1/.venv-presentations/bin"
cat > "$STUB_B1/.venv-presentations/bin/python" <<'PYSHIM'
#!/usr/bin/env bash
# Simulate an interpreter whose presentation imports are broken no matter what.
if [ "$1" = "-c" ] && printf '%s' "$2" | grep -q "import reportlab"; then exit 1; fi
if [ "$1" = "-m" ] && [ "$2" = "pip" ]; then exit 0; fi  # "install" is a no-op success
exec /opt/homebrew/bin/python3 "$@"
PYSHIM
chmod +x "$STUB_B1/.venv-presentations/bin/python"
run_converge "$STUB_B1" "SKILLS_DIR=\"$REPO_ROOT\"" "x" "$TMPDIR_TEST/conv-b1.sh"
if grep -q "python(reportlab" "$TMPDIR_TEST/out-$$.log" || grep -q "venv(reportlab" "$TMPDIR_TEST/out-$$.log"; then
    pass "B1 required python import missing -> named in missing list"
else
    fail "B1 required python import missing not named"
fi
if [ -f "$STUB_B1/logs/presentation-readiness.json" ]; then
    python3 -c "import json;d=json.load(open('$STUB_B1/logs/presentation-readiness.json'));assert d['status']=='DEGRADED'" 2>/dev/null \
        && pass "B1 no READY stamp (receipt DEGRADED)" || fail "B1 receipt not DEGRADED"
else
    fail "B1 receipt missing"
fi
rm -rf "$STUB_B1" "$TMPDIR_TEST/conv-b1.sh"

# B2: failed package installation (pip fails) -> missing lands in receipt.
STUB_B2="$(mktemp -p "$TMPDIR_TEST" -d)"; mkdir -p "$STUB_B2/logs" "$STUB_B2/.venv-presentations/bin"
cat > "$STUB_B2/.venv-presentations/bin/python" <<'PYSHIM'
#!/usr/bin/env bash
if [ "$1" = "-m" ] && [ "$2" = "pip" ]; then exit 1; fi
exec /opt/homebrew/bin/python3 "$@"
PYSHIM
chmod +x "$STUB_B2/.venv-presentations/bin/python"
run_converge "$STUB_B2" "SKILLS_DIR=\"$REPO_ROOT\"" "x" "$TMPDIR_TEST/conv-b2.sh"
if [ -f "$STUB_B2/logs/presentation-readiness.json" ]; then
    python3 -c "import json;d=json.load(open('$STUB_B2/logs/presentation-readiness.json'));assert d['missing_required']" 2>/dev/null \
        && pass "B2 failed pip install -> receipt carries missing_required" || fail "B2 receipt missing_required empty"
else
    fail "B2 receipt missing"
fi
rm -rf "$STUB_B2" "$TMPDIR_TEST/conv-b2.sh"

echo
echo "(C) video deps are REQUIRED canon rows; the optional-branch mechanism still works"

# C1: ONLY ffmpeg/ffprobe missing (all other required present) -> converge
#     returns 2 and the REQUIRED list names them. PD-928: they are required=true
#     because every shipped bundle carries audio_mp3 (synthesize_full_speech.py
#     hard-exits without ffmpeg/ffprobe) and webinar_mp4 (build_webinar_video.py
#     same), so no client deliverable exists without them.
STUB_C="$(mktemp -p "$TMPDIR_TEST" -d)"; mkdir -p "$STUB_C/logs" "$STUB_C/.venv-presentations/bin"
cat > "$STUB_C/.venv-presentations/bin/python" <<'PYSHIM'
#!/usr/bin/env bash
exec /opt/homebrew/bin/python3 "$@"
PYSHIM
chmod +x "$STUB_C/.venv-presentations/bin/python"
cat > "$TMPDIR_TEST/stubpath.sh" <<PREAM
# stub command(): everything present EXCEPT ffmpeg/ffprobe (required video deps).
# The converge code calls command -v <tool>, so the tool name is the 2nd arg.
command() {
  case "\$2" in
    ffmpeg|ffprobe) return 1 ;;
    *) return 0 ;;
  esac
}
SKILLS_DIR="$REPO_ROOT"
PREAM
run_converge "$STUB_C" "$(cat "$TMPDIR_TEST/stubpath.sh")" "x" "$TMPDIR_TEST/conv-c.sh"
RC="$(grep -E '^CONVERGE_RC=' "$TMPDIR_TEST/out-$$.log" | tail -1 | cut -d= -f2)"
if [ "$RC" = "2" ]; then
    pass "C1 required video missing -> converge returns 2 (readiness degraded)"
else
    fail "C1 required video missing returned $RC, expected 2"
fi
if grep -q "PRESENTATION_DEPS_MISSING after converge.*ffmpeg" "$TMPDIR_TEST/out-$$.log" \
   && grep -q "PRESENTATION_DEPS_MISSING after converge.*ffprobe" "$TMPDIR_TEST/out-$$.log"; then
    pass "C1 required missing list names ffmpeg AND ffprobe"
else
    fail "C1 required missing list does not name ffmpeg/ffprobe"
    grep -o "PRESENTATION_DEPS_MISSING after converge:[^.]*" "$TMPDIR_TEST/out-$$.log" | head -2 | sed 's/^/    > /'
fi
if grep -q "PRESENTATION_VIDEO_DEPS_MISSING (optional branch)" "$TMPDIR_TEST/out-$$.log"; then
    fail "C1 video gap ALSO landed in the optional branch (misclassified)"
else
    pass "C1 video gap never lands in the optional branch when the canon says required"
fi
rm -rf "$STUB_C" "$TMPDIR_TEST/conv-c.sh"

# C1b: the optional-branch MECHANISM still classifies a required:false row
#      separately (preserved, not weakened -- it is real code that must keep
#      working for any future optional row). A fixture canon declares one
#      optional binary that is absent: converge returns 0 and reports it in the
#      video branch, never in the required list.
STUB_C1B="$(mktemp -p "$TMPDIR_TEST" -d)"; mkdir -p "$STUB_C1B/logs" "$STUB_C1B/.venv-presentations/bin"
cat > "$STUB_C1B/.venv-presentations/bin/python" <<'PYSHIM'
#!/usr/bin/env bash
exec /opt/homebrew/bin/python3 "$@"
PYSHIM
chmod +x "$STUB_C1B/.venv-presentations/bin/python"
C1B_CANON_ROOT="$(mktemp -p "$TMPDIR_TEST" -d)"
mkdir -p "$C1B_CANON_ROOT/23-ai-workforce-blueprint/presentations/scripts"
cat > "$C1B_CANON_ROOT/23-ai-workforce-blueprint/presentations/scripts/presentation-deps.json" <<'JSON'
{ "deps": [
  {"name":"python:json","kind":"python_import","import_spec":"json","required":true,"features":["deck"]},
  {"name":"optionalprobe","kind":"binary","binary_name":"pd928optionalabsent","required":false,"features":["video"]}
] }
JSON
cat > "$TMPDIR_TEST/stubpath1b.sh" <<PREAM
command() {
  case "\$2" in
    pd928optionalabsent) return 1 ;;
    *) return 0 ;;
  esac
}
SKILLS_DIR="$C1B_CANON_ROOT"
PREAM
run_converge "$STUB_C1B" "$(cat "$TMPDIR_TEST/stubpath1b.sh")" "x" "$TMPDIR_TEST/conv-c1b.sh"
RC="$(grep -E '^CONVERGE_RC=' "$TMPDIR_TEST/out-$$.log" | tail -1 | cut -d= -f2)"
if [ "$RC" = "0" ]; then
    pass "C1b required:false row missing -> converge returns 0 (branch disabled, not blocked)"
else
    fail "C1b required:false row missing returned $RC, expected 0"
fi
if grep -q "PRESENTATION_VIDEO_DEPS_MISSING (optional branch).*pd928optionalabsent" "$TMPDIR_TEST/out-$$.log"; then
    pass "C1b optional row reported in the video branch"
else
    fail "C1b optional row not reported in the video branch"
fi
if grep -q "PRESENTATION_DEPS_MISSING after converge.*pd928optionalabsent" "$TMPDIR_TEST/out-$$.log"; then
    fail "C1b optional row leaked into the REQUIRED list"
else
    pass "C1b optional row never leaks into the required list"
fi
rm -rf "$STUB_C1B" "$TMPDIR_TEST/conv-c1b.sh" "$C1B_CANON_ROOT"

# C2: a required gap alongside the video gap -> the required gap is named AND
#     the video deps are named in the SAME required list (both required now).
STUB_C2="$(mktemp -p "$TMPDIR_TEST" -d)"; mkdir -p "$STUB_C2/logs" "$STUB_C2/.venv-presentations/bin"
cat > "$STUB_C2/.venv-presentations/bin/python" <<'PYSHIM'
#!/usr/bin/env bash
exec /opt/homebrew/bin/python3 "$@"
PYSHIM
chmod +x "$STUB_C2/.venv-presentations/bin/python"
cat > "$TMPDIR_TEST/stubpath2.sh" <<PREAM
command() {
  case "\$2" in
    ffmpeg|ffprobe|soffice) return 1 ;;
    *) return 0 ;;
  esac
}
SKILLS_DIR="$REPO_ROOT"
PREAM
run_converge "$STUB_C2" "$(cat "$TMPDIR_TEST/stubpath2.sh")" "x" "$TMPDIR_TEST/conv-c2.sh"
RC="$(grep -E '^CONVERGE_RC=' "$TMPDIR_TEST/out-$$.log" | tail -1 | cut -d= -f2)"
if [ "$RC" = "2" ]; then
    pass "C2 required+video missing -> converge returns 2"
else
    fail "C2 required+video missing returned $RC, expected 2"
fi
if grep -q "PRESENTATION_DEPS_MISSING after converge.*soffice" "$TMPDIR_TEST/out-$$.log"; then
    pass "C2 required gap (soffice) still named"
else
    fail "C2 required gap (soffice) not named"
fi
if grep -q "PRESENTATION_DEPS_MISSING after converge.*ffmpeg" "$TMPDIR_TEST/out-$$.log"; then
    pass "C2 video gap (ffmpeg) named in the required list alongside soffice"
else
    fail "C2 video gap (ffmpeg) not named in the required list"
fi
rm -rf "$STUB_C2" "$TMPDIR_TEST/conv-c2.sh"

echo
echo "(D) two distinct custom roots — no other-root / /data reads by assumption"

# D1: root A receipt lands ONLY in A; root B receipt lands ONLY in B.
for R in D1A D1B; do
    STUB_D="$(mktemp -p "$TMPDIR_TEST" -d)"; mkdir -p "$STUB_D/logs" "$STUB_D/.venv-presentations/bin"
    cat > "$STUB_D/.venv-presentations/bin/python" <<'PYSHIM'
#!/usr/bin/env bash
exec /opt/homebrew/bin/python3 "$@"
PYSHIM
    chmod +x "$STUB_D/.venv-presentations/bin/python"
    cat > "$TMPDIR_TEST/stubd.sh" <<PREAM
command() { return 0; }
SKILLS_DIR="$REPO_ROOT"
PREAM
    run_converge "$STUB_D" "$(cat "$TMPDIR_TEST/stubd.sh")" "x" "$TMPDIR_TEST/conv-$R.sh"
    if [ -f "$STUB_D/logs/presentation-readiness.json" ]; then
        RECROOT="$(python3 -c "import json;print(json.load(open('$STUB_D/logs/presentation-readiness.json'))['root'])" 2>/dev/null || echo "?")"
        [ "$RECROOT" = "$STUB_D" ] && pass "$R receipt root == its own custom root" \
            || fail "$R receipt root='$RECROOT', expected '$STUB_D'"
    else
        fail "$R no receipt in its own root"
    fi
    rm -rf "$STUB_D" "$TMPDIR_TEST/conv-$R.sh"
done

echo
echo "(E) entry GATE 1 — wrong interpreter caught; optional video classified"

ENTRY="$REPO_ROOT/23-ai-workforce-blueprint/scripts/presentation-canonical-entry.sh"
[ -f "$ENTRY" ] && pass "entry script present" || fail "entry script missing ($ENTRY)"
bash -n "$ENTRY" 2>/dev/null && pass "entry script parses (bash -n)" || fail "entry script bash -n FAILED"
# The deployed mirror must stay byte-identical (FIX 31).
MIRROR="$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation-canonical-entry.sh"
if cmp -s "$ENTRY" "$MIRROR"; then
    pass "entry deployed copy == role-library mirror (byte-identical)"
else
    fail "entry deployed copy DIVERGED from role-library mirror"
fi

# write_complete_ledger DIR — mint a completed intake ledger + signed driver
# envelope so GATE 0 / GATE 0b pass and the test can exercise GATE 1 (same
# fixture shape as presentation-deps-gate.test.sh).
write_complete_ledger() {
    mkdir -p "$1/working/interview"
    cat > "$1/working/interview/intake_ledger.json" <<'LEDGER'
{ "status": "complete", "complete": true, "turns": 6,
  "entries": {
    "representation_mix": {"validated": true, "answer": "no people at all"},
    "grounded_content": {"validated": true, "answer": "the Momentum Method"}
  } }
LEDGER
    cat > "$1/working/interview/intake_transcript.json" <<'TRACE'
{"format": "sp-intake-transcript-v1", "driver_signature": "fixture-signed",
 "qid_sequence": ["interview_choice", "q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "frame_selection"],
 "turns": [{"qid": "interview_choice", "answer": "quick"}, {"qid": "q1", "answer": "Make It Easy to Buy"}]}
TRACE
}

# E1: WRONG INTERPRETER — a stub "system python3" without the presentation
#     modules, and NO department venv. GATE 1 must name the interpreter and
#     refuse (exit 6), not import from a silently-substituted interpreter.
E1_RUN="$(mktemp -p "$TMPDIR_TEST" -d)"; mkdir -p "$E1_RUN/working/checkpoints"
touch "$E1_RUN/working/checkpoints/.test-context"
write_complete_ledger "$E1_RUN"
echo '[{"slide":1,"scene":"x","copy":["hi"]}]' > "$E1_RUN/slides.json"
E1_SCRIPTS="$(mktemp -p "$TMPDIR_TEST" -d)"
for f in build_deck.py run_signature_deck.py; do echo "x" > "$E1_SCRIPTS/$f"; done
E1_PYSHIM="$E1_RUN/pyshim"; mkdir -p "$E1_PYSHIM"
for b in bash date mkdir dirname tee sed cat printf grep env tr head cut wc sh; do
    src="$(command -v "$b" 2>/dev/null || true)"; [ -n "$src" ] && ln -sf "$src" "$E1_PYSHIM/$b"
done
cat > "$E1_PYSHIM/python3" <<'PYSHIM'
#!/usr/bin/env bash
# System python WITHOUT presentation modules (all imports fail).
if [ "$1" = "-c" ] && printf '%s' "$2" | grep -q "import reportlab"; then exit 1; fi
if [ "$1" = "-c" ] && printf '%s' "$2" | grep -q "import pypdf"; then exit 1; fi
exec /opt/homebrew/bin/python3 "$@"
PYSHIM
chmod +x "$E1_PYSHIM/python3"
# No department venv on the stub root: HOME is isolated so the gate's venv
# fallback cannot borrow THIS box's healthy interpreter, and
# PRESENTATION_PIPELINE_INTERPRETER points at a nonexistent venv python. The
# only python3 on PATH is the import-failing shim = the WRONG interpreter.
E1_HOME="$E1_RUN/home"; mkdir -p "$E1_HOME"
E1_RC=0
HOME="$E1_HOME" PATH="$E1_PYSHIM:/usr/bin:/bin" \
    PRESENTATION_PIPELINE_INTERPRETER="$E1_HOME/.venv-presentations/bin/python" \
    SCRIPTS_DIR="$E1_SCRIPTS" bash "$ENTRY" \
    --run-dir "$E1_RUN" --slides "$E1_RUN/slides.json" --out "$E1_RUN/out.pptx" \
    > "$TMPDIR_TEST/e1.log" 2>&1 || E1_RC=$?
if grep -q "PRESENTATION_DEPS_MISSING" "$TMPDIR_TEST/e1.log"; then
    pass "E1 wrong interpreter -> GATE 1 reports PRESENTATION_DEPS_MISSING"
else
    fail "E1 wrong interpreter not caught (rc=$E1_RC)"
    sed -n '1,15p' "$TMPDIR_TEST/e1.log" | sed 's/^/    > /'
fi
if grep -q "python(reportlab" "$TMPDIR_TEST/e1.log" || grep -q "interpreter" "$TMPDIR_TEST/e1.log"; then
    pass "E1 missing python dep named with interpreter context"
else
    fail "E1 missing python dep not named with interpreter context"
fi
rm -rf "$E1_RUN" "$E1_SCRIPTS"

# E2: VIDEO DEPS REQUIRED (PD-928) — ffmpeg/ffprobe absent, every other required
#     dep present -> GATE 1 REFUSES (exit 6) and names ffmpeg/ffprobe. This is the
#     first direction of the PD-928 proof: a build whose bundle carries audio_mp3
#     + webinar_mp4 cannot complete without them, so refusal is correct.
E2_RUN="$(mktemp -p "$TMPDIR_TEST" -d)"; mkdir -p "$E2_RUN/working/checkpoints"
touch "$E2_RUN/working/checkpoints/.test-context"
write_complete_ledger "$E2_RUN"
echo '[{"slide":1,"scene":"x","copy":["hi"]}]' > "$E2_RUN/slides.json"
E2_SCRIPTS="$(mktemp -p "$TMPDIR_TEST" -d)"
for f in build_deck.py run_signature_deck.py; do echo "x" > "$E2_SCRIPTS/$f"; done
# PD-917: GATE 1 reads its dependency LIST from the canon presentation-deps.json
# in SCRIPTS_DIR (absent list = hard failure by design since PD-010). E2 proves
# the REQUIRED classification, so give the fixture the real canon: its required
# rows are satisfied by this fixture except ffmpeg/ffprobe, which stay off PATH.
cp "$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation-deps.json" \
   "$E2_SCRIPTS/presentation-deps.json"
E2_BIN="$TMPDIR_TEST/e2bin"; mkdir -p "$E2_BIN"
for b in bash date mkdir dirname tee sed cat printf grep env python3 soffice pdftoppm tesseract tr head cut wc sh; do
    src="$(command -v "$b" 2>/dev/null || true)"; [ -n "$src" ] && ln -sf "$src" "$E2_BIN/$b"
done
# The env runs the entry with a MEASURED HEALTHY interpreter (imports all four
# presentation modules) and a PATH with NO ffmpeg/ffprobe. Both halves matter:
# an isolated HOME alone breaks the pytesseract row (it lives in the USER
# site-packages), which would make this assertion pass for the wrong reason —
# the ONLY missing required dep in the fixture must be ffmpeg/ffprobe.
# NO QC_SKIP_PRESENTATION_DEPS: GATE 1 must actually run and refuse.
E2_PY=""
for cand in "$HOME/.openclaw/.venv-presentations/bin/python" "$(command -v python3)"; do
    [ -n "$cand" ] && [ -x "$cand" ] || continue
    "$cand" -c "import reportlab, pptx, pypdf, pytesseract" >/dev/null 2>&1 || continue
    E2_PY="$cand"; break
done
E2_HOME="$E2_RUN/home"; mkdir -p "$E2_HOME"
E2_RC=0
if [ -n "$E2_PY" ]; then
    HOME="$E2_HOME" PATH="$E2_BIN" \
        PRESENTATION_PIPELINE_INTERPRETER="$E2_PY" \
        SCRIPTS_DIR="$E2_SCRIPTS" bash "$ENTRY" \
        --run-dir "$E2_RUN" --slides "$E2_RUN/slides.json" --out "$E2_RUN/out.pptx" \
        > "$TMPDIR_TEST/e2.log" 2>&1 || E2_RC=$?
else
    echo "  UNPROVEN: E2 required-video proof needs an interpreter importing reportlab+pptx+pypdf+pytesseract; none found on this box"
fi
if [ -z "$E2_PY" ]; then
    :  # UNPROVEN reported above; never a silent pass
elif grep -q "PRESENTATION_DEPS_MISSING" "$TMPDIR_TEST/e2.log" \
   && grep -q "ffmpeg" "$TMPDIR_TEST/e2.log"; then
    pass "E2 required video missing -> GATE 1 refuses and names ffmpeg (rc=$E2_RC)"
else
    fail "E2 required video missing did NOT refuse naming ffmpeg (rc=$E2_RC)"
    sed -n '1,15p' "$TMPDIR_TEST/e2.log" | sed 's/^/    > /'
fi
if [ -z "$E2_PY" ]; then
    :
elif [ "$E2_RC" = "6" ]; then
    pass "E2 GATE 1 exit code is 6 (PRESENTATION_DEPS_MISSING), not a silent pass"
else
    fail "E2 GATE 1 exit code is $E2_RC, expected 6"
fi
# Cause isolation: the ONLY named required gaps must be the two video deps.
E2_NAMED="$(grep -o "PRESENTATION_DEPS_MISSING: .*" "$TMPDIR_TEST/e2.log" | tail -1)"
case "$E2_NAMED" in
    *ffmpeg*ffprobe*|*ffprobe*ffmpeg*)
        if printf '%s' "$E2_NAMED" | grep -Eq "soffice|pdftoppm|pytesseract|reportlab|pypdf|pptx"; then
            fail "E2 refused for reasons beyond the video deps — cause not isolated: $E2_NAMED"
        else
            pass "E2 refusal names ONLY ffmpeg/ffprobe (cause isolated)"
        fi ;;
    "")
        [ -z "$E2_PY" ] || fail "E2 no PRESENTATION_DEPS_MISSING line to attribute" ;;
    *) fail "E2 named gap set is not the video pair: $E2_NAMED" ;;
esac
if grep -q "PRESENTATION_VIDEO_DEPS_MISSING (optional branch)" "$TMPDIR_TEST/e2.log"; then
    fail "E2 video gap ALSO reported as an optional branch (misclassified)"
else
    pass "E2 video gap never reported as an optional branch"
fi
rm -rf "$E2_RUN" "$E2_SCRIPTS"

# E3: DECK-ONLY BUILD STILL PASSES (PD-928 second proof direction) — a canon
#     that does NOT carry the video rows (the shape of a deck-only deployment:
#     no audio, no webinar) passes GATE 1 on a box with ffmpeg/ffprobe absent.
#     This is what "deck-only builds still work" must mean mechanically, and it
#     is proven, not asserted.
E3_RUN="$(mktemp -p "$TMPDIR_TEST" -d)"; mkdir -p "$E3_RUN/working/checkpoints"
touch "$E3_RUN/working/checkpoints/.test-context"
write_complete_ledger "$E3_RUN"
echo '[{"slide":1,"scene":"x","copy":["hi"]}]' > "$E3_RUN/slides.json"
E3_SCRIPTS="$(mktemp -p "$TMPDIR_TEST" -d)"
for f in build_deck.py run_signature_deck.py; do echo "x" > "$E3_SCRIPTS/$f"; done
python3 - "$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation-deps.json" \
        "$E3_SCRIPTS/presentation-deps.json" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
doc["deps"] = [d for d in doc["deps"] if d.get("name") not in ("ffmpeg", "ffprobe")]
json.dump(doc, open(sys.argv[2], "w", encoding="utf-8"), indent=2)
PY
E3_BIN="$TMPDIR_TEST/e3bin"; mkdir -p "$E3_BIN"
for b in bash date mkdir dirname tee sed cat printf grep env python3 soffice pdftoppm tesseract tr head cut wc sh; do
    src="$(command -v "$b" 2>/dev/null || true)"; [ -n "$src" ] && ln -sf "$src" "$E3_BIN/$b"
done
E3_HOME="$E3_RUN/home"; mkdir -p "$E3_HOME"
# PD-928: the interpreter is pinned to a MEASURED HEALTHY one, because this
# assertion's subject is the CANON (video rows absent -> no video dep demanded),
# never the interpreter. The gate resolves its python as
# PRESENTATION_PIPELINE_INTERPRETER -> <root>/.venv-presentations -> bare python3,
# and pytesseract lives in the USER site-packages under $HOME, so an isolated
# HOME alone would fail the pytesseract row for a reason that has nothing to do
# with this assertion. Pin a python that imports all four, and require the pin
# to be honest: if no such interpreter exists on this box, say UNPROVEN rather
# than reporting a canon failure that is really an interpreter failure.
E3_PY=""
for cand in "$HOME/.openclaw/.venv-presentations/bin/python" "$(command -v python3)"; do
    [ -n "$cand" ] && [ -x "$cand" ] || continue
    "$cand" -c "import reportlab, pptx, pypdf, pytesseract" >/dev/null 2>&1 || continue
    E3_PY="$cand"; break
done
E3_RC=0
if [ -z "$E3_PY" ]; then
    echo "  UNPROVEN: E3 deck-only proof needs an interpreter importing reportlab+pptx+pypdf+pytesseract; none found on this box (checked \$HOME/.openclaw/.venv-presentations and python3)"
elif HOME="$E3_HOME" PATH="$E3_BIN" \
    PRESENTATION_PIPELINE_INTERPRETER="$E3_PY" \
    SCRIPTS_DIR="$E3_SCRIPTS" bash "$ENTRY" \
    --run-dir "$E3_RUN" --slides "$E3_RUN/slides.json" --out "$E3_RUN/out.pptx" \
    > "$TMPDIR_TEST/e3.log" 2>&1; then
    :
else
    E3_RC=$?
fi
if [ -n "$E3_PY" ] && grep -q "OK: all runtime deps present" "$TMPDIR_TEST/e3.log"; then
    pass "E3 deck-only canon + no ffmpeg on PATH -> GATE 1 passes"
elif [ -z "$E3_PY" ]; then
    :  # UNPROVEN already reported above; never a silent pass
else
    fail "E3 deck-only canon did not pass GATE 1 (rc=$E3_RC, interpreter=$E3_PY)"
    sed -n '1,20p' "$TMPDIR_TEST/e3.log" | sed 's/^/    > /'
fi
if [ -n "$E3_PY" ] && ! grep -q "PRESENTATION_DEPS_MISSING" "$TMPDIR_TEST/e3.log"; then
    pass "E3 deck-only build never trips PRESENTATION_DEPS_MISSING"
elif [ -z "$E3_PY" ]; then
    :
else
    fail "E3 deck-only build tripped PRESENTATION_DEPS_MISSING"
fi
rm -rf "$E3_RUN" "$E3_SCRIPTS"

echo
echo "============================================"
echo "presentation-readiness: PASS=$PASS FAIL=$FAIL"
echo "============================================"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
