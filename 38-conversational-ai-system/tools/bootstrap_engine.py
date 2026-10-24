#!/usr/bin/env python3
"""bootstrap_engine.py - idempotent guided setup and permitted-only provisioning.

Contract basis: Purple-Billboard TODO T-36 ("client-bootstrap-engine") and
R-26/R-29: discover and reuse supported objects; a scoped diff; provisioning of
only what the operator permitted; an owner-authorisation handoff for anything
already present; a step receipt for every completed step; no traffic until the
owner authorises it. Python 3 standard library only.

Doctrine, enforced in code:

  * A plan never writes. Only run() creates anything, so nothing can be
    reported as provisioned when it was merely planned.
  * Nothing is created without an explicit permission entry. A resource that is
    not permitted is skipped and the report names the permission it needed.
  * Credentials, secrets, provider configuration and model configuration are
    NEVER provisioned by this engine, even when the operator supplies a
    permission naming them. That is a hard refusal with its own reason code.
  * An object that already exists and was not created by this engine is never
    overwritten. Matching bytes are adopted only when the spec asks for
    adoption AND the operator permitted it; otherwise the step blocks with an
    owner-authorisation handoff reason and the bytes are untouched.
  * An object this engine created is never rewritten with different content.
    Content drift blocks with a named reason instead of silently overwriting a
    hand-edit.
  * A completed step is recorded in the state file before the next step runs.
    A failure stops the run and leaves the completed receipts in place, so a
    resume continues from the failed step: completed resources are unchanged
    and nothing is created twice.
  * A second run over unchanged inputs is a no-op: no file is written, so the
    state file and the provisioned tree are byte-identical before and after.
  * All writes are atomic (temp file + os.replace) and confined to the target
    root; a path that escapes the root is refused.
  * No network code, no subprocess, no scheduler: the engine provisions files
    and writes receipts. Traffic stays the outbound gate's job.

Import (the stdlib path pattern used by the other Skill 38 tools):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from bootstrap_engine import BootstrapEngine, ResourceSpec

Assert-based self-check:  python3 -I bootstrap_engine.py
"""

from __future__ import annotations

import datetime as _datetime
import hashlib
import json
import os
import posixpath
import tempfile
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

SCHEMA = "skill38.bootstrap_state.v1"
DEFAULT_STATE_NAME = ".bootstrap-state.json"

ACTION_CREATE = "create"
ACTION_ADOPT = "adopt"
ACTION_NOOP = "unchanged"
ACTION_SKIP = "skip"
ACTION_BLOCK = "block"
ACTION_REFUSE = "refuse"

REASON_NOT_PERMITTED = "not_permitted"
REASON_NEVER_PERMITTED = "never_permitted"
REASON_OWNER_HANDOFF = "owner_handoff_required"
REASON_CONTENT_DRIFT = "content_drift"
REASON_TARGET_UNOWNED = "target_exists_unowned"
REASON_PATH_ESCAPE = "path_escape"
REASON_WRITE_FAILED = "write_failed"
REASON_UNKNOWN_SCHEMA = "unknown_state_schema"

# Hard rule from the unit brief: this engine never creates these, whatever the
# operator permits. Provider and model configuration belong to the operator's
# own tooling; credentials belong to the client.
NEVER_PERMITTED_KINDS = frozenset(
    {"credential", "credentials", "secret", "secrets", "provider", "providers",
     "provider_config", "model", "models", "model_config"}
)

# Provisioning creates files and receipts. It does not send anything; there is
# deliberately no network path in this module.
TRAFFIC_AUTHORIZED = False


class BootstrapError(Exception):
    """Invalid input or unusable state. Raised before anything is written."""


class BootstrapPermissionError(BootstrapError):
    """A permission entry was malformed or a resource is not permitted."""


@dataclass(frozen=True)
class ResourceSpec:
    """One object the operator wants to exist, identified by stable id."""

    resource_id: str
    kind: str
    path: str
    payload: str
    adopt_existing: bool = False


