"""CLI: compile a route, dispatch every page, assemble a package, check one, or report dependencies.

Exit 0 pass, 2 fail. The Council planning step runs on route/assemble and is
always recorded; a not-ready Council never changes the exit code.

``dispatch`` and ``assemble`` run the dependency preflight first and refuse on any
required entry that is missing, so a green preflight means the launch can run.
``plan`` shows the client the launch in plain words and the plan hash an approval
must bind; ``dispatch``, ``assemble`` and ``check`` refuse an approval that binds a
different hash.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, List

from . import (checks, council, dependencies, image_plan, intake, launch_bridge,
               launch_plan, package, route)
from .constants import DECIDED, SEAMS

_TEST_ONLY_REF = "TEST-ONLY"  # the placeholder approval ref on test fixtures


class CliError(Exception):
    """A refusal the CLI makes itself (approval binding, bad arguments). Stable code, plain detail."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


def _read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _emit(obj: Any) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True))


def _launch_event(launch_id: str, event: dict) -> None:
    """Tell the Command Center about a stage (U-cc-01 emitter). Never raises, never changes an exit code."""
    try:
        import substrate  # routes/ is on sys.path through the launch_bridge import
        substrate.load("shared-utils/signature_launch/launch_events.py",
                       "launcher_launch_events").emit(83, launch_id, event)
    except Exception as exc:  # a Command Center outage never fails a launch
        print(f"[launch_events] skipped ({type(exc).__name__})", file=sys.stderr)


def _plan_hash(launch: dict) -> str:
    """The hash an approval binds: Skill 49's plan_document_hash of the launch record."""
    return launch_bridge.substrate.dispatch().vlp.plan_document_hash(launch)


def _page_choices(args: argparse.Namespace) -> dict:
    """The client's page choices as launch_bridge.run takes them. `plan` and `dispatch` both read them
    here, so the plan hash a client approves is the hash dispatch binds."""
    landing = [k.strip() for k in (args.landing_pages or "").split(",") if k.strip()]
    return {"landing_pages": landing or None, "extra_pages": tuple(args.extra_page or ())}


def _launch_for(normalized: dict, inputs: dict, **choices: Any) -> dict:
    return launch_bridge.to_launch_record(normalized, route.compile_route(normalized), inputs, **choices)


def _resolved_launch(payload: Any, **choices: Any) -> tuple:
    """(normalized intake, launch record) exactly as launch_bridge.run would build them."""
    normalized = intake.validate(payload)
    inputs, _ = image_plan.resolve(normalized.get("image_plan"),
                                   test_only=bool(normalized.get("test_only", True)))
    return normalized, _launch_for(normalized, inputs, **choices)


def _bind(normalized: dict, real_hash: str, real_ref: str) -> dict:
    """The approval the run records: the intake's claim, verified against the real hash and ref.

    intake.approval is a claim, never proof. It must equal the real plan hash and the
    approval record's own ref. A test fixture's placeholder ref (TEST-ONLY...) on a
    test_only intake is replaced by the verified values instead, so a test receipt never
    prints a made-up hash; any other mismatch is refused.
    """
    claim = normalized["approval"]
    if normalized.get("test_only", True) and claim["ref"].startswith(_TEST_ONLY_REF):
        return {"ref": real_ref, "hash": real_hash}
    if claim["hash"] != real_hash or claim["ref"] != real_ref:
        raise CliError(
            "AF-LAUNCH-APPROVAL-BINDING",
            f"the intake says it was approved as {claim['ref']!r} for plan {claim['hash'][:8]}, but the "
            f"approval on record is {real_ref!r} for plan {real_hash[:8]}. Nothing was built and nothing "
            "was spent; run `plan` to see the plan and its hash, and approve that.")
    return dict(claim)


def _json_object(path: Path) -> dict:
    try:
        doc = _read_json(path)
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def cmd_route(args: argparse.Namespace) -> int:
    normalized = intake.validate(_read_json(args.intake))
    advice = council.planning_step(normalized)
    record = route.launch_record(normalized, advice)
    graph = route.compile_route(normalized, advice)
    _emit({"council": advice, "graph": graph, "launch_record": record})
    return 0


