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
is not evidence of an installed binding.

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


def _require_const(request, field, expected, code):
    if request.get(field) != expected:
        raise InstallPlanError(
            code, f"request {field} must be {expected!r}, got "
            f"{request.get(field)!r}")


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
    _require_const(request, "schema_version", "1.0",
                   "D1-INSTALL-REQUEST-SCHEMA-VERSION")
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
