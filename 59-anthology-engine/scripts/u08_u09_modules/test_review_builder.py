#!/usr/bin/env python3
"""test_review_builder.py -- unit tests for universal_review_builder.py, the
U08/U09 gated universal-review form builder (Skill 59, anthology engine).
The module builds the engine's ONE client-facing decision form (slug
"universal-review"; PRD Section 4 / U8) on the public v2 PUT /forms/{id}
surface: EXACTLY TWO hidden fields (anthology_id, stage -- NEVER the intake
contact_id / anthology_id / stage trio), a SINGLE_OPTIONS decision dropdown
with EXACTLY TWO options (Approve as-is / Request rewrite with notes), a
multi-line (LARGE_TEXT) notes surface, and the U8 cover dropdown with the
FOUR named style names (== cover_render.STYLE_NAMES). The write is
Trevor-gated: WITHOUT --execute the tool is a read-only dry-run and NOTHING
is ever written.

THE LAW UNDER TEST (mirrored from the module header):

  * FAIL-CLOSED -- a missing/empty/foreign listing is a named refusal
    (FORMS-EMPTY / FORMS-NOT-FOUND), never a pass; a slug-matched row with
    NO form id or a non-array hidden-field container is a STOP (raises), not
    a silent skip; a PUT body is built ONLY from the live row echoed
    byte-for-byte (an id guessed from memory is never shipped).
  * THE --execute GATE -- ok True / applied True ONLY when the build was
    performed with --execute AND read back byte-exact in the SAME job; ok
    True with applied False ONLY on the idempotent NO-OP (the live form
    already carries the contract); every dry-run on drift is ok False,
    applied False, af_code DRY-RUN; an ok False surface carries NO form id.
  * THE PIN LAW -- a pinned id (forms_check.FORM_ID_BY_SLUG
    ["universal-review"], the live-verified Review Fire id
    riNlAkYbcW3g92VRLqq0) BYPASSES the slug law and must BE the row written;
    a pinned id absent from the listing refuses FORMS-NOT-FOUND.
  * THE READ-BACK LAW -- a PUT that returned success but cannot be read back
    is HELD (reg.CafUnreachable), never reported as built; a read-back that
    does not prove the build is READBACK-MISMATCH (exit 5); a validation
    refusal on the PUT (400/409/422) is a STOP (ReviewBuildError); a scope
    refusal on the read-back (reg.ScopeDenied) is a STOP, never demoted to a
    HELD.
  * NEVER a token printed -- the pit- credential shape on any surface
    (hidden-field values, the pinned id) REFUSES the whole plan rather than
    print it; form ids and the location id are masked (last 4 chars) on
    every surface.
  * Browser UA (CF 1010) -- the write rides reg.CafClient, which sends
    reg.CAF_BROWSER_UA on EVERY request; urllib's default Python-urllib UA
    is 1010'd at the Cloudflare edge fronting services.leadconnectorhq.com.
    This battery pins the constant surface -- no network is ever touched.
  * The single-implementation doctrine -- the review hidden pair, the
    decision options, the cover options, the slug, and the pinned id are
    pinned against their OWNING authorities (hidden_field_module
    HIDDEN_FIELD_LAW as the CONTRAST, cover_render.STYLE_NAMES, form_reader
    SLUG_AS_NAME semantics, forms_check.FORM_ID_BY_SLUG); a drift in any
    authority breaks THIS battery first, fail-closed.

HERMETIC BY DESIGN -- OFFLINE: no network, no credentials, no browser. Every
plan_review_build invocation runs against the in-memory _FakeClient (the
same seam the module's own self-test uses: it serves the row list, applies a
PUT to its rows, and records every request, so the live request contract --
the listing path, the locationId query, the ONE PUT path -- is provable
without touching the wire). The module's own offline self-test battery runs
as a process (the house self-test convention -- a tamper NEVER masquerades
as exit 1).

Run: python3 -m pytest 59-anthology-engine/scripts/u08_u09_modules/test_review_builder.py -q
 or: python3 59-anthology-engine/scripts/u08_u09_modules/test_review_builder.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest  # noqa: F401  (house style: pytest with plain asserts)

U08 = Path(__file__).resolve().parent
SCRIPTS = U08.parent

for _p in (SCRIPTS, U08, SCRIPTS / "u04_modules"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import anthology_registry as reg  # noqa: E402
import universal_review_builder as rvb  # noqa: E402  (the module under test)
import form_reader as fr  # noqa: E402  (the ONE forms-listing read)
import hidden_field_module as hfm  # noqa: E402  (the ONE form WRITE path)

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

CREDENTIAL_SHAPE = re.compile(r"pit-\S+")
REVIEW_FORM_ID = rvb.DEFAULT_UNIVERSAL_REVIEW_FORM_ID


# ---------------------------------------------------------------------------
# The hermetic seam: the same in-memory public-v2 client the module's own
# self-test rides (serves the row list, applies a PUT to its rows, records
# every request). NEVER a network call.
# ---------------------------------------------------------------------------
class _FakeClient:
    """In-memory public-v2 client: serves the row list, applies a PUT to its
    rows (the write seam), and records the exact requests."""

    def __init__(self, rows, fail_put=False):
        self._rows = [dict(r) for r in (rows or [])]
        self._fail_put = fail_put
        self.calls = []

    def _request(self, method, path, query=None, body=None):
        self.calls.append({"method": method, "path": path,
                           "query": dict(query or {}), "body": body})
        if method == "GET" and path == fr.FORMS_LIST_PATH:
            return {"forms": [dict(r) for r in self._rows]}
        if method == "PUT" and path.startswith(hfm.FORMS_WRITE_PATH % ""):
            if self._fail_put:
                raise reg.CafValidation("Convert and Flow rejected the "
                                        "request (HTTP 422)")
            fid = path[len(hfm.FORMS_WRITE_PATH % ""):]
            for row in self._rows:
                if fr._row_id(row) == fid:
                    row.clear()
                    row.update(dict(body))
                    return {}
            raise reg.CafUnreachable("form id not found (fixture)")
        raise reg.CafUnreachable("unexpected request (fixture)")


def _review_row():
    """A mutable golden universal-review row carrying the full contract."""
    return {"id": REVIEW_FORM_ID,
            "name": "Universal Review",
            "type": "form",
            "hiddenFields": list(rvb.REVIEW_HIDDEN_LAW),
            "options": list(rvb.decision_options()),
            "choiceOptions": list(rvb._cover_choice_options()),
            "notes": rvb.NOTES_FIELD_LABEL,
            "dataType": rvb.NOTES_DATA_TYPE}


def _intake_row():
    """The engine's intake row -- the CONTRAST surface (three hidden fields)."""
    return {"id": fr.DEFAULT_UNIVERSAL_INTAKE_FORM_ID,
            "name": "Universal Intake",
            "type": "form",
            "hiddenFields": list(hfm.HIDDEN_FIELD_LAW)}