def cmd_assemble(args: argparse.Namespace) -> int:
    dependencies.require()
    run_dir = Path(args.run_dir) if args.run_dir else None
    pieces_dir = Path(args.pieces) if args.pieces else (run_dir / "pieces" if run_dir else None)
    if pieces_dir is None:
        raise CliError("AF-LAUNCH-ASSEMBLE-ARGS", "give --run-dir (the dispatch run folder) or --pieces")
    source_root = run_dir or pieces_dir.parent
    normalized = intake.validate(_read_json(args.intake))
    launch = _json_object(source_root / "launch.json")
    if launch:  # the dispatch record: its plan hash and approval ref are what the receipt binds
        normalized["approval"] = _bind(normalized, _plan_hash(launch), launch.get("plan_approval_ref", ""))
    elif not normalized.get("test_only", True):
        raise CliError("AF-LAUNCH-APPROVAL-UNBOUND",
                            f"no dispatch record (launch.json) in {source_root}, so the approval cannot be "
                            "tied to a plan. Pass --run-dir of the dispatch run.")
    advice = council.planning_step(normalized)
    graph = route.compile_route(normalized, advice)
    pieces = {role: _read_json(pieces_dir / f"{role}.json")
              for role in (n["role"] for n in graph["nodes"])}
    for slot in package.EXTRA_SLOTS:  # a second page of a role (downsell_2) rides beside its parent
        extra = pieces_dir / f"{slot}.json"
        if extra.is_file():
            pieces[slot] = _read_json(extra)
    plan = _read_json(args.launch_plan) if args.launch_plan else None
    deliveries = _read_json(args.deliveries) if args.deliveries else None
    scope = package.DELIVERY_SCOPE_PAGE_ONLY if args.page_only else package.DELIVERY_SCOPE_FULL
    try:
        out = package.assemble(Path(args.out), normalized, graph, pieces,
                               source_root=source_root, council=advice,
                               require_designs=not args.allow_no_designs,
                               design_waiver=_read_json(args.design_waiver) if args.design_waiver else None,
                               design_approvals=(_read_json(args.design_approvals)
                                                 if args.design_approvals else None),
                               launch_plan=plan, deliveries=deliveries,
                               delivery_scope=scope,
                               checkout_readback=(_read_json(args.checkout_readback)
                                                  if args.checkout_readback else None),
                               activation_readback=(_read_json(args.activation_readback)
                                                    if args.activation_readback else None))
    except package.PackageError as exc:
        _launch_event(normalized["launch_id"], {"event_type": "stage_blocked", "stage": "assemble",
                                                "failures": [exc.code]})
        raise
    _launch_event(normalized["launch_id"], {"event_type": "stage_closed", "stage": "assemble"})
    _emit({"manifest": out["manifest_path"], "receipt": out["receipt_path"],
           "council": advice["status"], "designs_required": not args.allow_no_designs,
           "to_confirm": out["manifest"]["to_confirm"],
           "delivery_scope": out["manifest"]["delivery_scope"],
           "delivery_label": out["manifest"]["delivery_label"],
           "activation": out["manifest"]["activation"],
           "activation_label": out["manifest"]["activation_label"],
           "launch_plan_completeness":
               (out["manifest"].get("launch_plan") or {}).get("completeness")})
    return 0


_BILLING = {"one_time": "one payment", "recurring": "recurring payments",
            "installment": "a payment plan", "payment_plan": "a payment plan"}


