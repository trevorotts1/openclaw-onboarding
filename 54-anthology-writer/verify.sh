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
#  10. negative attack-vector E2E fixtures (AF-AW-OVERRIDE-UNLOGGED,
#      AF-AW-ENTRY-BYPASS .js sender, AF-AW-UNRESOLVED-MODELMAP placeholder map)
#  11. ENGINE-PIN hash pin + tamper negative
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

# Redirect the labeled ~/Downloads deliverable into a THROWAWAY root so verify.sh
# NEVER writes into the operator's real ~/Downloads (state-path discipline — the
# Skill-23 lesson; mirrors 55-product-bio/verify.sh). The end-to-end pilots below
# run run_anthology.py through the entry, which assembles the ~/Downloads bundle.
export ANTHOLOGY_DELIVERY_ROOT="$(mktemp -d)"

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
for p in prove_aw_intake prove_aw_avatar prove_aw_fidelity prove_aw_tone prove_aw_chapter aw_build_check prove_aw_model_role; do
    if [ -f "$SCRIPTS/$p.py" ]; then
        run "$p.py --self-test" "$PY" "$SCRIPTS/$p.py" --self-test
    else
        printf '  [FAIL] %s.py missing at %s\n' "$p" "$SCRIPTS"; fails=$((fails + 1))
    fi
done
run "run_anthology.py --self-test" "$PY" "$SKILL_DIR/run_anthology.py" --self-test
run "board-contract suite (test_cc_contract.py)" "$PY" "$SKILL_DIR/test_cc_contract.py"

# 2) golden reproduce — each prover PASSes the golden bundle.
run "golden intake PASS"    "$PY" "$SCRIPTS/prove_aw_intake.py"   "$GOLD/intake.json"
run "golden avatar PASS"    "$PY" "$SCRIPTS/prove_aw_avatar.py"   "$GOLD/avatar.md"
run "golden fidelity PASS"  "$PY" "$SCRIPTS/prove_aw_fidelity.py"
run "golden tone-core sync" "$PY" "$SCRIPTS/verify_tone_core_sync.py"
run "golden tone PASS"      "$PY" "$SCRIPTS/prove_aw_tone.py"      "$GOLD/tone-doc.md"
run "golden chapter PASS"   "$PY" "$SCRIPTS/prove_aw_chapter.py"   "$GOLD/chapter.md" --mode chapter --title "$GOLD/title.json" --intake "$GOLD/intake.json"
run "golden outline PASS"   "$PY" "$SCRIPTS/prove_aw_chapter.py"   "$GOLD/outline.md" --mode outline --title "$GOLD/title.json" --intake "$GOLD/intake.json"
run "golden build-check PASS" "$PY" "$SCRIPTS/aw_build_check.py"   "$GOLD/RUN-LEDGER.json"
run "golden model-role PASS"  "$PY" "$SCRIPTS/prove_aw_model_role.py" "$GOLD/RUN-LEDGER.json" "$GOLD/model-map.json"

