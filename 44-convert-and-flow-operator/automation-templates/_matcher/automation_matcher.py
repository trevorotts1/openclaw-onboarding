#!/usr/bin/env python3
"""automation_matcher.py — FLEXIBLE template matcher for Skill 44 (convert-and-flow).

PURPOSE
-------
STEP 0 of any Skill-44 automation build. Before caf wires a GoHighLevel workflow it:

  1. CLASSIFIES the automation request (free text + structured intent),
  2. DETECTS the INTENT MODE via flex.detect_mode():
        EXPLICIT_USER_SPEC / UNSURE_WANTS_SUGGESTION / HANDS_OFF_DO_IT_ALL,
  3. SCORES the request against the 28 shipped automation templates,
  4. MAPS (mode, match) -> a flexibility decision via flex.decide():
        EXPLICIT  -> HONOR_USER       (build the user's spec; template = optional ref),
        UNSURE    -> SUGGEST_TEMPLATE  (recommend + why, await confirm)  | CREATE_NEW,
        HANDS_OFF -> USE_TEMPLATE       (build it all from the template) | CREATE_NEW,
        nothing fits -> CREATE_NEW (+ save_new_template so the library grows).
  5. LOGS the mode + decision + matched template + score.

The matcher NEVER blocks a build and NEVER imposes a template onto a user's explicit
desire — the template is a GUIDE and a RESOURCE, never a rule. (See flex.py.)

stdlib-only, deterministic, no network. The lexical scorer is the wired+proven path;
an optional ``embed_fn`` semantic re-rank hook is scaffolded.
"""
from __future__ import annotations
import json, os, re, time
from typing import Any, Callable

_HERE = os.path.dirname(os.path.abspath(__file__))
import sys
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import flex  # shared intent-mode + decision core

# --------------------------------------------------------------------------- #
# Config (mirrors funnel_matcher weights so behaviour is consistent fleet-wide)
# --------------------------------------------------------------------------- #
DEFAULT_THRESHOLD = 0.55
_CONF_DENOM = 6.0

_W_NAME = 6.0
_W_ALIAS = 4.0
_W_HEADNOUN = 2.5
_W_KW_FULL = 3.0
_W_KW_PART = 1.0
_W_GOAL = 0.30
_W_SIGNAL = 0.30
_W_CATEGORY = 3.0
_CAP_GOAL = 2.0
_CAP_SIGNAL = 2.0

_STOPWORDS = {
    "a", "an", "the", "to", "for", "of", "and", "or", "my", "me", "i", "we", "our",
    "your", "you", "with", "in", "on", "at", "is", "are", "be", "want", "need", "build",
    "make", "create", "get", "got", "into", "that", "this", "it", "so", "can", "will",
    "do", "have", "has", "page", "funnel", "automation", "workflow", "sequence", "new",
    "email", "emails", "send", "set", "up", "just",
}

# intent words -> the automation CATEGORY a structured intent maps to.
_CATEGORY_TO_GROUP = {
    "welcome": "welcome-indoctrination", "indoctrination": "welcome-indoctrination",
    "onboarding": "welcome-indoctrination", "onboard": "welcome-indoctrination",
    "bonding": "welcome-indoctrination", "new subscriber": "welcome-indoctrination",
    "soap opera": "welcome-indoctrination",
    "broadcast": "engagement-broadcast", "newsletter": "engagement-broadcast",
    "engagement": "engagement-broadcast", "seinfeld": "engagement-broadcast",
    "re-engagement": "engagement-broadcast", "reengagement": "engagement-broadcast",
    "winback": "engagement-broadcast", "win-back": "engagement-broadcast",
    "daily email": "engagement-broadcast",
    "close": "sales-close-sequences", "sales": "sales-close-sequences",
    "cart close": "sales-close-sequences", "scarcity": "sales-close-sequences",
    "deadline": "sales-close-sequences", "launch": "sales-close-sequences",
    "followup": "funnel-specific-followups", "follow-up": "funnel-specific-followups",
    "follow up": "funnel-specific-followups", "replay": "funnel-specific-followups",
    "reminder": "funnel-specific-followups", "post-purchase": "funnel-specific-followups",
    "oto": "funnel-specific-followups", "membership": "funnel-specific-followups",
    "application": "funnel-specific-followups",
    "multichannel": "multichannel-automation", "multi-channel": "multichannel-automation",
    "sms": "multichannel-automation", "retargeting": "multichannel-automation",
    "retarget": "multichannel-automation", "behavioral": "multichannel-automation",
    "branching": "multichannel-automation", "omnichannel": "multichannel-automation",
}


