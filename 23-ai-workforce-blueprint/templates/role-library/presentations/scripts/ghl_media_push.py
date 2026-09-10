#!/usr/bin/env python3
"""ghl_media_push.py — host a deck's approved images + final deliverables in GHL,
AND enforce the HARD closeout gate that no deck ships without that upload.

The Media Librarian's mechanical upload half. Per the BINDING GHL-touch rule in
CLIENT-WEBINAR-DECK-SOP (POST /medias/upload-file, Version 2021-07-28, client
LOCATION PIT), it:

  1. RESOLVES the per-deck media folder — FIX 36: FOLDER-CREATE IS DISABLED. The
     folder-create endpoint returns 404 for this department (the SOP is binding);
     the old 201 "primary path" branch is REMOVED. The folder is never created by
     the agent: the upload targets (a) the HUMAN-APPROVED folder id from
     intake.json.ghl_media_folder_id (a pre-existing folder made by a person in
     the GHL UI), else (b) the shareable media ROOT with a "<deck-slug> — " name
     PREFIX so the images stay grouped by name. Either way `ghl_folder_id` is
     recorded ("root" is a valid passing value).
  2. Uploads each approved PNG (+ the final PPTX/PDF when given) via
     ghl_media.upload_media (POST /medias/upload-file, multipart, parentId), recording
     the public storage.googleapis.com URL + fileId per file to media_library.json.

CANONICAL LEDGER PATH (the file the gates actually read):
    working/checkpoints/media_library.json
This is the SAME path SOP 9.1 (Step-0 landing zone) seeds, that delivery_gate.py and
the Delivery Concierge read, and that this module's closeout gate reads. The ledger is
MERGED (never clobbered): Step-0's folder name / version survive; the upload records
(ghl_folder_id, per-slide ghl_media_id, pptx_ghl_media_id) are added incrementally.

CLOSEOUT GATE — NO DELIVERY WITHOUT THE GHL UPLOAD (folds under AF-DELIVERY-COMPLETE):
    gate_ghl_media_complete(run_dir) -> (ok, reasons)
    `python3 ghl_media_push.py --gate --run-dir <run_dir>`   (exit 0 pass / 1 fail)
For every GHL-enabled deck it HARD-FAILS unless media_library.json records ALL THREE:
  (1) ghl_folder_id   — a real folder id OR "root" (the per-deck folder was resolved),
  (2) per-slide PNG uploads — each with a real ghl_media_id (status "complete"),
  (3) pptx_ghl_media_id — the final assembled PPTX is in the GHL media library.
The gate may be skipped by exactly ONE thing: a LOGGED owner/founder approval token in
working/checkpoints/process_manifest.json under `owner_skip_approval` (owner_approved:
true + approved_by + reason + a matching gate name). An agent setting `has_ghl:false`
on its own does NOT skip the gate — the skip must be an explicit owner decision.

FORBIDDEN: driving the GoHighLevel UI in a browser (agent-browser / Playwright /
Puppeteer / any UI automation). The media library is touched ONLY via this REST path.

Idempotent per file (the basename is the ledger key) so a retry never re-uploads.
Fail-loud: a missing LOCATION PIT raises; a non-PNG is refused; an upload returning no
fileId/url raises. No fabricated CDN URLs, ever.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import fcntl
import hashlib
import json
import os
import re
import sys
import threading
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ghl_media  # noqa: E402  (the SHARED, verified-working module)
import delivery_gate  # noqa: E402  (the OUT-OF-BAND delivery boundary gate)
# FIX 111 (MASTER Part 8 / R14 §5.10): the STANDARD over-cap rule lives in
# ghl_media_upload.py — the cap constant, the receipt builder/validator, and THE
# accept-either-id reader every gate calls. The push transport builds its PDF-twin
# receipt through build_receipt/record_upload_receipt (one implementation) and the
# closeout gate accepts either id through hosted_deck_media_id, so "the pptx was
# over the 25 MB cap, the PDF twin is the hosted deck" is machine-readable at the
# gate instead of an improvised per-incident shape.
import ghl_media_upload  # noqa: E402  (the FIX 111 rule + receipt + gate-reader layer)

# The closeout code this GHL-upload gate folds under (diagnosis 4.6 / Fix-Goal 5).
GHL_UPLOAD_GATE = "AF-DELIVERY-COMPLETE"


# ---------------------------------------------------------------------------
# OUT-OF-BAND DELIVERY BOUNDARY GATE wired INTO this transport (v16.1.1 — the #1 fix).
# Until now the boundary gate (delivery_gate.gate_delivered_artifact) ran ONLY inside
# run_signature_deck.py P9-DELIVER. A deck hand-built OUTSIDE the pipeline (python-pptx /
# Pillow / Google-Slides, native overlaid text, no kie.ai renders, no governed run dir)
# could be uploaded straight to the client's GHL media library through THIS module,
# skipping the pipeline entirely — exactly the failure that shipped a hand-built deck.
# push_deck_media() now runs the boundary gate over every deck artifact (.pptx/.pdf) it
# is about to host, in PRE-TRANSPORT mode (the deck's own GHL upload is what is about to
# happen, so the SOP-9.4 upload-record sub-check is deferred — but artifact provenance,
# kie provenance, no-run-dir, the AF-DH1 six-file package, and the teleprompter are all
# enforced). A rejection ABORTS the upload (fail-closed): nothing is hosted. The ONLY
# bypass is a logged owner_skip_approval token, honored inside gate_delivered_artifact.
# ---------------------------------------------------------------------------
# DeliveryGateRejected is the CANONICAL exception, now defined ONCE in delivery_gate.py
# and SHARED so `except DeliveryGateRejected` catches a rejection raised at EITHER the
# transport (here, push_deck_media) OR the lowest GHL upload chokepoint (the gated
# ghl_media.upload_media wrapper added in v16.1.2). Re-exported under this module's name
# for backward compatibility (any caller/test importing ghl_media_push.DeliveryGateRejected
# keeps working, and it is the same class identity the chokepoint raises).
DeliveryGateRejected = delivery_gate.DeliveryGateRejected


def _deck_artifacts(files):
    """The deck artifacts (.pptx/.pdf) among the files about to be pushed — these are the
    client-facing decks the boundary gate must inspect. Slide PNGs and other media are
    not decks and are not gated here."""
    return [str(f) for f in files if _classify(str(f)) in ("pptx", "pdf")]


def gate_deck_artifacts(run_dir, files):
    """Run the OUT-OF-BAND DELIVERY BOUNDARY GATE over every deck artifact (.pptx/.pdf)
    in `files`, in PRE-TRANSPORT mode, BEFORE any upload. Returns (ok, reasons). A
    hand-built / overlay / no-kie / no-governed-run-dir deck is REJECTED so it cannot
    reach the client's GHL media library regardless of how it was produced. The ONLY
    bypass is a logged owner_skip_approval token (honored inside gate_delivered_artifact).
    Fail-closed: if the gate itself raises, that is treated as a rejection."""
    run_dir = Path(run_dir)
    reasons, ok_all = [], True
    for art in _deck_artifacts(files):
        try:
            ok, rs = delivery_gate.gate_delivered_artifact(
                art, run_dir, verify_destinations=False)
        except Exception as exc:  # noqa: BLE001 — fail-closed
            ok, rs = False, [f"{GHL_UPLOAD_GATE}: delivery_gate boundary check raised on "
                             f"{Path(art).name}: {exc!r} (fail-closed — refusing to upload "
                             "an un-gated deck)."]
        if not ok:
            ok_all = False
            hard = [r for r in rs if not str(r).startswith("NOTE")]
            reasons.append(f"{Path(art).name}: " + "; ".join(hard))
    return ok_all, reasons
# Owner-skip token gate names this carve-out will honor (any one matches).
_GATE_ALIASES = frozenset({
    "AF-DELIVERY-COMPLETE", "AF-BUNDLE-COMPLETE",
    "ghl_media_upload", "ghl_media", "media_library", "ghl_upload",
})
# Canonical ledger location — the file every reader/gate shares.
_LEDGER_REL = ("working", "checkpoints", "media_library.json")
_SLIDE_RE = re.compile(r"slide[\s\-_]?0*(\d{1,3})", re.IGNORECASE)

# ---------------------------------------------------------------------------
# PRES-026 — resumable, content-addressed, concurrently-safe media-upload ledger.
# ---------------------------------------------------------------------------
# Two confirmed defects are fixed here (TODO PRES-026):
#   (a) a retry after a partial success re-uploads already-hosted files and saves
#       no receipt for the success (ledger written once at the end, keyed by path);
#   (b) a QC repair that rewrites a PNG in place at the same path is skipped, so
#       the stale hosted image keeps serving.
# Shape contract (new keys are ADDITIVE — every legacy reader keeps working):
#   jobs: {job_key: {job_key, company_id, presentation_id, artifact_type, ordinal,
#                    revision, sha256, size_bytes, local_path, status, attempts,
#                    file_id, url, remote_name, folder_id, uploaded_at, error,
#                    outcome_unknown, invalidated_by}}   — per-artifact durable receipt
#   run:  {run_id, company_id, presentation_id, deck_slug} — the binding scope
#   image_links: {job_key-or-local_path: {url, file_id, sha256, revision, active}}
#                — downstream image-link projection, invalidated on hash change
#   delivery_receipts_invalid: bool — set when a revision change invalidates them
_UPLOADS_LEDGER_VERSION = 1
_JOB_STATUS_PENDING = "pending"
_JOB_STATUS_UPLOADING = "uploading"
_JOB_STATUS_COMPLETE = "complete"
_JOB_STATUS_FAILED = "failed"
_JOB_STATUS_UNKNOWN = "unknown_remote_outcome"
_JOB_STATUS_REPAIR_REQUIRED = "repair_required"
_JOB_STATUS_SUPERSEDED = "superseded"
# Provider-specific bounded upload pool. GHL media is one serial-safe REST
# endpoint per location; 4 parallel uploads bound latency without hammering it.
# GHL_VIDEO_MAX_BYTES-tier (.mp4 webinar) uploads are larger and run at 2.
# _CLAIM_SERIAL serializes the plan/read/claim section across threads in one
# process (flock already serializes across processes): without it two same-run
# workers interleave plan (both see empty) and both claim+POST every key.
_CLAIM_SERIAL = threading.Lock()
_UPLOAD_POOL_DEFAULT = 4
_UPLOAD_POOL_VIDEO = 2
_UPLOAD_RETRIES_DEFAULT = 3
# Content types the uploader may serve evidence for (extension -> content type).
_CONTENT_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".pdf": "application/pdf", ".mp3": "audio/mpeg", ".mp4": "video/mp4",
    ".html": "text/html",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _ledger_path(run_dir: Path) -> Path:
    return run_dir.joinpath(*_LEDGER_REL)


def _classify(path_str: str) -> str:
    """slide PNG | pptx | pdf | image | other — drives gate-readable bucketing."""
    name = Path(path_str).name.lower()
    if name.endswith(".pptx"):
        return "pptx"
    if name.endswith(".pdf"):
        return "pdf"
    if name.endswith(".png") and _SLIDE_RE.search(name):
        return "slide"
    if name.endswith((".png", ".jpg", ".jpeg", ".webp")):
        return "image"
    return "other"


def _slide_number(path_str: str):
    m = _SLIDE_RE.search(Path(path_str).name)
    return int(m.group(1)) if m else None


def _sha256_file(path_str: str) -> str | None:
    """SHA-256 hex of a file's bytes; None when unreadable. The content address
    the PRES-026 job key binds — a same-path rewrite yields a new hash, never a
    silent skip of the repaired bytes."""
    try:
        h = hashlib.sha256()
        with open(path_str, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _content_type_for(path_str: str) -> str:
    return _CONTENT_TYPES.get(Path(path_str).suffix.lower(), "application/octet-stream")


def _run_scope(run_dir: Path, intake: dict, slug: str) -> dict:
    """Binding scope for every job key in this run. company_id/presentation_id
    come from the sealed intake when present and fall back to deterministic
    run-dir-derived values so the scope is NEVER empty and NEVER cross-run."""
    company = str(intake.get("company_id") or intake.get("client_company_id")
                  or intake.get("location_id") or "").strip()
    presentation = str(intake.get("presentation_id") or intake.get("deck_id")
                       or slug or "").strip()
    run_id = str(intake.get("run_id") or run_dir.name or "").strip()
    if not company:
        company = f"local-{hashlib.sha256(str(run_dir).encode()).hexdigest()[:16]}"
    if not presentation:
        presentation = slug or run_dir.name
    if not run_id:
        run_id = run_dir.name
    return {"run_id": run_id, "company_id": company,
            "presentation_id": presentation, "deck_slug": slug}


def _upload_job_key(*, company_id: str, presentation_id: str, artifact_type: str,
                    ordinal: int | None, revision: int, sha256: str) -> str:
    """PRES-026 upload job key: company/presentation/type/ordinal/revision/SHA.
    Two workers computing the same key for the same bytes MUST converge on one
    operation; any changed byte yields a distinct key (a new revision)."""
    ord_part = "none" if ordinal is None else str(int(ordinal))
    raw = "|".join([str(company_id), str(presentation_id), str(artifact_type),
                    ord_part, str(int(revision)), str(sha256)])
    return f"{artifact_type}:{ord_part}:r{int(revision)}:{hashlib.sha256(raw.encode()).hexdigest()[:24]}"


def _ledger_lock_path(ledger_path: Path) -> Path:
    return ledger_path.with_suffix(ledger_path.suffix + ".lock")


def _locked_ledger_update(ledger_path: Path, mutate):
    """Read-modify-write the ledger under an exclusive file lock (POSIX flock),
    fsync before release. Returns mutate's return value. Cross-process safe:
    two uploader workers on the same run serialize here, so no receipt update
    is lost. mutate(ledger: dict) -> value; the ledger dict is persisted iff
    mutate returns (value, True)."""
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = _ledger_lock_path(ledger_path)
    lock_path.touch(exist_ok=True)
    with open(lock_path, "w") as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        try:
            ledger = _read_json(ledger_path) if ledger_path.exists() else {}
            if not isinstance(ledger, dict):
                ledger = {}
            value, dirty = mutate(ledger)
            if dirty:
                tmp = ledger_path.with_suffix(ledger_path.suffix + ".tmp")
                tmp.write_text(json.dumps(ledger, indent=2))
                with open(tmp, "rb") as fh:
                    os.fsync(fh.fileno())
                os.replace(tmp, ledger_path)
                with open(ledger_path, "rb") as fh:
                    os.fsync(fh.fileno())
            return value
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)


def _read_ledger_locked(ledger_path: Path) -> dict:
    """Read the ledger under a shared lock (never a torn read mid-write)."""
    if not ledger_path.exists():
        return {}
    lock_path = _ledger_lock_path(ledger_path)
    lock_path.touch(exist_ok=True)
    with open(lock_path, "w") as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_SH)
        try:
            data = _read_json(ledger_path)
            return data if isinstance(data, dict) else {}
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)


def _job_key_for_record(rec: dict) -> str | None:
    if not isinstance(rec, dict):
        return None
    jk = rec.get("job_key")
    return str(jk) if jk else None


def _find_remote_match(entries: list, *, remote_name: str, file_id: str | None = None) -> dict | None:
    """Match a ledger record against a remote list-back: by recorded file id
    first (strongest), else by exact bound remote name."""
    for e in entries:
        if not isinstance(e, dict):
            continue
        eid = str(e.get("fileId") or e.get("_id") or e.get("id") or "")
        ename = str(e.get("name") or "")
        if file_id and eid and eid == file_id:
            return e
        if ename and ename == remote_name:
            return e
    return None


def _deck_pdf(uploaded):
    """The DECK PDF (named *-FINAL.pdf, kind "pdf") among the uploads — the client-facing
    deck as hosted when the assembled PPTX exceeds GHL's 25MB media-upload cap (HTTP 413,
    Defect #9). Deliberately NARROW (matches the -FINAL suffix the delivery gate / ghl_media
    chokepoint use for the deck) so the presenter guide / speech PDFs
    (PRESENTER-GUIDE.pdf / PRESENTERS-SPEECH.pdf) are never mistaken for the deck."""
    for e in uploaded:
        if not isinstance(e, dict) or e.get("kind") != "pdf":
            continue
        nm = str(e.get("ghl_remote_name") or e.get("name") or "").lower()
        if nm.endswith("-final.pdf"):
            return e
    return None

def _deck_pptx_local_path(run_dir, slug: str, extra_files) -> str | None:
    """FIX 111: the LOCAL deck pptx that would have been hosted — the file the over-cap
    receipt must name. Resolved the same narrow way the deck artifacts are classified:
    a *-FINAL.pptx among the extra deliverables (the assembled bundle deck) first, else
    the {slug}-FINAL.pptx under the run dir's delivery bundle. Returns None (never a
    guess) when no deck pptx exists — a PDF-twin receipt without a real local pptx is
    exactly the phantom ghl_media_upload refuses to build."""
    for f in extra_files or []:
        p = Path(str(f))
        if p.name.lower().endswith("-final.pptx") and p.is_file():
            return str(p)
    for cand in sorted((Path(run_dir) / "delivery").glob("*-FINAL.pptx")):
        if cand.is_file():
            return str(cand)
    named = Path(run_dir) / "delivery" / f"{slug}-FINAL.pptx"
    if named.is_file():
        return str(named)
    return None


def _is_timeout_like(exc: BaseException) -> bool:
    """True when the failure leaves the remote outcome UNKNOWN: the request may
    have landed server-side despite the client never seeing the receipt. Such
    outcomes MUST reconcile via list/readback before any recreate."""
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    if isinstance(exc, urllib.error.URLError) and not isinstance(exc, urllib.error.HTTPError):
        return True
    msg = str(exc).lower()
    return any(s in msg for s in ("timed out", "timeout", "connection reset",
                                  "connection aborted", "broken pipe", "unknown_remote_outcome"))


def _plan_upload_jobs(files: list, *, scope: dict, ledger: dict) -> list:
    """Content-address every requested file into an upload job. Returns one plan
    dict per file: {local_path, kind, slide_number, sha256, size_bytes, job_key,
    revision, action} where action is one of:
      reuse      — same hash already complete in this run's ledger (no upload)
      reconcile  — ledger outcome unknown; list/readback first, then decide
      upload     — new hash (or new path): create a new revision and upload
      missing    — file unreadable; caller records a failed job, never uploads
    A changed hash at a previously-uploaded path yields action=upload with
    revision = prior max + 1 (the stale revision is superseded, never reused)."""
    jobs_by_key = ledger.get("jobs") if isinstance(ledger, dict) else None
    jobs_by_key = jobs_by_key if isinstance(jobs_by_key, dict) else {}
    by_path: dict[str, list] = {}
    for jk, job in jobs_by_key.items():
        if isinstance(job, dict) and job.get("local_path"):
            by_path.setdefault(str(job["local_path"]), []).append((jk, job))
    plans = []
    for f in files:
        f = str(f)
        kind = _classify(f)
        sn = _slide_number(f)
        sha = _sha256_file(f)
        try:
            size = Path(f).stat().st_size if sha is not None else None
        except OSError:
            size = None
        if sha is None:
            plans.append({"local_path": f, "kind": kind, "slide_number": sn,
                          "sha256": None, "size_bytes": None, "job_key": None,
                          "revision": 0, "action": "missing"})
            continue
        artifact_type = kind
        prior = sorted(by_path.get(f, []),
                       key=lambda t: int(t[1].get("revision", 0) or 0))
        same = [(jk, j) for jk, j in prior
                if j.get("sha256") == sha
                and str(j.get("company_id") or "") == str(scope["company_id"])
                and str(j.get("presentation_id") or "") == str(scope["presentation_id"])]
        complete_same = [job for _, job in same if job.get("status") == _JOB_STATUS_COMPLETE]
        unknown_same = [(jk, job) for jk, job in same if job.get("status") == _JOB_STATUS_UNKNOWN]
        repair_same = [(jk, job) for jk, job in same
                       if job.get("status") in (_JOB_STATUS_FAILED, _JOB_STATUS_REPAIR_REQUIRED)]
        if complete_same:
            job = complete_same[-1]
            plans.append({"local_path": f, "kind": kind, "slide_number": sn,
                          "sha256": sha, "size_bytes": size,
                          "job_key": job.get("job_key"), "revision": job.get("revision", 1),
                          "action": "reuse"})
            continue
        if unknown_same:
            jk, job = unknown_same[-1]
            plans.append({"local_path": f, "kind": kind, "slide_number": sn,
                          "sha256": sha, "size_bytes": size,
                          "job_key": jk, "revision": job.get("revision", 1),
                          "action": "reconcile"})
            continue
        if repair_same:
            # Same bytes failed before (or remote dropped them): retry the SAME
            # job key + revision (no revision bump — the bytes never changed),
            # so exactly one operation exists per job key across retries.
            jk, job = repair_same[-1]
            plans.append({"local_path": f, "kind": kind, "slide_number": sn,
                          "sha256": sha, "size_bytes": size,
                          "job_key": jk, "revision": job.get("revision", 1),
                          "action": "upload"})
            continue
        revision = (max([int(j.get("revision", 0) or 0) for _, j in prior] or [0]) + 1)
        ordinal = sn if sn is not None else None
        jk = _upload_job_key(company_id=scope["company_id"],
                             presentation_id=scope["presentation_id"],
                             artifact_type=artifact_type, ordinal=ordinal,
                             revision=revision, sha256=sha)
        plans.append({"local_path": f, "kind": kind, "slide_number": sn,
                      "sha256": sha, "size_bytes": size,
                      "job_key": jk, "revision": revision, "action": "upload"})
    return plans


def _upload_one_with_retries(local_path: str, location_id: str, name: str, pit: str, *,
                             parent_id=None, opener=None, run_dir=None,
                             max_attempts: int = _UPLOAD_RETRIES_DEFAULT):
    """Upload one file with bounded individual retries. Transient blips are
    retried inside the transport already; this layer retries fail-loud upload
    errors up to max_attempts. A timeout-like failure raises with an
    unknown_remote_outcome marker so the caller reconciles via list/readback
    instead of blindly recreating. Returns (result_dict, attempts_used).
    require_png=False is passed for non-image deliverables (deck .pptx/.pdf,
    audio, video): the choke wrapper still runs the deck gate on deck
    artifacts, and the canonical call still enforces existence."""
    last: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            if _classify(local_path) in ("slide", "image"):
                res = ghl_media.upload_media(local_path, location_id, name, pit,
                                             parent_id=parent_id, opener=opener,
                                             run_dir=run_dir)
            else:
                res = ghl_media.upload_media(local_path, location_id, name, pit,
                                             parent_id=parent_id, opener=opener,
                                             run_dir=run_dir, require_png=False)
            return res, attempt
        except DeliveryGateRejected:
            raise
        except Exception as exc:  # noqa: BLE001 — bounded individual retry
            last = exc
            if _is_timeout_like(exc):
                if "unknown_remote_outcome" not in str(exc):
                    exc.args = (*exc.args, "unknown_remote_outcome")
                raise
            if attempt >= max_attempts:
                raise
    assert last is not None
    raise last


def _persist_job(ledger_path: Path, job: dict) -> dict:
    """Atomically merge one job record into the durable ledger (locked). Also
    refreshes the legacy gate-readable projections (uploaded/slides/counts)
    from the jobs table so old readers keep working."""
    def _mut(ledger: dict):
        jobs = ledger.get("jobs")
        if not isinstance(jobs, dict):
            jobs = {}
            ledger["jobs"] = jobs
        jobs[str(job["job_key"])] = dict(job)
        _refresh_legacy_projections(ledger)
        return dict(job), True
    return _locked_ledger_update(ledger_path, _mut)


def _refresh_legacy_projections(ledger: dict) -> None:
    """Rebuild uploaded/slides/upload_count-style projections from the jobs
    table: only ACTIVE complete revisions surface (superseded/failed/unknown
    rows never masquerade as the hosted file). Legacy path-keyed readers see
    the same shapes as before."""
    jobs = ledger.get("jobs")
    if not isinstance(jobs, dict):
        return
    active: dict[str, dict] = {}
    for jk, job in jobs.items():
        if not isinstance(job, dict) or job.get("status") != _JOB_STATUS_COMPLETE:
            continue
        if job.get("superseded_by"):
            continue
        lp = str(job.get("local_path") or "")
        prev = active.get(lp)
        if prev is None or int(job.get("revision", 0) or 0) > int(prev.get("revision", 0) or 0):
            active[lp] = job
    uploaded = []
    for lp in sorted(active):
        job = active[lp]
        rec = {"local_path": lp, "kind": job.get("artifact_type"),
               "name": job.get("remote_name"), "ghl_remote_name": job.get("remote_name"),
               "public_url": job.get("url"), "ghl_url": job.get("url"),
               "file_id": job.get("file_id"), "ghl_media_id": job.get("file_id"),
               "http_status": job.get("http_status"), "ghl_upload_status": "complete",
               "ghl_folder_id": job.get("folder_id"), "uploaded_at": job.get("uploaded_at"),
               "job_key": job.get("job_key"), "sha256": job.get("sha256"),
               "revision": job.get("revision"), "content_type": job.get("content_type"),
               "size_bytes": job.get("size_bytes"),
               "remote_verified": job.get("remote_verified", False)}
        if job.get("slide_number") is not None:
            rec["slide_number"] = job["slide_number"]
        uploaded.append(rec)
    # Preserve non-job legacy rows (e.g. Step-0 seeds) that jobs do not cover.
    legacy = [e for e in ledger.get("uploaded", [])
              if isinstance(e, dict) and not e.get("job_key")
              and str(e.get("local_path") or "") not in active]
    uploaded = legacy + uploaded
    ledger["uploaded"] = uploaded
    ledger["upload_count"] = len(uploaded)
    slides = sorted([e for e in uploaded if isinstance(e, dict) and e.get("kind") == "slide"],
                    key=lambda e: e.get("slide_number") or 0)
    ledger["slides"] = slides
    ledger["ghl_slide_upload_count"] = len(slides)
    pptx = next((e for e in uploaded if isinstance(e, dict) and e.get("kind") == "pptx"), None)
    if pptx:
        ledger["pptx_ghl_media_id"] = pptx["ghl_media_id"]
        ledger["pptx_ghl_url"] = pptx["ghl_url"]
        ledger["pptx_ghl_remote_name"] = pptx["ghl_remote_name"]
    links = ledger.get("image_links")
    if not isinstance(links, dict):
        links = {}
        ledger["image_links"] = links
    for lp, job in active.items():
        links[lp] = {"url": job.get("url"), "file_id": job.get("file_id"),
                     "sha256": job.get("sha256"), "revision": job.get("revision"),
                     "job_key": job.get("job_key"), "active": True}
        if job.get("job_key"):
            links[str(job["job_key"])] = links[lp]


def _supersede_prior_revisions(ledger_path: Path, *, local_path: str, sha256: str,
                               superseded_by: str) -> None:
    """Mark older complete revisions at the same path superseded + invalidate
    their downstream image links and delivery receipts (PRES-026 step 3)."""
    def _mut(ledger: dict):
        jobs = ledger.get("jobs")
        changed = False
        if isinstance(jobs, dict):
            for jk, job in jobs.items():
                if (isinstance(job, dict) and str(job.get("local_path") or "") == local_path
                        and job.get("sha256") != sha256
                        and job.get("status") == _JOB_STATUS_COMPLETE
                        and not job.get("superseded_by")):
                    job["status"] = _JOB_STATUS_SUPERSEDED
                    job["superseded_by"] = superseded_by
                    changed = True
        links = ledger.get("image_links")
        if isinstance(links, dict) and local_path in links:
            old = links[local_path]
            if isinstance(old, dict) and old.get("sha256") != sha256:
                old["active"] = False
                changed = True
        if changed:
            ledger["delivery_receipts_invalid"] = True
            _refresh_legacy_projections(ledger)
        return None, changed
    _locked_ledger_update(ledger_path, _mut)


def _reconcile_unknown_job(ledger_path: Path, job: dict, *, location_id: str, pit: str,
                           opener=None, limit: int = 200) -> dict:
    """Reconcile a job whose remote outcome is UNKNOWN via read-only
    list/readback BEFORE any recreate (PRES-026 step 2). When the remote
    already hosts the bytes under the bound name, the job completes WITHOUT a
    second POST (no duplicate). Otherwise it returns to pending for one fresh
    create. The list evidence (content-type/size/hash when the API exposes it)
    is recorded on the job."""
    try:
        listing = ghl_media.list_media(location_id, pit, media_type="file",
                                       limit=limit, opener=opener)
    except Exception as exc:  # noqa: BLE001 — readback itself failed: stay unknown
        job["status"] = _JOB_STATUS_UNKNOWN
        job["error"] = f"reconcile list failed: {exc!r}"
        return _persist_job(ledger_path, job)
    entries = listing.get("data") or []
    match = _find_remote_match(entries, remote_name=str(job.get("remote_name") or ""),
                               file_id=str(job.get("file_id") or "") or None)
    job["reconcile_evidence"] = {
        "listed": len(entries),
        "matched": bool(match),
        "matched_entry": ({k: match.get(k) for k in
                           ("fileId", "_id", "id", "name", "url", "fileUrl",
                            "contentType", "mimeType", "size", "fileSize", "md5", "sha256",
                            "createdAt", "updatedAt") if k in match}
                          if isinstance(match, dict) else None),
        "checked_at": _now_iso(),
    }
    if match:
        job["file_id"] = str(match.get("fileId") or match.get("_id") or match.get("id")
                             or job.get("file_id") or "")
        url = str(match.get("url") or match.get("fileUrl") or job.get("url") or "")
        job["url"] = url
        job["status"] = _JOB_STATUS_COMPLETE
        job["uploaded_at"] = _now_iso()
        job["outcome_unknown"] = False
        job["remote_verified"] = True
    else:
        job["status"] = _JOB_STATUS_PENDING
        job["outcome_unknown"] = False
        job["error"] = "reconcile: no remote object matched; safe to recreate once"
    return _persist_job(ledger_path, job)


def _remote_health_for_jobs(jobs: list, *, location_id: str, pit: str,
                            opener=None, limit: int = 200) -> dict:
    """One shared read-only list/readback for many jobs: returns
    {job_key: matched_entry-or-None, '_listed': N, '_error': str-or-None} plus
    per-entry content-type/size/hash evidence where the API exposes it."""
    try:
        listing = ghl_media.list_media(location_id, pit, media_type="file",
                                       limit=limit, opener=opener)
    except Exception as exc:  # noqa: BLE001
        return {"_listed": 0, "_error": repr(exc)}
    entries = listing.get("data") or []
    out: dict = {"_listed": len(entries), "_error": None}
    for job in jobs:
        match = _find_remote_match(entries, remote_name=str(job.get("remote_name") or ""),
                                   file_id=str(job.get("file_id") or "") or None)
        if isinstance(match, dict):
            out[str(job["job_key"])] = {
                k: match.get(k) for k in
                ("fileId", "_id", "id", "name", "url", "fileUrl",
                 "contentType", "mimeType", "size", "fileSize", "md5", "sha256",
                 "createdAt", "updatedAt") if k in match}
        else:
            out[str(job["job_key"])] = None
    return out


def push_deck_media(run_dir: Path, images: list, *, deck_slug: str | None = None,
                    extra_files: list | None = None, opener=None,
                    max_workers: int | None = None, retries: int = _UPLOAD_RETRIES_DEFAULT,
                    skip_boundary_gate: bool = False) -> dict:
    """Create the per-deck folder and upload the approved images (+ extra files).
    Writes the gate-readable ledger to working/checkpoints/media_library.json
    (MERGED with the Step-0 seed) and returns the same dict.

    PRES-026 resume contract: every successful upload persists its file ID + URL
    to the durable per-run ledger IMMEDIATELY (locked, atomic) before the next
    upload starts, keyed by the content-addressed job key
    (company/presentation/type/ordinal/revision/SHA). A retry reuses complete
    same-hash jobs (no re-upload), reconciles unknown outcomes via list/readback
    before recreating, and treats a changed hash as a new revision that
    supersedes the stale one and invalidates downstream links/receipts.
    Independent files upload through a bounded pool with individual retries; one
    broken artifact never restarts already-verified healthy ones."""
    run_dir = Path(run_dir).resolve()
    intake = _read_json(run_dir / "working" / "copy" / "intake.json")
    slug = (deck_slug or intake.get("deck_slug") or run_dir.name).strip()

    # OUT-OF-BAND DELIVERY BOUNDARY GATE (fail-closed) — runs BEFORE any credential
    # resolution or network call, so a deck not produced by the governed kie.ai pipeline
    # (overlay text / no kie taskIds / no governed run dir / incomplete bundle) is
    # REJECTED and NOTHING is uploaded. This closes the bypass where a hand-built deck
    # was pushed to the client's GHL media library straight through this transport.
    # skip_boundary_gate exists ONLY for the PRES-026 isolated unit tests, which
    # exercise the resume/ledger contract with synthetic PNGs outside a governed
    # run dir — never for production pushes (the default stays fail-closed).
    if not skip_boundary_gate:
        gate_ok, gate_reasons = gate_deck_artifacts(
            run_dir, list(images) + list(extra_files or []))
        if not gate_ok:
            raise DeliveryGateRejected(gate_reasons)

    pit = ghl_media.resolve_location_pit()        # client's LOCATION PIT (never operator's)
    location_id = ghl_media.resolve_location_id()  # client's location id

    # 1) FOLDER RESOLUTION — FIX 36: NEVER create a folder (the folder-create endpoint
    # returns 404 per the SOP; the former 201 "primary path" branch is removed).
    # Only a PRE-EXISTING, human-approved folder id from intake is accepted; else the
    # shareable media root with a name prefix. No network call for the folder at all.
    parent_id = str(intake.get("ghl_media_folder_id") or "").strip() or None
    name_prefix = "" if parent_id else f"{slug} — "
    ghl_folder_id = parent_id or "root"

    ledger_path = _ledger_path(run_dir)
    scope = _run_scope(run_dir, intake, slug)
    # Seed the run scope + ledger version once (locked; first writer wins, the
    # binding never migrates under a run).
    def _seed(ledger: dict):
        dirty = False
        if ledger.get("ledger_version") != _UPLOADS_LEDGER_VERSION:
            ledger["ledger_version"] = _UPLOADS_LEDGER_VERSION
            dirty = True
        run = ledger.get("run")
        if not isinstance(run, dict):
            ledger["run"] = dict(scope)
            dirty = True
        if "ghl_folder_id" not in ledger:
            ledger["ghl_folder_id"] = ghl_folder_id
            dirty = True
        if "ghl_folder_name" not in ledger:
            ledger["ghl_folder_name"] = ledger.get("ghl_folder_name") or f"DECK {slug}"
            dirty = True
        if "ghl_folder_created_via_api" not in ledger:
            ledger["ghl_folder_created_via_api"] = False
            dirty = True
        return None, dirty
    _locked_ledger_update(ledger_path, _seed)

    ledger = _read_ledger_locked(ledger_path)
    # Legacy path-keyed idempotency is PRESERVED as a backstop: a path completed
    # by an older writer (no job_key) is adopted into the jobs table instead of
    # re-uploaded.
    legacy_done = {e.get("local_path"): e for e in ledger.get("uploaded", [])
                   if isinstance(e, dict) and e.get("local_path") and not e.get("job_key")}
    plans = _plan_upload_jobs(list(images) + list(extra_files or []),
                              scope=scope, ledger=ledger)
    for plan in plans:
        leg = legacy_done.get(plan["local_path"])
        if (plan["action"] == "upload" and plan["sha256"] is not None and isinstance(leg, dict)
                and str(leg.get("ghl_media_id") or leg.get("file_id") or "")):
            adopt = {
                "job_key": plan["job_key"], "company_id": scope["company_id"],
                "presentation_id": scope["presentation_id"],
                "artifact_type": plan["kind"],
                "ordinal": plan["slide_number"], "revision": plan["revision"],
                "sha256": plan["sha256"], "size_bytes": plan["size_bytes"],
                "local_path": plan["local_path"], "remote_name": str(leg.get("ghl_remote_name") or leg.get("name") or ""),
                "folder_id": str(leg.get("ghl_folder_id") or ghl_folder_id),
                "location_id": location_id, "status": _JOB_STATUS_COMPLETE,
                "attempts": 0, "file_id": str(leg.get("ghl_media_id") or leg.get("file_id")),
                "url": str(leg.get("ghl_url") or leg.get("public_url") or ""),
                "content_type": _content_type_for(plan["local_path"]),
                "uploaded_at": str(leg.get("uploaded_at") or _now_iso()),
                "remote_verified": False, "adopted_legacy": True,
                "slide_number": plan["slide_number"],
            }
            _persist_job(ledger_path, adopt)
            plan["action"] = "reuse"
            plan["job_key"] = adopt["job_key"]

    # Reconcile unknown outcomes via list/readback BEFORE any recreate.
    for plan in [p for p in plans if p["action"] == "reconcile"]:
        ledger_now = _read_ledger_locked(ledger_path)
        job = (ledger_now.get("jobs") or {}).get(plan["job_key"] or "")
        if not isinstance(job, dict):
            plan["action"] = "upload"
            continue
        # Another worker may have finished the reconcile first — re-plan.
        if job.get("status") == _JOB_STATUS_COMPLETE:
            plan["action"] = "reuse"
            continue
        job = _reconcile_unknown_job(ledger_path, dict(job), location_id=location_id,
                                     pit=pit, opener=opener)
        plan["action"] = "reuse" if job.get("status") == _JOB_STATUS_COMPLETE else "upload"
        plan["job_key"] = job.get("job_key")

    to_upload = [p for p in plans if p["action"] == "upload"]
    missing = [p for p in plans if p["action"] == "missing"]
    for plan in missing:
        _persist_job(ledger_path, {
            "job_key": plan["job_key"] or f"missing:{plan['local_path']}",
            "company_id": scope["company_id"], "presentation_id": scope["presentation_id"],
            "artifact_type": plan["kind"], "ordinal": plan["slide_number"], "revision": 0,
            "sha256": "", "size_bytes": None, "local_path": plan["local_path"],
            "remote_name": "", "folder_id": ghl_folder_id, "location_id": location_id,
            "status": _JOB_STATUS_FAILED, "attempts": 0, "file_id": "", "url": "",
            "content_type": _content_type_for(plan["local_path"]),
            "error": "local file unreadable (sha256 failed) — never uploaded",
            "slide_number": plan["slide_number"]})

    # Claim one job-key row per upload BEFORE the POST (locked): two workers on
    # the same run converge — the loser sees a live claim and skips its own
    # POST, then reads the winner's receipt via the follower path below.
    # The whole claim loop holds _CLAIM_SERIAL so two threads in ONE process
    # cannot interleave plan/read/claim on the same keys (flock serializes
    # processes; this serializes threads). One POST per key, no lost receipts.
    claimed: list = []
    seen_keys: set = set()
    with _CLAIM_SERIAL:
        for plan in to_upload:
            if str(plan["job_key"]) in seen_keys:
                continue  # same-process duplicate plan row: one POST per key
            seen_keys.add(str(plan["job_key"]))
            name = f"{name_prefix}{Path(plan['local_path']).name}"
            job = {
                "job_key": plan["job_key"], "company_id": scope["company_id"],
                "presentation_id": scope["presentation_id"],
                "artifact_type": plan["kind"], "ordinal": plan["slide_number"],
                "revision": plan["revision"], "sha256": plan["sha256"],
                "size_bytes": plan["size_bytes"], "local_path": plan["local_path"],
                "remote_name": name, "folder_id": ghl_folder_id,
                "location_id": location_id, "status": _JOB_STATUS_UPLOADING,
                "attempts": 0, "file_id": "", "url": "",
                "content_type": _content_type_for(plan["local_path"]),
                "slide_number": plan["slide_number"],
            }

            def _claim(ledger: dict, _job=job):
                jobs = ledger.get("jobs")
                if not isinstance(jobs, dict):
                    jobs = {}
                    ledger["jobs"] = jobs
                cur = jobs.get(str(_job["job_key"]))
                if isinstance(cur, dict) and cur.get("status") in (
                        _JOB_STATUS_COMPLETE, _JOB_STATUS_UNKNOWN):
                    return cur.get("status"), False  # owned elsewhere — no POST here
                if isinstance(cur, dict) and cur.get("status") == _JOB_STATUS_UPLOADING:
                    # A concurrent worker (thread or process) holds the claim and
                    # its POST is in flight — no second POST here. The follower
                    # path below waits for the owner's receipt.
                    return "uploading", False
                jobs[str(_job["job_key"])] = dict(_job)
                return "claimed", True
            if _locked_ledger_update(ledger_path, _claim) == "claimed":
                claimed.append((plan, job, name))

    pool = max_workers if isinstance(max_workers, int) and max_workers > 0 \
        else (_UPLOAD_POOL_VIDEO if any(str(plan["local_path"]).lower().endswith(".mp4")
                                       for plan, _job, _name in claimed)
              else _UPLOAD_POOL_DEFAULT)
    errors: list = []
    lock = threading.Lock()

    def _do_one(item):
        plan, job, name = item
        try:
            res, attempts = _upload_one_with_retries(
                plan["local_path"], location_id, name, pit,
                parent_id=parent_id, opener=opener, run_dir=run_dir,
                max_attempts=max(1, int(retries)))

            def _complete(ledger: dict, _job=job, _res=res, _attempts=attempts):
                jobs = ledger.get("jobs")
                if not isinstance(jobs, dict):
                    jobs = {}
                    ledger["jobs"] = jobs
                cur = jobs.get(str(_job["job_key"]))
                if isinstance(cur, dict) and cur.get("status") == _JOB_STATUS_COMPLETE \
                        and cur.get("file_id"):
                    return None, False  # sibling retry already completed it
                _job["status"] = _JOB_STATUS_COMPLETE
                _job["attempts"] = _attempts
                _job["file_id"] = _res["fileId"]
                _job["url"] = _res["url"]
                _job["http_status"] = _res.get("http")
                _job["uploaded_at"] = _now_iso()
                _job["remote_verified"] = False
                _job["error"] = ""
                jobs[str(_job["job_key"])] = dict(_job)
                _refresh_legacy_projections(ledger)
                return None, True
            _locked_ledger_update(ledger_path, _complete)
            # A changed hash supersedes the stale revision + invalidates
            # downstream links/receipts (PRES-026 step 3).
            _supersede_prior_revisions(ledger_path, local_path=plan["local_path"],
                                       sha256=plan["sha256"] or "",
                                       superseded_by=str(plan["job_key"]))
            pass  # projections refresh once after all workers finish (below)
        except DeliveryGateRejected:
            raise
        except Exception as exc:  # noqa: BLE001 — individual retry exhausted
            unknown = "unknown_remote_outcome" in str(exc)
            def _fail(ledger: dict, _job=job, _exc=exc, _unknown=unknown):
                jobs = ledger.get("jobs")
                if not isinstance(jobs, dict):
                    return None, False
                cur = jobs.get(str(_job["job_key"]))
                if isinstance(cur, dict) and cur.get("status") == _JOB_STATUS_COMPLETE:
                    _job.update(cur)  # a retry/reconcile already completed it
                    return None, False
                _job["status"] = _JOB_STATUS_UNKNOWN if _unknown else _JOB_STATUS_FAILED
                _job["attempts"] = max(1, int(retries))
                _job["error"] = repr(_exc)[:500]
                _job["outcome_unknown"] = bool(_unknown)
                jobs[str(_job["job_key"])] = dict(_job)
                _refresh_legacy_projections(ledger)
                return None, True
            _locked_ledger_update(ledger_path, _fail)
            with lock:
                errors.append(f"{Path(plan['local_path']).name}: {exc!r}")
            # Swallow here: the aggregate raise below fires AFTER every claimed
            # upload settled, so one broken artifact never aborts healthy ones
            # mid-pool — and the per-job rows are already durable.
            return plan
        return plan

    # Follower path (ALWAYS when this call did not claim every plan): a
    # concurrent worker may own the remaining keys with its POST in flight.
    # Wait for the owner's receipts instead of reporting in-flight rows as
    # our result. Runs even when claimed is non-empty (split ownership) and
    # even when claimed is empty (pure follower) — but NOT when there is
    # nothing to wait for (claimed every plan and this call has no pool).
    unclaimed = [p for p in to_upload
                 if not any(str(c[0].get("job_key")) == str(p["job_key"])
                            for c in claimed)]
    if unclaimed:
        import time as _t
        deadline = _t.time() + 120
        while _t.time() < deadline:
            cur = _read_ledger_locked(ledger_path)
            cur_jobs = cur.get("jobs") if isinstance(cur.get("jobs"), dict) else {}
            pending = [p for p in unclaimed
                       if (cur_jobs.get(str(p["job_key"])) or {}).get("status")
                       in (_JOB_STATUS_UPLOADING, _JOB_STATUS_PENDING,
                           _JOB_STATUS_UNKNOWN)]
            if not pending:
                break
            _t.sleep(0.05)
    if claimed:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(pool, len(claimed))) as ex:
            futures = [ex.submit(_do_one, item) for item in claimed]
            for fut in futures:
                try:
                    fut.result()
                except DeliveryGateRejected:
                    raise
                except Exception:
                    pass  # recorded per-job above; surfaced in aggregate below
        # Post-pool follower re-wait: unclaimed keys owned by a sibling whose
        # POST was still in flight while our pool ran. Re-read until settled.
        if unclaimed:
            import time as _t2
            deadline = _t2.time() + 120
            while _t2.time() < deadline:
                cur = _read_ledger_locked(ledger_path)
                cur_jobs = cur.get("jobs") if isinstance(cur.get("jobs"), dict) else {}
                pending = [p for p in unclaimed
                           if (cur_jobs.get(str(p["job_key"])) or {}).get("status")
                           in (_JOB_STATUS_UPLOADING, _JOB_STATUS_PENDING,
                               _JOB_STATUS_UNKNOWN)]
                if not pending:
                    break
                _t2.sleep(0.05)
    if errors:
        raise RuntimeError(
            f"media upload incomplete: {len(errors)} file(s) failed "
            f"({'; '.join(errors)[:800]}). Already-complete jobs keep their "
            "persisted receipts — resume reuses them, failed items retry alone.")

    def _refresh_final(ledger: dict):
        _refresh_legacy_projections(ledger)
        return dict(ledger), True
    ledger = _locked_ledger_update(ledger_path, _refresh_final)
    if not isinstance(ledger, dict):
        ledger = _read_ledger_locked(ledger_path)
    uploaded = ledger.get("uploaded", [])
    # Normalized, gate-readable projections derived from the full upload list.
    slides = sorted([e for e in uploaded if isinstance(e, dict) and e.get("kind") == "slide"],
                    key=lambda e: e.get("slide_number") or 0)
    pptx = next((e for e in uploaded if isinstance(e, dict) and e.get("kind") == "pptx"), None)

    out = {
        "deck_slug": slug,
        "ghl_folder_id": ghl_folder_id,
        # FIX 36: the agent never creates folders — the folder is pre-existing
        # (human-approved intake id) or the root, so created_via_api is always False.
        "ghl_folder_name": ledger.get("ghl_folder_name") or f"DECK {slug}",
        "ghl_folder_created_via_api": False,
        "run": ledger.get("run") or scope,
        "ledger_version": ledger.get("ledger_version") or _UPLOADS_LEDGER_VERSION,
        "uploaded": uploaded,
        "upload_count": len(uploaded),
        "slides": slides,
        "ghl_slide_upload_count": len(slides),
        "jobs": ledger.get("jobs", {}),
        "image_links": ledger.get("image_links", {}),
    }
    if ledger.get("delivery_receipts_invalid"):
        out["delivery_receipts_invalid"] = True
    if pptx:
        # The canonical path: the final assembled PPTX is in the GHL media library.
        out["pptx_ghl_media_id"] = pptx["ghl_media_id"]
        out["pptx_ghl_url"] = pptx["ghl_url"]
        out["pptx_ghl_remote_name"] = pptx["ghl_remote_name"]
    else:
        # Defect #9: GHL caps media uploads at 25MB (HTTP 413) and a 20-slide deck PPTX
        # (~52MB) CANNOT be hosted. When no pptx upload exists but the DECK PDF
        # (*-FINAL.pdf, kind "pdf") WAS uploaded, record the deck PDF as the hosted deck
        # deliverable so the closeout/verifier ledger still passes — and mark the deck as
        # hosted-as-PDF so downstream readers know the pptx is intentionally absent (it
        # exceeds the 25MB cap), never lost.
        #
        # FIX 111: the projections alone are not the contract — the receipt is. The
        # deck PDF is accepted as the hosted deck ONLY alongside the standard over-cap
        # receipt ({pptx_local_path, pdf_media_id, pptx_media_id: null,
        # reason: "over_cap"}), built by the ONE implementation in
        # ghl_media_upload.build_receipt and merged into the ledger by
        # record_upload_receipt. The receipt is what every accept-either-id gate
        # (ghl_media_upload.hosted_deck_media_id) validates, and what a human reads to
        # tell "the pptx was over the cap, the PDF twin is the hosted deck" from "the
        # pptx upload was lost". The local pptx that exceeded the cap is resolved from
        # the deck-pptx name among the would-be uploads / the delivery bundle, and a
        # pptx that is NOT actually over the cap does NOT get a receipt: it gets an
        # honest failure surface instead (the upload of a sub-cap pptx that never
        # landed is a lost upload, not an over-cap hosting).
        deck_pdf = _deck_pdf(uploaded)
        if deck_pdf is not None:
            out["pptx_ghl_media_id"] = deck_pdf["ghl_media_id"]
            out["pptx_ghl_url"] = deck_pdf["ghl_url"]
            out["pptx_ghl_remote_name"] = deck_pdf["ghl_remote_name"]
            out["deck_upload_kind"] = "pdf"
            pptx_local = _deck_pptx_local_path(run_dir, slug, extra_files or [])
            if pptx_local is not None and ghl_media_upload.is_over_cap(pptx_local):
                receipt = ghl_media_upload.build_receipt(pptx_local, {
                    "ghl_media_id": deck_pdf.get("ghl_media_id"),
                    "ghl_url": deck_pdf.get("ghl_url"),
                    "ghl_remote_name": deck_pdf.get("ghl_remote_name"),
                })
                ghl_media_upload.record_upload_receipt(out, receipt)

    # Final persist under the same lock (atomic + fsync); merges projections
    # while KEEPING the jobs table, run scope and supersede/invalidation marks.
    def _final(ledger: dict):
        for k in ("deck_slug", "ghl_folder_id", "ghl_folder_name",
                  "ghl_folder_created_via_api", "run", "ledger_version",
                  "uploaded", "upload_count", "slides", "ghl_slide_upload_count",
                  "jobs", "image_links"):
            ledger[k] = out[k]
        for k in ("pptx_ghl_media_id", "pptx_ghl_url", "pptx_ghl_remote_name",
                  "deck_upload_kind", "deck_upload_receipt", "pptx_local_path",
                  "delivery_receipts_invalid"):
            if k in out:
                ledger[k] = out[k]
            else:
                ledger.pop(k, None)
        return dict(ledger), True
    return _locked_ledger_update(ledger_path, _final)


# ---------------------------------------------------------------------------
# CLOSEOUT GATE — no delivery without the GHL upload (folds under AF-DELIVERY-COMPLETE).
# ---------------------------------------------------------------------------
def _valid_owner_skip(run_dir: Path):
    """Return the owner-skip record that authorizes skipping the GHL-upload gate, or
    None. The ONLY legitimate skip: a LOGGED token in
    working/checkpoints/process_manifest.json under `owner_skip_approval` with
    owner_approved:true + a non-empty approved_by + a non-empty reason + a gate name
    that matches this gate. A list or a single dict are both accepted. An agent's own
    `has_ghl:false` is NOT a skip — only an explicit owner/founder decision is."""
    pm = _read_json(run_dir / "working" / "checkpoints" / "process_manifest.json")
    raw = pm.get("owner_skip_approval") if isinstance(pm, dict) else None
    if raw is None:
        return None
    records = raw if isinstance(raw, list) else [raw]
    for rec in records:
        if not isinstance(rec, dict):
            continue
        if rec.get("owner_approved") is not True:
            continue
        if not str(rec.get("approved_by", "")).strip():
            continue
        if not str(rec.get("reason", "")).strip():
            continue
        gate = str(rec.get("gate") or rec.get("gate_id") or rec.get("phase_id") or "").strip()
        if gate in _GATE_ALIASES:
            return rec
    return None


def _collect_slide_uploads(media: dict) -> list:
    """Gather per-slide upload records from any of the ledger shapes (the normalized
    `slides` list, an agent-written `images` list, or `uploaded` entries that are slide
    PNGs). Deduped so the same slide is never double-counted."""
    out, seen = [], set()

    def add(entry):
        if not isinstance(entry, dict):
            return
        key = (entry.get("local_path") or entry.get("ghl_media_id")
               or entry.get("file_id") or entry.get("ghl_remote_name") or repr(entry))
        if key in seen:
            return
        seen.add(key)
        out.append(entry)

    for e in media.get("slides") or []:
        add(e)
    for e in media.get("images") or []:
        add(e)
    for e in media.get("uploaded") or []:
        if not isinstance(e, dict):
            continue
        nm = str(e.get("name") or e.get("local_path") or "")
        if e.get("kind") == "slide" or (nm.lower().endswith(".png") and _SLIDE_RE.search(nm)):
            add(e)
    return out


def _slide_complete(e: dict) -> bool:
    mid = e.get("ghl_media_id") or e.get("file_id")
    if str(e.get("ghl_upload_status", "")).lower() in ("failed", "pending"):
        return False
    return bool(str(mid or "").strip())


def gate_ghl_media_complete(run_dir, *, expected_slide_count: int | None = None):
    """HARD closeout gate. Returns (ok: bool, reasons: list[str]).

    PASS only when working/checkpoints/media_library.json records all three GHL
    uploads — folder + per-slide PNGs + final PPTX — OR a logged owner_skip_approval
    authorizes the skip. There is NO defer-to-pass: this gate runs at closeout, where a
    GHL-enabled deck with no upload record is exactly the failure it exists to catch."""
    run_dir = Path(run_dir)

    # The ONLY skip path: an explicit, logged owner/founder approval token.
    if _valid_owner_skip(run_dir) is not None:
        return True, []

    intake = _read_json(run_dir / "working" / "copy" / "intake.json")
    media = _read_json(_ledger_path(run_dir))

    # has_ghl:false WITHOUT an owner token is an agent choice, not an authorization.
    if intake.get("has_ghl") is False:
        return False, [
            f"{GHL_UPLOAD_GATE}: intake has_ghl:false but no logged owner_skip_approval in "
            "working/checkpoints/process_manifest.json. The GHL media-upload gate may be "
            "skipped ONLY by an explicit owner/founder token (owner_approved:true + "
            "approved_by + reason + gate). An agent cannot opt out of the upload on its own."]

    if not media:
        return False, [
            f"{GHL_UPLOAD_GATE}: working/checkpoints/media_library.json is missing/empty — "
            "no GHL upload record at all (folder + per-slide PNGs + final PPTX). No deck "
            "ships without the GHL media upload."]

    reasons = []

    # (1) per-deck folder resolved (a real id OR the 'root' fallback; null seed fails).
    folder = str(media.get("ghl_folder_id") or "").strip()
    if not folder:
        reasons.append(
            f"{GHL_UPLOAD_GATE}: ghl_folder_id is null/empty — the per-deck GHL media "
            "folder was never resolved (the human-approved intake ghl_media_folder_id, "
            "or the 'root' fallback; the agent never creates folders — FIX 36).")

    # (2) per-slide PNG uploads, each with a real ghl_media_id.
    # PRES-026 repair surface: jobs stuck unknown/failed/repair_required are
    # named explicitly (not folded into a generic "incomplete" bucket), and a
    # superseded stale revision never counts as the hosted slide.
    jobs = media.get("jobs") if isinstance(media.get("jobs"), dict) else {}
    bad_jobs = sorted(
        str(j.get("job_key") or jk) for jk, j in jobs.items()
        if isinstance(j, dict) and j.get("artifact_type") == "slide"
        and j.get("status") in (_JOB_STATUS_UNKNOWN, _JOB_STATUS_FAILED,
                                _JOB_STATUS_REPAIR_REQUIRED)
        and not j.get("superseded_by"))
    if bad_jobs:
        reasons.append(
            f"{GHL_UPLOAD_GATE}: {len(bad_jobs)} slide upload job(s) need repair "
            f"(unknown_remote_outcome/failed/repair_required, not complete): "
            f"{', '.join(bad_jobs)}. Reconcile via list/readback (unknown) or "
            "re-upload the affected item; healthy files stay complete.")
    slides = _collect_slide_uploads(media)
    if not slides:
        reasons.append(
            f"{GHL_UPLOAD_GATE}: no per-slide PNG upload recorded in media_library.json — "
            "every passed slide must be uploaded with a real ghl_media_id.")
    else:
        incomplete = [s for s in slides if not _slide_complete(s)]
        if incomplete:
            ids = [str(s.get("slide_number") or s.get("ghl_remote_name") or s.get("local_path"))
                   for s in incomplete]
            reasons.append(
                f"{GHL_UPLOAD_GATE}: {len(incomplete)} slide upload(s) are not complete "
                f"(no ghl_media_id or status failed/pending): {', '.join(ids)}.")
        # coverage cross-check against any recorded expected count.
        exp = expected_slide_count
        if exp is None:
            for k in ("expected_slide_count", "slide_count_final", "slide_count", "local_count"):
                v = media.get(k)
                if isinstance(v, int) and v > 0:
                    exp = v
                    break
        if isinstance(exp, int) and exp > 0 and len(slides) < exp:
            reasons.append(
                f"{GHL_UPLOAD_GATE}: only {len(slides)} of {exp} slide PNGs are uploaded to "
                "GHL — every slide must be hosted before delivery.")

    # (3) final assembled deck uploaded — FIX 111 accept-either-id: a real pptx media
    # id (the canonical path) OR a PDF media id carrying a VALID over-cap receipt
    # (reason "over_cap", pptx_media_id null, real pdf id). The bare
    # pptx_ghl_media_id-absent check stays for the no-receipt case so the failure
    # message still names the missing upload; the accept-either-id reader
    # (ghl_media_upload.hosted_deck_media_id) decides the pass, never a bare
    # deck_upload_kind marker without a valid receipt.
    hosted_id = ghl_media_upload.hosted_deck_media_id(media)
    if not hosted_id:
        if not str(media.get("pptx_ghl_media_id") or "").strip():
            reasons.append(
                f"{GHL_UPLOAD_GATE}: pptx_ghl_media_id is absent — the final assembled PPTX was "
                "never uploaded to the GHL media library.")
        else:
            reasons.append(
                f"{GHL_UPLOAD_GATE}: the deck's hosted-media id does not pass the FIX 111 "
                "accept-either-id check — a PDF-twin id without a valid over-cap receipt "
                "(reason \"over_cap\", pptx_media_id null, real pdf_media_id) is not proof "
                "the deck is hosted.")

    # PRES-026 step 5 — completion-time remote proof (read-only, fail-soft by
    # design): when the LOCATION PIT resolves, confirm the recorded deck id
    # still lists back. A recorded id with no remote object is repair_required
    # signal, never a silent pass — but a missing credential/transport never
    # blocks closeout by itself (silent skip: the pre-existing NOTE-heavy
    # contract in test_upload_gate expects reasons == [] on a complete ledger
    # with no env; verify_run_uploads is the explicit evidence surface).
    if hosted_id:
        try:
            pit = ghl_media.resolve_location_pit()
            loc = ghl_media.resolve_location_id()
        except Exception:  # noqa: BLE001
            return (len([r for r in reasons if not str(r).startswith("NOTE")]) == 0), reasons
        try:
            listing = ghl_media.list_media(loc, pit, media_type="file", limit=200)
        except Exception:  # noqa: BLE001
            return (len([r for r in reasons if not str(r).startswith("NOTE")]) == 0), reasons
        entries = listing.get("data") or []
        deck_name = str(media.get("pptx_ghl_remote_name") or "")
        found = _find_remote_match(entries, remote_name=deck_name, file_id=hosted_id)
        if not found:
            reasons.append(
                f"{GHL_UPLOAD_GATE}: the recorded deck id {hosted_id[:24]}… is NOT "
                "present in the GHL media library listing (read-only GET "
                "/medias/files) — deleted or expired link, repair_required. "
                "Re-upload only the affected deck; healthy slide files stay complete.")
        elif not str(media.get("deck_listback_verified") or "").strip():
            # Record the positive evidence on the ledger (locked) so completion
            # carries URL content-type/size/hash proof, not just the id.
            def _mark_lb(ledger: dict):
                ledger["deck_listback_verified"] = _now_iso()
                ledger["deck_listback_evidence"] = {
                    k: found.get(k) for k in
                    ("fileId", "_id", "id", "name", "url", "fileUrl",
                     "contentType", "mimeType", "size", "fileSize",
                     "md5", "sha256") if k in found}
                return None, True
            try:
                _locked_ledger_update(_ledger_path(run_dir), _mark_lb)
            except Exception:  # noqa: BLE001 — evidence write is best-effort
                pass

    return (len([r for r in reasons if not str(r).startswith("NOTE")]) == 0), reasons


def verify_run_uploads(run_dir, *, opener=None, limit: int = 200) -> dict:
    """PRES-026 step 5 — completion-time remote verification for every job in
    the run's durable ledger. One shared read-only list/readback
    (GET /medias/files) is matched against each complete job by recorded file
    id, else by exact bound remote name. Each job records remote_verified True
    plus the remote's content-type/size/hash evidence where the API exposes it.
    A complete job with NO remote match flips to repair_required (deleted or
    expired link) while healthy files stay complete — repair touches only the
    affected item. Returns {listed, verified, repair_required:[job_keys],
    unknown:[job_keys], error}. Never mutates the remote (read-only GET)."""
    run_dir = Path(run_dir).resolve()
    ledger_path = _ledger_path(run_dir)
    ledger = _read_ledger_locked(ledger_path)
    jobs = ledger.get("jobs") if isinstance(ledger.get("jobs"), dict) else {}
    jobs = {jk: dict(j) for jk, j in jobs.items() if isinstance(j, dict)}
    result: dict = {"listed": 0, "verified": 0, "repair_required": [],
                    "unknown": [], "error": None}
    if not jobs:
        return result
    try:
        pit = ghl_media.resolve_location_pit()
        loc = ghl_media.resolve_location_id()
    except Exception as exc:  # noqa: BLE001 — no credentials: report, never block
        result["error"] = f"credential resolution: {exc!r}"
        return result
    health = _remote_health_for_jobs(list(jobs.values()), location_id=loc, pit=pit,
                                     opener=opener, limit=limit)
    result["listed"] = int(health.get("_listed") or 0)
    if health.get("_error"):
        result["error"] = str(health["_error"])
        for jk in jobs:
            result["unknown"].append(jk)
        return result
    for jk, job in jobs.items():
        if job.get("status") != _JOB_STATUS_COMPLETE or job.get("superseded_by"):
            continue
        match = health.get(jk)
        if isinstance(match, dict) and match:
            job["remote_verified"] = True
            job["remote_evidence"] = {
                "content_type": match.get("contentType") or match.get("mimeType") or "",
                "size": match.get("size", match.get("fileSize")),
                "hash": match.get("sha256") or match.get("md5") or "",
                "name": match.get("name") or "",
                "url": match.get("url") or match.get("fileUrl") or "",
                "checked_at": _now_iso(),
            }
            _persist_job(ledger_path, job)
            result["verified"] += 1
        else:
            job["status"] = _JOB_STATUS_REPAIR_REQUIRED
            job["remote_verified"] = False
            job["error"] = ("repair_required: ledger claims a complete upload but the "
                            "remote list/readback has no matching object (deleted or "
                            "expired link) — re-upload only this item")
            job["remote_evidence"] = {"listed": result["listed"], "matched": False,
                                      "checked_at": _now_iso()}
            _persist_job(ledger_path, job)
            result["repair_required"].append(jk)
    return result


def repair_run_uploads(run_dir, *, opener=None, max_workers: int | None = None,
                       retries: int = _UPLOAD_RETRIES_DEFAULT,
                       skip_boundary_gate: bool = False) -> dict:
    """Re-upload ONLY jobs in repair_required/failed/unknown status for the run
    (PRES-026 step 5 / acceptance 4). Healthy complete jobs are never touched.
    Unknown outcomes reconcile via list/readback before any recreate. Returns
    push_deck_media's result dict scoped to the repaired local paths."""
    run_dir = Path(run_dir).resolve()
    ledger_path = _ledger_path(run_dir)
    ledger = _read_ledger_locked(ledger_path)
    jobs = ledger.get("jobs") if isinstance(ledger.get("jobs"), dict) else {}
    targets = sorted(str(j.get("local_path") or "") for j in jobs.values()
                     if isinstance(j, dict)
                     and j.get("status") in (_JOB_STATUS_REPAIR_REQUIRED, _JOB_STATUS_FAILED,
                                             _JOB_STATUS_UNKNOWN)
                     and not j.get("superseded_by") and j.get("local_path"))
    if not targets:
        return {"repaired": [], "note": "no repair_required/failed/unknown jobs"}
    out = push_deck_media(run_dir, targets, opener=opener, max_workers=max_workers,
                          retries=retries, skip_boundary_gate=skip_boundary_gate)
    out["repaired"] = targets
    return out


