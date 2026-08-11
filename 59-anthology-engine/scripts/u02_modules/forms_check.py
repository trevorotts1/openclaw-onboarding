#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u02_modules.forms_check
# THE THREE FORM CHECK — universal-intake / universal-review / title-select
# against the engine's contract (MASTER-SPEC U02 item 3; the U02 tooling set
# alongside live_verify_template.py, which counts forms from the internal-rail
# /workflow list but never names them).
# -----------------------------------------------------------------------------
# THE THREE FORMS (slug -> contract role):
#   universal-intake        -> forms.required[0].role  "universal-author-intake"
#   universal-review        -> the engine's one client-facing decision form
#                              (PRD Section 4; U8: the cover SINGLE_OPTIONS
#                              dropdown the client picks from in the
#                              universal-review cover field). Deliberately NOT
#                              in the snapshot contract's required/bound lists:
#                              it is a NAMED form, not a count row — the
#                              snapshot contract counts 1+3 forms and this
#                              check asserts the three named ones against the
#                              live form rows of the same rail listing.
#   title-select            -> forms.contract_bound_per_anthology[0].role
#                              "title-subtitle-selection" (S3).
# The "universal hidden-field contract" (contact_id / anthology_id / stage) is
# the contract's forms.universal_hidden_fields, asserted byte-exact for every
# required and contract-bound form, exactly as qc-snapshot-contract.sh and
# live_verify_template.check_forms assert it.
#
# CREDENTIALS: by LABEL, never by value. The private-integration token is
# resolved through anthology_registry.resolve_pit (the house labels
# CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY / GOHIGHLEVEL_API_KEY /
# GOHIGHLEVEL_PIT / GHL_API_KEY, live process env first, then the three
# canonical client env stores). The optional internal-rail (Firebase) refresh
# token resolves through reg.resolve_firebase_refresh_token. SET / NOT SET
# only on every operator surface; a token value is NEVER printed.
#
# BROWSER UA: every request rides reg.CafClient / reg.InternalRailClient,
# which apply CAF_BROWSER_UA so the Cloudflare edge fronting
# services.leadconnectorhq.com never 1010s the check (the W0.6/GK-09
# discipline; urllib's default "Python-urllib/x.y" is 403'd at the edge, CF
# error 1010, before it reaches the API). Scope-vs-edge-block discrimination:
# a bare 401/403 is HELD (UpstreamBlockedError), never reported as a scope
# problem — the exact Wave 5 false-positive guard.
#
# FAIL-CLOSED (the whole point): a missing credential STOPS (exit 2), a
# transport/edge failure is HELD (exit 3), a rail read that cannot be
# performed is DEFERRED (never fabricated — snapshot-cut doctrine), and ANY
# absent form or drifted hidden-field contract is a FAIL (exit 5). A success
# is claimed ONLY when every requested form row exists on the live listing
# AND every one of its hidden fields is present in the universal contract
# (a strict subset is a FAIL, never a pass). The three form SLUGS are asserted
# on every successful read — no slug, no pass.
#
# STDLIB ONLY (urllib + json + argparse); calls NO model. Reuses
# anthology_registry for the client, the rail, and label resolution — the same
# bootstrap live_verify_template.py uses. DOCTRINE: move in silence,
# operator-verbose only; NOTHING Anthropic in any runtime file; Convert and
# Flow naming in every client surface; never print a secret value.
#
# EXIT CODES (house convention 0/1/2/3/5):
#   0  all three forms found, every hidden field inside the universal contract
#      (also --dry-run plan pass)
#   1  unexpected error
#   2  STOP refusal — a credential label NOT SET / non-pit- token / usage
#   3  Convert and Flow API unreachable / internal rail unavailable (HELD)
#   5  a form missing, hidden-field drift, or a DEFERRED live read without
#      --allow-deferred (fail-closed, never fabricated)
# =============================================================================
"""forms_check.py — check the three named Convert and Flow forms
(universal-intake / universal-review / title-select) against the engine's
contract. Returns {ok, found, missing}; fail-closed, never prints a token."""

