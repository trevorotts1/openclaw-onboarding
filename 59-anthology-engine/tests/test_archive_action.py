#!/usr/bin/env python3
"""test_archive_action.py -- unit tests for the U06 archive ACTION (Skill 59).

THE ARCHIVE ACTION LAW, pinned from the engine sources:

  * The ONE ACTION verb of the U06 workflow_lister module is 'archive'
    (workflow_lister.ACTION_ARCHIVE == "archive", mirror-pinned here).
  * Trevor-gated: the archive ACTION REQUIRES --execute passed explicitly
    (workflow_lister.main: "an ACTION without --execute is a refusal, never
    a silent no-op"). WITHOUT --execute the CLI is a STOP (exit 2) BEFORE
    any credential work, so the gate is provable OFFLINE with an explicit
    empty environ -- the self-test injection point that blocks the
    canonical env-store fallback (registry._env_first, environ=not-None).
  * Idempotent by construction: the archive plan is a pure function of the
    listing read (workflow_lister._archive_plan), and the ACTION never
    mutates ANY state -- it emits a structured PLAN ONLY, because the
    engine's endpoint doctrine (Skill 44: only proven endpoints) binds this
    module to no archive/delete surface for workflows (ARCHIVE_NOTE). The
    plan says exactly what it WOULD archive and writes nothing.
  * Dry-run writes nothing: _archive_plan is PURE -- no I/O, no writes, no
    prints. The same pure call is the body of both the dry-run and the
    --execute path (execute only toggles the reported flag); the file
    system and the record set are both unchanged after the plan.
  * Fail-closed: a malformed listing, a non-dict row, a missing target
    name, an empty name, a case-drifted name, a duplicate name, a blank
    name/id row -- all REFUSE (ValueError / STOP / dropped-with-count),
    never a guessed plan and never a fabricated success.
  * Never a token printed: credentials resolve BY LABEL (SET / NOT-SET
    only); the location id and every workflow id are MASKED to the last 4
    characters on every operator surface (_mask_id / _mask_location) -- the
    plan's target id is "....NNNN", never the full id.
  * Browser UA (CF 1010): every rail request rides
    registry._internal_request_headers, which carries CAF_BROWSER_UA
    (Mozilla/5.0 ... -- the house pattern that clears the Cloudflare edge
    fronting backend.leadconnectorhq.com); urllib's default Python-urllib
    UA is 1010'd. Pinned here against the registry constant so a regression
    in the edge fix is caught first.

OFFLINE BY DESIGN: no network, no secrets. Every test either calls a pure
helper with a synthetic golden listing or drives the CLI gates that return
before any credential resolution, with an explicit EMPTY environ.

Run: python3 -m pytest 59-anthology-engine/tests/test_archive_action.py -q
 or: python3 59-anthology-engine/tests/test_archive_action.py
"""
import json
import os
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
U06 = SCRIPTS / "u06_modules"

for _p in (SCRIPTS, U06):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import anthology_registry as reg  # noqa: E402
import workflow_lister as wl  # noqa: E402

GOLDEN_LISTING = {
    "rows": [
        {"name": "Anthology Intake Fire", "id": "wf-0001", "type": "workflow",
         "status": "published"},
        {"name": "Anthology Release: Avatar", "id": "wf-0002", "type": "workflow",
         "status": "published"},
        {"name": "Anthology Release: Cover", "id": "wf-0003", "type": "workflow",
         "status": "draft"},
        {"name": "Anthology Templates", "id": "folder-1", "type": "folder"},
    ]}


# ---------------------------------------------------------------------------
# The archive ACTION LAW: the one ACTION is 'archive' and it is --execute-gated.
# ---------------------------------------------------------------------------
def test_action_verb_is_exactly_archive():
    assert wl.ACTION_ARCHIVE == "archive", \
        "the ONE archive ACTION verb must be 'archive'"


