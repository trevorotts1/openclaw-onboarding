#!/usr/bin/env python3
"""ghl_recipe_runner.py — the ordered, injected execution shell for P5 object
recipes (Skill 06 v3.0 §10.2, C6).

WHY THIS EXISTS
---------------
`ghl_recipe_objects.py` decides (identity, reconciliation, readback, gates) and
`ghl_rest_canvas.py` / `ghl_funnels_read.py` provide the real primitives. What
was missing is the thing that runs the §10.2 SEQUENCE in order and refuses at
the right point:

    validate -> admission -> lease -> auth/location -> reconcile
      -> execute -> readback -> verify -> receipt -> release

This module is that shell. It owns NO transport: every step is an injected
callable, so the sequence itself is testable offline and a live run is the
same code with real callables wired in. It never constructs a payload — the
caller passes the already-shaped one, and the runner refuses a publishing
payload before it reaches a rail.

TWO-RUN IDEMPOTENCY (B17) is the load-bearing property and it is enforced HERE,
not by convention: the runner reconciles FIRST on every run, so run 2 sees run
1's object in the inventory and reuses it. The tests exercise exactly that.

RELEASE IS UNCONDITIONAL. The release callable runs in a ``finally`` block for
every outcome including exceptions and refusals: a leased browser that is not
released in all paths is the leak P3 spent its budget eliminating.

WHAT THIS MODULE IS *NOT*
-------------------------
No network, no browser, no credentials, no GHL I/O, no LLM. Not a second write
driver: the receipted write stays `ghl_object_router.execute_write`, reached
through the caller's ``execute`` callable.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import ghl_recipe_objects as ro  # noqa: E402

# Outcome labels — one per way the sequence can stop.
OK_CREATED = "created"
OK_REUSED = "reused"
REFUSED = "refused"
FAILED = "failed"


@dataclass
class RecipeRun:
    """Everything one run produced, in the order it happened."""

    recipe_id: str
    kind: str
    outcome: str = FAILED
    action: str = ""
    reason: str = ""
    native_id: str = ""
    steps: List[str] = field(default_factory=list)
    llm_calls_during_recipe: int = 0
    released: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.outcome in (OK_CREATED, OK_REUSED)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "recipe_id": self.recipe_id,
            "kind": self.kind,
            "outcome": self.outcome,
            "action": self.action,
            "reason": self.reason,
            "native_id": self.native_id,
            "steps": list(self.steps),
            "llm_calls_during_recipe": self.llm_calls_during_recipe,
            "released": self.released,
            "error": self.error,
        }


class RecipeRunError(RuntimeError):
    """A required collaborator was missing or the sequence was misused."""


class ScopeMismatch(RecipeRunError):
    """The authenticated location is not the contract's location. A refusal
    (wrong tenant), not a failure: nothing was attempted."""


def run_recipe(
    contract: ro.RecipeContract,
    *,
    inputs: Dict[str, Any],
    inventory: Callable[[], Dict[str, Any]],
    create: Callable[[Dict[str, Any]], Dict[str, Any]],
    readback: Callable[[str], Dict[str, Any]],
    recipe_id: str = "",
    verify: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
    receipt: Optional[Callable[[RecipeRun], None]] = None,
    admit: Optional[Callable[[], None]] = None,
    acquire_lease: Optional[Callable[[], Any]] = None,
    release_lease: Optional[Callable[[Any], None]] = None,
    authenticate: Optional[Callable[[], str]] = None,
    payload: Optional[Dict[str, Any]] = None,
    llm_guard: Optional[ro.LlmCallGuard] = None,
    saved_state_keys: tuple = (),
) -> RecipeRun:
    """Run one object recipe end to end.

    ``inventory()`` returns ``{"rows": [...], "complete": bool}``. ``complete``
    must be True for absence to be provable; False refuses before any create.
    ``create(payload)`` returns the platform create response. ``readback(id)``
    returns the authoritative read. Both are the caller's real primitives; the
    runner only orders them and checks the result.

    A DISABLED contract raises immediately — a disabled capability never gets
    as far as admission.
    """
    run = RecipeRun(recipe_id=recipe_id or f"{contract.object_kind}:{contract.parent_id}",
                    kind=contract.object_kind)
    guard = llm_guard or ro.LlmCallGuard(run.recipe_id)
    lease: Any = None

    try:
        # 1 — validate request + contract (+ publication gate on the payload).
        contract.validate()
        values = contract.validate_input(inputs)
        run.steps.append("validate_request")
        if payload is not None:
            ro.assert_no_publication(payload)
            run.steps.append("assert_no_publication")

        # 2 — admission (host/resource budget, owned by the caller).
        if admit is not None:
            admit()
        run.steps.append("admission")

        # 3 — one browser lease.
        if acquire_lease is not None:
            lease = acquire_lease()
        run.steps.append("browser_lease")

        # 4 — authenticate and prove the LOCATION (never a token alone).
        observed_location = None
        if authenticate is not None:
            observed_location = str(authenticate() or "").strip()
        if observed_location and observed_location != contract.location_id:
            raise ScopeMismatch(
                f"authenticated location {observed_location!r} != contract "
                f"location {contract.location_id!r}; refusing before any write"
            )
        run.steps.append("authenticate_and_verify_location")

        # 5 — reconcile against the CURRENT inventory (this is B17's mechanism).
        snap = inventory()
        if not isinstance(snap, dict):
            raise RecipeRunError("inventory() must return {'rows': [...], 'complete': bool}")
        decision = ro.reconcile(
            snap.get("rows") or [],
            kind=contract.object_kind,
            location_id=contract.location_id,
            parent_id=contract.parent_id,
            name=values.get("name"),
            native_id=values.get("native_id"),
            read_complete=bool(snap.get("complete")),
        )
        run.action = decision.action
        run.reason = decision.reason
        run.steps.append("reconcile")

        if decision.refused:
            run.outcome = REFUSED
            return run
        if decision.action == ro.REUSE:
            run.outcome = OK_REUSED
            run.native_id = decision.identity.native_id
            run.steps.append("reuse")
            return run

        # 6 — execute the create. No payload invented here.
        if payload is None:
            raise RecipeRunError(
                "create requires a caller-shaped payload; the runner never "
                "constructs one"
            )
        response = create(payload)
        run.steps.append("execute")

        # 7 — readback: native id + scope + saved state, from an independent read.
        native_id = ro.extract_native_id(contract.object_kind, response or {})
        read = readback(native_id)
        ro.assert_readback(
            contract.object_kind, response or {}, read,
            location_id=contract.location_id,
            parent_id=contract.parent_id,
            saved_state_keys=saved_state_keys,
        )
        run.native_id = native_id
        run.steps.append("readback")

        # 8 — canonical verification where the caller supplies one.
        if verify is not None:
            verdict = verify(native_id, read)
            if not isinstance(verdict, dict) or not verdict.get("ok"):
                raise ro.ReadbackIncomplete(
                    f"{contract.object_kind} {native_id}: canonical verification "
                    f"did not pass ({verdict!r})"
                )
        run.steps.append("verify")

        run.outcome = OK_CREATED
        return run

    except (ro.ContractError, ro.IdentityError, ro.RecipeRefusal,
            ro.ReadbackIncomplete, ro.PublicationRefused,
            ro.RecipeLlmCallViolation, RecipeRunError) as exc:
        run.outcome = REFUSED
        run.error = f"{type(exc).__name__}: {exc}"
        return run
    except Exception as exc:  # noqa: BLE001 — honest FAIL, never a silent pass
        run.outcome = FAILED
        run.error = f"{type(exc).__name__}: {exc}"
        return run
    finally:
        # Release is UNCONDITIONAL — refusal, failure and success all release.
        if release_lease is not None:
            try:
                release_lease(lease)
                run.released = True
            except Exception as exc:  # noqa: BLE001
                run.released = False
                run.error = (run.error + " | " if run.error else "") + \
                    f"lease release failed: {type(exc).__name__}: {exc}"
        run.steps.append("release")
        run.llm_calls_during_recipe = guard.count
        if receipt is not None:
            try:
                receipt(run)
            except Exception:  # noqa: BLE001 — a receipt failure must not
                pass           # mask the run outcome


def run_folder_recipe(
    kind: str,
    *,
    location_id: str,
    name: str,
    capture: Any = None,
    reviewed: bool = False,
    scoped_approval: str = "",
    inventory: Callable[[], Dict[str, Any]],
    create: Callable[[Dict[str, Any]], Dict[str, Any]],
    readback: Callable[[str], Dict[str, Any]],
    recipe_id: str = "",
    **kw: Any,
) -> RecipeRun:
    """Run one FOLDER recipe (``funnel_folder`` / ``website_folder``).

    The folder create verb is capture-gated (see
    ``ghl_rest_canvas.folder_create``), but folder IDENTITY and reuse are proven
    by the captured list route, which needs no gate. This entry point keeps that
    split honest:

      * the contract is built by ``ro.folder_create_recipe_contract``, which is
        ``disabled`` while the gate is closed;
      * while the gate is closed, reconciliation still runs FIRST so a resume
        that finds the folder already present reports ``reused`` (no capture
        needed to prove an existing object), and only a CREATE is refused.

    ``capture``/``reviewed`` open the gate; with both the run delegates to
    ``run_recipe`` unchanged. The payload is built from the capture via
    ``ghl_rest_canvas.folder_create_body`` — the runner never invents a body, and
    a caller may still pass their own ``payload``.
    """
    if kind not in ro.FOLDER_CREATE_KINDS:
        raise RecipeRunError(
            f"{kind!r} is not a folder kind; run_folder_recipe is for "
            f"{list(ro.FOLDER_CREATE_KINDS)}"
        )
    if capture is not None:
        import ghl_rest_canvas  # read-only reuse; the gate lives there
        if isinstance(capture, str):
            capture = ghl_rest_canvas.load_folder_create_capture(capture)
        if ghl_rest_canvas.is_synthetic_folder_capture(capture):
            # Loud, not silent: a shape fixture is never evidence.
            raise ghl_rest_canvas.CaptureRequired(
                f"ghl.folder.create: the supplied capture is synthetic "
                f"({ghl_rest_canvas.FOLDER_CREATE_FIXTURE_WARNING}); a shape "
                "fixture is not evidence"
            )
    contract = ro.folder_create_recipe_contract(
        kind, location_id=location_id, capture=capture, reviewed=reviewed,
        scoped_approval=scoped_approval,
    )
    run = RecipeRun(recipe_id=recipe_id or f"{kind}:{location_id}", kind=kind)

    # Gate CLOSED: prove reuse if the folder exists; refuse a create.
    #
    # No browser lease is acquired on this path at all (the only work is the
    # captured LIST read), so ``released`` stays False and no "release" step is
    # recorded — claiming a release that never happened would be a lie in the
    # receipt. ``released`` False here means "nothing to release", and the
    # recorded steps say exactly that.
    if contract.execution_mode == "disabled":
        try:
            snap = inventory()
            if not isinstance(snap, dict):
                raise RecipeRunError(
                    "inventory() must return {'rows': [...], 'complete': bool}"
                )
            decision = ro.reconcile(
                snap.get("rows") or [], kind=kind, location_id=location_id,
                parent_id="", name=name, read_complete=bool(snap.get("complete")),
            )
        except Exception as exc:  # noqa: BLE001 — honest FAIL, never silent
            run.outcome = FAILED
            run.error = f"{type(exc).__name__}: {exc}"
            return run
        run.action = decision.action
        run.reason = decision.reason
        run.steps.append("reconcile")
        if decision.action == ro.REUSE:
            run.outcome = OK_REUSED
            run.native_id = decision.identity.native_id
            run.steps.append("reuse")
            return run
        run.outcome = REFUSED
        state = ro.folder_create_gate_state(capture, reviewed=reviewed)
        run.error = (
            f"{state.get('state')}: {state.get('reason')} "
            f"[{state.get('next_action')}]"
        )
        return run

    # Gate OPEN: a normal §10.2 run, with the body replayed from the capture.
    payload = kw.pop("payload", None)
    if payload is None:
        import ghl_rest_canvas  # read-only reuse; shapes the captured body
        payload = ghl_rest_canvas.folder_create_body(
            location_id, name, ro.schema_for(kind).platform_type,
            capture=capture, reviewed=reviewed,
        )
    return run_recipe(
        contract, inputs={"name": name}, inventory=inventory, create=create,
        readback=readback, payload=payload, recipe_id=run.recipe_id, **kw,
    )


# ── Self-test (pure; injected fakes only) ────────────────────────────────────

def _selftest() -> int:
    errors: List[str] = []
    loc = "loc-selftest"

    contract = ro.recipe_contract_for(
        ro.KIND_FUNNEL, location_id=loc, parent_id="folder-1",
        parent_kind=ro.KIND_FUNNEL_FOLDER, scoped_approval="APPROVED-selftest",
    )
    store: Dict[str, Dict[str, Any]] = {}
    created: List[Dict[str, Any]] = []
    released: List[Any] = []

    def _inventory():
        return {"rows": list(store.values()), "complete": True}

    def _create(payload):
        created.append(payload)
        fid = f"funnel-{len(created)}"
        return {"id": fid, "locationId": loc, "parentId": "folder-1"}

    def _readback(native_id):
        row = {"id": native_id, "name": "ZHC Selftest", "locationId": loc,
               "parentId": "folder-1", "type": "funnel"}
        store[native_id] = row
        return row

    def _lease():
        return "lease-token"

    kw = dict(
        inputs={"name": "ZHC Selftest", "slug": "selftest"},
        inventory=_inventory, create=_create, readback=_readback,
        acquire_lease=_lease, release_lease=released.append,
        authenticate=lambda: loc,
        payload={"locationId": loc, "name": "ZHC Selftest", "type": "funnel",
                 "pageType": "draft"},
        recipe_id="selftest-funnel",
    )

    first = run_recipe(contract, **kw)
    if first.outcome != OK_CREATED or len(created) != 1:
        errors.append(f"run 1 should create once, got {first.as_dict()}")
    if not first.released:
        errors.append("run 1 must release the lease")

    second = run_recipe(contract, **kw)
    if second.outcome != OK_REUSED:
        errors.append(f"run 2 must reuse, got {second.as_dict()}")
    if len(created) != 1:
        errors.append(f"run 2 duplicated the object ({len(created)} creates) — B17")

    # A publishing payload is refused before any create.
    pub = dict(kw)
    pub["payload"] = {"locationId": loc, "pageType": "published"}
    r = run_recipe(contract, **pub)
    if r.outcome != REFUSED or len(created) != 1:
        errors.append(f"published payload must refuse pre-write, got {r.as_dict()}")

    # Wrong authenticated location refuses before any write.
    wrong = dict(kw)
    wrong["authenticate"] = lambda: "loc-other"
    wrong["payload"] = {"locationId": loc, "name": "ZHC Other", "type": "funnel"}
    r = run_recipe(contract, **wrong)
    if r.outcome != REFUSED or "!= contract location" not in r.error:
        errors.append(f"wrong-location run must refuse, got {r.as_dict()}")
    if not r.released:
        errors.append("a refused run must still release the lease")

    # ── Folder recipes: reuse without a capture, refuse a create without one ─
    import ghl_rest_canvas as canvas
    cap = dict(canvas.OFFLINE_FOLDER_CAPTURE)
    cap.pop("_fixture", None)          # fixture marker off: shape, still fake
    cap["location_id"] = floc = "loc-folder-selftest"
    folder_store: Dict[str, Dict[str, Any]] = {}
    folder_creates: List[Dict[str, Any]] = []

    def _f_inventory():
        return {"rows": list(folder_store.values()), "complete": True}

    def _f_create(payload):
        folder_creates.append(payload)
        return {cap["response_id_field"]: f"folder-{len(folder_creates)}"}

    def _f_readback(native_id):
        row = {"id": native_id, "name": "ZHC Folder", "locationId": floc,
               "type": "funnel"}
        folder_store[native_id] = row
        return row

    closed = run_folder_recipe(
        ro.KIND_FUNNEL_FOLDER, location_id=floc, name="ZHC Folder",
        inventory=_f_inventory, create=_f_create, readback=_f_readback,
        scoped_approval="APPROVED-selftest", recipe_id="folder-closed",
    )
    if closed.outcome != REFUSED or folder_creates:
        errors.append(f"a closed gate must refuse a create, got {closed.as_dict()}")

    opened = run_folder_recipe(
        ro.KIND_FUNNEL_FOLDER, location_id=floc, name="ZHC Folder",
        capture=cap, reviewed=True,
        inventory=_f_inventory, create=_f_create, readback=_f_readback,
        authenticate=lambda: floc, scoped_approval="APPROVED-selftest",
        recipe_id="folder-open",
    )
    if opened.outcome != OK_CREATED or len(folder_creates) != 1:
        errors.append(f"an open gate must create once, got {opened.as_dict()}")

    second = run_folder_recipe(
        ro.KIND_FUNNEL_FOLDER, location_id=floc, name="ZHC Folder",
        inventory=_f_inventory, create=_f_create, readback=_f_readback,
        scoped_approval="APPROVED-selftest", recipe_id="folder-reuse",
    )
    if second.outcome != OK_REUSED or len(folder_creates) != 1:
        errors.append(f"a closed gate must still REUSE, got {second.as_dict()}")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — ghl_recipe_runner sequence + two-run idempotency + "
          "folder capture gate (no network)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="offline selftest")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    ap.print_help()
    return 2


__all__ = [
    "OK_CREATED", "OK_REUSED", "REFUSED", "FAILED",
    "RecipeRun", "RecipeRunError", "run_recipe", "run_folder_recipe",
]


if __name__ == "__main__":
    sys.exit(main())
