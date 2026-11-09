#!/usr/bin/env python3
"""ghl_chat_widget_install.py -- Skill 6 helper for native chat-widget installs.

WHY THIS EXISTS
---------------
Skill 44 owns widget identity and configuration (the public adapter).  Skill 6
owns page work: installing the vendor embed once, at the right scope, without
changing page design, and proving it afterwards.  This helper is that narrow
page-side seam.  The central page/dispatcher hook is WF07's; this module is
called by it and never registers itself.

HARD RULES
----------
* No embed is generated here.  The caller supplies the exact captured snippet,
  script URL, widget id, provenance and evidence reference.  A fabricated script
  URL, attribute or token is refused by the engine validator.
* Only tracking code and custom-code elements are read/written for embed
  detection.  ``sections``/``elements`` (page design) are compared before and
  after and never modified.
* Global and page scope are both inventoried before an install, so the same
  widget cannot be installed twice.
* A rendered bubble is not delivery.  :func:`verify_rendered` and
  :func:`verify_conversation` are separate proofs.

This module imports the engine's frozen widget interface lazily so Skill 6 can
ship standalone; when the engine is absent the helper fails loudly instead of
carrying a second copy of the contract.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ENGINE_ROOT_ENV = "GHL_PUBLIC_ENGINE_ROOT"
_ENGINE: Any = None

_EMBED_ATTR = re.compile(r"<(script|iframe)\b([^>]*)>", re.IGNORECASE)
_SRC_ATTR = re.compile(r"""\bsrc\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_WIDGET_ATTR = re.compile(
    r"""\bdata-widget-id\s*=\s*["']([^"']+)["']""", re.IGNORECASE
)


class InstallerError(RuntimeError):
    """A page-side install refusal.  Never carries a credential value."""


def _engine_root() -> str:
    env = os.environ.get(ENGINE_ROOT_ENV)
    if env:
        return env
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        root = candidate / "44-convert-and-flow-operator" / "tools" / "engine"
        if (root / "cli_anything" / "gohighlevel" / "public").is_dir():
            return str(root)
    raise InstallerError(
        "engine not found: set %s to the Skill 44 engine root" % ENGINE_ROOT_ENV
    )


def widget_api() -> Any:
    """Import the frozen widget interface once."""

    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE
    root = _engine_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    from cli_anything.gohighlevel.public import chat_widgets as module

    _ENGINE = module
    return module


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------

def load_json(path: str) -> Any:
    try:
        return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except OSError as exc:
        raise InstallerError("cannot read %s: %s" % (path, exc)) from exc
    except ValueError as exc:
        raise InstallerError("invalid JSON in %s: %s" % (path, exc)) from exc


def write_json(path: str, value: Any) -> None:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def load_embed(payload: Mapping[str, Any]) -> Any:
    return widget_api().load_embed_instruction(payload)


def load_page_data(path: str) -> dict[str, Any]:
    """Load an editable page blob, accepting the explicit ``pageData`` wrapper."""

    payload = load_json(path)
    if not isinstance(payload, Mapping):
        raise InstallerError("page file must contain a JSON object")
    if "sections" not in payload and isinstance(payload.get("pageData"), Mapping):
        payload = payload["pageData"]
    if not isinstance(payload, Mapping) or "sections" not in payload:
        raise InstallerError(
            "page file is not an editable page blob (no sections; wrapper must be pageData)"
        )
    return dict(payload)


# ---------------------------------------------------------------------------
# inventory (both scopes)
# ---------------------------------------------------------------------------

def _embed_texts(page_data: Any) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if not isinstance(page_data, Mapping):
        return found
    tracking = page_data.get("trackingCode")
    if isinstance(tracking, Mapping):
        for slot in ("head", "body", "headerCode", "footerCode"):
            value = tracking.get(slot)
            if isinstance(value, str) and value:
                found.append(("trackingCode.%s" % slot, value))

    def walk(node: Any, path: str) -> None:
        if isinstance(node, Mapping):
            custom = node.get("customCode")
            if isinstance(custom, Mapping):
                value = custom.get("value")
                if isinstance(value, Mapping) and isinstance(
                    value.get("rawCustomCode"), str
                ):
                    found.append(
                        (path + ".customCode.value.rawCustomCode", value["rawCustomCode"])
                    )
            for key, item in node.items():
                if isinstance(item, (Mapping, list)):
                    walk(item, "%s.%s" % (path, key))
        elif isinstance(node, list):
            for index, item in enumerate(node):
                if isinstance(item, (Mapping, list)):
                    walk(item, "%s[%d]" % (path, index))

    walk(page_data, "pageData")
    return found


def inventory_embeds(
    page_data: Any, *, global_snippets: Sequence[str] = ()
) -> list[dict[str, Any]]:
    """List every script/iframe embed source at global and page scope.

    The scan reports the source and the widget id only when an explicit
    ``data-widget-id`` attribute is present.  It never guesses an identity from
    a URL shape.
    """

    found: list[dict[str, Any]] = []
    for index, snippet in enumerate(global_snippets or ()):
        for match in _EMBED_ATTR.finditer(str(snippet or "")):
            attrs = match.group(2) or ""
            src = _SRC_ATTR.search(attrs)
            widget = _WIDGET_ATTR.search(attrs)
            found.append(
                {
                    "scope": "global",
                    "path": "global[%d]" % index,
                    "tag": match.group(1).lower(),
                    "src": src.group(1) if src else None,
                    "widget_id": widget.group(1) if widget else None,
                }
            )
    for path, text in _embed_texts(page_data):
        for match in _EMBED_ATTR.finditer(text):
            attrs = match.group(2) or ""
            src = _SRC_ATTR.search(attrs)
            widget = _WIDGET_ATTR.search(attrs)
            found.append(
                {
                    "scope": "page",
                    "path": path,
                    "tag": match.group(1).lower(),
                    "src": src.group(1) if src else None,
                    "widget_id": widget.group(1) if widget else None,
                }
            )
    return found


