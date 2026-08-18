#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u02_modules/golden_pipeline.py
# GOLDEN PIPELINE PAYLOAD FIXTURE (U02 tooling, extension module) — the single
# canonical in-memory payload of the standard Anthology Convert and Flow
# pipeline (BYTE-EXACT name + the NINE contract stages BY NAME IN ORDER),
# derived BYTE-FOR-BYTE from config/field-map.json pipeline.standard_pipeline_
# name + pipeline.standard_stages (the single source of truth).
#
# WHERE THIS SITS: scripts/u02_modules/ — an importable module under the U02
# template-verify tooling, exactly like its siblings golden_fields.py and
# golden_forms.py. It is NOT a manifest row and NOT a checker: it ships the
# GOLDEN pipeline-state surface the self-tests of the U02 verifier and the
# sibling check modules assert against (pipeline_check.check_pipeline_name,
# stages_check.check_stages, live_verify_template.check_pipeline,
# delta_reporter.live_delta_report), so every checker's happy path is judged
# against the SAME payload and a drift in the field-map contract breaks THIS
# module's self-test first (fail-closed: an inconsistent map is a refusal,
# never a blind pass). Imported BY NAME as u02_modules.golden_pipeline, per
# the u02_modules package contract in __init__.py (pure namespace container).
#
# WHAT THIS OWNS:
#   1. GOLDEN_PIPELINE — a frozen, deterministic single-pipeline payload
#      exactly as a live GET /opportunities/pipelines read of a fully
#      provisioned location serves it: {"id", "name", "stages": [...]}. The
#      id is a stable synthetic pipeline id (pipe_golden); the name BYTE-EQUALs
#      the map's pipeline.standard_pipeline_name; one stage record per map
#      standard_stages row ({position, name, id}) in CONTRACT ORDER with
#      contiguous positions 0..8 (Intake .. Assembled). The canonical payload
#      is DEEP-FROZEN: the tuple of records is a tuple of MappingProxyType
#      records (stdlib types module), so a golden record can never be mutated
#      through the module's public surface — the self-test proves every
#      mutation route raises.
#   2. golden_pipeline(field_map) — the builder, fail-closed: a missing or
#      malformed pipeline section, a non-object stage row, a position that
#      does not match its index (the contract must be contiguous 0..8), a
#      blank or duplicate stage name, or an empty pipeline name raises
#      FixtureError instead of shipping a wrong fixture. 9 is the contract
#      stage count, pinned by the U02 contract — never "however many the
#      pipeline carries".
#   3. golden_pipeline_payload(field_map) — the full listing object the live
#      read serves for the golden state: {"pipelines": [GOLDEN_PIPELINE]} —
#      the exact shape the name-law gate (attack_wrong_name.verify) and the
#      pipeline/stage checkers judge.
#   4. golden_stage_ids(field_map) — the sorted stage-name -> stage-id map
#      (the resolved-slot surface: a per-box field-map resolved.stage_ids
#      stamp must pin the SAME ids — the registry's _stage_id_map law, name ->
#      id, with the golden fixture as the fixed reference).
#   5. payload — a FAIL-CLOSED byte-level invariant gate over a pipelines
#      listing: the standard pipeline present BYTE-EXACT with all 9 stages in
#      order -> exit 0; ANY deviation (absent, renamed, stage drift) is a
#      REFUSED exit 5 with the ONE JSON report object on stdout — never a
#      blind pass, never a fabricated success.
#
# DOCTRINE (house, inherited from the registry / drive adapter / U02
# verifier — the SAME doctrine every sibling fixture carries):
#   - Never a token printed: credentials resolve BY LABEL only (SET / NOT
#     SET). This module holds NO credential surface and reads NO env var —
#     a fixture cannot leak what it never holds.
#   - Fail-closed: a malformed map, an absent section, a non-object read all
#     STOP or FAIL — never a blind pass, never a fabricated success.
#   - READ-ONLY: this module never creates, never writes, never mutates.
#   - BROWSER UA: any module that TALKS to GoHighLevel / Convert and Flow
#     (services.leadconnectorhq.com, Cloudflare-fronted) MUST carry a browser
#     User-Agent on every request — urllib's default "Python-urllib/x.y" is
#     403'd at the WAF edge (CF error 1010) before it ever reaches the API
#     (CAF_BROWSER_UA in anthology_registry.py is the house pattern). THIS
#     module makes NO network call and defines NO User-Agent constant of its
#     own; the client that DOES (reg.CafClient) already sends CAF_BROWSER_UA
#     on every request — the proven edge fix (W0.6 / GK-09 discipline). The
#     --live surface pipes a listing in and reads NOTHING from the network;
#     the live reader is pipeline_check.py / stages_check.py, which ride
#     reg.CafClient.
#   - Move in silence; NOTHING Anthropic in any runtime file; Convert and
#     Flow naming in every client surface.
#
# THE NAME AND THE STAGES ARE NEVER HARDCODED HERE (SPEC M8): they come from
# config/field-map.json pipeline.standard_pipeline_name + standard_stages —
# the SAME source of truth provision-pipeline binds by and the sibling
# checkers assert byte-exact. A drift in the CONTRACT is caught by the
# offline self-test (the golden state must match it), never silently.
#
# EXIT CODE CONTRACT (house convention; mirrors the U02 verifier and the
# golden sibling):
#   0  verified success — the golden pipeline is internally consistent and
#      byte-equal to the field-map contract; also self-test / plan OK
#   1  unexpected error (malformed/unreadable field-map JSON)
#   5  mismatch — the field-map drifted from the fixture contract (pipeline
#      section absent/malformed, name empty, stages != 9, non-contiguous
#      positions, blank/duplicate stage names), a listing deviates from the
#      golden payload (absent/renamed pipeline or stage drift), or the
#      payload gate REFUSED (all FAIL-CLOSED refusals)
#
# STDLIB ONLY. Calls NO model. Sibling import bootstrap identical to
# golden_fields.py / pipeline_check.py / live_verify_template.py:
# sys.path.insert to scripts/ then `import anthology_registry as reg`.
# =============================================================================
"""golden_pipeline.py — golden pipeline payload fixture (name + 9 stages) for
self-test."""

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

