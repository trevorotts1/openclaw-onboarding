#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u03_modules/golden_wrong.py  (U03 tooling)
# GOLDEN WRONG-NAME FIXTURE — the canonical RENAMED-STATE payload of the U03
# name-law family, built BYTE-FOR-BYTE from config/field-map.json (the single
# source of truth) with the standard pipeline's name overridden to the WRONG
# name "Anthology Writer". It is the golden-half pair of the U03 drift gate:
# the sibling rename_checker.py applies the name law over a LIVE read (name ==
# "Anthology Engine", byte-exact) and name_reader.py reads every pipeline name;
# THIS module ships the state the checks must DETECT — the listing a live read
# of the DRIFTED location serves after the standard pipeline was renamed.
#
# WHY THE WRONG NAME IS "ANTHOLOGY WRITER": Skill 54 (Anthology Writer) is the
# engine's SIBLING SKILL — the per-chapter authoring core the engine CALLS
# (SKILL.md; it never re-authors the chapter pipeline). A renamed pipeline most
# plausibly drifts to the sibling's name: a template built under the authoring
# IP binds the wrong skill's pipeline by name, and find-and-bind is BY NAME
# (MASTERDOC floor 11; anthology_registry.py provision-pipeline). A RENAMED
# pipeline is indistinguishable from an ABSENT one to find-by-name, so the
# wrong state is exactly the drift that would silently unbind onboarding —
# the AF-AE-TEMPLATE-PIPELINE-MISSING family the U02 name check and the U03
# re-verification both refuse.
#
# WHAT THIS OWNS
#   1. WRONG_PIPELINE_NAME — "Anthology Writer", the canonical wrong name the
#      fixture carries (the SAME attack value u02_modules/attack_wrong_name.py
#      pins). THE ONE name hardcoded here BY DESIGN: it is the ATTACK value,
#      not a contract value. The contract name is NEVER hardcoded (SPEC M8) —
#      it comes from config/field-map.json pipeline.standard_pipeline_name.
#   2. golden_wrong_pipeline(field_map) — the canonical RENAMED pipeline row:
#      id "pipe_tmpl", name BYTE-EXACT WRONG_PIPELINE_NAME, the NINE contract
#      stages in position order (positions 0..8, contiguous, from the field-map
#      standard_stages) — a PURE RENAME, never a rebuild: the drift the U03
#      family exists to catch keeps every stage intact. Fail-closed builder:
#      an absent/malformed pipeline section, a stage count != 9, a non-
#      contiguous position, a blank or duplicate stage name, an empty contract
#      name, or a contract name that COLLIDES with the attack value raises
#      FixtureError — the fixture NEVER fabricates a renamed state.
#   3. golden_wrong_listing(field_map) — the full listing object a live read
#      of the drifted location serves: {"pipelines": [golden_wrong_pipeline]}
#      — exactly the shape the name-law checks (rename_checker.check_name,
#      name_reader.py) and the sibling attack fixture judge.
#   4. wrong_state(field_map) — the EXACT verdict dict rename_checker.check_name
#      returns on this fixture: {"ok": False, "current": "", "expected": <the
#      contract name>}. check_name finds BY THE WANTED NAME, so on the renamed
#      state it reports current "" — a rename reads IDENTICALLY to an absence
#      (that is the point of the law). ok False is the detection verdict; THIS
#      module's own gate below is what proves the wrong name is actually ON the
#      listing.
#   5. detect(payload, want_name="") — the fail-closed DETECTION gate over a
#      pipelines LISTING payload ({"pipelines": [...]} — exactly the object a
#      live GET /opportunities/pipelines read serves, so the live surface and
#      the offline fixture surface share ONE implementation):
#        - the wrong name present BYTE-EXACT, the contract name ABSENT ->
#          ("DETECTED", names, stage_count) with the wrong name PROVEN in the
#          found set — the golden wrong state is on the listing
#        - the wrong name ABSENT (a healthy listing, an empty listing, a
#          rename to anything else), the contract name ALSO present (an
#          ambiguous both-present state), a malformed payload, a non-dict
#          entry, or an entry without a non-empty string name -> raises
#          WrongStateError (STOP family, never a pass): a listing that does
#          not carry the wrong name is NEVER certified as the wrong state —
#          a healthy state cannot masquerade as a detected drift, never a
#          silent fallback
#   6. payload(*, out) — the CLI gate: emits the ONE JSON report object
#      (contract / ok / verdict / expected / found / stage_count / detail);
#      DETECTED is exit 0 with the wrong name proven in `found`; any refusal
#      is exit 5 (data or read-back mismatch) with a loud operator STOP line
#      on stderr — the wrong name absent or the healthy name present is PROVEN
#      in `found`, so a drift is never a fabricated pass and never a silent
#      failure.
#   7. self_test() — OFFLINE (no network, no credentials): the golden wrong
#      state DETECTED with the wrong name proven; the healthy listing, the
#      both-present state, the empty listing, and every malformed payload
#      REFUSED; the builder refuses an absent contract section; the CLI gate
#      exits 0 on the golden wrong state and 5 on the healthy listing. A
#      tamper NEVER masquerades as exit 1 — it is exit 4 (AF-AE-TEMPLATE-
#      ATTACK family), the house self-test convention.
#
# DOCTRINE (house, per anthology_registry.py / drive_adapter.py / the golden
# fixture siblings):
#   - A fixture is DATA, not code: this module performs NO I/O and NO network
#     call — it can never leak a token by construction. Nothing here reads an
#     env var or touches the wire. Credentials resolve BY LABEL only (SET /
#     NOT SET); a location id, when surfaced, is the marker via
#     reg._mask_location. THIS module surfaces no location and holds no
#     credential surface.
#   - BROWSER UA: any module that TALKS to GoHighLevel / Convert and Flow
#     (services.leadconnectorhq.com, Cloudflare-fronted) MUST carry a browser
#     User-Agent on every request — urllib's default "Python-urllib/x.y" is
#     403'd at the WAF edge (CF error 1010) before it ever reaches the API.
#     This module makes NO request of its own and therefore defines NO UA
#     constant of its own; the reader that DOES (name_reader.py /
#     rename_checker.py) rides reg.CafClient, which applies reg.CAF_BROWSER_UA
#     on every request — the proven edge fix (W0.6 / GK-09 discipline). The
#     --live surface pipes a listing in on stdin and reads NOTHING from the
#     network; the live reader is name_reader.py / rename_checker.py.
#   - FAIL-CLOSED: an empty contract name, a malformed listing, a listing
#     without the wrong name, an ambiguous both-present state — every
#     deviation REFUSES (FixtureError / WrongStateError, exit 2 or 5), never
#     a blind pass, never a fabricated success.
#   - READ-ONLY: this module never creates, never writes, never mutates.
#   - Move in silence; NOTHING Anthropic in any runtime file; Convert and
#     Flow naming in every client surface; never print a secret value.
#
# THE NAME IS NEVER HARDCODED HERE (SPEC M8): the wanted name comes from
# config/field-map.json pipeline.standard_pipeline_name — the SAME source of
# truth provision-pipeline binds by and rename_checker.py asserts byte-exact.
# WRONG_PIPELINE_NAME ("Anthology Writer") is the ONE exception: it is the
# ATTACK VALUE, pinned here by design (the same exception attack_wrong_name.py
# makes) — the sibling-skill drift the fixture exists to catch. A drift of the
# CONTRACT name is caught by the offline self-test (the wrong name must stay
# DISTINCT from the contract name), never silently.
#
# EXIT CODES (house convention 0/1/2/4/5; the wrong-name fixture family):
#   0  DETECTED — the wrong name "Anthology Writer" is present BYTE-EXACT and
#      the contract name absent on the listing (also self-test PASS and plan
#      OK)
#   1  unexpected error
#   2  STOP refusal — the contract name law is EMPTY (no name law to pin, the
#      fixture cannot be certified), or no gate mode selected
#   4  self-test FAILED — an attack fixture was NOT refused (AF-AE-TEMPLATE-
#      ATTACK family; a tamper NEVER masquerades as exit 1)
#   5  data or read-back mismatch — the wrong name is ABSENT from the listing
#      (a healthy / empty / differently-renamed state), the contract name is
#      ALSO present (ambiguous both-present state), the listing is malformed,
#      or config/field-map.json drifted from the fixture contract
#      (AF-AE-TEMPLATE-PIPELINE-MISSING family)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr;
# --self-test is OFFLINE and needs no token and no network):
#   golden_wrong.py --plan          # offline: the wrong-state law with sources
#   golden_wrong.py --live < listing.json
#                                   # pipes a full pipelines listing in
#   golden_wrong.py --self-test     # offline golden + attack fixtures
#
#   # the canonical live pairing (reader -> fixture gate, one pipeline):
#   name_reader.py live | golden_wrong.py --live
#
# STDLIB ONLY (json + argparse). Calls NO model. Reuses anthology_registry
# (load_field_map, _stop, _mask_location, CAF_BROWSER_UA doctrine). Deliberately
# imports NO sibling module: name_reader.py / rename_checker.py land in
# parallel and are composed by contract (payload shape / verdict dict shape),
# never by import.
# =============================================================================
"""golden_wrong.py — golden WRONG-name fixture for the U03 name-law family:
the canonical renamed pipeline "Anthology Writer" (nine contract stages intact)
exactly as a live read of the drifted location serves it, plus the fail-closed
DETECTION gate that certifies the wrong name is on a listing — never a pass,
never a token, never a network call."""

