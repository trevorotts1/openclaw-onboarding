"""Launch step compiler (U-skill44-04: S44-05, S44-09, S44-11).

Turns ONE launch-c build entry (plus the buildable template its automation names)
into a provider workflow definition that carries real sms / if_else / goal steps,
a trigger that is either sandbox-verified or BLOCKED, a stop-on-purchase goal on a
purchase tag the post-sale automation sets, and date-anchored sends gated by an
explicit "wait until date" step that is recorded as a managed-browser ledger step.

Never calls a provider, never sends, never publishes: every result is draft-only
and fails closed.  A blocked result carries NO workflows, only ``blocked_by``
reasons and the browser ledger rows an operator must still perform.

    result = compile_build(build, purchase_tag_set=True)
    doc = compile_launch_document(automation_build_document)
    findings = verify_readback(workflow_def, exported_templates)   # WF-9 / QC read-back
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional

from cli_anything.gohighlevel.utils.workflow_builder import (
    GUARD_PURCHASE,
    VERIFIED_ACTIONS,
    compile_guard_conditions,
    compile_trigger_conditions,
    sms_step,
    tag_step,
    wait_step,
)

# ── Trigger registry ─────────────────────────────────────────────────────────
# Only payloads CampaignBuilder already writes and a sandbox has accepted.  Every
# other trigger type is blocked (never defaulted to Tag Added); its trigger is a
# named managed-browser step in the run ledger.
# ponytail: add a type here ONLY with a sandbox-verified patch-trigger payload.
VERIFIED_TRIGGER_TYPES = {
    "tag_added": "contact_tag",
    "contact_tag": "contact_tag",
    # Calendar launches start from the opt-in tag and are gated by wait-until
    # steps; that is only real when an absolute schedule node exists (checked below).
    "launch_calendar": "contact_tag",
}

# Family -> default template key when the plan says template "new".
FAMILY_TEMPLATE = {
    "pre_launch": "launch-a/launch-a-prelaunch-window",
    "opt_in": "launch-a/launch-optin-register-login",
    "post_sale": "launch-b/launch-post-sale-purchase",
    "upsell_downsell": "launch-b/upsell-downsell-branch",
    "abandoned_checkout": "launch-b/abandoned-checkout-recovery",
    "page_retargeting": "launch-b/launch-b-retarget-visited-sales-no-checkout",
    "onboarding_review": "launch-c/launch-c-onboarding-first-hour-day-week",
    "win_back": "launch-c/launch-win-back-closed-no-purchase",
    "failed_payment": "launch-c/failed-payment-recovery",
    "conversation_ai_reply": "launch-ai/customer-replied-conversation-ai",
}
PROMO_FAMILIES = {"pre_launch", "opt_in", "upsell_downsell", "abandoned_checkout",
                  "page_retargeting", "win_back"}

# Must equal launch-c/plan_reader.DEFAULT_LIFECYCLE (a test asserts parity).  A
# lifecycle that is exactly this contract default, with no build-plan provenance,
# was synthesized by the reader, not authored by Skill 50: treated as absent.
CONTRACT_DEFAULT_LIFECYCLE = {
    "stop_rules": [
        {"rule": "stop_on_verified_purchase", "scope": "this_campaign_only"},
        {"rule": "stop_on_unsubscribe", "scope": "this_campaign_only"},
        {"rule": "stop_on_offer_version_superseded", "scope": "this_campaign_only"},
    ],
    "suppression_rules": [
        {"rule": "suppress_promotion_after_verified_purchase",
         "event": "purchase_verified", "applies_to": "all_remaining_email_steps",
         "scope": "this_campaign"},
        {"rule": "recheck_eligibility_immediately_before_send",
         "applies_to": "each_scheduled_email_step",
         "checks": ["verified_purchase", "unsubscribe", "offer_version_current"]},
    ],
}
REQUIRED_STOPS = ("stop_on_unsubscribe", "stop_on_verified_purchase")
REQUIRED_SUPPRESSIONS = ("suppress_promotion_after_verified_purchase",
                         "recheck_eligibility_immediately_before_send")

TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_./-]*$")
TOKEN_RE = re.compile(r"<([A-Za-z0-9_-]+)>|\[([A-Za-z0-9_-]+)\]")
LEFTOVER_RE = re.compile(r"<[^>]*>|\[[^\]]*\]|\{\{[^}]*\}\}")
DURATION_RE = re.compile(r"^(\d+)\s*(minute|hour|day|week)s?$")


def purchase_tag(launch_id: str) -> str:
    """The tag the post-sale automation sets on a verified purchase."""
    return "launch-buyer-%s" % launch_id


def _templates_root() -> Path:
    return Path(__file__).resolve().parents[5] / "automation-templates"


# ── Template resolution (buildable spec) ─────────────────────────────────────
def resolve_template(build: Mapping[str, Any], *, root: Optional[Path] = None,
                     manifest: Optional[Mapping[str, Any]] = None) -> tuple:
    """Return ``(spec, key, reason)``; spec is a template doc with a build_graph."""
    root = Path(root) if root else _templates_root()
    if manifest is None:
        try:
            rows = json.loads((root / "_matcher" / "buildable-templates.json")
                              .read_text(encoding="utf-8")).get("templates", [])
        except (OSError, ValueError):
            rows = []
        manifest = {r["key"]: r for r in rows if isinstance(r, dict) and r.get("key")}
    template = str(build.get("template") or "").strip()
    family = build.get("family")
    key = None
    if template in manifest:
        key = template
    elif template and template != "new":
        hits = [k for k in manifest if k.split("/")[-1] == template]
        key = hits[0] if len(hits) == 1 else None
        if key is None:
            return None, None, "template_unresolved:%s" % template
    else:
        key = FAMILY_TEMPLATE.get(family)
        if key is None:
            return None, None, "template_unresolved:%s" % family
    row = manifest.get(key)
    if row is None:
        return None, key, "template_unbuildable:%s" % key
    try:
        spec = json.loads((root / row["path"]).read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError):
        return None, key, "template_unreadable:%s" % key
    graph = spec.get("build_graph") if isinstance(spec, dict) else None
    if not isinstance(graph, list) or not graph:
        return None, key, "template_unbuildable:%s" % key
    return spec, key, None


# ── small helpers ────────────────────────────────────────────────────────────
def _preds(node: Mapping[str, Any]) -> list:
    after = node.get("after")
    return [] if after is None else [after] if isinstance(after, str) else list(after)


def _subst(text: str, bindings: Mapping[str, Any]) -> str:
    def repl(m):
        name = (m.group(1) or m.group(2)).replace("-", "_")
        value = bindings.get(name)
        return str(value) if isinstance(value, (str, int)) else m.group(0)
    return TOKEN_RE.sub(repl, text)


def _resolve_tags(raw: Any, bindings: Mapping[str, Any]) -> Optional[list]:
    out = []
    for item in raw if isinstance(raw, list) else [raw]:
        if not isinstance(item, str):
            return None
        value = bindings.get(item)
        value = _subst(item, bindings) if value is None else value
        for tag in value if isinstance(value, list) else [value]:
            if not isinstance(tag, str) or not TAG_RE.match(tag):
                return None
            out.append(tag)
    return out


def _tag_condition(tag: str) -> dict:
    # ponytail: shape mirrors the verified trigger select operator; confirm the
    # if/else contact-tag payload in a sandbox before widening beyond tag checks.
    return {"id": "has-tag", "type": "contact_tag", "field": "tags",
            "operator": "index-of-true", "value": tag, "title": "Has tag %s" % tag}


def _parse_condition(text: str, bindings: Mapping[str, Any]) -> Optional[dict]:
    m = (re.fullmatch(r"(?:contact has )?tag `([^`]+)`(?: present)?", text)
         or re.fullmatch(r"`([^`]+)` present", text)
         or re.fullmatch(r"([a-z0-9][a-z0-9_:.<>\[\]]*-[a-z0-9_:.\-<>\[\]]*) present", text))
    if not m:
        return None
    tags = _resolve_tags(m.group(1), bindings)
    return _tag_condition(tags[0]) if tags and len(tags) == 1 else None


def _referrers(steps: list, target: str, skip: Optional[str] = None) -> list:
    return [s for s in steps if s["id"] != skip and (
        s.get("next") == target or target in (s.get("branches") or {}).values())]


def _retarget(steps: list, old: str, new: str, skip: Optional[str] = None) -> None:
    for s in steps:
        if s["id"] == skip:
            continue
        if s.get("next") == old:
            s["next"] = new
        branches = s.get("branches")
        if branches:
            s["branches"] = {k: (new if v == old else v) for k, v in branches.items()}


def _lifecycle_blockers(build: Mapping[str, Any]) -> list:
    lifecycle = build.get("lifecycle")
    bid = build.get("id")
    if not isinstance(lifecycle, Mapping) or not lifecycle:
        return ["guards:%s:lifecycle_absent" % bid]
    if lifecycle == CONTRACT_DEFAULT_LIFECYCLE and build.get("lifecycle_source") != "build_plan":
        return ["guards:%s:lifecycle_not_authored" % bid]
    names = lambda key: {r.get("rule") for r in lifecycle.get(key) or [] if isinstance(r, Mapping)}  # noqa: E731
    missing = [r for r in REQUIRED_STOPS if r not in names("stop_rules")]
    missing += [r for r in REQUIRED_SUPPRESSIONS if r not in names("suppression_rules")]
    return ["guards:%s:%s" % (bid, ",".join(missing))] if missing else []


def _ledger(out: dict, action: str, **fields: Any) -> dict:
    row = {"kind": "managed_browser_step", "action": action, "unit_key": out["unit_key"],
           "status": "pending", **fields}
    row["ledger_id"] = "%s#%s#%s" % (out["unit_key"], action, fields.get("step_id") or len(out["browser_steps"]))
    out["browser_steps"].append(row)
    return row


def _until_step(step_id: str, at: str, tz: Optional[str], ledger_id: str) -> dict:
    name = "Wait until %s" % at
    return {"id": step_id, "type": "wait", "name": name, "rail": "managed_browser",
            "attributes": {"type": "until_date", "untilDate": at, "timezone": tz,
                           "name": name, "isHybridAction": True, "hybridActionType": "wait",
                           "rail": "managed_browser", "ledger_id": ledger_id}}


def _single_wait_chain(steps: list, eid: str) -> list:
    """Waits that run directly before step ``eid`` (nearest first), if linear."""
    chain, cur = [], eid
    while True:
        refs = _referrers(steps, cur)
        if len(refs) != 1 or refs[0].get("type") != "wait" or refs[0].get("branches"):
            return chain
        chain.append(refs[0])
        cur = refs[0]["id"]


# ── the compiler ─────────────────────────────────────────────────────────────
def compile_build(build: Mapping[str, Any], *, bindings: Optional[Mapping[str, Any]] = None,
                  purchase_tag_set: bool = False, root: Optional[Path] = None,
                  manifest: Optional[Mapping[str, Any]] = None,
                  allow_browser_steps: bool = True) -> dict:
    """Compile one build.  ``status`` is ``ok`` or ``blocked``; blocked has no workflows."""
    bid = str(build.get("id"))
    unit_key = build.get("unit_key") or bid
    launch_id = unit_key.split("/")[0] if "/" in unit_key else None
    family = build.get("family")
    out: dict[str, Any] = {"id": bid, "unit_key": unit_key, "family": family, "status": "blocked",
                           "blocked_by": [], "template": None, "trigger": None,
                           "workflows": {}, "browser_steps": []}
    blocked = out["blocked_by"]
    bindings = dict(bindings or {})

    if build.get("draft_only") is not True:
        blocked.append("not_draft")
    if build.get("state") != "ready" or build.get("blocked_by"):
        blocked.extend(build.get("blocked_by") or ["state:%s" % build.get("state")])

    schedule = build.get("schedule") or {}
    seqs = schedule.get("sequences") or {}
    promo = family in PROMO_FAMILIES or any(s.get("promotional") for s in seqs.values())
    if promo:
        blocked.extend(_lifecycle_blockers(build))
        if not purchase_tag_set:
            blocked.append("purchase_tag_unset")
    ptag = purchase_tag(launch_id) if launch_id else None
    if ptag is None:
        blocked.append("purchase_tag_unset:no_launch_id")
    else:
        bindings.setdefault("launch buyer tag", [ptag])

    workflows = [w for w in build.get("workflows") or [] if isinstance(w, Mapping)]
    emails = [s for w in workflows for s in w.get("steps") or []
              if isinstance(s, Mapping) and s.get("type") == "email"]
    sched = {n.get("step_id"): n for n in schedule.get("nodes") or []
             if isinstance(n, Mapping) and n.get("step_id")}
    absolute = [n for n in sched.values() if n.get("kind") == "absolute" and n.get("at")]
    tz = schedule.get("timezone")
    close_at = next((s.get("close_at") for s in seqs.values() if s.get("promotional")), None)

    # Template -> buildable spec.
    spec, key, reason = resolve_template(build, root=root, manifest=manifest)
    out["template"] = key
    if reason:
        blocked.append(reason)

    # Trigger: verified payload or blocked (never a Tag Added default).
    trig = build.get("trigger") if isinstance(build.get("trigger"), Mapping) else {}
    ttype = str(trig.get("type") or "")
    event = next((n.get("attributes", {}).get("event") for n in (spec or {}).get("build_graph", [])
                  if n.get("type") == "trigger"), None)
    tag = next((w.get("tag") for w in workflows if w.get("tag")), None)
    if VERIFIED_TRIGGER_TYPES.get(ttype) == "contact_tag":
        if ttype == "launch_calendar" and not absolute:
            blocked.append("trigger_unverified:launch_calendar:no_absolute_schedule")
        elif not tag:
            blocked.append("trigger_tag_missing:%s" % ttype)
        else:
            out["trigger"] = {"type": "contact_tag", "status": "draft", "rail": "api",
                              "conditions": compile_trigger_conditions(tag, build.get("eligibility") or [])}
    else:
        blocked.append("trigger_unverified:%s" % (ttype or "missing"))
        _ledger(out, "set_trigger", trigger_type=ttype, ghl_trigger=event)

    steps: list = []
    if spec is not None:
        steps = _compile_graph(out, spec["build_graph"], bid, emails, bindings, promo,
                               close_at, ptag, family)
    if steps and not blocked:
        until_dates = {"%s_at" % n["phase"]: n["at"] for n in schedule.get("calendar_nodes") or []
                       if isinstance(n, Mapping) and n.get("phase") and n.get("at")}
        until_dates.update(bindings.get("until") or {})
        steps = _apply_absolute(out, steps, sched, until_dates, tz, allow_browser_steps)
    if steps and not out["blocked_by"] and promo:
        _apply_purchase_gate(steps, bid, ptag)
    if family == "post_sale" and steps and not any(
            s["type"] == "add_contact_tag" and ptag in s["attributes"].get("tags", []) for s in steps):
        blocked.append("purchase_tag_not_set:%s" % bid)

    if blocked:
        return out
    wf_key = "%s__flow" % bid
    out["workflows"][wf_key] = {
        "name": (workflows[0].get("name") if workflows else None) or (spec or {}).get("name") or bid,
        "tag": tag, "status": "draft", "templates": steps, "unit_key": "%s/flow" % unit_key,
        "source_unit": bid, "phase": family, "promotional": promo, "close_at": close_at,
        "purchase_tag": ptag, "trigger": out["trigger"], "requires_browser": bool(out["browser_steps"]),
        "browser_steps": list(out["browser_steps"]),
        "expected_source_hash": build.get("expected_graph_hash"),
    }
    out["status"] = "ok"
    return out


def _compile_graph(out, graph, bid, emails, bindings, promo, close_at, ptag, family) -> list:
    blocked = out["blocked_by"]
    nodes = [n for n in graph if isinstance(n, Mapping) and n.get("type") != "trigger"]
    idmap = {n["id"]: "%s-%s" % (bid, n["id"]) for n in nodes}
    kids = {n["id"]: [] for n in nodes}
    for n in nodes:
        for p in _preds(n):
            if p in kids:
                kids[p].append(n["id"])
    # Template email nodes take the bound Skill 50 emails in order (verbatim copy).
    pool = list(emails)
    source = {}
    for n in nodes:
        if n.get("type") == "email":
            if pool:
                source[n["id"]] = pool.pop(0)
                idmap[n["id"]] = source[n["id"]]["id"]
            else:
                blocked.append("email_copy_missing:%s" % n["id"])
    pairs = []
    for n in nodes:
        nid, ntype, a = n["id"], n.get("type"), n.get("attributes") or {}
        sid = idmap[nid]
        if ntype not in VERIFIED_ACTIONS:
            blocked.append("unverified_action:%s:%s" % (nid, ntype))
            continue
        if ntype == "email":
            src = source.get(nid)
            if src is None:
                continue
            attrs = dict(src.get("attributes") or {})
            conds = [c for c in compile_guard_conditions(promotional=promo, close_at=close_at)
                     if c["id"] != GUARD_PURCHASE]  # purchase stop is a real tag gate, not this synthetic field
            known = {c.get("id") for c in attrs.get("conditions") or [] if isinstance(c, Mapping)}
            attrs["conditions"] = list(attrs.get("conditions") or []) + [c for c in conds if c["id"] not in known]
            attrs["marketing"] = promo
            step = {k: v for k, v in src.items() if k != "attributes"}
            step["attributes"] = attrs
        elif ntype == "sms":
            # The template's `message` is a DIRECTIVE ("confirm + calendar"),
            # not approved copy.  It never enters the real body: a placeholder
            # sitting in `body` is one downstream read away from shipping as
            # if it were the SMS text.  Only `body_ref` carries it, and the
            # action stays copy_pending until an approved body is supplied.
            ref = str(a.get("message") or a.get("ref") or nid)
            step = sms_step(ref, "", id=sid)
            step["attributes"].update({"body_ref": ref, "copy_pending": True})
        elif ntype == "wait":
            if a.get("kind") == "until":
                step = {"id": sid, "type": "wait", "name": "Wait until %s" % a.get("until"),
                        "attributes": {"type": "until_date", "untilDate": None, "template_until": a.get("until")}}
            else:
                m = DURATION_RE.match(str(a.get("duration") or ""))
                if not m:
                    blocked.append("wait_unparseable:%s" % nid)
                    continue
                value, unit = int(m.group(1)), m.group(2)
                value, unit = (value * 7, "day") if unit == "week" else (value, unit)
                step = wait_step("", value, {"minute": "minutes", "hour": "hours", "day": "days"}[unit], id=sid)
        elif ntype in ("add_contact_tag", "remove_contact_tag"):
            tags = _resolve_tags(a.get("tags") or a.get("tags_removed") or a.get("tag"), bindings)
            if not tags:
                blocked.append("tag_unresolved:%s" % nid)
                continue
            step = tag_step(str(a.get("ref") or nid), tags, remove=ntype == "remove_contact_tag", id=sid)
        elif ntype == "if_else":
            text = str(a.get("condition") or "")
            cond = _parse_condition(text, bindings)
            step = {"id": sid, "type": "if_else", "name": "If/Else: %s" % text,
                    "attributes": {"condition_text": text, "conditions": [cond] if cond else []}}
            if not cond:
                _ledger(out, "configure_if_else_condition", step_id=sid, condition_text=text)
        elif ntype == "workflow_goal":
            step = {"id": sid, "type": "workflow_goal", "name": "Goal: %s" % a.get("goal"),
                    "attributes": {"goal": a.get("goal")}}
        else:  # any other VERIFIED action type passes through unchanged
            step = {"id": sid, "type": ntype, "name": str(a.get("ref") or nid),
                    "attributes": {k: v for k, v in a.items() if k != "ref"}}
        parents = [idmap[p] for p in _preds(n) if p in idmap]
        step["parentKey"] = parents[0] if parents else None
        if ntype == "if_else" and isinstance(n.get("branches"), Mapping):
            step["branches"] = {k: idmap.get(v, v) for k, v in n["branches"].items()}
        pairs.append((n, step))
    for n, step in pairs:
        if step.get("branches") is not None:
            continue
        succ = kids[n["id"]]
        if len(succ) > 1:
            blocked.append("graph_fanout:%s" % n["id"])
        step["next"] = idmap[succ[0]] if succ else None
    return [step for _n, step in pairs]


def _apply_absolute(out, steps, sched, until_dates, tz, allow_browser_steps) -> list:
    """Gate every date-anchored send by a ledgered wait-until-date step."""
    blocked = out["blocked_by"]
    for eid in [s["id"] for s in steps if s["type"] == "email"]:
        node = sched.get(eid)
        if not node or node.get("kind") != "absolute" or not node.get("at"):
            continue
        if not allow_browser_steps:
            blocked.append("absolute_wait_unsupported:%s" % eid)
            continue
        at = node["at"]
        row = _ledger(out, "wait_until_date", step_id=eid, at=at, timezone=tz)
        chain = _single_wait_chain(steps, eid)
        if chain:
            keep = chain[0]  # nearest wait becomes the until step; earlier waits are subsumed
            for extra in chain[1:]:
                _retarget(steps, extra["id"], keep["id"], skip=extra["id"])
                steps.remove(extra)
            new = _until_step(keep["id"], at, tz, row["ledger_id"])
            new.update(next=keep.get("next"), parentKey=chain[-1].get("parentKey"))
            keep.clear()
            keep.update(new)
            row["wait_step_id"] = keep["id"]
        else:
            uid = "%s-until" % eid
            refs = _referrers(steps, eid)
            new = _until_step(uid, at, tz, row["ledger_id"])
            new.update(next=eid, parentKey=refs[0]["id"] if refs else None)
            _retarget(steps, eid, uid)
            target = next(s for s in steps if s["id"] == eid)
            target["parentKey"] = uid
            steps.insert(steps.index(target), new)
            row["wait_step_id"] = uid
    for s in steps:  # template "until" waits the sends did not claim: resolve by token or block
        if s["type"] != "wait" or s["attributes"].get("type") != "until_date" or s["attributes"].get("untilDate"):
            continue
        token = re.sub(r"[{}\s]", "", str(s["attributes"].get("template_until") or ""))
        at = until_dates.get(token)
        if not at or not allow_browser_steps:
            blocked.append("absolute_wait_unsupported:%s" % s["id"])
            continue
        row = _ledger(out, "wait_until_date", step_id=s["id"], at=at, timezone=tz, wait_step_id=s["id"])
        new = _until_step(s["id"], at, tz, row["ledger_id"])
        new.update(next=s.get("next"), parentKey=s.get("parentKey"))
        s.clear()
        s.update(new)
    return steps


def _apply_purchase_gate(steps: list, bid: str, ptag: str) -> None:
    """Real stop-on-purchase: an if/else on the purchase tag before every send,
    routed to one goal node on that tag (post-sale sets the tag)."""
    sends = [s for s in steps if s["type"] in ("email", "sms")]
    if not sends:
        return
    goal_id = "%s-goal-purchased" % bid
    for send in sends:
        gate_id = "%s-purchase-gate" % send["id"]
        refs = _referrers(steps, send["id"])
        gate = {"id": gate_id, "type": "if_else", "name": "Purchased? stop",
                "attributes": {"condition_text": "contact has tag `%s`" % ptag,
                               "conditions": [_tag_condition(ptag)], "purchase_tag": ptag},
                "parentKey": refs[0]["id"] if refs else send["parentKey"],
                "branches": {"true": goal_id, "false": send["id"]}}
        _retarget(steps, send["id"], gate_id)
        send["parentKey"] = gate_id
        steps.insert(steps.index(send), gate)
    steps.append({"id": goal_id, "type": "workflow_goal", "name": "Goal: purchased",
                  "attributes": {"goal": "purchased", "goalType": "contact_tag", "tag": ptag,
                                 "scope": "this_campaign_only"},
                  "parentKey": sends[-1]["id"], "next": None})


# ── one bound workflow -> installable provider steps (canonical entry) ───────
#
# The CLI build path (workflow_builder.compile_automation_build) and the
# document compiler below both compile through the functions in this module.
# ``compile_installable`` is the entry the production command uses, so the
# expanded compiler is no longer bypassed by the real execution path.
PURCHASE_IDENTITY_FIELDS = ("event_id", "transaction_id", "purchased_line_id")


def purchase_identity(build: Mapping[str, Any]) -> dict:
    """The identity a purchase handler deduplicates on, or an explicit unknown.

    One native order can carry several paid changes (the main order plus an
    upsell), so an order id alone never proves two deliveries are the same
    purchase.  Only an event / transaction / purchased-line identity is
    sufficient; anything less is recorded as insufficient rather than
    normalised into a usable key.
    """
    observed = build.get("purchase_identity")
    if not isinstance(observed, Mapping):
        return {"basis": None, "value": None, "dedupe_key": None,
                "sufficient": False, "reason": "no purchase-event identity declared"}
    for field in PURCHASE_IDENTITY_FIELDS:
        value = observed.get(field)
        if isinstance(value, str) and value.strip():
            return {"basis": field, "value": value,
                    "dedupe_key": "%s:%s" % (field, value), "sufficient": True,
                    "reason": None}
    order_id = observed.get("order_id")
    return {
        "basis": "order_id" if order_id else None,
        "value": str(order_id) if order_id else None,
        "dedupe_key": None,
        "sufficient": False,
        "reason": ("an order id alone cannot deduplicate a purchase: one order "
                   "can carry several paid changes") if order_id
                  else "no purchase-event identity declared",
    }


def _unresolved_until(graph: list, until_dates: Mapping[str, Any]) -> Optional[str]:
    """The first template ``wait until`` token this build cannot resolve."""
    for node in graph:
        if not isinstance(node, Mapping) or node.get("type") != "wait":
            continue
        attrs = node.get("attributes") or {}
        if attrs.get("kind") != "until":
            continue
        token = re.sub(r"[{}\s]", "", str(attrs.get("until") or ""))
        if token not in until_dates:
            return token or "(empty)"
    return None


def compile_installable(workflow: Mapping[str, Any], build: Mapping[str, Any], *,
                        seq_schedule: Optional[Mapping[str, Any]] = None,
                        promotional: bool = True,
                        close_at: Optional[str] = None,
                        bindings: Optional[Mapping[str, Any]] = None,
                        purchase_tag_set: bool = False,
                        root: Optional[Path] = None,
                        manifest: Optional[Mapping[str, Any]] = None,
                        allow_browser_steps: bool = True) -> dict:
    """Compile ONE bound Skill 50 workflow into installable provider steps.

    Two supported shapes, and the chosen one is always recorded:

    ``template_graph``
        The build's buildable template resolves, every ``wait until`` token
        binds to a real calendar/binding date, and every email slot has
        approved copy: the template's tags, branches, waits, SMS and goal
        nodes are installed.
    ``bound_sequence``
        Otherwise the approved Skill 50 email/wait sequence is installed with
        its guards, its absolute-wait ledger rows and the real purchase gate.

    An unresolved template is a recorded note, never a silent substitution.
    Copy that no approved source supplies stays ``copy_pending`` and the
    channel action is reported incomplete; it never blocks the email work.
    """
    from cli_anything.gohighlevel.utils.workflow_builder import (
        _guarded_templates,
        link_steps,
    )

    bindings = dict(bindings or {})
    bid = str(build.get("id"))
    unit_key = build.get("unit_key") or bid
    launch_id = unit_key.split("/")[0] if "/" in unit_key else None
    ptag = purchase_tag(launch_id) if launch_id else None
    if ptag:
        bindings.setdefault("launch buyer tag", [ptag])

    seq_schedule = seq_schedule or {}
    schedule = build.get("schedule") or {}
    tz = schedule.get("timezone")
    out: dict[str, Any] = {
        "id": bid, "unit_key": unit_key, "status": "ok", "blocked_by": [],
        "browser_steps": [], "notes": [], "steps": [],
        "compile_mode": "bound_sequence", "template": None,
        "channel_actions": {}, "incomplete_actions": [],
        "purchase_identity": purchase_identity(build),
    }
    blocked = out["blocked_by"]

    steps = _guarded_templates(
        workflow.get("steps") or [], promotional=promotional,
        close_at=close_at,
        schedule_by_id={node.get("step_id"): node
                        for node in seq_schedule.get("nodes") or []
                        if isinstance(node, Mapping) and node.get("step_id")})

    until_dates = {"%s_at" % node["phase"]: node["at"]
                   for node in schedule.get("calendar_nodes") or []
                   if isinstance(node, Mapping) and node.get("phase") and node.get("at")}
    until_dates.update(bindings.get("until") or {})

    # Template expansion: only when the whole short handler resolves.  A long
    # nurture/wait graph whose date tokens are not on this build stays on the
    # approved sequence, and says so.
    spec, key, reason = resolve_template(build, root=root, manifest=manifest)
    out["template"] = key
    emails = [step for step in workflow.get("steps") or []
              if isinstance(step, Mapping) and step.get("type") == "email"]
    if spec is None:
        out["notes"].append("template_graph_skipped:%s" % (reason or "unresolved"))
    elif not emails:
        out["notes"].append("template_graph_skipped:no_email_copy")
    else:
        token = _unresolved_until(spec.get("build_graph") or [], until_dates)
        if token:
            out["notes"].append("template_graph_skipped:unresolved_until:%s" % token)
        else:
            trial = {"unit_key": unit_key, "blocked_by": [], "browser_steps": []}
            graph_steps = _compile_graph(trial, spec["build_graph"], bid, emails,
                                         bindings, promotional, close_at, ptag,
                                         build.get("family"))
            if trial["blocked_by"] or not graph_steps:
                out["notes"].append("template_graph_skipped:" + ",".join(
                    trial["blocked_by"] or ["empty_graph"]))
            else:
                steps = graph_steps
                out["browser_steps"] = trial["browser_steps"]
                out["compile_mode"] = "template_graph"

    # Trigger: the automation's OWN declared trigger decides.  A contact-tag
    # trigger is installed only when that is the approved trigger type; any
    # other approved trigger (Order Submitted / Payment Received, checkout
    # abandoned, ...) has no verified create payload here, so it is recorded
    # as an owed native step instead of being replaced by a silent tag default.
    declared = build.get("trigger") if isinstance(build.get("trigger"), Mapping) else {}
    trigger_type = str(declared.get("type") or "")
    approved_tag = workflow.get("tag")
    if VERIFIED_TRIGGER_TYPES.get(trigger_type) == "contact_tag" and approved_tag:
        out["trigger"] = {"type": "contact_tag", "tag": approved_tag,
                          "status": "draft", "rail": "api",
                          "conditions": compile_trigger_conditions(
                              approved_tag, list(build.get("eligibility") or []))}
    else:
        out["trigger"] = {"type": trigger_type or None, "status": "unverified",
                          "rail": "managed_browser", "tag": None, "conditions": []}
        out["incomplete_actions"].append("trigger:%s" % (trigger_type or "missing"))
        out["notes"].append("trigger_unverified:%s" % (trigger_type or "missing"))
        if allow_browser_steps:
            _ledger(out, "set_trigger", trigger_type=trigger_type,
                    detail=declared.get("detail"))

    linked, unlinked = link_steps(steps)
    if unlinked:
        blocked.append("branch_unwired:%s" % ",".join(str(n) for n in unlinked))
    steps = linked

    sched = {node.get("step_id"): node
             for node in seq_schedule.get("nodes") or []
             if isinstance(node, Mapping) and node.get("step_id")
             and node.get("kind") == "absolute" and node.get("at")
             and node.get("status") != "suppressed"}
    steps = _apply_absolute(out, steps, sched, until_dates, tz, allow_browser_steps)

    if promotional and ptag and steps:
        if purchase_tag_set:
            _apply_purchase_gate(steps, bid, ptag)
        else:
            out["notes"].append("purchase_gate_unset:%s" % ptag)

    # F05 short purchase handler: the tag it sets is what lets the promotional
    # gate fire.  A handler that installs no tag step is recorded as an
    # incomplete action — it is reported, not silently graded complete.
    handler_incomplete = []
    if build.get("family") == "post_sale" and ptag and not any(
            step.get("type") == "add_contact_tag"
            and ptag in (step.get("attributes") or {}).get("tags", [])
            for step in steps):
        out["notes"].append("purchase_tag_step_missing:%s" % ptag)
        handler_incomplete.append("purchase_tag:%s" % ptag)

    sms_copy = bindings.get("sms_copy") if isinstance(bindings.get("sms_copy"),
                                                      Mapping) else {}
    pending = []
    for step in steps:
        if step.get("type") != "sms":
            continue
        attrs = step.setdefault("attributes", {})
        ref = str(attrs.get("body_ref") or "")
        supplied = sms_copy.get(step.get("id")) or sms_copy.get(ref)
        if isinstance(supplied, str) and supplied.strip():
            attrs["body"] = supplied
            attrs["body_ref"] = ref or step.get("name")
            attrs["copy_pending"] = False
        elif attrs.get("copy_pending") or not str(attrs.get("body") or "").strip():
            attrs["copy_pending"] = True
            pending.append(step.get("id"))
        else:
            # Body text copied verbatim from the template is bound copy; the
            # marker is cleared so the action is not reported half-done.
            attrs["copy_pending"] = False
    email_pending = []
    for step in steps:
        if step.get("type") != "email":
            continue
        attrs = step.setdefault("attributes", {})
        subject = str(attrs.get("subject") or "")
        body = str(attrs.get("body") or attrs.get("html") or "")
        # An email action is only complete with the real subject AND body it
        # will send.  An empty one is unfinished copy, never a finished send.
        if subject.strip() and body.strip():
            attrs["copy_pending"] = False
        else:
            attrs["copy_pending"] = True
            email_pending.append(step.get("id"))
    email_actions = sum(1 for step in steps if step.get("type") == "email")
    sms_actions = sum(1 for step in steps if step.get("type") == "sms")
    out["steps"] = steps
    out["channel_actions"] = {
        "email": {"actions": email_actions,
                  "complete": email_actions > 0 and not email_pending,
                  "copy_pending": email_pending,
                  "reason": ("approved email copy is missing a subject or a body; "
                             "the action stays copy_pending") if email_pending else None},
        "sms": {"actions": sms_actions,
                "complete": sms_actions > 0 and not pending,
                "copy_pending": pending,
                "unavailable": bool(sms_actions) and len(pending) == sms_actions,
                "reason": ("no approved SMS copy in the build plan or bindings; "
                           "the action stays copy_pending") if pending else None},
    }
    out["incomplete_actions"] = handler_incomplete + [
        "email:%s" % step_id for step_id in email_pending] + [
        "sms:%s" % step_id for step_id in pending]
    if pending:
        out["notes"].append("sms_copy_pending:%d" % len(pending))
    if email_pending:
        out["notes"].append("email_copy_pending:%d" % len(email_pending))
    return out


# ── document-level compile ───────────────────────────────────────────────────
def compile_launch_document(document: Mapping[str, Any], **kw: Any) -> dict:
    """Compile a whole launch-c automation-build document.

    Post-sale builds compile first; promo builds are blocked unless a post-sale
    build in the same document compiled and sets the purchase tag.
    """
    if not isinstance(document, Mapping) or document.get("draft_only") is not True:
        raise ValueError("DOCUMENT-NOT-DRAFT: automation-build document must be draft_only")
    builds = [b for b in document.get("builds") or [] if isinstance(b, Mapping)]
    results: dict[str, Any] = {}
    promo_tags = sorted({w.get("tag") for b in builds if b.get("family") in PROMO_FAMILIES
                         for w in b.get("workflows") or [] if isinstance(w, Mapping) and w.get("tag")})
    bindings = dict(kw.pop("bindings", None) or {})
    if promo_tags:
        bindings.setdefault("every launch promotional tag on the buyer", promo_tags)
    for b in [b for b in builds if b.get("family") == "post_sale"]:
        results[b["id"]] = compile_build(b, bindings=bindings, **kw)
    setter = any(r["status"] == "ok" for r in results.values())
    for b in builds:
        if b["id"] not in results:
            results[b["id"]] = compile_build(b, bindings=bindings, purchase_tag_set=setter, **kw)
    return {
        "builds": results,
        "campaign": {k: v for r in results.values() for k, v in r["workflows"].items()},
        "blocked": {i: r["blocked_by"] for i, r in results.items() if r["status"] != "ok"},
        "browser_steps": [row for r in results.values() for row in r["browser_steps"]],
    }


def append_browser_ledger(path: Any, rows: list) -> None:
    """Append managed-browser steps to a JSONL run ledger (no credentials, no copy)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


