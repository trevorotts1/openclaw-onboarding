#!/usr/bin/env python3
"""Unit tests for the keyless research gatherer (SPEC item 2, unit SWI-005).

stdlib only. The DEFAULT run never touches the network: every transport is a
fake injected through `gather.gather(..., transport=...)` /
`research.run_stage(..., transport=...)`, and the CLI is exercised by patching
`gather.default_transport`. The single live smoke is opt-in:

    DSAF_RESEARCH_LIVE_SMOKE=1 python3 -m pytest -q <this dir>

Covers: query selection, HTML link extraction against saved fixtures,
de-duplication and junk filtering, already-non-empty sources[] short-circuit
(no transport call at all), offline / budget degradation to exit 2 "waiting",
the JSON envelope + full exit contract, and one bounded call per URL.
"""
import contextlib
import datetime
import inspect
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
from pathlib import Path

try:
    import pytest
except ImportError:
    # The repo also runs skill-75 tests script-style (`python3 <test>.py`) in
    # an empty-HOME environment that has no pytest. Every test below is written
    # to run in BOTH modes: no pytest-only fixture is used without a stdlib
    # stand-in supplied by _run_all() at the bottom of this file.
    pytest = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gather as G          # noqa: E402
import research as R        # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures")


def _fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


def _reply(body, url):
    """Transport contract: (bytes, final_url, charset) — str bodies encode."""
    if isinstance(body, str):
        body = body.encode("utf-8")
    return body, url, "utf-8"


# ---------------------------------------------------------------- transports

class FakeTransport:
    """Injected transport: URL prefix -> (body, final_url, charset).

    Records every call so tests can assert one bounded attempt per URL and
    that an already-sourced brief never opens a connection at all. Unknown
    URLs raise URLError, which is exactly what an offline box sees.
    """

    def __init__(self, routes=None, default=None):
        self.routes = dict(routes or {})
        self.default = default
        self.calls = []

    def __call__(self, url, timeout, headers):
        self.calls.append((url, timeout, headers))
        for prefix in sorted(self.routes, key=len, reverse=True):
            if url.startswith(prefix):
                return _reply(self.routes[prefix], url)
        if self.default is not None:
            return _reply(self.default, url)
        raise urllib.error.URLError("Name or service not known")


class OfflineTransport:
    def __init__(self):
        self.calls = 0

    def __call__(self, url, timeout, headers):
        self.calls += 1
        raise urllib.error.URLError("Network is unreachable")


def _search_routes(page_html, page_url):
    """Routes for both search endpoints pointing at one saved results page."""
    return {
        "https://html.duckduckgo.com/html/": page_html,
        "https://lite.duckduckgo.com/lite/": page_html,
        page_url: _fixture("article.html"),
    }


BARE = {"offer": "Example back pain guide",
        "audience": "adults over 50 who want to sleep through the night",
        "action": "book a free call at example.invalid"}

SUB_AVATAR = {"avatar": "retiree", "emotional_wound": "nights awake",
              "desired_transformation": "sleeping through"}


def _complete(brief):
    """Bare brief plus the sub-avatar gate this unit does not own, so an
    expectation of outcome "ok" tests the gatherer, not that gate."""
    out = dict(brief)
    out["sub_avatar"] = dict(SUB_AVATAR)
    return out


# ------------------------------------------------------------- query selection

def test_pick_queries_deterministic_ordered_and_capped():
    first = G.pick_queries(BARE)
    second = G.pick_queries(dict(BARE))
    assert first == second, "query selection must be deterministic"
    assert first[0] == "Example back pain guide"
    assert first[1].startswith("Example back pain guide")
    assert "adults" in first[1]
    assert len(first) == 3
    for q in first:
        assert len(q.split()) <= G.MAX_QUERY_WORDS, q


def test_pick_queries_no_field_pasted_twice_and_no_duplicates():
    queries = G.pick_queries({"offer": "sleep program for adults",
                              "audience": "adults",
                              "cta": "book a call"})
    lowered = [q.lower() for q in queries]
    assert len(set(lowered)) == len(lowered), queries
    for q in queries:
        words = q.lower().split()
        assert len(words) == len(set(w.strip(".,") for w in words)), q


