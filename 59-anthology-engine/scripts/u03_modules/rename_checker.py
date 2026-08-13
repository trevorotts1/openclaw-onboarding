#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u03_modules/rename_checker.py  (U03 tooling)
# RENAME CHECKER — the smallest fail-closed live probe of the U03 family: it
# READS the location's pipelines through Convert and Flow (LeadConnector v2)
# with the client's OWN private-integration token and reports whether a
# pipeline named BYTE-EXACT "Anthology Engine" exists. A RENAMED pipeline is
# indistinguishable from an ABSENT one to find-by-name (MASTERDOC floor 11;
# anthology_registry.py provision-pipeline binds BY NAME), so BOTH refuse —
# the check NEVER fails open and NEVER auto-heals a drift.
#
# WHY A DEDICATED MODULE: the U03 units re-verify the template location's
# DRIFT-PRONE live state (pipeline name, stage set, workflow folder, intake
# route) WITHOUT touching the U02 scope. This module is deliberately NARROWER
# than u02_modules/pipeline_check.py (name only — stage order/position
# belong to the U03 stage verifier) and is a REUSABLE IMPORT
# (check_name -> dict) so the U03 gates and operators' live runs share ONE
# implementation of the name law.
#
# CONTRACT (this is the WHOLE law, fail-closed):
#   name == "Anthology Engine" — byte-for-byte equal. Any other value —
#   renamed, cased differently, suffixed, empty, whitespace — is a FAIL.
#   The expected name comes from the committed contract
#   config/field-map.json pipeline.standard_pipeline_name (SPEC M8: never
#   hardcoded), which is currently "Anthology Engine" and is pinned by the
#   offline self-test.
#
# LIVE SURFACE: GET /opportunities/pipelines?locationId=<id> — the ONLY
# pipeline read the public v2 API provides. The request rides
# anthology_registry.CafClient, which applies CAF_BROWSER_UA on every request
# so the Cloudflare edge fronting services.leadconnectorhq.com never 1010s
# the check (W0.6 / GK-09 discipline — the exact failure mode that 403s
# urllib's default "Python-urllib/x.y" User-Agent before the request reaches
# Convert and Flow). Scope-vs-edge-block discrimination is the registry's
# own: a bare 401/403 whose body does NOT match the genuine scope-denial
# signature raises UpstreamBlockedError -> HELD, never a scope STOP.
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
# EXIT CODES (house convention 0/1/2/3/5; drift in the name law is the STOP
# family, exit 2):
#   0  the standard pipeline is present and BYTE-EXACT (name match)
#   1  unexpected error
#   2  STOP refusal — PIT/location label NOT SET, non-pit- value, or the
#      standard pipeline is ABSENT or RENAMED on the location
#      (AF-AE-TEMPLATE-PIPELINE-MISSING; find-and-bind would fail silently)
#   3  Convert and Flow API unreachable / edge-blocked (HELD; retryable —
#      the scope is UNDETERMINED here, never proven absent)
#   5  self-test FAILED (an offline assertion tripped; a tamper NEVER
#      masquerades as exit 1)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; --self-test is OFFLINE and needs NO token and NO network):
#   rename_checker.py live [--location-id ID]
#   rename_checker.py plan            # offline; the name law with sources
#   rename_checker.py self-test       # offline golden + attack fixtures
#
# STDLIB ONLY (urllib + json); calls NO model. Reuses anthology_registry
# (CafClient, resolve_pit, resolve_location, load_field_map, _stop,
# _mask_location). DOCTRINE: move in silence; NOTHING Anthropic in any
# runtime file; Convert and Flow naming in every client surface; NEVER print
# a secret value.
# =============================================================================
"""rename_checker.py — fail-closed name check: name == "Anthology Engine"."""

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
EX_SELFTEST_FAIL = 5  # offline self-test FAILED (never masquerades as exit 1)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

# The expected name is NEVER hardcoded here (SPEC M8): it comes from the
# committed contract config/field-map.json pipeline.standard_pipeline_name,
# the SAME source of truth provision-pipeline binds by. A drift in the
# contract is caught by the offline self-test (golden state must match it).
_expected_name = (
    (reg.load_field_map(FIELD_MAP_PATH).get("pipeline") or {}).get("standard_pipeline_name") or "")


def _mask_location(loc: str) -> str:
    """Non-reversible location marker (last 4 chars) for operator surfaces."""
    return reg._mask_location(loc)


