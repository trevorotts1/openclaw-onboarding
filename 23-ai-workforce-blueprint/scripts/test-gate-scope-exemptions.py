#!/usr/bin/env python3
"""
test_gate_scope.py — NO-WEAKENING proof for the Option-2 gate-scope exemptions.

This harness exercises the ACTUAL edited logic, two ways:

  PART A  (per-role SOP floor + PA reconcile + lib%):
          Builds /tmp fixture department dirs + a fixture _index.json, then runs
          the REAL analyzer extracted verbatim from the main `python3 - <<'PYEOF'`
          heredoc in qc-completeness.sh against them and asserts the reported
          roles_below_min_sops / library_pct.

  PART B  (TRIO gate):
          Builds /tmp fixture role-library dirs + _index.json, then runs the REAL
          trio block extracted verbatim from verify-library-gate.sh and asserts
          trio_done / trio_gaps.

Both extract the real code from the shipped scripts so the test cannot drift from
what actually runs. Exit 0 = every assertion (including every NO-WEAKENING case)
passed.
"""
import json, os, re, sys, tempfile, textwrap
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "23-ai-workforce-blueprint" / "scripts"
QC = SCRIPTS / "qc-completeness.sh"
GATE = SCRIPTS / "verify-library-gate.sh"

PASS = 0
FAIL = 0
def ok(msg):
    global PASS; PASS += 1; print(f"  [PASS] {msg}")
def bad(msg):
    global FAIL; FAIL += 1; print(f"  [FAIL] {msg}")


def _all_heredocs(path):
    """Return list of (opener_line, body) for every python3 ... <<'PYEOF' heredoc."""
    lines = path.read_text().split("\n")
    out = []; i = 0
    while i < len(lines):
        stripped = lines[i].lstrip()
        if (not stripped.startswith("#")) and "<<'PYEOF'" in lines[i] and "python3" in lines[i]:
            j = i + 1; body = []
            while j < len(lines) and lines[j].rstrip() != "PYEOF":
                body.append(lines[j]); j += 1
            out.append((lines[i], "\n".join(body))); i = j + 1
        else:
            i += 1
    return out

def extract_heredoc(path, opener_contains):
    """Body of the heredoc whose OPENER contains opener_contains; if not found,
    the largest heredoc (the main analyzer block)."""
    hds = _all_heredocs(path)
    for opener, body in hds:
        if opener_contains in opener:
            return body
    # fallback: largest block
    return max(hds, key=lambda ob: len(ob[1]))[1]


# A real-enough substantive standalone SOP: >=7KB, all DMAIC headers, no placeholder.
SUBSTANTIVE_SOP = (
    "## Define\n" + ("Define body line of real content.\n" * 80) +
    "## Measure\n" + ("Measure body line of real content.\n" * 80) +
    "## Analyze\n" + ("Analyze body line of real content.\n" * 80) +
    "## Improve\n" + ("Improve body line of real content.\n" * 80) +
    "## Control\n" + ("Control body line of real content.\n" * 80)
)
assert len(SUBSTANTIVE_SOP.encode()) >= 7168

# A filled how-to with the library provenance marker, >=3KB.
FILLED_HOWTO = (
    "<!-- workforce-provenance: source=role-library role-slug=x content_sha=y -->\n"
    + ("How-to body content line.\n" * 200)
)
assert len(FILLED_HOWTO.encode()) >= 3072

# A THIN how-to (no marker, < 3KB) — a genuinely unfilled role.
THIN_HOWTO = "# placeholder\n"


def make_role(dept_dir: Path, slug: str, *, filled=True, sops=4, identity=True):
    """Create a role folder. filled=library marker+size; sops=# substantive standalone SOPs."""
    r = dept_dir / slug
    r.mkdir(parents=True, exist_ok=True)
    (r / "how-to.md").write_text(FILLED_HOWTO if filled else THIN_HOWTO)
    if identity:
        (r / "IDENTITY.md").write_text("# identity\n")
    for n in range(1, sops + 1):
        (r / f"0{n}-sop.md").write_text(SUBSTANTIVE_SOP)


