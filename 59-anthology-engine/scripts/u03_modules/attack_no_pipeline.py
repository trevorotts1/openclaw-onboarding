#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u03_modules/attack_no_pipeline.py
# NO-PIPELINE ATTACK FIXTURE (U03 tooling) — the fail-closed EMPTY-LISTING gate:
# ANY pipelines listing that does not carry a standard Anthology pipeline
# BYTE-EXACT, and above all the EMPTY listing ({"pipelines": []} — the exact
# object a live GET /opportunities/pipelines read serves on a location with NO
# pipeline bound), is REFUSED with a loud operator STOP, never a pass, never a
# silent fallback, never a fabricated success. It is the attack half of the U03
# empty-state pair: the sibling golden fixture ships the GOLDEN pipeline state
# that the SAME checks must PASS; THIS module ships the ATTACK state — the
# location with NOTHING bound — that the SAME checks must REFUSE.
#
# WHY THE EMPTY LISTING IS THE U03 ATTACK: find-and-bind is BY NAME
# (MASTERDOC floor 11; anthology_registry.py provision-pipeline), and a listing
# that serves [] is indistinguishable from a renamed pipeline at the find step —
# BOTH bind nothing. The engine's setup sequence is fail-closed across the
# board (a PIT token that cannot even READ pipelines STOPS setup,
# AF-AE-PIT-SCOPE; a failed browser-creation walk STOPS, AF-AE-PIPELINE-UI-
# CREATE), so the empty listing is the ONE state a drift could mistake for a
# pass: the API call succeeds, the JSON parses, and the pipelines array is
# simply empty — no error, no exception, just nothing to bind. A verifier that
# treated "no rows" as a clean read would report the location as verified with
# NO pipeline bound, and every subsequent gate would fail against a phantom
# pipeline. THIS module exists so that state is REFUSED at the gate: exit 5,
# AF-AE-TEMPLATE-PIPELINE-MISSING, with the empty listing PROVEN in `found` —
# never a fabricated pass, never a silent failure.
#
# WHAT THIS OWNS
#   1. verify(payload, want_name) — the fail-closed gate over a pipelines
#      LISTING PAYLOAD ({"pipelines": [...]} — exactly the object a live
#      GET /opportunities/pipelines read serves, so the live surface and the
#      offline attack surface share ONE implementation):
#        - the standard pipeline present BYTE-EXACT -> ("PASS", ...) with the
#          name and stage count read back
#        - EMPTY listing, absent, renamed, near-miss, or malformed -> raises
#          NoPipelineError (STOP family, never a pass, never a silent fallback)
#          — an empty array is REFUSED UP FRONT with its own loud message, so
#          the U03 attack never shares the refusal path with a renamed
#          pipeline: the operator sees exactly which drift the gate caught.
#   2. payload(*, out) — the CLI gate: emits the ONE JSON report object
#      (contract / ok / verdict / expected / found / detail), refusals are
#      exit 5 (data or read-back mismatch) with a loud operator STOP line on
#      stderr — the EMPTY listing is PROVEN in `found` as an explicit
#      "(empty listing)" marker, so an empty state is never a fabricated pass
#      and never a silent failure.
#   3. self_test() — OFFLINE (no network, no credentials): the golden
#      byte-exact state passes; the EMPTY listing (the U03 attack), the
#      absent-after-rename case, the near-misses, the malformed payload, and
#      the empty name law are each REFUSED. A tamper NEVER masquerades as
#      exit 1 — it is exit 4 (AF-AE-TEMPLATE-ATTACK family), the house
#      self-test convention.
#
# DOCTRINE (house, per anthology_registry.py / drive_adapter.py / the U02
# golden and attack fixture siblings):
#   - A fixture is DATA, not code: this module performs NO I/O and NO network
#     call — it can never leak a token by construction. Nothing here reads an
#     env var or touches the wire.
#   - BROWSER UA: any module that TALKS to GoHighLevel / Convert and Flow
#     (services.leadconnectorhq.com, Cloudflare-fronted) MUST carry a browser
#     User-Agent on every request — urllib's default "Python-urllib/x.y" is
#     403'd at the WAF edge (CF error 1010) before it ever reaches the API.
#     This module makes no request of its own and therefore defines no UA
#     constant of its own; the client that DOES (reg.CafClient) already sends
#     reg.CAF_BROWSER_UA on every request — the proven edge fix (W0.6 / GK-09
#     discipline; the registry's own self-test pins the byte-exact string).
#     The --live surface pipes a listing in and reads NOTHING from the
#     network; the live reader is the U03 pipeline checker, which rides
#     reg.CafClient.
#   - FAIL-CLOSED: an EMPTY listing, an absent contract name, a malformed
#     listing, a missing rows array — every deviation REFUSES (NoPipelineError
#     / exit 5), never a blind pass, never a fabricated success.
#   - NEVER print a secret value; SET / NOT SET only, by label. The location
#     id, when surfaced, is the marker (last 4 chars) via reg._mask_location.
#   - Move in silence; NOTHING Anthropic in any runtime file; Convert and
#     Flow naming in every client surface.
#
# THE NAME IS NEVER HARDCODED HERE (SPEC M8): the wanted name comes from
# config/field-map.json pipeline.standard_pipeline_name — the SAME source of
# truth provision-pipeline binds by and the sibling checkers assert byte-exact.
# A drift of the CONTRACT name is caught by the offline self-test (golden
# state must match it), never silently.
#
# EXIT CODES (house convention 0/1/2/3/4/5; ENGINE-MANIFEST.json
# exit_code_house_convention):
#   0  verified PASS — the standard pipeline is present BYTE-EXACT (also
#      self-test PASS and plan OK)
#   1  unexpected error
#   2  STOP refusal — no gate mode selected, or contract name EMPTY (no name
#      law to enforce)
#   4  self-test FAILED — an attack fixture was NOT refused (AF-AE-TEMPLATE-
#      ATTACK family; a tamper NEVER masquerades as exit 1)
#   5  data or read-back mismatch — the listing is EMPTY (the U03 attack), or
#      the standard pipeline is ABSENT, RENAMED, or near-miss
#      (AF-AE-TEMPLATE-PIPELINE-MISSING)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr;
# --self-test is OFFLINE and needs no token and no network):
#   attack_no_pipeline.py --plan          # offline: the empty-state law with sources
#   attack_no_pipeline.py --live < listing.json
#                                       # pipes a full pipelines listing in
#   attack_no_pipeline.py --self-test     # offline golden + attack fixtures
#
#   # the canonical live pairing (reader -> attack gate, one pipeline):
#   <u03 pipeline checker>.py live --location-id ... | attack_no_pipeline.py --live
#
# STDLIB ONLY (json + argparse). Calls NO model. Reuses anthology_registry
# (load_field_map, _stop, _mask_location, CAF_BROWSER_UA doctrine).
# =============================================================================
"""attack_no_pipeline.py — no-pipeline attack fixture for the U03 EMPTY-LISTING
law: REFUSES any listing with no standard pipeline BYTE-EXACT (the EMPTY
{"pipelines": []} state included), never a pass."""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# Cloudflare browser-UA wiring (CAF_BROWSER_UA, applied by reg.CafClient —
# the fixture makes no request of its own, so it carries no UA of its own),
# the label resolution contract, and the fail-closed helper surfaces.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