def _golden_rows():
    """The three-slug family: intake + review + title-select (the same family
    forms_check.py / golden_forms.py pin)."""
    return [_intake_row(), _review_row(),
            {"id": "UgiiSoZsA4vyqOVfO5fi", "name": "Title Select",
             "type": "form", "hiddenFields": list(hfm.HIDDEN_FIELD_LAW)}]


def _drift_review_row(**patch):
    """A golden review row with the given drift applied."""
    row = _review_row()
    row.update(patch)
    return row


def _puts(client):
    return [c for c in client.calls if c["method"] == "PUT"]


# ---------------------------------------------------------------------------
# Cross-cutting house doctrine: the exit-code convention, the fail-closed
# empty package init, the surface contract, and the CF 1010 browser-UA law.
# ---------------------------------------------------------------------------
def test_exit_code_convention_is_house_0_1_2_3_4_5():
    """The module pins the house exit-code convention (0/1/2/3/4/5) --
    asserted through the exported constants, never re-typed."""
    assert (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH) == (0, 1, 2, 3, 5)
    assert (rvb.EX_OK, rvb.EX_ERR, rvb.EX_STOP, rvb.EX_HELD,
            rvb.EX_MISMATCH) == (0, 1, 2, 3, 5)
    assert EX_VIOLATION == 4 and EX_VIOLATION not in (0, 1, 2, 3, 5)


def test_u08_u09_package_init_is_fail_closed_empty():
    """The package init is a pure namespace container -- no runtime code, no
    secret surface (fail-closed empty init)."""
    import u08_u09_modules as pkg
    assert pkg.__all__ == []
    assert pkg.__doc__ and "fail-closed" in pkg.__doc__.lower()


def test_report_contract_is_fixed_and_stable():
    """The one fixed config-surface contract: every plan report carries the
    same contract string and schema version, so a machine consumer can never
    mistake another JSON object for a universal-review build."""
    for rows in (_golden_rows(), []):
        res = rvb.plan_review_build(_FakeClient(rows), "loc_tmpl")
        assert res["contract"] == rvb.CONFIG_CONTRACT == \
            "anthology-engine-universal-review-build", res
        assert res["schema_version"] == rvb.CONFIG_SCHEMA_VERSION == 1, res


def test_browser_user_agent_is_a_browser_ua_cf_1010_law():
    """The CF 1010 law: the house client rides a browser User-Agent on every
    request -- urllib's default Python-urllib/x.y is 403'd at the Cloudflare
    WAF edge before it ever reaches Convert and Flow. The constant surface
    is the only place the law is enforceable offline; the module makes NO
    request of its own (the write rides reg.CafClient)."""
    ua = reg.CAF_BROWSER_UA
    assert rvb._CREDENTIAL_SHAPE is not None
    assert ua.startswith("Mozilla/5.0"), (
        "CAF_BROWSER_UA must be a browser User-Agent, got %r" % ua[:40])
    assert "Chrome/" in ua, "CAF_BROWSER_UA must carry a Chrome segment"
    assert "Python-urllib" not in ua, (
        "urllib's default UA is 1010'd at the Cloudflare edge")


# ---------------------------------------------------------------------------
# The review contract is pinned against its OWNING authorities, never
# re-implemented (the single-implementation doctrine).
# ---------------------------------------------------------------------------
def test_review_hidden_law_is_the_pair_and_never_the_intake_trio():
    """The review hidden-field law is EXACTLY (anthology_id, stage) -- the
    pair the release links pre-key. The intake trio (hfm.HIDDEN_FIELD_LAW)
    is the CONTRAST: a review submission must never ride the intake front
    door, and the contact is pre-identified by the anthology link, so
    contact_id is ABSENT by contract."""
    assert rvb.REVIEW_HIDDEN_LAW == ("anthology_id", "stage")
    assert "contact_id" not in rvb.REVIEW_HIDDEN_LAW
    assert hfm.HIDDEN_FIELD_LAW == ("contact_id", "anthology_id", "stage")
    assert tuple(rvb.REVIEW_HIDDEN_LAW) != tuple(hfm.HIDDEN_FIELD_LAW), (
        "the review law must stay distinct from the intake law")


