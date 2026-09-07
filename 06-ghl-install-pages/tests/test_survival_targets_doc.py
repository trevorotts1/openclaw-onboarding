"""Offline tests for the 9.7-2 loud-empty fix on the weekly iframe-survival
check (iframe-survival-targets.json v1.1.1).

THE HAZARD THIS LOCKS: tools/iframe-survival-targets.json ships with
``targets: []`` EMPTY, and an empty list is a VALID, clean zero-target run
(never an error — load_iframe_survival_targets / run_iframe_survival_check
fail loud only on a missing/corrupt file). Left undocumented that "clean" is
a SILENT NO-OP: a zero-target pass proves NOTHING about any published page
still embedding its cross-origin iframe, and an operator can go months
believing the weekly check guards iframe survival when it has scanned zero
targets.

THE FIX (documentation + self-description, NOT populated URLs — no real
client URLs belong in this fleet-wide repo): the JSON itself carries the
loud-empty note (``_operator_note`` + extended ``_comment``) and
run_iframe_survival_check() now emits an ADVISORY warning — a WARN line on
stderr plus a ``warnings`` list in IframeSurvivalReport (so it lands in both
the printed summary and the on-disk evidence JSON) — whenever it is called
with zero targets. Exit codes are UNCHANGED (empty = a valid run); the point
is that the no-op can never again be silent.

Mock-only: every page_fetcher here is a fake callable returning canned HTML;
no network, no browser, no GHL writes. pytest tmp_path/capsys do the rest.
"""

import json
import os
import sys

import pytest

_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import ghl_selector_drift_probe as canary  # noqa: E402

_SURVIVAL_TARGETS_JSON = os.path.join(_TOOLS, "iframe-survival-targets.json")

SURVIVED_HTML = (
    '<html><iframe src="https://forms.leadconnectorhq.com/widget/survey/x"></iframe></html>'
)

# ---------------------------------------------------------------------------
# The JSON doc itself — loud-empty self-description
# ---------------------------------------------------------------------------
def test_survival_targets_json_is_valid_and_still_empty():
    with open(_SURVIVAL_TARGETS_JSON, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    # The shipped doc must still be the loud-empty state: valid schema,
    # empty array (no real client URLs in the repo), _schema unchanged.
    assert data["targets"] == []
    assert "_schema" in data
    assert set(data["_schema"].keys()) == {"id", "url", "object_type"}

def test_survival_targets_json_version_bumped_to_v1_1_1():
    with open(_SURVIVAL_TARGETS_JSON, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["version"] == "v1.1.1", (
        "loud-empty note ships in v1.1.1 — a revert to v1.1.0 hides the fix"
    )

def test_survival_targets_json_carries_the_loud_empty_note():
    with open(_SURVIVAL_TARGETS_JSON, "r", encoding="utf-8") as fh:
        raw = fh.read()
    assert "_operator_note" in raw
    # The note must say the LOUD thing, not just restate "ships empty".
    note_blob = raw.lower()
    for required in ("proves nothing", "operator", "populate"):
        assert required in note_blob, f"loud-empty note missing {required!r}"

# ---------------------------------------------------------------------------
# run_iframe_survival_check — zero-target run is loud, never silent
# ---------------------------------------------------------------------------
def test_zero_target_run_warns_loudly_in_report_and_stderr(capsys):
    report = canary.run_iframe_survival_check([], lambda url: SURVIVED_HTML)
    # Advisory warning in the report (lands in the printed summary AND the
    # on-disk evidence via to_dict).
    assert report.warnings == [canary.IFRAME_SURVIVAL_EMPTY_TARGETS_WARN]
    assert report.summary()["warnings"] == [canary.IFRAME_SURVIVAL_EMPTY_TARGETS_WARN]
    assert report.summary()["clean"] is True  # still a VALID run, never an error
    assert report.summary()["total_targets"] == 0
    assert canary.IFRAME_SURVIVAL_EMPTY_TARGETS_WARN in report.to_dict()["warnings"]
    # WARN line on stderr (advisory — stdout stays the JSON summary).
    err = capsys.readouterr().err
    assert "WARN" in err
    assert "survival check no-op: 0 targets" in err
    assert "iframe-survival-targets.json" in err

def test_zero_target_run_writes_nothing_and_fetches_nothing(tmp_path, capsys):
    fetched = []
    report = canary.run_iframe_survival_check([], lambda url: fetched.append(url) or SURVIVED_HTML)
    assert fetched == []  # a no-op must not touch the network at all
    # The warn must not be swallowed into a fabricated per-target result.
    assert report.results == [] and report.misses == []

def test_zero_target_run_warns_are_idempotent_across_repeats(capsys):
    for _ in range(2):
        report = canary.run_iframe_survival_check([], lambda url: SURVIVED_HTML)
        assert report.summary()["warnings"] == [canary.IFRAME_SURVIVAL_EMPTY_TARGETS_WARN]

def test_one_target_run_does_not_warn(capsys):
    targets = [{"id": "t1", "url": "https://x/t1", "object_type": "survey"}]
    report = canary.run_iframe_survival_check(targets, lambda url: SURVIVED_HTML)
    assert report.summary()["warnings"] == []
    assert report.warnings == []
    assert capsys.readouterr().err == ""

def test_warn_is_advisory_exit_codes_unchanged():
    # The warning must live ONLY in warnings/stderr — it must not flip
    # `clean` (empty is a valid run per recon) or appear as a miss.
    report = canary.run_iframe_survival_check([], lambda url: "")
    assert report.summary()["clean"] is True
    assert report.summary()["misses"] == []

# ---------------------------------------------------------------------------
# CLI wiring — the warn surfaces on the cron entry point too
# ---------------------------------------------------------------------------
def test_cli_iframe_survival_empty_targets_offline_dry_run_warns(tmp_path, capsys):
    targets_path = tmp_path / "empty-targets.json"
    targets_path.write_text(json.dumps({"targets": []}))
    rc = canary.main([
        "--iframe-survival", "--selftest-finder",
        "--iframe-targets-path", str(targets_path),
    ])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)  # stdout stays the clean JSON summary
    assert payload["clean"] is True and payload["total_targets"] == 0
    assert payload["warnings"] == [canary.IFRAME_SURVIVAL_EMPTY_TARGETS_WARN]
    assert "survival check no-op: 0 targets" in captured.err
    assert rc == 0  # exit codes unchanged — empty is still a valid run

def test_cli_iframe_survival_one_target_offline_dry_run_no_warn(tmp_path, capsys):
    targets_path = tmp_path / "targets.json"
    targets_path.write_text(json.dumps({"targets": [
        {"id": "t1", "url": "https://x/t1", "object_type": "survey"}
    ]}))
    rc = canary.main([
        "--iframe-survival", "--selftest-finder",
        "--iframe-targets-path", str(targets_path),
    ])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["warnings"] == []
    assert captured.err == ""
    assert rc == 0