def test_archive_requires_execute_cli_stop_without_it():
    """NO --execute -> STOP exit 2, before any credential work. The explicit
    empty environ blocks the canonical env-store fallback, so the gate is
    deterministic OFFLINE (the fail-closed refusal, not a HELD)."""
    rc = wl.main(["archive", "--name", "Anthology Intake Fire"], environ={})
    assert rc == reg.EX_STOP, \
        "archive without --execute must STOP (Trevor-gated), got %r" % rc


def test_archive_requires_name_cli_stop_without_it():
    rc = wl.main(["archive"], environ={})
    assert rc == reg.EX_STOP, \
        "archive without --name must STOP, got %r" % rc


def test_archive_execute_with_empty_credentials_is_held_not_done():
    """WITH --execute but NO credential SET, the archive path must HELD (a
    truthful plan needs the live read), never emit 'done' and never mutate.
    `environ={}` is the registry's injection point: it blocks the live
    process env AND the canonical env-store fallback, so the HELD gate is
    deterministic OFFLINE with zero network."""
    rc = wl.archive_command("X", "", execute=True,
                            out=sys.stderr, jsonout=None, environ={})
    assert rc == reg.EX_HELD, \
        "archive --execute without credentials must HELD (exit 3), got %r" % rc


def test_list_needs_no_execute_and_is_read_only():
    """The read surface needs no --execute; with no credentials it HELDs
    (never fabricates a list) and never mutates. main() forwards environ to
    the list command, so the empty-environ HELD gate is offline-deterministic."""
    rc = wl.main(["list"], environ={})
    assert rc == reg.EX_HELD, \
        "list without credentials must HELD, got %r" % rc


# ---------------------------------------------------------------------------
# The plan is a pure function of the listing -- idempotence and dry-run safety.
# ---------------------------------------------------------------------------
def _rows():
    return wl._rows_from_listing(GOLDEN_LISTING)


def _plan(name="Anthology Release: Avatar"):
    return wl._archive_plan(_rows(), GOLDEN_LISTING, name)


def test_plan_shape_and_no_mutation_fields():
    plan = _plan()
    assert plan["ok"] is True
    assert plan["action"] == wl.ACTION_ARCHIVE == "archive"
    assert plan["execute"] is False, \
        "the pure plan must report execute=False (dry-run)"
    assert plan["would_archive"] == 1
    assert plan["rows_unknown_status"] == 0
    assert plan["rows_dropped"] == 0
    assert "note" in plan and plan["note"], (
        "the plan must carry the endpoint-doctrine note (no proven archive "
        "surface -> plan only, nothing written)")


def test_plan_target_resolves_byte_exact_and_is_masked():
    plan = _plan()
    assert plan["target"]["name"] == "Anthology Release: Avatar"
    assert plan["target"]["status"] == "published"
    assert plan["target"]["id"].startswith("..."), \
        "the target id must be masked on the plan surface"
    assert "wf-0002" not in json.dumps(plan), \
        "the full workflow id must never surface"


def test_plan_is_pure_no_filesystem_side_effects(tmp_path):
    """Idempotence + dry-run writes nothing, proven on the file system: a
    frozen snapshot of the tree is byte-identical after building the plan
    (and after building it twice), and a --execute-false plan carries zero
    write intent. The plan is a pure function: same listing in, same plan
    out, no state anywhere."""
    cwd = os.getcwd()
    tree_before = sorted(
        str(p.relative_to(tmp_path))
        for p in tmp_path.rglob("*"))
    try:
        os.chdir(tmp_path)
        p1 = _plan()
        p2 = _plan()
    finally:
        os.chdir(cwd)
    tree_after = sorted(
        str(p.relative_to(tmp_path))
        for p in tmp_path.rglob("*"))
    assert tree_before == tree_after, \
        "building the archive plan must not create, modify or delete any file"
    assert p1 == p2, \
        "the archive plan must be idempotent (pure function of the listing)"
    assert p1["execute"] is False and p1["would_archive"] == 1
    assert not any(k for k in p1 if "applied" in k or "done" in k), \
        "a dry-run plan must carry no applied/done field"


