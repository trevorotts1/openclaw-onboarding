#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u03_modules/golden_correct.py
# GOLDEN-NAME FIXTURE (U03 name-correctness tooling, extension module) — the
# single canonical in-memory payload of the engine's BYTE-EXACT contract name
# ("Anthology Engine"), derived BYTE-FOR-BYTE from config/field-map.json
# pipeline.standard_pipeline_name (the single source of truth).
#
# WHERE THIS SITS: scripts/u03_modules/ — an importable module under the U03
# name-correctness tooling, exactly like its siblings golden_fields.py /
# golden_pipeline.py under u02_modules. It is NOT a manifest row and NOT a
# checker: it ships the GOLDEN name-law surface the self-tests of the U03
# verifier and the sibling check modules assert against, so every checker's
# happy path is judged against the SAME payload and a drift in the field-map
# contract breaks THIS module's self-test first (fail-closed: an inconsistent
# map is a refusal, never a blind pass). Imported BY NAME as
# u03_modules.golden_correct, per the u03_modules package contract in
# __init__.py (pure namespace container).
#
# WHAT THIS OWNS:
#   1. GOLDEN_CORRECT — the deep-frozen canonical payload: a mappingproxy
#      record {"name": <the byte-exact engine name>} plus the derived
#      GOLDEN_ENGINE_NAME string constant, both built ONCE at import from the
#      field-map. str is immutable and the record is mappingproxy-frozen, so
#      no caller can mutate the canonical name through the module's public
#      surface — the self-test proves every mutation route raises.
#   2. golden_correct(field_map) — the builder, fail-closed: a missing or
#      malformed pipeline section or an empty/blank standard_pipeline_name
#      raises FixtureError instead of shipping a wrong fixture.
#   3. golden_correct_payload(field_map) / golden_listing_payload(field_map)
#      — the deep-copied payload surfaces (the config shape and the live
#      pipelines-listing shape) consumers mutate freely; the canon never
#      changes.
#   4. payload — a FAIL-CLOSED name-law gate: the candidate (a bare name
#      string, a {"name": ...} object, or a {"pipelines": [...]} listing)
#      carries the contract name BYTE-EXACT -> PASS exit 0; ANY deviation
#      (absent, renamed, near-miss, empty, malformed) is a REFUSED exit 5
#      with the ONE JSON report object on stdout — never a blind pass, never
#      a fabricated success.
#
# DOCTRINE (house, inherited from the registry / drive adapter / the U02
# golden siblings — the SAME doctrine every fixture carries):
#   - Never a token printed: credentials resolve BY LABEL only (SET / NOT
#     SET). This module holds NO credential surface and reads NO env var —
#     a fixture cannot leak what it never holds.
#   - Fail-closed: a malformed map, an absent section, a malformed read all
#     STOP or FAIL — never a blind pass, never a fabricated success.
#   - READ-ONLY: this module never creates, never writes, never mutates.
#   - BROWSER UA: any module that TALKS to GoHighLevel / Convert and Flow
#     (services.leadconnectorhq.com, Cloudflare-fronted) MUST carry a browser
#     User-Agent on every request — urllib's default "Python-urllib/x.y" is
#     403'd at the WAF edge (CF error 1010) before it ever reaches the API
#     (CAF_BROWSER_UA in anthology_registry.py is the house pattern). THIS
#     module makes NO network call and defines NO User-Agent constant of its
#     own; the client that DOES (reg.CafClient) already sends CAF_BROWSER_UA
#     on every request — the proven edge fix. The --live surface pipes a
#     candidate in on stdin and reads NOTHING from the network; the live
#     reader is the sibling checker that rides reg.CafClient.
#   - Move in silence; NOTHING Anthropic in any runtime file; Convert and
#     Flow naming in every client surface.
#
# THE NAME IS NEVER HARDCODED HERE (SPEC M8): it comes from
# config/field-map.json pipeline.standard_pipeline_name — the SAME source of
# truth find-and-bind binds by and the sibling checkers assert byte-exact
# ("Anthology Engine"; MASTER-SPEC U02 item 1, MASTERDOC floor 11). The
# OFFLINE self-test pins the contract value so a drift in the CONTRACT is
# caught first — never silently.
#
# EXIT CODE CONTRACT (house convention; mirrors the U02 verifier and the
# golden siblings):
#   0  verified success — the golden name is internally consistent and
#      byte-equal to the field-map contract; also self-test / plan OK
#   1  unexpected error (malformed/unreadable field-map JSON)
#   5  mismatch — the field-map drifted from the fixture contract (pipeline
#      section absent/malformed, empty standard_pipeline_name), or the
#      candidate deviates from the golden name (absent/renamed/near-miss/
#      malformed — all FAIL-CLOSED refusals)
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to
# golden_fields.py / golden_pipeline.py: sys.path.insert to scripts/ then
# `import anthology_registry as reg`.
# =============================================================================
"""golden_correct.py — golden BYTE-EXACT engine-name fixture for self-test."""

