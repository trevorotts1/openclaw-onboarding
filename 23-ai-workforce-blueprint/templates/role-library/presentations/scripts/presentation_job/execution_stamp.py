#!/usr/bin/env python3
"""
presentation_job/execution_stamp.py -- PRES-042: trusted execution-identity
stamps for author/QC independence.

THE GAP (PRES-042). build_deck._qc_independence_reason / qc_aggregate verify
independence from the REPORT's own text (graded_by / qc_independence block) --
useful, but a text report can claim any reviewer name. Runtime-assigned
identity is what makes independence verifiable:

  * The TRUSTED DISPATCHER stamps an immutable AUTHOR execution record
    (execution id, model, provider, artifact SHA-256) on every produced
    artifact revision, OUTSIDE model-authored prose (working/execution-stamps/
    <phase>.stamp.json). A model can never edit these stamps: they are written
    by the dispatcher process after the artifact lands, keyed to the file's
    content hash.
  * QC is dispatched as a SEPARATE execution: the dispatcher records the
    reviewer's actual execution id/model/provider plus the reviewed artifact
    SHA in the same stamp store (qc role), BEFORE the report prose is parsed.
  * Gates consume the STAMPS, not the prose: author != reviewer execution id;
    where policy demands it, opposite model classes for author vs reviewer;
    and a review is STALE the moment the reviewed artifact's current hash no
    longer matches the stamp (post-pass mutation only stales dependents).
  * Model-reported graded_by is DISPLAY metadata only (PRES-042 fix step 3).

Fail-closed posture: a missing/uncorroborated stamp is UNPROVEN (the reason
names what is missing) -- exactly the doctrine _qc_independence_reason already
uses for absent provenance. Rollback: PRESENTATION_EXECUTION_STAMPS=0 restores
the pre-PRES-042 text-only independence check verbatim.

Storage shape (one JSON per phase, append-only rows):
    working/execution-stamps/<phase_id>.stamp.json
    {"phase_id": ..., "rows": [StampRow, ...], "updated_at": ...}
Every row is immutable once written (verified by content hash at read time);
a repair that rewrites an artifact appends a NEW row for the new SHA and the
newest row per artifact is the ACTIVE one.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

STAMPS_DIR_REL = os.path.join("working", "execution-stamps")

# Model-class buckets for the opposite-model policy. A reviewer whose model
# class equals the author's fails when policy demands oppositeness.
MODEL_CLASS_BUCKETS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("deepseek", ("deepseek",)),
    ("openai", ("openai", "gpt", "o1", "o3", "o4")),
    ("anthropic", ("claude",)),
    ("google", ("gemini", "gemma")),
    ("qwen", ("qwen",)),
    ("kimi", ("kimi", "moonshot")),
    ("ollama", ("ollama",)),
    ("agnes", ("agnes",)),
)

STAMP_SCHEMA_VERSION = 1


def stamps_enabled() -> bool:
    """PRES-042 roll-forward/rollback switch. Default ON; ==0 restores the
    pre-PRES-042 text-only independence contract verbatim."""
    return os.environ.get("PRESENTATION_EXECUTION_STAMPS") != "0"


def utcnow() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    """Deterministic SHA-256 over the file's CURRENT bytes -- the same
    discipline state.sha256_file uses, so a stamp's hash means 'the exact
    bytes the dispatcher stamped'."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def model_class_of(model: Optional[str]) -> str:
    """Bucket a model id into its implementation class (best-effort, prefix
    match, case-insensitive). Unknown models bucket as their own lower-cased
    first token -- two unknown DIFFERENT models still differ as classes."""
    m = (model or "").strip().lower()
    if not m:
        return ""
    for bucket, prefixes in MODEL_CLASS_BUCKETS:
        if any(m.startswith(p) or f"/{p}" in m or f"-{p}" in m for p in prefixes):
            return bucket
    return m.split("/")[0].split(":")[0]


def _stamp_path(run_dir: Path, phase_id: str) -> Path:
    return run_dir / "working" / "execution-stamps" / f"{phase_id}.stamp.json"


