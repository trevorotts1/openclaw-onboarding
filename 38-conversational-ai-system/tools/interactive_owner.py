#!/usr/bin/env python3
"""Single-owner contract for interactive workflow steps (PBB-115 T-19 / C-19).

Every interactive workflow input -- a rendered control press, a provider
callback, free text, or a stale tap from an older step generation -- resolves to
exactly one responder. The default owner is OpenClaw's inbound path. A
``native_ghl`` owner is admitted only when the launch bundle named by the
contract says ``reply_owner.kind == "native_ghl"``.

Deliberate reuse, not a second guard: this module never decides whether a
native GHL translation is approved. That decision belongs to
``launch/qc-launch-conversation-ai.sh`` (REPLY_OWNER_TRANSLATION), so a bundle
without ``translation_approved`` is still admissible here -- the launch gate is
what refuses it. What this module does own is the one-responder rule and the
routing of the four input classes.

Schema validation reuses ``pb_contracts.validate_schema`` (T-08 contract layer).

Run: python3 tools/interactive_owner.py validate --contract <path>
     python3 tools/interactive_owner.py resolve --contract <path> --event <json|path>
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pb_contracts as contracts  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = SKILL_ROOT / "schemas" / "interactive-owner.schema.json"

OWNER_OPENCLAW = "openclaw_inbound"
OWNER_NATIVE_GHL = "native_ghl"
OWNER_KINDS = (OWNER_OPENCLAW, OWNER_NATIVE_GHL)
DEFAULT_OWNER_KIND = OWNER_OPENCLAW

# The three shapes an inbound interaction can take. A stale tap is not a fourth
# shape a provider may claim: it is any control/callback whose generation is
# behind the step's current generation, and it is refused as STALE_TAP.
EVENT_KINDS = ("control", "callback", "free_text")
FREE_TEXT_POLICIES = ("accept", "reject")

# Verdict codes. Refused codes are stable identifiers a caller can assert on.
ROUTED = "ROUTED"
STALE_TAP = "STALE_TAP"
UNKNOWN_STEP = "UNKNOWN_STEP"
UNKNOWN_CONTROL = "UNKNOWN_CONTROL"
FREE_TEXT_REJECTED = "FREE_TEXT_REJECTED"
MALFORMED_EVENT = "MALFORMED_EVENT"
TWO_RESPONDERS = "TWO_RESPONDERS"
NO_RESPONDER = "NO_RESPONDER"
RESPONDER_MISMATCH = "RESPONDER_MISMATCH"
OWNER_NOT_VERIFIED = "OWNER_NOT_VERIFIED"
DUPLICATE_STEP = "DUPLICATE_STEP"
INVALID_STEP = "INVALID_STEP"
INVALID_CONTRACT = "INVALID_CONTRACT"


def _err(code, message):
    return "%s: %s" % (code, message)


def _code_of(message):
    return message.split(":", 1)[0]


def _nonempty(value):
    return isinstance(value, str) and value.strip() != ""


def load_schema():
    return contracts.load_json(SCHEMA_PATH)


def resolve_path(path, base):
    """Resolve ``path`` against ``base`` unless it is already absolute."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return Path(base) / candidate


def load_launch_owner(bundle_path, base):
    """Return the launch bundle's ``reply_owner`` record, or None when absent.

    The caller supplies the path from the interactive contract; a relative path
    resolves against the contract file's own directory so a checkout moves as
    one unit.
    """
    if not _nonempty(bundle_path):
        return None
    bundle = contracts.load_json(resolve_path(bundle_path, base))
    owner = bundle.get("reply_owner") if isinstance(bundle, dict) else None
    return owner if isinstance(owner, dict) else None