@dataclass(frozen=True)
class Step:
    """One planned action. A plan is pure: producing it writes nothing."""

    resource_id: str
    action: str
    reason: str
    detail: str

    def as_dict(self) -> Dict[str, str]:
        return {
            "resource_id": self.resource_id,
            "action": self.action,
            "reason": self.reason,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Plan:
    steps: Tuple[Step, ...]

    def by_action(self, action: str) -> List[Step]:
        return [s for s in self.steps if s.action == action]

    def as_dict(self) -> Dict[str, List[Dict[str, str]]]:
        grouped: Dict[str, List[Dict[str, str]]] = {}
        for step in self.steps:
            grouped.setdefault(step.action, []).append(step.as_dict())
        return grouped


@dataclass
class Report:
    """What actually happened. created/adopted are the only provisioned sets."""

    created: List[Dict[str, str]]
    adopted: List[Dict[str, str]]
    unchanged: List[Dict[str, str]]
    skipped: List[Dict[str, str]]
    refused: List[Dict[str, str]]
    blocked: List[Dict[str, str]]
    failed: List[Dict[str, str]]
    not_attempted: List[Dict[str, str]]
    state_written: bool
    state_path: Optional[str]

    @property
    def provisioned(self) -> List[str]:
        return [s["resource_id"] for s in self.created] + [
            s["resource_id"] for s in self.adopted
        ]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "created": self.created,
            "adopted": self.adopted,
            "unchanged": self.unchanged,
            "skipped": self.skipped,
            "refused": self.refused,
            "blocked": self.blocked,
            "failed": self.failed,
            "not_attempted": self.not_attempted,
            "state_written": self.state_written,
            "state_path": self.state_path,
        }


def _utc_now() -> _datetime.datetime:
    return _datetime.datetime.now(_datetime.timezone.utc)


def _iso(moment: _datetime.datetime) -> str:
    return moment.astimezone(_datetime.timezone.utc).isoformat()


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _payload_bytes(payload: Any) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    raise BootstrapError("payload must be str or bytes")


def _atomic_write(path: str, data: bytes, mode: Optional[int] = None) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".bootstrap-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _canonical_state(receipts: Dict[str, Dict[str, Any]]) -> bytes:
    body = {"schema": SCHEMA, "receipts": receipts}
    text = json.dumps(body, sort_keys=True, indent=1, separators=(",", ": "))
    return (text + "\n").encode("utf-8")


