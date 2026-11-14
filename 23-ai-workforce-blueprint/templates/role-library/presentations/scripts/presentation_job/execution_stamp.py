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

PD-306 -- THE ROWS ARE KEYED. A row alone is a JSON object anybody with write
access to the run dir can append or edit, so an edited "model" or an inserted
reviewer row would otherwise launder independence. Each row therefore carries
``row_hash``: HMAC-SHA256 over the row's canonical fields, keyed by the RUN key
(``state.run_key_of`` -- one key per run, minted once by PD-906, never logged).

Legacy handling is EXPLICIT, not implicit:
  * a stamp file in which NO row carries ``row_hash`` predates PD-306: every
    row is accepted exactly as today, and the read logs ``stamp.legacy``;
  * a stamp file in which ANY row carries ``row_hash`` is strict: every row
    without a hash valid under this run's key is IGNORED (never trusted, never
    silently upgraded). A run with no key at all therefore trusts no hashed
    row -- fail-closed, and that is the correct answer.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:  # normal package import
    from .state import run_key_of as _state_run_key_of
except ImportError:  # pragma: no cover -- standalone load (scripts dir on sys.path)
    from state import run_key_of as _state_run_key_of  # type: ignore[no-redef]

STAMPS_DIR_REL = os.path.join("working", "execution-stamps")
STATE_FILENAME = "state.json"

# PD-306: the keyed-hash field on every stamp row, and the marker the legacy
# branch logs. A row is trusted only when row_hash verifies under the RUN key.
ROW_HASH_FIELD = "row_hash"
ROW_HASH_ALG = "hmac-sha256"
STAMP_LEGACY_MARK = "stamp.legacy"

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


def _canonical_row(row: Dict[str, Any]) -> str:
    """The exact bytes a row_hash covers: every field EXCEPT the hash itself,
    canonical JSON (sorted keys, no whitespace). Editing any field -- model,
    execution id, artifact sha, phase -- changes these bytes; editing nothing
    changes nothing."""
    payload = {k: v for k, v in row.items() if k != ROW_HASH_FIELD}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def keyed_row_hash(row: Dict[str, Any], run_key: str) -> str:
    """PD-306: HMAC-SHA256 over the row's canonical fields, keyed by the RUN
    key. A row without this run's key cannot produce it, so a row supplied by
    anyone outside the engine is unverifiable by construction."""
    return hmac.new(run_key.encode("utf-8"),
                    _canonical_row(row).encode("utf-8"),
                    hashlib.sha256).hexdigest()


def _row_is_valid(row: Dict[str, Any], run_key: Optional[str]) -> bool:
    """True only when the row carries a row_hash that verifies under this run's
    key. No key -> nothing is valid (fail-closed)."""
    if not run_key:
        return False
    stored = row.get(ROW_HASH_FIELD)
    if not isinstance(stored, str) or not stored:
        return False
    return hmac.compare_digest(stored, keyed_row_hash(row, run_key))


