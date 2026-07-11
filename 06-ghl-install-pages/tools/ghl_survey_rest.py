#!/usr/bin/env python3
"""ghl_survey_rest.py — CANVAS-FREE survey write lane (Skill 06, ``build_method='rest'``).

The survey builder's PRIMARY lane is the browser drag rail. This module is the
capture-gated FALLBACK: when a single smoke-test tile-drag on the survey canvas
walls, the build completes by composing the survey's ``formData`` and writing it
through the SPA's OWN internal save route — but ONLY after that route has been
RECORDED from the builder's own Save click.

⛔ ANTI-BLIND-POST INVARIANT (the whole reason this module is gated)
-------------------------------------------------------------------
There is NO public survey-build API. The save verb/origin/path is the SPA's
internal route and is app-version-coupled. This module therefore REFUSES to emit
a write whose target was guessed: ``survey_save_route`` derives the origin/path/
verb SOLELY from a capture receipt (``routing/survey-save-capture.json``, produced
by recording the builder's own Save request via CDP Network). No hardcoded save
endpoint exists anywhere in this file. If the receipt is absent/unparseable/does
not carry a real URL + method, ``require_capture`` / ``survey_save_route`` raise
``CaptureRequired`` and the rest lane HARD-STOPS. A build may never POST to an
assumed endpoint.

READ side is proven from disk (both reference surveys fetched via
``GET backend.leadconnectorhq.com/surveys/<id>`` with the owner ``token-id``
header). The WRITE side is unreceipted until the §6.1 capture runs — hence the
gate. Token staging + WAF-gated fetch execution REUSE ``ghl_rest_canvas`` verbatim
(JWT via python-written JS file → ``window.__VT``; never inlined in JS source).

Pure path/payload/JS builders + a semantic round-trip diff. NO network, NO browser
at import/selftest time.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

# Origins are documented for READ/LIST only. The SAVE origin is NEVER taken from a
# constant — it comes from the capture receipt (see survey_save_route).
SURVEY_BACKEND_ORIGIN = "https://backend.leadconnectorhq.com"      # GET <id> (owner token-id) — proven
SURVEY_SERVICES_ORIGIN = "https://services.leadconnectorhq.com"    # list GET (PIT + browser UA) — proven

# The capture receipt filename the builder writes and this lane gates on.
CAPTURE_RECEIPT_NAME = "survey-save-capture.json"


class CaptureRequired(RuntimeError):
    """The rest lane was asked to write without a real, parsed save-capture receipt.

    Raised whenever a save route / body would otherwise be emitted against an
    ASSUMED endpoint. This is the anti-blind-POST guarantee — record the builder's
    own Save request first (CDP ``capture-save``), persist it to
    ``routing/survey-save-capture.json``, THEN write."""


# ---------------------------------------------------------------------------
# Proven READ / LIST path builders
# ---------------------------------------------------------------------------

def survey_read_path(survey_id: str) -> str:
    """``GET backend.leadconnectorhq.com/surveys/<id>`` — proven with owner token-id."""
    if not survey_id or not str(survey_id).strip():
        raise ValueError("survey_id required")
    return f"/surveys/{str(survey_id).strip()}"


def survey_list_path(location_id: str, limit: int = 50) -> str:
    """``GET services.leadconnectorhq.com/surveys/?locationId=…&limit=…`` — proven
    with a LOCATION PIT + a real browser User-Agent (default urllib UA → CF 1010)."""
    if not location_id or not str(location_id).strip():
        raise ValueError("location_id required")
    return f"/surveys/?locationId={str(location_id).strip()}&limit={int(limit)}"


# ---------------------------------------------------------------------------
# CAPTURE GATE — the receipt is the only source of the save route
# ---------------------------------------------------------------------------

def _capture_receipt_path(evidence_root: str) -> str:
    return os.path.join(evidence_root, "routing", CAPTURE_RECEIPT_NAME)


def load_capture(path: str) -> Optional[dict]:
    """Load a save-capture receipt from disk. Returns the dict, or None if the file
    is absent/unreadable/not-JSON (never raises — the gate is ``require_capture``)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _extract_record(capture: dict) -> dict:
    """A receipt may be either the raw request dict ``{method,url,…}`` or a wrapper
    ``{save_request:{…}}`` / a ``requests`` list from the CDP recorder. Normalize to
    the single save-request record (the first POST/PUT/PATCH to a /surveys route)."""
    if not isinstance(capture, dict):
        return {}
    if capture.get("url") and capture.get("method"):
        return capture
    inner = capture.get("save_request")
    if isinstance(inner, dict) and inner.get("url"):
        return inner
    reqs = capture.get("requests") or capture.get("reqs")
    if isinstance(reqs, list):
        for r in reqs:
            if isinstance(r, dict) and "/surveys" in str(r.get("url", "")) \
                    and str(r.get("method", "")).upper() in ("POST", "PUT", "PATCH"):
                return r
    return {}


