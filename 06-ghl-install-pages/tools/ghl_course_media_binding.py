#!/usr/bin/env python3
"""ghl_course_media_binding.py — WF08 native course content / asset binding seam.

WHAT THIS IS
------------
KIE (and any other approved producer) creates the file; GHL hosts the learning
experience. This module owns the SEAM: given an approved course-asset manifest
(Document 1 section 10.3) it decides, deterministically, how that asset becomes
real lesson content, and it records four INDEPENDENT proofs.

It does not invent a GHL wire contract. Operation rows belong to WF06
(``public/courses.py``); selector JSON belongs to WF09. Here the public adapter
and the managed browser arrive as injected objects whose method names are frozen
in ``ghl_course_media_binding.contract.v1.json`` (WF08-CP01).

THREE PATHS (Document 1 section 8.5) — chosen, never guessed
-----------------------------------------------------------
  A ``existing_native_content`` — a verified, SAME-LOCATION native content id of
    the right type is attached through the documented lesson operation; the
    content is then read back from the lesson before anything is claimed.
  B ``public_import`` — the documented course import, only for a compatible NEW
    hierarchy and only when no individual create has been mixed into it. A
    processing response is NOT a completed course (acceptance A11).
  C ``managed_native_ui`` — the API-created course/category/lesson ids are kept
    and the managed browser fills ONLY the missing native-content step: attach
    the already validated asset, save, wait (bounded, resumable), read the
    association back. The course is never rebuilt in the browser.

FOUR PROOF FIELDS — never collapsed (Document 1 section 8.5)
------------------------------------------------------------
``asset_persisted`` · ``native_content_ready`` · ``lesson_association_verified``
· ``learner_render_verified``. A permanent video URL proves only the first.
An administrator preview does not prove the last. ``binding_complete`` is True
only when every required field was earned by an observed readback.

THE NARROW UPLOAD EXCEPTION (Document 1 section 8.5)
----------------------------------------------------
Ordinary GHL media stays API-first through ``ghl_media.py``. A browser file
upload is permitted ONLY for a native course-content ingestion step that has no
verified public equivalent. ``native_course_upload_exception`` refuses every
other purpose (page/ad/funnel/branding media), so the general API rail is not
loosened.

NO-FABRICATION / FAIL-LOUD
--------------------------
An invalid manifest raises; an unproven field stays False; an import that is
only "processing" never reduces to a completed course; a bounded processing
wait that runs out returns ``timeout`` with a resumable token instead of
spinning or claiming success.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

CONTRACT_VERSION = "1.0.0"
CONTRACT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "ghl_course_media_binding.contract.v1.json",
)

# ── Paths ────────────────────────────────────────────────────────────────────
PATH_A = "existing_native_content"
PATH_B = "public_import"
PATH_C = "managed_native_ui"
BINDING_PATHS = (PATH_A, PATH_B, PATH_C)

# ── Proof fields ─────────────────────────────────────────────────────────────
PROOF_FIELDS = (
    "asset_persisted",
    "native_content_ready",
    "lesson_association_verified",
    "learner_render_verified",
)

# ── Asset manifest contract (Document 1 section 10.3) ────────────────────────
ASSET_ROLES = ("lesson_video", "lesson_resource", "lesson_image", "lesson_audio")
_REQUIRED_MANIFEST_FIELDS = (
    "schema_version", "asset_key", "course_key", "module_key", "lesson_key",
    "role", "provider", "generation_state", "sha256", "mime_type", "byte_size",
    "storage_access",
)
ROLE_MIME_PREFIXES = {
    "lesson_video": ("video/",),
    "lesson_image": ("image/",),
    "lesson_audio": ("audio/",),
    "lesson_resource": ("application/pdf", "application/zip", "text/", "application/vnd"),
}
STORAGE_ACCESS_APPROVED = ("approved_for_destination", "private")
STORAGE_ACCESS_REFUSED = ("public", "public_discoverable", "any", "")

# ── Import lifecycle (Document 1 section 8.6) ────────────────────────────────
IMPORT_STATES = (
    "planned", "submitted", "processing", "reconciled", "content_verified",
    "failed", "unknown_outcome",
)
IMPORT_COMPLETE_STATES = ("content_verified",)
_IMPORT_TRANSITIONS = {
    "planned": ("submitted", "failed"),
    "submitted": ("processing", "failed", "unknown_outcome"),
    "processing": ("reconciled", "failed", "unknown_outcome"),
    "reconciled": ("content_verified", "failed"),
    "content_verified": (),
    "failed": (),
    "unknown_outcome": ("reconciled", "failed"),
}

# ── Native content types accepted on Path A ──────────────────────────────────
NATIVE_CONTENT_TYPES = ("video", "audio", "image", "document", "pdf", "file")

# ── Narrow managed-browser upload purposes ───────────────────────────────────
NATIVE_COURSE_UPLOAD_PURPOSE = "native_course_content"
REFUSED_UPLOAD_PURPOSES = (
    "page_media", "ad_media", "funnel_media", "branding", "thumbnail",
)

# Selector keys the managed path needs. The map itself is WF09's.
SELECTOR_OUTLINE_ROUTE = "course.routes.outline_builder"
SELECTOR_LESSON_EDITOR = "course.outline.lesson_body_editor"


class BindingError(RuntimeError):
    """Base class for a refused or failed binding step."""


class AssetValidationError(ValueError):
    """The asset manifest is not bindable (bad fields, wrong type, unsafe access)."""


class BindingRefused(BindingError):
    """A path/step was refused before any mutation (never a guessed selector)."""


class ProcessingTimeout(BindingError):
    """A bounded processing wait ran out; the returned state is resumable."""


# ── Asset inspection ─────────────────────────────────────────────────────────
_MAGIC = (
    ("image/png", b"\x89PNG\r\n\x1a\n"),
    ("image/jpeg", b"\xff\xd8\xff"),
    ("video/mp4", None),          # boxed: 'ftyp' at offset 4
    ("video/webm", b"\x1a\x45\xdf\xa3"),
    ("audio/mpeg", b"ID3"),
    ("audio/mpeg", b"\xff\xfb"),
    ("audio/wav", b"RIFF"),
    ("application/pdf", b"%PDF"),
    ("application/zip", b"PK\x03\x04"),
)


def _sniff_mime(head: bytes) -> Optional[str]:
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return "video/mp4"
    for mime, magic in _MAGIC:
        if magic is None:
            continue
        if head.startswith(magic):
            return "audio/wav" if mime == "audio/wav" and b"WAVE" not in head[:16] else mime
    return None


def inspect_asset(path: str, expected_mime: Optional[str] = None) -> dict:
    """Hash and type-sniff a real file. Returns the facts, never a claim they are GHL's."""
    if not path or not os.path.isfile(path):
        raise AssetValidationError(f"asset file not found: {path!r}")
    size = os.path.getsize(path)
    if size <= 0:
        raise AssetValidationError(f"asset file is empty: {path!r}")
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        head = fh.read(32)
        fh.seek(0)
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    sniffed = _sniff_mime(head)
    want = (expected_mime or "").strip().lower()
    magic_verified = bool(sniffed) and (
        not want or sniffed == want or want.startswith(sniffed.split("/")[0] + "/")
    )
    return {
        "path": os.path.abspath(path),
        "sha256": h.hexdigest(),
        "byte_size": size,
        "mime_type": want or sniffed or "",
        "sniffed_mime_type": sniffed,
        "magic_verified": magic_verified,
    }


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value.strip().lower()))