from __future__ import annotations

import argparse
import contextlib
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

# The canonical WRONG name the fixture carries — the engine's SIBLING SKILL
# (Skill 54, Anthology Writer), the most plausible drift a renamed pipeline
# takes (a template built under the authoring IP binds the wrong skill's
# pipeline by name, and find-and-bind is BY NAME). Pinned here BY DESIGN: it
# is the attack value, not a contract value — the ONE hardcoded name, the same
# exception attack_wrong_name.py makes. The contract name is NEVER hardcoded;
# it comes from field-map.json pipeline.standard_pipeline_name (SPEC M8) and
# the self-test proves the two stay DISTINCT.
WRONG_PIPELINE_NAME = "Anthology Writer"

# The NINE contract stages: the pinned count of the standard pipeline (field-
# map standard_stages, positions 0..8) — the same 9 the sibling checks assert.
CONTRACT_STAGE_COUNT = 9

FIXTURE_CONTRACT = "anthology-engine-golden-wrong-name"

# The ONE fixed report contract on every surface (plan / live / self-test).
_REPORT = {
    "contract": FIXTURE_CONTRACT,
    "schema_version": 1,
}


class FixtureError(Exception):
    """A fail-closed FIXTURE refusal (STOP family): the contract source
    cannot certify the golden wrong state — an empty contract name, a
    malformed pipeline section, a stage count != 9, a non-contiguous
    position, a blank or duplicate stage name, or a contract name that
    collides with the attack value. The fixture NEVER fabricates."""


