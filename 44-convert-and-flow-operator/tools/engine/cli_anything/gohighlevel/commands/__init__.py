"""Family command modules, registered exactly once by the CLI owner (WF03).

A family module lands in this package ONLY after its owner lane publishes an
approved interface checkpoint. Each module exposes ``register(cli)`` — it is
called with the root click group and nothing else is assumed. A module that is
absent is PENDING with its owning workflow id; it is never replaced by a stub
that returns success (Document 1 s21.7, Document 2 WF03).

Registration is idempotent per process: calling :func:`apply_families` twice
never adds the same family twice.
"""
from __future__ import annotations

import importlib

#: Family module name -> owning workflow id (Document 1 s21.7 proposals).
FAMILIES: dict[str, str] = {
    "courses": "WF06",
    "capabilities": "WF01",
    "agency": "WF05",
    "community": "WF10",
    "workflow_monitoring": "WF25",
    "meeting_rooms": "WF26",
    "voice_ai": "WF27",
    "conversation_ai": "WF28",
    "agent_studio": "WF29",
    "knowledge_bases": "WF30",
    "chat_widgets": "WF31",
    "projects": "WF32",
    "marketing_quizzes": "WF34",
}

#: Why a family that has no module is still owed, when "module not delivered"
#: is not the whole truth. A family whose registry rows do not exist yet cannot
#: ship a module without inventing an operation id, so it stays pending with
#: the named gap and the change request that asks for the row.
PENDING_REASONS: dict[str, str] = {
    "meeting_rooms": (
        "the frozen registry carries no meeting_rooms.* / meeting_room.* "
        "operation row (WF26 is a managed-browser walk, not an API surface); "
        "change request lanes/GHL-003-lane/change-requests/2.md asks WF00 for "
        "the rows"
    ),
}

_REGISTERED: set[str] = set()


def discover() -> tuple[dict[str, object], dict[str, dict[str, str]]]:
    """Import every family module; return ``(delivered, pending)``.

    ``pending`` keeps the owning workflow id and a plain reason, so the builder
    checkpoint can list exactly what is still owed. A module that imports but
    exposes no callable ``register`` is pending, not registered.
    """
    delivered: dict[str, object] = {}
    pending: dict[str, dict[str, str]] = {}
    for name, owner in FAMILIES.items():
        dotted = "%s.%s" % (__name__, name)
        try:
            module = importlib.import_module(dotted)
        except ModuleNotFoundError as exc:
            if exc.name not in (dotted, __name__ + "." + name.split(".")[0]):
                raise
            pending[name] = {
                "owner": owner,
                "reason": PENDING_REASONS.get(name, "module not delivered"),
            }
            continue
        register = getattr(module, "register", None)
        if not callable(register):
            pending[name] = {"owner": owner, "reason": "module exposes no register(cli)"}
            continue
        delivered[name] = module
    return delivered, pending


def apply_families(cli) -> dict[str, object]:
    """Register each delivered family exactly once on ``cli``.

    Returns ``{"applied": [...], "pending": {...}}`` for the builder
    checkpoint. Raises for a delivered module's own import error — a broken
    family module must be visible, never silently skipped.
    """
    delivered, pending = discover()
    applied: list[str] = []
    for name, module in delivered.items():
        if name in _REGISTERED:
            continue
        module.register(cli)
        _REGISTERED.add(name)
        applied.append(name)
    return {"applied": applied, "pending": pending}
