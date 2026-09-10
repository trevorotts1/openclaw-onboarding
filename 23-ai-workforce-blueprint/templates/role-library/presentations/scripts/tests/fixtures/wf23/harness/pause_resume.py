"""WF23 prep: pause/resume checkpoint harness TEMPLATE (NOT acceptance).

Atomic JSON checkpoint save/load for the pause/resume leg: pause mid-intake
or mid-run, exit the host, resume, continue without repeating completed
work. Hermetic: tempfile/JSON only, no engine, no subprocess.

Checkpoint schema:
  {"presentation_id", "company_id", "revision": int,
   "answers": {...}, "completed_units": [...], "saved_at": iso-ts}

Rules (fail-closed):
  - save refuses blank presentation_id/company_id and non-dict answers.
  - load refuses missing/corrupt files (UNDETERMINED, never an empty pass),
    identity mismatch (company/presentation must match the resume request),
    and revision rollback (incoming revision < stored revision).
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class CheckpointError(ValueError):
    pass


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def save_checkpoint(path: Path, *, presentation_id: str, company_id: str,
                    answers: dict, completed_units: list,
                    revision: int = 1) -> Path:
    if not str(presentation_id or "").strip():
        raise CheckpointError("presentation_id is required")
    if not str(company_id or "").strip():
        raise CheckpointError("company_id is required")
    if not isinstance(answers, dict):
        raise CheckpointError("answers must be a dict")
    if not isinstance(completed_units, list):
        raise CheckpointError("completed_units must be a list")
    if not isinstance(revision, int) or revision < 1:
        raise CheckpointError("revision must be a positive int")
    doc = {"presentation_id": presentation_id, "company_id": company_id,
           "revision": revision, "answers": answers,
           "completed_units": completed_units, "saved_at": _utcnow()}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".ckpt-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def load_checkpoint(path: Path, *, presentation_id: str | None = None,
                    company_id: str | None = None,
                    min_revision: int = 1) -> dict:
    path = Path(path)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CheckpointError(f"checkpoint missing: {path} (UNDETERMINED, never empty-pass)")
    except (json.JSONDecodeError, OSError) as exc:
        raise CheckpointError(f"checkpoint unreadable: {path}: {exc}")
    if not isinstance(doc, dict):
        raise CheckpointError("checkpoint is not a JSON object")
    for key in ("presentation_id", "company_id", "revision", "answers",
                "completed_units"):
        if key not in doc:
            raise CheckpointError(f"checkpoint missing key {key!r}")
    if presentation_id is not None and doc["presentation_id"] != presentation_id:
        raise CheckpointError("presentation_id mismatch: checkpoint belongs to "
                              f"{doc['presentation_id']!r}, resume asked for "
                              f"{presentation_id!r}")
    if company_id is not None and doc["company_id"] != company_id:
        raise CheckpointError("company_id mismatch: checkpoint belongs to "
                              f"{doc['company_id']!r}, resume asked for "
                              f"{company_id!r}")
    if not isinstance(doc["revision"], int) or doc["revision"] < min_revision:
        raise CheckpointError(f"revision rollback: stored {doc['revision']!r} "
                              f"< required {min_revision!r}")
    return doc