# The one fixed report contract. The pipeline NAME and the stage NAMES are
# NEVER hardcoded here — they come from the field-map (the single source of
# truth); a hardcoded name or stage list would drift and defeat the
# fixture's whole purpose.
FIXTURE_CONTRACT = "anthology-engine-golden-pipeline"

# The contract stage count, fixed by the U02 contract: EXACTLY nine stages
# (Intake, Avatar, Tone, Title, Outline, Chapter, Cover, Delivered,
# Assembled). Never "however many the pipeline carries" — the count is part
# of the contract (mirrors stages_check.EXPECTED_STAGE_COUNT).
EXPECTED_STAGE_COUNT = 9

# The stable synthetic pipeline id of the golden payload. The stage ids are
# derived positionally (stg_golden_0 .. stg_golden_8), matching the
# synthetic-id discipline of the sibling fixtures (pipe_tmpl / stg_<n>);
# a fixture id is never a real location id.
GOLDEN_PIPELINE_ID = "pipe_golden"

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value (e.g. "pit-abc123"). The label word "PIT" alone is NOT a credential
# shape — operator surfaces name labels, never values (the same pattern the
# delta_reporter / stages_check self-tests apply to their captured surfaces).
_CREDENTIAL_SHAPE = __import__("re").compile(r"pit-\S+")


class FixtureError(Exception):
    """A fail-closed fixture refusal (STOP/mismatch family): the field-map is
    inconsistent with the golden pipeline contract, so NO fixture is shipped —
    a wrong fixture is worse than no fixture."""


# ---------------------------------------------------------------------------
# Contract readers (fail-closed: a missing section is a refusal, never a pass)
# ---------------------------------------------------------------------------
def _contract_pipeline(field_map: dict) -> dict:
    pconf = field_map.get("pipeline")
    if not isinstance(pconf, dict):
        raise FixtureError(
            "field-map.json has no pipeline section — the golden pipeline "
            "payload has nothing to derive from; refusing a blind fixture "
            "(never fabricated).")
    return pconf


def _contract_pipeline_name(pconf: dict) -> str:
    name = pconf.get("standard_pipeline_name")
    if not isinstance(name, str) or not name.strip():
        raise FixtureError(
            "field-map pipeline.standard_pipeline_name is missing or empty — "
            "the name law (find-and-bind is BY NAME) has no contract source; "
            "refusing to ship a golden payload.")
    return name


