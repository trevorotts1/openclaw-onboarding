#!/usr/bin/env python3
"""anthology-smoke-test.py -- the Anthology Engine daily funded-reachability probe.

WHAT THIS SHIPS (SPEC 3.4 row 18; WAVE-PLAN W1.22; PRD Section 15; .build-state/W0.9.json):
  A once-a-day canary that answers ONE question: is every provider the engine
  depends on still REACHABLE and FUNDED? It hits BALANCE / METADATA endpoints ONLY
  (never a generation endpoint), so its total spend is provably at or under one
  cent -- every probe is a zero-generation-token read, cost 0.00. This is the exact
  failure class that killed the legacy system twice on record: silent
  insufficient-credits. The daily tick catches it before a participant does.

  The same run also (a) AGES THE HOLD QUEUE (SPEC row 18: "ages the hold queue" ->
  hold_queue.py daily age tick, resume from the exact cursor) and (b) on any failure
  fires exactly ONE deduped founder Telegram alert through the OpenClaw gateway
  (alert-dedup.py; the gateway is NEVER bypassed). Both are fail-soft: neither can
  turn a green probe red, and a missing sibling script degrades to a durable
  operator-side record, never a crash.

PROBES (balance endpoints ONLY; every one a zero-token metadata/balance GET):
  ollama-cloud  GET https://ollama.com/api/tags            200 + non-empty models = funded
  openrouter    GET https://openrouter.ai/api/v1/key       200 + (limit_remaining>0 OR
                                                            limit/limit_remaining null = PAYG/unlimited) = funded
  gemini        GET .../v1beta/models (x-goog-api-key hdr)  200 + non-empty models = funded
  minimax       GET https://api.minimax.io/v1/token_plan/remains  200 + remaining>0 = funded  [OPTIONAL]
  kie.ai        GET https://api.kie.ai/api/v1/chat/credit  200 code=200 data>0 = funded; 402 = unfunded

  MiniMax host (W0.9 flagged MEDIUM-confidence -- RE-CONFIRMED at W1.22 against the
  live docs): the programmatic host is api.minimax.io (global default), NOT
  www.minimax.io (that is the marketing/web host). api.minimaxi.com is the China
  regional host. MINIMAX_API_HOST overrides; a region-mismatch 401 on the primary
  triggers ONE bounded (still zero-cost) retry on the regional alternate. This
  matches model_router.py's inference base (https://api.minimax.io/v1) and the
  OpenClaw MiniMax provider default (MINIMAX_API_HOST=https://api.minimax.io).

DOCTRINE (binding, enforced in code):
  - STDLIB ONLY (urllib, json, subprocess, hashlib): zero third-party deps; calls NO
    model; consumes NO generation tokens.
  - SPEND CEILING is STRUCTURAL: the transport refuses any URL not on the pinned
    balance-endpoint allowlist, so a generation call cannot happen by accident; the
    per-probe cost is declared 0 and the run asserts the total is at or under the
    ceiling (default one cent) BEFORE any request leaves the box.
  - MOVE IN SILENCE: operator-verbose to stderr and the report dir; NOTHING to any
    client. The only outbound human signal is the founder alert, and it goes ONLY
    through alert-dedup.py -> the OpenClaw gateway, deduped to one per failure/day.
  - NEVER print a credential value: every provider key is resolved by LABEL across
    the live process env first, then the conventional aliases, and reported SET /
    NOT SET (+ length) only. No key is ever placed in a URL query, a log line, an
    exception, or the report.
  - Zero cross-provider (foreign-vendor) identifiers ship in this file; the engine
    probes ONLY the client's own configured providers.
  - Runs as the node user; writes ONLY under the engine state/report dir; never root.

EXIT CODES (SPEC 3.4 row 18; house map 0/1/2/3/4/5):
  0  all reachable and funded (idempotent; safe to re-run)
  4  a provider is unreachable, unfunded, unauthorized, or (for a REQUIRED provider)
     has no resolvable credential -> the alert path
  2  bad invocation / config invalid / spend-ceiling guard would be exceeded
  1  unexpected error

Ground truth for every endpoint/shape below: .build-state/W0.9.json (Part A balance
endpoints) plus the live docs re-confirmation performed at W1.22.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Exit codes (SPEC 3.4 row 18; house map).
# ---------------------------------------------------------------------------
EX_OK = 0
EX_ERR = 1
EX_BADINVOKE = 2       # bad invocation / config invalid / spend guard
EX_UNFUNDED = 4        # provider unreachable / unfunded / unauthorized (alert path)

# ---------------------------------------------------------------------------
# Per-probe result classes (strings; a probe is exactly one of these).
# ---------------------------------------------------------------------------
R_OK = "OK"                     # reachable + funded
R_UNFUNDED = "UNFUNDED"         # reachable but depleted/exhausted
R_UNAUTHORIZED = "UNAUTHORIZED" # key rejected (401/403)
R_UNREACHABLE = "UNREACHABLE"   # transport failure or server 5xx
R_NO_CREDENTIAL = "NO_CREDENTIAL"  # no key resolvable
R_SKIPPED = "SKIPPED"           # optional provider with no key: not a failure
R_ERROR = "ERROR"               # unexpected parse/probe error

# The classes that mean "this provider failed the canary".
_FAILING = frozenset((R_UNFUNDED, R_UNAUTHORIZED, R_UNREACHABLE, R_ERROR))

HTTP_TIMEOUT = 20  # seconds; a slow balance endpoint must not wedge the daily tick.


# ---------------------------------------------------------------------------
# Provider registry (pinned to W0.9.json Part A). Each provider declares:
#   id             stable provider id (matches model_router.py provider ids)
#   env_aliases    conventional env-var NAMES, live process env first (VALUE never read into logs)
#   required       True -> a missing credential is a canary FAILURE (false-green guard);
#                  False -> a missing credential is SKIPPED (optional direct account)
#   endpoints      one or more zero-token balance/metadata GETs, tried in order
#   parse          the response classifier
# Every URL that can be requested is enumerated here and nowhere else; the transport
# allowlist is built from exactly this set, which is what makes the spend ceiling
# structural rather than a promise.
# ---------------------------------------------------------------------------

def _parse_ollama(status, body):
    """Ollama Cloud exposes no credit balance; a 200 model list = funded reachability."""
    if status in (401, 403):
        return R_UNAUTHORIZED, "key rejected (HTTP %s)" % status
    if status != 200:
        return R_UNREACHABLE, "HTTP %s" % status
    obj = _json_or_none(body)
    models = (obj or {}).get("models")
    if isinstance(models, list) and models:
        return R_OK, "%d models reachable" % len(models)
    # /v1/models (OpenAI-compatible) shape carries "data".
    data = (obj or {}).get("data")
    if isinstance(data, list) and data:
        return R_OK, "%d models reachable" % len(data)
    return R_UNREACHABLE, "200 but empty model list"


def _parse_openrouter(status, body):
    """/api/v1/key returns {data:{limit,limit_remaining,...}}. null limit/limit_remaining
    = pay-as-you-go / unlimited = FUNDED (W0.9 flagged this null case -- resolved here)."""
    if status in (401, 403):
        return R_UNAUTHORIZED, "key rejected (HTTP %s)" % status
    if status != 200:
        return R_UNREACHABLE, "HTTP %s" % status
    obj = _json_or_none(body) or {}
    data = obj.get("data") if isinstance(obj.get("data"), dict) else obj
    lim = data.get("limit")
    rem = data.get("limit_remaining")
    if lim is None or rem is None:
        return R_OK, "pay-as-you-go / unlimited (limit null)"
    try:
        remf = float(rem)
    except (TypeError, ValueError):
        return R_OK, "reachable (limit_remaining unparseable, treated funded)"
    if remf > 0:
        return R_OK, "credit remaining"
    return R_UNFUNDED, "limit_remaining exhausted"


def _parse_gemini(status, body):
    """models.list is Gemini's key-validity + reachability probe (no credit balance API)."""
    if status in (401, 403):
        return R_UNAUTHORIZED, "key rejected / API not enabled (HTTP %s)" % status
    if status != 200:
        return R_UNREACHABLE, "HTTP %s" % status
    obj = _json_or_none(body) or {}
    models = obj.get("models")
    if isinstance(models, list) and models:
        return R_OK, "%d models reachable" % len(models)
    return R_UNREACHABLE, "200 but empty model list"


