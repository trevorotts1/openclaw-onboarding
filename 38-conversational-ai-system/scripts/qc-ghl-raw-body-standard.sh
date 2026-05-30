#!/usr/bin/env bash
# qc-ghl-raw-body-standard.sh — machine-enforce the GHL RAW BODY JSON STANDARD
# (references/ghl-raw-body-json-standard.md).
#
# WHY: the GHL Custom Webhook RAW BODY must be the FULL 23-key FLAT JSON — 23 is the
# minimum AND the standard, never fewer, never nested. This gate asserts the standard
# doc carries the hard headline + the FLAT rule + the exact 23-key list + the canonical
# body, and COMPOSES the existing scripts/qc-23-key-bodies.sh (which lints every RAW
# BODY example in the skill, including the canonical body in the standard doc itself),
# so a regression that guts the standard or introduces a stripped/nested body FAILS the
# build.
#
# WHAT IT CHECKS (from the repo alone — CI-safe, BASH-only so it respects the .py
# claude-/anthropic ban):
#   1. references/ghl-raw-body-json-standard.md exists.
#   2. The hard headline ("EVERY GHL CUSTOM WEBHOOK RAW BODY MUST BE THE FULL 23-KEY
#      FLAT JSON") + the "23 is the MINIMUM AND the standard" framing are present.
#   3. The FLAT rule + the placeholder-free messageTemplate rule + deliver:false are stated.
#   4. ALL 23 keys are named in the doc.
#   5. The doc references GHL-INBOUND-AND-PLAYBOOKS.md as source-of-truth + qc-23-key-bodies.sh.
#   6. The canonical body in the doc passes qc-23-key-bodies.sh (composed).
#   7. SKILL.md / INSTRUCTIONS.md carry a pointer to the standard.
#
# Exit codes: 0 = clean; 1 = at least one violation.
#
# Usage:
#   bash scripts/qc-ghl-raw-body-standard.sh
#   bash scripts/qc-ghl-raw-body-standard.sh --skill-dir DIR
#   bash scripts/qc-ghl-raw-body-standard.sh --doc PATH    # negative-test a fixture

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DOC=""

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    --doc)       DOC="$2"; shift 2 ;;
    -h|--help)   sed -n '1,32p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

[ -n "$DOC" ] || DOC="$SKILL_DIR/references/ghl-raw-body-json-standard.md"

FAIL=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAIL=1; }

echo "=== qc-ghl-raw-body-standard: GHL RAW BODY JSON STANDARD gate ==="
echo "doc : $DOC"
echo ""

if [ ! -f "$DOC" ]; then
  echo "  [FAIL] standard doc MISSING: $DOC"
  echo ""
  echo "RESULT: FAIL"
  exit 1
fi

# 1. Hard headline + framing.
grep -qiE 'EVERY GHL CUSTOM WEBHOOK RAW BODY MUST BE THE FULL 23-KEY FLAT JSON' "$DOC" \
  && pass "Section 0 hard headline present" \
  || fail "missing the 'EVERY GHL CUSTOM WEBHOOK RAW BODY MUST BE THE FULL 23-KEY FLAT JSON' headline"
grep -qiE 'MINIMUM AND the standard' "$DOC" \
  && pass "'23 is the MINIMUM AND the standard' framing present" \
  || fail "missing the '23 is the MINIMUM AND the standard, never fewer, never nested' framing"

# 2. The FLAT rule + placeholder-free + deliver:false.
grep -qiE 'FLAT[^a-z]*(—|-)?\s*no nested|FLAT — no nested|no nested objects' "$DOC" \
  && pass "FLAT (no nested objects) rule stated" \
  || fail "missing the FLAT / no-nested-objects rule"
grep -qiE 'placeholder-free' "$DOC" \
  && pass "placeholder-free messageTemplate rule stated" \
  || fail "missing the placeholder-free messageTemplate rule"
grep -qiE 'deliver.{0,4}false|`deliver` is `false`|deliver: ?false' "$DOC" \
  && pass "deliver:false rule stated" \
  || fail "missing the deliver:false rule"

# 3. ALL 23 keys named.
KEYS=(id match action agent_id model wakeMode name session_key messageTemplate deliver \
      timeoutSeconds channel to thinking contact_id first_name last_name email phone \
      subject message_body location_id location_name)
MISSING_KEYS=""
for k in "${KEYS[@]}"; do
  grep -qF "\`$k\`" "$DOC" || grep -qE "\"$k\"" "$DOC" || MISSING_KEYS="$MISSING_KEYS $k"
done
if [ -z "$MISSING_KEYS" ]; then
  pass "all 23 keys named in the standard doc"
else
  fail "23-key list is missing key(s):$MISSING_KEYS"
fi

# 4. Source-of-truth + linter references.
grep -qF 'GHL-INBOUND-AND-PLAYBOOKS.md' "$DOC" \
  && pass "doc references GHL-INBOUND-AND-PLAYBOOKS.md (source of truth)" \
  || fail "doc must reference GHL-INBOUND-AND-PLAYBOOKS.md as source of truth"
grep -qF 'qc-23-key-bodies.sh' "$DOC" \
  && pass "doc references the enforcing linter (qc-23-key-bodies.sh)" \
  || fail "doc must reference qc-23-key-bodies.sh"

# 5. Compose qc-23-key-bodies.sh — the canonical body in the doc (and everywhere) is lint-clean.
QC23="$SKILL_DIR/scripts/qc-23-key-bodies.sh"
if [ -f "$QC23" ]; then
  if bash "$QC23" >/dev/null 2>&1; then
    pass "composed qc-23-key-bodies.sh PASSES (canonical body + all skill bodies are 23-key/flat/placeholder-free)"
  else
    fail "composed qc-23-key-bodies.sh FAILED — a RAW BODY (possibly the standard's canonical body) violates the 23-key rule"
  fi
else
  fail "qc-23-key-bodies.sh not found to compose (scripts/qc-23-key-bodies.sh)"
fi

# 6. SKILL.md / INSTRUCTIONS.md pointer (skip when running against a fixture --doc).
if [ -z "${DOC##*ghl-raw-body-json-standard.md}" ]; then
  PTR=0
  for f in "$SKILL_DIR/SKILL.md" "$SKILL_DIR/INSTRUCTIONS.md"; do
    [ -f "$f" ] && grep -qF 'ghl-raw-body-json-standard.md' "$f" && PTR=1
  done
  [ "$PTR" -eq 1 ] && pass "SKILL.md/INSTRUCTIONS.md point to the standard" \
                    || fail "SKILL.md or INSTRUCTIONS.md must point to references/ghl-raw-body-json-standard.md"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — the GHL RAW BODY JSON standard carries the 23-key list + FLAT rule + canonical body, and qc-23-key-bodies.sh is clean."
  exit 0
else
  echo "RESULT: FAIL — a GHL-raw-body-standard requirement is missing or a body violates the 23-key rule (see above)."
  exit 1
fi