from __future__ import annotations

import argparse
import copy
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# Cloudflare browser-UA wiring + the LeadConnector client + the credential
# label resolution — the module reuses them, never re-implements.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_MISMATCH = reg.EX_OK, reg.EX_ERR, reg.EX_MISMATCH

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

# The one fixed report contract. The engine NAME itself is NEVER hardcoded
# here — it comes from the field-map (the single source of truth); a
# hardcoded name would drift and defeat the fixture's whole purpose.
FIXTURE_CONTRACT = "anthology-engine-golden-correct"

# The stable synthetic pipeline id of the live-listing surface (the same
# synthetic-id discipline as the sibling fixtures — a fixture id is never a
# real location id).
GOLDEN_PIPELINE_ID = "pipe_golden"


class FixtureError(Exception):
    """A fail-closed fixture refusal (STOP/mismatch family): the field-map is
    inconsistent with the golden name contract, so NO fixture is shipped — a
    wrong fixture is worse than no fixture."""


# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing section is a refusal, never a pass)
# ---------------------------------------------------------------------------
def _contract_pipeline(field_map: dict) -> dict:
    pconf = field_map.get("pipeline")
    if not isinstance(pconf, dict):
        raise FixtureError(
            "field-map.json has no pipeline section — the golden name payload "
            "has nothing to derive from; refusing a blind fixture (never "
            "fabricated).")
    return pconf


def _contract_engine_name(pconf: dict) -> str:
    name = pconf.get("standard_pipeline_name")
    if not isinstance(name, str) or not name.strip():
        raise FixtureError(
            "field-map pipeline.standard_pipeline_name is missing or empty — "
            "the name law (find-and-bind is BY NAME) has no contract source; "
            "refusing to ship a golden payload.")
    return name


# ---------------------------------------------------------------------------
# The golden builder — fail-closed, deterministic, byte-equal to the map.
# ---------------------------------------------------------------------------
def golden_correct(field_map: dict) -> dict:
    """Derive the golden name payload from the field-map.

    The canonical payload is EXACTLY what a live pipeline read of a fully
    provisioned location returns the engine name as: {"name": <byte-exact
    contract name>}. Raises FixtureError on ANY contract drift — a wrong
    fixture is never shipped.

    The returned dict is a deep copy; mutating it never touches the internal
    canonical payload (which itself is mappingproxy-frozen)."""
    pconf = _contract_pipeline(field_map)
    name = _contract_engine_name(pconf)
    return copy.deepcopy({"name": name})


def golden_engine_name(field_map: dict) -> str:
    """The golden BYTE-EXACT engine name (the resolved-slot surface): the
    standard_pipeline_name the field-map contract pins, altered by NOTHING —
    byte-identical, whitespace included (a near-miss with a trailing space is
    drift, never a pass)."""
    return golden_correct(field_map)["name"]


def golden_correct_payload(field_map: dict) -> dict:
    """The canonical config-surface payload: {"name": <golden name>} — the
    exact shape a field-map standard_pipeline_name read serves. A deep copy;
    callers may mutate it."""
    return golden_correct(field_map)


def golden_listing_payload(field_map: dict) -> dict:
    """The canonical live surface: {"pipelines": [{"id": "pipe_golden",
    "name": <golden name>}]} — exactly the shape a live GET
    /opportunities/pipelines read returns (reg.CafClient.list_pipelines
    returns out.get("pipelines") or []), so the live surface and the offline
    fixture surface share ONE shape. A deep copy; callers may mutate it."""
    return {"pipelines": [{
        "id": GOLDEN_PIPELINE_ID,
        "name": golden_engine_name(field_map),
    }]}


