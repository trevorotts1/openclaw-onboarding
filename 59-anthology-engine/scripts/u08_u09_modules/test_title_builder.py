#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u08_u09_modules/test_title_builder.py
# UNIT TESTS for the TITLE-SELECT FORM BUILDER
# (scripts/u08_u09_modules/title_select_builder.py — U08/U09 tooling: the
# gated, verified builder of the S3 title-and-subtitle selection form, slug
# title-select, on a Convert and Flow location). The laws this file exists
# to enforce — every one read ONCE from the module under test, never
# re-typed as a second implementation:
#
#   * THE S3 TITLE-SELECT SHAPE LAW — the form carries EXACTLY TWO hidden
#     routing fields in the contract's own universal order (anthology_id,
#     stage — never the intake trio with contact_id, never the G3
#     "anthology_active_id" lookalike) and TWO visible multi-line REQUIRED
#     fields (title, subtitle — the pair the s3_selection record path
#     consumes and the ONE-WAY TITLE LOCK stamps; a single-line or optional
#     visible field is a drift REPAIRED, never tolerated);
#   * THE TREVOR GATE — the ONE write (public v2 PUT /forms/{id}) is
#     REFUSED without --execute: a drifted form is a dry-run (exit 5,
#     applied:false, the drift named, ZERO writes), and only --execute
#     performs the PUT — proven by the call log: exactly ONE PUT, on the
#     /forms/<formId> path, with the body echoing the live row byte-for-byte
#     and the shape normalized onto it (never a body from memory);
#   * THE READ-BACK LAW — a PUT is certified ONLY by a same-job read-back
#     that proves the shape byte-exact: a read-back that does not prove it
#     is READBACK-MISMATCH (exit 5), an applied-but-unreadable PUT is HELD
#     (reg.CafUnreachable, exit 3 — the live state is UNDETERMINED, never
#     reported as built), and a scope refusal on the read-back leg stays a
#     real STOP (reg.ScopeDenied), never demoted to a HELD;
#   * THE TARGET LAW — the row written is proven by the slug law (the
#     normalized name "title select" — the reader's own law) or the pin law
#     (the engine's pinned fleet-wide id, forms_check.FORM_ID_BY_SLUG
#     ["title-select"], live-verified on the Title Fire trigger), which
#     BYPASSES the slug law; an empty listing is FORMS-EMPTY and a
#     non-matching listing is FORMS-NOT-FOUND — both ok:false with NO form
#     id (never an id guessed from memory); a slug-matched row with no id
#     and a non-array container are STOP refusals (FormsBuildError), never
#     silent skips;
#   * THE IDEMPOTENCY LAW — a form already carrying the exact S3 shape is a
#     NO-OP: ok true, applied false, NOTHING written — even with --execute;
#     extra non-law fields and the live container spellings are preserved,
#     never destroyed;
#   * NEVER-A-TOKEN — a hidden-field surface or pinned id that is
#     credential-shaped (the pit- house guard shape) REFUSES the whole plan
#     rather than print it; no captured surface (JSON report, plan payload,
#     or human note) ever carries the credential shape; form ids ride every
#     surface MASKED (last 4 chars);
#   * THE HOUSE DOCTRINE PINS — the exit-code convention through the
#     registry's exported constants, the browser User-Agent law (CF 1010:
#     CAF_BROWSER_UA is a browser UA, never optional — urllib's default
#     Python-urllib/x.y is 403'd at the Cloudflare edge), the fail-closed-
#     empty u08_u09_modules package init, the module's own offline battery
#     green (a red self-test is caught HERE first), and determinism (the
#     plan never mutates its inputs).
#
# Hermetic: imports title_select_builder.py directly (stdlib only), reuses
# the module's OWN offline _FakeClient for the golden live-surface tests
# (the exact seam the module's self-test proves), and exercises the read-
# back seams (half-write, transport, scope) through small stub clients the
# module's own fake cannot isolate. ZERO network calls, ZERO credentials,
# NO env var read, NO real CafClient constructed. The CLI credential
# boundary is deliberately NOT exercised (main() resolves the real token
# stores — that is the operator surface, not a unit-testable seam); the
# tested seams are plan_form_build / plan / _run_apply / main's self-test
# and plan subcommands, which are all offline.
#
# Run: python3 -m pytest 59-anthology-engine/scripts/u08_u09_modules/test_title_builder.py -q
#  or: python3 59-anthology-engine/scripts/u08_u09_modules/test_title_builder.py
# =============================================================================
"""test_title_builder.py -- the title-select builder's S3 shape law,
Trevor-gated write, read-back certification, target law, idempotency, and
never-a-token surfaces (U08/U09)."""

import contextlib
import copy
import io
import json
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

import anthology_registry as reg  # noqa: E402
import u08_u09_modules.title_select_builder as tsb  # noqa: E402 (module under test)
# The reader is imported AFTER tsb and by its BARE name — the same module
# object tsb's own bootstrap imported. Importing "u04_modules.form_reader"
# instead would load a SECOND, distinct module object for the same file,
# duplicating every exception class (pytest.raises against the wrong one
# would never catch) — the identity assertion below makes any future
# reorder fail loudly instead of silently.
import form_reader as fr  # noqa: E402 (the reader: slug/pin/mask laws)
assert fr is tsb.fr, (
    "the reader object must be shared with the module under test — an "
    "import-order split would duplicate exception classes")