class WrongStateError(Exception):
    """A fail-closed DETECTION refusal (STOP / mismatch family): the listing
    does NOT carry the golden wrong state — the wrong name absent, the
    contract name also present (ambiguous), or the listing unreadable. A
    listing that does not carry the wrong name is NEVER certified as the
    wrong state (never a pass, never a silent fallback)."""


# ---------------------------------------------------------------------------
# Contract reader (fail-closed: an empty name law is a refusal, never a pass)
# ---------------------------------------------------------------------------
def _contract_name(field_map: dict) -> str:
    """The byte-exact contract name from field-map.json
    pipeline.standard_pipeline_name — the single source of truth
    provision-pipeline binds by and rename_checker.py asserts. Fail-closed:
    an empty or non-string name is a FixtureError (no law to pin, the fixture
    cannot be certified), never a fabricated pass."""
    name = (field_map.get("pipeline") or {}).get("standard_pipeline_name")
    if not isinstance(name, str) or not name.strip():
        raise FixtureError(
            "config/field-map.json pipeline.standard_pipeline_name is EMPTY — "
            "the name law has no contract source; the golden wrong state "
            "cannot be certified (never a fabricated fixture).")
    return name


# ---------------------------------------------------------------------------
# The golden WRONG state — the renamed pipeline row and the full listing, both
# derived BYTE-FOR-BYTE from the field-map contract (stages) + the pinned
# attack value (name). A pure rename: every stage intact, only the name drifts.
# ---------------------------------------------------------------------------
def golden_wrong_pipeline(field_map: dict) -> dict:
    """The canonical RENAMED pipeline row: id "pipe_tmpl", name BYTE-EXACT
    WRONG_PIPELINE_NAME, the NINE contract stages in position order — exactly
    the row a live read of the drifted location serves. Fail-closed builder:
    an absent/malformed pipeline section, a stage count != 9, a non-contiguous
    position, a blank or duplicate stage name, an empty contract name, or a
    contract name COLLIDING with the attack value raises FixtureError — the
    fixture NEVER fabricates a renamed state."""
    pconf = field_map.get("pipeline") or {}
    want = _contract_name(field_map)
    if want == WRONG_PIPELINE_NAME:
        raise FixtureError(
            "config/field-map.json pipeline.standard_pipeline_name is %r — it "
            "COLLIDES with the attack value %r; a rename cannot be certified "
            "when the contract IS the wrong name." % (want, WRONG_PIPELINE_NAME))
    stages = pconf.get("standard_stages")
    if not isinstance(stages, list):
        raise FixtureError(
            "config/field-map.json pipeline.standard_stages is %r, not a "
            "list — the renamed pipeline would be fabricated."
            % type(stages).__name__)
    rows = [s for s in stages if isinstance(s, dict)]
    if len(rows) != CONTRACT_STAGE_COUNT:
        raise FixtureError(
            "config/field-map.json pipeline.standard_stages carries %d "
            "row(s), not the contract %d — the renamed pipeline would be "
            "fabricated." % (len(rows), CONTRACT_STAGE_COUNT))
    seen = set()
    for idx, s in enumerate(rows):
        if s.get("position") != idx:
            raise FixtureError(
                "config/field-map.json pipeline.standard_stages position %r "
                "at index %d is not contiguous — the renamed pipeline would "
                "be fabricated." % (s.get("position"), idx))
        name = s.get("name")
        if not isinstance(name, str) or not name.strip():
            raise FixtureError(
                "config/field-map.json pipeline.standard_stages carries a "
                "blank stage name — the renamed pipeline would be "
                "fabricated.")
        if name in seen:
            raise FixtureError(
                "config/field-map.json pipeline.standard_stages duplicates "
                "the stage name %r — the renamed pipeline would be "
                "fabricated." % name)
        seen.add(name)
    return {"id": "pipe_tmpl",
            "name": WRONG_PIPELINE_NAME,
            "stages": [{"position": s.get("position"), "name": s.get("name"),
                        "id": "stg_%s" % s.get("position")}
                       for s in rows]}


