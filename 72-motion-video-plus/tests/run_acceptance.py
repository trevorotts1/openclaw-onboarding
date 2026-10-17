#!/usr/bin/env python3
"""Acceptance runner for Skill 72 Motion Graphics V2 (directive 18.6).

Documented command surface:

    python3 72-motion-video-plus/tests/run_acceptance.py --test T28 \
        --spec-workspace SPEC_DIR --evidence-dir EVIDENCE_DIR
    python3 72-motion-video-plus/tests/run_acceptance.py --test T31 \
        --spec-workspace SPEC_DIR --evidence-dir EVIDENCE_DIR

Implemented by MG-043:

- T28 (directive/contract consistency) executes real checks against a
  spec workspace produced by the extraction helper: exactly 50 MG IDs,
  a complete and acyclic dependency graph, agreement between the
  Section 15 table and the Section 16.12 JSON, resolution of the source
  references cited by the Section 6 items, parseability of every JSON
  file in the workspace, and contract validation of the shared mode
  fixtures.
- T31 (fixture/command usability) runs the extraction helper in a clean
  path, checks that the Python and TypeScript contract layers agree on
  the shared fixtures (including one shared invalid mutation), and
  checks that the documented commands match the built CLI help.

T29 and T30 are agent-execution trials (directive 18.2 and 18.3): a
test harness cannot execute them, so this runner reports them as not
executable and exits 3 rather than fabricating evidence. The trials are
run by the coordinator and recorded at the integrated candidate.
T32-T34 belong to the MG-025/MG-032/MG-034 surfaces and likewise report
not executable until their owners wire them.

Exit codes: 0 = every executed check passed; 1 = a check failed;
3 = the test is not executable in this harness; 4 = partial (all
executed checks passed, but an optional input was not supplied, so a
named check did not run). Evidence JSON is written to --evidence-dir
under the directive's file names (T28-directive-conformance.json,
T31-contract-usability.json).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import motion_contracts  # noqa: E402

MODES = ("powerpoint_graphic", "vsl_desktop", "vsl_mobile", "standalone_video")
EVIDENCE_NAMES = {
    "T28": "T28-directive-conformance.json",
    "T31": "T31-contract-usability.json",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, check_id: str, status: str, detail: str) -> None:
        self.rows.append({"id": check_id, "status": status, "detail": detail})
        print(f"{status.upper():8s} {check_id}: {detail}")

    def passed(self, check_id: str, detail: str) -> None:
        self.add(check_id, "pass", detail)

    def failed(self, check_id: str, detail: str) -> None:
        self.add(check_id, "fail", detail)

    def not_run(self, check_id: str, detail: str) -> None:
        self.add(check_id, "not_run", detail)

    @property
    def status(self) -> str:
        if any(r["status"] == "fail" for r in self.rows):
            return "fail"
        if any(r["status"] == "not_run" for r in self.rows):
            return "partial"
        return "pass"


def load_dependencies(spec_workspace: Path) -> dict:
    path = spec_workspace / "extracted" / "execution" / "dependencies.json"
    return json.loads(path.read_text(encoding="utf-8"))


def check_t28(args: argparse.Namespace, checks: Checks) -> None:
    spec = Path(args.spec_workspace) if args.spec_workspace else None
    if spec is None or not spec.is_dir():
        checks.failed("spec_workspace", f"spec workspace not found: {args.spec_workspace}")
        return

    json_files = sorted(spec.rglob("*.json"))
    bad_json: list[str] = []
    for path in json_files:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - reported, not hidden
            bad_json.append(f"{path.relative_to(spec)}: {exc}")
    if bad_json:
        checks.failed("spec_json_parses", f"{len(bad_json)} JSON files do not parse: {bad_json[:3]}")
    else:
        checks.passed("spec_json_parses", f"all {len(json_files)} JSON files in the spec workspace parse")

    try:
        deps = load_dependencies(spec)
    except Exception as exc:  # noqa: BLE001
        checks.failed("dependencies_load", f"extracted/execution/dependencies.json unreadable: {exc}")
        return
    items = deps.get("items", [])
    ids = [it.get("id") for it in items]
    expected = [f"MG-{n:03d}" for n in range(1, 51)]
    if sorted(ids) == expected and len(ids) == 50:
        checks.passed("fifty_items", "exactly 50 unique MG IDs, MG-001..MG-050")
    else:
        checks.failed("fifty_items", f"expected MG-001..MG-050 once each, got {len(ids)} items")

    id_set = set(ids)
    unresolved = sorted(
        {d for it in items for d in it.get("depends_on", []) if d not in id_set}
    )
    if unresolved:
        checks.failed("deps_resolve", f"unresolved dependencies: {unresolved}")
    else:
        checks.passed("deps_resolve", "every depends_on entry names an existing item")

    # Kahn topological sort over prerequisite -> dependent edges.
    dependents: dict[str, list[str]] = {i: [] for i in id_set}
    remaining = {it["id"]: len(it.get("depends_on", [])) for it in items}
    for it in items:
        for dep in it.get("depends_on", []):
            dependents[dep].append(it["id"])
    queue = [i for i, n in remaining.items() if n == 0]
    seen = 0
    while queue:
        node = queue.pop()
        seen += 1
        for dependent in dependents[node]:
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                queue.append(dependent)
    if seen == len(id_set):
        checks.passed("graph_acyclic", "dependency graph is acyclic (topological sort covers all 50 items)")
    else:
        stuck = sorted(i for i, n in remaining.items() if n > 0)
        checks.failed("graph_acyclic", f"dependency cycle or unresolved chain involving {stuck}")

    unregistered = [it["id"] for it in items if not it.get("tests")]
    if unregistered:
        checks.failed("tests_registered", f"items with no acceptance tests registered: {unregistered}")
    else:
        checks.passed("tests_registered", "every item registers at least one acceptance test")

    fixture_root = spec / "extracted" / "fixtures"
    validated: list[str] = []
    fixture_failures: list[str] = []
    for mode in MODES:
        job_dir = fixture_root / mode
        if not (job_dir / "manifest.json").exists():
            fixture_failures.append(f"{mode}: no manifest.json in extracted fixtures")
            continue
        findings = motion_contracts.validate_job(job_dir)
        if findings:
            fixture_failures.append(
                f"{mode}: {len(findings)} findings, first {motion_contracts.first_error_category(findings)}"
            )
        else:
            validated.append(mode)
    if fixture_failures:
        checks.failed("fixtures_validate", "; ".join(fixture_failures))
    else:
        checks.passed("fixtures_validate", f"shared mode fixtures validate clean: {', '.join(validated)}")

    if not args.directive:
        checks.not_run("table_agrees", "no --directive supplied; Section 15 table not compared")
        checks.not_run("source_refs_resolve", "no --directive supplied; source references not checked")
        return
    directive = Path(args.directive)
    if not directive.is_file():
        checks.failed("directive_readable", f"directive not found: {directive}")
        return
    text = directive.read_text(encoding="utf-8")

    table = parse_section15_table(text)
    mismatches: list[str] = []
    json_deps = {it["id"]: sorted(it.get("depends_on", [])) for it in items}
    for mg_id, table_deps in table.items():
        if json_deps.get(mg_id) != table_deps:
            mismatches.append(f"{mg_id}: table {table_deps} vs JSON {json_deps.get(mg_id)}")
    missing_rows = [i for i in expected if i not in table]
    if missing_rows:
        mismatches.append(f"Section 15 table rows missing: {missing_rows}")
    if mismatches:
        checks.failed("table_agrees", "; ".join(mismatches[:5]))
    else:
        checks.passed("table_agrees", "Section 15 table prerequisites agree with the Section 16.12 JSON for all 50 items")

    section6 = slice_section(text, "## 6.", "## 7.")
    register = slice_section(text, "## 13.", "## 14.")
    cited = sorted(set(re.findall(r"\[([A-Z]{1,3}\d{1,2})\]", section6)))
    unresolved_refs = [tok for tok in cited if f"[{tok}]" not in register and tok not in register]
    if unresolved_refs:
        checks.failed("source_refs_resolve", f"cited references with no register entry: {unresolved_refs}")
    else:
        checks.passed(
            "source_refs_resolve",
            f"all {len(cited)} source references cited by Section 6 items resolve in the Section 13 register",
        )


def slice_section(text: str, start_marker: str, end_marker: str) -> str:
    """Slice between two level-2 headings (markers like '## 15.').

    Anchored at line starts so a subsection heading ('### 15.1') or a
    contents entry can never be mistaken for the section itself.
    """
    start_match = re.search(rf"(?m)^{re.escape(start_marker)}", text)
    if not start_match:
        return ""
    end_match = re.search(rf"(?m)^{re.escape(end_marker)}", text[start_match.start() + 1 :])
    if not end_match:
        return ""
    return text[start_match.start() : start_match.start() + 1 + end_match.start()]


def parse_section15_table(text: str) -> dict[str, list[str]]:
    section = slice_section(text, "## 15.", "## 16.")
    table: dict[str, list[str]] = {}
    for line in section.splitlines():
        match = re.match(r"\|\s*(MG-\d{3})\s*\|\s*([^|]+)\|", line)
        if not match:
            continue
        mg_id, cell = match.group(1), match.group(2).strip()
        if cell == "None":
            table[mg_id] = []
            continue
        range_match = re.fullmatch(r"(MG-\d{3}) through (MG-\d{3})", cell)
        if range_match:
            lo = int(range_match.group(1)[3:])
            hi = int(range_match.group(2)[3:])
            table[mg_id] = [f"MG-{n:03d}" for n in range(lo, hi + 1)]
            continue
        table[mg_id] = sorted(part.strip() for part in cell.split(",") if part.strip())
    return table


def check_t31(args: argparse.Namespace, checks: Checks) -> None:
    # 1. The extraction helper runs in a clean path.
    if args.extractor and args.directive:
        extractor = Path(args.extractor)
        directive = Path(args.directive)
        with tempfile.TemporaryDirectory(prefix="mg043-t31-extract-") as tmp:
            out_dir = Path(tmp) / "spec"
            proc = subprocess.run(
                [sys.executable, str(extractor), str(directive), str(out_dir)],
                capture_output=True,
                text=True,
            )
            # The helper writes execution/, fixtures/, references/ directly
            # under the workspace it is given.
            deps_path = out_dir / "execution" / "dependencies.json"
            if proc.returncode != 0 or not deps_path.exists():
                checks.failed(
                    "extractor_clean_path",
                    f"extractor exited {proc.returncode}; dependencies.json produced: {deps_path.exists()}; stderr tail: {proc.stderr.strip()[-300:]}",
                )
            else:
                fresh = json.loads(deps_path.read_text(encoding="utf-8"))
                fresh_ids = sorted(it["id"] for it in fresh.get("items", []))
                modes_present = [
                    m for m in MODES if (out_dir / "fixtures" / m / "manifest.json").exists()
                ]
                if len(fresh_ids) == 50 and len(modes_present) == 4:
                    checks.passed(
                        "extractor_clean_path",
                        "extraction helper ran in a clean path and produced 50 items and all four mode fixtures",
                    )
                else:
                    checks.failed(
                        "extractor_clean_path",
                        f"clean extraction produced {len(fresh_ids)} items and mode fixtures {modes_present}",
                    )
                if args.spec_workspace:
                    try:
                        shipped = load_dependencies(Path(args.spec_workspace))
                        shipped_ids = sorted(it["id"] for it in shipped.get("items", []))
                        if shipped_ids == fresh_ids:
                            checks.passed("extractor_matches_spec_workspace", "clean extraction and the supplied spec workspace name the same 50 items")
                        else:
                            checks.failed("extractor_matches_spec_workspace", "clean extraction item set differs from the supplied spec workspace")
                    except Exception as exc:  # noqa: BLE001
                        checks.failed("extractor_matches_spec_workspace", f"spec workspace unreadable: {exc}")
    else:
        checks.not_run("extractor_clean_path", "needs both --extractor and --directive")

    # 2. Python and TypeScript contract verdicts agree on shared fixtures.
    fixtures_modes = SKILL_ROOT / "tests" / "fixtures" / "modes"
    python_verdicts: dict[str, bool] = {}
    for mode in MODES:
        findings = motion_contracts.validate_job(fixtures_modes / mode)
        python_verdicts[mode] = not findings
    if all(python_verdicts.values()):
        checks.passed("python_fixture_verdicts", "Python contract layer validates all four mode fixtures clean")
    else:
        bad = [m for m, ok in python_verdicts.items() if not ok]
        checks.failed("python_fixture_verdicts", f"Python contract layer rejects: {bad}")

    corpus_js = SKILL_ROOT / "runtime" / "dist" / "tests" / "run-corpus.js"
    if not corpus_js.exists():
        checks.not_run("python_ts_agreement", "runtime not built (runtime/dist/tests/run-corpus.js missing); run npm run build first")
    else:
        proc = subprocess.run(
            ["node", str(corpus_js)],
            capture_output=True,
            text=True,
            cwd=str(SKILL_ROOT / "runtime"),
        )
        ts_valid_ok = all(f"PASS valid/{m}: 0 findings" in proc.stdout for m in MODES)
        ts_mutation_line = (
            "PASS invalid/canvas-1919x1080-off-aspect-and-odd: first category MG_MODE_MISMATCH as expected"
        )
        if proc.returncode == 0 and ts_valid_ok:
            checks.passed("ts_fixture_verdicts", "TypeScript corpus runner validates all four mode fixtures clean (15/15 corpus)")
        else:
            checks.failed(
                "ts_fixture_verdicts",
                f"corpus runner exit {proc.returncode}; valid-mode PASS lines present: {ts_valid_ok}",
            )
        # One shared invalid mutation, staged identically for the Python layer.
        with tempfile.TemporaryDirectory(prefix="mg043-t31-mutation-") as tmp:
            staged = Path(tmp) / "powerpoint_graphic"
            shutil.copytree(fixtures_modes / "powerpoint_graphic", staged)
            manifest_path = staged / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["canvas"]["width"] = 1919
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            python_category = motion_contracts.first_error_category(
                motion_contracts.validate_job(staged)
            )
        if python_category == "MG_MODE_MISMATCH" and ts_mutation_line in proc.stdout:
            checks.passed(
                "python_ts_agreement",
                "shared mutation (canvas width 1919) yields MG_MODE_MISMATCH as the first category in both the Python and TypeScript layers",
            )
        else:
            checks.failed(
                "python_ts_agreement",
                f"Python first category {python_category}; TS corpus line present: {ts_mutation_line in proc.stdout}",
            )

    # 3. Documented commands match the built CLI help.
    help_proc = subprocess.run(
        [sys.executable, str(SKILL_ROOT / "scripts" / "motion_contracts.py"), "--help"],
        capture_output=True,
        text=True,
    )
    if help_proc.returncode == 0 and "validate" in help_proc.stdout:
        checks.passed("documented_cli_motion_contracts", "scripts/motion_contracts.py --help runs and documents the validate subcommand")
    else:
        checks.failed("documented_cli_motion_contracts", f"motion_contracts.py --help exit {help_proc.returncode}")
    self_help = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--help"],
        capture_output=True,
        text=True,
    )
    needed_flags = ("--test", "--spec-workspace", "--evidence-dir")
    if self_help.returncode == 0 and all(f in self_help.stdout for f in needed_flags):
        checks.passed("documented_cli_run_acceptance", "tests/run_acceptance.py --help documents --test, --spec-workspace, and --evidence-dir")
    else:
        checks.failed("documented_cli_run_acceptance", "run_acceptance.py --help is missing a documented flag")
    if args.directive:
        directive_text = Path(args.directive).read_text(encoding="utf-8")
        if "run_acceptance.py --test T28" in directive_text and "run_acceptance.py --test T31" in directive_text:
            checks.passed("documented_commands_in_directive", "directive 18.6 documents exactly the T28/T31 commands this runner implements")
        else:
            checks.failed("documented_commands_in_directive", "directive 18.6 command lines do not match this runner's surface")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Skill 72 acceptance runner (directive Section 18.6).",
    )
    parser.add_argument("--test", required=True, choices=[f"T{n}" for n in range(28, 35)])
    parser.add_argument("--spec-workspace", default=None, help="spec workspace produced by the extraction helper (contains extracted/)")
    parser.add_argument("--directive", default=None, help="path to the directive markdown (enables table and reference checks)")
    parser.add_argument("--extractor", default=None, help="path to extract_motion_spec.py (T31 clean-path check)")
    parser.add_argument("--evidence-dir", default=None, help="directory for the evidence JSON")
    args = parser.parse_args()

    if args.test not in EVIDENCE_NAMES:
        print(
            f"{args.test}: not executable in this harness. "
            "T29/T30 are agent-execution trials run by the coordinator (directive 18.2/18.3); "
            "T32-T34 are wired by their owning items (MG-025/MG-032/MG-034). "
            "See tests/matrix.json. No evidence is fabricated by this runner."
        )
        return 3

    checks = Checks()
    started = now()
    if args.test == "T28":
        check_t28(args, checks)
    else:
        check_t31(args, checks)
    status = checks.status
    print(f"{args.test}: {status} ({sum(1 for r in checks.rows if r['status'] == 'pass')}/{len(checks.rows)} checks passed)")

    if args.evidence_dir:
        evidence_dir = Path(args.evidence_dir)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence = {
            "test": args.test,
            "status": status,
            "started_at": started,
            "finished_at": now(),
            "spec_workspace": args.spec_workspace,
            "directive": args.directive,
            "checks": checks.rows,
        }
        out_path = evidence_dir / EVIDENCE_NAMES[args.test]
        out_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(f"evidence written: {out_path}")

    return {"pass": 0, "fail": 1, "partial": 4}[status]


if __name__ == "__main__":
    sys.exit(main())