def resolve_run_key(run_dir: Path, run_key: Optional[str] = None) -> Optional[str]:
    """This run's key: the explicit argument when given, else read back from
    state.json (never minted here -- minting is PD-906's Engine.run job). The
    key is returned only; it is never logged or printed."""
    if isinstance(run_key, str) and run_key:
        return run_key
    try:
        obj = json.loads((Path(run_dir) / STATE_FILENAME).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return _state_run_key_of(obj) if isinstance(obj, dict) else None


def _log_legacy(phase_id: Optional[str], n_rows: int) -> None:
    """The ``stamp.legacy`` line: a stamp file written before PD-306, so none
    of its rows carries a hash. Never mentions the key."""
    try:
        print(f"{STAMP_LEGACY_MARK}: phase={phase_id} rows={n_rows} -- stamp file "
              f"predates PD-306 (no row is hashed); rows accepted as today",
              file=sys.stderr, flush=True)
    except Exception:  # noqa: BLE001 -- logging must never break a read
        pass


def trusted_rows(rows: List[Any], run_key: Optional[str], *,
                 run_dir: Optional[Path] = None,
                 phase_id: Optional[str] = None,
                 log_legacy: bool = True) -> List[Dict[str, Any]]:
    """PD-306's ONE read rule, applied to every stamp surface.

    No row carries a hash  -> legacy file: accept every row as today, log
                              ``stamp.legacy`` (only when there is something to
                              accept, so an empty store stays silent).
    Any row carries a hash -> strict: keep only rows whose row_hash verifies
                              under this run's key; every hashless or
                              tampered row is dropped in silence.
    """
    live = [r for r in rows if isinstance(r, dict)]
    if not live:
        return []
    if not any(r.get(ROW_HASH_FIELD) for r in live):
        if log_legacy and run_dir is not None:
            _log_legacy(phase_id, len(live))
        return live
    return [r for r in live if _row_is_valid(r, run_key)]


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
                 model: Optional[str], provider: Optional[str],
                 run_key: Optional[str] = None) -> Dict[str, Any]:
    """THE AUTHOR STAMP (PRES-042 step 1): the trusted dispatcher records WHO
    (execution id), WHAT (model/provider) produced an artifact revision and
    WHICH BYTES (sha256) -- written by the dispatcher process, outside any
    model-authored prose, AFTER the artifact lands. Returns the row appended.

    Immutability is enforced at the storage level: rows are append-only and a
    row's sha256 is verified against the artifact's CURRENT bytes at read
    time, so editing the artifact (a repair) necessarily orphans the old row
    and a NEW stamp must be minted for the new revision.

    PD-306: the row is keyed. ``run_key`` is this run's key (defaults to the
    key persisted in ``<run_dir>/state.json`` by PD-906); without a key the row
    is written UNKEYED, which every strict reader then ignores."""
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
    key = resolve_run_key(run_dir, run_key)
    if key:
        row[ROW_HASH_FIELD] = keyed_row_hash(row, key)
    obj = _load_stamps(run_dir, phase_id)
    obj.setdefault("rows", []).append(row)
    _save_stamps(run_dir, phase_id, obj)
    return row


