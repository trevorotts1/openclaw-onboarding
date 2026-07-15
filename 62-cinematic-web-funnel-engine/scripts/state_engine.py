#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""state_engine.py — Skill 62 (Cinematic and Web Funnel Engine), build unit U6.

The project/content/scene/cost/deployment state engine described in spec Section
11 ("Every generated site must have a durable project-manifest.json as the
source of truth") and Section 11.2 (state rules). Owns:

  - the five U6 schemas (structure/*.schema.json) and validates every read AND
    every write against them (json_schema_lite.py, stdlib-only, no jsonschema
    package dependency — ADR-5 is Python-stdlib orchestration);
  - atomic writes (tempfile in the same directory + os.replace, which is
    atomic on a POSIX filesystem — a crash mid-write can never leave a
    manifest half-written; readers only ever see the prior good file or the
    new good file, never a partial one);
  - ONE project lock (ProjectLock) guarding all paid-generation and manifest
    mutation for a project, with dead-process stale-lock recovery so a killed
    build can never permanently wedge a project;
  - idempotency: every paid call is keyed by a deterministic request_hash
    (sha256 over provider+model+operation+params); begin_task() refuses to
    open a second task for a request_hash that already has an active or
    complete cost-ledger entry (AF-CWFE-RESTART-DUPLICATE — spec 11.2 "never
    repeat a completed paid task with the same request hash");
  - a task status state machine (queued -> submitted -> in_progress ->
    complete|failed|cancelled, failed -> queued for a retry) with every
    transition recorded (spec 11.2 "record every status transition");
  - in_progress recovery: recover() is a READ-ONLY report distinguishing tasks
    that actually reached a provider (provider_task_id is set — a later unit's
    recover_tasks.py MUST query the provider before ever transitioning these)
    from tasks that never left this process (safe to requeue). state_engine
    itself never calls a provider — that stays in the provider abstraction
    (U4/U5), preserving the ADR-5 boundary.

Every manifest kind's file lives under a caller-supplied run_dir, matching the
artifact paths CWFE-MANIFEST.json already declares per phase (project-
manifest.json, content-manifest.json, journey/scene-plan.json, cost-ledger.json,
deployment receipts) — this module does not invent a new directory convention.

No secret values are ever handled or written by this module; only secret
NAMES pass through project-manifest.json's execution_environment/hosting/crm
`secret_names[]` arrays.

stdlib only. Exit 0 on --self-test success, 1 on failure.
"""

from __future__ import annotations

import argparse
import datetime
import errno
import hashlib
import json
import os
import shutil
import socket
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
_STRUCTURE_DIR = _SCRIPT_DIR.parent / "structure"

sys.path.insert(0, str(_SCRIPT_DIR / "lib"))
import json_schema_lite as jsl  # noqa: E402  (local sibling package, mirrors repo scripts/lib convention)


SCHEMA_VERSION = "1.0.0"

SCHEMA_FILES: Dict[str, str] = {
    "project-manifest": "project-manifest.schema.json",
    "content-manifest": "content-manifest.schema.json",
    "scene-plan": "scene-plan.schema.json",
    "cost-ledger": "cost-ledger.schema.json",
    "deployment-receipt": "deployment-receipt.schema.json",
}

# Per-run-dir artifact locations. Matches the paths CWFE-MANIFEST.json's
# `produces_artifact` field already names for P1/P3/P4/P9/P14/P15, and the
# canonical `journey/scene-plan.json` path from spec Section 15's directory
# tree (a per-run artifact, not a skill-dir path).
ARTIFACT_RELPATHS: Dict[str, str] = {
    "project-manifest": "project-manifest.json",
    "content-manifest": "content-manifest.json",
    "scene-plan": "journey/scene-plan.json",
    "cost-ledger": "cost-ledger.json",
    # deployment-receipt.schema.json describes ONE receipt; a project accrues
    # more than one over preview/production/redeploys, so the on-disk store is
    # an append-only JSON array where every element independently validates
    # against the singular schema.
    "deployment-receipt": "deployment-receipts.json",
}

TASK_STATUSES = ("queued", "submitted", "in_progress", "complete", "failed", "cancelled")

# The task/cost-ledger-entry status state machine. None is the "no entry yet"
# starting state. failed -> queued is the only retry path; complete/cancelled
# are terminal. in_progress -> in_progress is allowed (repeated polling).
_ALLOWED_TRANSITIONS: Dict[Optional[str], set] = {
    None: {"queued"},
    "queued": {"submitted", "cancelled", "failed"},
    "submitted": {"in_progress", "complete", "failed", "cancelled"},
    "in_progress": {"in_progress", "complete", "failed", "cancelled"},
    "failed": {"queued", "cancelled"},
    "complete": set(),
    "cancelled": set(),
}


# ------------------------------------------------------------------------
# Errors
# ------------------------------------------------------------------------
class StateEngineError(Exception):
    """Base class for every error this module raises."""


class ProjectLockError(StateEngineError):
    """The single project lock is already held by a live process."""


class ManifestNotFoundError(StateEngineError):
    """load() was called for a kind whose file does not exist on disk."""


class SchemaValidationFailed(StateEngineError):
    def __init__(self, errors: List[str], label: str = ""):
        self.errors = errors
        prefix = f"{label}: " if label else ""
        super().__init__(prefix + "; ".join(errors))


class IdempotencyViolation(StateEngineError):
    """begin_task() refused to open a duplicate paid call for a request_hash
    that already has an active or complete cost-ledger entry
    (AF-CWFE-RESTART-DUPLICATE)."""


class InvalidStateTransition(StateEngineError):
    """transition_task() was asked to move a task through a transition the
    state machine does not allow."""


class BudgetExceeded(StateEngineError):
    """begin_task() refused a paid call whose projected cumulative spend would
    exceed the project's recorded budget cap (spec 10.4 hard-stop)."""


# ------------------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------------------
def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_SCHEMA_CACHE: Dict[str, Dict[str, Any]] = {}


def _load_schema(kind: str) -> Dict[str, Any]:
    if kind not in SCHEMA_FILES:
        raise StateEngineError(f"unknown manifest kind '{kind}' (known: {sorted(SCHEMA_FILES)})")
    if kind not in _SCHEMA_CACHE:
        path = _STRUCTURE_DIR / SCHEMA_FILES[kind]
        if not path.exists():
            raise StateEngineError(f"schema file missing: {path}")
        _SCHEMA_CACHE[kind] = json.loads(path.read_text(encoding="utf-8"))
    return _SCHEMA_CACHE[kind]


def validate_kind(kind: str, instance: Any, *, label: str = "") -> None:
    """Validate `instance` against the named schema kind. Raises
    SchemaValidationFailed (never returns a boolean) so a caller can never
    accidentally ignore a validation failure — this is the enforcement point
    for spec 11.2's "schema validation on every read/write"."""
    schema = _load_schema(kind)
    errors = jsl.validate(instance, schema)
    if errors:
        raise SchemaValidationFailed(errors, label=label or kind)


# ------------------------------------------------------------------------
# Atomic writes
# ------------------------------------------------------------------------
def atomic_write_json(path: Path, data: Any) -> None:
    """Write `data` to `path` atomically: serialize to a tempfile in the SAME
    directory, fsync it, then os.replace() over the target. os.replace is a
    single atomic rename on a POSIX filesystem, so any reader (including a
    process that crashes and restarts) only ever observes the prior complete
    file or the new complete file — never a truncated/partial write, even if
    this process is killed mid-write."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, str(path))
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    # Best-effort directory fsync so the rename itself survives a crash
    # (durability beyond atomicity; harmless if the platform does not support it).
    try:
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass


def read_json(path: Path) -> Any:
    path = Path(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StateEngineError(f"{path} is corrupt JSON: {exc}") from exc


# ------------------------------------------------------------------------
# Project lock — ONE lock per project for paid generation and manifest mutation
# ------------------------------------------------------------------------
def _pid_alive(pid: Optional[int]) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but is owned by someone else — still alive.
        return True
    except OSError:
        return False
    return True


class ProjectLock:
    """A single, atomically-acquired lock file per project (run_dir). Acquiring
    twice from a live holder raises ProjectLockError. A lock whose recorded
    pid is no longer alive (the classic "process was killed mid-run" case
    spec 11.2/19.4 calls out) is detected and broken automatically so a dead
    process can never permanently wedge a project — this is what makes
    interrupted-and-restarted runs recoverable rather than deadlocked."""

    LOCK_FILENAME = ".cwfe_project.lock"

    def __init__(self, run_dir: Path, *, stale_after_seconds: float = 900.0):
        self.run_dir = Path(run_dir)
        self.lock_path = self.run_dir / self.LOCK_FILENAME
        self.stale_after_seconds = stale_after_seconds
        self._held = False

    def _read_holder(self) -> Optional[Dict[str, Any]]:
        try:
            data = json.loads(self.lock_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    def _write_lock_file(self) -> None:
        payload = {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "acquired_at": _now(),
            "acquired_at_epoch": time.time(),
        }
        self.run_dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)

    def acquire(self) -> None:
        if self._held:
            return
        try:
            self._write_lock_file()
            self._held = True
            return
        except FileExistsError:
            pass  # fall through to stale-lock inspection below

        holder = self._read_holder()
        if holder is None:
            self._force_break("lock file present but unreadable/corrupt")
        else:
            pid = holder.get("pid")
            age = time.time() - float(holder.get("acquired_at_epoch", 0))
            if _pid_alive(pid) and age < self.stale_after_seconds:
                raise ProjectLockError(
                    f"project lock at {self.lock_path} is held by pid {pid} on "
                    f"{holder.get('host')} since {holder.get('acquired_at')} "
                    f"(age {age:.0f}s) — another run is in progress"
                )
            self._force_break(
                f"stale lock (holder pid={pid} alive={_pid_alive(pid)} "
                f"age={age:.0f}s >= stale_after={self.stale_after_seconds}s)"
            )

        # Retry once, now that the stale/corrupt lock has been removed.
        self._write_lock_file()
        self._held = True

    def _force_break(self, reason: str) -> None:
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass

    def release(self) -> None:
        if not self._held:
            return
        try:
            holder = self._read_holder()
            if holder is not None and holder.get("pid") == os.getpid():
                self.lock_path.unlink()
        except FileNotFoundError:
            pass
        finally:
            self._held = False

    def __enter__(self) -> "ProjectLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.release()
        return False


# ------------------------------------------------------------------------
# ProjectState — the manifest/ledger lifecycle API
# ------------------------------------------------------------------------
class ProjectState:
    """Bound to one run_dir (one project). All mutation of project-manifest.json
    and cost-ledger.json goes through methods that acquire ProjectLock
    internally — callers never need to remember to lock manually, and it is
    therefore impossible to accidentally mutate either file unlocked from
    inside this class."""

    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)

    def _path(self, kind: str) -> Path:
        if kind not in ARTIFACT_RELPATHS:
            raise StateEngineError(f"unknown manifest kind '{kind}'")
        return self.run_dir / ARTIFACT_RELPATHS[kind]

    def lock(self, **kwargs: Any) -> ProjectLock:
        return ProjectLock(self.run_dir, **kwargs)

    def exists(self, kind: str) -> bool:
        return self._path(kind).exists()

    def load(self, kind: str) -> Any:
        path = self._path(kind)
        if not path.exists():
            raise ManifestNotFoundError(f"{kind} not found at {path}")
        data = read_json(path)
        if kind == "deployment-receipt":
            if not isinstance(data, list):
                raise StateEngineError(f"deployment-receipt store at {path} must be a JSON array")
            for i, receipt in enumerate(data):
                validate_kind("deployment-receipt", receipt, label=f"{path}[{i}]")
            return data
        validate_kind(kind, data, label=str(path))
        return data

    def save(self, kind: str, data: Any) -> None:
        """Validates against the kind's schema, then writes atomically. Callers
        mutating project-manifest or cost-ledger must hold the project lock
        first (every ProjectState method that mutates those two kinds already
        does this internally)."""
        if kind == "deployment-receipt":
            if not isinstance(data, list):
                raise StateEngineError("deployment-receipt store must be saved as a list")
            for i, receipt in enumerate(data):
                validate_kind("deployment-receipt", receipt, label=f"[{i}]")
        else:
            validate_kind(kind, data, label=kind)
        atomic_write_json(self._path(kind), data)

    # -- project-manifest lifecycle -----------------------------------------
    def create_project(
        self,
        *,
        project_id: str,
        client_slug: str,
        project_slug: str,
        deliverable_type: str,
        budget_cap_usd: float,
    ) -> Dict[str, Any]:
        now = _now()
        manifest: Dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "project_id": project_id,
            "client_slug": client_slug,
            "project_slug": project_slug,
            "deliverable_type": deliverable_type,
            "status": "created",
            "content_methodology": {
                "source": "unset",
                "source_skill": "",
                "source_skill_version": "",
                "content_manifest_hash": None,
            },
            "execution_environment": {"resolved_at": None, "secret_names": []},
            "hosting": {"provider": "unset", "secret_names": []},
            "crm": {"provider": "unset", "location_id": None, "secret_names": []},
            "budget": {
                "cap_usd": budget_cap_usd,
                "approved": False,
                "approved_by": None,
                "approved_at": None,
                "cumulative_spend_usd": 0.0,
            },
            "scenes": [],
            "connectors": [],
            "assets": [],
            "tasks": [],
            "quality": {},
            "deployment": {"preview": None, "production": None},
            "approvals": [],
            "status_history": [
                {"from_status": None, "to_status": "created", "at": now, "reason": "project created"}
            ],
            "created_at": now,
            "updated_at": now,
        }
        with self.lock():
            if self._path("project-manifest").exists():
                raise StateEngineError(
                    f"project-manifest.json already exists at {self._path('project-manifest')} — "
                    "create_project must never overwrite an existing project"
                )
            self.save("project-manifest", manifest)

            ledger = {
                "schema_version": SCHEMA_VERSION,
                "project_id": project_id,
                "budget_cap_usd": budget_cap_usd,
                "cumulative_spend_usd": 0.0,
                "remaining_budget_usd": budget_cap_usd,
                "entries": [],
                "created_at": now,
                "updated_at": now,
            }
            if not self._path("cost-ledger").exists():
                self.save("cost-ledger", ledger)
        return manifest

    def transition_project_status(self, new_status: str, *, reason: str) -> Dict[str, Any]:
        with self.lock():
            manifest = self.load("project-manifest")
            old = manifest["status"]
            now = _now()
            manifest["status"] = new_status
            manifest["updated_at"] = now
            manifest["status_history"].append(
                {"from_status": old, "to_status": new_status, "at": now, "reason": reason}
            )
            self.save("project-manifest", manifest)
            return manifest

    # -- idempotency / cost ledger / task lifecycle --------------------------
    @staticmethod
    def compute_request_hash(*, provider: str, model: str, operation: str, params: Dict[str, Any]) -> str:
        """The idempotency key: sha256 over the canonical (sorted-key, no
        whitespace) JSON serialization of provider+model+operation+params.
        Deterministic — the same logical request always hashes the same,
        regardless of dict key order or process."""
        canonical = json.dumps(
            {"provider": provider, "model": model, "operation": operation, "params": params},
            sort_keys=True,
            separators=(",", ":"),
        )
        return _sha256_hex(canonical.encode("utf-8"))

    def find_active_or_complete_entry(self, request_hash: str) -> Optional[Dict[str, Any]]:
        """Read-only. Returns the cost-ledger entry for `request_hash` if one
        exists and is queued/submitted/in_progress/complete, else None."""
        ledger = self.load("cost-ledger")
        for entry in ledger["entries"]:
            if entry["request_hash"] == request_hash and entry["status"] in (
                "queued",
                "submitted",
                "in_progress",
                "complete",
            ):
                return entry
        return None

    def begin_task(
        self,
        *,
        provider: str,
        model: str,
        operation: str,
        params: Dict[str, Any],
        estimated_cost_usd: float,
        seconds: Optional[float] = None,
        image_count: Optional[int] = None,
        resolution: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Locked. Opens a new cost-ledger entry (status=queued) and a matching
        project-manifest.tasks[] record. Raises IdempotencyViolation
        (AF-CWFE-RESTART-DUPLICATE) if a ledger entry for the same
        request_hash is already active or complete — this is the mechanism
        that makes a restarted/resumed run never repeat a completed (or even
        an in-flight) paid call. Raises BudgetExceeded (spec 10.4 hard-stop)
        if the projected cumulative spend would exceed the recorded cap."""
        request_hash = self.compute_request_hash(
            provider=provider, model=model, operation=operation, params=params
        )
        with self.lock():
            ledger = self.load("cost-ledger")
            for entry in ledger["entries"]:
                if entry["request_hash"] == request_hash and entry["status"] in (
                    "queued",
                    "submitted",
                    "in_progress",
                    "complete",
                ):
                    raise IdempotencyViolation(
                        f"request_hash {request_hash} already has a {entry['status']!r} task "
                        f"{entry['task_id']} — refusing duplicate paid call (AF-CWFE-RESTART-DUPLICATE)"
                    )

            # Projected spend must include estimates for tasks already committed
            # but not yet complete (queued/submitted/in_progress), not just the
            # completed-actual cumulative — otherwise several outstanding calls
            # queued back-to-back could jointly blow past the cap before any of
            # them finishes and rolls into cumulative_spend_usd.
            outstanding_estimated = sum(
                e["estimated_cost_usd"]
                for e in ledger["entries"]
                if e["status"] in ("queued", "submitted", "in_progress")
            )
            projected = ledger["cumulative_spend_usd"] + outstanding_estimated + estimated_cost_usd
            if projected > ledger["budget_cap_usd"]:
                raise BudgetExceeded(
                    f"projected spend {projected:.4f} would exceed budget cap "
                    f"{ledger['budget_cap_usd']:.4f} (cumulative {ledger['cumulative_spend_usd']:.4f} "
                    f"+ outstanding {outstanding_estimated:.4f} + estimated {estimated_cost_usd:.4f}) — "
                    "hard-stop before this paid call (spec 10.4)"
                )

            now = _now()
            task_id = f"t-{uuid.uuid4().hex[:16]}"
            entry = {
                "task_id": task_id,
                "request_hash": request_hash,
                "provider": provider,
                "model": model,
                "provider_task_id": None,
                "operation": operation,
                "resolution": resolution,
                "seconds": seconds,
                "image_count": image_count,
                "status": "queued",
                "estimated_cost_usd": estimated_cost_usd,
                "actual_cost_usd": None,
                "retry_count": 0,
                "retry_reason": None,
                "refunded": False,
                "status_history": [{"from_status": None, "to_status": "queued", "at": now}],
                "created_at": now,
                "updated_at": now,
            }
            ledger["entries"].append(entry)
            ledger["updated_at"] = now
            self.save("cost-ledger", ledger)

            manifest = self.load("project-manifest")
            manifest["tasks"].append(
                {
                    "task_id": task_id,
                    "kind": operation,
                    "status": "queued",
                    "request_hash": request_hash,
                    "provider_task_id": None,
                    "retry_count": 0,
                }
            )
            manifest["updated_at"] = now
            self.save("project-manifest", manifest)
            return entry

    def transition_task(
        self,
        task_id: str,
        new_status: str,
        *,
        provider_task_id: Optional[str] = None,
        actual_cost_usd: Optional[float] = None,
        retry_reason: Optional[str] = None,
        refunded: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Locked. Enforces the task status state machine and records every
        transition (spec 11.2 'record every status transition'). Rolls actual
        cost into the ledger's cumulative_spend_usd/remaining_budget_usd and
        mirrors it into project-manifest.budget.cumulative_spend_usd only on a
        transition INTO 'complete' carrying actual_cost_usd, so spend is never
        double-counted by a repeated poll."""
        if new_status not in TASK_STATUSES:
            raise InvalidStateTransition(f"unknown status '{new_status}' (known: {TASK_STATUSES})")
        with self.lock():
            ledger = self.load("cost-ledger")
            entry = next((e for e in ledger["entries"] if e["task_id"] == task_id), None)
            if entry is None:
                raise StateEngineError(f"no cost-ledger entry for task_id {task_id}")

            old_status = entry["status"]
            allowed = _ALLOWED_TRANSITIONS.get(old_status, set())
            if new_status not in allowed:
                raise InvalidStateTransition(
                    f"task {task_id}: {old_status!r} -> {new_status!r} is not an allowed transition "
                    f"(allowed from {old_status!r}: {sorted(allowed)!r})"
                )

            now = _now()
            # retry_reason is recorded at the point a task transitions INTO
            # 'failed' (when the reason is actually known) and preserved
            # across the subsequent failed -> queued retry transition, which
            # typically carries no retry_reason of its own. Only an explicit
            # non-None retry_reason ever overwrites the stored value.
            if new_status == "failed" and retry_reason is not None:
                entry["retry_reason"] = retry_reason
            if old_status == "failed" and new_status == "queued":
                entry["retry_count"] += 1
                if retry_reason is not None:
                    entry["retry_reason"] = retry_reason
            entry["status"] = new_status
            if provider_task_id is not None:
                entry["provider_task_id"] = provider_task_id
            if refunded is not None:
                entry["refunded"] = refunded
            entry["updated_at"] = now
            entry["status_history"].append(
                {"from_status": old_status, "to_status": new_status, "at": now}
            )

            spend_delta = 0.0
            if new_status == "complete" and actual_cost_usd is not None and entry["actual_cost_usd"] is None:
                entry["actual_cost_usd"] = actual_cost_usd
                spend_delta = actual_cost_usd
                ledger["cumulative_spend_usd"] = round(ledger["cumulative_spend_usd"] + spend_delta, 6)
                ledger["remaining_budget_usd"] = round(
                    ledger["budget_cap_usd"] - ledger["cumulative_spend_usd"], 6
                )
            ledger["updated_at"] = now
            self.save("cost-ledger", ledger)

            manifest = self.load("project-manifest")
            for t in manifest["tasks"]:
                if t["task_id"] == task_id:
                    t["status"] = new_status
                    if provider_task_id is not None:
                        t["provider_task_id"] = provider_task_id
                    if old_status == "failed" and new_status == "queued":
                        t["retry_count"] = t.get("retry_count", 0) + 1
                    break
            manifest["updated_at"] = now
            if spend_delta:
                manifest["budget"]["cumulative_spend_usd"] = round(
                    manifest["budget"]["cumulative_spend_usd"] + spend_delta, 6
                )
            self.save("project-manifest", manifest)
            return entry

    # -- in_progress recovery -------------------------------------------------
    def list_in_progress_tasks(self) -> List[Dict[str, Any]]:
        """Non-mutating. Every ledger entry whose status is 'submitted' or
        'in_progress' — the exact set spec 11.2 requires the engine to recover
        by QUERYING THE PROVIDER before resubmitting, never by blind resubmit."""
        ledger = self.load("cost-ledger")
        return [e for e in ledger["entries"] if e["status"] in ("submitted", "in_progress")]

    def recover(self) -> Dict[str, Any]:
        """Read-only restart-recovery report. Never mutates state and never
        calls a provider itself — that is the job of a later unit's
        recover_tasks.py, which should call the provider's get_task() for
        every entry in must_query_provider (keyed on provider_task_id) and
        then call transition_task() with the reconciled status. Entries that
        never received a provider_task_id (the process died before the
        provider call was actually sent) are safe to requeue directly without
        any provider call, because nothing was ever submitted."""
        in_progress = self.list_in_progress_tasks()
        must_query = [e for e in in_progress if e.get("provider_task_id")]
        never_submitted = [e for e in in_progress if not e.get("provider_task_id")]
        return {
            "checked_at": _now(),
            "in_progress_count": len(in_progress),
            "must_query_provider": must_query,
            "safe_to_requeue": never_submitted,
        }

    # -- deployment receipts --------------------------------------------------
    def append_deployment_receipt(self, receipt: Dict[str, Any]) -> None:
        """Locked (shares the project lock — a deployment receipt is a manifest
        mutation). Appends `receipt` to the append-only deployment-receipts.json
        store after validating it against deployment-receipt.schema.json."""
        validate_kind("deployment-receipt", receipt, label="new receipt")
        with self.lock():
            path = self._path("deployment-receipt")
            receipts: List[Dict[str, Any]] = self.load("deployment-receipt") if path.exists() else []
            receipts.append(receipt)
            self.save("deployment-receipt", receipts)

            manifest = self.load("project-manifest")
            manifest["deployment"][receipt["environment"]] = {
                "url": receipt.get("url"),
                "commit_sha": receipt["commit_sha"],
                "status": receipt["status"],
                "updated_at": receipt["updated_at"],
            }
            manifest["updated_at"] = _now()
            self.save("project-manifest", manifest)

    def latest_deployment_receipt(self, environment: str) -> Optional[Dict[str, Any]]:
        if not self.exists("deployment-receipt"):
            return None
        receipts = self.load("deployment-receipt")
        matching = [r for r in receipts if r["environment"] == environment]
        return matching[-1] if matching else None


# ------------------------------------------------------------------------
# Self-test — mirrors the --self-test convention of the other U2 module.
# Exercises schema validation, atomic-write crash-safety, lock contention +
# stale-lock recovery, idempotency rejection, and the task state machine
# end-to-end against a throwaway temp run_dir. No network, no secrets.
# ------------------------------------------------------------------------
def self_test() -> int:
    fails = 0

    def check(label: str, cond: bool) -> None:
        nonlocal fails
        if cond:
            print(f"  [PASS] {label}")
        else:
            print(f"  [FAIL] {label}")
            fails += 1

    tmp = Path(tempfile.mkdtemp(prefix="cwfe-state-engine-selftest-"))
    try:
        state = ProjectState(tmp)

        manifest = state.create_project(
            project_id="proj-selftest",
            client_slug="acme",
            project_slug="launch",
            deliverable_type="cinematic-landing-page",
            budget_cap_usd=10.0,
        )
        check("create_project writes a schema-valid project-manifest.json", manifest["status"] == "created")
        check("create_project writes a companion cost-ledger.json", state.exists("cost-ledger"))

        try:
            state.create_project(
                project_id="proj-selftest",
                client_slug="acme",
                project_slug="launch",
                deliverable_type="cinematic-landing-page",
                budget_cap_usd=10.0,
            )
            check("create_project refuses to overwrite an existing project", False)
        except StateEngineError:
            check("create_project refuses to overwrite an existing project", True)

        entry1 = state.begin_task(
            provider="kie",
            model="gpt-image-2-text-to-image",
            operation="generate_image",
            params={"prompt": "hero shot", "aspect_ratio": "16:9"},
            estimated_cost_usd=0.03,
        )
        try:
            state.begin_task(
                provider="kie",
                model="gpt-image-2-text-to-image",
                operation="generate_image",
                params={"prompt": "hero shot", "aspect_ratio": "16:9"},
                estimated_cost_usd=0.03,
            )
            check("begin_task rejects a duplicate request_hash (idempotency)", False)
        except IdempotencyViolation:
            check("begin_task rejects a duplicate request_hash (idempotency)", True)

        try:
            state.begin_task(
                provider="kie",
                model="bytedance/seedance-1.5-pro",
                operation="generate_video",
                params={"scene": "way-too-expensive"},
                estimated_cost_usd=999.0,
            )
            check("begin_task hard-stops a call that would exceed the budget cap", False)
        except BudgetExceeded:
            check("begin_task hard-stops a call that would exceed the budget cap", True)

        state.transition_task(entry1["task_id"], "submitted", provider_task_id="kie-task-abc123")
        state.transition_task(entry1["task_id"], "in_progress")
        try:
            state.transition_task(entry1["task_id"], "queued")
            check("transition_task rejects an illegal in_progress -> queued jump", False)
        except InvalidStateTransition:
            check("transition_task rejects an illegal in_progress -> queued jump", True)
        state.transition_task(entry1["task_id"], "complete", actual_cost_usd=0.031)

        ledger = state.load("cost-ledger")
        check(
            "cumulative spend rolls up exactly once on completion",
            abs(ledger["cumulative_spend_usd"] - 0.031) < 1e-9,
        )
        check(
            "project-manifest.budget mirrors the same cumulative spend",
            abs(state.load("project-manifest")["budget"]["cumulative_spend_usd"] - 0.031) < 1e-9,
        )

        entry2 = state.begin_task(
            provider="kie",
            model="bytedance/seedance-1.5-pro",
            operation="generate_video",
            params={"scene": "scene-02-draft"},
            estimated_cost_usd=0.05,
        )
        state.transition_task(entry2["task_id"], "submitted", provider_task_id="kie-task-def456")
        state.transition_task(entry2["task_id"], "in_progress")
        # Simulate a crash: nothing else touches state after this point.
        recovery = state.recover()
        check(
            "recover() reports the interrupted in_progress task for provider re-query",
            recovery["in_progress_count"] == 1 and len(recovery["must_query_provider"]) == 1,
        )
        check(
            "recover() never returns a task as safe_to_requeue once it has a provider_task_id",
            len(recovery["safe_to_requeue"]) == 0,
        )

        # Lock contention: acquire in this process, prove a second acquire in
        # the SAME process (a stand-in for "another live process") is refused.
        lock_a = state.lock()
        lock_a.acquire()
        lock_b = state.lock(stale_after_seconds=900)
        try:
            lock_b.acquire()
            check("a second live lock acquire is refused", False)
        except ProjectLockError:
            check("a second live lock acquire is refused", True)
        lock_a.release()

        # Stale-lock recovery: fabricate a lock file for a pid that cannot be alive.
        dead_pid = 999999
        while _pid_alive(dead_pid) and dead_pid > 2:
            dead_pid -= 1
        lock_path = tmp / ProjectLock.LOCK_FILENAME
        lock_path.write_text(
            json.dumps({"pid": dead_pid, "host": "nowhere", "acquired_at": "1970-01-01T00:00:00Z", "acquired_at_epoch": 0}),
            encoding="utf-8",
        )
        lock_c = state.lock(stale_after_seconds=900)
        try:
            lock_c.acquire()
            check("a lock held by a dead pid is detected and broken, not permanently wedged", True)
            lock_c.release()
        except ProjectLockError:
            check("a lock held by a dead pid is detected and broken, not permanently wedged", False)

        # Atomic-write crash safety: a stray leftover tmp file from a killed
        # writer must never be picked up as the real manifest.
        real_path = tmp / "project-manifest.json"
        before = real_path.read_text(encoding="utf-8")
        stray_tmp = tmp / f".{real_path.name}.deadwriter.tmp"
        stray_tmp.write_text('{"not": "valid", "schema_version": "1.0.0"', encoding="utf-8")  # truncated/corrupt
        after_reload = state.load("project-manifest")
        check(
            "a corrupt/leftover .tmp writer artifact never contaminates a read",
            json.dumps(after_reload, sort_keys=True) == json.dumps(json.loads(before), sort_keys=True),
        )
        stray_tmp.unlink()

        # Schema validation actually rejects a bad instance.
        try:
            state.save("project-manifest", {"schema_version": "1.0.0"})  # missing every other required field
            check("save() rejects a manifest missing required fields", False)
        except SchemaValidationFailed:
            check("save() rejects a manifest missing required fields", True)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"RESULT: FAIL — {fails} self-test check(s) failed.", file=sys.stderr)
        return 1
    print("RESULT: PASS — state engine self-test green.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        sys.exit(self_test())
    parser.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
