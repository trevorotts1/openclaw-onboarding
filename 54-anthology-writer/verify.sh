#!/usr/bin/env bash
# ==============================================================================
# 54-anthology-writer/verify.sh — Anthology Writer self-verification gate.
# ------------------------------------------------------------------------------
# READ-ONLY and IDEMPOTENT (writes only under temp run dirs it removes; never
# mutates the skill tree, so it can run twice -> identical PASS). Exits NONZERO
# on ANY failure, so it can gate a merge / CI / a post-install check. Mirrors
# 55-product-bio/verify.sh.
#
#   1. the provers --self-test               (built-in golden + attack fixtures)
#   2. golden reproduce                      (each prover PASSes the golden bundle)
#   3. broken-variants reject                (each attack fixture trips its AF, exit 2)
#   4. prompt-fidelity pins + tone-core sync  (baked IP matches recorded/canonical)
#   5. no-Anthropic scan                     (AF-AW-ANTHROPIC: no claude-*/anthropic/* id)
#   6. end-to-end golden pilot through the entry (a full pass issues a certificate)
#   7. shipped example re-issues the SHIPPED certificate_sha (deterministic => idempotent)
#   8. shipped-example broken-variants reject
#   9. seeded-defect E2E (a short chapter blocks the run; NO certificate issued)
#
# Usage:  bash 54-anthology-writer/verify.sh
# Exit:   0 = all checks passed;  nonzero = at least one check failed.
# ==============================================================================
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS="$SKILL_DIR/scripts"
GOLD="$SKILL_DIR/test-fixtures/golden"
ATK="$SKILL_DIR/test-fixtures/attack"
EX="$SKILL_DIR/examples/golden-unbroken-ground"        # shipped worked example
EBV="$EX/broken-variants"
PY="${PYTHON:-python3}"

fails=0
run() {
    local label="$1"; shift
    local log rc
    log="$("$@" 2>&1)"; rc=$?
    if [ "$rc" -eq 0 ]; then
        printf '  [PASS] %s\n' "$label"
    else
        printf '  [FAIL] %s (rc=%s)\n' "$label" "$rc"
        printf '%s\n' "$log" | sed 's/^/         /'
        fails=$((fails + 1))
    fi
}

# expect_reject "<label>" <prover.py> <AF-CODE> [args...] — passes iff the prover
# REJECTS (exit 2) AND the expected AF code is present in its output.
expect_reject() {
    local label="$1" prover="$2" code="$3"; shift 3
    local out rc
    out="$("$PY" "$SCRIPTS/$prover" "$@" --json 2>&1)"; rc=$?
    if [ "$rc" -eq 2 ] && printf '%s' "$out" | grep -q "$code"; then
        printf '  [PASS] reject %-28s -> %s\n' "$label" "$code"
    else
        printf '  [FAIL] reject %-28s (rc=%s, expected exit 2 + %s)\n' "$label" "$rc" "$code"
        printf '%s\n' "$out" | sed 's/^/         /'
        fails=$((fails + 1))
    fi
}

echo "== Skill 54 (Anthology Writer) :: verify.sh =="

# 1) the provers --self-test (+ the orchestrator's built-in gate self-test:
#    P7 delivery gate + fail-closed unmapped-checker).
for p in prove_aw_intake prove_aw_fidelity prove_aw_tone prove_aw_chapter aw_build_check; do
    if [ -f "$SCRIPTS/$p.py" ]; then
        run "$p.py --self-test" "$PY" "$SCRIPTS/$p.py" --self-test
    else
        printf '  [FAIL] %s.py missing at %s\n' "$p" "$SCRIPTS"; fails=$((fails + 1))
    fi
done
run "run_anthology.py --self-test" "$PY" "$SKILL_DIR/run_anthology.py" --self-test