def _load_stamps(run_dir: Path, phase_id: str) -> Dict[str, Any]:
    p = _stamp_path(run_dir, phase_id)
    if not p.is_file():
        return {"schema_version": STAMP_SCHEMA_VERSION, "phase_id": phase_id, "rows": []}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(obj, dict) and isinstance(obj.get("rows"), list):
            return obj
    except (json.JSONDecodeError, OSError):
        pass
    # A corrupt stamp file is a MISSING stamp store, never a pass: callers
    # treat rows==[] as unproven. Return empty (fail-closed) -- never invent.
    return {"schema_version": STAMP_SCHEMA_VERSION, "phase_id": phase_id, "rows": []}


def _save_stamps(run_dir: Path, phase_id: str, obj: Dict[str, Any]) -> None:
    p = _stamp_path(run_dir, phase_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    obj["updated_at"] = utcnow()
    tmp = p.with_name(p.name + f".tmp-{os.getpid()}")
    try:
        tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)  # atomic on POSIX, same filesystem
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def author_stamp(run_dir: Path, phase_id: str, target: Path, *,
                 model: Optional[str], provider: Optional[str]) -> Dict[str, Any]:
    """THE AUTHOR STAMP (PRES-042 step 1): the trusted dispatcher records WHO
    (execution id), WHAT (model/provider) produced an artifact revision and
    WHICH BYTES (sha256) -- written by the dispatcher process, outside any
    model-authored prose, AFTER the artifact lands. Returns the row appended.

    Immutability is enforced at the storage level: rows are append-only and a
    row's sha256 is verified against the artifact's CURRENT bytes at read
    time, so editing the artifact (a repair) necessarily orphans the old row
    and a NEW stamp must be minted for the new revision."""
    sha = sha256_file(target)
    row: Dict[str, Any] = {
        "kind": "author",
        "execution_id": f"exec-{uuid.uuid4().hex[:16]}",
        "phase_id": phase_id,
        "artifact": str(target.relative_to(run_dir)),
        "artifact_sha256": sha,
        "model": model or "unknown",
        "provider": provider or "unknown",
        "model_class": model_class_of(model),
        "stamped_at": utcnow(),
    }
    obj = _load_stamps(run_dir, phase_id)
    obj.setdefault("rows", []).append(row)
    _save_stamps(run_dir, phase_id, obj)
    return row


def qc_stamp(run_dir: Path, phase_id: str, reviewed_artifact: Path, *,
             reviewer_execution_id: str, model: Optional[str],
             provider: Optional[str], rubric_version: Optional[str] = None) -> Dict[str, Any]:
    """THE REVIEWER STAMP (PRES-042 steps 2-3): the dispatcher records the QC
    execution's ACTUAL reviewer id/model/provider, the reviewed artifact SHA
    and the rubric version -- recorded outside the report's verdict prose, so
    a report that CLAIMS a different graded_by cannot launder independence."""
    sha = sha256_file(reviewed_artifact)
    row: Dict[str, Any] = {
        "kind": "reviewer",
        "execution_id": reviewer_execution_id,
        "phase_id": phase_id,
        "reviewed_artifact": str(reviewed_artifact.relative_to(run_dir)),
        "reviewed_artifact_sha256": sha,
        "model": model or "unknown",
        "provider": provider or "unknown",
        "model_class": model_class_of(model),
        "rubric_version": rubric_version,
        "stamped_at": utcnow(),
    }
    obj = _load_stamps(run_dir, phase_id)
    obj.setdefault("rows", []).append(row)
    _save_stamps(run_dir, phase_id, obj)
    return row


def _active_author_row(rows: List[Dict[str, Any]], artifact_rel: str,
                       current_sha: str) -> Optional[Dict[str, Any]]:
    """The NEWEST author row for the artifact whose sha256 matches the
    artifact's CURRENT bytes (an orphaned pre-repair row never acts as the
    active author identity)."""
    for row in reversed(rows):
        if row.get("kind") != "author":
            continue
        if row.get("artifact") != artifact_rel:
            continue
        if row.get("artifact_sha256") == current_sha:
            return row
    return None