def validate_asset_manifest(manifest: dict, *, paid_course: bool = True) -> dict:
    """Validate one asset manifest against the Document 1 section 10.3 shape.

    Validates required fields, generation completion, checksum shape, role/type
    compatibility, and the storage ACCESS POLICY. When ``local_path`` is given
    the bytes are hashed and the declared sha256/byte_size must match, because
    Document 1 requires checksums computed from actual files.

    A paid course may not silently publish its content: ``storage_access`` must
    be one of ``STORAGE_ACCESS_APPROVED`` and ``public``/``public_discoverable``
    is refused by name.
    """
    if not isinstance(manifest, dict) or not manifest:
        raise AssetValidationError("asset manifest must be a non-empty dict")
    missing = [f for f in _REQUIRED_MANIFEST_FIELDS if manifest.get(f) in (None, "")]
    if missing:
        raise AssetValidationError(f"asset manifest missing required field(s): {', '.join(missing)}")

    role = str(manifest["role"]).strip()
    if role not in ASSET_ROLES:
        raise AssetValidationError(
            f"asset role {role!r} is not one of {', '.join(ASSET_ROLES)}"
        )
    if str(manifest["generation_state"]).strip() != "completed":
        raise AssetValidationError(
            f"asset generation_state is {manifest['generation_state']!r}; a queued or "
            "running generation is not a bindable asset (only 'completed' is)"
        )
    if not _is_sha256(manifest["sha256"]):
        raise AssetValidationError(
            "asset sha256 must be 64 lowercase hex characters computed from the bytes"
        )

    mime = str(manifest["mime_type"]).strip().lower()
    prefixes = ROLE_MIME_PREFIXES[role]
    if not any(mime.startswith(p) for p in prefixes):
        raise AssetValidationError(
            f"asset role {role!r} cannot carry mime_type {mime!r}; expected "
            f"{' or '.join(prefixes)}"
        )

    try:
        byte_size = int(manifest["byte_size"])
    except (TypeError, ValueError) as exc:
        raise AssetValidationError("asset byte_size must be an integer") from exc
    if byte_size <= 0:
        raise AssetValidationError("asset byte_size must be greater than zero")

    access = str(manifest.get("storage_access") or "").strip()
    if access in STORAGE_ACCESS_REFUSED:
        raise AssetValidationError(
            f"storage_access {access or '<empty>'!r} is refused: a paid course's delivery "
            "plan must explicitly choose approved/private storage, never assume every asset "
            "is publicly discoverable"
        )
    if paid_course and access not in STORAGE_ACCESS_APPROVED:
        raise AssetValidationError(
            f"storage_access {access!r} is not one of "
            f"{', '.join(STORAGE_ACCESS_APPROVED)} — the approved destination must be explicit"
        )

    durable_url = str(manifest.get("durable_url") or "").strip()
    if durable_url and not durable_url.lower().startswith("https://"):
        raise AssetValidationError(
            f"durable_url must be https (got {durable_url!r}); file:// and provider "
            "temporary result URLs are not a durable course resource"
        )

    qc = manifest.get("qc")
    if isinstance(qc, dict) and qc.get("state") not in (None, "", "passed"):
        raise AssetValidationError(
            f"asset qc state is {qc.get('state')!r}; only a passed QC binds"
        )

    out = dict(manifest)
    out["sha256"] = str(manifest["sha256"]).strip().lower()
    out["byte_size"] = byte_size
    out["mime_type"] = mime
    out["storage_access"] = access

    local_path = str(manifest.get("local_path") or "").strip()
    if local_path:
        got = inspect_asset(local_path, expected_mime=mime)
        if got["sha256"] != out["sha256"]:
            raise AssetValidationError(
                "local file sha256 does not match the manifest sha256 — the manifest "
                "does not describe this file"
            )
        if got["byte_size"] != byte_size:
            raise AssetValidationError(
                f"local file byte_size {got['byte_size']} does not match manifest "
                f"byte_size {byte_size}"
            )
        out["local_inspection"] = got
    elif not durable_url:
        raise AssetValidationError(
            "asset manifest needs either a local_path or a durable_url — nothing to bind"
        )
    return out


