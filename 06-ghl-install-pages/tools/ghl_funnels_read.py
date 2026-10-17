#!/usr/bin/env python3
"""ghl_funnels_read.py: S06-07, the SUPPORTED PUBLIC funnel/page inventory
reads for Skill 06 (doc 19 W3 correction), with fail-closed pagination.

WHAT THIS IS
------------
The public read transport + paginated listers behind the two dependency-
injection seams `ghl_inventory.enumerate_zhc_inventory` already exposes
(`funnel_lister(location_id)` / `page_lister(funnel_id, location_id)`).
Packet doc 19 (W3) corrects the old blanket claim: the official GoHighLevel
public API DOES document funnel/page READ endpoints. This module implements
exactly those two reads and nothing else:

  * ``GET /funnels/funnel/list``  (locationId required; offset/limit paging)
  * ``GET /funnels/page``         (locationId + funnelId required;
                                   limit/offset required)

READS ONLY. No public WRITE API for funnels/pages is documented by W3 and
none is claimed or extrapolated here: funnel/page CREATE stays on the
internal canvas / browser rails (see `ghl_rest_canvas.py`, labeled internal
there and everywhere).

CONTRACT PROVENANCE (step-1 capture, S06-07)
--------------------------------------------
The contract below comes from the public documentation capture recorded at
evidence/S06-07/S06-07-step1-public-contract-capture.md (the two primary
sources doc 19 W3 names), NEVER from the internal XHR's shape (prep
correction D1). The internal funnel-list XHR documented in
`tools/SELECTORS-LIVE-funnel.md` section A (backend origin, token-id auth,
in-browser) is a different surface; where the two families happen to agree
(path, offset/limit parameter names), the public capture is the authority.

Settled by the capture:
  * funnel list: params locationId (required), type, category, offset,
    limit, parentId, name; response envelope {funnels, count, traceId},
    all required. `count` is treated as the reported total for the
    completeness gate (see below; if that reading is ever wrong against a
    live account, the gate fails LOUD, never silently partial).
  * page list: params locationId + funnelId (both required), limit +
    offset (both required), name optional; documented item fields _id,
    locationId, funnelId, name, stepId, deleted, updatedAt.

UNVERIFIED (designed fail-closed around, never fabricated):
  * the funnels-family `Version` header value. The only version datum the
    primary sources attach to this endpoint family is the documentation
    version label 2023-02-21 on the versioned pages doc; GHL_FUNNELS_VERSION
    carries that value and is labeled live-UNVERIFIED. It is NOT the
    internal SPA static version (2021-07-28, `ghl_rest_canvas.SPA_VERSION`)
    and NOT the media family's version (`ghl_media.GHL_MEDIA_VERSION`,
    also 2021-07-28): reusing either would be the NQ4 conflation trap.
  * the required Private Integration Token scope name (not stated in the
    capture). This module uses the LOCATION PIT through the tree's shared
    resolver; a 403 surfaces as a token-context diagnosis (router F9),
    never as a guessed scope claim.
  * the `limit` page-size ceiling (not stated). DEFAULT_LIMIT is a named
    design parameter, not a contract claim.
  * funnel item field names (the envelope schema does not expand them).
    Rows are parsed tolerantly (id from `id` or `_id`, name from `name`)
    and no item field is ever invented.
  * the pages envelope key and any total field (not stated). Extraction
    accepts the tree's established candidate keys and raises on an
    unrecognized shape; with no documented total, the completeness proof
    for pages is the short-page end-of-pages signal plus the max-pages
    cap (the proof used, recorded here per the build checklist).
  * the page `status` vocabulary (no status field is documented). The
    mapping in `normalize_page_row` is explicit: draft/published pass
    through (case-insensitive), an absent status stays absent, and any
    other non-empty value RAISES rather than being silently coerced by
    the enumeration layer's fallback (Q7).
  * the build `marker` (not provided by the captured contract, Q4). Rows
    arrive marker-less; the consequence is that marker-keyed DUPLICATE
    detection in `ghl_inventory` can never fire on public-read rows.
    Nothing is fabricated to fill the gap. Likewise `created`: an
    `updatedAt` value is never substituted for a creation time.

AUTH / TRANSPORT (the tree's proven pattern, consumed not re-implemented)
-------------------------------------------------------------------------
Bare Python against the services origin (NOT Cloudflare-WAF-gated for
Bearer-PIT reads), exactly the `ghl_media.py` shape:
`Authorization: Bearer <LOCATION PIT>` + `Version` header + a real browser
User-Agent (services.* rejects the default Python UA; router doctrine F4),
with an injectable `opener` so tests never touch the network. The PIT and
the location id are resolved ONLY through `ghl_media.resolve_location_pit`
/ `resolve_location_id`, which delegate to the ONE shared resolver
(`ghl_secret_resolver`, S06-04): *_FILE indirection first, then the live
env alias chain, then the canonical stores, placeholders skipped, broken
*_FILE failing loud. This module re-implements none of that (delta-check
C4). No credential value is ever printed, logged, or placed in an error
message; errors name variables, paths, statuses, and shapes only.

FAIL-CLOSED PAGINATION (the ghl_bulk_workflow_enroll discipline)
----------------------------------------------------------------
  * Pages are collected in order and de-duplicated by row id.
  * A reported total (funnels `count`) must EQUAL the collected unique
    count at the end, or the read raises `IncompleteInventoryError`.
  * A page endpoint with no documented total terminates on a SHORT page
    (fewer rows than the requested limit); a run that never terminates
    hits the max-pages cap and raises.
  * An empty page while a reported total is still unmet raises.
  * A malformed page payload (non-JSON, unrecognized envelope, non-object
    row) raises. A partial inventory is NEVER returned as complete.

LIVE STATUS: LIVE_PROOF_PENDING. No approved test location exists for
these reads; everything here is proven against injected fixtures only.
The S79 sandbox test-payment ruling covers A08/A09 payment cases only and
authorizes nothing for this module's live legs.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import ghl_media  # noqa: E402  (services origin + the shared-resolver PIT/location entry points)

# ── Constants ────────────────────────────────────────────────────────────────

# The services origin is ghl_media's constant, imported so the public-API
# origin exists exactly once in the tree.
GHL_SERVICES_ORIGIN = ghl_media.GHL_SERVICES_ORIGIN

# The funnels-family Version header value, sourced from the versioned
# public documentation page for GET /funnels/page (docs label 2023-02-21;
# see the step-1 capture). Live-UNVERIFIED. Deliberately NOT
# ghl_rest_canvas.SPA_VERSION and NOT ghl_media.GHL_MEDIA_VERSION (both
# 2021-07-28, different families; NQ4).
GHL_FUNNELS_VERSION = "2023-02-21"

FUNNEL_LIST_PATH = "/funnels/funnel/list"
PAGE_LIST_PATH = "/funnels/page"

# Design parameters, NOT contract claims (the capture states no ceiling):
# rows requested per page, and the runaway cap on pages per read (the
# bulk-enroll template's default cap is also 50).
DEFAULT_LIMIT = 100
DEFAULT_MAX_PAGES = 50
DEFAULT_TIMEOUT = 60

# services.* rejects the default Python user agent (Cloudflare 1010; proven
# in the S79 sandbox run and encoded as router doctrine F4), so services
# reads always send a real browser UA.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# Candidate list keys for the pages envelope. The capture does not name the
# envelope key (UNVERIFIED), so extraction accepts the same candidate set
# the tree already tolerates for page-list bodies (ghl_rest_canvas.
# find_page_by_name / the inventory canvas sketch) and raises on anything
# else. A bare top-level JSON list is also accepted.
_PAGE_LIST_KEYS = ("pages", "funnelPages", "data", "steps")

# The documented page-status vocabulary this mapping will pass through.
# Anything else non-empty is an unmapped state and RAISES (Q7).
_KNOWN_PAGE_STATUSES = ("draft", "published")


# ── Named errors ─────────────────────────────────────────────────────────────

class FunnelsReadError(RuntimeError):
    """A public funnel/page read failed: transport, HTTP status, malformed
    payload, or an unmapped contract shape. Never carries a credential
    value. Callers must treat this as NO inventory, never a partial one."""


class IncompleteInventoryError(FunnelsReadError):
    """The pagination completeness gate refused the read: the collected
    set cannot be proven complete (reported total unmet or absent where
    documented, an empty page mid-read, or the max-pages cap hit). The
    partial set is discarded, never returned."""


# ── Small helpers ────────────────────────────────────────────────────────────

def _require(value: Any, name: str) -> None:
    """Reject empty / whitespace-only required values (fail loud, never
    silently proceed with a blank that would target the wrong resource)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{name} is required and must be non-empty")


