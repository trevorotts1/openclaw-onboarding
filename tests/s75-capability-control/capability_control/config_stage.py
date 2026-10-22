"""Staged configuration changes with whole-config validation (finding D30).

stage -> validate the entire resulting configuration against the runtime
schema -> apply atomically -> verify the supported reload. An invalid proposal
is rejected BEFORE activation and the previous usable configuration stays
active. Unrelated department models, credentials, aliases, heartbeat policies
and user preferences survive unchanged: only owned sections may be written.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .runtime_schema import OwnedMerge, RuntimeSchema, SchemaError, assert_writable_target


def canonical_digest(doc: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass
class StageResult:
    accepted: bool
    errors: List[SchemaError] = field(default_factory=list)
    merged: Optional[Dict[str, Any]] = None
    digest: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "errors": [e.as_dict() for e in self.errors],
            "digest": self.digest,
        }


@dataclass
class ApplyResult:
    applied: bool
    reload_verified: bool
    digest: Optional[str] = None
    rolled_back: bool = False
    detail: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


class ConfigStage:
    def __init__(self, path: str, schema: RuntimeSchema, owned_sections: List[str],
                 cache_paths: Optional[List[str]] = None,
                 extra_validators: Optional[List[Any]] = None):
        self.path = os.path.realpath(path)
        self.schema = schema
        self.merge = OwnedMerge(owned_sections=owned_sections)
        self.cache_paths = [os.path.realpath(p) for p in (cache_paths or [])]
        self.extra_validators = extra_validators or []

    # ---- read -------------------------------------------------------
    def load(self) -> Dict[str, Any]:
        with open(self.path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    # ---- stage ------------------------------------------------------
    def stage(self, proposal: Dict[str, Any]) -> StageResult:
        """Validate the ENTIRE resulting configuration. Never activates.

        On rejection the live configuration file is untouched: the previous
        usable configuration remains active.
        """
        base = self.load()
        try:
            merged = self.merge.merge(base, proposal)
        except ValueError as exc:
            return StageResult(accepted=False, errors=[SchemaError("$", str(exc))])
        errors = self.schema.validate(merged)
        for validator in self.extra_validators:
            errors.extend(validator(merged) or [])
        if errors:
            return StageResult(accepted=False, errors=errors)
        return StageResult(accepted=True, merged=merged, digest=canonical_digest(merged))

    # ---- apply ------------------------------------------------------
    def apply(self, staged: StageResult, read_back=None) -> ApplyResult:
        """Atomic apply + reload verification of a previously staged result.

        read_back: supported reload hook; defaults to re-reading the file.
        If the reload does not match the staged digest, the previous
        configuration is restored (in-memory; no backup artifacts are left).
        """
        if not staged.accepted or staged.merged is None:
            return ApplyResult(applied=False, reload_verified=False, detail="nothing valid staged")
        assert_writable_target(self.path, self.cache_paths)
        with open(self.path, "r", encoding="utf-8") as fh:
            previous_bytes = fh.read()
        previous_digest = canonical_digest(json.loads(previous_bytes))
        payload = json.dumps(staged.merged, indent=1, sort_keys=True) + "\n"
        directory = os.path.dirname(self.path)
        fd, tmp = tempfile.mkstemp(prefix=".s75w04u2-staged-", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)  # atomic on the same filesystem
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        # verify the supported reload
        if read_back is None:
            reloaded = self.load()
        else:
            reloaded = read_back()
        reload_ok = canonical_digest(reloaded) == staged.digest
        if not reload_ok:
            # restore previous usable configuration
            fd, tmp = tempfile.mkstemp(prefix=".s75w04u2-restore-", dir=directory)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(previous_bytes)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
            return ApplyResult(applied=False, reload_verified=False, rolled_back=True,
                               digest=previous_digest,
                               detail="reload did not match staged digest; previous configuration restored")
        return ApplyResult(applied=True, reload_verified=True, digest=staged.digest,
                           detail="applied atomically and reload verified")