# 3) broken-variants reject — each attack fixture trips its distinct AF (fail-closed proof).
expect_reject "intake-missing"        prove_aw_intake.py   "AF-AW-INTAKE-MISSING"    "$ATK/intake_missing.json"
expect_reject "intake-credential"     prove_aw_intake.py   "AF-AW-INTAKE-CREDENTIAL" "$ATK/intake_credential.json"
expect_reject "intake-bool-false"     prove_aw_intake.py   "AF-AW-INTAKE-TYPE"       "$ATK/intake_bool_false.json"
expect_reject "intake-num-zero"       prove_aw_intake.py   "AF-AW-INTAKE-TYPE"       "$ATK/intake_num_zero.json"
expect_reject "intake-num-42"         prove_aw_intake.py   "AF-AW-INTAKE-TYPE"       "$ATK/intake_num_42.json"
expect_reject "avatar-missing"        prove_aw_avatar.py   "AF-AW-AVATAR-MISSING"        "$ATK/avatar_empty.md"
expect_reject "avatar-handoff-drift"  prove_aw_avatar.py   "AF-AW-AVATAR-HANDOFF-DRIFT"  "$GOLD/avatar.md" --skill52-dir "$ATK/drifted-skill52"
expect_reject "avatar-copied"         prove_aw_avatar.py   "AF-AW-AVATAR-COPIED"         "$GOLD/avatar.md" --scan-root "$ATK/copied-skill52-tree"
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
expect_reject "model-role-anthropic"   prove_aw_model_role.py "AF-AW-MODEL-ROLE"        "$ATK/ledger_anthropic.json" "$GOLD/model-map.json"
expect_reject "model-role-not-in-map"  prove_aw_model_role.py "AF-AW-MODEL-ROLE"        "$ATK/ledger_model_not_in_map.json" "$GOLD/model-map.json"

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
trap 'rm -rf "$TMP" "${ANTHOLOGY_DELIVERY_ROOT:-}" "${EXTMP:-}" "${DTMP:-}" "${PTMP:-}" "${PRD:-}"' EXIT
mkdir -p "$TMP/working"
for f in intake.json avatar.md tone-doc.md title.json outline.md chapter.md blurb.md RUN-LEDGER.json; do
    cp "$GOLD/$f" "$TMP/working/$f"
done
cp "$GOLD/model-map.json" "$TMP/model-map.json"
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
    for f in intake.json avatar.md tone-doc.md title.json outline.md chapter.md blurb.md RUN-LEDGER.json; do
        cp "$EX/working/$f" "$EXTMP/working/$f"
    done
    cp "$GOLD/model-map.json" "$EXTMP/model-map.json"
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
for f in intake.json avatar.md tone-doc.md title.json outline.md RUN-LEDGER.json; do
    cp "$GOLD/$f" "$DTMP/working/$f"
done
cp "$GOLD/model-map.json" "$DTMP/model-map.json"
cp "$ATK/chapter_short.md" "$DTMP/working/chapter.md"
e2e_out="$(bash "$SKILL_DIR/anthology-entry.sh" --run-dir "$DTMP" 2>&1)"; e2e_rc=$?
no_cert=; [ ! -f "$DTMP/delivery/PROCESS-CERTIFICATE.json" ] && no_cert=1
af_found=; printf '%s' "$e2e_out" | grep -q "AF-AW-CHAP-LEN" && af_found=1
if [ "$e2e_rc" -eq 2 ] && [ -n "$af_found" ] && [ -n "$no_cert" ]; then
    printf '  [PASS] seeded short chapter blocks the run (rc=2, AF-AW-CHAP-LEN); NO certificate issued\n'
else
    reason=
    [ "$e2e_rc" -ne 2 ] && reason="${reason}rc=$e2e_rc(expected 2) "
    [ -z "$af_found" ]  && reason="${reason}AF-AW-CHAP-LEN missing "
    [ -z "$no_cert" ]   && reason="${reason}certificate leaked "
    printf '  [FAIL] seeded defect did not block correctly: %s\n' "$reason"
    printf '%s\n' "$e2e_out" | sed 's/^/         /'
    fails=$((fails + 1))
fi
rm -rf "$DTMP"

# 10) doc-consistency — the intake template fields match the schema required fields.
echo "  -- doc-consistency (template fields match schema required fields) --"
if CD_SKILL_DIR="$SKILL_DIR" "$PY" - <<'PY'
import json, os, re, sys
skill = os.environ["CD_SKILL_DIR"]
schema_path = os.path.join(skill, "intake", "aw-intake-schema.json")
template_path = os.path.join(skill, "intake", "aw-intake-template.md")
with open(schema_path) as f: schema = json.load(f)
schema_required = set(schema["required"])
schema_fields = set(schema["properties"].keys())
with open(template_path) as f: template = f.read()
template_fields = set(m.group(1) for m in re.finditer(r'"(\w+)"\s*:', template))
missing = schema_required - template_fields
# Only flag template fields NOT in schema (template having extra things schema doesn't know about).
# Schema fields that are optional but NOT in the template are fine.
extra = template_fields - schema_fields
if missing or extra:
    if missing:
        print("MISSING from template (required by schema, not in template):", sorted(missing), file=sys.stderr)
    if extra:
        print("EXTRA in template (in template but not in schema):", sorted(extra), file=sys.stderr)
    sys.exit(2)