def render_plan(normalized: dict, launch: dict) -> str:
    """The launch in plain words: every page, offer, price, billing term and route, then the hash to approve."""
    li = launch_bridge.substrate.load("49-signature-funnel/scripts/launch_intake.py",
                                      "launcher_launch_intake",
                                      sibling_dir="49-signature-funnel/scripts")
    real = _plan_hash(launch)
    *summary, question = li.render_summary({"plan": launch}).splitlines()
    lines = [*summary, "", "Offers, prices and billing:"]
    for offer in launch["offers"]:
        price = offer["prices"][0]
        term = _BILLING.get(price.get("billing_type"), str(price.get("billing_type")))
        lines.append(f"  - {offer['slot']}: {offer['display_name']}, "
                     f"{li._money_display(price['amount_minor'], price['currency'])}, {term}")
    graph = route.compile_route(normalized)
    prefix = launch_bridge.STRUCTURE_PREFIX
    structure = dict(r[len(prefix):].split("=", 1) for r in launch["source_refs"] if r.startswith(prefix))
    lines += ["", "Route (pages in order): " + " -> ".join(n["role"] for n in graph["nodes"]),
              "Landing pages: " + (structure.get("landing_pages", "").replace(",", " and ") or "none")
              + ". The hash covers this choice: dispatch must be given the same --landing-pages"
              + (f" and --extra-page ({structure['extra_pages']})" if structure.get("extra_pages") else "")
              + " as `plan`.", "",
              f"plan_document_hash: {real}",
              f"To approve this exact plan, quote the hash (its first 8 characters are {real[:8]}). "
              "An approval for any other hash is refused. Change anything above and the hash changes.",
              "", question]
    return "\n".join(lines)


def cmd_plan(args: argparse.Namespace) -> int:
    """`--intake`: show the client the plan and the hash to approve. `--plan`: validate a shared launch plan."""
    if bool(args.intake) == bool(args.plan):
        raise CliError("AF-LAUNCH-PLAN-ARGS", "give exactly one of --intake (show the plan to approve) "
                            "or --plan (validate a shared launch plan)")
    if args.intake:
        normalized = intake.validate(_read_json(args.intake))
        test_only = bool(normalized.get("test_only", True))
        try:
            inputs, _ = image_plan.resolve(normalized.get("image_plan"), test_only=test_only)
        except image_plan.ImagePlanError:
            # the picture details (brand file, cap) do not change the plan; only the provider is in the hash
            raw = (normalized.get("image_plan") or {}).get("image_provider")
            inputs = {"image_provider": raw if raw in image_plan.KNOWN_PROVIDERS else image_plan.DEFAULT_PROVIDER}
        print(render_plan(normalized, _launch_for(normalized, inputs, **_page_choices(args))))
        return 0
    plan = _read_json(args.plan)
    deliveries = _read_json(args.deliveries) if args.deliveries else None
    record = launch_plan.record(plan, deliveries)
    launch_plan.assert_complete(record["completeness"])
    _emit(record)
    return 0


def _launcher_intake():
    """shared-utils/client_intake/launcher_intake.py: the repo checkout, then any installed tree."""
    if "launcher_intake" in sys.modules:
        return sys.modules["launcher_intake"]
    home = Path.home()
    roots = [Path(__file__).resolve().parents[2]] + [
        home / ".openclaw" / "skills", home / ".claude" / "skills",
        home / ".claude-nine" / "skills", Path("/data/.openclaw/skills")]
    for root in roots:
        for d in (root / "shared-utils" / "client_intake", root / "client_intake"):
            path = d / "launcher_intake.py"
            if path.is_file():
                spec = importlib.util.spec_from_file_location("launcher_intake", path)
                module = importlib.util.module_from_spec(spec)
                sys.modules["launcher_intake"] = module
                spec.loader.exec_module(module)
                return module
    return None


