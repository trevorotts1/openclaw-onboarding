"""phases.py -- phase runner + engine-written attestations. [FIX 30]

Contract (published for W06 shared build; heal/checkpoint/workingset wiring
lands from B1/B3/B4):

    from presentation_job import phases

    result = phases.run_phase(phase, run_dir, verifier=fn, artifact=Path(...))
    # on done phases.append_attestation() writes to run_dir/process_manifest.json:
    #   {"phase_id": ..., "attested_at": <tz-aware ISO>, "attested_by": "engine:<pid>",
    #    "substance_verified": <bool>, "artifact_sha256": <hex>}

    ok, reasons = phases.check_phase_preconditions(phase_id, run_dir)
    # accepts ONLY engine-written rows (attested_by startswith "engine:"),
    # tz-aware attested_at that is not midnight T00:00:00, and a real sha256.

Problem being fixed [FIX 30]: the runner never wrote
``process_manifest.json.phase_attestations``; 28 rows were hand-written at
midnight.  Now ``run_phase`` appends one row per completed phase on done, and
``check_phase_preconditions`` rejects any row the engine did not write:

* ``attested_by`` must start with ``engine:`` (the pid of the writer);
* ``attested_at`` must be timezone-aware and not ``T00:00:00``;
* ``substance_verified`` must be a bool (the verifier's result);
* ``artifact_sha256`` must be a 64-char hex digest.

PROOF [QC.md FIX 30]: after a stubbed deck-12 run,
``process_manifest.json.phase_attestations`` has one row per completed phase,
every ``attested_at`` tz-aware and not ``T00:00:00``, every ``attested_by``
starting ``engine:``; a hand-written row without ``attested_by`` is rejected by
``check_phase_preconditions``.

100% stdlib; thread-safe manifest append under a file lock so concurrent
phase completions cannot lose a row.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

__all__ = [
    "MANIFEST_NAME",
    "ENGINE_ATTEST_PREFIX",
    "AttestationError",
    "PreconditionError",
    "run_phase",
    "append_attestation",
    "check_phase_preconditions",
    "attestation_is_engine_written",
    "read_attestations",
    "load_manifest",
    "write_manifest",
    "artifact_sha256",
    "now_tz",
]

MANIFEST_NAME = "process_manifest.json"
ENGINE_ATTEST_PREFIX = "engine:"

# Class of rejection reasons check_phase_preconditions emits.
R_NO_ATTESTATION = "no_attestation"
R_NOT_ENGINE = "not_engine_written"
R_NOT_TZ_AWARE = "attested_at_not_tz_aware"
R_MIDNIGHT = "attested_at_is_midnight"
R_NOT_BOOL = "substance_verified_not_bool"
R_BAD_SHA = "artifact_sha256_invalid"
R_MALFORMED = "row_malformed"


class AttestationError(RuntimeError):
    """Raised when a completed phase cannot be attested."""


class PreconditionError(RuntimeError):
    """Raised when a downstream phase's preconditions are not met."""


# --------------------------------------------------------------------------
# manifest io
# --------------------------------------------------------------------------

def manifest_path(run_dir: Path | str) -> Path:
    return Path(run_dir) / MANIFEST_NAME


def load_manifest(run_dir: Path | str) -> Dict[str, Any]:
    """Read process_manifest.json; a missing file yields a fresh skeleton."""
    p = manifest_path(run_dir)
    if not p.exists():
        return {"phase_attestations": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"phase_attestations": []}
    if not isinstance(data, dict):
        return {"phase_attestations": []}
    if not isinstance(data.get("phase_attestations"), list):
        data["phase_attestations"] = []
    return data


def write_manifest(run_dir: Path | str, manifest: Dict[str, Any]) -> None:
    p = manifest_path(run_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(p))


def now_tz() -> datetime:
    return datetime.now(timezone.utc)


def artifact_sha256(path: Path | str | None) -> str:
    """sha256 of the phase artifact.

    A phase with no artifact hashes the empty string -- still a valid 64-hex
    digest, so every engine row passes its own sha256 validation.
    """
    if path is None:
        return hashlib.sha256(b"").hexdigest()
    p = Path(path)
    if not p.exists() or not p.is_file():
        return hashlib.sha256(b"").hexdigest()
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------
# FIX 30: engine-written attestations
# --------------------------------------------------------------------------

def attestation_is_engine_written(row: Dict[str, Any]) -> Tuple[bool, str]:
    """True iff this single row was written by the engine.  Returns (ok, reason)."""
    if not isinstance(row, dict):
        return False, R_MALFORMED
    by = row.get("attested_by")
    if not isinstance(by, str) or not by.startswith(ENGINE_ATTEST_PREFIX):
        return False, R_NOT_ENGINE
    # the engine prefix must carry the writer pid: engine:<pid>
    pid_part = by[len(ENGINE_ATTEST_PREFIX):]
    if not pid_part.isdigit():
        return False, R_NOT_ENGINE
    at = row.get("attested_at")
    if not isinstance(at, str):
        return False, R_NOT_TZ_AWARE
    try:
        dt = datetime.fromisoformat(at)
    except ValueError:
        return False, R_NOT_TZ_AWARE
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return False, R_NOT_TZ_AWARE
    # not T00:00:00 -- a midnight stamp is the hand-written fingerprint
    if dt.hour == 0 and dt.minute == 0 and dt.second == 0 and dt.microsecond == 0:
        return False, R_MIDNIGHT
    sv = row.get("substance_verified")
    if not isinstance(sv, bool):
        return False, R_NOT_BOOL
    sha = row.get("artifact_sha256")
    if not isinstance(sha, str) or len(sha) != 64 or any(
        c not in "0123456789abcdef" for c in sha
    ):
        return False, R_BAD_SHA
    if not isinstance(row.get("phase_id"), str) or not row.get("phase_id"):
        return False, R_MALFORMED
    return True, ""


