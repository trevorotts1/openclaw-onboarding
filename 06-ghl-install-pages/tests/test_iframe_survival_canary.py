"""Offline tests for P3-04 (c)4 — the weekly iframe-survival check wired into
the existing selector-canary machinery (ghl_selector_canary.py).

THE RESIDUAL (Skill-6 spec §(b), 2026-07-11): iframe SURVIVAL in published GHL
pages/surveys/forms is proven ONCE (2026-06-27 probe: GHL preview does not
strip the cross-origin *.leadconnectorhq.com iframe) but was never
CONTINUOUSLY guarded — nothing re-checks it on a cadence, so a future GHL UI
change that starts stripping iframes on publish would go undetected until a
client reported broken pages.

THE FIX: run_iframe_survival_check() — same read-only, dependency-injected
shape as run_canary() (no network of its own; a caller-supplied page_fetcher
does the real HTTP GET / agent-browser snapshot), reporting each published
target as "survived" or "stripped" and fail-softly notifying the board (via
the SAME VERIFY-FAIL taxonomy value cc_board.py already enforces — this is a
post-publish render/verification check, F6's exact shape; it deliberately
does NOT invent a 7th taxonomy value) on a stripped iframe.

No network, no browser, no GHL writes: every page_fetcher in this file is a
fake callable returning canned HTML.
"""

import json
import os
import sys
import tempfile

import pytest

_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import ghl_selector_canary as canary  # noqa: E402


SURVIVED_HTML = """
<html><body>
  <div id="quick-add-tile">
    <iframe src="https://forms.leadconnectorhq.com/widget/survey/abc123"></iframe>
  </div>
</body></html>
"""

STRIPPED_HTML = """
<html><body>
  <div id="quick-add-tile">
    <!-- no iframe here -- GHL started stripping it on publish -->
    <p>Survey unavailable</p>
  </div>
</body></html>
"""


def _fetcher(mapping):
    def _fetch(url):
        return mapping[url]
    return _fetch


# ---------------------------------------------------------------------------
# Taxonomy discipline — reuses VERIFY-FAIL, never invents a 7th cc_board value
# ---------------------------------------------------------------------------
def test_iframe_survival_reuses_verify_fail_taxonomy_value():
    assert canary.BOARD_NOTE_IFRAME_SURVIVAL_MISS == "VERIFY-FAIL"


# ---------------------------------------------------------------------------
# run_iframe_survival_check — core behavior
# ---------------------------------------------------------------------------
def test_all_targets_survive_clean_run():
    targets = [
        {"id": "survey.p2.published", "url": "https://x/survey1", "object_type": "survey"},
        {"id": "form.p2.published", "url": "https://x/form1", "object_type": "form"},
    ]
    fetcher = _fetcher({"https://x/survey1": SURVIVED_HTML, "https://x/form1": SURVIVED_HTML})
    report = canary.run_iframe_survival_check(targets, fetcher)
    summary = report.summary()
    assert summary["clean"] is True
    assert summary["total_targets"] == 2
    assert summary["misses"] == []


def test_stripped_iframe_is_reported_as_a_miss_and_notifies_board():
    targets = [{"id": "survey.p2.published", "url": "https://x/survey1", "object_type": "survey"}]
    fetcher = _fetcher({"https://x/survey1": STRIPPED_HTML})
    notified = []
    report = canary.run_iframe_survival_check(
        targets, fetcher, board_notifier=lambda payload: notified.append(payload)
    )
    summary = report.summary()
    assert summary["clean"] is False
    assert "survey.p2.published" in summary["misses"]
    assert len(notified) == 1
    assert notified[0]["prefix"] == canary.BOARD_NOTE_IFRAME_SURVIVAL_MISS
    assert notified[0]["prefix"] == "VERIFY-FAIL"


def test_one_miss_never_blocks_scanning_the_rest():
    targets = [
        {"id": "survey.stripped", "url": "https://x/s1", "object_type": "survey"},
        {"id": "form.ok", "url": "https://x/f1", "object_type": "form"},
    ]
    fetcher = _fetcher({"https://x/s1": STRIPPED_HTML, "https://x/f1": SURVIVED_HTML})
    report = canary.run_iframe_survival_check(targets, fetcher)
    ids = {r["target"] for r in report.results}
    assert ids == {"survey.stripped", "form.ok"}
    assert len(report.results) == 2
    assert len(report.misses) == 1


