#!/usr/bin/env bash
# tests/unit/persona-task-mode-wiring.test.sh
# (Leadership / Task-Mode wiring guard — see CHANGELOG v14.10.2.)
#
# CI guard: proves the LEADERSHIP / Task-Mode half of a persona blueprint is
# actually WIRED to fire at task time — not just documented in the index. It
# closes the gaps the leadership-wiring verify found: a present "core-update
# applied" marker that coexisted with a MISSING Persona Reflex body, a Reflex
# that said "load Task Mode" without saying HOW, a funnel rubric that graded
# persona NAMING but not governance-APPLICATION, role files that said "act AS the
# persona" with no path to load the governance, and a retriever that could not
# surface the Section-4 governance distinctly.
#
# Assertion groups (every one is a real, executed check — no prose-only pass):
#   (A) REFLEX-BODY-NOT-JUST-MARKER — run skill 22's CORE_UPDATES.md through the
#       REAL update-skills.sh merger; the produced AGENTS.md must carry the
#       core-update SENTINEL *and* the explicit Task-Mode load body (Section 4 +
#       Definition of Done + build-to-standard). A marker can never ship without
#       the execution-path body.
#   (B) PROTOCOL-HAS-LOAD-STEP — persona-matching-protocol.md carries the
#       MANDATORY at-task-time "Load and Apply the Task Mode" step naming Section 4
#       and the Definition of Done.
#   (C) RUBRIC-GRADES-GOVERNANCE — funnel_rubrics R-PERSONA-GROUNDING has a
#       task_mode_applied sub-check that is GRADUATED: a selection-log WITH the
#       Section-4 governance markers earns > 0, one WITHOUT earns exactly 0.
#   (D) RETRIEVER-MODE-AWARE — embedding_engine.search(...,mode='leadership')
#       returns the Section-4 governance row over the coaching row on a seeded
#       section-tagged index, and is a no-op on a legacy chunk-only index.
#   (E) ROLE-FILES-SELF-SUFFICIENT — every role file whose §2 says "Persona
#       Governance Override" also carries the concrete load step, so the role is
#       not silently dependent on a missing AGENTS.md Reflex.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

SKILL22="22-book-to-persona-coaching-leadership-system"

echo "=== persona-task-mode-wiring.test.sh ==="
echo ""

# ---------------------------------------------------------------------------
# (A) Persona Reflex BODY is present after the real merger — not just a marker.
# Reuse the same merger-extraction approach as core-updates-all-skills-wired.
# ---------------------------------------------------------------------------
echo "--- (A) REFLEX-BODY-NOT-JUST-MARKER ---"

PY_MERGER_FILE="$TMPDIR_TEST/merger.py"
python3 - "$REPO_ROOT/update-skills.sh" > "$PY_MERGER_FILE" 2>"$TMPDIR_TEST/extract.err" << 'PYSCRAPER'
import sys, re
content = open(sys.argv[1]).read()
fn_match = re.search(r'# ---- Helper: idempotent CORE_UPDATES\.md merger \(v12\.3\.11', content)
if not fn_match:
    sys.stderr.write("merger marker not found\n"); sys.exit(1)
pyeof_start = content.find("<<'PYEOF'\n", fn_match.start())
py_start = pyeof_start + len("<<'PYEOF'\n")
py_end = content.find('\nPYEOF\n', py_start)
if pyeof_start == -1 or py_end == -1:
    sys.stderr.write("PYEOF bounds not found\n"); sys.exit(1)
print(content[py_start:py_end])
PYSCRAPER

if ! head -1 "$PY_MERGER_FILE" | grep -q "^import"; then
    fail "(A) could not extract merger from update-skills.sh"
    cat "$TMPDIR_TEST/extract.err"
else
    FIX="$TMPDIR_TEST/fixtureA"; mkdir -p "$FIX"
    touch "$FIX/AGENTS.md" "$FIX/TOOLS.md" "$FIX/MEMORY.md" "$FIX/SOUL.md" "$FIX/IDENTITY.md" "$FIX/USER.md"
    SENT="<!-- skill:${SKILL22}:core-update-applied -->"
    python3 "$PY_MERGER_FILE" \
        "$REPO_ROOT/$SKILL22/CORE_UPDATES.md" \
        "$FIX/AGENTS.md" "$FIX/TOOLS.md" "$FIX/MEMORY.md" \
        "$FIX/SOUL.md" "$FIX/IDENTITY.md" "$FIX/USER.md" \
        "$SENT" "$SKILL22" "0" > /dev/null 2>&1 || true

    if grep -qF "$SENT" "$FIX/AGENTS.md"; then
        pass "(A) core-update sentinel present in AGENTS.md"
    else
        fail "(A) core-update sentinel MISSING from AGENTS.md"
    fi
    # The execution-path body must travel WITH the marker.
    BODY_OK=1
    grep -qi "Persona Reflex" "$FIX/AGENTS.md" || BODY_OK=0
    grep -qi "Section 4"      "$FIX/AGENTS.md" || BODY_OK=0
    grep -qi "Definition of Done" "$FIX/AGENTS.md" || BODY_OK=0
    grep -qi "gemini-search" "$FIX/AGENTS.md" || BODY_OK=0
    if [ "$BODY_OK" -eq 1 ]; then
        pass "(A) Task-Mode load BODY present (Persona Reflex + Section 4 + Definition of Done + gemini-search)"
    else
        fail "(A) Task-Mode load BODY missing — a marker shipped without the execution-path instructions"
    fi
