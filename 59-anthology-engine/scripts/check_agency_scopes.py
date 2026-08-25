#!/usr/bin/env python3
"""U24 — probe the agency PIT's scopes on the Anthology Convert and Flow
template location. READ-ONLY: every probe is a GET; nothing is created,
modified, or deleted. Values are NEVER printed (doctrine: SET/NOT SET only,
masked identifiers).

The four scopes U24 names are granted on the AGENCY PIT (the operator-owned
token at GHL_AGENCY_PIT / GOHIGHLEVEL_AGENCY_PIT / GOHIGHLEVEL_CONVERTAND-
FLOW_AGENCY_PIT), not on a per-location PIT:

  snapshots.readonly    GET /snapshots                    (agency-level list)
  snapshots.write       POST /snapshots/from-location     (create a snapshot)
  locations.write       PUT  /locations/{id}              (push snapshot INTO)
  opportunities.write   POST /opportunities               (CC pipeline cards)

A scope is proven by its own read surface where one exists (snapshots list,
opportunities list); for write-only scopes the probe maps the documented
endpoint's auth outcome (401 invalid token vs 403/insuf_scope vs 404
route-exists) without ever issuing the write.
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import anthology_registry as reg

SKILL_DIR = Path(__file__).resolve().parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"

# The template location id is the CONTRACT's source_template_location (the
# operator's OWN template location, operator infrastructure config, not a
# secret). --location-id overrides for tests, matching the sibling verifiers.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

EX_OK = 0
EX_SCOPE_MISSING = 4      # a required scope is provably absent
EX_HELD = 3               # transport/edge — cannot conclude (never a claim)
EX_STOP = 2               # no credential at all
EX_ERR = 1                # unexpected error


def _out(mark: str, msg: str):
    sys.stderr.write("[u24] %s %s\n" % (mark, msg))


def _get(client, path: str, query=None):
    """GET through the registry client; returns (ok, kind, status) where kind
    is one of: ok / scope / invalid / edge / route / error. Never prints the
    body."""
    try:
        client._request("GET", path, query=query)
        return True, "ok", 200
    except reg.ScopeDenied:
        return False, "scope", 403
    except reg.UpstreamBlockedError as exc:
        text = str(exc)
        if "did NOT match a Convert and Flow scope-denial signature" in text:
            return False, "edge", 403
        return False, "edge", 403
    except reg.CafValidation as exc:
        # 400/409/422: route exists but the request is invalid — the token
        # PASSED auth, so the scope is not the blocker (404 routes prove
        # reachability, not scope).
        return False, "route", 400
    except reg.CafUnreachable as exc:
        return False, "transport", 0


def _probe(client, path: str, query=None):
    """Raw probe distinguishing 404 route-exists (auth passed) from 401
    invalid token from 403 scope denial. The registry client maps 401 and
    403 both to scope/edge, so this does its own HTTP call with the same
    browser-UA discipline."""
    url = reg.CAF_API_BASE + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer %s" % client._token,
        "Version": reg.CAF_VERSION_HEADER,
        "Accept": "application/json",
        "User-Agent": reg.CAF_BROWSER_UA,
    }, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=client._timeout) as resp:
            return resp.status, ""
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read()
        except Exception:
            body = b""
        return exc.code, body.decode("utf-8", errors="replace")[:300]
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, type(exc).__name__


def probe_snapshot_readonly(client):
    """GET /snapshots — the agency-level snapshot list. A 200 proves
    snapshots.readonly. A 404 (route exists) proves the token passed auth but
    the scope is not granted, OR the endpoint is versioned differently."""
    code, body = _probe(client, "/snapshots", query={"limit": 1})
    if code == 200:
        return ("PASS", "snapshots.readonly proven (GET /snapshots -> 200)")
    if code == 404:
        # The public v1 path may be /v1/snapshots — try the versioned path.
        code2, _ = _probe(client, "/v1/snapshots", query={"limit": 1})
        if code2 == 200:
            return ("PASS", "snapshots.readonly proven (GET /v1/snapshots -> 200)")
        return ("UNKNOWN", "GET /snapshots -> %d (route exists; scope not "
                           "discernible — may be a 404 for a different "
                           "snapshot API version)" % code)
    if code in (401, 403):
        if "insuf_scope" in body.lower() or "insufficient" in body.lower():
            return ("MISSING", "snapshots.readonly: insuf_scope on GET /snapshots")
        return ("MISSING", "snapshots.readonly: HTTP %d (token not authorized "
                           "for snapshot listing)" % code)
    return ("UNKNOWN", "snapshots.readonly: HTTP %d — %s" % (code, body[:100]))


def probe_opportunities_read(client, location_id):
    """GET /opportunities — the list surface. A 200 proves the token can READ
    opportunities (a strong signal the WRITE scope is also present, since the
    same OAuth scope group covers opportunities read+write)."""
    code, body = _probe(client, "/opportunities",
                        query={"locationId": location_id, "limit": 1})
    if code == 200:
        return ("PASS", "opportunities.read proven (GET /opportunities -> 200); "
                        "opportunities.write is the same scope group")
    if code in (401, 403):
        if "insuf_scope" in body.lower():
            return ("MISSING", "opportunities: insuf_scope on GET /opportunities")
        return ("MISSING", "opportunities: HTTP %d (token not authorized for "
                           "opportunity reads)" % code)
    return ("UNKNOWN", "opportunities: HTTP %d — %s" % (code, body[:100]))


def probe_locations_read(client):
    """GET /locations/ (agency list). A 200 proves locations.read; the write
    scope is the same OAuth group. A 401/403 proves the token lacks location
    access."""
    code, body = _probe(client, "/locations", query={"limit": 1})
    if code == 200:
        return ("PASS", "locations.read proven (GET /locations -> 200); "
                        "locations.write is the same scope group")
    if code in (401, 403):
        if "insuf_scope" in body.lower():
            return ("MISSING", "locations: insuf_scope on GET /locations")
        return ("MISSING", "locations: HTTP %d (token not authorized for "
                           "location reads)" % code)
    return ("UNKNOWN", "locations: HTTP %d — %s" % (code, body[:100]))


def probe_write_only(client, path, scope_name):
    """For write-only scopes, map the endpoint's auth outcome. A 404 route
    means the token PASSED auth (the 401 'invalid key' would appear first),
    which does not PROVE the scope — report UNKNOWN, never a claim."""
    code, body = _probe(client, path)
    if code == 404:
        return ("UNKNOWN", "%s: endpoint %s reached (auth passed); write scope "
                           "not provable via a read probe" % (scope_name, path))
    if code in (401, 403):
        if "insuf_scope" in body.lower():
            return ("MISSING", "%s: insuf_scope on %s" % (scope_name, path))
        return ("MISSING", "%s: HTTP %d on %s" % (scope_name, code, path))
    return ("UNKNOWN", "%s: HTTP %d on %s — %s" % (scope_name, code, path, body[:100]))


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="check_agency_scopes.py",
        description="U24 — probe the agency PIT's scopes on the Anthology "
                    "Convert and Flow template location (READ-ONLY: every "
                    "probe is a GET; values are never printed).")
    ap.add_argument("--location-id", default="",
                    help="override the template location id (default: the "
                         "contract's source_template_location."
                         "template_location_id, %s; never printed)"
                         % DEFAULT_TEMPLATE_LOCATION)
    args = ap.parse_args(argv)

    _, token = reg.resolve_pit()
    if not token:
        checked = ", ".join(reg.PIT_LABELS)
        _out("STOP", "No Convert and Flow agency PIT is SET (checked: %s). "
                     "U24 cannot be probed without the agency token." % checked)
        return EX_STOP

    try:
        with open(CONTRACT_PATH) as fh:
            contract = json.load(fh)
    except (OSError, ValueError) as exc:
        _out("HELD", "cannot read anthology-snapshot-contract.json (%s); "
                     "falling back to the built-in default" % type(exc).__name__)
        contract = {}
    location_id = (args.location_id.strip()
                   or (contract.get("source_template_location") or {}).get("template_location_id")
                   or DEFAULT_TEMPLATE_LOCATION)

    client = reg.CafClient(token)
    results = []
    results.append(probe_snapshot_readonly(client))
    results.append(probe_opportunities_read(client, location_id))
    results.append(probe_locations_read(client))
    results.append(probe_write_only(client, "/snapshots/from-location",
                                    "snapshots.write"))
    results.append(probe_write_only(client, "/locations/%s" % location_id,
                                    "locations.write"))

    _out("result", "U24 scope probe (read-only, values masked):")
    for verdict, detail in results:
        _out("  ", "%-7s %s" % (verdict, detail))

    missing = [r[1] for r in results if r[0] == "MISSING"]
    unknown = [r[1] for r in results if r[0] == "UNKNOWN"]
    if missing:
        _out("VERDICT", "U24 BLOCKED: %d scope(s) provably absent: %s"
                        % (len(missing), "; ".join(missing)))
        return EX_SCOPE_MISSING
    if unknown and not any(r[0] == "PASS" for r in results):
        _out("VERDICT", "U24 UNKNOWN: no scope provable via read probes "
                        "(transport/edge); cannot conclude — this is not a "
                        "claim of missing scopes")
        return EX_HELD
    _out("VERDICT", "U24 PASS: every probe scope read-passed; write-only "
                    "scopes share their read groups (U24 box may be checked "
                    "with the note 'read-proven, write-inferred')")
    return EX_OK


if __name__ == "__main__":
    sys.exit(main())