def _contract_standard_stages(pconf: dict) -> list:
    raw = pconf.get("standard_stages")
    if not isinstance(raw, list):
        raise FixtureError(
            "field-map pipeline.standard_stages is not a list (%s) — refusing."
            % type(raw).__name__)
    out = [s for s in raw if isinstance(s, dict)]
    if len(out) != len(raw):
        raise FixtureError(
            "field-map pipeline.standard_stages carries non-object rows — "
            "refusing to derive a golden payload from a malformed inventory.")
    return out


# ---------------------------------------------------------------------------
# The golden builder — fail-closed, deterministic, byte-equal to the map.
# ---------------------------------------------------------------------------
def golden_pipeline(field_map: dict) -> dict:
    """Derive the golden pipeline payload (name + 9 stages) from the field-map.

    Each record is EXACTLY what a live /opportunities/pipelines read of a
    fully provisioned location returns: the pipeline name BYTE-EQUALs the
    map's standard_pipeline_name, one stage entry per map standard_stages
    row ({position, name, id}) IN CONTRACT ORDER with contiguous positions
    0..8, and stable synthetic ids (pipe_golden / stg_golden_<n>). Raises
    FixtureError on ANY contract drift — a wrong fixture is never shipped.

    The returned dict is a deep copy; mutating it never touches the internal
    canonical payload (which itself stores stages in a tuple)."""
    pconf = _contract_pipeline(field_map)
    name = _contract_pipeline_name(pconf)
    stages = _contract_standard_stages(pconf)
    if len(stages) != EXPECTED_STAGE_COUNT:
        raise FixtureError(
            "field-map pipeline.standard_stages must carry exactly %d stages "
            "(the U02 nine-stage contract), got %d — the map drifted; refusing "
            "to ship a golden payload."
            % (EXPECTED_STAGE_COUNT, len(stages)))

    seen = {}
    out_stages = []
    for i, entry in enumerate(stages):
        if entry.get("position") != i:
            raise FixtureError(
                "field-map stage %d position %r != %d — the contract must be "
                "contiguous 0..%d; refusing."
                % (i, entry.get("position"), i, EXPECTED_STAGE_COUNT - 1))
        nm = entry.get("name")
        if not isinstance(nm, str) or not nm:
            raise FixtureError(
                "field-map stage %d name missing or empty — refusing." % i)
        if nm in seen:
            raise FixtureError(
                "duplicate stage name %r in the contract — refusing." % nm)
        seen[nm] = True
        out_stages.append({
            "position": i,
            "name": nm,
            "id": "stg_golden_%d" % i,
        })
    return copy.deepcopy({
        "id": GOLDEN_PIPELINE_ID,
        "name": name,
        "stages": out_stages,
    })


def golden_pipeline_payload(field_map: dict) -> dict:
    """The full listing object the live pipelines read serves for the golden
    state: {"pipelines": [golden_pipeline]} — exactly the shape a live GET
    /opportunities/pipelines read returns (reg.CafClient.list_pipelines
    returns out.get("pipelines") or []), so the live surface and the offline
    fixture surface share ONE shape. A deep copy; callers may mutate it."""
    return {"pipelines": [golden_pipeline(field_map)]}


def golden_stage_ids(field_map: dict) -> dict:
    """The sorted stage-name -> stage-id map (the resolved-slot surface).

    The registry's provision-pipeline stamps field-map resolved.stage_ids as
    name -> id from the LIVE read; those stamps must be CONSISTENT with this
    fixture's ids so a live read-back of the golden payload satisfies the
    id-consistency expectations of the checkers. The map is the source of
    truth for the ids, sorted deterministically."""
    return {s["name"]: s["id"] for s in
            sorted(golden_pipeline(field_map)["stages"],
                   key=lambda s: s["position"])}


# ---------------------------------------------------------------------------
# The golden fixture itself — derived ONCE at import, deep-frozen. The
# pipeline record is a MappingProxyType and the STAGES container is a tuple,
# so NO caller can mutate the canonical payload through the module's public
# surface — the self-test proves it. Consumers that need a mutable payload
# call golden_pipeline() / golden_pipeline_payload() (deep copies).
# ---------------------------------------------------------------------------
def _build_golden() -> tuple:
    from types import MappingProxyType
    fm = reg.load_field_map(FIELD_MAP_PATH)
    pipe = golden_pipeline(fm)
    return (
        MappingProxyType({
            "id": pipe["id"],
            "name": pipe["name"],
            "stages": tuple(
                MappingProxyType(dict(s)) for s in pipe["stages"]),
        }),
    )


