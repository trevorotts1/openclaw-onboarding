#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u02_modules/pipeline_check.py  (U02 tooling)
# LIVE PIPELINE NAME CHECK — the smallest fail-closed live probe in the U02
# re-verification family (see the sibling live_verify_template.py): it READS
# the location's pipelines through Convert and Flow (LeadConnector v2) with
# the client's OWN private-integration token and reports whether a pipeline
# named BYTE-EXACT "Anthology Engine" exists.
#
# WHY A DEDICATED MODULE: find-and-bind is BY NAME (MASTERDOC floor 11;
# anthology_registry.py provision-pipeline); a renamed or absent pipeline
# silently unbinds onboarding. This check is deliberately NARROWER than
# live_verify_template.py check_pipeline (name only, no stage judgment —
# stages belong to the stage-drift verifier). It is a reusable import
# (check_pipeline_name) so the U02 report and the operators' live runs share
# ONE implementation of the name law, plus a --live CLI surface that emits
# ONE JSON object.
#
# LIVE SURFACE: GET /opportunities/pipelines?locationId=<id> — the ONLY
# pipeline read the public v2 API provides (pipelines are UI-only; there is
# no create/delete endpoint). The name must equal the committed contract
# field-map.json pipeline.standard_pipeline_name byte-for-byte. The name law
# is FAIL-CLOSED and BY-NAME: find-by-name cannot distinguish a RENAMED
# pipeline from an ABSENT one, so ANY non-byte-exact result is a STOP
# refusal (AF-AE-TEMPLATE-PIPELINE-MISSING family) — exactly the semantics
# live_verify_template.py applies — never a silent fallback.
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
# never 1010s the check (W0.6 / GK-09 discipline — the exact failure mode
# that 403s urllib's default UA before the request reaches Convert and Flow).
# Scope-vs-edge-block discrimination is the registry's own: a bare 401/403
# whose body does NOT match the genuine scope-denial signature raises
# UpstreamBlockedError -> HELD, never a scope STOP.
#
# EXIT CODES (house convention 0/1/2/3/4; pipeline-name drift is the STOP
# family, exit 2 — mirroring live_verify_template.py's check_pipeline):
#   0  the standard pipeline is present and BYTE-EXACT (name match)
#   1  unexpected error
#   2  STOP refusal — PIT/location label NOT SET, non-pit- value, or the
#      standard pipeline is ABSENT or RENAMED on the location
#      (AF-AE-TEMPLATE-PIPELINE-MISSING; find-and-bind would fail silently)
#   3  Convert and Flow API unreachable / edge-blocked (HELD; retryable —
#      the scope is UNDETERMINED here, never proven absent)
#   4  self-test FAILED (an offline assertion tripped; a tamper NEVER
#      masquerades as exit 1)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; --self-test is OFFLINE and needs NO token and NO network):
#   pipeline_check.py live [--location-id ID]
#   pipeline_check.py plan            # offline; the name law with sources
#   pipeline_check.py self-test       # offline golden + attack fixtures
#
# STDLIB ONLY (urllib + json); calls NO model. Reuses anthology_registry
# (CafClient, resolve_pit, resolve_location, load_field_map, _stop,
# _mask_location). DOCTRINE: move in silence; NOTHING Anthropic in any
# runtime file; Convert and Flow naming in every client surface; NEVER print
# a secret value.
# =============================================================================
"""pipeline_check.py — live pipeline NAME check against the Anthology Convert
and Flow location (U02 tooling)."""
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

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

# The standard pipeline name is NEVER hardcoded here (SPEC M8): it comes from
# the committed contract config/field-map.json pipeline.standard_pipeline_name,
# the SAME source of truth provision-pipeline binds by. A drift in the contract
# is caught by the offline self-test (golden state must match it).
_standard_pipeline_name = (
    (reg.load_field_map(FIELD_MAP_PATH).get("pipeline") or {}).get("standard_pipeline_name") or "")


def _mask_location(loc: str) -> str:
    """Non-reversible location marker (last 4 chars) for operator surfaces."""
    return reg._mask_location(loc)