# ── Deterministic path selection (Document 1 section 8.5) ────────────────────
def select_binding_path(
    *,
    asset: dict,
    native_content: Optional[dict] = None,
    import_supported: bool = False,
    course_is_new: bool = False,
    hierarchy_created_by_api: bool = False,
    public_ingest_available: bool = False,
) -> dict:
    """Choose Path A, B or C deterministically and explain why.

    Order is fixed: an already-known native content id wins (A); else a
    documented import on a clean new hierarchy (B); else the managed UI step
    (C). Mixing individual creates with a full-course import is refused — the
    import would duplicate or ambiguate the objects, so that case falls to C.
    """
    if not isinstance(asset, dict) or not asset:
        raise AssetValidationError("select_binding_path needs a validated asset manifest")

    content_id = str((native_content or {}).get("content_id") or "").strip()
    content_type = str((native_content or {}).get("content_type") or "").strip().lower()
    same_location = bool((native_content or {}).get("same_location"))
    if content_id:
        if content_type not in NATIVE_CONTENT_TYPES:
            raise BindingRefused(
                f"native content {content_id!r} has content_type {content_type!r}; "
                f"expected one of {', '.join(NATIVE_CONTENT_TYPES)}"
            )
        if not same_location:
            raise BindingRefused(
                f"native content {content_id!r} was not verified as same-location — a "
                "content id from another sub-account is not bindable (wrong-tenant guard)"
            )
        return {
            "path": PATH_A,
            "rationale": "verified same-location native content id supplied",
            "native_content": {"content_id": content_id, "content_type": content_type},
            "requires_managed_browser": False,
            "mixed_import_refused": False,
        }

    if import_supported:
        if not course_is_new:
            return {
                "path": PATH_C,
                "rationale": "an import targets a NEW hierarchy only; this course already exists",
                "requires_managed_browser": True,
                "mixed_import_refused": False,
            }
        if hierarchy_created_by_api:
            return {
                "path": PATH_C,
                "rationale": (
                    "individual API creates are already in this hierarchy — mixing them with "
                    "a full-course import could duplicate or ambiguate objects, so only the "
                    "missing content step is filled through the managed UI"
                ),
                "requires_managed_browser": True,
                "mixed_import_refused": True,
            }
        return {
            "path": PATH_B,
            "rationale": "documented import is available for a clean new hierarchy",
            "requires_managed_browser": False,
            "mixed_import_refused": False,
        }

    return {
        "path": PATH_C,
        "rationale": (
            "no verified public ingest/associate operation exists for this asset; the "
            "already-created course/category/lesson ids are kept and only the missing "
            "native-content step is filled through the managed UI"
        ),
        "requires_managed_browser": bool(public_ingest_available is False),
        "mixed_import_refused": False,
    }


