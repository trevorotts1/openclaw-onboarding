#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u04_modules/form_reader.py  (U04 tooling)
# LIVE FORM READER — the public v2 `GET /forms/?locationId=` read that FINDS
# the universal author-intake form on a Convert and Flow location and reports
# the ONE minted-link identifier: its form id. OFFLINE plan + offline
# self-test always work; the live read needs a location-scoped PIT BY LABEL.
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u04_modules/ — an importable module under the U04
# package (pure namespace container per the u02/u03 package-init doctrine:
# imported BY NAME, side-effect-free at import). It is NOT a manifest row: it
# ships as the shared live form surface the U04 verification family imports,
# so the find-by-slug / pin-by-id semantics can NEVER drift between this
# reader and its callers — the delta_reporter.py single-implementation
# doctrine (a contract read once, in one module).
#
# WHAT THIS OWNS
#   1. THE PUBLIC FORMS SURFACE. The live form rows are read with ONE GET:
#      https://services.leadconnectorhq.com/forms/?locationId=<loc>
#      (public v2, Version 2021-07-28 — the path-based version map
#      /forms/ -> 2021-07-28 proven in
#      44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/
#      utils/ghl_client.py, Skill 44). The engine's U02 forms read rides the
#      internal rail (backend.*) through ACTIVE form_submission TRIGGERS
#      (forms_check.py — the only form surface that repo had proven live when
#      U02 shipped); THIS module is the PUBLIC-v2 sibling: the same forms,
#      read directly off services.* with the location PIT, no rail, no
#      Firebase refresh token. The listing response is read as JSON
#      (Content-Type application/json; charset=utf-8) and flattened over the
#      two proven container shapes — {"forms": [...]} (the shape Skill 44's
#      create/re-get receipts re-read) and a bare top-level array.
#   2. FIND-BY-SLUG. universal-intake is found by NAME first: a listing row
#      whose normalized name equals the slug with dashes -> spaces
#      ("universal intake") — the same name-match law golden_forms.py pins.
#      The slug also matches the two engine spellings of the hidden contract
#      key ("universal_intake", "universal_intake_form_id") wherever a row
#      carries them. Every row that carries the form id is kept, so a
#      near-miss is REPORTED (never silently ignored): candidates are the
#      rows whose name CONTAINS "universal" (case-insensitive), and they are
#      listed with their masked ids for the operator to resolve — the
#      fail-closed never-a-silent-pass surface.
#   3. PIN-BY-ID (the drift law). When --form-id is given (the engine's
#      pinned fleet value: DEFAULT_UNIVERSAL_INTAKE_FORM_ID in
#      scripts/anthology_book.py, or a box override
#      config/engine-config.template.json intake.universal_intake_form_id),
#      the reader ALSO requires the listing to carry that exact id — a
#      pinned id the listing does not contain is a MISMATCH (exit 5), never
#      a silent pass, and the pinned id BYPASSES the slug law (a pin is a
#      stronger contract than a name). The pinned value is masked on every
#      surface, exactly like a location id.
#   4. THE READ LAW. A 2xx whose body is NOT valid JSON, a listing with no
#      parseable rows, a listing with NO universal-intake row, or a pinned
#      id absent from the listing is a FAIL (exit 5) — never a fabricated
#      pass. A bare 401/403 is HELD (UpstreamBlockedError — the CF 1010
#      edge-block guard; a scope denial is only a REAL
#      "not authorized for this scope" signature), a transport failure is
#      HELD (exit 3), and a missing/refused credential STOPS (exit 2).
#      A NOT-FOUND is the fail-closed default: the form id is returned ONLY
#      when a row matched the slug law (or the pin matched); otherwise the
#      surface carries found=false and NO id value — no id, no pass.
#   5. NEVER-A-TOKEN SURFACE. The PIT is resolved through
#      anthology_registry.resolve_pit (the house labels
#      CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY / GOHIGHLEVEL_API_KEY /
#      GOHIGHLEVEL_PIT / GHL_API_KEY, live process env first then the three
#      canonical client env stores; SET / NOT SET only — a token value is
#      NEVER printed). Before any JSON is emitted, the payload is scanned
#      against the house credential shape (pit-<value>) and a hit REFUSES
#      the whole surface rather than print it — the delta_reporter.py
#      never-a-real-token doctrine.
#
# BROWSER UA (CF 1010 LAW): every request rides reg.CafClient, which applies
# CAF_BROWSER_UA on EVERY request — the Cloudflare edge fronting
# services.leadconnectorhq.com 403s urllib's default "Python-urllib/x.y"
# User-Agent at the WAF edge (CF error 1010) before the request ever reaches
# Convert and Flow (GK-09; the same browser UA the Podcast gate proved live).
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. SET / NOT SET only on every
# operator surface; a token value is NEVER printed, echoed, or reflected.
#
# FAIL-CLOSED (the whole point): a missing credential, a non-pit- token, an
# unreadable response, an empty listing, an absent universal-intake row, or
# a pinned id the listing lacks is a REFUSAL / FAIL — never a silent pass,
# never a fabricated success, and never an id guessed from memory.
#
# RETURN CONTRACT (the machine surface this module owns):
#   read_forms(client, location_id, *, pinned_id="", form_rows=None)
#       -> dict — {"contract", "ok", "found", "form_id", "form_id_masked",
#       "matched_by", "count", "candidates", "sources", "af_code",
#       "note"}; found=false carries NO form_id value.
#       Raises FormsReadError (STOP family) / reg.CafUnreachable,
#       reg.ScopeDenied, reg.UpstreamBlockedError (HELD family) — a caller
#       maps them onto the house exit codes.
#   plan(location_id, pinned_id, *, out=sys.stdout) -> int — ONE JSON
#       object, offline, no network, no credential.
#   self_test(out=sys.stderr) -> int — OFFLINE golden + attack battery
#       (needs no network and no credential; exit 0 PASS / 4 enforced
#       violation).
#   The CLI (main) offers check / plan / self-test.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 belongs to self-test FAILED):
#   0  PASS — the universal-intake form was found (also plan / self-test)
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — credential label NOT SET / non-pit- value / usage /
#      a malformed listing shape that cannot be read faithfully
#   3  Convert and Flow API unreachable / edge-blocked (HELD, retryable)
#   4  self-test FAILED (a tamper NEVER masquerades as exit 1)
#   5  MISMATCH — no universal-intake row, a pinned id absent from the
#      listing, or a malformed listing (the fail-closed default)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr;
# plan and self-test are OFFLINE and need NO token and NO network):
#   form_reader.py check [--location-id ID] [--form-id ID]
#   form_reader.py plan   [--location-id ID] [--form-id ID]
#   form_reader.py self-test
# =============================================================================
"""form_reader.py — live reader of the Convert and Flow forms listing that
finds the universal author-intake form (Skill 59, U04 tooling)."""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import sys
import urllib.error
import urllib.parse
from pathlib import Path