# ---------------------------------------------------------------------------
# Live check primitive — returns (status, detail, name, stages). FAIL-CLOSED:
# any non-byte-exact name is a STOP (raise) — never skipped, never fabricated.
# ---------------------------------------------------------------------------
def check_pipeline_name(client, location_id: str, want_name: str = "") -> tuple:
    """LIVE pipeline NAME check (read-only): the standard pipeline must exist
    BYTE-EXACT on the location.

    - present + byte-exact  -> ("PASS", detail, name, stage_count)
    - absent OR renamed     -> raises PipelineMissing (STOP family): find-by-
      name cannot tell a renamed pipeline from an absent one, so BOTH refuse —
      the exact AF-AE-TEMPLATE-PIPELINE-MISSING semantics of the sibling
      live_verify_template.py. The found names are surfaced in the message
      (never fabricated); reg.ScopeDenied / reg.CafUnreachable propagate
      exactly as the registry raises them.
    """
    want = want_name or _standard_pipeline_name
    if not want:
        raise PipelineMissing(
            "config/field-map.json pipeline.standard_pipeline_name is EMPTY "
            "— the name law has no contract source")

    pipes = client.list_pipelines(location_id)
    found = next((p for p in pipes if isinstance(p, dict) and p.get("name") == want), None)
    if found is None:
        names = sorted({p.get("name") for p in pipes if isinstance(p, dict) and p.get("name")})
        raise PipelineMissing(
            "AF-AE-TEMPLATE-PIPELINE-MISSING: the standard pipeline %r is ABSENT "
            "from the location (found: %s). Find-and-bind would fail silently — "
            "restore it in the Convert and Flow UI." % (want, ", ".join(names) or "(none)"))
    name = found.get("name") or ""
    stages = len([s for s in (found.get("stages") or []) if isinstance(s, dict)])
    return ("PASS", "pipeline name byte-exact", name, stages)


class PipelineMissing(Exception):
    """A fail-closed verification refusal (STOP family): the standard pipeline
    is absent, renamed, or the name law has no contract source."""


# ---------------------------------------------------------------------------
# Offline self-test (no network, no credentials) — proves the pure logic:
# golden state passes, every attack fixture is refused, and the name law
# stays pinned to the contract source.
# ---------------------------------------------------------------------------
class _FakeCaf:
    """Deterministic pipeline-listing stub (mirrors live_verify_template's
    _FakeCaf seam): 'pipelines' fixture, 'behavior' for scope/edge/transport."""

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
    pconf = (reg.load_field_map(FIELD_MAP_PATH).get("pipeline") or {})
    stages = sorted(pconf.get("standard_stages") or [], key=lambda s: s.get("position", 0))
    return {"id": "pipe_tmpl", "name": pconf.get("standard_pipeline_name") or "",
            "stages": [{"position": s.get("position"), "name": s.get("name"), "id": "stg_%s" % s.get("position")}
                       for s in stages if isinstance(s, dict)]}


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[pipeline-check] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    want = _standard_pipeline_name
    assert want, "contract name must not be empty"
    assert want == "Anthology Engine", "standard_pipeline_name drifted from the U02 contract"

    # ---- golden live state: present + byte-exact -> PASS ----
    caf = _FakeCaf(pipelines=[_golden_pipeline()])
    status, detail, name, stages = check_pipeline_name(caf, "loc_tmpl")
    assert status == "PASS", "golden pipeline: %s" % detail
    assert name == want and stages == 9
    assert caf.calls == ["loc_tmpl"], "unexpected calls: %s" % caf.calls

    # ---- attack fixtures: every mutation REFUSED (never a silent pass) ----
    # 1. pipeline RENAMED -> STOP refusal (find-by-name cannot tell renamed
    #    from absent; byte-exact is the law — live_verify_template semantics)
    a1 = [dict(_golden_pipeline(), name="Anthology Engine RENAMED")]
    try:
        check_pipeline_name(_FakeCaf(pipelines=a1), "loc_tmpl")
        raise AssertionError("pipeline-renamed was NOT refused")
    except PipelineMissing:
        pass
    # 2. pipeline ABSENT -> STOP refusal
    try:
        check_pipeline_name(_FakeCaf(pipelines=[]), "loc_tmpl")
        raise AssertionError("pipeline-absent was NOT refused")
    except PipelineMissing:
        pass
    # 3. extra unrelated pipeline alongside the standard -> PASS
    a3 = [_golden_pipeline(),
          dict(_golden_pipeline(), id="pipe_extra", name="Some Other Pipeline")]
    status, detail, _, _ = check_pipeline_name(_FakeCaf(pipelines=a3), "loc_tmpl")
    assert status == "PASS", "extra pipeline must not break the name check"
    # 4. scope denied -> STOP family surfaces as ScopeDenied (never a fabricated pass)
    try:
        check_pipeline_name(_FakeCaf(behavior="scope"), "loc_tmpl")
        raise AssertionError("scope-denied was NOT refused")
    except reg.ScopeDenied:
        pass
    # 5. edge/transport -> HELD family surfaces (never a scope STOP)
    for behavior in ("edge", "transport"):
        try:
            check_pipeline_name(_FakeCaf(behavior=behavior), "loc_tmpl")
            raise AssertionError("%s was NOT refused" % behavior)
        except reg.CafUnreachable:
            pass
    # 6. live CLI on the golden state -> exit 0 and a PASS JSON object
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = run_live(_FakeCaf(pipelines=[_golden_pipeline()]), "loc_tmpl", out=io.StringIO())
    assert rc == EX_OK, "golden run_live must exit 0, got %s" % rc
    report = json.loads(buf.getvalue())
    assert report["ok"] is True, "golden report must carry ok true"
    assert report["name"] == want and report["stages"] == 9
    assert report["delta"] == [], "golden report must carry an empty delta"
    # 7. live CLI on a RENAMED pipeline -> exit 2 (STOP) and ok false with delta
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc2 = run_live(_FakeCaf(pipelines=a1), "loc_tmpl", out=io.StringIO())
    assert rc2 == EX_STOP, "renamed run_live must exit 2, got %s" % rc2
    report2 = json.loads(buf2.getvalue())
    assert report2["ok"] is False and report2["present"] is False
    assert any("pipeline" in str(d.get("item")) for d in report2["delta"]), \
        "renamed report must carry a pipeline delta"
    assert report2["name"] == "" and report2["stages"] == 0

    dev.write("pipeline_check self-test: OK (name law pinned to field-map "
              "pipeline.standard_pipeline_name %r; golden PASS + 9 stages + "
              "empty delta; 7 attack fixtures refused: pipeline-renamed / "
              "pipeline-absent / extra-pipeline / scope-denied / edge-block / "
              "transport / renamed-run_live-STOP; run_live exits 0 on golden, "
              "2 on renamed)\n" % want)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _live_report(ok: bool, name: str, present: bool, stages: int, delta: list) -> None:
    """Emit the ONE JSON object (machine surface, stdout) for a live run."""
    sys.stdout.write(json.dumps({
        "ok": ok,
        "name": name,
        "present": present,
        "stages": stages,
        "delta": delta,
    }, indent=2, sort_keys=True) + "\n")