def main():
    ap = argparse.ArgumentParser(description="Host a deck's images + deliverables in GHL, "
                                             "run the GHL-upload closeout gate, or LIST "
                                             "the media library read-only.")
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--deck-slug", default=None)
    ap.add_argument("--images", nargs="*", default=None)
    ap.add_argument("--extra", nargs="*", default=None,
                    help="extra deliverables to upload (final PPTX/PDF).")
    ap.add_argument("--gate", action="store_true",
                    help="run the HARD closeout gate (no upload, exit 1 on fail).")
    ap.add_argument("--expected-slides", type=int, default=None,
                    help="optional per-slide coverage count for the gate.")
    ap.add_argument("--list", action="store_true",
                    help="READ-ONLY list of the GHL media library (GET /medias/files; "
                         "never mutates). No --run-dir needed. Optional --list-name "
                         "filters by name.")
    ap.add_argument("--list-name", default=None,
                    help="with --list, only show entries whose name contains this string.")
    ap.add_argument("--list-type", default="file", choices=["file", "folder"],
                    help="with --list, list files (default) or folders.")
    ap.add_argument("--list-limit", type=int, default=200,
                    help="with --list, max entries to fetch (default 200).")
    ap.add_argument("--verify", action="store_true",
                    help="PRES-026: read-only remote verification of every job in the "
                         "run ledger (list/readback; flips missing remotes to "
                         "repair_required, never mutates the remote).")
    ap.add_argument("--repair", action="store_true",
                    help="PRES-026: re-upload ONLY repair_required/failed/unknown jobs "
                         "for the run; healthy files untouched.")
    args = ap.parse_args()

    if args.list:
        # READ-ONLY LIST-BACK — never mutates the media library.
        try:
            pit = ghl_media.resolve_location_pit()
            loc = ghl_media.resolve_location_id()
        except Exception as exc:  # noqa: BLE001
            print(f"GHL MEDIA LIST: FAIL (credential resolution: {exc})", file=sys.stderr)
            return 2
        try:
            listing = ghl_media.list_media(loc, pit, media_type=args.list_type,
                                           limit=args.list_limit)
        except Exception as exc:  # noqa: BLE001
            print(f"GHL MEDIA LIST: FAIL ({exc})", file=sys.stderr)
            return 2
        entries = listing.get("data") or []
        if args.list_name:
            needle = str(args.list_name).lower()
            entries = [e for e in entries if isinstance(e, dict)
                       and needle in str(e.get("name") or "").lower()]
        print(json.dumps({"http": listing.get("http"), "count": len(entries),
                          "data": entries}, indent=2))
        return 0

    if not args.run_dir:
        ap.error("--run-dir is required (or use --list / --gate)")
    rd = Path(args.run_dir).resolve()

    if args.gate:
        ok, reasons = gate_ghl_media_complete(rd, expected_slide_count=args.expected_slides)
        if ok:
            print("GHL MEDIA GATE: PASS (folder + per-slide PNGs + final PPTX recorded, "
                  "or logged owner skip)")
            return 0
        print(f"GHL MEDIA GATE: FAIL ({GHL_UPLOAD_GATE})")
        for r in reasons:
            print("  -", r)
        return 1

    if args.verify:
        print(json.dumps(verify_run_uploads(rd), indent=2))
        return 0

    if args.repair:
        try:
            print(json.dumps(repair_run_uploads(rd), indent=2, default=str))
        except DeliveryGateRejected as exc:
            print("GHL MEDIA REPAIR: ABORTED — delivery boundary gate REJECTED the deck "
                  "(NOTHING uploaded).", file=sys.stderr)
            for r in exc.reasons:
                print("  - " + r, file=sys.stderr)
            return 1
        return 0

    imgs = args.images
    if not imgs:
        imgs = sorted(str(p) for p in (rd / "renders").glob("slide-*.png"))
    # A deck-only push (just --extra, no slide PNGs) is legitimate (host the final
    # assembled deck) and MUST still pass through the boundary gate, so only bail when
    # there is nothing at all to host.
    if not imgs and not (args.extra or []):
        print("FATAL: no images or deliverables to host (pass --images/--extra or "
              "populate renders/).", file=sys.stderr)
        return 2
    try:
        res = push_deck_media(rd, imgs, deck_slug=args.deck_slug, extra_files=args.extra)
    except DeliveryGateRejected as exc:
        print("GHL MEDIA PUSH: ABORTED — delivery boundary gate REJECTED the deck "
              "(NOTHING uploaded).", file=sys.stderr)
        for r in exc.reasons:
            print("  - " + r, file=sys.stderr)
        print("A deck not produced by the governed kie.ai pipeline cannot be delivered. "
              "The ONLY bypass is a logged owner_skip_approval token (gate=<AF code>); an "
              "agent may NOT self-approve.", file=sys.stderr)
        return 1
    print(json.dumps(res, indent=2))
    return 0