def cmd_dispatch(args: argparse.Namespace) -> int:
    if args.answers:  # PRD-16: the intake must be the one built from this answers file
        li = _launcher_intake()
        if li is None:
            print("FAIL shared-utils/client_intake/launcher_intake.py not found; an intake cannot be "
                  "checked against its answers file", file=sys.stderr)
            return 2
        prov_path = Path(args.provenance) if args.provenance else Path(args.intake).with_name(li.PROVENANCE_NAME)
        prov = _read_json(prov_path) if prov_path.is_file() else None
        try:
            li.verify(_read_json(args.intake), prov, _read_json(args.answers), Path(args.answers))
        except li.AnswersError as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
    dependencies.require()
    payload = _read_json(args.intake)
    approval = _read_json(args.approval)
    launch_id = str(payload.get("launch_id") or "") if isinstance(payload, dict) else ""
    normalized, launch = _resolved_launch(payload, **_page_choices(args))
    real = _plan_hash(launch)
    record = approval if isinstance(approval, dict) else {}
    if record.get("plan_hash") != real:
        raise CliError("AF-LAUNCH-APPROVAL-HASH",
                            f"the approval record binds plan {str(record.get('plan_hash'))[:8]}, but "
                            f"this intake builds plan {real[:8]}. Nothing was built and nothing was spent; "
                            "run `plan` and get the client's approval of that plan.")
    payload = {**payload, "approval": _bind(normalized, real, str(record.get("approval_id") or ""))}
    adapters_config = _read_json(args.adapters) if args.adapters else None
    adapter_inputs = _read_json(args.adapter_inputs) if args.adapter_inputs else None
    _launch_event(launch_id, {"event_type": "run_initialized"})
    try:
        report = launch_bridge.run(
            payload, Path(args.out),
            approval=approval,
            client_identity_ref=args.client, worker_identity_ref=args.worker,
            adapters_config=adapters_config, adapter_inputs=adapter_inputs,
            parallel=args.parallel,
            scoped_approvals=_read_json(args.scoped_approvals) if args.scoped_approvals else None,
            **_page_choices(args))
    except launch_bridge.BridgeError as exc:
        _launch_event(launch_id, {"event_type": "stage_blocked", "stage": "dispatch",
                                  "failures": [exc.code]})
        raise
    _launch_event(launch_id, {"event_type": "stage_closed", "stage": "dispatch"})
    _emit(report)
    print()
    for line in launch_bridge.summary_lines(report):
        print(line)
    return 0


def _client_intake():
    """shared-utils/client_intake/engine.py: the repo checkout, then any installed tree."""
    home = Path.home()
    roots = [Path(__file__).resolve().parents[2]] + [
        home / ".openclaw" / "skills", home / ".claude" / "skills",
        home / ".claude-nine" / "skills", Path("/data/.openclaw/skills")]
    for root in roots:
        for d in (root / "shared-utils" / "client_intake", root / "client_intake"):
            if (d / "engine.py").is_file():
                sys.path.insert(0, str(d))
                import engine  # noqa: E402
                return engine
    return None


def cmd_questions(args: argparse.Namespace) -> int:
    """The guided client interview: the ONE next applicable question from the shared
    question bank (Black Friday mode), never the raw bank and never a batch. The
    seasonal questions (promotion dates, the offer, real limitations, existing vs new
    buyers, delivery and follow-up) and the three picture questions are all part of it,
    selected by the bank's own conditions one at a time."""
    eng = _client_intake()
    if eng is None:
        print("FAIL shared-utils/client_intake not found; the interview runs on the shared "
              "guided intake, never a local question list", file=sys.stderr)
        return 2
    answers_path = Path(args.answers) if args.answers else None
    doc = eng.load(str(answers_path), "bf") if answers_path else eng.new_doc("bf")
    doc.setdefault("meta", {})["mode"] = "bf"
    q = eng.next_question(doc)
    if answers_path:
        eng.save(doc, str(answers_path))
    if q is None:
        _emit({"done": True, "check": eng.check(doc)})
    else:
        _emit({"question": q, "progress": q.get("progress"), "estimate": q.get("estimate"),
               "assistance_mode": q.get("assistance_mode"),
               "source": "shared-utils/client_intake/question-bank.json"})
    return 0


def _approval_fails(manifest: dict, root: Path) -> List[str]:
    """The manifest's approved hash and ref against the dispatch record in the run folder."""
    launch = _json_object(root / "launch.json")
    if not launch:
        if manifest.get("test_only", True):
            return []  # a test package carries no consent claim
        return ["AF-LAUNCH-APPROVAL-UNBOUND: no dispatch record (launch.json) in the run folder, so the "
                "approved plan hash cannot be tied to a plan"]
    real, fails = _plan_hash(launch), []
    if manifest.get("approved_plan_hash") != real:
        fails.append(f"AF-LAUNCH-APPROVAL-BINDING: the package says it was approved for plan "
                     f"{str(manifest.get('approved_plan_hash'))[:8]}, but the plan that was dispatched "
                     f"hashes to {real[:8]}")
    ref = (_json_object(root / "receipt.json").get("approvals") or {}).get("launch_plan_build")
    if ref is not None and ref != launch.get("plan_approval_ref"):
        fails.append(f"AF-LAUNCH-APPROVAL-BINDING: the receipt records approval {ref!r}, but the dispatch "
                     f"record carries {launch.get('plan_approval_ref')!r}")
    return fails


