"""AI MODELS: which AI builds the video and which AI checks the work — live binding.

Repair D01 (spec 7.1/7.3): the card answer is no longer a preference record.
bind_roles() stores the run's builder/QC role bindings in the run configuration
(``<run_dir>/model-bindings.json``), and every stage dispatch consumes them
through admit_dispatch()/record_attempt(), which verify the requested model,
the resolved provider model, the actual response model, the reasoning request
and the route, and record correlated request/router/response evidence. A label
or alias string is never proof of the model actually called.

Claude Sonnet is excluded from Skill 75 selectable, recommended and fallback
routes in both distributions (claude-nine/Claude Code and OpenClaw) and is
refused at catalog, alias, cache and fallback paths with an actionable
model-selection result. Other verified builder/QC choices stay configurable.
In OpenClaw the identifiers are the verified openrouter/ prefix ids
(``openclaw_id``); the direct OpenRouter request id is ``request_id`` (spec
7.1). A reasoning effort is only ever sent where the live catalog proves an
effort selector — never fabricated. ``build != check`` is enforced so the
checker stays independent.
"""
import hashlib
import json
import os
import re
from datetime import datetime, timezone

from capability_control.effort import ModelCaps, plan_request
from capability_control.failures import AccountBreaker

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_models.json"), encoding="utf-8") as _f:
    _T = json.load(_f)

MODELS = {m["id"]: m for m in _T["models"]}
REC_BUILD, REC_CHECK = _T["recommended"]["build"], _T["recommended"]["check"]
REC_RATIONALE = _T.get("recommended_rationale") or ""
EXCLUDED = tuple(_T.get("excluded_families") or ())
#: The run-configuration file bind_roles() writes and every dispatch reads.
STORE_NAME = "model-bindings.json"
STORE_SCHEMA = "blackceo.skill75.model-bindings/v1"
ROLE_BUILD, ROLE_CHECK, ROLE_REPAIR = "build", "check", "repair"
ROLES = (ROLE_BUILD, ROLE_CHECK, ROLE_REPAIR)
#: The two plain-language selection questions (spec 7.3).
BUILD_QUESTION = "Which available model should build and develop this?"
CHECK_QUESTION = "Which available model should check quality and fix problems?"
#: Evidence kinds that can prove which model actually answered. A label or
#: alias string is never proof (spec 7.1/7.2).
PROOF_KINDS = ("response_metadata", "router_receipt")
#: D30 typed codes at the dispatch boundary. These are capability-aware config
#: and account-failure outcomes, distinct from the model-selection codes above:
#: an unsupported capability claim is refused, never attempted or silently
#: stripped, and a failed account refuses queued launches instead of retrying.
CAPABILITY_UNSUPPORTED = "CAPABILITY_UNSUPPORTED"
ACCOUNT_FAILED = "ACCOUNT_FAILED"
#: One shared account breaker for the whole dispatch boundary (D30): one
#: actionable event per opening, queued launches suppressed while it is open.
ACCOUNT_BREAKER = AccountBreaker()
_PAT = re.compile(r"^\s*(.+?)\s+builds?\s*[,;]?\s*(?:and\s+)?(.+?)\s+checks?\s*\.?\s*$", re.I)
_BY_NAME = {}
_BANNED_WORDS = tuple(w for f in EXCLUDED for w in (f,))


def _key(s):
    return re.sub(r"[^a-z0-9.]+", " ", str(s).lower()).strip()


def _now(now=None):
    return now or datetime.now(timezone.utc).isoformat(timespec="seconds")


for _m in _T["models"]:
    for _n in [_m["id"], _m.get("request_id"), _m.get("openclaw_id"), _m["label"]] + _m["aliases"]:
        if _n and _key(_n) not in _BY_NAME:          # first registration wins; ids stay canonical
            _BY_NAME[_key(_n)] = _m["id"]


def _entry(mid):
    return MODELS[mid]