print("doc-consistency: all %d required schema fields present in template" % len(schema_required))
sys.exit(0)
PY
then
    printf '  [PASS] doc-consistency (template fields match schema)\n'
else
    printf '  [FAIL] doc-consistency (template fields do not match schema)\n'; fails=$((fails + 1))
fi

# 10b) negative attack-vector E2E fixtures (AF-AW-OVERRIDE-UNLOGGED,
#     AF-AW-ENTRY-BYPASS, AF-AW-UNRESOLVED-MODELMAP) — three additional attack
#     vectors that had no automated fixtures; each must trip its expected exit code.
# (a) AF-AW-OVERRIDE-UNLOGGED — an owner override with no log entry must NOT bypass
#     a gate. We plant the GATE-2 bypass trigger (upload.sh referencing slack.com)
#     AND an unlogged override; the gate must still fire (exit nonzero) because the
#     override is missing approved_by/reason.
echo "  -- AF-AW-OVERRIDE-UNLOGGED negative E2E (.json fixture in checkpoints/) --"
OVTMP="$(mktemp -d)"
mkdir -p "$OVTMP/working/checkpoints"
for f in intake.json avatar.md tone-doc.md title.json outline.md chapter.md blurb.md RUN-LEDGER.json; do
    cp "$GOLD/$f" "$OVTMP/working/$f"
done
cp "$SKILL_DIR/test-fixtures/working/upload.sh" "$OVTMP/working/"
cp "$ATK/owner_override.json" "$OVTMP/working/checkpoints/process_manifest.json"
bash "$SKILL_DIR/anthology-entry.sh" --run-dir "$OVTMP" >/dev/null 2>&1; ov_rc=$?
if [ "$ov_rc" -ne 0 ] && [ ! -f "$OVTMP/delivery/PROCESS-CERTIFICATE.json" ]; then
    printf '  [PASS] AF-AW-OVERRIDE-UNLOGGED: unlogged override does NOT bypass gate (rc=%s)\n' "$ov_rc"
else
    printf '  [FAIL] AF-AW-OVERRIDE-UNLOGGED: unlogged override bypassed the gate (rc=%s)\n' "$ov_rc"
    fails=$((fails + 1))
fi
rm -rf "$OVTMP"

# (b) AF-AW-ENTRY-BYPASS — a .js sender with fetch to slack.com/api must trip exit 5.
#     The bypass scanner (GATE 2) regex-matches slack\.com/api in any non-canonical
#     file under the run dir.
echo "  -- AF-AW-ENTRY-BYPASS .js sender negative E2E --"
BPTMP="$(mktemp -d)"
mkdir -p "$BPTMP/working"
for f in intake.json avatar.md tone-doc.md title.json outline.md chapter.md blurb.md RUN-LEDGER.json; do
    cp "$GOLD/$f" "$BPTMP/working/$f"
done
cp "$ATK/bypass_notify.js" "$BPTMP/working/"
bash "$SKILL_DIR/anthology-entry.sh" --run-dir "$BPTMP" >/dev/null 2>&1; bp_rc=$?
if [ "$bp_rc" -eq 5 ] && [ ! -f "$BPTMP/delivery/PROCESS-CERTIFICATE.json" ]; then
    printf '  [PASS] AF-AW-ENTRY-BYPASS: .js sender trips exit 5\n'
