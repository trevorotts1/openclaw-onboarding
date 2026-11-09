"""Versioned course deliverable request and receipt binding (WF13).

The launcher used to classify every promised course as ``unfinished_course`` and
stop there. That was honest while no producer existed, but it made the promise
permanently undeliverable. This module keeps the honesty and adds the missing
route:

  * ``convert_legacy_unfinished_course`` turns a legacy ``unfinished_course``
    deliverable into a versioned production REQUEST only when the approved
    course content and the required inputs exist. Without them it returns the
    honest pending state and names every missing fact; it never invents content.
  * ``build_request`` produces ``launcher.course-deliverable-request.v1``: the
    approved content, the requested components, the Skill 6 ``build_course``
    task, and DISTINCT course / group / offer / commerce / payment identifiers.
  * ``dispatch`` calls the supplied ``build_course`` facade. The facade is a
    parameter, never imported here, so this module stays offline and testable.
  * ``build_receipt`` records one result per requested component and decides
    whether the delivery is COMPLETE for what was actually requested
    (Document 1 section 15.3). A component nobody asked for never gates it; a
    requested component that was not verified always does.
  * ``access_state`` is separate from payment: an enrollment is an access grant,
    never proof that money was paid. A draft-only delivery can be complete while
    buyer access is not ready.
  * ``bindings`` emits a SEPARATE receipt-reference map keyed by entitlement id.
    The launch schema's strict ``delivery_bindings`` object is untouched, so old
    consumers keep reading the old shape. An included bump/upsell only ever gets
    the URL of the offer that owns its entitlement, never an unrelated course URL.

Stdlib only. Deterministic: the same facts produce the same request/receipt ids.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlsplit

REQUEST_TYPE = "launcher.course-deliverable-request.v1"
RECEIPT_TYPE = "launcher.course-delivery-receipt.v1"
REQUESTS_RECORD_TYPE = "launcher.course-delivery-requests.v1"
SCHEMA_VERSION = "1.0.0"
RECEIPTS_REL = "course-deliveries.json"

LEGACY_KIND = "unfinished_course"
STATE_NOT_APPLICABLE = "not_applicable"
STATE_PENDING = "pending"
STATE_REQUESTED = "requested"

MODE_COURSE = "course_delivery"

# What a promise's state means in a course receipt.
COMPONENT_VERIFIED = "verified"
COMPONENT_MISSING = "missing"

ACCESS_READY = "access_ready"
ACCESS_PENDING = "access_pending"
ACCESS_REVOKED = "access_revoked"
ACCESS_NOT_REQUESTED = "not_requested"

PENDING_REASON = (
    "the deliverable is recorded as unfinished_course and no approved course "
    "content (modules, lesson titles, requested media and an approval reference) "
    "is in hand, so no production request is minted; the promise stays pending "
    "until the content is approved")
ENROLLMENT_NOT_PAYMENT = (
    "a course enrollment created through the course producer is an access grant; "
    "it is never proof that a payment settled")


class CourseDeliveryError(Exception):
    """A request or receipt that cannot be built. Carries a stable code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _https(url: Any) -> bool:
    parts = urlsplit(url) if isinstance(url, str) else None
    return bool(parts and parts.scheme == "https" and parts.hostname
                and not parts.username and not parts.password
                and not any(c.isspace() for c in url))


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(obj: Any) -> str:
    return hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()


def _mint(prefix: str, intent: Mapping[str, Any]) -> str:
    return f"{prefix}_{_sha(intent)[:32]}"


# ---------------------------------------------------------------------------
# Approved content -> request
# ---------------------------------------------------------------------------
def content_problems(content: Any) -> List[str]:
    """Every missing fact that stops legacy conversion, by name.

    Content is the APPROVED course outline. Only these facts are required; a
    lesson with no requested media is a lesson with no media requirement, not a
    defect.
    """
    if not isinstance(content, Mapping):
        return ["the approved course content (modules, lesson titles, approval reference)"]
    problems: List[str] = []
    approval = content.get("approval")
    ref = approval.get("ref") if isinstance(approval, Mapping) else None
    if not _nonempty(ref):
        problems.append("the approved course content reference (content.approval.ref)")
    modules = content.get("modules")
    if not isinstance(modules, list) or not modules:
        problems.append("at least one approved module (content.modules)")
        return problems
    for index, module in enumerate(modules):
        if not isinstance(module, Mapping) or not _nonempty(module.get("title")):
            problems.append(f"module {index} title (content.modules[{index}].title)")
            continue
        lessons = module.get("lessons")
        if not isinstance(lessons, list) or not lessons:
            problems.append(
                f"at least one lesson in module {index} "
                f"(content.modules[{index}].lessons)")
    return problems


