#!/usr/bin/env python3
"""Funnel journey verifier + guarded test-mode order (S06-14).

"Every page installed" is not "the funnel works": a selection button can link to
the wrong step, or a 'No thanks' can lead to a 404. This module walks Skill 83's
route graph (nodes {page_id, role}, edges {from, to, event, guard}) on the
PUBLISHED funnel: for each edge it opens the source page, clicks that edge's
control, and asserts the landing URL equals the published URL of the edge's
target node and that the response is not an error.

The browser is injected, so the check is testable with a fake and the real
driver (Playwright, agent-browser, ...) lives outside this file:

    browser.click_edge(source_url: str, edge: dict) -> (final_url: str, status: int)

`run_test_order` is the payment-provider test-mode order. It is refused unless
the location is explicitly marked approved-test AND the launcher approval_ref
verifies. It never runs on an unmarked (client) location, and it refuses a
result that was not made in provider test mode.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Iterable, Optional
from urllib.parse import urlsplit


class TestOrderRefused(Exception):
    """The test-mode order was refused before any provider call was made."""

    __test__ = False  # not a pytest test class


def _norm(url: str) -> str:
    """scheme://host/path without query, fragment or trailing slash."""
    p = urlsplit(str(url or "").strip())
    return f"{p.scheme.lower()}://{p.netloc.lower()}{p.path.rstrip('/')}"


def verify_journey(graph: Dict[str, Any], published_urls: Dict[str, str], browser: Any) -> Dict[str, Any]:
    """Click every route edge on the published funnel; assert each target URL.

    Fails closed: no edges, an edge naming a node with no published URL, a
    browser error, an HTTP status >= 400 or a wrong landing URL all fail.
    """
    edges = graph.get("edges") or []
    results = []
    for edge in edges:
        src, dst = published_urls.get(edge.get("from")), published_urls.get(edge.get("to"))
        row = {"from": edge.get("from"), "to": edge.get("to"), "event": edge.get("event"),
               "expected": dst, "actual": None, "status": None, "ok": False, "reason": None}
        if not src or not dst:
            row["reason"] = "no published URL for edge endpoint"
        else:
            try:
                final_url, status = browser.click_edge(src, edge)
            except Exception as exc:  # a click that cannot be made is a failed edge
                row["reason"] = f"click failed: {type(exc).__name__}"
            else:
                row.update(actual=final_url, status=status)
                if not isinstance(status, int) or status >= 400:
                    row["reason"] = f"error response {status}"
                elif _norm(final_url) != _norm(dst):
                    row["reason"] = "wrong target URL"
                else:
                    row["ok"] = True
        results.append(row)
    return {"ok": bool(results) and all(r["ok"] for r in results),
            "edges_checked": len(results), "results": results}


def load_approved_test_locations(path: str) -> frozenset:
    """Read {"approved_test_locations": [ids]}. Missing/unreadable file -> empty (fail closed)."""
    try:
        with open(path, encoding="utf-8") as fh:
            return frozenset(str(x) for x in json.load(fh).get("approved_test_locations") or [])
    except (OSError, ValueError, AttributeError):
        return frozenset()


def run_test_order(location_id: str, approval_ref: str, *,
                   approved_test_locations: Iterable[str],
                   verify_approval: Optional[Callable[[str, str], bool]],
                   place_order: Callable[[str], Dict[str, Any]]) -> Dict[str, Any]:
    """Place ONE provider test-mode order, only on an approved-test location.

    `verify_approval(approval_ref, location_id) -> bool` is the launcher's
    approval verifier; with none supplied the order is refused.
    """
    if not location_id or location_id not in set(approved_test_locations):
        raise TestOrderRefused("location is not marked approved-test")
    if not approval_ref or verify_approval is None or verify_approval(approval_ref, location_id) is not True:
        raise TestOrderRefused("launcher approval_ref did not verify")
    order = place_order(location_id)
    if order.get("livemode") is not False:
        raise TestOrderRefused("provider result is not a test-mode order")
    return order
