"""One authoritative unit expansion plus the run result envelope (L03).

WHY THIS EXISTS
---------------
The scheduler, the durable progress file, the package record and the progress
UI each used to decide for themselves what a unit was and what a runner result
meant.  The divergence was observable:

* a runner that *returned* ``{"status": "failed"}`` was recorded ``ok=True`` by
  the scheduler, so its dependents started on top of failed work;
* the scheduler and the progress file expanded plan arrays independently, so a
  new array or kind had to be added twice;
* ``conversation_ai.requested`` (a requested configuration) was read as if it
  wired the reply automation (a separate unit);
* progress ``running`` units were reported as ready by a concurrent resume;
* a stall raised and discarded the partial results and the causal blockers.

This module is the single authority for:

1. ``expand_plan`` -- plan arrays -> ordered unit records (id, kind, lane,
   array, waits_for, family, page facts, requested-AI vs reply-wiring);
2. the result envelope -- ``verified_success``, ``failed``, ``blocked``,
   ``awaiting_facts``, ``dropped`` -- with ``satisfies_dependency`` as the one
   rule the scheduler and the progress file share.  A normally returned
   failure never satisfies a dependency;
3. the small cross-surface mapping tables (package status, UI state) so the
   four surfaces agree by construction instead of by coincidence.

Stdlib only. No network, no credentials, no execution.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ADMISSION = None


def _admission():
    """The one admission/completion service (shared-utils/signature_launch/admission.py).

    Loaded by path so this module stays importable standalone, exactly as
    progress.py loads this one.
    """
    global _ADMISSION
    if _ADMISSION is None:
        path = _HERE.parent / "admission.py"
        spec = importlib.util.spec_from_file_location("signature_launch_model_admission", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _ADMISSION = module
    return _ADMISSION

# array in the launch plan -> (progress kind, scheduler lane)
LANES = (
    ("pages", "page", "page"),
    ("email_sequences", "email_sequence", "email"),
    ("text_sets", "text_set", "text"),
    ("automations", "automation", "automation"),
    # Optional commerce units are units of the SAME approved plan
    # (launch-plan.schema.json); leaving them out made the denominator under-
    # count work a later stage can wait on.
    ("commerce_units", "commerce_unit", "commerce"),
)
ARRAYS = tuple(array for array, _kind, _lane in LANES)
KIND_BY_ARRAY = {array: kind for array, kind, _lane in LANES}
LANE_BY_ARRAY = {array: lane for array, _lane, lane in LANES}

# Envelope statuses.  These are the ONLY outcomes a runner may declare.
VERIFIED_SUCCESS = "verified_success"
FAILED = "failed"
BLOCKED = "blocked"
AWAITING_FACTS = "awaiting_facts"
DROPPED = "dropped"
ENVELOPE_STATUSES = (VERIFIED_SUCCESS, FAILED, BLOCKED, AWAITING_FACTS, DROPPED)

# The single dependency rule.  ``dropped`` is a client decision (terminal), a
# verified success is terminal, and nothing else is.  ``failed`` returned
# normally is a failed unit, never a satisfied dependency.
SATISFIES_DEPENDENCY = frozenset({VERIFIED_SUCCESS, DROPPED})

# Persisted progress state for each envelope status.  The progress file keeps
# its published six-state vocabulary (progress_file.schema.json); awaiting
# facts persists as ``blocked`` with a typed reason so the file stays valid.
PERSISTED_STATE = {
    VERIFIED_SUCCESS: "done",
    FAILED: "failed",
    BLOCKED: "blocked",
    AWAITING_FACTS: "blocked",
    DROPPED: "dropped",
}

# A persisted progress state -> the UI vocabulary used by progress_report.py.
# ``dropped`` is terminal for the launch, so the UI shows it finished.
UI_STATE = {
    "pending": "queued",
    "running": "working",
    "done": "done",
    "failed": "failed",
    "blocked": "blocked",
    "dropped": "done",
}

# Envelope status -> package.py status.  A dropped unit is terminal (the client
# removed it); callers keep the ``dropped`` list so it is never reported as
# delivered work.  awaiting_facts is blocked: the unit cannot start yet.
PACKAGE_STATUS = {
    VERIFIED_SUCCESS: "done",
    FAILED: "failed",
    BLOCKED: "blocked",
    AWAITING_FACTS: "blocked",
    DROPPED: "done",
}

_ALIASES = {
    "done": VERIFIED_SUCCESS,
    "success": VERIFIED_SUCCESS,
    "passed": VERIFIED_SUCCESS,
    "ok": VERIFIED_SUCCESS,
    "verified-success": VERIFIED_SUCCESS,
    "verifiedsuccess": VERIFIED_SUCCESS,
    "failed": FAILED,
    "failure": FAILED,
    "error": FAILED,
    "blocked": BLOCKED,
    "block": BLOCKED,
    "awaiting_fact": AWAITING_FACTS,
    "awaiting-facts": AWAITING_FACTS,
    "awaiting": AWAITING_FACTS,
    "missing_facts": AWAITING_FACTS,
    "dropped": DROPPED,
    "drop": DROPPED,
}


class ExpansionError(ValueError):
    """A plan whose units cannot be trusted. Fail closed."""


def canonical_status(value):
    """Map a runner-declared status to the envelope vocabulary, or None."""
    if not isinstance(value, str):
        return None
    token = value.strip().lower().replace(" ", "_")
    if token in ENVELOPE_STATUSES:
        return token
    return _ALIASES.get(token)


def _blocker(unit, state, detail=None, kind="dependency"):
    blocker = {"unit": str(unit), "state": str(state), "kind": kind}
    if detail:
        blocker["detail"] = str(detail)
    return blocker


def _as_text_list(value, field, unit_id):
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise ExpansionError("%s on %s must be a list" % (field, unit_id))
    out = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def expand_plan(plan):
    """The authoritative expansion: plan -> ordered units + AI wiring.

    Returns ``{"launch_id", "units", "by_id", "order", "ai", "empty"}``.
    Every unit keeps its plan row under ``data`` so a caller never needs a
    second lookup.  Requested Conversation AI configuration is reported under
    ``ai["requested_config"]``; the reply unit is reported separately under
    ``ai["reply_wiring"]``.  Neither is inferred from the other.
    """
    if not isinstance(plan, dict):
        raise ExpansionError("plan must be a JSON object")
    launch_id = str(plan.get("launch_id") or "").strip()
    if not launch_id:
        raise ExpansionError("plan has no launch_id")

    units, seen = [], set()
    for array, kind, lane in LANES:
        rows = plan.get(array)
        if rows is None:
            continue
        if not isinstance(rows, list):
            raise ExpansionError("%s must be a list" % array)
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ExpansionError("%s[%d] is not an object" % (array, index))
            unit_id = str(row.get("id") or "").strip()
            if not unit_id:
                raise ExpansionError("%s has a unit with no id" % array)
            if unit_id in seen:
                raise ExpansionError("duplicate unit id: %s" % unit_id)
            seen.add(unit_id)
            waits = _as_text_list(row.get("waits_for"), "waits_for", unit_id)
            for dependency in waits:
                if dependency == unit_id:
                    raise ExpansionError("%s waits_for itself" % unit_id)
            units.append({
                "id": unit_id,
                "kind": kind,
                "lane": lane,
                "array": array,
                "index": index,
                "waits_for": waits,
                "family": row.get("family"),
                "page_kind": row.get("kind") if lane == "page" else None,
                "url": row.get("url") if lane == "page" else None,
                "data": row,
            })

    for unit in units:
        unknown = [w for w in unit["waits_for"] if w not in seen]
        if unknown:
            raise ExpansionError("unit %s waits_for unknown unit(s): %s"
                                 % (unit["id"], ", ".join(unknown)))

    by_id = {unit["id"]: unit for unit in units}

    ai = plan.get("conversation_ai") or {}
    if not isinstance(ai, dict):
        raise ExpansionError("conversation_ai must be an object")
    requested = ai.get("requested") is True
    mode = ai.get("mode")
    channels = ai.get("channels")
    reply_units = [unit["id"] for unit in units
                   if unit["lane"] == "automation"
                   and unit.get("family") == "conversation_ai_reply"]

    problems = []
    if requested and mode in (None, "", "none"):
        problems.append("conversation_ai requested with no mode")
    if not requested and mode not in (None, "", "none"):
        problems.append("conversation_ai mode set while not requested")
    if reply_units and not requested:
        problems.append("reply automation wired without a requested AI")

    return {
        "launch_id": launch_id,
        "units": units,
        "by_id": by_id,
        "order": [unit["id"] for unit in units],
        "empty": not units,
        "ai": {
            # The requested configuration: what the client asked for.
            "requested_config": {
                "requested": requested,
                "mode": mode,
                "channels": list(channels) if isinstance(channels, list) else [],
                "source": "plan.conversation_ai",
            },
            # The reply-workflow wiring: which unit(s), if any, build replies.
            # Absence is not failure and presence is not proof of configuration.
            "reply_wiring": {
                "family": "conversation_ai_reply",
                "units": reply_units,
                "wired": bool(reply_units),
                "source": "plan.automations",
            },
            "consistent": not problems,
            "problems": problems,
        },
    }


def envelope(status, *, verified=None, detail=None, artifacts=None,
             missing_facts=None, blocker=None, retryable=None, payload=None,
             owner=None, evidence=None):
    """Build one result envelope. Unknown statuses fail closed as ``failed``.

    ``verified_success`` is not a declaration: it is only valid with an
    admission evidence object the one admission service accepts (see
    shared-utils/signature_launch/admission.py).  Without it the result is
    explicitly failed - never silently promoted.
    """
    canonical = canonical_status(status)
    note = detail
    if canonical is None:
        note = "unknown result status %r; treated as failed" % (status,)
        canonical = FAILED
    checked = None
    if canonical == VERIFIED_SUCCESS:
        if verified is False:
            canonical = FAILED
            note = note or "runner declared success without verification"
        else:
            checked = _admission().verify_evidence(evidence) \
                if evidence is not None else None
            if checked is None or not checked["ok"]:
                reasons = "no admission evidence" if checked is None else \
                    "; ".join(checked["reasons"][:3])
                canonical = FAILED
                note = note or ("success is not verified: " + reasons)
            else:
                verified = True
                artifacts = [entry.get("path") or entry.get("resource_id")
                             for entry in checked["artifacts"]]
    # Only a verified success may report ``verified``.  Every other canonical
    # status reports False, so a consumer that reads ``verified`` without also
    # reading ``status`` is never told a failed/blocked/dropped unit verified.
    verified = bool(verified) and canonical == VERIFIED_SUCCESS
    if retryable is None:
        retryable = canonical in (FAILED, AWAITING_FACTS)
    facts = [str(item) for item in (missing_facts or []) if str(item).strip()]
    arts = [str(item) for item in (artifacts or []) if str(item).strip()]
    out = {
        "status": canonical,
        "verified": bool(verified),
        "detail": str(note) if note is not None else None,
        "artifacts": arts,
        "missing_facts": facts,
        "blocker": dict(blocker) if isinstance(blocker, dict) else None,
        "retryable": bool(retryable),
        "payload": payload,
        "owner": str(owner) if owner else None,
    }
    if checked is not None and canonical == VERIFIED_SUCCESS:
        out["evidence"] = evidence
        out["evidence_checked"] = {
            "outcome": checked["outcome"],
            "artifact_set_hash": checked["artifact_set_hash"],
            "inputs_hash": checked["inputs_hash"],
            "content_checked": checked["content_checked"],
            "reviewed": checked["reviewed"],
        }
    if canonical == AWAITING_FACTS and not facts and not out["detail"]:
        out["detail"] = "awaiting facts"
    if canonical == BLOCKED and not out["blocker"] and not out["detail"]:
        out["detail"] = "blocked"
    return out


def _looks_like_evidence(value):
    return isinstance(value, dict) and "artifacts" in value and "unit" in value \
        and "plan_hash" in value


def normalize_result(value, *, evidence=None):
    """Turn any runner return value into one envelope, or an explicit failure.

    Accepted shapes:
      * a declared status -> that envelope; ``verified_success`` is re-checked
        through the admission service (a declared status is not evidence);
      * an evidence object -> verified success only when it validates;
      * a legacy mapping with ``ok=False`` or a truthy ``error`` -> failed;
      * any other normal return, including ``None``, a truthy object or a
        completed subprocess -> FAILED.  A function returning normally is not
        a finished unit.

    The last rule used to promote every return to ``verified_success``; that is
    the manufactured-completion path this closes.
    """
    if isinstance(value, dict) and value.get("status") is not None:
        return envelope(
            value.get("status"),
            verified=value.get("verified"),
            detail=value.get("detail") or value.get("error"),
            artifacts=value.get("artifacts") or (),
            missing_facts=value.get("missing_facts") or (),
            blocker=value.get("blocker"),
            retryable=value.get("retryable"),
            payload=value.get("payload", value.get("result")),
            owner=value.get("owner"),
            evidence=value.get("evidence", evidence),
        )
    if isinstance(value, dict):
        if value.get("ok") is False:
            return envelope(FAILED, detail=value.get("error") or "runner returned ok=False")
        if value.get("error"):
            return envelope(FAILED, detail=value.get("error"))
        if _looks_like_evidence(value):
            return envelope(VERIFIED_SUCCESS, evidence=value,
                            payload=value.get("payload"))
    return envelope(FAILED, detail=(
        "runner returned a value with no admission evidence; a return value, "
        "None, a truthy object or a completed subprocess is not verified success"))


def satisfies_dependency(value):
    """True only for a verified success or an explicit client drop.

    A verified success must carry the admission evidence that verified it: a
    hand-written ``{"status": "verified_success", "verified": true}`` unlocks
    nothing.
    """
    result = value if isinstance(value, dict) and "status" in value else normalize_result(value)
    status = canonical_status(result.get("status"))
    if status == DROPPED:
        return True
    if status == VERIFIED_SUCCESS:
        if result.get("verified") is not True:
            return False
        evidence = result.get("evidence")
        if evidence is None:
            return False
        return _admission().verify_evidence(evidence)["ok"]
    return False


def package_status(value):
    """The package.py status for one outcome (read-only mapping table)."""
    result = value if isinstance(value, dict) and "status" in value else normalize_result(value)
    return PACKAGE_STATUS[result["status"]]


def ui_state(state):
    """The progress_report.py state for one persisted progress state."""
    return UI_STATE.get(str(state), "queued")


def causal_blockers(unit_id, by_id, resolved):
    """Direct and root causes keeping ``unit_id`` from starting.

    ``resolved`` is the set of unit ids whose envelope satisfied a dependency
    (verified success or dropped).  A failed/blocked/awaiting unit is named,
    and a failed dependency is followed to the failures behind it so a stall
    report carries causes, not just the first edge.
    """
    unit = by_id.get(unit_id)
    if unit is None:
        return []
    out, seen = [], set()

    def walk(dependency, depth):
        if dependency in seen or dependency not in by_id:
            return
        seen.add(dependency)
        if dependency in resolved:
            return
        dep_unit = by_id[dependency]
        out.append(_blocker(dependency, "unresolved",
                            "waits for %s" % dependency))
        if depth < 8:
            for parent in dep_unit.get("waits_for") or []:
                walk(parent, depth + 1)

    for dependency in unit.get("waits_for") or []:
        walk(dependency, 0)
    return out


def read_json(path):
    """Small helper so script and package callers agree on one read rule."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
