#!/usr/bin/env bash
# qc-70-pointer-references.sh - Skill 70 quality-control gate.
#
# Run by the onboarding verification gate (oc_gate_skill in
# lib-onboarding-state.sh) with no arguments, and by hand from the repo or from
# an installed skill folder. READ-ONLY toward the box: every test builds its own
# throwaway folders and uses a fake `openclaw`; nothing touches the real
# workspace, master files, backups or cron store.
#
# Checks:
#   1. every file the skill ships is present
#   2. every shell script parses (bash -n) and the fake command line compiles
#   3. CORE_UPDATES.md carries both payloads, the AGENTS.md pointer is at most
#      two sentences, and the gate-visible sentinel line is present
#   4. SKILL.md frontmatter version equals skill-version.txt
#   5. hard wall: no script writes or reads the bootstrap limit keys
#   6. repo language rules in the skill's own docs: no em dashes
#   7. the three fixture batteries pass (audit, cron installer, wire.sh)
#
# EXIT: 0 PASS | 1 FAIL (a check failed) | 2 TOOLING (bash or python3 missing)

set -u
D="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
command -v python3 >/dev/null 2>&1 || { echo "TOOLING [qc-70]: python3 missing"; exit 2; }
FAILS=0
pass() { echo "  PASS $*"; }
fail() { echo "  FAIL $*"; FAILS=$((FAILS + 1)); }

echo "qc-70-pointer-references"

for f in SKILL.md pointer-references-full.md INSTALL.md INSTRUCTIONS.md EXAMPLES.md CORE_UPDATES.md QC.md \
         CHANGELOG.md skill-version.txt pointer-references.skill wire.sh \
         scripts/lib-paths.sh scripts/pointer-audit.sh scripts/install-weekly-cron.sh scripts/weekly-cron-message.txt \
         tests/test-pointer-audit.sh tests/test-install-weekly-cron.sh tests/test-wire.sh tests/fake-openclaw.py; do
  [ -f "$D/$f" ] || fail "missing file: $f"
done
[ "$FAILS" -eq 0 ] && pass "all shipped files present"

n0=$FAILS
for s in "$D/wire.sh" "$D/qc-70-pointer-references.sh" "$D"/scripts/*.sh "$D"/tests/*.sh; do
  bash -n "$s" 2>/dev/null || fail "bash -n: ${s#"$D"/}"
  if [ -x /bin/bash ] && /bin/bash --version 2>/dev/null | grep -q 'version 3\.'; then
    /bin/bash -n "$s" 2>/dev/null || fail "bash 3.2 -n: ${s#"$D"/}"
  fi
done
python3 -m py_compile "$D/tests/fake-openclaw.py" 2>/dev/null || fail "fake-openclaw.py does not compile"
find "$D/tests" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
[ "$FAILS" -eq "$n0" ] && pass "all scripts parse"

n0=$FAILS
python3 - "$D/CORE_UPDATES.md" <<'PY' || fail "CORE_UPDATES.md payload check"
import re, sys
cu = open(sys.argv[1]).read()
for t in ("AGENTS", "MEMORY"):
    m = re.search(r"^## %s\.md - UPDATE REQUIRED\n(.*?)(?=^## [A-Z]+\.md |\Z)" % t, cu, re.S | re.M)
    f = re.search(r"^```[^\n]*\n(.*?)^```", m.group(1), re.S | re.M) if m else None
    if not f:
        sys.exit("no fenced payload for %s.md" % t)
    if t == "AGENTS":
        if not m.group(1).lstrip("\n").startswith("<!-- skill:70-pointer-references:core-update-applied -->"):
            sys.exit("AGENTS.md section must open with the sentinel line")
        lines = [l for l in f.group(1).splitlines() if l.strip() and not l.startswith("#")]
        if len(lines) != 1:
            sys.exit("AGENTS.md pointer must be one line")
        t2 = re.sub(r"[\w~/.-]+\.md", "F", lines[0])
        if len(re.findall(r"[.!?](\s|$)", t2)) > 2:
            sys.exit("AGENTS.md pointer is longer than two sentences")
        if not re.search(r"\b(when|whenever)\b", lines[0], re.I):
            sys.exit("AGENTS.md pointer has no WHEN")
PY
[ "$FAILS" -eq "$n0" ] && pass "CORE_UPDATES.md payloads well formed (one-line pointer, two sentences, WHEN, sentinel)"

fm="$(awk 'BEGIN{f=0} /^---$/{f++; if(f>=2) exit; next} f==1 && /^version:/{sub(/^version:[ \t]*/,""); gsub(/"/,""); print; exit}' "$D/SKILL.md")"
sv="$(tr -d '[:space:]' < "$D/skill-version.txt")"
[ "v${fm#v}" = "v${sv#v}" ] && pass "SKILL.md version $fm equals skill-version.txt $sv" || fail "SKILL.md version '$fm' != skill-version.txt '$sv'"

if grep -n -E 'bootstrap(Total)?MaxChars' "$D/wire.sh" "$D"/scripts/*.sh 2>/dev/null | grep -v -E '^[^:]+:[0-9]+:[[:space:]]*#' | grep -q .; then
  fail "hard wall: a script line (not a comment) names a bootstrap limit key"
else
  pass "hard wall: no script touches the bootstrap limit keys"
fi

EM="$(printf '\342\200\224')"
if grep -l "$EM" "$D"/*.md "$D"/scripts/* "$D"/tests/* "$D/wire.sh" 2>/dev/null | grep -q .; then
  fail "em dash found in: $(grep -l "$EM" "$D"/*.md "$D"/scripts/* "$D"/tests/* "$D/wire.sh" 2>/dev/null | tr '\n' ' ')"
else
  pass "no em dashes in the skill's files"
fi

for t in test-pointer-audit.sh test-install-weekly-cron.sh test-wire.sh; do
  out="$(bash "$D/tests/$t" 2>&1)"; rc=$?
  last="$(printf '%s\n' "$out" | tail -1)"
  if [ "$rc" -eq 0 ]; then pass "$t: $last"; else fail "$t (exit $rc): $last"; printf '%s\n' "$out" | grep FAIL | sed 's/^/       /'; fi
done

if [ "$FAILS" -eq 0 ]; then echo "qc-70-pointer-references: PASS"; exit 0; fi
echo "qc-70-pointer-references: FAIL ($FAILS check(s))"; exit 1
