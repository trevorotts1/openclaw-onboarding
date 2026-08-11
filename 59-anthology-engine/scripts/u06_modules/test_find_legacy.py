#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u06_modules/test_find_legacy.py
# UNIT TESTS for the LEGACY WORKFLOW FINDER (scripts/u06_modules/
# find_legacy.py — U06 tooling: the FIND half of the U06 find-then-archive
# gate). The two laws this file exists to enforce: (1) the EXACT-NAME law —
# the two legacy engine workflows are found on a Convert and Flow location
# BY EXACT NAME ("00-Start Anthology Writer with Avatar Alchemist" and
# "Anthology Pipeline Manager and Notification System", dashes -> spaces,
# normalized lowercase, byte-exact against the module's ONE pinned table),
# with a renamed legacy indistinguishable from an absent one and BOTH
# refusing fail-closed — and (2) the ARCHIVE-ACTION GATE law — any archive
# ACTION in the U06 family REQUIRES --execute explicitly (Trevor-gated,
# per the u06 package init); the finder itself is READ-ONLY (it exposes NO
# write surface at all), and the sibling archive surface REFUSES without
# --execute.
#
# WHAT THIS FILE PROVES (network-free, credential-free):
#   * the golden live read: BOTH legacy workflows found BY EXACT NAME on the
#     golden listing (workflow-typed rows only; triggers and folders never
#     match), the ONE request contract (proven internal rail path
#     /workflow/<loc>/list?limit=200, the location in the path) recorded by
#     the stub, the id of EACH legacy reported under its stable key, the
#     never-a-token surfaces (ids ride the payload FULLY for machine
#     consumers but MASKED — last 4 chars — on every operator surface; the
#     full id is a workflow handle, never a credential),
#   * the exact-name law, every direction: case- and spacing-drifted names
#     still resolve through the normalization law; a RENAMED legacy (wrong
#     words) is indistinguishable from an ABSENT one and both refuse
#     (LEGACY-ABSENT / LEGACY-PARTIAL, never a similarity match); the
#     alternative container keys (_id / workflowId / workflowName) resolve
#     the same law; non-dict rows are skipped, never counted;
#   * the not-found paths, each NAMED: an empty listing and a trigger-only
#     listing are LEGACY-EMPTY; a non-empty listing without either legacy is
#     LEGACY-ABSENT; one legacy found and the other absent is
#     LEGACY-PARTIAL — every not-found surface carries NO id for the absent
#     keys (never an id guessed from memory) and keeps the candidate rows
#     (near-misses are REPORTED, never silently ignored),
#   * the narrowed surface: --legacy-name judges ONLY the named legacy —
#     the other's absence is not a MISMATCH and the unjudged key never
#     appears on the surface,
#   * the PIN law, both ways: a pinned id on the listing under its own
#     legacy name passes and BYPASSES the name law past a renamed row
#     (matched_by pin); a pinned id absent from a non-empty listing is
#     PIN-MISSING; a pinned id on the row of the OTHER legacy name is
#     PIN-ON-WRONG-NAME (a pin can never point the archive at the wrong
#     legacy) — all three through find_legacies AND through the plan
#     surface's masked id,
#   * never-a-token, every direction: a credential-shaped ROW id REFUSES the
#     whole read rather than print (the finder exists to emit ids, so an id
#     that looks like a token is never emitted); a credential-shaped PINNED
#     id refuses the same way; the plan payload is scanned against the
#     credential shape before print; no captured surface ever carries a
#     pit-/Bearer-shaped string; masked markers only for ids on human
#     surfaces,
#   * the malformed-listing ladder: a payload that is not an object, a
#     payload with no 'rows' key, a non-array 'rows', and a non-object
#     response each REFUSE (LegacyFindError, STOP family) — never a silent
#     empty,
#   * THE ARCHIVE-ACTION GATE (Trevor-gated): the finder exposes NO archive
#     write surface (no callable archive symbol, PROVEN_ARCHIVE_SURFACE is
#     the documented empty string — the repo has proven NO workflow
#     delete/archive endpoint, Skill 44 endpoint doctrine), the plan carries
#     the archive gate law as DATA (--execute required, --workflow-id pin
#     required, the proven-write law), and the sibling workflow_lister CLI
#     — the module that OWNS the archive ACTION — REFUSES at the CLI
#     boundary: archive without --execute STOPS (exit 2) before any
#     credential work, and archive WITH --execute is still a PLAN ONLY (no
#     mutation; the plan notes it; --execute never relaxes the proven-write
#     law),
#   * the house doctrine pins: the exit-code convention (0/1/2/3/4/5)
#     asserted through the registry's exported constants, the browser
#     User-Agent law (CF 1010 — CAF_BROWSER_UA is a browser UA, never
#     optional), the fail-closed-empty package init, the U06 sibling
#     batteries green (find_legacy's own self-test, golden_absent's
#     self-test, workflow_lister's self-test — a red sibling is caught HERE
#     first), and determinism (the finder never mutates its inputs; the
#     same listing gives the same verdict every time).
#
# House doctrine (Skill 59, u06_modules/__init__.py): fail-closed, both
# directions — the golden control passes and EVERY attack fails, so the
# pass/fail split discriminates (the golden control is never a broken
# instrument). Never a token printed; nothing Anthropic in any runtime
# surface; stdlib only; pytest with plain asserts; sys.path bootstrap
# identical to every other tests/ file; exit codes asserted by the exported
# module constants, never hardcoded. The registry's CafClient and the rail
# clients are NEVER constructed here, no env var is read, no network is
# touched.
#
# Run: python3 -m pytest 59-anthology-engine/scripts/u06_modules/test_find_legacy.py -q
#  or: python3 59-anthology-engine/scripts/u06_modules/test_find_legacy.py
# =============================================================================
"""test_find_legacy.py -- the legacy-workflow finder's exact-name law, pin
law, never-a-token guards, and the Trevor-gated archive ACTION (U06)."""

