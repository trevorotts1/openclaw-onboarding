#!/usr/bin/env bash
# tests/unit/fleet-standards-skill-workshop-mode.test.sh
# apply-fleet-standards.sh seeds skills.workshop.autonomous.mode="propose" ONLY when
# the 1b-SW schema probe says the key is valid-and-unset, and never overrides an
# operator's explicit value. The SKILL-WORKSHOP-MODE block is extracted LIVE from the
# shipped script and exec()'d against fixtures; no real openclaw.json is touched.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/apply-fleet-standards.sh"

python3 - "$SCRIPT" <<'PYEOF'
import os, sys, re
src = open(sys.argv[1]).read()
m = re.search(r"# >>> SKILL-WORKSHOP-MODE.*?\n(.*?)# <<< SKILL-WORKSHOP-MODE", src, re.S)
assert m, "SKILL-WORKSHOP-MODE block not found in apply-fleet-standards.sh"
block = m.group(1)
fails = 0
def run(cfg, seed):
    os.environ["FLEET_SEED_SKILL_WORKSHOP_MODE"] = "1" if seed else "0"
    exec(block, {"os": os, "cfg": cfg, "print": lambda *a: None})
    return cfg
def check(name, ok):
    global fails
    print(("  ok   " if ok else "  FAIL ") + name); fails += 0 if ok else 1

mode = lambda c: (((c.get("skills") or {}).get("workshop") or {}).get("autonomous") or {}).get("mode")
check("unset + probe says valid -> propose", mode(run({}, True)) == "propose")
check("existing skills block kept, mode seeded", run({"skills": {"load": {"x": 1}}}, True)["skills"]["load"] == {"x": 1})
for v in ("auto", "propose", "off"):
    check(f"explicit {v} kept", mode(run({"skills": {"workshop": {"autonomous": {"mode": v}}}}, True)) == v)
check("probe says unknown/older build -> nothing written", run({}, False) == {})
check("non-dict skills left alone", run({"skills": "x"}, True) == {"skills": "x"})
sys.exit(1 if fails else 0)
PYEOF
rc=$?

# The live probe in Section 1b-SW must key on the CLI's valid-but-unset answer.
grep -q "openclaw config get skills.workshop.autonomous.mode 2>&1 | grep -q 'valid but unset'" "$SCRIPT" \
  && echo "  ok   1b-SW probe present" || { echo "  FAIL 1b-SW probe missing"; rc=1; }
exit $rc