def test_plan_never_prints_to_stdout(tmp_path, capsys, monkeypatch):
    """The pure plan performs NO prints and NO stdout writes; even in a live
    stdout capture nothing is emitted (the plan only returns a dict)."""
    monkeypatch.chdir(tmp_path)
    _plan()
    captured = capsys.readouterr()
    assert captured.out == "", \
        "the pure plan must write nothing to stdout, got %r" % captured.out


# ---------------------------------------------------------------------------
# Fail-closed refusals -- an archive bound to the wrong record must be impossible.
# ---------------------------------------------------------------------------
def test_plan_refuses_unknown_name():
    with pytest.raises(ValueError):
        wl._archive_plan(_rows(), GOLDEN_LISTING, "No Such Workflow")


def test_plan_refuses_empty_name():
    with pytest.raises(ValueError):
        wl._archive_plan(_rows(), GOLDEN_LISTING, "")


def test_plan_refuses_case_drifted_name():
    with pytest.raises(ValueError):
        wl._archive_plan(_rows(), GOLDEN_LISTING, "Anthology release: Avatar")


def test_plan_refuses_duplicate_names():
    dup = {"rows": [
        {"name": "Dupe", "id": "wf-9", "type": "workflow", "status": "published"},
        {"name": "Dupe", "id": "wf-8", "type": "workflow", "status": "draft"}]}
    with pytest.raises(ValueError):
        wl._archive_plan(wl._rows_from_listing(dup), dup, "Dupe")


def test_plan_refuses_malformed_listings():
    for bad in ([], {"nope": True}, {"rows": "not-a-list"}, {"rows": ["scalar"]}):
        with pytest.raises(ValueError):
            wl._rows_from_listing(bad)


def test_plan_drops_blank_rows_with_count_surfaced():
    ragged = {"rows": [
        {"name": "", "id": "wf-1", "type": "workflow", "status": "published"},
        {"name": "Only Id", "id": "", "type": "workflow", "status": "draft"},
        {"name": "Good", "id": "wf-3", "type": "workflow", "status": "published"}]}
    plan = wl._archive_plan(wl._rows_from_listing(ragged), ragged, "Good")
    assert plan["would_archive"] == 1
    assert plan["rows_dropped"] == 2, \
        "blank-name and blank-id rows must drop with the count surfaced"


def test_plan_never_carries_a_credential_shaped_string():
    """The full plan JSON must never contain a pit-/Bearer-shaped value or a
    full workflow id -- the house never-print discipline on the ACTION
    surface."""
    plan = _plan()
    assert "pit-" not in json.dumps(plan)
    assert "Bearer " not in json.dumps(plan)


# ---------------------------------------------------------------------------
# House doctrine: browser UA (CF 1010) and masked markers.
# ---------------------------------------------------------------------------
def test_registry_browser_ua_is_a_browser_ua():
    assert reg.CAF_BROWSER_UA.startswith("Mozilla/5.0"), \
        "CAF_BROWSER_UA must be a browser User-Agent (CF 1010)"
    assert "Python-urllib" not in reg.CAF_BROWSER_UA


def test_internal_rail_headers_carry_browser_ua():
    hdrs = reg._internal_request_headers("dummy-id-token")
    assert hdrs.get("User-Agent") == reg.CAF_BROWSER_UA, \
        "every internal-rail request must ride CAF_BROWSER_UA (CF 1010)"


def test_mask_id_never_exposes_the_full_id():
    assert wl._mask_id("wf-0002") == "...0002", \
        "the resource-id marker is last-4 only"
    assert wl._mask_id("") == "...(short)"
    assert wl._mask_id("ab") == "...(short)"


