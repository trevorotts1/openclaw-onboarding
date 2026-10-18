"""Build-time page generation for the Launcher, separate from buyer-time.

Contract (doc 02 section 3): every enabled page is built independently of any
customer action. This module therefore accepts ONLY the approved launch
record. It has no event, purchase, journey-state or navigation parameter, and
it never calls route_law.navigate. Each enabled page gets its own build entry
from the real adapter wiring.
"""
from __future__ import annotations

from typing import Any, Dict, List
from pathlib import Path
import sys

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from launcher_core.constants import CROSS_SALE_TEACHING_STATE  # noqa: E402

import adapters
import route_law
import substrate


def plan(launch: Dict[str, Any]) -> Dict[str, Any]:
    """One independent build unit per enabled page. No buyer state involved."""
    compiled = route_law.compile_route(launch)
    graph = compiled["graph"]
    role_skill = substrate.dispatch().ROLE_SKILL
    pages: List[Dict[str, Any]] = []
    for node in graph["nodes"]:
        role = node["role"]
        if role in adapters.NATIVE_SURFACES:
            surface = adapters.NATIVE_SURFACES[role]
            build_entry = {
                "skill": surface["skill"],
                "surface": surface["surface"],
                "dispatch_adapter": False,
            }
        else:
            wiring = adapters.adapter_for(role)
            build_entry = {
                "skill": wiring["skill"],
                "module": wiring["module"],
                "entry": wiring["entry"],
            }
            if "second_module" in wiring:
                build_entry = {
                    "skill": wiring["skill"],
                    "chain": [
                        {"module": wiring["module"], "entry": wiring["entry"]},
                        {"module": wiring["second_module"],
                         "entry": wiring["second_entry"]},
                    ],
                }
        entry = {
            "page_id": node["page_id"],
            "role": role,
            "assigned_skill": role_skill[role],
            "build_entry": build_entry,
            "buyer_action_required": False,
        }
        if role == "thank_you":
            # Cross-sale surface: an offer relationship shown after purchase.
            # The teaching content is not in hand; it is recorded as pending,
            # never invented and never a reason to drop the surface.
            entry["cross_sales"] = launch.get("cross_sales") or {
                "relationships": [],
                "teaching": {"state": CROSS_SALE_TEACHING_STATE},
                "route_node": False,
                "surface": "thank_you",
            }
        pages.append(entry)
    return {
        "launch_id": launch["launch_id"],
        "revision": launch["revision"],
        "journey_mode": launch.get("journey_mode"),
        "route_graph_hash": compiled["route_graph_hash"],
        "council": launch.get("council"),
        "pages": pages,
    }