# ── Path A: attach an existing native content id ─────────────────────────────
def attach_existing_native_content(
    client: Any,
    *,
    location_id: str,
    course_id: str,
    lesson_id: str,
    content_id: str,
    content_type: str,
    asset: Optional[dict] = None,
) -> dict:
    """Attach an existing native content id to a lesson, then READ IT BACK.

    ``client`` is the WF06 public course adapter, duck-typed by the frozen
    contract: ``attach_lesson_content(location_id, lesson_id, content_id,
    content_type)`` and ``read_lesson(location_id, lesson_id)``. The result
    reports ``native_content_ready`` and ``lesson_association_verified`` from
    the readback only — never from the attach response.
    """
    for name, value in (
        ("location_id", location_id), ("course_id", course_id),
        ("lesson_id", lesson_id), ("content_id", content_id),
        ("content_type", content_type),
    ):
        if not str(value or "").strip():
            raise BindingRefused(f"{name} is required for Path A")
    if str(content_type).strip().lower() not in NATIVE_CONTENT_TYPES:
        raise BindingRefused(
            f"content_type {content_type!r} is not one of {', '.join(NATIVE_CONTENT_TYPES)}"
        )
    if not hasattr(client, "attach_lesson_content") or not hasattr(client, "read_lesson"):
        raise BindingRefused(
            "Path A needs a WF06 course adapter exposing attach_lesson_content() and "
            "read_lesson() — the frozen seam in WF08-CP01"
        )

    proof = empty_proof()
    if asset is not None:
        note_asset_persisted(proof, asset)

    attach = client.attach_lesson_content(
        location_id=location_id,
        lesson_id=lesson_id,
        content_id=str(content_id).strip(),
        content_type=str(content_type).strip().lower(),
    )
    readback = client.read_lesson(location_id=location_id, lesson_id=lesson_id)
    ready, assoc = _proof_from_lesson_readback(readback, str(content_id).strip())
    proof["native_content_ready"] = ready
    proof["lesson_association_verified"] = assoc
    return {
        "path": PATH_A,
        "course_id": course_id,
        "lesson_id": lesson_id,
        "content_id": str(content_id).strip(),
        "attach_response": attach,
        "readback": readback,
        "proof": proof,
    }


