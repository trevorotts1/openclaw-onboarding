#!/usr/bin/env python3
# =============================================================================
# SKILL 57 — SOCIAL MEDIA IN A BOX :: PREFLIGHT GATE (fail-closed readiness)
# -----------------------------------------------------------------------------
# DETERMINISTIC, FAIL-CLOSED per run (Module 0). Ports part2-validation:
#   * Kie.ai credits    >= 200      (https://api.kie.ai/api/v1/chat/credit)   -> AF-SM-PREFLIGHT-CREDITS
#   * OpenRouter balance >= $5      (https://openrouter.ai/api/v1/credits)    -> AF-SM-PREFLIGHT-BALANCE
#   * GHL PIT valid                 (GET /locations/{locationId})             -> AF-SM-PREFLIGHT-TOKEN
#   * required config fields present + secrets SET (never printed)            -> AF-SM-PREFLIGHT-CONFIG
#   * client status == Paid                                                   -> AF-SM-PREFLIGHT-STATUS
#   * C2 LIVE CONNECTED-ACCOUNTS DISCOVERY (merge plan C2/R8): the config
#     `platforms` enum is RECONCILED against the live GHL connected-accounts
#     listing (GET /social-media-posting/oauth/{locationId}/accounts)          -> AF-SM-DISCOVERY-DRIFT
#       - a configured platform with NO live-connected account -> BLOCK
#         (posting there would silently fail);
#       - a live-connected platform MISSING from the config enum -> BLOCK
#         (the BANNED silent-miss Skill 35 hardened against: a channel the
#         client actually connected must never be silently skipped). The
#         client's deliberate exclusion is honored via the LOGGED
#         `platformsExcluded` list (client's choice is FINAL, never silent).
#     Owner Q&A ("what does my planner post, and where?") is answered from
#     THIS reconcile result — the live listing, never a memorized list.
# FAIL -> a labeled failure report + configured notification; the run is
# BLOCKED (sys.exit 2) and NO downstream module can execute.
#
# Two modes:
#   * offline (default): reads a "probes" object from the config (kieCredits,
#     openrouterBalance, ghlTokenValid, connectedAccounts) and evaluates the
#     thresholds deterministically. This is what the self-test and dry-runs
#     use. `connectedAccounts` absent -> nothing to reconcile in a dry-run
#     (the credits/balance/token probes stay REQUIRED fail-closed).
#   * --live: probes the real endpoints with the CLIENT's own keys via urllib.
#     A probe that cannot be confirmed is treated as FAIL (fail-closed) —
#     INCLUDING the connected-accounts discovery. Secret values are used to
#     authenticate but are NEVER printed.
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

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

AF_CREDITS = "AF-SM-PREFLIGHT-CREDITS"
AF_BALANCE = "AF-SM-PREFLIGHT-BALANCE"
AF_TOKEN = "AF-SM-PREFLIGHT-TOKEN"
AF_CONFIG = "AF-SM-PREFLIGHT-CONFIG"
AF_STATUS = "AF-SM-PREFLIGHT-STATUS"
AF_DISCOVERY = "AF-SM-DISCOVERY-DRIFT"

KIE_MIN_CREDITS = 200
OPENROUTER_MIN_BALANCE = 5.0
PAID_STATUS = "Paid"

# Fields that must be present (non-empty) on the client config. Secret fields
# are confirmed SET (non-empty) but their values are never printed.
REQUIRED_FIELDS = ("brandName", "locationId", "userId", "openrouterModel",
                   "openrouterFallbacks", "platforms", "postTypes", "timezone", "status")
REQUIRED_SECRETS = ("pit", "openrouterKey", "kieKey", "geminiKey")


def _nonempty(v):
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return v is not None


def check_required_fields(cfg):
    fails = []
    missing = [f for f in REQUIRED_FIELDS if not _nonempty(cfg.get(f))]
    if missing:
        fails.append((AF_CONFIG, "missing/empty required config field(s): %s" % ", ".join(missing)))
    fb = cfg.get("openrouterFallbacks")
    if isinstance(fb, list) and len(fb) != 2:
        fails.append((AF_CONFIG, "openrouterFallbacks must be exactly 2 (got %d)" % len(fb)))
    # secrets confirmed SET (value NEVER printed)
    unset = [s for s in REQUIRED_SECRETS if not _nonempty(cfg.get(s))]
    if unset:
        fails.append((AF_CONFIG, "required secret(s) not SET (value never printed): %s" % ", ".join(unset)))
    return fails