def _row_id(row: Dict[str, Any]) -> str:
    """The row's id under the documented/established key spellings, or ""
    when the row carries none (such rows are kept for the enumeration
    layer to skip; an id is never fabricated for them)."""
    for key in ("id", "_id"):
        value = row.get(key)
        if value:
            return str(value)
    return ""


def _default_opener(req: urllib.request.Request, timeout: int) -> Any:
    return urllib.request.urlopen(req, timeout=timeout)


# ── Transport (ghl_media shape) ──────────────────────────────────────────────

def _http_error_message(status: int, detail: str, what: str) -> str:
    """The honest failure text for a non-2xx public read. 403 is a
    token-context diagnosis FIRST (router F9: LOCATION PIT vs Firebase
    token-id vs OAuth Company vs Agency PIT are never substituted for one
    another); 429 is a same-rail cooldown, never a tier-hop (router F8).
    No credential value is ever interpolated here."""
    excerpt = f" Response body (truncated): {detail[:300]}" if detail else ""
    if status == 403:
        return (
            f"{what}: HTTP 403. Token-context check FIRST (router F9): this "
            "read requires the LOCATION Private Integration Token on the "
            "services origin; agency-class tokens and the internal "
            "token-id context are different contexts and are never "
            "substituted. The exact scope name the funnels family requires "
            "is UNVERIFIED in the public documentation capture, so no scope "
            f"claim is made here.{excerpt}"
        )
    if status == 429:
        return (
            f"{what}: HTTP 429 (rate limited). Doctrine F8: cool down and "
            "retry on the SAME rail; a 429 never tier-hops and never falls "
            f"back to another transport.{excerpt}"
        )
    return f"{what}: HTTP {status}.{excerpt}"


