"""Bridge from the Launcher's intake to Skill 49's dispatch: one command, every page.

Skill 49 dispatches page requests from an APPROVED launch record. The Launcher holds an intake. This
module turns the second into the first, proves the result against Skill 49's own validator, then calls
Skill 49's dispatch and lays one result file per page where ``assemble`` already reads them.

Nothing here invents a commercial fact: every offer, price and level in the launch record is copied
from the validated intake, and the approval is a RECORD supplied by the caller, never synthesized (a
worker cannot approve its own plan; Skill 49's gate enforces that, this module only carries the
record to it).

Parallel build: the image-heavy pages are independent of each other once the landing page has fixed
the visual direction, so Skill 49's dispatch is asked to run them as parallel lanes when it supports
that (``parallel`` argument). The lane plan is computed and reported either way, so a client sees what
will run first and what runs together; if the dispatcher has no parallel mode yet, the report says
"serial" rather than pretending.
"""

from __future__ import annotations

import inspect
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import sys

_ROUTES_DIR = Path(__file__).resolve().parent.parent / "routes"
if str(_ROUTES_DIR) not in sys.path:
    sys.path.insert(0, str(_ROUTES_DIR))

import substrate  # noqa: E402

from . import image_plan, intake as intake_module, page_designs, route  # noqa: E402

LAUNCH_SCHEMA_VERSION = "1.2"
FIRST_ROLE = "landing"  # first when pages are built one at a time (side by side, Skill 49 starts every page together)


class BridgeError(Exception):
    """A dispatch that cannot start. Carries a stable code and a plain-English detail."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _offer(normalized: Dict[str, Any], offer: Dict[str, Any], by_role: Dict[str, str]) -> Dict[str, Any]:
    test_only = bool(normalized.get("test_only", True))
    excludes: List[str] = []
    if offer["role"] == "upsell_1" and "downsell_1" in by_role:
        excludes = [by_role["downsell_1"]]
    if offer["role"] == "downsell_1" and "upsell_1" in by_role:
        excludes = [by_role["upsell_1"]]
    level = offer.get("level") or {}
    return {
        "offer_id": offer["offer_id"],
        "slot": offer["role"],
        "display_name": offer["name"],
        "deliverables": list(level.get("deliverables") or []),
        "exclusions": [],
        "entitlement_ids": [offer["offer_id"].lower()],
        "requires": [],
        "excludes": excludes,
        "native_product_id": None,
        "prices": [{
            "price_choice_id": f"{offer['offer_id']}-{offer['price']['currency']}",
            "currency": offer["price"]["currency"],
            "amount_minor": offer["price"]["amount_minor"],
            "billing_type": "one_time",
            "native_price_id": None,
            "schedule": [],
            "approval_status": "approved",
        }],
        "source_kind": "test_fixture" if test_only else "owner",
        "source_ref": f"launcher-intake:{normalized['launch_id']}:r{normalized['revision']}",
        "test_only": test_only,
    }


def to_launch_record(normalized: Dict[str, Any], graph: Dict[str, Any],
                     inputs: Dict[str, Any]) -> Dict[str, Any]:
    """The Skill 49 launch record for a validated intake. Schema-valid; proven by check_launch_record."""
    roles = {o["role"] for o in normalized["offers"]}
    by_role: Dict[str, str] = {o["role"]: o["offer_id"] for o in normalized["offers"]
                               if o["role"] in ("upsell_1", "downsell_1")}
    compiler = substrate.compiler()
    offers = [_offer(normalized, o, by_role) for o in normalized["offers"]]
    launch_id, revision = normalized["launch_id"], normalized["revision"]
    return {
        "schema_version": LAUNCH_SCHEMA_VERSION,
        "tenant_id": normalized["tenant_id"],
        "location_id": normalized["location_id"],
        "launch_id": launch_id,
        "revision": revision,
        "journey_mode": normalized["journey_mode"],
        "status": "approved",
        "brand_ref": normalized["brand"]["ref"],
        "brand_hash": normalized["brand"]["hash"],
        "route_graph_ref": f"route-graph:{launch_id}:rev{revision}",
        "route_graph_hash": compiler.graph_hash(graph),
        "plan_approval_ref": normalized["approval"]["ref"],
        "offers": offers,
        "extras": {
            "upsell_1": "upsell_1" in roles,
            "downsell_1": "downsell_1" in roles,
            "upsell_2": "upsell_2" in roles,
        },
        "bump_enabled": "bump" in roles,
        "image_provider": inputs["image_provider"],
        "source_refs": [f"launcher-intake:{launch_id}:r{revision}"],
        "test_only": bool(normalized.get("test_only", True)),
    }


def check_launch_record(launch: Dict[str, Any]) -> List[str]:
    """Skill 49's own validator's verdict on the record. Empty list means schema- and domain-valid."""
    return list(substrate.dispatch().vlp.validate_launch(launch))


def lane_plan(graph: Dict[str, Any], workers: Optional[int] = None,
              extra_pages: Sequence[str] = (), side_by_side: bool = False) -> Dict[str, Any]:
    """What runs first and what runs together, in the order a client would be told.

    extra_pages are the design pages the client opted into (downsell_2): they ride beside their parent.
    side_by_side is what Skill 49 really does when it is given workers: every page starts together, the
    landing page too, because the shared look travels in the image inputs file, so no page waits."""
    roles = [n["role"] for n in graph["nodes"]] + list(extra_pages)
    first = [] if side_by_side else [r for r in roles if r == FIRST_ROLE]
    rest = [r for r in roles if r not in first]
    return {
        "phase_1_alone": first,
        "phase_1_reason": ("every page shares one look through the image inputs file, so no page waits for another"
                           if side_by_side else
                           "the landing page fixes the visual direction every other page follows"),
        "phase_2_together": rest,
        "workers": workers,
        "independent_pages": len(rest),
    }


def _accepts(dispatch_fn, name: str) -> bool:
    return name in inspect.signature(dispatch_fn).parameters


def _dispatch_image_inputs(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """What Skill 49's dispatch takes as ``image_inputs`` (what its page_set.load_image_inputs returns)."""
    out = image_plan.image_inputs_file(inputs)  # "kie" on a paid run, "stub" on a free one
    out["allow_paid"] = inputs["allow_paid"]
    return out