def test_fetch_error_is_a_miss_not_a_crash():
    def _boom(url):
        raise TimeoutError("page fetch timed out")
    targets = [{"id": "survey.timeout", "url": "https://x/s1", "object_type": "survey"}]
    report = canary.run_iframe_survival_check(targets, _boom)
    assert report.summary()["clean"] is False
    assert report.results[0]["status"] == "fetch-error"


def test_board_notifier_failure_is_fail_soft():
    targets = [{"id": "survey.stripped", "url": "https://x/s1", "object_type": "survey"}]
    fetcher = _fetcher({"https://x/s1": STRIPPED_HTML})
    def _boom(payload):
        raise RuntimeError("board is down")
    # Must not raise out of the check (fail-soft, same as run_canary).
    report = canary.run_iframe_survival_check(targets, fetcher, board_notifier=_boom)
    assert report.summary()["clean"] is False


def test_writes_evidence_file():
    targets = [{"id": "survey.ok", "url": "https://x/s1", "object_type": "survey"}]
    fetcher = _fetcher({"https://x/s1": SURVIVED_HTML})
    with tempfile.TemporaryDirectory() as tmp:
        report = canary.run_iframe_survival_check(targets, fetcher, evidence_root=tmp)
        assert report.summary()["clean"] is True
        written = [f for f in os.listdir(tmp) if f.startswith("iframe-survival-")]
        assert len(written) == 1
        with open(os.path.join(tmp, written[0])) as fh:
            on_disk = json.load(fh)
        assert on_disk["summary"]["clean"] is True


def test_custom_iframe_src_marker_is_respected():
    # A caller may point the marker at a different embed host; default stays
    # leadconnectorhq.com but the check must not hardcode it unreachably.
    html = '<html><body><iframe src="https://other-embed.example.com/x"></iframe></body></html>'
    targets = [{"id": "t1", "url": "https://x/t1", "object_type": "page"}]
    fetcher = _fetcher({"https://x/t1": html})
    report_default_marker = canary.run_iframe_survival_check(targets, fetcher)
    assert report_default_marker.summary()["clean"] is False  # default marker not present
    report_custom_marker = canary.run_iframe_survival_check(
        targets, fetcher, iframe_src_marker="other-embed.example.com"
    )
    assert report_custom_marker.summary()["clean"] is True


# ---------------------------------------------------------------------------
# live_page_fetcher_over_http — pure factory, no network at import/selftest time
# ---------------------------------------------------------------------------
def test_live_page_fetcher_factory_is_lazy_no_network_on_creation():
    # Must be constructible without making any network call (network only
    # happens if/when the returned callable is actually invoked).
    fetcher = canary.live_page_fetcher_over_http()
    assert callable(fetcher)


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------
def test_cli_iframe_survival_without_targets_or_fetcher_refuses_cleanly(tmp_path):
    empty_targets = tmp_path / "empty-targets.json"
    empty_targets.write_text(json.dumps({"targets": []}))
    rc = canary.main(["--iframe-survival", "--iframe-targets-path", str(empty_targets)])
    # No live fetcher wiring and no --selftest-finder => refuse loudly (2),
    # never silently "pass" a check it didn't actually run.
    assert rc == 2


def test_cli_iframe_survival_selftest_finder_offline_dry_run(tmp_path, capsys):
    targets_path = tmp_path / "targets.json"
    targets_path.write_text(json.dumps({"targets": [
        {"id": "t1", "url": "https://x/t1", "object_type": "survey"}
    ]}))
    rc = canary.main([
        "--iframe-survival", "--selftest-finder",
        "--iframe-targets-path", str(targets_path),
    ])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["clean"] is True
    assert rc == 0


# ---------------------------------------------------------------------------
# Module selftest also exercises the iframe-survival path (belt-and-suspenders,
# same convention as the existing _selftest()).
# ---------------------------------------------------------------------------
def test_module_selftest_still_passes_with_iframe_survival_added():
    assert canary._selftest() == 0
