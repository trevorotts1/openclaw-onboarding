"""gather.py: keyless web-search gatherer behind the research stage.

Directive 21 (research stage), 17.9 (claims carry citations), 24.4 (stable
envelope + exit codes). Stdlib only — urllib.request + html.parser. No API key,
no paid service, no browser, no model call: the stage has to run headless
inside a client container that has no search credential of any kind.

Reads the BARE brief {offer, audience, action/cta, claims?, sources?} and:

  1. never searches when the brief already carries a non-empty sources[] —
     the client's own sources win, untouched;
  2. derives its own short queries from offer/audience/action in a fixed order,
     deterministically (no randomness, no clock, no model);
  3. asks a DuckDuckGo HTML/lite endpoint, unwraps the redirect links, drops
     search-engine self links plus javascript:/mailto:/tel:/data: and asset
     URLs, and de-duplicates in first-seen order;
  4. fetches each candidate URL exactly ONCE with a browser-like User-Agent
     under a per-URL timeout, inside ONE total stage budget;
  5. extracts readable text and returns sources[] ({id, url, retrieved}) and
     claims[] ({id, text, source}) shaped exactly as research.validate_sources
     and research.validate_claims accept, plus a citation for any client claim
     whose text a fetched page actually contains (verbatim normalised match
     only — a claim no page contains stays untouched, so the validator still
     parks it instead of accepting an invented attribution).

Every network path is guarded: a dead link, a dead resolver or an exhausted
budget yields a status, never an exception. research.run_stage maps "offline"
and "budget" to outcome "waiting", exit 2, with a reason — an offline box
degrades, it does not crash and it never reports the client's brief as invalid.

Transport is injected: transport(url, timeout, headers) -> (body, final_url,
charset), so unit tests never touch the network. One env-gated live smoke
exists and is skipped in the default run.
"""
from __future__ import annotations

import datetime
import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser

# Search endpoints (keyless, no account). The HTML endpoint is tried first and
# the lite endpoint is the fallback for the same query.
SEARCH_ENDPOINTS = (
    "https://html.duckduckgo.com/html/?q=%s",
    "https://lite.duckduckgo.com/lite/?q=%s",
)
# Browser-shaped headers: some endpoints drop a bare urllib User-Agent.
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
ACCEPT_LANGUAGE = "en-US,en;q=0.8"

DEFAULT_BUDGET = 45.0        # seconds, whole stage
DEFAULT_TIMEOUT = 8.0        # seconds, one URL
DEFAULT_MAX_QUERIES = 3
DEFAULT_MAX_SOURCES = 6
DEFAULT_MAX_FETCHES = 8
MAX_BYTES = 1_500_000        # one bounded read per URL
MIN_TEXT = 60                # a page shorter than this carries no readable body
CLAIM_MAX = 220              # short claim text
MAX_QUERY_WORDS = 10

# Search-engine hosts never count as a research source (their own result pages,
# asset CDNs and tracking endpoints). Matched on the host and any subdomain.
SEARCH_HOSTS = ("duckduckgo.com", "google.com", "googleapis.com", "gstatic.com",
                "googleusercontent.com", "bing.com", "go.microsoft.com",
                "yahoo.com", "yandex.com", "brave.com", "startpage.com",
                "mojeek.com", "qwant.com", "ecosia.org", "search.com")
NON_WEB_SCHEMES = ("javascript", "mailto", "tel", "data", "about", "file",
                   "ftp", "blob", "ws")
ASSET_EXT = (".ico", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif",
             ".css", ".js", ".mjs", ".woff", ".woff2", ".ttf", ".map",
             ".mp4", ".mp3", ".wav", ".zip", ".gz", ".tar", ".dmg")

# Result-link markers across the two endpoint layouts.
RESULT_CLASSES = ("result__a", "result-link", "result__url", "results_links")

STOPWORDS = frozenset("""
a an and are as at be but by for from had has have how i if in into is it its
me my no nor not of on or our out s so that the their them then there these
they this to too up us was we were what when where which who whom why will
with would you your
""".split())