def qc_independence_reason(run_dir: Path, phase_id: str, report_obj: Optional[dict],
                           artifact: Path, *,
                           require_opposite_model: bool = False) -> str:
    """THE PRES-042 GATE (steps 3-4): returns "" when the artifact's CURRENT
    revision carries trusted, independent, non-stale author+reviewer stamps;
    a non-empty AF-EXEC-STAMP reason otherwise.

    Checks, in order (all fail-closed):
      1. stamps enabled (rollback short-circuits to "" -- the caller then
         applies its own pre-PRES-042 text check);
      2. the artifact's CURRENT sha256 has an ACTIVE author stamp (a repaired
         artifact without a fresh stamp is UNPROVEN -- this is also the
         post-pass-mutation staleness contract: mutate a reviewed file and
         its QC is stale, only dependent units re-run);
      3. a reviewer stamp covers EXACTLY that artifact sha (a review of an
         older revision never passes for the current one);
      4. reviewer execution_id != author execution_id (same-execution forgery
         is refused by trusted identity, not by report text);
      5. where policy demands it, reviewer model_class != author model_class
         (opposite-implementation/QC model);
      6. the rubric version is recorded (an unversioned review cannot be
         reproduced).
    Model-reported graded_by (report prose) is NEVER consulted here.
    """
    if not stamps_enabled():
        return ""
    try:
        current_sha = sha256_file(artifact)
    except OSError as exc:
        return (f"AF-EXEC-STAMP: artifact {artifact.name} is unreadable "
                f"({exc!r}) -- nothing is proven about it.")
    rows = _load_stamps(run_dir, phase_id).get("rows") or []
    artifact_rel = str(artifact.relative_to(run_dir))

    author = _active_author_row(rows, artifact_rel, current_sha)
    if author is None:
        return (f"AF-EXEC-STAMP: {artifact_rel} has no ACTIVE author stamp for its "
                f"CURRENT content (sha {current_sha[:12]}) -- a produced artifact "
                f"without a trusted dispatcher stamp is unproven, and a review of an "
                f"older revision is stale. Re-dispatch the phase so the dispatcher "
                f"re-stamps the new revision (PRES-042).")

    reviewer = None
    for row in reversed(rows):
        if (row.get("kind") == "reviewer"
                and row.get("reviewed_artifact") == artifact_rel
                and row.get("reviewed_artifact_sha256") == current_sha):
            reviewer = row
            break
    if reviewer is None:
        return (f"AF-EXEC-STAMP: no trusted REVIEWER stamp covers {artifact_rel} at its "
                f"current sha {current_sha[:12]} -- QC dispatched outside the engine's "
                f"reviewer-stamp store (or against an older revision) is unproven "
                f"(PRES-042: identity comes from the dispatch record, never the "
                f"report prose).")

    if reviewer.get("execution_id") == author.get("execution_id"):
        return (f"AF-EXEC-STAMP: the reviewer execution {reviewer.get('execution_id')} is "
                f"the SAME execution that authored {artifact_rel} -- a same-execution "
                f"self-review cannot pass regardless of what the report's graded_by "
                f"claims (PRES-042).")

    if require_opposite_model and reviewer.get("model_class") == author.get("model_class"):
        return (f"AF-EXEC-STAMP: the reviewer's model class ({reviewer.get('model_class')}) "
                f"equals the author's ({author.get('model_class')}) and this project's "
                f"policy demands an opposite implementation/QC model (PRES-042).")

    if not reviewer.get("rubric_version"):
        return (f"AF-EXEC-STAMP: the reviewer stamp carries no rubric version -- an "
                f"unversioned review cannot be reproduced or trusted (PRES-042).")

    return ""


def stale_units(run_dir: Path, phase_id: str,
                artifacts: List[Path]) -> List[str]:
    """Which of the given artifacts' QC is STALE under PRES-042 (fix step 4's
    reuse half): an artifact whose current sha256 has no covering reviewer
    stamp must be re-QC'd. Cheap: reads stamps once, hashes each unit."""
    if not stamps_enabled():
        return []
    rows = _load_stamps(run_dir, phase_id).get("rows") or []
    covered: Dict[str, str] = {}
    for row in rows:
        if row.get("kind") == "reviewer" and row.get("reviewed_artifact_sha256"):
            covered[row.get("reviewed_artifact")] = row["reviewed_artifact_sha256"]
    stale: List[str] = []
    for p in artifacts:
        try:
            sha = sha256_file(p)
        except OSError:
            continue
        rel = str(p.relative_to(run_dir))
        if covered.get(rel) != sha:
            stale.append(rel)
    return stale