def run_analyzer(analyzer_code, departments_dir, index_json):
    """Run the extracted qc analyzer body with env wired to fixtures; return parsed report."""
    with tempfile.TemporaryDirectory() as td:
        log_file = Path(td) / "qc.log"
        json_file = Path(td) / "qc.json"
        log_file.write_text("");
        env = dict(os.environ)
        env.update({
            "SKILL_DIR": str(REPO / "23-ai-workforce-blueprint"),
            "COMPANY_ROOT": str(departments_dir.parent),
            "DEPARTMENTS_DIR": str(departments_dir),
            "DEPARTMENTS_JSON": str(departments_dir.parent / "departments.json"),
            "INDEX_JSON": str(index_json),
            "LOG_FILE": str(log_file),
            "JSON_FILE": str(json_file),
            "TS": "test",
        })
        # departments.json: select all on-disk depts (the analyzer also walks disk)
        (departments_dir.parent / "departments.json").write_text(json.dumps(
            {d.name: {"id": d.name} for d in departments_dir.iterdir() if d.is_dir()}))
        import subprocess
        prog = SCRIPTS / "_extracted_analyzer.py"
        prog.write_text(analyzer_code)
        try:
            p = subprocess.run([sys.executable, str(prog)], env=env,
                               capture_output=True, text=True)
            if p.returncode != 0 or not json_file.exists():
                print("ANALYZER STDERR:\n", p.stderr[-3000:])
                raise RuntimeError("analyzer failed")
        finally:
            prog.unlink(missing_ok=True)
        return json.loads(json_file.read_text())


def dept_report(report, dept_id):
    for d in report["departments"]:
        if d["dept_id"] == dept_id:
            return d
    raise AssertionError(f"dept {dept_id} not in report")


# ───────────────────────────── PART A ─────────────────────────────
print("=" * 70)
print("PART A — per-role SOP floor + lib% (qc-completeness.sh analyzer)")
print("=" * 70)
analyzer = extract_heredoc(QC, "__MAIN_ANALYZER__")  # not in any opener -> largest block