else
    printf '  [FAIL] AF-AW-ENTRY-BYPASS: .js sender did not trip exit 5 (rc=%s)\n' "$bp_rc"
    fails=$((fails + 1))
fi
rm -rf "$BPTMP"

# (c) AF-AW-UNRESOLVED-MODELMAP — a model-map.json with <CLIENT_PROVIDER_ID> and
#     <CLIENT_MODEL> placeholders must trip exit 8 through the preflight --check
#     pre-gate (GATE 1b).
echo "  -- AF-AW-UNRESOLVED-MODELMAP negative E2E (placeholder map) --"
MPTMP="$(mktemp -d)"
mkdir -p "$MPTMP/working"
for f in intake.json avatar.md tone-doc.md title.json outline.md chapter.md blurb.md RUN-LEDGER.json; do
    cp "$GOLD/$f" "$MPTMP/working/$f"
done
cp "$ATK/model_map_unresolved.json" "$MPTMP/model-map.json"
bash "$SKILL_DIR/anthology-entry.sh" --run-dir "$MPTMP" >/dev/null 2>&1; mp_rc=$?
if [ "$mp_rc" -eq 8 ] && [ ! -f "$MPTMP/delivery/PROCESS-CERTIFICATE.json" ]; then
    printf '  [PASS] AF-AW-UNRESOLVED-MODELMAP: placeholder map trips exit 8\n'
else
    printf '  [FAIL] AF-AW-UNRESOLVED-MODELMAP: placeholder map did not trip exit 8 (rc=%s)\n' "$mp_rc"
    fails=$((fails + 1))
fi
rm -rf "$MPTMP"

# 11) ENGINE-PIN — the shipped ENGINE-PIN.sha256 must equal the computed hash of
#     the enforcement set, AND a tampered enforcement file must trip GATE 3
#     (AF-AW-HASH-PIN, exit 7) through the entry — proving the pin actually bites.
echo "  -- ENGINE-PIN hash pin (AF-AW-HASH-PIN) --"
ENFORCE_FILES=()
while IFS= read -r f; do
    [ -n "$f" ] && ENFORCE_FILES+=("$SKILL_DIR/$f")
done < "$SCRIPTS/ENFORCEMENT-FILES.list"
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
    cp "$GOLD/model-map.json" "$PRD/model-map.json"
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

# 11) artifact-presence sweep — every SKILL.md-listed shipped artifact must exist.
echo "  -- artifact-presence sweep --"
ARTIFACTS=(
    "$SKILL_DIR/anthology-entry.sh"
    "$SKILL_DIR/ANTHOLOGY-MANIFEST.json"
    "$SKILL_DIR/CHANGELOG.md"
    "$SKILL_DIR/ENGINE-PIN.sha256"
    "$SKILL_DIR/INSTRUCTIONS.md"
    "$SKILL_DIR/MASTERDOC.md"
    "$SKILL_DIR/mc_board.py"
    "$SKILL_DIR/preflight.sh"
    "$SKILL_DIR/REPAIRS.md"
    "$SKILL_DIR/run_anthology.py"
    "$SKILL_DIR/skill-version.txt"
    "$SKILL_DIR/SKILL.md"
    "$SKILL_DIR/verify.sh"
    "$SKILL_DIR/verify-deps.sh"
    "$SKILL_DIR/intake/aw-intake-schema.json"
    "$SKILL_DIR/intake/aw-intake-template.md"
    "$SKILL_DIR/roles/anthology-writer.role.md"
    "$SKILL_DIR/assets/model-map.template.json"
    "$SKILL_DIR/assets/prompts/06-suggested-titles.md"
    "$SKILL_DIR/assets/prompts/07-book-blurb.md"
    "$SKILL_DIR/assets/prompts/08-create-outline.md"
    "$SKILL_DIR/assets/prompts/09-write-chapter.md"
    "$SKILL_DIR/assets/prompts/10-chapter-rewrite.md"
    "$SKILL_DIR/scripts/_aw_common.py"
    "$SKILL_DIR/scripts/prove_aw_intake.py"
    "$SKILL_DIR/scripts/prove_aw_avatar.py"
    "$SKILL_DIR/scripts/prove_aw_fidelity.py"
    "$SKILL_DIR/scripts/prove_aw_tone.py"
    "$SKILL_DIR/scripts/prove_aw_chapter.py"
    "$SKILL_DIR/scripts/aw_build_check.py"
    "$SKILL_DIR/scripts/verify_tone_core_sync.py"
    "$SKILL_DIR/test_cc_contract.py"
)
for af in "${ARTIFACTS[@]}"; do
    if [ -f "$af" ]; then
        printf '  [PASS] artifact %s\n' "${af#$SKILL_DIR/}"
    else
        printf '  [FAIL] artifact %s MISSING\n' "${af#$SKILL_DIR/}"
        fails=$((fails + 1))
    fi