def validate_contract(doc, launch_owner=None):
    """Return a list of ``CODE: message`` strings. Empty list means valid.

    ``launch_owner`` is the ``reply_owner`` record read from the contract's
    launch bundle (see ``load_launch_owner``). Passing None means no bundle was
    bound.
    """
    # Schema errors carry the stable INVALID_CONTRACT code so a refused verdict
    # names a code a caller can assert on, never a JSON path like "$". A root
    # that is not an object (null, [], "hello") is refused here, before any
    # semantic rule reads a field from it.
    errs = [_err(INVALID_CONTRACT, e)
            for e in contracts.validate_schema(load_schema(), doc)]
    if errs:
        # The document is malformed; semantic rules would only add noise.
        return errs

    owner = doc.get("owner") or {}
    owner_kind = owner.get("kind") or DEFAULT_OWNER_KIND

    if owner_kind == OWNER_NATIVE_GHL:
        if not _nonempty(owner.get("launch_bundle")):
            errs.append(_err(
                OWNER_NOT_VERIFIED,
                "native_ghl requires owner.launch_bundle naming the launch that "
                "approved it",
            ))
        elif launch_owner is None or launch_owner.get("kind") != OWNER_NATIVE_GHL:
            errs.append(_err(
                OWNER_NOT_VERIFIED,
                "the bound launch bundle does not name native_ghl as its reply owner",
            ))

    responders = doc.get("responders")
    if responders is None:
        responders = [{"id": owner_kind, "kind": owner_kind}]
    if not isinstance(responders, list):
        errs.append(_err(NO_RESPONDER, "responders must be a list"))
    elif not responders:
        errs.append(_err(NO_RESPONDER, "the contract must name one responder"))
    elif len(responders) > 1:
        errs.append(_err(
            TWO_RESPONDERS,
            "exactly one responder may answer an interactive step; got %d (%s)"
            % (len(responders), ", ".join(str(r.get("id")) for r in responders)),
        ))
    else:
        responder = responders[0]
        if responder.get("kind") != owner_kind:
            errs.append(_err(
                RESPONDER_MISMATCH,
                "responder kind %r does not match the owner kind %r"
                % (responder.get("kind"), owner_kind),
            ))

    seen_steps = set()
    for index, step in enumerate(doc.get("steps") or []):
        step_id = step.get("step_id")
        if step_id in seen_steps:
            errs.append(_err(DUPLICATE_STEP, "step_id %r appears twice" % (step_id,)))
        seen_steps.add(step_id)
        if step.get("free_text") not in FREE_TEXT_POLICIES:
            errs.append(_err(
                INVALID_STEP,
                "step %r free_text must be one of %s" % (step_id, list(FREE_TEXT_POLICIES)),
            ))
    return errs


def _owner_record(doc):
    owner = doc.get("owner") or {}
    kind = owner.get("kind") or DEFAULT_OWNER_KIND
    inbound_path = owner.get("inbound_path") or doc.get("inbound_path")
    return {"id": kind, "kind": kind, "inbound_path": inbound_path}


def _refused(code, reason, **extra):
    verdict = {"status": "refused", "code": code, "route": None, "reason": reason}
    verdict.update(extra)
    return verdict


def _malformed(event):
    if not isinstance(event, dict):
        return _refused(MALFORMED_EVENT, "the event must be an object")
    if event.get("kind") not in EVENT_KINDS:
        return _refused(
            MALFORMED_EVENT,
            "event.kind must be one of %s" % (list(EVENT_KINDS),),
        )
    if not _nonempty(event.get("step_id")):
        return _refused(MALFORMED_EVENT, "event.step_id must be a nonempty string")
    generation = event.get("generation")
    if not isinstance(generation, int) or isinstance(generation, bool):
        return _refused(MALFORMED_EVENT, "event.generation must be an integer")
    if event["kind"] in ("control", "callback") and not _nonempty(event.get("control_id")):
        return _refused(
            MALFORMED_EVENT,
            "a %s must name the control_id it pressed" % (event["kind"],),
        )
    return None


def resolve_event(doc, event, launch_owner=None):
    """Resolve one inbound interactive event to its single responder.

    Returns ``{"status": "accepted"|"refused", "code": ..., "route": ...}``.
    A refused event has ``route: None``: no responder answers a stale tap, an
    unknown control, rejected free text, or a contract that names two
    responders.
    """
    errs = validate_contract(doc, launch_owner)
    if errs:
        return _refused(
            _code_of(errs[0]),
            errs[0].split(":", 1)[-1].strip(),
            errors=errs,
        )

    malformed = _malformed(event)
    if malformed:
        return malformed

    steps = {step["step_id"]: step for step in doc["steps"]}
    step = steps.get(event["step_id"])
    if step is None:
        return _refused(UNKNOWN_STEP, "no interactive step %r" % (event["step_id"],))

    if event["generation"] != step["generation"]:
        return _refused(
            STALE_TAP,
            "tap generation %d is behind step %r generation %d"
            % (event["generation"], step["step_id"], step["generation"]),
        )

    owner = _owner_record(doc)
    if event["kind"] == "free_text":
        if step["free_text"] == "reject":
            return _refused(
                FREE_TEXT_REJECTED,
                "step %r does not accept free text" % (step["step_id"],),
            )
        return {
            "status": "accepted",
            "code": ROUTED,
            "route": owner,
            "step_id": step["step_id"],
            "input": "free_text",
        }

    if event["control_id"] not in step["controls"]:
        return _refused(
            UNKNOWN_CONTROL,
            "step %r has no control %r" % (step["step_id"], event["control_id"]),
        )
    return {
        "status": "accepted",
        "code": ROUTED,
        "route": owner,
        "step_id": step["step_id"],
        "input": event["kind"],
        "control_id": event["control_id"],
    }


