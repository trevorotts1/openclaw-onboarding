#!/usr/bin/env bash
# ==============================================================================
# 55-product-bio/verify.sh — Product Bio Engine self-verification gate.
# ------------------------------------------------------------------------------
# READ-ONLY and IDEMPOTENT (writes only under a temp run dir it removes; never
# mutates the skill tree, so it can run twice -> identical PASS). Exits NONZERO
# on ANY failure, so it can gate a merge / CI / a post-install check. Mirrors
# 50-email-engine/verify.sh and 51-signature-presentation/verify.sh.
#
#   1. the five provers --self-test            (built-in golden + attack fixtures)
#   2. golden reproduce                        (each prover PASSes the golden bundle)
#   3. broken-variants reject                  (each attack fixture trips its AF, exit 2)
#   4. prompt-fidelity pins                    (baked assets match recorded sha256)
#   5. no-Anthropic scan                       (AF-PB-ANTHROPIC: no claude-*/anthropic/* id)
#   6. end-to-end golden pilot through the entry (a full pass issues a certificate)
#
# Usage:  bash 55-product-bio/verify.sh
# Exit:   0 = all checks passed;  nonzero = at least one check failed.
# ==============================================================================
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS="$SKILL_DIR/scripts"
GOLD="$SKILL_DIR/test-fixtures/golden"
ATK="$SKILL_DIR/test-fixtures/attack"
EX="$SKILL_DIR/examples/golden-atlasflow"        # shipped worked example
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
        printf '  [PASS] reject %-26s -> %s\n' "$label" "$code"
    else
        printf '  [FAIL] reject %-26s (rc=%s, expected exit 2 + %s)\n' "$label" "$rc" "$code"
        printf '%s\n' "$out" | sed 's/^/         /'
        fails=$((fails + 1))
    fi
}

echo "== Skill 55 (Product Bio Engine) :: verify.sh =="

# 1) the five provers --self-test + the orchestrator gate self-test.
for p in prove_pb_intake prove_pb_fidelity prove_pb_wordcount prove_pb_sections prove_pb_html; do
    if [ -f "$SCRIPTS/$p.py" ]; then
        run "$p.py --self-test" "$PY" "$SCRIPTS/$p.py" --self-test
    else
        printf '  [FAIL] %s.py missing at %s\n' "$p" "$SCRIPTS"; fails=$((fails + 1))
    fi
done
run "run_product_bio.py --self-test" "$PY" "$SKILL_DIR/run_product_bio.py" --self-test

# 2) golden reproduce — each prover PASSes the golden bundle.
run "golden intake PASS"   "$PY" "$SCRIPTS/prove_pb_intake.py"   "$GOLD/intake.json"
run "golden fidelity PASS" "$PY" "$SCRIPTS/prove_pb_fidelity.py"
run "golden wordcount PASS" "$PY" "$SCRIPTS/prove_pb_wordcount.py" "$GOLD/product-bio.md"
run "golden sections PASS" "$PY" "$SCRIPTS/prove_pb_sections.py"  "$GOLD/product-bio.md"
run "golden html PASS"     "$PY" "$SCRIPTS/prove_pb_html.py"      "$GOLD/product-bio.html" --source-bio "$GOLD/product-bio.md"

# 3) broken-variants reject — each attack fixture trips its distinct AF (fail-closed proof).
expect_reject "intake-missing"       prove_pb_intake.py   "AF-PB-INTAKE-MISSING"  "$ATK/intake_missing.json"
expect_reject "prompt-drift"         prove_pb_fidelity.py "AF-PB-PROMPT-DRIFT"    --prompts-dir "$ATK/drifted-prompts"
expect_reject "wordcount-short"      prove_pb_wordcount.py "AF-PB-WORDCOUNT"      "$ATK/wordcount_short.md"
expect_reject "whitespace-padding"   prove_pb_wordcount.py "AF-PB-WORDCOUNT"      "$ATK/wordcount_whitespace_pad.md"
expect_reject "verify-block-missing" prove_pb_wordcount.py "AF-PB-VERIFY-BLOCK"   "$ATK/verify_block_missing.md"
expect_reject "section-missing"      prove_pb_sections.py "AF-PB-SECTION"         "$ATK/section_missing.md"
expect_reject "closes-23"            prove_pb_sections.py "AF-PB-CLOSES"          "$ATK/closes_23.md"
expect_reject "counts-short"         prove_pb_sections.py "AF-PB-COUNTS"          "$ATK/counts_short.md"
expect_reject "html-envelope"        prove_pb_html.py     "AF-PB-HTML-ENVELOPE"   "$ATK/html_envelope.html"
expect_reject "html-two-h1"          prove_pb_html.py     "AF-PB-HTML-H1"         "$ATK/html_two_h1.html"
expect_reject "html-css"             prove_pb_html.py     "AF-PB-HTML-CSS"        "$ATK/html_css.html"
expect_reject "html-loss"            prove_pb_html.py     "AF-PB-HTML-LOSS"       "$ATK/html_loss.html" --source-bio "$GOLD/product-bio.md"

# 4) prompt-fidelity pins (explicit, already covered above but named for clarity).
run "prompt-fidelity pins match" "$PY" "$SCRIPTS/prove_pb_fidelity.py"

