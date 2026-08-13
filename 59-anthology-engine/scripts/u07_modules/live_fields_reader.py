#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u07_modules/live_fields_reader.py
# LIVE CUSTOM-FIELDS READER — the read surface of the U07 family: it reads
# the contact custom fields of a Convert and Flow (LeadConnector v2) location
# through the PROVEN public rail GET /locations/{locationId}/customFields
# (services.leadconnectorhq.com, the W0.5-verified surface documented in
# 29-ghl-convert-and-flow/references/custom-fields.md and already proven live
# by the engine's own anthology_registry.CafClient.list_custom_fields — the
# same call the U02 fields_check.py and the provision path exercise) and
# does NOTHING else. This module has NO write surface and NO ACTION verb:
# it is read-only by construction — there is nothing here an --execute flag
# could unlock. Fail-closed by design: a missing credential, an unreachable
# rail, an edge block, or an unparseable listing is a refusal with a typed
# reason — never a fabricated field list.
#
# WHY THE PUBLIC RAIL: U07's mandate is the LIVE READ of the custom-field
# inventory (the shape the U02 byte-exact gate judges against). The public
# v2 surface GET /locations/{locationId}/customFields is the PROVEN rail for
# that read — it is the exact call the engine's own provision/verify path
# makes (anthology_registry.list_custom_fields, exercised live by
# fields_check.py and by the U02 verify workflows). A response body is NEVER
# surfaced (it could echo a credential); only parsed field records, and the
# record fields the read legitimately carries — name, fieldKey, id, dataType
# — are surfaced with the id masked to its last 4 chars (house masking
# discipline; full ids ride inside request URLs only). A read is a truthful
# snapshot of the live inventory: an EMPTY field set is a correct answer, an
# unparseable body is HELD.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The read rides the client's OWN
# private-integration token resolved via anthology_registry (CONVERT_AND_FLOW_
# PIT / CONVERT_AND_FLOW_API_KEY / GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT /
# GHL_API_KEY — live process env first, then the three canonical client env
# stores, with the pit- prefix validated so a placeholder is refused) and a
# location id resolved the same way (CONVERT_AND_FLOW_LOCATION_ID /
# GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID), overridable with
# --location-id. Every credential is reported as LABEL + SET / NOT-SET only —
# a value is NEVER printed, echoed, or logged. The location id and every
# field id are MASKED on operator surfaces (last 4 chars, non-reversible);
# full ids ride inside request URLs only.
#
# BROWSER UA (CF 1010): the request rides reg.CafClient, whose every request
# carries CAF_BROWSER_UA (W0.6 / GK-09 discipline) so the Cloudflare edge
# fronting services.leadconnectorhq.com never 1010s the urllib default
# "Python-urllib" UA before the request reaches the API (the exact failure
# mode that 403s at the WAF edge with CF error 1010). A 401/403 is
# classified by the body signature: a genuine scope denial is a STOP, a
# non-matching edge block is HELD — a bare status is NEVER a verdict.
#
# EXIT CODES (house convention 0/1/2/3/4/5):
#   0  PASS — live listing returned and the report printed (including an
#      EMPTY custom-field set — an empty inventory is a truthful, correct
#      answer)
#   1  unexpected error
#   2  STOP refusal — credential labels NOT SET, or a GENUINE scope denial
#      (the response body matched the Convert and Flow scope signature)
#   3  HELD — API unreachable / edge-blocked (incl. the Cloudflare edge 403,
#      UNDETERMINED never a verdict) / malformed listing — retryable, never
#      a fabricated field list
#   4  self-test FAILED (an offline assertion tripped; a tamper NEVER
#      masquerades as exit 1)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr;
# self-test is OFFLINE and needs NO token and NO network; the live read
# needs the client's OWN pit- token BY LABEL):
#   live_fields_reader.py list [--location-id ID]   # live fields, sorted
#   live_fields_reader.py self-test                 # offline fixtures
#   live_fields_reader.py --json list [...]         # JSON report on stdout
#
# Read-only: no --execute exists because there is no ACTION — an --execute
# flag on a module with nothing to execute would be theater; the gate it
# represents (Trevor-gated destructive action) does not apply to a read.
#
# STDLIB ONLY (urllib + json via the registry); calls NO model. Reuses
# anthology_registry (CafClient, resolve_pit, resolve_location,
# _mask_location, ScopeDenied, UpstreamBlockedError, CafUnreachable,
# CAF_BROWSER_UA). DOCTRINE: move in silence; operator-verbose only;
# NOTHING Anthropic in any runtime file; Convert and Flow naming in every
# client surface; NEVER print a secret value.
# =============================================================================
"""live_fields_reader.py — live Convert and Flow contact custom-field reader
via the proven public rail GET /locations/{id}/customFields (U07 tooling).
Read-only by construction: no write surface, no ACTION, no --execute."""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + the REST client, and its label resolution
# is the house credential contract.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH
EX_SELFTEST = 4  # self-test FAILED (an offline assertion tripped)

