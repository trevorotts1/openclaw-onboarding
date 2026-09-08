#!/usr/bin/env python3
# =============================================================================
# SKILL 57 — SOCIAL MEDIA IN A BOX :: PREFLIGHT GATE (fail-closed readiness)
# -----------------------------------------------------------------------------
# DETERMINISTIC, FAIL-CLOSED per run (Module 0). F19 REBUILD — readiness is a
# CAPABILITY/DEPENDENCY GRAPH resolved from the SELECTED OUTPUT PLAN, not an
# all-or-nothing wall:
#   * every plan needs        -> brandName/locationId/userId/timezone/status
#                                + platforms (or an explicit plan)          -> AF-SM-PREFLIGHT-CONFIG
#   * GHL delivery in plan    -> PIT valid (GET /locations/{locationId})    -> AF-SM-PREFLIGHT-TOKEN
#   * images requested        -> Kie key SET + credits for the planned
#                                asset estimate (not one global threshold)  -> AF-SM-PREFLIGHT-CREDITS
#   * text/agent roles        -> OpenRouter key SET + balance for the plan  -> AF-SM-PREFLIGHT-BALANCE
#   * audio/video/podcast     -> only those branches' credentials; a podcast
#                                fold that is off or unconfigured is a
#                                LABELED SKIP (never a failure, never a stub
#                                presented as delivered)                    -> AF-SM-PREFLIGHT-CAPABILITY
#   * openrouterModel/fallbacks live in the provider-policy contract
#     (run/contracts/provider_policy.json), not in the global hard floor.
# C2/F06 REBUILD — the connected-accounts reconcile is PER-ACCOUNT (contract
# discovered_account.json): live GHL account IDs (S1 documented contract via
# scripts/ghl_contracts.py) intersected with the client-enabled channels each
# become a plan entry {account_id, platform, account_name, capabilities,
# health: ready|skipped|needs_reconnect|retrying|failed, supported_formats,
# exclusion_reason}. ONE platform's absence NEVER blocks the run — healthy
# accounts proceed independently; a connected-but-unconfigured channel is a
# per-account WARNING on the report (visible, never silent, never a BLOCK);
# platformsExcluded entries are recorded as deliberate skips.
# FAIL (on a REQUIRED node) -> a labeled failure report + configured
# notification; the run is BLOCKED (sys.exit 2) and no downstream module runs.
#
# Two modes:
#   * offline (default): reads a "probes" object from the config (kieCredits,
#     openrouterBalance, ghlTokenValid, connectedAccounts) and evaluates the
#     plan deterministically. `connectedAccounts` absent -> nothing to
#     reconcile in a dry-run (required-for-plan probes stay fail-closed).
#   * --live: probes the real endpoints with the CLIENT's own keys. A probe a
#     REQUIRED node depends on that cannot be confirmed FAILS CLOSED — but one
#     account's discovery failure downgrades THAT account, not the run.
#     Secret values are used to authenticate but are NEVER printed.
#
# EXIT: 0 PASS / 2 AUTOFAIL / 3 USAGE-IO.
# USAGE:
#   python3 preflight_gate.py <config.json> [--live] [--json] [--report PATH]
#   python3 preflight_gate.py --self-test
# =============================================================================
"""Fail-closed preflight readiness gate for Social Media in a Box (Skill 57)."""

import argparse
import json
import os
import sys
from pathlib import Path

_EXIT_USAGE = 3
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ghl_contracts  # noqa: E402  (F09 — one shared documented-contract layer)

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

AF_CREDITS = "AF-SM-PREFLIGHT-CREDITS"
AF_BALANCE = "AF-SM-PREFLIGHT-BALANCE"
AF_TOKEN = "AF-SM-PREFLIGHT-TOKEN"
AF_CONFIG = "AF-SM-PREFLIGHT-CONFIG"
AF_STATUS = "AF-SM-PREFLIGHT-STATUS"
AF_DISCOVERY = "AF-SM-DISCOVERY-DRIFT"
AF_CRED_CONFLICT = "AF-SM-CRED-CONFLICT"
AF_CAPABILITY = "AF-SM-PREFLIGHT-CAPABILITY"

# Per-account health states (discovered_account.json contract enum).
HEALTH_READY = "ready"
HEALTH_SKIPPED = "skipped"
HEALTH_NEEDS_RECONNECT = "needs_reconnect"
HEALTH_RETRYING = "retrying"
HEALTH_FAILED = "failed"

