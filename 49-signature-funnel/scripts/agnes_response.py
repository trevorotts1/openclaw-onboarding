#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agnes_response.py -- S49 dispatch-layer outcome/response handling for
the Skill 63 Agnes image adapter (A24 Leg 4, items G-07, G-13, G-14, G-15).

Authority: rooms/S63/work/a24-support/S71-S49-A24-DISPATCH-CONTRACT.md
sections 5.3, 5.5, 5.6, 9, 10.2 (G-07, G-13, G-14, G-15), 11.3, 11.4.

Transport success is raw bytes only. This module is the layer the
orchestrator (agnes_orchestrator.py) calls after transport returns a
SendResult, and the layer it consults when transport raises
AmbiguousOutcome. It performs, in order:

1. G-14: parse the HTTP 200 body as provider JSON, validate its shape,
   extract the image, persist the image bytes to the run's output path,
   and measure dimensions from the persisted bytes (stdlib PNG and
   JPEG header parsing). Only then is a receipt built, and it is built
   from the persisted file read back from disk, never from the raw
   transport envelope.
2. G-07: before any receipt is built, confirm the provider-actual
   model exposed in the response equals the resolved requested model.
   A difference stops the run and surfaces the mismatch in the run
   record. When the response exposes no actual-model evidence, the
   limitation is recorded in the run record and processing proceeds
   under that recorded limitation. This module never records a
   differing actual model in a receipt (the merged receipt builder
   cannot represent one) and never changes the receipt schema.
3. Receipt: built with the merged substrate's build_agnes_receipt()
   and checked with validate_receipt(); a ReceiptError stops the run.
   Agnes task_id stays exactly null; no KIE-named identifier field is
   added; a provider request ID is recorded only when the provider
   actually returned one, otherwise null. The evaluated policy
   citation is a required argument: this layer never falls back to
   the receipt builder's default policy ID.
4. G-13: a result store (a JSON index file in the run directory)
   keyed by the dispatch fingerprint. On AmbiguousOutcome the
   orchestrator consults check_existing_result() first. A completed
   stored result is returned as the dispatch outcome. A not-found
   result surfaces the duplicate-cost risk disclosure and requires a
   separate bounded resubmission decision. This module never
   resubmits anything, automatically or otherwise.
5. G-15: the dispatch layer's own reference-URL check. A reference
   URL must be https and must name a public host. This module was
   built under the reading that A24 requires public HTTPS for
   reference URLs (the dispatch contract states the item
   conditionally; the strict reading is built here and is flagged
   for SWARM at the Leg 4 check, per B-38 readiness Gap G-G).

Extraction points in the provider JSON (dispatch contract section
10.3 item 3 leaves these to this layer; they are fixed here):

- actual model evidence: the top-level "model" string of the
  response object; if absent, "model" inside data[0]; if both are
  absent, the response carries no actual-model evidence.
- provider request ID: the top-level "id" string of the response
  object; absent or empty means no request ID was returned (null).
- image URL: "url" inside data[0].
- base64 image: "b64_json" inside data[0] (standard base64).

This module performs no network I/O. For a URL-form image, the
caller injects fetcher(url) -> bytes (the orchestrator owns the
concrete sender/fetcher); without a fetcher a URL-form response is
an error here, never a silent placeholder.

The merged substrate (63-agnes-image/scripts/provider_receipt.py) is
located relative to this file inside the repository, or imported
directly when the caller already placed it on sys.path.
"""
from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import os
import struct
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse


def _load_provider_receipt():
    """Import the merged substrate's provider_receipt module."""
    try:
        import provider_receipt as module
        return module
    except ImportError:
        pass
    substrate = Path(__file__).resolve().parents[2] / "63-agnes-image" / "scripts"
    if (substrate / "provider_receipt.py").is_file():
        sys.path.insert(0, str(substrate))
        import provider_receipt as module
        return module
    raise ImportError(
        "provider_receipt.py (merged Skill 63 substrate) not found: expected "
        "it on sys.path or at 63-agnes-image/scripts/ relative to the repo root"
    )


provider_receipt = _load_provider_receipt()
build_agnes_receipt = provider_receipt.build_agnes_receipt
validate_receipt = provider_receipt.validate_receipt
ReceiptError = provider_receipt.ReceiptError