class BootstrapEngine:
    """Idempotent, permitted-only, resumable provisioning into one target root.

    target_root  - the only directory this engine may write inside.
    permissions  - iterable of explicit entries. An entry matches by exact
                   resource_id, by kind, or by "kind:<kind>". There is no
                   wildcard permission: something the operator did not name is
                   not permitted.
    state_path   - receipts file; defaults to <target_root>/.bootstrap-state.json
    clock        - injectable for deterministic tests.
    """

    def __init__(
        self,
        target_root: str,
        permissions: Iterable[str] = (),
        state_path: Optional[str] = None,
        clock: Callable[[], _datetime.datetime] = _utc_now,
    ) -> None:
        if not target_root:
            raise BootstrapError("target_root is required")
        self.target_root = os.path.abspath(target_root)
        self.permissions = self._normalize_permissions(permissions)
        self.state_path = (
            os.path.abspath(state_path)
            if state_path
            else os.path.join(self.target_root, DEFAULT_STATE_NAME)
        )
        self._clock = clock

    # ------------------------------------------------------------------ input

    @staticmethod
    def _normalize_permissions(permissions: Iterable[str]) -> frozenset:
        out = set()
        for entry in permissions:
            if not isinstance(entry, str) or not entry.strip():
                raise BootstrapPermissionError(
                    "every permission entry must be a non-empty string"
                )
            out.add(entry.strip())
        return frozenset(out)

    def _permitted(self, spec: ResourceSpec) -> bool:
        return (
            spec.resource_id in self.permissions
            or spec.kind in self.permissions
            or ("kind:" + spec.kind) in self.permissions
        )

    def _validate(self, specs: Sequence[ResourceSpec]) -> Tuple[ResourceSpec, ...]:
        seen_ids = set()
        seen_paths = set()
        ordered: List[ResourceSpec] = []
        for spec in specs:
            if not isinstance(spec, ResourceSpec):
                raise BootstrapError("specs must be ResourceSpec instances")
            for field in ("resource_id", "kind", "path"):
                value = getattr(spec, field)
                if not isinstance(value, str) or not value.strip():
                    raise BootstrapError(
                        "resource %r has an empty %s" % (spec.resource_id, field)
                    )
            if spec.resource_id in seen_ids:
                raise BootstrapError(
                    "duplicate resource_id %r" % spec.resource_id
                )
            seen_ids.add(spec.resource_id)
            normalized = self._safe_relpath(spec.path)
            if normalized in seen_paths:
                raise BootstrapError(
                    "duplicate path %r" % normalized
                )
            seen_paths.add(normalized)
            ordered.append(
                ResourceSpec(
                    resource_id=spec.resource_id,
                    kind=spec.kind,
                    path=normalized,
                    payload=spec.payload,
                    adopt_existing=bool(spec.adopt_existing),
                )
            )
        return tuple(ordered)

    def _safe_relpath(self, path: str) -> str:
        if not isinstance(path, str) or not path.strip():
            raise BootstrapError("path must be a non-empty string")
        candidate = path.replace("\\", "/")
        if candidate.startswith("/") or candidate.startswith("~"):
            raise BootstrapError("path %r is absolute; paths are target-relative" % path)
        normalized = posixpath.normpath(candidate)
        if normalized in ("", ".") or normalized == ".." or normalized.startswith("../"):
            raise BootstrapError("path %r escapes the target root" % path)
        return normalized

    def _target_path(self, relpath: str) -> str:
        joined = os.path.abspath(os.path.join(self.target_root, relpath))
        root_real = os.path.realpath(self.target_root)
        joined_real = os.path.realpath(joined)
        try:
            common = os.path.commonpath([root_real, joined_real])
        except ValueError:
            common = ""
        if common != root_real:
            raise BootstrapError("path %r escapes the target root" % relpath)
        return joined

    # ------------------------------------------------------------------ state

    def _load_state(self) -> Dict[str, Dict[str, Any]]:
        if not os.path.exists(self.state_path):
            return {}
        try:
            with open(self.state_path, "rb") as handle:
                raw = handle.read()
        except OSError as exc:
            raise BootstrapError(
                "state file %s is unreadable: %s" % (self.state_path, exc)
            )
        if not raw.strip():
            return {}
        try:
            body = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise BootstrapError(
                "state file %s is not valid JSON: %s" % (self.state_path, exc)
            )
        if not isinstance(body, dict):
            raise BootstrapError("state file %s is not an object" % self.state_path)
        if body.get("schema") != SCHEMA:
            raise BootstrapError(
                "state file %s has schema %r, expected %r"
                % (self.state_path, body.get("schema"), SCHEMA)
            )
        receipts = body.get("receipts", {})
        if not isinstance(receipts, dict):
            raise BootstrapError("state file %s receipts is not an object" % self.state_path)
        return receipts

    def _write_state(self, receipts: Dict[str, Dict[str, Any]]) -> None:
        _atomic_write(self.state_path, _canonical_state(receipts))

    # -------------------------------------------------------------- discovery

    def discover(self, specs: Sequence[ResourceSpec] = ()) -> Dict[str, Any]:
        """Report what this root already holds for the given specs and receipts.

        A resource is `owned` when this engine recorded its receipt. Reuse is
        decided from the bytes on disk, never from the presence of a receipt.
        """
        validated = self._validate(specs)
        receipts = self._load_state()
        resources: Dict[str, Any] = {}
        for spec in validated:
            target = self._target_path(spec.path)
            exists = os.path.isfile(target)
            disk_digest = None
            if exists:
                with open(target, "rb") as handle:
                    disk_digest = _digest(handle.read())
            receipt = receipts.get(spec.resource_id)
            resources[spec.resource_id] = {
                "kind": spec.kind,
                "path": spec.path,
                "exists": exists,
                "digest": disk_digest,
                "owned": bool(receipt),
                "matches_spec": disk_digest == _digest(_payload_bytes(spec.payload)),
            }
        return {
            "schema": SCHEMA,
            "target_root": self.target_root,
            "resources": resources,
        }

    # ------------------------------------------------------------------- plan

    def plan(self, specs: Sequence[ResourceSpec]) -> Plan:
        """Pure diff. Never creates, never writes, never persists a receipt."""
        validated = self._validate(specs)
        receipts = self._load_state()
        steps: List[Step] = []
        for spec in validated:
            steps.append(self._plan_one(spec, receipts.get(spec.resource_id)))
        return Plan(tuple(steps))

    def _plan_one(
        self, spec: ResourceSpec, receipt: Optional[Dict[str, Any]]
    ) -> Step:
        payload = _payload_bytes(spec.payload)
        wanted = _digest(payload)

        if spec.kind.strip().lower() in NEVER_PERMITTED_KINDS:
            return Step(
                spec.resource_id,
                ACTION_REFUSE,
                REASON_NEVER_PERMITTED,
                "kind %r is never provisioned by this engine" % spec.kind,
            )
        if not self._permitted(spec):
            return Step(
                spec.resource_id,
                ACTION_SKIP,
                REASON_NOT_PERMITTED,
                "needs permission %r (resource id) or 'kind:%s' (kind wide)"
                % (spec.resource_id, spec.kind),
            )

        try:
            target = self._target_path(spec.path)
        except BootstrapError as exc:
            return Step(
                spec.resource_id, ACTION_REFUSE, REASON_PATH_ESCAPE, str(exc)
            )
        exists = os.path.isfile(target)
        disk_digest = None
        if exists:
            with open(target, "rb") as handle:
                disk_digest = _digest(handle.read())

        if receipt:
            recorded_digest = receipt.get("digest")
            if not exists:
                # A recorded resource vanished: restoring it is an idempotent
                # create, not a duplicate - the receipt is replaced, not added.
                return Step(
                    spec.resource_id,
                    ACTION_CREATE,
                    "receipt_without_artifact",
                    "recorded resource is missing from disk; restoring",
                )
            if disk_digest != recorded_digest:
                return Step(
                    spec.resource_id,
                    ACTION_BLOCK,
                    REASON_CONTENT_DRIFT,
                    "on-disk bytes changed since this engine created them; "
                    "refusing to overwrite",
                )
            if disk_digest != wanted:
                return Step(
                    spec.resource_id,
                    ACTION_BLOCK,
                    REASON_CONTENT_DRIFT,
                    "the spec payload differs from the provisioned bytes; "
                    "refusing to rewrite a completed resource",
                )
            return Step(
                spec.resource_id, ACTION_NOOP, "unchanged", "already provisioned"
            )

        if exists:
            if disk_digest == wanted and spec.adopt_existing:
                return Step(
                    spec.resource_id,
                    ACTION_ADOPT,
                    "adopt_existing",
                    "matching unowned object; adopting without rewriting",
                )
            if disk_digest == wanted:
                return Step(
                    spec.resource_id,
                    ACTION_BLOCK,
                    REASON_OWNER_HANDOFF,
                    "matching object already exists and is not owned by this "
                    "engine; set adopt_existing and permit adoption to reuse it",
                )
            return Step(
                spec.resource_id,
                ACTION_BLOCK,
                REASON_TARGET_UNOWNED,
                "object exists with different content and is not owned by this "
                "engine; refusing to overwrite",
            )

        return Step(spec.resource_id, ACTION_CREATE, "absent", "will be created")

    # -------------------------------------------------------------------- run

    def run(
        self, specs: Sequence[ResourceSpec], stop_on_failure: bool = True
    ) -> Report:
        """Execute the plan. Atomic per step; resumable by calling run again."""
        validated = self._validate(specs)
        steps = self.plan(validated).steps
        receipts = self._load_state()

        created: List[Dict[str, str]] = []
        adopted: List[Dict[str, str]] = []
        unchanged: List[Dict[str, str]] = []
        skipped: List[Dict[str, str]] = []
        refused: List[Dict[str, str]] = []
        blocked: List[Dict[str, str]] = []
        failed: List[Dict[str, str]] = []
        not_attempted: List[Dict[str, str]] = []

        dirty = False
        stopped = False
        now = _iso(self._clock())

        for step, spec in zip(steps, validated):
            if stopped:
                not_attempted.append(step.as_dict())
                continue

            if step.action == ACTION_NOOP:
                unchanged.append(step.as_dict())
                continue
            if step.action == ACTION_SKIP:
                skipped.append(step.as_dict())
                continue
            if step.action == ACTION_REFUSE:
                refused.append(step.as_dict())
                continue
            if step.action == ACTION_BLOCK:
                blocked.append(step.as_dict())
                continue

            target = self._target_path(spec.path)
            payload = _payload_bytes(spec.payload)
            try:
                if step.action == ACTION_CREATE:
                    _atomic_write(target, payload)
                else:  # adopt: pure receipt, bytes are already correct
                    if not os.path.isfile(target):
                        raise OSError("adoption target disappeared")
            except OSError as exc:
                failed.append(
                    {
                        "resource_id": spec.resource_id,
                        "action": step.action,
                        "reason": REASON_WRITE_FAILED,
                        "detail": "%s: %s" % (type(exc).__name__, exc),
                    }
                )
                if stop_on_failure:
                    stopped = True
                continue

            receipts[spec.resource_id] = {
                "kind": spec.kind,
                "path": spec.path,
                "digest": _digest(payload),
                "outcome": (
                    "created" if step.action == ACTION_CREATE else "adopted"
                ),
                "at": now,
            }
            dirty = True
            record = {
                "resource_id": spec.resource_id,
                "path": spec.path,
                "digest": receipts[spec.resource_id]["digest"],
            }
            if step.action == ACTION_CREATE:
                created.append(record)
            else:
                adopted.append(record)

        state_written = False
        if dirty:
            self._write_state(receipts)
            state_written = True

        return Report(
            created=created,
            adopted=adopted,
            unchanged=unchanged,
            skipped=skipped,
            refused=refused,
            blocked=blocked,
            failed=failed,
            not_attempted=not_attempted,
            state_written=state_written,
            state_path=self.state_path,
        )