def banned_hits(text):
    """Excluded model-family names found in any string (catalog id, alias, cached
    entry, fallback member, response metadata). Sonnet-shaped tokens anywhere
    are refused at every path."""
    if not text:
        return []
    toks = set(re.split(r"[^a-z0-9]+", str(text).lower()))
    return [f for f in _BANNED_WORDS if any(t == f or t.startswith(f) for t in toks)]


def label(mid):
    return MODELS[mid]["label"]


def dispatch_id(model, runtime="claude-nine"):
    """The identifier a worker actually calls on this runtime: OpenClaw uses the
    verified openrouter/ prefix ids, direct OpenRouter requests use the bare
    request id, claude-nine/9Router uses the route its catalog advertises
    (spec 7.1). A label or alias is never a dispatch id."""
    m = _entry(model) if model in MODELS else MODELS[_BY_NAME[_key(model)]]
    if runtime == "openclaw":
        return m.get("openclaw_id") or m["id"]
    if runtime in ("openrouter-direct", "direct"):
        return m.get("request_id") or m["id"]
    return m["id"]


def _fact(map_, m):
    """The access/availability fact for an entry from any of its identifiers or
    its route; None when the runtime facts say nothing about it."""
    if not isinstance(map_, dict):
        return None
    for k in (m["id"], m.get("openclaw_id"), m.get("request_id"), m["route"]):
        if k in map_:
            return map_[k]
    return None


def _is_unavailable(availability, access, m):
    if _fact(access, m) is False:
        return True
    v = _fact(availability, m)
    if v is False or v == "unavailable":
        return True
    return isinstance(v, dict) and str(v.get("status", "")).lower() == "unavailable"


def selectable(access=None, needs=None, price_policy=None, availability=None):
    """Entries the user can actually pick, filtered by actual access, tool
    capabilities, modality needs, price policy and availability. An unavailable
    or inaccessible model is never shown as selectable."""
    out = []
    for m in _T["models"]:
        if banned_hits(m["id"]) or banned_hits(m["label"]) or any(banned_hits(a) for a in m["aliases"]):
            continue
        caps = set(m.get("capabilities") or []) | set(m.get("modalities") or [])
        if needs and not set(needs) <= caps:
            continue
        if price_policy in ("local", "local-only") and m.get("price_class") != "local":
            continue
        if _is_unavailable(availability, access, m):
            continue
        out.append(m)
    return out


def _selectable_rows(**filters):
    return [{"id": m["id"], "label": m["label"], "route": m["route"]} for m in selectable(**filters)]


def recommended():
    return {"build": REC_BUILD, "check": REC_CHECK, "route": MODELS[REC_BUILD]["route"]}


def recommended_text():
    return "%s builds, %s checks" % (label(REC_BUILD), label(REC_CHECK))


def _selection_result(requested, error_code, reason, who="build", next_action=None, **filters):
    """The actionable model-selection result every refusal carries: what was
    refused, why, what is still selectable, the recommended pair, and the exact
    next reply that works."""
    return {
        "ok": False,
        "error_code": error_code,
        "requested": requested,
        "role": who,
        "reason": reason,
        "selectable": _selectable_rows(**filters),
        "recommended": recommended(),
        "rationale": REC_RATIONALE,
        "next_action": next_action or ('Reply 1 for the recommended pair (%s), or name two '
                                       "different models like \"MiMo 2.6 Pro builds, GLM 5.3 checks\"."
                                       % recommended_text()),
    }


def _message(res, who):
    names = ", ".join(r["label"] for r in res["selectable"]) or "no model is currently available"
    return 'Sorry, I cannot use "%s" as the %s model. %s I can use: %s. %s' % (
        str(res["requested"]).strip(), who, res["reason"], names, res["next_action"])