def _get_json(
    path: str,
    params: Dict[str, Any],
    *,
    pit: str,
    opener: Callable[[urllib.request.Request, int], Any],
    timeout: int,
    what: str,
) -> Any:
    """One bare-Python GET against the services origin, in the ghl_media
    pattern: Bearer LOCATION PIT + the funnels Version header + browser
    UA, injectable opener, fail-loud on non-2xx and on a non-JSON 2xx."""
    query = urllib.parse.urlencode(
        {k: v for k, v in params.items() if v is not None}
    )
    url = GHL_SERVICES_ORIGIN.rstrip("/") + path + ("?" + query if query else "")
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {pit}")
    req.add_header("Version", GHL_FUNNELS_VERSION)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", _USER_AGENT)

    try:
        resp = opener(req, timeout)
        code = int(resp.getcode())
        raw = resp.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 (the status alone still fails loud)
            detail = ""
        raise FunnelsReadError(
            _http_error_message(int(exc.code), detail, what)
        ) from exc
    except urllib.error.URLError as exc:
        raise FunnelsReadError(
            f"{what}: transport error ({exc.__class__.__name__}: {exc.reason})"
        ) from exc

    if not (200 <= code < 300):
        raise FunnelsReadError(_http_error_message(code, raw, what))
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FunnelsReadError(
            f"{what}: HTTP {code} but the body is not JSON: {raw[:300]}"
        ) from exc


# ── Envelope extraction ──────────────────────────────────────────────────────

def _extract_items(body: Any, candidate_keys: Tuple[str, ...], *, what: str) -> List[Dict[str, Any]]:
    """Pull the row list out of one page payload. A bare JSON list is
    accepted; a dict is searched under `candidate_keys` in order. Anything
    else (or a non-object row) is a malformed page and RAISES: a partial
    or guessed inventory is never returned."""
    items: Any = None
    if isinstance(body, list):
        items = body
    elif isinstance(body, dict):
        for key in candidate_keys:
            candidate = body.get(key)
            if isinstance(candidate, list):
                items = candidate
                break
    if items is None:
        raise FunnelsReadError(
            f"{what}: unrecognized response envelope; expected a JSON list "
            f"or an object carrying a list under one of {candidate_keys}. "
            "Refusing to guess the shape."
        )
    rows: List[Dict[str, Any]] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise FunnelsReadError(
                f"{what}: row {i} is not a JSON object "
                f"(got {type(item).__name__}); refusing a malformed page."
            )
        rows.append(item)
    return rows


