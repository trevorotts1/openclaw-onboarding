#!/usr/bin/env python3
"""Fix 10 - three-tier D2 paid-model classification (config/signatures.json
paid_tier_markers).  Offline, hermetic, stdlib only, no network, no subprocess,
no model call.  Run:  python3 tests/test_paid_tiers.py   (rc 0 = all PASS).

Holds the REFERENCE resolver for the tier structure.  The D2 rebuild (Fix 1) binds
to the structure described in paid_tier_markers._source; copy resolve_tier() and
severity_for() rather than re-deriving them.

ponytail: resolve_tier() is test-local on purpose - loop_common.py is owned by the
D2 rebuild lane. Move it into loop_common.model_id_flags when that lane lands.
"""
import copy
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(SKILL / "scripts"))
import loop_common as C            # noqa: E402
import loop_detectors as D         # noqa: E402
import loop_watchdog as W          # noqa: E402

FIXTURE = HERE / "fixtures" / "paid-tier.rows.json"
RANK = {None: 0, "WARN": 1, "P1": 2}
FAILS = []


def check(name, ok, detail=""):
    print("  %s: %s%s" % (name, "PASS" if ok else "FAIL", (" (%s)" % detail) if detail else ""))
    if not ok:
        FAILS.append(name)


# --------------------------------------------------------------------------- #
# reference resolver - implements paid_tier_markers._source steps (1)-(8)
# --------------------------------------------------------------------------- #
def resolve_tier(model_id, sig):
    """Return 'metered' | 'subscription_capped' | 'local' | 'unclassified'."""
    pt = sig["paid_tier_markers"]
    if not isinstance(model_id, str) or not model_id.strip():
        return "unclassified"
    norm = pt["normalize"]
    s = model_id.strip()
    if norm.get("lowercase"):
        s = s.lower()
    if norm.get("strip_leading_slashes"):
        s = s.lstrip("/")
    if norm.get("strip_one_trailing_parenthesized_qualifier"):
        s = re.sub(r"\([^()]*\)$", "", s)
    routed = False
    rp = norm.get("router_prefix", "")
    if rp and s.startswith(rp):
        s, routed = s[len(rp):], True
    tiers = pt["tiers"]
    met, sub, loc = tiers["metered"], tiers["subscription_capped"], tiers["local"]
    if met.get("include_anthropic_family") and any(
            s.startswith(p.lower()) for p in sig.get("anthropic_family_deny_prefixes", [])):
        return "metered"
    provider = s.split("/", 1)[0] if "/" in s else ""
    name = s.rsplit("/", 1)[-1]
    if provider in loc["providers"]:
        return "local"
    if provider in met["providers"] or any(provider.startswith(p) for p in met["provider_prefixes"]):
        return "metered"
    if (provider in sub["providers"]
            or (routed and provider in sub["providers_when_router_prefixed"])
            or any(name.endswith(x) for x in sub["name_suffixes"])):
        return "subscription_capped"
    if not routed and provider in loc["providers_when_not_router_prefixed"]:
        return "local"
    return "unclassified"


def severity_for(tier, per_hour, idle_streak, th, sig):
    """Reference D2 severity for ONE idle window of `per_hour` tokens in `tier`: the
    same ladder d2_token_burn_rate uses, clamped to the tier's idle_burn_severity_max.
    Returns (severity|None, label|None)."""
    t = th["d2_token_burn_rate"]
    cfg = sig["paid_tier_markers"]["tiers"].get(tier)
    if cfg is None or cfg["idle_burn_severity_max"] is None:
        return None, None
    if per_hour > t["p1_tokens_per_hour"]:
        sev = "P1"
    elif per_hour > t["warn_tokens_per_hour"]:
        sev = "WARN"
    elif per_hour > 0 and idle_streak >= t["idle_paid_windows_to_p1"]:
        sev = "P1"
    else:
        sev = None
    if sev is not None and RANK[sev] > RANK[cfg["idle_burn_severity_max"]]:
        sev = cfg["idle_burn_severity_max"]
    return sev, (cfg["label"] if sev else None)


def real_d2_severity(tokens, streak, th):
    w = [{"label": "w", "paid_tokens": tokens, "local_tokens": 0,
          "initiated_sessions": 0, "idle_consecutive": streak}]
    f = D.d2_token_burn_rate(w, th)
    return f[0]["severity"] if f else None


def row_id(row):
    return "".join(row["id_parts"]) if "id_parts" in row else row["id"]


