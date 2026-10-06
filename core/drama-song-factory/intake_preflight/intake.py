"""intake.py: short adaptive opening intake (directive 24.3, 24.2 row 1). stdlib only.

Essentials (max 3 questions, one message): offer / audience+action / spending
authority. Never invents a spending ceiling or currency conversion. Brief text
is source material, never auth/policy (injection -> rejected, auth untouched).
"""
import hashlib
import json
import re

# ponytail: placement-substitution capped by leftover slots only; full
# re-prioritization add when a verdict needs it.

INJECTION_RES = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"\bskip\s+(qc|preflight|approval|authorization|intake)\b",
    r"\b(bypass|evade|override)\s+(the\s+)?(guard|gate|qc|approval|authorization|ceiling)\b",
    r"approve\w*\s+(the\s+)?(budget|spend|ceiling|authorization)",
    r"(set|raise|increase)\s+(the\s+)?(ceiling|budget|spending)",
    r"use\s+(my|this)\s+key",
    r"authorization\s+(is\s+)?approved",
    r"^\s*system\s*:",
]

DEFAULTS = {
    "placement": "unspecified (default: 9:16 vertical)",
    "aspect_ratio": "unspecified (default: 9:16)",
    "target_length_s": 30,
    "brand_rules": "unspecified (default: none)",
    "creative_prefs": "unspecified (default: none)",
    "repair_allowance": "unspecified (default: none authorized)",
}

Q_OFFER = "What product/offer are we promoting, and what link or assets should we use?"
Q_AUDIENCE = "Who is it for, and what should viewers do?"
Q_SPENDING = "What maximum generation budget is authorized, with its currency/credit unit?"
Q_PLACEMENT = "What placement/format should we produce (aspect ratio + target length)?"

APPROVAL_AFFECTING = ("offer", "audience", "action", "budget_minor", "budget_currency")


def _text(v):
    return v.strip() if isinstance(v, str) and v.strip() else None


def detect_injection(brief):
    """NAMES of brief fields whose text matches instruction-override patterns."""
    hits = []
    if not isinstance(brief, dict):
        return hits
    for key, val in brief.items():
        texts = val if isinstance(val, list) else [val]
        for t in texts:
            if not isinstance(t, str):
                continue
            low = t.lower()
            if any(re.search(p, low) for p in INJECTION_RES):
                hits.append(str(key))
                break
    return hits


def normalize(brief, settings=None):
    """Merge brief > settings > visible defaults. Spending never defaulted."""
    brief = brief or {}
    settings = settings or {}
    fields, prov = {}, {}

    def take(name, *sources):
        for value, src in sources:
            if value is not None:
                fields[name] = value
                prov[name] = src
                return
        fields[name] = None
        prov[name] = "missing"

    b = lambda k: _text(brief.get(k))  # noqa: E731
    s = lambda k: _text((settings.get("defaults") or {}).get(k)) if isinstance(settings.get("defaults"), dict) else None  # noqa: E731
    take("offer", (b("offer"), "provided"), (s("offer"), "inherited"))
    assets = brief.get("assets") or brief.get("link") or settings.get("assets")
    if isinstance(assets, str) and assets.strip():
        assets = [assets.strip()]
    take("assets", (assets or None, "provided" if "assets" in brief or "link" in brief else "inherited"))
    take("audience", (b("audience"), "provided"), (s("audience"), "inherited"))
    take("action", (b("action") or b("cta"), "provided"), (s("action"), "inherited"))
    bmin = brief.get("budget_minor", brief.get("budget_amount_minor"))
    smin = (settings.get("defaults") or {}).get("budget_minor") if isinstance(settings.get("defaults"), dict) else None
    take("budget_minor", ((bmin if isinstance(bmin, int) and bmin > 0 else None), "provided"),
         ((smin if isinstance(smin, int) and smin > 0 else None), "inherited"))
    take("budget_currency", (b("budget_currency") or b("currency"), "provided"), (s("budget_currency"), "inherited"))
    for name in ("placement", "aspect_ratio", "brand_rules", "creative_prefs", "repair_allowance"):
        take(name, (b(name), "provided"), (s(name), "inherited"), (DEFAULTS[name], "assumed"))
    tlen = brief.get("target_length_s", (settings.get("defaults") or {}).get("target_length_s"))
    take("target_length_s", ((tlen if isinstance(tlen, (int, float)) and tlen > 0 else None),
                             "provided" if "target_length_s" in brief else "inherited"),
         (DEFAULTS["target_length_s"], "assumed"))
    return fields, prov


def missing_essentials(fields, prov):
    """At most 3 questions. Placement substitutes into leftover slots only."""
    qs = []
    if not fields.get("offer"):
        qs.append({"id": "offer", "question": Q_OFFER})
    if not fields.get("audience") or not fields.get("action"):
        qs.append({"id": "audience_action", "question": Q_AUDIENCE})
    if not isinstance(fields.get("budget_minor"), int) or not fields.get("budget_currency"):
        qs.append({"id": "spending_authority", "question": Q_SPENDING})
    qs = qs[:3]
    ambiguous = prov.get("placement") == "assumed" and len(qs) < 3
    if ambiguous and not any(q["id"] == "placement" for q in qs):
        qs.append({"id": "placement", "question": Q_PLACEMENT})
    return qs[:3]