# ── Pagination engine (bulk-enroll completeness discipline) ─────────────────

def _paginate(
    fetch_page: Callable[[int], Tuple[List[Dict[str, Any]], Optional[int]]],
    *,
    limit: int,
    max_pages: int,
    what: str,
) -> List[Dict[str, Any]]:
    """Drive offset pagination to a PROVEN-complete set or raise.

    `fetch_page(offset)` returns (rows, reported_total_or_None). Rules:
      * rows are collected in order, de-duplicated by row id;
      * when a total is reported, the read ends exactly when the unique
        collected count reaches it, an empty page before that raises, and
        any final mismatch raises (IncompleteInventoryError);
      * when no total exists (the pages contract as captured), the read
        ends on a SHORT page (fewer rows than `limit`): that short page is
        the contract's end-of-pages signal, and it is the completeness
        proof used for page reads;
      * exceeding `max_pages` raises (runaway / unterminated read).
    """
    collected: List[Dict[str, Any]] = []
    seen_ids: set = set()
    total: Optional[int] = None
    offset = 0
    pages = 0

    while True:
        pages += 1
        if pages > max_pages:
            raise IncompleteInventoryError(
                f"{what}: exceeded {max_pages} pages without reaching the "
                "end of the inventory; refusing an unbounded partial read"
            )
        rows, page_total = fetch_page(offset)
        if page_total is not None:
            if total is None:
                total = page_total
            elif page_total != total:
                raise IncompleteInventoryError(
                    f"{what}: the reported total changed mid-read "
                    f"({total} then {page_total}); refusing an inconsistent read"
                )
        for row in rows:
            rid = _row_id(row)
            if rid:
                if rid in seen_ids:
                    continue
                seen_ids.add(rid)
            collected.append(row)

        if total is not None:
            if len(collected) >= total:
                break
            if not rows:
                raise IncompleteInventoryError(
                    f"{what}: page at offset {offset} returned no rows but "
                    f"the reported total is {total} with only "
                    f"{len(collected)} collected; refusing a partial read"
                )
        else:
            if len(rows) < limit:
                break
        offset += limit

    if total is not None and len(collected) != total:
        raise IncompleteInventoryError(
            f"{what}: reported total={total} but pagination collected "
            f"{len(collected)} unique rows; refusing a partial or "
            "inconsistent read"
        )
    return collected


# ── Row mappings (prep step 4: honest fields, explicit status mapping) ──────

def normalize_funnel_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Map one public funnel row to the enumeration seam's shape. The
    captured contract does not expand funnel item fields (UNVERIFIED), so
    the only mapping is the id alias (`_id` -> `id` when `id` is absent);
    every other field passes through exactly as delivered and nothing is
    invented."""
    out = dict(row)
    if not out.get("id") and out.get("_id"):
        out["id"] = out["_id"]
    return out


def normalize_page_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Map one public page row to the enumeration seam's shape.

    Honest-field rules (step 4):
      * `id` is aliased from the documented `_id` when `id` is absent.
      * `status`: draft/published pass through (case-insensitive). An
        ABSENT status stays absent (the enumeration layer's existing
        default then applies). Any OTHER non-empty value is an unmapped
        state and RAISES (Q7): the public contract as captured documents
        no status vocabulary, so a third state must surface loudly here
        rather than be silently coerced downstream.
      * `marker` is NOT provided by the captured public contract (Q4):
        when the row carries none, none is invented, and the row can
        therefore never be flagged DUPLICATE downstream.
      * `created` is never backfilled from `updatedAt`: an update time is
        not a creation time, and a fabricated creation time would corrupt
        the lifecycle STALE rule.
    """
    out = dict(row)
    if not out.get("id") and out.get("_id"):
        out["id"] = out["_id"]
    status = out.get("status")
    if status is not None and str(status).strip() != "":
        normalized = str(status).strip().lower()
        if normalized not in _KNOWN_PAGE_STATUSES:
            raise FunnelsReadError(
                f"public page row {_row_id(out) or '<no id>'} carries "
                f"status {status!r}, which is outside the draft/published "
                "vocabulary the inventory understands; refusing to "
                "silently coerce an unmapped status (Q7). If live proof "
                "shows this is a real third state, the mapping gets a "
                "reviewed amendment."
            )
        out["status"] = normalized
    return out