# The ONE surface this module reads — the PROVEN public rail (W0.5-verified,
# documented in 29-ghl-convert-and-flow/references/custom-fields.md, and the
# exact call anthology_registry.list_custom_fields makes — the same read the
# U02 fields_check gate and the provision path exercise live). The read is
# READ-ONLY by construction; there is no write surface and no ACTION verb,
# so no --execute gate exists (nothing to gate).
REPORT_CONTRACT = "anthology-engine-live-fields-reader"

# The response envelope key of the public rail (anthology_registry reads it).
FIELDS_KEY = "customFields"

# Known data types for classification. A field whose dataType is missing or
# unknown is SURFACED (never silently judged): the report counts it under
# unknown-data-type and still carries the record — a read does not get to
# guess what an unknown type means.
KNOWN_DATA_TYPES = (
    "TEXT", "LARGE_TEXT", "SINGLE_OPTIONS", "MULTIPLE_OPTIONS", "RADIO",
    "CHECKBOX", "DATE", "DATETIME", "TIME", "NUMBER", "EMAIL", "PHONE",
    "URL", "ADDRESS", "FILE", "FULL_ADDRESS",
)


# ---------------------------------------------------------------------------
# Fail-closed listing helpers. Pure: never raise beyond ValueError, never
# print secrets.
# ---------------------------------------------------------------------------
def _mask_id(rid: str) -> str:
    """Non-reversible resource-id marker (last 4 chars) for operator
    surfaces. The full id rides inside request URLs only, never on a
    surface."""
    rid = (rid or "").strip()
    return ("..." + rid[-4:]) if len(rid) >= 4 else "...(short)"


def rows_from_read(raw) -> list:
    """The custom-field records of a rail read. A non-dict body, a missing
    or non-list 'customFields' key, or a non-object record REFUSES (raises
    ValueError) — an unparseable body is a HELD, never an empty list (an
    empty list would silently read as 'no fields')."""
    if not isinstance(raw, dict):
        raise ValueError("customFields read is not a JSON object")
    rows = raw.get(FIELDS_KEY)
    if rows is None:
        raise ValueError("customFields read carries no %r array" % FIELDS_KEY)
    if not isinstance(rows, list):
        raise ValueError("customFields read's %r is not an array" % FIELDS_KEY)
    if not all(isinstance(r, dict) for r in rows):
        raise ValueError("customFields read carries a non-object record")
    return rows


def _field_rows(rows: list) -> list:
    """Only the object records, in read order (rows_from_read already
    refused non-objects; this guard is belt-and-suspenders for callers who
    pass an untrusted list)."""
    return [r for r in rows if isinstance(r, dict)]


def list_fields(raw) -> tuple:
    """(rows, dropped) — the parsed records and the count of records dropped
    for missing name or fieldKey (a record without a fieldKey cannot be the
    subject of a byte-exact bind, so it is never listed — the count is
    surfaced, never a silent drop). Raises ValueError on a malformed read
    (fail-closed). Pure: never prints."""
    rows = _field_rows(rows_from_read(raw))
    kept = [r for r in rows
            if (r.get("name") or "").strip() and (r.get("fieldKey") or "").strip()]
    dropped = len(rows) - len(kept)
    return kept, dropped


def read_ok(raw) -> bool:
    """A read that parses (raises nothing) is structurally OK. Pure."""
    try:
        list_fields(raw)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# The live list command — the ONLY network surface (proven public rail).
