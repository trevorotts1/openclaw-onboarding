#!/usr/bin/env python3
# =============================================================================
# SKILL 57 — SOCIAL MEDIA IN A BOX :: GHL API CONTRACTS (F09)
# -----------------------------------------------------------------------------
# ONE shared, documented-contract client layer for the GHL Social Planner API,
# imported by preflight_gate.py (account discovery) and run_social_media.py
# (post listing). Sourced from the OFFICIAL marketplace docs (SPEC.md sources,
# checked 2026-09-08):
#
#   S1 Get Accounts : GET  /social-media-posting/:locationId/accounts
#                     mandatory `Version` header; results wrapper; each account
#                     carries `id` + `name` + `platform` (IDs PRESERVED — the
#                     old platform-name-only collapse is gone, F06).
#   S2 Get Posts    : POST /social-media-posting/:locationId/posts/list
#                     mandatory `Version` header; body {type, skip, limit, ...}
#                     where skip/limit are NUMBER STRINGS (a real 422 was hit
#                     live by Skill 44, U88/GK-26: JSON integers are rejected);
#                     results wrapper; posts carry `_id`, `locationId`,
#                     `status` (draft|scheduled|failed|published|...); paging is
#                     skip/limit offset traversal (follow until a short page).
#
# The pinned API Version for this generation is 2021-07-28 (the version the
# Skill 44 client maps for /social-media-posting/ and proves live).
#
# ERROR TAXONOMY (the documented + observed failure classes, each a distinct
# GhlApiError.error_class): authentication (401), scope (403),
# disconnected_account (the account endpoint gone/unlinked for a connected
# identity), rate_limited (429 — Retry-After honored), transient (timeouts,
# 5xx, network), contract (a 2xx body that does not match the documented
# schema — never misread as "zero accounts").
#
# NO SECRETS in this module: keys are passed in by the caller and used only in
# the Authorization header; error messages carry status codes, never values.
# =============================================================================
"""Documented GHL Social Planner API contracts + error taxonomy (F09)."""

import json
import urllib.error
import urllib.request

BASE_URL = "https://services.leadconnectorhq.com"
API_VERSION = "2021-07-28"          # pinned: the /social-media-posting/ generation (Skill 44-proven live)
ACCOUNTS_TIMEOUT = 15
POSTS_TIMEOUT = 15
DEFAULT_PAGE_LIMIT = 100            # S2 default is 10; page wider and follow skip until short
MAX_PAGES = 50                      # hard stop so a mis-paged API can never loop forever

# Error classes (stable string taxonomy — callers branch on these, never on
# bare exception text).
E_AUTHENTICATION = "authentication"
E_SCOPE = "scope"
E_DISCONNECTED_ACCOUNT = "disconnected_account"
E_RATE_LIMITED = "rate_limited"
E_TRANSIENT = "transient"
E_CONTRACT = "contract"


class GhlApiError(Exception):
    """A classified GHL Social Planner API failure. `error_class` is one of the
    E_* constants above; `retry_after` is set only for rate_limited."""

    def __init__(self, error_class, message, status=None, retry_after=None):
        super().__init__(message)
        self.error_class = error_class
        self.status = status
        self.retry_after = retry_after

    def to_dict(self):
        d = {"error_class": self.error_class, "message": str(self)}
        if self.status is not None:
            d["status"] = self.status
        if self.retry_after is not None:
            d["retry_after"] = self.retry_after
        return d


def _headers(pit):
    return {"Authorization": "Bearer %s" % pit, "Version": API_VERSION,
            "Content-Type": "application/json"}


def _classify_http(status, retry_after_raw=None):
    if status == 401:
        return E_AUTHENTICATION, None
    if status == 403:
        return E_SCOPE, None
    if status == 404:
        # The location-scoped resource is gone: the account/location link is
        # broken (a disconnected/unlinked account), not a bad token.
        return E_DISCONNECTED_ACCOUNT, None
    if status == 429:
        try:
            ra = int(str(retry_after_raw).strip())
            return E_RATE_LIMITED, (ra if ra >= 0 else None)
        except (TypeError, ValueError):
            return E_RATE_LIMITED, None
    if 500 <= status <= 599:
        return E_TRANSIENT, None
    return E_TRANSIENT, None


def _read_retry_after(resp):
    try:
        return resp.headers.get("Retry-After")
    except Exception:  # noqa: BLE001 — header absence is never a crash
        return None


def parse_accounts_payload(data):
    """S1 contract parse: {results: {accounts: [...]}} (the documented wrapper).
    Accepts ONLY the documented shapes; anything else is a CONTRACT failure —
    a parser failure must never be misreported as zero accounts. Returns the
    list of raw account objects."""
    if not isinstance(data, dict):
        raise GhlApiError(E_CONTRACT, "accounts payload is not a JSON object")
    results = data.get("results")
    if results is None:
        raise GhlApiError(E_CONTRACT, "accounts payload has no results wrapper")
    if isinstance(results, list):
        # Some generations return results as a bare array; the account list is
        # the array itself (each element still an account object).
        accounts = results
    elif isinstance(results, dict):
        accounts = results.get("accounts")
    else:
        accounts = None
    if not isinstance(accounts, list):
        raise GhlApiError(E_CONTRACT, "results.accounts is not a list")
    return [a for a in accounts if isinstance(a, dict)]