def qc_stamp(run_dir: Path, phase_id: str, reviewed_artifact: Path, *,
             reviewer_execution_id: str, model: Optional[str],
             provider: Optional[str], rubric_version: Optional[str] = None,
             run_key: Optional[str] = None) -> Dict[str, Any]:
    """THE REVIEWER STAMP (PRES-042 steps 2-3): the dispatcher records the QC
    execution's ACTUAL reviewer id/model/provider, the reviewed artifact SHA
    and the rubric version -- recorded outside the report's verdict prose, so
    a report that CLAIMS a different graded_by cannot launder independence.

    PD-306: keyed exactly like an author row (see ``author_stamp``)."""
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
    key = resolve_run_key(run_dir, run_key)
    if key:
        row[ROW_HASH_FIELD] = keyed_row_hash(row, key)
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
                           require_opposite_model: bool = False,
                           run_key: Optional[str] = None) -> str:
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

    PD-306: rows pass ``trusted_rows`` first, so a hashless row in a hashed
    file, or any row edited after it was written, never reaches the checks."""
    if not stamps_enabled():
        return ""
    try:
        current_sha = sha256_file(artifact)
    except OSError as exc:
        return (f"AF-EXEC-STAMP: artifact {artifact.name} is unreadable "
                f"({exc!r}) -- nothing is proven about it.")
    key = resolve_run_key(run_dir, run_key)
    rows = trusted_rows(_load_stamps(run_dir, phase_id).get("rows") or [], key,
                        run_dir=run_dir, phase_id=phase_id)
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


def _all_stamp_rows(run_dir: Path, run_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """Every TRUSTED stamp row in the run's stamp store, across ALL phase files.
    Author stamps live under the PRODUCER phase's file; reviewer stamps under
    the QC phase's file — a consumed-coverage check must see both, so it
    scans the whole store (a handful of small JSON files). Corrupt files read
    as empty (fail-closed downstream: missing coverage blocks).

    PD-306: the legacy/strict decision is made PER FILE (a file is either all
    legacy or all strict), never across the store — one hashed file must not
    retroactively invalidate a neighbouring pre-PD-306 file. An unreadable
    file is skipped: its rows are simply absent, never trusted."""
    store = run_dir / STAMPS_DIR_REL
    rows: List[Dict[str, Any]] = []
    try:
        files = sorted(store.glob("*.stamp.json"))
    except OSError:
        return []
    for p in files:
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(obj, dict) and isinstance(obj.get("rows"), list):
            rows.extend(trusted_rows(obj["rows"], run_key, run_dir=run_dir,
                                     phase_id=obj.get("phase_id") or p.stem))
    return rows


def consumed_coverage_reasons(run_dir: Path, qc_phase_id: str,
                              artifact: Path,
                              run_key: Optional[str] = None) -> List[str]:
    """QC-SONNET-R5 (PRES-042 repair): the consumed-upstream half of the
    aggregate surface. For one consumed input artifact, require (a) an ACTIVE
    author stamp (some producer revision minted for its CURRENT bytes) and
    (b) a reviewer stamp FROM THIS QC PHASE covering the same current sha.
    Returns [] when covered, else blocking AF-EXEC-STAMP reasons. Disabled
    stamps short-circuit to [] (the caller then applies its own pre-PRES-042
    text check)."""
    if not stamps_enabled():
        return []
    try:
        current_sha = sha256_file(artifact)
    except OSError as exc:
        return [f"AF-EXEC-STAMP: consumed input {artifact.name} is unreadable "
                f"({exc!r}) -- nothing is proven about it."]
    try:
        rel = str(artifact.relative_to(run_dir))
    except ValueError:
        return [f"AF-EXEC-STAMP: consumed input {artifact} escapes the run dir "
                f"-- refusing to trust it."]
    rows = _all_stamp_rows(run_dir, resolve_run_key(run_dir, run_key))
    author = None
    for row in reversed(rows):
        if (row.get("kind") == "author" and row.get("artifact") == rel
                and row.get("artifact_sha256") == current_sha):
            author = row
            break
    if author is None:
        return [f"AF-EXEC-STAMP: consumed input {rel} has no ACTIVE author stamp "
                f"for its CURRENT content (sha {current_sha[:12]}) -- the input "
                f"was produced outside the stamped dispatch or repaired without "
                f"a fresh stamp; its QC coverage is unproven (PRES-042)."]
    reviewer = None
    for row in reversed(rows):
        if (row.get("kind") == "reviewer"
                and row.get("phase_id") == qc_phase_id
                and row.get("reviewed_artifact") == rel
                and row.get("reviewed_artifact_sha256") == current_sha):
            reviewer = row
            break
    if reviewer is None:
        return [f"AF-EXEC-STAMP: no reviewer stamp from {qc_phase_id} covers "
                f"consumed input {rel} at its current sha {current_sha[:12]} -- "
                f"the input changed after the review (or was never reviewed by "
                f"this phase); re-run {qc_phase_id} so a fresh independent "
                f"review covers the current bytes (PRES-042 row 2)."]
    if reviewer.get("execution_id") == author.get("execution_id"):
        return [f"AF-EXEC-STAMP: consumed input {rel} was reviewed by the SAME "
                f"execution that authored it ({reviewer.get('execution_id')}) -- "
                f"a same-execution self-review cannot pass (PRES-042)."]
    return []


def stale_units(run_dir: Path, phase_id: str,
                artifacts: List[Path],
                run_key: Optional[str] = None) -> List[str]:
    """Which of the given artifacts' QC is STALE under PRES-042 (fix step 4's
    reuse half): an artifact whose current sha256 has no covering reviewer
    stamp must be re-QC'd. Cheap: reads stamps once, hashes each unit.

    PD-306: only TRUSTED rows count as coverage -- a hashless or tampered
    reviewer row cannot keep a unit from going stale."""
    if not stamps_enabled():
        return []
    key = resolve_run_key(run_dir, run_key)
    rows = trusted_rows(_load_stamps(run_dir, phase_id).get("rows") or [], key,
                        run_dir=run_dir, phase_id=phase_id)
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