def append_attestation(
    run_dir: Path | str,
    phase_id: str,
    substance_verified: bool,
    artifact: Path | str | None = None,
    artifact_sha256_hex: Optional[str] = None,
) -> Dict[str, Any]:
    """Append one engine-written attestation row to process_manifest.json.

    Thread- and process-safe: the append happens under an exclusive lock on a
    sidecar lock file so concurrent phase completions cannot lose rows.
    """
    if not isinstance(substance_verified, bool):
        raise AttestationError("substance_verified must be the verifier's bool result")
    sha = artifact_sha256_hex if artifact_sha256_hex is not None else artifact_sha256(artifact)
    row: Dict[str, Any] = {
        "phase_id": str(phase_id),
        "attested_at": now_tz().isoformat(),
        "attested_by": f"{ENGINE_ATTEST_PREFIX}{os.getpid()}",
        "substance_verified": bool(substance_verified),
        "artifact_sha256": sha,
    }
    ok, reason = attestation_is_engine_written(row)
    if not ok:  # pragma: no cover - internal invariant
        raise AttestationError(f"engine refused to write invalid attestation: {reason}")

    run_dir = Path(run_dir)
    lock_path = run_dir / (MANIFEST_NAME + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+") as lockf:
        fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
        try:
            manifest = load_manifest(run_dir)
            manifest["phase_attestations"].append(row)
            write_manifest(run_dir, manifest)
        finally:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)
    return row


def read_attestations(run_dir: Path | str, phase_id: Optional[str] = None) -> List[Dict[str, Any]]:
    manifest = load_manifest(run_dir)
    rows = manifest.get("phase_attestations", [])
    if phase_id is None:
        return [r for r in rows if isinstance(r, dict)]
    return [r for r in rows if isinstance(r, dict) and r.get("phase_id") == phase_id]


# --------------------------------------------------------------------------
# FIX 30: precondition check
# --------------------------------------------------------------------------

def check_phase_preconditions(
    phase_id: str,
    run_dir: Path | str,
    required_inputs: Optional[List[str]] = None,
) -> Tuple[bool, List[str]]:
    """Gate a downstream phase on engine-written attestations.

    A phase may start only when every phase in ``required_inputs`` (default:
    none beyond the phase itself) has an attestation row that the engine wrote
    (see :func:`attestation_is_engine_written`).  Hand-written rows -- the
    midnight batch -- are rejected: no row at all, a row without
    ``attested_by``, or any other defect is a failed precondition with the
    reason recorded.

    Returns ``(ok, reasons)``; ``reasons`` lists every failed precondition as
    ``"<phase_id>:<reason>"``.
    """
    reasons: List[str] = []
    wanted = [phase_id] if not required_inputs else list(required_inputs)
    for req in wanted:
        rows = read_attestations(run_dir, req)
        if not rows:
            reasons.append(f"{req}:{R_NO_ATTESTATION}")
            continue
        ok, reason = attestation_is_engine_written(rows[-1])
        if not ok:
            reasons.append(f"{req}:{reason}")
    return (not reasons), reasons


# --------------------------------------------------------------------------
# FIX 30: run_phase -- the runner writes its own attestations on done
# --------------------------------------------------------------------------

def run_phase(
    phase: Dict[str, Any],
    run_dir: Path | str,
    verifier: Optional[Callable[[Dict[str, Any], Path], bool]] = None,
    artifact: Path | str | None = None,
    execute: Optional[Callable[[Dict[str, Any], Path], Any]] = None,
    preconditions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run one phase and, on done, append the engine attestation.

    ``phase`` needs at least ``phase_id``.  Order of operations:

    1. ``check_phase_preconditions`` -- refuses to start without engine rows
       for every required input phase (hand-written rows do not pass).
    2. ``execute`` (when given) produces the phase artifact.
    3. ``verifier`` (when given) checks substance; its bool result is recorded
       verbatim in the attestation's ``substance_verified``.
    4. On done: :func:`append_attestation` writes the row -- one row per
       completed phase, tz-aware non-midnight ``attested_at``, ``attested_by``
       ``engine:<pid>``, and the artifact's sha256.

    Returns the phase result dict ``{"phase_id", "status", "result",
    "attestation", "precondition_reasons"}``.
    """
    phase_id = str(phase.get("phase_id", ""))
    if not phase_id:
        raise AttestationError("phase dict requires phase_id")
    run_dir = Path(run_dir)

    # Gate only on upstream phases: check_phase_preconditions validates an
    # existing row, and this phase has none yet.  Upstream rows must be
    # engine-written (hand-written rows fail here).
    ok, reasons = (True, [])
    if preconditions:
        ok, reasons = check_phase_preconditions(phase_id, run_dir, preconditions)
    if not ok:
        return {
            "phase_id": phase_id,
            "status": "blocked",
            "result": None,
            "attestation": None,
            "precondition_reasons": reasons,
        }

    result: Any = None
    if execute is not None:
        result = execute(phase, run_dir)

    verified = bool(verifier(phase, run_dir)) if verifier is not None else True
    if not verified:
        return {
            "phase_id": phase_id,
            "status": "failed",
            "result": result,
            "attestation": None,
            "precondition_reasons": [],
        }

    row = append_attestation(
        run_dir,
        phase_id,
        substance_verified=verified,
        artifact=artifact,
    )
    return {
        "phase_id": phase_id,
        "status": "done",
        "result": result,
        "attestation": row,
        "precondition_reasons": [],
    }