with tempfile.TemporaryDirectory() as root:
    root = Path(root)
    depts = root / "company" / "departments"
    depts.mkdir(parents=True)

    # Fixture canonical index:
    #   - "ops-min": minimal ops dept WITHOUT a trio in its roster; 4 client-facing
    #     roles all WITH real SOPs (the genuinely-complete minimal dept).
    #   - "full-dept": has the trio in roster; all roles templated.
    #   - "personal-assistant": 12 templated (incl meta-roles) + bespoke personas.
    index = {
        "version": "test", "total_roles": 0,
        "departments": {
            "ops-min": {"count": 4, "roles": [
                "director-of-ops-min", "worker-a", "worker-b", "qc-specialist"]},
            "full-dept": {"count": 6, "roles": [
                "director-of-full", "worker-a", "worker-b",
                "qc-specialist", "deep-research-specialist", "devils-advocate--full-dept"]},
            "personal-assistant": {"count": 12, "roles": [
                "calendar-scheduling-manager", "daily-briefing-specialist",
                "deep-research-specialist-personal-assistant",
                "devils-advocate-personal-assistant", "director-of-personal-assistant",
                "healer-personal-assistant", "inbox-manager", "personal-coach",
                "qc-specialist-personal-assistant", "sop-writer",
                "task-priority-manager", "travel-logistics-specialist"]},
        },
    }
    index_json = root / "_index.json"
    index_json.write_text(json.dumps(index))

    # ── ops-min: 4 client-facing roles, ALL with real SOPs ── should be floor-clean
    d = depts / "ops-min"; d.mkdir()
    for slug in index["departments"]["ops-min"]["roles"]:
        make_role(d, slug, filled=True, sops=4)
    (d / "governing-personas.md").write_text("x")

    # ── full-dept: trio present; META-ROLES carry NO SOPs (exempt); client roles 4 SOPs
    d = depts / "full-dept"; d.mkdir()
    make_role(d, "director-of-full", filled=True, sops=4)
    make_role(d, "worker-a", filled=True, sops=4)
    make_role(d, "worker-b", filled=True, sops=4)
    make_role(d, "qc-specialist", filled=True, sops=4)
    make_role(d, "deep-research-specialist", filled=True, sops=4)
    make_role(d, "devils-advocate--full-dept", filled=True, sops=0)  # EXEMPT meta-role, 0 SOPs
    (d / "governing-personas.md").write_text("x")

    # ── personal-assistant: 12 templated (sop-writer + devils-advocate carry 0 SOPs;
    #    the other 10 templated carry 4 SOPs), PLUS 3 bespoke personas with 0 SOPs.
    d = depts / "personal-assistant"; d.mkdir()
    for slug in index["departments"]["personal-assistant"]["roles"]:
        sops = 0 if (slug == "sop-writer" or "devils-advocate" in slug) else 4
        make_role(d, slug, filled=True, sops=sops)
    # bespoke (no-template) personas: NOT in roster, NO marker, 0 SOPs
    for bespoke in ["ceo-chief-of-staff", "household-estate-manager", "investor-relations-aide"]:
        make_role(d, bespoke, filled=False, sops=0)
    (d / "governing-personas.md").write_text("x")

    rep = run_analyzer(analyzer, depts, index_json)

    om = dept_report(rep, "ops-min")
    fd = dept_report(rep, "full-dept")
    pa = dept_report(rep, "personal-assistant")

    # ops-min: all 4 client-facing roles have SOPs -> 0 below floor, lib 100
    if om["roles_below_min_sops"] == 0:
        ok("ops-min: 0 roles below SOP floor (minimal dept passes)")
    else:
        bad(f"ops-min: expected 0 below floor, got {om['roles_below_min_sops']}")
    if abs(om["library_pct"] - 100.0) < 0.01:
        ok("ops-min: library_pct == 100")
    else:
        bad(f"ops-min: expected lib 100, got {om['library_pct']}")

    # full-dept: meta-role with 0 SOPs is EXEMPT -> 0 below floor
    if fd["roles_below_min_sops"] == 0:
        ok("full-dept: devils-advocate with 0 SOPs is exempt -> 0 below floor")
    else:
        bad(f"full-dept: expected 0 below floor, got {fd['roles_below_min_sops']}")
    # the floor denominator must EXCLUDE the exempt meta-role (5 applicable, not 6)
    if fd.get("sop_floor_applicable") == 5:
        ok("full-dept: sop_floor_applicable == 5 (meta-role excluded from denominator)")
    else:
        bad(f"full-dept: expected sop_floor_applicable 5, got {fd.get('sop_floor_applicable')}")

    # PA: 12 templated (2 meta exempt, 10 with SOPs) + 3 bespoke (exempt) -> 0 below floor
    if pa["roles_below_min_sops"] == 0:
        ok("PA: 0 below floor (10 templated w/ SOPs pass; 2 meta + 3 bespoke exempt)")
    else:
        bad(f"PA: expected 0 below floor, got {pa['roles_below_min_sops']}")
    # PA floor denominator = 10 (12 templated minus 2 exempt meta-roles); bespoke excluded
    if pa.get("sop_floor_applicable") == 10:
        ok("PA: sop_floor_applicable == 10 (12 templated - 2 meta; 3 bespoke excluded)")
    else:
        bad(f"PA: expected sop_floor_applicable 10, got {pa.get('sop_floor_applicable')}")
    # PA lib% computed over 12 templated only (bespoke have no marker) -> 100
    if abs(pa["library_pct"] - 100.0) < 0.01:
        ok("PA: library_pct == 100 over 12 templated (26-bespoke not counted)")
    else:
        bad(f"PA: expected lib 100 over templated, got {pa['library_pct']}")