# The canonical golden pipeline payload: 1 pipeline record, deep-frozen (a
# tuple of one mappingproxy record with tuple-of-mappingproxy stages —
# immutable through every route).
GOLDEN_PIPELINE = _build_golden()[0]


# ---------------------------------------------------------------------------
# Fail-closed payload invariant — the offline gate the self-test and `--plan`
# both ride on. A drifted field-map or a drifted listing is REFUSED with
# exit 5, never tolerated.
# ---------------------------------------------------------------------------
def _judge_listing(listing, want_name, want_names, *, out) -> int:
    """The fail-closed gate over a pipelines LISTING payload. Returns the
    exit code: 0 PASS, 5 REFUSED (mismatch family). Emits the ONE JSON report
    object on stdout; human notes go to out (stderr)."""
    found_names = []
    if isinstance(listing, dict) and isinstance(listing.get("pipelines"), list):
        found_names = sorted({p.get("name") for p in listing["pipelines"]
                              if isinstance(p, dict) and p.get("name")})
    detail = ""
    ok = False
    if not isinstance(listing, dict) or not isinstance(listing.get("pipelines"), list):
        detail = "listing payload is not an object with a 'pipelines' array — malformed read, never a pass (fail-closed)"
    else:
        found = next((p for p in listing["pipelines"]
                      if isinstance(p, dict) and p.get("name") == want_name), None)
        if found is None:
            detail = ("AF-AE-TEMPLATE-PIPELINE-MISSING: the standard pipeline %r "
                      "is ABSENT from the listing — renamed, removed, or "
                      "near-miss (found: %s). Find-and-bind would fail "
                      "silently." % (want_name, ", ".join(found_names) or "(none)"))
        else:
            live_stages = [s for s in (found.get("stages") or [])
                           if isinstance(s, dict)]
            live_names = [s.get("name") or "" for s in live_stages]
            live_pos = [s.get("position") for s in live_stages]
            # The stage law is BYTE-EXACT in both senses: the LIST ORDER of
            # the stage entries must equal the contract order AND the position
            # field must be the contiguous 0..N index — keying only on the
            # position field would miss a UI reorder that renumbers positions.
            if (len(live_stages) == EXPECTED_STAGE_COUNT
                    and live_names == want_names
                    and live_pos == list(range(EXPECTED_STAGE_COUNT))):
                ok = True
                detail = ("standard pipeline %r present BYTE-EXACT with all %d "
                          "stages by name in order, positions 0..%d"
                          % (want_name, EXPECTED_STAGE_COUNT,
                             EXPECTED_STAGE_COUNT - 1))
            else:
                detail = ("stage drift: expected %s in list order with positions "
                          "0..%d; live %s with positions %s"
                          % (want_names, EXPECTED_STAGE_COUNT - 1,
                             live_names, live_pos))
    print(json.dumps({
        "contract": FIXTURE_CONTRACT,
        "schema_version": 1,
        "ok": ok,
        "verdict": "PASS" if ok else "REFUSED",
        "expected": {"name": want_name, "stages": want_names},
        "found": found_names,
        "detail": detail,
    }, indent=2, sort_keys=True))
    if not ok:
        out.write("[golden-pipeline] REFUSED: %s\n" % detail)
        return EX_MISMATCH
    return EX_OK


def payload(listing: dict, field_map: dict, *, out=None) -> int:
    """Validate a pipelines listing against the golden pipeline contract.

    READ-ONLY: derives the golden pipeline from the field-map and asserts the
    byte-level invariant — the standard pipeline present BYTE-EXACT with all
    9 contract stages by name in order. Any deviation is a FAIL-CLOSED exit 5,
    never a blind pass. Emits the ONE JSON report object on stdout; human
    notes go to out (stderr)."""
    out = out or sys.stderr
    try:
        pipe = golden_pipeline(field_map)
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
        out.write("[golden-pipeline] payload REFUSED: %s\n" % exc)
        return EX_MISMATCH
    want_names = [s["name"] for s in pipe["stages"]]
    return _judge_listing(listing, pipe["name"], want_names, out=out)


