#!/usr/bin/env python3
"""Course asset normalizer/validator -- the KIE -> GHL course seam (WF12, A16).

KIE creates the image/video/audio file; GHL hosts the learning experience. This
module is the ONE place that turns a provider completion into a *validated*
course-asset manifest, and the ONE place that decides whether an asset is really
finished. It never generates media, never picks a model, never holds a GHL
credential, and never performs a network call.

Rules it enforces (Document 1 section 10.3/10.4, runbook WF12):

  * Stable logical keys. An asset is identified by
    ``course_key:module_key:lesson_key:role`` (``asset_key``), never by a display
    title or a provider id. Two lessons with the same title stay distinct.
  * A queued or running generation is NEVER completed. Only ``completed`` is
    completed, and even then only once real bytes are persisted on disk.
  * Hashes come from the ACTUAL file. ``sha256`` and ``byte_size`` are recomputed
    from the file named by ``local_path``; a provider task id or a URL is never
    treated as proof of bytes.
  * MIME is sniffed from the file's own magic bytes and must agree with the
    declared type. A ``.mp4`` name on an HTML error page is a failure.
  * Durable persistence. A temporary provider result URL (KIE ``tempfile*``
    hosts) is never a permanent course resource: such a manifest is invalid until
    a durable local copy exists.
  * Per-type required fields. An image is not asked for an invented audio
    duration; a video/audio asset must carry one.
  * Duplicate callbacks update ONE asset record. The store is keyed by
    ``asset_key``; a repeat of the same completion is a no-op, and a second,
    DIFFERENT result for the same key is a recorded conflict, never a silent
    overwrite (that is how a re-upload or a duplicate lesson gets created).

Out of scope by ownership: provider polling/callback transport (Skill 46 / Skill
74), model and prompt policy (Skills 66/67/68), GHL writes and binding execution
(WF08), and course delivery state (the course delivery reducer).

Runnable check (assert-based self-check, no network, no credentials):
    python3 shared-utils/ghl/course_assets.py
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import time
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

SCHEMA_VERSION = "1.0.0"

# A generation is finished only here. queued/running/submitted are explicitly not.
COMPLETED_STATE = "completed"
ACTIVE_STATES = ("queued", "running", "submitted", "validated")
TERMINAL_FAILURE_STATES = ("failed", "blocked")

ROLES = {
    "lesson_video": "video",
    "lesson_audio": "audio",
    "lesson_image": "image",
    "lesson_thumbnail": "image",
    "lesson_transcript": "text",
    "lesson_attachment": "document",
}

STORAGE_ACCESS = ("approved_for_destination", "private_destination", "not_set")

# KIE result hosts are TEMPORARY (20 minutes to 24 hours). Never a durable URL.
TEMP_PROVIDER_HOSTS = (
    "tempfile.aiquickdraw.com",
    "tempfileb.aiquickdraw.com",
    "tempfile.redpandaai.co",
    "static.aiquickdraw.com",
    "file.aiquickdraw.com",
)

# Magic-byte families. A declared MIME must agree with the sniffed family.
_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
    (b"ID3", "audio/mpeg"),
    (b"\xff\xfb", "audio/mpeg"),
    (b"OggS", "audio/ogg"),
    (b"fLaC", "audio/flac"),
    (b"RIFF", "riff"),  # WAV or WEBP -- disambiguated below
)
_MP4_BRANDS = (b"ftyp",)


class AssetError(Exception):
    """A manifest that must not reach GHL. ``code`` is stable and machine-readable."""

    def __init__(self, code: str, msg: str):
        super().__init__(msg)
        self.code = code
        self.msg = msg


# --------------------------------------------------------------- logical keys
def logical_asset_key(course_key: str, module_key: str, lesson_key: str, role: str) -> str:
    """``launch101:welcome:intro:video`` -- stable, order-bearing, never a title."""
    parts = [course_key, module_key, lesson_key, role]
    for name, value in zip(("course_key", "module_key", "lesson_key", "role"), parts):
        if not isinstance(value, str) or not value.strip():
            raise AssetError("bad_key", "%s is required and must be a non-empty string" % name)
        if ":" in value:
            raise AssetError("bad_key", "%s must not contain ':' (it is the key separator)" % name)
    return ":".join(p.strip() for p in parts)


def parse_asset_key(asset_key: str) -> Dict[str, str]:
    if not isinstance(asset_key, str):
        raise AssetError("bad_key", "asset_key must be a string")
    parts = asset_key.split(":")
    if len(parts) != 4 or not all(parts):
        raise AssetError("bad_key", "asset_key must be course:module:lesson:role, got %r" % (asset_key,))
    return dict(zip(("course_key", "module_key", "lesson_key", "role"), parts))


def modality_for_role(role: str) -> str:
    """Declared modality for a role, or ``other`` (never guessed from a file name)."""
    return ROLES.get(role, "other")


# ------------------------------------------------------------ bytes inspection
def sniff_mime(head: bytes) -> Optional[str]:
    """MIME family from the file's own magic bytes. ``None`` when unrecognized."""
    if not head:
        return None
    for magic, mime in _MAGIC:
        if head.startswith(magic):
            if mime == "riff":
                if head[8:12] == b"WEBP":
                    return "image/webp"
                if head[8:12] == b"WAVE":
                    return "audio/wav"
                return None
            return mime
    if len(head) >= 12 and head[4:8] in _MP4_BRANDS:
        # ISO base media: video unless the brand says audio-only.
        brand = head[8:12]
        return "audio/mp4" if brand in (b"M4A ", b"M4B ") else "video/mp4"
    if head.startswith(b"\x1aE\xdf\xa3"):
        return "video/webm"
    return None


