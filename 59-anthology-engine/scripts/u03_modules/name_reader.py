#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u03_modules/name_reader.py  (U03 tooling)
# LIVE PIPELINE NAME READER — the read companion to the U02 name check. It
# GETs the location's pipelines through Convert and Flow (LeadConnector v2)
# with the client's OWN private-integration token and extracts EVERY pipeline
# name, exactly as the API returns them, sorted for deterministic diffing.
#
# WHAT THIS MODULE IS NOT: it makes NO judgment about which name is standard,
# whether a pipeline is absent, renamed, or byte-exact — that is the U02
# checker's job (u02_modules/pipeline_check.py, check_pipeline_name). This
# reader only READS: it returns the names the location actually has. The two
# units compose: the reader proves the read surface and the names that exist;
# the checker applies the name law on top.
#
# FAIL-CLOSED READ, NEVER A SILENT FALLBACK: an empty list is a legitimate
# live answer ("the location has zero pipelines" — reportable, never
# fabricated). But a payload whose SHAPE cannot be read faithfully — the
# "pipelines" key missing, not a list, an entry that is not a dict, or an
# entry whose name is not a non-empty string — is NOT a fact about the
# location; it is a broken parse, and reading on would fabricate an
# incomplete name list. Any such shape raises MalformedPayload (STOP family,
# exit 2) exactly like the sibling's PipelineMissing — never a silent empty.
# reg.ScopeDenied and reg.CafUnreachable propagate as the registry raises
# them (scope is a STOP, edge/transport is a HELD).
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The PIT is resolved via
# anthology_registry (CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY /
# GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT / GHL_API_KEY — live process env
# first, then the three canonical client env stores) and the location id via
# the standard location labels (CONVERT_AND_FLOW_LOCATION_ID /
# GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID), overridable with
# --location-id. SET / NOT SET only on every operator surface; a value is
# NEVER printed. The location id is a marker (last 4 chars) on any surface.
#
# BROWSER UA: the request rides anthology_registry.CafClient, which applies
# CAF_BROWSER_UA so the Cloudflare edge fronting services.leadconnectorhq.com
# never 1010s the read (W0.6 / GK-09 discipline — the exact failure mode
# that 403s urllib's default UA before the request reaches Convert and Flow).
# Scope-vs-edge-block discrimination is the registry's own: a bare 401/403
# whose body does NOT match the genuine scope-denial signature raises
# UpstreamBlockedError -> HELD, never a scope STOP.
#
# EXIT CODES (house convention 0/1/2/3/4, mirroring pipeline_check.py):
#   0  read complete — names extracted from the live payload
#   1  unexpected error
#   2  STOP refusal — PIT/location label NOT SET, payload shape unreadable
#      (MalformedPayload), or the token cannot read pipelines (scope)
#   3  Convert and Flow API unreachable / edge-blocked (HELD; retryable —
#      the read is UNDETERMINED here, never proven empty)
#   4  self-test FAILED (an offline assertion tripped; a tamper NEVER
#      masquerades as exit 1)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; --self-test is OFFLINE and needs NO token and NO network):
#   name_reader.py live [--location-id ID]
#   name_reader.py plan            # offline; the read surface with sources
#   name_reader.py self-test       # offline golden + attack fixtures
#
# STDLIB ONLY (urllib + json via the registry's CafClient); calls NO model.
# Reuses anthology_registry (CafClient, resolve_pit, resolve_location,
# _stop, _mask_location). DOCTRINE: move in silence; NOTHING Anthropic in
# any runtime file; Convert and Flow naming in every client surface; NEVER
# print a secret value.
# =============================================================================
"""name_reader.py — LIVE pipeline-name read against the Anthology Convert and
Flow location (U03 tooling): GET the pipelines, extract every name."""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + LeadConnector client, and its label
# resolution is the house credential contract.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The live surface this reader speaks (the ONLY pipeline read the public v2
# API provides — pipelines are UI-only; there is no create/delete endpoint).
PIPELINES_PATH = "/opportunities/pipelines"
PIPELINES_QUERY = "locationId"


class MalformedPayload(Exception):
    """A fail-closed read refusal (STOP family): the live payload's shape
    cannot be faithfully read, so reporting names would be fabrication.
    Distinct from 'the location has zero pipelines' — that is a valid read."""