# ---------------------------------------------------------------------------
def _build_report(raw: dict, *, location_id: str) -> dict:
    """The machine report for a parsed read: sorted field-key inventory plus
    counts and the masked location. Each field row carries ONLY the record
    surface the read legitimately carries — name, masked id, fieldKey and
    dataType — never a body, never a credential, never a full id. A record
    whose name, fieldKey, id or dataType is blank/missing is DROPPED with
    the count surfaced (it cannot be the subject of a byte-exact bind), and
    a record with an unknown dataType is still carried (a read does not
    guess). Pure."""
    kept, dropped = list_fields(raw)
    rows = _field_rows(rows_from_read(raw))
    unknown_type = 0
    fields = []
    for r in kept:
        name = str(r.get("name") or "").strip()
        fkey = str(r.get("fieldKey") or "").strip()
        fid = str(r.get("id") or "").strip()
        dtype = str(r.get("dataType") or "").strip()
        if not name or not fkey or not fid:
            dropped += 1
            continue
        if dtype not in KNOWN_DATA_TYPES:
            unknown_type += 1
        fields.append({
            "name": name,
            "fieldKey": fkey,
            "id": _mask_id(fid),
            "dataType": dtype or "(unset)",
        })
    fields.sort(key=lambda f: f["fieldKey"])
    return {
        "ok": True,
        "contract": REPORT_CONTRACT,
        "schema_version": 1,
        "action": "list",
        "location": _mask_id(location_id),
        "fields": fields,
        "field_count": len(fields),
        "rows": len(rows),
        "rows_dropped": dropped,
        "rows_unknown_data_type": unknown_type,
    }


def live_list_command(location_id: str, *, out=None, jsonout=None,
                      environ=None) -> int:
    """List the location's contact custom fields through the PROVEN public
    rail. Credential: the client's OWN private-integration token under the
    standard pit- labels; SET/NOT-SET only, value never printed. A rail
    failure or an unparseable read is HELD (exit 3) — never a fabricated
    field list. `environ` is the registry's self-test injection point (an
    explicit env dict blocks the canonical-store fallback, so the STOP
    credential gate is deterministic OFFLINE)."""
    out = out or sys.stderr
    # The registry's resolve_pit validates the pit- prefix but takes no
    # environ injection point; resolve BY LABEL through the same store list
    # here (mirroring resolve_pit's prefix validation) so the self-test's
    # empty-environ gate is deterministic OFFLINE — an explicit env dict
    # blocks the canonical-store fallback, so the STOP credential gate
    # fires BEFORE any network (same contract workflow_lister documents for
    # the Firebase resolver).
    pit_label, token = reg._env_first(reg.PIT_LABELS, environ)
    if token and not token.startswith(reg.PIT_PREFIX):
        # Resolved a value under a PIT label, but it is not a pit- token.
        # Refuse WITHOUT printing it (mirrors reg.resolve_pit).
        pit_label, token = pit_label, None
    if not token:
        checked = ", ".join(reg.PIT_LABELS)
        if pit_label:
            out.write("[live-fields-reader] STOP: a Convert and Flow token "
                      "is SET under %s but is not a valid private-integration "
                      "token (pit- prefix). The value is not printed. Checked "
                      "(in order): %s\n" % (pit_label, checked))
        else:
            out.write("[live-fields-reader] STOP: no Convert and Flow "
                      "private-integration token is SET. Checked (in order): "
                      "%s — all NOT SET. The live read needs the client's "
                      "OWN token; the offline self-test needs none.\n"
                      % checked)
        return EX_STOP
    loc_label, loc = reg.resolve_location(location_id)
    if not loc:
        out.write("[live-fields-reader] STOP: no Convert and Flow location "
                  "id SET (labels: %s).\n" % ", ".join(reg.LOCATION_LABELS))
        return EX_STOP
    out.write("[live-fields-reader] PIT resolved via %s (SET). Location via "
              "%s (marker %s).\n"
              % (pit_label, loc_label, reg._mask_location(loc)))
    masked = reg._mask_location(loc)
    try:
        client = reg.CafClient(token)
        raw = client.list_custom_fields(loc)
    except reg.ScopeDenied as exc:
        out.write("[live-fields-reader] STOP: %s (marker %s)\n" % (exc, masked))
        return EX_STOP
    except (reg.UpstreamBlockedError, reg.CafUnreachable) as exc:
        out.write("[live-fields-reader] HELD: public-rail customFields read "
                  "failed (marker %s): %s\n" % (masked, exc))
        return EX_HELD
    try:
        report = _build_report(raw, location_id=loc)
    except ValueError as exc:
        out.write("[live-fields-reader] HELD: customFields read malformed "
                  "(marker %s): %s\n" % (masked, exc))
        return EX_HELD
    if jsonout is not None:
        json.dump(report, jsonout, indent=2)
        jsonout.write("\n")
    else:
        out.write("[live-fields-reader] LIVE customFields (marker %s): %d "
                  "field(s), %d row(s), %d dropped (no name/fieldKey/id), "
                  "%d unknown data-type\n"
                  % (masked, report["field_count"], report["rows"],
                     report["rows_dropped"], report["rows_unknown_data_type"]))
        for f in report["fields"]:
            out.write("  %s (%s) %s %s\n"
                      % (f["fieldKey"], f["name"], f["dataType"], f["id"]))
    return EX_OK