def test_pick_queries_without_offer_falls_back_to_audience_then_action():
    assert G.pick_queries({"audience": "busy parents"}) == ["busy parents"]
    assert G.pick_queries({"action": "download the checklist"}) == ["download the checklist"]
    assert G.pick_queries({}) == []
    assert G.pick_queries(None) == []


# ---------------------------------------------------------- link extraction

def test_extract_result_urls_from_html_endpoint_fixture():
    urls = G.extract_result_urls(_fixture("ddg_html.html"),
                                 "https://html.duckduckgo.com/html/?q=x")
    assert urls == ["https://example.invalid/back-pain-guide",
                    "https://docs.example.org/guide",
                    "https://example.invalid/sleep-and-stress"]


def test_extract_result_urls_from_lite_endpoint_fixture():
    urls = G.extract_result_urls(_fixture("ddg_lite.html"),
                                 "https://lite.duckduckgo.com/lite/?q=x")
    assert urls == ["https://portal.example.net/start",
                    "https://blog.example.io/posts/habits"]


def test_junk_is_filtered_and_results_deduplicated():
    urls = G.extract_result_urls(_fixture("ddg_html.html"),
                                 "https://html.duckduckgo.com/html/?q=x")
    joined = " ".join(urls).lower()
    assert "javascript:" not in joined and "mailto:" not in joined
    assert "duckduckgo.com" not in joined, "search-engine self links must drop"
    assert ".png" not in joined
    # fragment + trailing-slash variants of one page collapse to a single URL
    assert G.normalize_url("https://example.invalid/sleep-and-stress/#top") == \
        G.normalize_url("https://example.invalid/sleep-and-stress")
    assert G.is_junk("javascript:void(0)")
    assert G.is_junk("mailto:sales@example.invalid")
    assert G.is_junk("tel:+10000000000")
    assert G.is_junk("https://html.duckduckgo.com/html/?q=x")
    assert G.is_junk("https://cdn.example.org/logo.png")
    assert not G.is_junk("https://docs.example.org/guide")


def test_extract_skips_unparseable_markup():
    assert G.extract_result_urls("<<< not html >>>") == []
    assert G.html_to_text("<div><p>only text <unclosed") != ""


# ------------------------------------------------------- already-sourced brief

def test_nonempty_sources_short_circuits_without_any_transport_call():
    transport = FakeTransport(routes=_search_routes(_fixture("ddg_html.html"),
                                                    "https://example.invalid/back-pain-guide"))
    brief = dict(BARE)
    brief["sources"] = [{"url": "https://example.invalid/client-note",
                         "retrieved": "2026-10-14"}]
    g = G.gather(brief, transport=transport)
    assert g["status"] == "client-supplied"
    assert transport.calls == [], "client sources win: no search, no fetch"
    assert g["sources"] == brief["sources"]
    assert g["queries"] == []


def test_nonempty_sources_brief_skips_the_gatherer_inside_run_stage(tmp_path):
    transport = FakeTransport(routes=_search_routes(_fixture("ddg_html.html"),
                                                    "https://example.invalid/back-pain-guide"))
    brief = dict(BARE)
    brief["sources"] = [{"url": "https://example.invalid/client-note"}]
    brief["claims"] = [{"text": "A claim the client filed themselves.",
                        "source": "src-1"}]  # dangling id: never re-pointed
    brief["sub_avatar"] = dict(SUB_AVATAR)
    env, code = R.run_stage(brief, str(tmp_path), transport=transport)
    assert transport.calls == [], "already-sourced brief must not search"
    assert code == R.EXIT["ok"]
    assert env["outcome"] == "ok"
    assert env["schema_version"] == R.SCHEMA_VERSION == "blackceo.research/v1"


# ------------------------------------------------------- bare brief: gathering