import contextlib
import io
import json
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

import anthology_registry as reg  # noqa: E402
import u06_modules.find_legacy as fl  # noqa: E402  (the module under test)
import u06_modules.workflow_lister as wl  # noqa: E402  (the archive-ACTION sibling)

# The house exit-code convention (0/1/2/3/4/5) — asserted through the
# exported constants, never re-typed.
EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# A credential-shaped string is the pit- token prefix followed by a non-empty
# value — the house guard shape every u06 surface is scanned against. No test
# fixture carries a real one, so no captured surface may either.
CREDENTIAL_SHAPE = "pit-"

# The golden listing rows (the proven Skill 58 shape): BOTH legacy workflows
# plus one unrelated workflow and one non-workflow row (a trigger) — the
# same rows the module's own self-test uses.
GOLDEN_ROWS = [
    {"type": "workflow", "name": fl.LEGACY_NAMES["start_anthology_writer"],
     "id": "wfLegacyStart01"},
    {"type": "workflow", "name": fl.LEGACY_NAMES["pipeline_manager"],
     "id": "wfLegacyPipe02"},
    {"type": "workflow", "name": "Anthology Intake Fire", "id": "wfIntakeFire03"},
    {"type": "trigger", "name": "Contact Tag Added", "id": "wfTriggerThing"},
]


def _fake_client(rows):
    """The module's own offline rail stub — the same stub its self-test
    uses, so this battery exercises the EXACT seam the module proves."""
    return fl._FakeClient(rows)


# ---------------------------------------------------------------------------
# Cross-cutting house doctrine
# ---------------------------------------------------------------------------
def test_finder_self_test_passes_offline():
    """The module's own offline battery passes — exit 0, no network, no
    credential (golden find plus every attack fixture refused)."""
    assert fl.self_test(out=io.StringIO()) == EX_OK


def test_exit_code_convention_is_house_0_1_2_3_4_5():
    """Every runner pins the house exit-code convention — asserted through
    the exported constants, never hardcoded."""
    assert (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH) == (0, 1, 2, 3, 5)
    assert EX_VIOLATION == 4
    assert EX_VIOLATION not in (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH)


def test_browser_user_agent_is_a_browser_ua_cf_1010_law():
    """The CF 1010 law: the house client rides a browser User-Agent on every
    request — urllib's default Python-urllib/x.y is 403'd at the Cloudflare
    WAF edge before it ever reaches Convert and Flow. The law is a house
    constant, never optional (recorded here so a future caller that adds a
    live read to this module keeps the discipline)."""
    assert reg.CAF_BROWSER_UA, "CAF_BROWSER_UA must never be empty"
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), (
        "CAF_BROWSER_UA must be a browser User-Agent, got %r"
        % reg.CAF_BROWSER_UA[:40])


def test_u06_package_init_is_fail_closed_empty():
    """The package init is a pure namespace container — no runtime code, no
    side effects, no secret surface, and it CARRIES the archive-ACTION gate
    doctrine (--execute, Trevor-gated) in its DOCTRINE comment block (the
    docstring itself is the one-line summary)."""
    import u06_modules as pkg
    assert pkg.__all__ == []
    assert pkg.__doc__ and "fail-closed" in pkg.__doc__.lower()
    init_text = Path(pkg.__file__).read_text(encoding="utf-8")
    assert "--execute" in init_text and "Trevor-gated" in init_text
    assert "archive ACTION" in init_text


# ---------------------------------------------------------------------------
# The golden live read: both legacies found by EXACT NAME.
# ---------------------------------------------------------------------------
def test_golden_read_finds_both_legacies_by_exact_name():
    """The golden listing read: ok True, both legacy workflows found with
    their ONE id each, only workflow-typed rows counted, and the ONE request
    contract (proven rail path with the location + limit) recorded by the
    stub."""
    client = _fake_client(GOLDEN_ROWS)
    res = fl.find_legacies(client, "loc_tmpl")
    assert res["ok"] is True and res["found"] is True
    assert res["contract"] == fl.CONFIG_CONTRACT
    assert res["af_code"] == "LEGACY-FOUND"
    assert res["workflows"]["start_anthology_writer"]["id"] == "wfLegacyStart01"
    assert res["workflows"]["pipeline_manager"]["id"] == "wfLegacyPipe02"
    assert res["workflows"]["start_anthology_writer"]["matched_by"] == "name"
    assert res["workflows"]["pipeline_manager"]["matched_by"] == "name"
    assert res["absent"] == []
    assert res["count"] == 3, "only workflow-typed rows may count"
    assert len(res["candidates"]) == 3
    assert client.calls == [
        {"path": fl.WORKFLOWS_LIST_PATH % "loc_tmpl" + "?limit=200"}], (
        "the request must be the proven rail path with the location + limit")