KIE_MIN_CREDITS = 200          # per-image-plan estimate floor (kept as the default band)
OPENROUTER_MIN_BALANCE = 5.0   # per-text-plan estimate floor (kept as the default band)
PAID_STATUS = "Paid"

class _CredentialConflict(Exception):
    """Internal carrier for a resolver-reported config/env credential conflict.

    Raised by _get_secret so every live probe surfaces the SAME blocking
    AF-SM-CRED-CONFLICT failure. Never carries a credential value — the
    message names the conflicting SOURCES only."""

# F19: the MINIMAL floor any plan needs. Provider/model selection lives in the
# provider-policy contract; media/podcast credentials are gated per branch.
REQUIRED_FIELDS = ("brandName", "locationId", "userId", "timezone", "status")
OPTIONAL_PLAN_FIELDS = ("platforms", "postTypes", "plan")
REQUIRED_SECRETS_BASE = ()      # secrets are gated per capability branch below

# Fold-mode -> the credentials its branch needs (only when the toggle is ON).
_FOLD_REQUIREMENTS = {
    "podcast": ("fishAudioKey", "podbeanApi"),
}
# Media-capability branch -> the secret(s) + probe(s) it needs.
_MEDIA_REQUIREMENTS = {
    "images": (("kieKey",), "kieCredits"),
}
_TEXT_REQUIREMENTS = {
    "text": (("openrouterKey",), "openrouterBalance"),
}


def _nonempty(v):
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return v is not None


# ---------------------------------------------------------------------------
# F19 — capability/dependency graph. The SELECTED OUTPUT PLAN decides which
# nodes are REQUIRED; an unused provider can never block a run. `plan` is the
# resolved plan dict (or None when the config carries no plan object).
# ---------------------------------------------------------------------------
def resolve_output_plan(cfg):
    """Resolve the selected output plan from the config. Returns a dict:
      ghl_delivery   bool  (platforms/plan present -> posts through GHL)
      images         bool  (image-bearing post types or an explicit plan ask)
      video          bool
      podcast        bool  (config fold toggle ON)
      newsletter     bool  (config fold toggle ON)
      blog           bool  (config fold toggle ON)
      engage         bool  (config fold toggle ON)
    Deterministic, config-only (no network, no side effects)."""
    post_types = {str(p).strip().lower() for p in (cfg.get("postTypes") or []) if str(p).strip()}
    plan = cfg.get("plan") if isinstance(cfg.get("plan"), dict) else {}
    platforms = [p for p in (cfg.get("platforms") or []) if str(p).strip()]
    ghl_delivery = bool(platforms or plan.get("platforms") or cfg.get("ghlDelivery") is not False
                        and (platforms or plan.get("platforms")))
    image_types = {"carousel", "story", "reel", "pin"}  # image-bearing GHL post types
    images = bool(post_types & image_types) or plan.get("images") is True \
        or bool(cfg.get("imagesRequested")) or (cfg.get("carousel") is True)
    video = bool("video" in post_types) or plan.get("video") is True or bool(cfg.get("videoRequested"))
    podcast = cfg.get("podcast") is True or plan.get("podcast") is True
    newsletter = cfg.get("newsletter") is True or plan.get("newsletter") is True
    blog = cfg.get("blog") is True or plan.get("blog") is True
    engage = cfg.get("engage") is True or plan.get("engage") is True
    return {"ghl_delivery": bool(ghl_delivery), "images": bool(images), "video": bool(video),
            "podcast": bool(podcast), "newsletter": bool(newsletter), "blog": bool(blog),
            "engage": bool(engage)}


def required_secrets_for_plan(cfg, plan):
    """The secret names the plan's REQUIRED nodes need (checked SET, never
    printed). Text roles always need OpenRouter when any authoring happens;
    GHL delivery needs the PIT; images need Kie; podcast needs Fish-Audio +
    Podbean only when the podcast fold is ON."""
    secrets = list(REQUIRED_SECRETS_BASE)
    if plan.get("ghl_delivery"):
        secrets.append("pit")
    if plan.get("images") or plan.get("video"):
        secrets.append("kieKey")
    secrets.append("openrouterKey")  # text/agent roles: every plan authors content
    if plan.get("podcast"):
        secrets.extend(_FOLD_REQUIREMENTS["podcast"])
    return secrets