# Sibling import bootstrap (house convention, identical to forms_check.py /
# config_loader.py): the registry owns the Cloudflare browser-UA wiring, the
# LeadConnector client, the credential resolution, and the exit-code contract.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"

# The one fixed config-surface contract. Every surface this module emits
# carries it, so a machine consumer can never mistake another JSON object for
# a form read (the self-test asserts the golden plan carries the exact string
# — the surface contract is load-bearing).
CONFIG_CONTRACT = "anthology-engine-form-read"
CONFIG_SCHEMA_VERSION = 1

# The slug this reader exists for — the engine's universal author-intake form
# (the same slug forms_check.py FORM_SLUGS / golden_forms.py
# GOLDEN_FORM_SLUGS pin; the snapshot contract's forms.required[0].role
# "universal-author-intake").
FORM_SLUG = "universal-intake"

# The public v2 forms-listing surface, proven in Skill 44
# (44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/utils/
# ghl_client.py: GET /forms/ with params locationId/limit/skip, Version
# 2021-07-28 — the same base + version header reg.CafClient already sends).
FORMS_LIST_PATH = "/forms/"

# The name-match law: the slug with dashes -> spaces ("universal intake") —
# the same law golden_forms.py golden_form_name_matches() pins for the
# three-form family. A listing row whose normalized name equals this string
# IS the universal-intake form.
SLUG_AS_NAME = FORM_SLUG.replace("-", " ")

# The alternate spellings of the hidden contract key that may ride a form row
# (the U02 forms read and anthology_book.py's config surface use both
# underscore spellings) — any of them names the same form.
_KEY_ALIASES = ("universal_intake", "universal_intake_form_id")

# The engine's pinned fleet-wide form id — the ONE universal author-intake
# form id baked into scripts/anthology_book.py (DEFAULT_UNIVERSAL_INTAKE_FORM_ID,
# live-verified 2026-08-11 byte-equal on the template location's Intake Fire
# trigger) and the slot config/engine-config.template.json
# intake.universal_intake_form_id can override per box. A location
# identifier, not a secret — but the reader masks it on every surface.
DEFAULT_UNIVERSAL_INTAKE_FORM_ID = "U65pwoeMTy1niMqllKWG"

