"""presentation_job/research_web.py -- FIX 19: real web access for research.

THE ONE-SENTENCE PROBLEM THIS FIXES: the P-0.5-RESEARCH phase was a no-web DeepSeek
call told to emit `research_complete:true` plus 8+ URLs. Nothing was ever retrieved;
the brief invented plausible-looking sources, and build_deck's mechanical gates
counted URL strings and shipped decks whose "sources" resolved to nothing.

Fix-spec FIX 19 (PRESENTATION-DEPT-FIX-SPEC.md):

  * Brave Search API is the PRIMARY search pathway, gated by BRAVE_SEARCH_API_KEY
    from the secrets store. Key absence / auth failure / exhausted quota parks
    P-0.5-RESEARCH with a configuration error -- it must NOT fall back to a no-web
    model claiming research.
  * Cap retrieval at 12 unique fetched URLs per deck and ONE network fetch per
    (canonical) URL -- repeated citations reuse the cached response.
  * Only public http/https targets: block loopback/private/link-local destinations,
    cap redirects at 2, response body at 2 MB, request time at 15 s.
  * The retrieval ledger records, per row: query, canonical URL, retrieval time,
    HTTP status, content hash, extraction length, and the citation anchors
    supported -- never the API key.
  * The relevance contract (binding here, consumed by FIX 20's citation gate):
    HTTP 200 after allowed redirects, >= 200 chars of extracted text, and either an
    exact normalized anchor phrase of >= 8 words or >= 60% of the anchor's
    non-stopword tokens present in the extracted text. A URL that merely resolves
    but does not support its anchor FAILS.
  * PRESENTATION_RESEARCH_WEB_FETCH emergency `0`: stops outbound research and
    parks P-0.5-RESEARCH with a configuration error. It may never restore the old
    no-web model / fictional-URL path.

TRANSPORTS: every network boundary is an injectable callable -- `search_transport`
and `fetch_transport` -- mirroring capacity.probe_one_provider's existing pattern so
proofs stub the transport in-process and never touch the network. The default
transports are plain urllib with the bounds above. No secret value is ever printed,
logged, or written to the ledger: the key is read only for the request header.
"""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants (the DEFAULT RULING values; operator-configurable, never per-callsite)
# ---------------------------------------------------------------------------
def _utcnow() -> str:
    from presentation_job.state import utcnow
    return utcnow()


BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
MAX_UNIQUE_URLS = 12          # 13th unique URL is refused WITHOUT a fetch
MAX_REDIRECTS = 2
MAX_BODY_BYTES = 2 * 1024 * 1024
FETCH_TIMEOUT_S = 15
RESULTS_PER_QUERY = 8
MIN_QUERIES = 3               # brief needs >= 8 sources across >= 6 domains
MAX_QUERIES = 6
MIN_EXTRACT_CHARS = 200       # relevance floor for a fetched page
ANCHOR_MIN_WORDS = 8          # exact-phrase path
ANCHOR_TOKEN_MATCH = 0.60     # token path (>= 60% of anchor's non-stopword tokens)
LEDGER_NAME = "retrieval_ledger.jsonl"

FLAG_ENV = "PRESENTATION_RESEARCH_WEB_FETCH"


class ResearchWebError(RuntimeError):
    """Parks P-0.5-RESEARCH: configuration/key/budget failure -- the phase must
    NOT fall back to a no-web model claiming research."""


# ---------------------------------------------------------------------------
# Feature flag (same strip discipline as _prompt_parallel_enabled in dispatcher.py)
# ---------------------------------------------------------------------------
def web_fetch_enabled() -> bool:
    """Default ON. The only value that disables is exactly "0" (quotes/whitespace
    stripped, so an EMPTY value counts as unset, never OFF)."""
    raw = os.environ.get(FLAG_ENV)
    if raw is None:
        return True
    return raw.strip().strip("'\"") != "0"