FIXTURE_CONTRACT = "anthology-engine-attack-no-pipeline"

# The ONE fixed report contract on every surface (plan / live / self-test).
_REPORT = {
    "contract": FIXTURE_CONTRACT,
    "schema_version": 1,
}

# The marker that PROVES the empty listing in `found` — the empty state must
# never masquerade as a named pipeline and never as a blank "(none)".
_EMPTY_MARKER = "(empty listing)"


class NoPipelineError(Exception):
    """A fail-closed verification refusal (STOP / mismatch family): the
    standard pipeline is absent, renamed, near-miss, or the name law has no
    contract source — an EMPTY pipelines array is refused UP FRONT with its
    own loud message, so the U03 empty-state attack never shares the refusal
    path with a renamed pipeline."""


# ---------------------------------------------------------------------------
# Contract reader (fail-closed: an empty name law is a refusal, never a pass)
# ---------------------------------------------------------------------------
def _wanted_name(field_map: dict) -> str:
    """The byte-exact contract name from field-map.json
    pipeline.standard_pipeline_name — the single source of truth
    provision-pipeline binds by and the sibling checkers assert byte-exact."""
    name = (field_map.get("pipeline") or {}).get("standard_pipeline_name")
    if not isinstance(name, str) or not name.strip():
        raise NoPipelineError(
            "config/field-map.json pipeline.standard_pipeline_name is EMPTY — "
            "the name law has no contract source; refusing to judge any "
            "listing (never a fabricated pass).")
    return name