def test_bare_brief_gathers_sources_and_claims_and_renders(tmp_path):
    routes = _search_routes(_fixture("ddg_html.html"),
                            "https://example.invalid/back-pain-guide")
    transport = FakeTransport(routes=routes)
    env, code = R.run_stage(_complete(BARE), str(tmp_path), transport=transport)
    assert code == R.EXIT["ok"] and env["outcome"] == "ok", env
    assert env["schema_version"] == "blackceo.research/v1"
    assert env["evidence"], env
    evidence = json.loads((tmp_path / "research" / "evidence.json").read_text())
    assert evidence["schema_version"] == "blackceo.research/v1"
    assert len(evidence["sources"]) >= 1
    assert all(s["url"].startswith("https://") for s in evidence["sources"])
    assert all(s["retrieved"] == datetime.date.today().isoformat()
               for s in evidence["sources"])
    source_ids = {s["id"] for s in evidence["sources"]}
    assert evidence["claims"], "gathered claims must be filed"
    for claim in evidence["claims"]:
        assert claim["status"] == "PASS"
        assert claim["source"] in source_ids, claim
    for rel in ("research/market.md", "research/audience.md",
                "research/competitors.md", "research/manifest.json",
                "brief/sub_avatar.json"):
        assert (tmp_path / rel).exists(), rel


def test_search_is_one_bounded_attempt_per_query_and_pages_once_each():
    routes = _search_routes(_fixture("ddg_html.html"),
                            "https://example.invalid/back-pain-guide")
    transport = FakeTransport(routes=routes)
    G.gather(dict(BARE), transport=transport, max_queries=3, max_sources=6)
    search_calls = [c for c in transport.calls
                    if "duckduckgo.com" in c[0]]
    page_calls = [c for c in transport.calls if "duckduckgo.com" not in c[0]]
    queries = G.pick_queries(BARE)
    assert len(search_calls) == len(queries), transport.calls
    assert len(page_calls) == len(set(c[0] for c in page_calls)), "one call per URL"
    assert all(0 < c[1] <= G.DEFAULT_TIMEOUT for c in transport.calls), "timeout bounded"
    assert all(c[2]["User-Agent"] for c in transport.calls), "browser-like UA"


def test_offline_box_degrades_to_waiting_exit_2_not_a_crash(tmp_path):
    transport = OfflineTransport()
    brief = dict(BARE)
    env, code = R.run_stage(brief, str(tmp_path), transport=transport,
                            gather_opts={"max_queries": 2})
    assert code == R.EXIT["waiting"] == 2, env
    assert env["outcome"] == "waiting"
    assert env["reason_code"] == "search-offline"
    assert env["next_action"], "waiting must carry a reason and a next action"
    assert env["data"]["gather_status"] == "offline"
    assert transport.calls >= 1


def test_search_page_with_no_results_is_waiting_not_rejected(tmp_path):
    empty_results = "<html><body><div class='results'>no results</div></body></html>"
    transport = FakeTransport(routes={"https://html.duckduckgo.com/html/": empty_results,
                                      "https://lite.duckduckgo.com/lite/": empty_results})
    env, code = R.run_stage(dict(BARE), str(tmp_path), transport=transport)
    assert code == 2 and env["outcome"] == "waiting"
    assert env["reason_code"] == "search-no-results"
    assert env["data"]["gather_status"] == "empty"


def test_exhausted_stage_budget_is_waiting_with_its_reason(tmp_path):
    transport = FakeTransport(routes=_search_routes(_fixture("ddg_html.html"),
                                                    "https://example.invalid/back-pain-guide"))
    env, code = R.run_stage(dict(BARE), str(tmp_path), transport=transport,
                            gather_opts={"budget": 0})
    assert code == 2 and env["outcome"] == "waiting"
    assert env["reason_code"] == "search-budget-exhausted"
    assert transport.calls == [], "budget 0: nothing may be asked"


def test_zero_results_on_a_live_budget_path_still_waiting(tmp_path):
    transport = FakeTransport(default="<html><body><p>nothing here</p></body></html>")
    env, code = R.run_stage(dict(BARE), str(tmp_path), transport=transport)
    assert code == 2 and env["reason_code"] == "search-no-results", env


# ------------------------------------------------------------- exit contract