done

# 12) mc_board.py byte-identity — the vendored copy is a CLONE of the canonical
#     50-email-engine copy; any drift (stale pre-U100 fork, hand-edited
#     divergences, accidental one-sided patch) is a hard failure.
echo "  -- mc_board.py byte-identity vs canonical 50-email-engine --"
run "mc_board.py byte-identical" diff "$SKILL_DIR/mc_board.py" "$SKILL_DIR/../50-email-engine/mc_board.py"

# 13) department-consistency — all three artifacts (SKILL.md, roles/anthology-writer.role.md,
#     run_anthology.py) must reference the same Kanban department ("marketing").
echo "  -- department-consistency check --"
DEPT_REF="marketing"
skill_dep=$(grep -o '\*\*marketing\*\*' "$SKILL_DIR/SKILL.md" 2>/dev/null | head -1)
role_dep=$(grep -o 'Department:\*\* marketing' "$SKILL_DIR/roles/anthology-writer.role.md" 2>/dev/null | head -1)
py_dep=$(grep -o 'department="marketing"' "$SKILL_DIR/run_anthology.py" 2>/dev/null | head -1)
if [ -n "$skill_dep" ] && [ -n "$role_dep" ] && [ -n "$py_dep" ]; then
    printf '  [PASS] department-consistency: all three artifacts reference "%s"\n' "$DEPT_REF"
else
    printf '  [FAIL] department-consistency: not all three artifacts reference "%s" (SKILL.md=%s role.md=%s run_anthology.py=%s)\n' \
        "$DEPT_REF" "${skill_dep:-MISSING}" "${role_dep:-MISSING}" "${py_dep:-MISSING}"
fi

# 14) version-consistency — ANTHOLOGY-MANIFEST.json skill_version equals
#     skill-version.txt content equals SKILL.md frontmatter version equals
#     latest CHANGELOG.md entry (version-of-record SINGLE SOURCE OF TRUTH gate).
echo "  -- version-consistency check --"
MANIFEST_VER=$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1]))["skill_version"])' "$SKILL_DIR/ANTHOLOGY-MANIFEST.json" 2>/dev/null)
TXT_VER=$(tr -d ' \t\n' < "$SKILL_DIR/skill-version.txt" 2>/dev/null)
SKILLMD_VER=$(head -10 "$SKILL_DIR/SKILL.md" | grep '^version:' | sed 's/version: *//' | tr -d ' \t\n' 2>/dev/null)
CHANGELOG_VER=$(head -5 "$SKILL_DIR/CHANGELOG.md" | grep -E '^## [0-9]' | head -1 | sed 's/^## *//' | sed 's/ .*//' | tr -d '\n' 2>/dev/null)
ver_fails=0
for pair in "ANTHOLOGY-MANIFEST.json:$MANIFEST_VER" "skill-version.txt:$TXT_VER" "SKILL.md:$SKILLMD_VER" "CHANGELOG.md:$CHANGELOG_VER"; do
    src="${pair%%:*}" val="${pair##*:}"
    if [ -z "$val" ]; then
        printf '  [FAIL] version-consistency: could not extract version from %s\n' "$src"
        ver_fails=$((ver_fails + 1))
    fi