def to_confirm_lines(to_confirm: List[Dict[str, Any]]) -> List[str]:
    """One plain sentence per flagged default, with the one-line way to change it."""
    return [f"{item['field']}: {item['reason']} To change it: {item['how_to_change']}" for item in to_confirm]


def _plan_landing_pages(dl, launch: Dict[str, Any], chosen: Optional[Sequence[str]],
                        extra_pages: Sequence[str]):
    """(the landing pages to build, the "to confirm" entries). Skill 49's own page set decides what is valid."""
    pset = dl.pset
    to_confirm: List[Dict[str, Any]] = []
    planned = list(chosen) if chosen else pset.recommended_landing_pages(launch)
    try:
        page_set = pset.build_page_set(launch, landing_pages=planned, extra_pages=extra_pages)
    except (pset.PageSetError, dl.clr.RouteError) as exc:
        raise BridgeError("AF-LAUNCH-BRIDGE-PAGES", f"{exc}. Nothing was dispatched and nothing was spent.") from exc
    if not chosen:
        labels = " and ".join(p["label"] for p in page_set["pages"] if p["role"] == FIRST_ROLE)
        to_confirm.append({
            "field": "landing_pages",
            "reason": f"You did not say which landing pages you want, so I planned the {labels}.",
            "how_to_change": "Tell me 'landing page only', 'sales page only' or 'both' and I will rebuild them.",
        })
    return planned, to_confirm