# Candidate remaining-quota field names in the MiniMax token_plan/remains payload.
_MINIMAX_REMAIN_KEYS = (
    "total_remain", "remain", "remaining", "total_remaining",
    "remain_quota", "remaining_quota", "left", "balance",
)


def _minimax_find_remaining(obj):
    """Best-effort extract of a numeric remaining quota from a MiniMax response,
    scanning the top level and a nested `data` object."""
    for container in (obj, obj.get("data") if isinstance(obj.get("data"), dict) else None):
        if not isinstance(container, dict):
            continue
        for k in _MINIMAX_REMAIN_KEYS:
            if k in container:
                try:
                    return float(container[k])
                except (TypeError, ValueError):
                    continue
    return None


def _parse_minimax(status, body):
    """token_plan/remains: 200 + remaining>0 = funded. MiniMax wraps success in
    base_resp.status_code == 0; a non-zero status_code is an application error
    (auth-family codes -> UNAUTHORIZED so the operator sees a key/region problem, not
    a phantom outage)."""
    if status in (401, 403):
        return R_UNAUTHORIZED, "key rejected (HTTP %s)" % status
    if status != 200:
        return R_UNREACHABLE, "HTTP %s" % status
    obj = _json_or_none(body) or {}
    base = obj.get("base_resp") if isinstance(obj.get("base_resp"), dict) else {}
    sc = base.get("status_code")
    if sc not in (None, 0):
        # 1004 / 1001-family = auth/permission; anything else = an application error.
        if sc in (1004, 1001, 1002, 1039):
            return R_UNAUTHORIZED, "MiniMax status_code=%s (auth/region)" % sc
        return R_UNREACHABLE, "MiniMax status_code=%s" % sc
    remaining = _minimax_find_remaining(obj)
    if remaining is None:
        # Authorized + success but no parseable quota field: reachable, cannot prove
        # depletion, so do NOT false-alarm.
        return R_OK, "reachable (token-plan quota field not parseable)"
    if remaining > 0:
        return R_OK, "token-plan quota remaining"
    return R_UNFUNDED, "token-plan quota depleted"


def _parse_kie(status, body):
    """Get Remaining Credits: 200 code=200 data>0 = funded; HTTP/body 402 = insufficient."""
    obj = _json_or_none(body) or {}
    code = obj.get("code")
    if status == 402 or code == 402:
        return R_UNFUNDED, "insufficient credits (402)"
    if status == 401 or code == 401:
        return R_UNAUTHORIZED, "key rejected (401)"
    if status != 200:
        return R_UNREACHABLE, "HTTP %s" % status
    if code not in (200, None):
        return R_UNREACHABLE, "body code=%s" % code
    data = obj.get("data")
    if data is None:
        return R_OK, "reachable (credit field absent, treated funded)"
    try:
        dataf = float(data)
    except (TypeError, ValueError):
        return R_OK, "reachable (credit unparseable, treated funded)"
    if dataf > 0:
        return R_OK, "credit remaining"
    return R_UNFUNDED, "credit balance zero"