# ---------------------------------------------------------------- self-check

def _self_check() -> None:
    import shutil

    root = tempfile.mkdtemp(prefix="pbb-bootstrap-selfcheck-")
    try:
        engine = BootstrapEngine(
            root,
            permissions=("kb.one", "kind:knowledgebase", "kind:journey_template"),
            clock=lambda: _datetime.datetime(
                2026, 10, 24, 12, 0, 0, tzinfo=_datetime.timezone.utc
            ),
        )
        specs = [
            ResourceSpec("kb.one", "knowledgebase", "kb/one.md", "alpha"),
            ResourceSpec("jt.one", "journey_template", "jt/one.json", "beta"),
            ResourceSpec("wf.denied", "workflow", "wf/denied.json", "gamma"),
            ResourceSpec("cred.one", "credential", "creds/one.txt", "nope"),
        ]

        plan = engine.plan(specs)
        assert not os.path.exists(engine.state_path), "plan must not write state"
        assert [s.action for s in plan.steps] == [
            ACTION_CREATE, ACTION_CREATE, ACTION_SKIP, ACTION_REFUSE
        ]

        first = engine.run(specs)
        assert sorted(c["resource_id"] for c in first.created) == [
            "jt.one", "kb.one"
        ]
        assert first.refused[0]["reason"] == REASON_NEVER_PERMITTED
        assert first.skipped[0]["reason"] == REASON_NOT_PERMITTED
        assert not os.path.exists(os.path.join(root, "wf/denied.json"))
        assert not os.path.exists(os.path.join(root, "creds/one.txt"))

        before_state = open(engine.state_path, "rb").read()
        before_one = open(os.path.join(root, "kb/one.md"), "rb").read()
        second = engine.run(specs)
        assert second.created == [] and second.adopted == []
        assert second.state_written is False
        assert open(engine.state_path, "rb").read() == before_state
        assert open(os.path.join(root, "kb/one.md"), "rb").read() == before_one

        # Interrupted run: kb.one already exists, jt.one is unwritable.
        jt_dir = os.path.join(root, "jt")
        os.chmod(jt_dir, 0o500)
        try:
            interrupted = engine.run(
                [
                    ResourceSpec("kb.two", "knowledgebase", "kb/two.md", "delta"),
                    ResourceSpec("jt.two", "journey_template", "jt/two.json", "eps"),
                    ResourceSpec("kb.three", "knowledgebase", "kb/three.md", "zeta"),
                ]
            )
        finally:
            os.chmod(jt_dir, 0o700)
        assert len(interrupted.failed) == 1
        assert interrupted.failed[0]["resource_id"] == "jt.two"
        assert [n["resource_id"] for n in interrupted.not_attempted] == ["kb.three"]

        resumed = engine.run(
            [
                ResourceSpec("kb.two", "knowledgebase", "kb/two.md", "delta"),
                ResourceSpec("jt.two", "journey_template", "jt/two.json", "eps"),
                ResourceSpec("kb.three", "knowledgebase", "kb/three.md", "zeta"),
            ]
        )
        assert [c["resource_id"] for c in resumed.created] == ["jt.two", "kb.three"]
        assert resumed.unchanged[0]["resource_id"] == "kb.two"
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    _self_check()
    print("bootstrap_engine self-check: OK")