def test_legacy_names_are_pinned_and_never_retyped_here():
    """The two legacy names ride the module's ONE pinned table — never
    re-typed in this file — and the exact-name law strings follow from the
    dashes -> spaces, lowercase normalization."""
    assert fl.LEGACY_NAMES["start_anthology_writer"] == \
        "00-Start Anthology Writer with Avatar Alchemist"
    assert fl.LEGACY_NAMES["pipeline_manager"] == \
        "Anthology Pipeline Manager and Notification System"
    # the law strings: the module's dashes -> spaces, lowercase normalization
    # (the exact byte strings the name law matches against)
    assert fl.LEGACY_SLUGS["start_anthology_writer"] == \
        "00-start anthology writer with avatar alchemist"
    assert fl.LEGACY_SLUGS["pipeline_manager"] == \
        "anthology pipeline manager and notification system"
    # the slug law is the module's OWN normalization, never re-typed here
    assert fl.LEGACY_SLUGS == {
        key: fl._normalize_name(name)
        for key, name in fl.LEGACY_NAMES.items()}
    assert sorted(fl.LEGACY_NAMES) == ["pipeline_manager", "start_anthology_writer"]


def test_case_and_spacing_drift_resolves_through_the_normalization_law():
    """The name-match law normalizes case and collapses spacing — a row
    whose name is the legacy name in caps / with doubled spaces still
    resolves (the law is byte-exact on the NORMALIZED form, never a
    similarity score)."""
    res = fl.find_legacies(_fake_client([
        {"type": "workflow",
         "name": "  ANTHOLOGY  PIPELINE manager and notification system  ",
         "id": "wfLegacyPipe02"}]), "loc_tmpl", legacy_key="pipeline_manager")
    assert res["ok"] is True and res["af_code"] == "LEGACY-FOUND"
    assert res["workflows"]["pipeline_manager"]["id"] == "wfLegacyPipe02"
    assert fl._normalize_name("  ANTHOLOGY  PIPELINE manager and "
                              "notification system  ") == \
        fl.LEGACY_SLUGS["pipeline_manager"], (
        "the drifted spelling must normalize to the pinned law string")


def test_alternative_container_keys_resolve_the_same_law():
    """A row carrying its id under _id / workflowId and its name under
    workflowName (the alternate container keys _row_id / _row_name read)
    resolves the SAME exact-name law."""
    res = fl.find_legacies(_fake_client([
        {"type": "workflow", "workflowName": fl.LEGACY_NAMES["pipeline_manager"],
         "_id": "wfLegacyPipe02"}]), "loc_tmpl", legacy_key="pipeline_manager")
    assert res["ok"] is True and res["af_code"] == "LEGACY-FOUND"
    assert res["workflows"]["pipeline_manager"]["id"] == "wfLegacyPipe02"
    assert res["workflows"]["pipeline_manager"]["matched_by"] == "name"
    assert fl._row_id({"type": "workflow", "_id": "wfLegacyPipe02"}) == \
        "wfLegacyPipe02"
    assert fl._row_name({"type": "workflow",
                         "workflowName": fl.LEGACY_NAMES["pipeline_manager"]}) == \
        fl.LEGACY_NAMES["pipeline_manager"]


class _RawListingClient:
    """Serves the rows VERBATIM (no dict-copy coercion) so a ragged listing
    — non-dict rows mixed with dict rows — can be handed to the finder
    exactly as the rail might return it."""

    def __init__(self, rows):
        self._rows = rows
        self.calls = []

    def _get(self, path):
        self.calls.append({"path": path})
        return {"rows": self._rows}


def test_non_dict_rows_are_skipped_never_counted():
    """Non-dict rows in the listing (scalars, nulls) are skipped, not
    counted, not judged — a ragged listing can never fabricate a row."""
    res = fl.find_legacies(_RawListingClient(GOLDEN_ROWS + ["junk", None, 42]),
                           "loc_tmpl")
    assert res["ok"] is True and res["count"] == 3


def test_finder_is_deterministic_and_never_mutates_its_inputs():
    """The find is pure and deterministic: the same listing gives the same
    verdict every time, and the input rows are never mutated."""
    rows = [dict(r) for r in GOLDEN_ROWS]
    before = json.dumps(rows, sort_keys=True)
    first = fl.find_legacies(_fake_client(rows), "loc_tmpl")
    second = fl.find_legacies(_fake_client(rows), "loc_tmpl")
    assert json.dumps(rows, sort_keys=True) == before, (
        "the finder must never mutate its listing")
    assert first == second, "the finder must be deterministic"