class ResponseProcessingError(ValueError):
    """The 200 body cannot be turned into a persisted, receipted result."""


class ActualModelMismatch(ResponseProcessingError):
    """G-07 stop: provider-actual model differs from the requested model."""

    def __init__(self, requested: str, actual: str, source_field: str):
        super().__init__(
            f"provider-actual model mismatch: requested {requested!r} but the "
            f"provider response reports {actual!r} (source: {source_field}); "
            "stopping before receipt construction"
        )
        self.requested = requested
        self.actual = actual
        self.source_field = source_field


class ReferenceUrlError(ValueError):
    """G-15 stop: a reference URL failed the dispatch-layer check, by name."""


RESULT_STORE_FILENAME = "agnes-result-store.json"
STORE_STATE_COMPLETED = "completed"

DUPLICATE_COST_RISK_DISCLOSURE = (
    "duplicate-cost risk: the earlier dispatch attempt timed out after "
    "submission, so the provider may already hold a result for this "
    "fingerprint and the account may already have incurred the charge; "
    "no completed result is recorded in this run's result store; any "
    "resubmission is a separate bounded decision and is never automatic"
)


# ---------------------------------------------------------------------------
# G-14: parse the provider body
# ---------------------------------------------------------------------------

@dataclass
class ParsedProviderResponse:
    """The dispatch-layer fields extracted from one provider 200 body.

    Extraction points (fixed by this layer; see module docstring):
    actual model from top-level "model", else data[0] "model";
    request ID from top-level "id"; image from data[0] "url" or
    data[0] "b64_json". Empty strings count as absent.
    """

    actual_model: Optional[str]
    actual_model_source: Optional[str]  # "response.model" | "response.data[0].model" | None
    request_id: Optional[str]
    image_url: Optional[str]
    image_b64: Optional[str]
    raw: dict = field(repr=False, default_factory=dict)


def _nonempty_str(value) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value
    return None