# ---------------------------------------------------------------------------
# The fail-closed gate over a pipelines LISTING payload. The payload is
# {"pipelines": [...]} — EXACTLY the object a live GET /opportunities/
# pipelines read serves (reg.CafClient.list_pipelines returns
# out.get("pipelines") or []), so the live surface and the offline attack
# surface share ONE implementation of the empty-state law.
# ---------------------------------------------------------------------------
def verify(payload: dict, want_name: str = "") -> tuple:
    """Verify a pipelines listing against the byte-exact name law, fail-closed.

    Returns ("PASS", detail, name, stage_count) when the standard pipeline is
    present BYTE-EXACT. Raises NoPipelineError on ANY other outcome — the EMPTY
    listing (the U03 attack; refused UP FRONT, never judged "clean"), absent,
    renamed, near-miss (case, whitespace, plural), malformed payload — never a
    silent fallback. The found names are surfaced in the message (never
    fabricated; a name cannot be a credential), so the drift is PROVEN present,
    not assumed.
    """
    want = want_name or _wanted_name(reg.load_field_map(FIELD_MAP_PATH))
    if not isinstance(payload, dict):
        raise NoPipelineError(
            "listing payload is %r, not an object — refusing to judge it."
            % type(payload).__name__)
    pipes = payload.get("pipelines")
    if pipes is None:
        raise NoPipelineError(
            "listing payload has no 'pipelines' array — a malformed read is "
            "NEVER a pass (fail-closed).")
    if not isinstance(pipes, list):
        raise NoPipelineError(
            "listing 'pipelines' is %r, not a list — refusing."
            % type(pipes).__name__)
    if not pipes:
        # THE U03 ATTACK: the API call succeeded, the JSON parsed, and the
        # array is empty — no error, no exception, just nothing to bind.
        # Find-and-bind cannot tell this from a renamed pipeline (both bind
        # nothing), so the empty listing is REFUSED UP FRONT with its own
        # loud message — never judged a clean read, never a blind pass.
        raise NoPipelineError(
            "AF-AE-TEMPLATE-PIPELINE-MISSING: the pipelines listing is EMPTY — "
            "no pipeline at all is bound at this location (%s). A clean read "
            "of a fully provisioned location must serve the standard pipeline "
            "byte-exact; an empty array is the U03 attack state. Refusing — "
            "find-and-bind would silently bind NOTHING."
            % _EMPTY_MARKER)

    found = next((p for p in pipes
                  if isinstance(p, dict) and p.get("name") == want), None)
    if found is None:
        names = sorted({p.get("name") for p in pipes
                        if isinstance(p, dict) and p.get("name")})
        if names and want in names:
            # Defensive: next() above is the byte-exact find; reaching here
            # with want in names is impossible, but a duplicate-free guard
            # costs nothing and a refusal is never wrong.
            raise NoPipelineError(
                "AF-AE-TEMPLATE-PIPELINE-MISSING: the standard pipeline %r is "
                "listed but was NOT matched byte-exact (found: %s) — refusing."
                % (want, ", ".join(names)))
        raise NoPipelineError(
            "AF-AE-TEMPLATE-PIPELINE-MISSING: the standard pipeline %r is "
            "ABSENT from the listing — renamed, removed, or near-miss "
            "(found: %s). Find-and-bind would fail silently — restore the "
            "byte-exact name in the Convert and Flow UI."
            % (want, ", ".join(names) or "(none)"))
    name = found.get("name") or ""
    stages = len([s for s in (found.get("stages") or []) if isinstance(s, dict)])
    return ("PASS", "pipeline name byte-exact", name, stages)