def test_decision_options_are_exactly_the_two_gate_options_in_order():
    """The decision dropdown offers EXACTLY TWO options, byte-exact, in
    order -- the chapter gate's decision pair, never a third option, never a
    renamed one. The LABEL is the client-facing surface; the SUBMITTED value
    is the byte-exact engine action name the gate consumes (the dropdown
    module's law, itself byte-derived from gate_engine -- the ONE
    authority)."""
    labels = rvb.decision_options()
    assert labels == ("Approve as-is", "Request rewrite with notes")
    assert len(labels) == 2
    assert len(set(labels)) == 2
    values = rvb._decision_option_law()
    assert values == ("approve_as_is", "request_rewrite_with_notes"), (
        "the submitted decision values must be the byte-exact engine action "
        "names")
    # the law is read ONCE from the dropdown module's own law (never a
    # second implementation) -- a drift there breaks THIS battery first
    import u08_u09_modules.dropdown_module as dd  # noqa: F401
    assert values == dd._decision_option_law(), (
        "the builder's decision-option law drifted from the dropdown "
        "module's law authority")


def test_cover_options_are_the_four_style_names_in_order():
    """The U8 cover dropdown offers EXACTLY the four named cover styles --
    cover_render.STYLE_NAMES in order (the U8 coherence law), never a
    guessed option set."""
    import cover_render  # noqa: F401
    opts = rvb._cover_choice_options()
    assert opts == ("Signature", "Bold Editorial", "Fine Art", "Pure Type")
    assert len(opts) == 4 and len(set(opts)) == 4
    assert tuple(opts) == tuple(cover_render.STYLE_NAMES), (
        "the cover options drifted from cover_render.STYLE_NAMES")


def test_notes_surface_is_the_multi_line_law():
    """The notes surface is the multi-line free-text field (LARGE_TEXT) --
    the every-text-input-field-is-multi-line law."""
    assert rvb.NOTES_FIELD_LABEL == "notes"
    assert rvb.NOTES_DATA_TYPE == "LARGE_TEXT"


def test_slug_and_pin_pin_against_the_authorities():
    """The review slug and the pinned id pin against the OWNING authorities:
    the negative-mirror slug, the reader's name-match law (slug with dashes
    -> spaces), and the live-verified Review Fire form id
    (forms_check.FORM_ID_BY_SLUG)."""
    assert rvb.REVIEW_SLUG == "universal-review"
    assert rvb.REVIEW_SLUG_AS_NAME == "universal review"
    assert rvb.DEFAULT_UNIVERSAL_REVIEW_FORM_ID == "riNlAkYbcW3g92VRLqq0"
    import u05_modules.negative_verifier as nv  # noqa: F401
    import u02_modules.forms_check as fc  # noqa: F401
    assert rvb.REVIEW_SLUG == nv.UNIVERSAL_REVIEW_FORM, (
        "the review slug drifted from the negative-mirror law")
    assert rvb.DEFAULT_UNIVERSAL_REVIEW_FORM_ID == \
        fc.FORM_ID_BY_SLUG["universal-review"], (
        "the pinned Review Fire id drifted from forms_check.FORM_ID_BY_SLUG")
    # the reader's name-match normalization is the SAME law the slug uses
    assert fr._normalize_name("  Universal  Review ") == rvb.REVIEW_SLUG_AS_NAME


def test_plan_runs_offline_and_names_the_write_surface():
    """plan is OFFLINE (no network, no credential) and names the write path
    (public v2 PUT /forms/{id}) as REFUSED without --execute -- never a
    fabricated promise."""
    import io
    buf = io.StringIO()
    rc = rvb.plan("loc_tmpl", out=buf)
    assert rc == EX_OK
    payload = json.loads(buf.getvalue())
    assert payload["contract"] == rvb.CONFIG_CONTRACT
    assert payload["form_slug"] == "universal-review"
    assert payload["hidden_fields_law"] == list(rvb.REVIEW_HIDDEN_LAW)
    assert payload["decision_options"] == list(rvb.decision_options())
    assert "REFUSED without --execute" in payload["write"]