def cmd_check(args: argparse.Namespace) -> int:
    fails = checks.check_package(Path(args.manifest), Path(args.root),
                                 require_designs=True if args.require_designs else None)
    manifest = _json_object(Path(args.manifest))
    fails = list(fails) + _approval_fails(manifest, Path(args.root))
    launch_id = str(manifest.get("launch_id") or "")
    if launch_id:
        _launch_event(launch_id, {"event_type": "stage_blocked", "stage": "check",
                                  "failures": [str(f) for f in fails][:20]} if fails
                      else {"event_type": "stage_closed", "stage": "check"})
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
    root = Path(args.root) if args.root else None
    try:
        # --install is the sanctioned fix: a missing runtime package goes into the shared pydeps folder
        report = dependencies.ensure_runtime_packages(root) if args.install else dependencies.check(root)
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
    # The metadata spines (registration.json, skill.json) are pointers, not a second
    # requirement list. A disagreement is printed as a finding and never changes the
    # exit code: those two files record nothing that runs.
    meta = report.get("metadata") or {}
    findings = meta.get("findings") or []
    print(f"\nmetadata spine: {meta.get('authoritative_manifest')} "
          f"digest={str(meta.get('requirements_digest'))[:12]} "
          f"entries={meta.get('entry_count')} required={meta.get('required_entry_count')}; "
          f"{len(findings)} finding(s)")
    for finding in findings:
        print(f"  METADATA   {finding}")
    return 2 if args.install and report["blockers"] else 0


_LANDING_HELP = ("the landing pages the client wants: landing, sales or landing,sales (default: the set "
                 "Skill 49 recommends, flagged 'to confirm'). The plan hash covers this choice, so give "
                 "`plan` and `dispatch` the same value")