def normalize_account(raw):
    """One account object -> the discovered_account contract fields.
    `account_id` is PRESERVED (never collapsed into a platform name)."""
    acct_id = raw.get("id") or raw.get("accountId") or raw.get("_id")
    platform = raw.get("platform") or raw.get("type") or raw.get("oauthProvider")
    name = raw.get("name") or raw.get("username") or ""
    return {
        "account_id": str(acct_id).strip() if acct_id is not None else "",
        "platform": str(platform).strip().lower() if isinstance(platform, str) and platform.strip() else "",
        "account_name": str(name).strip() if isinstance(name, str) else "",
    }


def fetch_accounts(pit, location_id, transport=None, timeout=ACCOUNTS_TIMEOUT):
    """S1: GET /social-media-posting/:locationId/accounts with the pinned Version
    header. `transport` is an injectable callable (method, url, headers, body)
    -> (status, body_bytes, headers_dict) for tests; the default is urllib.
    Returns the parsed account list [{account_id, platform, account_name}, ...].
    Raises GhlApiError on any classified failure."""
    if not pit or not location_id:
        raise GhlApiError(E_CONTRACT, "missing GHL PIT or locationId (cannot call the accounts contract)")
    url = "%s/social-media-posting/%s/accounts" % (BASE_URL, location_id)
    status, body, headers = _call("GET", url, _headers(pit), None, transport, timeout)
    if status // 100 != 2:
        cls, ra = _classify_http(status, _read_retry_after_shim(headers))
        raise GhlApiError(cls, "accounts listing failed (HTTP %d)" % status, status=status, retry_after=ra)
    try:
        data = json.loads(body.decode("utf-8")) if isinstance(body, (bytes, bytearray)) else body
    except (ValueError, AttributeError):
        raise GhlApiError(E_CONTRACT, "accounts payload is not valid JSON")
    return [normalize_account(a) for a in parse_accounts_payload(data)]


def _read_retry_after_shim(headers):
    if isinstance(headers, dict):
        for k, v in headers.items():
            if str(k).lower() == "retry-after":
                return v
    return None


def build_posts_list_body(post_type="all", skip=0, limit=DEFAULT_PAGE_LIMIT,
                          accounts=None, from_date=None, to_date=None,
                          include_users=None, post_type_filter=None):
    """S2 request body. skip/limit are NUMBER STRINGS (the live 422 contract:
    JSON integers are rejected with 'property X must be a number string').
    `accounts` is a comma-separated account-ID string when supplied."""
    body = {"type": str(post_type), "skip": str(int(skip)), "limit": str(int(limit))}
    if accounts:
        body["accounts"] = ",".join(str(a) for a in accounts)
    if from_date:
        body["fromDate"] = str(from_date)
    if to_date:
        body["toDate"] = str(to_date)
    if include_users is not None:
        body["includeUsers"] = bool(include_users)
    if post_type_filter:
        body["postType"] = str(post_type_filter)
    return body


def parse_posts_payload(data):
    """S2 contract parse: {results: {posts: [...]}} (wrapper) — results may also
    be a bare array. Anything else is a CONTRACT failure, never zero posts."""
    if not isinstance(data, dict):
        raise GhlApiError(E_CONTRACT, "posts payload is not a JSON object")
    results = data.get("results")
    if results is None:
        raise GhlApiError(E_CONTRACT, "posts payload has no results wrapper")
    if isinstance(results, list):
        posts = results
    elif isinstance(results, dict):
        posts = results.get("posts")
        if posts is None:
            posts = results.get("results")
    else:
        posts = None
    if not isinstance(posts, list):
        raise GhlApiError(E_CONTRACT, "results.posts is not a list")
    return [p for p in posts if isinstance(p, dict)]


def normalize_post(raw):
    """One post object -> the delivery-contract fields. `_id` is the GHL post
    id; `status` is the lifecycle state (draft|scheduled|failed|published|...);
    a missing status is 'unknown' (never silently 'published')."""
    pid = raw.get("id") or raw.get("_id") or raw.get("postId")
    status = raw.get("status")
    return {
        "post_id": str(pid).strip() if pid is not None else "",
        "status": str(status).strip().lower() if isinstance(status, str) and status.strip() else "unknown",
        "scheduled_at": raw.get("scheduleDate") if isinstance(raw.get("scheduleDate"), str) else None,
        "published_url": raw.get("url") if isinstance(raw.get("url"), str) else None,
    }