def require_capture(evidence_root_or_path: str) -> dict:
    """THE GATE. Return the normalized save-request record from the capture receipt,
    or raise ``CaptureRequired``. Accepts either an evidence-root dir (the receipt is
    resolved to ``<root>/routing/survey-save-capture.json``) or a direct file path.

    A receipt qualifies ONLY if it carries a real ``url`` containing ``/surveys`` and
    a write ``method`` (POST/PUT/PATCH). Anything short of that HARD-STOPS the rest
    lane — no assumed endpoint is ever accepted."""
    path = evidence_root_or_path
    if os.path.isdir(evidence_root_or_path):
        path = _capture_receipt_path(evidence_root_or_path)
    if not os.path.exists(path):
        raise CaptureRequired(
            f"no save-capture receipt at {path!r}: record the builder's OWN Save "
            "request (CDP capture-save) before the rest lane may write. NO blind POST.")
    capture = load_capture(path)
    if capture is None:
        raise CaptureRequired(f"save-capture receipt at {path!r} is missing/unparseable JSON")
    rec = _extract_record(capture)
    url = str(rec.get("url", "")).strip()
    method = str(rec.get("method", "")).strip().upper()
    if not url or "/surveys" not in url or method not in ("POST", "PUT", "PATCH"):
        raise CaptureRequired(
            f"save-capture receipt at {path!r} does not carry a real /surveys write "
            f"(url={url!r}, method={method!r}). Re-run capture-save. NO assumed endpoint.")
    return rec


def survey_save_route(capture: dict) -> Tuple[str, str, str]:
    """Derive ``(origin, path, verb)`` for the survey save from a CAPTURED request
    record ONLY. Never returns a hardcoded default — a capture without a real
    ``url``+``method`` raises ``CaptureRequired`` (anti-blind-POST)."""
    rec = _extract_record(capture) if capture is not None else {}
    url = str(rec.get("url", "")).strip()
    verb = str(rec.get("method", "")).strip().upper()
    if not url or "/surveys" not in url or verb not in ("POST", "PUT", "PATCH"):
        raise CaptureRequired(
            "survey_save_route refuses to derive a save endpoint without a captured "
            f"/surveys write request (got url={url!r}, method={verb!r}).")
    # Split the captured absolute URL into origin + path (keeps query if present).
    after_scheme = url.split("://", 1)
    scheme = after_scheme[0] if len(after_scheme) == 2 else "https"
    rest = after_scheme[1] if len(after_scheme) == 2 else url
    host, _, path_part = rest.partition("/")
    origin = f"{scheme}://{host}"
    path = "/" + path_part
    return origin, path, verb


# ---------------------------------------------------------------------------
# Body composer + fetch-JS emitters (write executes via ghl_rest_canvas)
# ---------------------------------------------------------------------------

def build_save_body(name: str, form_data: dict, capture: Optional[dict] = None) -> dict:
    """Compose the SPA save body ``{"name":…, "formData":…}`` (+ any EXTRA top-level
    keys the capture's recorded body shows the client sends, e.g. a client-stamped
    ``lastUpdatedAt``). Never invents keys the capture didn't demonstrate."""
    if not isinstance(form_data, dict):
        raise ValueError("form_data must be a dict")
    body: Dict[str, Any] = {"name": name, "formData": form_data}
    rec = _extract_record(capture) if isinstance(capture, dict) else {}
    posted = rec.get("postData")
    if isinstance(posted, str):
        try:
            posted = json.loads(posted)
        except ValueError:
            posted = None
    if isinstance(posted, dict):
        for k in posted:
            if k not in ("name", "formData") and k not in body:
                # mirror only the presence of the extra key; value comes from caller
                # state when known, else the captured scalar (server-stamped fields).
                body[k] = posted[k]
    return body


