#!/usr/bin/env bash
# qc-kie-callback-relay.sh — local QC gate for Skill 46 (kie-callback-relay).
#
# Runs THIS skill dir's checks against the copy the script lives in (never a stale
# installed ~/.openclaw/skills copy), so it tests the edits under review:
#   1. node --check on the three JS components (worker, poller, submitter)
#   2. the stubbed-fetch security regression suite (test/security.test.mjs)
#   3. frontmatter <-> skill-version.txt agreement for this skill dir
#
# Exit 0 = all pass; non-zero = a gate failed.
#
# Usage: bash 46-kie-callback-relay/qc-kie-callback-relay.sh
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fails=0

echo "== QC: kie-callback-relay =="
echo "-- skill dir: $SKILL_DIR"

# 1. Syntax checks -------------------------------------------------------------
echo "-- node --check on components"
for f in box-kv-poller.js kie-slide-submitter.js worker/src/index.js; do
  if node --check "$SKILL_DIR/$f" 2>/dev/null; then
    echo "   ok  $f"
  else
    # worker is ESM; --check needs the module hint
    if node --input-type=module --check < "$SKILL_DIR/$f" 2>/dev/null; then
      echo "   ok  $f (esm)"
    else
      echo "   FAIL $f"; fails=$((fails + 1))
    fi
  fi
done

# 2. Security regression suite -------------------------------------------------
echo "-- security regression suite"
if node "$SKILL_DIR/test/security.test.mjs"; then
  echo "   ok  test/security.test.mjs"
else
  echo "   FAIL test/security.test.mjs"; fails=$((fails + 1))
fi

# 3. frontmatter/skill-version agreement for THIS dir --------------------------
echo "-- frontmatter <-> skill-version.txt"
sv="$(tr -d ' \t\r\n' < "$SKILL_DIR/skill-version.txt" 2>/dev/null)"
# This skill carries its version nested under `metadata:` (not top-level), so match a
# `version:` line anywhere in the frontmatter block, indented or not.
fm="$(awk 'BEGIN{f=0}{if($0=="---"){f++;if(f>=2)exit;next}if(f==1&&$0~/^[[:space:]]*version:/){v=$0;sub(/^[[:space:]]*version:[ \t]*/,"",v);gsub(/["'"'"' \t\r]/,"",v);print v;exit}}' "$SKILL_DIR/SKILL.md")"
if [ -n "$sv" ] && [ "$sv" = "$fm" ]; then
  echo "   ok  version $sv (frontmatter == skill-version.txt)"
else
  echo "   FAIL version drift: skill-version.txt='$sv' SKILL.md frontmatter='$fm'"; fails=$((fails + 1))
fi

echo "=============================================="
if [ "$fails" -eq 0 ]; then
  echo "QC PASS"
  exit 0
fi
echo "QC FAIL ($fails gate(s))"
exit 1