def check_status(cfg):
    if cfg.get("status") != PAID_STATUS:
        return [(AF_STATUS, "client status is %r, must be %r" % (cfg.get("status"), PAID_STATUS))]
    return []


def check_kie_credits(cfg, live=False):
    if live:
        val = _live_kie_credits(cfg)
    else:
        val = (cfg.get("probes") or {}).get("kieCredits")
    if not isinstance(val, (int, float)):
        return [(AF_CREDITS, "Kie.ai credit balance could not be confirmed (fail-closed)")]
    if val < KIE_MIN_CREDITS:
        return [(AF_CREDITS, "Kie.ai credits %s below minimum %d" % (val, KIE_MIN_CREDITS))]
    return []


def check_openrouter_balance(cfg, live=False):
    if live:
        val = _live_openrouter_balance(cfg)
    else:
        val = (cfg.get("probes") or {}).get("openrouterBalance")
    if not isinstance(val, (int, float)):
        return [(AF_BALANCE, "OpenRouter balance could not be confirmed (fail-closed)")]
    if val < OPENROUTER_MIN_BALANCE:
        return [(AF_BALANCE, "OpenRouter balance $%s below minimum $%s" % (val, OPENROUTER_MIN_BALANCE))]
    return []


def check_ghl_token(cfg, live=False):
    if live:
        valid = _live_ghl_token(cfg)
    else:
        valid = (cfg.get("probes") or {}).get("ghlTokenValid")
    if valid is not True:
        return [(AF_TOKEN, "GHL Private Integration Token is not valid against GET /locations/{locationId}")]
    return []


def reconcile_connected_accounts(cfg, accounts):
    """C2 core reconcile (pure, deterministic). `accounts` is the live GHL
    connected-accounts platform list. Returns (fails, summary). Both drift
    directions BLOCK; a deliberate exclusion is honored only through the
    LOGGED `platformsExcluded` list (the client's choice is FINAL — and
    visible, never silent)."""
    fails = []
    configured = {str(p).strip().lower() for p in (cfg.get("platforms") or []) if str(p).strip()}
    live_set = {str(a).strip().lower() for a in accounts if str(a).strip()}
    excluded = {str(p).strip().lower() for p in (cfg.get("platformsExcluded") or []) if str(p).strip()}
    not_connected = sorted(configured - live_set)
    if not_connected:
        fails.append((AF_DISCOVERY, "configured platform(s) with NO live-connected GHL account: %s "
                      "(posting there would silently fail — connect the account or remove/exclude "
                      "the platform)" % ", ".join(not_connected)))
    silently_missed = sorted(live_set - configured - excluded)
    if silently_missed:
        fails.append((AF_DISCOVERY, "live-connected platform(s) MISSING from the config enum: %s "
                      "(the BANNED silent-miss — a channel the client connected must never be "
                      "silently skipped; add it to `platforms` or record the client's deliberate "
                      "exclusion in `platformsExcluded`)" % ", ".join(silently_missed)))
    summary = {"configured": sorted(configured), "live_connected": sorted(live_set),
               "excluded_logged": sorted(excluded), "drift": bool(fails)}
    return fails, summary


def check_connected_accounts(cfg, live=False):
    """C2 live connected-accounts discovery + reconcile (AF-SM-DISCOVERY-DRIFT).
    Offline: reads probes.connectedAccounts (a platform list) when supplied by
    the dry-run; absent -> nothing to reconcile (dry-run posture; the other
    probes stay REQUIRED). Live: the discovery is REQUIRED and fail-closed —
    an unconfirmable listing BLOCKS the run. Owner Q&A answers publish scope
    from this reconcile result, never a memorized list."""
    if live:
        accounts = _live_connected_accounts(cfg)
        if not isinstance(accounts, list):
            return [(AF_DISCOVERY, "connected-accounts discovery could not be confirmed against "
                     "the live GHL listing (fail-closed)")]
    else:
        accounts = (cfg.get("probes") or {}).get("connectedAccounts")
        if accounts is None:
            return []  # offline dry-run without a discovery probe: nothing to reconcile
        if not isinstance(accounts, list):
            return [(AF_DISCOVERY, "probes.connectedAccounts must be a platform list")]
    fails, _summary = reconcile_connected_accounts(cfg, accounts)
    return fails


