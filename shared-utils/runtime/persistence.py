#!/usr/bin/env python3
"""persistence.py - restart persistence and the engineering/client-runtime split.

Contract basis: Purple Billboard TODO T-38 ("restart persistence"), R-33 and
DEC-10 ("use the actual Universal v3 foundation and keep temporary engineering
separate from durable runtime"). Python 3 stdlib only.

Reuse, not reimplementation:

  * Durable action state and the crash sweep are the ACCEPTED T-12 modules
    (`38-conversational-ai-system/tools/durable_store.py` and
    `reconciliation.py`, both on main). If either is missing this module raises
    `ReuseUnavailable` naming the exact path; it never substitutes its own
    store. A missing upstream is not a reason to invent a second ledger.
  * The run state file lives on the verified external ledger destination and is
    written through `external.DestinationHandle` (no-follow open, device/inode
    recheck, no-replacement create, atomic replace).

Doctrine, enforced in code:

  * A restart is observed, not assumed. `begin()` reads the previous record; a
    different host fingerprint is a `HostRebound` refusal, never a silent
    continue on a host that is no longer the one that wrote the state.
  * Counters are monotonic. Restarts only increase, attempts only increase, and
    recorded unknown effects are unioned, never cleared. A resume never resets a
    counter or a deadline.
  * The crash sweep promotes a possibly-sent action to `unknown`; it does not
    close the attempt and does not resend. Recovery is reconciliation's job.
  * Engineering teardown disposes engineering temp and engineering processes
    only. Durable customer runtime, durable state and anything owning an unknown
    effect are preserved by name, and an unrecognised kind is refused rather
    than guessed.

Import::

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from runtime.persistence import RestartLedger, teardown

Assert-based self-check:  python3 -I persistence.py
"""

from __future__ import annotations

import datetime as _datetime
import importlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping as MappingABC
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:  # package import; the fallback exists so `python3 persistence.py` works
    from .external import (
        Destination,
        PathRejected,
        ReboundDestination,
        open_destination,
    )
except ImportError:  # pragma: no cover - direct execution
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from external import (  # type: ignore
        Destination,
        PathRejected,
        ReboundDestination,
        open_destination,
    )

SCHEMA = "pbb.runtime-run-state.v1"
STATE_NAME = "run-state.json"
STORE_NAME = "runtime-actions.db"
ADAPTER_REVISION = "pbb-t38-1"

ENGINEERING_TEMP = "engineering_temp"
ENGINEERING_PROCESS = "engineering_process"
CLIENT_RUNTIME = "client_runtime"
DURABLE_STATE = "durable_state"
KNOWN_KINDS = frozenset({ENGINEERING_TEMP, ENGINEERING_PROCESS,
                         CLIENT_RUNTIME, DURABLE_STATE})
PRESERVED_KINDS = frozenset({CLIENT_RUNTIME, DURABLE_STATE})

STATUS_RUNNING = "running"
STATUS_INTERRUPTED = "interrupted"
STATUS_STOPPED = "stopped"
STATUS_FAILED = "failed"
STATUSES = frozenset({STATUS_RUNNING, STATUS_INTERRUPTED, STATUS_STOPPED,
                      STATUS_FAILED})


class ReuseUnavailable(RuntimeError):
    """An accepted upstream module is missing. No local substitute is used."""

class HostRebound(RuntimeError):
    """The durable run state was written on a different host identity."""

class TeardownRefused(RuntimeError):
    """A teardown was asked to dispose of a resource it does not own."""


# ── accepted upstream reuse ─────────────────────────────────────────────────

_TOOLS_RELATIVE = Path("38-conversational-ai-system") / "tools"

def _tools_dir() -> Path:
    return Path(__file__).resolve().parents[2] / _TOOLS_RELATIVE