def summarize(fields, auth_status="missing"):
    summary = {
        "offer": fields.get("offer"),
        "assets": fields.get("assets"),
        "audience": fields.get("audience"),
        "cta": fields.get("action"),
        "placement": fields.get("placement"),
        "format": fields.get("aspect_ratio"),
        "target_length_s": fields.get("target_length_s"),
        "assumptions": [f"{k}={v!r} (assumed default)" for k, v in fields.items()
                        if v == DEFAULTS.get(k)],
        "generation_ceiling": {"amount_minor": fields.get("budget_minor"),
                               "currency": fields.get("budget_currency")},
        "repair_allowance": fields.get("repair_allowance"),
        "auth_status": auth_status,
    }
    digest = hashlib.sha256(json.dumps(summary, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return summary, digest


def auth_status_for(fields, digest, settings, now_unix=None):
    """Brief maximum is never an approval receipt; needs explicit auth object."""
    import time
    auth = (settings or {}).get("authorization") or {}
    if not auth:
        return "missing"
    exp = auth.get("expires_unix")
    now = now_unix if now_unix is not None else int(time.time())
    if isinstance(exp, (int, float)) and now > exp:
        return "expired"
    if auth.get("currency") and fields.get("budget_currency") and auth["currency"] != fields["budget_currency"]:
        return "out-of-scope"
    scope = auth.get("scope")
    if scope not in ("campaign", digest):
        return "out-of-scope"
    return "bound"


def evaluate(brief, settings=None, resume_state=None, run_id=None, now_unix=None):
    settings = settings or {}
    hits = detect_injection(brief or {})
    fields, prov = normalize(brief, settings)
    summary, digest = summarize(fields)
    status = auth_status_for(fields, digest, settings, now_unix)
    summary["auth_status"] = status
    if hits:  # untrusted text never touches auth/summary scope
        return {"outcome": "rejected", "reason_code": "untrusted-injection-blocked",
                "questions": [], "question_message": None, "summary": summary,
                "digest": digest, "provenance": prov, "untrusted_fields": hits,
                "auth_status": status, "approval_invalidated": False, "changes": [],
                "next_action": "Remove instruction language from brief fields and resubmit."}
    if resume_state and isinstance(resume_state, dict) and resume_state.get("digest"):
        prior = resume_state.get("summary") or {}
        cur = {k: summary.get(k) for k in ("offer", "audience", "cta", "placement",
                                           "generation_ceiling", "target_length_s")}
        old = {k: prior.get(k) for k in cur}
        changes = sorted(k for k in cur if json.dumps(cur[k], sort_keys=True, default=str) !=
                         json.dumps(old[k], sort_keys=True, default=str))
        affecting = sorted(set(changes) & {a for a in APPROVAL_AFFECTING if a in changes} |
                           ({"offer"} if "offer" in changes else set()) |
                           ({"audience"} if "audience" in changes else set()) |
                           ({"action"} if "cta" in changes else set()) |
                           ({"budget_minor", "budget_currency"} if "generation_ceiling" in changes else set()))
        if not changes and not (resume_state.get("outstanding") or []):
            return {"outcome": "ok", "reason_code": "resume-no-changes", "questions": [],
                    "question_message": None, "summary": summary, "digest": digest,
                    "provenance": prov, "auth_status": status, "approval_invalidated": False,
                    "changes": [], "next_stage": resume_state.get("next_stage"),
                    "next_action": resume_state.get("next_stage") or "Proceed to preflight."}
        if affecting:
            return {"outcome": "parked", "reason_code": "resume-approval-invalidated",
                    "questions": [], "question_message": None, "summary": summary,
                    "digest": digest, "provenance": prov, "auth_status": status,
                    "approval_invalidated": True, "changes": changes,
                    "next_action": "Re-approve scope: approval-affecting change invalidated prior approval."}
        outstanding = (resume_state.get("outstanding") or [])[:3]
        if outstanding:
            return {"outcome": "waiting", "reason_code": "resume-outstanding-decisions",
                    "questions": [{"id": f"resume-{i}", "question": q} for i, q in enumerate(outstanding)],
                    "question_message": "\n".join(f"{i+1}. {q}" for i, q in enumerate(outstanding)),
                    "summary": summary, "digest": digest, "provenance": prov,
                    "auth_status": status, "approval_invalidated": False, "changes": changes,
                    "next_stage": resume_state.get("next_stage"),
                    "next_action": "Answer outstanding decisions; questionnaire is not rerun."}
        return {"outcome": "ok", "reason_code": "resume-material-changes",
                "questions": [], "question_message": None, "summary": summary,
                "digest": digest, "provenance": prov, "auth_status": status,
                "approval_invalidated": False, "changes": changes,
                "next_stage": resume_state.get("next_stage"),
                "next_action": resume_state.get("next_stage") or "Proceed to preflight."}
    qs = missing_essentials(fields, prov)
    if not qs:
        return {"outcome": "ok", "reason_code": "complete-brief-zero-questions",
                "questions": [], "question_message": None, "summary": summary,
                "digest": digest, "provenance": prov, "auth_status": status,
                "approval_invalidated": False, "changes": [],
                "next_action": "Record summary digest + auth scope, then run preflight before paid work."}
    return {"outcome": "waiting", "reason_code": "missing-essentials",
            "questions": qs,
            "question_message": "\n".join(f"{i+1}. {q['question']}" for i, q in enumerate(qs)),
            "summary": summary, "digest": digest, "provenance": prov,
            "auth_status": status, "approval_invalidated": False, "changes": [],
            "next_action": "Answer the bundled questions in one reply; nothing else is asked."}