# ---------------------------------------------------------------------------
# The golden fixture itself — derived ONCE at import, deep-frozen. The record
# is a MappingProxyType and the name is a str (immutable by construction), so
# NO caller can mutate the canonical payload through the module's public
# surface — the self-test proves it. Consumers that need a mutable payload
# call golden_correct() / golden_correct_payload() (deep copies).
# ---------------------------------------------------------------------------
def _build_golden() -> tuple:
    from types import MappingProxyType
    fm = reg.load_field_map(FIELD_MAP_PATH)
    return (MappingProxyType(golden_correct(fm)),)


# The canonical golden name payload: 1 record, deep-frozen (a mappingproxy —
# immutable through every route).
GOLDEN_CORRECT = _build_golden()[0]

# The canonical BYTE-EXACT engine name, for the resolved-slot surfaces that
# want the bare string (the same value GOLDEN_CORRECT["name"] carries).
GOLDEN_ENGINE_NAME = GOLDEN_CORRECT["name"]


# ---------------------------------------------------------------------------
# Fail-closed payload invariant — the offline gate the self-test and `--plan`
# both ride on. A drifted field-map or a drifted candidate is REFUSED with
# exit 5, never tolerated.
# ---------------------------------------------------------------------------
def _candidate_names(candidate):
    """All names a candidate surface exposes, or None when the surface is
    malformed (fail-closed: malformed is NEVER a pass, and it is distinct
    from a well-formed surface carrying no name at all)."""
    if isinstance(candidate, str):
        return (candidate,)
    if isinstance(candidate, dict):
        if isinstance(candidate.get("pipelines"), list):
            return tuple(
                p.get("name") for p in candidate["pipelines"]
                if isinstance(p, dict) and isinstance(p.get("name"), str))
        if isinstance(candidate.get("name"), str):
            return (candidate["name"],)
    return None


def _judge(candidate, want: str, *, out) -> int:
    """The fail-closed name-law gate. Returns the exit code: 0 PASS, 5
    REFUSED (mismatch family). Emits the ONE JSON report object on stdout;
    human notes go to out (stderr)."""
    found = _candidate_names(candidate)
    detail = ""
    ok = False
    if found is None:
        detail = ("the candidate is not a name string, a {'name': ...} object, "
                  "or a {'pipelines': [...]} listing — malformed read, never a "
                  "pass (fail-closed)")
    elif want not in found:
        detail = ("AF-AE-NAME-MISSING: the engine name %r is ABSENT from the "
                  "candidate — renamed, near-miss, or removed (found: %s). "
                  "Find-and-bind would fail silently."
                  % (want, ", ".join(repr(n) for n in found) or "(none)"))
    else:
        ok = True
        detail = ("engine name %r present BYTE-EXACT (the find-and-bind law)"
                  % want)
    print(json.dumps({
        "contract": FIXTURE_CONTRACT,
        "schema_version": 1,
        "ok": ok,
        "verdict": "PASS" if ok else "REFUSED",
        "expected": {"name": want},
        "found": list(found) if found is not None else None,
        "detail": detail,
    }, indent=2, sort_keys=True))
    if not ok:
        out.write("[golden-correct] REFUSED: %s\n" % detail)
        return EX_MISMATCH
    return EX_OK