# ---------------------------------------------------------------------------
# install plan, read-back and rollback
# ---------------------------------------------------------------------------

def plan_install(
    page_data: Mapping[str, Any],
    embed_payload: Mapping[str, Any],
    *,
    scope: str = "page",
    slot: str = "footerCode",
    global_snippets: Sequence[str] = (),
) -> dict[str, Any]:
    """Plan exactly one install; return the new blob(s) and the revert blob."""

    module = widget_api()
    try:
        instruction = module.load_embed_instruction(embed_payload)
        if scope == "global":
            updated_global, plan = module.plan_global_install(
                global_snippets, instruction, page_data=page_data
            )
            return {
                "scope": "global",
                "global_snippets": updated_global,
                "page_data": plan.page_data,
                "rollback_page_data": plan.rollback_page_data,
                "install": plan.as_evidence(),
                "embed": instruction.as_dict(),
            }
        if scope != "page":
            raise InstallerError("scope must be 'page' or 'global'")
        plan = module.plan_page_install(
            page_data,
            instruction,
            global_snippets=global_snippets,
            slot=slot,
        )
        return {
            "scope": "page",
            "page_data": plan.page_data,
            "rollback_page_data": plan.rollback_page_data,
            "install": plan.as_evidence(),
            "embed": instruction.as_dict(),
        }
    except module.WidgetError as exc:
        raise InstallerError(str(exc)) from exc


def verify_saved(
    plan: Mapping[str, Any],
    saved_page_data: Mapping[str, Any],
    *,
    global_snippets: Sequence[str] = (),
) -> dict[str, Any]:
    """Read back the saved page: exactly one embed and unchanged page design."""

    module = widget_api()
    instruction = module.load_embed_instruction(plan["embed"])
    planned = plan.get("page_data") or {}
    design_unchanged = planned.get("sections") == saved_page_data.get("sections")
    single = module.verify_install(
        saved_page_data, instruction, global_snippets=global_snippets
    )
    return {
        "verified": bool(single and design_unchanged),
        "single_embed": single,
        "page_design_unchanged": design_unchanged,
        "install": plan.get("install"),
    }


def rollback_blob(plan: Mapping[str, Any]) -> dict[str, Any]:
    blob = plan.get("rollback_page_data")
    if not isinstance(blob, Mapping):
        raise InstallerError("plan has no rollback_page_data")
    return dict(blob)


# ---------------------------------------------------------------------------
# proof helpers (re-exported from the frozen interface)
# ---------------------------------------------------------------------------

def verify_rendered(
    widget_id: str, checks: Mapping[str, Any], *, evidence_ref: str
) -> dict[str, Any]:
    result = widget_api().evaluate_rendered_checks(
        widget_id, checks, evidence_ref=evidence_ref
    )
    return result.as_evidence()


def verify_conversation(
    payload: Mapping[str, Any],
    *,
    expected_widget_id: str,
    expected_location_id: str,
    expected_responder_kind: str,
    require_handoff: bool = False,
    require_after_hours: bool = False,
) -> dict[str, Any]:
    module = widget_api()
    messages = tuple(
        module.MessageEvidence(
            direction=str(item["direction"]),
            body=str(item["body"]),
            message_id=str(item["message_id"]),
        )
        for item in payload.get("messages", ())
    )
    evidence = module.ConversationEvidence(
        widget_id=str(payload.get("widget_id", "")),
        location_id=str(payload.get("location_id", "")),
        thread_id=str(payload.get("thread_id", "")),
        inbox_id=str(payload.get("inbox_id", "")),
        responder_kind=str(payload.get("responder_kind", "")),
        responder_id=str(payload.get("responder_id", "")),
        messages=messages,
        handoff_target=payload.get("handoff_target"),
        handoff_verified=bool(payload.get("handoff_verified")),
        after_hours_verified=bool(payload.get("after_hours_verified")),
        visible_bubble_observed=bool(payload.get("visible_bubble_observed")),
    )
    result = module.verify_conversation_delivery(
        evidence,
        expected_widget_id=expected_widget_id,
        expected_location_id=expected_location_id,
        expected_responder_kind=expected_responder_kind,
        require_handoff=require_handoff,
        require_after_hours=require_after_hours,
    )
    return result.as_evidence()


# ---------------------------------------------------------------------------
# file CLI (offline transforms only)
# ---------------------------------------------------------------------------

def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--embed-file", required=True)
    parser.add_argument("--page-file", required=True)
    parser.add_argument("--global-file", default=None)
    parser.add_argument("--scope", choices=("page", "global"), default="page")
    parser.add_argument("--slot", default="footerCode")
    parser.add_argument("--out", required=True)
    parser.add_argument("--rollback-out", required=True)
    args = parser.parse_args(argv)

    page_data = load_page_data(args.page_file)
    embed = load_json(args.embed_file)
    global_snippets = load_json(args.global_file) if args.global_file else []
    plan = plan_install(
        page_data,
        embed,
        scope=args.scope,
        slot=args.slot,
        global_snippets=global_snippets,
    )
    write_json(args.out, plan)
    write_json(args.rollback_out, rollback_blob(plan))
    print(json.dumps({"install": plan["install"], "out": args.out}, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
