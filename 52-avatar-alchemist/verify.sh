#!/usr/bin/env bash
# ==============================================================================
# verify.sh — Skill 52 (Avatar-Alchemist Brand Intelligence) self-verification.
# ------------------------------------------------------------------------------
# READ-ONLY and IDEMPOTENT. Never writes inside the checked-in tree: the golden
# BRAND run is regenerated into a fresh mktemp run-dir, the provers run there, and
# the temp dir is removed on exit. Exits NONZERO on ANY failure so it can gate a
# merge / CI / a post-install check.
#
# What it proves (all offline, client-providers-only, ZERO Anthropic at runtime):
#   1  every fail-closed prover's built-in --self-test (VALID passes + BAD fails)
#   2  the front door (entry.sh: deps->bypass-scan->hash-pin->nonce) + foreman plan
#   3  the golden BRAND run end-to-end: 40/40 content invariants + a signed cert
#   4  the five broken variants each fail closed with a DISTINCT AF-AV-* code
#   5  version=book ROUTES (Book skill present) and PARKS book-skill-not-available
#      (Book skill absent) — never served by the brand pipeline
#   6  no Anthropic MODEL IDs and no PII on the client-facing surface
#
# Usage:  bash 52-avatar-alchemist/verify.sh
# Exit:   0 = all checks passed;  nonzero = at least one check failed.
# ==============================================================================
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
S="$SKILL_DIR/scripts"
GD="$SKILL_DIR/examples/golden-lumen-rise"
PY="${PYTHON:-python3}"
export OPENCLAW_PLATFORM="${OPENCLAW_PLATFORM:-mac}"

TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

fails=0
pass() { printf '  [PASS] %s\n' "$1"; }
fail() { printf '  [FAIL] %s\n' "$1"; fails=$((fails + 1)); }

run() {  # run "<label>" <cmd...>   -> expects exit 0
    local label="$1"; shift
    local log; log="$("$@" 2>&1)"; local rc=$?
    if [ "$rc" -eq 0 ]; then pass "$label"
    else fail "$label (rc=$rc)"; printf '%s\n' "$log" | sed 's/^/         /'; fi
}

expect_fail() {  # expect_fail "<label>" "<substr>" <cmd...>  -> expects NONZERO + substr in output
    local label="$1" substr="$2"; shift 2
    local log; log="$("$@" 2>&1)"; local rc=$?
    if [ "$rc" -ne 0 ] && printf '%s' "$log" | grep -q "$substr"; then
        pass "$label (fail-closed rc=$rc, carries $substr)"
    else
        fail "$label (expected nonzero + '$substr', got rc=$rc)"
        printf '%s\n' "$log" | sed 's/^/         /'
    fi
}

echo "== Skill 52 (Avatar-Alchemist) :: verify.sh =="
echo ""
echo "-- 1) fail-closed prover self-tests --------------------------------------"
run "aa_intake_gate.py --self-test"        "$PY" "$S/aa_intake_gate.py" --self-test
run "aa_build_check.py --self-test"        "$PY" "$S/aa_build_check.py" --self-test
run "aa_director.py --self-test"           "$PY" "$S/aa_director.py" --self-test
run "aa_delivery_gate.py --self-test"      "$PY" "$S/aa_delivery_gate.py" --self-test
run "aa_links_gate.py --self-test"         "$PY" "$S/aa_links_gate.py" --self-test
run "aa_package.py --self-test"            "$PY" "$S/aa_package.py" --self-test
run "aa_gate_integrity_check.py --check"   "$PY" "$S/aa_gate_integrity_check.py" --check
run "verify_tone_core_sync.py"             "$PY" "$S/verify_tone_core_sync.py"
run "test_aa_preflight.py (negative suite)" "$PY" "$S/test_aa_preflight.py"

echo ""
echo "-- 2) front door + foreman schedule --------------------------------------"
RUN_DIR="$TMP/entry-run"
if ENTRY_OUT="$(bash "$SKILL_DIR/entry.sh" "$RUN_DIR" 2>&1)"; then
    pass "entry.sh front door (deps -> bypass-scan -> hash-pin -> nonce)"
    NONCE="$RUN_DIR/.entry-nonce"
    run "aa_director.py --plan (nonce accepted)" \
        "$PY" "$S/aa_director.py" --run-dir "$RUN_DIR" --nonce "$NONCE" --plan
else
    fail "entry.sh front door"; printf '%s\n' "$ENTRY_OUT" | sed 's/^/         /'
fi

echo ""
echo "-- 3) golden BRAND run end-to-end (regenerated into a temp run-dir) ------"
GRUN="$TMP/golden-run"; GDELIV="$TMP/golden-deliv"
run "build_golden.py --self-test (deterministic, self-verifying)" \
    "$PY" "$GD/build_golden.py" --self-test