def golden_wrong_listing(field_map: dict) -> dict:
    """The full listing object a live read of the drifted location serves —
    the exact {"pipelines": [...]} shape name_reader.py reads and
    rename_checker.py judges. One row only: the standard pipeline was RENAMED,
    never duplicated."""
    return {"pipelines": [golden_wrong_pipeline(field_map)]}


def wrong_state(field_map: dict) -> dict:
    """The EXACT verdict dict rename_checker.check_name returns on this
    fixture: {"ok": False, "current": WRONG_PIPELINE_NAME, "expected":
    <contract name>}. check_name finds BY THE WANTED NAME; on the renamed
    state the byte-exact match is absent, so "current" reports the FIRST
    live pipeline name — the drifted one — which is how a gate tells RENAMED
    from ABSENT (the sibling's documented rule: "" only when the location
    lists NO pipeline at all). ok False is the detection verdict the checker
    produces; THIS module's detect() is what proves the wrong name is
    actually ON the listing. Never fabricated: expected is derived from the
    field-map contract, and a drifted or empty contract raises
    FixtureError. This parity is pinned by the offline self-test: the golden
    wrong state must yield EXACTLY the verdict check_name yields on it."""
    return {"ok": False, "current": WRONG_PIPELINE_NAME,
            "expected": _contract_name(field_map)}