# 2) golden reproduce — each prover PASSes the golden bundle.
run "golden intake PASS"    "$PY" "$SCRIPTS/prove_aw_intake.py"   "$GOLD/intake.json"
run "golden fidelity PASS"  "$PY" "$SCRIPTS/prove_aw_fidelity.py"
run "golden tone-core sync" "$PY" "$SCRIPTS/verify_tone_core_sync.py"
run "golden tone PASS"      "$PY" "$SCRIPTS/prove_aw_tone.py"      "$GOLD/tone-doc.md"
run "golden chapter PASS"   "$PY" "$SCRIPTS/prove_aw_chapter.py"   "$GOLD/chapter.md" --mode chapter --title "$GOLD/title.json" --intake "$GOLD/intake.json"
run "golden outline PASS"   "$PY" "$SCRIPTS/prove_aw_chapter.py"   "$GOLD/outline.md" --mode outline --title "$GOLD/title.json" --intake "$GOLD/intake.json"
run "golden build-check PASS" "$PY" "$SCRIPTS/aw_build_check.py"   "$GOLD/RUN-LEDGER.json"

# 3) broken-variants reject — each attack fixture trips its distinct AF (fail-closed proof).
expect_reject "intake-missing"        prove_aw_intake.py   "AF-AW-INTAKE-MISSING"    "$ATK/intake_missing.json"
expect_reject "intake-credential"     prove_aw_intake.py   "AF-AW-INTAKE-CREDENTIAL" "$ATK/intake_credential.json"
expect_reject "prompt-drift"          prove_aw_fidelity.py "AF-AW-PROMPT-DRIFT"      --prompts-dir "$ATK/drifted-prompts"
expect_reject "tone-3-influences"     prove_aw_tone.py     "AF-AW-TONE-4"            "$ATK/tone_three_influences.md"
expect_reject "tone-short"            prove_aw_tone.py     "AF-AW-TONE-FLOOR"        "$ATK/tone_short.md"
expect_reject "chapter-short"         prove_aw_chapter.py  "AF-AW-CHAP-LEN"          "$ATK/chapter_short.md" --mode chapter --title "$GOLD/title.json" --intake "$GOLD/intake.json"
expect_reject "chapter-whitespace-pad" prove_aw_chapter.py "AF-AW-CHAP-LEN"         "$ATK/chapter_whitespace_pad.md" --mode chapter --title "$GOLD/title.json" --intake "$GOLD/intake.json"
expect_reject "chapter-verify-missing" prove_aw_chapter.py "AF-AW-VERIFY-BLOCK"     "$ATK/chapter_verify_missing.md" --mode chapter --title "$GOLD/title.json" --intake "$GOLD/intake.json"
expect_reject "chapter-subtitle-changed" prove_aw_chapter.py "AF-AW-TITLE-LOCK"     "$ATK/chapter_subtitle_changed.md" --mode chapter --title "$GOLD/title.json" --intake "$GOLD/intake.json"
expect_reject "chapter-story-dropped" prove_aw_chapter.py  "AF-AW-STORIES"          "$ATK/chapter_story_dropped.md" --mode chapter --title "$GOLD/title.json" --intake "$GOLD/intake.json"
expect_reject "chapter-placeholder"   prove_aw_chapter.py  "AF-AW-PLACEHOLDER"      "$ATK/chapter_placeholder.md" --mode chapter --title "$GOLD/title.json" --intake "$GOLD/intake.json"
expect_reject "ledger-anthropic"      aw_build_check.py    "AF-AW-ANTHROPIC"        "$ATK/ledger_anthropic.json"
expect_reject "ledger-rewrite-budget" aw_build_check.py    "AF-AW-REWRITE-BUDGET"   "$ATK/ledger_rewrite_over_budget.json"
expect_reject "ledger-no-provenance"  aw_build_check.py    "AF-AW-PROVENANCE-MISSING" "$ATK/ledger_no_provenance.json"

# 4) prompt-fidelity pins + tone-core sync (named for clarity; covered above).
run "prompt-fidelity pins match" "$PY" "$SCRIPTS/prove_aw_fidelity.py"
run "tone-core in lockstep"      "$PY" "$SCRIPTS/verify_tone_core_sync.py"

