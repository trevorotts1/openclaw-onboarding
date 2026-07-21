#!/usr/bin/env bash
# tests/unit/qc-convert-and-flow-layout-and-path.test.sh
#
# REGRESSION GUARD — Skill 44 QC: installed-layout + non-interactive-PATH.
#
# THE TWO FALSE FAILS THIS CLOSES (both proven live 2026-07-21 on a client box):
#
#  (1) REPO-ONLY PATH. qc-convert-and-flow.sh computed
#          REPO_ROOT_LATTICE="$(cd "$SKILL44_DIR/.." && pwd)"
#      and then ran "$REPO_ROOT_LATTICE/docs/tools/check_lattice_citation.py"
#      unconditionally. In the source repo the skill sits at the repo root, so
#      ".." resolves and docs/ is a sibling. On a client box the skill installs
#      to ~/.openclaw/skills/44-convert-and-flow-operator, so ".." is
#      ~/.openclaw/skills — which has NO docs/ directory — and python3 exited 2
#      ("can't open file"). Every client-box run hard-FAILED forever, reporting
#      citation drift that did not exist.
#
#  (2) BARE-PATH CLI ASSUMPTION. The "GOHIGHLEVEL_LOCATION_ID present in
#      openclaw.json env.vars" check shelled out to `openclaw config get`. In a
#      non-interactive shell (install harness / cron / ssh 'cmd') PATH does not
#      include the directory OpenClaw is installed in, so the command was not
#      found and the check FAILED on a box whose config had the value.
#
# WHAT THIS FILE PROVES (hermetic; fixtures in a tempdir, no box touched):
#   T1  installed layout (no docs/ sibling) -> the lattice check SKIPS VISIBLY
#   T2  ...and that skip is NOT counted as a pass, and does NOT fail the script
#   T3  repo layout with the checker present -> the check RUNS and passes
#   T4  repo layout with a DELIBERATELY BROKEN citation -> still FAILS
#       (the skip path did not blunt the tripwire)
#   T5  bare non-interactive PATH + value present in openclaw.json ->
#       the location-id check PASSES
#   T6  bare non-interactive PATH + value ABSENT -> the location-id check
#       still FAILS (the check is not a no-op)
#
# Exit 0 = pass. Exit 1 = one of the two false fails regressed.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILL_DIR="$REPO_ROOT/44-convert-and-flow-operator"
QC="$SKILL_DIR/qc-convert-and-flow.sh"
LATTICE_CHECKER_REL="docs/tools/check_lattice_citation.py"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== qc-convert-and-flow-layout-and-path.test.sh ==="
echo ""

for f in "$QC" "$REPO_ROOT/$LATTICE_CHECKER_REL"; do
  if [ ! -f "$f" ]; then echo "  FAIL: $f not found"; exit 1; fi
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

strip_ansi() { sed -e 's/\x1b\[[0-9;]*m//g'; }

# ── T1/T2: INSTALLED layout — skill dir with no docs/ sibling ───────────────
mkdir -p "$TMP/installed/skills"
cp -R "$SKILL_DIR" "$TMP/installed/skills/44-convert-and-flow-operator"
INSTALLED_OUT="$(bash "$TMP/installed/skills/44-convert-and-flow-operator/qc-convert-and-flow.sh" 2>&1 | strip_ansi)"
INSTALLED_RC=$?

if printf '%s' "$INSTALLED_OUT" | grep -qi 'SKIP:.*lattice'; then
  pass "T1 installed layout -> lattice tripwire reports a VISIBLE SKIP"
else
  fail "T1 installed layout -> no visible SKIP line for the lattice tripwire"
fi

INSTALLED_FAILED="$(printf '%s' "$INSTALLED_OUT" | grep -oE 'Result: [0-9]+ passed \| [0-9]+ failed' | grep -oE '[0-9]+ failed' | grep -oE '^[0-9]+')"
if [ "${INSTALLED_FAILED:-1}" = "0" ]; then
  pass "T2a installed layout -> 0 failures (no permanently-red gate)"
else
  fail "T2a installed layout -> ${INSTALLED_FAILED:-?} failure(s); expected 0"
fi
if printf '%s' "$INSTALLED_OUT" | grep -qi 'PASS:.*lattice'; then
  fail "T2b the absent checker was converted into a silent PASS"
else
  pass "T2b the absent checker was NOT counted as a pass"
fi