def check_required_fields(cfg):
    """F19 minimal floor: brandName/locationId/userId/timezone/status +
    platforms OR an explicit plan; per-branch secrets resolved from the plan.
    openrouterModel/openrouterFallbacks are provider-policy contract fields
    (validated there), not global hard requirements."""
    plan = resolve_output_plan(cfg)
    fails = []
    missing = [f for f in REQUIRED_FIELDS if not _nonempty(cfg.get(f))]
    has_channels = _nonempty(cfg.get("platforms")) or _nonempty((cfg.get("plan") or {}).get("platforms")) \
        if isinstance(cfg.get("plan"), dict) else _nonempty(cfg.get("platforms"))
    if not has_channels:
        fails.append((AF_CONFIG, "missing required output plan: set `platforms` (or an explicit "
                      "`plan` object) — the dependency graph cannot resolve without a selected plan"))
    for f in missing:
        fails.append((AF_CONFIG, "missing/empty required config field(s): %s" % f))
    if not missing and not has_channels:
        pass  # already reported above; never double-report
    # secrets confirmed SET (value NEVER printed) — per the plan's branches
    unset = [s for s in sorted(set(required_secrets_for_plan(cfg, plan)))
             if not _nonempty(cfg.get(s))]
    if unset:
        fails.append((AF_CONFIG, "required secret(s) for the selected plan not SET (value never "
                      "printed): %s" % ", ".join(unset)))
    return fails


def check_status(cfg):
    if not _nonempty(cfg.get("status")):
        return [(AF_STATUS, "client status is missing; must be %r" % PAID_STATUS)]
    if cfg.get("status") != PAID_STATUS:
        return [(AF_STATUS, "client status is %r, must be %r" % (cfg.get("status"), PAID_STATUS))]
    return []


def check_kie_credits(cfg, live=False, plan=None):
    """F19: the image branch's cost gate — estimated from the PLANNED assets vs
    the available balance (the KIE_MIN_CREDITS band is the default estimate,
    a logged client-exact `creditEstimates.images` wins). Never evaluated when
    the plan requests no images/video."""
    plan = plan or resolve_output_plan(cfg)
    if not (plan.get("images") or plan.get("video")):
        return []  # no image/video branch -> no Kie requirement
    estimate = KIE_MIN_CREDITS
    est_cfg = (cfg.get("creditEstimates") or {})
    if isinstance(est_cfg, dict) and isinstance(est_cfg.get("images"), (int, float)) \
            and est_cfg["images"] > 0:
        estimate = est_cfg["images"]
    if live:
        val = _live_kie_credits(cfg)
    else:
        val = (cfg.get("probes") or {}).get("kieCredits")
    if not isinstance(val, (int, float)):
        return [(AF_CREDITS, "Kie.ai credit balance could not be confirmed for the planned "
                             "image/video assets (fail-closed)")]
    if val < estimate:
        return [(AF_CREDITS, "Kie.ai credits %s below the planned asset estimate %s" % (val, estimate))]
    return []


def check_openrouter_balance(cfg, live=False, plan=None):
    """F19: the text branch's cost gate — estimated from the plan vs the
    available balance (OPENROUTER_MIN_BALANCE is the default estimate, a logged
    client-exact `creditEstimates.text` wins)."""
    plan = plan or resolve_output_plan(cfg)
    if not (plan.get("ghl_delivery") or plan.get("newsletter") or plan.get("blog")):
        return []  # no authored delivery branch -> no text requirement
    estimate = OPENROUTER_MIN_BALANCE
    est_cfg = (cfg.get("creditEstimates") or {})
    if isinstance(est_cfg, dict) and isinstance(est_cfg.get("text"), (int, float)) \
            and est_cfg["text"] > 0:
        estimate = est_cfg["text"]
    if live:
        val = _live_openrouter_balance(cfg)
    else:
        val = (cfg.get("probes") or {}).get("openrouterBalance")
    if not isinstance(val, (int, float)):
        return [(AF_BALANCE, "OpenRouter balance could not be confirmed for the planned "
                             "authoring work (fail-closed)")]
    if val < estimate:
        return [(AF_BALANCE, "OpenRouter balance $%s below the plan estimate $%s" % (val, estimate))]
    return []