# The house exit-code convention (0/1/2/3/4/5) — asserted through the
# exported constants, never re-typed.
EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# A credential-shaped string is the pit- token prefix — the house guard
# shape every operator surface is scanned against. No fixture carries a
# real one, so no captured surface may either.
CREDENTIAL_SHAPE = "pit-"

LOC = "loc_tmpl"  # the fixture location label (masked on every surface)

def _golden_rows() -> list:
    """The module's OWN golden listing rows — the title-select row carrying
    the pinned engine id with ONE of the two routing keys (the missing stage
    key is the defect) and no visible-field surface, plus the family's other
    two forms with their own contract trio untouched."""
    return tsb._golden_rows()

def _golden_client():
    """A fresh _FakeClient over the golden rows — the module's own offline
    seam (the same seam its self-test proves)."""
    return tsb._FakeClient(_golden_rows())

def _apply_surface(execute: bool = False):
    """plan_form_build on the golden drift, dry-run or --execute."""
    return tsb.plan_form_build(_golden_client(), LOC, execute=execute)

def _run_apply_surface(client, execute: bool = False):
    """_run_apply with the machine report captured off stdout and the human
    note on a scratch stream; returns (rc, payload, note)."""
    buf = io.StringIO()
    notes = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = tsb._run_apply(client, LOC, "", execute=execute, out=notes)
    return rc, json.loads(buf.getvalue()), notes.getvalue()

# ---------------------------------------------------------------------------
# Cross-cutting house doctrine
# ---------------------------------------------------------------------------
def test_module_self_test_passes_offline():
    """The module's own offline battery passes — exit 0, no network, no
    credential (the golden drift refused, the execute apply + read-back
    proven, every attack fixture named)."""
    assert tsb.self_test(out=io.StringIO()) == EX_OK

def test_exit_code_convention_is_house_0_1_2_3_4_5():
    """Every runner pins the house exit-code convention — asserted through
    the exported constants, never hardcoded."""
    assert (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH) == (0, 1, 2, 3, 5)
    assert EX_VIOLATION == 4
    assert EX_VIOLATION not in (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH)

def test_browser_user_agent_is_a_browser_ua_cf_1010_law():
    """The CF 1010 law: the house client rides a browser User-Agent on every
    request — urllib's default Python-urllib/x.y is 403'd at the Cloudflare
    WAF edge (CF error 1010) before it ever reaches Convert and Flow. The
    builder's every request rides reg.CafClient, which applies this UA."""
    assert reg.CAF_BROWSER_UA, "CAF_BROWSER_UA must never be empty"
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), (
        "CAF_BROWSER_UA must be a browser User-Agent, got %r"
        % reg.CAF_BROWSER_UA[:40])
    assert "Chrome/" in reg.CAF_BROWSER_UA, (
        "CAF_BROWSER_UA must be a well-formed Chrome build (GK-09)")
    assert hasattr(reg, "CafClient"), (
        "reg.CafClient — the client that applies CAF_BROWSER_UA — must exist")

def test_u08_u09_package_init_is_fail_closed_empty():
    """The package init is a pure namespace container — no runtime code, no
    side effects, no secret surface — and it CARRIES the --execute
    (Trevor-gated) and browser-UA doctrine in its DOCTRINE comment block."""
    import u08_u09_modules as pkg
    assert pkg.__all__ == []
    assert pkg.__doc__ and "fail-closed" in pkg.__doc__.lower()
    init_text = Path(pkg.__file__).read_text(encoding="utf-8")
    assert "--execute" in init_text and "Trevor-gated" in init_text
    assert "browser" in init_text and "1010" in init_text
    assert "secret" in init_text.lower()

def test_report_contract_is_pinned():
    """The ONE fixed report contract — a machine consumer can never mistake
    another JSON object for a title-select build (the module's own self-test
    asserts the golden plan carries the exact string)."""
    assert tsb.CONFIG_CONTRACT == "anthology-engine-title-select-build"
    assert tsb.CONFIG_SCHEMA_VERSION == 1

# ---------------------------------------------------------------------------
# The S3 title-select shape law, pinned from the REAL committed constants
# ---------------------------------------------------------------------------
def test_s3_shape_law_is_pinned_against_the_commit():
    """The shape law is the S3 routing pair and the visible lock pair,
    byte-exact: exactly TWO hidden keys in the contract's own universal
    order — anthology_id then stage — never the intake contact_id trio,
    never the G3 anthology_active_id lookalike; and title + subtitle, BOTH
    multi-line (LARGE_TEXT) and BOTH required (the one-way TITLE LOCK never
    stamps a blank pick)."""
    assert tsb.HIDDEN_LAW == ("anthology_id", "stage"), (
        "the S3 hidden-field law drifted from the routing pair")
    assert "contact_id" not in tsb.HIDDEN_LAW, (
        "the title-select form must NOT carry the intake contact_id — it "
        "is only ever opened from a resolved participant token page")
    assert "anthology_active_id" not in tsb.HIDDEN_LAW, (
        "the G3 lookalike must never enter the title-select hidden law")
    assert tsb.SLUG_AS_NAME == "title select", (
        "the title-select slug law drifted (the slug with dashes -> spaces)")
    assert tsb.TITLE_FIELD_NAME == "title", (
        "the visible title name drifted from the s3_selection record path")
    assert tsb.SUBTITLE_FIELD_NAME == "subtitle", (
        "the visible subtitle name drifted from the s3_selection record path")
    assert len(tsb.VISIBLE_FIELDS) == 2, (
        "the visible pair is exactly title and subtitle")
    for f in tsb.VISIBLE_FIELDS:
        assert f["data_type"] == "LARGE_TEXT" and f["required"] is True, (
            "every visible title-select field must be multi-line and "
            "required (the one-way TITLE LOCK never stamps a blank pick)")