def resolve(name, who="build", **filters):
    """A name/id/alias -> (model_id, None), or (None, actionable refusal).
    Excluded families are refused before any catalog lookup so they cannot
    arrive through an alias, a cache or a fallback name."""
    hits = banned_hits(name)
    if hits:
        return None, _selection_result(
            name, "MODEL_NOT_PERMITTED",
            "Claude Sonnet is excluded from Skill 75 model selection (selectable, recommended "
            "and fallback routes) in both distributions.", who, **filters)
    mid = _BY_NAME.get(_key(name)) if name else None
    if not mid:
        return None, _selection_result(
            name, "MODEL_UNKNOWN",
            "That model is not in the Skill 75 catalog.", who, **filters)
    if banned_hits(mid):
        return None, _selection_result(
            name, "MODEL_NOT_PERMITTED",
            "Claude Sonnet is excluded from Skill 75 model selection (selectable, recommended "
            "and fallback routes) in both distributions.", who, **filters)
    return mid, None


def check_result(build, checker, **filters):
    """The structured selection result for a build/check pair: accepted (with the
    canonical ids and route) or refused with the actionable model-selection
    result. Availability, access, capabilities, modality and price filters apply."""
    ids = []
    for who, name in ((ROLE_BUILD, build), (ROLE_CHECK, checker)):
        mid, err = resolve(name, who, **filters)
        if err:
            return err
        if mid not in {m["id"] for m in selectable(**filters)}:
            return _selection_result(
                name, "MODEL_UNAVAILABLE",
                "That model is not available on this box right now (missing route, no access "
                "or an unavailable endpoint), and an unavailable model is never selectable.",
                who, **filters)
        ids.append(mid)
    if ids[0] == ids[1]:
        return _selection_result(
            checker, "SAME_MODEL_ROLES",
            "The model that checks the work must be a different model from the one that builds it.",
            ROLE_CHECK, **filters)
    return {"ok": True, "build": ids[0], "check": ids[1], "route": MODELS[ids[0]]["route"],
            "pair": {"build": ids[0], "check": ids[1]}, "rationale": REC_RATIONALE, "message": None}


def check(build, checker):
    """Names or ids -> ({"build","check","route"}, None) or (None, actionable
    refusal text)."""
    res = check_result(build, checker)
    if not res["ok"]:
        return None, _message(res, res.get("role") or ROLE_BUILD)
    return {"build": res["build"], "check": res["check"], "route": res["route"]}, None


def parse(reply):
    """A card reply -> check()'s result. "1"/"recommended" takes the recommended
    pair; a pair is named like "MiMo 2.6 Pro builds, GLM 5.3 checks"."""
    t = (reply or "").strip()
    if t.lower() in ("recommended", "recommend", "rec", "1"):
        return recommended(), None
    m = _PAT.match(t)
    if not m:
        return None, 'Please reply 1, or name both models like "MiMo 2.6 Pro builds, GLM 5.3 checks".'
    return check(*m.groups())


def _recommended_pair(opts):
    """One recommended pair from selectable entries only: the catalog pair when
    both halves are selectable, otherwise the nearest selectable pair. Never the
    same model twice, never an unavailable model."""
    ids = [m["id"] for m in opts]
    if len(ids) < 2:
        return None
    build = REC_BUILD if REC_BUILD in ids else ids[0]
    check_id = REC_CHECK if REC_CHECK in ids and REC_CHECK != build else next(i for i in ids if i != build)
    return {"build": build, "check": check_id, "rationale": REC_RATIONALE}


def selection_questions(access=None, needs=None, price_policy=None, availability=None,
                        runtime="claude-nine"):
    """The two plain-language selection questions (spec 7.3) with one recommended
    pair, showing only what this box can actually run. Options carry the runtime's
    real dispatch identifiers: OpenClaw gets the verified openrouter/ prefix ids."""
    opts = selectable(access=access, needs=needs, price_policy=price_policy, availability=availability)
    pair = _recommended_pair(opts)

    def _rows():
        rows = []
        for m in opts:
            rows.append({"model_id": dispatch_id(m["id"], runtime), "id": m["id"],
                         "label": m["label"], "route": m["route"],
                         "reasoning": m.get("reasoning") or {}})
        return rows

    rows = _rows()

    def _q(qid, ask, who):
        ridx = next((i for i, r in enumerate(rows) if pair and r["id"] == pair[who]), None)
        return {"id": qid, "ask": ask,
                "why": ("One AI builds your video and a different AI checks the work."
                        if who == ROLE_BUILD else "The checker must be a different model from the builder."),
                "reason": REC_RATIONALE, "options": rows, "recommended": ridx}

    return {"questions": [_q("build_role", BUILD_QUESTION, ROLE_BUILD),
                          _q("check_role", CHECK_QUESTION, ROLE_CHECK)],
            "recommended_pair": pair,
            "selectable": rows,
            "runtime": runtime}


