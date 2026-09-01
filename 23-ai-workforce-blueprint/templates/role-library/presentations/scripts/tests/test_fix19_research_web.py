"""FIX 19 -- research phase gets real web access (spec PROOF tests).

Spec contract under test (PRESENTATION-DEPT-FIX-SPEC.md, FIX 19):

  1. Brave Search API primary pathway, gated by BRAVE_SEARCH_API_KEY. Key
     absence parks BEFORE synthesis (a missing key must fail before any model
     call; the caller's park path maps ResearchWebError -> parked, not a no-web
     dispatch).
  2. Cap retrieval at 12 unique fetched URLs per deck; the 13th unique URL is
     refused WITHOUT a fetch. One network fetch per cited (canonical) URL --
     repeated citations reuse the cached response.
  3. Public http(s) targets only: loopback/private/link-local refused; every
     REDIRECT HOP re-checked against the same public-only policy against the
     freshly resolved address (never a reused resolution); redirects capped at
     2; response body capped at 2 MB (over-cap REFUSES, never truncated);
     request time capped at 15 s.
  4. The retrieval ledger records query, canonical URL, retrieval time, HTTP
     status, content hash, extraction length, and citation anchors -- never
     the API key.

Every network boundary is an injectable transport (search_transport /
fetch_transport), so every test here runs fully offline and never touches the
network; the DNS-level guard is proven with a monkeypatched resolver.

Red/green discipline: the redirect + cap tests fail on the stock-urlopen
implementation (auto-follows redirects; over-cap truncates) and pass here.
"""

import hashlib
import io
import json
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job import research_web as rw
from presentation_job.research_web import (
    BoundedFetcher,
    MAX_BODY_BYTES,
    MAX_REDIRECTS,
    MAX_UNIQUE_URLS,
    MIN_EXTRACT_CHARS,
    ResearchWebError,
    canonical_url,
    derive_queries,
    registered_domain,
    run_research_retrieval,
)

# ---------------------------------------------------------------------------
# Stub transports: zero network in every test.
# ---------------------------------------------------------------------------

PAGE_BODY = (
    "<html><head><title>Doc</title></head><body>"
    "<p>Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu</p>"
    + ("<p>real substantive paragraph content for extraction. </p>" * 12)
    + "</body></html>"
)


def _fake_fetch_ok(url: str = None, body: str = PAGE_BODY):
    if url is None:
        return lambda u: (200, canonical_url(u), body)
    return 200, canonical_url(url), body


def _brave_transport(results_by_query):
    def transport(query: str):
        rows = results_by_query.get(query) or []
        return list(rows)
    return transport


def _brave_result(n: int, host: str = "example.com") -> dict:
    return {"url": f"https://host{n}.{host}/page-{n}?ref=ad",
            "title": f"Result {n}", "description": "desc"}


# ---------------------------------------------------------------------------
# 1. Ledger contract: fields present, key never recorded.
# ---------------------------------------------------------------------------

def test_ledger_records_query_url_status_hash_and_never_key(tmp_path, monkeypatch):
    env = {"BRAVE_SEARCH_API_KEY": "sk-test-SECRET-VALUE"}
    monkeypatch.setattr(rw, "_read_secret_named", lambda name: None)
    results = [_brave_result(1)]
    fetcher = BoundedFetcher(
        tmp_path, fetch_transport=_fake_fetch_ok(), search_transport=None,
        env=env)
    row = fetcher.fetch_page(results[0]["url"], query="q1")
    assert row["ok"] is True
    assert row["extraction_length"] >= MIN_EXTRACT_CHARS
    assert row["content_sha256"]
    ledger = json.loads(fetcher.ledger_path().read_text(encoding="utf-8"))
    r = ledger["rows"][0]
    for field in ("query", "canonical_url", "retrieved_at", "status",
                  "content_sha256", "extraction_length"):
        assert field in r, f"ledger row missing {field}: {sorted(r)}"
    text = json.dumps(ledger)
    assert "sk-test-SECRET-VALUE" not in text
    assert "SECRET" not in text


def test_ledger_file_is_retrieval_ledger_jsonl(tmp_path):
    fetcher = BoundedFetcher(tmp_path)
    fetcher.fetch_page("https://example.com/x", query="q")
    assert fetcher.ledger_path().name == "retrieval_ledger.jsonl"
    assert (tmp_path / "working" / "research" /
            "retrieval_ledger.jsonl").is_file()


