#!/usr/bin/env bash
# Skill 48 — Facebook & Instagram Ad Generator — clean-box dependency proof.
# Proves every outside tool the skill needs is present before a real run. Fail-loud.
set -u
FAIL=0
ok()  { printf "  [ok]   %s\n" "$1"; }
bad() { printf "  [FAIL] %s\n" "$1"; FAIL=1; }

echo "=== Skill 48 verify-deps ==="

command -v python3 >/dev/null 2>&1 && ok "python3" || bad "python3 missing"
python3 - <<'PY' >/dev/null 2>&1 && ok "python3 >= 3.8" || bad "python3 < 3.8"
import sys; sys.exit(0 if sys.version_info[:2] >= (3, 8) else 1)
PY

# Stdlib-only enforcement spine — no third-party deps required for the gates.
python3 -c "import json, re, ast, urllib.request, pathlib" >/dev/null 2>&1 \
  && ok "stdlib (json/re/ast/urllib/pathlib) importable" || bad "stdlib import failed"

# The reused Kie image adapter (generation) lives in Skill 47; the GHL media module is
# vendored into this skill's tools/.
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "${SKILL_DIR}/tools/ghl_media.py" ] && ok "ghl_media.py present (GoHighLevel host + create_media_folder)" \
  || bad "tools/ghl_media.py missing"

# requests is used by the reused Kie adapter at generation time (client box).
python3 -c "import requests" >/dev/null 2>&1 && ok "requests importable (Kie generation)" \
  || printf "  [warn] requests not importable — needed by the reused Kie adapter at S5\n"

echo ""
if [ "$FAIL" -ne 0 ]; then echo "verify-deps: FAILED"; exit 1; fi
echo "verify-deps: OK"
exit 0