# ── export read-back (WF-9 mechanical for launch builds) ─────────────────────
def _instant(value: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def verify_readback(wf_def: Mapping[str, Any], exported: list) -> list:
    """Compare a saved/exported step graph with the compiled definition.

    Returns findings (empty = pass): every compiled wait-until date must exist as
    an exported wait node, every promo workflow needs a real goal and if/else on
    the purchase tag, and a post-sale flow must actually set that tag.
    """
    findings = []
    nodes = [n for n in exported or [] if isinstance(n, Mapping)]
    attrs = lambda n: n.get("attributes") or {}  # noqa: E731
    have = {_instant(attrs(n).get("untilDate")) for n in nodes if n.get("type") == "wait"} - {None}
    for row in wf_def.get("browser_steps") or []:
        if row.get("action") == "wait_until_date" and _instant(row.get("at")) not in have:
            findings.append("wait_until_missing:%s" % row.get("at"))
    tag = wf_def.get("purchase_tag")
    if wf_def.get("promotional"):
        if not any(n.get("type") == "workflow_goal" and attrs(n).get("tag") == tag for n in nodes):
            findings.append("purchase_goal_missing:%s" % tag)
        if not any(n.get("type") == "if_else" and any(
                c.get("value") == tag for c in attrs(n).get("conditions") or [] if isinstance(c, Mapping))
                for n in nodes):
            findings.append("purchase_gate_missing:%s" % tag)
    if wf_def.get("phase") == "post_sale" and not any(
            n.get("type") == "add_contact_tag" and tag in (attrs(n).get("tags") or []) for n in nodes):
        findings.append("purchase_tag_not_set:%s" % tag)
    return findings
