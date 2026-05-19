#!/usr/bin/env bash
# verify-role-library.sh — sanity-check the v10.6.x role library on disk.
#
# Runs against the installed skill folder (resolved via detect_platform.py)
# OR against an explicit --skill-dir path. Exits 0 if the library is healthy,
# non-zero with a specific reason if not.
#
# Checks:
#   1. ≥180 PASS role docs exist across the 16 mandatory dept folders
#   2. Every PASS doc has at least 19 numbered sections
#   3. Every PASS doc contains the Persona Governance Override clause
#      (or the CEO variant for master-orchestrator)
#   4. No literal client names in any PASS doc ("BlackCEO", "Trevor",
#      "ZeroHumanCompany" — should be {{TOKENS}} instead)
#   5. _pending_rewrite/ slugs do NOT overlap with PASS library slugs
#   6. _index.json is present and parses
#   7. _index.json[total_roles] matches the actual count
#
# Usage:
#   bash 23-ai-workforce-blueprint/scripts/verify-role-library.sh
#   bash 23-ai-workforce-blueprint/scripts/verify-role-library.sh --skill-dir /tmp/openclaw-work/23-ai-workforce-blueprint
#   bash 23-ai-workforce-blueprint/scripts/verify-role-library.sh --json   (machine output)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR=""
JSON_MODE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    --json) JSON_MODE=1; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$SKILL_DIR" ]; then
  # Default: assume this script is in $SKILL_DIR/scripts/
  SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

LIB_DIR="$SKILL_DIR/templates/role-library"
INDEX_JSON="$LIB_DIR/_index.json"

PASS=0
FAIL=0
ISSUES=()

record_pass() { PASS=$((PASS + 1)); [ $JSON_MODE -eq 0 ] && echo "  PASS  $1"; }
record_fail() { FAIL=$((FAIL + 1)); ISSUES+=("$1"); [ $JSON_MODE -eq 0 ] && echo "  FAIL  $1"; }

[ $JSON_MODE -eq 0 ] && echo "=== Role library verification: $LIB_DIR ==="

# ─── Check 1: library directory exists ─────────────────────────────────────
if [ ! -d "$LIB_DIR" ]; then
  record_fail "role-library directory does not exist: $LIB_DIR"
  # Can't continue without the library
  if [ $JSON_MODE -eq 1 ]; then
    python3 -c "import json; print(json.dumps({'pass': $PASS, 'fail': $FAIL, 'issues': $(printf '%s\n' "${ISSUES[@]}" | python3 -c 'import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))')}))"
  fi
  exit 1
fi

# ─── Check 2: _index.json present + parses ─────────────────────────────────
if [ ! -f "$INDEX_JSON" ]; then
  record_fail "_index.json missing at $INDEX_JSON"
else
  if python3 -c "import json; json.load(open('$INDEX_JSON'))" 2>/dev/null; then
    record_pass "_index.json parses"
  else
    record_fail "_index.json fails to parse as JSON"
  fi
fi

# ─── Check 3: ≥180 PASS docs across dept folders ──────────────────────────
TOTAL=0
for dept_dir in "$LIB_DIR"/*/; do
  dept=$(basename "$dept_dir")
  [ "${dept:0:1}" = "_" ] && continue
  if [ -d "$dept_dir" ]; then
    count=$(find "$dept_dir" -maxdepth 1 -type f -name "*.md" ! -name "_*" | wc -l | tr -d ' ')
    TOTAL=$((TOTAL + count))
  fi
done
if [ $TOTAL -ge 180 ]; then
  record_pass "≥180 PASS role docs found (actual: $TOTAL)"
else
  record_fail "only $TOTAL PASS role docs (need ≥180)"
fi

# ─── Check 4: total_roles in index matches actual file count ──────────────
if [ -f "$INDEX_JSON" ]; then
  declared=$(python3 -c "import json; print(json.load(open('$INDEX_JSON')).get('total_roles', 0))")
  if [ "$declared" = "$TOTAL" ]; then
    record_pass "_index.json total_roles ($declared) matches file count"
  else
    record_fail "_index.json total_roles=$declared but actual count=$TOTAL"
  fi
fi

# ─── Check 5: Every PASS doc has ≥19 numbered sections ────────────────────
SECTION_FAILURES=$(
  for dept_dir in "$LIB_DIR"/*/; do
    dept=$(basename "$dept_dir")
    [ "${dept:0:1}" = "_" ] && continue
    if [ -d "$dept_dir" ]; then
      for f in "$dept_dir"*.md; do
        [ -f "$f" ] || continue
        fname=$(basename "$f")
        [ "${fname:0:1}" = "_" ] && continue
        sec_count=$(grep -cE '^##[[:space:]]+[0-9]+\.' "$f" || true)
        if [ "$sec_count" -lt 19 ]; then
          echo "$f:$sec_count"
        fi
      done
    fi
  done
)
if [ -z "$SECTION_FAILURES" ]; then
  record_pass "every PASS doc has ≥19 numbered sections"