# ---------------------------------------------------------------------------
# CLI surface (tiny, deterministic; used by the sibling scripts and tests).
# ---------------------------------------------------------------------------
def main(argv=None, environ=None):
    """Dispatch the CLI. Every command prints ONE JSON object on stdout
    (jsonout) and human notes on stderr; --json toggles stdout to the
    machine report. Never prints a credential, a token, a full id, or a
    response body. list and self-test are the surfaces (self-test is
    OFFLINE — needs no token and no network; list's happy path is the ONE
    live read, proven public rail, and its credential gate STOPS before any
    network when the client's own pit- token is not SET). Read-only module:
    no ACTION, no --execute. `environ` is the self-test injection point
    (deterministic offline gates)."""
    if argv is None:
        argv = sys.argv[1:]
    ap = argparse.ArgumentParser(
        prog="live_fields_reader.py", add_help=False,
        description="Live Convert and Flow contact custom-field reader "
                    "(Skill 59 U07) via the proven public rail "
                    "GET /locations/{id}/customFields. Fail-closed; "
                    "read-only by construction (no --execute — there is "
                    "nothing to gate); credentials BY LABEL, never printed; "
                    "browser UA CAF_BROWSER_UA on every request (CF 1010).")
    ap.add_argument("--help", "-h", action="store_true")
    ap.add_argument("--json", action="store_true",
                    help="machine report on stdout (ONE JSON object)")
    ap.add_argument("--location-id", default="",
                    help="Convert and Flow location id (default: env labels "
                         "CONVERT_AND_FLOW_LOCATION_ID / "
                         "GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID)")
    ap.add_argument("cmd", nargs="?", default="",
                    choices=["list", "self-test"])
    args = ap.parse_args(argv)

    if args.help or not args.cmd:
        sys.stdout.write(
            "live_fields_reader.py -- Skill 59 U07 live custom-field reader\n"
            "  list [--location-id ID]      live contact custom fields via the\n"
            "                               proven public rail (needs the\n"
            "                               client's OWN pit- token BY LABEL;\n"
            "                               NEVER printed)\n"
            "  self-test                     offline fixtures, no network, no\n"
            "                               secrets\n"
            "  --json                        ONE JSON object on stdout\n"
            "Exit codes: 0 PASS (incl. an EMPTY field set); 2 STOP (no\n"
            "credential SET / genuine scope denial); 3 HELD (rail unreachable\n"
            "or edge-blocked or malformed read); 4 self-test FAILED.\n"
            "Read-only module: no ACTION, no --execute.\n")
        return EX_OK if args.cmd else EX_STOP

    if args.cmd == "self-test":
        return self_test()

    # list — read-only, needs no --execute.
    try:
        return live_list_command(args.location_id,
                                 out=sys.stderr,
                                 jsonout=sys.stdout if args.json else None,
                                 environ=environ)
    except ValueError as exc:
        sys.stderr.write("[live-fields-reader] STOP: %s\n" % exc)
        return EX_STOP