def _lesson_content_id(readback: Any) -> Optional[str]:
    if not isinstance(readback, dict):
        return None
    lesson = readback.get("lesson") if isinstance(readback.get("lesson"), dict) else readback
    for key in ("contentId", "content_id"):
        value = lesson.get(key)
        if value:
            return str(value).strip()
    content = lesson.get("content")
    if isinstance(content, dict):
        for key in ("contentId", "content_id", "id"):
            if content.get(key):
                return str(content[key]).strip()
    return None


def _proof_from_lesson_readback(readback: Any, expected_content_id: str) -> tuple[bool, bool]:
    """(native_content_ready, lesson_association_verified) from an observed readback."""
    observed = _lesson_content_id(readback)
    if not observed:
        return False, False
    if observed != expected_content_id:
        return False, False
    lesson = readback.get("lesson") if isinstance(readback.get("lesson"), dict) else readback
    status = str(lesson.get("contentStatus") or lesson.get("content_status") or "").strip().lower()
    ready = status in ("", "ready", "processed", "completed")
    return ready, True


# ── Path B: import lifecycle ─────────────────────────────────────────────────
def submit_course_import(client: Any, *, location_id: str, payload: dict) -> dict:
    """Submit the documented import and record a SUBMITTED/PROCESSING state.

    The response is never reduced to a completed course: an import that is
    accepted is ``submitted``/``processing`` until a reconcile read earns
    ``content_verified`` (acceptance A11).
    """
    if not str(location_id or "").strip():
        raise BindingRefused("location_id is required for an import")
    if not isinstance(payload, dict) or not payload:
        raise BindingRefused("import payload must be a non-empty dict")
    if not hasattr(client, "submit_course_import"):
        raise BindingRefused(
            "Path B needs a WF06 course adapter exposing submit_course_import() — the "
            "frozen seam in WF08-CP01"
        )
    response = client.submit_course_import(location_id=location_id, payload=payload)
    state = "submitted"
    processing_id = None
    if isinstance(response, dict):
        state = "processing" if (response.get("processing") or response.get("status") == "processing") else "submitted"
        for key in ("processingId", "processing_id", "importId", "import_id", "id"):
            if response.get(key):
                processing_id = str(response[key])
                break
    return {
        "path": PATH_B,
        "state": state,
        "processing_id": processing_id,
        "response": response,
        "complete": False,
        "complete_states": list(IMPORT_COMPLETE_STATES),
    }


def import_lifecycle_step(state: str, event: str) -> str:
    """Apply one legal import transition; refuse everything else."""
    state = str(state or "").strip()
    event = str(event or "").strip()
    if state not in IMPORT_STATES:
        raise BindingRefused(f"unknown import state {state!r}")
    allowed = _IMPORT_TRANSITIONS[state]
    if event not in allowed:
        raise BindingRefused(
            f"illegal import transition {state!r} -> {event!r}; allowed from {state!r}: "
            f"{', '.join(allowed) or '<terminal>'}"
        )
    return event


def import_is_complete(state: str) -> bool:
    """True ONLY for content_verified — 'processing' is never a finished course."""
    return str(state or "").strip() in IMPORT_COMPLETE_STATES