# ---------------------------------------------------------------------------
# CLI gate — ONE JSON object on stdout, human notes on stderr, fail-closed.
# ---------------------------------------------------------------------------
def _report(ok: bool, verdict: str, expected: str, found, stage_count,
            detail: str) -> None:
    sys.stdout.write(json.dumps(dict(
        _REPORT,
        ok=ok,
        verdict=verdict,
        expected=expected,
        found=found,
        stage_count=stage_count,
        detail=detail,
    ), indent=2, sort_keys=True) + "\n")


def payload(payload_obj: dict, *, out=None) -> int:
    """Run the fail-closed empty-state gate over a listing payload. Returns the
    exit code: 0 PASS, 5 refusal (mismatch family). Human notes go to stderr;
    the ONE JSON report object lands on stdout."""
    out = out or sys.stderr
    want = _wanted_name(reg.load_field_map(FIELD_MAP_PATH))
    try:
        status, detail, name, stages = verify(payload_obj, want)
    except NoPipelineError as exc:
        found = _found_names(payload_obj)
        reg._stop(out, "The standard Anthology pipeline is NOT present "
                       "BYTE-EXACT on this listing.",
                  [str(exc), "Expected (byte-exact): %r" % want,
                   "Found on the listing: %s" % (", ".join(found) or "(none)"),
                   "AF-AE-TEMPLATE-PIPELINE-MISSING — bind the pipeline in the "
                   "Convert and Flow UI, then re-run."])
        _report(False, "FAIL", want, found, 0, str(exc))
        return EX_MISMATCH
    _report(True, "PASS", want, [name], stages,
            "pipeline name byte-exact (%d stage(s) read back)" % stages)
    out.write("[attack-no-pipeline] OK: standard pipeline %r present byte-exact, "
              "%d stage(s) read back.\n" % (name, stages))
    return EX_OK


def _found_names(payload_obj) -> list:
    """The live pipeline names on a listing — or the EXPLICIT empty-listing
    marker, so the U03 empty state is PROVEN in `found` and never collapses
    into a bare "(none)" (names are NOT credentials — surfacing them is how a
    drift is PROVEN)."""
    if not isinstance(payload_obj, dict):
        return []
    pipes = payload_obj.get("pipelines")
    if not isinstance(pipes, list):
        return []
    if not pipes:
        return [_EMPTY_MARKER]
    return sorted({p.get("name") for p in pipes
                   if isinstance(p, dict) and p.get("name")})


# ---------------------------------------------------------------------------
# Offline self-test — golden + attack fixtures, zero network, zero secrets.
# A FAILED self-test is exit 4 (enforced violation, AF-AE-TEMPLATE-ATTACK
# family), NEVER 'unexpected error' — the house convention.
# ---------------------------------------------------------------------------
def _golden_pipeline() -> dict:
    """The golden pipeline state derived from the field-map: the byte-exact
    contract name with the nine contract stages in position order — exactly
    the row a live read of a fully provisioned location serves."""
    pconf = (reg.load_field_map(FIELD_MAP_PATH).get("pipeline") or {})
    stages = sorted((pconf.get("standard_stages") or []),
                    key=lambda s: s.get("position", 0))
    return {"id": "pipe_tmpl",
            "name": (pconf.get("standard_pipeline_name") or ""),
            "stages": [{"position": s.get("position"), "name": s.get("name"),
                        "id": "stg_%s" % s.get("position")}
                       for s in stages if isinstance(s, dict)]}