fi
echo ""

# ---------------------------------------------------------------------------
# (B) persona-matching-protocol.md carries the mandatory load step.
# ---------------------------------------------------------------------------
echo "--- (B) PROTOCOL-HAS-LOAD-STEP ---"
PROTO="$REPO_ROOT/23-ai-workforce-blueprint/persona-matching-protocol.md"
B_OK=1
grep -qi "Load and Apply the Task Mode" "$PROTO" || B_OK=0
grep -qi "MANDATORY" "$PROTO" || B_OK=0
grep -qi "Section 4" "$PROTO" || B_OK=0
grep -qi "Definition of Done" "$PROTO" || B_OK=0
if [ "$B_OK" -eq 1 ]; then
    pass "(B) protocol has a mandatory Section-4 / Definition-of-Done load step"
else
    fail "(B) protocol is missing the mandatory Task-Mode load step"
fi

# (B2) NO-NAKED DEGRADED-STATE INVARIANT — the "Skill 22 not installed" edge case
# must NOT normalize persona-less operation. It must declare a DEGRADED state with a
# mandatory default-persona attachment (DEFAULT_PERSONA_FALLBACK) + install nag, so a
# future edit cannot silently regress it back to "valid state / operates without
# persona guidance". (F3.3)
B2_OK=1
grep -qi "DEGRADED" "$PROTO" || B2_OK=0
grep -qF "DEFAULT_PERSONA_FALLBACK" "$PROTO" || B2_OK=0
grep -qi "default fallback persona\|default-persona attachment\|Mandatory default-persona" "$PROTO" || B2_OK=0
grep -qi "install nag" "$PROTO" || B2_OK=0
# The old normalizing wording must be GONE (regression tripwire).
if grep -qi "operates without persona guidance. This is a valid state" "$PROTO"; then
    B2_OK=0
fi
if [ "$B2_OK" -eq 1 ]; then
    pass "(B2) Skill-22-absent edge case is a DEGRADED state with mandatory default-persona attachment + install nag"
else
    fail "(B2) protocol regressed: Skill-22-absent must be DEGRADED (default-persona + nag), not 'valid state'"
fi
echo ""

# ---------------------------------------------------------------------------
# (C) The funnel rubric GRADES governance application (graduated, not constant).
# ---------------------------------------------------------------------------
echo "--- (C) RUBRIC-GRADES-GOVERNANCE ---"
if python3 - "$REPO_ROOT" << 'PYC'
import os, sys, tempfile, shutil
repo = sys.argv[1]
sys.path.insert(0, os.path.join(repo, "23-ai-workforce-blueprint", "full-funnel-pipeline"))
import funnel_rubrics as R

def build(run_dir, with_markers):
    fr = os.path.join(run_dir, "working", "funnels", "demo")
    os.makedirs(fr, exist_ok=True)
    log = ("# persona-selection-log\n\n"
           "- selected_persona: hormozi-100m-offers\n"
           "- selector_ran: {\"ran\": true}\n\n"
           "## P1\n- task-id: p1-funnel-spec\n- selected_persona: hormozi-100m-offers\n")
    if with_markers:
        log += ("\n## Task-Mode governance applied (Section 4)\n"
                "- task_mode_loaded: .../persona-blueprint.md Section 4\n"
                "- execution_standard: value-equation decision logic\n"
                "- definition_of_done: offer stack before copy\n"
                "- failure_patterns: no feature-dump\n")
    open(os.path.join(fr, "persona-selection-log.md"), "w").write(log)

def grounding_subchecks(run_dir):
    res = {r.id: r for r in R.score_all(run_dir)}
    g = res["R-PERSONA-GROUNDING"]
    return {s["name"]: s["earned"] for s in g.subchecks}