# ---------------------------------------------------------------------------
# 2. URL cap: 12 unique fetched; the 13th is refused WITHOUT a fetch.
# ---------------------------------------------------------------------------

def test_thirteenth_unique_url_refused_without_fetch(tmp_path, monkeypatch):
    env = {"BRAVE_SEARCH_API_KEY": "k"}
    monkeypatch.setattr(rw, "_read_secret_named", lambda name: None)
    queries = derive_queries("wellness coaching")
    per_query: dict = {q: [_brave_result(i + 1) for i in range(3)]
                       for i, q in enumerate(queries)}
    fetcher = BoundedFetcher(
        tmp_path, fetch_transport=_fake_fetch_ok(), env=env,
        search_transport=_brave_transport(per_query))
    all_urls = [f"https://src{i}.example.com/p{i}" for i in range(13)]
    network_calls = {"n": 0}

    def counting_fetch(url):
        network_calls["n"] += 1
        return 200, canonical_url(url), PAGE_BODY

    for url in all_urls:
        fetcher.fetch_page(url, query="q")
    assert len(fetcher.fetched) == MAX_UNIQUE_URLS
    cap_refusals = [r for r in fetcher.refusals if "cap" in r]
    assert cap_refusals, "the 13th unique URL must be recorded as a cap refusal"
    # 13 URLs attempted, exactly 12 fetched: URL #13 costs zero network.
    fetcher2 = BoundedFetcher(
        tmp_path / "probe", fetch_transport=counting_fetch, env=env,
        search_transport=_brave_transport(per_query))
    for url in all_urls:
        fetcher2.fetch_page(url, query="q")
    assert network_calls["n"] == MAX_UNIQUE_URLS, (
        f"13 URLs attempted must cost exactly {MAX_UNIQUE_URLS} fetches; "
        f"got {network_calls['n']}")
    calls = {"n": 0}

    def counting(url):
        calls["n"] += 1
        return 200, canonical_url(url), PAGE_BODY

    fetcher3 = BoundedFetcher(
        tmp_path / "probe2", fetch_transport=counting, env=env,
        search_transport=_brave_transport(per_query))
    for url in all_urls:
        fetcher3.fetch_page(url, query="q")
    assert calls["n"] == MAX_UNIQUE_URLS, (
        f"expected exactly {MAX_UNIQUE_URLS} network fetches; got {calls['n']}")


def test_duplicate_citation_refsuses_cache_not_network(tmp_path):
    calls = {"n": 0}

    def counting(url):
        calls["n"] += 1
        return 200, canonical_url(url), PAGE_BODY

    fetcher = BoundedFetcher(tmp_path, fetch_transport=counting)
    u = "https://example.com/one-source"
    fetcher.fetch_page(u)
    fetcher.fetch_page(u)  # repeated citation
    assert calls["n"] == 1  # ONE network fetch per URL

# ---------------------------------------------------------------------------
# 3. Public-URL policy + redirect policy through _policy_fetch.
# ---------------------------------------------------------------------------


def test_policy_fetch_refuses_private_and_loopback_targets():
    for url in ("http://127.0.0.1/x", "http://localhost/x",
                "http://10.0.0.5/x", "http://169.254.1.1/x",
                "http://[::1]/x", "http://host.internal/x",
                "ftp://example.com/x"):
        with pytest.raises(ResearchWebError):
            rw._policy_fetch(url)


def test_policy_fetch_refuses_hostname_resolving_to_private_ip(monkeypatch):
    monkeypatch.setattr(rw, "_resolve_host_ip", lambda host: "192.168.1.10")
    with pytest.raises(ResearchWebError):
        rw._policy_fetch("https://example.com/page")


def test_redirect_cap_at_two_hops(monkeypatch):
    """3 redirects must raise: MAX_REDIRECTS=2. Each hop is re-checked."""
    hops = []

    class FakeHTTPError(urllib.error.HTTPError):
        def __init__(self, url, code, location):
            super().__init__(url, code, "redir", {}, io.BytesIO(b""))
            self.headers = {"Location": location}

    def hop3(url):
        hops.append(url)
        raise FakeHTTPError(url, 302, f"https://hop{len(hops)}.example.com/x")

    monkeypatch.setattr(rw, "_fetch_one_hop", hop3)
    monkeypatch.setattr(rw, "_resolve_host_ip",
                        lambda host: "93.184.216.34")
    with pytest.raises(ResearchWebError, match="redirect cap"):
        rw._policy_fetch("https://origin.example.com/start")
    # origin + 2 hops attempted, the 3rd 302 must be the refusal point:
    assert len(hops) == MAX_REDIRECTS + 1