# 5) no-Anthropic scan (AF-AW-ANTHROPIC) — no concrete claude-*/anthropic/* MODEL
#    id anywhere in the SHIPPED skill. Deliberately-broken fixtures under
#    test-fixtures/attack/, broken-variants/, and drifted-prompts/ are EXCLUDED —
#    they exist precisely to prove the runtime gate rejects an Anthropic id.
echo "  -- no-Anthropic scan (AF-AW-ANTHROPIC) --"
if SKILL_DIR="$SKILL_DIR" "$PY" - <<'PY'
import os, re, sys
skill = os.environ["SKILL_DIR"]
pat = re.compile(r"claude-(?:opus|sonnet|haiku|instant|fable)\b"
                 r"|claude-\d"
                 r"|anthropic/[a-z]"
                 r"|us\.anthropic\.[a-z]")
SKIP_SEGMENTS = ("/test-fixtures/attack/", "/broken-variants/", "/drifted-prompts/")
hits = []
for root, dirs, files in os.walk(skill):
    dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
    for fn in files:
        p = os.path.join(root, fn)
        norm = "/" + os.path.relpath(p, skill).replace(os.sep, "/")
        if any(seg in norm for seg in SKIP_SEGMENTS):
            continue
        try:
            src = open(p, "r", errors="replace").read()
        except Exception:
            continue
        for m in pat.finditer(src):
            hits.append("%s: %s" % (os.path.relpath(p, skill), m.group(0)))
if hits:
    print("AF-AW-ANTHROPIC: concrete Anthropic model id(s) found in the shipped skill:", file=sys.stderr)
    for h in hits:
        print("    " + h, file=sys.stderr)
    sys.exit(2)
print("no concrete Anthropic model id in the shipped skill (excluding deliberately-broken fixtures)")
sys.exit(0)
PY
then
    printf '  [PASS] no-Anthropic scan (AF-AW-ANTHROPIC)\n'
else
    printf '  [FAIL] no-Anthropic scan (AF-AW-ANTHROPIC)\n'; fails=$((fails + 1))
fi

# 6) end-to-end golden pilot through the entry (a full pass issues a certificate).
echo "  -- golden pilot through anthology-entry.sh --"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/working"
for f in intake.json tone-doc.md title.json outline.md chapter.md RUN-LEDGER.json; do
    cp "$GOLD/$f" "$TMP/working/$f"
done
if bash "$SKILL_DIR/anthology-entry.sh" --run-dir "$TMP" >/dev/null 2>&1 \
   && [ -f "$TMP/delivery/PROCESS-CERTIFICATE.json" ]; then
    printf '  [PASS] golden pilot issues a process certificate\n'
else
    printf '  [FAIL] golden pilot did not issue a certificate\n'; fails=$((fails + 1))
fi