def main():
    sig = C.load_signatures()
    th = C.load_skill_config("thresholds.json")
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))["rows"]
    pt = sig["paid_tier_markers"]

    # ---- 1. structure --------------------------------------------------- #
    tiers = pt["tiers"]
    check("structure: exactly three tiers", sorted(tiers) == ["local", "metered", "subscription_capped"])
    check("structure: only metered counts as paid",
          [k for k, v in tiers.items() if v["counts_as_paid"]] == ["metered"])
    check("structure: ceilings metered=P1 subscription=WARN local=none",
          tiers["metered"]["idle_burn_severity_max"] == "P1"
          and tiers["subscription_capped"]["idle_burn_severity_max"] == "WARN"
          and tiers["local"]["idle_burn_severity_max"] is None)
    check("structure: subscription never silent, 402/429 semantics named, label says usage-window",
          tiers["subscription_capped"]["never_silent"] is True
          and "402" in tiers["subscription_capped"]["semantics"]
          and "429" in tiers["subscription_capped"]["semantics"]
          and "usage-window" in tiers["subscription_capped"]["label"])
    check("structure: _source documents the tier structure for the D2 rebuild",
          all(k in pt["_source"] for k in ("metered", "subscription_capped", "local", "RESOLUTION", "D2 EXPECTATION")))
    prov = {k: set(v.get("providers", [])) for k, v in tiers.items()}
    check("structure: no provider listed in two tiers",
          not (prov["metered"] & prov["subscription_capped"]
               or prov["metered"] & prov["local"]
               or prov["subscription_capped"] & prov["local"]))
    named = {"deepseek", "alibaba", "moonshot", "google"}
    check("structure: spec-named metered providers present + anthropic family flagged",
          named <= prov["metered"] and tiers["metered"]["include_anthropic_family"] is True
          and "ollama-cloud" in prov["subscription_capped"] and "ollama-local" in prov["local"])
    check("structure: router prefix is 9router/", pt["normalize"]["router_prefix"] == "9router/")
    check("structure: no approval gate anywhere in the file",
          "requireapproval" not in (SKILL / "config" / "signatures.json").read_text(encoding="utf-8").lower())

    # ---- 2. fixture rows per tier + 9router/... forms -------------------- #
    real_socket, real_popen = socket.socket, subprocess.Popen

    def _boom(*a, **k):
        raise AssertionError("network/subprocess used during tier resolution")
    socket.socket, subprocess.Popen = _boom, _boom
    try:
        bad = [(row_id(r), r["tier"], resolve_tier(row_id(r), sig))
               for r in rows if resolve_tier(row_id(r), sig) != r["tier"]]
    finally:
        socket.socket, subprocess.Popen = real_socket, real_popen
    counts = {t: sum(1 for r in rows if r["tier"] == t) for t in
              ("metered", "subscription_capped", "local", "unclassified")}
    check("rows: every fixture row resolves to its tier (no network, no subprocess)",
          not bad, "%d rows %s%s" % (len(rows), counts, (" MISMATCH %s" % bad) if bad else ""))
    routed = [r for r in rows if row_id(r).lower().startswith("9router/")]
    check("rows: 9router/...-named forms covered in every classified tier",
          {r["tier"] for r in routed} >= {"metered", "subscription_capped", "local"},
          "%d routed rows" % len(routed))
    traps = [r for r in rows if "TRAP" in r["note"]]
    check("rows: provider-segment traps present (word deepseek / cloud inside another provider's id)",
          len(traps) >= 3 and all(resolve_tier(row_id(r), sig) == r["tier"] for r in traps))

    # ---- 3. severity per tier (same tokens, three different outcomes) ---- #
    hi = 300000
    sev_m, lab_m = severity_for("metered", hi, 1, th, sig)
    sev_s, lab_s = severity_for("subscription_capped", hi, 1, th, sig)
    sev_l, lab_l = severity_for("local", hi, 1, th, sig)
    check("severity: metered idle burn -> P1", sev_m == "P1")
    check("severity: subscription idle burn -> WARN at most, labelled usage-window, never P1",
          sev_s == "WARN" and "usage-window" in lab_s)
    check("severity: ollama-local same burn -> silent", sev_l is None)
    streak_m = severity_for("metered", 5000, 4, th, sig)[0]
    streak_s = severity_for("subscription_capped", 5000, 4, th, sig)[0]
    check("severity: 4-idle-window ANY-burn rule clamps subscription to WARN, metered stays P1",
          streak_m == "P1" and streak_s == "WARN")
    grid = [(tok, st) for tok in (0, 10000, 60000, 300000) for st in (1, 4)]
    drift = [(tok, st) for tok, st in grid
             if severity_for("metered", tok, st, th, sig)[0] != real_d2_severity(tok, st, th)]
    check("severity: reference metered ladder == real d2_token_burn_rate over the grid",
          not drift, "%d points" % len(grid))
    # the live D2 as shipped raises P1 on a paid_tokens window - so the metered path is the
    # ONLY tier that may be routed into paid_tokens; subscription/local tokens must not be.
    check("severity: live D2 P1 path fires for a metered window, silent when subscription/local tokens are not charged as paid",
          real_d2_severity(hi, 1, th) == "P1" and real_d2_severity(0, 1, th) is None)

    # ---- 4. legacy flat reader still parses the new shape ---------------- #
    with tempfile.TemporaryDirectory(prefix="paid-tier-test-") as td:
        stub = Path(td) / "signatures.json"
        stub.write_text(json.dumps(sig), encoding="utf-8")
        loaded = json.loads(stub.read_text(encoding="utf-8"))
    flags = {i: C.model_id_flags(i, loaded) for i in
             ("openrouter/glm-5.3", "ollama/minimax-m3:cloud", "ollama-local/ornith-1.5:9b", "glm-5.2", "")}
    check("reader: model_id_flags parses the new JSON (dict with family+paid for every id)",
          all(set(v) == {"family", "paid"} for v in flags.values()))
    check("reader: legacy flat mirror - openrouter paid, :cloud NOT paid, ollama-local NOT paid",
          flags["openrouter/glm-5.3"]["paid"] is True
          and flags["ollama/minimax-m3:cloud"]["paid"] is False
          and flags["ollama-local/ornith-1.5:9b"]["paid"] is False)
    unsound = [row_id(r) for r in rows
               if C.model_id_flags(row_id(r), sig)["paid"] and r["tier"] != "metered"]
    check("reader: legacy mirror is SOUND (never marks a subscription/local/unclassified id paid)",
          not unsound, str(unsound))
    old_shape = {"anthropic_family_deny_prefixes": sig["anthropic_family_deny_prefixes"],
                 "paid_tier_markers": {"suffix_deny": [":cloud"], "metered_provider_slugs": ["openrouter"]}}
    check("reader: pre-tier (schema 1) JSON still parses with the same reader",
          C.model_id_flags("x:cloud", old_shape)["paid"] is True
          and C.model_id_flags("glm-5.2", old_shape)["paid"] is False)
    check("reader: watchdog _paid_event over the new JSON (ollama :cloud not paid, openrouter paid)",
          W._paid_event({"provider": "ollama", "modelId": "minimax-m3:cloud"}, sig) is False
          and W._paid_event({"provider": "openrouter", "modelId": "z-ai/glm-5.3"}, sig) is True)
    check("reader: d2_token_burn_rate accepts the new signatures dict",
          D.d2_token_burn_rate([{"label": "w", "paid_tokens": hi, "initiated_sessions": 0,
                                 "idle_consecutive": 1}], th, sig)[0]["severity"] == "P1")

    # ---- 5. mutation checks: the data, not the test, drives the result --- #
    m1 = copy.deepcopy(sig)
    m1["paid_tier_markers"]["tiers"]["subscription_capped"]["name_suffixes"] = []
    check("mutation: dropping the :cloud suffix data flips ollama/minimax-m3:cloud off subscription",
          resolve_tier("ollama/minimax-m3:cloud", m1) != "subscription_capped")
    m2 = copy.deepcopy(sig)
    m2["paid_tier_markers"]["tiers"]["metered"]["providers"].remove("deepseek")
    check("mutation: dropping deepseek from metered flips deepseek direct off metered",
          resolve_tier("deepseek/deepseek-flash", m2) != "metered")
    m3 = copy.deepcopy(sig)
    m3["paid_tier_markers"]["tiers"]["subscription_capped"]["idle_burn_severity_max"] = "P1"
    check("mutation: raising the subscription ceiling makes it P1 (so the WARN clamp is real)",
          severity_for("subscription_capped", hi, 1, th, m3)[0] == "P1")
    m4 = copy.deepcopy(sig)
    m4["paid_tier_markers"]["normalize"]["router_prefix"] = ""
    check("mutation: dropping the 9router/ prefix data breaks routed ollama",
          resolve_tier("9router/ollama/minimax-m3", m4) != "subscription_capped")

    print("[paid-tier] %s (%d failed)" % ("PASS" if not FAILS else "FAIL", len(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