def test_two_redirects_succeed_and_final_url_canonicalized(monkeypatch):
    seq = ["https://origin.example.com/start",
           "https://mid.example.com/r1",
           "https://final.example.com/landing"]

    class FakeResponse:
        def __init__(self):
            self._url = seq[-1]
        def read(self, n=-1):
            return b""
        def getcode(self):
            return 200
        def close(self):
            pass

    state = {"i": 0}

    def hop(url):
        i = state["i"]
        state["i"] += 1
        if i < 2:
            raise _FakeRedirect(url, seq[i + 1])
        resp = FakeResponse()
        return resp

    class _FakeRedirect(urllib.error.HTTPError):
        def __init__(self, url, location):
            super().__init__(url, 302, "redir", {}, io.BytesIO(b""))
            self.headers = {"Location": location}

    monkeypatch.setattr(rw, "_fetch_one_hop", hop)
    monkeypatch.setattr(rw, "_resolve_host_ip",
                        lambda host: "93.184.216.34")
    status, canon, body = rw._policy_fetch(seq[0])
    assert status == 200
    assert canon == canonical_url(seq[2])
    assert state["i"] == 3  # exactly three one-hop requests: no opener follows


def test_every_redirect_hop_re_resolves_dns(monkeypatch):
    """The rebind guard: hop 1 resolves public; hop 2 (a redirect) resolves
    PRIVATE -- the fetch must refuse, never reuse hop 1's resolution."""
    seq = ["https://origin.example.com/a", "https://rebind.example.com/b"]

    class _FakeRedirect(urllib.error.HTTPError):
        def __init__(self, url, location):
            super().__init__(url, 302, "redir", {}, io.BytesIO(b""))
            self.headers = {"Location": location}

    resolutions = []

    def resolve(host):
        resolutions.append(host)
        return "93.184.216.34" if host.startswith("origin") else "10.1.2.3"

    def hop(url):
        if "origin" in url:
            raise _FakeRedirect(url, seq[1])
        return None

    monkeypatch.setattr(rw, "_fetch_one_hop", hop)
    monkeypatch.setattr(rw, "_resolve_host_ip", resolve)
    with pytest.raises(ResearchWebError, match="public"):
        rw._policy_fetch(seq[0])
    assert "rebind.example.com" in resolutions


def test_over_size_body_refused_not_truncated(monkeypatch):
    big = "x" * (MAX_BODY_BYTES + 1)

    class FakeRedirectOrResp:
        def read(self, n=-1):
            # hand back 64KB chunks like a real stream
            for i in range(0, len(big), 65536):
                yield None
            return
        def getcode(self):
            return 200
        def close(self):
            pass

    class Resp:
        def __init__(self):
            self._it = (big[i:i + 65536]
                        for i in range(0, len(big), 65536))
        def read(self, n=-1):
            try:
                return next(self._it)
            except StopIteration:
                return b""
        def getcode(self):
            return 200
        def close(self):
            pass

    monkeypatch.setattr(rw, "_fetch_one_hop", lambda url: Resp())
    monkeypatch.setattr(rw, "_resolve_host_ip", lambda host: "93.184.216.34")
    with pytest.raises(ResearchWebError, match="MAX_BODY_BYTES"):
        rw._policy_fetch("https://example.com/huge")


def test_stock_urlopen_would_auto_redirect():
    """Red-proof control: the DEFAULT opener follows redirects itself. This is
    exactly why _fetch_one_hop builds a redirect-free opener."""
    handlers = urllib.request.build_opener().handlers
    assert any(h.__class__ is urllib.request.HTTPRedirectHandler
               for h in handlers)
    # and our one-hop opener must NOT follow: its only redirect handler is the
    # _NoRedirect subclass (which build_opener dedupes against the default by
    # subclass relationship, so the stock follow-behavior handler is absent)
    ours = rw._NoRedirect()
    opener = urllib.request.build_opener(ours, urllib.request.HTTPSHandler())
    redirect_handlers = [h for h in opener.handlers
                         if isinstance(h, urllib.request.HTTPRedirectHandler)]
    assert len(redirect_handlers) == 1
    assert isinstance(redirect_handlers[0], rw._NoRedirect)
    assert type(redirect_handlers[0]) is rw._NoRedirect


