#!/usr/bin/env python3
"""S82 production thank-you page: the terminal page a buyer can be served.

`render_thank_you.py` builds the accessible fragment from a resolved order
view and is NOT changed here. This module wraps it into a publishable HTML
document and adds the one thing the page still owed: the buyer's DELIVERY
INSTRUCTIONS, one per actually purchased item.

PURCHASE TRUTH, ENFORCED HERE
-----------------------------
The view must declare that it was built from a verified normalized purchase
snapshot. Every item shown must be a purchase slot the approved route graph
carries (main/bump from checkout, upsell_1, downsell_1, upsell_2). Every
access block must belong to an item whose status is ``paid`` in this view -
access for anything else is refused, so a visit to U1/D1/U2 without buying
can never leak that offer's access. An unpurchased offer is never rendered,
never linked, never announced.

DELIVERY INSTRUCTIONS
---------------------
Read from the fulfillment/entitlement read (never invented): a record may
carry ``instruction`` text; otherwise the instruction is derived from its own
``state``/``next_action``/``delivery_url``. When a paid item has no granted
fulfillment yet, the page says access is being prepared and will also arrive
by email - it never claims access that does not exist.

FULFILLMENT DOES NOT DEPEND ON THIS PAGE
----------------------------------------
This builder only RENDERS state it is given. It grants nothing, sends nothing,
and is not on the fulfilment path: closing the browser before the thank-you
page cannot deny a confirmed buyer access (S44 owns fulfilment, begun on the
purchase event).

USAGE
  python3 build_thank_you_page.py --view order-view.json \
      --fulfillment fulfillment.json --route-graph route-graph.json \
      [--brand brand.json] --out-dir DIR
  python3 build_thank_you_page.py --selftest --out-dir DIR
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from render_thank_you import (  # noqa: E402
    ALLOWED_CTA_CLASSES, _https_access_url, _safe_url, render_thank_you)

THANK_YOU_ROLE = "thank_you"
#: purchase slot -> the route-graph role whose page sells it. The main offer
#: and the bump are both bought on the checkout step.
SLOT_ROLE = {"main": "checkout", "bump": "checkout", "upsell_1": "upsell_1",
             "downsell_1": "downsell_1", "upsell_2": "upsell_2"}
ALLOWED_ITEM_SLOTS = tuple(SLOT_ROLE)
PAID = "paid"
STATUSES = {"paid", "pending", "failed", "requires_customer_action",
            "refunded", "partially_refunded", "unknown"}


class PageError(RuntimeError):
    """The page cannot be built honestly; nothing is written."""


def _esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def load_json(path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def graph_hash(graph: dict, raw: bytes = None) -> str:
    """SHA-256 of the route-graph FILE's bytes (``raw``), the hash of record
    (``compile_launch_route.graph_file_hash``). An in-memory compiled graph
    (self-test) hashes the compiler's own emit serialization."""
    if raw is None:
        raw = (json.dumps(graph, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def route_roles(graph: dict) -> dict:
    """Read the approved graph's roles -> page id. A reader, not a planner."""
    nodes = graph.get("nodes") if isinstance(graph, dict) else None
    if not isinstance(nodes, list) or not nodes:
        raise PageError("route graph carries no nodes")
    out = {}
    for node in nodes:
        role, pid = node.get("role"), node.get("page_id")
        if not role or not pid or role in out:
            raise PageError(f"route graph node is incomplete or repeated: "
                            f"{node!r}")
        out[role] = pid
    if THANK_YOU_ROLE not in out:
        raise PageError("route graph carries no thank_you node")
    return out


def item_slot_allowed(slot, roles: dict) -> bool:
    """Every purchase slot maps to a route-graph role; that role must have a
    node in the approved graph (main and bump both ride ``checkout``)."""
    role = SLOT_ROLE.get(slot)
    return bool(role) and role in roles


def validate_view(view: dict, roles: dict) -> None:
    if not isinstance(view, dict):
        raise PageError("order view is not an object")
    provenance = view.get("provenance") or {}
    if provenance.get("built_from_verified_snapshot") is not True:
        raise PageError(
            "the order view was not built from a verified purchase snapshot; "
            "a page visit or URL parameter is never purchase authority")
    items = view.get("items")
    if not isinstance(items, list) or not items:
        raise PageError("the order view carries no purchased items")
    by_offer = {}
    for item in items:
        slot = item.get("slot")
        status = item.get("display_status")
        if slot not in ALLOWED_ITEM_SLOTS:
            raise PageError(f"item slot {slot!r} is not a purchase slot")
        if not item_slot_allowed(slot, roles):
            raise PageError(
                f"item slot {slot!r} has no node in the approved route graph; "
                "an offer the approved plan does not carry is not shown")
        if status not in STATUSES:
            raise PageError(f"item {item.get('offer_id')!r} has unknown "
                            f"status {status!r}")
        by_offer[item.get("offer_id")] = item
    paid_offers = {i.get("offer_id") for i in items
                   if i.get("display_status") == PAID}
    for block in view.get("access_blocks") or []:
        offer_id = block.get("offer_id")
        if offer_id not in by_offer:
            raise PageError(
                f"access block for {offer_id!r} belongs to no purchased item; "
                "access to an unpurchased offer is never shown")
        if offer_id not in paid_offers:
            raise PageError(
                f"access block for {offer_id!r} belongs to an item that is "
                f"{by_offer[offer_id].get('display_status')!r}, not paid; "
                "access is shown only for paid items")


def delivery_rows(view: dict, fulfillment: dict) -> list:
    """One row per item: its verified status and its delivery instruction."""
    fulfillment = fulfillment or {}
    blocks = {}
    for block in view.get("access_blocks") or []:
        blocks.setdefault(block.get("offer_id"), []).append(block)
    rows = []
    for item in view.get("items") or []:
        offer_id = item.get("offer_id")
        name = item.get("display_name") or offer_id
        status = item.get("display_status")
        instructions, links, states = [], [], []
        for block in blocks.get(offer_id, []):
            record = fulfillment.get(block.get("entitlement_id")) or {}
            state = record.get("state") or block.get("fulfillment_state") or ""
            states.append(state)
            url = _https_access_url(block.get("delivery_url")) \
                or _https_access_url(record.get("delivery_url"))
            action = block.get("next_action") or record.get("next_action") \
                or "access"
            if action not in ALLOWED_CTA_CLASSES:
                action = "access"
            instruction = record.get("instruction")
            if not instruction:
                instruction = (
                    f"{action.replace('_', ' ').title()}"
                    + (" — open the link below." if url else
                       "; it will also arrive by email."))
            instructions.append(str(instruction))
            if url:
                links.append((url, action))
        if not instructions:
            if status == PAID:
                instruction = ("Access for this item is being prepared. It "
                               "will also arrive by email; contact support if "
                               "it does not.")
            elif status == "pending":
                instruction = ("Payment is still being confirmed. Delivery "
                               "starts when it is confirmed; you do not need "
                               "to buy it again.")
            elif status == "failed":
                instruction = ("This item did not go through, so there is no "
                               "charge and no delivery for it.")
            else:
                instruction = ("This item is not active. Support can explain "
                               "its current state.")
            instructions.append(instruction)
        rows.append({
            "offer_id": offer_id,
            "slot": item.get("slot"),
            "display_name": name,
            "display_status": status,
            "instructions": instructions,
            "links": links,
            "fulfillment_states": states,
        })
    return rows


def _delivery_section(rows: list) -> str:
    if not rows:
        return ""
    cards = []
    for row in rows:
        links = "".join(
            '<a class="ty82-button ty82-button--secondary" data-cta-class="%s" '
            'href="%s">%s</a>'
            % (_esc(action), _esc(_safe_url(url)),
               _esc(action.replace("_", " ").title()))
            for url, action in row["links"])
        cards.append(
            '<div class="ty82-access-block" data-delivery-slot="%s">'
            "<h3>%s</h3><p>%s</p>%s</div>"
            % (_esc(row["slot"]), _esc(row["display_name"]),
               _esc(" ".join(row["instructions"])), links))
    return ('<section class="ty82" aria-labelledby="ty82-delivery-heading" '
            'data-ty82-section="3b">'
            '<h2 id="ty82-delivery-heading">Your delivery instructions</h2>'
            "<p>One instruction per item you actually purchased. Nothing "
            "unpurchased is listed here.</p>"
            '<div class="ty82-cards">%s</div></section>' % "".join(cards))


def build(view: dict, fulfillment: dict, graph: dict, brand: dict,
          graph_raw: bytes = None) -> dict:
    roles = route_roles(graph)
    validate_view(view, roles)
    rows = delivery_rows(view, fulfillment)
    fragment = render_thank_you(view, brand or {})
    document = "\n".join([
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="robots" content="noindex, nofollow">',
        "<title>%s</title>" % _esc(
            (brand or {}).get("brand_name") or "Your confirmation"),
        "</head>",
        "<body>",
        fragment,
        _delivery_section(rows),
        "</body>",
        "</html>",
    ]) + "\n"
    manifest = {
        "schema": "s82-thank-you-page/1",
        "order_ref": view.get("order_ref"),
        "order_number": view.get("order_number"),
        "thank_you_page_id": roles[THANK_YOU_ROLE],
        "route_graph_hash": graph_hash(graph, graph_raw),
        "items": rows,
        "rendered_paid_only": True,
        "fulfillment_authority": "s44",
        "fulfillment_independent_of_page": True,
        "sha256": hashlib.sha256(document.encode("utf-8")).hexdigest(),
    }
    return {"document": document, "manifest": manifest}


def write_page(out_dir: Path, built: dict) -> list:
    out_dir.mkdir(parents=True, exist_ok=True)
    page = out_dir / "thank-you.html"
    page.write_text(built["document"], encoding="utf-8")
    manifest = out_dir / "thank-you-manifest.json"
    manifest.write_text(json.dumps(built["manifest"], indent=2) + "\n",
                        encoding="utf-8")
    return [str(page), str(manifest)]


def _repo_root() -> Path:
    """The directory that holds the numbered skill folders, in BOTH
    distributions (``<root>/49-signature-funnel`` and
    ``<root>/.claude/skills/49-signature-funnel``)."""
    here = Path(__file__).resolve().parent
    for parent in [here] + list(here.parents)[:8]:
        for prefix in (parent, parent / ".claude" / "skills"):
            if (prefix / "49-signature-funnel" / "scripts"
                    / "compile_launch_route.py").is_file():
                return prefix
    raise PageError("cannot locate 49-signature-funnel from %s" % here)


def _selftest(out_dir: Path) -> int:
    repo = _repo_root()
    sys.path.insert(0, str(repo / "49-signature-funnel" / "scripts"))
    import compile_launch_route as compiler  # noqa: E402

    launch = load_json(repo / "49-signature-funnel" / "scripts" / "fixtures"
                       / "finalized-launch-record-signature-launch-l4.json")
    graph = compiler.compile_route(launch)
    view = load_json(repo / "82-signature-thank-you" / "fixtures"
                     / "test-only-order-view.json")
    fulfillment = load_json(repo / "82-signature-thank-you" / "fixtures"
                            / "test-only-fulfillment.json")
    brand = load_json(repo / "82-signature-thank-you" / "fixtures"
                      / "test-only-brand.json")
    built = build(view, fulfillment, graph, brand)
    text = built["document"]
    errors = []
    if "<!DOCTYPE html>" not in text or "</html>" not in text:
        errors.append("output is not a full document")
    for name in ("TEST ONLY MAIN-A", "TEST ONLY BUMP", "TEST ONLY U1"):
        if name not in text:
            errors.append("purchased item missing: %s" % name)
    if "Your delivery instructions" not in text:
        errors.append("delivery instructions section missing")
    slots = [row["slot"] for row in built["manifest"]["items"]]
    if slots != ["main", "bump", "upsell_1"]:
        errors.append("manifest items wrong: %s" % slots)
    if built["manifest"]["thank_you_page_id"] != "signature-launch-l4-THANK_YOU":
        errors.append("thank-you page id is not the graph's")
    if built["manifest"]["route_graph_hash"] != launch["route_graph_hash"]:
        errors.append("route graph hash does not match the launch record")
    unpurchased = dict(
        view,
        access_blocks=list(view["access_blocks"]) + [{
            "entitlement_id": "u2-entitlement", "offer_id": "U2",
            "slot": "upsell_2", "next_action": "access",
            "delivery_url": "https://example.test/access/u2",
            "fulfillment_state": "granted"}])
    try:
        build(unpurchased, fulfillment, graph, brand)
        errors.append("access for an unpurchased offer was not refused")
    except PageError:
        pass
    unverified = dict(view, provenance={"built_from_verified_snapshot": False})
    try:
        build(unverified, fulfillment, graph, brand)
        errors.append("an unverified view was not refused")
    except PageError:
        pass
    pending = json.loads(json.dumps(view))
    pending["items"][2]["display_status"] = "pending"
    pending["access_blocks"] = pending["access_blocks"][:2]
    pending["confirmation"] = {"status": "partially_pending",
                               "headline": "Your purchase is confirmed."}
    built_pending = build(pending, fulfillment, graph, brand)
    if "Delivery starts when it is confirmed" not in built_pending["document"]:
        errors.append("a pending item did not get the pending instruction")
    written = write_page(out_dir, built)
    for path in written:
        if not Path(path).is_file():
            errors.append("missing output %s" % path)
    if errors:
        for e in errors:
            print("  FAIL: %s" % e, file=sys.stderr)
        print("[selftest] FAIL - %d error(s)" % len(errors), file=sys.stderr)
        return 1
    print("[selftest] PASS - thank-you page built (%s)" % ", ".join(written))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--view")
    parser.add_argument("--fulfillment")
    parser.add_argument("--route-graph")
    parser.add_argument("--brand")
    parser.add_argument("--out-dir")
    args = parser.parse_args(argv)
    if not args.out_dir:
        print("--out-dir is required", file=sys.stderr)
        return 2
    out_dir = Path(args.out_dir)
    if args.selftest:
        return _selftest(out_dir)
    if not (args.view and args.route_graph):
        print("--view and --route-graph are required", file=sys.stderr)
        return 2
    try:
        graph_raw = Path(args.route_graph).read_bytes()
        built = build(load_json(args.view),
                      load_json(args.fulfillment) if args.fulfillment else {},
                      json.loads(graph_raw.decode("utf-8")),
                      load_json(args.brand) if args.brand else {},
                      graph_raw=graph_raw)
    except PageError as exc:
        print("FAIL-CLOSED: %s" % exc, file=sys.stderr)
        return 2
    for path in write_page(out_dir, built):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
