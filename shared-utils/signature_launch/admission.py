#!/usr/bin/env python3
"""admission.py - the one admission and completion service (S1 / W11).

WHY THIS EXISTS
---------------
The shared runtime used to accept three things as "finished": a nonempty file
(``progress.recover``), a declared status (``progress.mark``/``complete``), and
any ordinary runner return value (``scheduler/model.normalize_result``, which
turned ``None`` into ``verified_success``).  A fourth, quieter defect was the
denominator: ``progress.percent`` counted a client-dropped unit as delivered
work, so removing work from an approved launch could raise the reported
percentage.

This module is the single callable authority that closes those paths.  It is
one service, not a second ledger: it reads and writes the existing progress
record (``progress.py``) and the existing plan expansion (``scheduler/model.py``).

PUBLIC INTERFACE (what later pairs code against)
------------------------------------------------
identity(**facts)              run/unit/page/stage/item/attempt identity
artifact(path, ...)            one admitted artifact (path or resource id + sha256)
evidence(...)                  the completion evidence object a producer returns
verify_evidence(...)           the canonical validator; failures and facts
is_complete(...)               the completion predicate (verified outcome)
completion_predicate()         the same rule as data, for display/consumers
dimensions(...)                the four distinct status dimensions
required_units(plan)           the required unit set from the existing contracts
denominator(plan)              the one completion denominator
delivered(record)              delivered work and every excluded category
invalidate(record, units, ..)  targeted invalidation with downstream cascade
admit_entry(record, ...)       governed entry admission with resumable status
done_standard(record)          DERIVED export; never a second authority

Stdlib only.  No network, no credentials, no execution.

DELIBERATE CEILING (ponytail): content hashes are re-derived from bytes only
when a caller passes ``root``.  Without it the declared 64-hex hashes are bound
but not recomputed, and the result says ``content_checked: false``.  S2/S3 pass
the run root from the stage gate; nothing here claims byte verification that
did not happen.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = "signature-launch-admission/v1"
SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "signature-launch-contract/v1.0"

_HERE = Path(__file__).resolve().parent
_CONTRACT_DIR = _HERE.parent / "signature_launch_contract"
_HEX64 = re.compile(r"^[a-f0-9]{64}$")
_PLAN_HASH = re.compile(r"^(?:sha256:)?[a-f0-9]{64}$")
# Input hashes are hashes, not free text: a bare 64-hex digest or a
# ``sha256:``-prefixed one.  An arbitrary nonempty string is not an input hash.
_INPUT_HASH = _PLAN_HASH

# Unit kinds come from the EXISTING launch-plan contract
# (signature_launch_contract/launch-plan.schema.json) through
# scheduler/model.py's LANES.  Never invent a parallel taxonomy here.
UNIT_KINDS = ("page", "email_sequence", "text_set", "automation", "commerce_unit")

IDENTITY_REQUIRED = ("tenant", "installation", "skill", "launch_id",
                     "plan_revision", "plan_hash", "unit_id", "unit_kind",
                     "contract_version")
IDENTITY_OPTIONAL = ("page_key", "role", "role_instance", "copy_profile",
                     "viewport", "stage", "item", "attempt_id")

# The four status dimensions.  They are never collapsed into "complete".
DIMENSIONS = ("production", "review", "deployment", "availability")
DIMENSION_VALUES = {
    "production": ("pending", "in_progress", "emitted", "design_ready",
                   "draft", "complete", "removed", "unknown"),
    "review": ("not_required", "required_pending", "approved", "blocked", "unknown"),
    "deployment": ("not_deployed", "local", "draft_installed", "published",
                   "observed", "unknown"),
    "availability": ("available", "unverified", "stale", "superseded", "failed",
                     "blocked", "removed", "unknown"),
}

VERIFIED = "verified"
UNVERIFIED = "unverified"


class AdmissionError(ValueError):
    """Evidence, identity or a record that cannot be trusted. Fail closed."""


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def sha256_text(text):
    return "sha256:" + hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def plan_hash(plan):
    """The one plan hash (progress.py delegates here)."""
    return sha256_text(canonical(plan))


def _model():
    """The existing plan expansion / envelope authority (loaded by path)."""
    path = _HERE / "scheduler" / "model.py"
    spec = importlib.util.spec_from_file_location("signature_launch_admission_model", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _review_record():
    path = _CONTRACT_DIR / "review_record.py"
    spec = importlib.util.spec_from_file_location("signature_launch_admission_review", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _progress():
    """The existing progress ledger (loaded by path: it owns the lock and lease)."""
    path = _HERE / "progress.py"
    spec = importlib.util.spec_from_file_location("signature_launch_admission_progress", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hash(value, field):
    if not isinstance(value, str) or not _PLAN_HASH.match(value.strip()):
        raise AdmissionError("%s must be a sha256 hash, got %r" % (field, value))
    token = value.strip()
    return token if token.startswith("sha256:") else "sha256:" + token


def _digest(value, field):
    """A bare 64-hex content digest (the review record's own vocabulary)."""
    if not isinstance(value, str):
        raise AdmissionError("%s must be a 64-hex sha256 digest" % field)
    token = value.strip()
    if token.startswith("sha256:"):
        token = token[7:]
    if not _HEX64.match(token):
        raise AdmissionError("%s must be a 64-hex sha256 digest" % field)
    return token


def _declared_identity(declared):
    """Re-validate an identity object that carries its computed run/unit keys."""
    clean = {key: value for key, value in declared.items()
             if key not in ("run_key", "unit_key")}
    return identity(**clean)


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------

def identity(**facts):
    """One immutable run/unit identity.

    A human-friendly launch name is never the run id: run identity binds the
    tenant, the installation, the skill, the launch and the approved plan
    revision/hash.  Unknown or missing fields fail closed.
    """
    unknown = sorted(set(facts) - set(IDENTITY_REQUIRED) - set(IDENTITY_OPTIONAL))
    if unknown:
        raise AdmissionError("unknown identity field(s): %s" % ", ".join(unknown))
    missing = [key for key in IDENTITY_REQUIRED if facts.get(key) in (None, "")]
    if missing:
        raise AdmissionError("identity is missing: %s" % ", ".join(missing))
    out = {key: facts.get(key) for key in IDENTITY_REQUIRED + IDENTITY_OPTIONAL
           if facts.get(key) not in (None, "")}
    out["plan_hash"] = _hash(out["plan_hash"], "plan_hash")
    if out["unit_kind"] not in UNIT_KINDS:
        raise AdmissionError("unit_kind %r is not one of %s"
                             % (out["unit_kind"], ", ".join(UNIT_KINDS)))
    try:
        out["skill"] = int(out["skill"])
    except (TypeError, ValueError):
        raise AdmissionError("skill must be an integer")
    out["plan_revision"] = str(out["plan_revision"])
    out["contract_version"] = str(out["contract_version"])
    run_key = sha256_text(canonical({
        "tenant": out["tenant"], "installation": out["installation"],
        "skill": out["skill"], "launch_id": out["launch_id"],
        "plan_revision": out["plan_revision"], "plan_hash": out["plan_hash"],
        "contract_version": out["contract_version"],
    }))
    unit_key = sha256_text(canonical({
        "run_key": run_key, "unit_id": out["unit_id"],
        "stage": out.get("stage"), "item": out.get("item"),
        "attempt_id": out.get("attempt_id"),
    }))
    out["run_key"] = run_key
    out["unit_key"] = unit_key
    return out


def identity_of(plan, unit, *, tenant, installation, skill, plan_revision=None, **optional):
    """Identity for one expanded unit of an approved plan.

    Derives ``unit_kind`` and the plan revision/hash from the plan contract
    instead of asking a caller to retype them.
    """
    revision = plan_revision if plan_revision is not None else \
        (plan.get("approved_plan_hash") or plan_hash(plan))
    return identity(tenant=tenant, installation=installation, skill=skill,
                    launch_id=plan["launch_id"], plan_revision=revision,
                    plan_hash=_plan_hash_of(plan), unit_id=unit["id"],
                    unit_kind=unit["kind"], contract_version=CONTRACT_VERSION,
                    **optional)


def _plan_hash_of(plan):
    """The approved hash when the plan records one, else the canonical hash."""
    recorded = plan.get("approved_plan_hash")
    if isinstance(recorded, str) and _HEX64.match(recorded):
        return "sha256:" + recorded
    return plan_hash(plan)


# --------------------------------------------------------------------------
# artifacts and evidence
# --------------------------------------------------------------------------

def _canonical_path(value):
    """A relative artifact path, or AdmissionError. Absolute/escape paths are
    native resource identities, not file paths."""
    text = str(value or "").strip()
    if not text:
        raise AdmissionError("artifact path is empty")
    pure = Path(text)
    if pure.is_absolute() or text.startswith("~") or "\\" in text or ".." in pure.parts:
        raise AdmissionError("artifact path must be a canonical relative path: %r" % text)
    if text != str(pure):
        raise AdmissionError("artifact path is not normalised: %r" % text)
    return text


def artifact(path=None, sha256=None, *, resource_id=None, kind=None,
             stage=None, attempt_id=None, root=None, bytes_=None):
    """One admitted artifact: its exact identity and content hash.

    ``path`` is a canonical relative path; ``resource_id`` is a native/remote
    resource identity.  Supply ``bytes_`` or ``root`` to derive the hash from
    real content; a declared hash is bound but not recomputed.
    """
    if bool(path) == bool(resource_id):
        raise AdmissionError("artifact needs exactly one of path or resource_id")
    out = {}
    if path:
        out["path"] = _canonical_path(path)
        if bytes_ is not None:
            out["sha256"] = (hashlib.sha256(bytes_).hexdigest()
                             if isinstance(bytes_, (bytes, bytearray))
                             else sha256_text(str(bytes_))[7:])
        elif root is not None:
            target = Path(root) / out["path"]
            if not target.is_file():
                raise AdmissionError("artifact does not exist under root: %s" % out["path"])
            out["sha256"] = sha256_file(target)[7:]
        elif sha256:
            out["sha256"] = _digest(sha256, "artifact sha256")
        else:
            raise AdmissionError("artifact %s has no content hash" % out["path"])
    else:
        out["resource_id"] = str(resource_id)
        if not sha256:
            raise AdmissionError("resource artifact %s has no content hash" % resource_id)
        out["sha256"] = _digest(sha256, "artifact sha256")
    for key, value in (("kind", kind), ("stage", stage), ("attempt_id", attempt_id)):
        if value not in (None, ""):
            out[key] = str(value)
    return out


def evidence(unit, plan_hash_value, artifacts, *, inputs, identity_facts=None,
             review=None, stage=None, attempt_id=None, producer=None,
             revision=None):
    """Build the completion evidence a producer returns.

    Every field is required except ``identity_facts``/``review``/``stage``/
    ``attempt_id``/``producer``/``revision``.  Nothing here decides success;
    ``verify_evidence`` does.
    """
    unit = str(unit or "").strip()
    if not unit:
        raise AdmissionError("evidence needs a unit id")
    arts = list(artifacts or [])
    if not arts:
        raise AdmissionError("evidence needs at least one artifact")
    bound = []
    for entry in arts:
        if isinstance(entry, dict):
            bound.append(dict(entry))
        else:
            bound.append(artifact(entry))
    facts = dict(inputs or {})
    if not facts:
        raise AdmissionError("evidence needs the current input hashes")
    for key, value in facts.items():
        if not isinstance(value, str) or not _INPUT_HASH.match(value.strip()):
            raise AdmissionError("input hash %r must be a sha256 hash, got %r"
                                 % (key, value))
    out = {
        "schema": SCHEMA,
        "unit": unit,
        "plan_hash": _hash(plan_hash_value, "plan_hash"),
        "inputs": {str(key): str(value) for key, value in facts.items()},
        "artifacts": bound,
        "revision": str(revision) if revision is not None else "1",
    }
    if identity_facts is not None:
        out["identity"] = identity_facts if identity_facts.get("run_key") \
            else identity(**identity_facts)
    if review is not None:
        out["review"] = review
    for key, value in (("stage", stage), ("attempt_id", attempt_id),
                       ("producer", producer)):
        if value not in (None, ""):
            out[key] = str(value)
    return out


def _match_identity(want, declared):
    fails = []
    for key, value in want.items():
        if key in ("run_key", "unit_key"):
            continue
        if key in declared and declared.get(key) != value:
            fails.append("evidence identity %s=%r does not match %r"
                         % (key, declared.get(key), value))
    return fails


def verify_evidence(candidate, *, identity_facts=None, require_review=False,
                    root=None, ledger=None, author_session=None,
                    request_id=None, author_model=None,
                    require_model_independence=False,
                    exact_artifact_set=True, unit=None, plan_hash=None):
    """The canonical evidence validator. Returns failures and computed facts.

    A nonempty file, a truthy object, a zero-exit subprocess, a nonempty URL or
    a declared ``status`` are not inputs to this function; they are not
    evidence and can never reach it as success.

    ``unit`` and ``plan_hash`` bind the evidence to the record asking: evidence
    that names a DIFFERENT unit, or was produced under a different plan, is
    refused.  Omit them only for a structural check of an object that is not
    being admitted into a record.
    """
    fails = []
    result = {
        "schema": SCHEMA, "outcome": UNVERIFIED, "ok": False, "reasons": fails,
        "unit": None, "plan_hash": None, "artifacts": [], "artifact_set_hash": None,
        "inputs_hash": None, "content_checked": root is not None,
        "reviewed": False,
    }
    if not isinstance(candidate, dict):
        fails.append("evidence is absent or not an object")
        return result
    if candidate.get("schema") not in (None, SCHEMA):
        fails.append("evidence schema is not %s" % SCHEMA)
    declared_unit = candidate.get("unit")
    if not isinstance(declared_unit, str) or not declared_unit.strip():
        fails.append("evidence names no unit")
    else:
        result["unit"] = declared_unit.strip()
    try:
        result["plan_hash"] = _hash(candidate.get("plan_hash"), "plan_hash")
        result["inputs_hash"] = sha256_text(
            canonical({str(k): str(v) for k, v in (candidate.get("inputs") or {}).items()}))
    except AdmissionError as error:
        fails.append(str(error))
    if unit is not None and result["unit"] != str(unit):
        fails.append("evidence names unit %r, not %r"
                     % (result["unit"], str(unit)))
    if plan_hash is not None:
        try:
            wanted_plan = _hash(plan_hash, "plan_hash")
        except AdmissionError as error:
            wanted_plan = None
            fails.append(str(error))
        if wanted_plan is not None and result["plan_hash"] != wanted_plan:
            fails.append("evidence plan_hash %r does not match the record plan_hash %r"
                         % (result["plan_hash"], wanted_plan))
    inputs = candidate.get("inputs")
    if not isinstance(inputs, dict) or not inputs:
        fails.append("evidence carries no current input hashes")
    else:
        for key, value in inputs.items():
            if not isinstance(value, str) or not _INPUT_HASH.match(value.strip()):
                fails.append("input hash %r is not a hash" % key)
    arts = candidate.get("artifacts")
    if not isinstance(arts, list) or not arts:
        fails.append("evidence carries no artifact: nothing was produced")
        arts = []
    seen = set()
    bound = []
    for entry in arts:
        if not isinstance(entry, dict):
            fails.append("an artifact entry is not an object")
            continue
        path, resource = entry.get("path"), entry.get("resource_id")
        if bool(path) == bool(resource):
            fails.append("an artifact entry needs exactly one of path or resource_id")
            continue
        digest = entry.get("sha256")
        try:
            digest = _digest(digest, "artifact sha256")
        except AdmissionError:
            fails.append("artifact %s lacks a 64-hex sha256" % (path or resource))
            continue
        if path:
            try:
                path = _canonical_path(path)
            except AdmissionError as error:
                fails.append(str(error))
                continue
            if root is not None:
                target = Path(root) / path
                if not target.is_file():
                    fails.append("artifact is missing under root: %s" % path)
                elif sha256_file(target)[7:] != digest:
                    fails.append("artifact bytes changed since admission: %s" % path)
        key = (path, resource, digest)
        if key in seen:
            fails.append("duplicate artifact evidence: %s" % (path or resource))
            continue
        seen.add(key)
        bound.append({"path": path} if path else {"resource_id": str(resource),
                                                  "sha256": digest})
        bound[-1]["sha256"] = digest
        for extra in ("kind", "stage", "attempt_id"):
            if entry.get(extra) not in (None, ""):
                bound[-1][extra] = str(entry[extra])
    result["artifacts"] = bound
    result["artifact_set_hash"] = sha256_text(canonical(
        sorted((a.get("path") or a.get("resource_id"), a["sha256"]) for a in bound)))
    if identity_facts is not None:
        declared = candidate.get("identity")
        if not isinstance(declared, dict):
            fails.append("evidence carries no identity")
        else:
            try:
                fails.extend(_match_identity(identity_facts, _declared_identity(declared)))
            except AdmissionError as error:
                fails.append("evidence identity is not a valid identity: %s" % error)
    elif isinstance(candidate.get("identity"), dict):
        try:
            _declared_identity(candidate["identity"])
        except AdmissionError as error:
            fails.append("evidence identity is not a valid identity: %s" % error)
    elif candidate.get("identity") is not None:
        fails.append("evidence identity is not an object")
    if require_review:
        review = candidate.get("review")
        if not isinstance(review, dict):
            fails.append("independent review is required and absent")
        else:
            review_fails = _review_record().validate_review_record(
                review, ledger=ledger or {}, author_session=author_session,
                artifacts=bound, request_id=request_id,
                author_model=author_model,
                require_model_independence=require_model_independence,
                exact_artifact_set=exact_artifact_set)
            fails.extend(review_fails)
            result["reviewed"] = not review_fails
    if not fails:
        result["ok"] = True
        result["outcome"] = VERIFIED
    return result


def is_complete(candidate, **kwargs):
    """The completion predicate. True only for verified evidence."""
    return verify_evidence(candidate, **kwargs)["ok"]


def completion_predicate():
    """The one completion rule as data, so every consumer cites the same rule."""
    return {
        "schema": SCHEMA,
        "version": SCHEMA_VERSION,
        "requires": [
            "an evidence object naming the unit and the current plan hash",
            "at least one artifact with a 64-hex sha256 (path or resource id)",
            "the current input hashes the output was produced from",
            "identity match when a run/unit identity is supplied",
            "a successful independent review of those exact artifact hashes "
            "when the governing policy requires review",
            "real bytes under a run root when the caller supplies one",
        ],
        "forbids": [
            "None or any ordinary return value",
            "a truthy object, a completed subprocess or exit zero elsewhere",
            "a declared status without evidence",
            "a nonempty file, a nonempty URL or a receipt-shaped local JSON",
            "an unknown or unverifiable result promoted by omission",
        ],
        "never_claims": [
            "byte verification without a supplied root",
            "approval (W12 owns authority; this service verifies evidence only)",
            "a second done ledger; done_standard() is a derived view",
        ],
        "statuses": {"verified": VERIFIED, "unverified": UNVERIFIED},
        "dimensions": list(DIMENSIONS),
        "skip_contributes": 0,
    }


# --------------------------------------------------------------------------
# the four status dimensions
# --------------------------------------------------------------------------

def dimensions(*, production="unknown", review="unknown", deployment="unknown",
               availability="unknown"):
    """Four independent dimensions. Explicitly refuses to collapse them.

    "removed", "draft", "design-only", "emitted", "provider job accepted" and
    "published" are different values here and none of them is "complete".
    """
    out = {"production": production, "review": review,
           "deployment": deployment, "availability": availability}
    for name, value in out.items():
        if value not in DIMENSION_VALUES[name]:
            raise AdmissionError("%s=%r is not one of %s"
                                 % (name, value, ", ".join(DIMENSION_VALUES[name])))
    out["production_complete"] = production == "complete"
    out["ready_to_publish"] = (production == "complete"
                               and availability == "available"
                               and review in ("approved", "not_required"))
    out["published"] = deployment in ("published", "observed")
    # Delivered means the work exists AND is publicly observed; a local or
    # draft-installed artifact is complete work, not delivery.
    out["delivered"] = out["ready_to_publish"] and out["published"]
    return out


def dimension_status(record, uid):
    """Read the four dimensions off one persisted unit's actual facts.

    A unit state alone never proves completion: ``done`` with no verified
    evidence reports production ``emitted`` and availability ``unverified``.
    """
    unit = record["units"].get(uid)
    if unit is None:
        raise AdmissionError("unknown unit: %s" % uid)
    verified = unit.get("verified") is True and unit.get("state") == "done"
    stale = bool(unit.get("stale"))
    superseded = bool(unit.get("superseded"))
    facts = {
        "production": "complete" if verified
        else "in_progress" if unit.get("state") == "running"
        else "emitted" if unit.get("artifact")
        else "pending" if unit.get("state") in ("pending", "failed")
        else "removed" if unit.get("state") == "dropped"
        else "unknown",
        "review": "approved" if (unit.get("review") or {}).get("ok") is True
        else "required_pending" if unit.get("review_required")
        else "not_required",
        "deployment": (unit.get("deployment") or "not_deployed"),
        # Superseded is tested BEFORE stale: a superseded unit is not merely
        # stale, and the stale branch used to shadow this one (D5).
        "availability": "superseded" if superseded
        else "stale" if stale
        else "failed" if unit.get("state") == "failed"
        else "blocked" if unit.get("state") == "blocked"
        else "unverified" if unit.get("state") == "done" and not verified
        else "available",
    }
    return dimensions(**facts)


# --------------------------------------------------------------------------
# required units and the one denominator
# --------------------------------------------------------------------------

def required_units(plan):
    """The required unit set, derived from the existing plan expansion."""
    try:
        expanded = _model().expand_plan(plan)
    except Exception as error:  # ExpansionError, loaded by path
        raise AdmissionError(str(error))
    return [{"id": unit["id"], "kind": unit["kind"], "lane": unit["lane"],
             "waits_for": list(unit["waits_for"]), "family": unit.get("family")}
            for unit in expanded["units"]]


def denominator(plan):
    """The one completion denominator for an approved plan.

    Every unit the existing launch-plan contract requires, including optional
    commerce units.  A dropped, skipped, stale or superseded unit stays in the
    denominator and contributes zero delivered work.
    """
    units = required_units(plan)
    return {
        "schema": SCHEMA,
        "launch_id": plan["launch_id"],
        "plan_hash": plan_hash(plan),
        "approved_plan_hash": _plan_hash_of(plan),
        "revision": str(plan.get("approved_plan_hash") or plan_hash(plan)),
        "required": units,
        "total": len(units),
        "skip_contributes": 0,
        "by_kind": {kind: len([u for u in units if u["kind"] == kind])
                    for kind in UNIT_KINDS},
    }


EXCLUDED_CATEGORIES = ("dropped", "skipped", "stale", "superseded",
                       "unverified_done")


def delivered(record):
    """Delivered work against the one denominator, with every exclusion named.

    The denominator is the required unit set persisted at init
    (``new_progress`` writes ``record["required_units"]``), never the current
    size of the ``units`` dict: editing that dict used to shrink the
    denominator and silently raise the percentage.  A legacy record with no
    persisted set falls back to its own unit ids.  Units missing from the dict,
    or present outside the approved set, are reported as ``drift``.
    """
    units = record.get("units") or {}
    persisted = record.get("required_units")
    required = [str(uid) for uid in persisted] \
        if isinstance(persisted, list) and persisted else list(units)
    required_set = set(required)
    excluded = {name: [] for name in EXCLUDED_CATEGORIES}
    delivered_units = []
    for uid, unit in units.items():
        state = unit.get("state")
        if unit.get("superseded"):
            excluded["superseded"].append(uid)
        elif unit.get("stale"):
            excluded["stale"].append(uid)
        elif unit.get("skipped"):
            excluded["skipped"].append(uid)
        elif state == "dropped":
            excluded["dropped"].append(uid)
        elif state == "done" and unit.get("verified") is not True:
            excluded["unverified_done"].append(uid)
        elif state == "done" and unit.get("verified") is True:
            delivered_units.append(uid)
    delivered_units = [uid for uid in delivered_units if uid in required_set]
    missing = [uid for uid in required if uid not in units]
    extra = sorted(uid for uid in units if uid not in required_set)
    total = len(required)
    count = len(delivered_units)
    return {
        "schema": SCHEMA,
        "launch_id": record.get("launch_id"),
        "plan_hash": record.get("plan_hash"),
        "required": total,
        "required_units": required,
        "drift": {"missing": missing, "extra": extra,
                  "drifted": bool(missing or extra)},
        "delivered": count,
        "delivered_units": delivered_units,
        "percent": round(100.0 * count / total, 2) if total else 0.0,
        "excluded": excluded,
        "skip_contributes": 0,
    }


def done_standard(record):
    """DERIVED done export (never a second editable authority)."""
    view = delivered(record)
    return {
        "schema": "signature-launch-done-standard/v1",
        "derived_from": SCHEMA,
        "authority": "derived-view",
        "editable": False,
        "launch_id": view["launch_id"],
        "plan_hash": view["plan_hash"],
        "required": view["required"],
        "delivered": view["delivered"],
        "percent": view["percent"],
        "done": list(view["delivered_units"]),
        "not_done": sorted(uid for uid in record.get("units") or {}
                           if uid not in set(view["delivered_units"])),
        "excluded": view["excluded"],
    }


# --------------------------------------------------------------------------
# invalidation
# --------------------------------------------------------------------------

def _dependents(record, roots):
    """The changed units plus every unit transitively downstream of them."""
    affected, queue = [], list(roots)
    while queue:
        uid = queue.pop(0)
        if uid in affected or uid not in record["units"]:
            continue
        affected.append(uid)
        for other, unit in record["units"].items():
            if uid in (unit.get("waits_for") or []) and other not in affected:
                queue.append(other)
    return affected


def invalidate(record, units, *, kind, detail=None, clock=_now):
    """Invalidate changed units and only the downstream work they affect.

    An unaffected completed unit keeps its evidence.  A client-dropped unit is
    a decision, not a regression: it stays dropped.
    """
    if kind not in ("brand", "style", "offer", "copy", "prompt", "plan",
                    "approval", "contract", "evidence"):
        raise AdmissionError("unknown invalidation kind: %s" % kind)
    if isinstance(units, str):
        units = [units]
    roots = [uid for uid in (units or []) if uid in record["units"]]
    unknown = [uid for uid in (units or []) if uid not in record["units"]]
    affected = _dependents(record, roots)
    stamp = clock()
    out = {"invalidated": [], "preserved": [], "unknown": unknown}
    for uid in affected:
        unit = record["units"][uid]
        if unit.get("state") == "dropped":
            out["preserved"].append(uid)
            continue
        if unit.get("state") != "done" and unit.get("verified") is not True:
            out["preserved"].append(uid)
            continue
        unit["state"] = "pending"
        unit["verified"] = False
        unit["stale"] = True
        unit["owner"] = None
        unit["lease_expires_at"] = None
        unit["revision"] = int(unit.get("revision") or 1) + 1
        unit["invalidated"] = {"kind": kind, "detail": detail, "at": stamp}
        unit["updated_at"] = stamp
        out["invalidated"].append(uid)
    for uid, unit in record["units"].items():
        if uid not in affected and uid not in out["preserved"]:
            out["preserved"].append(uid)
    out["preserved"] = sorted(set(out["preserved"]))
    return out


# --------------------------------------------------------------------------
# governed entry admission
# --------------------------------------------------------------------------

def _resumable_status(record, uid, now):
    """The same fresh/retry/running/... vocabulary the progress file publishes."""
    unit = record["units"][uid]
    expires = progress_parse(unit.get("lease_expires_at"))
    if unit.get("state") == "running":
        return "running" if expires and expires > now else "stale_running"
    if unit.get("state") in ("done", "dropped"):
        return "terminal"
    if unit.get("missing_facts"):
        return "awaiting_facts"
    if unit.get("state") == "blocked":
        return "blocked"
    if unit.get("state") == "failed":
        return "retry"
    return "fresh"


def progress_parse(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _verified_resolved(record):
    """Unit ids that may unlock dependents: verified done, or client dropped."""
    out = set()
    for uid, unit in record["units"].items():
        if unit.get("state") == "dropped":
            out.add(uid)
        elif unit.get("state") == "done" and unit.get("verified") is True:
            out.add(uid)
    return out


def admit_entry(record, uid, owner, *, now=None, ttl_seconds=900, clock=_now,
                revalidate_stale=True):
    """Governed entry admission with an explicit resumable status.

    Refuses a unit whose dependencies are only self-declared done, a unit that
    claims done without verified evidence, and a late worker holding an attempt
    that is no longer current.  Delegates the lease to ``progress.claim``, so
    concurrency still runs through the existing lock/CAS.
    """
    ledger = _progress()

    unit = record["units"].get(uid)
    if unit is None:
        raise AdmissionError("unknown unit: %s" % uid)
    now = now or progress_parse(ledger._now())
    status = _resumable_status(record, uid, now)
    base = {"schema": SCHEMA, "unit": uid, "resumable_status": status,
            "admitted": False, "attempt": int(unit.get("attempts") or 0)}

    if unit.get("state") == "done":
        if unit.get("verified") is True:
            return {**base, "reason": "already verified complete",
                    "attempt": int(unit.get("attempts") or 0)}
        return {**base, "resumable_status": "unverified_complete",
                "reason": "unit claims done without verified evidence; "
                          "repair or invalidate it explicitly, never re-claim silently"}
    if unit.get("state") == "dropped":
        return {**base, "reason": "client-dropped unit"}

    missing = []
    for dependency in unit.get("waits_for") or []:
        dep = record["units"].get(dependency) or {}
        if dep.get("state") == "dropped":
            continue
        if dep.get("state") == "done" and dep.get("verified") is True:
            continue
        missing.append(dependency if dep.get("state") != "done"
                       else "%s (done, unverified)" % dependency)
    if missing:
        return {**base, "resumable_status": "blocked",
                "reason": "dependencies not verified complete: %s"
                          % ", ".join(missing)}

    if unit.get("stale") and not revalidate_stale:
        return {**base, "reason": "unit evidence is stale"}

    decision = ledger.claim(record, uid, owner, ttl_seconds=ttl_seconds,
                            now=now, clock=clock)
    if not decision.get("claimed"):
        return {**base, "resumable_status": "running"
                if decision.get("reason", "").startswith("held by") else status,
                "reason": decision.get("reason")}
    return {**base, "admitted": True, "resumable_status": "admitted",
            "attempt": int(unit.get("attempts") or 0),
            "reclaimed": bool(decision.get("reclaimed")),
            "lease_expires_at": unit.get("lease_expires_at")}


# --------------------------------------------------------------------------
# self-check
# --------------------------------------------------------------------------

def self_test():
    """Every closed path, proved with the module's own functions."""
    plan = {"launch_id": "admission-selftest",
            "pages": [{"id": "page_landing", "kind": "landing",
                       "url": None, "waits_for": []}]}
    ident = identity_of(plan, required_units(plan)[0], tenant="tenant-a",
                        installation="install-a", skill=83)
    art = artifact("artifacts/landing.html", sha256="a" * 64)
    good = evidence("page_landing", plan_hash(plan), [art],
                    inputs={"plan": plan_hash(plan)}, identity_facts=ident)

    # A real evidence-backed unit completes.
    assert is_complete(good) is True
    assert verify_evidence(good)["artifact_set_hash"].startswith("sha256:")

    # None and ordinary return values are not evidence.
    assert is_complete(None) is False
    assert is_complete("built") is False
    assert is_complete({"ok": True}) is False
    assert verify_evidence({"unit": "page_landing", "plan_hash": plan_hash(plan),
                            "artifacts": [], "inputs": {}})["ok"] is False

    # A declared status is not evidence.
    assert is_complete({"status": "verified_success", "verified": True}) is False

    # Identity mismatch is refused.
    other = identity_of(plan, required_units(plan)[0], tenant="tenant-b",
                        installation="install-a", skill=83)
    assert is_complete(good, identity_facts=other) is False

    # A changed artifact hash no longer matches the review/evidence binding.
    assert is_complete(good, require_review=True) is False

    # The four dimensions never collapse.
    d = dimensions(production="complete", review="approved",
                   deployment="draft_installed", availability="available")
    assert d["production_complete"] is True
    assert d["ready_to_publish"] is True
    assert d["published"] is False and d["delivered"] is False

    # Dropped work stays in the denominator and contributes zero.
    record = {"launch_id": "x", "plan_hash": plan_hash(plan), "units": {
        "a": {"state": "done", "verified": True},
        "b": {"state": "dropped"},
    }}
    assert delivered(record)["percent"] == 50.0
    assert delivered(record)["excluded"]["dropped"] == ["b"]
    assert delivered({"launch_id": "x", "plan_hash": "sha256:" + "0" * 64,
                      "units": {"a": {"state": "done", "verified": False}}}
                     )["excluded"]["unverified_done"] == ["a"]

    # Invalidation cascades downstream and preserves unaffected work.
    record = {"launch_id": "x", "plan_hash": plan_hash(plan), "units": {
        "a": {"state": "done", "verified": True, "waits_for": []},
        "b": {"state": "done", "verified": True, "waits_for": ["a"]},
        "c": {"state": "done", "verified": True, "waits_for": []},
    }}
    report = invalidate(record, ["a"], kind="copy", clock=lambda: "2030-01-01T00:00:00Z")
    assert report["invalidated"] == ["a", "b"], report
    assert record["units"]["c"]["state"] == "done"
    assert record["units"]["b"]["state"] == "pending"
    assert record["units"]["b"]["stale"] is True


if __name__ == "__main__":
    self_test()
    print("admission self-test: PASS")