# ---------------------------------------------------------------------------
# 4. Brave gating: key absence parks BEFORE any search/fetch/synthesis.
# ---------------------------------------------------------------------------

def test_missing_brave_key_parks_before_any_fetch(tmp_path, monkeypatch):
    monkeypatch.setattr(rw, "_read_secret_named", lambda name: None)
    fetch_calls = {"n": 0}

    def fetch(url):
        fetch_calls["n"] += 1
        return 200, canonical_url(url), PAGE_BODY

    with pytest.raises(ResearchWebError, match="BRAVE_SEARCH_API_KEY"):
        run_research_retrieval(
            tmp_path, topic="leadership coaching",
            fetch_transport=fetch, env={})
    assert fetch_calls["n"] == 0, (
        "no page may be fetched when the search key is absent -- the key gate "
        "fires before synthesis, before fetch, before anything")


def test_brave_auth_failure_and_quota_park(tmp_path, monkeypatch):
    env = {"BRAVE_SEARCH_API_KEY": "k"}
    monkeypatch.setattr(rw, "_read_secret_named", lambda name: None)
    for code, word in ((401, "authentication"), (429, "quota")):
        def failing_urlopen(req, timeout=None, code=code):
            raise urllib.error.HTTPError(rw.BRAVE_SEARCH_URL, code, "no",
                                         {}, io.BytesIO(b""))
        monkeypatch.setattr(rw.urllib.request, "urlopen", failing_urlopen)
        fetcher = BoundedFetcher(tmp_path / f"p{code}",
                                 env=env)
        with pytest.raises(ResearchWebError, match=word):
            fetcher.brave_search("q")


# ---------------------------------------------------------------------------
# 5. Relevance contract (evaluate_anchor) -- the FIX 20-shared verdict.
# ---------------------------------------------------------------------------

GOOD_BODY = ("This page discusses transformational leadership coaching with "
             "substantial detail. " * 20) + " " + \
    "transformational leadership coaching improves team performance measurably"
_ = GOOD_BODY


def test_anchor_exact_phrase_supported(tmp_path):
    # Exact-phrase path requires an anchor of >= 8 normalized words (spec:
    # "exact normalized anchor phrase of >= 8 words"); a 6-word anchor with a
    # full hit correctly resolves via the token path instead.
    body_text = ("filler words here for length padding in this page. " * 60) + \
        " Leadership coaching measurably improves the performance of the team."
    fetcher = BoundedFetcher(tmp_path)
    row = {"url": "https://example.com/a", "status": 200,
           "extracted": body_text}
    verdict = fetcher.evaluate_anchor(
        row, "leadership coaching measurably improves the performance of the team")
    assert verdict["supported"] is True
    assert verdict["basis"] == "exact-phrase"


def test_anchor_under_200_chars_fails(tmp_path):
    fetcher = BoundedFetcher(tmp_path)
    row = {"url": "https://example.com/a", "status": 200, "extracted": "too short"}
    verdict = fetcher.evaluate_anchor(row, "leadership coaching improves team performance")
    assert verdict["supported"] is False


def test_anchor_token_60pct_path(tmp_path):
    # No >=8-word exact phrase anywhere, but 4 of the anchor's 6 non-stopword
    # tokens (67% >= 60%) appear scattered in the text -> token path.
    body = ("coaching is central. leadership matters. teams thrive. "
            "measurable results follow. " * 80)
    fetcher = BoundedFetcher(tmp_path)
    row = {"url": "https://example.com/a", "status": 200, "extracted": body}
    verdict = fetcher.evaluate_anchor(row, "coaching frameworks leadership teams measurable results")
    assert verdict["supported"] is True
    assert verdict["basis"] == "token-60pct"


