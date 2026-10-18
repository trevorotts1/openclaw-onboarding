#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""downsell_wrapper.py - S49-08 bridge between S49 dispatch and Skill 81.

Skill 81 (81-signature-downsell, landed on main 2026-10-17 via PR #2229,
train #2235) ships NO executable consumer: its validators and adapters
are libraries, nothing reads a request file or writes a result file.
Per CR-S49-005 item 1 (CONFIRMED by S81), the runtime composition is
the validator library plus this S49 wrapper. The wrapper is the
invocable command dispatch runs for the downsell_1 role:

  1. ENRICH  builds the Skill 81 downsell-request (28 properties, 26
     required, additionalProperties: false) from the S49 page-request
     (1.0, or 1.1 under the adoption map 1.5 dual-accept revision of
     Skill 81's request contract): 18 fields carried verbatim at 1.0
     (19 at 1.1: the prompt_policy_id citation rides through into
     the enriched request, the contract document that carries it),
     offer_refs dropped (schema-illegal
     there), copy_profile overwritten to the const
     "signature-downsell-v1", and the 8 fields page-request 1.0 does
     not carry sourced from named inputs only - the launch record
     (declined/downsell offer refs by slot, native product/price ids
     from the record's D1 offer), the compiled route graph (success
     route from the D1 node's paid edge), and the enrichment sidecar
     (difference_kind, rationale, entry_guard_ref). A field with no
     honest source fails the run closed by name; the wrapper never
     fabricates a value. Native ids are never emitted as nulls at
     dispatch (CR-S49-005 item 4): a record that lacks them fails
     closed naming the missing binding.
  2. GAUNTLET  runs Skill 81's own contract checks, all fail-closed:
     the enriched request against the landed request schema (stdlib
     schema check, no third-party dependency, no silent skip); the
     entry guard over the guard state computed from the journey file
     and the record's extras; validate_copy over the staged page with
     its approved_amounts_minor set from the record's approved prices;
     validate_offer_difference over the record's U1/D1 offers with
     difference_kind and rationale folded in; and, for a non-one-time
     D1 price, validate_trial_disclosure over the staged disclosure.
  3. ASSEMBLE  validates the result extension the S81-side run staged
     (landed extension schema + validate_result_extension against the
     graph's canonical U2 page id), cross-checks its
     route_result.success_target against the enriched request's
     success_route (the request is the plan-side truth; CR-S49-005
     item 5) and its disclosure_audit.due_now_minor against the
     record's approved D1 price (the wrapper's result-time check;
     CR-S49-005 item 6, NOT claimed by S81), then assembles the base
     page-result 1.0 itself: exact echo identity from the S49 request,
     the extension written verbatim as the sibling artifact
     downsell-result-extension.json (never embedded; page-result 1.0
     is additionalProperties: false), and the projection validated
     through collect_launch_receipts.validate_result before placement.

HONESTY CEILING: this wrapper executes no native action and records
no install read-back, so a fully validated local run is capped at
status locally_verified / proof_class L2, never higher, and the
result names its standing blockers: no verified native action outcome
exists (the pending-lockout binding point is UNMAPPED,
D1-ADAPTER-PENDING-LOCKOUT-UNMAPPED, and CR-S81-006 is not
confirmed), and binding read-back is required but not recorded (the
install leg is plan-only).

The sidecar's difference_kind and rationale MUST be the launch's
recorded per-launch difference-table values (spec 11 section 4,
recorded before any copy is written), never values authored at
dispatch time: that is the binding sourcing condition of CR-S49-005
item 3, and the sidecar is whitelisted to exactly those keys plus
entry_guard_ref.

The landed validator and schemas are loaded from --skill81-root and
verified against the SHA-256 pins recorded when they were copied
verbatim from main at 9ccd653644a9ed179933ea32a801ee631c520125; a
diverging byte fails the run closed by name.

Deterministic, stdlib only. Exit 0 ok, 2 fail-closed refusal with a
named code, 3 usage error.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

EXIT_OK = 0
EXIT_FAILCLOSED = 2
EXIT_USAGE = 3

ROLE = "downsell_1"
SKILL = 81
D1_COPY_PROFILE = "signature-downsell-v1"
DECLINE_ROUTE = "thank_you"

# SHA-256 pins of the Skill 81 consumer bytes copied verbatim from
# main at 9ccd653644a9ed179933ea32a801ee631c520125 (PR #2229) into
# vendor-81/ at build time. The runtime loads these files from
# --skill81-root and refuses any byte that diverges from the pin.
PIN_VALIDATE_DOWNSELL = \
    "2a0d1d9fc8858080f58bcb9f08d84e76a0443332d387a3713e8402618476dd6d"
# PIN_REQUEST_SCHEMA was advanced by the adoption map 1.5 candidate
# (2026-10-18) to the dual-accept revision of Skill 81's request
# contract (schema_version enum 1.0/1.1 plus the Q12
# prompt_policy_id property); the other two pins stand because
# those bytes are unchanged.
PIN_REQUEST_SCHEMA = \
    "39e056705cae7fac81025e41feebdef5a1ed1ea87409423a4d60268c8c0d9e2b"
PIN_EXTENSION_SCHEMA = \
    "8108de3c81fe0d93843e8511d94b82ffe2bb0da6d723e3e0438b5268aa39e80e"

# The 19 page-request 1.0 fields (the packet schema's exact property
# set). A 1.1 request additionally carries exactly one key,
# prompt_policy_id (the prompt-policy citation, Q12 shape); it is
# admitted only on a request stamped "1.1", under the pair rule
# enforced in enrich (adoption map 1.5). Any other key fails closed
# by name instead of being forwarded (the upsell wrapper's DEFECT 1
# cure rule).
POLICY_FIELD = "prompt_policy_id"
REQUEST_FIELDS = ("schema_version", "tenant_id", "location_id", "launch_id",
                  "revision", "request_id", "page_id", "page_role",
                  "assigned_skill", "approval_ref", "input_hash", "brand_ref",
                  "brand_hash", "route_graph_ref", "route_graph_hash",
                  "offer_refs", "copy_profile", "allowed_write_target",
                  "test_only")
# The 17 page-result 1.0 fields, in shipped-schema order.
RESULT_FIELDS = ("schema_version", "tenant_id", "location_id", "launch_id",
                 "revision", "request_id", "input_hash", "page_id", "status",
                 "artifacts", "author_session", "reviewer_session",
                 "independent_review", "proof_class", "blockers",
                 "native_bindings_ref", "test_only")
ECHO_FIELDS = ("request_id", "input_hash", "page_id", "launch_id",
               "revision", "tenant_id", "location_id", "test_only")

DIFFERENCE_KINDS = ("reduced_scope", "lower_total_price",
                    "changed_payment_terms", "changed_access_terms")
NON_ONE_TIME_BILLING = ("trial", "recurring", "installment")
# The enrichment sidecar may carry ONLY these keys: difference_kind
# and rationale are the launch's recorded difference-table values
# (CR-S49-005 item 3 sourcing condition); entry_guard_ref names the
# staged journey entry evidence record (item 2).
SIDECAR_KEYS = frozenset({"difference_kind", "rationale", "entry_guard_ref"})
# The journey file is an S49-staged evidence summary carrying exactly
# the journey facts the entry guard consumes; anything else is the
# evidence record the sidecar's entry_guard_ref names, not this file.
JOURNEY_KEYS = frozenset({"main_purchased_verified", "u1_event",
                          "u1_accepted"})

STATUS_CAP = "locally_verified"
PROOF_CAP = "L2"
BLOCKERS = (
    "D1-ACTION-OUTCOME-UNVERIFIED: no verified native action outcome "
    "exists for this run; the shared action component was not executed "
    "by this local validation run, the pending-lockout binding point "
    "is UNMAPPED (D1-ADAPTER-PENDING-LOCKOUT-UNMAPPED, CR-S81-001) "
    "and CR-S81-006 is not confirmed, so this result attests local "
    "contract validation only",
    "D1-INSTALL-READBACK-NOT-RECORDED: the install leg is plan-only "
    "(executes_install False) and binding read-back is required but "
    "not recorded for extra offers; no verified native binding is "
    "claimed",
)


class WrapperError(ValueError):
    """Fail-closed refusal. `problems` names every fact that cannot be
    honestly supplied; the wrapper never guesses one."""

    def __init__(self, problems: List[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_json(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WrapperError([f"{what}: cannot load {path}: {exc}"])
    except ValueError as exc:
        raise WrapperError([f"{what}: {path} is not valid JSON: {exc}"])


def _read_bytes(path: Path, what: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise WrapperError([f"{what}: cannot read {path}: {exc}"])


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


# ---------------------------------------------------------------------------
# Stdlib JSON-Schema subset check (the vendored packet validator approach
# of the landing bridge, extended with maximum, minItems/maxItems, allOf
# and if/then/else, which the landed Skill 81 schemas use). No third-party
# jsonschema dependency and no silent skip, anywhere.
# ---------------------------------------------------------------------------
def _schema_violations(instance: Any, schema: Dict[str, Any],
                       path: str = "$") -> List[str]:
    problems: List[str] = []

    def type_ok(value: Any, want: str) -> bool:
        if want == "string":
            return isinstance(value, str)
        if want == "boolean":
            return isinstance(value, bool)
        if want == "null":
            return value is None
        if want == "array":
            return isinstance(value, list)
        if want == "object":
            return isinstance(value, dict)
        if want == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if want == "number":
            return isinstance(value, (int, float)) \
                and not isinstance(value, bool)
        return True

    if not isinstance(schema, dict):
        return problems
    for sub in schema.get("allOf") or []:
        if isinstance(sub, dict):
            problems.extend(_schema_violations(instance, sub, path))
    if isinstance(schema.get("if"), dict):
        if not _schema_violations(instance, schema["if"], path):
            branch = schema.get("then")
        else:
            branch = schema.get("else")
        if isinstance(branch, dict):
            problems.extend(_schema_violations(instance, branch, path))
    want = schema.get("type")
    if want is not None:
        wants = want if isinstance(want, list) else [want]
        if not any(type_ok(instance, w) for w in wants):
            problems.append(f"{path}: expected type {' or '.join(wants)}")
            return problems
    if "const" in schema and instance != schema["const"]:
        problems.append(f"{path}: must be {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        problems.append(f"{path}: {instance!r} is not one of "
                        f"{schema['enum']}")
    if isinstance(instance, str):
        if schema.get("minLength") is not None \
                and len(instance) < schema["minLength"]:
            problems.append(f"{path}: shorter than minLength "
                            f"{schema['minLength']}")
        if schema.get("pattern") \
                and not re.search(schema["pattern"], instance):
            problems.append(f"{path}: does not match pattern "
                            f"{schema['pattern']!r}")
    if isinstance(instance, (int, float)) \
            and not isinstance(instance, bool):
        if schema.get("minimum") is not None \
                and instance < schema["minimum"]:
            problems.append(f"{path}: below minimum {schema['minimum']}")
        if schema.get("maximum") is not None \
                and instance > schema["maximum"]:
            problems.append(f"{path}: above maximum {schema['maximum']}")
    if isinstance(instance, list):
        if schema.get("minItems") is not None \
                and len(instance) < schema["minItems"]:
            problems.append(f"{path}: fewer than minItems "
                            f"{schema['minItems']}")
        if schema.get("maxItems") is not None \
                and len(instance) > schema["maxItems"]:
            problems.append(f"{path}: more than maxItems "
                            f"{schema['maxItems']}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(instance):
                problems.extend(_schema_violations(
                    item, item_schema, f"{path}[{i}]"))
    if isinstance(instance, dict):
        for key in schema.get("required", []) or []:
            if key not in instance:
                problems.append(f"{path}: missing required field {key!r}")
        props = schema.get("properties", {}) or {}
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in props:
                    problems.append(f"{path}: additional property "
                                    f"{key!r} is not allowed")
        for key, subschema in props.items():
            if key in instance and isinstance(subschema, dict):
                problems.extend(_schema_violations(
                    instance[key], subschema, f"{path}.{key}"))
    return problems


# ---------------------------------------------------------------------------
# Skill 81 consumer bytes: loaded from --skill81-root, hash-pinned.
# ---------------------------------------------------------------------------
def _load_skill81(root: Path):
    wanted = {
        "validators/validate_downsell.py": PIN_VALIDATE_DOWNSELL,
        "schemas/downsell-request.schema.json": PIN_REQUEST_SCHEMA,
        "schemas/downsell-result-extension.schema.json":
            PIN_EXTENSION_SCHEMA,
    }
    raws: Dict[str, bytes] = {}
    for rel, pin in wanted.items():
        target = root / rel
        raw = _read_bytes(target, f"skill81 {rel}")
        digest = _sha256(raw)
        if digest != pin:
            raise WrapperError([
                f"skill81 {rel}: bytes at {target} hash to {digest}, "
                f"not the pinned {pin} recorded when the landed bytes "
                "were copied verbatim from main; the wrapper runs only "
                "the pinned consumer bytes"])
        raws[rel] = raw
    spec = importlib.util.spec_from_file_location(
        "validate_downsell", root / "validators" / "validate_downsell.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    request_schema = json.loads(
        raws["schemas/downsell-request.schema.json"].decode("utf-8"))
    extension_schema = json.loads(
        raws["schemas/downsell-result-extension.schema.json"]
        .decode("utf-8"))
    return mod, request_schema, extension_schema


# ---------------------------------------------------------------------------
# Receipt validation: collect_launch_receipts.validate_result when the
# shipped module is importable (the landing bridge's loader), else the
# vendored page-result 1.0 schema plus the exact echo and the
# independent-review cross-check. The fallback is announced on stderr
# and named in the run summary; it is never silent (review D2 rule).
# ---------------------------------------------------------------------------
def _load_receipts_validator():
    here = Path(__file__).resolve()
    candidates = []
    env = os.environ.get("S49_SCRIPTS_DIR")
    if env:
        candidates.append(Path(env))
    candidates.append(here.parent)
    for parent in here.parents:
        candidates.append(parent / "49-signature-funnel" / "scripts")
    for cand in candidates:
        target = cand / "collect_launch_receipts.py"
        if target.is_file():
            try:
                spec = importlib.util.spec_from_file_location(
                    "collect_launch_receipts", target)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod.validate_result, None
            except Exception as exc:
                return None, f"{target} could not be imported ({exc})"
    return None, ("no collect_launch_receipts.py found under "
                  "S49_SCRIPTS_DIR, beside this wrapper, or the sibling "
                  "dispatch tree")


def _validate_result(result: Dict[str, Any], request: Mapping[str, Any]):
    """Validate the assembled page-result before placement. Returns the
    validation mode that actually ran; raises WrapperError on any
    failure, so an invalid result is never placed."""
    schema_path = Path(__file__).resolve().parent / "vendor" \
        / "page-result.schema.json"
    schema = _load_json(schema_path, "vendored page-result schema")
    problems = _schema_violations(result, schema)
    if problems:
        raise WrapperError(
            ["page-result: the assembled result violates the "
             "page-result 1.0 schema: " + "; ".join(problems)])
    validator, unavailable = _load_receipts_validator()
    if validator is not None:
        fails = validator(result, dict(request))
        if fails:
            raise WrapperError(
                ["page-result: the assembled result failed S49 receipt "
                 "validation (collect_launch_receipts.validate_result): "
                 + "; ".join(fails)])
        return "collect_launch_receipts.validate_result"
    print("downsell wrapper: WARNING: collect_launch_receipts."
          "validate_result is unavailable (" + str(unavailable) + "); "
          "validating the assembled page-result with the vendored "
          "page-result 1.0 schema plus the exact echo and "
          "independent-review cross-checks instead. This is a "
          "downgrade and it is announced, not silent.", file=sys.stderr)
    for f in ECHO_FIELDS:
        if result.get(f) != request.get(f):
            raise WrapperError(
                [f"page-result: does not echo its request on {f}: "
                 f"{result.get(f)!r} != {request.get(f)!r}"])
    if result.get("independent_review"):
        reviewer = result.get("reviewer_session")
        if not reviewer:
            raise WrapperError(
                ["page-result: independent_review claimed with no "
                 "reviewer session (vendored-schema fallback enforces "
                 "the same rule as collect_launch_receipts."
                 "validate_result)"])
        if reviewer == result.get("author_session"):
            raise WrapperError(
                ["page-result: independent_review claimed but "
                 "reviewer == author (vendored-schema fallback enforces "
                 "the same rule as collect_launch_receipts."
                 "validate_result)"])
    return "vendored_schema_fallback"


# ---------------------------------------------------------------------------
# Enrichment: the Skill 81 request built from the S49 request. Every
# field has a named source or the run fails closed naming it.
# ---------------------------------------------------------------------------
def _select_offer(launch: Mapping[str, Any], slot: str,
                  problems: List[str]) -> Optional[Dict[str, Any]]:
    candidates = [o for o in launch.get("offers") or []
                  if isinstance(o, dict) and o.get("slot") == slot]
    if len(candidates) != 1:
        problems.append(
            f"offer slot {slot}: launch record carries "
            f"{len(candidates)} offer(s) for this slot; exactly one is "
            "required")
        return None
    return candidates[0]


def _approved_price(offer: Mapping[str, Any], label: str,
                    problems: List[str]) -> Optional[Dict[str, Any]]:
    prices = [p for p in offer.get("prices") or [] if isinstance(p, dict)]
    approved = [p for p in prices
                if p.get("approval_status") in ("approved", "provided")]
    if len(approved) == 1:
        return approved[0]
    if len(prices) == 1:
        return prices[0]
    problems.append(
        f"{label}: offer {offer.get('offer_id')!r} carries "
        f"{len(prices)} price choices ({len(approved)} approved); the "
        "wrapper never guesses which price is the approved one")
    return None


def _extras_flag(launch: Mapping[str, Any], key: str) -> Any:
    extras = launch.get("extras")
    return extras.get(key) if isinstance(extras, dict) else None


def enrich(request: Mapping[str, Any], launch: Mapping[str, Any],
           graph: Mapping[str, Any], graph_bytes: bytes,
           copy_doc: Any, journey: Mapping[str, Any],
           sidecar: Mapping[str, Any]) -> Dict[str, Any]:
    """Build the Skill 81 downsell-request, or raise WrapperError
    naming every field that has no honest source."""
    problems: List[str] = []

    # Input shape (adoption map 1.5 dual-accept): page-request 1.0,
    # or page-request 1.1 carrying the prompt-policy citation. The
    # pair rule binds version and field: a 1.1 request must carry a
    # non-empty prompt_policy_id; a 1.0 request must not carry the
    # field at all. Any other key fails closed by name.
    for key in sorted(set(request) - set(REQUEST_FIELDS)
                      - {POLICY_FIELD}):
        problems.append(
            f"request: field {key!r} is not part of page-request 1.0 "
            "or 1.1; this wrapper consumes 1.0-shaped requests and "
            "1.1 requests carrying the prompt-policy citation only "
            "(refused, never forwarded)")
    if request.get("page_role") != ROLE:
        problems.append(f"page_role: request page_role "
                        f"{request.get('page_role')!r} does not match "
                        f"this wrapper's fixed role {ROLE!r}")
    if request.get("assigned_skill") != SKILL:
        problems.append(f"assigned_skill: request assigns skill "
                        f"{request.get('assigned_skill')!r}, not 81")
    version = request.get("schema_version")
    if version == "1.1":
        if POLICY_FIELD not in request:
            problems.append(
                "prompt_policy_id: a 1.1 request must carry "
                "prompt_policy_id (the 1.1 label exists to carry "
                "the field); the request carries none (refused)")
        elif not (isinstance(request[POLICY_FIELD], str)
                  and request[POLICY_FIELD].strip()):
            problems.append(
                f"prompt_policy_id: value "
                f"{request[POLICY_FIELD]!r} is not a non-empty "
                "string; the citation is the minted policy id as a "
                "plain string (refused)")
    elif version == "1.0":
        if POLICY_FIELD in request:
            problems.append(
                "prompt_policy_id: prompt_policy_id requires "
                "request schema_version 1.1 (the 1.0 schema "
                "forbids the field); the request is stamped 1.0 "
                "(refused)")
    else:
        problems.append(f"schema_version: request schema_version "
                        f"{version!r} is not 1.0 or 1.1")

    # The launch record must be the record this request approves.
    if isinstance(launch, dict):
        for field in ("tenant_id", "location_id", "launch_id",
                      "revision"):
            if launch.get(field) != request.get(field):
                problems.append(
                    f"launch record: {field} is {launch.get(field)!r} "
                    f"but the page-request carries "
                    f"{request.get(field)!r}; the wrapper enriches "
                    "only from the record the request approves")
    else:
        problems.append("launch record: the document is not a JSON "
                        "object")
        launch = {}

    # Routes are derived only from the hash-verified graph.
    digest = _sha256(graph_bytes)
    if digest != request.get("route_graph_hash"):
        problems.append(
            f"route graph: file hash {digest} does not match the "
            f"request's route_graph_hash "
            f"{request.get('route_graph_hash')!r}; routes are never "
            "derived from an unverified graph")
    if launch.get("route_graph_hash") not in (None,
                                              request.get(
                                                  "route_graph_hash")):
        problems.append(
            f"route graph: launch record route_graph_hash "
            f"{launch.get('route_graph_hash')!r} disagrees with the "
            f"request's {request.get('route_graph_hash')!r}")

    # Sidecar discipline: whitelisted keys only.
    for key in sorted(set(sidecar) - SIDECAR_KEYS):
        problems.append(
            f"enrichment sidecar: unknown key {key!r}; the sidecar may "
            "only carry difference_kind, rationale and entry_guard_ref "
            "(the recorded difference-table values and the entry "
            "evidence name, CR-S49-005 items 2 and 3)")
    kind = sidecar.get("difference_kind")
    if kind not in DIFFERENCE_KINDS:
        problems.append(
            f"difference_kind: sidecar value {kind!r} is absent or "
            f"not one of {list(DIFFERENCE_KINDS)}; the value must be "
            "the launch's recorded difference-table value (spec 11 "
            "section 4), never authored at dispatch time")
    rationale = sidecar.get("rationale")
    if _blank(rationale):
        problems.append(
            "rationale: the sidecar carries no rationale; the "
            "difference table records rationale as REQUIRED (spec 11 "
            "section 4) and validate_offer_difference refuses its "
            "absence")
    entry_guard_ref = sidecar.get("entry_guard_ref")
    if _blank(entry_guard_ref):
        problems.append(
            "entry_guard_ref: the sidecar names no staged journey "
            "entry evidence record; the ref names the evidence record "
            "the entry guard consumes (CR-S49-005 item 2) and the "
            "wrapper never invents it")

    # Journey facts: exactly the three the guard consumes.
    for key in sorted(set(journey) - JOURNEY_KEYS):
        problems.append(
            f"journey: unknown key {key!r}; the staged journey file "
            "carries exactly main_purchased_verified, u1_event and "
            "u1_accepted")
    for key in ("main_purchased_verified", "u1_accepted"):
        if not isinstance(journey.get(key), bool):
            problems.append(
                f"journey.{key}: must be a boolean, got "
                f"{journey.get(key)!r}")
    if "u1_event" not in journey or not (
            journey.get("u1_event") is None
            or isinstance(journey.get("u1_event"), str)):
        problems.append(
            f"journey.u1_event: must be a string or null, got "
            f"{journey.get('u1_event')!r}; only the literal "
            "'explicit_decline' qualifies as a decline, and a payment "
            "failure or pending state never does")

    # Offers by slot, under the record's own enablement flags.
    u1 = _select_offer(launch, "upsell_1", problems)
    d1 = _select_offer(launch, "downsell_1", problems)
    if _extras_flag(launch, "upsell_1") is not True:
        problems.append(
            "declined_u1_offer_ref: upsell_1 is not enabled in the "
            "launch record's extras; downsell_1 presupposes an enabled "
            "upsell_1 (route law: D1 cannot remain enabled when U1 is "
            "disabled)")
    if _extras_flag(launch, "downsell_1") is not True:
        problems.append(
            "downsell_offer_ref: downsell_1 is not enabled in the "
            "launch record's extras; dispatch does not wire a disabled "
            "role")

    native_product_id = None
    price = None
    if d1 is not None:
        native_product_id = d1.get("native_product_id")
        if _blank(native_product_id):
            problems.append(
                "native_product_id: the record's D1 offer carries no "
                "native_product_id; the wrapper never emits a null "
                "native id at dispatch (CR-S49-005 item 4), because "
                "the install leg requires a matching non-null binding")
        price = _approved_price(d1, "native_price_id", problems)
        if price is not None and _blank(price.get("native_price_id")):
            problems.append(
                "native_price_id: the record D1 offer's approved "
                "price row carries no native_price_id; the wrapper "
                "never emits a null native id at dispatch "
                "(CR-S49-005 item 4)")

    # Success route: the D1 node's paid edge in the verified graph.
    role_of = {}
    for node in graph.get("nodes") or []:
        if isinstance(node, dict):
            role_of[node.get("page_id")] = node.get("role")
    page_id = request.get("page_id")
    success_route = None
    if role_of.get(page_id) != ROLE:
        problems.append(
            f"success_route: the verified route graph has no "
            f"downsell_1 node with page_id {page_id!r} (the graph "
            f"carries role {role_of.get(page_id)!r} for it)")
    else:
        paid_targets = [e.get("to") for e in graph.get("edges") or []
                        if isinstance(e, dict)
                        and e.get("from") == page_id
                        and e.get("event") == "payment_succeeded"]
        if len(paid_targets) != 1:
            problems.append(
                f"success_route: the verified route graph carries "
                f"{len(paid_targets)} payment_succeeded edge(s) from "
                f"the D1 node {page_id!r}; exactly one is required")
        else:
            target_role = role_of.get(paid_targets[0])
            if target_role == "upsell_2":
                success_route = "upsell_2"
            elif target_role == "thank_you":
                success_route = "thank_you"
            else:
                problems.append(
                    f"success_route: the D1 paid edge lands on role "
                    f"{target_role!r}; route law sends a paid D1 to "
                    "the canonical upsell_2 or the final thank_you "
                    "only")

    if problems:
        raise WrapperError(problems)

    # Every request field rides through verbatim except offer_refs;
    # on a 1.1 request that carries schema_version "1.1" and the
    # prompt_policy_id citation into the enriched request, which is
    # the Skill 81 contract document the citation lives on (the
    # base page-result 1.0 carries no policy field; the citation is
    # read at the receipt and registry layer, map section 4).
    enriched = {k: v for k, v in request.items() if k != "offer_refs"}
    enriched["copy_profile"] = D1_COPY_PROFILE
    enriched["declined_u1_offer_ref"] = u1["offer_id"]
    enriched["downsell_offer_ref"] = d1["offer_id"]
    enriched["difference_kind"] = kind
    enriched["native_product_id"] = native_product_id
    enriched["native_price_id"] = price["native_price_id"]
    enriched["entry_guard_ref"] = entry_guard_ref
    enriched["success_route"] = success_route
    enriched["decline_route"] = DECLINE_ROUTE
    page = _page_object(copy_doc)
    scarcity = page.get("scarcity_evidence_ref") \
        if isinstance(page, dict) else None
    if _blank(scarcity) and isinstance(copy_doc, dict):
        scarcity = copy_doc.get("scarcity_evidence_ref")
    enriched["scarcity_evidence_ref"] = \
        scarcity if not _blank(scarcity) else None
    return enriched


def _page_object(copy_doc: Any) -> Dict[str, Any]:
    """The staged copy document is the page object itself, or the
    fixture transport shape carrying it under "page"."""
    if isinstance(copy_doc, dict) and isinstance(copy_doc.get("page"),
                                                 dict):
        return copy_doc["page"]
    return copy_doc if isinstance(copy_doc, dict) else {}


def _record_amounts(launch: Mapping[str, Any]) -> List[int]:
    """Every approved price figure in the record: each price entry's
    amount plus every schedule row's amount, across all offers."""
    amounts = set()
    for offer in launch.get("offers") or []:
        if not isinstance(offer, dict):
            continue
        for price in offer.get("prices") or []:
            if not isinstance(price, dict):
                continue
            amount = price.get("amount_minor")
            if isinstance(amount, int) and not isinstance(amount, bool):
                amounts.add(amount)
            for row in price.get("schedule") or []:
                if isinstance(row, dict):
                    row_amount = row.get("amount_minor")
                    if isinstance(row_amount, int) \
                            and not isinstance(row_amount, bool):
                        amounts.add(row_amount)
    return sorted(amounts)


def guard_state(launch: Mapping[str, Any],
                journey: Mapping[str, Any]) -> Dict[str, Any]:
    """The entry-guard state: journey facts from the journey file,
    enablement facts from the launch record's extras (launch facts
    under route law, never from the named evidence record)."""
    return {
        "main_purchased_verified": journey.get("main_purchased_verified"),
        "u1_event": journey.get("u1_event"),
        "u1_enabled": _extras_flag(launch, "upsell_1") is True,
        "d1_enabled": _extras_flag(launch, "downsell_1") is True,
        "u2_enabled": _extras_flag(launch, "upsell_2") is True,
        "u1_accepted": journey.get("u1_accepted"),
    }


def canonical_u2_page_id(graph: Mapping[str, Any],
                         enriched: Mapping[str, Any]) -> Optional[str]:
    if enriched.get("success_route") != "upsell_2":
        return None
    # The canonical U2 is the target of the D1 node's own paid edge.
    role_of = {n.get("page_id"): n.get("role")
               for n in graph.get("nodes") or [] if isinstance(n, dict)}
    for edge in graph.get("edges") or []:
        if isinstance(edge, dict) \
                and edge.get("event") == "payment_succeeded" \
                and role_of.get(edge.get("to")) == "upsell_2":
            # Only the edge leaving a downsell_1 node names THIS
            # launch's canonical U2 for the D1 result; other paid
            # edges into U2 (from U1) name the same node by route law.
            if role_of.get(edge.get("from")) == ROLE:
                return edge.get("to")
    return None


# ---------------------------------------------------------------------------
# The wrapper run.
# ---------------------------------------------------------------------------
def run(args) -> Dict[str, Any]:
    request_path = Path(args.request)
    result_path = Path(args.result)
    work_dir = request_path.resolve().parent

    request = _load_json(request_path, "page-request")
    if not isinstance(request, dict):
        raise WrapperError(["page-request: the document is not a "
                            "JSON object"])
    launch = _load_json(Path(args.launch), "launch record")
    graph_bytes = _read_bytes(Path(args.route_graph), "route graph")
    try:
        graph = json.loads(graph_bytes)
    except ValueError as exc:
        raise WrapperError([f"route graph: not valid JSON: {exc}"])
    if not isinstance(graph, dict):
        raise WrapperError(["route graph: the document is not a JSON "
                            "object"])
    copy_doc = _load_json(Path(args.copy), "copy document")
    journey = _load_json(Path(args.journey), "journey state")
    if not isinstance(journey, dict):
        raise WrapperError(["journey state: the document is not a "
                            "JSON object"])
    sidecar = _load_json(Path(args.enrichment), "enrichment sidecar")
    if not isinstance(sidecar, dict):
        raise WrapperError(["enrichment sidecar: the document is not "
                            "a JSON object"])
    vd, request_schema, extension_schema = _load_skill81(
        Path(args.skill81_root))

    enriched = enrich(request, launch, graph, graph_bytes, copy_doc,
                      journey, sidecar)
    enriched_path = work_dir / "downsell-request-enriched.json"
    enriched_path.write_text(
        json.dumps(enriched, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")

    # ---- Validation gauntlet (all fail closed, named codes) ----
    # 1. The enriched request against the landed request schema.
    violations = _schema_violations(enriched, request_schema)
    if violations:
        raise WrapperError(
            ["enriched request violates the landed downsell-request "
             "schema: " + v for v in violations])
    # 2. The entry guard over the computed state.
    codes = vd.check_entry_guard(guard_state(launch, journey))
    if codes:
        raise WrapperError(
            [f"entry guard: {c}" for c in codes])
    # 3. The staged page under validate_copy, its approved amounts set
    #    from the record's approved prices.
    page = copy.deepcopy(_page_object(copy_doc))
    page["approved_amounts_minor"] = _record_amounts(launch)
    codes = vd.validate_copy(page)
    if codes:
        raise WrapperError([f"page copy: {c}" for c in codes])
    # 4. The offer difference, sidecar values folded onto the record's
    #    D1 offer exactly as the validator's contract reads them.
    u1 = _select_offer(launch, "upsell_1", [])
    d1 = _select_offer(launch, "downsell_1", [])
    main_offer = _select_offer(launch, "main", [])
    d1_extended = copy.deepcopy(d1)
    d1_extended["difference_kind"] = sidecar["difference_kind"]
    d1_extended["rationale"] = sidecar["rationale"]
    codes = vd.validate_offer_difference(u1, d1_extended, main_offer)
    if codes:
        raise WrapperError([f"offer difference: {c}" for c in codes])
    # 5. Trial/recurring/installment D1 prices need the staged
    #    disclosure, cross-checked by validate_trial_disclosure.
    price = _approved_price(d1, "disclosure", [])
    billing = price.get("billing_type") if price else None
    if billing in NON_ONE_TIME_BILLING:
        disclosure_path = Path(args.disclosure) if args.disclosure \
            else work_dir / "disclosure-downsell_1.json"
        if not disclosure_path.is_file():
            raise WrapperError(
                [f"disclosure: D1 billing_type is {billing!r}, which "
                 f"requires a staged disclosure document, and none "
                 f"exists at {disclosure_path}; the wrapper never "
                 "invents disclosure terms"])
        disclosure = _load_json(disclosure_path, "disclosure document")
        codes = vd.validate_trial_disclosure(d1, disclosure)
        if codes:
            raise WrapperError([f"trial disclosure: {c}" for c in codes])

    # ---- Result assembly (translator pattern) ----
    extension_path = Path(args.extension) if args.extension \
        else work_dir / "extension-downsell_1.json"
    if not extension_path.is_file():
        raise WrapperError(
            [f"result extension: the S81-side run bundle stages no "
             f"result-extension document at {extension_path}; the "
             "base result is never assembled without the extension it "
             "carries"])
    extension_raw = _read_bytes(extension_path, "result extension")
    extension_doc = _load_json(extension_path, "result extension")
    wrapped = isinstance(extension_doc, dict) \
        and isinstance(extension_doc.get("downsell_result_extension"),
                       dict)
    ext = extension_doc["downsell_result_extension"] if wrapped \
        else extension_doc
    if not isinstance(ext, dict):
        raise WrapperError(["result extension: the document is not a "
                            "JSON object"])
    violations = _schema_violations(ext, extension_schema)
    if violations:
        raise WrapperError(
            ["result extension violates the landed downsell-result-"
             "extension schema: " + v for v in violations])
    u2_id = canonical_u2_page_id(graph, enriched)
    codes = vd.validate_result_extension(ext, u2_id)
    if codes:
        raise WrapperError([f"result extension: {c}" for c in codes])
    target = (ext.get("route_result") or {}).get("success_target")
    if target != enriched["success_route"]:
        raise WrapperError(
            [f"result extension: route_result.success_target "
             f"{target!r} contradicts the enriched request's "
             f"success_route {enriched['success_route']!r}; the "
             "request, derived from the compiled route graph, is the "
             "plan-side truth and the result field is an echo that "
             "must match it (CR-S49-005 item 5)"])
    # The wrapper's result-time disclosure cross-check (CR-S49-005
    # item 6; S81 does not claim it): the extension's due-now must
    # equal the record's approved D1 price.
    audit = ext.get("disclosure_audit") or {}
    due_now = audit.get("due_now_minor")
    approved_amount = price.get("amount_minor") if price else None
    if due_now is None:
        raise WrapperError(
            [f"disclosure cross-check: extension disclosure_audit."
             f"due_now_minor is null while the launch record carries "
             f"an approved D1 price of {approved_amount!r}; the "
             "wrapper's result-time equality check (CR-S49-005 item "
             "6) cannot be skipped"])
    if due_now != approved_amount:
        raise WrapperError(
            [f"disclosure cross-check: D1-RESULT-DISCLOSURE-DUE-NOW-"
             f"MISMATCH: extension disclosure_audit.due_now_minor "
             f"{due_now!r} != the launch record's approved D1 price "
             f"{approved_amount!r} (wrapper cross-check, CR-S49-005 "
             "item 6)"])

    # The extension travels verbatim beside the result, never inside
    # it: the bare extension object's own bytes when staged bare, the
    # extracted object when staged in the fixture transport shape.
    extension_out = result_path.resolve().parent \
        / "downsell-result-extension.json"
    if wrapped:
        extension_out.write_text(json.dumps(ext, indent=2) + "\n",
                                 encoding="utf-8")
    else:
        extension_out.write_bytes(extension_raw)
    artifacts = [
        {"path": str(Path(args.copy)),
         "sha256": _sha256(_read_bytes(Path(args.copy), "copy "
                                       "document"))},
        {"path": str(extension_out),
         "sha256": _sha256(extension_out.read_bytes())},
    ]

    author_session = args.author_session \
        or os.environ.get("SIGNATURE_LAUNCH_AUTHOR_SESSION") \
        or os.environ.get("OPENCLAW_SESSION_ID") \
        or "s49-downsell-wrapper"
    result = {
        "schema_version": "1.0",
        "tenant_id": request["tenant_id"],
        "location_id": request["location_id"],
        "launch_id": request["launch_id"],
        "revision": request["revision"],
        "request_id": request["request_id"],
        "input_hash": request["input_hash"],
        "page_id": request["page_id"],
        "status": STATUS_CAP,
        "artifacts": artifacts,
        "author_session": author_session,
        "reviewer_session": None,
        "independent_review": False,
        "proof_class": PROOF_CAP,
        "blockers": list(BLOCKERS),
        "native_bindings_ref": None,
        "test_only": request["test_only"],
    }
    projected = {f: result[f] for f in RESULT_FIELDS}
    mode = _validate_result(projected, request)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(projected, indent=2) + "\n",
                           encoding="utf-8")
    return {
        "role": ROLE,
        "request_id": request["request_id"],
        "result_path": str(result_path),
        "status": projected["status"],
        "proof_class": projected["proof_class"],
        "receipt_validation": mode,
        "enriched_request": str(enriched_path),
        "extension_artifact": str(extension_out),
        "blockers": projected["blockers"],
    }


def _remove_stale(result_path: Path) -> None:
    """A failed run leaves no result behind (selection wrapper
    behavior): neither the result nor its extension sibling may
    survive from an earlier run and be mistaken for this run's."""
    for target in (result_path,
                   result_path.resolve().parent
                   / "downsell-result-extension.json"):
        try:
            if target.is_file():
                target.unlink()
        except OSError:
            pass


class _WrapperArgumentParser(argparse.ArgumentParser):
    """ArgumentParser whose usage errors exit EXIT_USAGE (3): stock
    argparse exits 2, which a caller could not distinguish from a
    fail-closed refusal (the landing bridge's documented contract)."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def main(argv: Optional[List[str]] = None) -> int:
    ap = _WrapperArgumentParser(
        description="S49-08 wrapper: S49 page-request -> Skill 81 "
                    "downsell-request + validators -> page-result 1.0 "
                    "for the downsell_1 role.")
    ap.add_argument("--request", required=True,
                    help="S49 page-request JSON ({request})")
    ap.add_argument("--result", required=True,
                    help="page-result JSON to write ({result})")
    ap.add_argument("--launch", required=True,
                    help="launch record JSON ({work_dir}/launch.json)")
    ap.add_argument("--route-graph", required=True,
                    help="compiled route graph JSON "
                         "({work_dir}/route-graph.json)")
    ap.add_argument("--copy", required=True,
                    help="staged D1 page/copy document JSON "
                         "({work_dir}/copy-downsell_1.json)")
    ap.add_argument("--journey", required=True,
                    help="staged journey entry facts JSON "
                         "({work_dir}/journey-downsell_1.json)")
    ap.add_argument("--enrichment", required=True,
                    help="enrichment sidecar JSON "
                         "({work_dir}/enrichment-downsell_1.json)")
    ap.add_argument("--skill81-root", required=True,
                    help="path to the landed 81-signature-downsell "
                         "tree (validators + schemas, hash-pinned)")
    ap.add_argument("--extension",
                    help="staged result-extension document (default: "
                         "extension-downsell_1.json beside the request)")
    ap.add_argument("--disclosure",
                    help="staged trial/recurring disclosure document "
                         "(default: disclosure-downsell_1.json beside "
                         "the request; required for non-one-time D1 "
                         "billing)")
    ap.add_argument("--author-session",
                    help="the dispatch run's session identity (the "
                         "page-result author); falls back to "
                         "SIGNATURE_LAUNCH_AUTHOR_SESSION / "
                         "OPENCLAW_SESSION_ID, then a fixed wrapper "
                         "label")
    args = ap.parse_args(argv)
    try:
        summary = run(args)
    except WrapperError as exc:
        _remove_stale(Path(args.result))
        for problem in exc.problems:
            print(f"FAIL-CLOSED: {problem}", file=sys.stderr)
        return EXIT_FAILCLOSED
    except OSError as exc:
        _remove_stale(Path(args.result))
        print(f"FAIL-CLOSED: cannot complete the run: {exc}",
              file=sys.stderr)
        return EXIT_FAILCLOSED
    print(json.dumps(summary, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