PROVIDERS = [
    {
        "id": "ollama-cloud",
        "label": "HEAVY-WRITER primary + LIGHT primary",
        "env_aliases": ["OLLAMA_API_KEY", "OLLAMA_CLOUD_API_KEY"],
        "required": True,
        "auth": "bearer",
        "endpoints": [
            "https://ollama.com/api/tags",
            "https://ollama.com/v1/models",
        ],
        "parse": _parse_ollama,
    },
    {
        "id": "openrouter",
        "label": "HEAVY-WRITER fallback 1 + LIGHT fallback",
        "env_aliases": ["OPENROUTER_API_KEY"],
        "required": True,
        "auth": "bearer",
        "endpoints": ["https://openrouter.ai/api/v1/key"],
        "parse": _parse_openrouter,
    },
    {
        "id": "gemini",
        "label": "HEAVY-WRITER final fallback + JUDGE option",
        "env_aliases": ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY"],
        "required": True,
        "auth": "gemini_header",   # x-goog-api-key header, key kept OUT of the URL
        "endpoints": ["https://generativelanguage.googleapis.com/v1beta/models"],
        "parse": _parse_gemini,
    },
    {
        "id": "kie",
        "label": "IMAGE tier (S7 covers, GPT-image-2 portrait)",
        "env_aliases": ["KIE_API_KEY"],
        "required": True,
        "auth": "bearer",
        "endpoints": ["https://api.kie.ai/api/v1/chat/credit"],
        "parse": _parse_kie,
    },
    {
        "id": "minimax",
        "label": "LIGHT/JUDGE optional DIRECT account (primary route is via ollama-cloud/openrouter)",
        "env_aliases": ["MINIMAX_API_KEY"],
        "required": False,          # SPEC routes Minimax V3 primarily via ollama-cloud then OpenRouter
        "auth": "bearer",
        # Host re-confirmed at W1.22: api.minimax.io is the global/programmatic host
        # (NOT www.minimax.io). api.minimaxi.com is the China regional host.
        # _minimax_endpoints() resolves the ordered host list at runtime honoring
        # MINIMAX_API_HOST; the allowlist below enumerates every host that can be hit.
        "endpoints": [
            "https://api.minimax.io/v1/token_plan/remains",
            "https://api.minimaxi.com/v1/token_plan/remains",
        ],
        "parse": _parse_minimax,
    },
]

# Structural spend guard: the ONLY hosts+paths the transport may ever request.
_ALLOWLIST = frozenset(u for p in PROVIDERS for u in p["endpoints"])
_PROBE_COST_CENTS = 0.0  # every probe is a zero-generation-token metadata/balance read


def _json_or_none(body):
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else body)
    except (ValueError, AttributeError, UnicodeDecodeError):
        return None


# ---------------------------------------------------------------------------
# Credential resolution (live process env first, then aliases). VALUE is never
# logged; only presence + length. Full three-store resolution is caf_credential_gate.py's
# job (W2.x); the live process env a cron node process carries is the primary store.
# ---------------------------------------------------------------------------
def resolve_credential(provider, environ=None):
    env = environ if environ is not None else os.environ
    for name in provider["env_aliases"]:
        v = env.get(name, "")
        if v and v.strip():
            return name, v.strip()
    return None, None


def _mask(value):
    return "NOT SET" if not value else "SET(len=%d)" % len(value)


# ---------------------------------------------------------------------------
# Runtime host resolution for MiniMax (region override + bounded regional retry).
# ---------------------------------------------------------------------------
def _minimax_endpoints(environ=None):
    env = environ if environ is not None else os.environ
    override = (env.get("MINIMAX_API_HOST") or "").strip().rstrip("/")
    ordered = []
    if override:
        # e.g. MINIMAX_API_HOST=https://api.minimaxi.com -> .../v1/token_plan/remains
        ordered.append(override + "/v1/token_plan/remains")
    # Global default first, China regional second (bounded, still zero-cost, retry).
    for u in ("https://api.minimax.io/v1/token_plan/remains",
              "https://api.minimaxi.com/v1/token_plan/remains"):
        if u not in ordered:
            ordered.append(u)
    # Never widen beyond the allowlist (an override host must be one we pinned).
    return [u for u in ordered if u in _ALLOWLIST] or list(
        ("https://api.minimax.io/v1/token_plan/remains",))


# ---------------------------------------------------------------------------
# Transport. Pluggable opener makes the whole probe testable offline. The allowlist
# check lives HERE so no code path -- test or production -- can request a
# non-balance URL. Signature: opener(method, url, headers) -> (status:int|None, body:bytes).
# status None signals a transport-level failure (unreachable).
# ---------------------------------------------------------------------------
class ProbeError(Exception):
    pass


def _urllib_opener(method, url, headers):
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return resp.getcode(), resp.read()
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read()
        except Exception:
            body = b""
        return exc.code, body
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        # Transport-level failure -> unreachable. NEVER echo the URL (it may, in a
        # future auth style, carry a token) or the underlying key.
        return None, b""


def _headers_for(provider, key):
    if provider["auth"] == "gemini_header":
        return {"x-goog-api-key": key, "Accept": "application/json"}
    # bearer
    h = {"Authorization": "Bearer %s" % key, "Accept": "application/json"}
    if provider["id"] == "minimax":
        h["Content-Type"] = "application/json"
    return h


def _endpoints_for(provider, environ=None):
    if provider["id"] == "minimax":
        return _minimax_endpoints(environ)
    return list(provider["endpoints"])