# The template location id is the CONTRACT's source_template_location (the
# operator's OWN template location, operator infrastructure config, not a
# secret). The check pins to it; --location-id overrides for tests.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value (e.g. "pit-abc123"). The label word "PIT" alone is NOT a credential
# shape — operator surfaces name labels, never values. The self-test proves
# the pattern discriminates both ways, and every emitted surface is scanned
# against it before print.
_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")


class FormsReadError(Exception):
    """A fail-closed read refusal (STOP family): a malformed listing shape
    that cannot be read faithfully, an empty listing, or a credential-shaped
    string in a payload. An expectation that cannot name its own sources
    must not run."""


# A genuine Convert and Flow LOCATION-scope refusal carries its own JSON
# signature ("does not have access to this location") that is NOT the
# registry's W0.5 pipeline-scope text ("not authorized for this scope").
# Live-verified 2026-08-11 on this operator box: the template location
# returns {"statusCode":403,"message":"The token does not have access to
# this location."} (79 bytes, plaintext JSON, no Content-Encoding) for the
# PIT-scoped public-v2 read — exactly the signature forms_check.py
# recognizes as a STOP. The registry's classifier deliberately matches only
# the W0.5 pipeline text, so a location-denied token must be recognized
# HERE and STOP (exit 2) — never a HELD misdiagnosis.
LOCATION_ACCESS_DENIAL_SIGNATURE = "does not have access to this location"


def _request_error_kind(exc) -> str:
    """Classify a request error into a STOP ('location-scope') or HELD
    ('blocked') family, exactly as forms_check.py does: the registry's own
    classifier matches only the W0.5 pipeline text, so the live-verified
    Convert and Flow LOCATION-scope signature ("does not have access to this
    location") is recognized in addition. A location-denied token STOPS;
    an edge block and everything else stays HELD (retryable) — never
    mislabeled. Fail-closed: an unreadable body is undecidable and
    classifies HELD — never a fabricated scope STOP from a header alone."""
    body = b""
    if not isinstance(exc, urllib.error.HTTPError):
        # A registry UpstreamBlockedError re-raised from a location-scope
        # denial keeps the ORIGINAL HTTPError as its __context__ (raised
        # inside the except handler) — unwrap BEFORE judging. The original
        # body may already be consumed by the registry's own read, but the
        # Content-Encoding header survives.
        ctx = exc.__context__
        if isinstance(ctx, urllib.error.HTTPError):
            exc = ctx
    if isinstance(exc, urllib.error.HTTPError):
        ce = ""
        try:
            ce = str(exc.headers.get("Content-Encoding") or "").lower()
        except AttributeError:
            ce = ""
        except Exception:
            ce = ""
        try:
            body = exc.read()
        except Exception:
            body = b""
        if ce == "gzip" and body[:2] == b"\x1f\x8b":
            try:
                body = gzip.decompress(body)
            except OSError:
                body = b""
    text = (body or b"").decode("utf-8", "replace")
    if LOCATION_ACCESS_DENIAL_SIGNATURE in text:
        return "location-scope"
    if "not authorized for this scope" in text:
        return "scope"
    return "blocked"


def mask_id(fid: str) -> str:
    """Non-reversible marker for a form id (last 4 chars) — the house surface
    shape for every operator-facing mention of a form id."""
    return reg._mask_location(fid)


def _normalize_name(name: str) -> str:
    """The name-match normalization: lowercase, spaces collapsed — so
    "Universal Intake", " universal  intake " and "UNIVERSAL INTAKE" all
    resolve to the same law string. Returns the normalized name."""
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


