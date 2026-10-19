#!/usr/bin/env python3
"""ghl_object_router.py — the mixed-use RAIL ROUTER for Skill 06 (U7 / §3).

WHY THIS EXISTS
---------------
Rail selection was per-agent judgment: which token context, which tier, browser
vs API, and what to do on a 401/403/429/selector-miss. That judgment is where
builds went wrong (wrong token context → false 403; browser used where an API
exists; tier-hopping on a 429 that shares one rate bucket). This module turns
the SKILL-6-BROWSER-CONTROL-BULLETPROOF-SPEC §3 decision matrix into TESTED DATA
+ CODE so every builder and every future engine asks the router instead of
hand-picking a rail.

For every GHL object type the router encodes:
  • an ORDERED rail list (API/MCP first where a create API exists, browser-only
    where none), each rail stamped with its TOKEN CONTEXT and TIER,
  • the idempotency key (GET/search-first probe field),
  • the read-back verifier contract,
  • the ordered fallback + failure-classification policy,
and it EMITS the mandatory ``[GHL tier used: N — tool]`` disclosure (Skill 36
Rule 7) and writes the F6 per-object RECEIPT on every operation.

DEPENDENCY-INJECTED, OFFLINE-TESTABLE
-------------------------------------
The router NEVER performs GHL I/O itself. Callers pass RUNNERS (callables) per
rail plus an idempotency probe and a verifier; the router owns the DECISION:
probe → attempt rail → classify failure → follow policy → next rail → read-back
verify → receipt → honest FAIL. This keeps rail choice as tested code while the
real transport (caf / MCP / raw HTTPS / agent-browser / REST-in-browser) stays
in the existing modules. ``--selftest`` drives the full decision path with fake
runners: no network, no browser, no GHL writes.

DOCTRINE ENCODED (from the spec)
--------------------------------
- F8: never tier-hop on 429 (one location = one shared rate bucket). A 429 is a
  cooldown-and-retry on the SAME rail, never a fallback.
- F9: token routing is part of the rail decision. 403 is classified as a
  token-CONTEXT mismatch FIRST (LOCATION PIT vs Firebase token-id vs OAuth
  Company vs Agency PIT), never blindly as an authorization failure.
- F4: builder-origin routes are in-browser-eval-only; services.* sends a real
  browser UA and a 403 there is retried once with UA before classification.
- F6: "no receipt = not created." The run summary is a pure reduction of receipts.
- Cheapest reliable rail first; browser is the LAST resort except where it is the
  ONLY rail (forms, surveys, funnels/pages, communities, courses, channels).

USAGE
-----
    import ghl_object_router as router
    r = router.route("custom_field")          # ObjectRoute (ordered rails)
    print(router.tier_disclosure(r.rails[0])) # [GHL tier used: 0 — caf ...]

    result = router.execute_write(
        "tag", "zhc_podcast_lead",
        evidence_root="/tmp/run01",
        idempotency_probe=probe_fn,           # -> existing dict | None
        rail_runners={"skill44_caf": run_caf, "rest_services": run_rest},
        verifier=verify_fn,                    # -> {"ok": bool, "proof": ...}
        request_shape={"tag": "zhc_podcast_lead"},
    )

    # CLI
    python3 ghl_object_router.py --matrix         # print the full matrix (JSON)
    python3 ghl_object_router.py --route survey    # one object's rail plan
    python3 ghl_object_router.py --selftest
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

# F6 receipts store + reducer live in their own module (ghl_receipts.py) so any
# builder — not just the router — can depend on receipts without pulling in
# rail-matrix/browser machinery. Re-exported here for backward compatibility
# with existing callers of ``ghl_object_router.make_receipt`` etc.
import ghl_receipts as receipts  # noqa: E402
from ghl_receipts import (  # noqa: E402,F401
    make_receipt,
    receipt_path,
    write_receipt,
    list_receipts,
    reduce_receipts,
    assert_consistent,
    ReceiptContradiction,
)

ROUTER_VERSION = "v1.0.0"


# ---------------------------------------------------------------------------
# Tiers (Skill 36) — the disclosure number N in [GHL tier used: N — tool]
# ---------------------------------------------------------------------------
class Tier:
    CAF = 0          # Skill 44 caf CLI / Skill 44 internal Build API (Firebase)
    MCP_OFFICIAL = 1  # orchestrator-only official MCP
    # 2 was the community MCP rail ($GHL_COMMUNITY_MCP_URL, port 8765). Removed
    # by GU-009/GU-010: the service is retired and is never a route. The number
    # stays unassigned so a historical receipt's "tier used: 2" can only ever
    # mean that retired rail, and REST/BROWSER keep the values other code and
    # stored receipts already carry.
    REST = 3          # raw HTTPS services.* (dual Accept + Version, browser UA)
    BROWSER = 4       # agent-browser / Playwright / REST-in-browser eval


# ---------------------------------------------------------------------------
# Token contexts (F9) — never substitute across contexts
# ---------------------------------------------------------------------------
class Token:
    LOCATION_PIT = "location_pit"      # location-scoped REST writes
    FIREBASE_TOKEN_ID = "firebase_token_id"  # internal SPA surfaces (in-browser)
    OAUTH_COMPANY = "oauth_company"    # company writes (sub-account create / SaaS)
    AGENCY_PIT = "agency_pit"          # snapshots (scope-verified pre-build)
    NONE = "none"                      # operator-manual / signed-URL


# ---------------------------------------------------------------------------
# Rail identifiers (the key callers register a runner under)
# ---------------------------------------------------------------------------
class Rail:
    SKILL44_CAF = "skill44_caf"
    SKILL44_BUILD = "skill44_build_api"     # Firebase-token internal workflow build
    MCP_OFFICIAL = "mcp_official"
    # "mcp_community" removed with Tier 2 (GU-009/GU-010): the community MCP is a
    # retired transport, not a rail. Do not re-add it as a fallback.
    REST_SERVICES = "rest_services"          # raw HTTPS services.leadconnectorhq.com
    REST_IN_BROWSER = "rest_in_browser"      # builder-origin autosave via seeded eval
    BROWSER = "browser"                      # agent-browser click-path (builders)
    VERCEL_EMBED = "vercel_embed"
    OPERATOR_MANUAL = "operator_manual"


# ---------------------------------------------------------------------------
# Failure classification → action (the ordered-fallback policy, §3)
# ---------------------------------------------------------------------------
class Action:
    RATE_COOLDOWN_RETRY = "rate_cooldown_retry"    # 429: cooldown, retry SAME rail
    RETRY_SAME_RAIL = "retry_same_rail"            # 401: re-mint/re-resolve once
    TOKEN_CONTEXT_CHECK = "token_context_check"    # 403: wrong token context FIRST
    NEXT_RAIL = "next_rail"                         # 404 / tool-absent
    SNAPSHOT_RETRY_THEN_STOP = "snapshot_retry_then_stop"  # selector miss
    BACKOFF_RETRY = "backoff_retry"                # 5xx / network (bounded)
    STOP_REPORT = "stop_report"                    # everything else


# Board failure-taxonomy prefixes (U9 item 3 — machine-parsable card notes)
BOARD_NOTE = {
    Action.RATE_COOLDOWN_RETRY: "RATE-LIMIT",
    Action.RETRY_SAME_RAIL: "AUTH-STOP",
    Action.TOKEN_CONTEXT_CHECK: "TOKEN-CONTEXT",
    Action.SNAPSHOT_RETRY_THEN_STOP: "SELECTOR-MISS",
    Action.STOP_REPORT: "VERIFY-FAIL",
}


@dataclass
class RailStep:
    rail: str
    tier: int
    token: str
    tool: str                 # human/disclosure name of the concrete tool
    can_create: bool = True    # False = read/attach/verify only on this rail
    note: str = ""


@dataclass
class ObjectRoute:
    object_type: str
    rails: List[RailStep]
    idempotency_key: str       # the field a GET/search-first probe matches on
    create_api_exists: bool    # False → browser is the ONLY create rail
    verify: str                # read-back verification contract (plain English)
    note: str = ""
    # S06-07: declared READ rails for this object type, kept BESIDE the
    # write rails: execute_write never attempts them, and every read step
    # carries can_create=False. Empty when no read surface is registered.
    read_rails: List[RailStep] = field(default_factory=list)

    def rail_names(self) -> List[str]:
        return [s.rail for s in self.rails]


def _public_inventory_read_step() -> RailStep:
    """The S06-07 public inventory READ step (doc 19 W3): one read-only
    services.* step naming both public reads. can_create=False: this step
    can never create anything. It gives the inventory read a declared
    router surface with a tier disclosure, beside (never inside) the
    write rails."""
    return RailStep(
        Rail.REST_SERVICES, Tier.REST, Token.LOCATION_PIT,
        "GET /funnels/funnel/list + GET /funnels/page "
        "(public API read, tools/ghl_funnels_read.py)",
        False,
        "S06-07: implemented at build tier, declared-not-live-proven "
        "(LIVE_PROOF_PENDING); reads only",
    )


# ---------------------------------------------------------------------------
# THE MATRIX — SKILL-6-BROWSER-CONTROL-BULLETPROOF-SPEC §3, encoded as data
# ---------------------------------------------------------------------------
def _matrix() -> Dict[str, ObjectRoute]:
    R = RailStep
    m: Dict[str, ObjectRoute] = {}

    m["custom_field"] = ObjectRoute(
        "custom_field",
        [
            R(Rail.SKILL44_CAF, Tier.CAF, Token.LOCATION_PIT,
              "caf locations custom-fields / create-custom-field", True,
              "GET-first; reuse matching key (zhc_ or verbatim per F2 contract)"),
            R(Rail.REST_SERVICES, Tier.REST, Token.LOCATION_PIT,
              "raw HTTPS services.* /custom-fields (browser UA)", True),
            R(Rail.BROWSER, Tier.BROWSER, Token.FIREBASE_TOKEN_ID,
              "app-shell Custom Fields modal", True,
              "operator-approved no-PIT fallback ONLY"),
        ],
        idempotency_key="field_key",
        create_api_exists=True,
        verify="GET fields; assert key byte-for-byte (incl. underscores)",
    )

    m["custom_value"] = ObjectRoute(
        "custom_value",
        [
            R(Rail.SKILL44_CAF, Tier.CAF, Token.LOCATION_PIT,
              "caf locations custom-values", True,
              "create endpoint shape confirmed by builder on first live run"),
            R(Rail.REST_SERVICES, Tier.REST, Token.LOCATION_PIT,
              "raw HTTPS services.* /custom-values", True),
            R(Rail.BROWSER, Tier.BROWSER, Token.FIREBASE_TOKEN_ID,
              "Settings → Custom Values UI", True),
        ],
        idempotency_key="value_name",
        create_api_exists=True,
        verify="GET by name; content matches",
    )

    m["tag"] = ObjectRoute(
        "tag",
        [
            R(Rail.SKILL44_CAF, Tier.CAF, Token.LOCATION_PIT, "caf tags", True,
              "GHL lowercases tags"),
            R(Rail.REST_SERVICES, Tier.REST, Token.LOCATION_PIT,
              "raw HTTPS services.* /tags", True),
        ],
        idempotency_key="tag",
        create_api_exists=True,
        verify="GET tags; contains string (lowercased)",
    )

    m["contact"] = ObjectRoute(
        "contact",
        [
            R(Rail.SKILL44_CAF, Tier.CAF, Token.LOCATION_PIT, "caf contacts", True),
            R(Rail.MCP_OFFICIAL, Tier.MCP_OFFICIAL, Token.LOCATION_PIT,
              "contacts_get-contacts (orchestrator ONLY)", True,
              "sub-agents have NO MCP injection — skip this rail in a sub-agent"),
            R(Rail.REST_SERVICES, Tier.REST, Token.LOCATION_PIT,
              "raw HTTPS /contacts/ (dual Accept + Version 2021-07-28)", True),
        ],
        idempotency_key="dedupe_email",
        create_api_exists=True,
        verify="re-GET record",
    )

    m["workflow"] = ObjectRoute(
        "workflow",
        [
            R(Rail.SKILL44_BUILD, Tier.CAF, Token.FIREBASE_TOKEN_ID,
              "caf workflows build (PLAN-MODE + WF-1..21 + rubric ≥8.5)", True,
              "internal Build API; public /workflows/ is GET-only"),
            R(Rail.BROWSER, Tier.BROWSER, Token.FIREBASE_TOKEN_ID,
              "agent-browser Build backstop", True,
              "ONLY when the Firebase token is genuinely absent + owner nudge"),
        ],
        idempotency_key="workflow_name",
        create_api_exists=False,  # internal-only; community MCP build tools UNVERIFIED
        verify="caf workflows export + re-read with ?includeTriggers=true",
        note="NEVER route a workflow BUILD through the community MCP (public API read-only)",
    )

    m["workflow_trigger"] = ObjectRoute(
        "workflow_trigger",
        [
            R(Rail.REST_IN_BROWSER, Tier.BROWSER, Token.FIREBASE_TOKEN_ID,
              "PUT /workflow/<loc>/trigger/<id> (token-id, in seeded eval)", True),
            R(Rail.SKILL44_BUILD, Tier.CAF, Token.FIREBASE_TOKEN_ID,
              "Skill 44 engine", True),
            R(Rail.BROWSER, Tier.BROWSER, Token.FIREBASE_TOKEN_ID,
              "builder UI", True),
        ],
        idempotency_key="trigger_id",
        create_api_exists=True,
        verify="re-read WITH ?includeTriggers=true (LOAD-BEARING query)",
    )

    m["form"] = ObjectRoute(
        "form",
        [
            R(Rail.BROWSER, Tier.BROWSER, Token.FIREBASE_TOKEN_ID,
              "ghl_form_builder.py (deps pre-created via Skill 44)", True),
        ],
        idempotency_key="zhc_name_search",
        create_api_exists=False,  # NO create API — browser is the ONLY create rail
        verify="qc-built-form.sh: render_check 200 + zhc_ marker in RENDERED DOM",
        note="creation browser-only; embed/read via caf forms list/submissions",
    )

    m["survey"] = ObjectRoute(
        "survey",
        [
            R(Rail.BROWSER, Tier.BROWSER, Token.FIREBASE_TOKEN_ID,
              "ghl_survey_builder.py (map-only fields per F1)", True),
        ],
        idempotency_key="zhc_name_search",
        create_api_exists=False,
        verify="public /widget/survey/<id> 200 + branch walk vs plan",
    )

    m["funnel"] = ObjectRoute(
        "funnel",
        [
            R(Rail.REST_IN_BROWSER, Tier.BROWSER, Token.FIREBASE_TOKEN_ID,
              "Family A REST autosave (seeded eval) for page content", True),
            R(Rail.BROWSER, Tier.BROWSER, Token.FIREBASE_TOKEN_ID,
              "Family C canvas-driving (CDP trusted events) for UI-only actions", True),
            R(Rail.VERCEL_EMBED, Tier.BROWSER, Token.NONE,
              "ghl_vercel.py embed for ADVANCED payloads", True,
              "assert_embeddable gate; child-frame load proof"),
        ],
        idempotency_key="funnel_workspace_url",
        create_api_exists=False,
        verify="sealed render_check (200 + marker + no render errors)",
        note="create_api_exists stays False: doc 19 W3 documents public "
        "READS only, no public write API. The public inventory read is "
        "registered under read_rails (S06-07).",
        read_rails=[_public_inventory_read_step()],
    )
    # website shares the funnel rail (Part-B deltas only)
    m["website"] = ObjectRoute(
        "website", list(m["funnel"].rails),
        idempotency_key="funnel_workspace_url",
        create_api_exists=False,
        verify=m["funnel"].verify,
        note="Websites tab is an <a> (not role=tab); two-card create modal. "
        "Public inventory READ registered under read_rails (S06-07); "
        "create_api_exists stays False (no public write API, doc 19 W3).",
        read_rails=[_public_inventory_read_step()],
    )
    m["page"] = ObjectRoute(
        "page", list(m["funnel"].rails),
        idempotency_key="page_id",
        create_api_exists=False,
        verify=m["funnel"].verify,
        note="create_api_exists stays False: doc 19 W3 documents public "
        "READS only, no public write API. The public inventory read is "
        "registered under read_rails (S06-07).",
        read_rails=[_public_inventory_read_step()],
    )

    m["media"] = ObjectRoute(
        "media",
        [
            R(Rail.REST_SERVICES, Tier.REST, Token.LOCATION_PIT,
              "POST /medias/upload-file + POST /medias/folder via ghl_media.py "
              "(LOCATION PIT)", True,
              "NEVER browser-routed; AGENCY PIT 401s for media. Sole route: the "
              "community MCP media fallback was removed (GU-009/GU-010)"),
        ],
        idempotency_key="folder_per_funnel_name",
        create_api_exists=True,
        verify="CDN URL fetch 200",
        note="Public REST covers upload (upload_media) and folder "
        "(create_media_folder). Media LIST has no implementation in ghl_media.py "
        "and no community route — named gap, UNSUPPORTED until a public list "
        "read is declared.",
    )

    m["product"] = ObjectRoute(
        "product",
        [
            R(Rail.REST_SERVICES, Tier.REST, Token.LOCATION_PIT,
              "raw HTTPS services.* /products", True,
              "sole route: the community MCP product rail was primary before "
              "GU-009/GU-010 and is removed; never a blind community-first "
              "attempt"),
        ],
        idempotency_key="product_sku",
        create_api_exists=True,
        verify="re-GET",
        note="Public REST only. Product collection / inventory / bulk-edit "
        "operations have no audited public operation row and are UNSUPPORTED — "
        "they are not routed to a retired transport.",
    )

    m["community"] = ObjectRoute(
        "community",
        [
            R(Rail.BROWSER, Tier.BROWSER, Token.FIREBASE_TOKEN_ID,
              "ghl_community_builder.py (Memberships area)", True),
        ],
        idempotency_key="zhc_name_search",
        create_api_exists=False,  # ASSUMED — no public create API; builder confirms first hour
        verify="list-page row + client-portal URL 200 (render_check)",
        note="GHL Communities/Memberships AUTHORING target (browser builder), "
        "NOT the retired community MCP service — it has no MCP rail and must "
        "never be read as one.",
    )

    m["course"] = ObjectRoute(
        "course",
        [
            R(Rail.BROWSER, Tier.BROWSER, Token.FIREBASE_TOKEN_ID,
              "ghl_course_builder.py (Memberships → Products/outline)", True),
        ],
        idempotency_key="zhc_name_search",
        create_api_exists=False,
        verify="Memberships list row + course preview render_check",
    )

    m["channel"] = ObjectRoute(
        "channel",
        [
            R(Rail.BROWSER, Tier.BROWSER, Token.FIREBASE_TOKEN_ID,
              "community builder channel extension", True),
        ],
        idempotency_key="channel_name_in_group",
        create_api_exists=False,
        verify="channel visible in the group nav snapshot",
    )

    m["subaccount"] = ObjectRoute(
        "subaccount",
        [
            R(Rail.REST_SERVICES, Tier.REST, Token.OAUTH_COMPANY,
              "POST /locations/ (OAuth Company token, locations.write)", True,
              "AGENCY PIT is empirically NOT honored for this write (F9)"),
            R(Rail.OPERATOR_MANUAL, Tier.BROWSER, Token.NONE,
              "operator creates in the agency UI", True),
        ],
        idempotency_key="company_unique_name",
        create_api_exists=True,
        verify="GET /locations/search",
    )

    m["snapshot"] = ObjectRoute(
        "snapshot",
        [
            R(Rail.REST_SERVICES, Tier.REST, Token.AGENCY_PIT,
              "Agency PIT + snapshots.write (scope-verified PRE-build)", True),
            R(Rail.OPERATOR_MANUAL, Tier.BROWSER, Token.NONE,
              "operator creates in the agency UI (no token needed)", True),
        ],
        idempotency_key="snapshot_name_version",
        create_api_exists=True,
        verify="snapshot object listing inspected",
    )

    return m


_MATRIX: Dict[str, ObjectRoute] = _matrix()
# Aliases so callers can use either spelling.
_ALIASES = {
    "customfield": "custom_field", "field": "custom_field",
    "customvalue": "custom_value", "value": "custom_value",
    "location": "subaccount", "sub_account": "subaccount", "sub-account": "subaccount",
    "trigger": "workflow_trigger", "wf": "workflow",
}


def object_types() -> List[str]:
    return sorted(_MATRIX.keys())


def route(object_type: str) -> ObjectRoute:
    """Return the ordered ObjectRoute for a GHL object type (raises on unknown)."""
    key = (object_type or "").strip().lower().replace(" ", "_")
    key = _ALIASES.get(key, key)
    if key not in _MATRIX:
        raise KeyError(
            f"unknown GHL object type {object_type!r}; known: {object_types()}"
        )
    return _MATRIX[key]


def read_route(object_type: str) -> List[RailStep]:
    """Return the declared READ rails for an object type (S06-07).

    Read rails live BESIDE the write rails on the ObjectRoute: they are
    never attempted by `execute_write` (a write orchestrator) and every
    read step carries can_create=False. An object type with no registered
    read surface returns an empty list."""
    return list(route(object_type).read_rails)


# ---------------------------------------------------------------------------
# Route-aware asymmetry (F4 — CF1010 fix: Cloudflare 1010 false-403)
# ---------------------------------------------------------------------------
def is_builder_origin_route(rail: str) -> bool:
    """Identify builder-origin routes (backend.leadconnectorhq.com).

    builder-origin routes MUST NEVER use bare HTTP transport — they are
    in-browser eval ONLY (REST_IN_BROWSER). Attempting to wire a bare
    REST runner for REST_IN_BROWSER is a configuration error.

    F4 doctrine: "builder-origin routes are in-browser-eval-only
    (never wire autosave into a bare transport)."
    """
    return rail == Rail.REST_IN_BROWSER


def is_services_route(rail: str) -> bool:
    """Identify services.* routes (services.leadconnectorhq.com).

    services.* routes MUST always send a real browser User-Agent.
    A 403 on services.* should be retried once with the UA set before
    being classified as an authorization failure.

    F4 doctrine: "services.* calls always send a real browser UA;
    any 403 on services.* is first re-tried once with the UA set
    before being classified as an authorization failure."
    """
    return rail == Rail.REST_SERVICES


def rail_requires_browser_context(rail: str) -> bool:
    """Check if this rail REQUIRES a browser/seeded eval context.

    If True, a bare HTTPS runner is not valid for this rail.
    This is the structural enforcement of F4.
    """
    return rail in (Rail.REST_IN_BROWSER, Rail.BROWSER, Rail.SKILL44_BUILD)


# ---------------------------------------------------------------------------
# Tier disclosure (Skill 36 Rule 7) — mandatory on every operation
# ---------------------------------------------------------------------------
def tier_disclosure(step: RailStep, context_note: str = "") -> str:
    """``[GHL tier used: N — tool]`` (+ optional parenthetical context)."""
    ctx = f" ({context_note})" if context_note else ""
    return f"[GHL tier used: {step.tier}{ctx} — {step.tool}]"


# ---------------------------------------------------------------------------
# Failure classification (§3 auto-retry/fallback policy)
# ---------------------------------------------------------------------------
def classify_failure(error_kind: Optional[str] = None,
                     status: Optional[int] = None) -> str:
    """Map an HTTP status / error kind to the ordered-fallback ACTION.

    ``error_kind`` (preferred) is one of: ``rate_limit``, ``auth``,
    ``token_context``, ``not_found``, ``tool_absent``, ``selector_miss``,
    ``server_error``, ``network``. ``status`` is used when only an HTTP code is
    known. Doctrine: 429 never tier-hops (F8); 403 is a token-context check FIRST
    (F9); a tool-absent/404 falls to the next rail.
    """
    if error_kind:
        k = error_kind.lower()
        table = {
            "rate_limit": Action.RATE_COOLDOWN_RETRY,
            "429": Action.RATE_COOLDOWN_RETRY,
            "auth": Action.RETRY_SAME_RAIL,
            "401": Action.RETRY_SAME_RAIL,
            "token_context": Action.TOKEN_CONTEXT_CHECK,
            "403": Action.TOKEN_CONTEXT_CHECK,
            "not_found": Action.NEXT_RAIL,
            "404": Action.NEXT_RAIL,
            "tool_absent": Action.NEXT_RAIL,
            "selector_miss": Action.SNAPSHOT_RETRY_THEN_STOP,
            "server_error": Action.BACKOFF_RETRY,
            "network": Action.BACKOFF_RETRY,
        }
        if k in table:
            return table[k]
    if status is not None:
        if status == 429:
            return Action.RATE_COOLDOWN_RETRY
        if status == 401:
            return Action.RETRY_SAME_RAIL
        if status == 403:
            return Action.TOKEN_CONTEXT_CHECK
        if status == 404:
            return Action.NEXT_RAIL
        if 500 <= status <= 599:
            return Action.BACKOFF_RETRY
    return Action.STOP_REPORT


# ---------------------------------------------------------------------------
# F6 receipts — "no receipt = not created"
#
# make_receipt / receipt_path / write_receipt / list_receipts / reduce_receipts
# / assert_consistent / ReceiptContradiction now live in ghl_receipts.py and are
# imported + re-exported above. This router calls them exactly as any other
# builder would — it has no privileged access to the receipts store.
# ---------------------------------------------------------------------------
# The orchestrator — probe → attempt rail → classify → fallback → verify → receipt
# ---------------------------------------------------------------------------
@dataclass
class RunResult:
    """What a rail RUNNER returns. ``ok`` gates success; on failure set
    ``error_kind`` (or ``status``) so the router can classify + fall back."""
    ok: bool
    response_id: Optional[str] = None
    status: Optional[int] = None
    error_kind: Optional[str] = None
    detail: str = ""
    # S06-08 (additive): the location the runner's own read observed, when it
    # knows it, one of the router's observed-location sources for tenant
    # binding (see execute_write).
    location_id: Optional[str] = None


def _as_run_result(x: Any) -> RunResult:
    if isinstance(x, RunResult):
        return x
    if isinstance(x, dict):
        return RunResult(
            ok=bool(x.get("ok")),
            response_id=x.get("response_id") or x.get("id"),
            status=x.get("status"),
            error_kind=x.get("error_kind"),
            detail=x.get("detail", ""),
            location_id=x.get("location_id") or x.get("observed_location_id"),
        )
    return RunResult(ok=bool(x))


_OBS_UNSET = object()  # _finish sentinel: "derive the observed location"


def execute_write(
    object_type: str,
    slug: str,
    *,
    evidence_root: str,
    idempotency_probe: Optional[Callable[[], Optional[dict]]] = None,
    rail_runners: Optional[Dict[str, Callable[[RailStep], Any]]] = None,
    verifier: Optional[Callable[[Optional[str]], dict]] = None,
    request_shape: Any = None,
    rate_cooldown: Optional[Callable[[RailStep], None]] = None,
    logger: Optional[Callable[[str], None]] = None,
    max_backoff: int = 3,
    expected_location_id: Optional[str] = None,
    observed_location_id: Optional[str] = None,
    run_id: Optional[str] = None,
    secret_values: Any = None,
) -> dict:
    """Drive one idempotent, read-back-verified, receipted GHL write per §3.

    Returns a result dict: ``{ok, action, rail, tier, receipt, receipt_path,
    disclosures, board_note?, error?}``. NEVER raises for an expected GHL failure
    — it returns an honest FAIL with the receipt trail (card → blocked upstream).

    S06-08 TENANT BINDING: ``expected_location_id`` is the run's GATED tenant
    context (established by the caller, e.g. ghl_builder.subaccount_matches'
    MatchGuard target). The observed location comes from, in order: the
    explicit ``observed_location_id``, the verifier's read-back dict
    (``location_id`` / ``observed_location_id``), the idempotency probe's
    dict, or the runner result's ``location_id``. Every receipt is stamped
    with the contract fields; when expected and observed are both known and
    DIFFER, the write is receipted as FAILED with a tenant-mismatch error:
    a cross-tenant read-back is a contradiction, never a create.
    """
    obj = route(object_type)
    log = logger or (lambda m: None)
    disclosures: List[str] = []
    rail_runners = rail_runners or {}

    def _observed(verify: Any = None, probe: Any = None,
                  result: Any = None) -> Optional[str]:
        if observed_location_id:
            return observed_location_id
        for source in (verify, probe):
            if isinstance(source, dict):
                value = source.get("observed_location_id") or source.get("location_id")
                if isinstance(value, str) and value.strip():
                    return value.strip()
        value = getattr(result, "location_id", None)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _finish(action: str, rail: Optional[RailStep], response_id, verify,
                error=None, board_note=None, observed=_OBS_UNSET) -> dict:
        obs = _observed(verify) if observed is _OBS_UNSET else observed
        receipt = make_receipt(
            object_type, slug, action, rail=rail, response_id=response_id,
            request_shape=request_shape, verify=verify, disclosures=disclosures,
            error=error, expected_location_id=expected_location_id,
            observed_location_id=obs, run_id=run_id,
        )
        rp = write_receipt(evidence_root, receipt, secret_values=secret_values)
        return {
            "ok": action in ("created", "reused"),
            "action": action, "rail": rail.rail if rail else None,
            "tier": rail.tier if rail else None,
            "disclosures": disclosures, "receipt": receipt, "receipt_path": rp,
            "board_note": board_note, "error": error,
            "tenant_binding": receipt.get("tenant_binding"),
        }

    # 1. Idempotency probe (GET/search-first) — reuse an existing object.
    if idempotency_probe is not None:
        try:
            existing = idempotency_probe()
        except Exception as exc:  # noqa: BLE001
            existing = None
            log(f"idempotency probe raised (treated as not-found): {exc}")
        if existing:
            step = obj.rails[0]
            d = tier_disclosure(step, "idempotency reuse")
            disclosures.append(d)
            log(d)
            rid = existing.get("id") if isinstance(existing, dict) else None
            verify = existing.get("verify") if isinstance(existing, dict) else None
            obs = _observed(verify, existing)
            if (expected_location_id and obs
                    and obs != expected_location_id):
                last_error = (
                    f"tenant mismatch on reuse probe: existing object observed "
                    f"in location {obs!r} but the run is gated for "
                    f"{expected_location_id!r}: cross-tenant reuse refused"
                )
                log(last_error)
                return _finish("failed", step, rid, verify or {"probe": "existing"},
                               error=last_error,
                               board_note=BOARD_NOTE[Action.STOP_REPORT],
                               observed=obs)
            return _finish("reused", step, rid, verify or {"probe": "existing"},
                           observed=obs)

    # 2. Ordered rails — attempt each with its failure policy.
    last_error = "no rail runner provided"
    for step in obj.rails:
        runner = rail_runners.get(step.rail)
        if runner is None:
            log(f"no runner for rail {step.rail!r} — skipping to next rail")
            continue

        attempts = 0
        backoffs = 0
        while True:
            attempts += 1
            d = tier_disclosure(step)
            try:
                res = _as_run_result(runner(step))
            except Exception as exc:  # noqa: BLE001
                res = RunResult(ok=False, error_kind="network", detail=str(exc))
            if res.ok:
                disclosures.append(d)
                log(d)
                # Read-back verify (un-fakeable). No verify pass = not created.
                verify: dict = {"skipped": True}
                if verifier is not None:
                    try:
                        verify = verifier(res.response_id) or {}
                    except Exception as exc:  # noqa: BLE001
                        verify = {"ok": False, "error": str(exc)}
                    if not verify.get("ok", False):
                        last_error = f"read-back verify failed on {step.rail}: {verify}"
                        log(last_error)
                        return _finish("failed", step, res.response_id, verify,
                                       error=last_error,
                                       board_note=BOARD_NOTE[Action.STOP_REPORT])
                # S06-08 tenant gate: a read-back that observed a DIFFERENT
                # location than the gated tenant turns the create into a
                # failed, tenant-mismatch receipt (mirrors the failed-verify
                # path above), never a created receipt for the wrong tenant.
                obs = _observed(verify, result=res)
                if (expected_location_id and obs
                        and obs != expected_location_id):
                    last_error = (
                        f"tenant mismatch on {step.rail}: read-back observed "
                        f"location {obs!r} but the run is gated for "
                        f"{expected_location_id!r}: cross-tenant read-back "
                        "is a contradiction, never a create"
                    )
                    log(last_error)
                    return _finish("failed", step, res.response_id, verify,
                                   error=last_error,
                                   board_note=BOARD_NOTE[Action.STOP_REPORT],
                                   observed=obs)
                return _finish("created", step, res.response_id, verify,
                               observed=obs)

            # Failure → classify → policy.
            action = classify_failure(res.error_kind, res.status)
            last_error = (f"{step.rail} failed "
                          f"(kind={res.error_kind}, status={res.status}): "
                          f"{res.detail} → {action}")
            log(last_error + f"  {d}")

            if action == Action.RATE_COOLDOWN_RETRY:
                # F8: never tier-hop on 429. Cool down, retry SAME rail (bounded).
                if attempts <= 2:
                    if rate_cooldown:
                        rate_cooldown(step)
                    continue
                # exhausted cooldown retries → honest stop (do NOT fall to next rail)
                return _finish("failed", step, None, {"ok": False},
                               error=last_error,
                               board_note=BOARD_NOTE[Action.RATE_COOLDOWN_RETRY])

            if action == Action.RETRY_SAME_RAIL:
                if attempts <= 2:      # 401: re-mint / re-resolve once
                    continue
                break                  # then fall to next rail

            if action == Action.BACKOFF_RETRY:
                backoffs += 1
                if backoffs <= max_backoff:
                    continue
                break                  # exhausted → next rail

            if action == Action.SNAPSHOT_RETRY_THEN_STOP:
                if attempts <= 2:      # one snapshot retry
                    continue
                return _finish("failed", step, None, {"ok": False},
                               error=last_error,
                               board_note=BOARD_NOTE[Action.SNAPSHOT_RETRY_THEN_STOP])

            if action == Action.TOKEN_CONTEXT_CHECK:
                # F4 + F9: services.* 403 should be retried once with User-Agent
                # before being classified as a token-context mismatch (CF1010 fix).
                # This handles the Cloudflare 1010 false-403 for bare clients.
                if is_services_route(step.rail) and attempts <= 2:
                    log(f"services.* 403 on attempt {attempts} — retrying with User-Agent (F4)")
                    continue
                # F9: a 403 is a token-context mismatch FIRST. If the NEXT rail
                # uses a different token context, try it; else STOP (don't guess).
                idx = obj.rails.index(step)
                nxt = obj.rails[idx + 1] if idx + 1 < len(obj.rails) else None
                if nxt is None or nxt.token == step.token:
                    return _finish("failed", step, None, {"ok": False},
                                   error=last_error + " (no alternate token context)",
                                   board_note=BOARD_NOTE[Action.TOKEN_CONTEXT_CHECK])
                break                  # fall to the differently-scoped rail

            if action == Action.NEXT_RAIL:
                break

            # STOP_REPORT and anything else
            return _finish("failed", step, None, {"ok": False},
                           error=last_error,
                           board_note=BOARD_NOTE[Action.STOP_REPORT])

    # 3. All rails exhausted → honest FAIL with the receipt trail.
    return _finish("failed", None, None, {"ok": False}, error=last_error,
                   board_note=BOARD_NOTE[Action.STOP_REPORT])


# ---------------------------------------------------------------------------
# Serialization (for --matrix and engines that want the table as JSON)
# ---------------------------------------------------------------------------
def matrix_as_dict() -> dict:
    out: dict = {"router_version": ROUTER_VERSION, "objects": {}}
    for name, r in _MATRIX.items():
        out["objects"][name] = {
            "idempotency_key": r.idempotency_key,
            "create_api_exists": r.create_api_exists,
            "verify": r.verify,
            "note": r.note,
            "rails": [asdict(s) for s in r.rails],
            "read_rails": [asdict(s) for s in r.read_rails],
        }
    return out


# ---------------------------------------------------------------------------
# Self-test — no network, no browser, no GHL writes
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile
    errors: List[str] = []

    # 1. Every object type routes; browser-only objects have create_api_exists=False.
    for t in ("custom_field", "custom_value", "tag", "form", "survey", "funnel",
              "community", "course", "channel", "workflow", "media", "snapshot",
              "subaccount", "product", "contact", "workflow_trigger", "page",
              "website"):
        r = route(t)
        if not r.rails:
            errors.append(f"{t}: no rails")
    for browser_only in ("form", "survey", "community", "course", "channel"):
        if route(browser_only).create_api_exists:
            errors.append(f"{browser_only}: should have NO create API")
        if route(browser_only).rails[0].rail != Rail.BROWSER:
            errors.append(f"{browser_only}: primary rail must be browser")

    # 2. API-first objects lead with a non-browser rail.
    for api_first in ("custom_field", "custom_value", "tag", "media"):
        first = route(api_first).rails[0]
        if first.tier == Tier.BROWSER:
            errors.append(f"{api_first}: primary rail must NOT be browser")

    # 3. Aliases + unknowns.
    if route("field").object_type != "custom_field":
        errors.append("alias 'field' -> custom_field broken")
    try:
        route("nonsense_object")
        errors.append("unknown object type should raise")
    except KeyError:
        pass

    # 4. Token routing (F9): subaccount create uses OAuth Company (never Agency PIT).
    if route("subaccount").rails[0].token != Token.OAUTH_COMPANY:
        errors.append("subaccount create must use OAuth Company token")
    if route("snapshot").rails[0].token != Token.AGENCY_PIT:
        errors.append("snapshot must use Agency PIT")
    if route("media").rails[0].token != Token.LOCATION_PIT:
        errors.append("media must use LOCATION PIT (agency PIT 401s)")

    # 5. Disclosure format.
    d = tier_disclosure(route("custom_field").rails[0])
    if not d.startswith("[GHL tier used: 0 — ") or not d.endswith("]"):
        errors.append(f"disclosure format wrong: {d!r}")

    # 6. Failure classification doctrine.
    cases = {
        ("rate_limit", None): Action.RATE_COOLDOWN_RETRY,
        (None, 429): Action.RATE_COOLDOWN_RETRY,
        ("token_context", None): Action.TOKEN_CONTEXT_CHECK,
        (None, 403): Action.TOKEN_CONTEXT_CHECK,
        (None, 401): Action.RETRY_SAME_RAIL,
        ("tool_absent", None): Action.NEXT_RAIL,
        (None, 404): Action.NEXT_RAIL,
        ("selector_miss", None): Action.SNAPSHOT_RETRY_THEN_STOP,
        (None, 503): Action.BACKOFF_RETRY,
        ("mystery", None): Action.STOP_REPORT,
    }
    for (kind, status), want in cases.items():
        got = classify_failure(kind, status)
        if got != want:
            errors.append(f"classify_failure({kind},{status})={got} want {want}")

    with tempfile.TemporaryDirectory() as tmp:
        # 7. Idempotency reuse → receipt action=reused, no runner called.
        called = {"n": 0}

        def _runner_should_not_run(step):
            called["n"] += 1
            return RunResult(ok=True, response_id="X")

        res = execute_write(
            "tag", "zhc_dupe", evidence_root=tmp,
            idempotency_probe=lambda: {"id": "existing123"},
            rail_runners={Rail.SKILL44_CAF: _runner_should_not_run},
            verifier=lambda rid: {"ok": True},
            request_shape={"tag": "zhc_dupe"},
        )
        if res["action"] != "reused" or called["n"] != 0:
            errors.append("idempotency reuse should skip runners")
        if not os.path.exists(res["receipt_path"]):
            errors.append("reuse must write a receipt")

        # 8. Primary rail succeeds + verifies → created.
        res = execute_write(
            "custom_field", "zhc_fav", evidence_root=tmp,
            idempotency_probe=lambda: None,
            rail_runners={Rail.SKILL44_CAF: lambda s: RunResult(ok=True, response_id="cf1")},
            verifier=lambda rid: {"ok": True, "proof": "GET matched"},
        )
        if res["action"] != "created" or res["rail"] != Rail.SKILL44_CAF:
            errors.append("primary-rail success should be created on caf")
        if not any("[GHL tier used: 0" in x for x in res["disclosures"]):
            errors.append("created result must carry a tier-0 disclosure")

        # 9. 404 on primary → fall to next rail → created on REST.
        def _cf_primary_404(step):
            return RunResult(ok=False, status=404, detail="tool absent")

        res = execute_write(
            "custom_field", "zhc_next", evidence_root=tmp,
            idempotency_probe=lambda: None,
            rail_runners={
                Rail.SKILL44_CAF: _cf_primary_404,
                Rail.REST_SERVICES: lambda s: RunResult(ok=True, response_id="cf2"),
            },
            verifier=lambda rid: {"ok": True},
        )
        if res["action"] != "created" or res["rail"] != Rail.REST_SERVICES:
            errors.append("404 on primary should fall to REST rail")

        # 10. 429 must NOT tier-hop — stays on the same rail then honest-fails.
        hop = {"caf": 0, "rest": 0}

        def _caf_429(step):
            hop["caf"] += 1
            return RunResult(ok=False, status=429, detail="rate limited")

        def _rest_should_not_run(step):
            hop["rest"] += 1
            return RunResult(ok=True, response_id="nope")

        res = execute_write(
            "tag", "zhc_429", evidence_root=tmp,
            idempotency_probe=lambda: None,
            rail_runners={Rail.SKILL44_CAF: _caf_429,
                          Rail.REST_SERVICES: _rest_should_not_run},
            verifier=lambda rid: {"ok": True},
            rate_cooldown=lambda s: None,
        )
        if hop["rest"] != 0:
            errors.append("429 must NEVER tier-hop to the next rail (F8)")
        if res["action"] != "failed" or res["board_note"] != "RATE-LIMIT":
            errors.append("exhausted 429 should honest-fail with RATE-LIMIT note")

        # 11. 403 with same-token next rail → STOP (token-context, no guessing).
        # tag rails are caf + REST, both LOCATION_PIT, so a 403 on the primary
        # must STOP rather than hop to the same token context.
        res = execute_write(
            "tag", "zhc_403", evidence_root=tmp,
            idempotency_probe=lambda: None,
            rail_runners={
                Rail.SKILL44_CAF: lambda s: RunResult(ok=False, status=403),
                Rail.REST_SERVICES: lambda s: RunResult(ok=True, response_id="t1"),
            },
            verifier=lambda rid: {"ok": True},
        )
        if res["action"] != "failed" or res["board_note"] != "TOKEN-CONTEXT":
            errors.append("403 with same-token next rail should STOP as TOKEN-CONTEXT")

        # 12. read-back verify failure → created rail but action=failed.
        res = execute_write(
            "survey", "zhc_survey", evidence_root=tmp,
            idempotency_probe=lambda: None,
            rail_runners={Rail.BROWSER: lambda s: RunResult(ok=True, response_id="s1")},
            verifier=lambda rid: {"ok": False, "detail": "public URL 404"},
        )
        if res["action"] != "failed" or res["board_note"] != "VERIFY-FAIL":
            errors.append("verify failure must fail even when the write 'succeeded'")

        # 13. receipt reduction summary.
        summ = reduce_receipts(tmp)
        if summ["total"] < 5:
            errors.append(f"reduce_receipts saw too few receipts: {summ['total']}")

    # 14. matrix serializes.
    md = matrix_as_dict()
    if "custom_field" not in md["objects"]:
        errors.append("matrix_as_dict missing custom_field")
    # 15. Route-aware asymmetry (CF1010 fix).
    if not is_builder_origin_route(Rail.REST_IN_BROWSER):
        errors.append("is_builder_origin_route(REST_IN_BROWSER) should be True")
    if is_builder_origin_route(Rail.REST_SERVICES):
        errors.append("is_builder_origin_route(REST_SERVICES) should be False")
    if not is_services_route(Rail.REST_SERVICES):
        errors.append("is_services_route(REST_SERVICES) should be True")
    if is_services_route(Rail.REST_IN_BROWSER):
        errors.append("is_services_route(REST_IN_BROWSER) should be False")
    if not rail_requires_browser_context(Rail.REST_IN_BROWSER):
        errors.append("rail_requires_browser_context(REST_IN_BROWSER) should be True")
    if not rail_requires_browser_context(Rail.BROWSER):
        errors.append("rail_requires_browser_context(BROWSER) should be True")
    if rail_requires_browser_context(Rail.REST_SERVICES):
        errors.append("rail_requires_browser_context(REST_SERVICES) should be False")

    # 16. The community MCP is retired (GU-009/GU-010): no route may name it,
    # and the product/media object types must lead with the public REST rail.
    for name, r in _MATRIX.items():
        for s in list(r.rails) + list(r.read_rails):
            if s.rail == "mcp_community" or s.tier == 2:
                errors.append(f"{name}: retired community MCP rail is still routed")
    for rest_led in ("product", "media"):
        if route(rest_led).rails[0].rail != Rail.REST_SERVICES:
            errors.append(f"{rest_led}: primary rail must be the public REST route")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — router decision path verified (no network / no browser)")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="ghl_object_router",
        description="Skill-6 mixed-use rail router (§3 matrix as tested code).",
    )
    p.add_argument("--selftest", action="store_true",
                   help="Run the no-network decision-path self-test and exit.")
    p.add_argument("--matrix", action="store_true",
                   help="Print the full object→rail matrix as JSON.")
    p.add_argument("--route", metavar="OBJECT_TYPE",
                   help="Print the ordered rail plan for one object type.")
    p.add_argument("--list", action="store_true",
                   help="List known object types.")
    p.add_argument("--route-analysis", metavar="RAIL",
                   help="Analyze a rail for route-aware properties (F4 asymmetry).")
    args = p.parse_args(argv)

    if args.selftest:
        return _selftest()
    if args.list:
        print("\n".join(object_types()))
        return 0
    if args.matrix:
        print(json.dumps(matrix_as_dict(), indent=2))
        return 0
    if args.route:
        try:
            r = route(args.route)
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        out = {
            "object_type": r.object_type,
            "create_api_exists": r.create_api_exists,
            "idempotency_key": r.idempotency_key,
            "verify": r.verify,
            "note": r.note,
            "rails": [
                {**asdict(s), "disclosure": tier_disclosure(s)} for s in r.rails
            ],
        }
        print(json.dumps(out, indent=2))
        return 0
    if args.route_analysis:
        rail = args.route_analysis
        out = {
            "rail": rail,
            "is_builder_origin": is_builder_origin_route(rail),
            "is_services": is_services_route(rail),
            "requires_browser_context": rail_requires_browser_context(rail),
        }
        print(json.dumps(out, indent=2))
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