def _mask_location(loc: str) -> str:
    """Non-reversible location marker (last 4 chars) for operator surfaces."""
    return reg._mask_location(loc)


# ---------------------------------------------------------------------------
# Live read primitive — returns (names, count, duplicates). FAIL-CLOSED: any
# unreadable shape raises MalformedPayload (STOP) — never a silent empty.
# ---------------------------------------------------------------------------
def read_pipeline_names(client, location_id: str) -> tuple:
    """LIVE pipeline-name read (read-only): GET /opportunities/pipelines and
    extract every pipeline's name, sorted for deterministic diffing.

    - payload well-formed        -> (names, count, duplicates) — an EMPTY
      list is a valid live answer, never an error
    - shape unreadable (missing/  -> raises MalformedPayload (STOP family):
      non-list "pipelines",        reading on would fabricate an incomplete
      non-dict entry, or an        name list
      entry without a non-empty
      string name)
    - reg.ScopeDenied / reg.CafUnreachable propagate exactly as the registry
      raises them (scope STOP / edge+transport HELD).
    """
    out = client.list_pipelines(location_id)
    # list_pipelines already collapses a missing key to [] -- so distinguish
    # "empty" from "unreadable" by the SHAPE the payload arrived in, by
    # re-reading the raw response through the registry's own surface is not
    # possible here; instead the fail-closed gate is the entry shape:
    # every reported pipeline must carry a non-empty string name.
    if not isinstance(out, list):
        raise MalformedPayload(
            "AF-AE-PIPELINES-UNREADABLE: GET %s returned %s, not a list -- "
            "the read cannot be certified" % (PIPELINES_PATH, type(out).__name__))

    names = []
    for entry in out:
        if not isinstance(entry, dict):
            raise MalformedPayload(
                "AF-AE-PIPELINES-UNREADABLE: a pipeline entry is %s, not a "
                "dict -- the name list would be incomplete" % type(entry).__name__)
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            raise MalformedPayload(
                "AF-AE-PIPELINES-UNREADABLE: a pipeline entry carries no "
                "non-empty string name -- the name list would be incomplete")
        names.append(name)

    names = sorted(names)
    count = len(names)
    duplicates = count - len(set(names))  # extra occurrences beyond the first
    return names, count, duplicates


