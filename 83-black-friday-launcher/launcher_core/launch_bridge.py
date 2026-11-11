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

import hashlib
import inspect
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.parse import urlsplit

import sys

_ROUTES_DIR = Path(__file__).resolve().parent.parent / "routes"
if str(_ROUTES_DIR) not in sys.path:
    sys.path.insert(0, str(_ROUTES_DIR))

import substrate  # noqa: E402

from . import (capability_check, delivery, image_plan, intake as intake_module,
               linked_delivery, page_designs, route)  # noqa: E402

LAUNCH_SCHEMA_VERSION = "1.2"
FIRST_ROLE = "landing"  # first when pages are built one at a time (side by side, Skill 49 starts every page together)


class BridgeError(Exception):
    """A dispatch that cannot start. Carries a stable code and a plain-English detail."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _offer(normalized: Dict[str, Any], offer: Dict[str, Any], by_role: Dict[str, str],
           grants: Optional[Mapping[str, List[str]]] = None) -> Dict[str, Any]:
    """The launch record offer. Billing, approval status, source kind and source ref come from the
    canonical offer the intake resolved in the client's answers file, never from a constant here."""
    canon = offer.get("canonical")
    if not canon:
        raise BridgeError("AF-LAUNCH-BRIDGE-PROVENANCE",
                          f"offer {offer['offer_id']!r} carries no answers-file provenance; run the intake "
                          "through intake.validate. Nothing was dispatched and nothing was spent.")
    grants = route.offer_entitlements(normalized) if grants is None else grants
    test_only = bool(normalized.get("test_only", True))
    excludes: List[str] = []
    if offer["role"] == "upsell_1" and "downsell_1" in by_role:
        excludes = [by_role["downsell_1"]]
    if offer["role"] == "downsell_1" and "upsell_1" in by_role:
        excludes = [by_role["upsell_1"]]
    level = offer.get("level") or {}
    included_in = list((offer.get("relationships") or {}).get("included_in", [])) if offer["role"] == "bump" else []
    return {
        "offer_id": offer["offer_id"],
        "slot": offer["role"],
        "display_name": offer["name"],
        "deliverables": list(level.get("deliverables") or canon.get("deliverables") or []),
        "exclusions": list(canon["exclusions"]),
        "entitlement_ids": list(grants[offer["offer_id"]]),
        "requires": route.offer_requires(offer),
        "excludes": excludes,
        "native_product_id": canon["native_product_id"],
        "prices": [{**p, "price_choice_id": f"{offer['offer_id']}-{p['currency']}"} for p in canon["prices"]],
        "source_kind": canon["source_kind"],
        "source_ref": canon["source_ref"],
        "test_only": test_only,
        # the levels whose buyers hold this bump (route.offer_entitlements grants it); Skill 49's bump-subset rule skips them
        **({"relationships": {"included_in": included_in}} if included_in else {}),
    }


INTAKE_SNAPSHOT = "intake-at-dispatch.json"
STRUCTURE_PREFIX = "launcher-structure:"


def structure_refs(normalized: Dict[str, Any], inputs: Dict[str, Any], landing_pages: Sequence[str],
                   extra_pages: Sequence[str]) -> List[str]:
    """The structure choices a client approves, as record source_refs so the plan hash binds them.

    The plan hash covers every record key but status and plan_approval_ref, so a copy form, a landing
    page set, a design style or an extra page that changes after approval is a re-approval, never a
    silent edit. source_refs is the one free-form list the launch schema (closed) already allows."""
    return [f"{STRUCTURE_PREFIX}copy_profile={normalized['copy_profile']}",
            f"{STRUCTURE_PREFIX}landing_pages={','.join(sorted(set(landing_pages)))}",
            f"{STRUCTURE_PREFIX}design_style={inputs['design_style']}",
            f"{STRUCTURE_PREFIX}extra_pages={','.join(sorted(set(extra_pages)))}"]


def _https_url(url: Any) -> bool:
    parts = urlsplit(url) if isinstance(url, str) else None
    return bool(parts and parts.scheme == "https" and parts.hostname and not parts.username
                and not parts.password and not any(c.isspace() for c in url))