def card_question(**filters):
    """The intake-card models question (the intake_card._models_q seam): one
    recommended pair with a brief rationale and a free choice, built from the
    selectable catalog so no card surface can print an excluded model. The two
    selection questions above are what "Choose my own" opens."""
    pair = _recommended_pair(selectable(**filters))
    pair_text = ("I recommend %s because %s" % (recommended_text(), REC_RATIONALE)) if pair else \
        "No pair is available on this box right now."
    return {"id": "models", "label": "AI MODELS",
            "why": "One AI builds your video and a different AI checks the work.",
            "reason": REC_RATIONALE,
            "ask": "Which AI should build your video, and which should check the work?",
            "options": [("Recommended setup", pair_text),
                        ("Choose my own", "Reply with the build model and the check model, "
                         "e.g. \"MiMo 2.6 Pro builds, GLM 5.3 checks\".")],
            "recommended": 0}


# --- live role binding and dispatch admission -------------------------------

def _store_path(run_dir):
    return os.path.join(str(run_dir), STORE_NAME)


def _read_store(run_dir):
    p = _store_path(run_dir)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _write_store(run_dir, doc):
    os.makedirs(str(run_dir), exist_ok=True)
    p = _store_path(run_dir)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
    os.replace(tmp, p)
    return p


def _binding_row(mid, runtime, bound_by, at):
    m = MODELS[mid]
    return {"role_id": hashlib.sha256(json.dumps([mid, at], sort_keys=True).encode()).hexdigest()[:16],
            "model_id": mid, "request_id": m.get("request_id") or mid,
            "openclaw_id": m.get("openclaw_id") or mid, "route": m["route"],
            "reasoning": m.get("reasoning") or {}, "bound_at": at, "bound_by": bound_by,
            "dispatch": {"claude-nine": dispatch_id(mid, "claude-nine"),
                         "openclaw": dispatch_id(mid, "openclaw"),
                         "openrouter-direct": dispatch_id(mid, "openrouter-direct"),
                         "runtime": runtime, "call_id": dispatch_id(mid, runtime)}}


def bind_roles(run_dir, build, checker, *, runtime="claude-nine", bound_by="intake", now=None, **filters):
    """Store the run's builder/QC role bindings in the run configuration. This is
    the binding every stage dispatch consumes — not a preference record. Refused
    pairs (excluded family, unknown, unavailable, same model twice) bind nothing."""
    res = check_result(build, checker, **filters)
    if not res["ok"]:
        res["message"] = _message(res, res.get("role") or ROLE_BUILD)
        return res
    existing = _read_store(run_dir)
    if existing is not None:
        bindings = existing.get("bindings") or {}
        same_pair = all((bindings.get(role) or {}).get("model_id") == res[role]
                        for role in (ROLE_BUILD, ROLE_CHECK))
        if (existing.get("schema") == STORE_SCHEMA and same_pair
                and existing.get("runtime") == runtime):
            return {"ok": True, "binding_id": existing.get("binding_id"),
                    "bindings": bindings, "store": _store_path(run_dir),
                    "runtime": runtime, "reused": True, "message": None}
        return _selection_result(
            {"build": build, "check": checker, "runtime": runtime},
            "ROLE_BINDING_CONFLICT",
            "This run already has different model-role bindings. Existing bindings "
            "and attempts are preserved; an intake reply cannot replace them.")
    at = _now(now)
    doc = {"schema": STORE_SCHEMA, "runtime": runtime, "bound_at": at, "bound_by": bound_by,
           "bindings": {ROLE_BUILD: _binding_row(res["build"], runtime, bound_by, at),
                        ROLE_CHECK: _binding_row(res["check"], runtime, bound_by, at)},
           "attempts": []}
    doc["binding_id"] = hashlib.sha256(json.dumps(
        {"build": res["build"], "check": res["check"], "bound_at": at}, sort_keys=True).encode()).hexdigest()[:16]
    path = _write_store(run_dir, doc)
    return {"ok": True, "binding_id": doc["binding_id"], "bindings": doc["bindings"],
            "store": path, "runtime": runtime, "message": None}