else
  short_count=$(echo "$SECTION_FAILURES" | wc -l | tr -d ' ')
  record_fail "$short_count docs have <19 sections; first 5: $(echo "$SECTION_FAILURES" | head -5)"
fi

# ─── Check 6: Persona Governance Override clause present in every doc ─────
MISSING_CLAUSE=$(
  for dept_dir in "$LIB_DIR"/*/; do
    dept=$(basename "$dept_dir")
    [ "${dept:0:1}" = "_" ] && continue
    if [ -d "$dept_dir" ]; then
      for f in "$dept_dir"*.md; do
        [ -f "$f" ] || continue
        fname=$(basename "$f")
        [ "${fname:0:1}" = "_" ] && continue
        if ! grep -q "Persona Governance Override\|Persona Governance — CEO Mode" "$f"; then
          echo "$f"
        fi
      done
    fi
  done
)
if [ -z "$MISSING_CLAUSE" ]; then
  record_pass "every doc has Persona Governance clause (standard or CEO)"
else
  miss_count=$(echo "$MISSING_CLAUSE" | wc -l | tr -d ' ')
  record_fail "$miss_count docs missing deferral clause; first 3: $(echo "$MISSING_CLAUSE" | head -3)"
fi

# ─── Check 7: No literal client names in any PASS doc ─────────────────────
LITERAL_NAMES=$(
  for dept_dir in "$LIB_DIR"/*/; do
    dept=$(basename "$dept_dir")
    [ "${dept:0:1}" = "_" ] && continue
    if [ -d "$dept_dir" ]; then
      grep -l -E '\b(BlackCEO|Trevor[^a-z]|ZeroHumanCompany)\b' "$dept_dir"*.md 2>/dev/null || true
    fi
  done
)
if [ -z "$LITERAL_NAMES" ]; then
  record_pass "no literal client names found in any PASS doc"
else
  lit_count=$(echo "$LITERAL_NAMES" | wc -l | tr -d ' ')
  record_fail "$lit_count docs contain literal client names; first 3: $(echo "$LITERAL_NAMES" | head -3)"
fi

# ─── Check 8: _pending_rewrite/ slug overlap ──────────────────────────────
PENDING_DIR="$LIB_DIR/_pending_rewrite"
if [ -d "$PENDING_DIR" ]; then
  OVERLAP=$(
    for pdept in "$PENDING_DIR"/*/; do
      pd=$(basename "$pdept")
      for pf in "$pdept"*.md; do
        [ -f "$pf" ] || continue
        slug=$(basename "$pf")
        # Check if same slug exists in production
        if [ -f "$LIB_DIR/$pd/$slug" ]; then
          echo "$pd/$slug"
        fi
      done
    done
  )
  if [ -z "$OVERLAP" ]; then
    record_pass "_pending_rewrite/ slugs do not overlap with library"
  else
    overlap_count=$(echo "$OVERLAP" | wc -l | tr -d ' ')
    record_fail "$overlap_count slug(s) appear in BOTH library and _pending_rewrite: $(echo "$OVERLAP" | head -3)"
  fi
else
  record_pass "_pending_rewrite/ not present (clean library)"
fi

# ─── Output ───────────────────────────────────────────────────────────────
if [ $JSON_MODE -eq 1 ]; then
  python3 - <<PYEOF
import json
issues = """${ISSUES[@]:-}"""
print(json.dumps({
    "pass": $PASS,
    "fail": $FAIL,
    "total_docs": $TOTAL,
    "issues": [s for s in """$(printf '%s\n' "${ISSUES[@]:-}")""".split("\n") if s.strip()],
    "verdict": "PASS" if $FAIL == 0 else "FAIL",
}, indent=2))
PYEOF
else
  echo ""
  echo "──────────────────────────────────────────────────────────────"
  echo "Result: $PASS passed / $FAIL failed (total $TOTAL docs verified)"
  if [ $FAIL -eq 0 ]; then
    echo "✅ Role library is healthy"
  else
    echo "❌ Role library failed verification"
  fi
fi

[ $FAIL -eq 0 ]