def check_capabilities(cfg, plan=None):
    """F19: branch-scoped capability checks. A requested-but-unresolvable
    branch FAILS CLOSED with a SPECIFIC repair action (never a global wall);
    unsupported modes are reported UNAVAILABLE before selection; a deferred
    stub is never presented as delivered."""
    plan = plan or resolve_output_plan(cfg)
    fails = []
    if plan.get("podcast"):
        # Only ON branches need credentials; unconfigured -> specific repair.
        if not (_nonempty(cfg.get("fishAudioKey")) and _nonempty(cfg.get("podbeanApi"))):
            fails.append((AF_CAPABILITY, "podcast branch requested but Fish-Audio/Podbean are not "
                          "both configured — repair: configure fishAudioKey+podbeanApi or turn the "
                          "podcast fold off (a labeled PODCAST_DEFERRED skip, not a failure)"))
    if plan.get("newsletter") and not _nonempty(cfg.get("plannerSheetId")):
        fails.append((AF_CAPABILITY, "newsletter branch requested but no plannerSheetId is set — "
                      "repair: set the planner sheet id or turn the newsletter fold off"))
    return fails


def check_ghl_token(cfg, live=False):
    if live:
        valid = _live_ghl_token(cfg)
    else:
        valid = (cfg.get("probes") or {}).get("ghlTokenValid")
    if valid is not True:
        return [(AF_TOKEN, "GHL Private Integration Token is not valid against GET /locations/{locationId}")]
    return []


def _supported_formats_for(platform, caps):
    """GHL-documented supported formats per platform, narrowed by the account's
    declared capabilities. An UNFAMILIAR platform label is allowed — it keeps
    whatever capabilities it declares (discovered_account.json: 'unfamiliar
    labels allowed with declared capabilities')."""
    p = str(platform).strip().lower()
    base = {
        "facebook": ["post", "carousel", "video", "story", "reel"],
        "instagram": ["post", "carousel", "story", "reel"],
        "linkedin": ["post", "carousel", "video"],
        "youtube": ["video", "short"],
        "tiktok": ["video", "short"],
        "pinterest": ["pin", "image"],
        "twitter": ["post"],
        "google-business": ["post", "image"],
        "threads": ["post"],
    }.get(p)
    if base is None:  # unfamiliar label: the account's own declared capabilities govern
        return [str(c).strip().lower() for c in (caps or []) if str(c).strip()]
    caps_lc = {str(c).strip().lower() for c in (caps or []) if str(c).strip()}
    if caps_lc:
        base = [f for f in base if f in caps_lc]
    return base


def build_account_plan(cfg, accounts):
    """F06 CORE (pure, deterministic). `accounts` is a list of discovered GHL
    account objects ({account_id, platform, account_name} — IDs PRESERVED, from
    ghl_contracts.fetch_accounts) intersected with the client-enabled channels.
    Returns (per_account_plan, summary):
      per-account: [{account_id, platform, account_name, capabilities,
                     health, supported_formats, exclusion_reason}]
      health: ready | skipped | needs_reconnect | retrying | failed
    NO platform-level collapse: two Facebook accounts are two entries, each
    with its own health and result. Excluded platforms are recorded as
    deliberate skips (platformsExcluded honored — never silently re-enabled).
    Connected-but-unconfigured channels are WARNING-level entries in the
    summary, never a run-wide BLOCK (F06)."""
    enabled = {str(p).strip().lower() for p in (cfg.get("platforms") or []) if str(p).strip()}
    excluded = {str(p).strip().lower() for p in (cfg.get("platformsExcluded") or []) if str(p).strip()}
    probe_health = cfg.get("probes", {}).get("accountHealth") or {}
    plan_rows, warnings = [], []
    for a in (accounts or []):
        if not isinstance(a, dict):
            continue
        platform = str(a.get("platform") or "").strip().lower()
        row = {
            "account_id": str(a.get("account_id") or ""),
            "platform": platform,
            "account_name": str(a.get("account_name") or ""),
            "capabilities": list(a.get("capabilities") or []),
            "health": HEALTH_READY,
            "supported_formats": _supported_formats_for(platform, a.get("capabilities")),
            "exclusion_reason": None,
        }
        if platform in excluded:
            row["health"] = HEALTH_SKIPPED
            row["exclusion_reason"] = "platformsExcluded (client's deliberate choice — FINAL, visible)"
        elif enabled and platform not in enabled:
            # Connected but not client-enabled: a WARNING-level report row —
            # visible in the reconcile summary, never a global BLOCK (F06).
            row["health"] = HEALTH_SKIPPED
            row["exclusion_reason"] = ("connected-but-unconfigured: not in the client's `platforms` "
                                       "list — add it to platforms or record it in platformsExcluded")
            warnings.append(row["account_id"] and
                            "account %s (%s) is connected but not configured" % (
                                row["account_id"], platform) or row["account_name"])
        probe = probe_health.get(row["account_id"]) if isinstance(probe_health, dict) else None
        if isinstance(probe, str) and probe in (HEALTH_NEEDS_RECONNECT, HEALTH_RETRYING, HEALTH_FAILED):
            row["health"] = probe
            row["exclusion_reason"] = "per-account health probe: %s" % probe
        plan_rows.append(row)
    # Configured platforms with NO live account keep the run ALIVE (F06) — they
    # surface as unmet channels in the summary, never as a run-wide BLOCK.
    covered = {r["platform"] for r in plan_rows if r["health"] == HEALTH_READY}
    unmet = sorted(enabled - covered - excluded)
    summary = {
        "enabled_platforms": sorted(enabled),
        "excluded_logged": sorted(excluded),
        "accounts": plan_rows,
        "ready_accounts": [r["account_id"] for r in plan_rows if r["health"] == HEALTH_READY],
        "unmet_configured_platforms": unmet,
        "warnings": warnings,
        "per_account": True,
    }
    return plan_rows, summary