def load_bindings(run_dir):
    """The run's stored role bindings, or None when the run never bound any."""
    return _read_store(run_dir)


def _reasoning_check(m, req):
    """Verify a reasoning request against the entry's honest policy. An effort the
    provider does not expose is refused — never fabricated, never silently dropped."""
    if req is None:
        return True, None, None
    if not isinstance(req, dict) or "effort" not in req:
        return False, "REASONING_NOT_SUPPORTED", "A reasoning request must name an effort."
    r = m.get("reasoning") or {}
    if not r.get("supported"):
        return False, "REASONING_NOT_SUPPORTED", "%s does not support a reasoning effort." % m["label"]
    if not r.get("effort_selector"):
        return False, "REASONING_NOT_SUPPORTED", (
            "%s supports reasoning but exposes no effort selector; sending an effort would "
            "fabricate provider support." % m["label"])
    if req["effort"] not in (r.get("efforts") or []):
        return False, "REASONING_NOT_SUPPORTED", "%s offers effort %s." % (
            m["label"], " or ".join(r.get("efforts") or []) or "none")
    return True, {"effort": req["effort"]}, "effort selector proven on the live provider catalog"


def _model_caps(m):
    """The catalog entry as capability_control's ModelCaps. The authoritative
    catalog decides; a UI ladder or an alias claim never adds support."""
    r = m.get("reasoning") or {}
    return ModelCaps(model_id=m["id"], reasoning=bool(r.get("supported")),
                     effort_selector=bool(r.get("effort_selector")),
                     tools="tool_use" in (m.get("capabilities") or []),
                     provider=m.get("route") or "")


def _capability_refusal(m, claim, role, requested):
    """Refuse a capability claim the authoritative catalog does not support.

    `claim` may name `needs` (capability/modality tokens) and `effort`. An
    unsupported token or effort is refused with CAPABILITY_UNSUPPORTED — never
    attempted and never silently stripped.
    """
    held = set(m.get("capabilities") or []) | set(m.get("modalities") or [])
    missing = [n for n in (claim.get("needs") or []) if n not in held]
    if missing:
        return _selection_result(
            requested, CAPABILITY_UNSUPPORTED,
            "%s does not expose %s; the claim is refused rather than attempted."
            % (m["label"], ", ".join(missing)), role,
            next_action="Drop the unsupported claim or pick a model that exposes %s."
                        % ", ".join(missing))
    effort = claim.get("effort")
    if effort:
        plan = plan_request(_model_caps(m), effort, required=True)
        if plan.refusal:
            return _selection_result(
                requested, CAPABILITY_UNSUPPORTED, "%s: %s" % (m["label"], plan.refusal), role,
                next_action="Send no effort for %s; its catalog entry exposes no effort selector."
                            % m["label"])
    return None


def _account_refusal(account, role, requested):
    """The typed outcome for a dispatch to an account the breaker has failed."""
    if not account or ACCOUNT_BREAKER.admit(account):
        return None
    ev = next((e for e in ACCOUNT_BREAKER.open_events() if e.account == account), None)
    return _selection_result(
        requested, ACCOUNT_FAILED,
        "Account %s is marked failed (%s); queued launches to it are suppressed."
        % (account, ev.kind if ev else "unknown"), role or ROLE_BUILD,
        next_action=(ev.action if ev else "Repair the account, then retry."))


def record_account_failure(account, envelope):
    """D30 at the dispatch boundary: normalize one account/provider failure.

    Returns the ONE actionable breaker event when this failure opens the
    breaker, and None when it is already open (no second event) or when the
    failure is only throttling / transient service error (no breaker opened).
    """
    return ACCOUNT_BREAKER.record_failure(account, envelope)