# ---------------------------------------------------------------------------
# Self-test — OFFLINE golden + attack fixtures, no network, no secrets.
# ---------------------------------------------------------------------------
def self_test():
    """Offline acceptance battery. Any failure prints a one-line note to
    stderr and returns 4; the happy path prints 'live_fields_reader
    self-test: OK' to stderr and returns 0. Never touches the network; never
    prints a token or a full id."""
    dev = io.StringIO()

    # -- the golden read (the proven public-rail envelope: customFields) ------
    golden_raw = {
        "customFields": [
            {"name": "Anthology Avatar Doc URL", "fieldKey": "contact.anthology_avatar_doc_url",
             "id": "fld_0001", "dataType": "LARGE_TEXT"},
            {"name": "Anthology Cover Choice", "fieldKey": "contact.anthology_cover_choice",
             "id": "fld_0002", "dataType": "SINGLE_OPTIONS"},
            {"name": "Anthology Client Email", "fieldKey": "contact.anthology_client_email",
             "id": "fld_0003", "dataType": "EMAIL"},
        ]}

    # 1. list_fields: all three records kept, nothing dropped
    kept, dropped = list_fields(golden_raw)
    assert len(kept) == 3 and dropped == 0, \
        "golden read must keep all three records: %d kept, %d dropped" % (len(kept), dropped)

    # 2. the report carries the field surface only — never full ids
    report = _build_report(golden_raw, location_id="2HIKGNgsixWx0yds7Qnx")
    assert report["ok"] is True and report["action"] == "list"
    assert report["field_count"] == 3 and report["rows"] == 3
    assert report["location"].startswith("..."), "location must be masked"
    assert "2HIKGNgsixWx0yds7Qnx" not in json.dumps(report), \
        "the full location id must never reach the report"
    assert "fld_0001" not in json.dumps(report), \
        "the full field id must never reach the report"
    assert all(f["id"].startswith("...") for f in report["fields"]), \
        "every field id must be masked"
    assert [f["fieldKey"] for f in report["fields"]] == sorted(
        f["fieldKey"] for f in report["fields"]), "fields must be sorted by key"

    # 3. an EMPTY field set is a truthful, correct answer (exit-0 family)
    report_empty = _build_report({"customFields": []}, location_id="2HIKGNgsixWx0yds7Qnx")
    assert report_empty["ok"] is True and report_empty["field_count"] == 0 \
        and report_empty["rows"] == 0, "an empty inventory must be a PASS"

    # 4. an unknown dataType is surfaced, never judged
    odd = {"customFields": [
        {"name": "Odd", "fieldKey": "contact.odd", "id": "fld_9", "dataType": "WEIRD"}]}
    report_odd = _build_report(odd, location_id="loc")
    assert report_odd["rows_unknown_data_type"] == 1, \
        "unknown dataType must be counted, got %d" % report_odd["rows_unknown_data_type"]
    assert report_odd["field_count"] == 1, "the odd record must still be carried"

    # 5. ragged records (no name / no fieldKey / no id) drop WITH the count
    ragged = {"customFields": [
        {"name": "", "fieldKey": "contact.blank_name", "id": "fld_1", "dataType": "TEXT"},
        {"name": "No Key", "fieldKey": "", "id": "fld_2", "dataType": "TEXT"},
        {"name": "No Id", "fieldKey": "contact.no_id", "id": "", "dataType": "TEXT"},
        {"name": "Good", "fieldKey": "contact.good", "id": "fld_3", "dataType": "TEXT"}]}
    report_rag = _build_report(ragged, location_id="loc")
    assert report_rag["field_count"] == 1, \
        "only the complete record may be listed, got %r" % report_rag["fields"]
    assert report_rag["rows_dropped"] == 3, \
        "the three ragged records must be dropped WITH the count, got %d" \
        % report_rag["rows_dropped"]

    # -- ATTACK fixtures: every malformed read REFUSED (fail-closed) ---------
    # 6. malformed reads refuse (never an empty list). A record that is a
    #    dict but misses name/fieldKey is NOT malformed — it is a ragged
    #    record and drops WITH the count (fixture 5); malformed means the
    #    envelope or a row is not the expected shape at all.
    for bad in (None, [], "text", {}, {"nope": True},
                {"customFields": "not-a-list"},
                {"customFields": ["scalar"]}):
        try:
            _build_report(bad, location_id="loc")
        except ValueError:
            pass
        else:
            raise AssertionError("malformed read must refuse: %r" % (bad,))
        try:
            list_fields(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("malformed read must refuse in list_fields: %r" % (bad,))

    # -- the live command surface: deterministic OFFLINE gates ----------------
    # The offline contract (an explicit EMPTY environ blocks the canonical
    # env-store fallback, so the STOP credential gate is deterministic with
    # zero network): no command is a STOP (help-less), and a credential-less
    # list STOPS before any network (never a fabricated field list). The
    # live-network happy path is NOT exercised here: when the client's own
    # pit- token is live (as on this box) it performs the real live read, and
    # the CLI gate tests cannot depend on live state, so they assert only the
    # pre-network refusals (which are env-independent).
    empty_env = {}
    rc_help = main([], environ=empty_env)
    assert rc_help == EX_STOP, "no command must STOP, got %r" % rc_help
    rc_creds = main(["list"], environ=empty_env)
    assert rc_creds == EX_STOP, \
        "list without credentials must STOP (never a fabricated list), got %r" % rc_creds

    sys.stderr.write("live_fields_reader self-test: OK "
                     "(golden read parsed/sorted/masked, empty-inventory "
                     "PASS, unknown-data-type surfaced, ragged records "
                     "dropped with the count, 7 malformed reads refused "
                     "fail-closed, credential-less list STOPS before any "
                     "network)\n")
    return EX_OK


if __name__ == "__main__":
    sys.exit(main())