# ---------------------------------------------------------------------------
# Secret resolution -- same posture as dispatcher._load_deepseek_key: the value
# exists only for the request header; presence is all callers may surface.
# ---------------------------------------------------------------------------
def _read_secret_named(name: str) -> Optional[str]:
    value = (os.environ.get(name) or "").strip()
    if value:
        return value
    env_path = Path.home() / ".openclaw" / "secrets" / ".env"
    fallback = Path.home() / ".openclaw" / "secrets" / "secrets.env"
    for path in (env_path, fallback):
        try:
            if not path.is_file():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith(f"{name}="):
                    candidate = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if candidate:
                        return candidate
        except OSError:
            continue
    return None


def brave_key_present(env: Optional[dict] = None) -> bool:
    """Key PRESENCE only. `env` overrides the process environment (the same
    proof-stubbing posture capacity.probe_one_provider uses for its env view)."""
    view = os.environ if env is None else env
    if str(view.get("BRAVE_SEARCH_API_KEY") or "").strip():
        return True
    if env is not None:
        return False  # a fake environment never reads the real secrets files
    return _read_secret_named("BRAVE_SEARCH_API_KEY") is not None


def _brave_key(env: Optional[dict] = None) -> Optional[str]:
    view = os.environ if env is None else env
    value = str(view.get("BRAVE_SEARCH_API_KEY") or "").strip()
    if value:
        return value
    if env is not None:
        return None
    return _read_secret_named("BRAVE_SEARCH_API_KEY")


# ---------------------------------------------------------------------------
# URL safety: public http/https only; no loopback/private/link-local.
# ---------------------------------------------------------------------------
def _is_public_http_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        return False
    if host == "localhost" or host.endswith(".localhost") or host == "0.0.0.0":
        return False
    # IPv6 literal in brackets -> hostname already strips them; pure-ip check
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        addr = None
    if addr is not None:
        return addr.is_global and not addr.is_link_local
    # hostname: reject the reserved placeholder TLDs the citation gate also
    # refuses (.local/.internal/.test/.invalid/.example etc.)
    final = host.rsplit(".", 1)[-1].lower()
    if final in ("local", "internal", "test", "invalid", "example", "localhost"):
        return False
    return True


_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "has",
    "have", "if", "in", "into", "is", "it", "its", "of", "on", "or", "per", "that",
    "the", "their", "then", "these", "they", "this", "to", "was", "were", "will",
    "with",
})