# Omitting ``event`` means "validate only". A parsed JSON ``null`` is an event
# like any other and must be judged -- it is refused MALFORMED_EVENT -- so the
# validate-only switch cannot be ``None``.
_VALIDATE_ONLY = object()


def resolve_contract(path, event=_VALIDATE_ONLY, launch_bundle=None):
    """Load a contract file and (when given) resolve one event against it."""
    contract_path = Path(path)
    doc = contracts.load_json(contract_path)
    bundle_path = launch_bundle
    # Read the bundle pointer defensively: validation has not run yet, so the
    # document may be any JSON value. A non-object here is refused below.
    owner_doc = doc.get("owner") if isinstance(doc, dict) else None
    if bundle_path is None and isinstance(owner_doc, dict):
        bundle_path = owner_doc.get("launch_bundle")
    launch_owner = None
    if _nonempty(bundle_path):
        launch_owner = load_launch_owner(bundle_path, contract_path.parent)
    if event is _VALIDATE_ONLY:
        errs = validate_contract(doc, launch_owner)
        return {"status": "refused" if errs else "accepted", "errors": errs, "doc": doc}
    return resolve_event(doc, event, launch_owner)


def _usage(message):
    sys.stderr.write("%s\n" % message)
    sys.stderr.write(
        "usage: interactive_owner.py validate --contract <path> [--launch-bundle <path>]\n"
        "       interactive_owner.py resolve --contract <path> --event <json|path> "
        "[--launch-bundle <path>]\n"
    )
    return 2


def _parse_event(value):
    # os.path.isfile answers False for any string that cannot be a path (too
    # long, NUL byte); Path.is_file raises OSError there on Python 3.9, which
    # crashed a long but valid inline event.
    if os.path.isfile(value):
        return contracts.load_json(value)
    # Caller-controlled text: a parse failure is a usage error, the same verdict
    # contracts.load_json gives the same bytes supplied as a file path. A raw
    # json traceback would exit 1 with no verdict at all.
    try:
        return json.loads(value)
    except ValueError as exc:
        raise contracts.UsageError("invalid JSON event: %s" % exc)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return _usage("a command is required")

    command = argv.pop(0)
    if command not in ("validate", "resolve"):
        return _usage("unknown command %r" % (command,))
    args = {}
    while argv:
        flag = argv.pop(0)
        if flag not in ("--contract", "--event", "--launch-bundle"):
            return _usage("unknown argument %r" % (flag,))
        if not argv:
            return _usage("%s needs a value" % (flag,))
        args[flag.lstrip("-").replace("-", "_")] = argv.pop(0)

    contract_path = args.get("contract")
    if not contract_path:
        return _usage("--contract is required")

    try:
        if command == "validate":
            result = resolve_contract(
                contract_path, launch_bundle=args.get("launch_bundle")
            )
            payload = {"status": result["status"], "errors": result["errors"]}
            print(json.dumps(payload, indent=2))
            return 0 if not result["errors"] else 1

        if command == "resolve":
            raw_event = args.get("event")
            if not raw_event:
                return _usage("--event is required for resolve")
            event = _parse_event(raw_event)
            verdict = resolve_contract(
                contract_path, event, args.get("launch_bundle")
            )
            print(json.dumps(verdict, indent=2))
            return 0 if verdict["status"] == "accepted" else 1
    except contracts.UsageError as exc:
        return _usage(str(exc))
    except (OSError, UnicodeError, RecursionError) as exc:
        # A caller path that is a folder or not UTF-8, or input nested past
        # what the parser and checker can walk: "2 = usage or IO", no verdict.
        return _usage("cannot read or check the input: %s" % (exc,))

    return _usage("unknown command %r" % (command,))


if __name__ == "__main__":
    sys.exit(main())