_EXTRA_HELP = ("an extra design page the client opted into (downsell_2); repeat for more. The plan hash "
               "covers it, so give `plan` and `dispatch` the same value")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="launcher_core.cli")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("route", help="validate intake and compile the route graph")
    r.add_argument("--intake", required=True)
    r.set_defaults(fn=cmd_route)

    a = sub.add_parser("assemble", help="assemble package-manifest.json and receipt.json")
    a.add_argument("--intake", required=True)
    a.add_argument("--run-dir", help="the dispatch run folder (its --out): holds pieces/, launch.json and "
                                     "dispatch-report.json. The approval is tied to launch.json, and --pieces "
                                     "defaults to <run-dir>/pieces")
    a.add_argument("--pieces", help="directory of <role>.json page results (default: <run-dir>/pieces)")
    a.add_argument("--out", required=True)
    a.add_argument("--allow-no-designs", action="store_true",
                   help="assemble without every page's wireframes and mockups; needs --design-waiver "
                        "(an owner approval bound to this plan hash) and is never accepted for a client "
                        "delivery (test_only false)")
    a.add_argument("--design-waiver",
                   help="the owner's design_waiver approval record (JSON: approval_ref, subject_type "
                        "'design_waiver', subject_hash = the plan hash, owner_identity_ref, revoked)")
    a.add_argument("--design-approvals",
                   help='JSON {"design_board": {state, approval_ref, record_sha256}, "final_mockups": {...}}; '
                        "an approved entry must resolve to a recorded Skill 71 Design Board approval "
                        "(page_designs.approval_violations)")
    a.add_argument("--launch-plan",
                   help="the shared launch plan (U-CONTRACT); its Black Friday calendar and every "
                        "planned email, text, automation and requested AI must be delivered. "
                        "Required unless --page-only")
    a.add_argument("--deliveries",
                   help="JSON object of unit id -> delivery result ({'state': 'complete'})")
    a.add_argument("--checkout-readback",
                   help="the Skill 06 install read-back record (JSON): the native capability evidence, "
                        "fulfillment mapping and failed/pending copy the order form needs. Without it the "
                        "order-form mapping lists those facts as unknown and check refuses it")
    a.add_argument("--activation-readback",
                   help="the OBSERVED record of an installation or publication (JSON: stage "
                        "'installed' or 'published', the read route as source, page_id, https "
                        "page_url, observed_at and — for published — page_type and page_version; "
                        "for installed — the native install facts). A save click or a local "
                        "'published' field is refused")
    a.add_argument("--page-only", action="store_true",
                   help="assemble pages alone and label the package page-only: no shared launch "
                        "plan, so no Black Friday calendar and no planned email, text or automation "
                        "is delivered or checked. Never the default")
    a.set_defaults(fn=cmd_assemble)

    pl = sub.add_parser("plan", help="show the client the launch in plain words with the plan hash to approve "
                                     "(--intake), or validate a shared launch plan's calendar (--plan)")
    pl.add_argument("--intake", help="the intake: prints every page, offer, price, billing term and route, "
                                     "then the plan_document_hash an approval must bind")
    pl.add_argument("--plan", help="a shared launch plan to validate")
    pl.add_argument("--landing-pages", help=_LANDING_HELP)
    pl.add_argument("--extra-page", action="append", choices=["downsell_2"], help=_EXTRA_HELP)
    pl.add_argument("--deliveries",
                    help="JSON object of unit id -> delivery result; omit to see what is missing")
    pl.set_defaults(fn=cmd_plan)

    x = sub.add_parser("dispatch", help="turn the intake into a Skill 49 launch record and build every page")
    x.add_argument("--intake", required=True)
    x.add_argument("--out", required=True, help="run folder: launch.json, dispatch/, pieces/, dispatch-report.json")
    x.add_argument("--approval", required=True, help="the client's recorded plan approval (JSON record)")
    x.add_argument("--answers", help="the client answers file (client-intake-answers/v1) this intake was built "
                                     "from; dispatch refuses unless the intake is bound to it by hash")
    x.add_argument("--provenance", help="the intake provenance file (default: intake.provenance.json "
                                        "beside --intake)")
    x.add_argument("--client", required=True, help="the client's identity reference")
    x.add_argument("--worker", required=True, help="the identity running the build (never the approver)")
    x.add_argument("--adapters", help="ready Skill 49 adapter configuration (JSON)")
    x.add_argument("--adapter-inputs", help="per-page inputs to build the adapter configuration (JSON)")
    x.add_argument("--parallel", type=int, default=None,
                   help="build the independent pages as this many parallel lanes (1 = one at a time; "
                        "default: this computer's worker count)")
    x.add_argument("--scoped-approvals", help="JSON array of extra scoped approvals")
    x.add_argument("--landing-pages", help=_LANDING_HELP)
    x.add_argument("--extra-page", action="append", choices=["downsell_2"], help=_EXTRA_HELP)
    x.set_defaults(fn=cmd_dispatch)

    q = sub.add_parser("questions", help="the guided interview's ONE next question (Black Friday "
                                         "seasonal questions and picture questions alike), as data")
    q.add_argument("--answers", help="the shared answers file (client-intake-answers/v1); "
                                     "the run is created on first use and resumed after that")
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
    d.add_argument("--install", action="store_true",
                   help="first install any missing runtime package (jsonschema) into the shared pydeps "
                        "folder <root>/pydeps/py<X.Y>/ with pip --target, never --break-system-packages "
                        "and never a venv; exit 2 if one is still missing")
    d.set_defaults(fn=cmd_dependencies)
    return p


# These commands read data only and never import the runtime packages, so they must not start an install.
_NO_RUNTIME_PACKAGES = ("seams", "dependencies", "questions")


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command not in _NO_RUNTIME_PACKAGES:
            dependencies.ensure_runtime_packages()  # a missing package is fixed here, never asked of the client
        return args.fn(args)
    except (intake.IntakeError, route.RouteError, package.PackageError,
            launch_bridge.BridgeError, image_plan.ImagePlanError,
            launch_plan.LaunchPlanError, CliError,
            dependencies.DependencyError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
