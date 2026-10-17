#!/usr/bin/env python3
"""selection_runtime.py - Skill 78 runtime adapter (S78 runtime lane).

One fail-closed facade between the launch runtime and the skill's shipped
modules. The runtime sends a request envelope {"action": ..., ...args};
the adapter dispatches to exactly one shipped function and returns
{"ok": true, "action": ..., "result": ...} or
{"ok": false, "error": {"code": ..., "message": ...}}.

Actions: invocation, plan, preview, select, validate_binding,
reject_query_authority, binding_plan, page_result, session_create,
session_resume, session_confirm.

Session storage is chosen when the Runtime is constructed, never by the
request: store={"kind": "memory"} (default) or
store={"kind": "durable", "base_dir": <path>} for the production
tenant-scoped durable store in selection_session_store.py. A request
cannot redirect storage, widen its own authority, or smuggle a price:
select re-runs the core approval checks, and reject_query_authority is
exposed so the runtime can screen inbound query strings.

Usage:
  selection_runtime.py <request.json> [--durable-base <dir>]
  selection_runtime.py --self-test
Exit: 0 ok, 2 violation, 3 fail-closed error (bad request, storage, unknown action).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_selection_plan import SELF_TEST_LAUNCH, build_plan  # noqa: E402
from emit_binding_plan import emit_plan  # noqa: E402
from emit_page_result import emit as emit_page_result  # noqa: E402
from render_selection_preview import render  # noqa: E402
from selection_core import (  # noqa: E402
    Violation, build_selection, check_invocation, reject_query_authority, validate_binding,
)
from selection_session import SessionStore  # noqa: E402
from selection_session_store import DurableSessionStore, StorageError  # noqa: E402

V_RUNTIME_BAD_REQUEST = "S78-RUNTIME-BAD-REQUEST"
V_RUNTIME_UNKNOWN_ACTION = "S78-RUNTIME-UNKNOWN-ACTION"

ACTIONS = (
    "invocation", "plan", "preview", "select", "validate_binding",
    "reject_query_authority", "binding_plan", "page_result",
    "session_create", "session_resume", "session_confirm",
)


class BadRequest(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.code = V_RUNTIME_BAD_REQUEST
        self.message = message


def _need(request, key):
    if key not in request or request[key] is None:
        raise BadRequest(f"request is missing required field {key!r}")
    return request[key]


class Runtime:
    def __init__(self, store=None):
        if store is None:
            store = {"kind": "memory"}
        kind = store.get("kind", "memory")
        if kind == "memory":
            self.store = SessionStore(ttl_seconds=int(store.get("ttl_seconds", 1800)))
        elif kind == "durable":
            base = store.get("base_dir")
            if not base:
                raise BadRequest("durable store requires base_dir at construction")
            self.store = DurableSessionStore(base, ttl_seconds=int(store.get("ttl_seconds", 1800)))
        else:
            raise BadRequest(f"unknown store kind {kind!r}")

    def handle(self, request):
        if not isinstance(request, dict):
            return self._err(V_RUNTIME_BAD_REQUEST, "request envelope must be a JSON object")
        action = request.get("action")
        try:
            if action == "invocation":
                result = {"mode": check_invocation(_need(request, "launch"))}
            elif action == "plan":
                result = build_plan(
                    _need(request, "launch"),
                    request.get("recommendation"),
                    production=bool(request.get("production", False)),
                )
            elif action == "preview":
                result = {"html": render(_need(request, "plan"), state=request.get("state", "default"))}
            elif action == "select":
                result = build_selection(
                    _need(request, "launch"),
                    offer_id=_need(request, "offer_id"),
                    price_choice_id=_need(request, "price_choice_id"),
                    quantity=int(request.get("quantity", 1)),
                    selected_at=_need(request, "selected_at"),
                    source_page_id=_need(request, "source_page_id"),
                    session_ref=_need(request, "session_ref"),
                )
            elif action == "validate_binding":
                validate_binding(
                    _need(request, "selection"),
                    _need(request, "launch"),
                    expected_revision=int(_need(request, "expected_revision")),
                )
                result = {"valid": True}
            elif action == "reject_query_authority":
                reject_query_authority(_need(request, "query"))
                result = {"accepted": True}
            elif action == "binding_plan":
                result = emit_plan(
                    _need(request, "launch"),
                    _need(request, "targets"),
                    route=request.get("route", "per_offer_targets"),
                )
            elif action == "page_result":
                page_request = request.get("page_request") or request.get("request")
                result = emit_page_result(
                    _need(request, "plan"),
                    author_session=_need(request, "author_session"),
                    request_id=request.get("request_id") or (page_request.get("request_id") if isinstance(page_request, dict) else None) or _need(request, "request_id"),
                    page_id=request.get("page_id"),
                    input_hash=request.get("input_hash"),
                    request=page_request if isinstance(page_request, dict) else None,
                    test_only=bool(request.get("test_only", False)),
                )
            elif action == "session_create":
                ref = self.store.create(_need(request, "selection"), now=int(_need(request, "now")))
                result = {"session_ref": ref}
            elif action == "session_resume":
                result = self.store.resume(
                    _need(request, "session_ref"),
                    tenant_id=_need(request, "tenant_id"),
                    launch_id=_need(request, "launch_id"),
                    launch=_need(request, "launch"),
                    now=int(_need(request, "now")),
                )
            elif action == "session_confirm":
                result = self.store.confirm(
                    _need(request, "session_ref"),
                    tenant_id=_need(request, "tenant_id"),
                    launch_id=_need(request, "launch_id"),
                    launch=_need(request, "launch"),
                    now=int(_need(request, "now")),
                )
            else:
                return self._err(V_RUNTIME_UNKNOWN_ACTION, f"unknown action {action!r}")
        except Violation as v:
            return self._err(v.code, v.message)
        except StorageError as e:
            return self._err(e.code, e.message)
        except BadRequest as e:
            return self._err(e.code, e.message)
        except Exception as e:  # fail closed: never leak a traceback as a result
            return self._err(V_RUNTIME_BAD_REQUEST, f"request could not be processed: {e}")
        return {"ok": True, "action": action, "result": result}

    @staticmethod
    def _err(code, message):
        return {"ok": False, "error": {"code": code, "message": message}}


def self_test():
    rt = Runtime()
    out = rt.handle({"action": "plan", "launch": SELF_TEST_LAUNCH})
    assert out["ok"] and out["result"]["outcome"] == "plan", out
    pr = rt.handle({
        "action": "page_result", "plan": out["result"], "author_session": "self-test",
        "request_id": "self-test-request", "page_id": "SELF-TEST-SELECTION-PAGE",
        "input_hash": "c" * 64, "test_only": True,
    })
    assert pr["ok"], pr
    assert pr["result"]["page_id"] == "SELF-TEST-SELECTION-PAGE"
    assert pr["result"]["input_hash"] == "c" * 64
    assert "outcome" not in pr["result"]
    no_echo = rt.handle({
        "action": "page_result", "plan": out["result"], "author_session": "self-test",
        "request_id": "self-test-request",
    })
    assert not no_echo["ok"], no_echo
    sel = rt.handle({
        "action": "select", "launch": SELF_TEST_LAUNCH, "offer_id": "MAIN-B",
        "price_choice_id": "MAIN-B-USD", "selected_at": "2026-10-15T20:00:00Z",
        "source_page_id": "TEST-SELECTION", "session_ref": "opaque",
    })
    assert sel["ok"], sel
    created = rt.handle({"action": "session_create", "selection": sel["result"], "now": 1000})
    assert created["ok"], created
    ref = created["result"]["session_ref"]
    resumed = rt.handle({
        "action": "session_resume", "session_ref": ref, "tenant_id": "TEST-TENANT",
        "launch_id": "TEST-LAUNCH", "launch": SELF_TEST_LAUNCH, "now": 1100,
    })
    assert resumed["ok"] and resumed["result"]["state"] == "resumed", resumed
    smuggle = rt.handle({"action": "reject_query_authority", "query": {"price": "97"}})
    assert not smuggle["ok"] and smuggle["error"]["code"] == "S78-QUERY-PRICE-AUTHORITY", smuggle
    unknown = rt.handle({"action": "nonsense"})
    assert not unknown["ok"] and unknown["error"]["code"] == V_RUNTIME_UNKNOWN_ACTION, unknown
    bad = json.loads(json.dumps(SELF_TEST_LAUNCH))
    bad["offers"][0]["prices"][0]["amount_minor"] = None
    bad["offers"][0]["prices"][0]["approval_status"] = "unknown"
    rejected = rt.handle({"action": "plan", "launch": bad})
    assert not rejected["ok"] and rejected["error"]["code"] == "S78-UNKNOWN-PRICE", rejected
    print("selection_runtime --self-test: PASS (plan, select, session round trip, query authority, unknown action, violation mapping)")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    args = [a for a in argv[1:] if not a.startswith("--")]
    if not args:
        print("usage: selection_runtime.py <request.json> [--durable-base <dir>] | --self-test", file=sys.stderr)
        return 3
    store = {"kind": "memory"}
    if "--durable-base" in argv:
        store = {"kind": "durable", "base_dir": argv[argv.index("--durable-base") + 1]}
    try:
        request = json.loads(Path(args[0]).read_text())
        out = Runtime(store).handle(request)
    except Exception as e:  # fail closed
        print(f"FAIL-CLOSED: {e}", file=sys.stderr)
        return 3
    print(json.dumps(out, indent=2))
    if out["ok"]:
        return 0
    fail_closed = (V_RUNTIME_BAD_REQUEST, V_RUNTIME_UNKNOWN_ACTION, "S78-SESSION-STORAGE")
    return 3 if out["error"]["code"] in fail_closed else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