from __future__ import annotations

import argparse
import gzip
import io
import json
import sys
import urllib.error
import urllib.parse
from pathlib import Path

# Sibling import bootstrap (house convention, identical to live_verify_template.py):
# the registry does the Cloudflare browser-UA wiring + LeadConnector client +
# internal-rail client, and its label resolution is the house credential contract.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"

# The three named forms this check exists for. SLUG is the Convert and Flow
# form slug; ROLE is the contract role that names the same form. The
# universal-review slug is the engine's own name for the PRD Section 4
# decision form (not a snapshot-contract count row) — see the header.
FORM_SLUGS = ("universal-intake", "universal-review", "title-select")

# The FORM_ID of each slug on the operator's OWN template location — a
# location identifier, not a secret. Live-verified 2026-08-11 against the
# internal-rail trigger surface (the ONLY form-read surface this repo has
# proven; Skill 44 doctrine — never an invented endpoint):
#   universal-intake -> the active form_submission trigger of "Anthology
#       Intake Fire" carries form.id [U65pwoeMTy1niMqllKWG], BYTE-EQUAL to
#       anthology_book.py DEFAULT_UNIVERSAL_INTAKE_FORM_ID (the minted link
#       the engine ships), and the Review/Title fires carry their own forms.
#   universal-review -> riNlAkYbcW3g92VRLqq0, the Review Fire trigger AND the
#       form the release emails link (widget/form/<id>?anthology_id=..&stage=..).
#   title-select     -> UgiiSoZsA4vyqOVfO5fi, the Title Fire trigger AND the
#       S3 title-and-subtitle link in "Release: Titles".
# The FIRE-trigger is the proof: a form record (not the widget URL) lives on
# the template location and fires the engine's webhook. The universal hidden
# fields are asserted from the contract (there is no proven per-form read
# surface) — the hidden-field contract of every required/bound form is the
# snapshot contract's universal_hidden_fields, asserted byte-exact.
FORM_ID_BY_SLUG = {
    "universal-intake": "U65pwoeMTy1niMqllKWG",
    "universal-review": "riNlAkYbcW3g92VRLqq0",
    "title-select": "UgiiSoZsA4vyqOVfO5fi",
}

# The template location id is the CONTRACT's source_template_location (the
# operator's OWN template location, operator infrastructure config, not a
# secret). The check pins to it; --location-id overrides for tests.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

# The internal-rail surfaces this repo has PROVEN live (Podcast gate; snapshot
# cut; live_verify_template item 3): the /workflow/{loc}/list listing, the
# per-workflow GET, and the per-workflow TRIGGER read. Forms have NO proven
# read surface of their own on the rail (a by-id GET 404s, verified
# 2026-08-11) — the check proves each form THROUGH its ACTIVE form_submission
# trigger instead. READ-ONLY GETs.
RAIL_WORKFLOW_LIST = "/workflow/{loc}/list?limit=200"
RAIL_WORKFLOW_TRIGGER = "/workflow/{loc}/trigger?workflowId={wid}"

# A genuine Convert and Flow location-scope refusal carries its own JSON
# signature ("does not have access to this location") that is NOT the registry
# scope-denial substring. The registry's _auth_denial_kind deliberately
# matches only the W0.5 pipeline scope text, so a location-scope denial reads
# "blocked" and HELDs. Live-verified 2026-08-11: the template location
# (2HIKGNgsixWx0yds7Qnx) and the configured client location both return
# {"statusCode":403,"message":"The token does not have access to this
# location."} for every PIT-scoped read, while the SAME transport's internal
# rail (Firebase-JWT) returns rows OK and pipelines OK on the same location —
# the PIT here is template/client-location-scoped and the live form rows ride
# the rail. This signature IS recognized so a location-scope denial surfaces
# as a STOP (exit 2), never a HELD misdiagnosis.
LOCATION_ACCESS_DENIAL_SIGNATURE = "does not have access to this location"


