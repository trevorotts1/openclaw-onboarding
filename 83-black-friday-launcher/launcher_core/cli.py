"""CLI: compile a route, assemble a package, check one, or report dependencies.

Exit 0 pass, 2 fail. The Council planning step runs on route/assemble and is
always recorded; a not-ready Council never changes the exit code.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List

from . import checks, council, dependencies, intake, package, route
from .constants import DECIDED, SEAMS


def _read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _emit(obj: Any) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True))


def cmd_route(args: argparse.Namespace) -> int:
    normalized = intake.validate(_read_json(args.intake))
    advice = council.planning_step(normalized)
    record = route.launch_record(normalized, advice)
    graph = route.compile_route(normalized, advice)
    _emit({"council": advice, "graph": graph, "launch_record": record})
    return 0


def cmd_assemble(args: argparse.Namespace) -> int:
    normalized = intake.validate(_read_json(args.intake))
    advice = council.planning_step(normalized)
    graph = route.compile_route(normalized, advice)
    pieces = {role: _read_json(Path(args.pieces) / f"{role}.json")
              for role in (n["role"] for n in graph["nodes"])}
    out = package.assemble(Path(args.out), normalized, graph, pieces,
                           source_root=Path(args.pieces).parent, council=advice)
    _emit({"manifest": out["manifest_path"], "receipt": out["receipt_path"],
           "council": advice["status"]})
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    fails = checks.check_package(Path(args.manifest), Path(args.root))
    if fails:
        print(f"FAIL {len(fails)} violation(s)")
        for f in fails:
            print(" -", f)
        return 2
    print("PASS package complete")
    return 0


def cmd_seams(_args: argparse.Namespace) -> int:
    _emit({"seams": list(SEAMS), "count": len(SEAMS),
           "decided": [d["id"] for d in DECIDED]})
    return 0


def cmd_dependencies(args: argparse.Namespace) -> int:
    try:
        report = dependencies.check(Path(args.root) if args.root else None)
    except dependencies.DependencyError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 2
    _emit(report)
    print(f"\n{len(report['present'])} present, {len(report['missing'])} missing, "
          f"{len(report['unverifiable'])} unverifiable; "
          f"enabled_in_999={report['enabled_in_999']}, "
          f"would_enable={report['would_enable']}")
    for entry in report["entries"]:
        print(f"  {entry['status'].upper():12s} {entry['id']}  ({entry['evidence']})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="launcher_core.cli")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("route", help="validate intake and compile the route graph")
    r.add_argument("--intake", required=True)
    r.set_defaults(fn=cmd_route)

    a = sub.add_parser("assemble", help="assemble package-manifest.json and receipt.json")
    a.add_argument("--intake", required=True)
    a.add_argument("--pieces", required=True, help="directory of <role>.json page results")
    a.add_argument("--out", required=True)
    a.set_defaults(fn=cmd_assemble)

    c = sub.add_parser("check", help="run package completeness checks")
    c.add_argument("--manifest", required=True)
    c.add_argument("--root", required=True)
    c.set_defaults(fn=cmd_check)

    s = sub.add_parser("seams", help="list open decisions and implemented decisions")
    s.set_defaults(fn=cmd_seams)

    d = sub.add_parser("dependencies",
                       help="report the 999 enablement dependencies present and missing")
    d.add_argument("--root", default=None,
                   help="repository root to inspect (default: the repo containing this skill)")
    d.set_defaults(fn=cmd_dependencies)
    return p


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except (intake.IntakeError, route.RouteError, package.PackageError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