# Site chrome that opens a page but says nothing about the subject: never a claim.
CHROME_PREFIXES = ("medically reviewed", "written by", "fact checked",
                   "fact-checked", "last updated", "updated on", "advertisement",
                   "skip to", "sign up", "subscribe", "log in", "we use cookies",
                   "this site uses", "cookie", "all rights reserved", "copyright",
                   "share this", "print this", "menu", "search")

# Response bodies that are not HTML text (archives, documents, images): stdlib
# cannot read their text, so they never become a source.
BINARY_MAGIC = (b"%PDF", b"PK\x03\x04", b"\x89PNG", b"GIF8", b"RIFF",
                b"\x1f\x8b", b"\xd0\xcf\x11\xe0", b"\x1f\xa0", b"BZ")

BLOCK_TAGS = frozenset(("p", "div", "br", "li", "ul", "ol", "dl", "dt", "dd",
                        "tr", "td", "th", "table", "h1", "h2", "h3", "h4",
                        "h5", "h6", "section", "article", "header", "footer",
                        "nav", "aside", "main", "blockquote", "pre", "hr",
                        "figcaption", "figure", "form", "label"))
SKIP_TAGS = frozenset(("script", "style", "noscript", "template", "svg",
                       "head", "iframe", "object", "canvas", "select",
                       "option", "button"))

STATUS_OK = "ok"
STATUS_EMPTY = "empty"
STATUS_OFFLINE = "offline"
STATUS_BUDGET = "budget"
STATUS_CLIENT = "client-supplied"


def _clean(value):
    """Whitespace-collapsed copy of a brief field, '' for anything non-text."""
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _tokens(text):
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", (text or "").lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def _trim_query(text, words=MAX_QUERY_WORDS):
    """Deterministic word budget: first N whitespace words, punctuation-tidy."""
    parts = _clean(text).split()[:words]
    out = " ".join(parts).strip(" ,;:.!?\t\"'()[]{}")
    return out if len(_tokens(out)) else ""


def _words(text):
    return _clean(text).split()


def _content_words(words):
    """Content words only — used when a field is MERGED into another field's
    query, so the word budget goes to terms, not glue words."""
    return [w for w in words if w.lower().strip(".,;:!?") not in STOPWORDS]


def _join(*groups, limit=MAX_QUERY_WORDS):
    """Concatenate word groups, dropping repeats, capped at `limit` words."""
    out, seen = [], set()
    for group in groups:
        for word in group:
            key = word.lower().strip(".,;:!?")
            if key in seen:
                continue
            seen.add(key)
            out.append(word)
            if len(out) >= limit:
                return " ".join(out)
    return " ".join(out)


def pick_queries(brief, limit=DEFAULT_MAX_QUERIES):
    """Short search queries for the bare brief, in fixed order, no model call.

    offer alone -> offer + audience -> offer + action, each capped at
    MAX_QUERY_WORDS with repeated words dropped so no field is ever pasted
    into a query twice. Returns [] for a brief with nothing to search
    (research.evaluate rejects that earlier anyway).
    """
    brief = brief or {}
    offer = _words(brief.get("offer"))
    audience_raw = _words(brief.get("audience"))
    action_raw = _words(brief.get("action") or brief.get("cta"))
    audience = _content_words(audience_raw)
    action = _content_words(action_raw)
    head = offer[:6]
    candidates = []
    if offer:
        candidates.append(_join(offer))
        if audience:
            candidates.append(_join(head, audience))
        if action:
            candidates.append(_join(head, action))
    if not candidates:                      # no offer: the field itself is the query
        if audience_raw:
            candidates.append(_join(audience_raw))
            if action:
                candidates.append(_join(audience_raw[:6], action))
        elif action_raw:
            candidates.append(_join(action_raw))
    out, seen = [], set()
    for cand in candidates:
        q = _trim_query(cand)
        if not q or q.lower() in seen:
            continue
        seen.add(q.lower())
        out.append(q)
        if len(out) >= limit:
            break
    return out