def run_live(client, location_id: str, *, out=None) -> int:
    """Run the live check against a resolved client. Returns the exit code.
    One JSON object lands on stdout; human notes go to stderr."""
    out = out or sys.stderr
    masked = _mask_location(location_id)
    want = _standard_pipeline_name
    if not want:
        reg._stop(out, "The pipeline name contract is EMPTY.",
                  ["config/field-map.json pipeline.standard_pipeline_name is empty.",
                   "Restore the contract name and re-run."])
        return EX_MISMATCH
    try:
        status, detail, name, stages = check_pipeline_name(client, location_id, want)
    except PipelineMissing as exc:
        reg._stop(out, "The standard Anthology pipeline is NOT present by name on this location.",
                  [str(exc), "Location marker: %s" % masked])
        _live_report(False, "", False, 0,
                     [{"item": "pipeline", "status": "FAIL",
                       "detail": "AF-AE-TEMPLATE-PIPELINE-MISSING: absent or "
                                 "renamed", "expected": want, "live": None}])
        return EX_STOP
    except reg.ScopeDenied:
        reg._stop(out, "The Convert and Flow token cannot READ pipelines on this location.",
                  ["Location marker: %s" % masked,
                   "Grant the client's OWN location-scoped token the opportunities "
                   "scope and re-run.", "AF-AE-PIT-SCOPE."])
        return EX_STOP
    except reg.CafUnreachable as exc:   # includes UpstreamBlockedError (edge/WAF)
        out.write("[pipeline-check] HELD: %s (marker %s). "
                  "NOT a token-scope problem; retryable.\n" % (exc, masked))
        return EX_HELD

    out.write("[pipeline-check] OK (marker %s): pipeline %r present, "
              "byte-exact, %d stage(s) read back.\n" % (masked, name, stages))
    _live_report(True, name, True, stages, [])
    return EX_OK


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="pipeline_check.py",
        description="Live pipeline NAME check against the Anthology Convert and "
                    "Flow location (U02): the standard pipeline must exist "
                    "BYTE-EXACT by name — find-and-bind is BY NAME. One JSON "
                    "object on stdout; fail-closed; never prints a secret "
                    "(Skill 59).")
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
                "contract": "anthology-engine-pipeline-name-plan",
                "schema_version": 1,
                "standard_pipeline_name": want,
                "check": "GET /opportunities/pipelines?locationId=<id> — the "
                         "standard pipeline must be present BYTE-EXACT by name",
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
        sys.stderr.write("[pipeline-check] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[pipeline-check] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[pipeline-check] HELD: %s\n" % exc)
        return EX_HELD
    except PipelineMissing as exc:
        sys.stderr.write("[pipeline-check] STOP: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[pipeline-check] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
