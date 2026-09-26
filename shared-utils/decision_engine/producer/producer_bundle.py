#!/usr/bin/env python3
"""D24 producer bundle + dispatch parity (JEV spec 1.1, ss 10.5/10.6; A26/A35/A37/A38).

A producer that already resolved a full compatible bundle passes that same
decision through ingest. This module validates company, source provenance,
catalog/content versions, schema, hash, and confirmation evidence through the
REAL D02 validators, then reuses the bundle (no re-selection). Bare persona
IDs are attribution claims, never proof: they are rejected as forged
confirmation. Auto and manual dispatch consume the same committed snapshot.

Imports the REAL D02 ``contracts/schema.py`` validators and the REAL D20
``parts`` ``validate_part`` (file-location loading, repo convention) — never
reimplemented. D20 pending correction ``emit_bundle_scope_goal`` (onb-d20
``b16cc12e``) is used when present; otherwise the same mapping runs here
against the same REAL validators, so both paths prove identical D02 shape.

Stdlib only. No network, no provider access, no state writes. Validators
return ``(ok, errors)`` fail-closed; deciders raise ValueError on bad input
(never a silent default).

ponytail: confirmation evidence is structural (confirmation object OR
already-confirmed provenance), ceiling is cryptographic attestation;
upgrade path is a signature check behind the same ``confirmation`` field
(no API change).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

__all__ = [
    "PROVENANCE_SOURCES",
    "check_redispatch",
    "ingest_producer_bundle",
    "parts_to_bundle",
    "prepare_dispatch",
]

# D02 audience/goal provenance values that count as already-confirmed
# evidence (no re-ask owed). Anything else needs an envelope confirmation.
CONFIRMED_SOURCES = ("operator_confirmed",)
MECHANICAL_SOURCES = ("n/a",)

# Envelope keys a producer decision must carry beyond bare-ID claims.
PROVENANCE_SOURCES = (
    "operator_confirmed",
    "onboarding_icp",
    "asked",
    "n/a",
)


def _by_path(mod_name, path):
    """Load the REAL module at path (offline test convention)."""
    import importlib.util
    import sys
    existing = sys.modules.get(mod_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


_here = Path(__file__).resolve()
_de = _here.parent.parent

_schema = _by_path(
    "d24_decision_engine_contracts_schema", _de / "contracts" / "schema.py")
_parts = _by_path("d24_parts", _de / "parts" / "__init__.py")
_FIX = _de / "contracts" / "fixtures"


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _confirmation_evidenced(envelope, bundle) -> tuple[bool, str]:
    """Structural confirmation evidence (never a bare-ID claim)."""
    if bundle.get("no_persona_required") is True:
        return True, "mechanical: no persona required"
    if isinstance(envelope.get("confirmation"), dict):
        return True, "envelope confirmation object present"
    if bundle.get("confirm_required") is False:
        ra = bundle.get("resolved_audience") or {}
        rg = bundle.get("resolved_goal") or {}
        goal_src = bundle.get("goal_source")
        audience_ok = ra.get("source") in CONFIRMED_SOURCES
        goal_ok = (
            rg.get("source") in CONFIRMED_SOURCES
            or (not (bundle.get("conversion_goal") or "").strip()
                and rg.get("source") in MECHANICAL_SOURCES
                and goal_src in MECHANICAL_SOURCES)
        )
        if audience_ok and goal_ok:
            return True, "already-confirmed audience+goal provenance"
        return False, (
            "confirm_required is false but audience/goal provenance is not "
            "already-confirmed (re-ask owed, not evidenced)"
        )
    return False, "confirmation unproven: confirmation object absent"


def ingest_producer_bundle(envelope, *, company_id, catalog_version,
                           head_revision=None, input_hash=None,
                           ) -> tuple[bool, list[str], dict | None]:
    """Validate a producer-supplied full bundle, then reuse it. Never raises.

    Returns ``(ok, errors, bundle)``: on success ``bundle`` is the reused
    bundle (deep copy, every D02 field preserved). Bare persona IDs or
    partial dicts fail as forged confirmation; stale revisions/hashes fail
    instead of overwriting a newer task decision; unconfirmed bundles fail
    instead of bypassing persona confirmation.
    """
    try:
        if isinstance(envelope, str) or not isinstance(envelope, dict):
            return False, [
                "forged confirmation: bare persona ID %r is an attribution "
                "claim, not proof of a complete confirmed bundle"
                % (envelope,)
            ], None
        if ("schemaVersion" not in envelope or "decisionId" not in envelope
                or "personaBundle" not in envelope):
            return False, [
                "forged confirmation: ID-only claim without a full "
                "decision envelope + personaBundle proves nothing"
            ], None
        errors: list[str] = []
        ok, errs = _schema.validate_envelope(envelope)
        if not ok:
            return False, ["schema: " + e for e in errs], None
        if envelope.get("companyId") != company_id:
            errors.append(
                "company mismatch: envelope companyId=%r != expected %r"
                % (envelope.get("companyId"), company_id))
        bundle = envelope.get("personaBundle")
        if envelope.get("status") == "committed":
            if not isinstance(bundle, dict):
                errors.append("committed producer bundle must be an object")
                return False, errors, None
            if not (isinstance(envelope.get("bundleHash"), str)
                    and envelope["bundleHash"].strip()):
                errors.append("committed producer bundle missing bundleHash")
            if (envelope.get("candidateCatalogVersion") != catalog_version
                    or bundle.get("catalog_version") != catalog_version):
                errors.append(
                    "catalog/content version mismatch: envelope=%r bundle=%r "
                    "expected=%r" % (
                        envelope.get("candidateCatalogVersion"),
                        bundle.get("catalog_version"), catalog_version))
            if (bundle.get("catalog_version")
                    != envelope.get("candidateCatalogVersion")):
                errors.append(
                    "content version drift: bundle catalog_version=%r != "
                    "envelope candidateCatalogVersion=%r" % (
                        bundle.get("catalog_version"),
                        envelope.get("candidateCatalogVersion")))
            ra = bundle.get("resolved_audience") or {}
            if ra.get("source") not in PROVENANCE_SOURCES:
                errors.append(
                    "source provenance %r not evidenced" % (ra.get("source"),))
            evidenced, why = _confirmation_evidenced(envelope, bundle)
            if not evidenced:
                errors.append("persona confirmation bypass refused: " + why)
        if (head_revision is not None
                and _is_int(envelope.get("decisionRevision"))
                and envelope["decisionRevision"] < head_revision):
            errors.append(
                "stale producer decision: revision %r is older than task "
                "head %r (refuses to overwrite a newer task decision)"
                % (envelope["decisionRevision"], head_revision))
        if (input_hash is not None
                and envelope.get("inputHash") != input_hash):
            errors.append(
                "stale producer input: inputHash %r != current %r"
                % (envelope.get("inputHash"), input_hash))
        if errors:
            return False, errors, None
        return True, [], copy.deepcopy(bundle)
    except Exception as exc:  # fail-closed: validator never raises
        return False, ["validator error: %s" % (exc,)], None


def parts_to_bundle(parts) -> dict:
    """Map validated D20 parts into D02 task_personas rows. Raises.

    Every part is validated by the REAL D20 ``validate_part``; per-part
    scope_id/seq/goal/conversion_goal travel as additive row extensions
    (``scope_id``/``goal``/``conversion_goal`` keys plus ``why``/``part``
    provenance strings). The first non-empty conversion_goal seeds the
    bundle ``conversion_goal``/``resolved_goal.value`` (D02 "empty when
    unresolved"). The emitted bundle revalidates clean through the REAL
    D02 ``validate_persona_bundle``. Returns ``{envelope, bundle}``.
    """
    if not isinstance(parts, (list, tuple)):
        raise ValueError(
            "parts: required non-empty list (got %s)"
            % type(parts).__name__)
    if not parts:
        raise ValueError("parts: required non-empty list (got empty)")
    if hasattr(_parts, "emit_bundle_scope_goal"):
        # Pending D20 correction path exists: cross-check our row count and
        # seq set against it so both mappings stay identical.
        ref = _parts.emit_bundle_scope_goal(list(parts))
        ref_rows = ref["bundle"]["task_personas"]
        ref_seq = sorted(r["seq"] for r in ref_rows)
        got_seq = sorted(p["seq"] for p in parts)
        if ref_seq != got_seq:
            raise ValueError(
                "D20 emit cross-check mismatch: ref seq %r != parts seq %r"
                % (ref_seq, got_seq))
    carrier = json.loads(
        (_FIX / "envelope_committed.json").read_text(encoding="utf-8"))
    template_rows = carrier["personaBundle"]["task_personas"]
    template_pid = template_rows[0]["persona_id"]
    template_category = template_rows[0]["task_category"]
    if len(parts) > 10:
        raise ValueError(
            "parts: %d rows exceed D02 up-to-10 task_personas cap"
            % len(parts))
    seen_seq: set = set()
    rows: list[dict] = []
    for i, part in enumerate(parts):
        where = "parts[%d]" % i
        ok, errs = _parts.validate_part(part)
        if not ok:
            raise ValueError("%s: invalid part: %s" % (where, "; ".join(errs)))
        seq = part["seq"]
        if seq in seen_seq:
            raise ValueError("%s: duplicate seq %r" % (where, seq))
        seen_seq.add(seq)
        rows.append({
            "seq": seq,
            "part": part["part_id"],
            "persona_id": template_pid,
            "why": "scope %r goal %r (source %r)" % (
                part["scope_id"], part["goal"], part["source"]),
            "no_persona_required": False,
            "governance_persona_id": None,
            "task_category": template_category,
            "scope_id": part["scope_id"],
            "goal": part["goal"],
            "conversion_goal": part["conversion_goal"],
        })
    bundle = copy.deepcopy(carrier["personaBundle"])
    bundle["task_personas"] = sorted(rows, key=lambda r: r["seq"])
    resolved = next(
        (p["conversion_goal"] for p in parts
         if isinstance(p.get("conversion_goal"), str)
         and p["conversion_goal"].strip()),
        "")
    resolved = resolved.strip()
    bundle["conversion_goal"] = resolved
    rg = bundle.get("resolved_goal")
    if isinstance(rg, dict):
        rg = copy.deepcopy(rg)
        rg["value"] = resolved
        bundle["resolved_goal"] = rg
    ok, errs = _schema.validate_persona_bundle(
        bundle, company_id=carrier["companyId"])
    if not ok:
        raise ValueError(
            "emitted bundle failed REAL D02 validation: %s" % "; ".join(errs))
    envelope = copy.deepcopy(carrier)
    envelope["personaBundle"] = copy.deepcopy(bundle)
    ok, errs = _schema.validate_envelope(envelope)
    if not ok:
        raise ValueError(
            "emitted envelope failed REAL D02 validation: %s"
            % "; ".join(errs))
    return {"envelope": envelope, "bundle": bundle}


def check_redispatch(current, candidate) -> dict:
    """Same unchanged re-dispatch reuses; changed scope revises. Raises.

    Returns ``{reuse, reason, revision}``: ``reuse=True`` only when
    scopeId, inputHash, and bundleHash all match; otherwise ``reuse=False``
    with an auditable reason naming the first difference and the next
    ``decisionRevision``.
    """
    for name, env in (("current", current), ("candidate", candidate)):
        if not isinstance(env, dict):
            raise ValueError("%s: required decision envelope dict" % name)
        for key in ("scopeId", "inputHash", "bundleHash", "decisionRevision"):
            if key not in env:
                raise ValueError("%s: missing required key %r" % (name, key))
    if candidate["scopeId"] != current["scopeId"]:
        reason = "scope_changed: %r -> %r" % (
            current["scopeId"], candidate["scopeId"])
    elif candidate["inputHash"] != current["inputHash"]:
        reason = "input_changed: %r -> %r" % (
            current["inputHash"], candidate["inputHash"])
    elif candidate["bundleHash"] != current["bundleHash"]:
        reason = "bundle_changed: %r -> %r" % (
            current["bundleHash"], candidate["bundleHash"])
    else:
        return {"reuse": True, "reason": "unchanged: reuse committed",
                "revision": current["decisionRevision"]}
    revision = current["decisionRevision"]
    if not _is_int(revision):
        raise ValueError("current: decisionRevision must be int >= 0")
    return {"reuse": False, "reason": reason, "revision": revision + 1}


def prepare_dispatch(envelope, *, mode, operator_lock_persona_id=None) -> dict:
    """One dispatch snapshot for auto and manual paths. Raises.

    Consumes the committed envelope and states the selection is already
    assigned (``reselect_prohibited=True``). Renderer load references cover
    ALL applicable roles (voice winner, every task_persona, governance and
    default fallbacks). An operator persona lock contradicting the bundle
    returns ``needs_rescore`` instead of coexisting with a stale blend.
    """
    if mode not in ("auto", "manual"):
        raise ValueError("mode: must be 'auto' or 'manual'")
    if not isinstance(envelope, dict):
        raise ValueError("envelope: required decision envelope dict")
    if envelope.get("status") != "committed":
        raise ValueError(
            "dispatch requires a committed decision (got status %r)"
            % (envelope.get("status"),))
    bundle = envelope.get("personaBundle")
    if not isinstance(bundle, dict):
        raise ValueError("dispatch requires a committed personaBundle object")
    if (operator_lock_persona_id is not None
            and operator_lock_persona_id != bundle.get("persona_id")):
        return {
            "dispatched": False,
            "needs_rescore": True,
            "mode": mode,
            "reason": "operator lock %r contradicts bundle persona %r: "
                      "rescore/amend, never coexist with a stale blend"
                      % (operator_lock_persona_id, bundle.get("persona_id")),
        }
    refs: list[str] = []
    winner = bundle.get("persona_id")
    if isinstance(winner, str) and winner:
        refs.append(winner)
    for row in bundle.get("task_personas") or []:
        pid = row.get("persona_id") if isinstance(row, dict) else None
        if isinstance(pid, str) and pid and pid not in refs:
            refs.append(pid)
    fallbacks = bundle.get("fallbacks") or {}
    for key in ("governance", "default_persona"):
        pid = fallbacks.get(key)
        if isinstance(pid, str) and pid and pid not in refs:
            refs.append(pid)
    snapshot = copy.deepcopy(envelope)
    return {
        "dispatched": True,
        "needs_rescore": False,
        "mode": mode,
        "selection_assigned": True,
        "reselect_prohibited": True,
        "snapshot": snapshot,
        "renderer_load_references": refs,
        "scope_id": envelope.get("scopeId"),
        "decision_revision": envelope.get("decisionRevision"),
        "bundle_hash": envelope.get("bundleHash"),
    }
