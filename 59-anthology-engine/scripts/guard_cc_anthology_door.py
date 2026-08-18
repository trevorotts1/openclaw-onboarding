#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: guard_cc_anthology_door.py  (NEW-7)
# PROVES THE COMMAND CENTER ANTHOLOGY INTEGRATION OVER THE LIVE COMMAND
# CENTER — NEVER OVER DOCS. ENGINE-MANIFEST script_inventory n=46.
# -----------------------------------------------------------------------------
# WHAT THIS OWNS
#   The Command Center anthology surface is the engine's Layer-4 board door
#   (SKILL.md L4: "ALL INSIDE THE CLIENT'S OWN COMMAND CENTER"; SPEC 11.3
#   both-door rule; the gate route is the cc repo's
#   src/app/api/anthology/gate/route.ts). Four integration seams must hold for
#   the producer's board door to actually work, and this guard PROVES each one
#   with real requests against the live Command Center:
#
#     1. GATE ROUTE AUTH   -- GET /api/anthology/gate is BEARER-GATED for an
#        external caller: a request with NO Authorization header is rejected
#        (401 missing-header), a WRONG bearer is rejected (401
#        token-mismatch), and the CORRECT bearer passes the middleware
#        (Gate B, cc src/middleware.ts). The route is a NON-webhook route
#        (absent from WEBHOOK_SECRET_ROUTES) and is listed in
#        BEARER_REQUIRED_WRITE_ROUTES, so no tokenless path exists. A box
#        whose MC_API_TOKEN is unset rejects with 503 (fail-closed
#        mc-api-token-unset) -- the no-token probe proves THAT too.
#     2. DONE-ACTION 403    -- POST /api/anthology/gate with action "done" is
#        refused with HTTP 403 BEFORE the engine is ever shelled
#        (FORBIDDEN_ACTIONS, gate route lines 151-162): a producer can never
#        self-grade its own card; review -> done belongs ONLY to the
#        independent QC auto-scorer at >= 8.5. The guard proves the 403 stays
#        explicit and testable, and that the probe body can never record a
#        real decision (subjectKey is an explicit guard placeholder that no
#        live ledger key collides with).
#     3. WORKSPACE RESOLUTION -- GET /api/workspaces carries the seeded
#        "anthology" workspace (slug present, lowercase-equal), and GET
#        /api/workspaces/{slug} resolves it BY SLUG (cc route resolves id OR
#        slug), so the home tile's /workspace/anthology route is a live board,
#        never a dead link.
#     4. HOME-SCREEN TILE   -- GET /api/engine-db reports the engine DB
#        present for slug "anthology" (cc src/app/api/engine-db/route.ts
#        probes ~/.anthology-engine/state/anthology_state.db), and workspace
#        slug presence comes from /api/workspaces -- exactly the two fetches
#        the home dashboard gates the producer card on
#        (src/lib/dashboard-workspaces.ts selectProducerCardSlugs: slug
#        PRESENT and engine DB PRESENT -> live card; any fetch failure renders
#        a degraded slot, never a live card).
#
#   The guard FAILS CLOSED on every seam: a missing credential label, an
#   unreachable Command Center, a non-2xx response, a malformed payload, or an
#   unexpected shape are FAILURES with an operator surface -- never a silent
#   pass. A Command Center whose MC_API_TOKEN is unset (503) cannot
#   authenticate ANY external board-door caller and is reported as a held
#   dependency (exit 3), not a green.
#
#   CREDENTIAL DISCIPLINE (house doctrine): the Command Center API token is
#   resolved BY LABEL only -- live process env first, then the engine-config
#   board.api_token_label, then the standard MC_API_TOKEN name. Only SET /
#   NOT SET (plus length) is ever surfaced; the VALUE is never printed, never
#   logged, never placed in a URL, and travels only inside the
#   Authorization: Bearer header of the requests that need it.
#
#   TRANSPORT: stdlib urllib only; every request carries the house browser
#   User-Agent (Convert and Flow / GHL surfaces are Cloudflare-fronted and
#   403 urllib's Python-urllib UA at the WAF edge, CF error 1010 -- the same
#   byte-for-byte constant the sibling adapters carry). A reachable non-2xx is
#   classified (auth rejection vs 404 route-missing); only genuine
#   unreachability (URLError / timeout / OSError) maps to the held class.
#   REQUIRE_CF_ACCESS=true boxes must be probed through the tunnel/edge
#   (Layer 1 rejects bare direct calls) -- the same constraint mc_board.py
#   lives under; the canary is designed for the plain-tunnel boxes the fleet
#   runs.
#
# EXIT CODES (house convention; ENGINE-MANIFEST row 46):
#   0  all four checks PASS
#   4  one or more checks FAIL (gate route auth, done-action 403, workspace
#      resolution, or home-screen tile) -- the drift/alarm path
#   2  bad invocation (unknown flag, missing required argument, bad --url)
#   3  credential label NOT SET or Command Center unreachable (dependency /
#      held; re-runnable)
#   1  unexpected error
#
# USAGE:
#   guard_cc_anthology_door.py [--url CC_URL] [--token-label LABEL] [--json]
#   guard_cc_anthology_door.py --self-test
#
# Runs in CI and as a canary. Zero Anthropic identifiers ship in this file.
# =============================================================================
"""guard_cc_anthology_door.py — Command Center anthology-integration prover."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ---- exit codes (house convention) ------------------------------------------
EX_OK = 0
EX_ERR = 1
EX_BADINVOKE = 2
EX_DEP = 3          # credential label NOT SET, or Command Center unreachable
EX_DRIFT = 4        # one or more integration checks FAIL

# ---- Command Center surface (proved against cc repo sources, 2026-08-10) -----
DEFAULT_BASE_URL = "http://localhost:4000"
DEFAULT_BASE_URL_ENV = ("MISSION_CONTROL_URL", "MC_URL")   # first present wins
DEFAULT_API_TOKEN_LABEL = "MC_API_TOKEN"                   # cc env name
GATE_PATH = "/api/anthology/gate"
WORKSPACES_PATH = "/api/workspaces"
ENGINE_DB_PATH = "/api/engine-db"
ANTHOLOGY_SLUG = "anthology"

# The browser UA is REQUIRED: Command Center deployments fronted by Cloudflare
# (Access or plain tunnel) 403 urllib's default "Python-urllib/x.y" UA at the
# WAF edge (CF error 1010) before the request reaches the app. Byte-for-byte
# the sibling adapters' constant (anthology_registry.py CAF_BROWSER_UA).
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

HTTP_TIMEOUT = 20  # seconds; a hung Command Center must not wedge the guard

# ---- layout ---------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = SKILL_DIR / "config" / "engine-config.json"
TEMPLATE_CONFIG = SKILL_DIR / "config" / "engine-config.template.json"

# ---- check ids (stable, surfaced in every report) ---------------------------
CHK_AUTH_NO_TOKEN = "gate-route-auth-no-token"     # 401/403/503, never 200
CHK_AUTH_WRONG_TOKEN = "gate-route-auth-wrong-token"  # 401, never 200
CHK_AUTH_GOOD_TOKEN = "gate-route-auth-good-token"    # 200/400 (route validates query)
CHK_DONE_403 = "done-action-403"                       # POST done -> 403
CHK_WORKSPACE_SLUG = "workspace-slug-resolves"         # /api/workspaces -> slug
CHK_WORKSPACE_BY_SLUG = "workspace-resolves-by-slug"   # /api/workspaces/{slug} -> 200
CHK_TILE_MIDDLEWARE = "home-tile-middleware-secret"    # token SET on this box
CHK_TILE_SLUG = "home-tile-workspace-slug"             # workspaces slug present
CHK_TILE_ENGINE_DB = "home-tile-engine-db"             # engine-db.anthology is true


def _load_config(explicit=None):
    """Best-effort read of the resolved per-box engine config, else the
    template, else {}. Only the board.* label-name knob is consulted; the file
    is owned by other units and never written from here (mc_board pattern)."""
    for p in (Path(explicit) if explicit else None, DEFAULT_CONFIG, TEMPLATE_CONFIG):
        if p and p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
    return {}


def _env_first(names):
    """(name, value|None) for the first env var in names that is set. The
    VALUE is never printed anywhere; only SET / NOT SET is surfaced."""
    for n in names:
        v = os.environ.get(n, "").strip()
        if v:
            return n, v
    return (names[0] if names else None), None


def _token_label(cfg):
    """Resolve the API-token LABEL name (never the value): engine-config
    board.api_token_label first, then the CC env name."""
    board = (cfg.get("board") or {}) if isinstance(cfg, dict) else {}
    return board.get("api_token_label") or DEFAULT_API_TOKEN_LABEL


def _base_url(cfg, explicit_url=None):
    """Resolve the Command Center base URL: explicit --url wins, then an env
    NAME from config board.base_url_env, then the standard env names, then the
    safe localhost default (mc_board resolution, mirrored)."""
    if explicit_url:
        return explicit_url.rstrip("/")
    board = (cfg.get("board") or {}) if isinstance(cfg, dict) else {}
    env_names = []
    if board.get("base_url_env"):
        env_names.append(board["base_url_env"])
    env_names.extend(DEFAULT_BASE_URL_ENV)
    _n, url = _env_first(env_names)
    return (url or board.get("base_url") or DEFAULT_BASE_URL).rstrip("/")


# ---- pure decision predicates (the self-test exercises THESE, never copies) --
def _is_bearer_auth_rejection(status):
    """The middleware's external /api/* rejections for a bearer-gated route:
    401 missing-header / token-mismatch, 503 mc-api-token-unset, and a box
    misconfigured at the edge (403). NEVER 200/202/400."""
    return status in (401, 403, 503)


def _auth_good_passes(status):
    """The good-token probe passes when the middleware let the request
    through: the route then answers 400 (subjectKey missing -- validation, the
    expected signature) or 200. Anything else (404 route missing on an old
    CC, 500, an auth rejection) is a FAIL."""
    return status in (200, 400)


def _done_forbidden(status):
    """The done-action invariant: only a literal 403 proves the route's
    FORBIDDEN_ACTIONS guard fired. 200/202/422 would mean the guard vanished;
    401/503 mean the auth seam broke (reported by check 1); None means the
    Command Center is unreachable."""
    return status == 403


def _slug_present(body, wanted=ANTHOLOGY_SLUG):
    """True iff the /api/workspaces JSON payload is a list carrying a row
    whose slug is lowercase-equal to the wanted slug. Tolerant of a
    non-list payload and missing/non-string slugs (returns False -- fail
    closed), never throws."""
    rows = body if isinstance(body, list) else []
    slugs = {str(r.get("slug", "")).lower() for r in rows if isinstance(r, dict)}
    return wanted in slugs


def _engine_db_present(status, body, wanted=ANTHOLOGY_SLUG):
    """True iff /api/engine-db answered 200 and reports the engine DB present
    for the wanted slug (JSON true exactly -- a string "present" or an int
    does not count)."""
    return (status == 200 and isinstance(body, dict)
            and body.get(wanted) is True)


def _all_checks_passed(checks):
    """True iff every check value is exactly True. None (held/unreachable)
    and False are never passes -- fail closed. Keys prefixed '_' are report
    metadata, not checks."""
    return all(v is True for k, v in checks.items() if not k.startswith("_"))


# ---- transport ---------------------------------------------------------------
def _request(url, token=None, method="GET", body_bytes=None, timeout=HTTP_TIMEOUT):
    """One HTTP request with the house browser UA. Returns
    (status_code:int|None, body:dict|None). A reachable non-2xx returns its
    real code plus the parsed JSON body (or None) so the caller can classify an
    auth/scope rejection. Only genuine unreachability (URLError / timeout /
    OSError) returns (None, None). The token value never leaves this function
    except inside the Authorization header."""
    headers = {"User-Agent": BROWSER_UA, "Accept": "application/json"}
    if token is not None:
        headers["Authorization"] = "Bearer %s" % token
    if body_bytes is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body_bytes, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.getcode(), json.loads(raw)
            except ValueError:
                return resp.getcode(), None
    except urllib.error.HTTPError as e:            # reachable server, non-2xx
        raw = e.read().decode("utf-8", "replace") if e.fp else ""
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, None
    except (urllib.error.URLError, OSError):       # genuinely unreachable
        return None, None


# ---- the four seam checks -----------------------------------------------------
def _check_auth(base, token):
    """CHECK 1 -- gate route auth. Three probes against GET
    /api/anthology/gate: no token (must be rejected), wrong token (must be
    rejected), correct token (must pass the middleware; the route then answers
    400 for the missing subjectKey -- the pass signature). The middleware
    gates BEFORE the route handler, so every status below is decided by the
    auth layer."""
    results = {}
    url = "%s%s" % (base, GATE_PATH)

    status, _body = _request(url, token=None)
    if status is None:
        results[CHK_AUTH_NO_TOKEN] = None
    else:
        results[CHK_AUTH_NO_TOKEN] = _is_bearer_auth_rejection(status)

    status, _body = _request(url, token="definitely-wrong-token-value")
    if status is None:
        results[CHK_AUTH_WRONG_TOKEN] = None
    else:
        results[CHK_AUTH_WRONG_TOKEN] = status == 401

    if token is None:
        # Credential NOT SET: the good-token probe cannot run; the no-token
        # probe already proved the box fails closed. The caller reports this
        # as a held dependency.
        results[CHK_AUTH_GOOD_TOKEN] = None
    else:
        status, _body = _request(url, token=token)
        if status is None:
            results[CHK_AUTH_GOOD_TOKEN] = None
        else:
            results[CHK_AUTH_GOOD_TOKEN] = _auth_good_passes(status)
            results["_good_status"] = status
    return results


def _check_done_403(base, token):
    """CHECK 2 -- done-action 403. POST /api/anthology/gate with
    action="done" and an EXPLICITLY INVALID subjectKey
    ("<guard-probe-no-live-subject>"): the route's FORBIDDEN_ACTIONS check
    runs BEFORE the engine is shelled, so the only correct outcome is 403.
    A 200/202/422 here means the done guard vanished; 401/503 means the auth
    seam broke (check 1 already reported it). The body can never record a
    real decision: no live subject key is ever used, and a real decide
    requires a valid subjectKey + an allowed action on an open gate."""
    results = {}
    url = "%s%s" % (base, GATE_PATH)
    body = json.dumps({
        "subjectKey": "<guard-probe-no-live-subject>",
        "action": "done",
    }).encode("utf-8")
    status, body_json = _request(url, token=token, method="POST", body_bytes=body)
    if status is None:
        results[CHK_DONE_403] = None
    else:
        results[CHK_DONE_403] = _done_forbidden(status)
        results["_done_status"] = status
        if body_json is not None:
            results["_done_error"] = body_json.get("error")
    return results


def _check_workspace(base, token):
    """CHECK 3 -- workspace resolution. GET /api/workspaces must carry the
    seeded "anthology" workspace (slug present, lowercase-equal), and GET
    /api/workspaces/{slug} must resolve it by SLUG (the cc route resolves id
    OR slug) -- the /workspace/anthology board is a live route, never a dead
    link."""
    results = {}
    status, body = _request("%s%s" % (base, WORKSPACES_PATH), token=token)
    if status is None:
        results[CHK_WORKSPACE_SLUG] = None
        results["_workspaces_status"] = None
        results[CHK_WORKSPACE_BY_SLUG] = None
        return results
    results["_workspaces_status"] = status
    results[CHK_WORKSPACE_SLUG] = _slug_present(body)

    if results[CHK_WORKSPACE_SLUG]:
        s2, _b2 = _request("%s%s/%s" % (base, WORKSPACES_PATH, ANTHOLOGY_SLUG),
                           token=token)
        results[CHK_WORKSPACE_BY_SLUG] = s2 == 200
        results["_workspace_by_slug_status"] = s2
    else:
        results[CHK_WORKSPACE_BY_SLUG] = False
        results["_workspace_by_slug_status"] = None
    return results


def _check_tile(base, token):
    """CHECK 4 -- home-screen tile. The home dashboard gates the Anthology
    producer card on TWO fetches (cc src/app/page.tsx + dashboard-workspaces.ts
    selectProducerCardSlugs): the workspace slug PRESENT and the engine DB
    PRESENT. GET /api/engine-db reports {anthology: bool}; the slug half is
    mirrored into the tile row by the caller (already proven by check 3)."""
    results = {}
    results[CHK_TILE_MIDDLEWARE] = token is not None
    status, body = _request("%s%s" % (base, ENGINE_DB_PATH), token=token)
    if status is None:
        results[CHK_TILE_ENGINE_DB] = None
        results["_engine_db_status"] = None
    else:
        results["_engine_db_status"] = status
        results[CHK_TILE_ENGINE_DB] = _engine_db_present(status, body)
    return results


# ---- the guard ---------------------------------------------------------------
def run_guard(url=None, token_label=None):
    """Run the four-seam proof. Returns (exit_code, report_dict). Never
    raises for a reachable/parseable Command Center; every unexpected
    exception is mapped to EX_ERR with the message in the report."""
    cfg = _load_config()
    label = token_label or _token_label(cfg)
    base = _base_url(cfg, url)

    _n, token = _env_first((label,))
    report = {
        "guard": "guard_cc_anthology_door",
        "cc_base_url": base,
        "token_label": label,
        "token_status": "SET" if token is not None else "NOT SET",
        "checks": {},
    }

    if token is None:
        # Fail closed: a box without the token cannot authenticate ANY
        # external board-door caller. The no-token probe still proves the box
        # refuses tokenless calls (reported), then we hold on the dependency.
        try:
            c1 = _check_auth(base, None)
        except Exception as exc:  # noqa: BLE001
            report["checks"] = {CHK_AUTH_NO_TOKEN: False,
                                "_error": "%s: %s" % (exc.__class__.__name__, exc)}
            report["ok"] = False
            return EX_ERR, report
        report["checks"].update(c1)
        report["ok"] = False
        if c1.get(CHK_AUTH_NO_TOKEN) is None:
            report["note"] = ("Command Center unreachable or timed out while "
                              "probing tokenless auth; held, re-run")
        else:
            report["note"] = ("credential label %r NOT SET (live process env): "
                              "the gate-route and workspace probes cannot "
                              "authenticate; the box fails closed" % label)
        return EX_DEP, report

    try:
        report["checks"].update(_check_auth(base, token))
        report["checks"].update(_check_done_403(base, token))
        report["checks"].update(_check_workspace(base, token))
        tile = _check_tile(base, token)
        tile[CHK_TILE_SLUG] = report["checks"].get(CHK_WORKSPACE_SLUG, False)
        report["checks"].update(tile)
    except Exception as exc:  # noqa: BLE001
        report["checks"]["_error"] = "%s: %s" % (exc.__class__.__name__, exc)
        report["ok"] = False
        return EX_ERR, report

    # Unreachable Command Center -> dependency class (re-runnable), never a
    # drift verdict.
    unreachable = any(
        report["checks"].get(k) is None
        for k in (CHK_AUTH_NO_TOKEN, CHK_DONE_403, CHK_WORKSPACE_SLUG,
                  CHK_TILE_ENGINE_DB))
    ok = _all_checks_passed(report["checks"])
    report["ok"] = ok
    if unreachable:
        report["note"] = "Command Center unreachable or timed out; held, re-run"
        return EX_DEP, report
    return (EX_OK if ok else EX_DRIFT), report


def _fmt_check(value):
    if value is True:
        return "PASS"
    if value is None:
        return "HELD"
    return "FAIL"


# ---- offline self-test: golden + attack fixtures over the REAL predicates ----
def self_test():
    """Offline wiring self-test (no network, no secrets). Golden fixtures
    (the shape a correct Command Center returns) must PASS; attack fixtures
    (the shapes a broken/misconfigured one returns) must FAIL. Every fixture
    runs through the SAME pure predicates the live run uses -- never a copy
    of the decision logic."""
    checks = []

    def record(label, cond):
        checks.append((label, bool(cond)))

    # -- exit-code contract --
    record("exit-code contract (0/1/2/3/4)",
           (EX_OK, EX_ERR, EX_BADINVOKE, EX_DEP, EX_DRIFT) == (0, 1, 2, 3, 4))

    # -- check 1: gate route auth classifier (golden + attack) --
    record("auth: 401/403/503 are rejections, 200/400 are not",
           all(_is_bearer_auth_rejection(s) for s in (401, 403, 503))
           and not _is_bearer_auth_rejection(200)
           and not _is_bearer_auth_rejection(400)
           and not _is_bearer_auth_rejection(202))
    record("auth: good-token passes on 400 (route validates query) and 200",
           _auth_good_passes(400) and _auth_good_passes(200))
    record("auth: good-token FAILS on 401/404/500 (attack)",
           not _auth_good_passes(401) and not _auth_good_passes(404)
           and not _auth_good_passes(500) and not _auth_good_passes(None))

    # -- check 2: done-action 403 invariant (golden + attack) --
    record("done: literal 403 is the invariant",
           _done_forbidden(403))
    record("done: 200/202/422/401/None are failures (attack)",
           not _done_forbidden(200) and not _done_forbidden(202)
           and not _done_forbidden(422) and not _done_forbidden(401)
           and not _done_forbidden(None))

    # -- check 3: workspace resolution (golden + attack fixtures) --
    golden_workspaces = [{"id": "a", "slug": "anthology", "name": "Anthology"},
                         {"id": "b", "slug": "podcast", "name": "Podcast"}]
    record("workspace: golden payload with the anthology slug passes",
           _slug_present(golden_workspaces))
    record("workspace: slug match is lowercase-exact (attack: 'Anthology' works",
           _slug_present([{"id": "a", "slug": "Anthology"}]))
    record("workspace: a different slug fails (attack: 'anthologies')",
           not _slug_present([{"id": "a", "slug": "anthologies"}]))
    record("workspace: missing slug field fails (attack)",
           not _slug_present([{"id": "a", "name": "Anthology"}]))
    record("workspace: empty list fails (attack)",
           not _slug_present([]))
    record("workspace: non-list payload fails closed, never throws",
           not _slug_present({"error": "boom"})
           and not _slug_present(None))

    # -- check 4: home-screen tile engine-db (golden + attack fixtures) --
    record("tile: golden engine-db {anthology: true} passes",
           _engine_db_present(200, {"anthology": True, "podcast": True}))
    record("tile: {anthology: false} fails (attack)",
           not _engine_db_present(200, {"anthology": False}))
    record("tile: engine absent from the map fails (attack)",
           not _engine_db_present(200, {"podcast": True}))
    record("tile: non-200 fails (attack)",
           not _engine_db_present(503, {"anthology": True})
           and not _engine_db_present(None, {"anthology": True}))
    record("tile: truthy string is NOT boolean true (attack)",
           not _engine_db_present(200, {"anthology": "present"}))

    # -- fail-closed aggregation --
    record("aggregate: None is never a pass (fail closed)",
           not _all_checks_passed({CHK_DONE_403: True,
                                   CHK_WORKSPACE_SLUG: None}))
    record("aggregate: False is never a pass (fail closed)",
           not _all_checks_passed({CHK_DONE_403: False,
                                   CHK_WORKSPACE_SLUG: True}))
    record("aggregate: underscore metadata keys never fail the run",
           _all_checks_passed({CHK_DONE_403: True,
                               "_done_status": 403,
                               "_done_error": "Forbidden"}))
    record("aggregate: all-true passes",
           _all_checks_passed({CHK_DONE_403: True, CHK_WORKSPACE_SLUG: True}))

    # -- label / URL resolution --
    record("token label resolves to the CC env name",
           _token_label({}) == DEFAULT_API_TOKEN_LABEL)
    record("board label override wins",
           _token_label({"board": {"api_token_label": "CC_TOKEN_LABEL"}})
           == "CC_TOKEN_LABEL")
    record("base url honors explicit --url over env/localhost",
           _base_url({}, "http://cc.example") == "http://cc.example")
    record("base url falls back to the localhost default",
           _base_url({}) == DEFAULT_BASE_URL)

    ok = all(c for _, c in checks)
    print("guard_cc_anthology_door self-test: %s (%d checks)"
          % ("OK" if ok else "FAIL", len(checks)))
    return EX_OK if ok else EX_DRIFT


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="guard_cc_anthology_door.py",
        description="Command Center anthology-integration prover (NEW-7): gate "
                    "route auth, done-action 403, workspace resolution, and the "
                    "home-screen tile, over the live Command Center. Runs in CI "
                    "and as a canary; fails closed.")
    ap.add_argument("--url", help="Command Center base URL (default: resolved "
                                  "env, then http://localhost:4000)")
    ap.add_argument("--token-label", dest="token_label",
                    help="env label holding the CC API token (default: resolved "
                         "board.api_token_label, then MC_API_TOKEN)")
    ap.add_argument("--json", action="store_true",
                    help="emit the machine-readable report to stdout")
    ap.add_argument("--self-test", action="store_true",
                    help="run the offline wiring checks and exit")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    rc, report = run_guard(url=args.url, token_label=args.token_label)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        c = report.get("checks", {})
        print("[guard_cc_anthology_door] CC %s | token label %r %s"
              % (report.get("cc_base_url"), report.get("token_label"),
                 report.get("token_status")))
        for name in (CHK_AUTH_NO_TOKEN, CHK_AUTH_WRONG_TOKEN, CHK_AUTH_GOOD_TOKEN,
                     CHK_DONE_403, CHK_WORKSPACE_SLUG, CHK_WORKSPACE_BY_SLUG,
                     CHK_TILE_MIDDLEWARE, CHK_TILE_SLUG, CHK_TILE_ENGINE_DB):
            if name in c:
                print("  %-30s %s" % (name, _fmt_check(c[name])))
        if report.get("_done_error"):
            print("  done-403 body: %r" % report["_done_error"])
        if report.get("note"):
            print("[guard_cc_anthology_door] %s" % report["note"])
        print("[guard_cc_anthology_door] %s"
              % ("PASS" if report.get("ok") else "FAIL"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