def _family(mime: str) -> str:
    return (mime or "").split("/", 1)[0]


def file_facts(path: str) -> Dict[str, Any]:
    """Recompute sha256 / byte_size / sniffed mime from the ACTUAL file."""
    if not isinstance(path, str) or not path:
        raise AssetError("no_local_file", "local_path is required: a URL is not proof of bytes")
    real = os.path.realpath(path)
    if not (os.path.isfile(real) and os.access(real, os.R_OK)):
        raise AssetError("no_local_file", "not a readable regular file: %s" % path)
    digest = hashlib.sha256()
    size = 0
    head = b""
    with open(real, "rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            if len(head) < 32:
                head += chunk[: 32 - len(head)]
            digest.update(chunk)
            size += len(chunk)
    if size == 0:
        raise AssetError("empty_file", "file is 0 bytes: %s" % path)
    return {"sha256": digest.hexdigest(), "byte_size": size, "sniffed_mime": sniff_mime(head),
            "real_path": real}


# ------------------------------------------------------------------- manifests
def new_manifest(course_key: str, module_key: str, lesson_key: str, role: str,
                 provider: str = "kie", model_id: Optional[str] = None,
                 provider_task_id: Optional[str] = None) -> Dict[str, Any]:
    """A manifest in its pre-generation state. Nothing here claims completion."""
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "asset_key": logical_asset_key(course_key, module_key, lesson_key, role),
        "course_key": course_key,
        "module_key": module_key,
        "lesson_key": lesson_key,
        "role": role,
        "modality": modality_for_role(role),
        "provider": provider,
        "model_id": model_id,
        "provider_task_id": provider_task_id,
        "generation_state": "queued",
        "local_path": None,
        "sha256": None,
        "mime_type": None,
        "byte_size": None,
        "duration_seconds": None,
        "durable_url": None,
        "storage_access": "not_set",
        "qc": {"state": "not_run", "receipt_ref": None},
        "ghl_binding": {"state": "not_started", "content_id": None, "lesson_id": None},
        "manifest_revision": 1,
        "updated_at": None,
    }
    return manifest