# ---------------------------------------------------------------------------
# The fail-closed DETECTION gate over a pipelines LISTING payload. The payload
# is {"pipelines": [...]} — EXACTLY the object a live GET /opportunities/
# pipelines read serves (reg.CafClient.list_pipelines returns the pipeline
# list), so the live surface and the offline fixture surface share ONE
# implementation of the wrong-state law.
# ---------------------------------------------------------------------------
def detect(payload: dict, want_name: str = "") -> tuple:
    """Certify the golden WRONG state is on a pipelines listing.

    Returns ("DETECTED", names, stage_count) when the wrong name
    WRONG_PIPELINE_NAME is present BYTE-EXACT and the contract name is ABSENT.
    Raises WrongStateError on ANY other outcome — the wrong name absent (a
    healthy, empty, or differently-renamed listing), the contract name ALSO
    present (an ambiguous both-present state that find-by-name cannot
    disambiguate), a malformed payload, a non-dict entry, an entry without a
    non-empty string name — never a pass, never a silent fallback. The found
    names are surfaced in the message (names are NOT credentials), so the
    wrong name is PROVEN present or PROVEN absent, never assumed. An empty
    name law raises FixtureError (no contract source, the fixture cannot be
    certified).
    """
    want = want_name or _contract_name(reg.load_field_map(FIELD_MAP_PATH))
    if not isinstance(payload, dict):
        raise WrongStateError(
            "listing payload is %r, not an object — refusing to judge it."
            % type(payload).__name__)
    pipes = payload.get("pipelines")
    if pipes is None:
        raise WrongStateError(
            "listing payload has no 'pipelines' array — a malformed read is "
            "NEVER certified as the wrong state (fail-closed).")
    if not isinstance(pipes, list):
        raise WrongStateError(
            "listing 'pipelines' is %r, not a list — refusing."
            % type(pipes).__name__)

    # Entry shape must be readable before ANY name is reported (the
    # name_reader's fail-closed rule): a non-dict entry or an entry without a
    # non-empty string name would make the name set incomplete — fabrication.
    for entry in pipes:
        if not isinstance(entry, dict):
            raise WrongStateError(
                "listing carries a %r entry, not a dict — the name set would "
                "be incomplete, refusing." % type(entry).__name__)
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            raise WrongStateError(
                "listing carries an entry without a non-empty string name — "
                "the name set would be incomplete, refusing.")

    names = sorted({p.get("name") for p in pipes})
    wrong_present = WRONG_PIPELINE_NAME in names
    contract_present = want in names
    if not wrong_present:
        raise WrongStateError(
            "AF-AE-TEMPLATE-PIPELINE-MISSING: the WRONG name %r is ABSENT "
            "from the listing — a healthy, empty, or differently-renamed "
            "state is NEVER certified as the wrong state (found: %s)."
            % (WRONG_PIPELINE_NAME, ", ".join(names) or "(none)"))
    if contract_present:
        raise WrongStateError(
            "AF-AE-TEMPLATE-PIPELINE-MISSING: the listing carries BOTH the "
            "contract name %r AND the wrong name %r — an ambiguous "
            "both-present state is NEVER certified as the wrong state "
            "(find-by-name cannot disambiguate; refusing)."
            % (want, WRONG_PIPELINE_NAME))
    found_pipe = next(p for p in pipes if p.get("name") == WRONG_PIPELINE_NAME)
    stages = len([s for s in (found_pipe.get("stages") or [])
                  if isinstance(s, dict)])
    return ("DETECTED", names, stages)


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


def _found_names(payload_obj) -> list:
    """The sorted live pipeline names on a listing (may be empty). Names are
    NOT credentials — surfacing them is how the wrong state is PROVEN present
    or PROVEN absent."""
    if not isinstance(payload_obj, dict):
        return []
    pipes = payload_obj.get("pipelines")
    if not isinstance(pipes, list):
        return []
    return sorted({p.get("name") for p in pipes
                   if isinstance(p, dict) and p.get("name")})


def payload(payload_obj: dict, *, out=None) -> int:
    """Run the fail-closed wrong-state gate over a listing payload. Returns
    the exit code: 0 DETECTED, 5 refusal (mismatch family). Human notes go to
    stderr; the ONE JSON report object lands on stdout."""
    out = out or sys.stderr
    want = _contract_name(reg.load_field_map(FIELD_MAP_PATH))
    try:
        status, names, stages = detect(payload_obj, want)
    except WrongStateError as exc:
        found = _found_names(payload_obj)
        reg._stop(out, "The golden WRONG state is NOT on this listing — the "
                       "renamed pipeline %r is NOT present byte-exact."
                       % WRONG_PIPELINE_NAME,
                  [str(exc),
                   "Expected on the listing (the drifted name): %r"
                   % WRONG_PIPELINE_NAME,
                   "Found on the listing: %s"
                   % (", ".join(found) or "(none)"),
                   "AF-AE-TEMPLATE-PIPELINE-MISSING — a listing that does not "
                   "carry the wrong name is NEVER certified as the wrong "
                   "state."])
        _report(False, "FAIL", WRONG_PIPELINE_NAME, found, 0, str(exc))
        return EX_MISMATCH
    _report(True, "DETECTED", WRONG_PIPELINE_NAME, [WRONG_PIPELINE_NAME],
            stages, "wrong name %r present byte-exact, contract name %r "
                    "absent (%d stage(s) read back on the renamed pipeline)"
                    % (WRONG_PIPELINE_NAME, want, stages))
    out.write("[golden-wrong] DETECTED: the renamed pipeline %r is present "
              "byte-exact, %d stage(s) read back.\n"
              % (WRONG_PIPELINE_NAME, stages))
    return EX_OK