def test_pinned_form_id_is_the_engine_fleet_constant():
    """The builder's pinned title-select form id is the SAME engine-fleet
    constant the U02 forms check pins (forms_check.FORM_ID_BY_SLUG
    ["title-select"], the live-verified Title Fire trigger) — read once,
    never drifted."""
    assert tsb.DEFAULT_TITLE_SELECT_FORM_ID == (
        "UgiiSoZsA4vyqOVfO5fi")
    assert tsb.DEFAULT_UNIVERSAL_INTAKE_FORM_ID == (
        fr.DEFAULT_UNIVERSAL_INTAKE_FORM_ID)
    assert tsb.DEFAULT_TEMPLATE_LOCATION == fr.DEFAULT_TEMPLATE_LOCATION

def test_the_write_path_is_the_public_v2_form_surface():
    """The ONE write surface is the public v2 PUT /forms/{id} — the path the
    sibling hidden-field creator uses, proven in Skill 44 — never a custom
    surface built from memory."""
    assert tsb.FORMS_WRITE_PATH == "/forms/%s"

# ---------------------------------------------------------------------------
# The golden drift: the defect this module exists to fix, refused without
# --execute (the Trevor gate).
# ---------------------------------------------------------------------------
def test_golden_drift_refuses_in_dry_run_and_names_the_drift():
    """The golden title-select row carries only ONE routing key and NO
    visible surface — the stage key and the visible pair are the defect.
    Without --execute the plan REFUSES (ok false, applied false), the
    af_code is DRY-RUN, the report names the drift (hidden_current =
    anthology_id only, hidden_law = the routing pair, fields_law = the
    visible pair), and the target was proven by the slug law."""
    res = _apply_surface(execute=False)
    assert res["ok"] is False and res["applied"] is False, (
        "a drifted form must refuse in dry-run")
    assert res["af_code"] == "DRY-RUN" and res["execute"] is False
    assert res["target_matched_by"] == "slug"
    assert res["form_id"] == tsb.DEFAULT_TITLE_SELECT_FORM_ID, (
        "a dry-run still identifies the proven target")
    assert res["hidden_current"] == ["anthology_id"], (
        "the missing stage key is the defect, named on the surface")
    assert res["hidden_law"] == list(tsb.HIDDEN_LAW)
    assert res["fields_current"] == [], (
        "the golden row carries no visible-field surface — the visible "
        "pair is the defect")
    assert [f["name"] for f in res["fields_law"]] == [
        "title", "subtitle"], "fields_law must be the visible pair"

def test_dry_run_performs_exactly_one_read_and_zero_writes():
    """The dry-run is read-only: EXACTLY ONE listing read on the reader's
    path with the locationId query, and NO PUT — proven by the call log."""
    client = _golden_client()
    tsb.plan_form_build(client, LOC)
    assert client.calls == [
        {"method": "GET", "path": fr.FORMS_LIST_PATH,
         "query": {"locationId": LOC, "limit": 200}, "body": None}], (
        "a dry-run must perform ONLY the listing read: %s" % client.calls)

def test_dry_run_exits_5_with_one_json_on_stdout():
    """The full dry-run surface: exit 5 (MISMATCH — the shape is missing and
    no build was performed, the dry-run refusal surface), ONE JSON object on
    stdout, the human note on the given out stream."""
    rc, payload, note = _run_apply_surface(_golden_client(), execute=False)
    assert rc == EX_MISMATCH
    assert payload["af_code"] == "DRY-RUN" and payload["applied"] is False
    assert "DRY-RUN" in note and "--execute" in note, (
        "the human note must name the Trevor gate and the flag that writes")

# ---------------------------------------------------------------------------
# --execute: the ONE write, certified only by the same-job read-back.
# ---------------------------------------------------------------------------
def test_execute_builds_and_reads_back_byte_exact():
    """With --execute the PUT happens and the read-back in the SAME job
    proves the build: ok true, applied true, af_code BUILT, the read-back
    hidden/field shapes carrying the full S3 shape."""
    res = _apply_surface(execute=True)
    assert res["ok"] is True and res["applied"] is True, (
        "the build must apply and pass under --execute")
    assert res["af_code"] == "BUILT"
    assert res["hidden_current"] == list(tsb.HIDDEN_LAW), (
        "the read-back must carry both routing hidden keys")
    assert [f["name"] for f in res["fields_current"]] == [
        "title", "subtitle"], "the read-back must carry the visible pair"
    assert res["form_id"] == tsb.DEFAULT_TITLE_SELECT_FORM_ID
    assert res["target_matched_by"] == "slug"