def _load_upstream() -> Tuple[Any, Any]:
    """Import the accepted T-12 modules from their real path, or refuse."""
    tools = _tools_dir()
    for name in ("durable_store.py", "reconciliation.py"):
        if not (tools / name).is_file():
            raise ReuseUnavailable(
                "reuse_unavailable: accepted upstream module %s is missing; "
                "refusing to substitute a second store" % (tools / name))
    text = str(tools)
    if text not in sys.path:
        sys.path.insert(0, text)
    durable_store = importlib.import_module("durable_store")
    reconciliation = importlib.import_module("reconciliation")
    return durable_store, reconciliation


# ── run state ───────────────────────────────────────────────────────────────

def _utc_now() -> str:
    return _datetime.datetime.now(_datetime.timezone.utc).isoformat()

def _require_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or "/" in value \
            or value in (".", ".."):
        raise PathRejected("bad_%s: %r" % (name, value))
    return value

@dataclass(frozen=True)
class TeardownReport:
    stopped: Tuple[Mapping[str, str], ...]
    preserved: Tuple[Mapping[str, str], ...]
    refused: Tuple[Mapping[str, str], ...]

    def as_dict(self) -> Dict[str, List[Dict[str, str]]]:
        return {"stopped": [dict(x) for x in self.stopped],
                "preserved": [dict(x) for x in self.preserved],
                "refused": [dict(x) for x in self.refused]}