# ---- live probes (urllib; secret values used to auth, NEVER printed) --------
def _get_secret(cfg, field, env_name):
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
        loc = cfg.get("locationId", "")
        data = _http_get_json("https://services.leadconnectorhq.com/locations/%s" % loc,
                              {"Authorization": "Bearer %s" % pit, "Version": "2021-07-28"})
        return isinstance(data, dict) and bool(data.get("location") or data.get("id") or data.get("_id"))
    except Exception:
        return False


def _live_connected_accounts(cfg):
    """C2: live GHL connected-accounts listing for the location (client's own PIT).
    Returns a platform-name list, or None when unconfirmable (fail-closed upstream)."""
    try:
        pit = _get_secret(cfg, "pit", "GHL_API_KEY")
        loc = cfg.get("locationId", "")
        data = _http_get_json(
            "https://services.leadconnectorhq.com/social-media-posting/oauth/%s/accounts" % loc,
            {"Authorization": "Bearer %s" % pit, "Version": "2021-07-28"})
        if not isinstance(data, dict):
            return None
        results = data.get("results") or data.get("accounts") or data.get("data")
        if isinstance(results, dict):
            results = results.get("accounts") or results.get("results")
        if not isinstance(results, list):
            return None
        platforms = []
        for a in results:
            if isinstance(a, dict):
                p = a.get("platform") or a.get("type") or a.get("oauthProvider")
                if isinstance(p, str) and p.strip():
                    platforms.append(p.strip().lower())
        return platforms
    except Exception:
        return None


def evaluate(cfg, live=False):
    fails = []
    fails += check_required_fields(cfg)
    fails += check_status(cfg)
    fails += check_kie_credits(cfg, live)
    fails += check_openrouter_balance(cfg, live)
    fails += check_ghl_token(cfg, live)
    fails += check_connected_accounts(cfg, live)
    return fails


def decide_exit(failures):
    return EXIT_PASS if not failures else EXIT_AUTOFAIL


def _write_report(report_path, cfg, failures, live=False):
    try:
        rec = {"gate": "social-media-preflight", "brand": cfg.get("brandName", ""),
               "pass": not failures,
               "failures": [{"code": c, "message": m} for c, m in failures]}
        # C2: persist the discovery reconcile so Owner Q&A answers publish scope
        # from the LIVE result on record, never a memorized list.
        accounts = _live_connected_accounts(cfg) if live \
            else (cfg.get("probes") or {}).get("connectedAccounts")
        if isinstance(accounts, list):
            _f, summary = reconcile_connected_accounts(cfg, accounts)
            rec["connected_accounts"] = summary
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
        "probes": {"kieCredits": 500, "openrouterBalance": 25.0, "ghlTokenValid": True},
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
    # C2: discovery reconcile — live listing matches the enum -> PASS
    c = _ready_cfg(); c["probes"]["connectedAccounts"] = ["facebook"]
    cp("discovery-reconciled", c)
    # C2: a live-connected extra channel deliberately excluded (LOGGED) -> PASS
    c = _ready_cfg(); c["probes"]["connectedAccounts"] = ["facebook", "twitter"]
    c["platformsExcluded"] = ["twitter"]
    cp("discovery-logged-exclusion", c)

    print("== self-test: BLOCKED (must FAIL / exit 2) ==")
    c = _ready_cfg(); c["probes"]["kieCredits"] = 150
    cf("kie-credits-low", c, AF_CREDITS)
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
    c = _ready_cfg(); c["openrouterFallbacks"] = ["only-one"]
    cf("fallbacks-not-2", c, AF_CONFIG)
    c = _ready_cfg(); del c["probes"]
    cf("no-probes-failclosed", c, AF_CREDITS)
    # C2: a configured platform with NO live-connected account -> BLOCK
    c = _ready_cfg(); c["platforms"] = ["facebook", "instagram"]
    c["probes"]["connectedAccounts"] = ["facebook"]
    cf("discovery-not-connected", c, AF_DISCOVERY)
    # C2: the BANNED silent-miss — a live-connected channel missing from the enum -> BLOCK
    c = _ready_cfg(); c["probes"]["connectedAccounts"] = ["facebook", "twitter"]
    cf("discovery-silent-miss", c, AF_DISCOVERY)
    # C2: a malformed discovery probe is refused (fail-closed)
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