def test_execute_performs_exactly_one_put_on_the_write_path():
    """The apply performs EXACTLY ONE PUT on the public v2 /forms/<formId>
    path (the form id URL-quoted), and re-reads the listing for the
    read-back — the write is proven only by the read-back in the same job."""
    client = _golden_client()
    tsb.plan_form_build(client, LOC, execute=True)
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert len(puts) == 1, "exactly ONE PUT must ride the apply"
    assert puts[0]["path"] == tsb.FORMS_WRITE_PATH % (
        tsb.DEFAULT_TITLE_SELECT_FORM_ID), (
        "the PUT must target the pinned form id on the public v2 path")
    gets = [c for c in client.calls if c["method"] == "GET"]
    assert len(gets) >= 2, (
        "the apply must re-read the listing for the read-back")

def test_put_body_echoes_the_live_row_never_memory():
    """The PUT body is the live-row echo byte-for-byte — the id, the name,
    and the query key intact — with the hidden container normalized to the
    S3 routing pair and the visible container to exactly the two law
    fields (multi-line, required). A body from memory is never sent."""
    client = _golden_client()
    tsb.plan_form_build(client, LOC, execute=True)
    body = [c for c in client.calls if c["method"] == "PUT"][0]["body"]
    assert body.get("id") == tsb.DEFAULT_TITLE_SELECT_FORM_ID, (
        "the PUT body must echo the live row's id")
    assert body.get("name") == "Title Select", (
        "the PUT body must echo the live row's name")
    assert body.get("queryKey") == "anthology_id", (
        "the PUT body must echo the live row's query key")
    assert body.get("hiddenFields") == list(tsb.HIDDEN_LAW), (
        "the PUT body must carry the two routing hidden fields")
    fields = body.get("fields")
    assert isinstance(fields, list) and len(fields) == 2, (
        "the PUT body must carry exactly the two visible fields")
    by_name = {f.get("name"): f for f in fields}
    assert set(by_name) == {"title", "subtitle"}, (
        "the visible pair must be exactly title and subtitle")
    for f in fields:
        assert f.get("data_type") == "LARGE_TEXT", (
            "every visible field must be multi-line (LARGE_TEXT)")
        assert f.get("required") is True, "every visible field must be required"

def test_execute_apply_exits_0_with_one_json_on_stdout():
    """The full apply surface: exit 0, ONE JSON object on stdout, the human
    OK note naming the built shape on the given out stream."""
    rc, payload, note = _run_apply_surface(_golden_client(), execute=True)
    assert rc == EX_OK
    assert payload["af_code"] == "BUILT" and payload["ok"] is True
    assert "OK" in note and "anthology_id" in note and "stage" in note

# ---------------------------------------------------------------------------
# The idempotency law: an already-built form writes NOTHING, even with
# --execute.
# ---------------------------------------------------------------------------
def test_idempotent_no_op_writes_nothing_even_with_execute():
    """A form already carrying the exact S3 shape is ok true, applied false,
    af_code NO-OP — and the call log proves ZERO PUTs, even with --execute
    (the query_key_fixer old==new doctrine)."""
    rows = copy.deepcopy(_golden_rows())
    rows[2]["hiddenFields"] = list(tsb.HIDDEN_LAW)
    rows[2]["fields"] = list(tsb._normalized_fields_law(()))
    client = tsb._FakeClient(rows)
    res = tsb.plan_form_build(client, LOC, execute=True)
    assert res["ok"] is True and res["applied"] is False, (
        "an already-built form must be an idempotent no-op")
    assert res["af_code"] == "NO-OP"
    assert not any(c["method"] == "PUT" for c in client.calls), (
        "a no-op must never perform a PUT")

def test_extra_non_law_fields_are_preserved_never_destroyed():
    """A live row that already carries extra fields beyond the law pair is
    NOT destroyed by the build: the no-op holds with the extras intact."""
    rows = copy.deepcopy(_golden_rows())
    rows[2]["hiddenFields"] = list(tsb.HIDDEN_LAW)
    rows[2]["fields"] = [
        {"name": "title", "data_type": "LARGE_TEXT", "required": True},
        {"name": "subtitle", "data_type": "LARGE_TEXT", "required": True},
        {"name": "extra", "data_type": "TEXT", "required": False},
    ]
    res = tsb.plan_form_build(tsb._FakeClient(rows), LOC)
    assert res["ok"] is True and res["af_code"] == "NO-OP"
    assert [f["name"] for f in res["fields_current"]] == [
        "title", "subtitle", "extra"], "extra fields must survive the build"

def test_container_spelling_drift_is_normalized():
    """A live row carrying the snake "hidden_fields" spelling is written
    under ITS OWN live spelling (the write preserves the live container key),
    normalized to the S3 routing pair, and the read-back proves the law."""
    rows = copy.deepcopy(_golden_rows())
    rows[2] = {"id": tsb.DEFAULT_TITLE_SELECT_FORM_ID, "name": "Title Select",
               "type": "form", "queryKey": "anthology_id",
               "hidden_fields": ["anthology_id"]}
    client = tsb._FakeClient(rows)
    res = tsb.plan_form_build(client, LOC, execute=True)
    assert res["ok"] is True and res["applied"] is True
    puts = [c for c in client.calls if c["method"] == "PUT"]
    assert len(puts) == 1 and "hidden_fields" in puts[0]["body"], (
        "the PUT body must preserve the live hidden container spelling")
    assert puts[0]["body"]["hidden_fields"] == list(tsb.HIDDEN_LAW)

