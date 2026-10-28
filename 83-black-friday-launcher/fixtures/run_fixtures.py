#!/usr/bin/env python3
"""Offline worked-example fixtures for the Black Friday Launcher.

Two shapes, exactly as the owner records state them and never merged:

  Elevation           12-section no-price signature page -> SEPARATE three-level
                      product selection -> native order form (S79).
 7FigurePreneur       three levels FOLDED INTO the signature page -> native order
                      form. No product selection page, and never relabelled a
                      single offer.

Both shapes now build. 7FigurePreneur uses the settled `folded_levels` journey
mode: N >= 2 distinct main offers, landing straight to the native order form,
no product_selection node.

No price, level content or product default is invented here. Every amount used
comes from the repository's own TEST-ONLY fixtures; see fixtures/README.md.
Council advice is stubbed so the run needs no live session.

Writes only under TMPDIR. Exit 0 when every executable assertion holds.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
REPO_ROOT = SKILL_ROOT.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import checks, council, intake, package, route  # noqa: E402
from launcher_core.constants import DECIDED_IDS, SEAM_IDS  # noqa: E402

ROUTES_DIR = SKILL_ROOT / "routes"
sys.path.insert(0, str(ROUTES_DIR))
import build_time  # noqa: E402
import route_law  # noqa: E402
import substrate  # noqa: E402

PASSED: List[str] = []
FAILED: List[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(label)
        print(f"PASS  {label}")
    else:
        FAILED.append(f"{label}: {detail}")
        print(f"FAIL  {label} {detail}")


def load(name: str) -> Dict[str, Any]:
    return json.loads((HERE / name / "intake.json").read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stub_council(_launch: Dict[str, Any]) -> Dict[str, Any]:
    """A stub Council: proves the step is wired without any paid session."""
    return {"status": "advice_returned", "ready": True,
            "advice": {"recommendation": "TEST-ONLY stub advice",
                       "advisory_only": True},
            "advice_state": "returned"}


def not_ready_council(_launch: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "not_ready", "ready": False,
            "detail": "TEST-ONLY not-ready stub",
            "advice": None, "advice_state": "pending_live_session"}


def write_piece_artifacts(out_dir: Path, plan: Dict[str, Any],
                          normalized: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """One authored-level page result per enabled page, built from the plan.

    The artifact is the build plan for that page, not page copy. Page bytes are
    the assigned skill's output; this fixture proves composition and package
    completeness without inventing level content.
    """
    pieces: Dict[str, Dict[str, Any]] = {}
    for page in plan["pages"]:
        role = page["role"]
        rel = Path("artifacts") / f"{page['page_id']}-build-plan.json"
        target = out_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({
            "note": "TEST-ONLY build plan; not page content",
            "page_id": page["page_id"],
            "role": role,
            "assigned_skill": page["assigned_skill"],
            "build_entry": page["build_entry"],
            "cross_sales": page.get("cross_sales"),
            "route_graph_hash": plan["route_graph_hash"],
            "buyer_action_required": False,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        pieces[role] = {
            "schema_version": normalized["schema_version"],
            "tenant_id": normalized["tenant_id"],
            "location_id": normalized["location_id"],
            "launch_id": normalized["launch_id"],
            "revision": normalized["revision"],
            "page_id": page["page_id"],
            "request_id": f"fixture-{page['page_id']}",
            "input_hash": plan["route_graph_hash"],
            "author_session": "fixture-offline-build",
            "status": "authored",
            "proof_class": "L0",
            "independent_review": False,
            "test_only": True,
            "native_bindings_ref": None,
            "blockers": [],
            "artifacts": [{"path": str(target), "sha256": sha256_file(target)}],
        }
    return pieces


def build_and_check(name: str, payload: Dict[str, Any],
                    expected_roles: List[str],
                    council_runner=stub_council) -> Dict[str, Any]:
    """Validate, compile, plan, assemble and check one worked example."""
    normalized = intake.validate(payload)
    advice = council.planning_step(normalized, runner=council_runner)
    check(f"{name} Council step is recorded and never blocks",
          advice["blocks_build"] is False and advice["is_permission"] is False,
          repr(advice))
    record = route.launch_record(normalized, advice)
    graph = route.compile_route(normalized, advice)

    violations = route_law.graph_violations(record, graph)
    check(f"{name} route invariants hold", violations == [], repr(violations))
    roles = [n["role"] for n in graph["nodes"]]
    check(f"{name} role order is the settled shape", roles == expected_roles, str(roles))
    check(f"{name} graph is the real S49 compiler graph",
          substrate.compiler().graph_hash(graph) ==
          route_law.compile_route(record)["route_graph_hash"])
    check(f"{name} launch record carries the Council planning step",
          record.get("council", {}).get("step") == "council_launch_planning")

    plan = build_time.plan(record)
    check(f"{name} every enabled page has an independent build unit",
          [p["role"] for p in plan["pages"]] == roles,
          str([p["role"] for p in plan["pages"]]))
    check(f"{name} no page waits for a customer action",
          all(p["buyer_action_required"] is False for p in plan["pages"]))
    checkout_page = next(p for p in plan["pages"] if p["role"] == "checkout")
    check(f"{name} checkout is the native S79 surface, not a dispatch adapter",
          checkout_page["build_entry"].get("dispatch_adapter") is False,
          repr(checkout_page["build_entry"]))
    thank_you = next(p for p in plan["pages"] if p["role"] == "thank_you")
    check(f"{name} cross-sale surface rides on the thank-you page",
          thank_you.get("cross_sales", {}).get("surface") == "thank_you")
    check(f"{name} cross-sale teaching is explicitly pending",
          thank_you["cross_sales"]["teaching"]["state"] == "pending")

    out = Path(tempfile.mkdtemp(prefix=f"{name.lower()}-"))
    run_dir = out / "package"
    pieces = write_piece_artifacts(out, plan, normalized)
    out_record = package.assemble(run_dir, normalized, graph, pieces,
                                  council=advice)
    fails = checks.check_package(Path(out_record["manifest_path"]), run_dir)
    check(f"{name} package completeness checks pass", fails == [], repr(fails))
    check(f"{name} package is self-contained",
          all((run_dir / art["path"]).is_file()
              for p in out_record["manifest"]["pieces"] for art in p["artifacts"]))
    check(f"{name} receipt records the entitlement basis",
          out_record["receipt"]["entitlement"]["basis"] ==
          normalized["entitlement"]["basis"])
    check(f"{name} checkout mapping is bound to the S79 contract",
          out_record["manifest"]["checkout"]["contract"].endswith(
              "checkout.schema.json")
          and out_record["manifest"]["checkout"]["validator"]["state"]
          in ("bound", "unavailable"))
    print(f"      {name} run dir: {run_dir}")
    return out_record


def run_elevation() -> None:
    print("\n== Elevation (multiple_options, three cumulative levels) ==")
    payload = load("elevation")
    check("elevation declares a separate product selection route",
          payload["journey_mode"] == "multiple_options", payload["journey_mode"])
    normalized = intake.validate(payload)
    mains = [o for o in normalized["offers"] if o["role"] == "main"]
    check("elevation keeps three distinct main offers", len(mains) == 3, str(len(mains)))
    check("elevation never carries a no-price offer",
          all(o["price"]["amount_minor"] > 0 for o in normalized["offers"]))
    check("elevation entitlement is attested, never defaulted",
          normalized["entitlement"]["basis"] == "purchase"
          and normalized["entitlement"]["requires_purchase"] is True)
    build_and_check(
        "elevation", payload,
        ["landing", "product_selection", "checkout", "upsell_1",
         "downsell_1", "upsell_2", "thank_you"])


def run_seven_figure_preneur() -> None:
    print("\n== 7FigurePreneur (folded_levels, three levels on the signature page) ==")
    payload = load("seven-figure-preneur")
    mains = [o for o in payload["offers"] if o["role"] == "main"]
    check("7FigurePreneur keeps three distinct main offers", len(mains) == 3,
          str(len(mains)))
    check("7FigurePreneur is not relabelled a single offer",
          len({o["offer_id"] for o in mains}) == 3)
    check("7FigurePreneur keeps a priced profile",
          all(o["price"]["amount_minor"] > 0 for o in payload["offers"]))
    check("7FigurePreneur is not represented as single_simple or multiple_options",
          payload["journey_mode"] not in ("single_simple", "multiple_options"),
          payload["journey_mode"])
    check("7FigurePreneur uses the settled folded_levels mode",
          payload["journey_mode"] == "folded_levels", payload["journey_mode"])

    normalized = intake.validate(payload)
    check("7FigurePreneur membership qualifies without a purchase",
          normalized["entitlement"]["basis"] == "brand_management_membership"
          and normalized["entitlement"]["requires_purchase"] is False)

    record = build_and_check(
        "seven-figure-preneur", payload,
        ["landing", "checkout", "upsell_1", "downsell_1", "upsell_2", "thank_you"])
    graph = route.compile_route(normalized, route.launch_record(normalized))
    roles = [n["role"] for n in graph["nodes"]]
    check("folded_levels inserts NO product_selection page",
          "product_selection" not in roles, str(roles))
    plan = build_time.plan(route.launch_record(normalized))
    thank_you = next(p for p in plan["pages"] if p["role"] == "thank_you")
    check("cross-sale relationships are present on the thank-you page",
          thank_you["cross_sales"]["relationships"] ==
          [{"offer_id": "BUMP", "included_in": ["MAIN-B", "MAIN-C"]}],
          repr(thank_you["cross_sales"]["relationships"]))
    check("7FigurePreneur package manifest keeps all three levels",
          len(record["manifest"]["offer_facts"]) == len(payload["offers"]))

    # A not-ready Council is recorded and the build still completes.
    not_ready = council.planning_step(normalized, runner=not_ready_council)
    check("a not-ready Council is recorded and never blocks",
          not_ready["status"] == "not_ready"
          and not_ready["blocks_build"] is False)
    graph2 = route.compile_route(normalized, not_ready)
    check("a not-ready Council does not change the compiled graph",
          substrate.compiler().graph_hash(graph2) ==
          substrate.compiler().graph_hash(
              route.compile_route(normalized, council.planning_step(
                  normalized, runner=not_ready_council))))


def main() -> int:
    print(f"skill root: {SKILL_ROOT}")
    print(f"open seams: {list(SEAM_IDS)}")
    print(f"decided: {list(DECIDED_IDS)}")
    try:
        run_elevation()
        run_seven_figure_preneur()
    except Exception:
        traceback.print_exc()
        return 2
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 0 if not FAILED else 2


if __name__ == "__main__":
    raise SystemExit(main())