def test_resolving_but_irrelevant_page_fails_anchor(tmp_path):
    body = ("unrelated content about pottery and ceramics and glazes. " * 200)
    fetcher = BoundedFetcher(tmp_path)
    row = {"url": "https://example.com/a", "status": 200, "extracted": body}
    verdict = fetcher.evaluate_anchor(row, "leadership coaching improves measurable team performance")
    assert verdict["supported"] is False


# ---------------------------------------------------------------------------
# 6. run_research_retrieval end-to-end (offline stubs): ledger written,
#    kill-switch parks, no-web fallback impossible.
# ---------------------------------------------------------------------------

def test_run_research_retrieval_happy_path_writes_ledger(tmp_path, monkeypatch):
    env = {"BRAVE_SEARCH_API_KEY": "k"}
    monkeypatch.setattr(rw, "_read_secret_named", lambda name: None)
    queries = derive_queries("executive presence")
    per_query = {q: [_brave_result(1), _brave_result(2)] for q in queries}
    fetches = {"n": 0}

    def fetch(url):
        fetches["n"] += 1
        return 200, canonical_url(url), PAGE_BODY

    out = run_research_retrieval(
        tmp_path, topic="executive presence",
        fetch_transport=fetch,
        search_transport=_brave_transport(per_query), env=env)
    assert fetches["n"] == 2
    assert out["network_fetches"] == 2
    ledger = json.loads((tmp_path / "working" / "research" /
                         "retrieval_ledger.jsonl").read_text(encoding="utf-8"))
    assert len(ledger["rows"]) == 2
    for row in ledger["rows"]:
        assert row["status"] == 200
        assert row["query"]


def test_kill_switch_flag_zero_parks(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESENTATION_RESEARCH_WEB_FETCH", "0")
    with pytest.raises(ResearchWebError, match="kill-switch"):
        run_research_retrieval(tmp_path, topic="t")


def test_dispatcher_parks_research_on_researchweberror(tmp_path, monkeypatch):
    """The dispatcher contract: a ResearchWebError from the web module parks the
    phase -- never a no-web model dispatch claiming research."""
    sys.path.insert(0, str(_scripts_dir))
    from presentation_job import dispatcher as disp

    class FakeWeb:
        class ResearchWebError(RuntimeError):
            pass
        MIN_EXTRACT_CHARS = MIN_EXTRACT_CHARS

        @staticmethod
        def run_research_retrieval(run_dir, topic):
            raise FakeWeb.ResearchWebError(
                "BRAVE_SEARCH_API_KEY absent from the secrets store")
        @staticmethod
        def canonical_url(u):
            return canonical_url(u)
    monkeypatch.setattr(disp, "_research_web", FakeWeb)
    order = {"produces_artifact": ["working/research/brief-x.md"],
             "owning_role": "deep-research-specialist-presentations"}
    result = disp._dispatch_research_phase(
        tmp_path, order, dept_root=_scripts_dir, phase_obj=None,
        worker_id="w1")
    assert result.status == "error"
    assert not (tmp_path / "working" / "research" / "brief-x.md").exists()


def test_dispatcher_parks_when_research_web_module_missing(tmp_path, monkeypatch):
    from presentation_job import dispatcher as disp

    class FakeWeb:
        class ResearchWebError(RuntimeError):
            pass
        MIN_EXTRACT_CHARS = MIN_EXTRACT_CHARS

        @staticmethod
        def run_research_retrieval(run_dir, topic):
            raise FakeWeb.ResearchWebError("no module")
        @staticmethod
        def canonical_url(u):
            return u
    monkeypatch.setattr(disp, "_research_web", None)
    order = {"produces_artifact": ["working/research/brief-x.md"]}
    result = disp._dispatch_research_phase(
        tmp_path, order, dept_root=_scripts_dir, phase_obj=None,
        worker_id="w1")
    assert result.status == "error"


# ---------------------------------------------------------------------------
# Canonicalization + registered-domain helpers (cited-domain diversity inputs)
# ---------------------------------------------------------------------------

def test_canonical_url_dedupes_variants():
    assert canonical_url("HTTPS://WWW.Example.com:443/a/?q=2#frag") == \
        canonical_url("https://www.example.com/a/?q=2")
    assert canonical_url("https://example.com/a") != \
        canonical_url("https://example.com/b")


def test_registered_domain_variants():
    assert registered_domain("https://www.acme.com/x") == "acme.com"
    assert registered_domain("https://blog.acme.com/") == "blog.acme.com"