def save_survey_js(survey_id: str, body: dict, capture: dict,
                   token_global: str = "__VT") -> str:
    """Emit the in-browser WAF-gated write JS for the survey save.

    Origin/path/verb come from ``survey_save_route(capture)`` — a missing/blind
    capture raises ``CaptureRequired`` BEFORE any JS is produced. Reuses
    ``ghl_rest_canvas.build_fetch_js`` (staged ``window.<token_global>`` → token-id
    header, Cloudflare clearance, browser UA)."""
    import ghl_rest_canvas as rc  # local import keeps this module standalone-testable
    origin, path, verb = survey_save_route(capture)  # raises CaptureRequired if unproven
    # If the captured path already carries the id, don't double-append.
    if survey_id and survey_id not in path:
        path = path.rstrip("/") + "/" + str(survey_id).strip()
    return rc.build_fetch_js(verb, path, body=body, origin=origin, token_global=token_global)


def read_survey_js(survey_id: str, token_global: str = "__VT") -> str:
    """Emit the in-browser GET for read-back verification (proven backend route)."""
    import ghl_rest_canvas as rc
    return rc.build_fetch_js("GET", survey_read_path(survey_id),
                             origin=SURVEY_BACKEND_ORIGIN, token_global=token_global)


# ---------------------------------------------------------------------------
# Round-trip verification (semantic diff — the rest lane's proof of done)
# ---------------------------------------------------------------------------

def _slides_of(form_data: dict) -> List[dict]:
    fd = form_data.get("formData", form_data) if isinstance(form_data, dict) else {}
    sl = fd.get("slides") if isinstance(fd, dict) else None
    return sl if isinstance(sl, list) else []


def _conditional_logic_of(form_data: dict) -> List[dict]:
    fd = form_data.get("formData", form_data) if isinstance(form_data, dict) else {}
    form = fd.get("form") if isinstance(fd, dict) else None
    cl = form.get("conditionalLogic") if isinstance(form, dict) else None
    return cl if isinstance(cl, list) else []


def verify_roundtrip(expected: dict, got: dict) -> dict:
    """Semantic diff of an expected vs read-back survey. Compares slide COUNT, the
    slideName sequence, per-slide element count, and the conditionalLogic count
    (server-stamped fields ignored). Returns ``{ok, diffs:[…]}`` — any diff = the
    build FAILS (no false "done")."""
    diffs: List[str] = []
    exp_sl, got_sl = _slides_of(expected), _slides_of(got)
    if len(exp_sl) != len(got_sl):
        diffs.append(f"slide count {len(exp_sl)} != {len(got_sl)}")
    else:
        for i, (a, b) in enumerate(zip(exp_sl, got_sl)):
            an = a.get("slideName") or a.get("name") or ""
            bn = b.get("slideName") or b.get("name") or ""
            if an != bn:
                diffs.append(f"slide[{i}] name {an!r} != {bn!r}")
            al = len(a.get("slideData", []) if isinstance(a.get("slideData"), list) else [])
            bl = len(b.get("slideData", []) if isinstance(b.get("slideData"), list) else [])
            if al != bl:
                diffs.append(f"slide[{i}] element count {al} != {bl}")
    ec = len(_conditional_logic_of(expected))
    gc = len(_conditional_logic_of(got))
    if ec != gc:
        diffs.append(f"conditionalLogic count {ec} != {gc}")
    return {"ok": not diffs, "diffs": diffs}


# ---------------------------------------------------------------------------
# CLI / selftest — fully offline
# ---------------------------------------------------------------------------