def test_no_gather_restores_the_original_sourcemissing_contract(tmp_path):
    transport = FakeTransport(routes=_search_routes(_fixture("ddg_html.html"),
                                                    "https://example.invalid/back-pain-guide"))
    env, code = R.run_stage(dict(BARE), str(tmp_path), transport=transport,
                            gather=False)
    assert code == R.EXIT["rejected"] == 4
    assert env["outcome"] == "rejected"
    assert env["reason_code"] == "SOURCES_MISSING"
    assert transport.calls == []


def test_bare_brief_is_never_rejected_on_sourcemissing(tmp_path):
    """SOURCES_MISSING stays reachable only where no gathering happened.

    A bare brief whose search DID return sources leaves the validator's
    SOURCES_MISSING branch entirely; what still stops it is the pre-existing
    sub-avatar gate, which this unit does not own (documented in the PR body).
    """
    transport = FakeTransport(routes=_search_routes(_fixture("ddg_html.html"),
                                                    "https://example.invalid/back-pain-guide"))
    env, code = R.run_stage(dict(BARE), str(tmp_path), transport=transport)
    assert env["reason_code"] != "SOURCES_MISSING"
    assert transport.calls, "gather must have run"
    # the one exit-4 path left for a bare brief is the untouched sub-avatar gate
    assert (code, env["reason_code"]) == (4, "sub-avatar-incomplete")
    assert any("sub_avatar" in e for e in env["data"]["errors"]), env


def test_parked_contract_untouched_for_a_claim_no_page_cites(tmp_path):
    routes = _search_routes(_fixture("ddg_html.html"),
                            "https://example.invalid/back-pain-guide")
    brief = dict(BARE)
    brief["claims"] = [{"text": "A client claim that no fetched page contains verbatim anywhere in its body text."}]
    brief["sub_avatar"] = dict(SUB_AVATAR)
    env, code = R.run_stage(brief, str(tmp_path), transport=FakeTransport(routes=routes))
    assert code == R.EXIT["parked"] == 3, env
    assert env["reason_code"] == "claims-without-source"


def test_claim_contained_in_a_fetched_page_gets_that_citation(tmp_path):
    claim_text = "  Chronic back pain keeps millions of adults awake at night,\nand most of them never mention it to a doctor.  "
    routes = _search_routes(_fixture("ddg_html.html"),
                            "https://example.invalid/back-pain-guide")
    brief = dict(BARE)
    brief["claims"] = [{"text": claim_text}]
    brief["sub_avatar"] = dict(SUB_AVATAR)
    transport = FakeTransport(routes=routes)
    g = G.gather(brief, transport=transport)
    assert g["status"] == "ok"
    cited = [c for c in g["claims"] if c.get("text") == claim_text][0]
    assert cited["source"].startswith("gsrc-")
    index = int(cited["source"].split("-")[1]) - 1
    assert g["sources"][index]["url"] == "https://example.invalid/back-pain-guide"
    env, code = R.run_stage(brief, str(tmp_path), transport=transport)
    assert code == R.EXIT["ok"], env
    evidence = json.loads((tmp_path / "research" / "evidence.json").read_text())
    filed = [c for c in evidence["claims"] if c["text"] == claim_text.strip()]
    assert filed and filed[0]["source"] == cited["source"], evidence["claims"]
    assert filed[0]["status"] == "PASS"


def test_missing_essentials_stays_waiting_before_any_network(tmp_path):
    transport = OfflineTransport()
    env, code = R.run_stage({"audience": "adults"}, str(tmp_path), transport=transport)
    assert code == 2 and env["reason_code"] == "missing-essentials"
    assert transport.calls == 0


