"""presentation_job/retrieval_store.py -- PRES-029: immutable retrieval snapshots.

WHY THIS EXISTS: BoundedFetcher._record OVERWRITES the shared retrieval
ledger on every validation fetch, and validate_citations reads the baseline
hashes only AFTER the fetch rewrote them. Changed-source evidence passes as
though unchanged, original queries/hashes are lost, and restart clears rows.

CONTRACT (SPEC PRES-029):
  1. Immutable research retrieval SNAPSHOTS, separate from validation
     REPORTS. Each snapshot: retrieval_id, query, normalized source ID
     (canonical URL), body/excerpt hash, relevant excerpts, timestamp, scope.
  2. The baseline is read BEFORE validation and never overwritten by it.
     Cited claims validate against the exact saved snapshot synthesis
     consumed. A freshness re-fetch is a NEW snapshot version with a visible
     changed-source decision (changed | unchanged | new), never a silent
     replace.
  3. Rotating ads/navigation: comparison uses relevant NORMALIZED excerpts /
     claims, not raw-HTML equality. Timestamp/ad-only drift keeps the claim
     valid with normalization evidence; changed facts force downstream
     revalidation.
  4. Atomic durable writes (checkpoint.atomic_write_text -- write-temp-then-
     rename + fsync); the phase FAILS when required evidence cannot be
     saved. Restart recovers existing snapshots/ledger instead of clearing.
  5. Validation caching by source-snapshot hash + claim hash + policy
     version (support_gate.POLICY_VERSION) avoids repeated network and
     semantic calls. Cache lives in the run dir, keyed on content hashes,
     never on mutable paths alone.

STORAGE SHAPE (all under working/research/):
  retrieval_snapshots.jsonl -- append-only, one JSON object per line:
      {retrieval_id, query, canonical_url, url, status, content_sha256,
       excerpt_sha256, extracted_preview, retrieved_at, scope,
       fetch_ordinal, supersedes}
  retrieval_ledger.jsonl  -- the legacy FIX 19 ledger file is PRESERVED as
      the write-once baseline view: this module only ever APPENDS new
      snapshot rows to it (refreshing an existing canonical's in-memory
      anchor view in place, as before) and NEVER deletes rows. Snapshot
      identity (retrieval_id) rides each row so validation can address the
      exact snapshot synthesis consumed.
  validation_cache.json   -- {cache_key: verdict-row}; cache_key =
      sha256(snapshot_hash + claim_hash + policy_version).

FAIL-CLOSED: save_snapshot raises SnapshotPersistenceError when the write
cannot land (read-only dir, disk full). Callers must park/fail the phase --
never report success without persisted evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SNAPSHOTS_NAME = "retrieval_snapshots.jsonl"
VALIDATION_CACHE_NAME = "validation_cache.json"

POLICY_VERSION = "retrieval-snapshots-v1"

# Navigation / boilerplate / volatile markers stripped before the
# excerpt comparison. A page whose ONLY diffs are in these markers (plus
# timestamps, see _normalize_excerpt) is ad/timestamp drift -- the claim
# stays valid WITH normalization evidence. Anything else is a changed fact.
_VOLATILE_PATTERNS = (
    r"skip to content", r"sign in", r"subscribe", r"cookie",
    r"all rights reserved", r"privacy policy", r"terms of service",
    r"log in", r"advertisement", r"sponsored", r"newsletter signup",
)
_VOLATILE_RE = re.compile("|".join(_VOLATILE_PATTERNS), re.IGNORECASE)
_TIMESTAMP_RE = re.compile(
    r"\b(?:\d{1,2}:\d{2}(?::\d{2})?\s*(?:am|pm)?|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}|"
    r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?|"
    r"\d+\s+(?:seconds?|minutes?|hours?|days?)\s+ago|"
    r"last updated[^\n]{0,60})\b",
    re.IGNORECASE)


class SnapshotPersistenceError(RuntimeError):
    """Required retrieval evidence could not be saved. Fail the phase."""


def snapshots_path(run_dir: Path) -> Path:
    return run_dir / "working" / "research" / SNAPSHOTS_NAME


def validation_cache_path(run_dir: Path) -> Path:
    return run_dir / "working" / "research" / VALIDATION_CACHE_NAME


def _utcnow() -> str:
    from presentation_job.state import utcnow
    return utcnow()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def normalize_excerpt(text: str) -> str:
    """Volatile-insensitive normalization for snapshot comparison.

    Strips volatile markers + timestamps, collapses whitespace, lowercases.
    Two snapshots whose normalized excerpts match differ only by rotating
    ads/navigation/timestamps -- NOT by changed facts.
    """
    t = _VOLATILE_RE.sub(" ", text or "")
    t = _TIMESTAMP_RE.sub(" <ts> ", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def excerpt_hash(normalized: str) -> str:
    return sha256_text(normalized)


def _atomic_write_json(path: Path, obj: Any) -> None:
    from presentation_job.checkpoint import atomic_write_text
    atomic_write_text(path, json.dumps(obj, indent=2, ensure_ascii=False))


def _atomic_append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    """Append one JSON line atomically: write temp, fsync, then append-read
    under an exclusive create, so a concurrent validator never reads a torn
    line. The append itself is a single os.write of the full line (<= PIPE_BUF
    discipline for small rows; large rows still land as one write call)."""
    from presentation_job.checkpoint import atomic_write_text
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False) + "\n"
    data = line.encode("utf-8")
    # Best-effort atomicity: single write() syscall to O_APPEND fd.
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        mv = memoryview(data)
        while mv:
            n = os.write(fd, mv)
            mv = mv[n:]
        os.fsync(fd)
    finally:
        os.close(fd)
    void = atomic_write_text  # noqa: F841 -- import pinned for fail-closed parity
    _ = void


def read_snapshots(run_dir: Path) -> List[Dict[str, Any]]:
    """All persisted snapshots, oldest first. Missing file -> []. Corrupt
    lines are skipped individually (one torn line never hides the rest);
    callers needing strictness use verify_snapshot_chain."""
    path = snapshots_path(run_dir)
    if not path.is_file():
        return []
    out: List[Dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("retrieval_id"):
            out.append(obj)
    return out


def snapshots_by_canonical(
        run_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for snap in read_snapshots(run_dir):
        grouped.setdefault(str(snap.get("canonical_url") or ""), []).append(snap)
    return grouped


def latest_snapshot(run_dir: Path,
                    canonical_url: str) -> Optional[Dict[str, Any]]:
    snaps = snapshots_by_canonical(run_dir).get(canonical_url) or []
    return snaps[-1] if snaps else None


def baseline_snapshot(run_dir: Path,
                      canonical_url: str) -> Optional[Dict[str, Any]]:
    """The FIRST snapshot for a canonical URL -- the exact evidence the
    research phase recorded, which synthesis consumed. Validation compares
    against THIS, never against a row the validator itself just wrote."""
    snaps = snapshots_by_canonical(run_dir).get(canonical_url) or []
    return snaps[0] if snaps else None


def save_snapshot(run_dir: Path, *, query: Optional[str],
                  url: str, canonical_url: str, status: int,
                  body_or_excerpt: str, is_body: bool,
                  scope: str = "research",
                  fetch_ordinal: Optional[int] = None,
                  extracted_preview_chars: int = 200,
                  raw_body_for_hash: Optional[str] = None,
                  _content_sha_passthrough: Optional[str] = None
                  ) -> Dict[str, Any]:
    """Persist one immutable snapshot. Raises SnapshotPersistenceError when
    the write cannot land -- the caller must fail the phase, never claim
    success without persisted evidence.

    content_sha256 is the RAW-BODY hash (byte-identity of the fetched
    evidence, same level as research_web fetch rows). Pass the raw body via
    raw_body_for_hash whenever the caller only kept the extraction, or the
    already-computed row hash via _content_sha_passthrough (research_web
    _record path -- the body left scope post-extraction, so the row's own
    hash is passed through verbatim instead of re-hashing the excerpt, which
    would alias distinct bodies). Otherwise content falls back to hashing
    the excerpt (recovery path -- same level as the baseline it will be
    compared against, since both go through this function).

    _snapshot_content_passthrough note (for research_web._record): the fetch
    row's content_sha256 is authoritative; re-hashing the excerpt here would
    produce a DIFFERENT hash than the ledger row for the same bytes and
    break the validator's same-level changed-source comparison.
    """
    from presentation_job import research_web as _rw
    if is_body:
        excerpt_text = _rw.extract_text(body_or_excerpt)
    else:
        excerpt_text = body_or_excerpt
    if _content_sha_passthrough:
        content_sha = _content_sha_passthrough
    elif raw_body_for_hash is not None:
        content_sha = sha256_text(raw_body_for_hash)
    else:
        content_sha = sha256_text(body_or_excerpt)
    normalized = normalize_excerpt(excerpt_text)
    prev = latest_snapshot(run_dir, canonical_url)
    retrieval_id = "ret_%s" % sha256_text(
        canonical_url + "|" + content_sha + "|" + _utcnow())[:16]
    snap = {
        "retrieval_id": retrieval_id,
        "policy_version": POLICY_VERSION,
        "query": query,
        "url": url,
        "canonical_url": canonical_url,
        "status": int(status),
        "content_sha256": content_sha,
        "excerpt_sha256": excerpt_hash(normalized),
        "extracted_preview": excerpt_text[:extracted_preview_chars],
        "retrieved_at": _utcnow(),
        "scope": scope,
        "fetch_ordinal": fetch_ordinal,
        "supersedes": prev["retrieval_id"] if prev else None,
    }
    try:
        _atomic_append_jsonl(snapshots_path(run_dir), snap)
    except OSError as exc:
        raise SnapshotPersistenceError(
            f"AF-RESEARCH-PERSIST: could not persist retrieval snapshot for "
            f"{canonical_url} ({type(exc).__name__}: {exc}). Required "
            f"research evidence was NOT saved -- the phase must fail, never "
            f"report success without durable grounded evidence.") from exc
    # Verify the row actually landed (read-back, not just no-exception).
    try:
        landed = any(s.get("retrieval_id") == retrieval_id
                     for s in read_snapshots(run_dir))
    except OSError as exc:
        raise SnapshotPersistenceError(
            f"AF-RESEARCH-PERSIST: snapshot write for {canonical_url} could "
            f"not be verified by read-back ({exc}). Failing closed.") from exc
    if not landed:
        raise SnapshotPersistenceError(
            f"AF-RESEARCH-PERSIST: snapshot {retrieval_id} for "
            f"{canonical_url} did not survive read-back verification. "
            f"Failing closed -- evidence is not durable.")
    return snap


def recover_snapshots(run_dir: Path) -> Dict[str, Any]:
    """Restart recovery: reconcile the legacy FIX 19 ledger into the snapshot
    store WITHOUT clearing anything. Legacy ledger rows with a canonical URL
    and content hash but no snapshot become one snapshot each (preserving
    their recorded query/timestamp). Existing snapshots are untouched.

    Returns {snapshots, recovered_from_legacy, ledger_rows}.
    """
    from presentation_job import research_web as _rw
    snaps = read_snapshots(run_dir)
    have = {(s.get("canonical_url"), s.get("content_sha256")) for s in snaps}
    ledger_path = run_dir / "working" / "research" / _rw.LEDGER_NAME
    rows: List[Dict[str, Any]] = []
    if ledger_path.is_file():
        try:
            obj = json.loads(ledger_path.read_text(encoding="utf-8",
                                                   errors="replace"))
            rows = (obj or {}).get("rows") or []
        except (OSError, ValueError):
            rows = []
    recovered = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        canon = str(row.get("canonical_url") or "").strip()
        sha = str(row.get("content_sha256") or "").strip()
        if not canon or not sha or (canon, sha) in have:
            continue
        preview = str(row.get("extracted_chars")
                      or row.get("extracted") or "")
        snap = {
            "retrieval_id": "ret_legacy_%s" % sha256_text(
                canon + "|" + sha)[:16],
            "policy_version": POLICY_VERSION,
            "query": row.get("query"),
            "url": str(row.get("url") or canon),
            "canonical_url": canon,
            "status": int(row.get("status") or 0),
            "content_sha256": sha,
            "excerpt_sha256": excerpt_hash(normalize_excerpt(preview)),
            "extracted_preview": preview[:200],
            "retrieved_at": str(row.get("retrieved_at") or ""),
            "scope": "research",
            "fetch_ordinal": row.get("fetch_ordinal"),
            "supersedes": None,
        }
        try:
            _atomic_append_jsonl(snapshots_path(run_dir), snap)
            recovered += 1
            have.add((canon, sha))
        except OSError:
            break  # fail-open writes help nothing; report what landed
    return {"snapshots": len(read_snapshots(run_dir)),
            "recovered_from_legacy": recovered,
            "ledger_rows": len(rows)}


def compare_snapshot_to_baseline(
        baseline: Dict[str, Any],
        fresh: Dict[str, Any]) -> Dict[str, Any]:
    """Fresh re-fetch vs the immutable baseline. Returns
    {decision, evidence}: decision is unchanged | ad_drift | changed | new.

      * identical content hash -> unchanged.
      * different hash but identical NORMALIZED excerpt -> ad_drift (claim
        stays valid, with normalization evidence).
      * different normalized excerpt -> changed (dependent claims fail /
        revise; downstream revalidation required).
      * no baseline at all -> new (first observation, not a change).
    """
    if baseline is None:
        return {"decision": "new",
                "evidence": "no baseline snapshot for this canonical URL"}
    if (fresh.get("content_sha256") or "") == \
            (baseline.get("content_sha256") or ""):
        return {"decision": "unchanged",
                "evidence": "content_sha256 identical to baseline "
                            f"{baseline.get('retrieval_id')}"}
    if (fresh.get("excerpt_sha256") or "") == \
            (baseline.get("excerpt_sha256") or ""):
        return {"decision": "ad_drift",
                "evidence": "raw body hash differs but normalized excerpt "
                            "hash matches baseline "
                            f"{baseline.get('retrieval_id')} (rotating "
                            "ads/navigation/timestamps only)"}
    return {"decision": "changed",
            "evidence": f"normalized excerpt differs from baseline "
                        f"{baseline.get('retrieval_id')}: "
                        f"{baseline.get('excerpt_sha256')} -> "
                        f"{fresh.get('excerpt_sha256')}"}


# ---------------------------------------------------------------------------
# Validation cache: (snapshot_hash, claim_hash, policy_version) -> verdict.
# ---------------------------------------------------------------------------

def cache_key(snapshot_hash: str, claim_hash: str,
              policy_version: str) -> str:
    return sha256_text(
        f"{snapshot_hash}|{claim_hash}|{policy_version}")


def read_validation_cache(run_dir: Path) -> Dict[str, Any]:
    path = validation_cache_path(run_dir)
    if not path.is_file():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def lookup_validation(run_dir: Path, snapshot_hash: str,
                      claim_hash: str, policy_version: str) -> Optional[Any]:
    return read_validation_cache(run_dir).get(
        cache_key(snapshot_hash, claim_hash, policy_version))


def store_validation(run_dir: Path, snapshot_hash: str, claim_hash: str,
                     policy_version: str, verdict: Any) -> None:
    """Cache a verdict. Best-effort (a lost cache row costs a re-review,
    never correctness) -- but a denied write on the SNAPSHOT path is fatal
    and handled by save_snapshot, not here."""
    path = validation_cache_path(run_dir)
    try:
        cache = read_validation_cache(run_dir)
        cache[cache_key(snapshot_hash, claim_hash, policy_version)] = verdict
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(path, cache)
    except OSError:
        pass