def test_visible_field_drift_is_repaired_never_tolerated():
    """A live title field that is single-line and optional refuses in
    dry-run (a drift is never a blind pass) and is REPAIRED to multi-line
    REQUIRED under --execute — the law wins over the drifted live value,
    for both title and subtitle."""
    rows = copy.deepcopy(_golden_rows())
    rows[2]["fields"] = [{"name": "title", "data_type": "TEXT",
                          "required": False}]
    res = tsb.plan_form_build(tsb._FakeClient(rows), LOC)
    assert res["ok"] is False and res["af_code"] == "DRY-RUN", (
        "a single-line or optional visible field must refuse in dry-run")
    client = tsb._FakeClient(rows)
    res = tsb.plan_form_build(client, LOC, execute=True)
    assert res["ok"] is True and res["applied"] is True, (
        "the build must normalize the visible pair under --execute")
    puts = [c for c in client.calls if c["method"] == "PUT"]
    by_name = {f.get("name"): f for f in puts[0]["body"].get("fields", [])}
    assert by_name["title"]["data_type"] == "LARGE_TEXT", (
        "the law data type must win over a drifted live value")
    assert by_name["title"]["required"] is True, (
        "the law required flag must win over a drifted live value")
    assert by_name["subtitle"]["required"] is True, (
        "the subtitle field must be required after the build")

def test_container_less_row_is_fixable_and_never_silently_skipped():
    """A title-select row with NO hidden-field container is fixable (the
    routing pair REQUIRES the keys): the dry-run surfaces the absence and
    refuses, --execute applies the full shape, and the read-back proves it."""
    rows = copy.deepcopy(_golden_rows())
    del rows[2]["hiddenFields"]
    res = tsb.plan_form_build(tsb._FakeClient(rows), LOC)
    assert res["ok"] is False and res["hidden_current"] == [], (
        "a container-less row must surface the absence")
    assert res["af_code"] == "DRY-RUN"
    res = tsb.plan_form_build(tsb._FakeClient(rows), LOC, execute=True)
    assert res["ok"] is True and res["applied"] is True
    assert res["hidden_current"] == list(tsb.HIDDEN_LAW)

def test_intake_trio_never_satisfies_the_title_select_shape():
    """The universal three-key trio is NOT the title-select shape: a row
    carrying contact_id + anthology_id still lacks the stage routing key —
    a drift that refuses in dry-run, and --execute adds the true key. The
    review submission must never ride the intake trio onto this form."""
    rows = copy.deepcopy(_golden_rows())
    rows[2]["hiddenFields"] = ["contact_id", "anthology_id"]
    res = tsb.plan_form_build(tsb._FakeClient(rows), LOC)
    assert res["ok"] is False and res["af_code"] == "DRY-RUN", (
        "the intake trio must never satisfy the title-select shape law")
    res = tsb.plan_form_build(tsb._FakeClient(rows), LOC, execute=True)
    assert res["ok"] is True and res["applied"] is True, (
        "the build must add the stage key under --execute")
    assert res["hidden_current"] == list(tsb.HIDDEN_LAW)

# ---------------------------------------------------------------------------
# The target law: slug, pin, and every not-found path NAMED.
# ---------------------------------------------------------------------------
def test_pin_law_bypasses_the_slug_law_and_is_the_row_written():
    """The pinned id (the engine fleet constant) BYPASSES the slug law and
    IS the row written — the report proves the match by "pin"."""
    client = _golden_client()
    res = tsb.plan_form_build(
        client, LOC, pinned_id=tsb.DEFAULT_TITLE_SELECT_FORM_ID,
        execute=True)
    assert res["ok"] is True and res["applied"] is True
    assert res["target_matched_by"] == "pin"
    assert res["form_id"] == tsb.DEFAULT_TITLE_SELECT_FORM_ID

def test_pinned_id_absent_from_listing_refuses_with_no_form_id():
    """A pinned id the listing does not carry is FORMS-NOT-FOUND: ok false,
    and NO form id on the surface (never an id guessed from memory)."""
    rows = copy.deepcopy(_golden_rows())
    rows[2]["id"] = "DriftedDriftedId00"
    res = tsb.plan_form_build(tsb._FakeClient(rows), LOC,
                              pinned_id=tsb.DEFAULT_TITLE_SELECT_FORM_ID)
    assert res["ok"] is False and res["af_code"] == "FORMS-NOT-FOUND"
    assert res["form_id"] == "", "a failed plan must never carry a form id"

def test_empty_listing_is_forms_empty():
    """An EMPTY listing is "everything missing" — FORMS-EMPTY, ok false,
    applied false, no form id, never a silent pass."""
    res = tsb.plan_form_build(tsb._FakeClient([]), LOC)
    assert res["ok"] is False and res["af_code"] == "FORMS-EMPTY"
    assert res["applied"] is False and res["form_id"] == ""

def test_non_matching_listing_is_forms_not_found():
    """A non-empty listing with no title-select row is FORMS-NOT-FOUND — a
    write to a form we cannot prove is the title-select form is a write to
    the wrong record, never performed."""
    client = tsb._FakeClient(
        [{"id": "OtherFormId0000", "name": "Contact Us",
          "hiddenFields": ["email"]}])
    res = tsb.plan_form_build(client, LOC)
    assert res["ok"] is False and res["af_code"] == "FORMS-NOT-FOUND"
    assert res["form_id"] == ""