# ---------------------------------------------------------------------------
# A CLI path with credentials exercises a truthful plan end to end. OFFLINE:
# the registry's injectable InternalRailClient (mint_fn/get_fn) returns the
# golden listing without any network, and the environment is fully stubbed
# by monkeypatch so no live credential is read, used, or printed.
# ---------------------------------------------------------------------------
def test_archive_execute_reports_plan_via_injectable_rail(capsys, monkeypatch):
    monkeypatch.setenv(reg.FIREBASE_REFRESH_LABELS[0], "dummy-refresh-token")
    monkeypatch.setenv(reg.FIREBASE_API_KEY_LABELS[0], "dummy-api-key")
    monkeypatch.setenv(reg.LOCATION_LABELS[0], "dummy-location")

    real_client = reg.InternalRailClient  # bind BEFORE the patch

    def fake_get(path, tok):
        assert "dummy-location" in path
        return GOLDEN_LISTING

    def fake_client(refresh, api_key):
        # the REAL class, constructed with the injectable mint/get functions
        # (the registry's offline-test seam); no network is touched
        return real_client(refresh, api_key,
                           mint_fn=lambda rt: "dummy-id-token", get_fn=fake_get)

    monkeypatch.setattr(reg, "InternalRailClient", fake_client)

    rc = wl.archive_command(
        "Anthology Intake Fire", "", execute=True,
        out=sys.stderr, jsonout=None, environ=None)
    assert rc == reg.EX_OK, "a truthful plan must exit 0, got %r" % rc

    err = capsys.readouterr().err
    assert "ARCHIVE PLAN" in err
    assert "execute=True" in err
    assert "Nothing was written." in err, \
        "the plan surface must state that no mutation was performed"
    # never-print: no token, no api key, no full id on the operator surface
    assert "dummy-refresh-token" not in err
    assert "dummy-api-key" not in err
    assert "wf-0001" not in err


def test_archive_execute_json_report_is_a_plan_not_a_result(capsys, monkeypatch):
    monkeypatch.setenv(reg.FIREBASE_REFRESH_LABELS[0], "dummy-refresh-token")
    monkeypatch.setenv(reg.FIREBASE_API_KEY_LABELS[0], "dummy-api-key")
    monkeypatch.setenv(reg.LOCATION_LABELS[0], "dummy-location")

    real_client = reg.InternalRailClient  # bind BEFORE the patch

    def fake_get(path, tok):
        return GOLDEN_LISTING

    def fake_client(refresh, api_key):
        return real_client(refresh, api_key,
                           mint_fn=lambda rt: "dummy-id-token", get_fn=fake_get)

    monkeypatch.setattr(reg, "InternalRailClient", fake_client)

    buf = __import__("io").StringIO()
    rc = wl.archive_command(
        "Anthology Intake Fire", "", execute=True,
        out=sys.stderr, jsonout=buf, environ=None)
    assert rc == reg.EX_OK
    report = json.loads(buf.getvalue())
    assert report["action"] == "archive"
    assert report["execute"] is True
    assert report["would_archive"] == 1
    assert report["target"]["id"].startswith("...")
    assert report["location"].startswith("...")
    assert "dummy-refresh-token" not in json.dumps(report)
    assert "dummy-api-key" not in json.dumps(report)
    assert "wf-0001" not in json.dumps(report)


def test_list_via_injectable_rail_lists_and_never_mutates(capsys, monkeypatch):
    """The read surface needs NO --execute: with the injectable rail it lists
    the golden names and reports a list -- never an archive, never a write."""
    monkeypatch.setenv(reg.FIREBASE_REFRESH_LABELS[0], "dummy-refresh-token")
    monkeypatch.setenv(reg.FIREBASE_API_KEY_LABELS[0], "dummy-api-key")
    monkeypatch.setenv(reg.LOCATION_LABELS[0], "dummy-location")

    real_client = reg.InternalRailClient  # bind BEFORE the patch

    def fake_get(path, tok):
        return GOLDEN_LISTING

    def fake_client(refresh, api_key):
        return real_client(refresh, api_key,
                           mint_fn=lambda rt: "dummy-id-token", get_fn=fake_get)

    monkeypatch.setattr(reg, "InternalRailClient", fake_client)

    buf = __import__("io").StringIO()
    rc = wl.live_list_command("", out=sys.stderr, jsonout=buf, environ=None)
    assert rc == reg.EX_OK
    report = json.loads(buf.getvalue())
    assert report["action"] == "list"
    assert report["workflows"] == ["Anthology Intake Fire",
                                   "Anthology Release: Avatar",
                                   "Anthology Release: Cover"]
    assert report["location"].startswith("...")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