def split_landing(result: Dict[str, Any], landing_pages: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """The one landing result as one piece per planned landing page: {slot: piece}.

    Skill 71 files are labeled for their own page (sales-page_..., landing_...), so the design files are
    split by that label; every other artifact stays with the main page. A planned page that came back
    with no file of its own is refused by name: a funnel is never delivered one page short."""
    both = set(landing_pages) == {"landing", "sales"}
    sales_prefix = page_designs.label_slug({"role": FIRST_ROLE, "page_kind": "sales"}) + "_"
    arts = result.get("artifacts") or []
    is_sales = [bool(page_designs.classify(str(a.get("path")), a.get("kind")))
                and Path(str(a.get("path"))).name.lower().startswith(sales_prefix) for a in arts]
    main_kind = "sales" if list(landing_pages) == ["sales"] else "opt_in"
    main = {**result, "page_kind": main_kind,
            "artifacts": [a for a, s in zip(arts, is_sales) if not (both and s)]}
    if not both:
        return {FIRST_ROLE: main}
    sales_arts = [a for a, s in zip(arts, is_sales) if s]
    if not sales_arts:
        raise BridgeError("AF-LAUNCH-BRIDGE-LANDING-SPLIT",
                          "the signature sales page was planned, but the landing build returned no file "
                          f"labeled for it (a sales page file starts with {sales_prefix!r}). Nothing was "
                          "delivered for that page, so the package would be one page short.")
    return {FIRST_ROLE: main, "sales": {**result, "page_kind": "sales", "role_instance": "sales",
                                        "artifacts": sales_arts}}


def run(payload: Dict[str, Any], out_dir: Path, *, approval: Dict[str, Any],
        client_identity_ref: str, worker_identity_ref: str,
        adapters_config: Optional[Dict[str, Any]] = None,
        adapter_inputs: Optional[Dict[str, Any]] = None,
        parallel: Optional[int] = None,
        scoped_approvals: Optional[List[Dict[str, Any]]] = None,
        extra_pages: Sequence[str] = (),
        landing_pages: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Validate, bridge, dispatch, and write one result per page. Returns the dispatch report.

    landing_pages is the client's landing page choice ("landing", "sales" or both). Without it the set
    Skill 49 recommends is used and flagged "to confirm". Either way Skill 49's page set is the
    plan: one piece is written for every page in it (the sales page too), never fewer.

    Fail-closed and plain-spoken: every refusal raises BridgeError (or the Launcher's own IntakeError /
    ImagePlanError) whose detail says what is needed and what has NOT been done (nothing spent, nothing sent).
    """
    out_dir = Path(out_dir)
    normalized = intake_module.validate(payload)
    inputs, to_confirm = image_plan.resolve(normalized.get("image_plan"),
                                            test_only=bool(normalized.get("test_only", True)))
    graph = route.compile_route(normalized)
    launch = to_launch_record(normalized, graph, inputs)
    fails = check_launch_record(launch)
    if fails:
        raise BridgeError("AF-LAUNCH-BRIDGE-RECORD",
                          "Skill 49 would not accept this launch plan: " + "; ".join(fails)
                          + ". Nothing was dispatched and nothing was spent.")

    out_dir.mkdir(parents=True, exist_ok=True)
    dispatch_dir = out_dir / "dispatch"
    pieces_dir = out_dir / "pieces"
    inputs_path = out_dir / "image_inputs.json"
    order_inputs_path = out_dir / "order-page-inputs.json"
    launch_path = out_dir / "launch.json"
    launch_path.write_text(json.dumps(launch, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    inputs_path.write_text(json.dumps(image_plan.image_inputs_file(inputs), indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    order_inputs_path.write_text(json.dumps(image_plan.order_page_inputs_file(
        inputs, route_graph=str(dispatch_dir / "route-graph.json")), indent=2, sort_keys=True) + "\n",
        encoding="utf-8")

    dl = substrate.dispatch()
    planned, landing_to_confirm = _plan_landing_pages(dl, launch, landing_pages, extra_pages)
    dispatch_dir.mkdir(parents=True, exist_ok=True)  # the adapter builder needs the folder to exist
    if adapters_config is None:
        if adapter_inputs is None:
            raise BridgeError("AF-LAUNCH-BRIDGE-ADAPTERS",
                              "I have no way to build the pages yet: give me either a ready adapter "
                              "configuration or the per-page inputs (copy, journey and enrichment for the "
                              "upsell and downsell pages). Nothing was dispatched.")
        adapters_config = _build_adapters(adapter_inputs, out_dir, launch_path, inputs, inputs_path,
                                          order_inputs_path)

    kwargs: Dict[str, Any] = {}
    parallel_state = "serial"
    if parallel is None and _accepts(dl.dispatch, "parallel"):
        parallel = dl.swarm.default_workers()  # no flag: the runner profile's workers, as Skill 49's own "auto"
    if parallel is not None and parallel != 1:
        if _accepts(dl.dispatch, "parallel"):
            kwargs["parallel"] = parallel
            parallel_state = f"parallel x{parallel}"
        else:
            parallel_state = "serial (Skill 49's dispatch has no parallel mode in this checkout)"
    # Spend ledger and KIE rate limiter: Skill 49 only creates them when it is handed the image inputs
    # (and, for a paid run, the limiter), exactly as its own command line does.
    if _accepts(dl.dispatch, "image_inputs"):
        kwargs["image_inputs"] = _dispatch_image_inputs(inputs)
    if _accepts(dl.dispatch, "limiter") and inputs["executor_provider"] == "kie":
        kwargs["limiter"] = dl.swarm.kie_limiter()
    if extra_pages:  # an opted-in design page (downsell_2) is never silently dropped
        if not _accepts(dl.dispatch, "extra_pages"):
            raise BridgeError("AF-LAUNCH-BRIDGE-EXTRA-PAGES",
                              f"Skill 49's dispatch cannot build {', '.join(extra_pages)} in this checkout. "
                              "Nothing was dispatched and nothing was spent.")
        kwargs["extra_pages"] = tuple(extra_pages)
    try:
        manifest = dl.dispatch(
            launch, approval,
            client_identity_ref=client_identity_ref, worker_identity_ref=worker_identity_ref,
            copy_profile=normalized["copy_profile"],
            allowed_write_target=normalized["allowed_write_target"],
            scoped_approvals=scoped_approvals or [],
            out_dir=dispatch_dir,
            landing_pages=planned,
            executor=dl.executor_from_config(adapters_config, dispatch_dir, landing_pages=planned),
            **kwargs)
    except (dl.DispatchError, dl.vlp.ApprovalError, dl.clr.RouteError) as exc:
        raise BridgeError("AF-LAUNCH-BRIDGE-DISPATCH",
                          f"Skill 49 stopped the dispatch: {exc}. Check what was already built in "
                          f"{dispatch_dir}; nothing was published.") from exc

    pieces_dir.mkdir(parents=True, exist_ok=True)
    written: List[str] = []
    for result in manifest["results"]:
        role = next(r["page_role"] for r in manifest["requests"] if r["request_id"] == result["request_id"])
        if role == FIRST_ROLE:  # one landing result carries every landing page Skill 49 planned
            for slot, piece in split_landing(result, planned).items():
                (pieces_dir / f"{slot}.json").write_text(json.dumps(piece, indent=2) + "\n", encoding="utf-8")
                written.append(slot)
            continue
        shutil.copyfile(dispatch_dir / f"result-{role}.json", pieces_dir / f"{role}.json")
        written.append(role)
    for lane in manifest.get("page_results", {}):  # an extra page rides on its parent's request
        shutil.copyfile(dispatch_dir / f"page-result-{lane}.json", pieces_dir / f"{lane}.json")
        written.append(lane)

    report = {
        "launch_id": normalized["launch_id"],
        "execution": manifest["execution"],
        "pages": written,
        "page_labels": [p["label"] for p in manifest["page_set"]["pages"]],
        "landing_pages": planned,
        "lane_plan": lane_plan(graph, parallel, extra_pages, side_by_side=parallel_state.startswith("parallel")),
        "parallel": parallel_state,
        "pieces_dir": str(pieces_dir),
        "launch_record": str(launch_path),
        "image_inputs": str(inputs_path),
        "image_provider": inputs["image_provider"],
        "executor_provider": inputs["executor_provider"],
        "paid_calls_allowed": inputs["allow_paid"],
        "to_confirm": to_confirm + landing_to_confirm,
    }
    (out_dir / "dispatch-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                                                  encoding="utf-8")
    return report


def summary_lines(report: Dict[str, Any]) -> List[str]:
    """What the client is told after a dispatch, in plain English."""
    plan = report["lane_plan"]
    lines = [f"Built {len(report['pages'])} pages: {', '.join(report.get('page_labels') or report['pages'])}."]
    if plan["phase_1_alone"]:
        lines.append(f"First, {', '.join(plan['phase_1_alone'])} on its own, because it fixes the look "
                     f"every other page follows. Then the other {plan['independent_pages']} pages, which do "
                     f"not depend on each other. Run mode: {report['parallel']}.")
    else:
        lines.append(f"All {plan['independent_pages']} page lanes are built side by side: they share one look, "
                     f"so none waits for another. Run mode: {report['parallel']}.")
    if report["paid_calls_allowed"]:
        lines.append("Pictures: real rendering, within the ceiling you approved.")
    else:
        lines.append("Pictures: practice placeholders only. Nothing was spent.")
    if report["to_confirm"]:
        lines.append(f"{len(report['to_confirm'])} choice(s) are waiting for your confirmation:")
        lines += [f"  - {line}" for line in to_confirm_lines(report["to_confirm"])]
    else:
        lines.append("Every choice came from you. Nothing is waiting for confirmation.")
    return lines


def _build_adapters(adapter_inputs: Dict[str, Any], out_dir: Path, launch_path: Path,
                    inputs: Dict[str, Any], inputs_path: Path, order_inputs_path: Path) -> Dict[str, Any]:
    import adapters  # routes/adapters.py (on sys.path through substrate)
    try:
        return _bind_adapters(adapters, adapter_inputs, out_dir, launch_path, inputs, inputs_path,
                              order_inputs_path)
    except adapters.AdapterError as exc:
        raise BridgeError("AF-LAUNCH-BRIDGE-ADAPTERS", f"{exc}. Nothing was dispatched.") from exc
    except KeyError as exc:
        raise BridgeError("AF-LAUNCH-BRIDGE-ADAPTERS",
                          f"the per-page inputs are missing {exc}. Nothing was dispatched.") from exc


def _bind_adapters(adapters, adapter_inputs: Dict[str, Any], out_dir: Path, launch_path: Path,
                   inputs: Dict[str, Any], inputs_path: Path, order_inputs_path: Path) -> Dict[str, Any]:
    if not adapter_inputs.get("checkout_manuscript"):
        raise BridgeError("AF-LAUNCH-BRIDGE-ADAPTERS",
                          "the order form page gets its wireframes and mockups like every other page, and "
                          "they are drawn from its copy: give me checkout_manuscript (the path to the order "
                          "form page's copy). Nothing was dispatched.")
    checkout_design = {"manuscript": adapter_inputs["checkout_manuscript"],
                       "brand_file": inputs["brand_file"], "brand_owner": inputs["brand_owner"],
                       "image_cap": inputs["image_cap"], "design_style": inputs["design_style"]}
    return adapters.build_dispatch_config(
        work_dir=out_dir / "dispatch", launch_record=launch_path,
        bridge_config=adapter_inputs["bridge_config"],
        author_session=adapter_inputs["author_session"],
        copy=adapter_inputs["copy"], journey=adapter_inputs["journey"],
        enrichment=adapter_inputs["enrichment"], image_inputs=inputs_path,
        order_page_inputs=order_inputs_path,
        skill80_root=adapter_inputs.get("skill80_root"), skill81_root=adapter_inputs.get("skill81_root"),
        image_provider=inputs["executor_provider"], allow_paid=inputs["allow_paid"],
        checkout_design=checkout_design, image_plan=inputs)