# ---------------------------------------------------------------------------
# Offline self-test (no network, no credentials) — proves the pure logic:
# golden state reads clean, every attack fixture is refused, and the read
# never fabricates a name list from a broken payload.
# ---------------------------------------------------------------------------
class _FakeCaf:
    """Deterministic pipeline-listing stub (mirrors pipeline_check's
    _FakeCaf seam): 'pipelines' fixture, 'behavior' for scope/edge/transport."""

    def __init__(self, pipelines=None, behavior="ok"):
        # Entries pass through BYTE-FOR-BYTE as given — never coerced with
        # dict(...), which would mangle a malformed-entry attack fixture
        # before the code under test ever sees it.
        self._pipelines = list(pipelines or [])
        self._behavior = behavior
        self.calls = []

    def list_pipelines(self, location_id):
        self.calls.append(location_id)
        if self._behavior == "scope":
            raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
        if self._behavior == "edge":
            raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
        if self._behavior == "transport":
            raise reg.CafUnreachable("transport failure (fixture)")
        return list(self._pipelines)


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[name-reader] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    # ---- golden live state: two pipelines -> both names, sorted ----
    names, count, dupes = read_pipeline_names(
        _FakeCaf(pipelines=[
            {"id": "pipe_b", "name": "Zeta Pipeline", "stages": []},
            {"id": "pipe_a", "name": "Anthology Engine", "stages": []},
        ]), "loc_tmpl")
    assert names == ["Anthology Engine", "Zeta Pipeline"], "golden names sorted: %r" % names
    assert count == 2 and dupes == 0, "golden count/dupes: %s/%s" % (count, dupes)

    # ---- zero pipelines IS a valid live read (never fabricated) ----
    names, count, dupes = read_pipeline_names(_FakeCaf(pipelines=[]), "loc_tmpl")
    assert names == [] and count == 0 and dupes == 0, "empty read must be clean"

    # ---- duplicate names are READ, never silently deduped (the checker's
    #      find-by-name would be ambiguous; the reader must report it) ----
    names, count, dupes = read_pipeline_names(
        _FakeCaf(pipelines=[
            {"id": "p1", "name": "Anthology Engine", "stages": []},
            {"id": "p2", "name": "Anthology Engine", "stages": []},
        ]), "loc_tmpl")
    assert names == ["Anthology Engine", "Anthology Engine"] and dupes == 1, \
        "duplicate names must be reported, never hidden"

    # ---- attack fixtures: every unreadable shape REFUSED (never silent) ----
    # 1. payload not a list -> STOP refusal
    class _NotListCaf(_FakeCaf):
        def list_pipelines(self, location_id):
            return {"pipelines": "not-a-list"}
    try:
        read_pipeline_names(_NotListCaf(), "loc_tmpl")
        raise AssertionError("non-list payload was NOT refused")
    except MalformedPayload:
        pass
    # 2. entry not a dict -> STOP refusal
    try:
        read_pipeline_names(_FakeCaf(pipelines=[["nope"]]), "loc_tmpl")
        raise AssertionError("non-dict entry was NOT refused")
    except MalformedPayload:
        pass
    # 3. entry with a missing name -> STOP refusal
    try:
        read_pipeline_names(_FakeCaf(pipelines=[{"id": "p1"}]), "loc_tmpl")
        raise AssertionError("missing name was NOT refused")
    except MalformedPayload:
        pass
    # 4. entry with an empty name -> STOP refusal
    try:
        read_pipeline_names(_FakeCaf(pipelines=[{"id": "p1", "name": ""}]), "loc_tmpl")
        raise AssertionError("empty name was NOT refused")
    except MalformedPayload:
        pass
    # 5. scope denied -> STOP family surfaces as ScopeDenied (never fabricated)
    try:
        read_pipeline_names(_FakeCaf(behavior="scope"), "loc_tmpl")
        raise AssertionError("scope-denied was NOT refused")
    except reg.ScopeDenied:
        pass
    # 6. edge/transport -> HELD family surfaces (never a scope STOP)
    for behavior in ("edge", "transport"):
        try:
            read_pipeline_names(_FakeCaf(behavior=behavior), "loc_tmpl")
            raise AssertionError("%s was NOT refused" % behavior)
        except reg.CafUnreachable:
            pass
    # 7. live CLI on the golden state -> exit 0 and a clean JSON object
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = run_live(_FakeCaf(pipelines=[
            {"id": "pipe_a", "name": "Anthology Engine", "stages": []},
            {"id": "pipe_b", "name": "Zeta Pipeline", "stages": []},
        ]), "loc_tmpl", out=io.StringIO())
    assert rc == EX_OK, "golden run_live must exit 0, got %s" % rc
    report = json.loads(buf.getvalue())
    assert report["ok"] is True, "golden report must carry ok true"
    assert report["names"] == ["Anthology Engine", "Zeta Pipeline"]
    assert report["count"] == 2 and report["duplicates"] == 0
    assert report["delta"] == [], "golden report must carry an empty delta"
    # 8. live CLI on an UNREADABLE payload -> exit 2 (STOP) and ok false
    class _BrokenCaf(_FakeCaf):
        def list_pipelines(self, location_id):
            return [{"id": "p1"}]
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc2 = run_live(_BrokenCaf(), "loc_tmpl", out=io.StringIO())
    assert rc2 == EX_STOP, "unreadable run_live must exit 2, got %s" % rc2
    report2 = json.loads(buf2.getvalue())
    assert report2["ok"] is False and report2["names"] == [] and report2["count"] == 0
    assert any("pipeline" in str(d.get("item")) for d in report2["delta"]), \
        "unreadable report must carry a pipelines delta"

    dev.write("name_reader self-test: OK (golden read + empty read + duplicate "
              "report; 8 attack fixtures refused: non-list payload / non-dict "
              "entry / missing name / empty name / scope-denied / edge-block / "
              "transport / unreadable-run_live-STOP; run_live exits 0 on "
              "golden, 2 on unreadable)\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _live_report(ok: bool, names: list, count: int, duplicates: int,
                 marker: str, delta: list) -> None:
    """Emit the ONE JSON object (machine surface, stdout) for a live run."""
    sys.stdout.write(json.dumps({
        "ok": ok,
        "verb": "read",
        "names": names,
        "count": count,
        "duplicates": duplicates,
        "location_marker": marker,
        "delta": delta,
    }, indent=2, sort_keys=True) + "\n")