def _required_for(role: str) -> Tuple[str, ...]:
    """Identity fields every manifest needs, whatever its state."""
    return ("asset_key", "course_key", "module_key", "lesson_key", "role", "provider", "generation_state")


def _bytes_required_for(role: str) -> Tuple[str, ...]:
    """Per-type byte fields, required only once the asset claims completion.

    An image is never asked for an invented audio duration; video and audio must
    carry one because a consumer cannot verify length from a hash.
    """
    common = ("local_path", "sha256", "mime_type", "byte_size")
    if modality_for_role(role) in ("video", "audio"):
        return common + ("duration_seconds",)
    return common


def _is_temp_provider_url(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
    except (ValueError, AttributeError):
        return False
    return any(host == h or host.endswith("." + h) for h in TEMP_PROVIDER_HOSTS)


def validate_manifest(manifest: Mapping[str, Any]) -> List[str]:
    """-> list of error strings. An empty list means the manifest may be handed to WF08."""
    errs: List[str] = []
    if not isinstance(manifest, Mapping):
        return ["manifest: not an object"]
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errs.append("schema_version: expected %s, got %r" % (SCHEMA_VERSION, manifest.get("schema_version")))

    role = manifest.get("role")
    if role not in ROLES:
        errs.append("role: unknown role %r (known: %s)" % (role, ", ".join(sorted(ROLES))))
        return errs

    # Keys must agree with each other: a manifest cannot be filed under one lesson
    # while carrying another lesson's key (that is how an asset lands on the wrong one).
    try:
        expected = logical_asset_key(manifest.get("course_key"), manifest.get("module_key"),
                                     manifest.get("lesson_key"), role)
    except AssetError as e:
        errs.append("asset_key: %s" % e.msg)
        expected = None
    if expected is not None and manifest.get("asset_key") != expected:
        errs.append("asset_key: %r does not match its own keys (%r)" % (manifest.get("asset_key"), expected))

    state = manifest.get("generation_state")
    if state not in (COMPLETED_STATE,) + ACTIVE_STATES + TERMINAL_FAILURE_STATES:
        errs.append("generation_state: unknown %r" % (state,))

    # Identity fields must carry a value in EVERY state: a manifest with no provider
    # cannot be resolved back to the generation that produced it.
    for field in _required_for(role):
        if manifest.get(field) in (None, ""):
            errs.append("%s: required" % field)

    if state != COMPLETED_STATE:
        # Nothing below applies yet; an in-flight asset is valid without bytes.
        return errs

    for field in _bytes_required_for(role):
        if manifest.get(field) in (None, ""):
            errs.append("%s: required once generation_state is %s (role %s)"
                        % (field, COMPLETED_STATE, role))

    mime = manifest.get("mime_type") or ""
    expected_family = modality_for_role(role)
    if expected_family in ("image", "video", "audio") and _family(mime) != expected_family:
        errs.append("mime_type: %r does not match the %s role" % (mime, expected_family))

    size = manifest.get("byte_size")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        errs.append("byte_size: must be a positive integer, got %r" % (size,))

    digest = manifest.get("sha256") or ""
    if not re.fullmatch(r"[0-9a-f]{64}", str(digest)):
        errs.append("sha256: must be 64 lowercase hex characters")

    modality = modality_for_role(role)
    if modality in ("video", "audio"):
        dur = manifest.get("duration_seconds")
        if not isinstance(dur, (int, float)) or isinstance(dur, bool) or dur <= 0:
            errs.append("duration_seconds: must be a positive number for a %s asset, got %r" % (modality, dur))

    url = manifest.get("durable_url")
    if url:
        if not re.match(r"^https://", str(url)):
            errs.append("durable_url: must be https")
        elif _is_temp_provider_url(str(url)):
            errs.append("durable_url: a temporary provider result URL is not durable; persist the bytes")
    elif manifest.get("storage_access") == "approved_for_destination":
        errs.append("durable_url: storage_access says approved_for_destination but no durable_url is set")

    if manifest.get("storage_access") not in STORAGE_ACCESS:
        errs.append("storage_access: %r not in %s" % (manifest.get("storage_access"), list(STORAGE_ACCESS)))

    qc = manifest.get("qc") or {}
    if qc.get("state") not in ("passed", "failed", "not_run"):
        errs.append("qc.state: %r not in passed/failed/not_run" % (qc.get("state"),))
    binding = manifest.get("ghl_binding") or {}
    if binding.get("state") not in ("not_started", "in_progress", "bound", "failed"):
        errs.append("ghl_binding.state: %r not in not_started/in_progress/bound/failed" % (binding.get("state"),))
    return errs


def assert_valid(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    """Raise ``AssetError('invalid_manifest')`` listing every error. Returns the manifest."""
    errs = validate_manifest(manifest)
    if errs:
        raise AssetError("invalid_manifest", "; ".join(errs))
    return manifest


# ------------------------------------------------------- completion -> manifest
def normalize_completion(manifest: Mapping[str, Any], *, local_path: Optional[str] = None,
                         durable_url: Optional[str] = None,
                         storage_access: Optional[str] = None,
                         duration_seconds: Optional[float] = None,
                         qc: Optional[Mapping[str, Any]] = None,
                         mime_type: Optional[str] = None) -> Dict[str, Any]:
    """Fold one provider completion into a copy of ``manifest`` and validate it.

    The file named by ``local_path`` (or already on the manifest) is the ONLY
    source of sha256 / byte_size / MIME. A caller-supplied ``mime_type`` must
    agree with the sniffed family, so a mislabeled download is caught here.
    Raises ``AssetError`` with ``invalid_manifest`` when the result may not reach GHL.
    """
    out = dict(manifest)
    out["local_path"] = local_path or out.get("local_path")
    if durable_url is not None:
        out["durable_url"] = durable_url
    if storage_access is not None:
        out["storage_access"] = storage_access
    if qc is not None:
        out["qc"] = dict(qc)

    facts = file_facts(out.get("local_path") or "")
    sniffed = facts["sniffed_mime"]
    declared = mime_type or out.get("mime_type") or (mimetypes.guess_type(facts["real_path"])[0] or None)
    if sniffed and declared and _family(sniffed) != _family(declared):
        raise AssetError("mime_mismatch",
                         "declared %r but the bytes are %r" % (declared, sniffed))
    out["mime_type"] = sniffed or declared
    if not out["mime_type"]:
        raise AssetError("unknown_mime", "cannot determine a MIME type from the bytes: %s" % out["local_path"])
    out["sha256"] = facts["sha256"]
    out["byte_size"] = facts["byte_size"]
    out["local_path"] = facts["real_path"]
    if duration_seconds is not None:
        out["duration_seconds"] = duration_seconds
    out["generation_state"] = COMPLETED_STATE
    out["updated_at"] = _now()

    errs = validate_manifest(out)
    if errs:
        raise AssetError("invalid_manifest", "; ".join(errs))
    return out


def record_failure(manifest: Mapping[str, Any], reason: str) -> Dict[str, Any]:
    """A failed generation. Never completed, never carries bytes."""
    out = dict(manifest)
    out["generation_state"] = "failed"
    out["failure_reason"] = str(reason or "unspecified")
    out["updated_at"] = _now()
    return out


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ------------------------------------------------------- Skill 74 / 46 adapters
def completion_from_adapter_result(result: Mapping[str, Any], manifest: Mapping[str, Any], *,
                                   local_path: Optional[str] = None,
                                   duration_seconds: Optional[float] = None) -> Dict[str, Any]:
    """Skill 74 result envelope -> manifest. Queued/running/timeout stay incomplete.

    ``save``d paths are the only accepted byte source; ``result_urls`` alone never
    completes an asset (they expire). A ``skipped`` result (adapter off or shadow)
    is a failure for the course seam: nothing was generated.
    """
    state = (result or {}).get("state")
    if state in ("skipped", "fail") or (result or {}).get("error"):
        return record_failure(manifest, "adapter %s: %s" % (state, (result or {}).get("error")))
    if state != "success":
        out = dict(manifest)
        out["generation_state"] = "running" if state in ("queued", "running") else "queued"
        out["provider_task_id"] = (result or {}).get("task_id") or out.get("provider_task_id")
        out["updated_at"] = _now()
        return out
    saved = [p for p in ((result or {}).get("saved_paths") or []) if isinstance(p, str) and p]
    path = local_path or (saved[0] if saved else None)
    if not path:
        raise AssetError("no_persisted_bytes",
                         "adapter reported success with no saved file; a result URL is not persistence")
    return normalize_completion(manifest, local_path=path, duration_seconds=duration_seconds)


def completion_from_callback_record(record: Mapping[str, Any], manifest: Mapping[str, Any], *,
                                    local_path: str, duration_seconds: Optional[float] = None) -> Dict[str, Any]:
    """Skill 46 callback / KV-read record -> manifest.

    Skill 46 is image/deck oriented: it proves a task finished and lists result
    URLs. It never proves the bytes are on disk, so a real ``local_path`` that the
    caller downloaded is still required for every modality. ``status`` must be
    ``done``; ``timeout``/``failed`` never complete an asset.
    """
    status = (record or {}).get("status")
    if status != "done":
        return record_failure(manifest, "callback record status %r" % (status,))
    if not (record or {}).get("resultUrls"):
        return record_failure(manifest, "callback record reported done with zero result URLs")
    if not local_path:
        raise AssetError("no_local_file", "the callback record lists URLs only; download the bytes first")
    return normalize_completion(manifest, local_path=local_path, duration_seconds=duration_seconds)


def bounded_poll(fetch_result: Callable[[], Mapping[str, Any]], manifest: Mapping[str, Any], *,
                 timeout_seconds: float = 300.0, interval_seconds: float = 3.0,
                 backoff: float = 1.5, max_interval_seconds: float = 15.0,
                 sleep: Callable[[float], None] = time.sleep,
                 now: Callable[[], float] = time.time) -> Dict[str, Any]:
    """Bounded polling completion hook for modalities Skill 46 cannot carry.

    ``fetch_result`` returns a Skill 74 result envelope (``wait``/``save`` output).
    Stops at ``timeout_seconds`` and returns a running manifest with the task id --
    a deadline is not a failure and never a completion. Provider/policy timing is
    the caller's: this only bounds the loop.
    """
    deadline = now() + float(timeout_seconds)
    delay = float(interval_seconds)
    last: Dict[str, Any] = dict(manifest)
    while True:
        result = fetch_result() or {}
        state = result.get("state")
        if state in ("skipped", "fail") or result.get("error"):
            return record_failure(manifest, "adapter %s: %s" % (state, result.get("error")))
        if state == "success":
            saved = [p for p in (result.get("saved_paths") or []) if isinstance(p, str) and p]
            if not saved:
                return record_failure(manifest, "success with no saved file after polling")
            return normalize_completion(manifest, local_path=saved[0])
        last = dict(manifest)
        last["generation_state"] = "running"
        last["provider_task_id"] = result.get("task_id") or last.get("provider_task_id")
        last["updated_at"] = _now()
        if now() + delay >= deadline:
            last["poll_deadline_reached"] = True
            return last
        sleep(delay)
        delay = min(delay * backoff, float(max_interval_seconds))


# -------------------------------------------------------------- duplicate guard
class AssetStore:
    """In-memory asset records keyed by ``asset_key`` (one record per asset).

    Duplicate callbacks and retries update ONE record. A repeat of the same
    completed bytes is a no-op (``duplicate=True``); a second, different result for
    a key that is already completed is recorded as a conflict and the original
    bytes are kept, so a re-upload or a duplicate lesson cannot be created from it.
    """

    def __init__(self) -> None:
        self.records: Dict[str, Dict[str, Any]] = {}

    def get(self, asset_key: str) -> Optional[Dict[str, Any]]:
        rec = self.records.get(asset_key)
        return json.loads(json.dumps(rec)) if rec is not None else None

    def apply(self, manifest: Mapping[str, Any]) -> Dict[str, Any]:
        """-> {"record", "changed", "duplicate", "conflict"}."""
        errs = validate_manifest(manifest)
        if errs:
            raise AssetError("invalid_manifest", "; ".join(errs))
        key = manifest["asset_key"]
        current = self.records.get(key)
        incoming = json.loads(json.dumps(dict(manifest)))
        if current is None:
            self.records[key] = incoming
            return {"record": self.get(key), "changed": True, "duplicate": False, "conflict": False}

        if current.get("generation_state") == COMPLETED_STATE and incoming.get("generation_state") == COMPLETED_STATE:
            if current.get("sha256") == incoming.get("sha256") and current.get("byte_size") == incoming.get("byte_size"):
                return {"record": self.get(key), "changed": False, "duplicate": True, "conflict": False}
            merged = dict(current)
            merged["conflict"] = {
                "at": _now(),
                "kept_sha256": current.get("sha256"),
                "rejected_sha256": incoming.get("sha256"),
                "reason": "second different completion for one asset_key",
            }
            merged["manifest_revision"] = int(current.get("manifest_revision") or 1)
            self.records[key] = merged
            return {"record": self.get(key), "changed": False, "duplicate": False, "conflict": True}

        if current.get("generation_state") == COMPLETED_STATE:
            # A late queued/failed callback never downgrades a completed asset.
            return {"record": self.get(key), "changed": False, "duplicate": True, "conflict": False}

        merged = dict(current)
        merged.update({k: v for k, v in incoming.items() if v is not None})
        merged["manifest_revision"] = int(current.get("manifest_revision") or 1) + 1
        self.records[key] = merged
        return {"record": self.get(key), "changed": True, "duplicate": False, "conflict": False}


# ------------------------------------------------------------------ WF08 handoff
def to_wf08_handoff(manifest: Mapping[str, Any]) -> Dict[str, Any]:
    """The course-media binding request. Refuses anything not completed and valid."""
    assert_valid(manifest)
    if manifest.get("generation_state") != COMPLETED_STATE:
        raise AssetError("not_completed", "generation_state is %r; only %r may be handed off"
                         % (manifest.get("generation_state"), COMPLETED_STATE))
    return {
        "schema_version": SCHEMA_VERSION,
        "asset_key": manifest["asset_key"],
        "course_key": manifest["course_key"],
        "module_key": manifest["module_key"],
        "lesson_key": manifest["lesson_key"],
        "role": manifest["role"],
        "modality": manifest.get("modality") or modality_for_role(manifest["role"]),
        "local_path": manifest["local_path"],
        "sha256": manifest["sha256"],
        "mime_type": manifest["mime_type"],
        "byte_size": manifest["byte_size"],
        "duration_seconds": manifest.get("duration_seconds"),
        "durable_url": manifest.get("durable_url"),
        "storage_access": manifest.get("storage_access"),
        "qc": dict(manifest.get("qc") or {}),
        "ghl_binding": dict(manifest.get("ghl_binding") or {}),
    }


def handoff_batch(manifests: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """All-or-nothing handoff: one invalid asset blocks the batch and names itself."""
    items, errors = [], []
    for m in manifests:
        try:
            items.append(to_wf08_handoff(m))
        except AssetError as e:
            errors.append({"asset_key": (m or {}).get("asset_key"), "code": e.code, "msg": e.msg})
    if errors:
        raise AssetError("invalid_batch", json.dumps(errors, sort_keys=True))
    return {"schema_version": SCHEMA_VERSION, "assets": items}


# ------------------------------------------------------------------- self-check
def _selfcheck() -> None:
    import tempfile

    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.png")
        with open(p, "wb") as f:
            f.write(png)

        m = new_manifest("launch-101", "welcome", "intro", "lesson_image")
        assert m["asset_key"] == "launch-101:welcome:intro:lesson_image"
        assert validate_manifest(m) == [], validate_manifest(m)  # queued is valid, incomplete
        assert m["generation_state"] == "queued"

        done = normalize_completion(m, local_path=p)
        assert done["generation_state"] == "completed"
        assert done["sha256"] == hashlib.sha256(png).hexdigest()
        assert done["byte_size"] == len(png) and done["mime_type"] == "image/png"

        # A video role without a duration is invalid; an image is never asked for one.
        v = new_manifest("c", "m", "l", "lesson_video")
        try:
            normalize_completion(v, local_path=p)
            raise AssertionError("a video asset must require duration_seconds")
        except AssetError as e:
            assert e.code == "invalid_manifest" and "duration_seconds" in e.msg, e.msg

        # Mislabeled bytes are refused.
        try:
            normalize_completion(m, local_path=p, mime_type="video/mp4")
            raise AssertionError("mime mismatch must be refused")
        except AssetError as e:
            assert e.code == "mime_mismatch", e.code

        # A temporary provider URL is not a durable URL.
        try:
            normalize_completion(m, local_path=p, durable_url="https://tempfile.aiquickdraw.com/x.png",
                                 storage_access="approved_for_destination")
            raise AssertionError("a temp provider URL must be refused as durable")
        except AssetError as e:
            assert e.code == "invalid_manifest" and "temporary provider" in e.msg, e.msg

        # Queued adapter output never completes; duplicate completion is a no-op.
        store = AssetStore()
        assert store.apply(m)["changed"] is True
        r1 = store.apply(done)
        assert r1["changed"] is True and r1["duplicate"] is False
        r2 = store.apply(done)
        assert r2["duplicate"] is True and r2["changed"] is False
        assert r2["record"]["sha256"] == done["sha256"]

        # A different completion for the same key is a conflict, not an overwrite.
        p2 = os.path.join(d, "b.png")
        with open(p2, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"1" * 64)
        other = normalize_completion(m, local_path=p2)
        r3 = store.apply(other)
        assert r3["conflict"] is True and r3["record"]["sha256"] == done["sha256"]

        # Handoff refuses an incomplete asset.
        try:
            to_wf08_handoff(m)
            raise AssertionError("a queued asset must not be handed to WF08")
        except AssetError as e:
            assert e.code == "not_completed", e.code
        assert to_wf08_handoff(done)["asset_key"] == done["asset_key"]

        # Skill 74: queued stays incomplete; success without saved bytes is refused.
        assert completion_from_adapter_result({"state": "queued", "task_id": "T1"}, m)["generation_state"] == "running"
        try:
            completion_from_adapter_result({"state": "success", "result_urls": ["https://x/a.png"]}, m)
            raise AssertionError("a URL is not persistence")
        except AssetError as e:
            assert e.code == "no_persisted_bytes", e.code
        assert completion_from_adapter_result({"state": "success", "saved_paths": [p]}, m)["sha256"] == done["sha256"]

        # Skill 46: a done record with no URLs never completes an asset.
        assert completion_from_callback_record({"status": "done", "resultUrls": []}, m, local_path=p)["generation_state"] == "failed"
        assert completion_from_callback_record({"status": "done", "resultUrls": ["https://x/a.png"]},
                                               m, local_path=p)["sha256"] == done["sha256"]

        # Bounded poll: a deadline returns running, never completed.
        ticks = iter([{"state": "running", "task_id": "T9"}] * 50)
        clock = {"t": 0.0}
        res = bounded_poll(lambda: next(ticks), m, timeout_seconds=10, interval_seconds=3,
                           sleep=lambda s: clock.__setitem__("t", clock["t"] + s),
                           now=lambda: clock["t"])
        assert res["generation_state"] == "running" and res["poll_deadline_reached"] is True

    print("course_assets self-check: PASS")


if __name__ == "__main__":
    _selfcheck()