def _normalize_ws(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def registered_domain(url: str) -> str:
    """The registered domain: hostname minus a leading 'www.' (the citation
    gate's dedupe key; the URL cap counts unique URLS, not domains)."""
    host = (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def canonical_url(url: str) -> str:
    """Canonical form used for dedupe + the one-fetch-per-URL guarantee: scheme
    lowercased, host lowercased, default port removed, trailing '/' kept only at
    root, fragment dropped, 'www.' kept (same-document identity)."""
    parts = urllib.parse.urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.port and parts.port not in (80, 443):
        netloc = f"{host}:{parts.port}"
    else:
        netloc = host
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    query = f"?{parts.query}" if parts.query else ""
    return f"{scheme}://{netloc}{path}{query}"


# ---------------------------------------------------------------------------
# Page extraction (pure string ops only -- no external html parser dependency):
# drop script/style/noscript, strip tags, collapse whitespace, drop nav-ish
# lines so boilerplate/navigation does not count toward the 200-char floor.
# ---------------------------------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_TAGS = re.compile(
    r"<(script|style|noscript|svg|head|nav|footer|header|aside|form|null)\b.*?</\1>",
    re.IGNORECASE | re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_NAV_MARKERS = ("skip to content", "sign in", "subscribe", "cookie",
                "all rights reserved", "©", "menu", "privacy policy",
                "terms of service", "log in")


def extract_text(html: str) -> str:
    text = _COMMENT_RE.sub(" ", html)
    text = _BLOCK_TAGS.sub(" ", text)
    text = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h[1-6]>|</tr>", "\n", text,
                  flags=re.IGNORECASE)
    text = _TAG_RE.sub(" ", text)
    try:
        import html as _html
        text = _html.unescape(text)
    except Exception:  # noqa: BLE001 -- unescape is best-effort
        pass
    lines: List[str] = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        low = line.lower()
        if len(line) < 4 and low in ("|", "-", "•", "*"):
            continue
        if any(marker in low for marker in _NAV_MARKERS) and len(line) < 120:
            continue
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The bounded fetch. ONE network fetch per canonical URL (the caller passes the
# cached response for repeats). Redirects are followed manually (max 2) so every
# hop is re-checked against the public-URL policy and the total redirect count
# is bounded -- urllib's stock opener cannot express that contract.
# ---------------------------------------------------------------------------
def _resolve_host_ip(host: str) -> Optional[str]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return None
    for info in infos:
        addr = info[4][0]
        try:
            parsed = ipaddress.ip_address(addr)
        except ValueError:
            continue
        return str(parsed)
    return None


def _host_and_ip_safe(url: str) -> bool:
    """DNS-level re-check: the HOSTNAME must not resolve to a private/link-local
    address (SSRF guard beyond the literal-IP check). Local-only proofs pass a
    stub fetch_transport and never hit this path.

    FIX 19 audit: the spec's "freshly resolved address at fetch time (per fetch
    AND per redirect hop, never a reused resolution)" is enforced by CALLING
    this at every hop of _policy_fetch -- each call re-resolves DNS (the lookup
    is never cached here), so a hostname that rebinds to an internal address
    after an earlier hop is refused."""
    host = (urllib.parse.urlsplit(url).hostname or "").rstrip(".")
    if not host:
        return False
    try:
        ipaddress.ip_address(host)
        return True  # literal IP: the literal policy check already decided
    except ValueError:
        pass
    ip = _resolve_host_ip(host)
    if ip is None:
        return False  # unresolvable host is not a fetchable public target
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return parsed.is_global and not parsed.is_link_local and \
        parsed.is_loopback is False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Redirect handler that NEVER follows: any 3xx response raises the
    HTTPError upward instead. Subclassing HTTPRedirectHandler (and passing the
    instance to build_opener) is what removes the stock auto-follow behavior --
    build_opener skips its default redirect handler when a subclass instance is
    supplied, so this instance is the only redirect handler in the chain."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # urllib's contract: a 3xx with no redirect_request result ends the
        # chain; raising surfaces the response AS an HTTPError the manual
        # loop in _policy_fetch catches and re-checks.
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)


def _fetch_one_hop(url: str) -> Any:
    """ONE HTTP round trip with redirects DISABLED -- the transport primitive
    that makes the manual redirect loop real.

    FIX 19 audit root cause: the pre-audit hop loop called stock
    urllib.request.urlopen(), whose default HTTPRedirectHandler silently
    follows 3xx responses itself. The manual redirect cap and the per-hop
    public-URL recheck never executed -- the first redirect was followed
    transparently by the opener before the loop saw it. Here the
    _NoRedirect handler (the ONLY redirect handler in the opener) raises on
    every 3xx, so each hop is one visible, policy-checked request."""
    opener = urllib.request.build_opener(_NoRedirect(),
                                         urllib.request.HTTPSHandler())
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (presentations research fetch)",
                 "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5"},
    )
    return opener.open(req, timeout=FETCH_TIMEOUT_S)


def _read_capped_body(opened: Any) -> str:
    """Read the response body under MAX_BODY_BYTES. A body exceeding the cap
    raises ResearchWebError rather than silently truncating (the truncated
    tail could legitimately hold the anchor text a passing verdict would
    otherwise claim)."""
    body = b""
    while True:
        chunk = opened.read(65536)
        if not chunk:
            break
        if isinstance(chunk, str):  # defensive: str-yielding stubs in proofs
            chunk = chunk.encode("utf-8", errors="replace")
        body += chunk
        if len(body) > MAX_BODY_BYTES:
            raise ResearchWebError(
                f"response body exceeds MAX_BODY_BYTES ({MAX_BODY_BYTES}) "
                f"-- refused, never truncated")
    return body.decode("utf-8", errors="replace")