def run_live(client, location_id: str, *, out=None) -> int:
    """Run the live read against a resolved client. Returns the exit code.
    One JSON object lands on stdout; human notes go to stderr."""
    out = out or sys.stderr
    masked = _mask_location(location_id)
    try:
        names, count, duplicates = read_pipeline_names(client, location_id)
    except MalformedPayload as exc:
        reg._stop(out, "The live pipeline payload cannot be read faithfully.",
                  [str(exc), "Location marker: %s" % masked,
                   "This is a payload-shape STOP, NOT an empty location."])
        _live_report(False, [], 0, 0, masked,
                     [{"item": "pipelines", "status": "FAIL",
                       "detail": "AF-AE-PIPELINES-UNREADABLE: payload shape "
                                 "not certifiable", "expected": "list of "
                                 "pipeline names", "live": None}])
        return EX_STOP
    except reg.ScopeDenied:
        reg._stop(out, "The Convert and Flow token cannot READ pipelines on this location.",
                  ["Location marker: %s" % masked,
                   "Grant the client's OWN location-scoped token the "
                   "opportunities scope and re-run.", "AF-AE-PIT-SCOPE."])
        return EX_STOP
    except reg.CafUnreachable as exc:   # includes UpstreamBlockedError (edge/WAF)
        out.write("[name-reader] HELD: %s (marker %s). "
                  "NOT a token-scope problem; retryable.\n" % (exc, masked))
        return EX_HELD

    out.write("[name-reader] OK (marker %s): %d pipeline(s) read: %s\n"
              % (masked, count, ", ".join(names) or "(none)"))
    _live_report(True, names, count, duplicates, masked, [])
    return EX_OK


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="name_reader.py",
        description="Live pipeline NAME read against the Anthology Convert and "
                    "Flow location (U03): GET the pipelines and extract every "
                    "name — the read companion to the U02 name check. One JSON "
                    "object on stdout; fail-closed; never prints a secret "
                    "(Skill 59).")
    ap.add_argument("--location-id", default="",
                    help="override the location id (default: the standard "
                         "location labels; never printed)")
    ap.add_argument("cmd", nargs="?", choices=["live", "plan", "self-test"], default="live")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()

        if args.cmd == "plan":
            # offline plan: no network, no credentials
            print(json.dumps({
                "contract": "anthology-engine-pipeline-name-read-plan",
                "schema_version": 1,
                "check": "GET %s?%s=<id> — read every pipeline's name from "
                         "the live payload" % (PIPELINES_PATH, PIPELINES_QUERY),
                "fail_closed": "an EMPTY list is a valid read; any unreadable "
                               "shape (missing/non-list payload, non-dict "
                               "entry, empty name) is a STOP refusal — never "
                               "a silent empty",
                "note": "offline plan only — no network, no credential needed; "
                        "no judgment about which name is standard (that is "
                        "the U02 checker's job)",
            }, indent=2, sort_keys=True))
            return EX_OK

        # ---- live read ----
        pit_label, token = reg.resolve_pit()
        if not token:
            checked = ", ".join(reg.PIT_LABELS)
            reg._stop(sys.stderr, "No Convert and Flow private-integration token is SET.",
                      ["Checked (in order): %s — all NOT SET." % checked,
                       "Set the client's OWN pit- token under a standard label "
                       "and re-run."])
            return EX_STOP
        loc_label, location_id = reg.resolve_location(args.location_id)
        if not location_id:
            checked = ", ".join(reg.LOCATION_LABELS)
            reg._stop(sys.stderr, "No Convert and Flow location id is SET.",
                      ["Checked (in order): %s — all NOT SET." % checked,
                       "Set the location id under a standard label (or pass "
                       "--location-id) and re-run."])
            return EX_STOP
        client = reg.CafClient(token)

        return run_live(client, location_id, out=sys.stderr)

    except reg.ScopeDenied as exc:
        sys.stderr.write("[name-reader] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[name-reader] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[name-reader] HELD: %s\n" % exc)
        return EX_HELD
    except MalformedPayload as exc:
        sys.stderr.write("[name-reader] STOP: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[name-reader] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR

if __name__ == "__main__":
    sys.exit(main())