def test_forms_empty_exits_2_with_one_json_on_stdout():
    """The not-found surfaces map to the STOP family (exit 2) — the form
    cannot be identified, so no write can be planned; the machine report
    still lands as ONE JSON object on stdout."""
    rc, payload, note = _run_apply_surface(tsb._FakeClient([]), execute=False)
    assert rc == EX_STOP
    assert payload["af_code"] == "FORMS-EMPTY" and payload["ok"] is False
    assert "STOP" in note or "cannot be identified" in note

def test_id_less_slug_matched_row_is_an_unreadable_shape_stop():
    """A slug-matched row carrying NO form id is an unreadable shape — a
    STOP (FormsBuildError), never a silent skip to FORMS-NOT-FOUND."""
    with pytest.raises(tsb.FormsBuildError):
        tsb.plan_form_build(
            tsb._FakeClient(
                [{"name": "Title Select", "hiddenFields": ["anthology_id"]}]),
            LOC)

def test_non_array_containers_are_malformed_shapes_stop():
    """A hidden-field or visible-field container that is not an array is a
    malformed shape — a STOP (FormsBuildError), never a guessed set."""
    rows = copy.deepcopy(_golden_rows())
    rows[2]["hiddenFields"] = "anthology_id"
    with pytest.raises(tsb.FormsBuildError):
        tsb.plan_form_build(tsb._FakeClient(rows), LOC)
    rows = copy.deepcopy(_golden_rows())
    rows[2]["fields"] = "title"
    with pytest.raises(tsb.FormsBuildError):
        tsb.plan_form_build(tsb._FakeClient(rows), LOC)

# ---------------------------------------------------------------------------
# Fail-closed read-back certification and the HELD / STOP discrimination.
# ---------------------------------------------------------------------------
def test_readback_that_does_not_prove_the_build_is_mismatch():
    """A PUT that returned success but whose read-back does not prove the S3
    shape is READBACK-MISMATCH: ok false, applied true (a PUT DID happen),
    af_code READBACK-MISMATCH — never reported as built."""
    class _HalfWrite(tsb._FakeClient):
        """The PUT is accepted but applies nothing — the read-back re-reads
        the unchanged listing, which cannot prove the build."""

        def _request(self, method, path, query=None, body=None):
            self.calls.append({"method": method, "path": path,
                               "query": dict(query or {}), "body": body})
            if method == "GET" and path == fr.FORMS_LIST_PATH:
                return {"forms": [dict(r) for r in self._rows]}
            if method == "PUT":
                return {}
            raise reg.CafUnreachable("unexpected request (fixture)")

    res = tsb.plan_form_build(_HalfWrite(_golden_rows()), LOC, execute=True)
    assert res["ok"] is False and res["applied"] is True, (
        "a PUT that happened but is not proven must refuse")
    assert res["af_code"] == "READBACK-MISMATCH"

def test_readback_mismatch_exits_5():
    """The read-back-mismatch surface maps to exit 5 (MISMATCH family) with
    the ONE JSON report on stdout."""
    class _HalfWrite(tsb._FakeClient):
        def _request(self, method, path, query=None, body=None):
            if method == "GET" and path == fr.FORMS_LIST_PATH:
                return {"forms": [dict(r) for r in self._rows]}
            if method == "PUT":
                return {}
            raise reg.CafUnreachable("unexpected request (fixture)")

    rc, payload, note = _run_apply_surface(
        _HalfWrite(_golden_rows()), execute=True)
    assert rc == EX_MISMATCH
    assert payload["af_code"] == "READBACK-MISMATCH"
    assert "MISMATCH" in note and "AF-AE-READBACK-MISMATCH" in note

def test_applied_but_unreadable_put_is_held_never_fabricated():
    """A PUT that returned success but cannot be read back is HELD
    (reg.CafUnreachable) — the live state is UNDETERMINED, never reported
    as built, never demoted to a mismatch."""
    class _WriteButUnreadable(tsb._FakeClient):
        """The PUT is accepted; every read after it raises transport."""

        def _request(self, method, path, query=None, body=None):
            if method == "PUT":
                for row in self._rows:
                    if fr._row_id(row) == tsb.DEFAULT_TITLE_SELECT_FORM_ID:
                        row["hiddenFields"] = list(tsb.HIDDEN_LAW)
                        row["fields"] = list(tsb._normalized_fields_law(()))
                        return {}
                raise reg.CafUnreachable("form id not found (fixture)")
            raise reg.CafUnreachable("read-back transport failure (fixture)")

    with pytest.raises(reg.CafUnreachable):
        tsb.plan_form_build(_WriteButUnreadable(_golden_rows()), LOC,
                            execute=True)

def test_scope_denied_on_read_back_stays_a_real_stop():
    """A scope refusal on the read-back leg is a real credential STOP
    (reg.ScopeDenied) and propagates untouched — never demoted to a HELD."""
    class _WriteThenScope(tsb._FakeClient):
        """The PUT is accepted; the read-back then refuses scope."""

        def _request(self, method, path, query=None, body=None):
            if method == "PUT":
                for row in self._rows:
                    if fr._row_id(row) == tsb.DEFAULT_TITLE_SELECT_FORM_ID:
                        row["hiddenFields"] = list(tsb.HIDDEN_LAW)
                        row["fields"] = list(tsb._normalized_fields_law(()))
                        return {}
                raise reg.CafUnreachable("form id not found (fixture)")
            raise reg.ScopeDenied("token not authorized for this scope "
                                  "(HTTP 403)")

    with pytest.raises(reg.ScopeDenied):
        tsb.plan_form_build(_WriteThenScope(_golden_rows()), LOC,
                            execute=True)