def _policy_fetch(url: str) -> Tuple[int, str, str]:
    """The default fetch transport. Returns (final_status, final_canonical_url,
    body_text). Raises ResearchWebError on any policy refusal -- never returns
    a private-network body.

    The redirect loop is a REAL manual loop: _fetch_one_hop disables urllib's
    auto-redirect handling, so every 3xx hop re-enters this loop body and is
    re-checked against the public-URL policy + a FRESH DNS resolution
    (_host_and_ip_safe) before the next request. Redirects are capped at
    MAX_REDIRECTS; hop 3 raises rather than passing."""
    if not _is_public_http_url(url):
        raise ResearchWebError(
            f"refused: {url!r} is not a public http(s) target")
    if not _host_and_ip_safe(url):
        raise ResearchWebError(
            f"refused: host for {url!r} does not resolve to a public address")
    current = url
    redirects = 0
    for _ in range(MAX_REDIRECTS + 1):
        if not _is_public_http_url(current):
            raise ResearchWebError(
                f"redirect target refused: {current!r} is not public http(s)")
        # Fresh DNS resolution at EVERY hop -- the spec's rebind guard.
        if not _host_and_ip_safe(current):
            raise ResearchWebError(
                f"refused: host for {current!r} does not resolve to a public "
                f"address (re-checked at fetch time)")
        opened: Any = None
        try:
            opened = _fetch_one_hop(urllib.parse.urlunsplit(
                urllib.parse.urlsplit(current)))
            body = _read_capped_body(opened)
            status = int(opened.getcode() or 0)
            # 200-only policy (per FIX 20's binding contract): the gate requires
            # HTTP 200; non-200 final statuses refuse here, never pass.
            if status != 200:
                raise ResearchWebError(f"HTTP {status} (non-200) at {current}")
            return 200, canonical_url(current), body
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308):
                redirects += 1
                if redirects > MAX_REDIRECTS:
                    raise ResearchWebError(
                        f"redirect cap ({MAX_REDIRECTS}) exceeded "
                        f"following {url}") from exc
                loc = exc.headers.get("Location") if exc.headers else None
                if not loc:
                    raise ResearchWebError(
                        f"redirect without Location at {current}") from exc
                current = urllib.parse.urljoin(current, loc)
                continue
            raise ResearchWebError(f"HTTP {exc.code} fetching {url}") from exc
        except (urllib.error.URLError, http.client.HTTPException, socket.timeout,
                TimeoutError, OSError) as exc:
            raise ResearchWebError(
                f"{type(exc).__name__} fetching {url}: {exc}") from exc
        finally:
            try:
                if opened is not None:
                    opened.close()
            except Exception:  # noqa: BLE001
                pass
    raise ResearchWebError(f"unreachable fetching {url}")