def reconcile_connected_accounts(cfg, accounts):
    """F06 entry point (BACK-COMPAT SHAPE: returns (fails, summary)). The plan
    is per-account and one platform's absence NEVER blocks the run; a
    connected-but-unconfigured channel is a per-account WARNING, not a global
    BLOCK. BLOCKS only the unconfirmable-discovery case upstream
    (check_connected_accounts). `accounts` may be account objects
    ({account_id, platform, ...}) or legacy bare platform-name strings."""
    normalized = []
    for a in (accounts or []):
        if isinstance(a, dict):
            normalized.append(a)
        elif str(a).strip():
            normalized.append({"account_id": "", "platform": str(a).strip().lower(),
                               "account_name": ""})
    plan_rows, summary = build_account_plan(cfg, normalized)
    fails = []
    # FAIL-CLOSED only where a REQUIRED node truly depends on it: the discovery
    # itself. A configured platform with no healthy account is REPORTED here as
    # part of the plan; the run continues on the healthy accounts (F06).
    return fails, summary


def check_connected_accounts(cfg, live=False):
    """F06: per-account discovery + plan (AF-SM-DISCOVERY-DRIFT is now only the
    UNCONFIRMABLE-DISCOVERY code). Offline: reads probes.connectedAccounts
    (account objects or legacy platform-name strings); absent -> nothing to
    reconcile (dry-run posture). Live: the listing comes from the S1 documented
    contract (ghl_contracts.fetch_accounts); one account's failure downgrades
    THAT account (needs_reconnect/failed), the run continues on healthy ones —
    only a WHOLLY unconfirmable listing fails closed, and only when the plan
    actually needs GHL delivery."""
    plan = resolve_output_plan(cfg)
    if live:
        try:
            pit = _get_secret(cfg, "pit", "GHL_API_KEY")
            accounts = ghl_contracts.fetch_accounts(pit, cfg.get("locationId", ""))
        except ghl_contracts.GhlApiError as exc:
            if exc.error_class == ghl_contracts.E_RATE_LIMITED and exc.retry_after:
                return [(AF_DISCOVERY, "connected-accounts discovery rate-limited; retry after %ss"
                         % exc.retry_after)]
            if plan.get("ghl_delivery"):
                return [(AF_DISCOVERY, "connected-accounts discovery could not be confirmed against "
                         "the live GHL listing (%s — fail-closed for a GHL-delivery plan)" % exc)]
            return []  # no GHL-delivery branch -> the discovery is not a required node
    else:
        accounts = (cfg.get("probes") or {}).get("connectedAccounts")
        if accounts is None:
            return []  # offline dry-run without a discovery probe: nothing to reconcile
        if not isinstance(accounts, list):
            return [(AF_DISCOVERY, "probes.connectedAccounts must be an account list")]
    _fails, summary = reconcile_connected_accounts(cfg, accounts)
    return []