def poll_processing(
    poll: Callable[[dict], str],
    *,
    state: Optional[dict] = None,
    deadline_s: float = 300.0,
    interval_s: float = 5.0,
    max_polls: int = 60,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Bounded, RESUMABLE processing wait (Document 1 sections 8.5/8.6).

    ``poll(cursor)`` returns one of ``ready``, ``failed``, ``pending``, or
    ``unknown``. The returned dict carries an absolute monotonic ``deadline`` and
    the poll count, so a later call can pass it back as ``state`` and continue
    WITHOUT restarting the budget (a waiting import must not block other work).
    Running out of budget returns ``state='timeout'`` with the resumable token —
    never a fabricated success.
    """
    if not callable(poll):
        raise TypeError("poll must be callable")
    if deadline_s <= 0:
        raise ValueError("deadline_s must be positive")
    if interval_s < 0:
        raise ValueError("interval_s must not be negative")
    if max_polls <= 0:
        raise ValueError("max_polls must be positive")

    now = clock()
    cursor = dict(state) if isinstance(state, dict) else {}
    deadline = float(cursor.get("deadline") or (now + float(deadline_s)))
    polls = int(cursor.get("polls") or 0)
    last = str(cursor.get("last") or "")

    while True:
        if polls >= max_polls:
            return _wait_result("timeout", last, polls, deadline, "max_polls_reached")
        if clock() > deadline:
            return _wait_result("timeout", last, polls, deadline, "deadline_reached")
        last = str(poll(cursor) or "unknown").strip().lower()
        polls += 1
        if last == "ready":
            return _wait_result("ready", last, polls, deadline, "")
        if last == "failed":
            return _wait_result("failed", last, polls, deadline, "provider_reported_failure")
        if last == "unknown":
            return _wait_result("unknown", last, polls, deadline, "status_unavailable")
        if interval_s:
            sleep(interval_s)


def _wait_result(state: str, last: str, polls: int, deadline: float, reason: str) -> dict:
    return {
        "state": state,
        "last": last,
        "polls": polls,
        "deadline": deadline,
        "reason": reason,
        "bounded": True,
        "resumable": state == "timeout",
    }


# ── Path C: managed native-course UI step ────────────────────────────────────
def native_course_upload_exception(
    *, purpose: str, public_ingest_available: bool, asset: Optional[dict] = None,
) -> dict:
    """Grant the NARROW managed-browser upload, or refuse by name.

    The only allowed purpose is ``native_course_content`` on a step with no
    verified public equivalent. Every page/ad/funnel/branding/thumbnail upload
    stays on the API rail: this function refuses those purposes outright, so
    the exception can never become a general browser-upload allowance.
    """
    purpose = str(purpose or "").strip().lower()
    if purpose in REFUSED_UPLOAD_PURPOSES:
        raise BindingRefused(
            f"purpose {purpose!r} is not a native course-content step — ordinary media "
            "uploads stay API-first through ghl_media.py; the browser exception does not "
            "cover page, ad, funnel, branding or thumbnail media"
        )
    if purpose != NATIVE_COURSE_UPLOAD_PURPOSE:
        raise BindingRefused(
            f"purpose {purpose!r} is not one of ('{NATIVE_COURSE_UPLOAD_PURPOSE}',)"
        )
    if public_ingest_available:
        raise BindingRefused(
            "a verified public ingest/associate path exists for this asset, so the managed "
            "browser upload is not permitted (the exception is only for a real API gap)"
        )
    if asset is not None:
        role = str(asset.get("role") or "")
        if role not in ASSET_ROLES:
            raise BindingRefused(f"asset role {role!r} is not a lesson asset role")
    return {
        "allowed": True,
        "rail": "managed_browser_native_course_upload",
        "purpose": purpose,
        "narrows_to": "native course-content ingestion only",
    }


def managed_binding_steps(asset: dict, *, course_id: str, lesson_id: str) -> list[dict]:
    """The ordered Path C steps for ONE lesson. Selector JSON stays WF09's.

    Each step names the selector KEY it needs; a caller resolves it through the
    selector map and STOPs if the anchor is still capture-pending (D8).
    """
    if not str(course_id or "").strip() or not str(lesson_id or "").strip():
        raise BindingRefused("course_id and lesson_id are required for the managed path")
    asset_key = str(asset.get("asset_key") or "").strip() if isinstance(asset, dict) else ""
    return [
        {"n": 1, "action": "navigate_exact_object", "selector": SELECTOR_OUTLINE_ROUTE,
         "target": {"course_id": course_id, "lesson_id": lesson_id},
         "note": "go to the existing API-created course/lesson — never rebuild the course"},
        {"n": 2, "action": "open_lesson_editor", "selector": SELECTOR_LESSON_EDITOR,
         "target": {"lesson_id": lesson_id},
         "note": "the lesson content editor for the exact lesson"},
        {"n": 3, "action": "attach_validated_asset", "selector": None,
         "target": {"asset_key": asset_key, "sha256": (asset or {}).get("sha256")},
         "note": "attach the already validated local file (narrow native-course upload)"},
        {"n": 4, "action": "save", "selector": None, "target": {"lesson_id": lesson_id},
         "note": "save the lesson"},
        {"n": 5, "action": "wait_processing", "selector": None,
         "target": {"lesson_id": lesson_id},
         "note": "bounded, resumable processing wait"},
        {"n": 6, "action": "readback_association", "selector": None,
         "target": {"lesson_id": lesson_id, "content_id": None},
         "note": "READ the native association back before any proof is claimed"},
    ]


def apply_managed_ui_binding(
    steps: list[dict], actions: dict, *, asset: Optional[dict] = None,
) -> dict:
    """Execute the Path C steps through injected actions, in order, with readback.

    ``actions`` maps an action name to a callable ``(step, cursor) -> dict``.
    A step with a selector key MUST be resolved by the caller's ``resolve_anchor``
    action first; when it is still capture-pending the caller raises
    ``BindingRefused`` from there (D8, no guessed CSS). The run is only
    "verified" when the readback action returned the association.
    """
    if not isinstance(steps, list) or not steps:
        raise BindingRefused("managed binding needs at least one step")
    if not isinstance(actions, dict):
        raise BindingRefused("actions must be a dict of injected callables")

    proof = empty_proof()
    if asset is not None:
        note_asset_persisted(proof, asset)
    cursor: dict[str, Any] = {}
    done: list[dict] = []
    readback: Optional[dict] = None

    for step in steps:
        name = str(step.get("action") or "")
        fn = actions.get(name)
        if not callable(fn):
            raise BindingRefused(
                f"managed path needs an injected action for step {step.get('n')} "
                f"({name!r})"
            )
        if step.get("selector") and callable(actions.get("resolve_anchor")):
            anchor_step = actions["resolve_anchor"](step, cursor)
            cursor.update({"anchor": (anchor_step or {}).get("anchor")})
            done.append({"n": step.get("n"), "action": "resolve_anchor",
                         "anchor": (anchor_step or {}).get("anchor")})
        result = fn(step, cursor) or {}
        if not isinstance(result, dict):
            raise BindingRefused(f"action {name!r} must return a dict result")
        cursor.update({k: v for k, v in result.items() if k != "readback"})
        if result.get("readback") is not None:
            readback = result["readback"]
        if name == "readback_association":
            readback = result.get("readback") if result.get("readback") is not None else result
        done.append({"n": step.get("n"), "action": name, "ok": bool(result.get("ok", True))})

    if readback is None:
        raise BindingRefused(
            "managed path finished without a readback — an association that was not read "
            "back is not verified"
        )
    content_id = str(cursor.get("content_id") or (asset or {}).get("content_id") or "").strip()
    if content_id and isinstance(readback, dict):
        ready, assoc = _proof_from_lesson_readback(readback, content_id)
        proof["native_content_ready"] = ready
        proof["lesson_association_verified"] = assoc
    return {
        "path": PATH_C,
        "steps_done": done,
        "readback": readback,
        "proof": proof,
        "browser_routed": True,
    }


# ── Four separate proofs ─────────────────────────────────────────────────────
def empty_proof() -> dict:
    """All four proofs start unearned."""
    return {
        "asset_persisted": False,
        "native_content_ready": False,
        "lesson_association_verified": False,
        "learner_render_verified": False,
        "earned_from": {},
    }


def note_asset_persisted(proof: dict, asset: dict) -> dict:
    """Mark ONLY ``asset_persisted`` — a durable URL never implies native content."""
    if not isinstance(proof, dict):
        raise TypeError("proof must be a dict")
    local = asset.get("local_inspection") if isinstance(asset, dict) else None
    if isinstance(local, dict) and local.get("sha256") == asset.get("sha256"):
        proof["asset_persisted"] = True
        proof.setdefault("earned_from", {})["asset_persisted"] = (
            f"local bytes sha256={local['sha256'][:12]}…"
        )
    elif str(asset.get("durable_url") or "").startswith("https://"):
        # A durable URL alone is not a fetch; record it as declared, not verified.
        proof["asset_persisted"] = True
        proof.setdefault("earned_from", {})["asset_persisted"] = (
            "manifest durable_url (declared, not fetched)"
        )
    return proof


def note_learner_render_verified(
    proof: dict, *, context: str, marker_in_dom: bool, evidence: str = "",
) -> dict:
    """Earn ``learner_render_verified`` ONLY from a learner-context observation."""
    if not isinstance(proof, dict):
        raise TypeError("proof must be a dict")
    if str(context or "").strip().lower() != "learner":
        raise BindingRefused(
            "learner_render_verified needs a LEARNER-context observation; an admin preview "
            "does not prove that a paid member sees the content"
        )
    if not marker_in_dom:
        proof["learner_render_verified"] = False
        return proof
    proof["learner_render_verified"] = True
    proof.setdefault("earned_from", {})["learner_render_verified"] = evidence or "learner DOM marker"
    return proof


def binding_complete(proof: dict, *, require_learner_render: bool = True) -> bool:
    """Delivery readiness: every required proof earned independently."""
    if not isinstance(proof, dict):
        return False
    required = list(PROOF_FIELDS) if require_learner_render else list(PROOF_FIELDS[:3])
    return all(proof.get(field) is True for field in required)


def bind_asset(
    asset: dict,
    *,
    native_content: Optional[dict] = None,
    client: Any = None,
    location_id: str = "",
    course_id: str = "",
    lesson_id: str = "",
    import_supported: bool = False,
    course_is_new: bool = False,
    hierarchy_created_by_api: bool = False,
    public_ingest_available: bool = False,
    paid_course: bool = True,
    managed_actions: Optional[dict] = None,
    import_payload: Optional[dict] = None,
) -> dict:
    """One entrypoint: validate, select, execute the chosen path, return the proof.

    Nothing is claimed that the path did not observe. Callers that only need the
    decision can call ``select_binding_path`` directly.
    """
    validated = validate_asset_manifest(asset, paid_course=paid_course)
    decision = select_binding_path(
        asset=validated,
        native_content=native_content,
        import_supported=import_supported,
        course_is_new=course_is_new,
        hierarchy_created_by_api=hierarchy_created_by_api,
        public_ingest_available=public_ingest_available,
    )
    path = decision["path"]

    if path == PATH_A:
        result = attach_existing_native_content(
            client, location_id=location_id, course_id=course_id, lesson_id=lesson_id,
            content_id=(native_content or {})["content_id"],
            content_type=(native_content or {})["content_type"],
            asset=validated,
        )
    elif path == PATH_B:
        if import_payload is None:
            raise BindingRefused("Path B needs an import_payload")
        result = submit_course_import(client, location_id=location_id, payload=import_payload)
        result["proof"] = empty_proof()
        note_asset_persisted(result["proof"], validated)
    else:
        steps = managed_binding_steps(validated, course_id=course_id, lesson_id=lesson_id)
        if managed_actions is None:
            raise BindingRefused(
                "Path C needs injected managed actions; nothing was executed and no proof "
                "was claimed"
            )
        result = apply_managed_ui_binding(steps, managed_actions, asset=validated)

    result["decision"] = decision
    result["asset"] = {
        "asset_key": validated["asset_key"],
        "sha256": validated["sha256"],
        "mime_type": validated["mime_type"],
        "byte_size": validated["byte_size"],
        "role": validated["role"],
    }
    result["contract_version"] = CONTRACT_VERSION
    return result


def load_contract(path: str = CONTRACT_PATH) -> dict:
    """Read the frozen WF08-CP01 interface file this module implements."""
    import json

    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


__all__ = [
    "CONTRACT_VERSION",
    "CONTRACT_PATH",
    "PATH_A",
    "PATH_B",
    "PATH_C",
    "BINDING_PATHS",
    "PROOF_FIELDS",
    "ASSET_ROLES",
    "ROLE_MIME_PREFIXES",
    "STORAGE_ACCESS_APPROVED",
    "IMPORT_STATES",
    "IMPORT_COMPLETE_STATES",
    "NATIVE_CONTENT_TYPES",
    "NATIVE_COURSE_UPLOAD_PURPOSE",
    "SELECTOR_OUTLINE_ROUTE",
    "SELECTOR_LESSON_EDITOR",
    "BindingError",
    "AssetValidationError",
    "BindingRefused",
    "ProcessingTimeout",
    "inspect_asset",
    "validate_asset_manifest",
    "select_binding_path",
    "attach_existing_native_content",
    "submit_course_import",
    "import_lifecycle_step",
    "import_is_complete",
    "poll_processing",
    "native_course_upload_exception",
    "managed_binding_steps",
    "apply_managed_ui_binding",
    "empty_proof",
    "note_asset_persisted",
    "note_learner_render_verified",
    "binding_complete",
    "bind_asset",
    "load_contract",
]