class BoundedFetcher:
    """FIX 19's web-fetch capability. Holds the per-deck cap + the fetch cache
    (one network fetch per canonical URL; repeats reuse the cached row).

    `fetch_transport` (injectable): (url) -> (status:int, canonical:str,
    body:str). Default is _policy_fetch. `search_transport` (injectable):
    (query) -> list of result dicts with at least {'url', 'title'}. Default
    posts to the Brave Search API with the header-only key.
    """

    def __init__(self, run_dir: Path, *, max_unique: int = MAX_UNIQUE_URLS,
                 fetch_transport: Optional[Callable[[str], Tuple[int, str, str]]] = None,
                 search_transport: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
                 env: Optional[dict] = None) -> None:
        self.run_dir = run_dir
        self.max_unique = max_unique
        self._fetch_transport = fetch_transport or _policy_fetch
        self._search_transport = search_transport
        self.env = env
        self.cache: Dict[str, Dict[str, Any]] = {}   # canonical -> row
        self.fetched: Dict[str, Dict[str, Any]] = {} # canonical -> row (network hit)
        self.rows: List[Dict[str, Any]] = []         # ledger rows, in order
        self.refusals: List[str] = []

    # -- ledger -------------------------------------------------------------
    def ledger_path(self) -> Path:
        return self.run_dir / "working" / "research" / LEDGER_NAME

    def _ledger_view(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """The on-disk ledger view of a row: the spec's fields (query, canonical
        URL, retrieval time, HTTP status, content hash, extraction length,
        citation anchors) -- NEVER the API key, NEVER the full page text (a
        bounded preview only, so the ledger stays a retrieval record)."""
        view = {k: v for k, v in row.items() if k != "extracted"}
        if "extracted" in row and isinstance(row.get("extracted"), str):
            view["extracted_chars"] = row["extracted"][:200]
        return view

    def _record(self, row: Dict[str, Any]) -> None:
        self.rows.append(self._ledger_view(row))
        try:
            self.ledger_path().parent.mkdir(parents=True, exist_ok=True)
            self.ledger_path().write_text(
                json.dumps({"rows": self.rows}, indent=2, ensure_ascii=False),
                encoding="utf-8")
        except OSError:
            pass  # ledger write is best-effort; the in-memory rows still bind

    def _record_ledger_row(self, row: Dict[str, Any]) -> None:
        # alias kept distinct from cache-side row mutation; both end at _record
        self._record(row)

    # -- search -------------------------------------------------------------
    def brave_search(self, query: str) -> List[Dict[str, Any]]:
        """One Brave web-search call. Raises ResearchWebError on missing key /
        auth failure / exhausted quota (parks the phase -- no no-web fallback)."""
        key = _brave_key(self.env)
        if not key:
            raise ResearchWebError(
                "BRAVE_SEARCH_API_KEY absent from the secrets store -- P-0.5-"
                "RESEARCH parks on a configuration error (research must cite "
                "sources actually retrieved, never a no-web model's invention). "
                "Operator action: supply the key, then re-run.")
        if self._search_transport is not None:
            return self._search_transport(query)
        req = urllib.request.Request(
            f"{BRAVE_SEARCH_URL}?q={urllib.parse.quote(query)}"
            f"&count={RESULTS_PER_QUERY}",
            headers={"X-Subscription-Token": key, "Accept": "application/json",
                     "Accept-Encoding": "gzip"},
        )
        try:
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ResearchWebError(
                    "Brave Search authentication failed (HTTP "
                    f"{exc.code}) -- P-0.5-RESEARCH parks: the run must not "
                    "fall back to a no-web model claiming research.")
            if exc.code == 429:
                raise ResearchWebError(
                    "Brave Search quota exhausted (HTTP 429) -- P-0.5-RESEARCH "
                    "parks with a configuration error.")
            raise ResearchWebError(f"Brave search HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ResearchWebError(
                f"Brave search unreachable: {type(exc).__name__}: {exc}") from exc
        try:
            import gzip as _gzip
            if raw[:2] == b"\x1f\x8b":
                raw = _gzip.decompress(raw)
            obj = json.loads(raw.decode("utf-8"))
        except (ValueError, OSError) as exc:
            raise ResearchWebError(f"Brave search response unusable: {exc}") from exc
        results: List[Dict[str, Any]] = []
        for item in ((obj.get("web") or {}).get("results") or [])[:RESULTS_PER_QUERY]:
            results.append({
                "url": str(item.get("url") or ""),
                "title": str(item.get("title") or ""),
                "description": str(item.get("description") or ""),
            })
        return results

    # -- fetch --------------------------------------------------------------
    def fetch_page(self, url: str, *, query: Optional[str] = None) -> Dict[str, Any]:
        """Fetch (or reuse the cached fetch of) one URL under every cap. Returns
        the ledger row. A cap/policy refusal returns a refused row -- it never
        silently passes and never consumes budget, so exactly the 13th unique
        URL path can be discriminated from real refusals. `query` (optional) is
        the Brave query that surfaced this URL -- recorded in the ledger row
        (the spec's ledger contract names the query alongside the canonical
        URL, retrieval time, status, hash, extraction length, and anchors)."""
        canon = canonical_url(url)
        if canon in self.cache:
            return self.cache[canon]
        if not _is_public_http_url(url):
            row = {"url": url, "canonical_url": canon, "status": 0,
                   "refused": "non-public http(s) target", "ok": False}
            self.refusals.append(row["refused"])
            return row
        unique_so_far = len(self.fetched)
        if unique_so_far >= self.max_unique:
            row = {"url": url, "canonical_url": canon, "status": 0,
                   "refused": f"URL cap ({self.max_unique} unique fetched URLs "
                              f"per deck) reached -- refused WITHOUT a fetch",
                   "ok": False, "over_cap": True}
            if query:
                row["query"] = query
            self.refusals.append(row["refused"])
            self._record(row)
            return row
        fetched_url_count = len(self.fetched)
        try:
            status, final_canon, body = self._fetch_transport(url)
        except ResearchWebError as exc:
            # A refused/failed fetch does NOT count against the cap (no evidence
            # was acquired); it is recorded and the source simply does not exist.
            row = {"url": url, "canonical_url": canon, "status": 0,
                   "refused": str(exc), "ok": False}
            self.refusals.append(row["refused"])
            self._record(row)
            return row
        extracted = extract_text(body)
        content_hash = hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()
        row = {
            "url": url,
            "canonical_url": final_canon or canon,
            "status": int(status),
            "retrieved_at": _utcnow(),
            "content_sha256": content_hash,
            "extraction_length": len(extracted),
            "extracted": extracted,
            "network_fetch": True,
            "fetch_ordinal": fetched_url_count + 1,
            "ok": int(status) == 200,
        }
        if query:
            row["query"] = query
        self.cache[canon] = row
        self.cache[row["canonical_url"]] = row
        self.fetched[canon] = row
        self.fetched[row["canonical_url"]] = row
        self._record_ledger_row(row)
        return row

    def fetch_many(self, urls: List[str]) -> None:
        # cap-aware: stops after the cap; every later URL is refused-no-fetch
        for url in urls:
            if len(self.fetched) >= self.max_unique:
                self.fetch_page(url)  # records the cap refusal, no network
                continue
            self.fetch_page(url)

    # -- anchors ------------------------------------------------------------
    def evaluate_anchor(self, fetched: Dict[str, Any], anchor: str) -> Dict[str, Any]:
        """The relevance contract for one (URL, anchor) pair -- FIX 20 consumes
        the same verdict. Normalized exact phrase >= 8 words, OR >= 60% of the
        anchor's non-stopword tokens in the extracted text."""
        verdict: Dict[str, Any] = {"anchor": anchor, "url": fetched.get("url")}
        text = self.extracted_text(fetched)
        tokens = [t for t in re.findall(r"[a-z0-9]+", anchor.lower())
                  if t not in _STOPWORDS]
        if fetched.get("status") != 200 or len(text) < MIN_EXTRACT_CHARS:
            verdict.update({
                "supported": False,
                "why": fetched.get("refused")
                       or f"HTTP {fetched.get('status')} / "
                          f"{len(text)} extracted chars (< {MIN_EXTRACT_CHARS})",
            })
            return verdict
        norm_text = _normalize_ws(text)
        phrase = _normalize_ws(re.sub(r"[^a-z0-9\s]", " ", anchor.lower()))
        phrase_words = [w for w in phrase.split() if w]
        if len(phrase_words) >= ANCHOR_MIN_WORDS and _normalize_ws(" ".join(phrase_words)) in norm_text:
            verdict.update({"supported": True, "basis": "exact-phrase"})
            return verdict
        if tokens:
            blob = set(re.findall(r"[a-z0-9]+", norm_text))
            hits = sum(1 for t in tokens if t in blob)
            ratio = hits / len(tokens)
            if ratio >= ANCHOR_TOKEN_MATCH:
                verdict.update({"supported": True, "basis": "token-60pct",
                                "ratio": round(ratio, 3)})
                return verdict
        verdict.update({
            "supported": False,
            "basis": None,
            "ratio": round((sum(1 for t in tokens
                                if t in set(re.findall(r"[a-z0-9]+", norm_text)))
                            / len(tokens)) if tokens else 0.0, 3),
            "why": "anchor neither exact-phrase (>=8 words) nor >=60% token match",
        })
        return verdict

    def extracted_text(self, row: Dict[str, Any]) -> str:
        """Extracted page text for a row. Stub transports hand back the BODY, so
        the cache stores the extraction with the row (never the raw html)."""
        extracted = row.get("extracted")
        if isinstance(extracted, str):
            return extracted
        return ""

    def note_anchor_support(self, canonical: str, anchor: str) -> Dict[str, Any]:
        """Record that canonical URL supports (or fails) an anchor -- appended to
        the ledger row's `citation_anchors` and to the pending anchor verdicts."""
        row = self.cache.get(canonical) or self.fetched.get(canonical)
        if row is None:
            row = self.fetch_page(canonical)
        verdict = self.evaluate_anchor(row, anchor)
        supported = row.setdefault("citation_anchors", [])
        supported.append({"anchor": anchor, "supported": verdict.get("supported")})
        # Update the row's EXISTING ledger view in place (never duplicate rows
        # per citation): find the already-recorded view of this fetch and
        # refresh it; append only when this canonical URL has no view yet.
        canon = row.get("canonical_url")
        existing = next(
            (i for i, v in enumerate(self.rows)
             if v.get("canonical_url") == canon and "network_fetch" in v),
            None)
        view = self._ledger_view(row)
        if existing is not None:
            self.rows[existing] = view
        else:
            self.rows.append(view)
        try:
            self.ledger_path().parent.mkdir(parents=True, exist_ok=True)
            self.ledger_path().write_text(
                json.dumps({"rows": self.rows}, indent=2, ensure_ascii=False),
                encoding="utf-8")
        except OSError:
            pass
        return verdict


# ---------------------------------------------------------------------------
# The P-0.5-RESEARCH retrieval driver: queries -> Brave results -> bounded
# fetches -> citations appended to upstream context for the synthesis call.
# ---------------------------------------------------------------------------
def derive_queries(topic: str, *, max_queries: int = MAX_QUERIES) -> List[str]:
    """Deck-specific web-search queries from the intake topic. Pure function --
    the search pathway never needs a model call to decide WHAT to search."""
    topic_n = re.sub(r"\s+", " ", str(topic or "")).strip(" -,.:;") or \
        "audience research"
    return [
        f"{topic_n} research studies statistics",
        f"{topic_n} objections counterarguments expert quotes",
        f"{topic_n} best practices benchmarks pricing",
        f"{topic_n} 2025 2026 trends report",
        f"{topic_n} case study results proof",
        f"{topic_n} compliance regulation requirements",
    ][:max(1, max_queries)]


def run_research_retrieval(run_dir: Path, *, topic: str,
                           fetch_transport: Optional[Callable[[str], Tuple[int, str, str]]] = None,
                           search_transport: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
                           env: Optional[dict] = None,
                           max_queries: int = MAX_QUERIES) -> Dict[str, Any]:
    """Brave-primary retrieval for P-0.5-RESEARCH. Raises ResearchWebError to
    PARK the phase on missing key / flag-off / exhausted quota (fail-closed,
    never a no-web fallback). On success returns:
      {sources: [{url, title, description}], fetcher, ledger_path, queries}
    and writes working/research/retrieval_ledger.jsonl (the FIX 20 input).
    """
    if not web_fetch_enabled():
        raise ResearchWebError(
            f"{FLAG_ENV}=0: outbound research disabled by operator kill-switch "
            "-- P-0.5-RESEARCH parks until an operator supplies a gate-valid "
            "source packet or re-enables the flag. The old no-web model / "
            "fictional-URL path may never be restored.")
    fetcher = BoundedFetcher(run_dir, fetch_transport=fetch_transport,
                             search_transport=search_transport, env=env)
    queries = derive_queries(topic, max_queries=max_queries)
    key = _brave_key(env)
    if not key:
        brave_search = fetcher.brave_search  # raises the park error
        brave_search(queries[0])  # park with the canonical missing-key message
        raise ResearchWebError("unreachable: key-present check passed but search parked")
    all_sources: List[Dict[str, Any]] = []
    seen_urls: set = set()
    for query in queries:
        results = fetcher.brave_search(query)
        for res in results:
            url = str(res.get("url") or "")
            if not url or url in seen_urls:
                continue
            if not _is_public_http_url(url):
                continue
            seen_urls.add(url)
            res = {**res, "query": query}
            all_sources.append(res)
    # Bounded fetch: the cap refuses the 13th unique URL WITHOUT a network hit.
    # Fetched per-source (not fetch_many) so each ledger row carries the query
    # that surfaced it.
    for res in all_sources:
        fetcher.fetch_page(res["url"], query=res.get("query"))
    return {
        "sources": all_sources,
        "fetcher": fetcher,
        "queries": queries,
        "ledger_path": str(fetcher.ledger_path()),
        "network_fetches": len(fetcher.fetched),
        "refusals": list(fetcher.refusals),
    }