class _AnchorParser(HTMLParser):
    """Collects (href, classes, rels, text) for every anchor in the page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchors = []
        self._href = None
        self._cls = ()
        self._rel = ()
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if not href:
            return
        raw = dict(attrs)
        self._href = href
        self._cls = tuple((raw.get("class") or "").split())
        self._rel = tuple((raw.get("rel") or "").lower().split())
        self._buf = []

    def handle_data(self, data):
        if self._href is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            text = " ".join("".join(self._buf).split())
            self.anchors.append((self._href, self._cls, self._rel, text))
            self._href = None
            self._buf = []


def _parse_anchors(page):
    parser = _AnchorParser()
    try:
        parser.feed(page or "")
        parser.close()
    except Exception:            # malformed markup: keep what was parsed
        pass
    return parser.anchors


def unwrap_redirect(href, base_url=""):
    """Absolute http(s) target of an href, following DuckDuckGo's /l/?uddg=.

    Returns None when nothing web-shaped comes out.
    """
    href = _clean(href)
    if not href:
        return None
    if href.startswith("//"):
        href = "https:" + href
    try:
        absolute = urllib.parse.urljoin(base_url or "https://duckduckgo.com/", href)
        parts = urllib.parse.urlsplit(absolute)
        if parts.query:
            target = urllib.parse.parse_qs(parts.query).get("uddg") or []
            if target:
                target = _clean(target[0])
                if target.startswith("//"):
                    target = "https:" + target
                if re.match(r"^https?://", target, re.I):
                    absolute = target
                    parts = urllib.parse.urlsplit(absolute)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https"):
        return None
    return absolute


def normalize_url(url):
    """Canonical form for de-duplication: lower scheme/host, no fragment,
    no default port, no trailing slash. None when the URL is not web-shaped."""
    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme.lower() not in ("http", "https") or not host:
            return None
        try:
            port = parts.port
        except ValueError:
            return None
        netloc = host if port in (None, 80, 443) else "%s:%d" % (host, port)
        path = parts.path or "/"
        if len(path) > 1:
            path = path.rstrip("/") or "/"
        return urllib.parse.urlunsplit(
            (parts.scheme.lower(), netloc, path, parts.query, ""))
    except ValueError:
        return None


def is_junk(url):
    """True for links that can never be a research source: non-web schemes,
    search-engine self links, asset files, hostless URLs."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return True
    if parts.scheme.lower() in NON_WEB_SCHEMES:
        return True
    if parts.scheme.lower() not in ("http", "https"):
        return True
    host = (parts.hostname or "").lower()
    if not host:
        return True
    for bad in SEARCH_HOSTS:
        if host == bad or host.endswith("." + bad):
            return True
    path = parts.path.lower()
    return any(path.endswith(ext) for ext in ASSET_EXT)


def extract_result_urls(page, base_url=""):
    """Candidate source URLs from one search page, in document order,
    junk-filtered and de-duplicated (first occurrence wins)."""
    anchors = _parse_anchors(page)
    picked = [a for a in anchors
              if (set(a[1]) & set(RESULT_CLASSES)) or ("nofollow" in a[2])]
    if not picked:
        picked = [a for a in anchors if a[3]]
    out, seen = [], set()
    for href, _cls, _rel, _text in picked:
        target = unwrap_redirect(href, base_url)
        if not target or is_junk(target):
            continue
        key = normalize_url(target)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(target)
    return out


