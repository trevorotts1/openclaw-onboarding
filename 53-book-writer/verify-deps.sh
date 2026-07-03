#!/usr/bin/env bash
# 53-book-writer/verify-deps.sh — prove ZERO external runtime services (idempotent).
# ============================================================================
# The Book Writer is LOCAL-ONLY: no n8n, Airtable, Google Drive/Docs/Slides,
# Gmail, Slack, or GHL at runtime. This script proves that no RUNTIME script in
# the skill calls any of those services. Detection/ban code (the bypass scanner in
# prove_bw_process.py + this file) is allowlisted — those files NAME the services
# only to REJECT them. Exit 0 = clean; nonzero = a real external call slipped in.
# ============================================================================
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

command -v python3 >/dev/null 2>&1 || { echo "verify-deps: python3 required" >&2; exit 6; }

echo "== Skill 53 verify-deps :: proving zero external runtime services =="
SELF_DIR="$SELF_DIR" python3 - <<'PY'
import os, re, sys
skill = os.environ["SELF_DIR"]
# files whose PURPOSE is to name+reject external services (allowlisted)
ALLOW = {"prove_bw_process.py", "verify-deps.sh", "book-writer-entry.sh",
         "MASTERDOC.md", "INSTRUCTIONS.md", "REPAIRS.md", "SKILL.md",
         "BOOK-WRITER-MANIFEST.json", "GOLDEN-BOOK-BIBLE.md", "WIRING-SPEC.md",
         "make_broken.py", "REJECTION-RESULTS.json", "CHANGELOG.md", "verify.sh"}
svc = re.compile(r"googleapis\.com|hooks\.slack\.com|chat\.postMessage|api\.airtable\.com"
                 r"|smtp\.gmail|leadconnectorhq\.com|gohighlevel\.com|n8n\.cloud|/webhook/",
                 re.IGNORECASE)
hits = []
for root, dirs, files in os.walk(skill):
    dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
    for fn in files:
        if fn in ALLOW or not fn.endswith((".py", ".sh")):
            continue
        p = os.path.join(root, fn)
        try:
            src = open(p, errors="replace").read()
        except Exception:
            continue
        for m in svc.finditer(src):
            hits.append("%s: %s" % (os.path.relpath(p, skill), m.group(0)))
if hits:
    print("FAIL: an external-service call is present in a runtime script:", file=sys.stderr)
    for h in hits:
        print("   " + h, file=sys.stderr)
    sys.exit(2)
print("PASS: no n8n / Airtable / Google / Gmail / Slack / GHL call in any runtime script.")
print("      (provers are stdlib-only; the engine is fully local.)")
sys.exit(0)
PY