class FormsCheckError(Exception):
    """A fail-closed verification refusal (STOP or mismatch family)."""


def _request_error_kind(exc) -> str:
    """Classify a request error into a STOP ('location-scope') or HELD
    ('blocked') family. Accepts a urllib HTTPError OR a registry
    UpstreamBlockedError (whose __context__ is the original HTTPError). The
    registry's own classifier matches only the W0.5 pipeline scope text, so
    this module recognizes the live-verified Convert and Flow LOCATION-scope
    signature in addition, and a location-denied token STOPS instead of
    reading as an edge block. Edge blocks and everything else stay HELD
    (retryable) — never mislabeled as scope. Fail-closed: a body that is
    already consumed (the registry read it once) is undecidable by body and
    classifies HELD — never a fabricated scope STOP from a header alone."""
    body = b""
    if not isinstance(exc, urllib.error.HTTPError):
        # A registry UpstreamBlockedError re-raised from a LOCATION-scope
        # denial keeps the ORIGINAL HTTPError as its __context__ (raised
        # inside the except handler). The HTTPError's body was consumed for
        # the registry's own W0.5-scope check and is not re-readable, but
        # the RESPONSE HEADERS survive — and the live location-scope body is
        # plaintext JSON under a Content-Length header with no
        # Content-Encoding. Unwrap BEFORE judging.
        ctx = exc.__context__
        if isinstance(ctx, urllib.error.HTTPError):
            exc = ctx
    if isinstance(exc, urllib.error.HTTPError):
        # The response body is read ONCE per error and the registry's own
        # _request already consumed it (the registry reads the body to
        # classify before re-raising UpstreamBlockedError) — a second read
        # here returns b"", so the text check would never see the signature.
        # The Content-Encoding header survives (None = plaintext): a header
        # of gzip means the (possibly already-consumed) body was compressed.
        ce = ""
        try:
            ce = str(exc.headers.get("Content-Encoding") or "").lower()
        except AttributeError:
            ce = ""  # a header-less error (tests) is plaintext
        except Exception:
            ce = ""
        cl = ""
        try:
            cl = str(exc.headers.get("Content-Length") or "").strip()
        except AttributeError:
            cl = ""
        except Exception:
            cl = ""
        # The body is read ONCE per error: the registry's own _request ALREADY
        # consumed it (it reads to classify before re-raising
        # UpstreamBlockedError), so a second read on the live error returns
        # b"" and the signature is undecidable by body -> HELD, never a scope
        # STOP from a header alone. The STOP branch is reached only by the
        # FRESH path (the probe's except handler, before any other consumer),
        # where the read succeeds and the plaintext JSON carries the
        # location-scope signature.
        try:
            body = exc.read()
        except Exception:
            body = b""
        if not body:
            return "blocked"  # consumed (registry read it) -> undecidable -> HELD
        if ce == "gzip" and body[:2] == b"\x1f\x8b":
            try:
                body = gzip.decompress(body)
            except OSError:
                body = b""
    text = (body or b"").decode("utf-8", "replace")
    if LOCATION_ACCESS_DENIAL_SIGNATURE in text:
        return "location-scope"
    # The registry's _auth_denial_kind inspects only its own fixed signature
    # ("not authorized for this scope") against the text; when the body is
    # unreadable (a wrapped error) or carries another signature, it returns
    # "blocked" — re-check the text here so a location-scope denial read
    # through either path is caught. The registry signature check remains the
    # authoritative W0.5 scope test.
    if "not authorized for this scope" in text:
        return "scope"
    return "blocked"


def _contract_forms(contract: dict) -> dict:
    return contract.get("forms") or {}


def _universal_hidden_fields(contract: dict) -> list:
    return list((_contract_forms(contract)).get("universal_hidden_fields") or [])