def _row_id(row) -> str:
    """The form id of a listing row under any of its container keys — "id"
    (the canonical key, proven in Skill 44 receipts), "_id", or
    "formId". Returns "" when the row carries none."""
    if not isinstance(row, dict):
        return ""
    for key in ("id", "_id", "formId"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _row_keys(row) -> list:
    """The str-typed value keys of a row, for the alias-name match. A key
    whose value is a string is treated as a name-bearing field; a value that
    is not a string (a list of hidden fields, a dict) can never name a form."""
    if not isinstance(row, dict):
        return []
    out = []
    for k, v in row.items():
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    return out


def _unmasked_row_id_scan(row_id: str) -> None:
    """Never-a-token guard for a SINGLE form id: a credential-shaped id
    REFUSES rather than surface (a row whose id looks like a token is not a
    form we report — the id is what this reader exists to emit)."""
    if _CREDENTIAL_SHAPE.search(row_id):
        raise FormsReadError(
            "a listing row id resolved to a credential-shaped string — "
            "REFUSED without printing it")


def _flatten_rows(payload) -> list:
    """Flatten a forms-listing payload to a list of row dicts over the two
    PROVEN container shapes: {"forms": [...]} (the shape Skill 44's form
    create/re-get receipts re-read) and a bare top-level array. Any other
    shape — including a payload that parses to a non-dict — is a
    FormsReadError (never a silent empty; an unreadable shape is not proof
    of zero forms)."""
    if isinstance(payload, dict):
        rows = payload.get("forms")
        if rows is None:
            raise FormsReadError(
                "forms listing payload has no 'forms' array and is not a "
                "top-level array — the listing shape is not readable")
    elif isinstance(payload, list):
        rows = payload
    else:
        raise FormsReadError(
            "forms listing payload is neither an object nor an array — the "
            "listing shape is not readable")
    if not isinstance(rows, list):
        raise FormsReadError("forms listing 'forms' value is not an array")
    return [r for r in rows if isinstance(r, dict)]


def _read_forms_payload(client, location_id: str) -> dict:
    """The ONE live forms read: public v2 GET /forms/?locationId=<loc> via
    reg.CafClient, which applies CAF_BROWSER_UA on every request (the CF
    1010 law) and raises ScopeDenied / UpstreamBlockedError / CafUnreachable
    / CafValidation — all mapped onto the HELD/STOP families by the CLI."""
    out = client._request(
        "GET", FORMS_LIST_PATH,
        query={"locationId": location_id, "limit": 200})
    if not isinstance(out, dict):
        raise FormsReadError(
            "forms listing response is not a JSON object — the listing shape "
            "is not readable")
    return out


def read_forms(client, location_id: str, *, pinned_id: str = "",
               form_rows=None) -> dict:
    """Read the live forms listing and FIND the universal-intake form.
    Fail-closed, never a token.

    `client` is a reg.CafClient (its own _request rides CAF_BROWSER_UA).
    `form_rows` is an explicit row list (self-tests); when None the live
    GET is performed. `pinned_id` is the engine's pinned fleet-wide form id
    (or a box override) — when non-empty it must appear on the listing
    (exit-5 MISMATCH otherwise) and it BYPASSES the slug law.

    Returns the documented surface {contract, schema_version, ok, found,
    form_id, form_id_masked, matched_by, count, candidates, sources,
    af_code, note} — fail-closed:
      - ok True ONLY when a row matched the slug law (name byte-equal to
        "universal intake" after normalization, or an alias key match)
        AND a pinned_id, when given, appeared on the listing; the returned
        form_id is the matched row's id,
      - ok False carries NO form_id (found=false; never an id guessed from
        memory) and a named af_code — FORMS-NOT-FOUND when the listing was
        read but held no match, FORMS-EMPTY when the listing held zero
        rows, PIN-MISSING when a pinned id was absent from a non-empty
        listing,
      - every row that carried the form id is kept in `candidates` (with a
        masked id) so a near-miss is REPORTED, never silently ignored —
        even on the not-found paths,
      - count is the total number of rows read; sources names the exact
        read (the public v2 path + the live/cached seam).
    Never raises for a data mismatch (a mismatch is a result); raises for a
    broken listing shape (FormsReadError, STOP family) or a transport/scope
    failure (the client's exceptions, HELD family).
    """
    if form_rows is None:
        payload = _read_forms_payload(client, location_id)
        rows = _flatten_rows(payload)
    else:
        rows = [r for r in form_rows if isinstance(r, dict)]
    count = len(rows)

    matched = None
    matched_by = ""
    candidates = []
    for row in rows:
        row_id = _row_id(row)
        if row_id:
            _unmasked_row_id_scan(row_id)
            candidates.append({"id_masked": mask_id(row_id)})
        if matched is not None:
            continue
        # the slug law: the normalized name is the slug with dashes -> spaces,
        # or the row carries an underscore spelling of the same key — as a row
        # KEY (e.g. {"universal_intake": ...}) or as a string VALUE
        if _normalize_name(str(row.get("name") or "")) == SLUG_AS_NAME:
            matched, matched_by = row, "name"
            continue
        for key in row:
            if _normalize_name(key) in _KEY_ALIASES:
                matched, matched_by = row, "alias"
                break
        if matched is None:
            for val in _row_keys(row):
                if _normalize_name(val) in _KEY_ALIASES:
                    matched, matched_by = row, "alias"
                    break

    pinned_checked = bool(pinned_id and pinned_id.strip())
    pinned = pinned_id.strip() if pinned_id else ""
    if pinned:
        _unmasked_row_id_scan(pinned)
    pin_present = any(_row_id(r) == pinned for r in rows)
    if pinned and not pin_present:
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": False,
            "found": False,
            "form_id": "",
            "form_id_masked": "",
            "matched_by": "",
            "count": count,
            "candidates": candidates,
            "sources": {"read": "public v2 %s?locationId=<loc> (Version %s, "
                                "CAF_BROWSER_UA on the request)"
                                % (FORMS_LIST_PATH, reg.CAF_VERSION_HEADER),
                        "rows": "live GET" if form_rows is None else "explicit (self-test)",
                        "pinned_id": "pinned %s; absent from the listing"
                                     % mask_id(pinned)},
            "af_code": "PIN-MISSING",
            "note": "the pinned universal-intake form id is not on the "
                    "listing — fail-closed, never a silent pass",
        }

    if matched is None:
        return {
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": False,
            "found": False,
            "form_id": "",
            "form_id_masked": "",
            "matched_by": "",
            "count": count,
            "candidates": candidates,
            "sources": {"read": "public v2 %s?locationId=<loc> (Version %s, "
                                "CAF_BROWSER_UA on the request)"
                                % (FORMS_LIST_PATH, reg.CAF_VERSION_HEADER),
                        "rows": "live GET" if form_rows is None else "explicit (self-test)",
                        "pinned_id": "pinned %s; checked"
                                     % (mask_id(pinned) if pinned_checked else "none")},
            "af_code": "FORMS-EMPTY" if count == 0 else "FORMS-NOT-FOUND",
            "note": ("the listing is empty" if count == 0 else
                     "no universal-intake row on the listing — the slug law "
                     "matched nothing") + " (fail-closed, never an id guessed "
                     "from memory)",
        }

    fid = _row_id(matched)
    if not fid:
        raise FormsReadError(
            "the universal-intake row carries no form id — the listing shape "
            "is not readable")
    return {
        "contract": CONFIG_CONTRACT,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "ok": True,
        "found": True,
        "form_id": fid,
        "form_id_masked": mask_id(fid),
        "matched_by": matched_by,
        "count": count,
        "candidates": candidates,
        "sources": {"read": "public v2 %s?locationId=<loc> (Version %s, "
                            "CAF_BROWSER_UA on the request)"
                            % (FORMS_LIST_PATH, reg.CAF_VERSION_HEADER),
                    "rows": "live GET" if form_rows is None else "explicit (self-test)",
                    "pinned_id": "pinned %s; %s"
                                 % (mask_id(pinned) if pinned_checked else "none",
                                    "on the listing" if pin_present else "not checked")},
        "af_code": "OK" if not pinned_checked or pin_present else "PIN-MISSING",
        "note": "matched the universal-intake row by %s" % matched_by,
    }


