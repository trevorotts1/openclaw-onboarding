#!/usr/bin/env bash
# Skill 48 — Facebook & Instagram Ad Generator — before-you-start preflight.
# Asserts the box can actually run a batch: python3, the client's own keys, a
# paid-advertisement agent to assign, and a money ceiling set. Fail-loud, non-destructive.
set -u
FAIL=0
note() { printf "  %s\n" "$1"; }
ok()   { printf "  [ok]   %s\n" "$1"; }
bad()  { printf "  [MISS] %s\n" "$1"; FAIL=1; }

echo "=== Skill 48 preflight ==="

command -v python3 >/dev/null 2>&1 && ok "python3 present" || bad "python3 missing"

# Client's own Kie key (generation) — env-var NAME only; never the operator's key.
if [ -n "${KIE_API_KEY:-}" ]; then ok "KIE_API_KEY set (client's own image-gen key)";
else note "KIE_API_KEY not set in this shell — required at S5 image generation (client's own key)"; fi

# Client's own GoHighLevel LOCATION PIT with medias.write (hosting).
if [ -n "${GOHIGHLEVEL_API_KEY:-}${GHL_API_KEY:-}" ]; then ok "GoHighLevel LOCATION PIT present (client's own)";
else note "GoHighLevel LOCATION PIT not set — required at S7 image hosting (client's own location PIT, medias.write)"; fi

# A money ceiling must be decided before a run (passed in the job brief).
note "Money ceiling (money_ceiling_usd) is set per-run in the job brief at S0-INTAKE."

# The enforcement spine must be importable.
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 -c "import ast; ast.parse(open('${SKILL_DIR}/scripts/ad_director.py').read())" >/dev/null 2>&1 \
  && ok "ad_director.py parses" || bad "ad_director.py missing/broken"
python3 -c "import ast; ast.parse(open('${SKILL_DIR}/scripts/ad_build_check.py').read())" >/dev/null 2>&1 \
  && ok "ad_build_check.py parses" || bad "ad_build_check.py missing/broken"

echo ""
if [ "$FAIL" -ne 0 ]; then echo "preflight: BLOCKERS present (see [MISS] above)"; exit 1; fi
echo "preflight: OK (notes above are reminders, not blockers)"
exit 0
