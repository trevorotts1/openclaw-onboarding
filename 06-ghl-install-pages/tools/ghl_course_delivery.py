#!/usr/bin/env python3
"""ghl_course_delivery.py — the course PLAN VALIDATOR, LOGICAL-KEY IDENTITY MAP
and AGGREGATE COURSE-DELIVERY REDUCER for Skill 06 (WF07 / doc 1 s8.2, s8.3, s8.4, s8.8).

WHY THIS EXISTS
---------------
The course builder used to be a browser walk over a title-deduped tree. Two defects
follow from that shape and this module closes both:

  * A title is not an identity. Two legitimate lessons both named "Introduction"
    were silently collapsed because an old deduper compared titles. Identity here is
    the caller's LOGICAL KEY (``module_key`` / ``lesson_key``); titles are display
    text and duplicates are legal.
  * "Created" is not "delivered". A shell course with empty lessons reduced to a
    green summary. The reducer below can only claim what per-object artifacts on
    disk prove (the same F6 discipline as ``ghl_receipts``).

WHAT THIS MODULE OWNS
---------------------
  * ``validate_plan`` — rejects duplicate logical keys within the appropriate
    parent, missing content references, unknown parents, parent cycles,
    cross-location object IDs and invalid visibility. Duplicate DISPLAY titles are
    allowed when the logical keys differ.
  * ``identity_map`` — the deterministic logical-key -> position/parent map the
    coordinator walks; the only thing reconciliation may match on.
  * ``reduce_delivery`` / ``write_delivery_receipt`` — the aggregate
    ``course-delivery-receipt/1`` reducer. States: ``delivered`` / ``incomplete``
    / ``failed``. A standalone course does not require a Community association.

PURE FUNCTIONS ONLY: no network, no browser, no GHL write. Every caller injects
the per-object artifacts it actually holds.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

PLAN_SCHEMA = "course-build-plan/1.0.0"
RECEIPT_SCHEMA = "course-delivery-receipt/1"
RECEIPT_FILENAME = "course-delivery-receipt.json"

# Module and lesson visibility vocabularies DIFFER (doc 1 s8.3: "The category and
# lesson visibility vocabularies differ"). Keep them separate names on purpose.
# ponytail: these are the two vocabulary sets the build plan can express today;
# widen only with a captured vendor contract, never by merging the two sets.
MODULE_VISIBILITY = ("draft", "published")
LESSON_VISIBILITY = ("draft", "published", "hidden")

DELIVERY_DELIVERED = "delivered"
DELIVERY_INCOMPLETE = "incomplete"
DELIVERY_FAILED = "failed"


class CoursePlanError(ValueError):
    """The plan is structurally invalid — refused before any GHL write."""

    def __init__(self, errors: List[str]) -> None:
        self.errors = list(errors)
        super().__init__("; ".join(self.errors) or "invalid course plan")


def _as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def _text(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""


# ---------------------------------------------------------------------------
# Plan validation
# ---------------------------------------------------------------------------
def validate_plan(plan: Any) -> List[str]:
    """Return every structural error in ``plan`` (empty list = valid).

    Checks, in order:
      1. shape basics — modules list, non-empty title/location, module keys present;
      2. duplicate logical keys within the appropriate parent;
      3. unknown parent keys and parent cycles;
      4. missing content references for lessons required for delivery;
      5. cross-location object IDs (an explicit ``location_id`` on any bound
         object ID that disagrees with the plan's location);
      6. invalid visibility for the module/lesson vocabularies.

    Duplicate DISPLAY titles are deliberately NOT an error (doc 1 s8.2: "do not
    drop a legitimate second lesson named 'Introduction'").
    """
    errors: List[str] = []
    if not isinstance(plan, dict):
        return ["plan is not a JSON object"]

    location_id = _text(plan.get("location_id"))
    if not location_id:
        errors.append("plan.location_id is required")
    if not _text(plan.get("title")):
        errors.append("plan.title is required")

    modules = _as_list(plan.get("modules"))
    if not modules:
        errors.append("plan.modules must be a non-empty list")

    seen_module_keys: Dict[str, str] = {}          # module_key -> parent key ("")
    keys: List[str] = []
    for i, m in enumerate(modules):
        if not isinstance(m, dict):
            errors.append(f"modules[{i}] is not an object")
            continue
        mkey = _text(m.get("module_key"))
        if not mkey:
            errors.append(f"modules[{i}].module_key is required (a title is not an identity)")
            continue
        parent = _text(m.get("parent_module_key"))
        keys.append(mkey)
        if mkey in seen_module_keys:
            errors.append(f"duplicate module_key {mkey!r} (logical keys must be unique)")
        seen_module_keys[mkey] = parent
        # duplicate module_key WITHIN one parent is the documented case; the keys
        # are globally unique here, which is stricter and cannot hide a sibling.
        if not _text(m.get("title")):
            errors.append(f"module {mkey!r} has no title")
        vis = _text(m.get("visibility")) or "draft"
        if vis not in MODULE_VISIBILITY:
            errors.append(
                f"module {mkey!r} visibility {vis!r} is not one of {MODULE_VISIBILITY}")

        seen_lesson_keys: set = set()
        lessons = _as_list(m.get("lessons"))
        for j, l in enumerate(lessons):
            if not isinstance(l, dict):
                errors.append(f"module {mkey!r} lessons[{j}] is not an object")
                continue
            lkey = _text(l.get("lesson_key"))
            if not lkey:
                errors.append(
                    f"module {mkey!r} lessons[{j}].lesson_key is required "
                    "(a title is not an identity)")
                continue
            if lkey in seen_lesson_keys:
                errors.append(f"duplicate lesson_key {lkey!r} within module {mkey!r}")
            seen_lesson_keys.add(lkey)
            if not _text(l.get("title")):
                errors.append(f"lesson {mkey}/{lkey} has no title")
            lvis = _text(l.get("visibility")) or "draft"
            if lvis not in LESSON_VISIBILITY:
                errors.append(
                    f"lesson {mkey}/{lkey} visibility {lvis!r} is not one of "
                    f"{LESSON_VISIBILITY}")
            required = l.get("required_for_delivery", True)
            has_content = bool(_text(l.get("description")) or _text(l.get("body"))
                               or _text(l.get("description_ref")))
            if required and not has_content:
                errors.append(
                    f"lesson {mkey}/{lkey} is required_for_delivery but carries no "
                    "approved content reference (description/body/description_ref)")

    # Unknown parents + cycles (walk each chain; a repeat is a cycle).
    for key in keys:
        chain: List[str] = []
        cur = key
        while True:
            parent = seen_module_keys.get(cur, "")
            if not parent:
                break
            if parent not in seen_module_keys:
                errors.append(f"module {cur!r} declares unknown parent {parent!r}")
                break
            if parent in chain or parent == key:
                errors.append(f"parent cycle detected through module {key!r}")
                break
            chain.append(parent)
            cur = parent

    # Cross-location object IDs. A bound object may carry the location it was
    # observed in; a disagreement is a cross-tenant write waiting to happen.
    for label, ref in _iter_object_refs(plan):
        ref_loc = _text(ref.get("location_id")) if isinstance(ref, dict) else ""
        if ref_loc and location_id and ref_loc != location_id:
            errors.append(
                f"{label} is bound to location {ref_loc!r} but the plan is for "
                f"{location_id!r} (cross-location object IDs are refused)")
    return errors


def _iter_object_refs(plan: dict):
    """Yield (label, ref) for every place a plan may bind an EXISTING object ID."""
    for field in ("existing_course_product_id", "course_product_id"):
        v = plan.get(field)
        if isinstance(v, dict) and v.get("id"):
            yield field, v
    for m in _as_list(plan.get("modules")):
        if not isinstance(m, dict):
            continue
        mkey = _text(m.get("module_key")) or "?"
        v = m.get("existing_category_id")
        if isinstance(v, dict) and v.get("id"):
            yield f"module {mkey!r} existing_category_id", v
        for l in _as_list(m.get("lessons")):
            if not isinstance(l, dict):
                continue
            lkey = _text(l.get("lesson_key")) or "?"
            for field in ("existing_lesson_id", "native_content_id"):
                v = l.get(field)
                if isinstance(v, dict) and v.get("id"):
                    yield f"lesson {mkey}/{lkey} {field}", v


def require_valid_plan(plan: Any) -> dict:
    """``validate_plan`` as a gate: raises :class:`CoursePlanError` when invalid."""
    errors = validate_plan(plan)
    if errors:
        raise CoursePlanError(errors)
    return plan


# ---------------------------------------------------------------------------
# Identity map
# ---------------------------------------------------------------------------
def identity_map(plan: dict) -> Dict[str, dict]:
    """The deterministic logical-key -> identity record map.

    Keys are ``module:<module_key>`` and ``lesson:<module_key>/<lesson_key>``.
    Ordering is by (position, declaration index) so the coordinator walks
    parent-before-child deterministically without trusting dict order.
    """
    out: Dict[str, dict] = {}
    modules = [m for m in _as_list(plan.get("modules")) if isinstance(m, dict)]
    ordered = sorted(
        enumerate(modules),
        key=lambda t: (_position(t[1].get("position"), t[0]), t[0]),
    )
    for idx, m in ordered:
        mkey = _text(m.get("module_key"))
        if not mkey:
            continue
        out[f"module:{mkey}"] = {
            "object_type": "course_module",
            "module_key": mkey,
            "parent_module_key": _text(m.get("parent_module_key")),
            "position": _position(m.get("position"), idx),
            "logical_key": mkey,
        }
        lessons = [l for l in _as_list(m.get("lessons")) if isinstance(l, dict)]
        for lidx, l in sorted(
                enumerate(lessons),
                key=lambda t: (_position(t[1].get("position"), t[0]), t[0])):
            lkey = _text(l.get("lesson_key"))
            if not lkey:
                continue
            out[f"lesson:{mkey}/{lkey}"] = {
                "object_type": "course_lesson",
                "module_key": mkey,
                "lesson_key": lkey,
                "position": _position(l.get("position"), lidx),
                "logical_key": f"{mkey}/{lkey}",
            }
    return out


def parent_order(plan: dict) -> List[str]:
    """Module keys in parent-before-child order (stable; cycle-safe).

    A module whose parent is unknown/cyclic is emitted in declaration order rather
    than dropped — ``validate_plan`` is the gate that refuses such a plan, and the
    coordinator must never silently lose a module.
    """
    modules = [m for m in _as_list(plan.get("modules")) if isinstance(m, dict)]
    by_key = {_text(m.get("module_key")): m for m in modules if _text(m.get("module_key"))}
    emitted: List[str] = []
    seen: set = set()

    def emit(key: str, stack: tuple) -> None:
        if key in seen or not key:
            return
        m = by_key.get(key)
        if m is None:
            return
        parent = _text(m.get("parent_module_key"))
        if parent and parent in by_key and parent not in stack and parent not in seen:
            emit(parent, stack + (key,))
        if key not in seen:
            seen.add(key)
            emitted.append(key)

    for m in modules:
        emit(_text(m.get("module_key")), ())
    return emitted


def _position(v: Any, fallback: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return int(fallback) + 1


# ---------------------------------------------------------------------------
# Aggregate delivery reducer
# ---------------------------------------------------------------------------
def _state_of(artifact: Any) -> str:
    if not isinstance(artifact, dict):
        return "not_requested"
    state = _text(artifact.get("state")) or _text(artifact.get("status"))
    if not state and artifact.get("ok") is True:
        return "verified"
    return state or "unknown"


def reduce_delivery(plan: dict, artifacts: Dict[str, dict], *,
                    community_artifact: Optional[dict] = None,
                    content_proof: Optional[dict] = None,
                    extra_blocking: Optional[List[str]] = None) -> dict:
    """Reduce the plan + per-object artifacts into one delivery receipt.

    ``artifacts`` is keyed by the SAME logical identity keys ``identity_map``
    produces (``module:<key>`` / ``lesson:<key>``), plus optionally ``course``.
    An object with no artifact is NOT delivered — the reducer can never claim
    more than the artifacts prove (F6: "no receipt = not created").
    """
    errors = validate_plan(plan)
    idmap = identity_map(plan)
    community_spec = plan.get("community") if isinstance(plan.get("community"), dict) else {}
    community_required = bool(community_spec.get("required"))

    course_art = artifacts.get("course") or {}
    course_state = _state_of(course_art)
    if course_state in ("created",):
        course_state = "verified" if course_art.get("verified") is True else "created_unverified"

    modules_out: List[dict] = []
    lessons_out: List[dict] = []
    blocking: List[str] = list(extra_blocking or [])

    if not idmap:
        blocking.append("plan declares no addressable modules/lessons")
    if course_state not in ("verified",):
        blocking.append(f"course shell is {course_state}, not verified")

    for key in idmap:
        rec = idmap[key]
        art = artifacts.get(key) or {}
        state = _state_of(art)
        verified = state in ("verified", "created") and (
            art.get("verified") is True or art.get("present") is True)
        entry = {
            "logical_key": rec["logical_key"],
            "position": rec["position"],
            "state": "verified" if verified else (state or "not_requested"),
            "object_id": art.get("object_id") or art.get("response_id") or art.get("id"),
            "visibility": art.get("visibility") or art.get("actual_visibility"),
        }
        if rec["object_type"] == "course_module":
            entry["parent_module_key"] = rec["parent_module_key"]
            modules_out.append(entry)
        else:
            entry["module_key"] = rec["module_key"]
            lessons_out.append(entry)
        if not verified:
            blocking.append(f"{key} is {entry['state']}, not verified")

    # Content/media proof is a SEPARATE set of fields (doc 1 s8.5): a permanent
    # asset URL proves only persistence, never native content readiness.
    proof = content_proof if isinstance(content_proof, dict) else {}
    content = {
        "asset_persisted": bool(proof.get("asset_persisted")),
        "native_content_ready": bool(proof.get("native_content_ready")),
        "lesson_association_verified": bool(proof.get("lesson_association_verified")),
        "learner_render_verified": bool(proof.get("learner_render_verified")),
    }
    if proof.get("required") and not content["lesson_association_verified"]:
        blocking.append("required lesson content/media is not association-verified")

    # Community association only when REQUESTED (a standalone course needs no group).
    if community_required:
        cstate = _state_of(community_artifact)
        community = {
            "required": True,
            "state": cstate,
            "group_id": (community_artifact or {}).get("group_id"),
            "access_policy": (community_artifact or {}).get("access_policy"),
        }
        if cstate != "verified":
            blocking.append(f"community association is {cstate}, not verified")
    else:
        community = {"required": False, "state": "not_requested"}

    if errors:
        state = DELIVERY_FAILED
    elif blocking:
        state = DELIVERY_INCOMPLETE
    else:
        state = DELIVERY_DELIVERED

    return {
        "schema_version": RECEIPT_SCHEMA,
        "run_id": _text(plan.get("run_id")),
        "location_id": _text(plan.get("location_id")),
        "course_key": _text(plan.get("course_key")),
        "state": state,
        "course": {
            "state": course_state,
            "course_product_id": course_art.get("object_id")
            or course_art.get("response_id") or plan.get("existing_course_product_id"),
        },
        "modules": modules_out,
        "lessons": lessons_out,
        "counts": {
            "modules_expected": len([k for k in idmap if k.startswith("module:")]),
            "modules_verified": len([m for m in modules_out if m["state"] == "verified"]),
            "lessons_expected": len([k for k in idmap if k.startswith("lesson:")]),
            "lessons_verified": len([l for l in lessons_out if l["state"] == "verified"]),
        },
        "content": content,
        "community": community,
        "blocking": blocking,
        "plan_errors": errors,
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def write_delivery_receipt(evidence_root: str, receipt: dict) -> str:
    """Persist the reducer output at ``<evidence_root>/routing/`` atomically."""
    routing = os.path.join(str(evidence_root), "routing")
    os.makedirs(routing, exist_ok=True)
    path = os.path.join(routing, RECEIPT_FILENAME)
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return path


# ---------------------------------------------------------------------------
# Self-test — no network, no browser, tmp only
# ---------------------------------------------------------------------------
def _selftest() -> int:
    errors: List[str] = []

    base = {
        "schema_version": PLAN_SCHEMA,
        "run_id": "run-fixture",
        "location_id": "LOC_SYNTH",
        "course_key": "launch-101",
        "title": "Launch 101",
        "modules": [
            {"module_key": "welcome", "title": "Welcome", "position": 1, "lessons": [
                # duplicate DISPLAY title, distinct keys -> both must survive
                {"lesson_key": "intro-a", "title": "Introduction", "position": 1,
                 "description": "A"},
                {"lesson_key": "intro-b", "title": "Introduction", "position": 2,
                 "description": "B"},
            ]},
            {"module_key": "build", "parent_module_key": "welcome", "title": "Build",
             "position": 2, "lessons": [
                 {"lesson_key": "first", "title": "First page", "description": "C"}]},
        ],
    }
    if validate_plan(base):
        errors.append(f"valid plan rejected: {validate_plan(base)}")
    if len(identity_map(base)) != 5:
        errors.append(
            f"identity_map should address 2 modules + 3 lessons, got {len(identity_map(base))}")
    if parent_order(base) != ["welcome", "build"]:
        errors.append(f"parent_order wrong: {parent_order(base)}")

    # duplicate module keys
    dup = json.loads(json.dumps(base))
    dup["modules"][1]["module_key"] = "welcome"
    if not any("duplicate module_key" in e for e in validate_plan(dup)):
        errors.append("duplicate module key accepted")

    # duplicate lesson keys within a module
    dupl = json.loads(json.dumps(base))
    dupl["modules"][0]["lessons"][1]["lesson_key"] = "intro-a"
    if not any("duplicate lesson_key" in e for e in validate_plan(dupl)):
        errors.append("duplicate lesson key accepted")

    # unknown parent
    unk = json.loads(json.dumps(base))
    unk["modules"][1]["parent_module_key"] = "ghost"
    if not any("unknown parent" in e for e in validate_plan(unk)):
        errors.append("unknown parent accepted")

    # cycle
    cyc = json.loads(json.dumps(base))
    cyc["modules"][0]["parent_module_key"] = "build"
    cyc["modules"][1]["parent_module_key"] = "welcome"
    if not any("cycle" in e for e in validate_plan(cyc)):
        errors.append("parent cycle accepted")

    # missing content ref on a required lesson
    noc = json.loads(json.dumps(base))
    del noc["modules"][0]["lessons"][0]["description"]
    if not any("no approved content reference" in e for e in validate_plan(noc)):
        errors.append("missing required content accepted")

    # invalid visibility (lesson vocab vs module vocab kept distinct)
    badv = json.loads(json.dumps(base))
    badv["modules"][0]["visibility"] = "hidden"     # legal for a lesson, not a module
    if not any("visibility" in e for e in validate_plan(badv)):
        errors.append("invalid module visibility accepted")

    # cross-location bound object
    cross = json.loads(json.dumps(base))
    cross["modules"][0]["existing_category_id"] = {"id": "cat1", "location_id": "OTHER"}
    if not any("cross-location" in e for e in validate_plan(cross)):
        errors.append("cross-location object id accepted")

    # reducer: everything verified -> delivered
    idm = identity_map(base)
    arts = {"course": {"state": "verified", "verified": True, "object_id": "course1"}}
    for key in idm:
        arts[key] = {"state": "verified", "verified": True, "object_id": f"id-{key}"}
    rec = reduce_delivery(base, arts, content_proof={
        "required": True, "asset_persisted": True, "native_content_ready": True,
        "lesson_association_verified": True, "learner_render_verified": True})
    if rec["state"] != DELIVERY_DELIVERED:
        errors.append(f"all-verified plan should be delivered, got {rec['state']}: {rec['blocking']}")
    if rec["community"]["state"] != "not_requested":
        errors.append("standalone course must not require a community association")

    # reducer: a missing lesson artifact can never be delivered
    partial = dict(arts)
    partial.pop("lesson:welcome/intro-b")
    rec2 = reduce_delivery(base, partial, content_proof={
        "required": True, "lesson_association_verified": True})
    if rec2["state"] == DELIVERY_DELIVERED:
        errors.append("reducer claimed delivered with a missing lesson artifact")
    if not any("lesson:welcome/intro-b" in b for b in rec2["blocking"]):
        errors.append("missing lesson artifact not named in blocking[]")

    # reducer: community required but unverified blocks delivery
    req = json.loads(json.dumps(base))
    req["community"] = {"required": True, "group_ref": "g.json"}
    rec3 = reduce_delivery(req, arts, content_proof={"required": True,
                                                     "lesson_association_verified": True})
    if rec3["state"] == DELIVERY_DELIVERED:
        errors.append("required community association unverified but still delivered")

    # reducer: content required but not association-verified blocks delivery
    rec4 = reduce_delivery(base, arts, content_proof={"required": True})
    if rec4["state"] == DELIVERY_DELIVERED:
        errors.append("required media not association-verified but still delivered")

    # reducer: invalid plan -> failed, never delivered
    rec5 = reduce_delivery(dup, arts)
    if rec5["state"] != DELIVERY_FAILED:
        errors.append("invalid plan must reduce to FAILED")

    # write path round-trip
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = write_delivery_receipt(tmp, rec)
        with open(p, encoding="utf-8") as fh:
            back = json.load(fh)
        if back["schema_version"] != RECEIPT_SCHEMA:
            errors.append("delivery receipt round-trip broken")

    if errors:
        import sys
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — course plan validation + identity map + delivery reducer "
          "(no network / no browser)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="ghl_course_delivery",
        description="Skill-6 course plan validator + logical-key map + delivery reducer.")
    p.add_argument("--selftest", action="store_true",
                   help="Run the no-network self-test and exit.")
    p.add_argument("--validate", metavar="PLAN_JSON",
                   help="Validate a course plan JSON file and print the errors.")
    p.add_argument("--receipt", metavar="RECEIPT_JSON",
                   help="Print a delivery receipt for a plan + artifacts pair.")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.validate:
        with open(args.validate, encoding="utf-8") as fh:
            plan = json.load(fh)
        errs = validate_plan(plan)
        print(json.dumps({"valid": not errs, "errors": errs}, indent=2))
        return 0 if not errs else 1
    if args.receipt:
        with open(args.receipt, encoding="utf-8") as fh:
            doc = json.load(fh)
        rec = reduce_delivery(doc.get("plan") or {}, doc.get("artifacts") or {},
                              community_artifact=doc.get("community_artifact"),
                              content_proof=doc.get("content_proof"))
        print(json.dumps(rec, indent=2, sort_keys=True))
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


__all__ = [
    "PLAN_SCHEMA", "RECEIPT_SCHEMA", "RECEIPT_FILENAME",
    "MODULE_VISIBILITY", "LESSON_VISIBILITY",
    "DELIVERY_DELIVERED", "DELIVERY_INCOMPLETE", "DELIVERY_FAILED",
    "CoursePlanError", "validate_plan", "require_valid_plan",
    "identity_map", "parent_order", "reduce_delivery", "write_delivery_receipt",
]