# ---------------------------------------------------------------------------
# Offline self-test (no network, no credentials) — proves the reader against
# the REAL committed constants, then runs every attack fixture: golden
# finds, the pin law both ways, every not-found path named, the alias key
# match, the never-a-token guard, and the location-scope-vs-edge 403
# discrimination the CLI depends on.
# ---------------------------------------------------------------------------

class _FakeClient:
    """In-memory public-v2 client: serves the row list the self-test hands it
    and records the exact request, so the live-read contract (the path, the
    locationId query, CAF_BROWSER_UA on the request) is provable offline."""

    def __init__(self, rows):
        self._rows = list(rows or [])
        self.calls = []

    def _request(self, method, path, query=None, body=None):
        self.calls.append({"method": method, "path": path, "query": dict(query or {})})
        return {"forms": [dict(r) for r in self._rows]}


def _golden_rows():
    """The golden listing rows: the universal-intake form carrying the pinned
    engine id, plus the engine's two gate forms — the same three-slug family
    forms_check.py / golden_forms.py pin."""
    return [
        {"id": DEFAULT_UNIVERSAL_INTAKE_FORM_ID, "name": "Universal Intake",
         "type": "form", "hiddenFields": ["contact_id", "anthology_id", "stage"]},
        {"id": "riNlAkYbcW3g92VRLqq0", "name": "Universal Review",
         "type": "form", "hiddenFields": ["contact_id", "anthology_id", "stage"]},
        {"id": "UgiiSoZsA4vyqOVfO5fi", "name": "Title Select",
         "type": "form", "hiddenFields": ["contact_id", "anthology_id", "stage"]},
    ]