done
if [ "$ver_fails" -gt 0 ]; then
    fails=$((fails + 1))
elif [ "$MANIFEST_VER" = "$TXT_VER" ] && [ "$TXT_VER" = "$SKILLMD_VER" ] && [ "$SKILLMD_VER" = "$CHANGELOG_VER" ]; then
    printf '  [PASS] version-consistency: all four surfaces read %s\n' "$MANIFEST_VER"
else
    printf '  [FAIL] version-consistency drift: manifest=%s txv=%s skillmd=%s changelog=%s\n' "$MANIFEST_VER" "$TXT_VER" "$SKILLMD_VER" "$CHANGELOG_VER"
    fails=$((fails + 1))
fi

# 15) claim-before-act concurrent-entries lock (FIX-15)
#    Pre-create the .anthology.lock dir so the entry sees contention, then
#    launch anthology-entry.sh — it MUST abort with the lock-held message (exit 9).
echo "  -- claim-before-act lock (FIX-15) --"
if [ -f "$GOLD/intake.json" ]; then
    TMP="$(mktemp -d)"
    trap 'rm -rf "$TMP"' EXIT
    mkdir -p "$TMP/working"
    for f in intake.json tone-doc.md title.json outline.md chapter.md blurb.md RUN-LEDGER.json; do
        if [ -f "$GOLD/$f" ]; then
            cp "$GOLD/$f" "$TMP/working/$f"
        fi
    done

    # Pre-create the lock dir to simulate a held lock.
    LOCK_DIR="$TMP/.anthology.lock"
    mkdir "$LOCK_DIR"
    echo "99999" > "$LOCK_DIR/pid"

    second_out="$(bash "$SKILL_DIR/anthology-entry.sh" --run-dir "$TMP" 2>&1; echo "EXIT:$?")"
    second_rc="$(echo "$second_out" | tail -1 | sed 's/^EXIT://')"
    second_out="$(echo "$second_out" | sed '$d')"
    rm -rf "$LOCK_DIR"

    if [ "$second_rc" -eq 9 ] && echo "$second_out" | grep -q "Another agent holds this run dir"; then
        printf '  [PASS] entry aborts with lock-held message when another agent holds the lock (rc=9)\n'
    else
        printf '  [FAIL] entry did not abort as expected (rc=%s, expected 9; output=%s)\n' "$second_rc" "$second_out"
        fails=$((fails + 1))
    fi

    # Now run again WITHOUT a contended lock — the entry must NOT exit 9, proving
    # the lock is acquired and released cleanly.
    clean_out="$(bash "$SKILL_DIR/anthology-entry.sh" --run-dir "$TMP" 2>&1; echo "EXIT:$?")"
    clean_rc="$(echo "$clean_out" | tail -1 | sed 's/^EXIT://')"
    clean_out="$(echo "$clean_out" | sed '$d')"
    rm -rf "$TMP"
    trap '' EXIT
    if [ "$clean_rc" -ne 9 ]; then
        printf '  [PASS] entry after lock release does NOT exit 9 (rc=%s) — lock cleaned up\n' "$clean_rc"
    else
        printf '  [FAIL] entry after lock release still exits 9 — stale lock\n'
        fails=$((fails + 1))
    fi
else
    printf '  [SKIP] golden fixtures not found (%s) — skipping concurrent lock test\n' "$GOLD/intake.json"
fi

# 16) FIX-18 — owner_skip_approval clobber + wildcard gate "*" rejection.
#     (a) _write_proc() must MERGE existing owner_skip_approvals, not clobber them.
#     (b) A {gate:"*"} token must be REJECTED (one record disarming every gate).
echo "  -- FIX-18: owner_skip_approval survives _write_proc() + wildcard rejection --"