# ---------------------------------------------------------------------------
# F40 — GHL ANALYTICS ADAPTER SEAM (extends S1/S2 patterns; NO live calls).
# ---------------------------------------------------------------------------
# The provider reports per-post engagement in the posts/list payloads wherever
# the platform supplies it. The F40 contract: collect provider-supported
# metrics WITH account/post id, measurement window and fetched_at; represent
# unavailable data as UNKNOWN — never zero, never interpolated. A metric the
# payload does not carry is simply absent from the observations (the
# social_measured_outcomes store records the explicit unknown only where the
# caller asks for coverage of an expected metric).
#
# Metric keys seen across generations (absent key or non-numeric value ⇒
# UNKNOWN): counts.reactions|likes|comments, metrics.impressions|reach, and
# flat numeric fields of the same names.
METRIC_KEYS = {
    "impressions": ("metrics.impressions", "counts.impressions", "impressions"),
    "reach": ("metrics.reach", "counts.reach", "reach"),
    "reactions": ("counts.reactions", "counts.likes", "reactions", "likes"),
    "comments": ("counts.comments", "comments"),
    "clicks": ("metrics.clicks", "counts.clicks", "clicks"),
}


def _dig(raw, dotted):
    cur = raw
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def extract_post_metrics(raw, fetched_at=None, window_start=None, window_end=None):
    """One posts/list post object -> normalized metric observations with
    UNKNOWN semantics (F40).

    Returns a list of {post_id, metric, value, is_unknown, window_start,
    window_end, fetched_at, source:'ghl-analytics'} rows for the KNOWN
    metric keys. A metric the provider did not report produces an explicit
    unknown row (value None, is_unknown True) — NEVER a zero — so downstream
    coverage is honest. A post id that cannot be resolved yields no rows
    (never an invented post).
    """
    pid = raw.get("id") or raw.get("_id") or raw.get("postId")
    if pid is None or not str(pid).strip():
        return []
    out = []
    for metric, keys in METRIC_KEYS.items():
        value = None
        found = False
        for key in keys:
            v = _dig(raw, key)
            if v is None:
                continue
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)) and v == v and v not in (float("inf"), float("-inf")):
                value, found = float(v), True
                break
            if isinstance(v, str):
                try:
                    value, found = float(v), True
                    break
                except ValueError:
                    continue
        out.append({
            "post_id": str(pid).strip(),
            "account_id": str(raw.get("accountId") or raw.get("account_id") or "").strip(),
            "metric": metric,
            "value": value if found else None,
            "is_unknown": not found,
            "window_start": window_start,
            "window_end": window_end,
            "fetched_at": fetched_at,
            "source": "ghl-analytics",
        })
    return out


def fetch_posts(pit, location_id, post_type="all", accounts=None,
                from_date=None, to_date=None, transport=None,
                timeout=POSTS_TIMEOUT, max_pages=MAX_PAGES,
                page_limit=DEFAULT_PAGE_LIMIT):
    """S2: POST /social-media-posting/:locationId/posts/list with the pinned
    Version header + number-string skip/limit; follows skip/offset pagination
    until a short page (or MAX_PAGES). Returns the accumulated normalized post
    list [{post_id, status, scheduled_at, published_url}, ...]."""
    if not pit or not location_id:
        raise GhlApiError(E_CONTRACT, "missing GHL PIT or locationId (cannot call the posts/list contract)")
    url = "%s/social-media-posting/%s/posts/list" % (BASE_URL, location_id)
    out = []
    skip = 0
    for _page in range(max_pages):
        body = build_posts_list_body(post_type=post_type, skip=skip, limit=page_limit,
                                     accounts=accounts, from_date=from_date, to_date=to_date)
        status, rbody, headers = _call("POST", url, _headers(pit),
                                       json.dumps(body).encode("utf-8"), transport, timeout)
        if status // 100 != 2:
            cls, ra = _classify_http(status, _read_retry_after_shim(headers))
            raise GhlApiError(cls, "posts listing failed (HTTP %d)" % status, status=status, retry_after=ra)
        try:
            data = json.loads(rbody.decode("utf-8")) if isinstance(rbody, (bytes, bytearray)) else rbody
        except (ValueError, AttributeError):
            raise GhlApiError(E_CONTRACT, "posts payload is not valid JSON")
        page = [normalize_post(p) for p in parse_posts_payload(data)]
        out.extend(page)
        if len(page) < page_limit:
            break
        skip += page_limit
    return out


def _call(method, url, headers, body, transport, timeout):
    """One HTTP call via the injectable transport (or urllib). Network-level
    failures classify as transient; HTTP errors are classified by status."""
    if transport is not None:
        try:
            return transport(method, url, headers, body)
        except GhlApiError:
            raise
        except Exception as exc:  # noqa: BLE001 — simulated/real network faults are transient
            raise GhlApiError(E_TRANSIENT, "network error calling %s %s (%s)" % (method, url, exc))
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - client's own endpoint
            return resp.getcode(), resp.read(), dict(resp.headers.items())
    except urllib.error.HTTPError as exc:
        ra = None
        try:
            ra = exc.headers.get("Retry-After")
        except Exception:  # noqa: BLE001
            pass
        return exc.code, exc.read() if hasattr(exc, "read") else b"", \
            dict(exc.headers.items()) if exc.headers else {}
    except Exception as exc:  # noqa: BLE001 — timeout/DNS/reset are all transient
        if isinstance(exc, GhlApiError):
            raise
        raise GhlApiError(E_TRANSIENT, "network error calling %s %s" % (method, url))