def admit_dispatch(run_dir, role, requested_model=None, *, route=None, reasoning_request=None,
                   fallbacks=None, cached_model=None, runtime=None,
                   capability_claim=None, account=None):
    """Dispatch admission: every stage dispatch consumes the run's stored role
    binding here before any worker is called. Refuses an unbound run, an excluded
    model arriving through any catalog/alias/cache/fallback name, a request that
    does not match the persisted binding, a wrong route, an unsupported
    capability claim (CAPABILITY_UNSUPPORTED), a dispatch to an account the
    shared breaker has failed (ACCOUNT_FAILED) and an unsupported reasoning
    request — each refusal an actionable, typed result."""
    failed = _account_refusal(account, role, requested_model)
    if failed:
        return failed
    doc = _read_store(run_dir)
    if not doc:
        return _selection_result(
            requested_model, "NO_ROLE_BINDING",
            "This run has no stored builder/QC role binding; every stage dispatch consumes "
            "the run's stored bindings (bind_roles first).", role or ROLE_BUILD)
    if role not in ROLES:
        return _selection_result(requested_model, "ROLE_UNKNOWN",
                                 'Unknown role "%s"; the roles are build, check and repair.' % role, ROLE_BUILD)
    # Repair is the existing QC choice, never a third model or intake question.
    binding_role = ROLE_CHECK if role == ROLE_REPAIR else role
    scan = [requested_model, cached_model, doc.get("bindings", {}).get(binding_role, {}).get("model_id")]
    scan += [str(f) for f in (fallbacks or [])]
    for s in scan:
        if banned_hits(s):
            return _selection_result(
                s, "MODEL_NOT_PERMITTED",
                "Claude Sonnet is excluded from Skill 75 selectable, recommended and fallback "
                "routes in both distributions.", role)
    binding = doc.get("bindings", {}).get(binding_role)
    if not binding:
        return _selection_result(requested_model, "NO_ROLE_BINDING",
                                 "This run has no stored binding for role %s." % role, role)
    mid = binding["model_id"]
    if requested_model:
        got, err = resolve(requested_model, role)
        if err:
            return err
        if got != mid:
            return _selection_result(
                requested_model, "MODEL_MISMATCH",
                "This run bound %s for role %s; a dispatch may not change the model."
                % (label(mid), role), role)
    if route and route != binding["route"]:
        return _selection_result(requested_model, "ROUTE_MISMATCH",
                                 "Role %s is bound to route %s, not %s." % (role, binding["route"], route), role)
    m = _entry(mid)
    if capability_claim:
        refused = _capability_refusal(m, capability_claim, role, requested_model or mid)
        if refused:
            return refused
    ok, verified_req, note = _reasoning_check(m, reasoning_request)
    if not ok:
        return {"ok": False, "error_code": "REASONING_NOT_SUPPORTED",
                "requested": requested_model or mid, "role": role, "reason": note,
                "selectable": _selectable_rows(), "recommended": recommended(),
                "rationale": REC_RATIONALE,
                "next_action": "Send only the reasoning settings this model exposes; see the "
                               "catalog's reasoning policy for %s." % m["label"], "message": note}
    return {"ok": True, "decision": "admit", "role": role, "binding_role": binding_role,
            "binding_id": doc.get("binding_id"), "binding": binding,
            "dispatch": dict(binding["dispatch"]),
            "reasoning_request": verified_req, "reasoning_verification": note,
            "message": None}