if "$PY" "$GD/build_golden.py" --out "$GRUN" --deliver "$GDELIV" >"$TMP/gen.log" 2>&1; then
    pass "build_golden.py --out/--deliver (40 artifacts + 16 deliverables + cert)"
else
    fail "build_golden.py --out/--deliver"; sed 's/^/         /' "$TMP/gen.log"
fi
run "aa_build_check.py --run (temp golden run)"        "$PY" "$S/aa_build_check.py" --run "$GRUN"
run "aa_build_check.py --run (checked-in golden run)"  "$PY" "$S/aa_build_check.py" --run "$GD/run"
run "aa_intake_gate.py (golden BRAND intake)"          "$PY" "$S/aa_intake_gate.py" --intake "$GRUN/intake.json"
# G-LINKS (fail-soft): the golden stage-02 artifact resolves to degraded:search offline (exit 0)
if LINKS_OUT="$("$PY" "$S/aa_links_gate.py" --stage-file "$GD/run/artifacts/02-avatar-questions-31-32.md" 2>&1)" \
     && printf '%s' "$LINKS_OUT" | grep -q 'degraded:search'; then
    pass "G-LINKS stage-02 (fail-soft, offline -> degraded:search, exit 0)"
else
    fail "G-LINKS stage-02"; printf '%s\n' "$LINKS_OUT" | sed 's/^/         /'
fi
# certificate present and 40/40 attested
if "$PY" - "$GDELIV/PROCESS-CERTIFICATE.json" <<'PYCERT'
import json, sys
c = json.load(open(sys.argv[1]))
assert c["stages_attested"] == 40, c["stages_attested"]
assert c["content_gate"] == "PASS"
assert float(c["qc_score"]) >= 8.5
assert len(c["chain"]) == 40
print("cert ok")
PYCERT
then pass "PROCESS-CERTIFICATE: 40/40 attested, content PASS, QC>=8.5, 40-link chain"
else fail "PROCESS-CERTIFICATE assertion"; fi
# exactly 16 named deliverables + index + manifest + certificate
NDLV="$(ls "$GDELIV" | grep -c '^.*-Amara_Vale\.md$')"
if [ "$NDLV" -eq 16 ]; then pass "16 named deliverables assembled"; else fail "expected 16 deliverables, got $NDLV"; fi

echo ""
echo "-- 4) broken variants (each a DISTINCT AF-AV-*, all fail closed) ---------"
run "make_broken.py (5/5 variants rejected)" \
    "$PY" "$GD/broken-variants/make_broken.py" --results "$TMP/rejection-results.json"

echo ""
echo "-- 5) version=book routing (route when present / park when absent) -------"
run "version=book ROUTES to Book skill (present)" \
    "$PY" "$S/aa_intake_gate.py" --intake "$GD/broken-variants/book_intake.json" --book-skill-present
expect_fail "version=book PARKS book-skill-not-available (absent)" "AF-AV-BOOK-SKILL-MISSING" \
    "$PY" "$S/aa_intake_gate.py" --intake "$GD/broken-variants/book_intake.json"

echo ""
echo "-- 6) client-path hygiene: no Anthropic model ids, no PII ----------------"
ANTHRO_PAT='anthropic/|claude-[0-9]|claude-sonnet|claude-opus|claude-haiku|claude-3|claude-4'
if grep -REnI "$ANTHRO_PAT" "$GD/run" "$GD/delivery" "$SKILL_DIR/prompts" "$SKILL_DIR"/*.json >/dev/null 2>&1; then
    fail "Anthropic MODEL ID present on the client-run/prompt/manifest surface"
    grep -REnI "$ANTHRO_PAT" "$GD/run" "$GD/delivery" "$SKILL_DIR/prompts" "$SKILL_DIR"/*.json | sed 's/^/         /'
else
    pass "no Anthropic model ids (G-NOANTHROPIC surface clean)"
fi
if grep -REoiI '[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}' "$GD" 2>/dev/null \
     | grep -viE '@example\.(com|org|net)' | grep -q .; then
    fail "non-example email (possible PII) in the golden sample"
else
    pass "no PII emails (only example.* addresses)"
fi
if grep -REnI '\b[0-9]{3}[-.][0-9]{3}[-.][0-9]{4}\b' "$GD" >/dev/null 2>&1; then
    fail "phone-number pattern (possible PII) in the golden sample"
else
    pass "no phone-number PII patterns"
fi

echo ""
echo "=========================================================================="
if [ "$fails" -eq 0 ]; then
    echo "RESULT: PASS — all Skill 52 self-verification checks green."
    exit 0
fi
echo "RESULT: FAIL — $fails check(s) failed."
exit 1