def _lesson_media(lesson: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Requested media for one lesson: explicit entries only, never invented."""
    out: List[Dict[str, Any]] = []
    raw = lesson.get("media")
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, Mapping) and _nonempty(entry.get("url")):
                out.append({"kind": str(entry.get("kind") or "file"),
                            "url": str(entry["url"]),
                            "sha256": entry.get("sha256")})
    elif _nonempty(lesson.get("media_url")):
        out.append({"kind": "file", "url": str(lesson["media_url"]), "sha256": None})
    return out


def _course_task(offer: Mapping[str, Any], content: Mapping[str, Any],
                 release: Mapping[str, Any]) -> Dict[str, Any]:
    """The approved outline in the Skill 6 ``build_course`` task shape."""
    modules = []
    for module in content["modules"]:
        lessons = []
        for lesson in module["lessons"]:
            media = _lesson_media(lesson)
            lessons.append({"title": str(lesson["title"]),
                            "media_url": media[0]["url"] if media else None,
                            "_media": media})
        modules.append({"title": str(module["title"]), "lessons": lessons})
    approval = release.get("policy") if isinstance(release, Mapping) else None
    publish = str(approval).strip().lower() in ("published", "publish", "go-live")
    return {
        "course_name": str(offer.get("name") or offer.get("offer_id")),
        "location_id": offer.get("location_id"),
        "description": str(content.get("description") or ""),
        "modules": modules,
        "approval": approval,
        "publish": publish,
    }


def _components(content: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """One requested component per module and lesson, plus requested media/assessment.

    A component is REQUESTED only because the approved content names it. Nothing
    is added to make a receipt look fuller.
    """
    out: List[Dict[str, Any]] = []
    for m_index, module in enumerate(content["modules"]):
        out.append({"component_id": f"module:{m_index}", "kind": "module",
                    "required": True, "expected": {"title": str(module["title"])},
                    "source_ref": f"content.modules[{m_index}]"})
        for l_index, lesson in enumerate(module["lessons"]):
            cid = f"lesson:{m_index}:{l_index}"
            out.append({"component_id": cid, "kind": "lesson", "required": True,
                        "expected": {"title": str(lesson["title"]),
                                     "module": str(module["title"])},
                        "source_ref": f"content.modules[{m_index}].lessons[{l_index}]"})
            for n, media in enumerate(_lesson_media(lesson)):
                out.append({"component_id": f"{cid}:media:{n}", "kind": "media",
                            "required": True, "expected": {"lesson": str(lesson["title"]),
                                                           "url": media["url"],
                                                           "sha256": media["sha256"]},
                            "source_ref": f"content.modules[{m_index}].lessons[{l_index}].media[{n}]"})
    for n, assessment in enumerate(content.get("assessments") or []):
        if isinstance(assessment, Mapping) and _nonempty(assessment.get("id")):
            out.append({"component_id": f"assessment:{assessment['id']}",
                        "kind": "assessment", "required": True,
                        "expected": {"id": str(assessment["id"]),
                                     "title": assessment.get("title")},
                        "source_ref": f"content.assessments[{n}]"})
    release = content.get("release") if isinstance(content.get("release"), Mapping) else {}
    if _nonempty(release.get("policy")):
        out.append({"component_id": "release:policy", "kind": "release_policy",
                    "required": True, "expected": {"policy": str(release["policy"])},
                    "source_ref": "content.release.policy"})
    return out


def build_request(*, launch: Mapping[str, Any], offer: Mapping[str, Any],
                  content: Any, group: Optional[Mapping[str, Any]] = None,
                  commerce: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """The versioned production request for one offer's approved course.

    Distinct identifiers are mandatory: the course offer id, the native course
    product id, the commerce product/price ids, the buyer order reference, the
    community group id and the entitlement ids are all separate fields.
    """
    problems = content_problems(content)
    if problems:
        raise CourseDeliveryError("AF-COURSE-REQUEST-CONTENT", "; ".join(problems))
    offer_id = offer.get("offer_id")
    if not _nonempty(offer_id):
        raise CourseDeliveryError("AF-COURSE-REQUEST-OFFER", "the offer has no offer_id")
    if not _nonempty(offer.get("location_id")):
        raise CourseDeliveryError("AF-COURSE-REQUEST-OFFER",
                                  f"offer {offer_id!r} carries no location_id")
    entitlement_ids = [e for e in (offer.get("entitlement_ids") or []) if _nonempty(e)]
    if not entitlement_ids:
        raise CourseDeliveryError(
            "AF-COURSE-REQUEST-ENTITLEMENT",
            f"offer {offer_id!r} grants no entitlement, so no receipt can be bound to a buyer")
    release = content.get("release") if isinstance(content.get("release"), Mapping) else {}
    access = content.get("access") if isinstance(content.get("access"), Mapping) else {}
    destination = access.get("destination")
    if destination is not None and not _https(destination):
        raise CourseDeliveryError("AF-COURSE-REQUEST-ACCESS",
                                  f"access destination {destination!r} is not https")
    group_doc = {"requested": bool(group and group.get("requested")),
                 "community_group_id": (group or {}).get("community_group_id"),
                 "learning_area_id": (group or {}).get("learning_area_id")}
    if group_doc["requested"] and not _nonempty(group_doc["community_group_id"]):
        # The group is requested but not yet identified: the request records the
        # gap, it does not invent an id.
        group_doc["community_group_id"] = None
    commerce_doc = {
        "commerce_product_id": (commerce or {}).get("commerce_product_id"),
        "commerce_price_id": (commerce or {}).get("commerce_price_id"),
        "order_ref": (commerce or {}).get("order_ref"),
        "payment_state": (commerce or {}).get("payment_state") or "not_verified",
    }
    intent = {
        "launch_id": launch.get("launch_id"), "tenant_id": launch.get("tenant_id"),
        "location_id": offer.get("location_id"), "revision": launch.get("revision"),
        "offer_id": offer_id, "content_hash": _sha(content),
        "entitlement_ids": entitlement_ids,
    }
    return {
        "contract_type": REQUEST_TYPE,
        "schema_version": SCHEMA_VERSION,
        "request_id": _mint("cdreq", intent),
        "launch_id": launch.get("launch_id"),
        "tenant_id": launch.get("tenant_id"),
        "location_id": offer.get("location_id"),
        "revision": launch.get("revision"),
        # --- distinct identities, never one overloaded product_id -----------
        "course_offer_id": offer_id,
        "course_product_id": offer.get("native_product_id"),
        "entitlement_ids": entitlement_ids,
        "commerce": commerce_doc,
        "group": group_doc,
        # --------------------------------------------------------------------
        "components": _components(content),
        "expected": {
            "module_count": len(content["modules"]),
            "lesson_count": sum(len(m["lessons"]) for m in content["modules"]),
            "media_count": sum(len(_lesson_media(l)) for m in content["modules"]
                               for l in m["lessons"]),
            "assessment_count": len([a for a in (content.get("assessments") or [])
                                     if isinstance(a, Mapping) and _nonempty(a.get("id"))]),
        },
        "content": content,
        "content_hash": _sha(content),
        "approval": {"ref": content["approval"]["ref"]},
        "course_task": _course_task(offer, content, release),
        "release": {"policy": release.get("policy")},
        "access": {"destination": destination,
                   "verified": access.get("verified") is True,
                   "proof_ref": access.get("proof_ref")},
        "payment_evidence": "none",
        "enrollment_is_payment_proof": False,
        "notes": ENROLLMENT_NOT_PAYMENT,
    }


def convert_legacy_unfinished_course(item: Any, *, launch: Mapping[str, Any],
                                     offer: Mapping[str, Any],
                                     content: Any = None,
                                     group: Any = None,
                                     commerce: Any = None) -> Dict[str, Any]:
    """Legacy ``unfinished_course`` -> versioned request, or the honest pending state.

    Never renames the legacy state to completed. Without approved content the
    answer is ``pending`` with every missing fact named.
    """
    kind = item.get("kind") if isinstance(item, Mapping) else None
    if kind != LEGACY_KIND:
        return {"state": STATE_NOT_APPLICABLE,
                "detail": f"deliverable kind {kind!r} is not {LEGACY_KIND!r}"}
    problems = content_problems(content)
    if problems:
        return {"state": STATE_PENDING, "reason": PENDING_REASON, "missing": problems}
    request = build_request(launch=launch, offer=offer, content=content,
                            group=group, commerce=commerce)
    return {"state": STATE_REQUESTED, "request": request}


# ---------------------------------------------------------------------------
# Dispatch through the approved producer facade
# ---------------------------------------------------------------------------
def dispatch(request: Mapping[str, Any], producer: Any, evidence_root: str,
             *, dry_run: bool = True) -> Dict[str, Any]:
    """Call the Skill 6 ``build_course`` facade (or a fake with the same shape).

    The facade is not imported here: a missing producer is a caller error, never
    a silent success. A raised error is returned as a recorded failure so the
    receipt can say the delivery did not happen.
    """
    if not callable(producer):
        raise CourseDeliveryError("AF-COURSE-PRODUCER-MISSING",
                                  "no build_course facade was supplied")
    task = request.get("course_task")
    if not isinstance(task, Mapping):
        raise CourseDeliveryError("AF-COURSE-PRODUCER-TASK", "the request carries no course_task")
    try:
        result = producer(dict(task), str(evidence_root), dry_run=dry_run)
    except TypeError:
        result = producer(dict(task), str(evidence_root))
    if not isinstance(result, Mapping):
        return {"ok": False, "error": "the producer returned a non-object result"}
    return dict(result)


# ---------------------------------------------------------------------------
# Receipt: complete only for what was requested
# ---------------------------------------------------------------------------
def _result_modules(result: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    modules = result.get("modules")
    if isinstance(modules, list):
        return [m for m in modules if isinstance(m, Mapping)]
    plan = result.get("plan") if isinstance(result.get("plan"), Mapping) else {}
    modules = plan.get("modules")
    return [m for m in modules if isinstance(m, Mapping)] if isinstance(modules, list) else []


def _verify_components(request: Mapping[str, Any],
                       result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """One row per requested component: verified or missing, with the reason."""
    rows: List[Dict[str, Any]] = []
    result_location = result.get("location_id") or (
        (result.get("plan") or {}).get("location_id")
        if isinstance(result.get("plan"), Mapping) else None)
    modules = _result_modules(result)
    delivered = {}
    for m_index, module in enumerate(modules):
        title = str(module.get("title") or "")
        delivered[f"module:{m_index}"] = module
        for l_index, lesson in enumerate(module.get("lessons") or []):
            if isinstance(lesson, Mapping):
                delivered[f"lesson:{m_index}:{l_index}"] = lesson
    release = result.get("release") if isinstance(result.get("release"), Mapping) else {}
    group = result.get("group") if isinstance(result.get("group"), Mapping) else {}
    access = result.get("access") if isinstance(result.get("access"), Mapping) else {}
    for component in request.get("components") or []:
        cid, kind = component.get("component_id"), component.get("kind")
        expected = component.get("expected") or {}
        detail = ""
        verified = False
        if kind == "module":
            found = delivered.get(cid)
            verified = bool(found and str(found.get("title") or "") == expected.get("title"))
            detail = "" if verified else f"module {expected.get('title')!r} is not in the delivered course"
        elif kind == "lesson":
            found = delivered.get(cid)
            verified = bool(found and str(found.get("title") or "") == expected.get("title"))
            detail = "" if verified else f"lesson {expected.get('title')!r} is not in the delivered module"
        elif kind == "media":
            lesson = delivered.get(cid.rsplit(":media:", 1)[0])
            media = lesson.get("media") if isinstance(lesson, Mapping) else None
            urls = [m.get("url") for m in media or [] if isinstance(m, Mapping)]
            listed = expected.get("url") in urls
            bound = bool(lesson and lesson.get("media_bound") is True)
            verified = bool(listed and bound)
            detail = "" if verified else (
                f"media {expected.get('url')!r} is not bound on the delivered lesson "
                "(listed is not bound)")
        elif kind == "assessment":
            assessments = result.get("assessments") or []
            found = next((a for a in assessments if isinstance(a, Mapping)
                          and a.get("id") == expected.get("id")), None)
            verified = bool(found and found.get("verified") is True)
            detail = "" if verified else f"assessment {expected.get('id')!r} is not verified"
        elif kind == "release_policy":
            verified = (release.get("applied") is True
                        and str(release.get("policy") or "") == str(expected.get("policy")))
            detail = "" if verified else "the requested release/access policy is not applied"
        else:
            detail = f"unknown component kind {kind!r}"
        rows.append({"component_id": cid, "kind": kind,
                     "state": COMPONENT_VERIFIED if verified else COMPONENT_MISSING,
                     "required": bool(component.get("required", True)),
                     "detail": detail})
    # Location identity gates the whole receipt.
    if not _nonempty(result_location) or result_location != request.get("location_id"):
        rows.insert(0, {"component_id": "course:location", "kind": "course_entity",
                        "state": COMPONENT_MISSING, "required": True,
                        "detail": (f"the produced course is in {result_location!r}, not the "
                                   f"requested location {request.get('location_id')!r}")})
    elif not _nonempty(result.get("course_id")):
        rows.insert(0, {"component_id": "course:entity", "kind": "course_entity",
                        "state": COMPONENT_MISSING, "required": True,
                        "detail": "the producer returned no course id"})
    else:
        rows.insert(0, {"component_id": "course:entity", "kind": "course_entity",
                        "state": COMPONENT_VERIFIED, "required": True, "detail": ""})
    # The group gates delivery only when it was requested.
    if (request.get("group") or {}).get("requested"):
        linked = bool(group.get("learning_association_verified") is True
                      and group.get("community_group_id") ==
                      (request.get("group") or {}).get("community_group_id"))
        rows.append({"component_id": "group:association", "kind": "group_association",
                     "state": COMPONENT_VERIFIED if linked else COMPONENT_MISSING,
                     "required": True,
                     "detail": "" if linked else
                     "the requested group and its Learning association are not verified"})
    return rows


def _access_state(request: Mapping[str, Any], result: Mapping[str, Any]) -> Dict[str, Any]:
    """Access readiness, separate from payment and from content completion."""
    if result.get("revoked") is True or result.get("refunded") is True:
        return {"state": ACCESS_REVOKED,
                "basis": "the producer reported a refund or revocation",
                "destination": None, "proves_payment": False,
                "enrollment_is_payment_proof": False}
    asked = request.get("access") if isinstance(request.get("access"), Mapping) else {}
    if not _nonempty(asked.get("destination")) and not asked.get("verified"):
        return {"state": ACCESS_NOT_REQUESTED,
                "basis": "no buyer access destination or access proof was requested",
                "destination": None, "proves_payment": False,
                "enrollment_is_payment_proof": False}
    access = result.get("access") if isinstance(result.get("access"), Mapping) else {}
    proof = access.get("test_access_proof") or asked.get("proof_ref")
    verified = access.get("enrollment_verified") is True or _nonempty(proof)
    if verified:
        return {"state": ACCESS_READY,
                "basis": ("an approved test-access proof exists" if _nonempty(proof)
                          else "the enrollment/access grant was verified; it is not payment proof"),
                "destination": asked.get("destination"),
                "proves_payment": False,
                "enrollment_is_payment_proof": False}
    return {"state": ACCESS_PENDING,
            "basis": "the access grant is not verified yet, so no link is promoted",
            "destination": None, "proves_payment": False,
            "enrollment_is_payment_proof": False}


def build_receipt(request: Mapping[str, Any], result: Mapping[str, Any]) -> Dict[str, Any]:
    """The versioned receipt for one request. Never claims an unverified component."""
    if not isinstance(request, Mapping) or request.get("contract_type") != REQUEST_TYPE:
        raise CourseDeliveryError("AF-COURSE-RECEIPT-REQUEST",
                                  "the receipt requires a course deliverable request")
    if not isinstance(result, Mapping):
        raise CourseDeliveryError("AF-COURSE-RECEIPT-RESULT", "the producer result is not an object")
    components = _verify_components(request, result)
    missing = [c for c in components if c["state"] != COMPONENT_VERIFIED and c["required"]]
    access = _access_state(request, result)
    complete = not missing
    receipt = {
        "contract_type": RECEIPT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "request_id": request["request_id"],
        "request_hash": _sha(request),
        "launch_id": request.get("launch_id"),
        "tenant_id": request.get("tenant_id"),
        "location_id": request.get("location_id"),
        "revision": request.get("revision"),
        "course_offer_id": request.get("course_offer_id"),
        "course_product_id": request.get("course_product_id"),
        "entitlement_ids": list(request.get("entitlement_ids") or []),
        "commerce": dict(request.get("commerce") or {}),
        "group": dict(request.get("group") or {}),
        "components": components,
        "expected": dict(request.get("expected") or {}),
        "complete": complete,
        "missing": [c["component_id"] for c in missing],
        "outstanding": [c["detail"] for c in missing if c["detail"]],
        "access": access,
        "producer": {
            "ok": result.get("ok") is True,
            "course_id": result.get("course_id"),
            "preview_url": result.get("preview_url"),
            "dry_run": result.get("dry_run") is True,
            "error": result.get("error"),
        },
        "payment_evidence": "none",
        "enrollment_is_payment_proof": False,
    }
    receipt["receipt_id"] = _mint("cdrec", receipt)
    return receipt


def access_ready(receipt: Mapping[str, Any]) -> bool:
    """True only when the delivery is complete AND access was verified."""
    return bool(receipt.get("complete") is True
                and (receipt.get("access") or {}).get("state") == ACCESS_READY)


def bindings(request: Mapping[str, Any], receipt: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """entitlement id -> receipt reference, for a SEPARATE receipt-reference map.

    The launch record's strict ``delivery_bindings`` object is never modified.
    Only the entitlements this request carries are bound; an included bump or
    upsell is never handed this offer's URL.
    """
    ready = access_ready(receipt)
    url = ((receipt.get("access") or {}).get("destination")
           if ready and (receipt.get("access") or {}).get("state") == ACCESS_READY else None)
    out: Dict[str, Dict[str, Any]] = {}
    for entitlement_id in request.get("entitlement_ids") or []:
        out[entitlement_id] = {
            "receipt_ref": receipt["receipt_id"],
            "course_offer_id": request.get("course_offer_id"),
            "access_ready": ready,
            "delivery_kind": "access",
            "delivery_url": url,
        }
    return out


# ---------------------------------------------------------------------------
# Files: the request list and the separate receipt-reference map
# ---------------------------------------------------------------------------
def write_requests(requests: Sequence[Mapping[str, Any]], out_dir: Path) -> Dict[str, Any]:
    path = Path(out_dir) / "course-delivery-requests.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"contract_type": REQUESTS_RECORD_TYPE, "schema_version": SCHEMA_VERSION,
           "requests": list(requests)}
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "count": len(requests)}


def write_receipt_map(records: Iterable[Tuple[Mapping[str, Any], Mapping[str, Any]]],
                      out_dir: Path) -> Dict[str, Any]:
    """Write the separate map: entitlement id -> receipt reference + access state."""
    merged: Dict[str, Dict[str, Any]] = {}
    receipts: List[Dict[str, Any]] = []
    for request, receipt in records:
        receipts.append(receipt)
        for entitlement_id, entry in bindings(request, receipt).items():
            merged[entitlement_id] = entry
    path = Path(out_dir) / RECEIPTS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"contract_type": "launcher.course-delivery-receipts.v1",
           "schema_version": SCHEMA_VERSION,
           "bindings": merged, "receipts": receipts}
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "entitlements": len(merged), "receipts": len(receipts)}