# 7) shipped worked example — regression-guard it in a THROWAWAY temp run-dir. A
#    full pass must (a) issue a certificate and (b) reproduce the SHIPPED
#    certificate_sha exactly (deterministic sha => idempotent).
echo "  -- shipped example golden-unbroken-ground through the entry (temp run-dir) --"
if [ -d "$EX" ]; then
    EXTMP="$(mktemp -d)"
    mkdir -p "$EXTMP/working"
    for f in intake.json tone-doc.md title.json outline.md chapter.md RUN-LEDGER.json; do
        cp "$EX/working/$f" "$EXTMP/working/$f"
    done
    if bash "$SKILL_DIR/anthology-entry.sh" --run-dir "$EXTMP" >/dev/null 2>&1 \
       && [ -f "$EXTMP/delivery/PROCESS-CERTIFICATE.json" ]; then
        FRESH_SHA="$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1]))["certificate_sha"])' "$EXTMP/delivery/PROCESS-CERTIFICATE.json" 2>/dev/null)"
        SHIP_SHA="$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1]))["certificate_sha"])' "$EX/delivery/PROCESS-CERTIFICATE.json" 2>/dev/null)"
        if [ -n "$FRESH_SHA" ] && [ "$FRESH_SHA" = "$SHIP_SHA" ]; then
            printf '  [PASS] example re-issues the SHIPPED certificate_sha (%s…)\n' "${SHIP_SHA:0:12}"
        else
            printf '  [FAIL] example certificate_sha drift (fresh=%s ship=%s)\n' "${FRESH_SHA:0:12}" "${SHIP_SHA:0:12}"
            fails=$((fails + 1))
        fi
    else
        printf '  [FAIL] shipped example did not issue a certificate\n'; fails=$((fails + 1))
    fi
    rm -rf "$EXTMP"

    # 8) shipped example broken-variants — each must trip its distinct AF (exit 2).
    echo "  -- shipped example broken-variants reject --"
    expect_reject "ex/intake-missing"       prove_aw_intake.py   "AF-AW-INTAKE-MISSING"    "$EBV/intake_missing.json"
    expect_reject "ex/intake-credential"    prove_aw_intake.py   "AF-AW-INTAKE-CREDENTIAL" "$EBV/intake_credential.json"
    expect_reject "ex/prompt-drift"         prove_aw_fidelity.py "AF-AW-PROMPT-DRIFT"      --prompts-dir "$EBV/drifted-prompts"
    expect_reject "ex/tone-3-influences"    prove_aw_tone.py     "AF-AW-TONE-4"            "$EBV/tone_three_influences.md"
    expect_reject "ex/tone-short"           prove_aw_tone.py     "AF-AW-TONE-FLOOR"        "$EBV/tone_short.md"
    expect_reject "ex/chapter-short"        prove_aw_chapter.py  "AF-AW-CHAP-LEN"          "$EBV/chapter_short.md" --mode chapter --title "$GOLD/title.json" --intake "$GOLD/intake.json"
    expect_reject "ex/chapter-ws-pad"       prove_aw_chapter.py  "AF-AW-CHAP-LEN"          "$EBV/chapter_whitespace_pad.md" --mode chapter --title "$GOLD/title.json" --intake "$GOLD/intake.json"
    expect_reject "ex/chapter-verify"       prove_aw_chapter.py  "AF-AW-VERIFY-BLOCK"      "$EBV/chapter_verify_missing.md" --mode chapter --title "$GOLD/title.json" --intake "$GOLD/intake.json"
    expect_reject "ex/chapter-subtitle"     prove_aw_chapter.py  "AF-AW-TITLE-LOCK"        "$EBV/chapter_subtitle_changed.md" --mode chapter --title "$GOLD/title.json" --intake "$GOLD/intake.json"
    expect_reject "ex/chapter-story"        prove_aw_chapter.py  "AF-AW-STORIES"           "$EBV/chapter_story_dropped.md" --mode chapter --title "$GOLD/title.json" --intake "$GOLD/intake.json"
    expect_reject "ex/chapter-placeholder"  prove_aw_chapter.py  "AF-AW-PLACEHOLDER"       "$EBV/chapter_placeholder.md" --mode chapter --title "$GOLD/title.json" --intake "$GOLD/intake.json"
    expect_reject "ex/ledger-anthropic"     aw_build_check.py    "AF-AW-ANTHROPIC"         "$EBV/ledger_anthropic.json"
    expect_reject "ex/ledger-rewrite"       aw_build_check.py    "AF-AW-REWRITE-BUDGET"    "$EBV/ledger_rewrite_over_budget.json"
else
    printf '  [WARN] examples/golden-unbroken-ground not present — skipping shipped-example checks\n'
fi

# 9) seeded-defect E2E — a short chapter must BLOCK the run and issue NO certificate.
echo "  -- seeded-defect E2E (short chapter -> no certificate) --"
DTMP="$(mktemp -d)"
mkdir -p "$DTMP/working"
for f in intake.json tone-doc.md title.json outline.md RUN-LEDGER.json; do
    cp "$GOLD/$f" "$DTMP/working/$f"