# ── The two public listers (the seams' live implementations) ─────────────────

def list_funnels(
    location_id: str,
    *,
    pit: Optional[str] = None,
    opener: Optional[Callable[[urllib.request.Request, int], Any]] = None,
    limit: int = DEFAULT_LIMIT,
    max_pages: int = DEFAULT_MAX_PAGES,
    timeout: int = DEFAULT_TIMEOUT,
) -> List[Dict[str, Any]]:
    """List EVERY funnel in a location over the public API
    (GET /funnels/funnel/list), paginated to a proven-complete set.

    The completeness gate uses the envelope's documented `count` as the
    reported total; a response missing it cannot be proven complete and
    raises (the bulk-enroll discipline). Sends only the documented
    required + pagination parameters (locationId, offset, limit); the
    optional type/category/name filters are not needed for a full
    inventory and are not sent.

    Raises FunnelsReadError / IncompleteInventoryError on any failure;
    a partial list is never returned.
    """
    _require(location_id, "location_id")
    pit = pit if pit is not None else ghl_media.resolve_location_pit()
    _opener = opener or _default_opener
    what = "GET /funnels/funnel/list"

    def _fetch(offset: int) -> Tuple[List[Dict[str, Any]], Optional[int]]:
        body = _get_json(
            FUNNEL_LIST_PATH,
            {"locationId": location_id, "offset": offset, "limit": limit},
            pit=pit, opener=_opener, timeout=timeout, what=what,
        )
        rows = _extract_items(body, ("funnels",), what=what)
        total: Optional[int] = None
        if isinstance(body, dict) and body.get("count") is not None:
            try:
                total = int(body["count"])
            except (TypeError, ValueError) as exc:
                raise IncompleteInventoryError(
                    f"{what}: the documented count field is not a number "
                    f"({body['count']!r}); cannot prove completeness"
                ) from exc
        if total is None:
            raise IncompleteInventoryError(
                f"{what}: the response carries no count, but the documented "
                "envelope requires one; cannot prove the collected set is "
                "complete, so the read is refused"
            )
        return rows, total

    rows = _paginate(_fetch, limit=limit, max_pages=max_pages, what=what)
    return [normalize_funnel_row(r) for r in rows]


def list_pages(
    funnel_id: str,
    location_id: str,
    *,
    pit: Optional[str] = None,
    opener: Optional[Callable[[urllib.request.Request, int], Any]] = None,
    limit: int = DEFAULT_LIMIT,
    max_pages: int = DEFAULT_MAX_PAGES,
    timeout: int = DEFAULT_TIMEOUT,
) -> List[Dict[str, Any]]:
    """List EVERY page of one funnel over the public API
    (GET /funnels/page; locationId + funnelId + limit + offset are the
    documented required parameters), paginated to a proven-complete set.

    The captured contract documents no total field for this endpoint, so
    the completeness proof is the short-page end-of-pages signal plus the
    max-pages cap (recorded in the module docstring). The envelope key is
    UNVERIFIED in the capture; extraction accepts the tree's established
    candidate keys and raises on an unrecognized shape.

    Raises FunnelsReadError / IncompleteInventoryError on any failure;
    a partial list is never returned.
    """
    _require(funnel_id, "funnel_id")
    _require(location_id, "location_id")
    pit = pit if pit is not None else ghl_media.resolve_location_pit()
    _opener = opener or _default_opener
    what = "GET /funnels/page"

    def _fetch(offset: int) -> Tuple[List[Dict[str, Any]], Optional[int]]:
        body = _get_json(
            PAGE_LIST_PATH,
            {
                "locationId": location_id,
                "funnelId": funnel_id,
                "limit": limit,
                "offset": offset,
            },
            pit=pit, opener=_opener, timeout=timeout, what=what,
        )
        return _extract_items(body, _PAGE_LIST_KEYS, what=what), None

    rows = _paginate(_fetch, limit=limit, max_pages=max_pages, what=what)
    return [normalize_page_row(r) for r in rows]