class RestartLedger:
    """Durable run state on an external ledger destination.

    The caller supplies a destination already resolved by
    `external.resolve_destinations(create=True)`; the DNS of trust is that
    resolution, so this class re-opens with a no-follow handle rather than
    re-deriving paths.
    """

    def __init__(self, destination: Destination, *, run_id: str, runtime: str,
                 host_fingerprint: str, now: Optional[Callable[[], str]] = None
                 ) -> None:
        if not os.path.isabs(destination.path):
            raise PathRejected("ledger_not_absolute: %r" % (destination.path,))
        if destination.inode == 0:
            raise PathRejected(
                "ledger_not_created: %s was resolved without create=True"
                % destination.path)
        self.destination = destination
        self.run_id = _require_id(run_id, "run_id")
        self.runtime = _require_id(runtime, "runtime")
        self.host_fingerprint = _require_id(host_fingerprint, "host_fingerprint")
        self._now = now or _utc_now
        self._state: Optional[Dict[str, Any]] = None

    # -- state --------------------------------------------------------------
    def _handle(self):
        return open_destination(self.destination.path, expected=self.destination)

    def read(self) -> Dict[str, Any]:
        """Read the persisted record, or raise if it is absent or malformed."""
        with self._handle() as handle:
            try:
                raw = handle.read(STATE_NAME)
            except FileNotFoundError:
                raise ReboundDestination(
                    "run_state_absent: %s has no %s"
                    % (self.destination.path, STATE_NAME)) from None
        try:
            state = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ReboundDestination(
                "run_state_unreadable: %s: %s" % (STATE_NAME, exc)) from None
        if state.get("schema") != SCHEMA:
            raise ReboundDestination(
                "run_state_schema: %r is not %r" % (state.get("schema"), SCHEMA))
        if state.get("run_id") != self.run_id:
            raise ReboundDestination(
                "run_state_foreign: record belongs to run %r, expected %r"
                % (state.get("run_id"), self.run_id))
        self._state = state
        return state

    def _write(self, state: Dict[str, Any], *, first: bool) -> Dict[str, Any]:
        previous = self._state
        if previous is not None:
            for counter in ("restarts", "attempts"):
                if int(state[counter]) < int(previous[counter]):
                    raise ReboundDestination(
                        "counter_reset: %s would drop from %d to %d; a resume "
                        "never resets a counter"
                        % (counter, previous[counter], state[counter]))
            known = set(previous.get("unknown_effects") or [])
            if not known.issubset(set(state.get("unknown_effects") or [])):
                raise ReboundDestination(
                    "unknown_effects_cleared: %r is not preserved"
                    % sorted(known - set(state.get("unknown_effects") or [])))
        payload = json.dumps(state, sort_keys=True, indent=2).encode("utf-8")
        with self._handle() as handle:
            if first:
                handle.publish(STATE_NAME, payload)
            else:
                handle.replace(STATE_NAME, payload)
        self._state = state
        return state

    def begin(self, worker_id: str) -> Dict[str, Any]:
        """Create the run record or reopen it after a restart.

        A first start publishes without replacement. Reopening verifies the host
        fingerprint, increments `restarts`, preserves every counter and every
        unknown effect, and records the previous status in history.
        """
        _require_id(worker_id, "worker_id")
        stamp = self._now()
        try:
            previous = self.read()
        except ReboundDestination as exc:
            if not str(exc).startswith("run_state_absent:"):
                raise
            state = {
                "schema": SCHEMA,
                "adapter_revision": ADAPTER_REVISION,
                "run_id": self.run_id,
                "runtime": self.runtime,
                "host_fingerprint": self.host_fingerprint,
                "status": STATUS_RUNNING,
                "restarts": 0,
                "attempts": 0,
                "unknown_effects": [],
                "created_at": stamp,
                "updated_at": stamp,
                "worker_id": worker_id,
                "history": [{"at": stamp, "status": STATUS_RUNNING,
                             "note": "first_start"}],
            }
            return self._write(state, first=True)
        if previous["host_fingerprint"] != self.host_fingerprint:
            raise HostRebound(
                "host_rebound: run %r was written on fingerprint %r, this host "
                "is %r; re-verify the bind and unknown effects before resuming"
                % (self.run_id, previous["host_fingerprint"],
                   self.host_fingerprint))
        state = dict(previous)
        state["restarts"] = int(previous["restarts"]) + 1
        state["status"] = STATUS_RUNNING
        state["updated_at"] = stamp
        state["worker_id"] = worker_id
        state["history"] = list(previous.get("history") or []) + [
            {"at": stamp, "status": STATUS_RUNNING,
             "note": "restart_after:" + str(previous.get("status"))}]
        return self._write(state, first=False)

    def record_attempt(self, note: str = "") -> Dict[str, Any]:
        state = dict(self._state or self.read())
        state["attempts"] = int(state["attempts"]) + 1
        state["updated_at"] = self._now()
        if note:
            state["history"] = list(state.get("history") or []) + [
                {"at": state["updated_at"], "status": state["status"],
                 "note": "attempt:" + note}]
        return self._write(state, first=False)

    def record_unknown(self, ids: Iterable[str]) -> Dict[str, Any]:
        state = dict(self._state or self.read())
        current = list(state.get("unknown_effects") or [])
        for action_id in ids:
            if action_id not in current:
                current.append(action_id)
        state["unknown_effects"] = current
        state["updated_at"] = self._now()
        return self._write(state, first=False)

    def finish(self, status: str) -> Dict[str, Any]:
        if status not in STATUSES:
            raise ValueError("bad_status: %r not in %s" % (status, sorted(STATUSES)))
        state = dict(self._state or self.read())
        state["status"] = status
        state["updated_at"] = self._now()
        state["history"] = list(state.get("history") or []) + [
            {"at": state["updated_at"], "status": status, "note": "finish"}]
        return self._write(state, first=False)

    # -- restart reconciliation --------------------------------------------
    def _store(self, durable_store: Any) -> Any:
        path = os.path.join(self.destination.path, STORE_NAME)
        if os.path.islink(path):
            raise PathRejected("symlink_component: %s" % path)
        if os.path.exists(path):
            if os.stat(path).st_dev != self.destination.device:
                raise PathRejected(
                    "different_device: %s is not on the ledger destination"
                    % path)
        return durable_store.DurableStore(path)

    def reconcile_restart(self, *, now: Optional[float] = None) -> Dict[str, Any]:
        """Sweep possibly-sent actions to `unknown` and union them into state.

        Uses the accepted `reconciliation.sweep_inflight`, which never closes an
        attempt and never resends. The returned ids are also persisted so a
        second restart cannot lose them.
        """
        durable_store, reconciliation = _load_upstream()
        store = self._store(durable_store)
        try:
            promoted = reconciliation.sweep_inflight(store, now=now)
        finally:
            store.close()
        state = self.record_unknown(promoted)
        return {
            "promoted": list(promoted),
            "restarts": state["restarts"],
            "unknown_effects": list(state["unknown_effects"]),
            "attempts": state["attempts"],
            "status": state["status"],
        }