def _role_hidden_fields(contract: dict, role: str):
    """The hidden-field list of the contract row whose role is `role`, or None
    when no row carries it (required + contract_bound_per_anthology, exactly
    the surfaces qc-snapshot-contract.sh and live_verify_template read)."""
    forms = _contract_forms(contract)
    for f in list(forms.get("required") or []):
        if isinstance(f, dict) and f.get("role") == role:
            return f.get("hidden_fields")
    for f in list(forms.get("contract_bound_per_anthology") or []):
        if isinstance(f, dict) and f.get("role") == role:
            return f.get("hidden_fields")
    return None


def _read_contract(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FormsCheckError("cannot read %s: %s" % (path, exc)) from exc
    except ValueError as exc:
        raise FormsCheckError("%s is not valid JSON: %s" % (path, exc)) from exc
    if not isinstance(data, dict):
        raise FormsCheckError("%s does not parse to a JSON object" % path)
    return data


def _live_trigger_form_ids(rail, location_id: str) -> dict:
    """Read every ACTIVE form_submission trigger on the location and index the
    form ids they fire. The trigger surface is the form-read this repo has
    PROVEN live (live-verified 2026-08-11 on the template location: the
    Anthology Intake/Review/Title Fire workflows each carry one ACTIVE
    form_submission trigger on form.id). A failed read raises
    InternalRailUnavailable — the caller HELDs exactly as live_verify_template
    does. Returns {form_id: [workflow_name, ...]}."""
    out = rail._get(RAIL_WORKFLOW_LIST.format(loc=location_id))
    rows = out.get("rows") or []
    if not isinstance(rows, list):
        raise reg.InternalRailUnavailable("unexpected rail listing shape")
    found = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("type") != "workflow":
            continue
        wid = row.get("id")
        if not wid:
            continue
        trigs = rail._get(RAIL_WORKFLOW_TRIGGER.format(loc=location_id, wid=wid))
        for t in (trigs or []):
            if not isinstance(t, dict) or t.get("type") != "form_submission":
                continue
            if t.get("active") is not True:
                continue
            for cond in (t.get("conditions") or []):
                if not isinstance(cond, dict) or cond.get("field") != "form.id":
                    continue
                vals = cond.get("value") or []
                if isinstance(vals, str):
                    vals = [vals]
                for fid in vals:
                    if isinstance(fid, str) and fid:
                        found.setdefault(fid, []).append(row.get("name") or "?")
    return found


def _live_forms(location_id: str, *, rail=None) -> dict:
    """The live form-id index to compare against. Fail-closed: without the
    internal rail there is NO proven public-v2 forms read surface in this
    repo (Skill 44 doctrine — never invent one), so the read is DEFERRED.
    An explicit rail (self-tests) is used as given; a missing rail raises
    InternalRailUnavailable and the caller defers — never fabricates."""
    if rail is None:
        raise reg.InternalRailUnavailable("no internal rail — live form rows not readable")
    return _live_trigger_form_ids(rail, location_id)


def check_forms(location_id: str, contract: dict, *, rail=None) -> dict:
    """Check the three named forms against the contract and the live trigger
    surface.

    Returns the documented surface {ok, found, missing} — fail-closed:
      - every requested slug's FORM ID must appear among the location's ACTIVE
        form_submission triggers (a slug whose id is not fired is recorded in
        `missing` and ok is False),
      - a slug whose id appears on an INACTIVE trigger only, or whose id is
        absent, is missing — an active fire is the only proof,
      - a DEFERRED live read (no rail) never fabricates: it is reported with
        ok False and missing [] — the caller decides exit 5 vs. an
        --allow-deferred acceptance,
      - the contract itself is asserted offline: the universal hidden fields
        must be exactly [contact_id, anthology_id, stage] and the universal
        hidden-field contract must appear on every required/bound row.
    Never raises for a data mismatch (a mismatch is a result); raises only
    for a broken rail (InternalRailUnavailable, held) or a broken contract
    (FormsCheckError, stop/mismatch family).
    """
    forms = _contract_forms(contract)
    universal = _universal_hidden_fields(contract)

    # ---- offline contract assertion (the same gates the snapshot QC runs) --
    if universal != ["contact_id", "anthology_id", "stage"]:
        raise FormsCheckError(
            "forms.universal_hidden_fields drifted: %r != [contact_id, anthology_id, stage]"
            % (universal,))
    # The role rows are checked against the universal contract, not the count
    # (the count belongs to qc-snapshot-contract.sh / live_verify_template).
    for role in ("universal-author-intake", "title-subtitle-selection"):
        if _role_hidden_fields(contract, role) != universal:
            raise FormsCheckError(
                "contract role %r hidden fields %r != universal contract %r"
                % (role, _role_hidden_fields(contract, role), universal))

    # ---- live read (fail-closed: no rail -> DEFERRED, never fabricated) ----
    try:
        live = _live_forms(location_id, rail=rail)
    except reg.InternalRailUnavailable as exc:
        return {
            "ok": False,
            "found": [],
            "missing": [],
            "deferred": True,
            "note": "live form reads not readable without the internal rail: %s — "
                    "never fabricated (exit 5 unless --allow-deferred)" % exc,
        }

    missing = []
    detail = []
    for slug in FORM_SLUGS:
        fid = FORM_ID_BY_SLUG.get(slug, "")
        if not fid or fid not in live:
            missing.append(slug)
            continue
        detail.append("%s (id %s) fired by %s" % (slug, fid, ", ".join(live[fid])))
    ok = not missing
    return {
        "ok": ok,
        "found": [s for s in FORM_SLUGS if s not in missing],
        "missing": missing,
        "deferred": False,
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: golden + attack fixtures, no network, no secrets.
# ---------------------------------------------------------------------------
class _FakeRail:
    """In-memory internal rail serving workflow rows + per-workflow triggers,
    mirroring the live listing/trigger shape the check reads."""

    def __init__(self, rows=None, outcome="ok"):
        self._rows = list(rows or [])
        self._outcome = outcome
        self.calls = []

    def _get(self, path):
        self.calls.append(path)
        if self._outcome == "unavailable":
            raise reg.InternalRailUnavailable("fixture: rail unavailable")
        if "/trigger?" in path:
            import re
            m = re.search(r"workflowId=([^&]+)", path)
            wid = m.group(1) if m else ""
            for r in self._rows:
                if r.get("id") == wid:
                    return [dict(t) for t in (r.get("trigger") or [])]
            return []
        return {"rows": [dict(r) for r in self._rows]}


def _fake_contract():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _golden_rows():
    """The live shape verified 2026-08-11: each of the three Fire workflows
    carries ONE ACTIVE form_submission trigger on its form id. Each row is a
    workflow LIST row (type workflow) whose per-workflow TRIGGER read returns
    the form_submission trigger — exactly the two-surface read the check
    performs."""
    out = []
    for i, fid in enumerate(FORM_ID_BY_SLUG.values()):
        out.append({"id": "wf-%d" % i, "name": "Fire %d" % i, "type": "workflow",
                    "trigger": [{"workflow_id": "wf-%d" % i,
                                 "type": "form_submission", "active": True,
                                 "conditions": [{"field": "form.id",
                                                 "value": [fid]}]}]})
    return out


def _self_test_body(dev) -> None:
    contract = _fake_contract()
    expected = [("universal-intake", "universal-author-intake"),
                ("title-select", "title-subtitle-selection")]
    # 0. the location-scope 403 signature (live-verified 2026-08-11) is
    #    classified STOP, never HELD
    loc_denial = urllib.error.HTTPError("loc", 403,
                                        "Forbidden",
                                        hdrs=None,
                                        fp=io.BytesIO(b'{"statusCode":403,'
                                                      b'"message":"The token does not '
                                                      b'have access to this location."}'))
    assert _request_error_kind(loc_denial) == "location-scope", \
        "location-scope 403 must classify as location-scope"
    edge_denial = urllib.error.HTTPError("loc", 403, "Forbidden", hdrs=None,
                                         fp=io.BytesIO(b"<html>cf 1010</html>"))
    assert _request_error_kind(edge_denial) == "blocked", \
        "edge 403 must classify as blocked (HELD)"
    # a gzip-encoded body with the Content-Encoding header -> decompressed
    # and classified (the header survives even after the body is consumed)
    gz_denial = urllib.error.HTTPError(
        "loc", 403, "Forbidden",
        hdrs={"Content-Encoding": "gzip"},
        fp=io.BytesIO(gzip.compress(b'{"statusCode":403,"message":"The token '
                                     b'does not have access to this location."}')))
    assert _request_error_kind(gz_denial) == "location-scope", \
        "a gzip-encoded location-scope 403 must still classify as location-scope"
    # a CONSUMED body (the registry read it first, the live shape) with no
    # Content-Encoding header -> the text path still sees plaintext when the
    # fp is re-openable; when it is empty -> blocked (HELD), never scope
    consumed = urllib.error.HTTPError("loc", 403, "Forbidden", hdrs=None,
                                      fp=io.BytesIO(b""))
    consumed.read()  # simulate the registry's prior read
    assert _request_error_kind(consumed) == "blocked", \
        "a consumed empty body must classify as blocked (HELD)"

    # 1. golden: all three active fires -> ok True, found all three, missing []
    res = check_forms("loc_tmpl", contract, rail=_FakeRail(_golden_rows()))
    assert res["ok"] is True, "golden rows must pass, got %r" % res
    assert res["found"] == list(FORM_SLUGS), "found drift: %r" % res["found"]
    assert res["missing"] == [] and res.get("deferred") is False

    # 2. one slug's form id not fired -> fail-closed, missing names it
    rows = [dict(r) for r in _golden_rows() if r["id"] != "wf-1"]
    res = check_forms("loc_tmpl", contract, rail=_FakeRail(rows))
    assert res["ok"] is False and res["missing"] == ["universal-review"], \
        "missing must name the absent slug, got %r" % res

    # 3. trigger exists but INACTIVE -> the form is NOT proven -> missing
    rows = [dict(r) for r in _golden_rows()]
    rows[1]["trigger"][0]["active"] = False
    res = check_forms("loc_tmpl", contract, rail=_FakeRail(rows))
    assert res["ok"] is False and res["missing"] == ["universal-review"], \
        "an inactive trigger must not prove the form, got %r" % res

    # 4. a form id fired on a DIFFERENT field (not form.id) -> not proven
    rows = [dict(r) for r in _golden_rows()]
    rows[1]["trigger"][0]["conditions"] = [{"field": "tag.value", "value": ["x"]}]
    res = check_forms("loc_tmpl", contract, rail=_FakeRail(rows))
    assert res["ok"] is False and res["missing"] == ["universal-review"], \
        "a non-form.id condition must not prove the form, got %r" % res

    # 5. contract hidden-field drift -> FormsCheckError (never a blind pass)
    bad = json.loads(json.dumps(contract))
    bad["forms"]["universal_hidden_fields"] = ["contact_id", "stage"]
    try:
        check_forms("loc_tmpl", bad, rail=_FakeRail(_golden_rows()))
        raise AssertionError("universal hidden-field drift must refuse")
    except FormsCheckError:
        pass

    # 6. rail unavailable -> DEFERRED, never fabricated, never ok
    res = check_forms("loc_tmpl", contract, rail=_FakeRail(outcome="unavailable"))
    assert res["ok"] is False and res.get("deferred") is True, "no rail must defer, got %r" % res
    assert res["missing"] == [], "a deferred read never claims a missing form"

    dev.write("forms_check self-test: OK (golden all-three active-fire pass, "
              "missing-slug names it, inactive-trigger not-proven, wrong-field "
              "not-proven, contract drift refused, rail-unavailable "
              "deferred-never-fabricated, location-scope 403 STOP vs edge 403 "
              "HELD, gzip-encoded 403 body still classified)\n")


def self_test(out=None) -> int:
    import io
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        out.write("[forms-check] SELF-TEST FAILED: %s\n" % exc)
        return 4  # enforced violation (the house self-test convention)
    out.write(dev.getvalue())
    return EX_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="forms_check.py",
        description="Check the three named Convert and Flow forms "
                    "(universal-intake / universal-review / title-select) against "
                    "the engine's contract. Returns {ok, found, missing}. "
                    "Fail-closed; never prints a token (Skill 59, U02 tooling).")
    ap.add_argument("--location-id", default="",
                    help="override the template location id (default: the contract's "
                         "source_template_location.template_location_id, %s; never "
                         "printed)" % DEFAULT_TEMPLATE_LOCATION)
    ap.add_argument("--contract", default=str(CONTRACT_PATH),
                    help="path to anthology-snapshot-contract.json")
    ap.add_argument("--allow-deferred", action="store_true",
                    help="explicit operator opt-in: accept a DEFERRED live read "
                         "(internal-rail credential NOT SET) as PASS — the result "
                         "still records the deferral")
    ap.add_argument("cmd", nargs="?", choices=["check", "plan", "self-test"], default="check")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()

        contract = _read_contract(Path(args.contract).expanduser())
        location_id = (args.location_id.strip() or
                       (contract.get("source_template_location") or {}).get("template_location_id")
                       or DEFAULT_TEMPLATE_LOCATION)

        if args.cmd == "plan":
            # offline plan: no network, no credentials
            print(json.dumps({
                "contract": "anthology-engine-forms-check-plan",
                "schema_version": 1,
                "template_location_id": location_id,
                "forms": list(FORM_SLUGS),
                "universal_hidden_fields": _universal_hidden_fields(contract),
                "note": "offline plan only — no network, no credential needed; "
                        "the live check reads the internal-rail form rows "
                        "(never fabricated)",
            }, indent=2, sort_keys=True))
            return EX_OK

        # ---- live check ----
        pit_label, token = reg.resolve_pit()
        if not token:
            checked = ", ".join(reg.PIT_LABELS)
            reg._stop(sys.stderr, "No Convert and Flow private-integration token is SET.",
                      ["Checked (in order): %s — all NOT SET." % checked,
                       "The check runs against the operator's OWN template location %s; "
                       "set the template PIT (client-standard labels first) and re-run."
                       % location_id])
            return EX_STOP
        # The READ probe doubles as the scope proof; the token value itself is
        # never printed — the client applies CAF_BROWSER_UA on every request.
        # The registry's own classifier matches only the W0.5 pipeline scope
        # text, so a Convert and Flow LOCATION-scope denial ("does not have
        # access to this location", live-verified 2026-08-11 on this operator
        # box) surfaces as an UpstreamBlockedError (HELD). It is reclassified
        # here as a STOP (exit 2) — never a HELD misdiagnosis. The probe does
        # its OWN raw read (the registry consumes the body before it re-
        # raises, so the wrapped error cannot be re-read) and classifies the
        # FRESH error, whose body still carries the plaintext JSON signature.
        probe_denied = False
        try:
            reg.CafClient(token).list_custom_fields(location_id)
        except reg.UpstreamBlockedError:
            # Re-run the raw read to classify the FRESH body (the registry
            # consumed the first one; a second read of the same error is
            # empty). A genuine location-scope denial STOPS here.
            import urllib.request as _ur
            url = reg.CAF_API_BASE + "/locations/%s/customFields" % urllib.parse.quote(location_id, safe="")
            req = _ur.Request(
                url,
                headers={"Authorization": "Bearer %s" % token,
                         "Version": reg.CAF_VERSION_HEADER,
                         "Accept": "application/json",
                         "User-Agent": reg.CAF_BROWSER_UA})
            try:
                with _ur.urlopen(req, timeout=15):
                    pass  # a 2xx now — the probe raced; proceed to the check
            except urllib.error.HTTPError as exc2:
                probe_denied = (_request_error_kind(exc2) == "location-scope")
            except Exception:
                pass  # any transport failure is the check's business; HELD below
        if probe_denied:
            reg._stop(sys.stderr,
                      "The Convert and Flow token cannot READ this location "
                      "(\"does not have access to this location\").",
                      ["Location marker: %s" % reg._mask_location(location_id),
                       "The token resolved from a PIT label is not location-scoped "
                       "to it (the live forms ride the internal rail, not the PIT). "
                       "Grant the template PIT access to the template location, "
                       "or point --location-id at the location the PIT can read.",
                       "AF-AE-PIT-SCOPE family: STOP, never a silent fallback."])
            return EX_STOP

        # Internal rail (optional): without a Firebase refresh token the live
        # form rows are DEFERRED (never fabricated) and the result is fail-
        # closed unless --allow-deferred.
        rail = None
        rlabel, rtoken = reg.resolve_firebase_refresh_token()
        if rtoken:
            _, api_key = reg._resolve_firebase_api_key() or (None, "")
            rail = reg.InternalRailClient(rtoken, api_key) if api_key else None
        if rail is None:
            sys.stderr.write("[forms-check] internal-rail refresh token NOT SET — the live "
                             "form read will be DEFERRED (fail-closed, never fabricated). "
                             "Set one of %s to read the live form rows.\n"
                             % ", ".join(reg.FIREBASE_REFRESH_LABELS))

        result = check_forms(location_id, contract, rail=rail)

        if result.get("deferred"):
            result["template_location_id"] = location_id
            print(json.dumps(result, indent=2, sort_keys=True))
            if not args.allow_deferred:
                sys.stderr.write("[forms-check] DEFERRED (fail-closed): the live form read "
                                 "was not performed — re-run with the Firebase refresh token "
                                 "BY LABEL or pass --allow-deferred to accept the deferral "
                                 "explicitly. Never fabricated.\n")
                return EX_MISMATCH
            return EX_OK

        print(json.dumps(result, indent=2, sort_keys=True))
        return EX_OK if result.get("ok") else EX_MISMATCH

    except reg.ScopeDenied as exc:
        sys.stderr.write("[forms-check] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[forms-check] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[forms-check] HELD: %s\n" % exc)
        return EX_HELD
    except reg.InternalRailUnavailable as exc:
        sys.stderr.write("[forms-check] HELD: %s\n" % exc)
        return EX_HELD
    except FormsCheckError as exc:
        sys.stderr.write("[forms-check] STOP/FAIL: %s\n" % exc)
        return EX_STOP
    except urllib.error.HTTPError as exc:
        # The probe raises this only when the CafClient itself translated the
        # 403 — no location-scope signature in it; the raise path above could
        # not see it. Reclassify from the original response body; a genuine
        # location-scope denial STOPS, an edge block stays HELD.
        if _request_error_kind(exc) == "location-scope":
            reg._stop(sys.stderr,
                      "The Convert and Flow token cannot READ this location "
                      "(\"does not have access to this location\").",
                      ["Location marker: %s" % reg._mask_location(location_id),
                       "The token resolved from a PIT label is not location-scoped "
                       "to it (the live forms ride the internal rail, not the PIT). "
                       "Grant the template PIT access to the template location, "
                       "or point --location-id at the location the PIT can read.",
                       "AF-AE-PIT-SCOPE family: STOP, never a silent fallback."])
            return EX_STOP
        sys.stderr.write("[forms-check] HELD: HTTP %s (edge/upstream block)\n" % exc.code)
        return EX_HELD
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[forms-check] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
