#!/usr/bin/env python3
"""Route law in code (DTY-25, UPS-26): the legacy preset graph obeys the launch
route law, and role_wrappers.py is stated library-only and is not on the run path.

Run: python3 -m pytest 49-signature-funnel/scripts/test_route_presets.py -q
"""
import ast
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
ROOT = SKILL.parent
sys.path.insert(0, str(HERE))

import compile_launch_route as clr  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ra = _load("route_adapters_under_test",
           ROOT / "shared-utils" / "signature_launch" / "route_adapters.py")


def _out(graph, node):
    return {e["on"]: e["to"] for e in graph["edges"] if e["from"] == node}


def test_preset5_downsell_decline_goes_to_thank_you_never_upsell_2():
    out = _out(ra.preset_graph(5), "downsell")
    assert out["decline"] == "thank-you"
    assert out["accept"] == "upsell-2"  # paid goes to the same U2


def test_every_preset_downsell_decline_is_thank_you():
    for size in (5, 7):
        g = ra.preset_graph(size)
        for node in g["nodes"]:
            if node["page_role"] == "downsell_1":
                assert _out(g, node["id"])["decline"] == "thank-you", (size, node["id"])


def test_legacy_preset_matches_compiled_launch_route_for_d1():
    launch = {"tenant_id": "t", "location_id": "l", "launch_id": "L", "revision": 1,
              "journey_mode": "single_simple",
              "extras": {"upsell_1": True, "downsell_1": True, "upsell_2": True}}
    role_of = {n["page_id"]: n["role"] for n in clr.compile_route(launch)["nodes"]}
    law = {e["event"]: role_of[e["to"]] for e in clr.compile_route(launch)["edges"]
           if role_of[e["from"]] == "downsell_1"}
    legacy = _out(ra.preset_graph(5), "downsell")
    assert law["explicit_decline"] == "thank_you" == legacy["decline"].replace("-", "_")
    assert law["payment_succeeded"] == "upsell_2" == legacy["accept"].replace("-", "_")


def test_preset_adapters_still_validate_and_carry_decline_kind():
    doc = ra.preset_route_adapters(5, location="ghl-test")
    ids = {n["node_id"]: n["logical_id"] for n in doc["pages"]}
    kinds = {e["kind"]: e["to"] for e in doc["edges"]
             if e["from"] == ids["downsell"] and e["kind"] != "error"}
    assert kinds == {"accept": ids["upsell-2"], "decline": ids["thank-you"]}


def test_role_wrappers_states_library_only_and_run_path_does_not_import_it():
    doc = ast.get_docstring(ast.parse((SKILL / "role_wrappers.py").read_text(encoding="utf-8")))
    assert "LIBRARY ONLY" in doc
    tree = ast.parse((HERE / "dispatch_launch.py").read_text(encoding="utf-8"))
    imported = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imported |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            imported.add(n.module.split(".")[0])
    assert "role_wrappers" not in imported