# ── Self-test (fixtures only; no network, no credential resolution) ──────────

class _FakeResponse:
    def __init__(self, payload: Any, code: int = 200):
        self._payload = payload
        self._code = code

    def getcode(self) -> int:
        return self._code

    def read(self) -> bytes:
        if isinstance(self._payload, bytes):
            return self._payload
        return json.dumps(self._payload).encode("utf-8")


def _selftest() -> int:
    errors: List[str] = []

    def _opener_for(pages_by_offset: Dict[int, Any], calls: List[Any]):
        def _opener(req: urllib.request.Request, timeout: int) -> Any:
            calls.append(req)
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
            offset = int(query["offset"][0])
            return _FakeResponse(pages_by_offset[offset])
        return _opener

    # Multi-page funnels with a duplicate row: deduped, in order, complete.
    calls: List[Any] = []
    opener = _opener_for({
        0: {"funnels": [{"id": "f1", "name": "ZHC A"}, {"id": "f2", "name": "ZHC B"}], "count": 3, "traceId": "t"},
        2: {"funnels": [{"id": "f2", "name": "ZHC B"}, {"id": "f3", "name": "ZHC C"}], "count": 3, "traceId": "t"},
    }, calls)
    got = list_funnels("loc1", pit="pit-selftest-placeholder-value", opener=opener, limit=2)
    if [f["id"] for f in got] != ["f1", "f2", "f3"]:
        errors.append(f"multi-page funnel read wrong: {got}")
    if len(calls) != 2:
        errors.append(f"expected exactly 2 funnel requests, got {len(calls)}")
    if calls and calls[0].get_header("Version") != GHL_FUNNELS_VERSION:
        errors.append("the funnels Version header was not sent")

    # Reported total unmet -> IncompleteInventoryError, nothing returned.
    opener = _opener_for({
        0: {"funnels": [{"id": "f1"}], "count": 5, "traceId": "t"},
        2: {"funnels": [], "count": 5, "traceId": "t"},
    }, [])
    try:
        list_funnels("loc1", pit="pit-selftest-placeholder-value", opener=opener, limit=2)
        errors.append("an unmet reported total must raise IncompleteInventoryError")
    except IncompleteInventoryError:
        pass

    # Pages: short page ends the read; _id is aliased to id.
    opener = _opener_for({
        0: {"pages": [{"_id": "p1", "name": "ZHC One"}, {"_id": "p2", "name": "ZHC Two"}]},
        2: {"pages": [{"_id": "p3", "name": "ZHC Three"}]},
    }, [])
    got = list_pages("f1", "loc1", pit="pit-selftest-placeholder-value", opener=opener, limit=2)
    if [p["id"] for p in got] != ["p1", "p2", "p3"]:
        errors.append(f"page read wrong: {got}")

    # An unmapped third status raises instead of being silently coerced.
    opener = _opener_for({0: {"pages": [{"_id": "p1", "status": "archived"}]}}, [])
    try:
        list_pages("f1", "loc1", pit="pit-selftest-placeholder-value", opener=opener, limit=2)
        errors.append("an unmapped page status must raise FunnelsReadError")
    except FunnelsReadError:
        pass

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — ghl_funnels_read public reads + fail-closed pagination (no network)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="run offline selftest, no network")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    ap.print_help()
    return 2


__all__ = [
    "GHL_SERVICES_ORIGIN",
    "GHL_FUNNELS_VERSION",
    "FUNNEL_LIST_PATH",
    "PAGE_LIST_PATH",
    "DEFAULT_LIMIT",
    "DEFAULT_MAX_PAGES",
    "FunnelsReadError",
    "IncompleteInventoryError",
    "list_funnels",
    "list_pages",
    "normalize_funnel_row",
    "normalize_page_row",
]


if __name__ == "__main__":
    sys.exit(main())