def record_attempt(run_dir, role, attempt_id, *, requested_model, resolved_provider_model,
                   response_model, route=None, reasoning_request=None, request_receipt=None,
                   router_receipt=None, response_evidence="response_metadata",
                   response_provider=None, fallbacks=None, cached_model=None,
                   runtime=None, now=None):
    """Verify and record one worker attempt against its persisted role binding:
    requested model, resolved provider model, actual response model, reasoning
    request and route, with correlated request/router/response evidence. The
    response model must come from provider response metadata or a router receipt
    in canonical-id form — a label or alias string is never proof of the model
    actually called."""
    adm = admit_dispatch(run_dir, role, requested_model, route=route,
                         reasoning_request=reasoning_request, fallbacks=fallbacks,
                         cached_model=cached_model, runtime=runtime)
    if not adm.get("ok"):
        return adm
    doc = _read_store(run_dir)
    if any(a.get("attempt_id") == attempt_id for a in doc.get("attempts") or []):
        return {"ok": False, "error_code": "ATTEMPT_EXISTS", "requested": attempt_id,
                "role": role, "reason": "Attempt %s is already recorded." % attempt_id,
                "selectable": _selectable_rows(), "recommended": recommended(),
                "rationale": REC_RATIONALE,
                "next_action": "Use a fresh attempt id per attempt.", "message": "attempt exists"}
    mid = adm["binding"]["model_id"]
    m = _entry(mid)
    canon = {_key(v) for v in (mid, m.get("request_id"), m.get("openclaw_id")) if v}
    if banned_hits(resolved_provider_model) or banned_hits(response_model):
        return _selection_result(response_model or resolved_provider_model, "MODEL_NOT_PERMITTED",
                                 "Claude Sonnet is excluded from Skill 75 routes in both "
                                 "distributions.", role)
    if m["route"] == "router-alias":
        return _selection_result(
            mid, "CHAIN_RESOLUTION_UNVERIFIED",
            "The literal router alias remains bound, but no supported correlated "
            "chain-member receipt reader has verified the resolved provider and "
            "response identity. No attempt is recorded as verified.", role,
            next_action="Keep the requested chain alias unchanged; provide supported "
                        "correlated router evidence before recording a verified attempt.")
    if _key(resolved_provider_model) not in canon:
        return _selection_result(resolved_provider_model, "RESOLVED_MISMATCH",
                                 "The resolved provider model does not match the model bound "
                                 "for role %s." % role, role)
    if response_evidence not in PROOF_KINDS:
        return _selection_result(response_model, "PROOF_NOT_IDENTITY",
                                 'Evidence kind "%s" cannot prove the model called; only provider '
                                 "response metadata or a router receipt can (a label or alias "
                                 "string is never proof)." % response_evidence, role)
    if _key(response_model) in {_key(v) for v in (m.get("label"),) + tuple(m.get("aliases") or ())}:
        return _selection_result(response_model, "PROOF_NOT_IDENTITY",
                                 "That is this model's label or alias, not its identity; a label "
                                 "or alias string is never proof of the model actually called.", role)
    if _key(response_model) not in canon:
        return _selection_result(response_model, "RESPONSE_MISMATCH",
                                 "The response model is not the model bound for role %s." % role, role)
    at = _now(now)
    row = {
        "attempt_id": attempt_id, "role": role, "recorded_at": at,
        "binding_id": doc.get("binding_id"),
        "binding": {"role_id": adm["binding"]["role_id"], "model_id": mid,
                    "bound_at": adm["binding"]["bound_at"], "bound_by": adm["binding"]["bound_by"]},
        "requested_model": requested_model,
        "resolved_provider_model": resolved_provider_model,
        "response_model": response_model,
        "response_provider": response_provider,
        "reasoning_request": adm.get("reasoning_request"),
        "reasoning_verification": adm.get("reasoning_verification"),
        "route": {"requested": route, "bound": adm["binding"]["route"]},
        "evidence": {"request_receipt": request_receipt, "router_receipt": router_receipt,
                     "response_evidence": response_evidence},
    }
    row["evidence"]["correlation"] = hashlib.sha256(json.dumps(
        {"binding_id": row["binding_id"], "role": role, "attempt_id": attempt_id,
         "requested": requested_model, "resolved": resolved_provider_model,
         "response": response_model, "request_receipt": request_receipt,
         "router_receipt": router_receipt}, sort_keys=True).encode()).hexdigest()
    doc.setdefault("attempts", []).append(row)
    path = _write_store(run_dir, doc)
    return {"ok": True, "attempt": row, "store": path, "message": None}