class _TextParser(HTMLParser):
    """Readable body text: skips head/script/style, breaks on block tags."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in SKIP_TAGS:
            self._skip += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in SKIP_TAGS:
            if self._skip:
                self._skip -= 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(page):
    """Plain readable text of a fetched page: one non-empty line per block,
    scripts/styles/head dropped, whitespace collapsed."""
    parser = _TextParser()
    try:
        parser.feed(page or "")
        parser.close()
    except Exception:            # malformed markup: keep the text parsed so far
        pass
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line)


def first_claim(text, max_len=CLAIM_MAX, min_len=MIN_TEXT):
    """Short claim text: the first complete prose sentence long enough to say
    something, cut on a word boundary inside max_len. Site chrome (bylines,
    cookie banners, copyright lines) and unreadable debris are skipped; '' when
    the page carries no such sentence."""
    for raw in (text or "").splitlines():        # one block of prose per line
        for sentence in re.split(r"(?<=[.!?])\s+", raw):
            sentence = " ".join(sentence.split())
            if not _usable_claim(sentence, min_len, max_len):
                continue
            return sentence if len(sentence) <= max_len else _cut(sentence, max_len, min_len)
    return ""


def _cut(sentence, max_len, min_len):
    cut = sentence[:max_len]
    space = cut.rfind(" ")
    return (cut[:space] if space >= min_len else cut).rstrip(" ,;:-")


def _usable_claim(sentence, min_len, max_len):
    if len(sentence) < min_len or len(sentence) > 2000:
        return False
    if sentence[:60].lower().startswith(CHROME_PREFIXES):
        return False
    if not re.search(r"[.!?][\"')\]]*\Z", sentence):
        return False                       # not a finished sentence: nav/headline
    if re.search(r"[a-z][A-Z0-9]", sentence):
        return False                       # two chunks glued without a space
    letters = sum(1 for ch in sentence if ch.isalpha() or ch.isspace())
    if letters < 0.6 * len(sentence):
        return False                       # binary / encoded debris
    words = sentence.split()
    return len(words) >= 8 and " " in sentence


def default_transport(url, timeout, headers):
    """One bounded GET with a browser-shaped header set (stdlib urllib).

    Returns (body_bytes, final_url, charset). Raises on any network failure —
    every caller guards, nothing propagates to the CLI.
    """
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        body = response.read(MAX_BYTES)
        try:
            charset = response.headers.get_content_charset()
        except Exception:
            charset = None
        return body, response.geturl(), charset


def looks_binary(body):
    """True for a response that is not HTML text (PDF, zip, image, gzip...)."""
    sample = bytes(body[:4096])
    if not sample:
        return True
    if sample.startswith(BINARY_MAGIC):
        return True
    readable = sum(1 for b in sample if 32 <= b < 127 or b in (9, 10, 13) or b >= 128)
    return readable / float(len(sample)) < 0.85


def _fetch(transport, url, headers, timeout):
    """One attempt, one bounded read. Returns (body, final_url, charset, error)."""
    try:
        body, final_url, charset = transport(url, timeout, headers)
    except Exception as exc:            # noqa: BLE001 - offline must degrade
        return None, url, None, str(exc)[:200]
    if not isinstance(body, (bytes, bytearray)):
        return None, url, None, "transport returned non-bytes body"
    if looks_binary(body):
        return None, url, None, "not HTML text (binary response)"
    return bytes(body), final_url, None if charset is None else str(charset), None


def _decode(body, charset):
    for encoding in (charset, "utf-8", "latin-1"):
        if not encoding:
            continue
        try:
            return body.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", "replace")


class _Budget:
    """One monotonic deadline for the whole stage; every attempt draws from it."""

    def __init__(self, seconds):
        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            seconds = DEFAULT_BUDGET
        self.deadline = time.monotonic() + max(0.0, seconds)
        self.hit = False

    def left(self):
        return self.deadline - time.monotonic()

    def done(self):
        if self.left() <= 0.0:
            self.hit = True
            return True
        return False

    def timeout_for(self, timeout):
        try:
            timeout = float(timeout)
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT
        left = self.left()
        return max(0.1, min(timeout, left))


def _has_sources(brief):
    sources = (brief or {}).get("sources")
    return isinstance(sources, list) and bool(sources)


def _claim_id(index, used):
    while True:
        cid = "gclaim-%d" % index
        if cid not in used:
            used.add(cid)
            return cid
        index += 1


def _find_source_for_claim(text, pages):
    """Index of the fetched page whose text literally contains the claim
    (normalised substring). -1 when no page says it — never guess a citation."""
    needle = " ".join(_clean(text).lower().split())
    if len(needle) < 24:
        return -1
    for i, (_url, page_text) in enumerate(pages):
        hay = " ".join(page_text.lower().split())
        if needle in hay:
            return i
    return -1


def gather(brief, transport=None, budget=DEFAULT_BUDGET, timeout=DEFAULT_TIMEOUT,
           max_queries=DEFAULT_MAX_QUERIES, max_sources=DEFAULT_MAX_SOURCES,
           max_fetches=DEFAULT_MAX_FETCHES, today=None):
    """Keyless research pass over the bare brief. Never raises on network.

    Returns a dict:
      status   "client-supplied" | "ok" | "empty" | "offline" | "budget"
      sources  [{id, url, retrieved}]   (empty unless status == "ok")
      claims   [{id, text, source}]     client claims kept verbatim first,
                                        gathered claims appended
      queries  the queries actually asked, in order
      urls     candidate URLs after junk filtering + de-duplication
      fetched  how many candidate pages were attempted
      errors   bounded strings, no bodies, no credentials
    """
    brief = brief or {}
    result = {"status": STATUS_EMPTY, "sources": [], "claims": [],
              "queries": [], "urls": [], "fetched": 0, "errors": []}
    # Requirement: the client's own sources win — no search, no network, no
    # transport call at all when sources[] is already a non-empty list.
    if _has_sources(brief):
        result["status"] = STATUS_CLIENT
        result["sources"] = list(brief["sources"])
        return result

    queries = pick_queries(brief, max_queries)
    result["queries"] = queries
    if not queries:
        result["status"] = STATUS_EMPTY
        return result

    transport = transport or default_transport
    headers = {"User-Agent": USER_AGENT, "Accept": ACCEPT,
               "Accept-Language": ACCEPT_LANGUAGE}
    clock = _Budget(budget)
    today = today or datetime.date.today().isoformat()

    candidates, search_attempts, search_ok = [], 0, 0
    for query in queries:
        if clock.done() or len(candidates) >= max_fetches:
            break
        for template in SEARCH_ENDPOINTS:
            if clock.done():
                break
            url = template % urllib.parse.quote_plus(query)
            search_attempts += 1
            body, final_url, charset, err = _fetch(
                transport, url, headers, clock.timeout_for(timeout))
            if err:
                result["errors"].append("search %s" % err)
                continue
            search_ok += 1
            for found in extract_result_urls(_decode(body, charset), final_url):
                if found not in candidates:
                    candidates.append(found)
                if len(candidates) >= max_fetches:
                    break
            break
    result["urls"] = candidates[:max_fetches]

    pages, page_attempts, page_ok = [], 0, 0
    for url in result["urls"]:
        if clock.done() or len(pages) >= max_sources:
            break
        page_attempts += 1
        result["fetched"] = page_attempts
        body, final_url, charset, err = _fetch(
            transport, url, headers, clock.timeout_for(timeout))
        if err:
            result["errors"].append("fetch %s" % err)
            continue
        page_ok += 1
        text = html_to_text(_decode(body, charset))
        if len(text) < MIN_TEXT or not first_claim(text):
            result["errors"].append("no readable text")
            continue
        pages.append((final_url or url, text))

    # Client claims first, verbatim; a source is attached only when a fetched
    # page literally contains the claim text. Generated ids never collide with
    # an id the client already used.
    claims = []
    supplied = brief.get("claims")
    if isinstance(supplied, list):
        for claim in supplied:
            if isinstance(claim, dict):
                copy = dict(claim)
                if _clean(copy.get("text")) and not _clean(copy.get("source")):
                    hit = _find_source_for_claim(copy.get("text"), pages)
                    if hit >= 0:
                        copy["source"] = "gsrc-%d" % (hit + 1)
                claims.append(copy)
            else:
                claims.append(claim)
    used = {c.get("id") for c in claims
            if isinstance(c, dict) and _clean(c.get("id"))}
    sources = [{"id": "gsrc-%d" % (i + 1), "url": url, "retrieved": today}
               for i, (url, _text) in enumerate(pages)]
    index = 0
    for i, (_url, text) in enumerate(pages):
        index += 1
        claims.append({"id": _claim_id(index, used), "text": first_claim(text),
                       "source": "gsrc-%d" % (i + 1)})
    result["sources"], result["claims"] = sources, claims

    if sources:
        result["status"] = STATUS_OK
    elif search_attempts and not search_ok:
        result["status"] = STATUS_OFFLINE      # every search request failed
    elif clock.hit:
        result["status"] = STATUS_BUDGET       # budget ran out before a source
    elif not candidates:
        result["status"] = STATUS_EMPTY        # page read, nothing usable in it
    elif not page_ok:
        result["status"] = STATUS_OFFLINE      # links found, every fetch failed
    else:
        result["status"] = STATUS_EMPTY        # pages read, no readable body
    return result