# ── NO-WEAKENING fixtures (PART A) ────────────────────────────────────────────
print("-" * 70)
print("NO-WEAKENING (Part A): real client-facing/templated gaps STILL fail")
print("-" * 70)
with tempfile.TemporaryDirectory() as root:
    root = Path(root)
    depts = root / "company" / "departments"; depts.mkdir(parents=True)
    index = {"version": "t", "departments": {
        "ops-min": {"count": 4, "roles": ["director-of-ops-min", "worker-a", "worker-b", "qc-specialist"]},
        "personal-assistant": {"count": 12, "roles": [
            "calendar-scheduling-manager", "daily-briefing-specialist",
            "deep-research-specialist-personal-assistant", "devils-advocate-personal-assistant",
            "director-of-personal-assistant", "healer-personal-assistant", "inbox-manager",
            "personal-coach", "qc-specialist-personal-assistant", "sop-writer",
            "task-priority-manager", "travel-logistics-specialist"]},
    }}
    index_json = root / "_index.json"; index_json.write_text(json.dumps(index))

    # ops-min but worker-a (CLIENT-FACING, templated) has NO SOPs -> MUST fail
    d = depts / "ops-min"; d.mkdir()
    make_role(d, "director-of-ops-min", filled=True, sops=4)
    make_role(d, "worker-a", filled=True, sops=0)   # client-facing, no SOPs
    make_role(d, "worker-b", filled=True, sops=4)
    make_role(d, "qc-specialist", filled=True, sops=4)
    (d / "governing-personas.md").write_text("x")

    # PA but a TEMPLATED non-meta role (inbox-manager) has NO SOPs -> MUST fail;
    # and a TEMPLATED role (personal-coach) is NOT library-filled -> lib% < 100.
    d = depts / "personal-assistant"; d.mkdir()
    for slug in index["departments"]["personal-assistant"]["roles"]:
        if slug == "inbox-manager":
            make_role(d, slug, filled=True, sops=0)          # templated, no SOPs -> fail
        elif slug == "personal-coach":
            make_role(d, slug, filled=False, sops=4)         # templated, no marker -> lib% down
        elif slug == "sop-writer" or "devils-advocate" in slug:
            make_role(d, slug, filled=True, sops=0)
        else:
            make_role(d, slug, filled=True, sops=4)
    make_role(d, "bespoke-aide", filled=False, sops=0)        # bespoke, exempt
    (d / "governing-personas.md").write_text("x")

    rep = run_analyzer(analyzer, depts, index_json)
    om = dept_report(rep, "ops-min"); pa = dept_report(rep, "personal-assistant")

    if om["roles_below_min_sops"] >= 1:
        ok("ops-min: client-facing worker-a with 0 SOPs STILL fails (>=1 below floor)")
    else:
        bad("ops-min: client-facing 0-SOP role was wrongly exempted")

    if pa["roles_below_min_sops"] >= 1:
        ok("PA: templated inbox-manager with 0 SOPs STILL fails (>=1 below floor)")
    else:
        bad("PA: templated 0-SOP role was wrongly exempted")

    if pa["library_pct"] < 100.0:
        ok(f"PA: templated personal-coach unfilled STILL drags lib% < 100 ({pa['library_pct']})")
    else:
        bad("PA: unfilled templated role did not lower lib% (bespoke scoping too broad)")


# ───────────────────────────── PART B ─────────────────────────────
print("=" * 70)
print("PART B — TRIO gate (verify-library-gate.sh)")
print("=" * 70)
trio_code = extract_heredoc(GATE, '"$LIBRARY_DIR"')

def run_trio(library_dir):
    import subprocess
    prog = SCRIPTS / "_extracted_trio.py"
    prog.write_text(trio_code)
    try:
        out = subprocess.run([sys.executable, str(prog), str(library_dir)],
                             check=True, capture_output=True, text=True)
    finally:
        prog.unlink(missing_ok=True)
    return json.loads(out.stdout)