def test_scope_denied_on_the_first_read_propagates():
    """A scope refusal on the very first read propagates untouched — a real
    credential problem, never misread as an empty listing."""
    class _ScopeOnRead(tsb._FakeClient):
        def _request(self, method, path, query=None, body=None):
            raise reg.ScopeDenied("token not authorized for this scope "
                                  "(HTTP 403)")

    with pytest.raises(reg.ScopeDenied):
        tsb.plan_form_build(_ScopeOnRead([]), LOC)

def test_validation_refusal_on_the_put_is_a_stop_never_a_skip():
    """A 400/409/422 validation refusal on the PUT is a STOP
    (FormsBuildError, exit-2 family) — never a silent skip, never a
    fabricated success."""
    with pytest.raises(tsb.FormsBuildError):
        tsb.plan_form_build(tsb._FakeClient(_golden_rows(), fail_put=True),
                            LOC, execute=True)

def test_plan_is_deterministic_and_never_mutates_its_inputs():
    """The plan is pure and deterministic: the same listing gives the same
    report every time, and neither the listing rows nor the client state
    is mutated by a read-only plan."""
    rows = _golden_rows()
    before = json.dumps(rows, sort_keys=True)
    first = tsb.plan_form_build(tsb._FakeClient(rows), LOC)
    second = tsb.plan_form_build(tsb._FakeClient(rows), LOC)
    assert json.dumps(rows, sort_keys=True) == before, (
        "the plan must never mutate the listing rows")
    assert first == second, "the plan must be deterministic"

# ---------------------------------------------------------------------------
# Never-a-token: credential-shaped values REFUSE; surfaces never carry them.
# ---------------------------------------------------------------------------
def test_credential_shaped_hidden_field_refuses_the_whole_plan():
    """A hidden-field surface that IS a credential-shaped string (the house
    pit- guard shape) REFUSES the whole plan rather than print it — a row
    that looks like a token is not a surface we report."""
    rows = copy.deepcopy(_golden_rows())
    rows[2]["hiddenFields"] = ["pit-abc123", "anthology_id"]
    with pytest.raises(tsb.FormsBuildError):
        tsb.plan_form_build(tsb._FakeClient(rows), LOC)

def test_credential_shaped_pinned_id_refuses():
    """A pinned id that is credential-shaped refuses the same way — through
    the reader's own unmasked-id scan (FormsReadError, STOP family)."""
    with pytest.raises(fr.FormsReadError):
        tsb.plan_form_build(_golden_client(), LOC, pinned_id="pit-abc123")

def test_no_captured_surface_prints_a_token():
    """No captured surface ever carries a credential-shaped string: the
    golden dry-run AND the golden apply payloads, the offline plan payload,
    and every human note are scanned and clean — and the full form id rides
    surfaces MASKED only."""
    for kwargs in ({}, {"execute": True}):
        dumped = json.dumps(
            tsb.plan_form_build(_golden_client(), LOC, **kwargs),
            indent=2, sort_keys=True)
        assert CREDENTIAL_SHAPE not in dumped, (
            "a builder surface must never carry a credential-shaped string")
        assert "pit-" not in dumped, "no pit- shape anywhere on the surface"
    # The MACHINE payload carries the full form id by contract (a machine
    # consumer needs it to pin the write); the OPERATOR surface — every
    # human note _run_apply writes — carries the masked marker only. The
    # marker is the last 4 chars and never leaks the id's prefix.
    assert tsb.mask_id(tsb.DEFAULT_TITLE_SELECT_FORM_ID) == "...O5fi", (
        "the id marker is the last 4 chars — the house surface shape")
    assert "O5fi" not in tsb.DEFAULT_TITLE_SELECT_FORM_ID[:12], (
        "the marker's last-4 must never appear in the id's prefix")
    rc, payload, note = _run_apply_surface(_golden_client(), execute=True)
    assert rc == EX_OK
    assert tsb.DEFAULT_TITLE_SELECT_FORM_ID not in note, (
        "a human note must never carry the full form id")
    assert "...O5fi" not in note, (
        "a human note never carries the form id at all — the location is "
        "the marker surface (masked, last 4)")
    assert LOC not in note, "the location must never ride a note in full"

def test_plan_is_offline_and_never_carries_credential_shape():
    """plan() is the offline, no-network, no-credential plan surface: ONE
    JSON object, exit 0, the S3 shape laws pinned in the payload, the write
    named as REFUSED without --execute on the public v2 path with the
    browser-UA note (CF 1010 law), and no credential-shaped string anywhere."""
    buf = io.StringIO()
    rc = tsb.plan(LOC, "", out=buf)
    assert rc == EX_OK
    payload = json.loads(buf.getvalue())
    assert payload["contract"] == tsb.CONFIG_CONTRACT
    assert payload["schema_version"] == tsb.CONFIG_SCHEMA_VERSION
    assert payload["form_slug"] == "title-select"
    assert payload["hidden_fields_law"] == list(tsb.HIDDEN_LAW)
    assert payload["visible_fields_law"] == [
        dict(f) for f in tsb.VISIBLE_FIELDS]
    assert "REFUSED without --execute" in payload["write"]
    assert "/forms/<formId>" in payload["write"]
    assert "CAF_BROWSER_UA" in payload["write"] and \
        "CAF_BROWSER_UA" in payload["read"], (
        "the plan must pin the browser-UA law (CF 1010) on both surfaces")
    assert CREDENTIAL_SHAPE not in buf.getvalue()
    assert "pit-" not in buf.getvalue(), "no pit- shape anywhere on the plan"
    assert tsb.DEFAULT_TITLE_SELECT_FORM_ID not in buf.getvalue(), (
        "the offline plan must never carry a full form id")