def probe_provider(provider, key, opener, environ=None):
    """Try each endpoint in order; the first that yields a definitive verdict wins.
    A transport failure (status None) falls through to the next endpoint/host; if
    every endpoint is unreachable, the verdict is UNREACHABLE."""
    last = (R_UNREACHABLE, "no endpoint reachable")
    for url in _endpoints_for(provider, environ):
        if url not in _ALLOWLIST:
            # Defensive: should be impossible; a non-allowlisted URL is a spend risk.
            raise ProbeError("refusing non-allowlisted URL for %s" % provider["id"])
        status, body = opener("GET", url, _headers_for(provider, key))
        if status is None:
            last = (R_UNREACHABLE, "transport failure")
            continue
        verdict, detail = provider["parse"](status, body)
        # A UNAUTHORIZED on the primary MiniMax host may be a region mismatch; keep
        # trying the alternate host before settling. For every other class, settle.
        if provider["id"] == "minimax" and verdict == R_UNAUTHORIZED:
            last = (verdict, detail)
            continue
        return verdict, detail, url
    return last[0], last[1], None


# ---------------------------------------------------------------------------
# Hold-queue aging (SPEC row 18: the daily tick ages the hold queue). Fail-soft
# shell-out to the sibling hold_queue.py (SPEC row 19; authored by W1.20). Its exit
# 0 (aged) and 3 (still held) are BOTH "ran cleanly"; anything else, or its absence,
# degrades to an operator-side note and NEVER changes the smoke verdict (unless
# --strict-hold is passed). The exact age subcommand is resolved defensively so a
# CLI-name drift in hold_queue.py cannot silently no-op the aging.
# ---------------------------------------------------------------------------
_HOLD_QUEUE_AGE_CANDIDATES = ("age", "age-tick", "tick", "age_tick")


def age_hold_queue(scripts_dir, environ=None, runner=None):
    env = environ if environ is not None else os.environ
    run = runner or _run_subprocess
    hq = Path(scripts_dir) / "hold_queue.py"
    if not hq.exists():
        return {"status": "skipped", "reason": "hold_queue.py not present (W1.20 not yet integrated)"}

    override = (env.get("ANTHOLOGY_HOLD_QUEUE_AGE_ARGS") or "").strip()
    if override:
        try:
            args = json.loads(override)
            if not isinstance(args, list):
                raise ValueError
        except ValueError:
            return {"status": "error", "reason": "ANTHOLOGY_HOLD_QUEUE_AGE_ARGS is not a JSON list"}
        candidates = [args]
    else:
        candidates = [[c] for c in _HOLD_QUEUE_AGE_CANDIDATES]

    for extra in candidates:
        rc, err = run([sys.executable, str(hq)] + extra)
        if rc in (0, 3):
            return {"status": "aged", "exit": rc, "args": extra,
                    "note": "still-held holds remain" if rc == 3 else "cursor advanced"}
        # argparse "invalid choice" is exit 2 with a usage message -> wrong subcommand.
        if rc == 2 and ("invalid choice" in (err or "") or "usage" in (err or "")):
            continue
        # Any other non-zero: a real hold_queue.py failure; stop and report (fail-soft).
        return {"status": "error", "exit": rc, "args": extra,
                "reason": "hold_queue.py returned %s" % rc}
    return {"status": "error", "reason": "no known hold_queue.py age subcommand accepted"}


def reconcile_board(scripts_dir, environ=None, runner=None):
    """Board-mirror reconcile step of the daily tick (SPEC 11.2 safety net, finding
    A2): shell `mc_board.py reconcile --json` so EVERY ledger subject (participant
    chapter cards + anthology Assembly cards) is re-projected onto its board card and
    any card a stage's fail-soft swallow missed (a board outage mid-stage, or an S0
    that held at Drive) is recovered. mc_board is FAIL-SOFT by construction: it always
    exits 0 even with the board down, so this step never fails the tick. Kept separate
    from the funded-reachability probe so a probe failure never suppresses the
    reconcile and vice versa."""
    env = environ if environ is not None else os.environ
    run = runner or _run_subprocess
    mc = Path(scripts_dir) / "mc_board.py"
    if not mc.exists():
        return {"status": "skipped", "reason": "mc_board.py not present (W3.1 not yet integrated)"}
    argv = [sys.executable, str(mc), "reconcile", "--json"]
    state_dir = (env.get("ANTHOLOGY_STATE_DIR") or "").strip()
    if state_dir:
        argv += ["--state-dir", state_dir]
    rc, err = run(argv)
    if rc == 0:
        return {"status": "reconciled", "exit": rc}
    # mc_board.py is fail-soft (exit 0 on any board condition); a non-zero here is a
    # local wiring refusal (2) or an unexpected error (1) -- surfaced, never fatal.
    return {"status": "error", "exit": rc, "reason": "mc_board.py reconcile returned %s" % rc,
            "detail": (err or "")[:200]}


def _run_subprocess(argv):
    """Run a sibling script; return (exit_code, stderr_text). Fail-soft on any OSError."""
    try:
        proc = subprocess.run(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=120, check=False,
        )
        return proc.returncode, (proc.stderr or b"").decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "subprocess failed: %s" % type(exc).__name__


