#!/usr/bin/env bash
# ==============================================================================
# 53-book-writer/verify.sh — Book Writer Engine self-verification gate.
# ------------------------------------------------------------------------------
# READ-ONLY and IDEMPOTENT (writes only under a temp run dir it removes; never
# mutates the skill tree, so it can run twice -> identical result). Exits NONZERO
# on ANY failure, so it can gate a merge / CI / a post-install check. Mirrors
# 55-product-bio/verify.sh + 52-avatar-alchemist/verify.sh.
#
#   1. the twelve provers --self-test        (built-in in-memory fixtures)
#   2. golden bundle PASS                     (each prover PASSes the golden bundle)   [prose-gated]
#   3. broken-variants reject                 (make_broken.py: each fixture trips its AF)
#   4. idempotency                            (re-run entry -> reproduce certificate_sha) [prose-gated]
#   5. tone-core lockstep                     (verify_tone_core_sync.py PASS)
#   6. shared_tone_core manifest key present
#   7. no-Anthropic + no-client-name + no-absolute-path scans over shipped files
#   8. version routing                        (version=book accepted; version=brand parks/handoff)
#
# Sections 2 + 4 are GATED on the presence of the Wave-2 golden prose + Agent D's
# assembled certificate; until then they print a TODO and do not fail the gate.
#
# Usage:  bash 53-book-writer/verify.sh
# Exit:   0 = all runnable checks passed;  nonzero = at least one check failed.
# ==============================================================================
set -uo pipefail

# This gate carries a bash shebang but is also invoked under zsh (bash -c AND
# zsh -c must both pass). zsh does NOT word-split unquoted parameters and aborts on
# an unmatched glob by default, which would silently skip the prover loop and trip
# the certificate lookup. Make those two behaviors bash-compatible, and below we
# additionally use an explicit array + find(1) so the gate is correct even if these
# setopts are unavailable. Belt and suspenders — exit code is identical in both shells.
if [ -n "${ZSH_VERSION:-}" ]; then
    setopt sh_word_split 2>/dev/null || true
    setopt nonomatch 2>/dev/null || true
fi

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SCRIPTS="$SKILL_DIR/scripts"
EX="$SKILL_DIR/examples/golden-marcus-halloway"
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

echo "== Skill 53 (Book Writer Engine) :: verify.sh =="

# An explicit array (not a space-joined string) so iteration never depends on
# word-splitting — bash and zsh both expand "${PROVERS[@]}" to the 12 elements.
PROVERS=(prove_bw_intake prove_bw_titlelock prove_bw_stories prove_bw_chapters
prove_bw_continuity prove_bw_tone prove_bw_challenge prove_bw_433
prove_bw_placeholder prove_bw_noanthropic prove_bw_anon prove_bw_process)

# 1) each prover --self-test.
echo "-- 1) prover self-tests --"
for p in "${PROVERS[@]}"; do
    if [ -f "$SCRIPTS/$p.py" ]; then
        run "$p.py --self-test" "$PY" "$SCRIPTS/$p.py" --self-test
    else
        printf '  [FAIL] %s.py missing at %s\n' "$p" "$SCRIPTS"; fails=$((fails + 1))
    fi
done

# 5) tone-core lockstep (runs now).
echo "-- 5) tone-core lockstep --"
run "verify_tone_core_sync.py" "$PY" "$SCRIPTS/verify_tone_core_sync.py"

# 6) shared_tone_core manifest key present.
echo "-- 6) shared_tone_core manifest key --"
if "$PY" -c 'import json,sys; m=json.load(open(sys.argv[1])); sys.exit(0 if m.get("shared_tone_core")=="shared-utils/tone-writing-core" else 1)' "$SKILL_DIR/BOOK-WRITER-MANIFEST.json"; then
    printf '  [PASS] shared_tone_core = shared-utils/tone-writing-core\n'
else
    printf '  [FAIL] shared_tone_core manifest key missing/wrong\n'; fails=$((fails + 1))
fi