def test_cli_exit_codes_and_envelope(tmp_path, capsys, monkeypatch):
    routes = _search_routes(_fixture("ddg_html.html"),
                            "https://example.invalid/back-pain-guide")
    monkeypatch.setattr(G, "default_transport", FakeTransport(routes=routes))
    brief_file = tmp_path / "brief.json"
    brief_file.write_text(json.dumps(_complete(BARE)), encoding="utf-8")
    outdir = tmp_path / "run"

    code = R.main(["--brief", str(brief_file), "--outdir", str(outdir)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0, payload
    assert payload["schema_version"] == "blackceo.research/v1"
    assert payload["command"] == "research" and payload["outcome"] == "ok"
    assert payload["state_version"]["current"] == payload["run_id"]

    code = R.main(["--brief", str(brief_file), "--outdir", str(outdir),
                   "--no-gather"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 4 and payload["reason_code"] == "SOURCES_MISSING"

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    code = R.main(["--brief", str(bad), "--outdir", str(outdir)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1 and payload["reason_code"] == "brief-unreadable"


def test_cli_offline_degrades_to_waiting_exit_2(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(G, "default_transport", OfflineTransport())
    brief_file = tmp_path / "brief.json"
    brief_file.write_text(json.dumps(dict(BARE)), encoding="utf-8")
    code = R.main(["--brief", str(brief_file), "--outdir", str(tmp_path / "run"),
                   "--budget", "3"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 2, payload
    assert payload["outcome"] == "waiting"
    assert payload["reason_code"] in ("search-offline", "search-budget-exhausted")


def test_script_mode_cli_imports_gather_as_a_sibling(tmp_path):
    """The documented invocation is `python3 research.py --brief ... --outdir
    ...`, where research.py binds gather as a sibling module rather than a
    package member. `--budget 0` keeps this subprocess offline: nothing may be
    asked, so no socket is opened in the default run either."""
    assert R.EXIT == {"ok": 0, "waiting": 2, "parked": 3, "rejected": 4, "error": 1}
    script = os.path.join(HERE, "research.py")
    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps(dict(BARE)), encoding="utf-8")
    outdir = str(tmp_path / "run")

    proc = subprocess.run(
        [sys.executable, script, "--brief", str(brief), "--outdir", outdir,
         "--budget", "0"], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2, (proc.returncode, proc.stdout, proc.stderr)
    assert json.loads(proc.stdout)["reason_code"] == "search-budget-exhausted"

    proc = subprocess.run(
        [sys.executable, script, "--brief", str(brief), "--outdir", outdir,
         "--no-gather"], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 4, (proc.returncode, proc.stdout, proc.stderr)
    assert json.loads(proc.stdout)["reason_code"] == "SOURCES_MISSING"


def test_first_claim_never_files_nav_glued_or_chrome_text():
    prose = ("Chronic back pain keeps millions of adults awake at night, "
             "and most of them never mention it to a doctor.")
    assert G.first_claim(prose) == prose
    # unfinished line (navigation / heading soup)
    assert G.first_claim("FindCare Cardiology Dentistry Neurology Orthopedic "
                         "Surgery Pediatrics Primary Care Psychiatry Urology") == ""
    # two chunks glued together without a space
    assert G.first_claim("Melatonin Dosage: How Much Melatonin to Take94% of Us "
                         "Drink Caffeinated Beverages.") == ""
    # site chrome is skipped, the real sentence behind it still filed
    chrome = ("Medically reviewed by a board certified physician, written by the "
              "editorial team. Sleep and stress feed each other in both directions "
              "for most adults over fifty, night after night.")
    assert G.first_claim(chrome).startswith("Sleep and stress")
    assert G.first_claim("") == ""


def test_binary_and_claimless_pages_never_become_sources():
    pdf_body = b"%PDF-1.7\n1 0 obj\n" + b"stream data " * 40
    nav_page = ("<html><body><p>FindCare Cardiology Dentistry Neurology "
                "Orthopedic Surgery Pediatrics Primary Care Psychiatry Urology "
                "Search Healthline</p></body></html>")
    routes = {
        "https://html.duckduckgo.com/html/": _fixture("ddg_html.html"),
        "https://lite.duckduckgo.com/lite/": _fixture("ddg_html.html"),
        "https://example.invalid/back-pain-guide": pdf_body,
        "https://docs.example.org/guide": nav_page,
        "https://example.invalid/sleep-and-stress": _fixture("article.html"),
    }
    transport = FakeTransport(routes=routes)
    g = G.gather(dict(BARE), transport=transport)
    assert g["status"] == "ok", g
    urls = [s["url"] for s in g["sources"]]
    assert "https://example.invalid/back-pain-guide" not in urls, "PDF must drop"
    assert "https://docs.example.org/guide" not in urls, "nav-only page must drop"
    assert urls == ["https://example.invalid/sleep-and-stress"], urls
    assert any("binary" in e for e in g["errors"]), g["errors"]
    assert g["claims"], g
    for claim in g["claims"]:
        assert claim["text"].endswith((".", "!", "?")), claim


# -------------------------------------------------------------- live (opt-in)

def test_live_smoke_one_keyless_search():
    """Opt-in only: skipped unless DSAF_RESEARCH_LIVE_SMOKE=1, and never run
    by the script-style runner (which has no pytest to skip through)."""
    if os.environ.get("DSAF_RESEARCH_LIVE_SMOKE") != "1":
        if pytest is not None:
            pytest.skip("live smoke gated on DSAF_RESEARCH_LIVE_SMOKE=1")
        print("skip: live smoke gated on DSAF_RESEARCH_LIVE_SMOKE=1")
        return
    g = G.gather({"offer": "sleep and stress guide for adults",
                  "audience": "adults over 50", "action": "read the guide"},
                 budget=20.0, timeout=6.0, max_queries=1, max_fetches=3)
    assert g["status"] in (G.STATUS_OK, G.STATUS_EMPTY, G.STATUS_OFFLINE,
                           G.STATUS_BUDGET), g["status"]
    assert isinstance(g["sources"], list) and isinstance(g["queries"], list)
    for source in g["sources"]:
        assert source["url"].startswith("http")
        assert source["retrieved"]


class _Captured:
    """capsys stand-in: buffers sys.stdout from construction to readouterr()."""

    def __init__(self):
        self._buf = io.StringIO()
        self._old = sys.stdout
        sys.stdout = self._buf

    def readouterr(self):
        out = self._buf.getvalue()
        self._buf.seek(0)
        self._buf.truncate(0)
        return type("Captured", (), {"out": out, "err": ""})()

    def close(self):
        sys.stdout = self._old


class _Patch:
    """monkeypatch stand-in: records every setattr and restores on undo()."""

    def __init__(self):
        self._undo = []

    def setattr(self, obj, name, value):
        self._undo.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def close(self):
        for obj, name, old in reversed(self._undo):
            setattr(obj, name, old)
        self._undo.clear()


def _run_all():
    """Script-style runner (no pytest): injects stdlib stand-ins for the three
    pytest fixtures these tests use and reports one line per test. Returns an
    exit code, so `python3 test_research_gather.py` is still a real test run."""
    passed, failures = 0, []
    for name, fn in sorted(globals().items()):
        if not (name.startswith("test_") and callable(fn)):
            continue
        kwargs, teardown = {}, []
        unknown = [p for p in inspect.signature(fn).parameters
                   if p not in ("tmp_path", "capsys", "monkeypatch")]
        if unknown:
            failures.append(name)
            print("FAIL: %s: no script-style runner for fixture(s) %s"
                  % (name, unknown))
            continue
        for param in inspect.signature(fn).parameters:
            if param == "tmp_path":
                kwargs[param] = Path(tempfile.mkdtemp(prefix="research-engine-"))
            elif param == "capsys":
                kwargs[param] = _Captured()
                teardown.append(kwargs[param])
            else:
                kwargs[param] = _Patch()
                teardown.append(kwargs[param])
        error = None
        try:
            fn(**kwargs)
        except Exception as exc:            # noqa: BLE001 - report, keep running
            error = exc
        finally:
            for item in teardown:
                item.close()
            if "tmp_path" in kwargs:
                shutil.rmtree(kwargs["tmp_path"], ignore_errors=True)
        if error is None:
            passed += 1
            print("ok: %s" % name)
        else:
            failures.append(name)
            print("FAIL: %s: %s" % (name, error))
    print("%d passed, %d failed" % (passed, len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    if pytest is not None:
        sys.exit(pytest.main([__file__, "-q"]))
    sys.exit(_run_all())