# --------------------------------------------------------------------------- #
# Tokenisation
# --------------------------------------------------------------------------- #
def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _singular(tok: str) -> str:
    """Light singularisation so plurals match (subscribers->subscriber, carts->cart).
    Deliberately conservative: only fold a trailing 's' on words >=4 chars that don't
    end in 'ss' (so 'process' stays). Helps real-world plural requests; no stemming lib."""
    if len(tok) >= 4 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def _tokens(text: str) -> list[str]:
    raw = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [_singular(t) for t in raw if t not in _STOPWORDS and len(t) > 1]


def _content_tokens(text: str) -> set[str]:
    return set(_tokens(text))


def _head_nouns(tid: str, name: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9]+", (tid or "").lower()))
    words |= set(re.findall(r"[a-z0-9]+", (name or "").lower()))
    drop = {"sequence", "automation", "workflow", "the", "and", "for", "with", "email",
            "emails", "campaign", "followup", "follow", "stack", "close", "multichannel"}
    return {w for w in words if w not in drop and len(w) > 2}


# --------------------------------------------------------------------------- #
# Schema normalisation (automation template dialect)
# --------------------------------------------------------------------------- #
def _pick(d: dict, *keys: str, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] is not None:
            return d[k]
    return default


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def _trigger_text(trig: Any) -> str:
    if isinstance(trig, dict):
        vals = []
        for k in ("primary_event", "what_starts_it", "ghl_trigger_type",
                  "primary_trigger", "fires", "entry_conditions"):
            v = trig.get(k)
            if isinstance(v, (list, tuple)):
                vals.append(" ".join(map(str, v)))
            elif v:
                vals.append(str(v))
        return " ".join(vals)
    return str(trig or "")


def normalise_template(doc: dict, *, group: str, path: str) -> dict:
    summary = _pick(doc, "summary", "purpose", default="")
    aliases = list(_pick(doc, "aliases", default=[]) or [])
    channels = _pick(doc, "channels", default=[]) or []
    trig = _trigger_text(_pick(doc, "trigger", default={}))
    # synthesise keywords/signals from aliases + channels + trigger (templates have no
    # explicit whenToUse block, so the search bag is built from what they DO carry).
    rec = {
        "id": _pick(doc, "id", default=_slug(_pick(doc, "name", default=os.path.basename(path)))),
        "name": _pick(doc, "name", default=""),
        "group": group,
        "category": _pick(doc, "category", default=group),
        "aliases": aliases,
        "summary": summary,
        "channels": [str(c) for c in channels] if isinstance(channels, (list, tuple)) else [str(channels)],
        "trigger": trig,
        "keywords": aliases,            # aliases are the strongest 'when to use' phrases here
        "goals": [summary] if summary else [],
        "signals": ([trig] if trig else []) + ([str(c) for c in channels] if isinstance(channels, (list, tuple)) else []),
        "antiSignals": list(_pick(doc, "antiSignals", "anti_signals", default=[]) or []),
        "ghlBuild": _pick(doc, "ghl_build", "ghlBuild", default={}),
        "sourcePath": path,
        "flexibility": _pick(doc, "flexibility", default={}),
    }
    rec["headNouns"] = sorted(_head_nouns(rec["id"], rec["name"]))
    bag = " ".join([rec["name"], " ".join(aliases), summary, group,
                    " ".join(rec["channels"]), trig])
    rec["searchText"] = _norm(bag)
    rec["searchTokens"] = sorted(_content_tokens(bag))
    return rec