def build_library(tmp, depts):
    """depts: {dept: (roster_roles_list, on_disk_member_files_list)}; writes _index.json + files."""
    lib = Path(tmp) / "role-library"; lib.mkdir()
    index = {"version": "t", "departments": {}}
    for dept, (roster, on_disk) in depts.items():
        index["departments"][dept] = {"count": len(roster), "roles": roster}
        dd = lib / dept; dd.mkdir()
        for fname in on_disk:
            (dd / fname).write_text("# x\n")
    (lib / "_index.json").write_text(json.dumps(index))
    return lib

# Positive: minimal ops dept whose roster lacks the trio -> NOT required -> trio_done
with tempfile.TemporaryDirectory() as tmp:
    lib = build_library(tmp, {
        # podcast-like: roster has qc only; on disk only qc -> would fail old gate
        "podcast": (["director-of-podcast", "podcast-host", "audio-post-producer",
                     "qc-specialist-podcast"],
                    ["director-of-podcast.md", "podcast-host.md",
                     "audio-post-producer.md", "qc-specialist-podcast.md"]),
        # full dept: roster has trio + on disk has trio -> required + present -> pass
        "sales": (["director-of-sales", "qc-specialist", "deep-research-specialist",
                   "devils-advocate--sales"],
                  ["director-of-sales.md", "qc-specialist.md",
                   "deep-research-specialist.md", "devils-advocate--sales.md"]),
    })
    res = run_trio(lib)
    if res["trio_done"]:
        ok("trio_done == True (minimal podcast roster exempt; sales trio present)")
    else:
        bad(f"trio_done should be True; gaps={res['trio_gaps']}")
    if res["per_dept"]["podcast"].get("trioRequired") is False:
        ok("podcast marked trioRequired=False (roster lacks trio)")
    else:
        bad("podcast was not marked trioRequired=False")
    if res["per_dept"]["sales"].get("trioRequired") is True:
        ok("sales marked trioRequired=True (roster includes trio)")
    else:
        bad("sales was not marked trioRequired=True")

# NO-WEAKENING (Part B): a dept whose ROSTER includes the trio but is MISSING a
# member on disk STILL fails.
print("-" * 70)
print("NO-WEAKENING (Part B): roster-requires-trio dept missing a member STILL fails")
print("-" * 70)
with tempfile.TemporaryDirectory() as tmp:
    lib = build_library(tmp, {
        "marketing": (["director-of-marketing", "qc-specialist",
                       "deep-research-specialist", "devils-advocate--marketing"],
                      # MISSING the devils-advocate on disk
                      ["director-of-marketing.md", "qc-specialist.md",
                       "deep-research-specialist.md"]),
    })
    res = run_trio(lib)
    if not res["trio_done"] and any("marketing" in g for g in res["trio_gaps"]):
        ok("marketing (roster has trio) missing DA on disk STILL fails the trio gate")
    else:
        bad(f"marketing missing-DA was not caught; trio_done={res['trio_done']} gaps={res['trio_gaps']}")

# NO-WEAKENING (Part B): unreadable/absent roster entry => fail-closed (trio required)
with tempfile.TemporaryDirectory() as tmp:
    lib = Path(tmp) / "role-library"; lib.mkdir()
    # dept with NO _index.json entry, on disk missing DA -> must still fail (fail-closed)
    dd = lib / "rogue-dept"; dd.mkdir()
    (dd / "qc-specialist.md").write_text("x")
    (dd / "deep-research-specialist.md").write_text("x")
    (lib / "_index.json").write_text(json.dumps({"version": "t", "departments": {}}))
    res = run_trio(lib)
    if not res["trio_done"] and any("rogue-dept" in g for g in res["trio_gaps"]):
        ok("dept absent from index (fail-closed) missing DA STILL fails the trio gate")
    else:
        bad(f"fail-closed path broken; trio_done={res['trio_done']} gaps={res['trio_gaps']}")


print("=" * 70)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 70)
sys.exit(0 if FAIL == 0 else 1)