# ---------------------------------------------------------------------------
# Offline self-test — golden + attack fixtures, zero network, zero secrets.
# A FAILED self-test is exit 4 (enforced violation, AF-AE-TEMPLATE-ATTACK
# family), NEVER 'unexpected error' — the house convention.
# ---------------------------------------------------------------------------
def _healthy_pipeline(field_map: dict) -> dict:
    """The healthy golden counterpart for the attack fixtures: the standard
    pipeline with the byte-exact CONTRACT name and the nine contract stages —
    the state the wrong-state gate must NEVER certify."""
    pconf = field_map.get("pipeline") or {}
    want = _contract_name(field_map)
    stages = sorted((pconf.get("standard_stages") or []),
                    key=lambda s: s.get("position", 0))
    return {"id": "pipe_tmpl",
            "name": want,
            "stages": [{"position": s.get("position"), "name": s.get("name"),
                        "id": "stg_%s" % s.get("position")}
                       for s in stages if isinstance(s, dict)]}


def _expect_refused(payload_obj, want: str, label: str) -> None:
    """The attack-fixture harness: the payload must be REFUSED — any
    certification is a self-test violation."""
    try:
        detect(payload_obj, want)
    except WrongStateError:
        return
    raise AssertionError(label)


def self_test(out=None) -> int:
    """OFFLINE self-test: golden + attack fixtures, no network, no secrets.
    A tamper NEVER masquerades as exit 1 — it is exit 4
    (AF-AE-TEMPLATE-ATTACK family)."""
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except Exception as exc:  # noqa: BLE001 — a tamper NEVER masquerades as
        # an unexpected error (exit 1) or a data mismatch (exit 5); an
        # assertion that should have refused and escaped is EXIT 4, the house
        # self-test convention (AF-AE-TEMPLATE-ATTACK family).
        sys.stderr.write("[golden-wrong] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _self_test_body(dev) -> None:
    fm = reg.load_field_map(FIELD_MAP_PATH)
    want = _contract_name(fm)
    assert want == "Anthology Engine", \
        "standard_pipeline_name drifted from the U02/U03 contract (got %r)" % want
    assert WRONG_PIPELINE_NAME == "Anthology Writer", \
        "the attack value must stay the sibling-skill name (Skill 54)"
    assert want != WRONG_PIPELINE_NAME, \
        "the attack value must stay DISTINCT from the contract name"

    # ---- golden wrong state: DETECTED, the wrong name PROVEN ----
    wrong = golden_wrong_listing(fm)
    status, names, stages = detect(wrong, want)
    assert status == "DETECTED", "golden wrong listing: %s" % (status,)
    assert WRONG_PIPELINE_NAME in names, \
        "the wrong name must be PROVEN on the golden listing"
    assert want not in names, \
        "the contract name must be ABSENT from the renamed listing"
    assert stages == CONTRACT_STAGE_COUNT, \
        "the renamed pipeline must carry the contract %d stages" \
        % CONTRACT_STAGE_COUNT
    pipe = golden_wrong_pipeline(fm)
    assert pipe["name"] == WRONG_PIPELINE_NAME and \
        len(pipe["stages"]) == CONTRACT_STAGE_COUNT, \
        "the renamed row must carry the wrong name byte-exact and 9 stages"
    # the checker's verdict dict on the golden wrong state: not-ok, and the
    # drifted name in "current" — the sibling's documented rule for telling a
    # RENAMED pipeline from an ABSENT one ("" only when the location lists NO
    # pipeline at all). The parity is pinned against the actual check_name
    # logic, not re-typed from memory (NEGATIVE-RESULT discipline).
    verdict = wrong_state(fm)
    assert verdict == {"ok": False, "current": WRONG_PIPELINE_NAME,
                       "expected": want}, \
        "wrong_state must equal rename_checker.check_name's verdict on the " \
        "renamed state: %s" % verdict
    try:
        from rename_checker import check_name  # noqa: PLC0415
    except ImportError:
        check_name = None  # sibling lands in parallel; parity re-pinned then
    if check_name is not None:
        class _FakeCaf:
            def __init__(self, pipes):
                self._pipes = pipes
            def list_pipelines(self, location_id):
                return self._pipes
        live = check_name(_FakeCaf(golden_wrong_listing(fm)["pipelines"]),
                          "X", want)
        assert live == verdict, \
            "wrong_state drifted from rename_checker.check_name's live " \
            "verdict on the golden wrong state: fixture %s vs check %s" \
            % (verdict, live)

    # ---- attack fixtures: every mutation REFUSED (never a silent pass) ----
    # 1. the HEALTHY listing (byte-exact contract name) -> refusal: a healthy
    #    state can NEVER masquerade as the detected wrong state
    a1 = {"pipelines": [_healthy_pipeline(fm)]}
    _expect_refused(a1, want, "healthy listing was certified as the wrong state")
    # 2. BOTH names present (ambiguous) -> refusal: find-by-name cannot
    #    disambiguate, so the state is never certified
    a2 = {"pipelines": [_healthy_pipeline(fm), golden_wrong_pipeline(fm)]}
    _expect_refused(a2, want, "ambiguous both-present state was certified")
    # 3. empty listing -> refusal: nothing to detect
    a3 = {"pipelines": []}
    _expect_refused(a3, want, "empty listing was certified as the wrong state")
    # 4. malformed listings -> refusal, never a pass
    _expect_refused({"no_pipelines_here": True}, want,
                    "listing without 'pipelines' was certified")
    _expect_refused({"pipelines": "not-a-list"}, want,
                    "non-list pipelines was certified")
    _expect_refused({"pipelines": [42]}, want,
                    "non-dict entry was certified")
    _expect_refused({"pipelines": [{"stages": []}]}, want,
                    "entry without a name was certified")
    # 5. empty name law -> FixtureError (no contract source, never a blind
    #    pass) — the law is tested AT its source: an empty contract name in
    #    the field-map must refuse, not certify
    try:
        _contract_name({"pipeline": {"standard_pipeline_name": "  "}})
        raise AssertionError("empty name law was NOT refused")
    except FixtureError:
        pass
    # 6. builder: absent pipeline section -> FixtureError (never fabricate)
    try:
        golden_wrong_pipeline({})
        raise AssertionError("absent pipeline section fabricated a fixture")
    except FixtureError:
        pass
    try:
        golden_wrong_pipeline({"pipeline": {"standard_pipeline_name": "x"}})
        raise AssertionError("missing standard_stages fabricated a fixture")
    except FixtureError:
        pass
    # 7. golden wrong state read back through the CLI gate -> exit 0,
    #    DETECTED JSON with the wrong name PROVEN in found
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = payload(wrong, out=io.StringIO())
    assert rc == EX_OK, "golden wrong payload must exit 0, got %s" % rc
    report = json.loads(buf.getvalue())
    assert report["ok"] is True and report["verdict"] == "DETECTED"
    assert report["expected"] == WRONG_PIPELINE_NAME
    assert report["found"] == [WRONG_PIPELINE_NAME], \
        "the wrong name must be PROVEN in found: %s" % report["found"]
    assert report["stage_count"] == CONTRACT_STAGE_COUNT
    assert report["contract"] == FIXTURE_CONTRACT
    # 8. the HEALTHY listing through the CLI gate -> exit 5, FAIL JSON, and
    #    the healthy name PROVEN in found — never a fabricated detection
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc2 = payload(a1, out=io.StringIO())
    assert rc2 == EX_MISMATCH, "healthy payload must exit 5, got %s" % rc2
    report2 = json.loads(buf2.getvalue())
    assert report2["ok"] is False and report2["verdict"] == "FAIL"
    assert report2["expected"] == WRONG_PIPELINE_NAME
    assert report2["found"] == [want], \
        "the healthy name must be PROVEN in found: %s" % report2["found"]
    assert report2["stage_count"] == 0

    dev.write("golden_wrong self-test: OK (wrong name %r pinned DISTINCT from "
              "the field-map contract %r; golden renamed state DETECTED with "
              "%d stages, wrong name proven; rename_checker verdict on the "
              "renamed state is ok False / current %r (the drifted name — how "
              "a gate tells RENAMED from ABSENT), parity pinned against the "
              "live check_name logic when the sibling is present; 9 attack "
              "fixtures refused: healthy / both-present / empty-listing / "
              "no-pipelines / non-list-pipelines / non-dict-entry / "
              "entry-without-name / empty-name-law / absent-pipeline-section; "
              "payload gate exits 0 on the golden wrong state, 5 on the "
              "healthy listing)\n"
              % (WRONG_PIPELINE_NAME, want, CONTRACT_STAGE_COUNT,
                 WRONG_PIPELINE_NAME))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="golden_wrong.py",
        description="Golden wrong-name fixture for the U03 name-law family "
                    "(Skill 59): ships the canonical renamed pipeline "
                    "'Anthology Writer' (Skill 54 sibling) exactly as a live "
                    "read of the drifted location serves it, and CERTIFIES a "
                    "pipelines listing only when the wrong name is present "
                    "byte-exact and the contract name is absent — never a "
                    "pass, never a token, never a network call. One JSON "
                    "object on stdout; fail-closed.")
    ap.add_argument("--live", action="store_true",
                    help="read a full pipelines listing JSON from stdin "
                         "(the exact shape name_reader.py live emits) and "
                         "gate it against the wrong-state law")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (source of truth for the "
                         "byte-exact contract name)")
    ap.add_argument("cmd", nargs="?", choices=["plan", "self-test"],
                    help="offline subcommands (no network, no credentials)")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --plan / --self-test / --selftest -> positional subcommands
    # (the same normalization the registry and the U02 verifier use).
    if "--plan" in argv:
        argv = ["plan" if a == "--plan" else a for a in argv]
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()

        field_map = reg.load_field_map(Path(args.field_map).expanduser())
        want = _contract_name(field_map)
        if args.cmd == "plan":
            # offline plan: no network, no credentials — the wrong-state law
            # with its sources, including the attack value this fixture
            # exists for.
            print(json.dumps({
                "contract": FIXTURE_CONTRACT + "-plan",
                "schema_version": 1,
                "standard_pipeline_name": want,
                "wrong_name": WRONG_PIPELINE_NAME,
                "check": "the golden WRONG state is certified only when %r is "
                         "present BYTE-EXACT on a listing AND the contract "
                         "name %r is ABSENT; any other state REFUSES "
                         "(AF-AE-TEMPLATE-PIPELINE-MISSING)"
                         % (WRONG_PIPELINE_NAME, want),
                "note": "offline plan only — no network, no credential needed",
            }, indent=2, sort_keys=True))
            return EX_OK

        # ---- live gate: the listing comes in on stdin, read from NO network
        #      (the live READER is name_reader.py / rename_checker.py, which
        #      ride reg.CafClient and its CAF_BROWSER_UA — this fixture never
        #      touches the wire) ----
        if not args.live:
            reg._stop(sys.stderr, "No gate mode selected.",
                      ["Pass --live with a pipelines listing JSON on stdin "
                       "(name_reader.py live | golden_wrong.py --live), "
                       "or --plan / --self-test (offline)."])
            return EX_STOP
        try:
            listing = json.load(sys.stdin)
        except ValueError as exc:
            reg._stop(sys.stderr, "The pipelines listing on stdin is not valid JSON.",
                      ["%s" % exc,
                       "Pipe the exact JSON name_reader.py live emits."])
            return EX_STOP
        return payload(listing, out=sys.stderr)

    except FixtureError as exc:
        reg._stop(sys.stderr, "The contract source cannot certify the golden "
                              "wrong state.",
                  [str(exc),
                   "Fix config/field-map.json pipeline; the fixture NEVER "
                   "fabricates a renamed state."])
        return EX_STOP
    except WrongStateError as exc:
        sys.stderr.write("[golden-wrong] REFUSED: %s\n" % exc)
        return EX_MISMATCH
    except FileNotFoundError as exc:
        sys.stderr.write("[golden-wrong] file not found: %s\n" % exc)
        return EX_ERR
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[golden-wrong] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