# --------------------------------------------------------------------------- #
# Index path portability (keep committed indexes free of operator-local paths)
# --------------------------------------------------------------------------- #
def _relativise_index(idx: dict, base_dir: str) -> None:
    """Rewrite absolute paths in an index dict to be RELATIVE to ``base_dir`` so the
    committed file has no machine-specific path. Inverse: ``_absolutise_index``."""
    if idx.get("root") and os.path.isabs(idx["root"]):
        idx["root"] = os.path.relpath(idx["root"], base_dir)
    for t in idx.get("templates", []):
        sp = t.get("sourcePath")
        if sp and os.path.isabs(sp):
            t["sourcePath"] = os.path.relpath(sp, base_dir)


def _absolutise_index(idx: dict, base_dir: str) -> None:
    """Re-resolve relative paths in a loaded index against ``base_dir`` so sourcePath/root
    point at the real files on whatever box loads the index. Inverse of relativise."""
    if idx.get("root") and not os.path.isabs(idx["root"]):
        idx["root"] = os.path.normpath(os.path.join(base_dir, idx["root"]))
    for t in idx.get("templates", []):
        sp = t.get("sourcePath")
        if sp and not os.path.isabs(sp):
            t["sourcePath"] = os.path.normpath(os.path.join(base_dir, sp))


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #
class Catalog:
    def __init__(self, root: str, templates: list[dict]):
        self.root = root
        self.templates = templates
        # NOTE: bare-id index is COLLISION-PRONE — two different templates can share the
        # same bare id (e.g. 'soap-opera-sequence' lives in BOTH welcome-indoctrination/
        # and sales-close-sequences/). Keep it only for the unambiguous-id convenience
        # case; the qualified 'group/id' index below is the collision-safe source of truth.
        self.by_id = {t["id"]: t for t in templates}
        self.by_key = {self._qkey(t["group"], t["id"]): t for t in templates}
        # ids that appear in more than one group — must be resolved by qualified key.
        self.ambiguous_ids = sorted({
            t["id"] for t in templates
            if sum(1 for x in templates if x["id"] == t["id"]) > 1
        })

    @staticmethod
    def _qkey(group: str, tid: str) -> str:
        return f"{group}/{tid}"

    def get(self, tid: str | None, *, group: str | None = None) -> dict | None:
        """Resolve a template COLLISION-SAFELY.

        Prefer the qualified 'group/id'. Fall back to the bare id ONLY when it is
        unambiguous (exactly one template carries it). Never returns the wrong variant."""
        if not tid:
            return None
        if group:
            t = self.by_key.get(self._qkey(group, tid))
            if t:
                return t
        if tid in self.ambiguous_ids:
            return None  # bare id is ambiguous and no/wrong group given — refuse to guess
        return self.by_id.get(tid)

    @classmethod
    def load(cls, root: str) -> "Catalog":
        root = os.path.abspath(root)
        templates: list[dict] = []
        for group in sorted(os.listdir(root)):
            gdir = os.path.join(root, group)
            if not os.path.isdir(gdir) or group.startswith("_"):
                continue
            for fn in sorted(os.listdir(gdir)):
                if not fn.endswith(".json") or fn.startswith("_"):
                    continue
                path = os.path.join(gdir, fn)
                try:
                    doc = json.load(open(path, encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                if not isinstance(doc, dict) or ("id" not in doc and "name" not in doc):
                    continue
                templates.append(normalise_template(doc, group=group, path=path))
        templates.sort(key=lambda t: (t["group"], t["id"]))
        return cls(root, templates)

    def to_index(self) -> dict:
        return {"generated_at": _ts(), "root": self.root,
                "templateCount": len(self.templates),
                "groups": sorted({t["group"] for t in self.templates}),
                "templates": self.templates}

    def save_index(self, out_path: str) -> str:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        idx = self.to_index()
        # PORTABILITY: store root + every sourcePath RELATIVE to the index file's dir so
        # the committed index carries NO machine-specific absolute path (no operator-local
        # path leak; works on any box). from_index() re-absolutises on load.
        _relativise_index(idx, os.path.dirname(os.path.abspath(out_path)))
        json.dump(idx, open(out_path, "w", encoding="utf-8"), indent=2)
        return out_path

    @classmethod
    def from_index(cls, index_path: str) -> "Catalog":
        idx = json.load(open(index_path, encoding="utf-8"))
        _absolutise_index(idx, os.path.dirname(os.path.abspath(index_path)))
        return cls(idx.get("root", ""), idx["templates"])


# --------------------------------------------------------------------------- #
# Classify + Score (lexical, mirrors funnel_matcher)
# --------------------------------------------------------------------------- #
def classify(request: dict | str) -> dict:
    if isinstance(request, str):
        request = {"text": request}
    text_parts = [str(request.get(k, "")) for k in
                  ("text", "brief", "goal", "intent", "description", "ask", "message")]
    text = _norm(" ".join(p for p in text_parts if p))
    explicit_type = _norm(str(request.get("automation_type", request.get("type", ""))))
    cat_raw = _norm(str(request.get("category", "")))
    group_hint = ""
    for key, grp in _CATEGORY_TO_GROUP.items():
        if cat_raw == key or key in text or (explicit_type and key in explicit_type):
            group_hint = grp
            break
    return {"text": text, "tokens": _content_tokens(text + " " + explicit_type),
            "explicit_type": explicit_type, "category": cat_raw,
            "group_hint": group_hint, "raw": request}


def _phrase_hit(phrase: str, req_text: str, req_tokens: set[str]) -> float:
    phrase_n = _norm(phrase)
    if not phrase_n:
        return 0.0
    if phrase_n in req_text:
        return 1.0
    ptoks = _content_tokens(phrase)
    if not ptoks:
        return 0.0
    return 0.5 if len(ptoks & req_tokens) / len(ptoks) >= 0.6 else 0.0


def score_template(t: dict, feats: dict) -> dict:
    req_text, req_tokens = feats["text"], feats["tokens"]
    parts: dict[str, float] = {}

    if t["name"] and _norm(t["name"]) in req_text:
        parts["name"] = _W_NAME
    alias_hit = max((_W_ALIAS for a in t["aliases"] if _norm(a) and _norm(a) in req_text),
                    default=0.0)
    if alias_hit:
        parts["alias"] = alias_hit

    head_hits = [w for w in t["headNouns"] if w in req_tokens]
    if head_hits:
        parts["headNoun"] = _W_HEADNOUN

    if feats["explicit_type"] and (feats["explicit_type"] in _norm(t["name"])
                                   or feats["explicit_type"] in t["id"]):
        parts["explicitType"] = _W_HEADNOUN

    kw = 0.0
    for phrase in t["keywords"]:
        h = _phrase_hit(phrase, req_text, req_tokens)
        kw += _W_KW_FULL if h == 1.0 else (_W_KW_PART if h else 0.0)
    if kw:
        parts["keywords"] = round(kw, 3)

    goal_tokens = _content_tokens(" ".join(t["goals"]))
    g = min(_CAP_GOAL, _W_GOAL * len(goal_tokens & req_tokens))
    if g:
        parts["goals"] = round(g, 3)
    sig_tokens = _content_tokens(" ".join(t["signals"]))
    s = min(_CAP_SIGNAL, _W_SIGNAL * len(sig_tokens & req_tokens))
    if s:
        parts["signals"] = round(s, 3)

    if feats["group_hint"] and feats["group_hint"] == t["group"]:
        parts["category"] = _W_CATEGORY

    raw = sum(parts.values())
    return {"id": t["id"], "name": t["name"], "group": t["group"],
            "raw": round(raw, 3), "parts": parts}


def _confidence(raw: float) -> float:
    return max(0.0, min(1.0, raw / _CONF_DENOM))


# --------------------------------------------------------------------------- #
# Match (FLEXIBLE — the heart of Skill 44 STEP 0)
# --------------------------------------------------------------------------- #
def match_automation(request: dict | str, catalog: Catalog, *,
                     threshold: float = DEFAULT_THRESHOLD,
                     top_k: int = 5,
                     intent_mode: str | None = None) -> dict:
    """Classify -> detect intent mode -> score -> flexibility decision.

    Returns the decision record (also what gets logged). NEVER blocks; NEVER imposes."""
    feats = classify(request)
    mode_info = flex.detect_mode(request, override=intent_mode)
    mode = mode_info["mode"]

    scored = [score_template(t, feats) for t in catalog.templates]
    for s in scored:
        s["confidence"] = round(_confidence(s["raw"]), 4)
    scored.sort(key=lambda s: (-s["confidence"], -s["raw"], s["id"]))
    ranked = scored[:top_k]
    best = ranked[0] if ranked else None

    has_any = bool(best and best["raw"] > 0)
    has_confident = bool(best and best["confidence"] >= threshold and best["raw"] > 0)
    flex_dec = flex.decide(mode, has_confident_match=has_confident, has_any_match=has_any)
    decision = flex_dec["decision"]

    matched_id = best["id"] if (has_any and decision != flex.DEC_CREATE_NEW) else None
    matched_group = best["group"] if matched_id else None
    template = catalog.get(matched_id, group=matched_group) if matched_id else None
    matched_key = catalog._qkey(matched_group, matched_id) if template else None
    pages = instantiate_workflow(template) if (template and flex_dec["build_from_template"]) else None

    return {
        "intent_mode": mode,
        "mode_reason": mode_info["reason"],
        "mode_cue": mode_info.get("cue"),
        "decision": decision,
        "imposes_on_user": flex_dec["imposes_on_user"],   # always False
        "override_allowed": flex_dec["override_allowed"], # always True
        "await_confirm": flex_dec["await_confirm"],
        "build_from_template": flex_dec["build_from_template"],
        "template_role": flex_dec["template_role"],
        "matched_template": matched_id,
        "matched_template_key": matched_key,   # qualified 'group/id' (collision-safe)
        "matched_name": (template["name"] if template else None),
        "matched_category": (template["group"] if template else None),
        "confidence": best["confidence"] if best else 0.0,
        "threshold": threshold,
        "score_parts": best["parts"] if best else {},
        "workflow_plan": pages,
        "ranked": [{"id": r["id"], "name": r["name"], "group": r["group"],
                    "confidence": r["confidence"], "raw": r["raw"], "parts": r["parts"]}
                   for r in ranked],
        "rationale": _rationale(mode, decision, best, threshold, flex_dec),
        "flex_note": flex_dec["note"],
        "flex_principle": flex.flex_principle(),
        "classified": {k: (sorted(v) if isinstance(v, set) else v)
                       for k, v in feats.items() if k != "raw"},
        "request": request if isinstance(request, dict) else {"text": request},
        "ts": _ts(),
    }


def _rationale(mode: str, decision: str, best: dict | None, threshold: float,
               flex_dec: dict) -> str:
    bm = (f"best='{best['name']}' confidence={best['confidence']} (threshold {threshold})"
          if best else "no candidate scored")
    return f"mode={mode} -> decision={decision}. {bm}. {flex_dec['note']}"


# --------------------------------------------------------------------------- #
# Instantiate (template -> caf workflow build-plan)
# --------------------------------------------------------------------------- #
def instantiate_workflow(tmpl: dict) -> dict:
    """Turn a matched automation template into an ordered caf workflow build-plan.

    Pulls the documented ghl_build (trigger + actions_in_order/nodes) so Skill 44 can
    wire it. Order + parentKey discipline is the caller's (Skill-44 reliability rule)."""
    gb = tmpl.get("ghlBuild", {}) or {}
    actions = (gb.get("actions_in_order")
               or (gb.get("workflow", {}) or {}).get("nodes")
               or [])
    return {
        "automation_id": tmpl["id"],
        "automation_name": tmpl["name"],
        "category": tmpl["group"],
        "workflow_name": gb.get("workflow_name") or (gb.get("workflow", {}) or {}).get("name")
                         or tmpl["name"],
        "trigger": gb.get("trigger_config") or (gb.get("workflow", {}) or {}).get("trigger")
                   or tmpl.get("trigger", ""),
        "channels": tmpl.get("channels", []),
        "actions_in_order": list(actions),
        "if_else_branches": gb.get("if_else_branches")
                            or (gb.get("workflow", {}) or {}).get("if_else_branches", []),
        "wait_steps": gb.get("wait_steps") or (gb.get("workflow", {}) or {}).get("wait_steps", []),
        "tags_used": gb.get("tags_used", []),
        "source_ref": tmpl["sourcePath"],
    }


# --------------------------------------------------------------------------- #
# Save-back (grow the library after CREATE_NEW)
# --------------------------------------------------------------------------- #
def save_new_template(spec: dict, catalog_root: str, *, group: str | None = None,
                      reindex_path: str | None = None) -> dict:
    name = spec.get("name") or "New Automation"
    tid = spec.get("id") or _slug(name)
    group = group or spec.get("group") or spec.get("category") or "_generated"
    gdir = os.path.join(os.path.abspath(catalog_root), group)
    os.makedirs(gdir, exist_ok=True)
    out = {
        "id": tid, "name": name, "aliases": spec.get("aliases", []),
        "category": spec.get("category", group),
        "summary": spec.get("summary", spec.get("purpose", "")),
        "origin": "CREATE_NEW (saved back by automation_matcher)",
        "generated_at": _ts(),
        "trigger": spec.get("trigger", {}),
        "channels": spec.get("channels", []),
        "sequence": spec.get("sequence", []),
        "copy_persona": spec.get("copy_persona", {}),
        "ghl_build": spec.get("ghl_build", spec.get("ghlBuild", {})),
        "flexibility": spec.get("flexibility", flex.flex_principle()),
    }
    path = os.path.join(gdir, f"{tid}.json")
    json.dump(out, open(path, "w", encoding="utf-8"), indent=2)
    if reindex_path:
        Catalog.load(catalog_root).save_index(reindex_path)
    return {"path": path, "id": tid, "group": group}


# --------------------------------------------------------------------------- #
# Decision log (mode + decision + template + score)
# --------------------------------------------------------------------------- #
def log_decision(decision: dict, log_path: str) -> str:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    line = json.dumps({
        "ts": decision.get("ts", _ts()),
        "intent_mode": decision.get("intent_mode"),
        "mode_cue": decision.get("mode_cue"),
        "decision": decision["decision"],
        "matched_template": decision.get("matched_template"),
        "confidence": decision.get("confidence"),
        "threshold": decision.get("threshold"),
        "await_confirm": decision.get("await_confirm"),
        "request": decision.get("request"),
        "ranked": [(r["id"], r["confidence"]) for r in decision.get("ranked", [])[:3]],
        "rationale": decision.get("rationale"),
    }, ensure_ascii=False)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    return log_path


# --------------------------------------------------------------------------- #
# Funnel -> linked-automations expansion (the "complete funnel" trigger)
# --------------------------------------------------------------------------- #
def expand_funnel_to_automations(funnel_id: str, *, link_map_path: str,
                                 catalog: Catalog | None = None,
                                 include_secondary: bool = True,
                                 overrides: list[str] | None = None,
                                 intent_mode: str | None = None) -> dict:
    """Given a Skill-6 funnel template id, return the linked automation build-plans
    (primary + optional secondary + graduation) from funnel-to-automation.json — MINUS
    any automation the user overrode/ignored. This is what fires when instantiating a
    Skill-6 funnel template so Skill 44 builds the COMPLETE funnel's follow-ups.

    overrides: automation ids (or 'category/id') the user already specified themselves or
    explicitly declined — they are DROPPED from the auto-build (never imposed).
    The whole expansion is RECOMMENDED, not mandatory; in EXPLICIT mode it is a reference
    list only (build_now=False)."""
    overrides = set(overrides or [])
    data = json.load(open(link_map_path, encoding="utf-8"))
    entry = next((l for l in data.get("links", []) if l["funnel_template_id"] == funnel_id), None)
    if not entry:
        return {"funnel_template_id": funnel_id, "found": False,
                "reason": "no link entry for this funnel id", "automations": []}

    mode = (flex.detect_mode({"text": ""}, override=intent_mode)["mode"]
            if intent_mode else flex.MODE_HANDSOFF)
    # In EXPLICIT mode the linked list is a reference only; otherwise it's a build set.
    build_now = mode in (flex.MODE_HANDSOFF,)

    def _dropped(ref: dict) -> bool:
        key = f"{ref['category']}/{ref['automation_id']}"
        return ref["automation_id"] in overrides or key in overrides

    picks = [entry["primary_followup"]]
    if include_secondary:
        picks += entry.get("secondary_followups", [])
    if "graduation_followup" in entry:
        picks.append(entry["graduation_followup"])

    automations = []
    for ref in picks:
        dropped = _dropped(ref)
        item = {**ref, "recommended": True, "mandatory": False,
                "overridden_by_user": dropped, "build_now": build_now and not dropped}
        # Resolve by the QUALIFIED 'category/automation_id' the link map already supplies.
        # Bare-id lookup would cross-wire variants that share an id (soap-opera-sequence).
        tmpl = (catalog.get(ref["automation_id"], group=ref.get("category"))
                if catalog else None)
        if tmpl and not dropped:
            item["workflow_plan"] = instantiate_workflow(tmpl)
        automations.append(item)

    return {
        "funnel_template_id": funnel_id,
        "funnel_group": entry["funnel_group"],
        "found": True,
        "intent_mode": mode,
        "recommended": True,
        "mandatory": False,
        "note": "Linked automations are RECOMMENDED defaults for a complete funnel. Any the "
                "user overrode are dropped (overridden_by_user=true, build_now=false). In "
                "EXPLICIT mode the whole list is a reference only.",
        "automations": automations,
    }


# --------------------------------------------------------------------------- #
# STEP 0 wiring entrypoint (called by Skill 44 before PLAN MODE / caf build)
# --------------------------------------------------------------------------- #
def step0_match(task: dict, evidence_root: str, *,
                catalog_root: str | None = None,
                index_path: str | None = None,
                link_map_path: str | None = None,
                threshold: float = DEFAULT_THRESHOLD) -> dict:
    """STEP 0 of the Skill-44 automation build.

    Builds a request from the build ``task``, matches it flexibly, LOGS the decision,
    writes ``routing/automation-match.json``, and MUTATES the task so PLAN MODE is
    flexibility-aware:

      * HONOR_USER      -> task['template_reference'] (optional), build the user's spec.
      * SUGGEST_TEMPLATE-> task['suggested_template'] + await_confirm=True (don't build yet).
      * USE_TEMPLATE    -> task['workflow_plan'] = instantiated plan (build it all).
      * CREATE_NEW      -> builder generates net-new; caller calls save_new_template after.

    If task['funnel_template_id'] is present, ALSO expands the linked automations for a
    complete funnel (minus task['automation_overrides']).

    Never raises into the build loop (matching is advisory glue)."""
    try:
        index_path = index_path or os.environ.get("CAF_AUTOMATION_INDEX")
        catalog_root = catalog_root or os.environ.get("CAF_AUTOMATION_CATALOG")
        link_map_path = link_map_path or os.environ.get("CAF_FUNNEL_AUTOMATION_LINKS")
        if index_path and os.path.isfile(index_path):
            catalog = Catalog.from_index(index_path)
        elif catalog_root and os.path.isdir(catalog_root):
            catalog = Catalog.load(catalog_root)
        else:
            return {"decision": "SKIPPED",
                    "reason": "no catalog (set CAF_AUTOMATION_CATALOG / CAF_AUTOMATION_INDEX)"}

        request = {
            "text": task.get("brief", "") or task.get("text", ""),
            "category": task.get("category", ""),
            "automation_type": task.get("automation_type", task.get("type", "")),
            "goal": task.get("goal", ""),
            "steps": task.get("user_steps") or task.get("steps"),
            "spec": task.get("user_spec"),
        }
        decision = match_automation(request, catalog, threshold=threshold,
                                    intent_mode=task.get("intent_mode"))

        routing = os.path.join(evidence_root, "routing")
        os.makedirs(routing, exist_ok=True)
        json.dump(decision, open(os.path.join(routing, "automation-match.json"), "w",
                                 encoding="utf-8"), indent=2)
        log_decision(decision, os.path.join(routing, "automation-decisions.jsonl"))

        task["template_match"] = {
            "intent_mode": decision["intent_mode"], "decision": decision["decision"],
            "matched_template": decision["matched_template"],
            "matched_template_key": decision.get("matched_template_key"),
            "confidence": decision["confidence"],
            "await_confirm": decision["await_confirm"],
            "imposes_on_user": decision["imposes_on_user"],
        }
        # Compact, normalised match-decision receipt for the QC gate (FAB-QC reads this).
        try:
            _mt = catalog.get(decision.get("matched_template"),
                              group=decision.get("matched_category"))
            json.dump({
                "skill": "44-convert-and-flow-operator",
                "matched_template_id": decision.get("matched_template"),
                "matched_template_key": decision.get("matched_template_key"),
                "template_path": (_mt.get("sourcePath") if _mt else None),
                "intent_mode": decision.get("intent_mode"),
                "flex_decision": decision.get("decision"),
                "confident_match": bool(decision.get("confidence", 0) >= threshold),
                "funnel_template_id": task.get("funnel_template_id"),
                "ts": _ts(),
            }, open(os.path.join(routing, "match-decision.json"), "w",
                    encoding="utf-8"), indent=2)
        except Exception:  # noqa: BLE001 — receipt is advisory, never blocks
            pass
        d = decision["decision"]
        if d == flex.DEC_USE:
            task.setdefault("workflow_plan", decision["workflow_plan"])
            task["built_from_template"] = decision["matched_template"]
        elif d == flex.DEC_SUGGEST:
            task["suggested_template"] = decision["matched_template"]
            task["await_confirm"] = True       # do NOT build until user confirms
        elif d == flex.DEC_HONOR_USER:
            task["template_reference"] = decision["matched_template"]  # optional ref only

        # complete-funnel expansion (only if a funnel id rode in on the task)
        if task.get("funnel_template_id") and link_map_path and os.path.isfile(link_map_path):
            decision["linked_automations"] = expand_funnel_to_automations(
                task["funnel_template_id"], link_map_path=link_map_path, catalog=catalog,
                overrides=task.get("automation_overrides"),
                intent_mode=task.get("intent_mode"))
            task["linked_automations"] = decision["linked_automations"]
        return decision
    except Exception as exc:  # noqa: BLE001 — matching must never break a build
        return {"decision": "SKIPPED", "reason": f"matcher error: {type(exc).__name__}: {exc}"}


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