# ---------------------------------------------------------------------------
# SELF-TEST for the closeout gate — no network, stdlib only.
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile
    fails = []

    def _setup(base, *, intake=None, media=None, pm=None):
        ck = base / "working" / "checkpoints"
        ck.mkdir(parents=True, exist_ok=True)
        (base / "working" / "copy").mkdir(parents=True, exist_ok=True)
        if intake is not None:
            (base / "working" / "copy" / "intake.json").write_text(json.dumps(intake))
        if media is not None:
            (ck / "media_library.json").write_text(json.dumps(media))
        if pm is not None:
            (ck / "process_manifest.json").write_text(json.dumps(pm))

    GOOD_MEDIA = {
        "ghl_folder_id": "fld_123",
        "slides": [{"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"},
                   {"slide_number": 2, "ghl_media_id": "m2", "ghl_upload_status": "complete"}],
        "pptx_ghl_media_id": "pptx_9",
    }

    # A — all three uploads present -> PASS.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t); _setup(base, intake={"has_ghl": True}, media=GOOD_MEDIA)
        ok, r = gate_ghl_media_complete(base)
        if not ok:
            fails.append(f"A complete: expected PASS, got {r}")

    # B — empty ledger -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t); _setup(base, intake={"has_ghl": True}, media={})
        ok, r = gate_ghl_media_complete(base)
        if ok or not r:
            fails.append(f"B empty: expected FAIL, got ok={ok} {r}")

    # C — folder + slides but NO pptx -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        m = dict(GOOD_MEDIA); m.pop("pptx_ghl_media_id")
        _setup(base, intake={"has_ghl": True}, media=m)
        ok, r = gate_ghl_media_complete(base)
        if ok or not any("pptx_ghl_media_id" in x for x in r):
            fails.append(f"C no-pptx: expected pptx FAIL, got ok={ok} {r}")

    # D — folder + pptx but NO slide uploads -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, intake={"has_ghl": True},
               media={"ghl_folder_id": "root", "pptx_ghl_media_id": "p1"})
        ok, r = gate_ghl_media_complete(base)
        if ok or not any("per-slide" in x for x in r):
            fails.append(f"D no-slides: expected slide FAIL, got ok={ok} {r}")

    # E — null ghl_folder_id (Step-0 seed only) -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        m = dict(GOOD_MEDIA); m["ghl_folder_id"] = None
        _setup(base, intake={"has_ghl": True}, media=m)
        ok, r = gate_ghl_media_complete(base)
        if ok or not any("ghl_folder_id" in x for x in r):
            fails.append(f"E null-folder: expected folder FAIL, got ok={ok} {r}")

    # F — has_ghl:false with NO owner token -> FAIL (agent cannot opt out).
    with tempfile.TemporaryDirectory() as t:
        base = Path(t); _setup(base, intake={"has_ghl": False}, media={})
        ok, r = gate_ghl_media_complete(base)
        if ok or not any("owner_skip_approval" in x for x in r):
            fails.append(f"F agent-skip: expected owner-token FAIL, got ok={ok} {r}")

    # G — has_ghl:false WITH a valid logged owner skip -> PASS (carve-out).
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, intake={"has_ghl": False}, media={},
               pm={"owner_skip_approval": {"owner_approved": True, "approved_by": "owner",
                                           "reason": "client has no GHL account",
                                           "gate": "AF-DELIVERY-COMPLETE"}})
        ok, r = gate_ghl_media_complete(base)
        if not ok:
            fails.append(f"G owner-skip: expected PASS, got {r}")

    # H — owner skip present but owner_approved:false -> NOT a skip -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, intake={"has_ghl": True}, media={},
               pm={"owner_skip_approval": {"owner_approved": False, "approved_by": "x",
                                           "reason": "y", "gate": "AF-DELIVERY-COMPLETE"}})
        ok, r = gate_ghl_media_complete(base)
        if ok:
            fails.append(f"H false-token: expected FAIL, got ok={ok} {r}")

    # I — a slide upload missing its media id -> FAIL (incomplete).
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        m = {"ghl_folder_id": "root", "pptx_ghl_media_id": "p",
             "slides": [{"slide_number": 1, "ghl_media_id": "m1", "ghl_upload_status": "complete"},
                        {"slide_number": 2, "ghl_upload_status": "pending"}]}
        _setup(base, intake={"has_ghl": True}, media=m)
        ok, r = gate_ghl_media_complete(base)
        if ok or not any("not complete" in x for x in r):
            fails.append(f"I incomplete-slide: expected FAIL, got ok={ok} {r}")

    # J — coverage shortfall (2 uploaded, 50 expected) -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        m = dict(GOOD_MEDIA); m["expected_slide_count"] = 50
        _setup(base, intake={"has_ghl": True}, media=m)
        ok, r = gate_ghl_media_complete(base)
        if ok or not any("of 50" in x for x in r):
            fails.append(f"J coverage: expected coverage FAIL, got ok={ok} {r}")

    # === OUT-OF-BAND DELIVERY BOUNDARY GATE wired into THIS transport (v16.1.1) ===
    # gate_deck_artifacts is the decision push_deck_media makes BEFORE any upload. These
    # cases prove a hand-built / no-run-dir deck is rejected (transport aborts) while a
    # clean kie-baked deck and non-deck media are allowed. Decks are built via the
    # delivery_gate stdlib OOXML helpers (no python-pptx, no network).
    # K — clean kie-baked deck in a full governed run -> ALLOW (ok, []).
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        deck = delivery_gate._mk_full_run(base, with_text=False, task_ids=("kie-aaa",))
        delivery_gate._write_render_manifest(base, ["kie-aaa"])
        ok, r = gate_deck_artifacts(base, [str(deck)])
        if not ok:
            fails.append(f"K transport-clean: expected ALLOW, got {r}")

    # L — hand-built OVERLAY deck (selectable on-slide text) -> ABORT upload.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        deck = delivery_gate._mk_full_run(base, with_text=True, task_ids=("kie-aaa",))
        ok, r = gate_deck_artifacts(base, [str(deck)])
        if ok or not any("AF-OVERLAY-DELIVERED" in x for x in r):
            fails.append(f"L transport-overlay: expected ABORT (AF-OVERLAY-DELIVERED), got ok={ok} {r}")

    # M — deck with NO governed run dir (hand-built outside the pipeline) -> ABORT.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        deck = delivery_gate._mk_pptx(base / "loose-deck.pptx", with_text=False)
        ok, r = gate_deck_artifacts(base, [str(deck)])
        if ok or not any("AF-NO-RUN-DIR" in x for x in r):
            fails.append(f"M transport-no-run-dir: expected ABORT (AF-NO-RUN-DIR), got ok={ok} {r}")

    # N — non-deck media only (slide PNGs) -> NOT gated (mid-pipeline slide uploads must
    # not be blocked; only the final deck artifact is inspected).
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        ok, r = gate_deck_artifacts(base, ["renders/slide-01.png", "renders/slide-02.png"])
        if not ok or r:
            fails.append(f"N transport-non-deck: expected ALLOW (no decks to gate), got ok={ok} {r}")

    # O — push_deck_media itself ABORTS before any network/credential call on a bad deck.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        deck = delivery_gate._mk_pptx(base / "loose-deck.pptx", with_text=False)
        raised = False
        try:
            push_deck_media(base, [str(deck)])
        except DeliveryGateRejected:
            raised = True
        except Exception as exc:  # noqa: BLE001 — must be the gate, not a network error
            fails.append(f"O push-abort: expected DeliveryGateRejected, got {exc!r}")
        if not raised:
            fails.append("O push-abort: push_deck_media did NOT abort on an un-governed deck")

    # === LOWEST GHL UPLOAD CHOKEPOINT (v16.1.2) — the direct upload_media(deck) bypass ===
    # ghl_media.upload_media is now a gated wrapper. These cases prove (P/Q) a deck handed
    # STRAIGHT to upload_media (bypassing push_deck_media) is REJECTED and never POSTed,
    # (R) the governed push_deck_media path still HOSTS a clean deck end-to-end (does NOT
    # self-block), and (S) an ordinary image is UNAFFECTED. Decks/run dirs are built via
    # the delivery_gate stdlib OOXML helpers (no python-pptx, no network).
    import os as _os

    def _mock_ghl_opener(req, timeout):
        # Mock for the upload POST (FIX 36: no folder-create POST is ever issued; the
        # push path resolves the folder from the pre-existing intake id or the root).
        # Carries the fields the canonical upload parser reads (fileId/url).
        class _R:
            def getcode(self):
                return 200

            def read(self):
                return (b'{"id":"fld_x","folderId":"fld_x","fileId":"file_x",'
                        b'"url":"https://storage.googleapis.com/msgsndr/file_x"}')
        return _R()

    # P — DIRECT upload_media on a HAND-BUILT (overlay) deck is REJECTED; opener never reached.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        deck = delivery_gate._mk_full_run(base, with_text=True, task_ids=("kie-aaa",))
        posted = []

        def _trip(req, timeout):
            posted.append(1)
            raise AssertionError("opener reached — overlay deck POSTed UNGATED")

        raised = False
        try:
            ghl_media.upload_media(str(deck), "loc", deck.name, "pit", opener=_trip)
        except DeliveryGateRejected:
            raised = True
        except Exception as exc:  # noqa: BLE001 — must be the gate, not a network error
            fails.append(f"P chokepoint-overlay: expected DeliveryGateRejected, got {exc!r}")
        if not raised:
            fails.append("P chokepoint-overlay: direct upload_media(overlay deck) was NOT blocked")
        if posted:
            fails.append("P chokepoint-overlay: opener invoked — overlay deck was uploaded")

    # Q — DIRECT upload_media on a deck with NO governed run dir is REJECTED (AF-NO-RUN-DIR).
    with tempfile.TemporaryDirectory() as t:
        loose = delivery_gate._mk_pptx(Path(t) / "loose-deck.pptx", with_text=False)
        posted = []

        def _trip2(req, timeout):
            posted.append(1)
            raise AssertionError("opener reached — no-run-dir deck POSTed UNGATED")

        raised = False
        try:
            ghl_media.upload_media(str(loose), "loc", "loose-deck.pptx", "pit", opener=_trip2)
        except DeliveryGateRejected:
            raised = True
        except Exception as exc:  # noqa: BLE001
            fails.append(f"Q chokepoint-no-run-dir: expected DeliveryGateRejected, got {exc!r}")
        if not raised:
            fails.append("Q chokepoint-no-run-dir: direct upload_media(loose deck) was NOT blocked")
        if posted:
            fails.append("Q chokepoint-no-run-dir: opener invoked — loose deck was uploaded")

    # R — the GOVERNED path still SUCCEEDS end-to-end: push_deck_media over a clean governed
    # deck passes the gate at the chokepoint and HOSTS the deck (mock HTTP), recording
    # pptx_ghl_media_id. The fix does NOT self-block the legitimate upload.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        deck = delivery_gate._mk_full_run(base, with_text=False, task_ids=("kie-aaa",))
        delivery_gate._write_render_manifest(base, ["kie-aaa"])
        saved = {k: _os.environ.get(k) for k in ("GHL_API_KEY", "GHL_LOCATION_ID")}
        _os.environ["GHL_API_KEY"] = "pit-" + "a" * 40  # 40+ chars: not a doc placeholder
        _os.environ["GHL_LOCATION_ID"] = "loc-" + "a" * 40
        out = None
        try:
            out = push_deck_media(base, [], extra_files=[str(deck)], opener=_mock_ghl_opener)
        except Exception as exc:  # noqa: BLE001
            fails.append(f"R governed-allow: push_deck_media(governed deck) raised {exc!r} "
                         "(the legitimate upload must NOT self-block)")
        finally:
            for k, v in saved.items():
                if v is None:
                    _os.environ.pop(k, None)
                else:
                    _os.environ[k] = v
        if out is not None and not str(out.get("pptx_ghl_media_id") or "").strip():
            fails.append(f"R governed-allow: expected a hosted pptx_ghl_media_id, got {out!r}")

    # S — an ORDINARY IMAGE through the SAME chokepoint is UNAFFECTED (no gate runs; the
    # canonical PNG path). Even with no run dir a real PNG uploads cleanly.
    with tempfile.TemporaryDirectory() as t:
        png = Path(t) / "slide-01.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)  # real PNG magic bytes
        res = None
        try:
            res = ghl_media.upload_media(str(png), "loc", "Slide 01 v1", "pit",
                                         opener=_mock_ghl_opener)
        except Exception as exc:  # noqa: BLE001
            fails.append(f"S image-unaffected: ordinary image upload raised {exc!r}")
        if res is not None and res.get("fileId") != "file_x":
            fails.append(f"S image-unaffected: expected a clean upload, got {res!r}")

    # === DEFECT #9 — GHL 25MB media cap (HTTP 413) + DECK-PDF fallback ===
    # T — a governed run whose deck is hosted ONLY as the *-FINAL.pdf (the pptx exceeds
    # the 25MB cap) must record the deck PDF as the deck deliverable: pptx_ghl_media_id /
    # pptx_ghl_url / pptx_ghl_remote_name come from the deck-PDF upload and
    # deck_upload_kind == "pdf" notes the deck is hosted as PDF.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        pkg = base / "delivery" / "demo-deck-FINAL"
        pkg.mkdir(parents=True, exist_ok=True)
        deck_pdf = pkg / "demo-deck-FINAL.pdf"
        deck_pdf.write_bytes(b"%PDF-1.7\n" + b"\x00" * 128)  # real %PDF header (image-only: no fonts/text ops)
        for nm in ("demo-deck-FINAL.pptx", "PRESENTER-GUIDE.pdf", "PRESENTERS-SPEECH.pdf",
                   "PRESENTER-AUDIO.mp3", "demo-deck-WEBINAR.mp4"):
            (pkg / nm).write_bytes(b"x" * 1024)
        (base / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
        (base / "working" / "checkpoints" / "process_manifest.json").write_text(json.dumps(
            {"phases": [{"phase": "render", "output_slide_count": 1,
                         "slides": [{"slide": 1, "taskId": "kie-aaa"}]}]}))
        (base / "working" / "checkpoints" / "delivery_plan.json").write_text(json.dumps(
            {"destinations": [{"type": "ghl", "status": "uploaded"},
                              {"type": "mac_downloads",
                               "verify_anchor": str(pkg / "demo-deck-FINAL.pptx")}]}))
        (base / "working" / "teleprompter").mkdir(parents=True, exist_ok=True)
        (base / "working" / "teleprompter" / "teleprompter.html").write_text("<html></html>")
        (pkg / "presenter-teleprompter.html").write_text("<html></html>")
        saved = {k: _os.environ.get(k) for k in ("GHL_API_KEY", "GHL_LOCATION_ID")}
        _os.environ["GHL_API_KEY"] = "pit-" + "a" * 40  # 40+ chars: not a doc placeholder
        _os.environ["GHL_LOCATION_ID"] = "loc-" + "a" * 40
        out = None
        try:
            out = push_deck_media(base, [], extra_files=[str(deck_pdf)], opener=_mock_ghl_opener)
        except Exception as exc:  # noqa: BLE001
            fails.append(f"T deck-pdf-allow: push_deck_media(deck PDF only) raised {exc!r} "
                         "(a 25MB-capped deck must still host via its deck PDF)")
        finally:
            for k, v in saved.items():
                if v is None:
                    _os.environ.pop(k, None)
                else:
                    _os.environ[k] = v
        if out is not None:
            if not str(out.get("pptx_ghl_media_id") or "").strip():
                fails.append(f"T deck-pdf-allow: expected pptx_ghl_media_id from the deck "
                             f"PDF, got {out!r}")
            if out.get("deck_upload_kind") != "pdf":
                fails.append(f"T deck-pdf-allow: expected deck_upload_kind == 'pdf', "
                             f"got {out!r}")

    # U — a DECK PDF present alongside an actual PPTX must NOT be mislabeled: the pptx is
    # still the deck deliverable and deck_upload_kind stays absent (pptx path wins).
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        deck_pptx = delivery_gate._mk_full_run(base, with_text=False, task_ids=("kie-aaa",))
        delivery_gate._write_render_manifest(base, ["kie-aaa"])
        deck_pdf = base / "delivery" / "demo-deck-FINAL" / "demo-deck-FINAL.pdf"
        deck_pdf.write_bytes(b"%PDF-1.7\n" + b"\x00" * 128)  # real %PDF header (image-only)
        saved = {k: _os.environ.get(k) for k in ("GHL_API_KEY", "GHL_LOCATION_ID")}
        _os.environ["GHL_API_KEY"] = "pit-" + "a" * 40  # 40+ chars: not a doc placeholder
        _os.environ["GHL_LOCATION_ID"] = "loc-" + "a" * 40
        out = None
        try:
            out = push_deck_media(base, [], extra_files=[str(deck_pptx), str(deck_pdf)],
                                  opener=_mock_ghl_opener)
        except Exception as exc:  # noqa: BLE001
            fails.append(f"U pptx-wins: push_deck_media(pptx + deck pdf) raised {exc!r}")
        finally:
            for k, v in saved.items():
                if v is None:
                    _os.environ.pop(k, None)
                else:
                    _os.environ[k] = v
        if out is not None:
            if out.get("deck_upload_kind") is not None:
                fails.append(f"U pptx-wins: deck_upload_kind must stay absent when a pptx "
                             f"IS uploaded, got {out!r}")
            if str(out.get("pptx_ghl_media_id") or "") != "file_x":
                fails.append(f"U pptx-wins: expected pptx_ghl_media_id from the PPTX "
                             f"upload, got {out!r}")
            if out.get("deck_upload_receipt") is not None:
                fails.append(f"U pptx-wins: no over-cap receipt may exist on the canonical "
                             f"pptx path, got {out!r}")

    # === FIX 111 — THE STANDARD OVER-CAP RULE (MASTER Part 8 / R14 §5.10) ===
    # V — a 52 MB fixture pptx: the PDF twin is uploaded, the receipt carries
    # reason "over_cap" + pptx_media_id null, and the closeout gate is GREEN via the
    # accept-either-id reader.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        pkg = base / "delivery" / "demo-deck-FINAL"
        pkg.mkdir(parents=True, exist_ok=True)
        big_pptx = pkg / "demo-deck-FINAL.pptx"
        big_pptx.write_bytes(b"PK\x03\x04" + b"\x00" * (52 * 1024 * 1024))
        deck_pdf = pkg / "demo-deck-FINAL.pdf"
        deck_pdf.write_bytes(b"%PDF-1.7\n" + b"\x00" * 128)  # real %PDF header (image-only)
        (base / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
        (base / "working" / "checkpoints" / "process_manifest.json").write_text(json.dumps(
            {"phases": [{"phase": "render", "output_slide_count": 1,
                         "slides": [{"slide": 1, "taskId": "kie-aaa"}]}]}))
        (base / "working" / "checkpoints" / "delivery_plan.json").write_text(json.dumps(
            {"destinations": [{"type": "ghl", "status": "uploaded"},
                              {"type": "mac_downloads",
                               "verify_anchor": str(big_pptx)}]}))
        (base / "working" / "teleprompter").mkdir(parents=True, exist_ok=True)
        (base / "working" / "teleprompter" / "teleprompter.html").write_text("<html></html>")
        (pkg / "presenter-teleprompter.html").write_text("<html></html>")
        saved = {k: _os.environ.get(k) for k in ("GHL_API_KEY", "GHL_LOCATION_ID")}
        _os.environ["GHL_API_KEY"] = "pit-" + "a" * 40
        _os.environ["GHL_LOCATION_ID"] = "loc-" + "a" * 40
        out = None
        try:
            out = push_deck_media(base, [], extra_files=[str(big_pptx), str(deck_pdf)],
                                  opener=_mock_ghl_opener)
        except Exception as exc:  # noqa: BLE001
            fails.append(f"V over-cap-52MB: push_deck_media raised {exc!r}")
        finally:
            for k, v in saved.items():
                if v is None:
                    _os.environ.pop(k, None)
                else:
                    _os.environ[k] = v
        if out is None:
            fails.append("V over-cap-52MB: push_deck_media returned None")
        else:
            rec = out.get("deck_upload_receipt")
            if not ghl_media_upload.receipt_ok(rec):
                fails.append(f"V over-cap-52MB: expected a VALID over-cap receipt, got "
                             f"{rec!r}")
            else:
                if rec.get("reason") != "over_cap" or rec.get("pptx_media_id") is not None:
                    fails.append(f"V over-cap-52MB: receipt shape wrong, got {rec!r}")
                if not ghl_media_upload.is_over_cap(rec.get("pptx_local_path")):
                    fails.append(f"V over-cap-52MB: receipt pptx_local_path is not a real "
                                 f"over-cap file: {rec!r}")
            if out.get("deck_upload_kind") != "pdf":
                fails.append(f"V over-cap-52MB: expected deck_upload_kind 'pdf', got {out!r}")
            if str(out.get("pptx_ghl_media_id") or "") != "file_x":
                fails.append(f"V over-cap-52MB: expected the hosted id from the PDF twin "
                             f"upload, got {out!r}")
            # the persisted ledger must carry the receipt too (the gate reads the FILE).
            led = _read_json(_ledger_path(base))
            if not ghl_media_upload.receipt_ok(led.get("deck_upload_receipt")):
                fails.append(f"V over-cap-52MB: media_library.json did not persist the "
                             f"receipt, got {led.get('deck_upload_receipt')!r}")
            ok_g, r_g = gate_ghl_media_complete(base)
            if not ok_g:
                fails.append(f"V over-cap-52MB: closeout gate must be GREEN on the over-cap "
                             f"PDF twin, got {r_g}")

    # W — a deck hosted via the PDF twin WITHOUT a valid over-cap receipt (a bare
    # deck_upload_kind marker / legacy shape only) must FAIL the closeout gate: the
    # receipt is the reason carrier, and without it a human cannot tell "over the cap"
    # from "the pptx upload was lost".
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, intake={"has_ghl": True},
               media={"ghl_folder_id": "root",
                      "pptx_ghl_media_id": "pdf_legacy",
                      "deck_upload_kind": "pdf"})
        ok_g, r_g = gate_ghl_media_complete(base)
        if ok_g:
            fails.append("W no-receipt: closeout gate must FAIL on a pdf-hosted deck with "
                         "no valid over-cap receipt")
        elif not any("accept-either-id" in x for x in r_g):
            fails.append(f"W no-receipt: expected the FIX 111 accept-either-id reason, "
                         f"got {r_g}")

    # X — a 10 MB pptx uploads AS PPTX with a real media id (the canonical path), and
    # the closeout gate is green WITHOUT any receipt.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        deck_pptx = delivery_gate._mk_full_run(base, with_text=False, task_ids=("kie-aaa",))
        delivery_gate._write_render_manifest(base, ["kie-aaa"])
        saved = {k: _os.environ.get(k) for k in ("GHL_API_KEY", "GHL_LOCATION_ID")}
        _os.environ["GHL_API_KEY"] = "pit-" + "a" * 40
        _os.environ["GHL_LOCATION_ID"] = "loc-" + "a" * 40
        out = None
        try:
            out = push_deck_media(base, [], extra_files=[str(deck_pptx)],
                                  opener=_mock_ghl_opener)
        except Exception as exc:  # noqa: BLE001
            fails.append(f"X under-cap-10MB: push_deck_media raised {exc!r}")
        finally:
            for k, v in saved.items():
                if v is None:
                    _os.environ.pop(k, None)
                else:
                    _os.environ[k] = v
        if out is None:
            fails.append("X under-cap-10MB: push_deck_media returned None")
        else:
            if str(out.get("pptx_ghl_media_id") or "") != "file_x":
                fails.append(f"X under-cap-10MB: expected a real pptx media id, got {out!r}")
            if out.get("deck_upload_receipt") is not None:
                fails.append(f"X under-cap-10MB: an under-cap pptx must NOT carry an "
                             f"over-cap receipt, got {out!r}")
        ok_g, r_g = gate_ghl_media_complete(base)
        if not ok_g:
            fails.append(f"X under-cap-10MB: closeout gate must be GREEN on the canonical "
                         f"pptx path, got {r_g}")

    if fails:
        print("ghl_media_push gate selftest -> FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("ghl_media_push gate selftest -> PASS (24 cases: complete/empty/no-pptx/"
          "no-slides/null-folder/agent-skip/owner-skip/false-token/incomplete/coverage + "
          "transport-boundary: clean-allow/overlay-abort/no-run-dir-abort/non-deck-allow/"
          "push-aborts-pre-network + chokepoint: direct-overlay-BLOCKED/direct-no-run-dir-"
          "BLOCKED/governed-push-ALLOWED/image-unaffected + deck-pdf-fallback-ALLOWED/"
          "pptx-wins-over-deck-pdf + FIX-111: over-cap-52MB-receipt-green/no-receipt-FAILS/"
          "under-cap-10MB-pptx-canonical)")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(main())