tmp = tempfile.mkdtemp()
try:
    d_with = os.path.join(tmp, "with"); build(d_with, True)
    d_wo = os.path.join(tmp, "without"); build(d_wo, False)
    sc_with = grounding_subchecks(d_with)
    sc_wo = grounding_subchecks(d_wo)
    assert "task_mode_applied" in sc_with, "task_mode_applied sub-check absent"
    assert sc_with["task_mode_applied"] > 0, f"governance markers earned 0: {sc_with}"
    assert sc_wo["task_mode_applied"] == 0, f"no-marker run wrongly earned credit: {sc_wo}"
    assert sc_with["task_mode_applied"] != sc_wo["task_mode_applied"], "not graduated"
    print(f"OK task_mode_applied with={sc_with['task_mode_applied']} without={sc_wo['task_mode_applied']}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
PYC
then
    pass "(C) R-PERSONA-GROUNDING grades governance-applied (>0 with markers, 0 without)"
else
    fail "(C) R-PERSONA-GROUNDING does not grade governance application"
fi
echo ""

# ---------------------------------------------------------------------------
# (D) The retriever can surface the Section-4 governance distinctly.
# ---------------------------------------------------------------------------
echo "--- (D) RETRIEVER-MODE-AWARE ---"
if python3 - "$REPO_ROOT" << 'PYD'
import os, sys, sqlite3, tempfile
repo = sys.argv[1]
sys.path.insert(0, os.path.join(repo, "shared-utils"))
import embedding_engine as ee

tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "idx.sqlite")
c = sqlite3.connect(db); cur = c.cursor()
cur.execute("CREATE TABLE embeddings(id TEXT, file_path TEXT, chunk_index INT, content TEXT, "
            "vector BLOB, last_updated REAL, provider TEXT, model TEXT, dim INT, "
            "section_number INT, mode TEXT)")
rows = [
 ("1","x/coaching-personas/personas/hormozi/persona-blueprint.md",0,
  "Section 4 Agent Governance Framework execution standard definition of done failure patterns",
  b"",0,"gemini","gemini-embedding-2",3072,4,"leadership"),
 ("2","x/coaching-personas/personas/hormozi/persona-blueprint.md",1,
  "Section 3 coaching framework powerful questions support assessment",
  b"",0,"gemini","gemini-embedding-2",3072,3,"coaching"),
]
cur.executemany("INSERT INTO embeddings VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows)
c.commit(); c.close()

import io, contextlib
def run(mode):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ee.keyword_fallback_search("framework standard done support", 5, db_path=db, mode=mode)
    return buf.getvalue()

lead = run("leadership")
coach = run("coaching")
assert "Section 4" in lead and "Section 3" not in lead, f"leadership mode leaked coaching:\n{lead}"
assert "Section 3" in coach and "Section 4" not in coach, f"coaching mode leaked leadership:\n{coach}"

# Legacy chunk-only index (no mode/section columns) must NOT be filtered.
db2 = os.path.join(tmp, "legacy.sqlite")
c2 = sqlite3.connect(db2); cur2 = c2.cursor()
cur2.execute("CREATE TABLE embeddings(id TEXT, file_path TEXT, content TEXT)")
frag, params = ee._mode_filter_sql(cur2, "leadership")
assert frag == "" and params == [], f"legacy index wrongly filtered: {frag!r} {params!r}"
c2.close()
print("OK leadership->Section4, coaching->Section3, legacy index unfiltered")
PYD
then
    pass "(D) search(--mode leadership) surfaces Section-4 governance; legacy index unaffected"
else
    fail "(D) mode-aware retrieval not wired"
fi
echo ""

# ---------------------------------------------------------------------------
# (E) Every role file with §2 carries the concrete load step.
# ---------------------------------------------------------------------------
echo "--- (E) ROLE-FILES-SELF-SUFFICIENT ---"
MISSING=$(python3 - "$REPO_ROOT" << 'PYE'
import glob, os, sys
repo = sys.argv[1]
root = os.path.join(repo, "23-ai-workforce-blueprint", "templates", "role-library")
miss = []
for f in glob.glob(os.path.join(root, "**", "*.md"), recursive=True):
    t = open(f, encoding="utf-8").read()
    # Only files whose §2 is the actual "Persona Governance Override" SECTION.
    if "## 2. Persona Governance Override" not in t:
        continue
    if "How to load the persona's Task Mode" not in t:
        miss.append(os.path.relpath(f, repo))
print("\n".join(miss))
PYE
)
if [ -z "$MISSING" ]; then
    pass "(E) all role-library §2 sections carry the concrete Task-Mode load step"
else
    fail "(E) role files missing the load step:"
    echo "$MISSING" | sed 's/^/      /'
fi
echo ""

# ---------------------------------------------------------------------------
echo "========================================"
echo "RESULTS: $PASS passed, $FAIL failed"
echo "========================================"
[ "$FAIL" -gt 0 ] && exit 1
exit 0