# ---------------------------------------------------------------------------
# The check — returns a dict {"ok", "current", "expected"}. FAIL-CLOSED:
# any non-byte-exact name is ok False (never skipped, never fabricated).
# ---------------------------------------------------------------------------
def check_name(client, location_id: str, want: str = "") -> dict:
    """LIVE name check (read-only): the standard pipeline must exist
    BYTE-EXACT on the location.

    Returns {"ok": bool, "current": str, "expected": str} where "expected" is
    the name law's source and "current" is the live pipeline name: the
    byte-exact match's name when found, else the first live pipeline's name
    (a renamed standard pipeline — so a gate can tell RENAMED from ABSENT),
    else "" when the location lists no pipeline at all. NEVER prints a token
    and NEVER raises on a name drift — a mismatch is a reportable FAIL, not
    an exception. reg.ScopeDenied / reg.CafUnreachable (incl.
    UpstreamBlockedError) propagate exactly as the registry raises them.
    """
    want = want or _expected_name
    if not want:
        # Fail closed: no contract source, no name law.
        return {"ok": False, "current": "", "expected": ""}

    pipes = client.list_pipelines(location_id)
    found = next((p for p in pipes if isinstance(p, dict) and p.get("name") == want), None)
    if found is not None:
        current = found.get("name") or ""
    else:
        live = next((p.get("name") for p in pipes
                     if isinstance(p, dict) and p.get("name")), "")
        current = live or ""
    return {"ok": found is not None and current == want, "current": current, "expected": want}


class _NameCheckError(Exception):
    """Unexpected error surfaced by a rename_checker run (fail-closed)."""


# ---------------------------------------------------------------------------
# Offline self-test (no network, no credentials) — proves the pure logic:
# golden state passes, every attack fixture FAILS, and the name law stays
# pinned to the contract source. A tamper NEVER masquerades as exit 1.
# ---------------------------------------------------------------------------
class _FakeCaf:
    """Deterministic pipeline-listing stub (mirrors the registry's CafClient
    seam): 'pipelines' fixture, 'behavior' for scope/edge/transport."""

    def __init__(self, pipelines=None, behavior="ok"):
        self._pipelines = [dict(p) for p in (pipelines or [])]
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
        return [dict(p) for p in self._pipelines]


def _golden_pipeline() -> dict:
    """The contract's standard pipeline as a live-style dict."""
    return {"id": "pipe_tmpl", "name": _expected_name}


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[rename-checker] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_SELFTEST_FAIL
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    want = _expected_name
    assert want, "contract name must not be empty"
    assert want == "Anthology Engine", \
        "standard_pipeline_name drifted from the U03 contract"

    # ---- golden live state: present + byte-exact -> ok True ----
    caf = _FakeCaf(pipelines=[_golden_pipeline()])
    report = check_name(caf, "loc_tmpl")
    assert report["ok"] is True, "golden pipeline must be ok"
    assert report["current"] == want and report["expected"] == want
    assert caf.calls == ["loc_tmpl"], "unexpected calls: %s" % caf.calls

    # ---- attack fixtures: every mutation FAILS (never a silent pass) ----
    # 1. pipeline RENAMED -> ok False (find-by-name cannot bind; byte-exact
    #    is the law — pipeline_check.py semantics); current carries the live
    #    renamed name so a gate can tell RENAMED from ABSENT
    a1 = [dict(_golden_pipeline(), name="Anthology Engine RENAMED")]
    report = check_name(_FakeCaf(pipelines=a1), "loc_tmpl")
    assert report["ok"] is False, "pipeline-renamed was NOT failed"
    assert report["current"] == "Anthology Engine RENAMED"
    assert report["expected"] == want
    # 2. pipeline ABSENT -> ok False
    report = check_name(_FakeCaf(pipelines=[]), "loc_tmpl")
    assert report["ok"] is False and report["current"] == ""
    assert report["expected"] == want
    # 3. extra unrelated pipeline alongside the standard -> ok True
    a3 = [_golden_pipeline(),
          dict(_golden_pipeline(), id="pipe_extra", name="Some Other Pipeline")]
    report = check_name(_FakeCaf(pipelines=a3), "loc_tmpl")
    assert report["ok"] is True, "extra pipeline must not break the name check"
    # 4. whitespace-padded name -> ok False (byte-exact, not .strip())
    a4 = [dict(_golden_pipeline(), name="Anthology Engine ")]
    report = check_name(_FakeCaf(pipelines=a4), "loc_tmpl")
    assert report["ok"] is False, "padded name must fail byte-exact"
    # 5. case drift -> ok False
    a5 = [dict(_golden_pipeline(), name="anthology engine")]
    report = check_name(_FakeCaf(pipelines=a5), "loc_tmpl")
    assert report["ok"] is False, "case drift must fail byte-exact"
    # 6. scope denied -> propagates (never a fabricated pass/fail)
    try:
        check_name(_FakeCaf(behavior="scope"), "loc_tmpl")
        raise AssertionError("scope-denied was NOT refused")
    except reg.ScopeDenied:
        pass
    # 7. edge/transport -> HELD family propagates (never a scope STOP)
    for behavior in ("edge", "transport"):
        try:
            check_name(_FakeCaf(behavior=behavior), "loc_tmpl")
            raise AssertionError("%s was NOT refused" % behavior)
        except reg.CafUnreachable:
            pass
    # 8. live CLI on the golden state -> exit 0 and an ok-true JSON object
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = run_live(_FakeCaf(pipelines=[_golden_pipeline()]), "loc_tmpl", out=io.StringIO())
    assert rc == EX_OK, "golden run_live must exit 0, got %s" % rc
    report = json.loads(buf.getvalue())
    assert report["ok"] is True, "golden report must carry ok true"
    assert report["current"] == want and report["expected"] == want
    # 9. live CLI on a RENAMED pipeline -> exit 2 (STOP) and ok false
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc2 = run_live(_FakeCaf(pipelines=a1), "loc_tmpl", out=io.StringIO())
    assert rc2 == EX_STOP, "renamed run_live must exit 2, got %s" % rc2
    report2 = json.loads(buf2.getvalue())
    assert report2["ok"] is False and report2["current"] == "Anthology Engine RENAMED"
    assert report2["expected"] == want
    # 10. no contract source -> fail closed with an empty expected name
    saved = _expected_name
    try:
        globals()["_expected_name"] = ""
        report = check_name(_FakeCaf(pipelines=[_golden_pipeline()]), "loc_tmpl")
        assert report["ok"] is False and report["current"] == ""
        assert report["expected"] == "", "empty contract must surface an empty expected name"
    finally:
        globals()["_expected_name"] = saved

    dev.write("rename_checker self-test: OK (name law pinned to field-map "
              "pipeline.standard_pipeline_name %r; golden PASS; 10 fixtures: "
              "renamed / absent / extra-pipeline / whitespace-padded / "
              "case-drift FAIL; scope-denied / edge-block / transport "
              "propagate; run_live exits 0 on golden, 2 on renamed)\n" % want)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _live_report(report: dict) -> None:
    """Emit the ONE JSON object (machine surface, stdout) for a live run."""
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")