def payload(candidate, field_map: dict, *, out=None) -> int:
    """Judge a candidate name surface against the golden contract.

    READ-ONLY: derives the golden name from the field-map and asserts the
    byte-level invariant — the candidate carries the contract name BYTE-EXACT
    ("Anthology Engine" -> PASS). The candidate is a bare name string (the
    config surface), a {"name": ...} object, or a {"pipelines": [...]}
    listing (the live read surface). Any deviation is a FAIL-CLOSED exit 5,
    never a blind pass. Emits the ONE JSON report object on stdout; human
    notes go to out (stderr)."""
    out = out or sys.stderr
    try:
        want = golden_engine_name(field_map)
    except FixtureError as exc:
        print(json.dumps({
            "contract": FIXTURE_CONTRACT,
            "schema_version": 1,
            "ok": False,
            "verdict": "REFUSED",
            "expected": None,
            "found": None,
            "detail": str(exc),
        }, indent=2, sort_keys=True))
        out.write("[golden-correct] payload REFUSED: %s\n" % exc)
        return EX_MISMATCH
    return _judge(candidate, want, out=out)


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: golden coherence + attack fixtures, no network, no
# secrets. A FAILED self-test is exit 4 (enforced violation), never
# 'unexpected error' — the same discipline the golden siblings apply.
# ---------------------------------------------------------------------------
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[golden-correct] SELF-TEST FAILED "
                         "(AF-AE-GOLDENCORRECT-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    from types import MappingProxyType
    field_map = reg.load_field_map(FIELD_MAP_PATH)
    pconf = _contract_pipeline(field_map)
    name = _contract_engine_name(pconf)

    # ---- contract coherence: the map is the single source of truth ---------
    assert name == "Anthology Engine", \
        "standard_pipeline_name drifted from the U03 contract (got %r)" % name
    assert name.strip() == name, \
        "the contract name must be byte-stable with no surrounding whitespace"

    # ---- the canonical fixture: name byte-exact, deep-frozen ---------------
    assert isinstance(GOLDEN_CORRECT, MappingProxyType), \
        "GOLDEN_CORRECT must be mappingproxy-frozen"
    assert GOLDEN_CORRECT["name"] == name, \
        "the golden name must byte-equal the map's standard_pipeline_name"
    assert GOLDEN_ENGINE_NAME == name, \
        "GOLDEN_ENGINE_NAME must byte-equal the map's standard_pipeline_name"
    assert GOLDEN_ENGINE_NAME == "Anthology Engine", \
        "golden engine name drifted from the U03 contract"

    # ---- the payload surfaces cover the name on every shape ----------------
    cfg = golden_correct_payload(field_map)
    assert cfg == {"name": name}, "config surface must carry exactly the name"
    listing = golden_listing_payload(field_map)
    assert isinstance(listing, dict) and isinstance(listing.get("pipelines"), list) \
        and len(listing["pipelines"]) == 1, "listing surface must carry one row"
    assert listing["pipelines"][0]["id"] == GOLDEN_PIPELINE_ID
    assert listing["pipelines"][0]["name"] == name

    # ---- the canonical fixture can never be mutated through the surface -----
    before = GOLDEN_CORRECT["name"]

    def _try_rebind():  # subscript assignment on a mappingproxy -> TypeError
        GOLDEN_CORRECT["name"] = "Anthology Engine MUTATED"  # noqa: B034 -- deliberately attempted

    try:
        _try_rebind()
        raise AssertionError("the canonical fixture must be immutable")
    except TypeError:
        pass
    assert GOLDEN_CORRECT["name"] == before, \
        "the canonical fixture changed during the self-test"
    # golden_correct() returns a deep copy: mutating it never touches the canon.
    copy_ = golden_correct(field_map)
    copy_["name"] = "Anthology Engine MUTATED"
    assert GOLDEN_CORRECT["name"] == before, \
        "the returned copy must not alias the canonical payload"

    # ---- attack fixtures: every drift REFUSED, never shipped ----------------
    # 1. missing pipeline section -> FixtureError
    try:
        golden_correct({"$note": "no pipeline section"})
        raise AssertionError("a missing pipeline section was NOT refused")
    except FixtureError:
        pass
    # 2. empty pipeline name -> FixtureError
    tampered = copy.deepcopy(field_map)
    tampered["pipeline"]["standard_pipeline_name"] = "  "
    try:
        golden_correct(tampered)
        raise AssertionError("an empty pipeline name was NOT refused")
    except FixtureError:
        pass
    # 3. non-string pipeline name -> FixtureError
    tampered = copy.deepcopy(field_map)
    tampered["pipeline"]["standard_pipeline_name"] = 42
    try:
        golden_correct(tampered)
        raise AssertionError("a non-string pipeline name was NOT refused")
    except FixtureError:
        pass

    # ---- the payload gate: golden exits 0, every drift exits 5 --------------
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload("Anthology Engine", field_map, out=io.StringIO())
    assert rc == EX_OK, "payload on the golden name must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["contract"] == FIXTURE_CONTRACT
    assert parsed["expected"] == {"name": "Anthology Engine"}
    # every candidate surface must PASS on the golden name
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload({"name": name}, field_map, out=io.StringIO()) == EX_OK, \
            "the object surface must also exit 0 on the golden name"
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload(golden_listing_payload(field_map), field_map,
                       out=io.StringIO()) == EX_OK, \
            "the live listing surface must also exit 0 on the golden name"
    # renamed -> REFUSED exit 5, proven in found
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc2 = payload("Anthology Engine RENAMED", field_map, out=io.StringIO())
    assert rc2 == EX_MISMATCH, "renamed payload must exit 5, got %s" % rc2
    parsed2 = json.loads(buf2.getvalue())
    assert parsed2["ok"] is False and parsed2["verdict"] == "REFUSED"
    assert "RENAMED" in parsed2["found"][0], \
        "the drifted name must be PROVEN in found: %s" % parsed2["found"]
    # near-miss (case / joining / trailing whitespace) -> REFUSED exit 5
    # (the name law is BYTE-EXACT: near is not present)
    for near in ("Anthology engine", "AnthologyEngine", "Anthology Engine "):
        with contextlib.redirect_stdout(io.StringIO()):
            assert payload(near, field_map, out=io.StringIO()) == EX_MISMATCH, \
                "near-miss %r must exit 5 (byte-exact law)" % near
    # renamed inside a live listing -> REFUSED exit 5
    listing_bad = copy.deepcopy(golden_listing_payload(field_map))
    listing_bad["pipelines"][0]["name"] = "Anthology Engine RENAMED"
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload(listing_bad, field_map, out=io.StringIO()) == EX_MISMATCH, \
            "a renamed listing must exit 5"
    # absent name -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload({"pipelines": []}, field_map, out=io.StringIO()) == EX_MISMATCH, \
            "an absent name must exit 5"
    # empty name string -> REFUSED exit 5 (never a pass)
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload("", field_map, out=io.StringIO()) == EX_MISMATCH, \
            "an empty name must exit 5"
    # malformed candidate -> REFUSED exit 5 (never a pass)
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload({"no_name_here": True}, field_map,
                       out=io.StringIO()) == EX_MISMATCH, \
            "a malformed candidate must exit 5"
    # empty name law -> REFUSED exit 5 (no contract source)
    bad_map = copy.deepcopy(field_map)
    bad_map["pipeline"]["standard_pipeline_name"] = ""
    with contextlib.redirect_stdout(io.StringIO()):
        assert payload("Anthology Engine", bad_map, out=io.StringIO()) == EX_MISMATCH, \
            "an empty name law must exit 5"

    # ---- never-print: no credential-shaped string on any surface -----------
    all_text = buf.getvalue() + buf2.getvalue()
    for token in ("pit-", "Bearer "):
        assert token not in all_text, \
            "surface leak: %r must never appear" % token

    dev.write("golden_correct self-test: OK (name law pinned byte-exact to "
              "field-map pipeline.standard_pipeline_name %r; config + object "
              "+ live listing payload surfaces; canonical mappingproxy-frozen "
              "immutability + deep-copy surface; 3 attack fixtures refused "
              "(missing-pipeline-section / empty-name / non-string-name); "
              "payload gate exits 0 on the golden name across every surface, "
              "5 on renamed / near-miss / absent / empty / malformed / "
              "empty-name-law; never-print)\n" % name)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="golden_correct.py",
        description="Golden name fixture for the U03 self-tests (Skill 59): "
                    "the canonical BYTE-EXACT engine name derived from "
                    "config/field-map.json pipeline.standard_pipeline_name, "
                    "fail-closed.")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (the single source of truth)")
    ap.add_argument("cmd", nargs="?", choices=["payload", "plan", "self-test"],
                    default="payload")

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
        if args.cmd == "plan":
            # Offline plan (no network, no credentials): the golden engine
            # name, straight from the field-map — never a hardcoded list.
            print(json.dumps({
                "contract": FIXTURE_CONTRACT + "-plan",
                "schema_version": 1,
                "engine_name": golden_engine_name(field_map),
                "dry_run": True,
                "note": "offline plan only — no network, no credential needed",
            }, indent=2, sort_keys=True))
            return EX_OK
        # payload: the candidate arrives on stdin, read from NO network (the
        # live READER is the sibling checker, which rides reg.CafClient and
        # its CAF_BROWSER_UA — this fixture never touches the wire). The
        # candidate is a bare JSON string, a {"name": ...} object, or a
        # {"pipelines": [...]} listing.
        try:
            candidate = json.load(sys.stdin)
        except ValueError as exc:
            sys.stderr.write("[golden-correct] the name candidate on stdin is "
                             "not valid JSON: %s\n" % exc)
            return EX_MISMATCH
        return payload(candidate, field_map)
    except FixtureError as exc:
        sys.stderr.write("[golden-correct] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except FileNotFoundError as exc:
        sys.stderr.write("[golden-correct] file not found: %s\n" % exc)
        return EX_ERR
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[golden-correct] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