def delivery_bindings(normalized: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """entitlement id -> {delivery_kind, delivery_url}, from the client's own delivery answer.

    The kind comes from the answered ``access_delivery`` (launcher_core/delivery.py):
    "send access after purchase" binds ``access``, "nothing to deliver" binds
    ``schedule_included_service`` — a person follows up by hand. With no answer the
    record is exactly what it has always been: ``access`` plus each offer's
    owner-confirmed https destination, all or none.

    All or none is kept for the access case: an intake that states no destination
    for any offer yields no bindings (absence is the record's one encoding of "no
    bindings"); one that states some but not all is refused, because a buyer of the
    unbound item would read "being prepared" with no link. A human-delivered
    service needs no per-offer destination, so its absence is recorded, not refused.
    """
    try:
        decision = delivery.decide(normalized)
    except delivery.DeliveryError as exc:
        raise BridgeError("AF-LAUNCH-BRIDGE-DELIVERY",
                          f"{exc.detail}. Nothing was dispatched and nothing was spent.") from exc
    offers = normalized["offers"]
    if decision["state"] != "absent":
        try:
            planned = delivery.plan(normalized)
            out = delivery.bindings(planned)
        except delivery.DeliveryError as exc:
            raise BridgeError("AF-LAUNCH-BRIDGE-DELIVERY",
                              f"{exc.detail}. Nothing was dispatched and nothing was spent.") from exc
        if decision["kind"] == delivery.KIND_ACCESS:
            unbound = [e["offer_id"] for e in planned["offers"] if e["delivery_url"] is None]
            if unbound:
                raise BridgeError(
                    "AF-LAUNCH-BRIDGE-DELIVERY",
                    f"no access destination for {', '.join(unbound)}: the client asked for access "
                    "after purchase, so every offer needs the https address where its buyer gets it. "
                    "Nothing was dispatched and nothing was spent.")
        return out
    stated = [o for o in offers if o.get("delivery") is not None]
    if not stated:
        return {}
    missing = [o["offer_id"] for o in offers if o.get("delivery") is None]
    if missing:
        raise BridgeError("AF-LAUNCH-BRIDGE-DELIVERY",
                          f"no delivery destination for {', '.join(missing)}: every offer needs the https "
                          "address where its buyer gets access. Nothing was dispatched and nothing was spent.")
    out: Dict[str, Dict[str, Any]] = {}
    for o in stated:
        d = o["delivery"]
        if not isinstance(d, dict) or d.get("owner_confirmed") is not True or not _https_url(d.get("destination")):
            raise BridgeError("AF-LAUNCH-BRIDGE-DELIVERY",
                              f"the delivery destination for {o['offer_id']} must be an https address the "
                              "owner confirmed. Nothing was dispatched and nothing was spent.")
        out[o["offer_id"].lower()] = {"delivery_kind": decision["kind"], "delivery_url": d["destination"]}
    return out


def to_launch_record(normalized: Dict[str, Any], graph: Dict[str, Any],
                     inputs: Dict[str, Any], *, landing_pages: Optional[Sequence[str]] = None,
                     extra_pages: Sequence[str] = ()) -> Dict[str, Any]:
    """The Skill 49 launch record for a validated intake. Schema-valid; proven by check_launch_record.

    landing_pages and extra_pages are the client's page choices; without landing_pages the set Skill 49
    recommends is recorded. Either way the set, the copy form and the design style are in the record, so
    the approval hash covers them."""
    roles = {o["role"] for o in normalized["offers"]}
    by_role: Dict[str, str] = {o["role"]: o["offer_id"] for o in normalized["offers"]
                               if o["role"] in ("upsell_1", "downsell_1")}
    compiler = substrate.compiler()
    grants = route.offer_entitlements(normalized)
    offers = [_offer(normalized, o, by_role, grants) for o in normalized["offers"]]
    launch_id, revision = normalized["launch_id"], normalized["revision"]
    launch = {
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
        "source_refs": sorted({o["source_ref"] for o in offers}),
        "test_only": bool(normalized.get("test_only", True)),
    }
    bindings = delivery_bindings(normalized)
    if bindings:
        launch["delivery_bindings"] = bindings
    planned = list(landing_pages) if landing_pages else substrate.dispatch().pset.recommended_landing_pages(launch)
    launch["source_refs"] += structure_refs(normalized, inputs, planned, extra_pages)
    return launch


def check_launch_record(launch: Dict[str, Any]) -> List[str]:
    """Skill 49's own validator's verdict on the record. Empty list means schema- and domain-valid."""
    return list(substrate.dispatch().vlp.validate_launch(launch))


def plan_document_hash(launch: Dict[str, Any]) -> str:
    """Skill 49's own hash of the record: the one value an approval binds."""
    return substrate.dispatch().vlp.plan_document_hash(launch)


def resolve_launch(normalized: Dict[str, Any], graph: Dict[str, Any], *,
                   landing_pages: Optional[Sequence[str]] = None,
                   extra_pages: Sequence[str] = ()) -> tuple:
    """(image inputs, to_confirm, launch record) with the paid budget verified against the plan's OWN hash.

    F20: the paid image resolver needs the plan hash, and the plan hash is computed from the record that
    carries the resolved style and provider, so resolving the paid plan first is circular. The record is
    therefore built from the plan-shape inputs (style and provider only), hashed, and the spend is then
    verified against that hash. The final record is rebuilt from the verified inputs and must hash
    identically: a resolution that moved the hash would mean the client approved a different plan.
    """
    test_only = bool(normalized.get("test_only", True))
    shape = image_plan.plan_shape(normalized.get("image_plan"), test_only=test_only)
    provisional = to_launch_record(normalized, graph, shape,
                                  landing_pages=landing_pages, extra_pages=extra_pages)
    approved_hash = plan_document_hash(provisional)
    inputs, to_confirm = image_plan.resolve(normalized.get("image_plan"), test_only=test_only,
                                            plan_hash=approved_hash)
    launch = to_launch_record(normalized, graph, inputs,
                              landing_pages=landing_pages, extra_pages=extra_pages)
    if plan_document_hash(launch) != approved_hash:
        raise BridgeError("AF-LAUNCH-PLAN-HASH-UNSTABLE",
                          "resolving the picture plan changed the plan hash, so an approval would bind a "
                          "plan the client never saw. Nothing was dispatched and nothing was spent.")
    return inputs, to_confirm, launch


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


# Issue 57 (M5): the carrier for a page piece's ``stage_state``. Skill 71 writes the closed-stage record of
# every page run at <page run>/private/state.json; page_designs.load_stage_state reads a copy of it that rides
# in the package. Nothing wrote that copy, so every client package was refused. This is the writer: the copy
# is laid down beside the piece (pieces/<slot>.stage-state.json) with its sha256 recorded on the piece, and
# package._validate_piece / page_designs refuse a piece whose copy does not verify or whose stages never closed.
STAGE_STATE_REL = Path("private") / "state.json"
STAGE_STATE_SUFFIX = ".stage-state.json"


def landing_run_roots(dispatch_root: Optional[Path]) -> List[Path]:
    """The landing bridge's run folder(s), from the config the dispatch wrote beside its run. The bridge lists
    its files relative to that folder (an opt-in run's carry its folder name, so they resolve from its parent)."""
    if dispatch_root is None:
        return []
    try:
        landing = json.loads((Path(dispatch_root) / "dispatch" / "landing-bridge.json")
                             .read_text(encoding="utf-8")).get("landing")
    except (OSError, ValueError, AttributeError):
        return []
    if not isinstance(landing, dict) or not landing.get("run_dir"):
        return []
    roots = [Path(landing["run_dir"])]
    opt_in = landing.get("opt_in")
    if isinstance(opt_in, dict) and opt_in.get("run_dir"):
        roots.append(Path(opt_in["run_dir"]).parent)
    return roots


def stage_state_bases(run_dir: Path) -> List[Path]:
    """Where a piece's relative artifact paths resolve: the launch run, its dispatch folder, the landing runs."""
    run_dir = Path(run_dir)
    return [run_dir, run_dir / "dispatch", *landing_run_roots(run_dir)]


def _page_run_dir(piece: Dict[str, Any], bases: Sequence[Path]) -> Optional[Path]:
    """The Skill 71 page run that made this piece's files: the nearest folder above one of its design files
    that holds private/state.json. None when no file resolves into a stage_gate run (a fixture, a stub)."""
    arts = [a for a in piece.get("artifacts") or [] if isinstance(a, dict) and a.get("path")]
    for art in [a for a in arts if page_designs.classify(str(a["path"]))] or arts:
        raw = Path(str(art["path"]))
        for found in ([raw] if raw.is_absolute() else [Path(b) / raw for b in bases]):
            if not found.is_file():
                continue
            for parent in found.resolve().parents:
                if (parent / STAGE_STATE_REL).is_file():
                    return parent
    return None


def attach_stage_state(piece: Dict[str, Any], slot: str, run_dir: Path, bases: Sequence[Path]) -> bool:
    """Copy the page run's private/state.json to <run_dir>/pieces/<slot>.stage-state.json and record
    {path, sha256} on the piece. False (the piece is left as it was) when the piece names no stage_gate run."""
    page_run = _page_run_dir(piece, bases)
    if page_run is None:
        return False
    data = (page_run / STAGE_STATE_REL).read_bytes()
    rel = f"pieces/{slot}{STAGE_STATE_SUFFIX}"
    dest = Path(run_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    piece["stage_state"] = {"path": rel, "sha256": hashlib.sha256(data).hexdigest()}
    return True


def _carry_stage_state(piece_path: Path, slot: str, out_dir: Path, bases: Sequence[Path]) -> None:
    """Add the stage_state carrier to a piece file that was copied from the dispatch's stored result."""
    try:
        piece = json.loads(piece_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return  # package.assemble names an unreadable piece
    if isinstance(piece, dict) and attach_stage_state(piece, slot, out_dir, bases):
        piece_path.write_text(json.dumps(piece, indent=2) + "\n", encoding="utf-8")


def refresh_stage_states(run_dir: Path) -> List[str]:
    """Re-copy every piece's stage_gate state after a later stage closed (final-mockups closes AFTER dispatch,
    so the copy made at dispatch is stale by then). Returns the slots refreshed."""
    run_dir = Path(run_dir)
    bases, done = stage_state_bases(run_dir), []
    for path in sorted((run_dir / "pieces").glob("*.json")):
        if path.name.endswith(STAGE_STATE_SUFFIX):
            continue
        try:
            piece = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(piece, dict) and attach_stage_state(piece, path.stem, run_dir, bases):
            path.write_text(json.dumps(piece, indent=2) + "\n", encoding="utf-8")
            done.append(path.stem)
    return done


def _bind_approval(launch: Dict[str, Any], normalized: Dict[str, Any], approval: Any) -> None:
    """Take the approval ref from the verified --approval record, never from the intake.

    The hash the client approved is the record's own plan hash (the dispatch gate checks the record's
    subject_hash against it). A live intake that names a different approval is refused; a test-only
    intake carries a placeholder, which is never an approval. A missing or malformed record is left for
    Skill 49's gate to refuse by name."""
    if not isinstance(approval, dict) or not approval.get("approval_id"):
        return
    ref, plan_hash = approval["approval_id"], substrate.dispatch().vlp.plan_document_hash(launch)
    asked = normalized["approval"]
    if not normalized.get("test_only", True) and (asked["ref"], asked["hash"]) != (ref, plan_hash):
        raise BridgeError("AF-LAUNCH-BRIDGE-APPROVAL",
                          "the intake names an approval that is not the one on record for this plan "
                          f"(record {ref!r}, plan hash {plan_hash[:8]}). Nothing was dispatched and nothing "
                          "was spent.")
    launch["plan_approval_ref"] = ref


def _bridge_config_path(adapters_config: Optional[Dict[str, Any]],
                        adapter_inputs: Optional[Dict[str, Any]]) -> Optional[str]:
    if adapter_inputs and adapter_inputs.get("bridge_config"):
        return str(adapter_inputs["bridge_config"])
    command = ((adapters_config or {}).get("adapters", {}).get("landing") or {}).get("command") or []
    flag = "--bridge-config"
    return str(command[command.index(flag) + 1]) if flag in command[:-1] else None


def _check_copy_form(normalized: Dict[str, Any], adapters_config: Optional[Dict[str, Any]],
                     adapter_inputs: Optional[Dict[str, Any]]) -> None:
    """Refuse a landing page built in a different copy form than the client approved.

    The approved copy_profile (Standard or Long-Form) is in the plan hash; the landing bridge config
    carries its own page_version. When they disagree the sales page would be a form the client never
    approved and every later check would still pass, so the run stops here. The opt-in page is
    Long-Form only, so a config that adds it needs Long-Form too."""
    path = _bridge_config_path(adapters_config, adapter_inputs)
    try:
        landing = json.loads(Path(path).read_text(encoding="utf-8")).get("landing") if path else None
    except (OSError, ValueError, AttributeError):
        return  # an unreadable config is the adapter builder's refusal to make, by name
    if not isinstance(landing, dict) or "page_version" not in landing:
        return
    forms = {landing["page_version"], *(["long-form"] if landing.get("opt_in") else [])}
    if forms != {normalized["copy_profile"]}:
        raise BridgeError("AF-LAUNCH-BRIDGE-COPY-FORM",
                          f"the intake approved copy form {normalized['copy_profile']!r} but the landing "
                          f"bridge config builds {', '.join(sorted(map(str, forms)))!s}. Make them agree "
                          "(or re-approve the plan). Nothing was dispatched and nothing was spent.")


def _validate_supplied_adapters(config: Dict[str, Any], test_only: bool) -> None:
    """An operator-supplied adapter config goes through Skill 83's adapter allow-list before anything runs."""
    import adapters  # routes/adapters.py, as _build_adapters does
    check = getattr(adapters, "validate_adapter_config", None)  # ponytail: U-structure-01 adds the allow-list; absent on this base
    if check is None:
        return
    try:
        check(config, test_only=test_only)
    except adapters.AdapterError as exc:
        raise BridgeError("AF-LAUNCH-BRIDGE-ADAPTERS",
                          f"{exc}. Nothing was dispatched and nothing was spent.") from exc


def _resolved_inputs(key: str, held: Any) -> Any:
    """The config's own image_inputs path(s), resolved the way the plan's are, so a symlinked or relative
    spelling of the same file (macOS /tmp is /private/tmp) is not a disagreement; a different file still is."""
    if key == "image_inputs" and isinstance(held, str):
        return str(Path(held).resolve())
    if key == "image_plan" and isinstance(held, dict) and isinstance(held.get("image_inputs"), str):
        return {**held, "image_inputs": str(Path(held["image_inputs"]).resolve())}
    return held


def _landing_bridge_config(adapter_inputs: Dict[str, Any], dispatch_dir: Path, inputs: Dict[str, Any],
                           inputs_path: Path) -> Dict[str, Any]:
    """Hand Skill 49's landing bridge the approved image plan (STR-16).

    With no bridge_config in adapter_inputs, adapter_inputs is returned unchanged. Otherwise the
    supplied config's landing section gets image_inputs, image_plan, image_cap and brand_owner from the
    plan this run resolved, and draft is False unless the config already declares it True; a value the
    supplied config already holds that differs from the plan is refused. The rewritten config is
    written beside the dispatch and replaces the supplied path. An unreadable file, or one with no
    landing section, is refused here."""
    if not adapter_inputs.get("bridge_config"):
        return adapter_inputs
    try:
        doc = json.loads(Path(adapter_inputs["bridge_config"]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BridgeError("AF-LAUNCH-BRIDGE-ADAPTERS",
                          f"the landing bridge config {adapter_inputs['bridge_config']} cannot be read ({exc}). "
                          "Nothing was dispatched and nothing was spent.") from exc
    landing = doc.get("landing") if isinstance(doc, dict) else None
    if not isinstance(landing, dict):
        raise BridgeError("AF-LAUNCH-BRIDGE-ADAPTERS",
                          f"the landing bridge config {adapter_inputs['bridge_config']} has no \"landing\" section, "
                          "so the landing and sales pages have nothing to build from. "
                          "Nothing was dispatched and nothing was spent.")
    written = image_plan.image_inputs_file(inputs)
    abs_inputs = str(Path(inputs_path).resolve())
    want = {"image_inputs": abs_inputs,
            "image_plan": {"image_inputs": abs_inputs, "image_cap": written["image_cap"],
                           "brand_owner": written["brand_owner"], "design_style": written["design_style"],
                           "image_provider": written["image_provider"]},
            "image_cap": written["image_cap"], "brand_owner": written["brand_owner"]}
    for key, value in want.items():
        if key in landing and _resolved_inputs(key, landing[key]) != value:
            raise BridgeError("AF-LAUNCH-BRIDGE-IMAGE-PLAN",
                              f"{key} in the landing bridge config is {landing[key]!r} but the approved image "
                              f"plan says {value!r}. Nothing was dispatched and nothing was spent.")
    landing.update(want)
    landing["draft"] = landing.get("draft") is True  # a draft is only ever declared, never defaulted on
    path = Path(dispatch_dir) / "landing-bridge.json"
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {**adapter_inputs, "bridge_config": str(path)}


def run(payload: Dict[str, Any], out_dir: Path, *, approval: Dict[str, Any],
        client_identity_ref: str, worker_identity_ref: str,
        adapters_config: Optional[Dict[str, Any]] = None,
        adapter_inputs: Optional[Dict[str, Any]] = None,
        parallel: Optional[int] = None,
        scoped_approvals: Optional[List[Dict[str, Any]]] = None,
        extra_pages: Sequence[str] = (),
        landing_pages: Optional[Sequence[str]] = None,
        observed_capabilities: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Validate, bridge, dispatch, and write one result per page. Returns the dispatch report.

    landing_pages is the client's landing page choice ("landing", "sales" or both). Without it the set
    Skill 49 recommends is used and flagged "to confirm". Either way Skill 49's page set is the
    plan: one piece is written for every page in it (the sales page too), never fewer.

    Fail-closed and plain-spoken: every refusal raises BridgeError (or the Launcher's own IntakeError /
    ImagePlanError) whose detail says what is needed and what has NOT been done (nothing spent, nothing sent).
    """
    out_dir = Path(out_dir)
    normalized = intake_module.validate(payload)
    # F22: BEFORE any design work or paid render, prove the capabilities this dispatch
    # needs. Fail closed: a required capability that cannot be proved stops the run by
    # name; nothing is spent and no page is built. Capabilities the approved feature set
    # did not select are reported as advisories, never silently treated as satisfied.
    capabilities = capability_check.run(
        normalized, require=("journey_mapping",),
        observed=observed_capabilities or {})
    try:
        capability_check.assert_ready(capabilities)
    except capability_check.CapabilityError as exc:
        raise BridgeError(exc.code,
                          f"{exc.detail}. Nothing was dispatched and nothing was spent.") from exc
    resources = linked_delivery.resolve(normalized)
    # F20: the image plan is resolved ONCE, below, by resolve_launch — it verifies the paid budget
    # against the plan hash the record itself produces and rebuilds the record from the verified inputs.
    graph = route.compile_route(normalized)
    # F20: the paid budget is verified against the plan hash the record itself produces (no circular
    # dependency), and the record is rebuilt from the verified inputs.
    inputs, to_confirm, launch = resolve_launch(normalized, graph, landing_pages=landing_pages,
                                                extra_pages=extra_pages)
    _bind_approval(launch, normalized, approval)
    fails = check_launch_record(launch)
    if fails:
        raise BridgeError("AF-LAUNCH-BRIDGE-RECORD",
                          "Skill 49 would not accept this launch plan: " + "; ".join(fails)
                          + ". Nothing was dispatched and nothing was spent.")
    if adapters_config is not None:
        _validate_supplied_adapters(adapters_config, bool(normalized.get("test_only", True)))

    out_dir.mkdir(parents=True, exist_ok=True)
    dispatch_dir = out_dir / "dispatch"
    pieces_dir = out_dir / "pieces"
    inputs_path = out_dir / "image_inputs.json"
    order_inputs_path = out_dir / "order-page-inputs.json"
    launch_path = out_dir / "launch.json"
    launch_path.write_text(json.dumps(launch, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if normalized.get("checkout_terms"):
        # the checkout wrapper reads the approved terms beside the launch record (the closed launch schema cannot carry them)
        (out_dir / "checkout-terms.json").write_text(
            json.dumps({"checkout_terms": normalized["checkout_terms"]}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    (out_dir / INTAKE_SNAPSHOT).write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n",
                                                     encoding="utf-8")  # the dispatch-time intake package.assemble binds to (package.INTAKE_SNAPSHOT_REL)
    # F22: the launch's linked delivery/access destinations, recorded before any page is
    # built. Same inputs give the same ordered inventory and the same fingerprint.
    resources_path = linked_delivery.write_record(resources, out_dir)
    capabilities_path = out_dir / capability_check.RECORD_REL
    capabilities_path.write_text(json.dumps(capabilities, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
    inputs_path.write_text(json.dumps(image_plan.image_inputs_file(inputs), indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    order_inputs_path.write_text(json.dumps(image_plan.order_page_inputs_file(
        inputs, route_graph=str(dispatch_dir / "route-graph.json")), indent=2, sort_keys=True) + "\n",
        encoding="utf-8")

    dl = substrate.dispatch()
    planned, landing_to_confirm = _plan_landing_pages(dl, launch, landing_pages, extra_pages)
    _check_copy_form(normalized, adapters_config, adapter_inputs)
    dispatch_dir.mkdir(parents=True, exist_ok=True)  # the adapter builder needs the folder to exist
    if adapters_config is None:
        if adapter_inputs is None:
            raise BridgeError("AF-LAUNCH-BRIDGE-ADAPTERS",
                              "I have no way to build the pages yet: give me either a ready adapter "
                              "configuration or the per-page inputs (copy, journey and enrichment for the "
                              "upsell and downsell pages). Nothing was dispatched.")
        adapter_inputs = _landing_bridge_config(adapter_inputs, dispatch_dir, inputs, inputs_path)
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
    front_door = getattr(substrate, "front_door_check", None)  # Skill 49's one front door, once the tree has it
    if front_door is not None:
        front_door()  # version, hash-pin and bypass scan: the same gates the shell entry runs, before any page
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
    bases = stage_state_bases(out_dir)
    for result in manifest["results"]:
        role = next(r["page_role"] for r in manifest["requests"] if r["request_id"] == result["request_id"])
        if role == FIRST_ROLE:  # one landing result carries every landing page Skill 49 planned
            for slot, piece in split_landing(result, planned).items():
                attach_stage_state(piece, slot, out_dir, bases)  # each landing page carries its OWN run's state
                (pieces_dir / f"{slot}.json").write_text(json.dumps(piece, indent=2) + "\n", encoding="utf-8")
                written.append(slot)
            continue
        shutil.copyfile(dispatch_dir / f"result-{role}.json", pieces_dir / f"{role}.json")
        _carry_stage_state(pieces_dir / f"{role}.json", role, out_dir, bases)
        written.append(role)
    for lane in manifest.get("page_results", {}):  # an extra page rides on its parent's request
        shutil.copyfile(dispatch_dir / f"page-result-{lane}.json", pieces_dir / f"{lane}.json")
        _carry_stage_state(pieces_dir / f"{lane}.json", lane, out_dir, bases)
        written.append(lane)

    _stamp_image_provider(pieces_dir, written, inputs["executor_provider"])

    # F08 delivery: produce each offer's delivery sheet, bind it, and record what the
    # run did and did not make. A failed dispatch above leaves no product record.
    try:
        delivered = delivery.run(normalized, out_dir, launch=launch)
    except delivery.DeliveryError as exc:
        raise BridgeError(exc.code, f"{exc.detail}. The pages were built; no product record was written.") from exc

    report = {
        "launch_id": normalized["launch_id"],
        "execution": manifest["execution"],
        "pages": written,
        "page_labels": [p["label"] for p in manifest["page_set"]["pages"]],
        "landing_pages": planned,
        "lane_plan": lane_plan(graph, parallel, extra_pages, side_by_side=parallel_state.startswith("parallel")),
        "parallel": parallel_state,
        "pieces_dir": str(pieces_dir),
        "design_only_pages": [r for r in written if r in ("upsell_1", "upsell_2")],
        "launch_record": str(launch_path),
        "image_inputs": str(inputs_path),
        "image_provider": inputs["image_provider"],
        "executor_provider": inputs["executor_provider"],
        "paid_calls_allowed": inputs["allow_paid"],
        "to_confirm": to_confirm + landing_to_confirm,
        # F22: what this launch depends on and where its buyers are sent, recorded with the
        # page build so the package check re-verifies the same facts rather than new ones.
        "capabilities": {
            "path": capability_check.RECORD_REL,
            "state": capabilities["state"],
            "required": capabilities["required"],
            "blocked": capabilities["blocked"],
            "advisories": [name for name, row in capabilities["capabilities"].items()
                           if row["state"] == "unproven" and not row["required"]],
        },
        "linked_delivery": {
            "path": str(resources_path.name),
            "fingerprint": resources["fingerprint"],
            "counts": resources["summary"]["counts"],
            "state": resources["summary"]["state"],
            "pages": resources["pages"],
            "client_blockers": resources["summary"]["client_blockers"],
            "next_steps": resources["summary"]["next_steps"],
        },
        "delivery": {
            "record": delivered["record_path"],
            "kind": delivered["plan"]["kind"],
            "kind_state": delivered["plan"]["kind_state"],
            # Projected from the record, never re-derived: one identity (path + sha256)
            # per offer, the same one product-delivery.json carries. `sheets` stays as
            # the path-only view earlier readers were given.
            "artifacts": {o["offer_id"]: o["sheet"] for o in delivered["record"]["offers"]},
            "sheets": {o["offer_id"]: o["sheet"]["path"] for o in delivered["record"]["offers"]},
            "delivery_modes": {o["offer_id"]: o["delivery_mode"] for o in delivered["record"]["offers"]},
            "free_entry": delivered["record"]["free_entry"],
        },
    }
    (out_dir / "dispatch-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                                                  encoding="utf-8")
    return report


def _stamp_image_provider(pieces_dir: Path, slots: Sequence[str], provider: str) -> None:
    """Record which provider drew each page, on the piece, when its own result names none (issue 16).

    The package check refuses a client delivery whose design files name no provider (a placeholder cannot
    be told from a real render). A page-result 1.0 carries no provider field, so the run's approved image
    plan (the executor provider every adapter was handed) is the piece-level record. An artifact that
    names its own provider keeps it: the artifact wins over the piece in page_designs._provider_of."""
    for slot in slots:
        path = Path(pieces_dir) / f"{slot}.json"
        piece = json.loads(path.read_text(encoding="utf-8"))
        if not (isinstance(piece.get("image_provider"), str) and piece["image_provider"].strip()):
            piece["image_provider"] = provider
            path.write_text(json.dumps(piece, indent=2) + "\n", encoding="utf-8")


def with_production(report: Dict[str, Any], root: Path) -> Dict[str, Any]:
    """The dispatch report plus what the produce and install stages left in the package (issue 80)."""
    out = dict(report)
    root = Path(root)

    def read(rel: str) -> Dict[str, Any]:
        try:
            doc = json.loads((root / rel).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return doc if isinstance(doc, dict) else {}

    pages = read("production/manifest.json").get("pages")
    if isinstance(pages, dict):
        out["production"] = {role: row.get("state") for role, row in pages.items() if isinstance(row, dict)}
    back = read("install/install-readback.json").get("pages")
    if isinstance(back, dict):
        out["install_readbacks"] = back
    return out


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
    # F22 item 8: a real blocker is stated in plain words with the practical next step,
    # and the work that does not depend on it keeps going. It is never hidden.
    linked = report.get("linked_delivery") or {}
    for message, step in zip(linked.get("client_blockers") or [],
                             linked.get("next_steps") or []):
        lines.append(f"Still to sort out: {message} Next step: {step}")
    # Issue 80: these lines are DATA-DRIVEN. What a page is called depends on what exists on disk, not on a
    # fixed sentence: the production manifest (report["production"]: role -> "built" | "not_built") and the
    # install read-back (report["install_readbacks"]), both added by with_production(). A page with no
    # production record is a design; one that was produced is a finished page; one that was read back from
    # the install is installed. skill06_readbacks is the older, role-keyed record Skill 6 may leave.
    produced = report.get("production") or {}
    installed = report.get("install_readbacks") or {}
    readbacks = report.get("skill06_readbacks") or {}
    for role, label in (("upsell_1", "Upsell 1 (U1)"), ("downsell_1", "Downsell (D1)"),
                        ("upsell_2", "Upsell 2 (U2)"), ("thank_you", "Thank-you page")):
        if role not in report["pages"]:
            continue
        if produced.get(role) == "built":
            if installed.get(role):
                lines.append(f"{label}: built as a finished page and installed in your account; the install was "
                             "read back and matched.")
            else:
                lines.append(f"{label}: built as a finished page; not installed yet. The install step has not "
                             "recorded a read-back for it.")
        elif role in ("upsell_1", "upsell_2"):
            lines.append(f"{label}: design only. The finished page has not been built yet; the production step "
                         "builds it from the approved design.")
        elif not readbacks.get(role):
            lines.append(f"{label}: design only; not installed. No install read-back is recorded for it "
                         "(scheduled: S06-02 / UPS-08).")
    return lines


def _checkout_request_file(out_dir: Path, launch_path: Path) -> Path:
    """The Skill 79 checkout request the order form page is written and designed from.

    It is the first main price choice's own request, built by checkout_instances from the intake at dispatch
    and the launch record being dispatched (the read-back facts that only Skill 06 can supply stay missing;
    the copy needs none of them). Skill 79's emitter stamps the page copy with this file's sha256 and Skill 49's
    checkout wrapper refuses copy stamped with any other request."""
    from . import checkout_instances  # imports this module, so it is loaded here, not at the top
    snapshot = json.loads((out_dir / INTAKE_SNAPSHOT).read_text(encoding="utf-8"))
    launch = json.loads(launch_path.read_text(encoding="utf-8"))
    built = checkout_instances.record(snapshot, route.compile_route(snapshot), launch=launch)
    request = out_dir / "checkout-request.json"
    request.write_text(json.dumps(built["instances"][0]["request"], indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
    return request


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
    if adapter_inputs.get("checkout_manuscript"):
        raise BridgeError("AF-LAUNCH-BRIDGE-ADAPTERS",
                          "the order form page's copy is written by Skill 79 from the approved checkout "
                          "request, never staged by hand: remove checkout_manuscript. Nothing was dispatched.")
    request = _checkout_request_file(out_dir, launch_path)
    # Skill 79 writes the order form's copy from that request, before the checkout design lane runs.
    manuscript = adapters.emit_checkout_manuscript(
        request=request, launch=launch_path, terms=out_dir / "checkout-terms.json",
        out=out_dir / "dispatch" / "copy-checkout.md")
    checkout_design = {"manuscript": str(manuscript), "checkout_request": str(request),
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
        checkout_design=checkout_design, image_plan=inputs,
        measured_design_system=adapter_inputs.get("measured_design_system"))