def run_live(client, location_id: str, *, out=None) -> int:
    """Run the live check against a resolved client. Returns the exit code.
    One JSON object lands on stdout; human notes go to stderr."""
    out = out or sys.stderr
    masked = _mask_location(location_id)
    want = _expected_name
    if not want:
        reg._stop(out, "The pipeline name contract is EMPTY.",
                  ["config/field-map.json pipeline.standard_pipeline_name is empty.",
                   "Restore the contract name and re-run."])
        return EX_MISMATCH
    try:
        report = check_name(client, location_id, want)
    except reg.ScopeDenied:
        reg._stop(out, "The Convert and Flow token cannot READ pipelines on this location.",
                  ["Location marker: %s" % masked,
                   "Grant the client's OWN location-scoped token the opportunities "
                   "scope and re-run.", "AF-AE-PIT-SCOPE."])
        return EX_STOP
    except reg.CafUnreachable as exc:   # includes UpstreamBlockedError (edge/WAF)
        out.write("[rename-checker] HELD: %s (marker %s). "
                  "NOT a token-scope problem; retryable.\n" % (exc, masked))
        return EX_HELD

    if report["ok"]:
        out.write("[rename-checker] OK (marker %s): pipeline %r present, "
                  "byte-exact.\n" % (masked, report["current"]))
        _live_report(report)
        return EX_OK

    reg._stop(out, "The standard Anthology pipeline is NOT present by name on this location.",
              ["AF-AE-TEMPLATE-PIPELINE-MISSING: absent or renamed — "
               "find-and-bind would fail silently.",
               "Expected byte-exact: %r" % report["expected"],
               "Live pipeline by that name: NONE" if not report["current"] else
               "Live pipeline name found: %r — not byte-exact; the standard "
               "pipeline appears RENAMED" % report["current"],
               "Restore the exact name in the Convert and Flow UI, then re-run.",
               "Location marker: %s" % masked])
    _live_report(report)
    return EX_STOP


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="rename_checker.py",
        description="Fail-closed name check against the Anthology Convert and "
                    "Flow location (U03): name == 'Anthology Engine' byte-exact "
                    "— find-and-bind is BY NAME, so a renamed pipeline is a "
                    "STOP, never an auto-heal. One JSON object on stdout; "
                    "never prints a secret (Skill 59).")
    ap.add_argument("--location-id", default="",
                    help="override the location id (default: the standard "
                         "location labels; never printed)")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (source of truth for the "
                         "byte-exact name)")
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

        field_map = reg.load_field_map(Path(args.field_map).expanduser())
        want = (field_map.get("pipeline") or {}).get("standard_pipeline_name") or ""
        if not want:
            reg._stop(sys.stderr, "The pipeline name contract is EMPTY.",
                      [str(Path(args.field_map).expanduser()),
                       "pipeline.standard_pipeline_name is empty — restore it and re-run."])
            return EX_MISMATCH

        if args.cmd == "plan":
            # offline plan: no network, no credentials
            print(json.dumps({
                "contract": "anthology-engine-rename-check-plan",
                "schema_version": 1,
                "standard_pipeline_name": want,
                "check": "GET /opportunities/pipelines?locationId=<id> — the "
                         "standard pipeline must be present BYTE-EXACT by name; "
                         "renamed or absent is a STOP (fail-closed)",
                "note": "offline plan only — no network, no credential needed",
            }, indent=2, sort_keys=True))
            return EX_OK

        # ---- live check ----
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
        sys.stderr.write("[rename-checker] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[rename-checker] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[rename-checker] HELD: %s\n" % exc)
        return EX_HELD
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[rename-checker] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
