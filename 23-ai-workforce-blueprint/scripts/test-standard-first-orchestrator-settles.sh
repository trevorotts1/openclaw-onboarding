#!/usr/bin/env bash
# test-standard-first-orchestrator-settles.sh — BU-52 acceptance test.
#
# Builds a fixture state exactly as the prebuild's final write does (entries
# for the floor including master-orchestrator, all prebuilt), creates
# departments/master-orchestrator/SOUL.md, runs the new block through a small
# harness that imports the function, then calls
# workforce_completion.evaluate(state) and asserts "departments" is not in
# the result. Without the SOUL file asserts the entry stays prebuilt.
#
# Exit 0 = all guards pass; non-zero = a guard failed.
# Hermetic: sandboxed $HOME, scratch state file, scratch departments dir.
# Nothing may escape the sandbox.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PASS=0
FAIL=0
good() { PASS=$((PASS + 1)); echo "PASS: $1"; }
bad()  { FAIL=$((FAIL + 1)); echo "FAIL: $1" >&2; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
SANDBOX_HOME="$TMP/home"
COMPANY="$TMP/company"
DEPTS="$COMPANY/departments"
STATE="$TMP/.workforce-build-state.json"
mkdir -p "$SANDBOX_HOME" "$DEPTS"

# Fixture state exactly as the prebuild's final write does: one entry per
# prebuilt id ({slug, status prebuilt}), including master-orchestrator.
python3 - "$STATE" <<'PY'
import json, sys
slugs = ["master-orchestrator", "ceo", "marketing", "sales", "support"]
state = {
    "companyId": "scratch-canary-co",
    "companySlug": "scratch-canary-co",
    "buildType": "standard-first",
    "departments": [{"slug": s, "status": "prebuilt"} for s in slugs],
}
json.dump(state, open(sys.argv[1], "w"), indent=2)
PY

# Case 1: SOUL.md present -> block settles the orchestrator entries to done
# and evaluate() no longer reports "departments".
mkdir -p "$DEPTS/master-orchestrator" "$DEPTS/ceo"
printf '# soul\n' > "$DEPTS/master-orchestrator/SOUL.md"
printf '# soul\n' > "$DEPTS/ceo/SOUL.md"
python3 - "$SCRIPT_DIR/build-workforce.py" "$STATE" "$DEPTS" <<'PY'
import importlib.util, json, sys
bw_path, state_path, depts_dir = sys.argv[1:4]
spec = importlib.util.spec_from_file_location("bw", bw_path)
bw = importlib.util.module_from_spec(spec)
sys.modules["bw"] = bw
spec.loader.exec_module(bw)
import workforce_completion
state = json.load(open(state_path))
depts = state["departments"]
fails = []
src = open(bw_path, encoding="utf-8").read().splitlines()
start = next(i for i, l in enumerate(src) if "# BU-52:" in l)
end = next(i for i, l in enumerate(src)
           if i > start and l.strip().startswith("# Departments the diff dropped"))
body = [l[12:] if l.startswith(" " * 12) else l for l in src[start:end] if l.strip()]
fn_src = ("def _bu52(depts, DEPARTMENTS_DIR, registration_failures):\n"
          "    from datetime import datetime\n"
          "    _now = datetime.now().isoformat()\n"
          + "".join("    " + l + "\n" for l in body))
ns = {"os": __import__("os"), "_decline_norm": bw._decline_norm}
exec(compile(fn_src, "<bu52>", "exec"), ns)
ns["_bu52"](depts, depts_dir, fails)
by_slug = {e.get("slug"): e for e in depts if isinstance(e, dict)}
ok = True
for slug in ("master-orchestrator", "ceo"):
    if by_slug.get(slug, {}).get("status") != "done":
        print(f"FAIL: {slug} not settled to done (status={by_slug.get(slug, {}).get('status')})")
        ok = False
if fails:
    print(f"FAIL: unexpected registration failures: {fails}")
    ok = False
for e in depts:
    if isinstance(e, dict) and e.get("status") != "done":
        e["status"] = "done"
full = dict(interviewComplete=True, interviewQc={"status": "pass"},
            roleLibraryStatus="done", sopLibraryStatus="done",
            commsAutomationStatus="done", companyId="x", companySlug="x",
            confirmationsComplete=True, buildType="standard-first", buildId="b1",
            buildChecks={k: {"status": "pass", "buildId": "b1"}
                         for k in ("registration", "postBuild", "qc", "libraries")},
            departments=depts)
full["buildArtifactVerification"] = {
    "root": None, "digest": None, "digestVersion": 2,
    "inputDigest": workforce_completion.input_digest(full)}
got = [m for m in workforce_completion.evaluate(full)
       if m not in ("changed-or-missing-artifacts", "changed-inputs")]
if "departments" in got:
    print(f"FAIL: evaluate still reports departments: {got}")
    ok = False
else:
    print(f"PASS: evaluate clean of departments gate (remaining={got})")
sys.exit(0 if ok else 1)
PY
[ $? -eq 0 ] && good "SOUL present: orchestrator entries settle, evaluate clean" \
              || bad "SOUL present: orchestrator entries did not settle"

# Case 2: without the SOUL file the entry stays prebuilt.
rm -f "$DEPTS/master-orchestrator/SOUL.md"
python3 - "$SCRIPT_DIR/build-workforce.py" "$DEPTS" <<'PY'
import importlib.util, sys
bw_path, depts_dir = sys.argv[1:3]
spec = importlib.util.spec_from_file_location("bw", bw_path)
bw = importlib.util.module_from_spec(spec)
sys.modules["bw"] = bw
spec.loader.exec_module(bw)
src = open(bw_path, encoding="utf-8").read().splitlines()
start = next(i for i, l in enumerate(src) if "# BU-52:" in l)
end = next(i for i, l in enumerate(src)
           if i > start and l.strip().startswith("# Departments the diff dropped"))
body = [l[12:] if l.startswith(" " * 12) else l for l in src[start:end] if l.strip()]
fn_src = ("def _bu52(depts, DEPARTMENTS_DIR, registration_failures):\n"
          "    from datetime import datetime\n"
          "    _now = datetime.now().isoformat()\n"
          + "".join("    " + l + "\n" for l in body))
ns = {"os": __import__("os"), "_decline_norm": bw._decline_norm}
exec(compile(fn_src, "<bu52>", "exec"), ns)
depts = [{"slug": "master-orchestrator", "status": "prebuilt"},
         {"slug": "marketing", "status": "prebuilt"}]
fails = []
ns["_bu52"](depts, depts_dir, fails)
by_slug = {e.get("slug"): e for e in depts}
ok = (by_slug["master-orchestrator"].get("status") == "prebuilt"
      and "orchestrator-foundation-missing" in fails)
print(f"PASS: no SOUL -> entry stays prebuilt, failure recorded"
      if ok else f"FAIL: no-SOUL case wrong: {depts} {fails}")
sys.exit(0 if ok else 1)
PY
[ $? -eq 0 ] && good "SOUL absent: entry stays prebuilt" \
              || bad "SOUL absent: entry did not stay prebuilt"

echo "=============================================="
echo "test-standard-first-orchestrator-settles: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