def parse_provider_body(body: bytes) -> ParsedProviderResponse:
    """Parse and shape-validate one HTTP 200 body from the provider.

    Raises ResponseProcessingError on non-JSON bytes, a non-object
    document, or a document whose "data" is not a non-empty list with
    an object first item carrying a usable image field.
    """
    if isinstance(body, (bytearray, memoryview)):
        body = bytes(body)
    if not isinstance(body, bytes):
        raise ResponseProcessingError(
            f"provider body must be bytes, got {type(body).__name__}"
        )
    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResponseProcessingError(
            f"provider body is not valid UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(document, dict):
        raise ResponseProcessingError("provider body is not a JSON object")
    items = document.get("data")
    if not isinstance(items, list) or not items:
        raise ResponseProcessingError(
            "provider body has no data[0] result (data missing, not a list, or empty)"
        )
    first = items[0]
    if not isinstance(first, dict):
        raise ResponseProcessingError("provider body data[0] is not an object")
    image_url = _nonempty_str(first.get("url"))
    image_b64 = _nonempty_str(first.get("b64_json"))
    if image_url is None and image_b64 is None:
        raise ResponseProcessingError(
            "provider body data[0] carries no usable image (url and b64_json both empty)"
        )
    actual_model = _nonempty_str(document.get("model"))
    actual_model_source = "response.model" if actual_model is not None else None
    if actual_model is None:
        actual_model = _nonempty_str(first.get("model"))
        if actual_model is not None:
            actual_model_source = "response.data[0].model"
    return ParsedProviderResponse(
        actual_model=actual_model,
        actual_model_source=actual_model_source,
        request_id=_nonempty_str(document.get("id")),
        image_url=image_url,
        image_b64=image_b64,
        raw=document,
    )


def extract_image_bytes(parsed: ParsedProviderResponse,
                        fetcher: Optional[Callable[[str], bytes]] = None) -> bytes:
    """Resolve a parsed response to image bytes.

    The base64 form is preferred. A base64 payload that fails to
    decode falls back to the URL form when one is present (mirroring
    the substrate's observed response contract). The URL form needs
    the caller-injected fetcher; this module does no network I/O.
    """
    if parsed.image_b64:
        try:
            raw = base64.b64decode(parsed.image_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            if not parsed.image_url:
                raise ResponseProcessingError(
                    f"b64_json did not decode and no url fallback exists: {exc}"
                ) from exc
        else:
            if raw:
                return raw
            if not parsed.image_url:
                raise ResponseProcessingError("b64_json decoded to zero bytes")
    if parsed.image_url:
        if fetcher is None:
            raise ResponseProcessingError(
                "response carries the image as a URL and no fetcher was "
                "injected; the response layer performs no network I/O itself"
            )
        raw = fetcher(parsed.image_url)
        if not raw:
            raise ResponseProcessingError("fetcher returned no bytes for the image URL")
        return bytes(raw)
    raise ResponseProcessingError("parsed response carries no image form to extract")


# ---------------------------------------------------------------------------
# G-14: measure dimensions from persisted bytes (stdlib PNG / JPEG headers)
# ---------------------------------------------------------------------------

def measure_image_dimensions(data: bytes) -> tuple[str, int, int]:
    """Return (media_type, width, height) parsed from real image headers.

    Supports PNG and JPEG, the formats this layer measures. Anything
    else (including text or HTML error pages) raises
    ResponseProcessingError: a non-image payload is never persisted
    or receipted as an image.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(data) < 24 or data[12:16] != b"IHDR":
            raise ResponseProcessingError("PNG signature present but IHDR missing or truncated")
        width, height = struct.unpack(">II", data[16:24])
        return "png", width, height
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg", *_jpeg_dimensions(data)
    if data.lstrip().lower().startswith((b"<!doctype", b"<html", b"{", b"[")):
        raise ResponseProcessingError("payload is text/HTML/JSON, not image bytes")
    raise ResponseProcessingError(
        "unrecognized image bytes (no PNG or JPEG signature); this layer "
        "measures PNG and JPEG only"
    )


def _jpeg_dimensions(data: bytes) -> tuple[int, int]:
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
            return width, height
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        if length < 2:
            break
        i += 2 + length
    raise ResponseProcessingError("JPEG SOF marker not found; cannot measure dimensions")


def persist_image_bytes(data: bytes, output_path) -> Path:
    """Validate bytes as a measurable image, then persist atomically.

    The bytes are measured before anything is written, written to a
    temp file in the destination directory, fsynced, and renamed over
    the destination, so a partial file never stands as the output.
    """
    measure_image_dimensions(data)  # refuse non-images before any write
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(dest.parent), prefix=dest.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return dest


# ---------------------------------------------------------------------------
# G-07: confirm the provider-actual model before any receipt
# ---------------------------------------------------------------------------

def _record(run_record: Optional[dict], event: dict) -> None:
    if run_record is not None:
        run_record.setdefault("response_events", []).append(event)


def confirm_actual_model(parsed: ParsedProviderResponse, requested_model_id: str,
                         run_record: Optional[dict] = None) -> str:
    """Confirm the provider-actual model equals the requested model.

    Returns "confirmed_equal" when response evidence names the same
    model. Returns "no_evidence_recorded" when the response exposes
    no actual-model evidence: the limitation is recorded in the run
    record and processing may proceed under it. Raises
    ActualModelMismatch on a differing actual model, after recording
    the mismatch in the run record; no receipt may be built then.
    """
    if parsed.actual_model is None:
        _record(run_record, {
            "event": "actual_model_evidence_absent",
            "limitation": (
                "the provider response exposed no actual-model evidence "
                "(no top-level model field and no data[0] model field); "
                "the receipt's model_actual is the builder's copy of the "
                "requested model, not independent proof"
            ),
            "requested_model": requested_model_id,
        })
        return "no_evidence_recorded"
    if parsed.actual_model != requested_model_id:
        _record(run_record, {
            "event": "actual_model_mismatch",
            "requested_model": requested_model_id,
            "actual_model": parsed.actual_model,
            "source_field": parsed.actual_model_source,
        })
        raise ActualModelMismatch(
            requested_model_id, parsed.actual_model, parsed.actual_model_source or "unknown"
        )
    _record(run_record, {
        "event": "actual_model_confirmed",
        "model": requested_model_id,
        "source_field": parsed.actual_model_source,
    })
    return "confirmed_equal"


# ---------------------------------------------------------------------------
# G-14 + section 9: build the receipt only from the persisted output
# ---------------------------------------------------------------------------

def build_receipt_from_persisted(*, output_path, model_id: str, prompt: str,
                                 prompt_policy_id: str,
                                 request_id: Optional[str] = None) -> dict:
    """Build and validate the Agnes receipt from the persisted file.

    The persisted file is read back from disk: if it is missing or is
    not a measurable image, receipt construction fails. Dimensions
    come from the persisted bytes. prompt_policy_id is required: the
    evaluated policy citation is passed explicitly, never defaulted.
    validate_receipt() runs before returning; ReceiptError stops.
    """
    path = Path(output_path)
    if not path.is_file():
        raise ResponseProcessingError(
            f"persisted output {str(path)!r} is missing; a receipt is built "
            "only from a persisted output"
        )
    output_bytes = path.read_bytes()
    _media_type, width, height = measure_image_dimensions(output_bytes)
    receipt = build_agnes_receipt(
        model_id=model_id,
        prompt=prompt,
        output_bytes=output_bytes,
        dimensions=f"{width}x{height}",
        output_path=str(path),
        request_id=request_id,
        prompt_policy_id=prompt_policy_id,
    )
    validate_receipt(receipt)
    return receipt


def process_success_body(body: bytes, *, requested_model_id: str, prompt: str,
                         prompt_policy_id: str, output_path,
                         run_dir=None, fingerprint: Optional[str] = None,
                         fetcher: Optional[Callable[[str], bytes]] = None,
                         run_record: Optional[dict] = None) -> dict:
    """Full response-layer path for one HTTP 200 SendResult body.

    Order (contract sections 3 steps 8-9, 9, 11.4): parse the body;
    confirm the provider-actual model (G-07); extract the image;
    persist it; measure the persisted bytes; build and validate the
    receipt from the persisted output. When both fingerprint and
    run_dir are supplied, the completed result is recorded in the
    run's result store (G-13) so a later AmbiguousOutcome for the
    same fingerprint resolves without resubmission.

    Returns a dict with keys: receipt, output_path, dimensions,
    media_type, actual_model_status ("confirmed_equal" or
    "no_evidence_recorded"), request_id (or None).
    """
    parsed = parse_provider_body(body)
    actual_model_status = confirm_actual_model(parsed, requested_model_id, run_record)
    image_bytes = extract_image_bytes(parsed, fetcher)
    dest = persist_image_bytes(image_bytes, output_path)
    receipt = build_receipt_from_persisted(
        output_path=dest,
        model_id=requested_model_id,
        prompt=prompt,
        prompt_policy_id=prompt_policy_id,
        request_id=parsed.request_id,
    )
    _record(run_record, {
        "event": "result_persisted_and_receipted",
        "output_path": str(dest),
        "dimensions": receipt["dimensions"],
        "actual_model_status": actual_model_status,
        "request_id": parsed.request_id,
    })
    if fingerprint is not None and run_dir is not None:
        record_completed_result(
            run_dir, fingerprint,
            output_path=str(dest), receipt=receipt,
            dimensions=receipt["dimensions"],
        )
    return {
        "receipt": receipt,
        "output_path": str(dest),
        "dimensions": receipt["dimensions"],
        "media_type": measure_image_dimensions(image_bytes)[0],
        "actual_model_status": actual_model_status,
        "request_id": parsed.request_id,
    }


# ---------------------------------------------------------------------------
# G-13: existing-result check before any resubmission
# ---------------------------------------------------------------------------

def result_store_path(run_dir) -> Path:
    return Path(run_dir) / RESULT_STORE_FILENAME


def load_result_store(run_dir) -> dict:
    """Load the run's result-store index; an absent store is empty."""
    path = result_store_path(run_dir)
    if not path.is_file():
        return {}
    try:
        store = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResponseProcessingError(
            f"result store {str(path)!r} is unreadable: {exc}"
        ) from exc
    if not isinstance(store, dict):
        raise ResponseProcessingError(f"result store {str(path)!r} is not a JSON object")
    return store


def record_completed_result(run_dir, fingerprint: str, *, output_path: str,
                            receipt: dict, dimensions: str) -> dict:
    """Record one completed dispatch outcome under its fingerprint.

    The entry carries the persisted output path, the receipt identity
    (result_sha256 plus the full receipt), the dimensions, and the
    completion state. The store write is atomic (temp + rename).
    """
    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)
    store = load_result_store(run_path)
    entry = {
        "state": STORE_STATE_COMPLETED,
        "fingerprint": fingerprint,
        "output_path": output_path,
        "dimensions": dimensions,
        "receipt_result_sha256": receipt.get("result_sha256"),
        "receipt": receipt,
    }
    store[fingerprint] = entry
    fd, tmp = tempfile.mkstemp(dir=str(run_path), prefix=RESULT_STORE_FILENAME + ".",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(store, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, result_store_path(run_path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return entry


def check_existing_result(run_dir, fingerprint: str) -> Optional[dict]:
    """Return the stored completed entry for a fingerprint, or None."""
    entry = load_result_store(run_dir).get(fingerprint)
    if isinstance(entry, dict) and entry.get("state") == STORE_STATE_COMPLETED:
        return entry
    return None


def resolve_ambiguous_outcome(run_dir, fingerprint: str,
                              run_record: Optional[dict] = None) -> dict:
    """The G-13 check the orchestrator runs on AmbiguousOutcome.

    Found: the stored completed result is the dispatch outcome and no
    resubmission happens. Not found: the duplicate-cost risk is
    disclosed and any resubmission is a separate bounded decision.
    This function never resubmits and never calls any sender.
    """
    entry = check_existing_result(run_dir, fingerprint)
    if entry is not None:
        _record(run_record, {
            "event": "ambiguous_outcome_existing_result_found",
            "fingerprint": fingerprint,
            "output_path": entry.get("output_path"),
        })
        return {
            "outcome": "existing_result",
            "fingerprint": fingerprint,
            "entry": entry,
            "resubmission": "not_performed",
        }
    _record(run_record, {
        "event": "ambiguous_outcome_no_existing_result",
        "fingerprint": fingerprint,
        "disclosure": DUPLICATE_COST_RISK_DISCLOSURE,
    })
    return {
        "outcome": "no_existing_result",
        "fingerprint": fingerprint,
        "duplicate_cost_risk": DUPLICATE_COST_RISK_DISCLOSURE,
        "resubmission": "separate_bounded_decision_required",
        "automatic_resubmission": False,
    }


# ---------------------------------------------------------------------------
# G-15: the dispatch layer's own public-HTTPS reference-URL check
# ---------------------------------------------------------------------------

def check_reference_url(url: str) -> str:
    """Require one reference URL to be https on a public host.

    Rejects by name: a non-https scheme (including plain http), a
    missing host, localhost (and any .localhost name), and IP
    literals that are loopback, private, link-local, multicast,
    reserved, or unspecified. A public hostname or a public IP
    literal passes and the URL is returned unchanged. Reachability
    is not probed; this layer performs no network I/O.
    """
    if not isinstance(url, str) or not url.strip():
        raise ReferenceUrlError("reference URL is empty or not a string")
    parts = urlparse(url.strip())
    if parts.scheme.lower() != "https":
        raise ReferenceUrlError(
            f"reference URL {url!r} rejected: scheme {parts.scheme!r} is not "
            "https; the dispatch layer requires public HTTPS reference URLs"
        )
    host = parts.hostname
    if not host:
        raise ReferenceUrlError(f"reference URL {url!r} rejected: no host named")
    host_lower = host.lower()
    if host_lower == "localhost" or host_lower.endswith(".localhost"):
        raise ReferenceUrlError(
            f"reference URL {url!r} rejected: host {host!r} is localhost, not a public host"
        )
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (
        ip.is_loopback or ip.is_private or ip.is_link_local
        or ip.is_multicast or ip.is_reserved or ip.is_unspecified
    ):
        raise ReferenceUrlError(
            f"reference URL {url!r} rejected: host {host!r} is a non-public "
            "IP literal (loopback/private/link-local/reserved range)"
        )
    return url


def check_reference_urls(urls) -> list[str]:
    """Apply check_reference_url to every reference URL, in order."""
    return [check_reference_url(url) for url in urls]