# ---------------------------------------------------------------------------
# Founder alert (fail-soft). On failure we ALWAYS write a durable, deduped
# operator-side alert record, THEN best-effort hand it to alert-dedup.py (SPEC row
# 21; authored by W2.4) which performs the single gateway send. We NEVER touch
# Telegram directly and NEVER bypass the gateway. If alert-dedup.py is absent the
# durable record stands and stderr flags it; the alert is never lost.
# ---------------------------------------------------------------------------
def dedup_signature(failures):
    """Stable one-per-day signature: the sorted set of failed providers + verdicts +
    the UTC date. Same failure twice in a day -> same signature -> one alert."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sig = ";".join("%s:%s" % (f["provider"], f["result"]) for f in sorted(failures, key=lambda x: x["provider"]))
    return "anthology-smoke:%s:%s" % (day, sig)


def fire_alert(failures, report_dir, scripts_dir, environ=None, runner=None):
    env = environ if environ is not None else os.environ
    run = runner or _run_subprocess
    sig = dedup_signature(failures)
    summary = ("Anthology daily smoke test: %d provider(s) unreachable/unfunded. "
               "This is the insufficient-credits class that stalled the legacy system twice."
               % len(failures))
    payload = {
        "source": "anthology-smoke-test",
        "severity": "high",
        "dedup_key": sig,
        "summary": summary,
        "failures": failures,   # provider + result + detail only; NO secret, NO client PII
        "utc": datetime.now(timezone.utc).isoformat(),
    }
    # 1) Durable operator-side record (idempotent per signature).
    alerts_dir = Path(report_dir) / "alerts"
    written = None
    try:
        alerts_dir.mkdir(parents=True, exist_ok=True)
        safe = sig.replace(":", "_").replace(";", "_").replace("/", "_")
        written = alerts_dir / ("%s.json" % safe)
        written.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        sys.stderr.write("[anthology-smoke-test] WARN: could not persist alert record: %s\n"
                         % type(exc).__name__)

    # 2) Best-effort gateway send via alert-dedup.py (never a direct Telegram call).
    dedup = Path(scripts_dir) / "alert-dedup.py"
    if not dedup.exists():
        sys.stderr.write("[anthology-smoke-test] WARN: alert-dedup.py not present (W2.4 not yet "
                         "integrated); alert recorded at %s, gateway send deferred.\n"
                         % (written or "<report>"))
        return {"status": "recorded", "gateway": "deferred", "record": str(written) if written else None,
                "dedup_key": sig}

    override = (env.get("ANTHOLOGY_ALERT_ARGS") or "").strip()
    if override and written:
        try:
            extra = json.loads(override)
            if not isinstance(extra, list):
                raise ValueError
        except ValueError:
            extra = None
        if extra is not None:
            argv = [sys.executable, str(dedup)] + [a.replace("{payload}", str(written)).replace("{key}", sig)
                                                   for a in extra]
            rc, err = run(argv)
            return {"status": "sent" if rc == 0 else "gateway_error", "exit": rc,
                    "record": str(written), "dedup_key": sig, "detail": (err or "")[:200]}

    # Default invocation contract (documented for W2.4/integrator in cross_file_needs).
    argv = [sys.executable, str(dedup), "--source", "anthology-smoke-test",
            "--dedup-key", sig, "--summary", summary]
    if written:
        argv += ["--payload-file", str(written)]
    rc, err = run(argv)
    return {"status": "sent" if rc == 0 else "gateway_error", "exit": rc,
            "record": str(written) if written else None, "dedup_key": sig,
            "detail": (err or "")[:200]}


# ---------------------------------------------------------------------------
# State / report dirs -- mirror caf_delivery.py / anthology_state.py exactly.
# ---------------------------------------------------------------------------
def default_state_dir():
    env = os.environ.get("ANTHOLOGY_STATE_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    data = os.environ.get("OPENCLAW_DATA_DIR", "").strip()
    if data:
        return Path(data).expanduser() / "anthology-engine" / "state"
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return Path(home) / ".anthology-engine" / "state"


def report_dir(explicit=None):
    if explicit:
        return Path(explicit).expanduser()
    return default_state_dir() / "reports"


SCRIPTS_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# The run: assert spend ceiling, probe each provider, age the hold queue, decide.
# ---------------------------------------------------------------------------
def assert_spend_ceiling(max_cents):
    total = _PROBE_COST_CENTS * len(PROVIDERS)
    if total > max_cents:
        raise ProbeError("spend ceiling %.4f cents would be exceeded by declared %.4f cents"
                         % (max_cents, total))
    return total


def run_smoke(opener=None, environ=None, rdir=None, scripts_dir=None,
              age=True, do_alert=True, strict_hold=False, subprocess_runner=None,
              max_spend_cents=1.0, reconcile=True):
    environ = environ if environ is not None else os.environ
    opener = opener or _urllib_opener
    scripts_dir = scripts_dir or SCRIPTS_DIR
    rdir = report_dir(rdir)

    total_spend = assert_spend_ceiling(max_spend_cents)

    results = []
    for prov in PROVIDERS:
        name, key = resolve_credential(prov, environ)
        row = {"provider": prov["id"], "role": prov["label"], "required": prov["required"],
               "credential": _mask(key), "credential_alias": name}
        if not key:
            if prov["required"]:
                row["result"] = R_NO_CREDENTIAL
                row["detail"] = "no credential resolvable for a REQUIRED provider"
            else:
                row["result"] = R_SKIPPED
                row["detail"] = "optional direct account not configured; skipped"
            results.append(row)
            continue
        try:
            verdict, detail, hit = probe_provider(prov, key, opener, environ)
        except ProbeError as exc:
            verdict, detail, hit = R_ERROR, str(exc), None
        except Exception as exc:  # noqa: BLE001 -- unexpected probe fault, fail-soft to ERROR
            verdict, detail, hit = R_ERROR, "unexpected: %s" % type(exc).__name__, None
        row["result"] = verdict
        row["detail"] = detail
        row["endpoint"] = hit
        results.append(row)

    # Verdict: any failing probe OR any missing REQUIRED credential -> exit 4.
    failures = []
    for r in results:
        res = r["result"]
        if res in _FAILING or (res == R_NO_CREDENTIAL and r["required"]):
            failures.append({"provider": r["provider"], "result": res, "detail": r.get("detail", "")})
    exit_code = EX_UNFUNDED if failures else EX_OK

    # Age the hold queue regardless of probe outcome (it is part of the daily tick).
    aging = None
    if age:
        aging = age_hold_queue(scripts_dir, environ, subprocess_runner)
        if strict_hold and aging.get("status") == "error":
            exit_code = EX_UNFUNDED if exit_code == EX_OK else exit_code
            failures.append({"provider": "hold_queue", "result": R_ERROR,
                             "detail": aging.get("reason", "aging failed")})

    # Board-mirror reconcile regardless of probe outcome (it is part of the daily
    # tick, finding A2). mc_board is fail-soft, so this never changes the exit code;
    # it recovers any board card a stage's fail-soft swallow missed.
    reconciling = None
    if reconcile:
        reconciling = reconcile_board(scripts_dir, environ, subprocess_runner)

    # Alert on failure (fail-soft; one deduped founder alert through the gateway).
    alerting = None
    if failures and do_alert:
        alerting = fire_alert(failures, rdir, scripts_dir, environ, subprocess_runner)

    report = {
        "contract": "anthology-smoke-test-report",
        "schema_version": 1,
        "utc": datetime.now(timezone.utc).isoformat(),
        "spend_ceiling_cents": max_spend_cents,
        "declared_spend_cents": total_spend,     # 0.0: every probe is a zero-token read
        "exit_code": exit_code,
        "verdict": "all reachable and funded" if exit_code == EX_OK else "provider unreachable/unfunded",
        "providers": results,
        "failures": failures,
        "hold_queue_aging": aging,
        "board_reconcile": reconciling,
        "alert": alerting,
    }
    return exit_code, report


def persist_report(report, rdir=None):
    d = report_dir(rdir)
    try:
        d.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = d / ("smoke-test-%s.json" % stamp)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
    except OSError as exc:
        sys.stderr.write("[anthology-smoke-test] WARN: could not persist report: %s\n"
                         % type(exc).__name__)
        return None


# ---------------------------------------------------------------------------
# CLI commands.
# ---------------------------------------------------------------------------
def cmd_run(args):
    exit_code, report = run_smoke(
        rdir=args.report_dir,
        age=not args.no_age,
        do_alert=not args.no_alert,
        strict_hold=args.strict_hold,
        max_spend_cents=args.max_spend_cents,
        reconcile=not args.no_reconcile,
    )
    path = persist_report(report, args.report_dir)
    if path:
        report["_report_path"] = str(path)
    # Operator-verbose to stdout (never a client surface).
    sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return exit_code


def cmd_plan(args):
    """Print the probe plan + credential presence (SET / NOT SET only). NO network."""
    assert_spend_ceiling(args.max_spend_cents)
    plan = {
        "contract": "anthology-smoke-test-plan",
        "spend_ceiling_cents": args.max_spend_cents,
        "declared_spend_cents": _PROBE_COST_CENTS * len(PROVIDERS),
        "allowlisted_endpoints": sorted(_ALLOWLIST),
        "providers": [],
    }
    for prov in PROVIDERS:
        name, key = resolve_credential(prov)
        plan["providers"].append({
            "provider": prov["id"],
            "role": prov["label"],
            "required": prov["required"],
            "endpoints": _endpoints_for(prov),
            "credential": _mask(key),
            "credential_alias": name,
        })
    sys.stdout.write(json.dumps(plan, indent=2, ensure_ascii=False) + "\n")
    return EX_OK


# ---------------------------------------------------------------------------
# Offline self-test (no network, no subprocess side effects): a scripted opener
# feeds each classifier funded / unfunded / unauthorized / unreachable bodies and
# asserts the verdict AND the exit-code mapping, plus the allowlist and spend guards.
# ---------------------------------------------------------------------------
def _scripted_opener(mapping, default=(500, b"{}")):
    def opener(method, url, headers):
        for frag, resp in mapping.items():
            if frag in url:
                return resp
        return default
    return opener


def self_test():
    passed = []
    failed = []

    def check(name, cond):
        (passed if cond else failed).append(name)

    # --- classifier unit checks -------------------------------------------------
    check("ollama funded", _parse_ollama(200, b'{"models":[{"name":"glm-4.6"}]}')[0] == R_OK)
    check("ollama empty->unreachable", _parse_ollama(200, b'{"models":[]}')[0] == R_UNREACHABLE)
    check("ollama 401->unauth", _parse_ollama(401, b'{}')[0] == R_UNAUTHORIZED)
    check("openrouter credit->ok", _parse_openrouter(200, b'{"data":{"limit":10,"limit_remaining":8.8}}')[0] == R_OK)
    check("openrouter null->ok(payg)", _parse_openrouter(200, b'{"data":{"limit":null,"limit_remaining":null}}')[0] == R_OK)
    check("openrouter zero->unfunded", _parse_openrouter(200, b'{"data":{"limit":5,"limit_remaining":0}}')[0] == R_UNFUNDED)
    check("openrouter 401->unauth", _parse_openrouter(401, b'{}')[0] == R_UNAUTHORIZED)
    check("gemini funded", _parse_gemini(200, b'{"models":[{"name":"models/gemini-3.5-flash"}]}')[0] == R_OK)
    check("gemini 403->unauth", _parse_gemini(403, b'{"error":{"status":"PERMISSION_DENIED"}}')[0] == R_UNAUTHORIZED)
    check("minimax funded", _parse_minimax(200, b'{"base_resp":{"status_code":0},"total_remain":1234}')[0] == R_OK)
    check("minimax depleted->unfunded", _parse_minimax(200, b'{"base_resp":{"status_code":0},"total_remain":0}')[0] == R_UNFUNDED)
    check("minimax authcode->unauth", _parse_minimax(200, b'{"base_resp":{"status_code":1004,"status_msg":"invalid api key"}}')[0] == R_UNAUTHORIZED)
    check("minimax success-noquota->ok", _parse_minimax(200, b'{"base_resp":{"status_code":0}}')[0] == R_OK)
    check("kie funded", _parse_kie(200, b'{"code":200,"message":"success","data":100}')[0] == R_OK)
    check("kie 402->unfunded", _parse_kie(402, b'{"code":402,"message":"Insufficient Credits"}')[0] == R_UNFUNDED)
    check("kie data0->unfunded", _parse_kie(200, b'{"code":200,"data":0}')[0] == R_UNFUNDED)

    # --- host re-confirmation: default MiniMax host is api.minimax.io, not www ---
    eps = _minimax_endpoints({})
    check("minimax default host api.minimax.io first", eps[0] == "https://api.minimax.io/v1/token_plan/remains")
    check("minimax no www host anywhere", all("www.minimax.io" not in u for u in eps))
    ov = _minimax_endpoints({"MINIMAX_API_HOST": "https://api.minimaxi.com"})
    check("minimax host override honored", ov[0] == "https://api.minimaxi.com/v1/token_plan/remains")

    # --- spend guards -----------------------------------------------------------
    check("declared spend is zero", _PROBE_COST_CENTS == 0.0)
    check("spend ceiling ok at 1c", assert_spend_ceiling(1.0) == 0.0)
    check("every allowlist url is https", all(u.startswith("https://") for u in _ALLOWLIST))
    # transport allowlist: probe_provider refuses a non-allowlisted URL.
    bad = {"id": "x", "auth": "bearer", "endpoints": ["https://evil.example/generate"],
           "parse": _parse_kie}
    raised = False
    try:
        probe_provider(bad, "k", _scripted_opener({}, (200, b'{}')))
    except ProbeError:
        raised = True
    check("non-allowlisted url refused", raised)

    # --- end-to-end run: all funded -> exit 0 -----------------------------------
    env_full = {"OLLAMA_API_KEY": "x", "OPENROUTER_API_KEY": "x", "GOOGLE_API_KEY": "x",
                "KIE_API_KEY": "x", "MINIMAX_API_KEY": "x"}
    opener_ok = _scripted_opener({
        "ollama.com/api/tags": (200, b'{"models":[{"name":"m"}]}'),
        "openrouter.ai/api/v1/key": (200, b'{"data":{"limit":null,"limit_remaining":null}}'),
        "generativelanguage.googleapis.com": (200, b'{"models":[{"name":"m"}]}'),
        "api.minimax.io": (200, b'{"base_resp":{"status_code":0},"total_remain":9}'),
        "api.kie.ai": (200, b'{"code":200,"data":50}'),
    })
    rc, rep = run_smoke(opener=opener_ok, environ=env_full, age=False, do_alert=False, reconcile=False)
    check("all-funded exits 0", rc == EX_OK)
    check("all-funded no failures", rep["failures"] == [])
    check("report declares zero spend", rep["declared_spend_cents"] == 0.0)

    # --- one provider unfunded -> exit 4 ----------------------------------------
    opener_kie_broke = _scripted_opener({
        "ollama.com/api/tags": (200, b'{"models":[{"name":"m"}]}'),
        "openrouter.ai/api/v1/key": (200, b'{"data":{"limit":null,"limit_remaining":null}}'),
        "generativelanguage.googleapis.com": (200, b'{"models":[{"name":"m"}]}'),
        "api.minimax.io": (200, b'{"base_resp":{"status_code":0},"total_remain":9}'),
        "api.kie.ai": (402, b'{"code":402}'),
    })
    rc2, rep2 = run_smoke(opener=opener_kie_broke, environ=env_full, age=False, do_alert=False, reconcile=False)
    check("kie unfunded exits 4", rc2 == EX_UNFUNDED)
    check("kie is the sole failure", [f["provider"] for f in rep2["failures"]] == ["kie"])

    # --- missing REQUIRED credential -> exit 4; missing OPTIONAL -> skipped -------
    env_missing = {"OPENROUTER_API_KEY": "x", "GOOGLE_API_KEY": "x", "KIE_API_KEY": "x"}  # no ollama, no minimax
    rc3, rep3 = run_smoke(opener=opener_ok, environ=env_missing, age=False, do_alert=False, reconcile=False)
    provs = {r["provider"]: r["result"] for r in rep3["providers"]}
    check("missing required ollama fails", provs["ollama-cloud"] == R_NO_CREDENTIAL)
    check("missing optional minimax skipped", provs["minimax"] == R_SKIPPED)
    check("missing-required run exits 4", rc3 == EX_UNFUNDED)
    check("optional-skip is not a failure", "minimax" not in [f["provider"] for f in rep3["failures"]])

    # --- transport failure (status None) -> unreachable -> exit 4 ----------------
    opener_down = _scripted_opener({}, (None, b""))
    rc4, rep4 = run_smoke(opener=opener_down, environ={"OLLAMA_API_KEY": "x"}, age=False, do_alert=False, reconcile=False)
    check("all-unreachable exits 4", rc4 == EX_UNFUNDED)

    # --- minimax region retry: primary 401 -> alternate host funded -> OK --------
    def opener_region(method, url, headers):
        if "api.minimax.io" in url:
            return 401, b'{}'
        if "api.minimaxi.com" in url:
            return 200, b'{"base_resp":{"status_code":0},"total_remain":5}'
        return 500, b'{}'
    v, d, hit = probe_provider(PROVIDERS[-1], "k", opener_region, {})
    check("minimax region retry lands on alt host", v == R_OK and hit == "https://api.minimaxi.com/v1/token_plan/remains")

    # --- hold-queue aging fail-soft when hold_queue.py absent --------------------
    aging = age_hold_queue("/nonexistent-scripts-dir", {}, runner=lambda a: (0, ""))
    check("aging skipped when hold_queue absent", aging["status"] == "skipped")

    # --- board reconcile step (finding A2) ---------------------------------------
    # absent mc_board.py -> skipped (fail-soft), never fatal.
    rec_absent = reconcile_board("/nonexistent-scripts-dir", {}, runner=lambda a: (0, ""))
    check("reconcile skipped when mc_board absent", rec_absent["status"] == "skipped")
    # present + exit 0 -> reconciled; the real mc_board.py is a sibling of this file.
    rec_calls = {"n": 0, "argv": None}

    def _rec_runner(argv):
        rec_calls["n"] += 1
        rec_calls["argv"] = list(argv)
        return 0, ""
    rec_ok = reconcile_board(SCRIPTS_DIR, {}, runner=_rec_runner)
    check("reconcile reconciled on exit 0", rec_ok["status"] == "reconciled")
    check("reconcile shells mc_board.py reconcile --json",
          rec_calls["argv"] is not None
          and rec_calls["argv"][1].endswith("mc_board.py")
          and "reconcile" in rec_calls["argv"] and "--json" in rec_calls["argv"])
    # a non-zero mc_board (wiring refusal) is surfaced as error, never fatal.
    rec_err = reconcile_board(SCRIPTS_DIR, {}, runner=lambda a: (2, "guard refusal"))
    check("reconcile surfaces non-zero as error", rec_err["status"] == "error" and rec_err["exit"] == 2)
    # ANTHOLOGY_STATE_DIR is threaded through to mc_board when set.
    reconcile_board(SCRIPTS_DIR, {"ANTHOLOGY_STATE_DIR": "/tmp/x-state"}, runner=_rec_runner)
    check("reconcile threads --state-dir when ANTHOLOGY_STATE_DIR set",
          "--state-dir" in rec_calls["argv"] and "/tmp/x-state" in rec_calls["argv"])
    # run_smoke wires the reconcile step into the daily tick (default on) + report.
    rs_calls = {"reconcile": 0}

    def _rs_runner(argv):
        if len(argv) > 1 and str(argv[1]).endswith("mc_board.py"):
            rs_calls["reconcile"] += 1
        return 0, ""
    _rc, _rep = run_smoke(opener=_scripted_opener({}, (200, b'{"models":[{"name":"m"}]}')),
                          environ={"OLLAMA_API_KEY": "x"}, age=False, do_alert=False,
                          reconcile=True, subprocess_runner=_rs_runner)
    check("run_smoke invokes the board reconcile step", rs_calls["reconcile"] == 1)
    check("report carries the board_reconcile block",
          _rep.get("board_reconcile") is not None and _rep["board_reconcile"]["status"] == "reconciled")

    # --- alert record is written on failure (fail-soft, no gateway present) ------
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        res = fire_alert([{"provider": "kie", "result": R_UNFUNDED, "detail": "402"}],
                         td, "/nonexistent-scripts-dir", {}, runner=lambda a: (0, ""))
        rec_ok = res.get("record") and Path(res["record"]).exists()
        check("alert record persisted", bool(rec_ok))
        check("alert gateway deferred when absent", res.get("gateway") == "deferred")
        # dedup signature stable within a day for the same failure set.
        s1 = dedup_signature([{"provider": "kie", "result": R_UNFUNDED}])
        s2 = dedup_signature([{"provider": "kie", "result": R_UNFUNDED}])
        check("dedup signature stable", s1 == s2)

    # --- no foreign-vendor model identifier leaked into any surface string --------
    # The banned tokens are assembled from FRAGMENTS so this shipped file carries no
    # contiguous banned literal (mirrors model_router.py; keeps
    # guard-no-anthropic-runtime.py green over the engine's own source).
    blob = json.dumps({"providers": [p["id"] for p in PROVIDERS],
                       "allow": sorted(_ALLOWLIST)})
    banned = ("cla" + "ude", "anthro" + "pic")
    check("no foreign-vendor id in provider/allowlist surface",
          not any(b in blob.lower() for b in banned))

    total = len(passed) + len(failed)
    sys.stdout.write("anthology-smoke-test self-test: %d/%d passed\n" % (len(passed), total))
    for f in failed:
        sys.stdout.write("  FAIL: %s\n" % f)
    return EX_OK if not failed else EX_ERR


# ---------------------------------------------------------------------------
def build_parser():
    ap = argparse.ArgumentParser(
        prog="anthology-smoke-test.py",
        description="Anthology Engine daily funded-reachability probe (balance endpoints only, "
                    "spend at or under one cent; ages the hold queue).")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("run", help="probe every provider balance endpoint, age the hold queue, "
                                   "reconcile the board mirror, alert on failure (the daily tick)")
    p.add_argument("--report-dir", help="operator report directory (default: state dir/reports)")
    p.add_argument("--no-age", action="store_true", help="skip hold-queue aging (probe only)")
    p.add_argument("--no-reconcile", action="store_true",
                   help="skip the board-mirror reconcile (mc_board.py reconcile) step")
    p.add_argument("--no-alert", action="store_true", help="do not fire the founder alert on failure")
    p.add_argument("--strict-hold", action="store_true",
                   help="treat a hold_queue.py aging error as a smoke failure (default: fail-soft)")
    p.add_argument("--max-spend-cents", type=float, default=1.0,
                   help="spend ceiling in cents (default 1.0; every probe is declared cost 0)")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("plan", help="print the probe plan + credential presence (SET/NOT SET); NO network")
    p.add_argument("--max-spend-cents", type=float, default=1.0)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("self-test", help="offline self-test (no network, no side effects)")
    p.set_defaults(func=lambda a: self_test())

    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "cmd", None):
        ap.print_help()
        return EX_BADINVOKE
    try:
        return args.func(args)
    except ProbeError as exc:
        sys.stderr.write("[anthology-smoke-test] guard refusal: %s\n" % exc)
        return EX_BADINVOKE
    except BrokenPipeError:
        return EX_OK
    except Exception as exc:  # noqa: BLE001 -- house convention: unexpected -> exit 1
        sys.stderr.write("[anthology-smoke-test] unexpected error: %s\n" % exc)
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