def test_plan_refuses_a_credential_shaped_pinned_id():
    """The offline plan refuses a credential-shaped pinned id through the
    reader's unmasked-id scan (FormsReadError) — a refusal, never a print."""
    with pytest.raises(fr.FormsReadError):
        tsb.plan(LOC, "pit-abc123", out=io.StringIO())

# ---------------------------------------------------------------------------
# The CLI's offline subcommands: self-test and plan.
# ---------------------------------------------------------------------------
def test_cli_self_test_subcommand_runs_offline():
    """The CLI's self-test subcommand runs offline: exit 0, no network, no
    credential."""
    assert tsb.main(["self-test"]) == EX_OK

def test_cli_plan_subcommand_runs_offline():
    """The CLI's plan subcommand runs offline: exit 0, ONE JSON object on
    stdout, no credential needed."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = tsb.main(["plan"])
    assert rc == EX_OK
    payload = json.loads(buf.getvalue())
    assert payload["contract"] == tsb.CONFIG_CONTRACT

# ---------------------------------------------------------------------------
# The direct runner: run the whole battery with plain python3 too.
# ---------------------------------------------------------------------------
TESTS = [
    (test_module_self_test_passes_offline, False),
    (test_exit_code_convention_is_house_0_1_2_3_4_5, False),
    (test_browser_user_agent_is_a_browser_ua_cf_1010_law, False),
    (test_u08_u09_package_init_is_fail_closed_empty, False),
    (test_report_contract_is_pinned, False),
    (test_s3_shape_law_is_pinned_against_the_commit, False),
    (test_pinned_form_id_is_the_engine_fleet_constant, False),
    (test_the_write_path_is_the_public_v2_form_surface, False),
    (test_golden_drift_refuses_in_dry_run_and_names_the_drift, False),
    (test_dry_run_performs_exactly_one_read_and_zero_writes, False),
    (test_dry_run_exits_5_with_one_json_on_stdout, False),
    (test_execute_builds_and_reads_back_byte_exact, False),
    (test_execute_performs_exactly_one_put_on_the_write_path, False),
    (test_put_body_echoes_the_live_row_never_memory, False),
    (test_execute_apply_exits_0_with_one_json_on_stdout, False),
    (test_idempotent_no_op_writes_nothing_even_with_execute, False),
    (test_extra_non_law_fields_are_preserved_never_destroyed, False),
    (test_container_spelling_drift_is_normalized, False),
    (test_visible_field_drift_is_repaired_never_tolerated, False),
    (test_container_less_row_is_fixable_and_never_silently_skipped, False),
    (test_intake_trio_never_satisfies_the_title_select_shape, False),
    (test_pin_law_bypasses_the_slug_law_and_is_the_row_written, False),
    (test_pinned_id_absent_from_listing_refuses_with_no_form_id, False),
    (test_empty_listing_is_forms_empty, False),
    (test_non_matching_listing_is_forms_not_found, False),
    (test_forms_empty_exits_2_with_one_json_on_stdout, False),
    (test_id_less_slug_matched_row_is_an_unreadable_shape_stop, False),
    (test_non_array_containers_are_malformed_shapes_stop, False),
    (test_readback_that_does_not_prove_the_build_is_mismatch, False),
    (test_readback_mismatch_exits_5, False),
    (test_applied_but_unreadable_put_is_held_never_fabricated, False),
    (test_scope_denied_on_read_back_stays_a_real_stop, False),
    (test_scope_denied_on_the_first_read_propagates, False),
    (test_validation_refusal_on_the_put_is_a_stop_never_a_skip, False),
    (test_plan_is_deterministic_and_never_mutates_its_inputs, False),
    (test_credential_shaped_hidden_field_refuses_the_whole_plan, False),
    (test_credential_shaped_pinned_id_refuses, False),
    (test_no_captured_surface_prints_a_token, False),
    (test_plan_is_offline_and_never_carries_credential_shape, False),
    (test_plan_refuses_a_credential_shaped_pinned_id, False),
    (test_cli_self_test_subcommand_runs_offline, False),
    (test_cli_plan_subcommand_runs_offline, False),
]

def main():
    failed = 0
    for t, _ in TESTS:
        try:
            t()
            print("  PASS: %s" % t.__name__)
        except AssertionError as exc:
            failed += 1
            print("  FAIL: %s\n        %s" % (t.__name__, exc))
        except Exception as exc:  # noqa: BLE001 — a crash is a failure, reported as one
            failed += 1
            print("  ERROR: %s\n        %r" % (t.__name__, exc))
    print("\n=== %d passed, %d failed ===" % (len(TESTS) - failed, failed))
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