# ---------------------------------------------------------------------------
# Golden: the review form already carries the contract -> idempotent NO-OP,
# nothing written -- even with --execute.
# ---------------------------------------------------------------------------
def test_golden_contract_matching_form_is_an_idempotent_no_op():
    """A live form that already carries the review contract is ok True,
    applied False, af_code NO-OP -- and NOTHING is written even with
    --execute (the idempotent no-op doctrine)."""
    client = _FakeClient(_golden_rows())
    res = rvb.plan_review_build(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is False, res
    assert res["af_code"] == "NO-OP"
    assert res["form_id"] == REVIEW_FORM_ID
    assert res["form_id_masked"] == "...Lqq0"
    assert res["hidden_law"] == list(rvb.REVIEW_HIDDEN_LAW)
    assert res["decision_options"] == list(rvb.DECISION_OPTION_LABELS)
    assert res["cover_options"] == list(rvb._cover_choice_options())
    assert res["notes_law"] == rvb.NOTES_FIELD_LABEL
    assert res["target_matched_by"] == "slug"
    assert not _puts(client), "a no-op must never perform a PUT"
    assert client.calls == [{"method": "GET", "path": fr.FORMS_LIST_PATH,
                             "query": {"locationId": "loc_tmpl", "limit": 200},
                             "body": None}], (
        "a no-op must perform ONLY the listing read")


def test_golden_no_op_is_deterministic_and_value_free():
    """The no-op report is deterministic and carries no credential-shaped
    string on any surface. The form_id VALUE rides the machine surface (the
    documented return contract: the id is a location identifier, not a
    secret); the masking law is enforced per-STRING at emit time by the
    module's own surfaces (plan / _run_apply), asserted below."""
    res = rvb.plan_review_build(_FakeClient(_golden_rows()), "loc_tmpl")
    dumped = json.dumps(res, indent=2, sort_keys=True)
    assert CREDENTIAL_SHAPE.search(dumped) is None
    assert "Bearer" not in dumped
    assert res["form_id"] == REVIEW_FORM_ID
    assert res["form_id_masked"] == "...Lqq0"


# ---------------------------------------------------------------------------
# Attack: the THREE-FIELD intake trio on the review form (the review
# submission would ride the intake front door) -> dry-run refusal.
# ---------------------------------------------------------------------------
def test_intake_trio_drift_refuses_in_dry_run():
    """A review form carrying the three-field intake trio instead of the
    pair is the attack this builder exists to fix: dry-run ok False,
    applied False, af_code DRY-RUN, nothing written, execute False."""
    rows = _golden_rows()
    for r in rows:
        if fr._row_id(r) == REVIEW_FORM_ID:
            r["hiddenFields"] = list(hfm.HIDDEN_FIELD_LAW)
    client = _FakeClient(rows)
    res = rvb.plan_review_build(client, "loc_tmpl")
    assert res["ok"] is False and res["applied"] is False, res
    assert res["af_code"] == "DRY-RUN" and res["execute"] is False
    assert res["form_id"] == REVIEW_FORM_ID
    assert res["hidden_law"] == list(rvb.REVIEW_HIDDEN_LAW)
    assert not _puts(client), "a dry-run must never perform a PUT"
    # the note names the drifted surface (the FIELD NAMES are contract
    # vocabulary, not credentials) -- the CONTRACT pair is never in the
    # refusal's plan; contact_id appears only as the drift report's
    # key name, never as a value
    assert "anthology_id" in res["note"]


def test_intake_trio_drift_builds_only_with_execute_and_read_back():
    """Under --execute the drifted row is rebuilt: the PUT body carries the
    review hidden pair ONLY -- contact_id never rides the review form, not
    even in the PUT body -- and the read-back in the SAME job proves the
    build (af_code CREATED, ONE PUT)."""
    rows = _golden_rows()
    for r in rows:
        if fr._row_id(r) == REVIEW_FORM_ID:
            r["hiddenFields"] = list(hfm.HIDDEN_FIELD_LAW)
    client = _FakeClient(rows)
    res = rvb.plan_review_build(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is True, res
    assert res["af_code"] == "CREATED"
    assert res["execute"] is True
    puts = _puts(client)
    assert len(puts) == 1, "exactly ONE PUT must ride the apply"
    assert puts[0]["path"] == hfm.FORMS_WRITE_PATH % REVIEW_FORM_ID
    body = puts[0]["body"]
    assert body.get("hiddenFields") == list(rvb.REVIEW_HIDDEN_LAW), (
        "the PUT body must carry the review hidden pair only")
    assert "contact_id" not in json.dumps(body), (
        "the review PUT body must never carry the intake contact_id hidden "
        "field")
    assert body.get("options") == list(rvb.decision_options())
    assert body.get("id") == REVIEW_FORM_ID, (
        "the PUT body must echo the live row's id")
    gets = [c for c in client.calls if c["method"] == "GET"]
    assert len(gets) >= 2, "the apply must re-read the listing for the read-back"


# ---------------------------------------------------------------------------
# The pin law: the pinned id BYPASSES the slug law and IS the row written;
# a pinned id absent from the listing is FORMS-NOT-FOUND.
# ---------------------------------------------------------------------------
def test_pinned_id_bypasses_the_slug_law_and_is_the_row_written():
    """When --form-id is given, the pinned id must BE the row written and it
    BYPASSES the slug law (a renamed review row is still the pinned row).
    The rename (with the contract pair, the two decision options, the four
    cover options, and the notes surface all intact) is then an idempotent
    NO-OP under the pin -- the pin alone identifies the row."""
    rows = [_drift_review_row(name="Completely Different Name")]
    client = _FakeClient(rows)
    res = rvb.plan_review_build(client, "loc_tmpl",
                                pinned_id=REVIEW_FORM_ID, execute=True)
    assert res["ok"] is True and res["applied"] is False, res
    assert res["target_matched_by"] == "pin"
    assert res["af_code"] == "NO-OP"
    assert res["form_id"] == REVIEW_FORM_ID
    assert not _puts(client), "a renamed-but-contract row must never be written"


def test_absent_pinned_id_refuses_for_forms_not_found():
    """A pinned id absent from the listing is FORMS-NOT-FOUND with NO form
    id on the surface (never an id guessed from memory)."""
    rows = [_intake_row(), _drift_review_row(id="DriftedDriftedId00")]
    res = rvb.plan_review_build(_FakeClient(rows), "loc_tmpl",
                                pinned_id=REVIEW_FORM_ID)
    assert res["ok"] is False and res["af_code"] == "FORMS-NOT-FOUND", res
    assert res["form_id"] == "", "a failed plan must never carry a form id"


def test_default_pin_is_the_engine_pin():
    """The builder's default pinned id IS the engine's pinned Review Fire id
    -- a drifted default is caught here first (the loader and the reader
    share the SAME pin, never re-typed)."""
    import u08_u09_modules.form_spec_loader as fsl  # noqa: F401
    assert rvb.DEFAULT_UNIVERSAL_REVIEW_FORM_ID == \
        fsl.FORM_ID_BY_SLUG["universal-review"], (
        "the builder's pin drifted from the form-spec loader's pin")


# ---------------------------------------------------------------------------
# Not-found paths, each NAMED: FORMS-EMPTY / FORMS-NOT-FOUND; an id-less
# slug-matched row and a non-array hidden container are STOPs, never silent.
# ---------------------------------------------------------------------------
def test_empty_listing_refuses_forms_empty():
    """A listing with zero rows is FORMS-EMPTY -- fail-closed, never a
    silent pass."""
    res = rvb.plan_review_build(_FakeClient([]), "loc_tmpl")
    assert res["ok"] is False and res["applied"] is False, res
    assert res["af_code"] == "FORMS-EMPTY"
    assert res["form_id"] == ""


def test_foreign_listing_refuses_forms_not_found():
    """A non-empty listing without the universal-review form is
    FORMS-NOT-FOUND (the slug law matched nothing)."""
    rows = [{"id": "OtherFormId0000", "name": "Contact Us",
             "hiddenFields": ["email"]}]
    res = rvb.plan_review_build(_FakeClient(rows), "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "FORMS-NOT-FOUND", res
    assert res["form_id"] == ""


def test_slug_matched_row_without_id_stops():
    """A slug-matched row with NO form id is an unreadable shape -- a STOP
    (ReviewBuildError), never a silent FORMS-NOT-FOUND."""
    with pytest.raises(rvb.ReviewBuildError):
        rvb.plan_review_build(
            _FakeClient([{"name": "Universal Review",
                          "hiddenFields": list(rvb.REVIEW_HIDDEN_LAW)}]),
            "loc_tmpl")


def test_non_array_hidden_container_stops():
    """A non-array hidden-field container is a malformed shape -- a STOP,
    never a guessed set."""
    with pytest.raises(rvb.ReviewBuildError):
        rvb.plan_review_build(
            _FakeClient([_drift_review_row(hiddenFields="anthology_id")]),
            "loc_tmpl")


def test_alias_key_match_names_the_review_form():
    """The review form may also be found under its alias spellings
    (universal_review / universal_review_form_id) -- as a row KEY or as a
    string VALUE -- the same alias discipline form_reader applies."""
    for row in ({"universal_review": "universal-review",
                 "id": "FakeAliasRowId01",
                 "hiddenFields": list(rvb.REVIEW_HIDDEN_LAW),
                 "options": list(rvb.decision_options()),
                 "choiceOptions": list(rvb._cover_choice_options()),
                 "notes": rvb.NOTES_FIELD_LABEL},
                {"name": "Intake",
                 "universal_review_form_id": "universal-review",
                 "id": "FakeAliasRowId02",
                 "hiddenFields": list(rvb.REVIEW_HIDDEN_LAW),
                 "options": list(rvb.decision_options()),
                 "choiceOptions": list(rvb._cover_choice_options()),
                 "notes": rvb.NOTES_FIELD_LABEL}):
        res = rvb.plan_review_build(_FakeClient([row]), "loc_tmpl")
        assert res["ok"] is True and res["af_code"] == "NO-OP", res
        # the alias row carries its OWN synthetic id (never the engine pin)
        assert res["form_id"].startswith("FakeAliasRowId")


# ---------------------------------------------------------------------------
# Option drift attacks: a THIRD decision option, a renamed option, a drifted
# cover set -- each refused in dry-run, each normalized to the contract set
# under --execute.
# ---------------------------------------------------------------------------
def test_every_option_drift_refuses_in_dry_run_and_normalizes_on_execute():
    """A third decision option, a missing decision option, a reordered pair,
    a shortened cover set, an extra cover option -- EVERY drift refuses in
    dry-run (ok False, DRY-RUN, nothing written) and normalizes to the
    contract set under --execute (ok True, applied True, ONE PUT carrying
    the contract set)."""
    cases = (
        ("options", ["Approve as-is", "Request rewrite with notes", "Third"]),
        ("options", ["Approve as-is"]),
        ("options", ["Request rewrite with notes", "Approve as-is"]),
        ("choiceOptions", ["Signature", "Bold Editorial"]),
        ("choiceOptions", ["Signature", "Bold Editorial", "Fine Art",
                           "Pure Type", "Extra"]),
    )
    full_labels = list(rvb.decision_options())
    for key, value in cases:
        rows = _golden_rows()
        for r in rows:
            if fr._row_id(r) == REVIEW_FORM_ID:
                r[key] = list(value)
        res = rvb.plan_review_build(_FakeClient(rows), "loc_tmpl")
        assert res["ok"] is False and res["af_code"] == "DRY-RUN", (
            "drift %r=%r must refuse in dry-run" % (key, value))
        assert res["form_id"] == REVIEW_FORM_ID
        client = _FakeClient(rows)
        res = rvb.plan_review_build(client, "loc_tmpl", execute=True)
        assert res["ok"] is True and res["applied"] is True, (
            "drift %r=%r must build under --execute, got %r" % (key, value, res))
        puts = _puts(client)
        assert puts[0]["body"].get(key) == (
            full_labels if key == "options"
            else list(rvb._cover_choice_options())), (
            "the PUT body must normalize %r to the contract set" % key)


def test_missing_notes_surface_refuses_then_is_restored():
    """The notes surface absent -> dry-run refuses; --execute restores the
    multi-line notes field (the LARGE_TEXT law)."""
    rows = _golden_rows()
    for r in rows:
        if fr._row_id(r) == REVIEW_FORM_ID:
            del r["notes"]
    res = rvb.plan_review_build(_FakeClient(rows), "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "DRY-RUN", (
        "a missing notes surface must refuse in dry-run")
    client = _FakeClient(rows)
    res = rvb.plan_review_build(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is True
    puts = _puts(client)
    assert "notes" in puts[0]["body"], (
        "the PUT body must restore the notes surface")


# ---------------------------------------------------------------------------
# The container-spelling law: the contract surface is the key SET, so a
# spelling-only drift is an idempotent NO-OP (nothing written, never churn);
# a content drift under a snake spelling preserves the live spelling and
# writes the contract pair.
# ---------------------------------------------------------------------------
def test_spelling_only_drift_is_an_idempotent_no_op():
    """A row carrying the pair under "hidden_fields" (snake) instead of
    "hiddenFields" is NOT a contract drift -- idempotent NO-OP, nothing
    written, never a churn."""
    rows = [_intake_row(),
            _drift_review_row(hidden_fields=list(rvb.REVIEW_HIDDEN_LAW))]
    del rows[1]["hiddenFields"]
    client = _FakeClient(rows)
    res = rvb.plan_review_build(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is False, res
    assert res["af_code"] == "NO-OP"
    assert not _puts(client), "a spelling-only drift must never perform a PUT"


def test_content_drift_preserves_the_live_container_spelling():
    """A content drift under the snake spelling builds under --execute and
    the PUT body PRESERVES the live container spelling while writing the
    contract pair."""
    rows = [_intake_row(),
            _drift_review_row(hidden_fields=list(hfm.HIDDEN_FIELD_LAW))]
    del rows[1]["hiddenFields"]
    client = _FakeClient(rows)
    res = rvb.plan_review_build(client, "loc_tmpl", execute=True)
    assert res["ok"] is True and res["applied"] is True, res
    puts = _puts(client)
    assert "hidden_fields" in puts[0]["body"], (
        "the PUT body must preserve the live container spelling")
    assert puts[0]["body"]["hidden_fields"] == list(rvb.REVIEW_HIDDEN_LAW), (
        "the PUT body must write the contract pair under the live spelling")


# ---------------------------------------------------------------------------
# Never-a-token: a credential-shaped string on ANY surface REFUSES the whole
# plan rather than print it (the pit- shape; a token value is never echoed).
# ---------------------------------------------------------------------------
def test_credential_shaped_hidden_field_refuses_without_printing():
    """A hidden-field value that IS a credential-shaped string REFUSES the
    whole plan (ReviewBuildError) -- never echoed, never printed."""
    rows = [_drift_review_row(hiddenFields=["pit-abc123", "stage"])]
    with pytest.raises(rvb.ReviewBuildError):
        rvb.plan_review_build(_FakeClient(rows), "loc_tmpl")


def test_credential_shaped_pinned_id_refuses():
    """A credential-shaped pinned id REFUSES the same way -- an id that looks
    like a token is not a form this builder reports."""
    with pytest.raises(fr.FormsReadError):
        rvb.plan_review_build(_FakeClient(_golden_rows()), "loc_tmpl",
                              pinned_id="pit-abc123")


def test_full_ids_never_ride_any_surface():
    """The full form id never appears on any report surface -- the masked
    marker (last 4 chars, the house surface shape) is the only id shape.
    The masked marker itself is expected (the report's form_id_masked), so
    the assert is the FULL id value, never the marker."""
    for kwargs in ({}, {"execute": True}):
        res = rvb.plan_review_build(_FakeClient(_golden_rows()), "loc_tmpl",
                                    **kwargs)
        assert res["form_id"] == REVIEW_FORM_ID  # the ok surface carries the
        # id VALUE in the dict (the machine contract); the JSON surface may
        # too -- the masking law is enforced per-STRING at emit time by the
        # module's own surfaces (plan / _run_apply), scanned here
        dumped = json.dumps(res, indent=2, sort_keys=True)
        assert CREDENTIAL_SHAPE.search(dumped) is None, (
            "a report surface leaked a credential-shaped string")
        assert "Bearer" not in dumped
        assert res["form_id_masked"] == rvb._mask_id(REVIEW_FORM_ID), (
            "the masked marker must be the house last-4 surface")
        assert rvb._mask_id(REVIEW_FORM_ID) == "...Lqq0"


def test_cli_apply_report_emits_only_the_masked_marker(monkeypatch):
    """The CLI apply report (the JSON the machine consumer sees) carries
    form_id_masked and NO full form id -- proven with the CLI's stdout
    capture, the seam that actually reaches an operator."""
    import contextlib
    import io
    rows = _golden_rows()
    client = _FakeClient(rows)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = rvb._run_apply(client, "loc_tmpl", "", execute=False, out=None)
    assert rc == EX_OK
    assert "...Lqq0" in buf.getvalue(), (
        "the CLI report must carry the masked marker")


# ---------------------------------------------------------------------------
# The read-back law: a PUT that returned success but cannot be read back is
# HELD (the live state is UNDETERMINED, never reported as built); a read-back
# that does not prove the build is READBACK-MISMATCH; a validation refusal on
# the PUT is a STOP; a scope refusal on the read-back is a STOP, never demoted
# to a HELD.
# ---------------------------------------------------------------------------
class _WriteButUnreadableClient(_FakeClient):
    """The PUT is accepted, but every read after it raises transport -- the
    applied-but-unreadable seam (HELD family, never fabricated)."""

    def _request(self, method, path, query=None, body=None):
        self.calls.append({"method": method, "path": path})
        if method == "PUT":
            for row in self._rows:
                if fr._row_id(row) == REVIEW_FORM_ID:
                    row.update(dict(body))
                    return {}
            raise reg.CafUnreachable("form id not found (fixture)")
        raise reg.CafUnreachable("read-back transport failure (fixture)")


class _ScopeOnReadbackClient(_FakeClient):
    """The PUT is accepted; the read-back then refuses scope -- a real
    credential problem on the SECOND leg, a STOP, never a HELD."""

    def _request(self, method, path, query=None, body=None):
        self.calls.append({"method": method, "path": path})
        if method == "PUT":
            for row in self._rows:
                if fr._row_id(row) == REVIEW_FORM_ID:
                    row.update(dict(body))
                    return {}
            raise reg.CafUnreachable("form id not found (fixture)")
        raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")


def test_applied_but_unreadable_put_is_held_never_reported_built():
    """A PUT that returned success but cannot be read back is HELD
    (reg.CafUnreachable) -- the live state is UNDETERMINED, never reported
    as built."""
    rows = _golden_rows()
    for r in rows:
        if fr._row_id(r) == REVIEW_FORM_ID:
            r["hiddenFields"] = list(hfm.HIDDEN_FIELD_LAW)
    with pytest.raises(reg.CafUnreachable):
        rvb.plan_review_build(_WriteButUnreadableClient(rows),
                              "loc_tmpl", execute=True)


def test_scope_refusal_on_read_back_stops_never_held():
    """A genuine scope refusal on the read-back leg is a STOP
    (reg.ScopeDenied) -- never demoted to a HELD misdiagnosis."""
    rows = _golden_rows()
    for r in rows:
        if fr._row_id(r) == REVIEW_FORM_ID:
            r["hiddenFields"] = list(hfm.HIDDEN_FIELD_LAW)
    with pytest.raises(reg.ScopeDenied):
        rvb.plan_review_build(_ScopeOnReadbackClient(rows),
                              "loc_tmpl", execute=True)


def test_put_validation_refusal_is_a_stop():
    """A 400/409/422 validation refusal on the PUT is a STOP
    (ReviewBuildError), never a silent skip."""
    rows = _golden_rows()
    for r in rows:
        if fr._row_id(r) == REVIEW_FORM_ID:
            r["hiddenFields"] = list(hfm.HIDDEN_FIELD_LAW)
    with pytest.raises(rvb.ReviewBuildError):
        rvb.plan_review_build(_FakeClient(rows, fail_put=True),
                              "loc_tmpl", execute=True)


def test_plan_never_raises_for_a_data_mismatch():
    """A data mismatch is a RESULT, never a raise -- for golden, drifted,
    empty, foreign, and pin-missing shapes alike (a raise is reserved for a
    broken shape / transport / scope)."""
    shapes = (
        _golden_rows(),
        [_drift_review_row(hiddenFields=list(hfm.HIDDEN_FIELD_LAW))],
        [],
        [{"id": "OtherFormId0000", "name": "Contact Us"}],
        [_drift_review_row(id="DriftedDriftedId00")],
    )
    for rows in shapes:
        res = rvb.plan_review_build(_FakeClient(rows), "loc_tmpl",
                                    pinned_id=REVIEW_FORM_ID)
        assert isinstance(res, dict) and "af_code" in res, res
        assert res["contract"] == rvb.CONFIG_CONTRACT


# ---------------------------------------------------------------------------
# The CLI surface: the dry-run exit mapping (drift -> exit 5, nothing
# written), the --execute refusal before any credential is even resolved,
# the STOP mapping, and the HELD mapping.
# ---------------------------------------------------------------------------
def test_cli_apply_dry_run_on_drift_exits_5():
    """apply without --execute on a drifted form: ONE JSON report on stdout
    (ok False, DRY-RUN), exit 5, nothing written (the CLI never invents an
    --execute it was not given)."""
    rows = [_intake_row(),
            _drift_review_row(hiddenFields=list(hfm.HIDDEN_FIELD_LAW))]

    class _LocalClient(_FakeClient):
        """Same seam, recorded so the caller can assert no PUT happened."""

    client = _LocalClient(rows)
    rc = rvb._run_apply(client, "loc_tmpl", "", execute=False, out=None)
    assert rc == EX_MISMATCH, "a drifted dry-run must exit 5, got %s" % rc
    assert not _puts(client), "a dry-run must never perform a PUT"


def test_cli_apply_no_op_exits_0():
    """apply on a contract-matching form exits 0 (idempotent no-op, nothing
    written)."""
    rc = rvb._run_apply(_FakeClient(_golden_rows()), "loc_tmpl", "",
                        execute=False, out=None)
    assert rc == EX_OK


def test_cli_apply_forms_not_found_stops_exit_2():
    """apply when the review form cannot be identified STOPS (exit 2) --
    reg._stop never returns a pass."""
    rc = rvb._run_apply(_FakeClient([]), "loc_tmpl", "", execute=False,
                        out=None)
    assert rc == EX_STOP, "FORMS-EMPTY must STOP (exit 2), got %s" % rc


def test_cli_missing_pit_refuses_before_any_read(monkeypatch):
    """apply without a resolved PIT STOPS (exit 2) -- no credential, no
    client, no read. The refusal happens BEFORE any network call."""
    calls = []

    def _no_pit():
        return None, None

    monkeypatch.setattr(rvb.reg, "resolve_pit", _no_pit)
    old_argv = sys.argv
    sys.argv = ["universal_review_builder.py", "apply"]
    try:
        code = rvb.main()
    finally:
        sys.argv = old_argv
    assert code == EX_STOP, "a missing PIT must STOP (exit 2), got %s" % code
    assert calls == []


def test_cli_self_test_and_plan_are_offline(monkeypatch):
    """self-test and plan need NO token and NO network -- they run with a
    resolve_pit that would raise if touched."""
    def _forbidden_pit():
        raise AssertionError("offline commands must never resolve a token")

    monkeypatch.setattr(rvb.reg, "resolve_pit", _forbidden_pit)
    old_argv = sys.argv
    try:
        sys.argv = ["universal_review_builder.py", "plan"]
        assert rvb.main() == EX_OK
        sys.argv = ["universal_review_builder.py", "self-test"]
        assert rvb.main() == EX_OK
    finally:
        sys.argv = old_argv


# ---------------------------------------------------------------------------
# The module's own offline self-test battery (the house self-test convention:
# run as a process so a tamper never masquerades as exit 1), and the golden
# sibling family stays green.
# ---------------------------------------------------------------------------
def test_module_self_test_battery_passes():
    """The module's own offline golden/attack battery must pass: golden
    no-op writes nothing, the intake-trio drift refuses in dry-run, the
    execute apply + read-back proves the build, and the review contract
    stays pinned to the owning authorities."""
    proc = subprocess.run(
        [sys.executable, str(U08 / "universal_review_builder.py"),
         "self-test"],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == EX_OK, (
        "universal_review_builder self-test FAILED (exit %d):\n%s\n%s"
        % (proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:]))


def test_self_test_is_offline_with_empty_environment():
    """The self-test must not touch the network -- an EMPTY environment
    (no secrets, no proxy state) must still pass (it is pure)."""
    import os
    env = {k: v for k, v in os.environ.items()
           if k in ("PATH", "SYSTEMROOT", "HOME", "PYTHONPATH")}
    proc = subprocess.run(
        [sys.executable, str(U08 / "universal_review_builder.py"),
         "self-test"],
        capture_output=True, text=True, timeout=120, env=env)
    assert proc.returncode == EX_OK, (
        "self-test must pass with an empty environment (exit %d):\n%s\n%s"
        % (proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:]))


def test_sibling_self_tests_stay_green():
    """The U08/U09 family's other offline batteries pass -- the golden
    review fixture and the form-spec loader -- so the builder is tested
    against a green family (a red sibling is caught HERE first)."""
    import golden_review as gr  # noqa: F401
    import form_spec_loader as fsl  # noqa: F401
    import io
    assert gr.self_test(out=io.StringIO()) == EX_OK
    assert fsl.self_test() == EX_OK


# ---------------------------------------------------------------------------
# Never-print, family-wide: no credential-shaped string rides any captured
# surface of the builder or of the report fixtures it pins against.
# ---------------------------------------------------------------------------
def test_no_credential_shape_on_any_captured_surface():
    """Every surface this battery captures -- the plan report, the no-op
    report, the dry-run report, the CREATED report -- is scanned against the
    pit- credential shape and the Bearer shape."""
    surfaces = [
        json.dumps(rvb.plan_review_build(_FakeClient(_golden_rows()),
                                         "loc_tmpl"), sort_keys=True),
        json.dumps(rvb.plan_review_build(
            _FakeClient(_golden_rows()), "loc_tmpl", execute=True),
            sort_keys=True),
        json.dumps(rvb.plan_review_build(
            _FakeClient([_drift_review_row(hiddenFields=list(
                hfm.HIDDEN_FIELD_LAW))]), "loc_tmpl"), sort_keys=True),
    ]
    import io
    buf = io.StringIO()
    assert rvb.plan("loc_tmpl", out=buf) == EX_OK
    surfaces.append(buf.getvalue())
    for blob in surfaces:
        assert CREDENTIAL_SHAPE.search(blob) is None, (
            "a captured surface leaked a credential-shaped string")
        assert "Bearer" not in blob, (
            "a captured surface leaked a Bearer shape")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