# 3) broken-variants reject via make_broken.py (data-anchor variants now; prose ones when authored).
echo "-- 3) broken-variants fail-closed proof --"
if [ -f "$EBV/make_broken.py" ]; then
    RESULTS_TMP="$(mktemp)"
    if "$PY" "$EBV/make_broken.py" --results "$RESULTS_TMP" >/dev/null 2>&1; then
        printf '  [PASS] every PRESENT broken-variant rejects with its AF-BK code\n'
    else
        printf '  [FAIL] a broken-variant leaked (see make_broken.py output)\n'
        "$PY" "$EBV/make_broken.py" --results "$RESULTS_TMP" 2>&1 | sed 's/^/         /'
        fails=$((fails + 1))
    fi
    rm -f "$RESULTS_TMP"
else
    printf '  [WARN] make_broken.py missing — skipping\n'
fi

# 7) no-Anthropic / no-client-name / no-absolute-path scans over shipped files.
echo "-- 7) anti-pattern scans over shipped files --"
if SKILL_DIR="$SKILL_DIR" "$PY" - <<'PY'
import os, re, sys
skill = os.environ["SKILL_DIR"]
# concrete Anthropic MODEL-ID shapes only (lowercase config ids) — NOT the words
# "Anthropic"/"claude" used in this skill's own ban documentation.
anth = re.compile(r"claude-(?:opus|sonnet|haiku|instant|fable)\b|claude-\d|anthropic/[a-z]|us\.anthropic\.[a-z]")
# box-specific absolute paths must never be baked into shipped files. (Fragment-built
# so this scanner file does not self-match its own pattern.)
abspath = re.compile("/" + "Users/" + "|/home/[a-z]")
# DETECTION / FIXTURE files legitimately contain example ids + abspaths as their
# whole purpose (the no-Anthropic prover, the broken-variant generator + its result
# ledger, and this scanner). Allowlisted like 55's scan ignores its own ban logic.
DETECT_ALLOW = {"prove_bw_noanthropic.py", "make_broken.py",
                "REJECTION-RESULTS.json", "verify.sh"}
hits = []
for root, dirs, files in os.walk(skill):
    dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
    for fn in files:
        if fn in DETECT_ALLOW:
            continue
        p = os.path.join(root, fn)
        rel = os.path.relpath(p, skill)
        try:
            src = open(p, "r", errors="replace").read()
        except Exception:
            continue
        for m in anth.finditer(src):
            hits.append("ANTHROPIC %s: %s" % (rel, m.group(0)))
        for m in abspath.finditer(src):
            hits.append("ABSPATH %s: %s" % (rel, m.group(0)))
if hits:
    print("anti-pattern scan FAILED:", file=sys.stderr)
    for h in hits:
        print("    " + h, file=sys.stderr)
    sys.exit(2)
print("no concrete Anthropic model id, no baked absolute path in the shipped skill")
sys.exit(0)
PY
then
    printf '  [PASS] no-Anthropic + no-absolute-path scan\n'
else
    printf '  [FAIL] anti-pattern scan tripped\n'; fails=$((fails + 1))
fi
# anon lint over the shipped tree with a representative REAL-client-shaped denylist
# supplied via a temp file (so the token strings never appear in the tree itself,
# which would self-match). The tree uses fictional names only -> must find nothing.
TOKENS_TMP="$(mktemp)"
# tokens assembled from fragments at runtime so the contiguous phrases never appear
# as literals in this (shipped) file, which would self-match the very lint they drive.
printf '%s %s\n%s %s\n' 'Contoso' 'Pharmaceuticals' 'Globex' 'Dynamics' > "$TOKENS_TMP"
run "anon lint (no real-client token in shipped tree)" \
    "$PY" "$SCRIPTS/prove_bw_anon.py" --dir "$SKILL_DIR" --tokens-file "$TOKENS_TMP"
rm -f "$TOKENS_TMP"

# 8) version routing.
echo "-- 8) version routing --"
run "version=book intake accepted" "$PY" "$SCRIPTS/prove_bw_intake.py" "$EX/run/intake.json"
if BRAND="$(mktemp)"; then
    "$PY" - "$BRAND" <<'PY'
import json, sys
json.dump({"version":"brand","first_name":"Jordan","last_name":"Rivers",
           "ideal_avatar":"founders","niche":"coaching","primary_goal":"launch",
           "tone_style_1":"Maya Angelou","tone_style_2":"N/A","tone":"warm"}, open(sys.argv[1],"w"))