# 5) no-Anthropic scan (AF-PB-ANTHROPIC) — no concrete claude-*/anthropic/* MODEL
#    id anywhere in the shipped skill (its own anti-Anthropic prose is not an id).
echo "  -- no-Anthropic scan (AF-PB-ANTHROPIC) --"
if SKILL_DIR="$SKILL_DIR" "$PY" - <<'PY'
import os, re, sys
skill = os.environ["SKILL_DIR"]
# Concrete Anthropic MODEL-ID shapes only (lowercase, as real config ids are) —
# NOT the words "Anthropic"/"claude-*" wildcards or "Anthropic/claude-*" prose
# used in this skill's own ban documentation. Case-SENSITIVE on purpose.
pat = re.compile(r"claude-(?:opus|sonnet|haiku|instant|fable)\b"
                 r"|claude-\d"
                 r"|anthropic/[a-z]"
                 r"|us\.anthropic\.[a-z]")
hits = []
for root, dirs, files in os.walk(skill):
    dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
    for fn in files:
        p = os.path.join(root, fn)
        try:
            src = open(p, "r", errors="replace").read()
        except Exception:
            continue
        for m in pat.finditer(src):
            rel = os.path.relpath(p, skill)
            hits.append("%s: %s" % (rel, m.group(0)))
if hits:
    print("AF-PB-ANTHROPIC: concrete Anthropic model id(s) found in the shipped skill:", file=sys.stderr)
    for h in hits:
        print("    " + h, file=sys.stderr)
    sys.exit(2)
print("no concrete Anthropic model id in the shipped skill")
sys.exit(0)
PY
then
    printf '  [PASS] no-Anthropic scan (AF-PB-ANTHROPIC)\n'
else
    printf '  [FAIL] no-Anthropic scan (AF-PB-ANTHROPIC)\n'; fails=$((fails + 1))
fi

# 6) end-to-end golden pilot through the entry (a full pass issues a certificate).
echo "  -- golden pilot through product-bio-entry.sh --"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/working"
cp "$GOLD/intake.json"      "$TMP/working/intake.json"
cp "$GOLD/product-bio.md"   "$TMP/working/product-bio.md"
cp "$GOLD/product-bio.html" "$TMP/working/product-bio.html"
if bash "$SKILL_DIR/product-bio-entry.sh" --run-dir "$TMP" >/dev/null 2>&1 \
   && [ -f "$TMP/delivery/PROCESS-CERTIFICATE.json" ]; then
    printf '  [PASS] golden pilot issues a process certificate\n'
else
    printf '  [FAIL] golden pilot did not issue a certificate\n'; fails=$((fails + 1))
fi

# 7) shipped worked example (examples/golden-atlasflow) — regression-guard it in a
#    THROWAWAY temp run-dir (read-only w.r.t. the skill tree). A full pass must (a)
#    issue a certificate and (b) reproduce the SHIPPED certificate_sha exactly
#    (deterministic sha => idempotent), proving the shipped example still holds.
echo "  -- shipped example golden-atlasflow through the entry (temp run-dir) --"
if [ -d "$EX" ]; then
    EXTMP="$(mktemp -d)"
    mkdir -p "$EXTMP/working"
    cp "$EX/working/intake.json"      "$EXTMP/working/intake.json"
    cp "$EX/working/product-bio.md"   "$EXTMP/working/product-bio.md"
    cp "$EX/working/product-bio.html" "$EXTMP/working/product-bio.html"
    if bash "$SKILL_DIR/product-bio-entry.sh" --run-dir "$EXTMP" >/dev/null 2>&1 \
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
    expect_reject "ex/intake-missing"     prove_pb_intake.py   "AF-PB-INTAKE-MISSING" "$EBV/intake_missing.json"
    expect_reject "ex/prompt-sha-mismatch" prove_pb_fidelity.py "AF-PB-PROMPT-DRIFT"   --prompts-dir "$EBV/drifted-prompts"
    expect_reject "ex/wordcount-short"    prove_pb_wordcount.py "AF-PB-WORDCOUNT"      "$EBV/wordcount_short.md"
    expect_reject "ex/whitespace-padding" prove_pb_wordcount.py "AF-PB-WORDCOUNT"      "$EBV/wordcount_whitespace_pad.md"
    expect_reject "ex/verify-block"       prove_pb_wordcount.py "AF-PB-VERIFY-BLOCK"   "$EBV/verify_block_missing.md"
    expect_reject "ex/section-missing"    prove_pb_sections.py "AF-PB-SECTION"         "$EBV/section_missing.md"
    expect_reject "ex/closes-23"          prove_pb_sections.py "AF-PB-CLOSES"          "$EBV/closes_23.md"
    expect_reject "ex/counts-short"       prove_pb_sections.py "AF-PB-COUNTS"          "$EBV/counts_short.md"
    expect_reject "ex/html-envelope"      prove_pb_html.py     "AF-PB-HTML-ENVELOPE"   "$EBV/html_envelope.html"
    expect_reject "ex/html-two-h1"        prove_pb_html.py     "AF-PB-HTML-H1"         "$EBV/html_two_h1.html"
    expect_reject "ex/html-css"           prove_pb_html.py     "AF-PB-HTML-CSS"        "$EBV/html_css.html"
    expect_reject "ex/html-loss"          prove_pb_html.py     "AF-PB-HTML-LOSS"       "$EBV/html_loss.html" --source-bio "$EX/working/product-bio.md"
else
    printf '  [WARN] examples/golden-atlasflow not present — skipping shipped-example checks\n'
fi

echo "=================================================="
if [ "$fails" -eq 0 ]; then
    echo "RESULT: PASS — all Skill 55 self-verification checks green."
    exit 0
fi
echo "RESULT: FAIL — $fails check(s) failed."
exit 1