# ── engineering / client-runtime separation ─────────────────────────────────

def teardown(resources: Sequence[Mapping[str, Any]],
             *, stop: Callable[[Mapping[str, Any]], Any]) -> TeardownReport:
    """Dispose engineering-owned resources only.

    Each resource is a mapping with `id` and `kind` (one of the four named
    kinds) and optional `unknown_effect`. Durable customer runtime, durable
    state and any resource owning an unknown effect are preserved by name. An
    unrecognised kind is refused, never stopped on a guess.
    """
    stopped: List[Mapping[str, str]] = []
    preserved: List[Mapping[str, str]] = []
    refused: List[Mapping[str, str]] = []
    for resource in resources:
        if not isinstance(resource, MappingABC):
            raise TeardownRefused("bad_resource: %r" % (resource,))
        rid = str(resource.get("id") or "")
        kind = resource.get("kind")
        if not rid:
            raise TeardownRefused("bad_resource_id: %r" % (resource,))
        if resource.get("unknown_effect"):
            preserved.append({"id": rid, "reason": "unknown_effect"})
            continue
        if kind in PRESERVED_KINDS:
            preserved.append({"id": rid, "reason": "durable_runtime"})
            continue
        if kind in (ENGINEERING_TEMP, ENGINEERING_PROCESS):
            stop(resource)
            stopped.append({"id": rid, "reason": "engineering_scope"})
            continue
        refused.append({"id": rid, "reason": "unknown_kind:%r" % (kind,)})
    return TeardownReport(tuple(stopped), tuple(preserved), tuple(refused))


# ── assert-based self-check (stdlib only) ───────────────────────────────────

def _selfcheck() -> None:
    try:
        from .external import resolve_destinations
    except ImportError:  # pragma: no cover - direct execution
        from external import resolve_destinations  # type: ignore

    base = os.path.realpath(os.environ.get("TMPDIR") or os.getcwd())
    work = tempfile.mkdtemp(prefix="pbb-persistence-selfcheck-", dir=base)
    destinations = resolve_destinations(work, "selfcheck-persistence",
                                        create=True, require_mount=False)
    try:
        ledger = RestartLedger(destinations["ledger"], run_id="selfcheck",
                              runtime="mac", host_fingerprint="fp-a")
        first = ledger.begin("worker-1")
        assert first["restarts"] == 0 and first["attempts"] == 0
        ledger.record_attempt("probe")
        second = ledger.begin("worker-2")
        assert second["restarts"] == 1 and second["attempts"] == 1, second
        report = teardown(
            [{"id": "t", "kind": ENGINEERING_TEMP},
             {"id": "c", "kind": CLIENT_RUNTIME},
             {"id": "u", "kind": ENGINEERING_TEMP, "unknown_effect": True}],
            stop=lambda _resource: None)
        assert [x["id"] for x in report.stopped] == ["t"], report
        assert {x["id"] for x in report.preserved} == {"c", "u"}, report
        try:
            RestartLedger(destinations["ledger"], run_id="selfcheck",
                          runtime="mac", host_fingerprint="fp-b").begin("w")
        except HostRebound:
            pass
        else:
            raise AssertionError("a fingerprint change resumed silently")
        print("persistence.py self-check OK")
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    _selfcheck()
