"""CLI: compile a route, dispatch every page, assemble a package, check one, or report dependencies.

Exit 0 pass, 2 fail. The Council planning step runs on route/assemble and is
always recorded; a not-ready Council never changes the exit code.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List

from . import (checks, council, dependencies, image_plan, intake, launch_bridge,
               launch_plan, package, route)
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
    for slot in package.EXTRA_SLOTS:  # a second page of a role (downsell_2) rides beside its parent
        extra = Path(args.pieces) / f"{slot}.json"
        if extra.is_file():
            pieces[slot] = _read_json(extra)
    report_path = Path(args.pieces).parent / "dispatch-report.json"
    report = _read_json(report_path) if report_path.is_file() else {}
    plan = _read_json(args.launch_plan) if args.launch_plan else None
    deliveries = _read_json(args.deliveries) if args.deliveries else None
    out = package.assemble(Path(args.out), normalized, graph, pieces,
                           source_root=Path(args.pieces).parent, council=advice,
                           require_designs=not args.allow_no_designs,
                           to_confirm=report.get("to_confirm"),
                           landing_pages=report.get("landing_pages"),
                           launch_plan=plan, deliveries=deliveries)
    _emit({"manifest": out["manifest_path"], "receipt": out["receipt_path"],
           "council": advice["status"], "designs_required": not args.allow_no_designs,
           "to_confirm": out["manifest"]["to_confirm"],
           "launch_plan_completeness":
               (out["manifest"].get("launch_plan") or {}).get("completeness")})
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    """Validate a shared launch plan: Black Friday calendar + planned-unit completeness."""
    plan = _read_json(args.plan)
    deliveries = _read_json(args.deliveries) if args.deliveries else None
    record = launch_plan.record(plan, deliveries)
    launch_plan.assert_complete(record["completeness"])
    _emit(record)
    return 0


def cmd_dispatch(args: argparse.Namespace) -> int:
    adapters_config = _read_json(args.adapters) if args.adapters else None
    adapter_inputs = _read_json(args.adapter_inputs) if args.adapter_inputs else None
    report = launch_bridge.run(
        _read_json(args.intake), Path(args.out),
        approval=_read_json(args.approval),
        client_identity_ref=args.client, worker_identity_ref=args.worker,
        adapters_config=adapters_config, adapter_inputs=adapter_inputs,
        parallel=args.parallel,
        scoped_approvals=_read_json(args.scoped_approvals) if args.scoped_approvals else None,
        extra_pages=tuple(args.extra_page or ()),
        landing_pages=[k.strip() for k in args.landing_pages.split(",") if k.strip()]
        if args.landing_pages else None)
    _emit(report)
    print()
    for line in launch_bridge.summary_lines(report):
        print(line)
    return 0


def cmd_questions(_args: argparse.Namespace) -> int:
    """The picture questions as canonical question objects, for any harness to ask in its own way."""
    _emit({"questions": image_plan.QUESTIONS})
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    fails = checks.check_package(Path(args.manifest), Path(args.root),
                                 require_designs=True if args.require_designs else None)
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
    a.add_argument("--allow-no-designs", action="store_true",
                   help="assemble without requiring every page's wireframes and mockups; recorded "
                        "in the manifest, never the default for a delivery")
    a.add_argument("--launch-plan",
                   help="the shared launch plan (U-CONTRACT); its Black Friday calendar and every "
                        "planned email, text, automation and requested AI must be delivered")
    a.add_argument("--deliveries",
                   help="JSON object of unit id -> delivery result ({'state': 'complete'})")
    a.set_defaults(fn=cmd_assemble)

    pl = sub.add_parser("plan", help="validate a shared launch plan's calendar and completeness")
    pl.add_argument("--plan", required=True)
    pl.add_argument("--deliveries",
                    help="JSON object of unit id -> delivery result; omit to see what is missing")
    pl.set_defaults(fn=cmd_plan)

    x = sub.add_parser("dispatch", help="turn the intake into a Skill 49 launch record and build every page")
    x.add_argument("--intake", required=True)
    x.add_argument("--out", required=True, help="run folder: launch.json, dispatch/, pieces/, dispatch-report.json")
    x.add_argument("--approval", required=True, help="the client's recorded plan approval (JSON record)")
    x.add_argument("--client", required=True, help="the client's identity reference")
    x.add_argument("--worker", required=True, help="the identity running the build (never the approver)")
    x.add_argument("--adapters", help="ready Skill 49 adapter configuration (JSON)")
    x.add_argument("--adapter-inputs", help="per-page inputs to build the adapter configuration (JSON)")
    x.add_argument("--parallel", type=int, default=None,
                   help="build the independent pages as this many parallel lanes (1 = one at a time; "
                        "default: this computer's worker count)")
    x.add_argument("--scoped-approvals", help="JSON array of extra scoped approvals")
    x.add_argument("--landing-pages",
                   help="the landing pages the client wants: landing, sales or landing,sales "
                        "(default: the set Skill 49 recommends, flagged 'to confirm')")
    x.add_argument("--extra-page", action="append", choices=["downsell_2"],
                   help="an extra design page the client opted into (downsell_2); repeat for more")
    x.set_defaults(fn=cmd_dispatch)

    q = sub.add_parser("questions", help="the picture questions a client is asked, as data")
    q.set_defaults(fn=cmd_questions)

    c = sub.add_parser("check", help="run package completeness checks")
    c.add_argument("--manifest", required=True)
    c.add_argument("--root", required=True)
    c.add_argument("--require-designs", action="store_true",
                   help="also require every page's labeled wireframes and mockups (AF-LAUNCH-PAGE-DESIGNS)")
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
    except (intake.IntakeError, route.RouteError, package.PackageError,
            launch_bridge.BridgeError, image_plan.ImagePlanError,
            launch_plan.LaunchPlanError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
