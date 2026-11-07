"""Skill 81 (D1) S06 install wrapper (S81-05 companion), reconciled
to the confirmed extra-offer interface contract.

The confirmed contract (S49, contract owner): revision 1
(rooms/S49/s79-interface-confirmation/
extra_offer_interface-CONFIRMED.md, SHA-256
cb2a15f7af367432824c70b5f4c287cdb65336668cd3f6e18328612797402a0b) as
completed by revision 2 (followon-g7/
extra_offer_interface-CONFIRMED-r2.md, SHA-256
07f6b75794a3a8e98aad02a94fb82bcdec78d1264b0a56fa3bda066484b3022f,
post-cure; as authored
3bd42c33fe8ade1579dc2890e83e82b0a7647f5cb6ac761375e0f9f57819f2e8).
For CR-S81-009, revision 2 section 8A.8 carries the tenant/location
binding read-back output FOR EXTRA OFFERS: tenant, location, and
offer identity read from the installed configuration (S06 is the
installed binding source), never echoed from the request, with a
binding mismatch reported as a failure and no charge path proceeding
on a mismatched binding. The plan's read-back step therefore names a
CONFIRMED carrier. It still stays required, planned, and UNRECORDED:
recorded flips only off an actual install read-back, and no install
is performed by or for this package (the owner's no-sandbox ruling
struck the install-proof legs), so the plan itself remains
provisional by design.

This wrapper produces the S06 install PLAN for the D1 page and nothing
else. It performs NO install, NO network call, and NO file write: the
plan object is handed to Skill 6's native install rail later. A plan
is not evidence of an installed binding. Status: design only; not
installed. ``install_d1_page`` refuses and names the scheduled Skill 06
work items (S06-02, UPS-08) instead of doing nothing.

The shape mirrors the committed S06 plan layer: the product binding is
CALLER-SUPPLIED (this wrapper never invents a native product or price
id) and every missing, mismatched, or out-of-scope input fails closed
with a named error before any plan exists. Inputs are the page request
(schemas/downsell-request.schema.json), the caller-supplied native
product/price binding, and the verified page bundle (copy, design,
assets, action binding refs) named in adapters/README.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "validators"))
from validate_downsell import _blank  # noqa: E402  (package-internal helper)


class InstallPlanError(Exception):
    """The install plan failed closed. ``code`` is the named error;
    ``detail`` carries the reason and any missing field names."""

    def __init__(self, code, detail="", missing=None):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
        self.missing = list(missing or [])


# DTY-11: the D1 page is design-only until Skill 6 ships a native
# install step for it. Skill 06 work items that schedule that step:
# S06-02 (commerce driver) and UPS-08 (extra-offer install). Any client
# summary line for D1 reads DESIGN_ONLY_STATUS until Skill 6 records a
# binding read-back for it.
DESIGN_ONLY_STATUS = "design only; not installed"
SCHEDULED_SKILL06_WORK_ITEMS = ("S06-02", "UPS-08")


class InstallRefusedError(InstallPlanError):
    """The D1 install was requested but no installer exists. Raised by
    ``install_d1_page``; ``detail`` names the scheduled Skill 06 work
    items so the refusal is never a silent no-op."""


def install_d1_page(*_args, **_kwargs):
    """Refuse. This package has no installer: Skill 6's native install
    step for D1 is scheduled work (``SCHEDULED_SKILL06_WORK_ITEMS``), not
    shipped code. Always raises ``InstallRefusedError``; never returns,
    never writes, never calls the network."""
    raise InstallRefusedError(
        "D1-INSTALL-DESIGN-ONLY",
        f"{DESIGN_ONLY_STATUS}: no D1 installer exists; the native "
        "install is scheduled Skill 06 work item(s) "
        + " / ".join(SCHEDULED_SKILL06_WORK_ITEMS))


# Required fields of schemas/downsell-request.schema.json, in the
# schema's own required order.
REQUEST_REQUIRED = [
    "schema_version", "tenant_id", "location_id", "launch_id",
    "revision", "request_id", "page_id", "page_role", "assigned_skill",
    "approval_ref", "input_hash", "brand_ref", "brand_hash",
    "route_graph_ref", "route_graph_hash", "declined_u1_offer_ref",
    "downsell_offer_ref", "difference_kind", "native_product_id",
    "native_price_id", "entry_guard_ref", "success_route",
    "decline_route", "copy_profile", "allowed_write_target", "test_only",
]

_DIFFERENCE_KINDS = {"reduced_scope", "lower_total_price",
                     "changed_payment_terms", "changed_access_terms"}
_SUCCESS_ROUTES = {"upsell_2", "thank_you"}
_WRITE_TARGETS = {"local_only", "approved_test_location",
                  "approved_live_publication"}

# Binding fields the plan's read-back step must confirm against the
# installed location before anyone treats the binding as real.
READBACK_FIELDS = ["native_product_id", "native_price_id",
                   "purchase_action_ref", "decline_action_ref", "page_id"]

#: The one native install rail this package hands its plan to. Skill 6 owns
#: the driver; this package owns the D1 page and its bindings and never
#: imports a browser.
INSTALL_RAIL = "06-ghl-install-pages/tools/ghl_funnel_steps.install_funnel"
#: The D1 offer slot in the funnel installer's own offer vocabulary.
RAIL_OFFER_ROLE = "downsell_1"


def _route_link(by_role, role, key):
    link = (by_role.get(role) or {}).get(key) or {}
    return link.get("target_role"), link.get("target_page_id")


def read_approved_routes(graph):
    """READ the approved route graph (Skill 49's compiled graph) into
    ``{role: {page_id, accept, decline}}``. A reader: nothing is derived."""
    if not isinstance(graph, dict):
        raise InstallPlanError("D1-INSTALL-ROUTE-GRAPH-MALFORMED",
                               "route graph is not an object")
    nodes, edges = graph.get("nodes"), graph.get("edges")
    if not isinstance(nodes, list) or not nodes:
        raise InstallPlanError("D1-INSTALL-ROUTE-GRAPH-MALFORMED",
                               "route graph carries no nodes")
    if not isinstance(edges, list):
        raise InstallPlanError("D1-INSTALL-ROUTE-GRAPH-MALFORMED",
                               "route graph carries no edges")
    role_of, by_role = {}, {}
    for node in nodes:
        pid = str(node.get("page_id") or "").strip()
        role = str(node.get("role") or "").strip()
        if not pid or not role:
            raise InstallPlanError("D1-INSTALL-ROUTE-GRAPH-MALFORMED",
                                   f"route node is incomplete: {node!r}")
        if pid in role_of or role in by_role:
            raise InstallPlanError("D1-INSTALL-ROUTE-GRAPH-MALFORMED",
                                   f"route graph repeats {pid!r}/{role!r}")
        role_of[pid] = role
        by_role[role] = {"page_id": pid, "accept": None, "decline": None}
    for edge in edges:
        frm, to = edge.get("from"), edge.get("to")
        if frm not in role_of or to not in role_of:
            raise InstallPlanError("D1-INSTALL-ROUTE-GRAPH-MALFORMED",
                                   f"dangling edge {edge!r}")
        event = edge.get("event")
        if event not in ("payment_succeeded", "explicit_decline"):
            continue
        key = "accept" if event == "payment_succeeded" else "decline"
        role = role_of[frm]
        if by_role[role][key] is not None:
            raise InstallPlanError(
                "D1-INSTALL-ROUTE-GRAPH-MALFORMED",
                f"second {event} edge from {role!r}")
        guard = edge.get("guard")
        if not isinstance(guard, str) or not guard.strip():
            raise InstallPlanError("D1-INSTALL-ROUTE-GRAPH-MALFORMED",
                                   f"unguarded edge {edge!r}")
        if key == "accept" and not guard.startswith("verified_"):
            raise InstallPlanError(
                "D1-INSTALL-ROUTE-GRAPH-MALFORMED",
                f"paid edge from {role!r} carries guard {guard!r}")
        if key == "decline" and guard != "no_charge_decline":
            raise InstallPlanError(
                "D1-INSTALL-ROUTE-GRAPH-MALFORMED",
                f"decline edge from {role!r} carries guard {guard!r}")
        by_role[role][key] = {"event": event, "target_role": role_of[to],
                              "target_page_id": to, "guard": guard}
    if "downsell_1" not in by_role:
        raise InstallPlanError(
            "D1-INSTALL-ROUTE-GRAPH-NO-D1",
            "the approved route graph carries no downsell_1 node")
    return by_role


def production_handoff(request, product_binding, page_bundle, route_graph):
    """The D1 production handoff: the page identity and every binding the
    native install needs, read from the APPROVED route graph.

    Returns the S06 install plan (see ``build_install_plan``) extended with
    ``handoff``: the page id, the native product/price, the purchase and
    decline action refs, the paid and decline targets, and the rail entry the
    caller hands to ``ghl_funnel_steps.install_funnel``.

    The route targets are cross-checked against the graph, so page
    generation, the native button configuration and the workflow delivery all
    read ONE route source. ``installed`` stays False and ``binding_readback``
    stays unrecorded until a real install read-back exists: a handoff is not
    evidence of an installed binding.
    """
    plan = build_install_plan(request, product_binding, page_bundle)
    by_role = read_approved_routes(route_graph)
    d1 = by_role["downsell_1"]
    accept_role, accept_page = _route_link(by_role, "downsell_1", "accept")
    decline_role, decline_page = _route_link(by_role, "downsell_1", "decline")
    if decline_role != "thank_you":
        raise InstallPlanError(
            "D1-INSTALL-DECLINE-ROUTE-DIVERGES",
            f"the approved graph routes the D1 decline to {decline_role!r}; "
            "the D1 contract routes a decline to the final thank-you")
    if accept_role not in ("upsell_2", "thank_you"):
        raise InstallPlanError(
            "D1-INSTALL-SUCCESS-ROUTE-DIVERGES",
            f"the approved graph routes a paid D1 to {accept_role!r}; only "
            "the canonical upsell_2 or the final thank-you is valid")
    if request["success_route"] != accept_role:
        raise InstallPlanError(
            "D1-INSTALL-SUCCESS-ROUTE-DIVERGES",
            f"the page request routes a paid D1 to "
            f"{request['success_route']!r} while the approved graph routes it "
            f"to {accept_role!r}; the graph is the single route source")
    if accept_role == "upsell_2":
        u2_page = (by_role.get("upsell_2") or {}).get("page_id")
        if u2_page and page_bundle.get("canonical_u2_page_id") \
                and page_bundle["canonical_u2_page_id"] != u2_page:
            raise InstallPlanError(
                "D1-INSTALL-U2-ID-MISMATCH",
                "the bundle's canonical U2 page id is not the graph's "
                "upsell_2 page id; a D1-specific duplicate U2 is never "
                "installed")
    if request["page_id"] != d1["page_id"]:
        raise InstallPlanError(
            "D1-INSTALL-PAGE-ID-DIVERGES",
            f"the page request names {request['page_id']!r} while the "
            f"approved graph names {d1['page_id']!r} for downsell_1")
    plan["handoff"] = {
        "page_role": "downsell_1",
        "page_id": d1["page_id"],
        "native_product_id": product_binding["native_product_id"],
        "native_price_id": product_binding["native_price_id"],
        "purchase_action_ref": page_bundle["action_refs"]["purchase_action_ref"],
        "decline_action_ref": page_bundle["action_refs"]["decline_action_ref"],
        "purchase_is_native_action": True,
        "purchase_navigates": False,
        "on_payment_succeeded": {"target_role": accept_role,
                                 "target_page_id": accept_page},
        "on_explicit_decline": {"target_role": decline_role,
                                "target_page_id": decline_page},
        "on_payment_failed": {"is_decline": False, "is_acceptance": False,
                              "behaviour": "remain_on_page_recoverable"},
        "on_payment_pending": {"is_decline": False, "is_acceptance": False,
                               "behaviour": "remain_on_page_recoverable"},
        "install_rail": INSTALL_RAIL,
        "rail_offer": {"role": RAIL_OFFER_ROLE,
                       "offer_id": request["downsell_offer_ref"]},
        "installed": False,
        "install_status": DESIGN_ONLY_STATUS,
    }
    plan["installed"] = False
    return plan


def _require_const(request, field, expected, code):
    if request.get(field) != expected:
        raise InstallPlanError(
            code, f"request {field} must be {expected!r}, got "
            f"{request.get(field)!r}")

# The adoption map 1.5 dual-accept pair rule, applied at the plan
# layer: request 1.0 must carry no prompt_policy_id key, and request
# 1.1 must carry it as a non-empty string. The citation itself is
# read at the receipt and registry layer (map section 4); the plan
# dict never echoes it, and plan_kind / provisional-1 are unchanged.
POLICY_FIELD = "prompt_policy_id"

def _check_request_version_pair(request):
    version = request.get("schema_version")
    if version == "1.0":
        if POLICY_FIELD in request:
            raise InstallPlanError(
                "D1-INSTALL-REQUEST-UNEXPECTED-PROMPT_POLICY_ID",
                "request schema_version 1.0 must not carry "
                f"{POLICY_FIELD} (the 1.0 contract has no such field)")
        return
    if version == "1.1":
        if POLICY_FIELD not in request:
            raise InstallPlanError(
                "D1-INSTALL-REQUEST-MISSING-PROMPT_POLICY_ID",
                "request schema_version 1.1 must carry a non-empty "
                f"{POLICY_FIELD}; the request carries none")
        value = request.get(POLICY_FIELD)
        if not isinstance(value, str):
            raise InstallPlanError(
                "D1-INSTALL-REQUEST-PROMPT_POLICY_ID-WRONG-TYPE",
                f"{POLICY_FIELD} must be a non-empty string, got "
                f"{value!r}")
        if _blank(value):
            raise InstallPlanError(
                "D1-INSTALL-REQUEST-PROMPT_POLICY_ID-TOO-SHORT",
                f"{POLICY_FIELD} must be a non-empty string, got "
                f"{value!r}")
        return
    raise InstallPlanError(
        "D1-INSTALL-REQUEST-SCHEMA-VERSION",
        "request schema_version must be '1.0' or '1.1', got "
        f"{version!r}")


def build_install_plan(request, product_binding, page_bundle):
    """Build the S06 install plan for the D1 page. The plan is
    plan-only and stays provisional: it records no install and no
    read-back result.

    request: dict per schemas/downsell-request.schema.json.
    product_binding: caller-supplied {"native_product_id",
    "native_price_id"} for the D1 offer.
    page_bundle: the verified page bundle: an identifying bundle_ref
    or content_hash, plus action_refs {"purchase_action_ref",
    "decline_action_ref"} and, when the success route is upsell_2,
    canonical_u2_page_id.

    Returns the plan dict. Raises InstallPlanError, fail-closed, on
    any missing, malformed, mismatched, or out-of-scope input.
    """
    if not isinstance(request, dict):
        raise InstallPlanError("D1-INSTALL-REQUEST-MALFORMED",
                               "page request is not a dict")
    # The schema requires every field present, but native_product_id
    # and native_price_id are nullable there (the binding arrives
    # caller-supplied, below), so null counts as missing only for the
    # non-nullable fields; a blank string counts as missing everywhere.
    nullable = {"native_product_id", "native_price_id"}
    missing = [f for f in REQUEST_REQUIRED
               if f not in request
               or (request.get(f) is None and f not in nullable)
               or (isinstance(request.get(f), str)
                   and _blank(request.get(f)))]
    if missing:
        raise InstallPlanError(
            "D1-INSTALL-REQUEST-MISSING-FIELDS",
            "page request is missing required fields", missing=missing)
    _check_request_version_pair(request)
    _require_const(request, "page_role", "downsell_1",
                   "D1-INSTALL-REQUEST-PAGE-ROLE")
    _require_const(request, "assigned_skill", 81,
                   "D1-INSTALL-REQUEST-SKILL")
    _require_const(request, "copy_profile", "signature-downsell-v1",
                   "D1-INSTALL-REQUEST-COPY-PROFILE")
    _require_const(request, "decline_route", "thank_you",
                   "D1-INSTALL-REQUEST-DECLINE-ROUTE")
    if request["success_route"] not in _SUCCESS_ROUTES:
        raise InstallPlanError(
            "D1-INSTALL-REQUEST-SUCCESS-ROUTE",
            f"success_route must be one of {sorted(_SUCCESS_ROUTES)}, "
            f"got {request['success_route']!r}")
    if request["difference_kind"] not in _DIFFERENCE_KINDS:
        raise InstallPlanError(
            "D1-INSTALL-REQUEST-DIFFERENCE-KIND",
            f"difference_kind {request['difference_kind']!r} is not a "
            "declared D1 difference kind")
    target = request["allowed_write_target"]
    if target not in _WRITE_TARGETS:
        raise InstallPlanError("D1-INSTALL-TARGET-INVALID",
                               f"allowed_write_target {target!r} is "
                               "not a declared write target")
    if target == "approved_live_publication":
        # No live activation is authorized from this room; this
        # wrapper will not even plan one.
        raise InstallPlanError(
            "D1-INSTALL-LIVE-TARGET-REFUSED",
            "this install wrapper never plans a live publication; "
            "live activation is outside S81's authority")

    # Caller-supplied product binding (the S06 plan-layer discipline:
    # the caller supplies the binding, the plan layer never invents
    # one, and an absent binding is a refusal, not a default).
    if not isinstance(product_binding, dict) \
            or _blank(product_binding.get("native_product_id")) \
            or _blank(product_binding.get("native_price_id")):
        raise InstallPlanError(
            "D1-INSTALL-BINDING-MISSING",
            "caller-supplied product binding must carry a non-blank "
            "native_product_id and native_price_id")
    for field in ("native_product_id", "native_price_id"):
        if request.get(field) is not None \
                and request[field] != product_binding[field]:
            raise InstallPlanError(
                "D1-INSTALL-BINDING-MISMATCH",
                f"caller-supplied binding {field} "
                f"{product_binding[field]!r} does not match the page "
                f"request's {request[field]!r}")

    if not isinstance(page_bundle, dict):
        raise InstallPlanError("D1-INSTALL-BUNDLE-MALFORMED",
                               "page bundle is not a dict")
    bundle_ref = page_bundle.get("bundle_ref") \
        or page_bundle.get("content_hash")
    if _blank(bundle_ref):
        raise InstallPlanError(
            "D1-INSTALL-BUNDLE-UNIDENTIFIED",
            "page bundle carries neither a bundle_ref nor a "
            "content_hash; an unidentified bundle is never planned")
    action_refs = page_bundle.get("action_refs")
    if not isinstance(action_refs, dict) \
            or _blank(action_refs.get("purchase_action_ref")) \
            or _blank(action_refs.get("decline_action_ref")):
        raise InstallPlanError(
            "D1-INSTALL-ACTION-BINDING-MISSING",
            "page bundle must carry the purchase and decline action "
            "references for the D1 page")
    if action_refs["decline_action_ref"] == action_refs["purchase_action_ref"]:
        raise InstallPlanError(
            "D1-INSTALL-DECLINE-IS-PURCHASE-ACTION",
            "the decline action reference must differ from the "
            "purchase action reference; a decline bound to the charge "
            "action would charge on decline")
    u2_id = page_bundle.get("canonical_u2_page_id")
    if request["success_route"] == "upsell_2" and _blank(u2_id):
        raise InstallPlanError(
            "D1-INSTALL-U2-ID-MISSING",
            "success route is upsell_2 but the bundle names no "
            "canonical U2 page id; a D1-specific duplicate U2 is "
            "never planned")

    steps = [
        {"step": "verify_page_bundle", "bundle_ref": bundle_ref,
         "copy_profile": request["copy_profile"],
         "input_hash": request["input_hash"]},
        {"step": "bind_native_product_price",
         "native_product_id": product_binding["native_product_id"],
         "native_price_id": product_binding["native_price_id"],
         "binding_source": "caller_supplied"},
        {"step": "bind_action_refs",
         "purchase_action_ref": action_refs["purchase_action_ref"],
         "decline_action_ref": action_refs["decline_action_ref"]},
        {"step": "install_page_draft",
         "page_id": request["page_id"], "page_role": "downsell_1",
         "location_id": request["location_id"], "target": target,
         "activation": "none"},
        {"step": "read_back_binding", "required": True,
         "fields": list(READBACK_FIELDS),
         "carrier_status": "CONFIRMED_R2_SECTION_8A.8_BINDING_READBACK",
         # The recordable result slot for the confirmed section 8A.8
         # read-back output. It stays None in every plan: a result is
         # recorded only from an actual install read-back, never from
         # the request (section 8A.8: never echoed from the request).
         "result": None},
    ]
    return {
        "plan_kind": "s06-install-plan",
        "schema_version": "provisional-1",
        "provisional": True,
        "executes_install": False,
        "network_calls": False,
        "installed": False,
        "install_status": DESIGN_ONLY_STATUS,
        "scheduled_skill06_work_items": list(SCHEDULED_SKILL06_WORK_ITEMS),
        "skill": 81,
        "page_role": "downsell_1",
        "request_id": request["request_id"],
        "tenant_id": request["tenant_id"],
        "location_id": request["location_id"],
        "launch_id": request["launch_id"],
        "target": target,
        "test_only": request["test_only"],
        "product_binding": {
            "native_product_id": product_binding["native_product_id"],
            "native_price_id": product_binding["native_price_id"],
            "binding_source": "caller_supplied",
        },
        "steps": steps,
        "binding_readback": {"required": True, "recorded": False,
                             "carrier_status":
                                 "CONFIRMED_R2_SECTION_8A.8_BINDING_READBACK",
                             "result": None},
        "routes": {
            "success": request["success_route"],
            "decline": "thank_you",
            "canonical_u2_page_id":
                u2_id if request["success_route"] == "upsell_2" else None,
            "u2_entry_context":
                "from_downsell_1"
                if request["success_route"] == "upsell_2" else None,
        },
    }


def _selftest():
    """Prove the D1 handoff against the REAL Skill 49 compiler: the route
    targets on the handoff are the graph's own edges, and every route
    divergence is refused. No network, no install, no browser."""
    import json
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", ".."))
    sys.path.insert(0, os.path.join(root, "49-signature-funnel", "scripts"))
    import compile_launch_route as compiler

    with open(os.path.join(root, "49-signature-funnel", "scripts", "fixtures",
                           "finalized-launch-record-signature-launch-l4.json"),
              encoding="utf-8") as fh:
        launch = json.load(fh)
    graph = compiler.compile_route(launch)
    with open(os.path.join(here, "..", "fixtures",
                           "valid-downsell-request.json"),
              encoding="utf-8") as fh:
        request = dict(json.load(fh))
    request.update(page_id="signature-launch-l4-DOWNSELL_1",
                   success_route="upsell_2",
                   route_graph_hash=launch["route_graph_hash"])
    binding = {"native_product_id": "6ad3260277b7bb2edf62765f",
               "native_price_id": "6ad3262da514801786c9ed15"}
    bundle = {"bundle_ref": "SELFTEST-D1-BUNDLE",
              "action_refs": {"purchase_action_ref": "native-d1-action",
                              "decline_action_ref": "native-decline-d1"},
              "canonical_u2_page_id": "signature-launch-l4-UPSELL_2"}
    errors = []
    plan = production_handoff(request, binding, bundle, graph)
    handoff = plan["handoff"]
    if handoff["on_payment_succeeded"] != {
            "target_role": "upsell_2",
            "target_page_id": "signature-launch-l4-UPSELL_2"}:
        errors.append("paid D1 does not route to the canonical U2: %r"
                      % handoff["on_payment_succeeded"])
    if handoff["on_explicit_decline"]["target_role"] != "thank_you":
        errors.append("declined D1 does not route to thank-you")
    if handoff["on_payment_failed"]["is_decline"] is not False \
            or handoff["on_payment_pending"]["is_acceptance"] is not False:
        errors.append("pending/failed is treated as a decline")
    if handoff["purchase_navigates"] is not False \
            or handoff["purchase_is_native_action"] is not True:
        errors.append("the purchase action is not native")
    if plan["installed"] is not False or plan["binding_readback"]["recorded"]:
        errors.append("the handoff claims an install it never performed")
    bad_cases = [
        ("page id diverges", dict(request, page_id="OTHER-PAGE"), binding,
         bundle, graph),
        ("success route diverges", dict(request, success_route="thank_you"),
         binding, bundle, graph),
        ("u2 id diverges", request, binding,
         dict(bundle, canonical_u2_page_id="OTHER-U2"), graph),
        ("graph has no D1", request, binding, bundle,
         {**graph, "nodes": [n for n in graph["nodes"]
                             if n["role"] != "downsell_1"]}),
    ]
    for label, req, bind, bnd, gph in bad_cases:
        try:
            production_handoff(req, bind, bnd, gph)
            errors.append("%s was not refused" % label)
        except InstallPlanError:
            pass
    if errors:
        for e in errors:
            print("  FAIL: %s" % e, file=sys.stderr)
        print("[selftest] FAIL - %d error(s)" % len(errors), file=sys.stderr)
        return 1
    print("[selftest] PASS - D1 production handoff reads the approved graph")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        raise SystemExit(_selftest())
    raise SystemExit("usage: s06_install_wrapper.py --selftest")