# (a) clobber: seed a valid token, call _write_proc() with a fresh dict, assert
#     the token is still present.
_clobber_out="$(SKILL_DIR="$SKILL_DIR" "$PY" -c '
import json, sys, os, tempfile
from pathlib import Path
td = Path(tempfile.mkdtemp())
pm = td / "working" / "checkpoints" / "process_manifest.json"
pm.parent.mkdir(parents=True)
pm.write_text(json.dumps({
    "owner_skip_approvals": [{"gate":"AF-AW-HASH-PIN","approved":True,
                              "approved_by":"operator1","reason":"known good drift"}]
}), encoding="utf-8")
sys.path.insert(0, os.environ["SKILL_DIR"])
from run_anthology import _write_proc
_write_proc(td, {"skill":"test","phases":[]}, failed=None)
result = json.loads(pm.read_text(encoding="utf-8"))
token = result.get("owner_skip_approvals") or result.get("owner_skip_approval")
if isinstance(token, list) and len(token) == 1 and token[0].get("gate") == "AF-AW-HASH-PIN":
    print("PASS: owner_skip_approval survived _write_proc merge")
    sys.exit(0)
else:
    print("FAIL: owner_skip_approval was clobbered; result=%s" % token)
    sys.exit(1)
' 2>&1)"; _clobber_rc=$?
if [ "$_clobber_rc" -eq 0 ]; then
    printf '  [PASS] FIX-18 clobber: owner_skip_approval survives _write_proc()\n'
else
    printf '  [FAIL] FIX-18 clobber: %s\n' "$_clobber_out"
    fails=$((fails + 1))
fi

# (b) wildcard: a {gate:"*"} token must be REJECTED at the entry.  Exercise
#     the REAL production path — copy skill dir to a temp, seed a wildcard
#     process_manifest.json, tamper one enforcement file to trip the hash pin,
#     and run anthology-entry.sh so the rejection travels through gate_fail +
#     owner_skip_approved, not a hollow inline reimplementation.
WTMP="$(mktemp -d)"
cp -R "$SKILL_DIR/." "$WTMP/skill/"
printf '\n# tamper — verify.sh FIX-18 wildcard test\n' >> "$WTMP/skill/run_anthology.py"
WRD="$(mktemp -d)"; mkdir -p "$WRD/working/checkpoints"
"$PY" -c "
import json
manifest = {
    'owner_skip_approvals': [{
        'gate': '*', 'approved': True,
        'approved_by': 'bad-actor', 'reason': 'disarm everything'
    }]
}
with open('$WRD/working/checkpoints/process_manifest.json', 'w') as f:
    json.dump(manifest, f)
"
for f in intake.json tone-doc.md title.json outline.md chapter.md RUN-LEDGER.json; do
    cp "$GOLD/$f" "$WRD/working/$f"
done
_wildcard_out="$(bash "$WTMP/skill/anthology-entry.sh" --run-dir "$WRD" 2>&1)"; _wildcard_rc=$?
# owner_skip_approved exits 2 internally, but gate_fail catches it and returns 7
# from the hash-pin gate. The wildcard rejection message IS printed to stderr.
if [ "$_wildcard_rc" -eq 7 ] && printf '%s' "$_wildcard_out" | grep -q "wildcard"; then
    printf '  [PASS] FIX-18 wildcard: {gate:"*"} rejected through production path (exit 7, wildcard spawned)\n'
else
    printf '  [FAIL] FIX-18 wildcard: rc=%s (expected 7 + wildcard rejection); output:\n' "$_wildcard_rc"
    printf '%s\n' "$_wildcard_out" | sed 's/^/         /'
    fails=$((fails + 1))
fi
rm -rf "$WTMP" "$WRD"

echo "=================================================="
if [ "$fails" -eq 0 ]; then
    echo "RESULT: PASS — all Skill 54 self-verification checks passed."
    exit 0
fi
echo "RESULT: FAIL — $fails check(s) failed."
exit 1