# ── T3: REPO layout — checker present, citations intact -> runs and passes ──
mkdir -p "$TMP/repo"
cp -R "$SKILL_DIR" "$TMP/repo/44-convert-and-flow-operator"
cp -R "$REPO_ROOT/docs" "$TMP/repo/docs"
REPO_OUT="$(bash "$TMP/repo/44-convert-and-flow-operator/qc-convert-and-flow.sh" 2>&1 | strip_ansi)"
if printf '%s' "$REPO_OUT" | grep -qi 'PASS:.*lattice'; then
  pass "T3 repo layout -> lattice tripwire RUNS and passes (still enforced)"
else
  fail "T3 repo layout -> lattice tripwire did not run/pass:
$(printf '%s' "$REPO_OUT" | grep -i lattice)"
fi

# ── T4: REPO layout with a genuinely broken citation -> must still FAIL ─────
mkdir -p "$TMP/drift"
cp -R "$SKILL_DIR" "$TMP/drift/44-convert-and-flow-operator"
cp -R "$REPO_ROOT/docs" "$TMP/drift/docs"
python3 - "$TMP/drift" <<'PY'
import json, os, sys
root = sys.argv[1]
manifest = json.load(open(os.path.join(root, "docs", "lattice-citations.json")))
target = None
for edge in manifest.get("edges", []):
    if str(edge.get("owner_skill", "")).startswith("44-"):
        for c in edge.get("citations", []):
            if c.get("line") and c.get("must_contain"):
                target = c
                break
    if target:
        break
if not target:
    print("NO-CITATION-TO-BREAK")
    raise SystemExit(0)
path = os.path.join(root, target["file"])
lines = open(path).read().split("\n")
idx = int(target["line"]) - 1
# REMOVE the cited substring (do not merely prefix it -- a prefixed line still
# CONTAINS the substring and the tripwire would correctly still pass).
lines[idx] = lines[idx].replace(target["must_contain"], "DRIFTED-CITATION-MARKER")
assert target["must_contain"] not in lines[idx], "fixture failed to break the citation"
open(path, "w").write("\n".join(lines))
print("    (fixture: broke %s line %s)" % (target["file"], target["line"]))
PY
DRIFT_OUT="$(bash "$TMP/drift/44-convert-and-flow-operator/qc-convert-and-flow.sh" 2>&1 | strip_ansi)"
if printf '%s' "$DRIFT_OUT" | grep -qi 'FAIL:.*lattice'; then
  pass "T4 repo layout + broken citation -> lattice tripwire still FAILS"
else
  fail "T4 repo layout + broken citation -> tripwire did NOT fail (gate blunted!)"
fi

# ── T5/T6: bare non-interactive PATH, live mode ────────────────────────────
mk_cfg() {
  local home="$1" env_json="$2"
  mkdir -p "$home/.openclaw"
  python3 -c '
import json, sys
json.dump({"env": json.loads(sys.argv[2])}, open(sys.argv[1], "w"), indent=2)
' "$home/.openclaw/openclaw.json" "$env_json"
}

locid_verdict() {
  local home="$1"
  env -i HOME="$home" PATH="/usr/bin:/bin" CAF_LIVE=1 OPENCLAW_PLATFORM=mac \
    /bin/bash "$QC" 2>&1 | strip_ansi \
    | grep -a 'GOHIGHLEVEL_LOCATION_ID present in openclaw.json env.vars' \
    | grep -oE '(PASS|FAIL|SKIP)' | head -1
}

mk_cfg "$TMP/live-set" '{"vars": {"GOHIGHLEVEL_LOCATION_ID": "fixture-location-id"}}'
V5="$(locid_verdict "$TMP/live-set")"
[ "$V5" = "PASS" ] \
  && pass "T5 bare PATH + value in openclaw.json -> location-id check PASSES" \
  || fail "T5 bare PATH + value in openclaw.json -> expected PASS, got '${V5:-<no verdict line>}'"

mk_cfg "$TMP/live-unset" '{"vars": {}}'
V6="$(locid_verdict "$TMP/live-unset")"
[ "$V6" = "FAIL" ] \
  && pass "T6 bare PATH + value absent -> location-id check still FAILS" \
  || fail "T6 bare PATH + value absent -> expected FAIL, got '${V6:-<no verdict line>}' (check softened!)"

echo ""
echo "  Result: $PASS passed | $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
  echo "qc-convert-and-flow-layout-and-path.test.sh: FAILED"
  exit 1
fi
echo "qc-convert-and-flow-layout-and-path.test.sh: PASSED"
exit 0