def _golden_payload() -> dict:
    """The full listing object for the golden state — the exact
    {"pipelines": [...]} shape a live read serves."""
    return {"pipelines": [_golden_pipeline()]}


def self_test(out=None) -> int:
    """OFFLINE self-test: golden + attack fixtures, no network, no secrets.
    A tamper NEVER masquerades as exit 1 — it is exit 4
    (AF-AE-TEMPLATE-ATTACK family)."""
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[attack-no-pipeline] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    want = _wanted_name(reg.load_field_map(FIELD_MAP_PATH))
    assert want == "Anthology Engine", \
        "standard_pipeline_name drifted from the U03 contract (got %r)" % want

    # ---- golden state: present + byte-exact -> PASS ----
    status, detail, name, stages = verify(_golden_payload(), want)
    assert status == "PASS", "golden listing: %s" % detail
    assert name == want and stages == 9, \
        "golden pipeline must carry the byte-exact name and 9 stages"

    # ---- attack fixtures: every mutation REFUSED (never a silent pass) ----
    # 1. THE U03 ATTACK: the EMPTY listing ({"pipelines": []} — a location
    #    with NOTHING bound; the exact object a live read of an unbound
    #    location serves) -> refusal, and the marker PROVEN in the message
    a1 = {"pipelines": []}
    try:
        verify(a1, want)
        raise AssertionError("empty-listing attack was NOT refused")
    except NoPipelineError as exc:
        assert _EMPTY_MARKER in str(exc), \
            "the refusal must PROVE the empty listing: %s" % exc
    # 2. pipeline ABSENT (a listing with SOME other pipeline, none standard)
    #    -> refusal (the empty-array fast path must not mask this family)
    a2 = {"pipelines": [{"id": "pipe_other",
                         "name": "Some Other Pipeline", "stages": []}]}
    try:
        verify(a2, want)
        raise AssertionError("pipeline-absent was NOT refused")
    except NoPipelineError:
        pass
    # 3. renamed: the standard pipeline RENAMED (the drift that binds nothing)
    #    -> refusal, never a pass
    a3 = {"pipelines": [dict(_golden_pipeline(), name="Anthology Writer")]}
    try:
        verify(a3, want)
        raise AssertionError("renamed-pipeline was NOT refused")
    except NoPipelineError:
        pass
    # 4. near-miss: case drift "anthology engine" -> refusal (byte-exact law)
    a4 = {"pipelines": [dict(_golden_pipeline(), name=want.lower())]}
    try:
        verify(a4, want)
        raise AssertionError("case-drift was NOT refused")
    except NoPipelineError:
        pass
    # 5. malformed listing (no 'pipelines' array) -> refusal, never a pass
    try:
        verify({"no_pipelines_here": True}, want)
        raise AssertionError("malformed listing was NOT refused")
    except NoPipelineError:
        pass
    try:
        verify({"pipelines": "not-a-list"}, want)
        raise AssertionError("non-list pipelines was NOT refused")
    except NoPipelineError:
        pass
    # 6. empty name law -> refusal (no contract source, never a blind pass)
    try:
        verify({"pipelines": []}, "")
        raise AssertionError("empty name law was NOT refused")
    except NoPipelineError:
        pass
    # 7. golden state read back through the CLI gate -> exit 0, PASS JSON
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(_golden_payload(), out=io.StringIO())
    assert rc == EX_OK, "golden payload must exit 0, got %s" % rc
    report = json.loads(buf.getvalue())
    assert report["ok"] is True and report["verdict"] == "PASS"
    assert report["expected"] == want and report["found"] == [want]
    assert report["stage_count"] == 9
    assert report["contract"] == FIXTURE_CONTRACT
    # 8. THE U03 ATTACK through the CLI gate -> exit 5, FAIL JSON, and the
    #    EMPTY LISTING PROVEN in found (the explicit marker) — never a
    #    fabricated pass, never a silent "(none)"
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc2 = payload(a1, out=io.StringIO())
    assert rc2 == EX_MISMATCH, "empty payload must exit 5, got %s" % rc2
    report2 = json.loads(buf2.getvalue())
    assert report2["ok"] is False and report2["verdict"] == "FAIL"
    assert report2["expected"] == want
    assert report2["found"] == [_EMPTY_MARKER], \
        "the empty listing must be PROVEN in found: %s" % report2["found"]
    assert report2["stage_count"] == 0

    dev.write("attack_no_pipeline self-test: OK (empty-state law pinned "
              "byte-exact to field-map.json pipeline.standard_pipeline_name "
              "%r; golden PASS with 9 stages; 8 attack fixtures refused: "
              "empty-listing / absent / renamed / case-drift / "
              "malformed-payload / non-list-pipelines / empty-name-law / "
              "empty-CLI-exit-5; payload gate exits 0 on golden, 5 on the "
              "empty listing)\n" % want)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="attack_no_pipeline.py",
        description="No-pipeline attack fixture for the U03 EMPTY-LISTING law "
                    "(Skill 59): REFUSES any pipelines listing with no "
                    "standard pipeline BYTE-EXACT — the EMPTY "
                    "{'pipelines': []} state (a location with nothing bound) "
                    "included. One JSON object on stdout; fail-closed; never "
                    "prints a secret value.")
    ap.add_argument("--live", action="store_true",
                    help="read a full pipelines listing JSON from stdin "
                         "(the exact shape the U03 pipeline checker live "
                         "emits) and gate it against the byte-exact name law")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (source of truth for the "
                         "byte-exact name)")
    ap.add_argument("cmd", nargs="?", choices=["plan", "self-test"],
                    help="offline subcommands (no network, no credentials)")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # (the same normalization the registry and the U02 verifier use).
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()

        field_map = reg.load_field_map(Path(args.field_map).expanduser())
        want = _wanted_name(field_map)
        if args.cmd == "plan":
            # offline plan: no network, no credentials — the empty-state law
            # with its sources, including the attack this fixture exists for.
            print(json.dumps({
                "contract": FIXTURE_CONTRACT + "-plan",
                "schema_version": 1,
                "standard_pipeline_name": want,
                "attack": "empty pipelines listing ({'pipelines': []}) — the "
                          "U03 no-pipeline state: a location with NOTHING "
                          "bound. Find-and-bind cannot tell empty from "
                          "renamed (both bind nothing), so it is REFUSED "
                          "up front, never judged a clean read.",
                "check": "the standard pipeline must be present BYTE-EXACT on "
                         "any listing; an EMPTY listing is REFUSED "
                         "(AF-AE-TEMPLATE-PIPELINE-MISSING)",
                "note": "offline plan only — no network, no credential needed",
            }, indent=2, sort_keys=True))
            return EX_OK

        # ---- live gate: the listing comes in on stdin, read from NO network
        #      (the live READER is the U03 pipeline checker, which rides
        #      reg.CafClient and its CAF_BROWSER_UA — this fixture never
        #      touches the wire) ----
        if not args.live:
            reg._stop(sys.stderr, "No gate mode selected.",
                      ["Pass --live with a pipelines listing JSON on stdin "
                       "(<u03 pipeline checker>.py live | "
                       "attack_no_pipeline.py --live), or --plan / --self-test "
                       "(offline)."])
            return EX_STOP
        try:
            listing = json.load(sys.stdin)
        except ValueError as exc:
            reg._stop(sys.stderr, "The pipelines listing on stdin is not valid JSON.",
                      ["%s" % exc,
                       "Pipe the exact JSON the U03 pipeline checker live "
                       "emits."])
            return EX_STOP
        return payload(listing, out=sys.stderr)

    except NoPipelineError as exc:
        sys.stderr.write("[attack-no-pipeline] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except FileNotFoundError as exc:
        sys.stderr.write("[attack-no-pipeline] file not found: %s\n" % exc)
        return EX_ERR
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[attack-no-pipeline] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