# ---------------------------------------------------------------------------
# Self-test — OFFLINE: golden coherence + attack fixtures, no network, no
# secrets. A FAILED self-test is exit 4 (enforced violation), never
# 'unexpected error' — the same discipline the golden sibling applies.
# ---------------------------------------------------------------------------
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[golden-pipeline] SELF-TEST FAILED "
                         "(AF-AE-GOLDENPIPELINE-* family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    from types import MappingProxyType
    field_map = reg.load_field_map(FIELD_MAP_PATH)
    pconf = _contract_pipeline(field_map)
    name = _contract_pipeline_name(pconf)
    stages = _contract_standard_stages(pconf)

    # ---- contract coherence: the map is the single source of truth ---------
    assert len(stages) == EXPECTED_STAGE_COUNT, \
        "field-map must carry exactly 9 stages (the U02 contract), got %d" % len(stages)
    assert name == "Anthology Engine", \
        "standard_pipeline_name drifted from the U02 contract (got %r)" % name
    assert [s.get("name") for s in stages] == \
        ["Intake", "Avatar", "Tone", "Title", "Outline", "Chapter", "Cover",
         "Delivered", "Assembled"], "field-map standard stages drifted"
    assert [s.get("position") for s in stages] == list(range(9)), \
        "field-map stage positions must be contiguous 0..8"
    assert len(set(s.get("name") for s in stages)) == EXPECTED_STAGE_COUNT, \
        "stage names must be unique"

    # ---- the canonical fixture: name + 9 stages, byte-exact, deep-frozen ----
    assert isinstance(GOLDEN_PIPELINE, MappingProxyType), \
        "GOLDEN_PIPELINE must be mappingproxy-frozen"
    assert GOLDEN_PIPELINE["id"] == GOLDEN_PIPELINE_ID
    assert GOLDEN_PIPELINE["name"] == name, \
        "golden name must byte-equal the map's standard_pipeline_name"
    assert isinstance(GOLDEN_PIPELINE["stages"], tuple), \
        "golden stages container must be a tuple (immutable canonical surface)"
    golden_stages = GOLDEN_PIPELINE["stages"]
    assert len(golden_stages) == EXPECTED_STAGE_COUNT
    assert [s["name"] for s in golden_stages] == [s.get("name") for s in stages], \
        "golden stage names/order must equal the map's standard stages in order"
    assert [s["position"] for s in golden_stages] == list(range(9)), \
        "golden stage positions must be contiguous 0..8"
    for i, s in enumerate(golden_stages):
        assert isinstance(s, MappingProxyType), "golden stage %d must be frozen" % i
        assert s["id"] == "stg_golden_%d" % i, s["id"]
    assert GOLDEN_PIPELINE["name"] == "Anthology Engine", \
        "golden pipeline name drifted from the U02 contract"

    # ---- the payload surface and the id map cover every stage --------------
    listing = golden_pipeline_payload(field_map)
    assert isinstance(listing, dict) and isinstance(listing.get("pipelines"), list) \
        and len(listing["pipelines"]) == 1
    assert listing["pipelines"][0]["name"] == name
    ids = golden_stage_ids(field_map)
    assert len(ids) == EXPECTED_STAGE_COUNT and sorted(ids) == \
        sorted(s["name"] for s in golden_stages)
    for s in golden_stages:
        assert ids[s["name"]] == s["id"]

    # ---- the canonical fixture can never be mutated through the surface -----
    def _fp():
        return tuple(
            tuple(sorted((k, tuple((k2, v2) for k2, v2 in it.items()))
                         if isinstance(it, MappingProxyType) else (k, it)
                         for k, it in item.items()))
            for item in (GOLDEN_PIPELINE,))

    before = _fp()

    def _try_rebind():        # attribute assignment on a mappingproxy -> TypeError
        GOLDEN_PIPELINE["id"] = "pipe_MUTATED"  # noqa: B034 -- deliberately attempted

    def _try_mutate_stage():  # subscript assignment on a mappingproxy -> TypeError
        GOLDEN_PIPELINE["stages"][0]["name"] = "Intake MUTATED"  # noqa: B034

    def _try_swap_stage():    # subscript assignment on a tuple -> TypeError
        GOLDEN_PIPELINE["stages"][0] = {"position": 0, "name": "Intake", "id": "x"}  # noqa: B034

    for attempt in (_try_rebind, _try_mutate_stage, _try_swap_stage):
        try:
            attempt()
            raise AssertionError("the canonical fixture must be immutable")
        except TypeError:
            pass
    assert _fp() == before, "the canonical fixture changed during the self-test"
    # golden_pipeline() returns a deep copy: mutating it never touches the canon.
    copy_ = golden_pipeline(field_map)
    copy_["name"] = "Anthology Engine RENAMED"
    copy_["stages"][0]["name"] = "Intake MUTATED"
    assert GOLDEN_PIPELINE["name"] == name and \
        GOLDEN_PIPELINE["stages"][0]["name"] == "Intake", \
        "the returned copy must not alias the canonical payload"

    # ---- attack fixtures: every drift REFUSED, never shipped ----------------
    # 1. missing pipeline section -> FixtureError
    try:
        golden_pipeline({"$note": "no pipeline section"})
        raise AssertionError("a missing pipeline section was NOT refused")
    except FixtureError:
        pass
    # 2. empty pipeline name -> FixtureError
    tampered = copy.deepcopy(field_map)
    tampered["pipeline"]["standard_pipeline_name"] = "  "
    try:
        golden_pipeline(tampered)
        raise AssertionError("an empty pipeline name was NOT refused")
    except FixtureError:
        pass
    # 3. eight stages -> FixtureError
    tampered = copy.deepcopy(field_map)
    tampered["pipeline"]["standard_stages"] = tampered["pipeline"]["standard_stages"][:8]
    try:
        golden_pipeline(tampered)
        raise AssertionError("an 8-stage contract was NOT refused")
    except FixtureError:
        pass
    # 4. non-contiguous positions -> FixtureError
    tampered = copy.deepcopy(field_map)
    tampered["pipeline"]["standard_stages"] = [
        dict(s) for s in tampered["pipeline"]["standard_stages"][:2]
    ] + [{"position": i + 1, "name": n}
         for i, n in enumerate([s["name"] for s in tampered["pipeline"]["standard_stages"][2:]])]
    try:
        golden_pipeline(tampered)
        raise AssertionError("non-contiguous positions were NOT refused")
    except FixtureError:
        pass
    # 5. duplicate stage name -> FixtureError
    tampered = copy.deepcopy(field_map)
    tampered["pipeline"]["standard_stages"][7]["name"] = \
        tampered["pipeline"]["standard_stages"][6]["name"]
    try:
        golden_pipeline(tampered)
        raise AssertionError("a duplicate stage name was NOT refused")
    except FixtureError:
        pass
    # 6. blank stage name -> FixtureError
    tampered = copy.deepcopy(field_map)
    tampered["pipeline"]["standard_stages"][3]["name"] = ""
    try:
        golden_pipeline(tampered)
        raise AssertionError("a blank stage name was NOT refused")
    except FixtureError:
        pass
    # 7. non-object stage row -> FixtureError
    tampered = copy.deepcopy(field_map)
    tampered["pipeline"]["standard_stages"][3] = "not-a-dict"
    try:
        golden_pipeline(tampered)
        raise AssertionError("a non-object stage row was NOT refused")
    except FixtureError:
        pass
    # 8. standard_stages not a list -> FixtureError
    tampered = copy.deepcopy(field_map)
    tampered["pipeline"]["standard_stages"] = "not-a-list"
    try:
        golden_pipeline(tampered)
        raise AssertionError("a non-list standard_stages was NOT refused")
    except FixtureError:
        pass

    # ---- the payload gate: golden exits 0, every drift exits 5 --------------
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(golden_pipeline_payload(field_map), field_map, out=io.StringIO())
    assert rc == EX_OK, "payload on the true listing must exit 0, got %s" % rc
    parsed = json.loads(buf.getvalue())
    assert parsed["ok"] is True and parsed["verdict"] == "PASS"
    assert parsed["contract"] == FIXTURE_CONTRACT
    # renamed pipeline -> REFUSED exit 5
    buf2 = io.StringIO()
    renamed = copy.deepcopy(golden_pipeline_payload(field_map))
    renamed["pipelines"][0]["name"] = "Anthology Engine RENAMED"
    with contextlib.redirect_stdout(buf2):
        rc2 = payload(renamed, field_map, out=io.StringIO())
    assert rc2 == EX_MISMATCH, "renamed payload must exit 5, got %s" % rc2
    parsed2 = json.loads(buf2.getvalue())
    assert parsed2["ok"] is False and parsed2["verdict"] == "REFUSED"
    assert "RENAMED" in parsed2["found"][0], \
        "the drifted name must be PROVEN in found: %s" % parsed2["found"]
    # stage drift (reordered) -> REFUSED exit 5
    reordered = copy.deepcopy(golden_pipeline_payload(field_map))
    st = reordered["pipelines"][0]["stages"]
    st[4], st[5] = st[5], st[4]
    with contextlib.redirect_stdout(io.StringIO()):
        rc3 = payload(reordered, field_map, out=io.StringIO())
    assert rc3 == EX_MISMATCH, "reordered payload must exit 5, got %s" % rc3
    # absent pipeline -> REFUSED exit 5
    with contextlib.redirect_stdout(io.StringIO()):
        rc4 = payload({"pipelines": []}, field_map, out=io.StringIO())
    assert rc4 == EX_MISMATCH, "absent payload must exit 5, got %s" % rc4
    # malformed listing -> REFUSED exit 5 (never a pass)
    with contextlib.redirect_stdout(io.StringIO()):
        rc5 = payload({"no_pipelines_here": True}, field_map, out=io.StringIO())
    assert rc5 == EX_MISMATCH, "malformed payload must exit 5, got %s" % rc5
    # empty name law -> REFUSED exit 5 (no contract source)
    bad_map = copy.deepcopy(field_map)
    bad_map["pipeline"]["standard_pipeline_name"] = ""
    with contextlib.redirect_stdout(io.StringIO()):
        rc6 = payload(golden_pipeline_payload(field_map), bad_map, out=io.StringIO())
    assert rc6 == EX_MISMATCH, "empty name law must exit 5, got %s" % rc6

    # ---- never-print: no credential-shaped string on any surface -----------
    all_text = buf.getvalue() + buf2.getvalue()
    for token in ("pit-", "Bearer "):
        assert token not in all_text, \
            "surface leak: %r must never appear" % token

    dev.write("golden_pipeline self-test: OK (name law pinned byte-exact to "
              "field-map pipeline.standard_pipeline_name %r; 9 stages by name "
              "in order with contiguous positions 0..8; canonical deep-frozen "
              "immutability + deep-copy surface; 8 attack fixtures refused "
              "(missing-pipeline-section / empty-name / 8-stages / "
              "non-contiguous-positions / duplicate-stage-name / blank-stage-"
              "name / non-object-stage-row / non-list-stages); payload gate "
              "exits 0 on golden, 5 on renamed / reordered / absent / "
              "malformed / empty-name-law; never-print)\n" % name)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="golden_pipeline.py",
        description="Golden pipeline payload fixture (name + 9 stages) for "
                    "the U02 self-tests (Skill 59): derive the canonical "
                    "pipelines-listing payload byte-exact from "
                    "config/field-map.json, fail-closed.")
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
            # Offline plan (no network, no credentials): the golden pipeline
            # state, straight from the field-map — never a hardcoded list.
            pipe = golden_pipeline(field_map)
            print(json.dumps({
                "contract": FIXTURE_CONTRACT + "-plan",
                "schema_version": 1,
                "pipeline": {
                    "id": pipe["id"],
                    "name": pipe["name"],
                    "stages": [s["name"] for s in pipe["stages"]],
                    "positions": [s["position"] for s in pipe["stages"]],
                },
                "dry_run": True,
                "note": "offline plan only — no network, no credential needed",
            }, indent=2, sort_keys=True))
            return EX_OK
        # payload: the listing arrives on stdin, read from NO network (the
        # live READER is pipeline_check.py / stages_check.py, which ride
        # reg.CafClient and its CAF_BROWSER_UA — this fixture never touches
        # the wire).
        try:
            listing = json.load(sys.stdin)
        except ValueError as exc:
            sys.stderr.write("[golden-pipeline] the pipelines listing on stdin "
                             "is not valid JSON: %s\n" % exc)
            return EX_MISMATCH
        return payload(listing, field_map)
    except FixtureError as exc:
        sys.stderr.write("[golden-pipeline] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except FileNotFoundError as exc:
        sys.stderr.write("[golden-pipeline] file not found: %s\n" % exc)
        return EX_ERR
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[golden-pipeline] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