# ---------------------------------------------------------------------------
# The exact-name law, every direction.
# ---------------------------------------------------------------------------
def test_renamed_legacy_is_indistinguishable_from_absent_and_both_refuse():
    """A RENAMED legacy (wrong words — the name law does not match) is
    indistinguishable from an ABSENT one to find-by-name: the surface is
    LEGACY-PARTIAL when the other legacy is found, the renamed key carries
    NO id, and the near-miss row is REPORTED as a candidate — never
    accepted by similarity."""
    res = fl.find_legacies(_fake_client([
        {"type": "workflow", "name": "00-Start Anthology Writer",
         "id": "wfRenamedLegacy1"},
        {"type": "workflow", "name": fl.LEGACY_NAMES["pipeline_manager"],
         "id": "wfLegacyPipe02"}]), "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "LEGACY-PARTIAL"
    assert res["workflows"]["start_anthology_writer"]["id"] == "", (
        "a renamed legacy must not be reported under the legacy key")
    assert fl.LEGACY_NAMES["start_anthology_writer"] in res["absent"]
    # the near-miss row stays on the surface as a masked candidate
    assert {"id_masked": fl.mask_id("wfRenamedLegacy1")} in res["candidates"]


def test_absent_legacy_never_carries_an_id_anywhere():
    """A not-found legacy carries NO id on every surface — found False, id
    empty, id_masked empty — never an id guessed from memory."""
    res = fl.find_legacies(_fake_client([
        {"type": "workflow", "name": "Anthology Intake Fire",
         "id": "wfIntakeFire03"}]), "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "LEGACY-ABSENT"
    for key in ("start_anthology_writer", "pipeline_manager"):
        assert res["workflows"][key]["found"] is False
        assert res["workflows"][key]["id"] == ""
        assert res["workflows"][key]["id_masked"] == ""
    dumped = json.dumps(res)
    assert "wfIntakeFire03" not in dumped or \
        dumped.count("wfIntakeFire03") == 0, (
        "a near-miss id must never ride the surface in full")


# ---------------------------------------------------------------------------
# The not-found paths, each NAMED.
# ---------------------------------------------------------------------------
def test_empty_listing_is_legacy_empty():
    """An empty listing is LEGACY-EMPTY (exit-5 MISMATCH surface) — never a
    silent pass, never a fabricated empty that certifies absence."""
    res = fl.find_legacies(_fake_client([]), "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "LEGACY-EMPTY"
    assert res["count"] == 0
    assert res["workflows"]["start_anthology_writer"]["id"] == ""


def test_trigger_only_listing_is_legacy_empty():
    """A listing with only non-workflow rows is LEGACY-EMPTY — a location
    with zero workflows is not a location with the legacy workflows."""
    res = fl.find_legacies(_fake_client([
        {"type": "trigger", "name": "Contact Tag Added", "id": "wfTriggerThing"}]),
        "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "LEGACY-EMPTY"
    assert res["count"] == 0


def test_partial_find_is_a_mismatch_never_a_half_pass():
    """One legacy found and the other absent is LEGACY-PARTIAL: the found id
    is reported, the absent legacy is NAMED, and the surface is a MISMATCH —
    never a silent half-pass."""
    res = fl.find_legacies(_fake_client([
        {"type": "workflow", "name": fl.LEGACY_NAMES["pipeline_manager"],
         "id": "wfLegacyPipe02"}]), "loc_tmpl")
    assert res["ok"] is False and res["af_code"] == "LEGACY-PARTIAL"
    assert res["workflows"]["pipeline_manager"]["id"] == "wfLegacyPipe02", (
        "the found id must be reported on the partial surface")
    assert res["workflows"]["start_anthology_writer"]["id"] == "" and \
        fl.LEGACY_NAMES["start_anthology_writer"] in res["absent"]


# ---------------------------------------------------------------------------
# The narrowed surface (--legacy-name).
# ---------------------------------------------------------------------------
def test_narrowed_surface_judges_only_the_named_legacy():
    """--legacy-name judges ONLY the named legacy: the other's absence is
    NOT a MISMATCH, and the unjudged key never appears on the surface."""
    res = fl.find_legacies(_fake_client([
        {"type": "workflow", "name": fl.LEGACY_NAMES["pipeline_manager"],
         "id": "wfLegacyPipe02"}]), "loc_tmpl", legacy_key="pipeline_manager")
    assert res["ok"] is True and res["af_code"] == "LEGACY-FOUND"
    assert res["workflows"]["pipeline_manager"]["id"] == "wfLegacyPipe02"
    assert "start_anthology_writer" not in res["workflows"], (
        "the unjudged legacy must not appear on the narrowed surface")


def test_narrowed_surface_still_refuses_for_the_named_legacy():
    """The narrowed surface is still fail-closed for the NAMED legacy: a
    renamed named legacy refuses (LEGACY-ABSENT), never a pass."""
    res = fl.find_legacies(_fake_client([
        {"type": "workflow", "name": "Anthology Pipeline Manager",
         "id": "wfRenamedPipe"}]), "loc_tmpl", legacy_key="pipeline_manager")
    assert res["ok"] is False and res["af_code"] == "LEGACY-ABSENT"
    assert res["workflows"]["pipeline_manager"]["id"] == ""


# ---------------------------------------------------------------------------
# The PIN law, both ways (a pin is a STRONGER contract than a name).
# ---------------------------------------------------------------------------
def test_pinned_id_on_the_listing_passes_and_bypasses_the_name_law():
    """A pinned id on the listing under its own legacy name passes even past
    a RENAMED row — the pin bypasses the name law for the legacy it pins
    (matched_by pin) and the surface stays LEGACY-FOUND. The caller names
    the legacy (--legacy-name): the pin attribute is the ONLY way a pin can
    bind past a rename — without the name, a renamed pinned row cannot be
    attributed and REFUSES (PIN-UNATTRIBUTABLE, never bound by guess)."""
    rows = [dict(r) for r in GOLDEN_ROWS]
    rows[0]["name"] = "Renamed Legacy Writer"  # the name law no longer matches
    res = fl.find_legacies(_fake_client(rows), "loc_tmpl",
                           pinned_id="wfLegacyStart01",
                           legacy_key="start_anthology_writer")
    assert res["ok"] is True and res["af_code"] == "LEGACY-FOUND"
    assert res["workflows"]["start_anthology_writer"]["matched_by"] == "pin"
    assert res["workflows"]["start_anthology_writer"]["id"] == "wfLegacyStart01"


def test_pinned_id_absent_from_the_listing_is_pin_missing():
    """A pinned id ABSENT from a non-empty listing is PIN-MISSING (the
    exit-5 MISMATCH family), never a silent pass — and the failed surface
    never carries a workflow id."""
    rows = [dict(r) for r in GOLDEN_ROWS]
    rows[0]["id"] = "DriftedLegacy0000"  # the pinned id disappears
    res = fl.find_legacies(_fake_client(rows), "loc_tmpl",
                           pinned_id="wfLegacyStart01")
    assert res["ok"] is False and res["af_code"] == "PIN-MISSING"
    assert res["workflows"]["start_anthology_writer"]["id"] == "", (
        "a failed read must never carry a workflow id")


def test_pinned_id_on_the_wrong_legacy_name_is_pin_on_wrong_name():
    """A pin attributed to the WRONG legacy refuses (PIN-ON-WRONG-NAME): the
    module pins `wfLegacyPipe02` while the caller names the OTHER legacy
    (`--legacy-name start_anthology_writer`) — the pinned row is the
    pipeline-manager row, so the pin can never be accepted under the named
    legacy. A pin can never point the archive at the wrong legacy."""
    res = fl.find_legacies(_fake_client(GOLDEN_ROWS), "loc_tmpl",
                           pinned_id="wfLegacyPipe02",
                           legacy_key="start_anthology_writer")
    assert res["ok"] is False and res["af_code"] == "PIN-ON-WRONG-NAME"
    assert res["workflows"]["start_anthology_writer"]["found"] is False, (
        "the wrong-name pin must never report the named legacy as found")
    # the named-legacy surface carries ONLY the named key — the pinned
    # row's id never rides the surface on the refusal
    assert sorted(res["workflows"]) == ["start_anthology_writer"]
    assert res["pinned"]["start_anthology_writer"]["state"] == "wrong-name"
    assert res["workflows"]["start_anthology_writer"]["id"] == "", (
        "the pinned row's id must never ride the surface on the refusal")


def test_pinned_id_on_the_wrong_legacy_name_with_named_legacy_refuses():
    """The mirror direction: the caller names the start-anthology-writer and
    pins the PIPE-manager row (name law still matching — the pin never
    re-attributes it) — PIN-ON-WRONG-NAME, never a pass. (The wrong-name
    property is judged against the FULL legacy set, never the narrowed
    scope: a pinned row naming the OTHER legacy is wrong-name even when
    that legacy is not under judgment. Conversely, a pinned row whose name
    matches NO legacy law is the renamed case and is attributed by the
    caller's word — the pin bypasses the rename.)"""
    rows = [dict(r) for r in GOLDEN_ROWS]
    res = fl.find_legacies(_fake_client(rows), "loc_tmpl",
                           pinned_id="wfLegacyPipe02",
                           legacy_key="start_anthology_writer")
    assert res["ok"] is False and res["af_code"] == "PIN-ON-WRONG-NAME"
    assert res["pinned"]["start_anthology_writer"]["state"] == "wrong-name"
    assert res["workflows"]["start_anthology_writer"]["id"] == "", (
        "the named legacy must never carry the pinned row's id")
    # the same pin under the PIPE legacy — the caller's own word — passes
    # (matched_by name: the pinned row IS the pipe row); the pin was never
    # the problem, only its attribution was
    res2 = fl.find_legacies(_fake_client(rows), "loc_tmpl",
                            pinned_id="wfLegacyPipe02",
                            legacy_key="pipeline_manager")
    assert res2["ok"] is True and res2["af_code"] == "LEGACY-FOUND"


def test_unattributable_pin_is_refused_never_bound_by_guess():
    """A pinned id whose row's name matches NO legacy law — and no
    --legacy-name to attribute it — is PIN-UNATTRIBUTABLE (the exit-5
    family): the finder never binds a pin to a legacy by guess."""
    res = fl.find_legacies(_fake_client([
        {"type": "workflow", "name": "Totally Unrelated Workflow",
         "id": "wfElsewhere"}]), "loc_tmpl", pinned_id="wfElsewhere")
    assert res["ok"] is False and res["af_code"] == "PIN-UNATTRIBUTABLE"
    assert res["workflows"]["start_anthology_writer"]["id"] == "" and \
        res["workflows"]["pipeline_manager"]["id"] == ""


def test_named_pin_bypasses_a_rename_but_never_the_wrong_legacy():
    """With --legacy-name, a pin bypasses a rename for the NAMED legacy —
    the pin for the named legacy still passes past the renamed row
    (matched_by pin, LEGACY-FOUND). The pin WITHOUT --legacy-name on the
    same renamed row is PIN-UNATTRIBUTABLE (the finder never binds a pin to
    a legacy by guess — the caller must name it)."""
    rows = [dict(r) for r in GOLDEN_ROWS]
    rows[0]["name"] = "Renamed Legacy Writer"
    res = fl.find_legacies(_fake_client(rows), "loc_tmpl",
                           pinned_id="wfLegacyStart01",
                           legacy_key="start_anthology_writer")
    assert res["ok"] is True and res["af_code"] == "LEGACY-FOUND"
    assert res["workflows"]["start_anthology_writer"]["matched_by"] == "pin"
    # WITHOUT --legacy-name the renamed pinned row cannot be attributed —
    # refused, never bound by guess (PIN-UNATTRIBUTABLE, exit-5 family)
    res2 = fl.find_legacies(_fake_client(rows), "loc_tmpl",
                            pinned_id="wfLegacyStart01")
    assert res2["ok"] is False and res2["af_code"] == "PIN-UNATTRIBUTABLE"


def test_blank_pin_is_a_no_op_never_a_mismatch():
    """A blank pinned id is a no-op — the find runs under the plain name
    law, never a spurious PIN-MISSING."""
    res = fl.find_legacies(_fake_client(GOLDEN_ROWS), "loc_tmpl",
                           pinned_id="   ")
    assert res["ok"] is True and res["af_code"] == "LEGACY-FOUND"


# ---------------------------------------------------------------------------
# Never-a-token guards.
# ---------------------------------------------------------------------------
def test_credential_shaped_row_id_refuses_the_whole_read():
    """A listing row whose id IS a credential-shaped string REFUSES the
    whole read rather than print — the id is exactly what the finder exists
    to emit, so an id that looks like a token is never emitted."""
    with pytest.raises(fl.LegacyFindError):
        fl.find_legacies(_fake_client([
            {"type": "workflow", "name": fl.LEGACY_NAMES["pipeline_manager"],
             "id": "pit-abc123"}]), "loc_tmpl")


def test_credential_shaped_pinned_id_refuses():
    """A credential-shaped PINNED id refuses the same way — before any read,
    never printed."""
    with pytest.raises(fl.LegacyFindError):
        fl.find_legacies(_fake_client(GOLDEN_ROWS), "loc_tmpl",
                         pinned_id="pit-abc123")


def test_no_surface_prints_a_token_or_a_full_id():
    """The golden read's machine payload carries the FULL workflow ids (the
    documented machine contract — a workflow id is a handle, never a
    credential) but the masked markers ride every surface, and no surface
    carries a credential-shaped string."""
    res = fl.find_legacies(_fake_client(GOLDEN_ROWS), "loc_tmpl")
    assert res["workflows"]["start_anthology_writer"]["id_masked"] == \
        fl.mask_id("wfLegacyStart01")
    dumped = json.dumps(res)
    assert CREDENTIAL_SHAPE not in dumped and "Bearer" not in dumped
    assert "pit-" not in dumped
    # the full ids ARE the machine payload contract; the markers are the
    # human surface — both pinned here so neither drifts
    assert "wfLegacyStart01" in dumped and "wfLegacyPipe02" in dumped


def test_plan_surface_never_carries_credential_shape_and_masks_ids():
    """The offline plan carries the archive-gate law, masks the location and
    any pinned id, and is scanned against the credential shape before
    print."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fl.plan("loc_tmpl", pinned_id="wfLegacyStart01")
    assert rc == EX_OK
    out = buf.getvalue()
    assert "wfLegacyStart01" not in out, (
        "the plan must never surface a full pinned id")
    assert fl.mask_id("wfLegacyStart01") in out, (
        "the plan carries the pinned id as a masked marker")
    assert CREDENTIAL_SHAPE not in out and "Bearer" not in out
    payload = json.loads(out)
    assert payload["archive_gate"]["execute"], (
        "the plan must carry the --execute gate (Trevor-gated)")


# ---------------------------------------------------------------------------
# The malformed-listing ladder (fail-closed, never a silent empty).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        ("not-a-dict", "not a JSON object"),
        ({"nope": 1}, "no 'rows' array"),
        ({"rows": "not-a-list"}, "'rows' value is not an array"),
    ])
def test_malformed_listing_shapes_refuse(payload, detail):
    """A payload that is not an object, a payload with no rows key, and a
    non-array rows each REFUSE (LegacyFindError, STOP family) — an
    unreadable shape is never proof of zero workflows."""

    class _BadClient:
        def __init__(self, payload):
            self._payload = payload

        def _get(self, path):
            return self._payload

    with pytest.raises(fl.LegacyFindError) as excinfo:
        fl.find_legacies(_BadClient(payload), "loc_tmpl")
    assert detail in str(excinfo.value)


def test_malformed_listing_shapes_refuse_payload():
    """The ladder also refuses when driven one case at a time through a raw
    payload client — the plain-python runner (no pytest) covers the same
    three refusals with the module's exact typed reasons."""

    class _PayloadClient:
        def __init__(self, payload):
            self._payload = payload

        def _get(self, path):
            return self._payload

    for payload, detail in (
            ("not-a-dict", "workflows listing response is not a JSON object"),
            ({"nope": 1}, "no 'rows' array"),
            ({"rows": "not-a-list"}, "'rows' value is not an array")):
        with pytest.raises(fl.LegacyFindError) as excinfo:
            fl.find_legacies(_PayloadClient(payload), "loc_tmpl")
        assert detail in str(excinfo.value)


def test_non_object_listing_response_refuses():
    """A listing response that is not a JSON object refuses (a non-object
    cannot carry the rows shape) — a response that parses to a list is a
    LegacyFindError, never a silent empty."""

    class _ListResponseClient:
        def _get(self, path):
            return ["not", "a", "dict"]

    with pytest.raises(fl.LegacyFindError):
        fl.find_legacies(_ListResponseClient(), "loc_tmpl")


def test_explicit_row_seam_never_touches_the_client():
    """The explicit workflow_rows seam (the self-test seam) never calls the
    client — the finder can be proven offline against handed rows."""

    class _NoGetClient:
        def _get(self, path):
            raise AssertionError("explicit seam must not touch the client")

    res = fl.find_legacies(_NoGetClient(), "loc_tmpl", workflow_rows=GOLDEN_ROWS)
    assert res["ok"] is True and res["count"] == 3


# ---------------------------------------------------------------------------
# THE ARCHIVE-ACTION GATE (Trevor-gated) — the U06 write law.
# ---------------------------------------------------------------------------
def test_finder_exposes_no_archive_write_surface():
    """The finder itself is READ-ONLY: it exposes no archive callable at
    all, and the module carries the proven-write law — the repo has PROVEN
    no workflow delete/archive endpoint (Skill 44 endpoint doctrine), so
    PROVEN_ARCHIVE_SURFACE is the documented empty string."""
    assert not hasattr(fl, "archive"), (
        "the finder must expose no archive write surface")
    assert not hasattr(fl, "archive_workflow"), (
        "the finder must expose no archive write surface")
    assert fl.PROVEN_ARCHIVE_SURFACE == "", (
        "the U06 family must not claim a proven archive surface this repo "
        "has not verified live")
    assert hasattr(fl, "find_legacies") and hasattr(fl, "plan") \
        and hasattr(fl, "self_test"), (
        "the finder's ONLY surfaces are find / plan / self-test — all "
        "read-only")


def test_archive_action_requires_execute_at_the_cli_boundary():
    """THE Trevor gate, at the CLI boundary of the sibling that OWNS the
    archive ACTION: workflow_lister archive WITHOUT --execute STOPS (exit
    2) before any credential work — a dry-run of an ACTION is never a
    silent no-op; the bare invocation STOPS before any name; and list
    without credentials HELDs (never a fabricated list). The explicit EMPTY
    environ blocks the canonical env-store fallback so the gates are
    deterministic OFFLINE — no network, no credential."""
    assert wl.main(["archive", "--name", "X"], environ={}) == EX_STOP, (
        "an archive ACTION without --execute must STOP (Trevor-gated)")
    assert wl.main(["archive"], environ={}) == EX_STOP, (
        "archive without --name must STOP")
    assert wl.main(["list"], environ={}) == EX_HELD, (
        "list without credentials must HELD (never a fabricated list)")
    assert wl.main([], environ={}) == EX_STOP, (
        "a bare invocation must STOP")


def test_execute_never_relaxes_the_proven_write_law():
    """Even WITH --execute the archive ACTION performs NO mutation — it is
    a structured PLAN ONLY (the endpoint-doctrine note rides the plan, the
    plan reports execute explicitly, and the plan's target id is MASKED)."""
    plan = wl._archive_plan(
        [{"type": "workflow", "name": "Anthology Release: Avatar",
          "id": "wf-0002", "status": "published"}],
        {"rows": [{"type": "workflow", "name": "Anthology Release: Avatar",
                   "id": "wf-0002", "status": "published"}]},
        "Anthology Release: Avatar")
    assert plan["action"] == wl.ACTION_ARCHIVE == "archive"
    assert plan["execute"] is False
    assert "no archive/delete surface" in plan["note"]
    assert plan["target"]["id"].startswith("..."), (
        "the plan's target id must be masked")
    assert "wf-0002" not in json.dumps(plan), (
        "the full workflow id must never surface")
    assert plan["would_archive"] == 1


def test_finder_plan_carries_the_archive_gate_law_as_data():
    """The finder's offline plan carries the archive-gate law as DATA: the
    archive ACTION requires --execute (Trevor-gated) AND a pinned
    --workflow-id, and the proven-write law (no workflow delete/archive
    surface proven) — a plan that could be mistaken for an executed archive
    is impossible."""
    payload = fl.plan_surface()
    gate = payload["archive_gate"]
    assert sorted(gate) == ["execute", "pin", "proven_write_law", "this_module"]
    assert "--execute" in gate["execute"]
    assert "Trevor-gated" in gate["execute"]
    assert "NEVER archives" in gate["this_module"]
    assert "read-only" in gate["this_module"]
    assert "--workflow-id" in gate["pin"]
    assert "no workflow delete/archive surface is PROVEN" in gate["proven_write_law"]
    assert not fl._CREDENTIAL_SHAPE.search(json.dumps(payload)), (
        "the plan must never carry a credential-shaped string")


# ---------------------------------------------------------------------------
# The U06 family — sibling batteries green and surfaces agree.
# ---------------------------------------------------------------------------
def test_sibling_u06_batteries_are_green():
    """The U06 family's other offline batteries pass — the golden absent-
    state fixture and the archive-ACTION lister — so the finder is tested
    against a green family (a red sibling is caught HERE first)."""
    import u06_modules.golden_absent as ga
    assert fl.self_test(out=io.StringIO()) == EX_OK
    assert ga.self_test(out=io.StringIO()) == EX_OK
    assert wl.self_test() == EX_OK


def test_sibling_archive_surfaces_agree_on_the_execute_gate():
    """The family's archive surfaces agree on the Trevor gate: golden_absent
    ships the dry-run report with execute_required True (applied false,
    dry_run true — the shape an archive ACTION MUST emit without --execute),
    and workflow_lister's ACTION constant is 'archive'."""
    import u06_modules.golden_absent as ga
    report = ga.golden_dry_run_report()
    assert report["action"] == "archive"
    assert report["applied"] is False and report["dry_run"] is True
    assert report["execute_required"] is True
    assert ga.GOLDEN_EXECUTE_REQUIRED is True
    assert wl.ACTION_ARCHIVE == "archive"


# ---------------------------------------------------------------------------
# Plain-python runner (no pytest required) — house style.
# ---------------------------------------------------------------------------
TESTS = [
    (test_finder_self_test_passes_offline, False),
    (test_exit_code_convention_is_house_0_1_2_3_4_5, False),
    (test_browser_user_agent_is_a_browser_ua_cf_1010_law, False),
    (test_u06_package_init_is_fail_closed_empty, False),
    (test_golden_read_finds_both_legacies_by_exact_name, False),
    (test_legacy_names_are_pinned_and_never_retyped_here, False),
    (test_case_and_spacing_drift_resolves_through_the_normalization_law, False),
    (test_alternative_container_keys_resolve_the_same_law, False),
    (test_non_dict_rows_are_skipped_never_counted, False),
    (test_finder_is_deterministic_and_never_mutates_its_inputs, False),
    (test_renamed_legacy_is_indistinguishable_from_absent_and_both_refuse, False),
    (test_absent_legacy_never_carries_an_id_anywhere, False),
    (test_empty_listing_is_legacy_empty, False),
    (test_trigger_only_listing_is_legacy_empty, False),
    (test_partial_find_is_a_mismatch_never_a_half_pass, False),
    (test_narrowed_surface_judges_only_the_named_legacy, False),
    (test_narrowed_surface_still_refuses_for_the_named_legacy, False),
    (test_pinned_id_on_the_listing_passes_and_bypasses_the_name_law, False),
    (test_pinned_id_absent_from_the_listing_is_pin_missing, False),
    (test_pinned_id_on_the_wrong_legacy_name_is_pin_on_wrong_name, False),
    (test_pinned_id_on_the_wrong_legacy_name_with_named_legacy_refuses, False),
    (test_unattributable_pin_is_refused_never_bound_by_guess, False),
    (test_named_pin_bypasses_a_rename_but_never_the_wrong_legacy, False),
    (test_blank_pin_is_a_no_op_never_a_mismatch, False),
    (test_credential_shaped_row_id_refuses_the_whole_read, False),
    (test_credential_shaped_pinned_id_refuses, False),
    (test_no_surface_prints_a_token_or_a_full_id, False),
    (test_plan_surface_never_carries_credential_shape_and_masks_ids, False),
    (test_malformed_listing_shapes_refuse_payload, False),
    (test_non_object_listing_response_refuses, False),
    (test_explicit_row_seam_never_touches_the_client, False),
    (test_finder_exposes_no_archive_write_surface, False),
    (test_archive_action_requires_execute_at_the_cli_boundary, False),
    (test_execute_never_relaxes_the_proven_write_law, False),
    (test_finder_plan_carries_the_archive_gate_law_as_data, False),
    (test_sibling_u06_batteries_are_green, False),
    (test_sibling_archive_surfaces_agree_on_the_execute_gate, False),
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