PY
    # version=brand WITHOUT a brand-skill route must PARK (rc 2 + AF-BK-VERSION)
    OUT="$("$PY" "$SCRIPTS/prove_bw_intake.py" "$BRAND" 2>&1)"; RC=$?
    if [ "$RC" -eq 2 ] && printf '%s' "$OUT" | grep -q "AF-BK-VERSION"; then
        printf '  [PASS] version=brand parks fail-closed (never runs the book pipeline)\n'
    else
        printf '  [FAIL] version=brand did not park (rc=%s)\n' "$RC"; fails=$((fails + 1))
    fi
    # version=brand WITH the brand-skill route present must PASS (hand-off)
    run "version=brand routes with --brand-skill-present" \
        "$PY" "$SCRIPTS/prove_bw_intake.py" "$BRAND" --brand-skill-present
    rm -f "$BRAND"
fi

# 2) golden bundle PASS + 4) idempotency — GATED on Wave-2 prose + Agent D's assembled cert.
echo "-- 2/4) golden bundle + idempotency (prose-gated) --"
# find(1) does its own matching (no shell glob), so an absent delivery/ never aborts
# under zsh's nomatch and never leaks a literal glob under bash.
SHIP_CERT="$(find "$EX/delivery" -maxdepth 2 -name PROCESS-CERTIFICATE.json 2>/dev/null | head -1)"
if [ -f "$EX/run/chapters/ch12.md" ] && [ -n "$SHIP_CERT" ]; then
    TMP="$(mktemp -d)"
    DLROOT="$(mktemp -d)"   # keep the labeled ~/Downloads copy OUT of the real ~/Downloads
    trap 'rm -rf "$TMP" "$DLROOT"' EXIT
    mkdir -p "$TMP/run"
    cp -R "$EX/run/." "$TMP/run/"
    if BOOK_WRITER_DELIVERY_ROOT="$DLROOT" bash "$SKILL_DIR/book-writer-entry.sh" --run-dir "$TMP" >/dev/null 2>&1; then
        FRESH="$(find "$TMP/delivery" -maxdepth 2 -name PROCESS-CERTIFICATE.json 2>/dev/null | head -1)"
        if [ -n "$FRESH" ]; then
            FSHA="$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1]))["certificate_sha"])' "$FRESH")"
            SSHA="$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1]))["certificate_sha"])' "$SHIP_CERT")"
            if [ "$FSHA" = "$SSHA" ]; then
                printf '  [PASS] golden re-issues the SHIPPED certificate_sha (%s…)\n' "${SSHA:0:12}"
            else
                printf '  [FAIL] certificate_sha drift (fresh=%s ship=%s)\n' "${FSHA:0:12}" "${SSHA:0:12}"; fails=$((fails + 1))
            fi
        else
            printf '  [FAIL] golden pilot did not issue a certificate\n'; fails=$((fails + 1))
        fi
    else
        printf '  [FAIL] golden pilot through the entry failed\n'; fails=$((fails + 1))
    fi
    rm -rf "$TMP" "$DLROOT"; trap - EXIT
else
    printf '  [TODO] golden prose / shipped certificate absent — Wave-2 authors prose, Agent D runs\n'
    printf '         run_book_writer.py to assemble the bundle + mint the certificate, then this\n'
    printf '         section lights up (golden-bundle PASS + certificate_sha idempotency).\n'
fi

# 9) role-SOP registry (content_sha re-stamp gate) — the 7 role SOPs are registered
# in roles/_index.json with a canonical content_sha, the dispatcher is named, and no
# stored sha is stale vs the file on disk.
echo "-- 9) role-SOP registry (content_sha) --"
run "roles/_index.json complete + not stale" "$PY" "$SCRIPTS/hash_role_index.py" --check

# 10) Command Center department-slug regression (FIX-BK-DEPT-01) — the mc_board
# department= wired in run_book_writer.py must be a REAL, already-seeded canonical
# department (never a fabricated slug like the historic "books" bug: mc_board.py
# fails SOFT on an unrecognized department_slug, so a fabricated value never throws
# and every card is silently dropped/misrouted).
echo "-- 10) Command Center department-slug regression --"
run "test_department_slug.py" "$PY" "$SCRIPTS/test_department_slug.py"

echo "=================================================="
if [ "$fails" -eq 0 ]; then
    echo "RESULT: PASS — all runnable Skill 53 self-verification checks green."
    exit 0
fi
echo "RESULT: FAIL — $fails check(s) failed."
exit 1