def _selftest() -> int:  # noqa: C901
    import tempfile
    errors: List[str] = []

    # 1. read/list path shapes
    if survey_read_path("ExAPmAV3Llo0tREenfJy") != "/surveys/ExAPmAV3Llo0tREenfJy":
        errors.append("survey_read_path wrong")
    if survey_list_path("LOC", 25) != "/surveys/?locationId=LOC&limit=25":
        errors.append("survey_list_path wrong")

    # 2. survey_save_route derives origin/path/verb ONLY from a real capture
    cap = {"method": "POST",
           "url": "https://backend.leadconnectorhq.com/surveys/abc123?locationId=LOC"}
    origin, path, verb = survey_save_route(cap)
    if not (origin == "https://backend.leadconnectorhq.com"
            and path.startswith("/surveys/abc123") and verb == "POST"):
        errors.append(f"survey_save_route mis-derived: {(origin, path, verb)}")

    # 3. ANTI-BLIND-POST: no capture / empty / non-survey URL → CaptureRequired
    for bad in ({}, {"method": "POST"}, {"url": "https://x/other", "method": "POST"},
                {"url": "https://backend/surveys/x", "method": "GET"}):
        try:
            survey_save_route(bad)
            errors.append(f"survey_save_route must refuse a blind/guessed route: {bad}")
        except CaptureRequired:
            pass

    # 4. require_capture gate against the filesystem
    with tempfile.TemporaryDirectory() as tmp:
        routing = os.path.join(tmp, "routing")
        os.makedirs(routing)
        # (a) absent receipt
        try:
            require_capture(tmp)
            errors.append("require_capture must raise when receipt is absent")
        except CaptureRequired:
            pass
        # (b) unparseable receipt
        rp = os.path.join(routing, CAPTURE_RECEIPT_NAME)
        with open(rp, "w") as fh:
            fh.write("{not json")
        try:
            require_capture(tmp)
            errors.append("require_capture must raise on unparseable receipt")
        except CaptureRequired:
            pass
        # (c) receipt without a real /surveys write
        with open(rp, "w") as fh:
            json.dump({"method": "GET", "url": "https://x/surveys/1"}, fh)
        try:
            require_capture(tmp)
            errors.append("require_capture must raise when method is not a write")
        except CaptureRequired:
            pass
        # (d) a VALID captured write (dir + wrapper + requests-list forms all resolve)
        with open(rp, "w") as fh:
            json.dump({"requests": [
                {"method": "GET", "url": "https://x/surveys/?locationId=L"},
                {"method": "POST", "url": "https://backend.leadconnectorhq.com/surveys/abc",
                 "postData": json.dumps({"name": "N", "formData": {}, "lastUpdatedAt": 1})},
            ]}, fh)
        rec = require_capture(tmp)
        if rec.get("method") != "POST" or "/surveys/abc" not in rec.get("url", ""):
            errors.append("require_capture did not pick the POST /surveys write from a list")

        # 5. build_save_body mirrors extra captured top-level keys, keeps name/formData
        body = build_save_body("My Survey", {"slides": []}, capture=rec)
        if body["name"] != "My Survey" or "formData" not in body:
            errors.append("build_save_body base shape wrong")
        if "lastUpdatedAt" not in body:
            errors.append("build_save_body should mirror an extra captured top-level key")

        # 6. save_survey_js refuses without a valid capture (CaptureRequired before JS)
        try:
            save_survey_js("abc", body, {})
            errors.append("save_survey_js must refuse an empty capture")
        except CaptureRequired:
            pass

    # 7. verify_roundtrip catches a dropped logic rule + a slide-count drift
    exp = {"formData": {"slides": [{"slideName": "A", "slideData": [1, 2]},
                                   {"slideName": "B", "slideData": [3]}],
                        "form": {"conditionalLogic": [{"x": 1}, {"y": 2}]}}}
    got_ok = json.loads(json.dumps(exp))
    if not verify_roundtrip(exp, got_ok)["ok"]:
        errors.append("verify_roundtrip should pass identical surveys")
    got_bad = json.loads(json.dumps(exp))
    got_bad["formData"]["form"]["conditionalLogic"].pop()      # drop a rule
    vr = verify_roundtrip(exp, got_bad)
    if vr["ok"] or not any("conditionalLogic" in d for d in vr["diffs"]):
        errors.append("verify_roundtrip must catch a dropped logic rule")
    got_short = {"formData": {"slides": exp["formData"]["slides"][:1],
                              "form": {"conditionalLogic": [{"x": 1}, {"y": 2}]}}}
    if verify_roundtrip(exp, got_short)["ok"]:
        errors.append("verify_roundtrip must catch a slide-count drift")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        print(f"\n[selftest] FAIL — {len(errors)} error(s)")
        return 1
    print("[selftest] PASS — read/list paths + capture-gated save route (anti-blind-POST) "
          "+ body composer + roundtrip diff (no network / no browser)")
    return 0


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="ghl_survey_rest",
        description="Capture-gated canvas-free survey write lane (Skill 06). Offline.")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
