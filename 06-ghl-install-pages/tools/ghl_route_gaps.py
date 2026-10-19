#!/usr/bin/env python3
"""ghl_route_gaps.py — every Skill 06 raw-REST route that is NOT on the adapter.

Derived from source at ``origin/main`` (2026-10-19) against the frozen registry
``cli_anything/gohighlevel/public/operations.py``.  A caller is either routed
through ``ghl_public_client`` (the frozen ``PublicGhlAdapter``) or listed here
with the exact call site and the reason no supported operation fits.

The negative-control test (``tests/test_ghl_public_routes.py``) scans the five
caller files for raw-REST markers and fails when a marker is not covered by an
entry below.  Adding a raw call therefore requires declaring it — silence is not
a route.

``line`` is the line at the revision this table was derived from; ``anchor`` is
the stable substring the test matches instead of the number.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

# Files owned by this unit. Relative to the Skill 06 root.
CALLER_FILES = (
    "tools/ghl_media.py",
    "tools/ghl_object_router.py",
    "tools/ghl_rest_canvas.py",
    "tools/ghl_funnels_read.py",
    "tools/ghl_survey_rest.py",
)

# Raw-REST markers the negative control treats as a route. The client module is
# the one permitted owner of the transport seam and is excluded.
RAW_MARKERS = (
    "urllib.request.Request(",
    "urllib.request.urlopen(",
    "urlopen(req",
    "leadconnectorhq.com",
)

_JSON_ONLY = (
    "PublicGhlAdapter carries JSON bodies only "
    "(public/transport.py:112 json.dumps); it cannot encode the documented "
    "multipart/form-data file body"
)
_NO_READBACK = (
    "the row declares no readback plan (operations.py:591-596, final None) and "
    "no evidenced readback filter exists, while every write refuses without a "
    "non-vacuous caller ReadbackSpec (public/adapter.py:418-458)"
)


def _gap(
    file: str,
    line: int,
    anchor: str,
    route: str,
    reason: str,
    *,
    operation_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "file": file,
        "line": line,
        "anchor": anchor,
        "route": route,
        "operation_id": operation_id,
        "reason": reason,
    }


NAMED_GAPS: List[Dict[str, Any]] = [
    # ── ghl_media.py ────────────────────────────────────────────────────────
    _gap(
        "tools/ghl_media.py",
        860,
        'body, content_type = _multipart_encode(fields, "file", png_path)',
        "POST /medias/upload-file (multipart)",
        "media upload is a registered write (`media.upload`) but no supported "
        "adapter route fits: " + _JSON_ONLY + "; and " + _NO_READBACK + ".",
        operation_id="media.upload",
    ),
    _gap(
        "tools/ghl_media.py",
        1082,
        'body = json.dumps(payload).encode("utf-8")',
        "POST /medias/folder (JSON)",
        "folder create is a registered write (`media.folders.create`) but no "
        "supported adapter route fits: " + _NO_READBACK + ".",
        operation_id="media.folders.create",
    ),
    # ── ghl_funnels_read.py ─────────────────────────────────────────────────
    _gap(
        "tools/ghl_funnels_read.py",
        145,
        "FUNNEL_LIST_PATH",
        "GET /funnels/funnel/list",
        "no registry row for this path. `funnels.list` is GET /funnels/ "
        "(operations.py:564-566) — a different route whose envelope/paging was "
        "never captured, so switching would replace a captured contract with an "
        "unverified one. Registered route recorded, not claimed.",
        operation_id="funnels.list",
    ),
    _gap(
        "tools/ghl_funnels_read.py",
        146,
        "PAGE_LIST_PATH",
        "GET /funnels/page",
        "no registry row for this path. `funnels.pages.list` is "
        "GET /funnels/{funnelId}/pages (operations.py:567-570) — a different "
        "route; the page-envelope key is UNVERIFIED in the capture, so the "
        "public row cannot be proven to carry the same rows.",
        operation_id="funnels.pages.list",
    ),
    _gap(
        "tools/ghl_funnels_read.py",
        258,
        "urllib.request.Request(url, method=\"GET\")",
        "the two funnel reads' transport",
        "direct urllib transport for the two no-row routes above; kept until a "
        "contract capture exists for the registered paths.",
    ),
    # ── ghl_survey_rest.py ──────────────────────────────────────────────────
    _gap(
        "tools/ghl_survey_rest.py",
        44,
        "SURVEY_BACKEND_ORIGIN",
        "GET backend.leadconnectorhq.com/surveys/{id} (token-id)",
        "internal SPA read; `surveys.get` is an internal skill06_authoring row "
        "with auth class firebase_internal and no public adapter route "
        "(operations.py:557-558).",
        operation_id="surveys.get",
    ),
    _gap(
        "tools/ghl_survey_rest.py",
        160,
        "def survey_save_route",
        "captured POST/PUT /surveys (SPA save)",
        "no public survey-build API exists; `surveys.write` is an undocumented "
        "skill06_authoring row with no path or auth class "
        "(operations.py:562-563). The route is capture-gated by design and "
        "cannot be a registry-driven adapter call.",
        operation_id="surveys.write",
    ),
    # ── ghl_rest_canvas.py (internal SPA authoring; in-browser eval) ────────
    _gap(
        "tools/ghl_rest_canvas.py",
        126,
        "base = f\"/funnels/page/{page_id}\"",
        "GET /funnels/page/{id}",
        "internal SPA route; `funnels.pages.get` is internal with path UNKNOWN "
        "(operations.py:582-583). No public adapter route exists.",
        operation_id="funnels.pages.get",
    ),
    _gap(
        "tools/ghl_rest_canvas.py",
        141,
        "/funnels/builder/autosave/",
        "POST /funnels/builder/autosave/{id}",
        "internal SPA route; `funnels.pages.autosave` is internal with path "
        "UNKNOWN (operations.py:584-585). No public adapter route exists.",
        operation_id="funnels.pages.autosave",
    ),
    _gap(
        "tools/ghl_rest_canvas.py",
        154,
        "/workflow/{location_id}/{workflow_id}",
        "GET /workflow/{loc}/{wf}?includeTriggers=true",
        "registered as `workflows.private.get` but the row is skill44_private "
        "(operations.py:714-716) and the call runs inside the browser with a "
        "Firebase token-id; the public adapter's location-PIT transport cannot "
        "carry it.",
        operation_id="workflows.private.get",
    ),
    _gap(
        "tools/ghl_rest_canvas.py",
        166,
        "/workflow/{location_id}/trigger/{trigger_id}",
        "PUT /workflow/{loc}/trigger/{id}",
        "the registry records only the FIRST call of the two-call trigger row "
        "(operations.py:723-726); the PUT rewire has no row. Skill 44 private "
        "rail.",
        operation_id="workflows.private.trigger.link",
    ),
    _gap(
        "tools/ghl_rest_canvas.py",
        193,
        "/funnels/funnel/create",
        "POST /funnels/funnel/create",
        "internal SPA route; `funnels.create` is internal with path /funnels/ "
        "and Firebase auth (operations.py:574-575) — not the called route.",
        operation_id="funnels.create",
    ),
    _gap(
        "tools/ghl_rest_canvas.py",
        206,
        "/funnels/funnel/create-step",
        "POST /funnels/funnel/create-step",
        "internal SPA route; `funnels.steps.create` is internal "
        "(operations.py:576-577) — not the called route.",
        operation_id="funnels.steps.create",
    ),
    _gap(
        "tools/ghl_rest_canvas.py",
        218,
        "/funnels/funnel/fetch/",
        "GET /funnels/funnel/fetch/{id}",
        "internal SPA route; `funnels.get` is internal with path "
        "/funnels/{funnelId} (operations.py:578-579) — not the called route.",
        operation_id="funnels.get",
    ),
    _gap(
        "tools/ghl_rest_canvas.py",
        228,
        "/funnels/page/list",
        "GET /funnels/page/list?funnelId=&locationId=",
        "internal SPA route; `funnels.pages.list_internal` is retired with path "
        "UNKNOWN (operations.py:586-587). The public `funnels.pages.list` row "
        "is a different path and does not carry this shape.",
        operation_id="funnels.pages.list_internal",
    ),
    _gap(
        "tools/ghl_rest_canvas.py",
        240,
        "/funnels/funnel/delete",
        "POST /funnels/funnel/delete",
        "internal SPA route; `funnels.delete` is internal (operations.py:580-581) "
        "— not the called route.",
        operation_id="funnels.delete",
    ),
]

# Routes this unit DID move onto the frozen adapter.
ROUTED_OPERATIONS = (
    "media.files.list",  # ghl_media.list_media -> ghl_public_client
    "surveys.list",      # ghl_survey_rest path contract -> ghl_public_client
)


def gaps_for(file: str) -> List[Dict[str, Any]]:
    return [gap for gap in NAMED_GAPS if gap["file"] == file]


def undeclared_raw_lines(root: str, allowed_lines) -> List[Dict[str, Any]]:
    """Every raw-REST marker line in the caller files that is not allowed.

    ``allowed_lines`` is the pinned set of stripped line texts the gap table
    documents; ``allowed_lines=None`` means nothing is allowed (the
    discriminating self-check).  The client module is deliberately NOT a
    caller file: it is the one permitted owner of the transport seam.
    """
    hits: List[Dict[str, Any]] = []
    for relative in CALLER_FILES:
        path = os.path.join(root, relative)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if any(marker in line for marker in RAW_MARKERS):
                    stripped = line.strip()
                    if allowed_lines is None or stripped not in allowed_lines:
                        hits.append(
                            {"file": relative, "line": number, "text": stripped}
                        )
    return hits


def missing_anchors(root: str) -> List[Dict[str, Any]]:
    """Gap entries whose declared anchor no longer exists in the file."""
    missing: List[Dict[str, Any]] = []
    for gap in NAMED_GAPS:
        path = os.path.join(root, gap["file"])
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            missing.append(gap)
            continue
        if gap["anchor"] not in text:
            missing.append(gap)
    return missing


__all__ = [
    "CALLER_FILES",
    "NAMED_GAPS",
    "RAW_MARKERS",
    "ROUTED_OPERATIONS",
    "gaps_for",
    "missing_anchors",
    "undeclared_raw_lines",
]