# ---- live probes (urllib; secret values used to auth, NEVER printed) --------
_CRED_CONFLICT_MSG = (
    "credential conflict: the client config and the environment set DIFFERENT "
    "values for the same credential (%s: config field %r vs env %s) — resolve "
    "the mismatch before running (values never printed). "
    "Sources: client config file + process environment (plus fleet env files "
    "via the Skill 44 secret canon)."
)


def _get_secret(cfg, field, env_name):
    """F18: ONE documented credential resolver.

    Delegates to shared-utils/social_planner_credentials.py (explicit
    precedence config field > canonical env name > Skill 44 canonical
    resolver, conflicting config/env values FAIL CLOSED: raises
    CredentialConflictError) when importable. The conflict surfaces here as a
    blocking AF-SM-CRED-CONFLICT failure (named sources, values never
    printed); only an ImportError/AttributeError (resolver absent) falls back
    to the historical config-then-env behavior — so a deployment without
    shared-utils keeps working exactly as before.
    Secret values are used to authenticate and are NEVER printed.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared-utils"))
        from social_planner_credentials import (  # noqa: PLC0415
            CREDENTIALS,
            CredentialConflictError,
            resolve_planner_credentials,
        )
        try:
            creds, _report = resolve_planner_credentials(cfg)
        except CredentialConflictError as exc:
            try:
                _cfg_field, _canon_env, _svc = CREDENTIALS.get(field, (field, env_name, ""))
            except Exception:  # noqa: BLE001 — table unreadable: name the fallback
                _cfg_field, _canon_env = field, env_name
            raise _CredentialConflict(_CRED_CONFLICT_MSG % (_cfg_field, _cfg_field, _canon_env)) from exc
        return creds.get(field) or ""
    except (ImportError, AttributeError):  # noqa: BLE001 — resolver unavailable: historical behavior
        v = cfg.get(field)
        if _nonempty(v):
            return v
        return os.environ.get(env_name, "")


def _http_get_json(url, headers, timeout=15):
    import urllib.request
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - client's own endpoints
        return json.loads(resp.read().decode("utf-8"))


def _live_kie_credits(cfg):
    try:
        key = _get_secret(cfg, "kieKey", "KIE_API_KEY")
    except _CredentialConflict:
        raise
    try:
        data = _http_get_json("https://api.kie.ai/api/v1/chat/credit",
                              {"Authorization": "Bearer %s" % key})
        for k in ("credits", "data", "balance", "credit"):
            v = data.get(k) if isinstance(data, dict) else None
            if isinstance(v, (int, float)):
                return v
            if isinstance(v, dict) and isinstance(v.get("credits"), (int, float)):
                return v["credits"]
    except Exception:
        return None
    return None


def _live_openrouter_balance(cfg):
    try:
        key = _get_secret(cfg, "openrouterKey", "OPENROUTER_API_KEY")
    except _CredentialConflict:
        raise
    try:
        data = _http_get_json("https://openrouter.ai/api/v1/credits",
                              {"Authorization": "Bearer %s" % key})
        d = data.get("data", data) if isinstance(data, dict) else {}
        total = d.get("total_credits")
        used = d.get("total_usage")
        if isinstance(total, (int, float)) and isinstance(used, (int, float)):
            return total - used
        if isinstance(d.get("balance"), (int, float)):
            return d["balance"]
    except Exception:
        return None
    return None


def _live_ghl_token(cfg):
    try:
        pit = _get_secret(cfg, "pit", "GHL_API_KEY")
    except _CredentialConflict:
        raise
    try:
        loc = cfg.get("locationId", "")
        data = _http_get_json("https://services.leadconnectorhq.com/locations/%s" % loc,
                              {"Authorization": "Bearer %s" % pit, "Version": "2021-07-28"})
        return isinstance(data, dict) and bool(data.get("location") or data.get("id") or data.get("_id"))
    except Exception:
        return False


def _live_connected_accounts(cfg):
    """F06/F09: live GHL connected-accounts for the location via the S1
    documented contract (ghl_contracts.fetch_accounts — IDs preserved).
    Returns the normalized account-object list, or None when unconfirmable
    (classified upstream by check_connected_accounts)."""
    try:
        pit = _get_secret(cfg, "pit", "GHL_API_KEY")
        return ghl_contracts.fetch_accounts(pit, cfg.get("locationId", ""))
    except ghl_contracts.GhlApiError:
        return None


def evaluate(cfg, live=False):
    """F19: run the capability/dependency graph for THIS plan. Every checker is
    plan-scoped; unused providers are never consulted."""
    plan = resolve_output_plan(cfg)
    fails = []
    fails += check_required_fields(cfg)
    fails += check_status(cfg)
    try:
        fails += check_kie_credits(cfg, live, plan)
        fails += check_openrouter_balance(cfg, live, plan)
        if plan.get("ghl_delivery"):
            fails += check_ghl_token(cfg, live)
            fails += check_connected_accounts(cfg, live)
    except _CredentialConflict as exc:
        fails.append((AF_CRED_CONFLICT, str(exc)))
    fails += check_capabilities(cfg, plan)
    return fails


def decide_exit(failures):
    return EXIT_PASS if not failures else EXIT_AUTOFAIL


def _write_report(report_path, cfg, failures, live=False):
    try:
        rec = {"gate": "social-media-preflight", "brand": cfg.get("brandName", ""),
               "pass": not failures,
               "failures": [{"code": c, "message": m} for c, m in failures]}
        # C2 + F06: persist the discovery reconcile so Owner Q&A answers publish
        # scope from the LIVE result on record, never a memorized list.
        # A credential conflict is already recorded in `failures` by evaluate;
        # the report must still write, so the conflict is not re-raised here.
        if live:
            try:
                accounts = _live_connected_accounts(cfg)
            except _CredentialConflict:
                accounts = None
        else:
            accounts = (cfg.get("probes") or {}).get("connectedAccounts")
        if isinstance(accounts, list):
            _f, summary = reconcile_connected_accounts(cfg, accounts)
            rec["account_plan"] = summary
            # Back-compat mirror for older report readers (platform-level view).
            rec["connected_accounts"] = {
                "configured": summary.get("enabled_platforms"),
                "live_connected": sorted({r["platform"] for r in summary.get("accounts", [])
                                          if r.get("platform")}),
                "excluded_logged": summary.get("excluded_logged"),
                "ready_accounts": summary.get("ready_accounts"),
                "per_account": True,
            }
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(json.dumps(rec, indent=2), encoding="utf-8")
    except OSError:
        pass


def _emit(source, failures, as_json):
    if as_json:
        print(json.dumps({"gate": "social-media-preflight", "source": source, "pass": not failures,
                          "failures": [{"code": c, "message": m} for c, m in failures]}, indent=2))
        return
    print("== Social Media in a Box :: preflight gate ==")
    print("source: %s" % source)
    if not failures:
        print("RESULT: PASS — box is ready (credits/balance/token/config/status).")
    else:
        print("RESULT: FAIL (fail-closed, run BLOCKED) — %d violation(s):" % len(failures))
        for c, m in failures:
            print("  [%s] %s" % (c, m))


def run(path, live=False, as_json=False, report=None):
    p = Path(path)
    if not p.is_file():
        _emit(str(p), [(AF_CONFIG, "config file not found: %s" % p)], as_json)
        return EXIT_USAGE
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        _emit(str(p), [(AF_CONFIG, "cannot read/parse config JSON: %s" % exc)], as_json)
        return EXIT_USAGE
    failures = evaluate(cfg, live=live)
    if report:
        _write_report(report, cfg, failures, live=live)
    _emit(str(p), failures, as_json)
    return decide_exit(failures)


# =============================================================================
# SELF-TEST — offline probe fixtures.
# =============================================================================
def _ready_cfg():
    return {
        "brandName": "Brand One", "pit": "pit-set", "locationId": "loc123", "userId": "user123",
        "openrouterKey": "set", "openrouterModel": "google/gemini-2.0-flash-001",
        "openrouterFallbacks": ["meta-llama/llama-3.1-70b", "mistralai/mistral-large"],
        "kieKey": "set", "geminiKey": "set", "platforms": ["facebook"], "postTypes": ["post"],
        "timezone": "America/New_York", "status": "Paid",
        "probes": {"kieCredits": 500, "openrouterBalance": 25.0, "ghlTokenValid": True,
                   "connectedAccounts": [{"account_id": "fb-1", "platform": "facebook",
                                          "account_name": "Brand One FB"}]},
    }


def self_test():
    ok = True

    def cp(name, cfg):
        nonlocal ok
        fails = evaluate(cfg)
        good = not fails
        ok = ok and good
        print("  [%s] READY %-24s -> exit %d %s" % ("PASS" if good else "MISS", name,
              decide_exit(fails), "" if good else fails))

    def cf(name, cfg, expect):
        nonlocal ok
        fails = evaluate(cfg)
        codes = [c for c, _ in fails]
        good = bool(fails) and expect in codes
        ok = ok and good
        print("  [%s] BLOCK %-24s -> exit %d has %s %s" % ("PASS" if good else "MISS", name,
              decide_exit(fails), expect, "" if good else codes))

    print("== self-test: READY (must PASS / exit 0) ==")
    cp("all-green", _ready_cfg())
    # F06: one platform's account absent — the run CONTINUES on the healthy one
    c = _ready_cfg(); c["platforms"] = ["facebook", "instagram"]
    c["probes"]["connectedAccounts"] = [{"account_id": "fb-1", "platform": "facebook",
                                         "account_name": "Brand One FB"}]
    cp("instagram-absent-continues", c)
    # F06: connected-but-unconfigured channel is a WARNING, not a BLOCK
    c = _ready_cfg()
    c["probes"]["connectedAccounts"] = [
        {"account_id": "fb-1", "platform": "facebook", "account_name": "Brand One FB"},
        {"account_id": "x-1", "platform": "twitter", "account_name": "Brand One X"}]
    cp("unconfigured-channel-warns", c)
    # F06: a live-connected extra channel deliberately excluded (LOGGED) -> PASS
    c = _ready_cfg()
    c["probes"]["connectedAccounts"] = [
        {"account_id": "fb-1", "platform": "facebook", "account_name": "Brand One FB"},
        {"account_id": "x-1", "platform": "twitter", "account_name": "Brand One X"}]
    c["platformsExcluded"] = ["twitter"]
    cp("discovery-logged-exclusion", c)
    # F19: text-only plan needs NO image/podcast credentials
    c = _ready_cfg(); del c["kieKey"]; del c["geminiKey"]
    c["probes"].pop("kieCredits", None)
    c["postTypes"] = ["post"]; c.pop("carousel", None)
    cp("text-only-no-media-creds", c)

    print("== self-test: BLOCKED (must FAIL / exit 2) ==")
    c = _ready_cfg(); c["probes"]["kieCredits"] = 150
    c["postTypes"] = ["carousel"]  # image branch requested -> Kie is required
    cf("kie-credits-low-images", c, AF_CREDITS)
    c = _ready_cfg(); c["probes"]["openrouterBalance"] = 2.0
    cf("openrouter-low", c, AF_BALANCE)
    c = _ready_cfg(); c["probes"]["ghlTokenValid"] = False
    cf("ghl-token-invalid", c, AF_TOKEN)
    c = _ready_cfg(); c["status"] = "Trial"
    cf("status-not-paid", c, AF_STATUS)
    c = _ready_cfg(); del c["locationId"]
    cf("missing-field", c, AF_CONFIG)
    c = _ready_cfg(); c["pit"] = ""
    cf("secret-unset", c, AF_CONFIG)
    c = _ready_cfg(); del c["probes"]
    c["postTypes"] = ["post"]; c.pop("carousel", None)  # keep the text branch; drop all probes
    cf("no-probes-failclosed", c, AF_BALANCE)
    # F19: podcast branch requested without Fish-Audio/Podbean -> specific repair
    c = _ready_cfg(); c["podcast"] = True
    cf("podcast-unconfigured", c, AF_CAPABILITY)
    # F06: a malformed discovery probe is refused (fail-closed)
    c = _ready_cfg(); c["probes"]["connectedAccounts"] = "facebook"
    cf("discovery-malformed", c, AF_DISCOVERY)

    print("== self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fail-closed preflight readiness gate (Skill 57).")
    ap.add_argument("path", nargs="?", help="client config.json")
    ap.add_argument("--live", action="store_true", help="probe real endpoints (client's own keys)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--report", help="write a labeled failure/PASS report to this path")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.path:
        ap.error("a config path is required (or use --self-test)")
    return run(args.path, live=args.live, as_json=args.json, report=args.report)


if __name__ == "__main__":
    sys.exit(main())