done
cp "$ATK/chapter_short.md" "$DTMP/working/chapter.md"
bash "$SKILL_DIR/anthology-entry.sh" --run-dir "$DTMP" >/dev/null 2>&1; e2e_rc=$?
if [ "$e2e_rc" -ne 0 ] && [ ! -f "$DTMP/delivery/PROCESS-CERTIFICATE.json" ]; then
    printf '  [PASS] seeded short chapter blocks the run; NO certificate issued (rc=%s)\n' "$e2e_rc"
else
    printf '  [FAIL] seeded defect did not block the run / a certificate leaked (rc=%s)\n' "$e2e_rc"
    fails=$((fails + 1))
fi
rm -rf "$DTMP"

# 10) ENGINE-PIN — the shipped ENGINE-PIN.sha256 must equal the computed hash of
#     the enforcement set, AND a tampered enforcement file must trip GATE 3
#     (AF-AW-HASH-PIN, exit 7) through the entry — proving the pin actually bites.
echo "  -- ENGINE-PIN hash pin (AF-AW-HASH-PIN) --"
ENFORCE_FILES=(
    "$SKILL_DIR/run_anthology.py"
    "$SCRIPTS/_aw_common.py"
    "$SCRIPTS/prove_aw_intake.py"
    "$SCRIPTS/prove_aw_fidelity.py"
    "$SCRIPTS/prove_aw_tone.py"
    "$SCRIPTS/prove_aw_chapter.py"
    "$SCRIPTS/aw_build_check.py"
    "$SCRIPTS/verify_tone_core_sync.py"
)
_sha_concat() {
    if command -v sha256sum >/dev/null 2>&1; then
        cat "$@" | sha256sum | awk '{print $1}'
    else
        cat "$@" | shasum -a 256 | awk '{print $1}'
    fi
}
PIN_FILE="$SKILL_DIR/ENGINE-PIN.sha256"
if [ -f "$PIN_FILE" ]; then
    COMPUTED="$(_sha_concat "${ENFORCE_FILES[@]}")"
    EXPECTED="$(tr -d ' \t\n' < "$PIN_FILE")"
    if [ -n "$EXPECTED" ] && [ "$EXPECTED" = "$COMPUTED" ]; then
        printf '  [PASS] ENGINE-PIN.sha256 matches the computed enforcement hash (%s…)\n' "${COMPUTED:0:12}"
    else
        printf '  [FAIL] ENGINE-PIN.sha256 drift (pinned=%s computed=%s)\n' "${EXPECTED:0:12}" "${COMPUTED:0:12}"
        fails=$((fails + 1))
    fi

    # negative: a tampered enforcement file must make the entry fail GATE 3 (exit 7).
    PTMP="$(mktemp -d)"
    cp -R "$SKILL_DIR/." "$PTMP/skill/"
    printf '\n# tamper — verify.sh negative test\n' >> "$PTMP/skill/run_anthology.py"
    PRD="$(mktemp -d)"; mkdir -p "$PRD/working"
    for f in intake.json tone-doc.md title.json outline.md chapter.md RUN-LEDGER.json; do
        cp "$GOLD/$f" "$PRD/working/$f"
    done
    bash "$PTMP/skill/anthology-entry.sh" --run-dir "$PRD" >/dev/null 2>&1; tamper_rc=$?
    if [ "$tamper_rc" -eq 7 ]; then
        printf '  [PASS] tampered enforcement file trips AF-AW-HASH-PIN at the entry (exit 7)\n'
    else
        printf '  [FAIL] tampered enforcement file did NOT trip the hash pin (rc=%s, expected 7)\n' "$tamper_rc"
        fails=$((fails + 1))
    fi
    rm -rf "$PTMP" "$PRD"
else
    printf '  [FAIL] ENGINE-PIN.sha256 not shipped — GATE 3 hash pin can never fail (S36-54)\n'
    fails=$((fails + 1))
fi

echo "=================================================="
if [ "$fails" -eq 0 ]; then
    echo "RESULT: PASS — all Skill 54 self-verification checks green."
    exit 0
fi
echo "RESULT: FAIL — $fails check(s) failed."
exit 1