def _self_test_body(dev) -> None:
    import urllib.error

    # ---- 0. the location-scope-vs-edge 403 discrimination the CLI depends
    #      on: a REAL location-scope denial (the live-verified "does not have
    #      access to this location" JSON, 79 bytes plaintext) -> STOP family,
    #      an edge block (CF 1010 HTML) and an empty body -> HELD family —
    #      the exact classification forms_check.py proved live
    loc_denial = urllib.error.HTTPError(
        "loc", 403, "Forbidden", hdrs=None,
        fp=io.BytesIO(b'{"statusCode":403,"message":"The token does not have '
                       b'access to this location."}'))
    assert _request_error_kind(loc_denial) == "location-scope", \
        "a live location-scope 403 must classify as location-scope (STOP)"
    w05_denial = urllib.error.HTTPError(
        "loc", 403, "Forbidden", hdrs=None,
        fp=io.BytesIO(b'{"message":"The token is not authorized for this '
                       b'scope."}'))
    assert _request_error_kind(w05_denial) == "scope", \
        "the W0.5 pipeline-scope 403 must classify as scope (STOP)"
    edge_denial = urllib.error.HTTPError("loc", 403, "Forbidden", hdrs=None,
                                         fp=io.BytesIO(b"<html>cf 1010</html>"))
    assert _request_error_kind(edge_denial) == "blocked", \
        "an edge 403 must classify as blocked (HELD)"
    empty_denial = urllib.error.HTTPError("loc", 403, "Forbidden", hdrs=None,
                                          fp=io.BytesIO(b""))
    empty_denial.read()  # simulate the registry's prior read (consumed body)
    assert _request_error_kind(empty_denial) == "blocked", \
        "a consumed empty body must classify as blocked (HELD)"
    gz_denial = urllib.error.HTTPError(
        "loc", 403, "Forbidden",
        hdrs={"Content-Encoding": "gzip"},
        fp=io.BytesIO(gzip.compress(b'{"statusCode":403,"message":"The token '
                                     b'does not have access to this '
                                     b'location."}')))
    assert _request_error_kind(gz_denial) == "location-scope", \
        "a gzip-encoded location-scope 403 must still classify as location-scope"
    # a wrapped UpstreamBlockedError carries the ORIGINAL HTTPError as its
    # __context__ — unwrapping must find the live location-scope signature.
    # The wrapped error is given a FRESH, unread HTTPError: an already-read
    # one is consumed (the registry reads the body before re-raising — the
    # real shape), and a consumed body is undecidable by design (HELD).
    wrapped = reg.UpstreamBlockedError("HTTP 403")
    wrapped.__context__ = urllib.error.HTTPError(
        "loc", 403, "Forbidden", hdrs=None,
        fp=io.BytesIO(b'{"statusCode":403,"message":"The token does not have '
                       b'access to this location."}'))
    assert _request_error_kind(wrapped) == "location-scope", \
        "a wrapped UpstreamBlockedError must unwrap to the location-scope 403"

    # ---- 1. golden: the live read finds universal-intake by name and the
    #      pinned id rides the listing
    client = _FakeClient(_golden_rows())
    res = read_forms(client, "loc_tmpl")
    assert res["ok"] is True and res["found"] is True, "golden read must find the form"
    assert res["form_id"] == DEFAULT_UNIVERSAL_INTAKE_FORM_ID, \
        "the found id must be the pinned engine id"
    assert res["form_id_masked"] == mask_id(DEFAULT_UNIVERSAL_INTAKE_FORM_ID)
    assert res["matched_by"] == "name"
    assert res["count"] == 3 and len(res["candidates"]) == 3
    assert res["af_code"] == "OK" and res["contract"] == CONFIG_CONTRACT
    # the request contract: the public-v2 path, the locationId query, and the
    # browser UA the house requires (CF 1010)
    assert client.calls == [{"method": "GET", "path": FORMS_LIST_PATH,
                             "query": {"locationId": "loc_tmpl", "limit": 200}}]
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), \
        "the house browser UA must stay a browser UA (CF 1010 law)"

    # ---- 2. the pin law, both ways: a pinned id ON the listing passes; a
    #      pinned id ABSENT from a non-empty listing is PIN-MISSING (exit 5),
    #      never a silent pass — even when the slug law matched
    res = read_forms(client, "loc_tmpl", pinned_id=DEFAULT_UNIVERSAL_INTAKE_FORM_ID)
    assert res["ok"] is True and res["af_code"] == "OK", \
        "pinned id on the listing must pass"
    rows = [dict(r) for r in _golden_rows()]
    rows[0]["id"] = "DriftedDriftedId00"  # the pinned id disappears from the listing
    client = _FakeClient(rows)
    res = read_forms(client, "loc_tmpl", pinned_id=DEFAULT_UNIVERSAL_INTAKE_FORM_ID)
    assert res["ok"] is False and res["af_code"] == "PIN-MISSING", \
        "an absent pinned id must be a MISMATCH, got %r" % res
    assert res["form_id"] == "" and res["found"] is False, \
        "a failed read must never carry a form id"

    # ---- 3. not-found paths, each NAMED: an empty listing is FORMS-EMPTY; a
    #      non-empty listing without universal-intake is FORMS-NOT-FOUND; both
    #      carry no id and keep the candidate rows (near-misses are reported)
    res = read_forms(client, "loc_tmpl", form_rows=[])
    assert res["ok"] is False and res["af_code"] == "FORMS-EMPTY", \
        "an empty listing must be FORMS-EMPTY"
    client = _FakeClient([{"id": "OtherFormId0000", "name": "Contact Us"}])
    res = read_forms(client, "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "FORMS-NOT-FOUND", \
        "a listing without universal-intake must be FORMS-NOT-FOUND"
    assert res["form_id"] == "" and res["candidates"] == \
        [{"id_masked": mask_id("OtherFormId0000")}], \
        "near-miss rows must stay on the surface (never silently ignored)"

    # ---- 4. the alias-key match: a row naming the form through an underscore
    #      spelling of the hidden contract key is found (matched_by alias)
    client = _FakeClient([{"_id": "AliasFormId0001", "universal_intake": "1",
                           "name": "Intake Form"}])
    res = read_forms(client, "loc_tmpl")
    assert res["ok"] is True and res["matched_by"] == "alias", \
        "an alias key must match the slug law, got %r" % res
    assert res["form_id"] == "AliasFormId0001"

    # ---- 5. never-a-token: a row id that IS a credential-shaped string
    #      REFUSES the whole read rather than print it; a pinned id that is
    #      credential-shaped refuses the same way
    client = _FakeClient([{"id": "pit-abc123", "name": "Universal Intake"}])
    try:
        read_forms(client, "loc_tmpl")
        raise AssertionError("a credential-shaped row id must refuse")
    except FormsReadError:
        pass
    try:
        read_forms(client, _FakeClient(_golden_rows()),
                   pinned_id="pit-abc123")
        raise AssertionError("a credential-shaped pinned id must refuse")
    except FormsReadError:
        pass

    # ---- 6. malformed listing shapes REFUSE (never a silent empty): a
    #      payload without a 'forms' key, a 'forms' value that is not an
    #      array, and a response that is not an object
    class _BadClient(_FakeClient):
        def __init__(self, payload):
            self._payload = payload
            self.calls = []

        def _request(self, method, path, query=None, body=None):
            self.calls.append({"method": method, "path": path})
            return self._payload

    try:
        read_forms(_BadClient({"nope": 1}), "loc_tmpl")
        raise AssertionError("a payload without 'forms' must refuse")
    except FormsReadError:
        pass
    try:
        read_forms(_BadClient({"forms": "not-a-list"}), "loc_tmpl")
        raise AssertionError("a non-array 'forms' must refuse")
    except FormsReadError:
        pass
    try:
        read_forms(_BadClient([{"id": "X"}]), "loc_tmpl")
        raise AssertionError("a non-object response must refuse")
    except FormsReadError:
        pass

    # ---- 7. the surface contract: the golden read never emits a
    #      credential-shaped string anywhere on the payload
    dumped = json.dumps(read_forms(_FakeClient(_golden_rows()), "loc_tmpl"),
                        indent=2, sort_keys=True)
    assert not _CREDENTIAL_SHAPE.search(dumped), \
        "a successful read must never carry a credential-shaped string"

    dev.write("[form-reader] self-test PASS: golden find + request contract "
              "(public v2 path, locationId, CAF_BROWSER_UA), pin law both "
              "ways, FORMS-EMPTY / FORMS-NOT-FOUND / PIN-MISSING named, "
              "alias-key match, credential-shaped ids refused, malformed "
              "listing shapes refused, location-scope 403 STOP vs edge 403 "
              "HELD (incl. gzip-encoded + wrapped-denial unwrap)\n")


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[form-reader] SELF-TEST FAILED: %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def plan(location_id: str, pinned_id: str = "", *, out=None) -> int:
    """Emit the ONE offline plan JSON object (no network, no credential).
    The payload is scanned against the credential shape before print: a hit
    REFUSES the surface rather than echo a token."""
    pinned = (pinned_id or "").strip()
    if pinned:
        _unmasked_row_id_scan(pinned)
    payload = {
        "contract": CONFIG_CONTRACT,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "slug": FORM_SLUG,
        "name_law": "row name == %r after normalization" % SLUG_AS_NAME,
        "pinned_id_masked": mask_id(pinned) if pinned else "",
        "read": "%s?locationId=<loc> (Version %s; CAF_BROWSER_UA on the "
                "request — CF 1010 law)" % (FORMS_LIST_PATH, reg.CAF_VERSION_HEADER),
        "note": "offline plan only — no network, no credential needed; a "
                "pinned form id absent from the live listing is a MISMATCH "
                "(exit 5), never a silent pass",
    }
    dumped = json.dumps(payload, indent=2, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped):
        raise FormsReadError(
            "plan payload carries a credential-shaped string — REFUSED "
            "without printing it")
    out = out or sys.stdout
    out.write(dumped)
    out.write("\n")
    return EX_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="form_reader.py",
        description="Live-read the public v2 Convert and Flow forms listing "
                    "(GET /forms/?locationId=) and find the universal-intake "
                    "form, reporting its ONE form id (Skill 59, U04 tooling). "
                    "Fail-closed; never prints a token. One JSON object on "
                    "stdout.")
    ap.add_argument("--location-id", default="",
                    help="override the template location id (default: the contract's "
                         "source_template_location.template_location_id, %s; never "
                         "printed)" % DEFAULT_TEMPLATE_LOCATION)
    ap.add_argument("--form-id", default="",
                    help="the pinned universal-intake form id (default: the engine "
                         "fleet value %s; masked on every surface; a pinned id "
                         "absent from the listing is a MISMATCH)"
                         % DEFAULT_UNIVERSAL_INTAKE_FORM_ID)
    ap.add_argument("cmd", nargs="?", choices=["check", "plan", "self-test"], default="check")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    location_id = args.location_id.strip() or DEFAULT_TEMPLATE_LOCATION
    pinned_id = args.form_id.strip() or DEFAULT_UNIVERSAL_INTAKE_FORM_ID

    try:
        if args.cmd == "self-test":
            return self_test()

        if args.cmd == "plan":
            return plan(location_id, pinned_id)

        # ---- live check ----
        pit_label, token = reg.resolve_pit()
        if not token:
            checked = ", ".join(reg.PIT_LABELS)
            reg._stop(sys.stderr,
                      "No Convert and Flow private-integration token is SET.",
                      ["Checked (in order): %s — all NOT SET." % checked,
                       "The reader runs against the operator's OWN template "
                       "location marker %s; set the template PIT "
                       "(client-standard labels first) and re-run."
                       % mask_id(location_id)])
            return EX_STOP
        # The location id on every operator surface is the masked marker only.
        # The registry's classifier matches only the W0.5 pipeline-scope text,
        # so a Convert and Flow LOCATION-scope denial ("does not have access
        # to this location", live-verified 2026-08-11 on this operator box for
        # the PIT-scoped public-v2 read) surfaces as an UpstreamBlockedError
        # (HELD). It is reclassified here as a STOP (exit 2) — never a HELD
        # misdiagnosis. The reclassification runs the RAW read again (the
        # registry consumed the first body before re-raising, so the wrapped
        # error cannot be re-read) and classifies the FRESH error, whose body
        # still carries the plaintext JSON signature.
        try:
            result = read_forms(reg.CafClient(token), location_id,
                                pinned_id=pinned_id)
        except reg.UpstreamBlockedError:
            import urllib.request as _ur
            url = (reg.CAF_API_BASE + FORMS_LIST_PATH + "?"
                   + urllib.parse.urlencode(
                       {"locationId": location_id, "limit": 200}))
            req = _ur.Request(
                url,
                headers={"Authorization": "Bearer %s" % token,
                         "Version": reg.CAF_VERSION_HEADER,
                         "Accept": "application/json",
                         "User-Agent": reg.CAF_BROWSER_UA})
            denied = False
            try:
                with _ur.urlopen(req, timeout=15):
                    pass  # a 2xx now — the probe raced; proceed to the check
            except urllib.error.HTTPError as exc2:
                denied = (_request_error_kind(exc2) == "location-scope")
            except Exception:
                pass  # any transport failure stays HELD below
            if denied:
                reg._stop(sys.stderr,
                          "The Convert and Flow token cannot READ this "
                          "location (\"does not have access to this "
                          "location\").",
                          ["Location marker: %s" % mask_id(location_id),
                           "The token resolved from a PIT label is not "
                           "location-scoped to it. Grant the template PIT "
                           "access to the template location, or point "
                           "--location-id at the location the PIT can read.",
                           "AF-AE-PIT-SCOPE family: STOP, never a silent "
                           "fallback."])
                return EX_STOP
            raise
        print(json.dumps(result, indent=2, sort_keys=True))
        return EX_OK if result.get("ok") else EX_MISMATCH

    except FormsReadError as exc:
        sys.stderr.write("[form-reader] STOP: %s\n" % exc)
        return EX_STOP
    except reg.ScopeDenied as exc:
        sys.stderr.write("[form-reader] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[form-reader] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[form-reader] HELD: %s\n" % exc)
        return EX_HELD
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[form-reader] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
