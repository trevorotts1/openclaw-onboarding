#!/usr/bin/env python3
"""funnel_matcher.py — TEMPLATE-FIRST funnel matcher for Skill 6 (06-ghl-install-pages).

PURPOSE
-------
Make Skill 6 *template-first*. Before any net-new funnel is generated, classify the
request, score it against the Brunson funnel-template library (the 38 structured
templates the group agents produced), and:

  * if the best score clears the confidence threshold  -> decision = USE_TEMPLATE
      (return the matched template + which persona writes the copy + an instantiated
       page-build plan ready for ghl_builder.build_manifest),
  * else                                                -> decision = CREATE_NEW
      (caller generates a net-new funnel; afterward call ``save_new_template`` so the
       net-new funnel becomes a template and the library grows).

Every decision is LOGGED (matched template + score + ranked runners-up + rationale)
so Trevor can see WHY a template was used or a new funnel was created.

FLEXIBILITY MODEL (retrofitted — v14.6.0)
------------------------------------------
This matcher is a GUIDE and a RESOURCE, never a rule or a gate.

  Mode 1 — Explicit desire:   User has stated which funnel they want.
                               match_funnel() returns HONORED_EXPLICIT and does
                               NOT run scoring. The caller MUST build what was named.
                               No suggestion overrides explicit user desire.

  Mode 2 — User is unsure:    Normal scoring path. The best match is SUGGESTED —
                               the caller presents it to the user for confirmation.
                               The user can accept, choose a different template, or
                               request a custom funnel.

  Mode 3 — Just do it:        User says 'handle it'. The highest-scoring match
                               is used directly; the caller skips the confirmation
                               step. Activated by passing ``just_do_it=True`` in
                               the request dict.

EXPLICIT DESIRE DETECTION: ``match_funnel`` checks ``request["explicit_funnel"]``
first. If absent, it runs ``_detect_funnel_explicit`` — a lightweight name/alias
scan that returns a template id when the request text unambiguously names a template.
When either path fires, the decision is ``HONORED_EXPLICIT`` and no scoring runs.

NEVER BLOCKS: a below-threshold score never prevents a build. CREATE_NEW is advisory
— the caller can still proceed with the template (user override) or go fully custom.

DESIGN
------
* stdlib-only, deterministic, no network. Lexical scorer by default; an optional
  embedding hook (``embed_fn``) can be supplied for semantic re-ranking (scaffolded —
  see ``EmbeddingReranker``; the lexical path is the one that is wired and proven).
* Robust loader: the 38 template JSONs use TWO schema dialects — camelCase
  (``whenToUse`` / ``pageStructure`` / ``copyFramework``) and snake_case
  (``when_to_use`` / ``page_structure`` / ``copy_framework``). ``primaryPersona`` may
  be a string, a persona-id, or an object ``{slug,book,script,role}``. The loader
  normalizes all of these into one shape.

This module is GLUE for the matcher; it does not open a browser or call GHL.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any, Callable, Iterable

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
DEFAULT_THRESHOLD = 0.55          # confidence (0..1) to USE_TEMPLATE vs CREATE_NEW
_CONF_DENOM = 6.0                 # raw-score -> confidence normaliser (tuned by selftest)

# raw-score weights
_W_NAME = 6.0                     # template name appears in the request
_W_ALIAS = 4.0                    # an alias appears in the request
_W_HEADNOUN = 2.5                 # the template's id head-noun appears (webinar/book/...)
                                  # < a full keyword hit, so specific intent beats a bare noun
_W_KW_FULL = 3.0                  # a whole keyword phrase matched
_W_KW_PART = 1.0                  # a keyword phrase partially matched (>=60% tokens)
_W_GOAL = 0.30                    # per goal-token overlap (capped)
_W_SIGNAL = 0.30                  # per signal-token overlap (capped)
_W_CATEGORY = 3.0                 # structured-intent category matches the template group
_W_ANTI = -4.0                    # an anti-signal phrase matched (penalty)
_CAP_GOAL = 2.0
_CAP_SIGNAL = 2.0

# --------------------------------------------------------------------------- #
# FLEXIBILITY — intent-mode detection + decision mapping (retrofitted v14.7.0)
# --------------------------------------------------------------------------- #
# CORE PRINCIPLE: every template/persona is a GUIDE and a RESOURCE, never a rule or a
# requirement. It must NOT dominate the user's desire. This mirrors the Skill-44
# automation matcher's flex.py (kept inline here so this file stays self-contained).
# Three modes:
#   EXPLICIT_USER_SPEC      -> HONOR_USER       (build the user's spec; template = optional ref)
#   UNSURE_WANTS_SUGGESTION -> SUGGEST_TEMPLATE  (recommend + why, await confirm) | CREATE_NEW
#   HANDS_OFF_DO_IT_ALL     -> USE_TEMPLATE       (build it all from the template)| CREATE_NEW
# The matcher NEVER blocks a build and NEVER imposes a template onto an explicit desire.
# Backward compat: HONORED_EXPLICIT = HONOR_USER (kept so v14.6.0 callers still work).
MODE_EXPLICIT = "EXPLICIT_USER_SPEC"
MODE_UNSURE = "UNSURE_WANTS_SUGGESTION"
MODE_HANDSOFF = "HANDS_OFF_DO_IT_ALL"
MODES = (MODE_EXPLICIT, MODE_UNSURE, MODE_HANDSOFF)

DEC_HONOR_USER = "HONOR_USER"        # EXPLICIT: build the user's spec; template = optional ref
DEC_SUGGEST = "SUGGEST_TEMPLATE"     # UNSURE + confident: recommend + why, await confirm
DEC_USE = "USE_TEMPLATE"             # HANDS_OFF + confident: build it all from the template
DEC_CREATE_NEW = "CREATE_NEW"        # nothing fits: build net-new, save back
HONORED_EXPLICIT = DEC_HONOR_USER    # backward-compat alias

_HANDSOFF_CUES = [
    "just do it", "just build", "just make it", "just set it up", "the full", "handle it",
    "you handle", "take care of it", "do it all", "do the rest", "do everything",
    "build the whole", "the whole", "whole thing", "whole funnel", "complete funnel",
    "full funnel", "full sequence", "set it all up", "set up everything", "set and forget",
    "turnkey", "done for me", "done-for-you", "dfy", "your call", "you decide",
    "you choose", "whatever you think", "whatever's best", "whatever is best",
    "best practice", "do what's best", "do what is best", "make it happen", "i trust you",
    "up to you", "surprise me", "go ahead and build", "build it out", "wire it all", "all of it",
]
_UNSURE_CUES = [
    "not sure", "unsure", "no idea", "don't know", "dont know", "what do you recommend",
    "what would you recommend", "what would you suggest", "what do you suggest",
    "any suggestions", "any recommendation", "recommend", "suggest", "which one",
    "which should", "what should i", "what should we", "help me decide", "help me pick",
    "what are my options", "what are the options", "options", "thinking about", "maybe",
    "considering", "torn between", "should i use", "is there a", "what's best", "what is best",
    "advice", "guidance", "not certain", "kind of want",
]
_EXPLICIT_SPEC_KEYS = ("spec", "sequence", "steps", "user_steps", "user_sequence",
                       "user_spec", "my_sequence", "exact_steps", "pages")
_EXPLICIT_CUES = [
    "exactly", "specifically", "to the letter", "as written", "do not change",
    "don't change", "dont change", "no changes", "must be", "must have", "has to",
    "i want it to", "i need it to", "use my", "use these", "here's my", "heres my",
    "here is my", "my own", "my exact", "follow this", "follow my", "build this:",
    "build exactly", "this exact", "these exact", "only these", "only the", "just the",
    "strictly", "verbatim", "i already have", "i have a spec", "per my spec",
    "do it this way", "the way i want", "i'll specify", "i will specify",
]


def _flex_request_text(request: Any) -> str:
    if isinstance(request, str):
        return request.lower()
    if isinstance(request, dict):
        parts = [str(request.get(k, "")) for k in
                 ("text", "brief", "goal", "intent", "description", "ask", "message")]
        return " ".join(p for p in parts if p).lower()
    return str(request or "").lower()


def _flex_has_user_spec(request: Any) -> bool:
    if not isinstance(request, dict):
        return False
    for k in _EXPLICIT_SPEC_KEYS:
        v = request.get(k)
        if isinstance(v, (list, tuple)) and len(v) >= 1:
            return True
        if isinstance(v, str) and v.strip():
            return True
    return False


def _flex_numbered_steps(text: str) -> int:
    return len(re.findall(r"(?:^|\s)(?:[1-9]\d?[\.\)]|step\s*[1-9])", text))


def _flex_any(text: str, cues: list[str]) -> str | None:
    for c in cues:
        if c in text:
            return c
    return None


def detect_mode(request: Any, override: str | None = None) -> dict:
    """Detect the intent mode for a request. Precedence: explicit override > user spec /
    EXPLICIT cues > HANDS_OFF cues > UNSURE cues > default UNSURE (least-dominating:
    suggest, never impose/auto-build when unsure). Also honors legacy ``just_do_it``
    and ``explicit_funnel`` fields from v14.6.0 callers."""
    if override in MODES:
        return {"mode": override, "reason": "explicit caller/user override", "cue": override}
    # legacy v14.6.0 compat
    if isinstance(request, dict):
        if request.get("explicit_funnel"):
            return {"mode": MODE_EXPLICIT, "reason": "explicit_funnel field set (v14.6.0 compat)",
                    "cue": "explicit_funnel"}
        if request.get("just_do_it"):
            return {"mode": MODE_HANDSOFF, "reason": "just_do_it field set (v14.6.0 compat)",
                    "cue": "just_do_it"}
    text = _flex_request_text(request)
    if _flex_has_user_spec(request):
        return {"mode": MODE_EXPLICIT, "reason": "user supplied an explicit spec/sequence",
                "cue": "user_spec"}
    if _flex_numbered_steps(text) >= 2:
        return {"mode": MODE_EXPLICIT, "reason": "user wrote their own ordered steps",
                "cue": "numbered_steps"}
    cue = _flex_any(text, _EXPLICIT_CUES)
    if cue:
        return {"mode": MODE_EXPLICIT, "reason": f"explicit-spec cue: '{cue}'", "cue": cue}
    cue = _flex_any(text, _HANDSOFF_CUES)
    if cue:
        return {"mode": MODE_HANDSOFF, "reason": f"hands-off cue: '{cue}'", "cue": cue}
    cue = _flex_any(text, _UNSURE_CUES)
    if cue:
        return {"mode": MODE_UNSURE, "reason": f"unsure cue: '{cue}'", "cue": cue}
    return {"mode": MODE_UNSURE, "reason": "no strong cue -> default to suggest (never impose)",
            "cue": None}


def flex_decide(mode: str, *, has_confident_match: bool, has_any_match: bool = False) -> dict:
    """Map (mode, match availability) -> a flexibility decision. Invariants:
    imposes_on_user is ALWAYS False; override_allowed is ALWAYS True; never blocks."""
    base = {"imposes_on_user": False, "override_allowed": True}
    if mode == MODE_EXPLICIT:
        return {**base, "decision": DEC_HONOR_USER, "await_confirm": False,
                "build_from_template": False,
                "template_role": ("optional_reference" if has_any_match else "none"),
                "note": "User has an explicit desire — build exactly that. Closest template is "
                        "an optional reference only; never imposed or overridden onto the choice."}
    if mode == MODE_HANDSOFF:
        if has_confident_match:
            return {**base, "decision": DEC_USE, "await_confirm": False,
                    "build_from_template": True, "template_role": "build_source",
                    "note": "User wants it handled ('just do it') and a proven template fits — "
                            "build the whole thing from it (still fully overridable after)."}
        return {**base, "decision": DEC_CREATE_NEW, "await_confirm": False,
                "build_from_template": False, "template_role": "none",
                "note": "User wants it handled but nothing fits — create net-new + save back."}
    if has_confident_match:
        return {**base, "decision": DEC_SUGGEST, "await_confirm": True,
                "build_from_template": False, "template_role": "suggested",
                "note": "User is unsure — suggest the proven template + why, then let the user "
                        "decide. Do NOT build until they confirm."}
    return {**base, "decision": DEC_CREATE_NEW, "await_confirm": True,
            "build_from_template": False, "template_role": "none",
            "note": "User is unsure and nothing fits — propose net-new; await confirm, save back."}


def flex_principle() -> dict:
    return {
        "core": "Every template is a GUIDE and a RESOURCE, never a rule. It assists; it never "
                "dominates the user's desire.",
        "modes": {MODE_EXPLICIT: "Do exactly what the user wants; template = optional reference.",
                  MODE_UNSURE: "Suggest the proven template + why; let the user decide.",
                  MODE_HANDSOFF: "Build the whole thing from the template."},
        "always": "Overridable, mixable, customizable, ignorable. Never blocks a build.",
    }


_STOPWORDS = {
    "a", "an", "the", "to", "for", "of", "and", "or", "my", "me", "i", "we", "our",
    "your", "you", "with", "in", "on", "at", "is", "are", "be", "want", "need",
    "build", "make", "create", "get", "got", "into", "that", "this", "it", "so",
    "can", "will", "do", "have", "has", "page", "funnel", "funnels", "new",
}

# Category synonyms -> the template GROUP a structured intent maps to.
_CATEGORY_TO_GROUP = {
    "lead": "lead", "lead funnels": "lead", "opt-in": "lead", "lead-gen": "lead",
    "buyer": "buyer", "buyer funnels": "buyer", "sales": "buyer", "checkout": "buyer",
    "event": "event", "event funnels": "event", "webinar": "event",
    "retention": "retention-followup", "retention-followup": "retention-followup",
    "follow-up": "retention-followup", "followup": "retention-followup",
    "traffic": "traffic-advanced", "traffic-advanced": "traffic-advanced",
    "advanced": "traffic-advanced",
}


# --------------------------------------------------------------------------- #
# Tokenisation
# --------------------------------------------------------------------------- #
def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _tokens(text: str) -> list[str]:
    raw = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [t for t in raw if t not in _STOPWORDS and len(t) > 1]


def _content_tokens(text: str) -> set[str]:
    return set(_tokens(text))


def _head_nouns(template_id: str, name: str) -> set[str]:
    """The distinctive 'type' words for a template (squeeze, webinar, book, ...)."""
    words = set(re.findall(r"[a-z0-9]+", (template_id or "").lower()))
    words |= set(re.findall(r"[a-z0-9]+", (name or "").lower()))
    drop = {"funnel", "page", "the", "and", "a", "of", "free", "plus", "step", "2",
            "5", "minute", "front", "end", "self", "liquidating", "offer"}
    return {w for w in words if w not in drop and len(w) > 2}


# --------------------------------------------------------------------------- #
# Schema normalisation (camelCase + snake_case dialects)
# --------------------------------------------------------------------------- #
def _pick(d: dict, *keys: str, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _normalise_persona(raw: Any) -> dict:
    """primaryPersona may be: a persona-id string, a label string, or an object."""
    if isinstance(raw, dict):
        label = _pick(raw, "label", "name", "slug", "id", default="")
        return {
            "id": _pick(raw, "id", "slug", default=_slug(label)),
            "label": label or _pick(raw, "slug", default=""),
            "author": _pick(raw, "author", "book", default=""),
            "script": _pick(raw, "script", "role", default=""),
            "detail": json.dumps(raw, ensure_ascii=False),
        }
    if isinstance(raw, str):
        return {"id": _slug(raw), "label": raw, "author": "", "script": "", "detail": raw}
    return {"id": "", "label": "", "author": "", "script": "", "detail": ""}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def _normalise_pages(raw: list) -> list[dict]:
    out = []
    for i, p in enumerate(raw or [], 1):
        if not isinstance(p, dict):
            continue
        blocks = _pick(p, "blocks", "key_elements", "keyElements", "elements", default=[])
        out.append({
            "order": _pick(p, "order", default=i),
            "page": _pick(p, "page", "name", "title", default=f"Step {i}"),
            "purpose": _pick(p, "purpose", default=""),
            "blocks": list(blocks) if isinstance(blocks, (list, tuple)) else [str(blocks)],
            "skill44Widgets": _pick(p, "skill44Widgets", "skill44_widgets", default=[]),
        })
    return out


def normalise_template(doc: dict, *, group: str, path: str) -> dict:
    """Collapse a raw template JSON (either dialect) into the catalog record shape."""
    wtu = _pick(doc, "whenToUse", "when_to_use", default={}) or {}
    cf = _pick(doc, "copyFramework", "copy_framework", default={}) or {}
    primary = _pick(cf, "primaryPersona", "primary_persona", default="")
    supporting = _pick(cf, "supportingPersonas", "supporting_personas",
                       "secondary_scripts", default=[]) or []
    scripts = _pick(cf, "scripts", "script", "salesScript", "primary_script", default="")

    rec = {
        "id": _pick(doc, "id", default=_slug(_pick(doc, "name", default=os.path.basename(path)))),
        "name": _pick(doc, "name", default=""),
        "group": group,
        "category": _pick(doc, "category", default=group),
        "aliases": list(_pick(doc, "aliases", default=[]) or []),
        "lengthClass": _pick(doc, "lengthClass", "funnel_length_class", default=""),
        "libraryRef": _pick(doc, "libraryRef", "libraryEntry", "library_entry", default=None),
        "summary": _pick(wtu, "summary", default=""),
        "goals": list(_pick(wtu, "goals", default=[]) or []),
        "keywords": list(_pick(wtu, "keywords", default=[]) or []),
        "signals": list(_pick(wtu, "signals", default=[]) or []),
        "antiSignals": list(_pick(wtu, "antiSignals", "anti_signals", "antisignals",
                                  default=[]) or []),
        "persona": _normalise_persona(primary),
        "supportingPersonas": supporting if isinstance(supporting, list) else [supporting],
        "scripts": scripts,
        "pageStructure": _normalise_pages(_pick(doc, "pageStructure", "page_structure",
                                                default=[])),
        "sourcePath": path,
    }
    rec["headNouns"] = sorted(_head_nouns(rec["id"], rec["name"]))
    # Pre-computed search bag (kept small + serialisable).
    bag = " ".join([
        rec["name"], " ".join(rec["aliases"]), rec["summary"],
        " ".join(rec["goals"]), " ".join(rec["keywords"]), " ".join(rec["signals"]),
    ])
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
# Catalog index
# --------------------------------------------------------------------------- #
class Catalog:
    """In-memory searchable index of every funnel template + persona registry."""

    def __init__(self, root: str, templates: list[dict], personas: dict):
        self.root = root
        self.templates = templates
        self.personas = personas          # persona-id -> persona record (cross-group)
        # The 38 funnel ids are currently UNIQUE, but key a collision-safe 'group/id'
        # index too (mirrors the Skill-44 fix) so a future duplicate bare id can never
        # silently cross-wire the wrong template.
        self.by_id = {t["id"]: t for t in templates}
        self.by_key = {self._qkey(t["group"], t["id"]): t for t in templates}
        self.ambiguous_ids = sorted({
            t["id"] for t in templates
            if sum(1 for x in templates if x["id"] == t["id"]) > 1
        })

    @staticmethod
    def _qkey(group: str, tid: str) -> str:
        return f"{group}/{tid}"

    def get(self, tid: str | None, *, group: str | None = None) -> dict | None:
        """Resolve a template collision-safely (qualified 'group/id' first, bare id only
        when unambiguous). Never returns the wrong variant."""
        if not tid:
            return None
        if group:
            t = self.by_key.get(self._qkey(group, tid))
            if t:
                return t
        if tid in self.ambiguous_ids:
            return None
        return self.by_id.get(tid)

    # ---- construction -----------------------------------------------------
    @classmethod
    def load(cls, root: str) -> "Catalog":
        root = os.path.abspath(root)
        templates: list[dict] = []
        personas: dict = {}
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
                if not isinstance(doc, dict) or "id" not in doc and "name" not in doc:
                    continue
                templates.append(normalise_template(doc, group=group, path=path))
            # persona registry per group (optional)
            for pf in ("_personas.json", "_PERSONAS.json"):
                pp = os.path.join(gdir, pf)
                if os.path.isfile(pp):
                    try:
                        reg = json.load(open(pp, encoding="utf-8")).get("personas", {})
                        for pid, prec in reg.items():
                            personas.setdefault(pid, prec)
                    except (json.JSONDecodeError, OSError):
                        pass
        templates.sort(key=lambda t: (t["group"], t["id"]))
        return cls(root, templates, personas)

    # ---- serialisation ----------------------------------------------------
    def to_index(self) -> dict:
        return {
            "generated_at": _ts(),
            "root": self.root,
            "templateCount": len(self.templates),
            "groups": sorted({t["group"] for t in self.templates}),
            "personaCount": len(self.personas),
            "templates": self.templates,
            "personas": self.personas,
        }

    def save_index(self, out_path: str) -> str:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        idx = self.to_index()
        # PORTABILITY: store root + every sourcePath RELATIVE to the index file's dir so
        # the committed index carries NO machine-specific absolute path. Re-absolutised
        # on load by from_index().
        _relativise_index(idx, os.path.dirname(os.path.abspath(out_path)))
        json.dump(idx, open(out_path, "w", encoding="utf-8"), indent=2)
        return out_path

    @classmethod
    def from_index(cls, index_path: str) -> "Catalog":
        idx = json.load(open(index_path, encoding="utf-8"))
        _absolutise_index(idx, os.path.dirname(os.path.abspath(index_path)))
        return cls(idx.get("root", ""), idx["templates"], idx.get("personas", {}))

    def resolve_persona(self, persona: dict) -> dict:
        """Enrich a template's persona with the cross-group registry record if present."""
        pid = persona.get("id")
        if pid and pid in self.personas:
            reg = self.personas[pid]
            return {**persona,
                    "label": persona.get("label") or reg.get("label", ""),
                    "author": persona.get("author") or reg.get("author", ""),
                    "book": reg.get("book", ""),
                    "owns_scripts": reg.get("owns_scripts", []),
                    "voice": reg.get("voice", "")}
        return persona


# --------------------------------------------------------------------------- #
# Classify
# --------------------------------------------------------------------------- #
def classify(request: dict | str) -> dict:
    """Extract goal/category/specifics from free text + structured intent.

    ``request`` is either a free-text string, or a dict like::

        {"text": "...", "category": "lead", "goal": "...", "length": "short-form",
         "funnel_type": "webinar"}

    Returns a feature bundle the scorer consumes.
    """
    if isinstance(request, str):
        request = {"text": request}
    text_parts = [str(request.get(k, "")) for k in
                  ("text", "brief", "goal", "intent", "description", "ask")]
    text = _norm(" ".join(p for p in text_parts if p))
    explicit_type = _norm(str(request.get("funnel_type", request.get("type", ""))))
    cat_raw = _norm(str(request.get("category", "")))
    group_hint = _CATEGORY_TO_GROUP.get(cat_raw, _CATEGORY_TO_GROUP.get(explicit_type, ""))
    return {
        "text": text,
        "tokens": _content_tokens(text + " " + explicit_type),
        "explicit_type": explicit_type,
        "category": cat_raw,
        "group_hint": group_hint,
        "length": _norm(str(request.get("length", request.get("lengthClass", "")))),
        "raw": request,
    }


# --------------------------------------------------------------------------- #
# Score
# --------------------------------------------------------------------------- #
def _phrase_hit(phrase: str, req_text: str, req_tokens: set[str]) -> float:
    """1.0 full hit, 0.5 partial (>=60% content tokens present), else 0."""
    phrase_n = _norm(phrase)
    if not phrase_n:
        return 0.0
    if phrase_n in req_text:
        return 1.0
    ptoks = _content_tokens(phrase)
    if not ptoks:
        return 0.0
    overlap = len(ptoks & req_tokens) / len(ptoks)
    if overlap >= 0.6:
        return 0.5
    return 0.0


def score_template(t: dict, feats: dict) -> dict:
    """Raw score + per-signal breakdown for one template against the request."""
    req_text, req_tokens = feats["text"], feats["tokens"]
    parts: dict[str, float] = {}

    # name / alias
    if t["name"] and _norm(t["name"]) in req_text:
        parts["name"] = _W_NAME
    alias_hit = max((_W_ALIAS for a in t["aliases"] if _norm(a) and _norm(a) in req_text),
                    default=0.0)
    if alias_hit:
        parts["alias"] = alias_hit

    # head-noun (squeeze / webinar / book / cancellation ...)
    head_hits = [w for w in t["headNouns"] if w in req_tokens]
    if head_hits:
        parts["headNoun"] = _W_HEADNOUN

    # explicit funnel_type match
    if feats["explicit_type"] and (feats["explicit_type"] in _norm(t["name"])
                                   or feats["explicit_type"] in t["id"]):
        parts["explicitType"] = _W_HEADNOUN

    # keyword phrases (the strongest 'when to use' signal)
    kw = 0.0
    for phrase in t["keywords"]:
        h = _phrase_hit(phrase, req_text, req_tokens)
        kw += _W_KW_FULL * 1.0 if h == 1.0 else (_W_KW_PART if h else 0.0)
    if kw:
        parts["keywords"] = round(kw, 3)

    # goals / signals token overlap (capped)
    goal_tokens = _content_tokens(" ".join(t["goals"]))
    g = min(_CAP_GOAL, _W_GOAL * len(goal_tokens & req_tokens))
    if g:
        parts["goals"] = round(g, 3)
    sig_tokens = _content_tokens(" ".join(t["signals"]))
    s = min(_CAP_SIGNAL, _W_SIGNAL * len(sig_tokens & req_tokens))
    if s:
        parts["signals"] = round(s, 3)

    # structured category
    if feats["group_hint"] and feats["group_hint"] == t["group"]:
        parts["category"] = _W_CATEGORY

    # anti-signals (penalty)
    anti = 0.0
    for phrase in t["antiSignals"]:
        if _phrase_hit(phrase, req_text, req_tokens) == 1.0:
            anti += _W_ANTI
    if anti:
        parts["antiSignal"] = round(anti, 3)

    raw = sum(parts.values())
    return {"id": t["id"], "name": t["name"], "group": t["group"],
            "raw": round(raw, 3), "parts": parts}


def _confidence(raw: float) -> float:
    return max(0.0, min(1.0, raw / _CONF_DENOM))


# --------------------------------------------------------------------------- #
# Optional embedding reranker (SCAFFOLD — lexical path is the wired one)
# --------------------------------------------------------------------------- #
class EmbeddingReranker:
    """Optional semantic re-rank hook. Supply ``embed_fn(text)->vector`` (e.g. local
    Ollama). If absent, ``rerank`` is a no-op so the lexical scorer stands alone.
    This is intentionally SCAFFOLDED: the lexical scorer is what is wired + proven."""

    def __init__(self, embed_fn: Callable[[str], list[float]] | None = None):
        self.embed_fn = embed_fn

    def available(self) -> bool:
        return self.embed_fn is not None

    def rerank(self, request_text: str, catalog: Catalog,
               candidates: list[dict], blend: float = 0.35) -> list[dict]:
        if not self.available() or not candidates:
            return candidates
        import math
        qv = self.embed_fn(request_text)

        def cos(a, b):
            num = sum(x * y for x, y in zip(a, b))
            da = math.sqrt(sum(x * x for x in a)) or 1.0
            db = math.sqrt(sum(y * y for y in b)) or 1.0
            return num / (da * db)

        for c in candidates:
            t = catalog.by_id[c["id"]]
            sem = cos(qv, self.embed_fn(t["searchText"]))
            c["semantic"] = round(sem, 4)
            c["confidence"] = round((1 - blend) * c["confidence"] + blend * sem, 4)
        candidates.sort(key=lambda c: (-c["confidence"], c["id"]))
        return candidates


# --------------------------------------------------------------------------- #
# Explicit desire detection (Flexibility Model — Mode 1)
# --------------------------------------------------------------------------- #
def _detect_funnel_explicit(text: str, catalog: Catalog) -> str | None:
    """Return a funnel template id if the user has unambiguously named one.

    Checks (in order):
    1. Template id with hyphens replaced by spaces (e.g. 'squeeze page', 'webinar funnel')
    2. Template id as-is (handles direct id copy-paste)
    3. Core template name tokens (first 3-4 significant words, parenthetical stripped)
    4. Alias match — phrase aliases >= 6 characters checked

    Returns None if no unambiguous match is found — scoring proceeds normally.
    This is an OPTIONAL helper; explicit desire can also be set via
    ``request["explicit_funnel"]``.
    """
    norm_text = _norm(text)
    # 1. ID as space-separated words
    for t in catalog.templates:
        id_as_words = t["id"].replace("-", " ")
        if id_as_words and id_as_words in norm_text:
            return t["id"]
    # 2. ID with hyphens (less likely in natural language)
    for t in catalog.templates:
        if t["id"] and t["id"] in norm_text:
            return t["id"]
    # 3. Core name — strip parenthetical, take first 4 non-stopword tokens
    for t in catalog.templates:
        raw_name = re.sub(r"\(.*?\)", "", t["name"])
        core_tokens = [tok for tok in _tokens(raw_name) if len(tok) > 2][:4]
        if len(core_tokens) >= 2:
            core_phrase = " ".join(core_tokens)
            if core_phrase in norm_text:
                return t["id"]
    # 4. Alias match — phrase aliases only (>= 6 chars to avoid false positives)
    for t in catalog.templates:
        for alias in t["aliases"]:
            if len(alias) >= 6 and _norm(alias) in norm_text:
                return t["id"]
    return None


# --------------------------------------------------------------------------- #
# Match
# --------------------------------------------------------------------------- #
def match_funnel(request: dict | str, catalog: Catalog, *,
                 threshold: float = DEFAULT_THRESHOLD,
                 top_k: int = 5,
                 reranker: "EmbeddingReranker | None" = None,
                 intent_mode: str | None = None,
                 persona_bundle: dict | None = None) -> dict:
    """Classify -> detect intent mode -> score every template -> FLEXIBLE decision.

    decision is one of HONOR_USER / SUGGEST_TEMPLATE / USE_TEMPLATE / CREATE_NEW.
    The template is NEVER imposed onto a user's explicit desire; the matcher never blocks.

    ``persona_bundle`` (B-U1/U15's normalized receipt) threads through to
    ``instantiate_pages`` so each instantiated page carries a per-page
    blend_directive (B-U2/U16). Optional and additive — omitting it is
    byte-identical to the pre-B-U2 behavior.

    Backward compat: passing ``request["explicit_funnel"]`` or ``request["just_do_it"]``
    still works exactly as in v14.6.0 — those fields are honoured by detect_mode().

    Returns a decision record (also what gets logged)."""
    if isinstance(request, str):
        request = {"text": request}

    # Check for EXPLICIT by name (fast path via the existing _detect_funnel_explicit
    # helper — name/alias scan). This fires before mode detection so an unambiguous
    # name always routes to HONOR_USER regardless of the rest of the text.
    explicit_id = request.get("explicit_funnel") or ""
    if not explicit_id:
        explicit_id = _detect_funnel_explicit(request.get("text", ""), catalog) or ""

    # FLEXIBILITY: detect intent mode (honors legacy just_do_it / explicit_funnel fields)
    mode_info = detect_mode(request, override=(
        MODE_EXPLICIT if explicit_id else intent_mode))
    mode = mode_info["mode"]

    # Scoring path (always runs so we have a ranked list for reference / SUGGEST)
    feats = classify(request)
    scored = [score_template(t, feats) for t in catalog.templates]
    for s in scored:
        s["confidence"] = round(_confidence(s["raw"]), 4)
    scored.sort(key=lambda s: (-s["confidence"], -s["raw"], s["id"]))

    if reranker and reranker.available():
        scored = reranker.rerank(feats["text"], catalog, scored)

    ranked = scored[:top_k]
    best = ranked[0] if ranked else None

    has_any = bool(best and best["raw"] > 0)
    has_confident = bool(best and best["confidence"] >= threshold and best["raw"] > 0)

    # When EXPLICIT and a name was detected, force matched_id to the named template
    if mode == MODE_EXPLICIT and explicit_id and explicit_id in catalog.by_id:
        matched_id = explicit_id
        has_any = True
        has_confident = True
    else:
        matched_id = best["id"] if has_any else None

    flex = flex_decide(mode, has_confident_match=has_confident, has_any_match=has_any)
    decision = flex["decision"]

    matched_group = best["group"] if (best and matched_id == best["id"]) else None
    persona = None
    pages = None
    tmpl = catalog.get(matched_id, group=matched_group)
    if tmpl:
        persona = catalog.resolve_persona(tmpl["persona"])
        if flex["build_from_template"] or mode == MODE_EXPLICIT:
            pages = instantiate_pages(tmpl, bundle=persona_bundle)

    rationale = _rationale_flex(mode, decision, best, threshold, flex)
    return {
        "decision": decision,
        "intent_mode": mode,
        "mode_reason": mode_info["reason"],
        "mode_cue": mode_info.get("cue"),
        "imposes_on_user": flex["imposes_on_user"],     # always False
        "override_allowed": flex["override_allowed"],   # always True
        "await_confirm": flex["await_confirm"],
        "build_from_template": flex["build_from_template"],
        "template_role": flex["template_role"],
        "flex_note": flex["note"],
        "flex_principle": flex_principle(),
        "matched_template": matched_id,
        "matched_template_key": (catalog._qkey(matched_group, matched_id)
                                 if (tmpl and matched_group) else None),
        "matched_name": tmpl["name"] if tmpl else None,
        "confidence": (1.0 if mode == MODE_EXPLICIT and explicit_id else
                       (best["confidence"] if best else 0.0)),
        "threshold": threshold,
        "score_parts": best["parts"] if best else {},
        "copy_persona": persona,
        "pages": pages,
        "ranked": [{"id": r["id"], "name": r["name"], "group": r["group"],
                    "confidence": r["confidence"], "raw": r["raw"],
                    "parts": r["parts"]} for r in ranked],
        "classified": {k: (sorted(v) if isinstance(v, set) else v)
                       for k, v in feats.items() if k != "raw"},
        "rationale": rationale,
        "request": request if isinstance(request, dict) else {"text": request},
        "ts": _ts(),
    }


def _rationale_flex(mode: str, decision: str, best: dict | None, threshold: float,
                    flex: dict) -> str:
    bm = (f"best='{best['name']}' confidence={best['confidence']} (threshold {threshold})"
          if best else "no candidate scored")
    return f"mode={mode} -> decision={decision}. {bm}. {flex['note']}"


def _rationale(best: dict | None, threshold: float, decision: str,
               flex_mode: int = 2) -> str:
    flex_preamble = (
        "This matcher is a GUIDE and a RESOURCE, never a rule. "
        "Every suggestion is overridable — the user's explicit desire always wins. "
        f"(Flexibility Mode {flex_mode}{'  — user said just do it' if flex_mode == 3 else ''}.)"
    )
    if not best or best["raw"] <= 0:
        return (f"{flex_preamble} No template scored above zero against the request — "
                "CREATE_NEW (a net-new funnel will be generated and saved back). "
                "The user can still request any template by name.")
    drivers = ", ".join(f"{k}(+{v})" if v >= 0 else f"{k}({v})"
                        for k, v in sorted(best["parts"].items(),
                                           key=lambda kv: -abs(kv[1])))
    if decision == "USE_TEMPLATE":
        return (f"{flex_preamble} Best match '{best['name']}' confidence={best['confidence']} "
                f">= threshold {threshold}. Drivers: {drivers}. "
                "If the user prefers a different template or wants a custom funnel, "
                "honor that choice — this is a suggestion, not a requirement.")
    return (f"{flex_preamble} Best candidate '{best['name']}' confidence={best['confidence']} "
            f"< threshold {threshold} -> CREATE_NEW. Drivers: {drivers}. "
            "A custom funnel can still be built, or the user can name any template to use it.")


# --------------------------------------------------------------------------- #
# B-U2 / U16 — per-page blend directive (converges the template's persona onto
# the ONE unified persona-blend system: the template persona is DEMOTED to a
# crosswalk-resolved TOPIC/craft hint, never a second voice authority; the
# VOICE stays the ONE task-level persona from the B-U1 bundle across every
# page). Lazy-loaded and fully fail-soft: a repo layout where shared-utils or
# 23-ai-workforce-blueprint aren't reachable simply skips the blend fields —
# `copy_persona` (structure/craft) keeps working exactly as before.
# --------------------------------------------------------------------------- #
_CROSSWALK_CACHE: "tuple | None" = None
_BLEND_MODULE_CACHE: "Any | bool | None" = None


def _load_crosswalk_once():
    """Lazy-load shared-utils/persona_crosswalk.py once. Returns
    (module, canonical_set, crosswalk_dict) or None when unreachable."""
    global _CROSSWALK_CACHE
    if _CROSSWALK_CACHE is not None:
        return _CROSSWALK_CACHE or None
    try:
        _tools_dir = os.path.dirname(os.path.abspath(__file__))
        _shared = os.path.normpath(os.path.join(_tools_dir, "..", "..", "shared-utils"))
        if _shared not in sys.path:
            sys.path.insert(0, _shared)
        import persona_crosswalk as _pcw  # type: ignore
        canonical = _pcw.load_canonical()
        crosswalk = _pcw.load_crosswalk()
        _CROSSWALK_CACHE = (_pcw, canonical, crosswalk)
    except Exception:  # noqa: BLE001 — the per-page blend directive is advisory
        _CROSSWALK_CACHE = False
    return _CROSSWALK_CACHE or None


def _load_blend_module():
    """Lazy-load 23-ai-workforce-blueprint/scripts/persona_blend.py once."""
    global _BLEND_MODULE_CACHE
    if _BLEND_MODULE_CACHE is not None:
        return _BLEND_MODULE_CACHE or None
    try:
        _tools_dir = os.path.dirname(os.path.abspath(__file__))
        _scripts = os.path.normpath(
            os.path.join(_tools_dir, "..", "..", "23-ai-workforce-blueprint", "scripts"))
        if _scripts not in sys.path:
            sys.path.insert(0, _scripts)
        import persona_blend as _pb  # type: ignore
        _BLEND_MODULE_CACHE = _pb
    except Exception:  # noqa: BLE001
        _BLEND_MODULE_CACHE = False
    return _BLEND_MODULE_CACHE or None


def _build_page_blend(page: dict, template_persona_ref: str, bundle: dict, xwalk: tuple) -> dict:
    """Resolve this PAGE's crosswalk topic hint + compose its blend_directive
    under the bundle's ONE task-level voice. Different pages -> different
    topic (and directive text); the voice_persona_id is constant across
    pages (per-page SCOPE, one task-level VOICE)."""
    _pcw, canonical, crosswalk = xwalk
    page_topic_pid = None
    if template_persona_ref:
        resolved, _how = _pcw.resolve(template_persona_ref, canonical, crosswalk)
        page_topic_pid = resolved
    if not page_topic_pid:
        page_topic_pid = bundle.get("topic_persona_id")

    voice_pid = bundle.get("voice_persona_id")
    audience_id = bundle.get("audience_id")
    audience_label = bundle.get("audience_label") or ""
    content_task = bundle.get("content_task")
    if content_task is None:
        content_task = True
    task_personas = bundle.get("task_personas") or []
    task_pid = next((tp.get("persona_id") for tp in task_personas
                     if isinstance(tp, dict) and tp.get("persona_id")), None)

    # Cheap, catalog-free collapse check (mirrors decide_collapse's first,
    # zero-cost branch): the SAME persona covering audience + this page's
    # topic collapses; anything else stays a two-persona blend.
    collapsed = bool(audience_id and page_topic_pid and audience_id == page_topic_pid)
    collapsed_pid = page_topic_pid if collapsed else None

    directive = None
    _pb = _load_blend_module()
    if _pb is not None and voice_pid:
        topic_text = page.get("purpose") or page.get("name") or ""
        directive = _pb.build_blend_directive(
            audience_id, page_topic_pid, topic_text, collapsed, collapsed_pid,
            content_task, audience_label, task_persona_pid=task_pid,
        )

    return {
        "blend_directive": directive,
        "voice_persona_id": voice_pid,
        "topic_persona_id": page_topic_pid,
    }


# --------------------------------------------------------------------------- #
# Instantiate (template -> ghl_builder page plan)
# --------------------------------------------------------------------------- #
def instantiate_pages(tmpl: dict, *, bundle: dict | None = None) -> list[dict]:
    """Turn a matched template's pageStructure into a build plan ready for
    ``ghl_builder.build_manifest`` (the persona that writes each page's copy is
    attached so the copy step pulls from the right swipe-file voice).

    When ``bundle`` (the normalized persona-bundle-acquisition-ladder receipt,
    B-U1/U15 — ``task['persona_bundle']``) is supplied AND carries a usable
    ``voice_persona_id``, each page ALSO carries a per-page
    ``blend_directive`` / ``voice_persona_id`` / ``topic_persona_id`` (B-U2 /
    U16): the template persona is DEMOTED to a crosswalk-resolved topic/craft
    hint feeding the blend's per-page TOPIC slot, while the VOICE stays the
    ONE task-level persona from the bundle across every page.
    ``copy_persona`` is UNCHANGED for back-compat (``ghl_survey_builder`` keeps
    reading it verbatim) — its meaning is redefined as the topic/craft hint,
    never the voice authority. Additive-only: omitting ``bundle`` is
    byte-identical to the pre-B-U2 behavior."""
    persona = tmpl["persona"]
    persona_label = persona.get("label", "")
    persona_ref = persona.get("id") or persona_label
    usable_bundle = (bundle if isinstance(bundle, dict) and bundle.get("voice_persona_id")
                     else None)
    xwalk = _load_crosswalk_once() if usable_bundle else None

    pages = []
    for p in tmpl["pageStructure"]:
        path = _slug(p["page"]) or f"step-{p['order']}"
        page = {
            "order": p["order"],
            "name": p["page"],
            "path": path,
            "mode": "direct",
            "purpose": p["purpose"],
            "blocks": p["blocks"],
            "skill44Widgets": p.get("skill44Widgets", []),
            "copy_persona": persona_label,
            "copy_scripts": tmpl.get("scripts", ""),
        }
        if usable_bundle and xwalk is not None:
            page.update(_build_page_blend(page, persona_ref, usable_bundle, xwalk))
        pages.append(page)
    return pages


# --------------------------------------------------------------------------- #
# Save-back (grow the library after a CREATE_NEW)
# --------------------------------------------------------------------------- #
def save_new_template(spec: dict, catalog_root: str, *, group: str | None = None,
                      reindex_path: str | None = None) -> dict:
    """Persist a net-new funnel as a NEW template so the library grows.

    ``spec`` is the net-new funnel description (free-form but ideally with
    ``name`` + ``pageStructure`` + ``whenToUse``). Returns ``{path, id, group}``.
    The new file is written in the canonical camelCase dialect.
    """
    name = spec.get("name") or "New Funnel"
    tid = spec.get("id") or _slug(name)
    group = group or spec.get("group") or "_generated"
    gdir = os.path.join(os.path.abspath(catalog_root), group)
    os.makedirs(gdir, exist_ok=True)
    out = {
        "id": tid,
        "name": name,
        "aliases": spec.get("aliases", []),
        "category": spec.get("category", group),
        "group": group,
        "lengthClass": spec.get("lengthClass", ""),
        "origin": "CREATE_NEW (saved back by funnel_matcher)",
        "generated_at": _ts(),
        "whenToUse": spec.get("whenToUse", {
            "summary": spec.get("summary", ""),
            "goals": spec.get("goals", []),
            "keywords": spec.get("keywords", []),
            "signals": spec.get("signals", []),
            "antiSignals": spec.get("antiSignals", []),
        }),
        "pageStructure": spec.get("pageStructure", []),
        "copyFramework": spec.get("copyFramework", {
            "primaryPersona": spec.get("primaryPersona", ""),
            "supportingPersonas": spec.get("supportingPersonas", []),
            "scripts": spec.get("scripts", ""),
        }),
        "ghlBuild": spec.get("ghlBuild", {}),
    }
    path = os.path.join(gdir, f"{tid}.json")
    json.dump(out, open(path, "w", encoding="utf-8"), indent=2)
    if reindex_path:
        Catalog.load(catalog_root).save_index(reindex_path)
    return {"path": path, "id": tid, "group": group}


# --------------------------------------------------------------------------- #
# Decision log
# --------------------------------------------------------------------------- #
def log_decision(decision: dict, log_path: str) -> str:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    line = json.dumps({
        "ts": decision.get("ts", _ts()),
        "intent_mode": decision.get("intent_mode"),
        "mode_cue": decision.get("mode_cue"),
        "decision": decision["decision"],
        "await_confirm": decision.get("await_confirm"),
        "matched_template": decision.get("matched_template"),
        "confidence": decision.get("confidence"),
        "threshold": decision.get("threshold"),
        "request": decision.get("request"),
        "ranked": [(r["id"], r["confidence"]) for r in decision.get("ranked", [])[:3]],
        "rationale": decision.get("rationale"),
    }, ensure_ascii=False)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    return log_path


# --------------------------------------------------------------------------- #
# Funnel -> linked-automations (the "complete funnel" handoff to Skill 44)
# --------------------------------------------------------------------------- #
def linked_automations(funnel_id: str, link_map_path: str, *,
                       overrides: list[str] | None = None,
                       include_secondary: bool = True) -> dict:
    """Read funnel-to-automation.json and return the RECOMMENDED follow-up automations
    for ``funnel_id`` (primary + optional secondary + graduation), MINUS any the user
    overrode. This is what Skill 6 emits so Skill 44 can build the COMPLETE funnel's
    follow-ups. RECOMMENDED, never mandatory; anything the user overrode is dropped."""
    overrides = set(overrides or [])
    try:
        data = json.load(open(link_map_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"funnel_template_id": funnel_id, "found": False,
                "reason": f"link map unreadable: {exc}", "automations": []}
    entry = next((l for l in data.get("links", []) if l["funnel_template_id"] == funnel_id), None)
    if not entry:
        return {"funnel_template_id": funnel_id, "found": False,
                "reason": "no link entry", "automations": []}
    picks = [entry["primary_followup"]]
    if include_secondary:
        picks += entry.get("secondary_followups", [])
    if "graduation_followup" in entry:
        picks.append(entry["graduation_followup"])
    out = []
    for ref in picks:
        key = f"{ref['category']}/{ref['automation_id']}"
        dropped = ref["automation_id"] in overrides or key in overrides
        out.append({**ref, "recommended": True, "mandatory": False,
                    "overridden_by_user": dropped, "build_now": not dropped})
    return {"funnel_template_id": funnel_id, "funnel_group": entry["funnel_group"],
            "found": True, "recommended": True, "mandatory": False,
            "note": "RECOMMENDED follow-ups for a complete funnel; user overrides are dropped. "
                    "Hand to Skill 44 (caf) to build the linked automations.",
            "automations": out}


# --------------------------------------------------------------------------- #
# STEP 0 wiring (called by v2_dispatcher before the builder runs)
# --------------------------------------------------------------------------- #
def step0_match(task: dict, evidence_root: str, *,
                catalog_root: str | None = None,
                index_path: str | None = None,
                threshold: float = DEFAULT_THRESHOLD,
                reranker: "EmbeddingReranker | None" = None,
                intent_mode: str | None = None,
                link_map_path: str | None = None) -> dict:
    """STEP 0 of the funnel build flow — FLEXIBLE + template-aware.

    Build a request from the board ``task`` (free text + structured intent), detect
    the intent mode, match against the catalog, LOG the decision, write
    ``routing/funnel-match.json``, and MUTATE the task per the flexibility contract:

      * USE_TEMPLATE     (HANDS_OFF + confident) -> task['pages'] = instantiated plan,
                          task['copy_persona'], task['instantiated_from_template'].
      * SUGGEST_TEMPLATE (UNSURE + confident)    -> task['suggested_template'] +
                          task['await_confirm']=True; pages NOT set (await user confirm).
      * HONOR_USER       (EXPLICIT)              -> task['template_reference'] = optional
                          ref only; the user's own spec/pages are left untouched.
      * CREATE_NEW       (nothing fits)          -> builder generates net-new; caller
                          then calls save_new_template.

    If a link map is available (``link_map_path`` / GHL_FUNNEL_AUTOMATION_LINKS) and the
    funnel is identified, the RECOMMENDED follow-up automations are attached (minus
    task['automation_overrides']) so Skill 44 can build the COMPLETE funnel. Recommended,
    never mandatory.

    Returns the decision record. Never raises into the build loop (matching is advisory
    glue — a matcher failure must not block a build)."""
    try:
        if index_path and os.path.isfile(index_path):
            catalog = Catalog.from_index(index_path)
        else:
            root = catalog_root or os.environ.get("GHL_FUNNEL_CATALOG", "")
            if not root or not os.path.isdir(root):
                return {"decision": "SKIPPED",
                        "reason": "no catalog (set GHL_FUNNEL_CATALOG or pass catalog_root)"}
            catalog = Catalog.load(root)

        request = {
            "text": task.get("brief", "") or task.get("text", ""),
            "category": task.get("category", ""),
            "funnel_type": task.get("funnel_type", task.get("type", "")),
            "goal": task.get("goal", ""),
            "length": task.get("length", ""),
            "steps": task.get("user_steps") or task.get("steps"),
            "spec": task.get("user_spec"),
            # v14.6.0 compat fields (honoured by detect_mode)
            "explicit_funnel": task.get("explicit_funnel", ""),
            "just_do_it": bool(task.get("just_do_it")),
        }
        # B-U2/U16: thread the task's acquired persona bundle (B-U1/U15's
        # normalized routing/persona-bundle-receipt.json, if any) through to
        # instantiate_pages so each page carries a per-page blend_directive.
        _task_bundle = task.get("persona_bundle")
        _task_bundle = _task_bundle if isinstance(_task_bundle, dict) else None
        decision = match_funnel(request, catalog, threshold=threshold, reranker=reranker,
                                intent_mode=intent_mode or task.get("intent_mode"),
                                persona_bundle=_task_bundle)

        # persist
        routing = os.path.join(evidence_root, "routing")
        os.makedirs(routing, exist_ok=True)
        json.dump(decision, open(os.path.join(routing, "funnel-match.json"), "w",
                                 encoding="utf-8"), indent=2)
        log_decision(decision, os.path.join(routing, "funnel-decisions.jsonl"))

        # mutate task — flexibility-aware (never imposes onto an explicit desire)
        task["template_match"] = {
            "intent_mode": decision["intent_mode"],
            "decision": decision["decision"],
            "matched_template": decision["matched_template"],
            "confidence": decision["confidence"],
            "await_confirm": decision["await_confirm"],
            "imposes_on_user": decision["imposes_on_user"],
        }
        d = decision["decision"]
        if d == DEC_USE:
            task.setdefault("pages", decision["pages"])
            task["copy_persona"] = decision["copy_persona"]
            task["instantiated_from_template"] = decision["matched_template"]
        elif d == DEC_HONOR_USER:
            # honor existing pages/spec; template is reference only
            if decision["pages"] and not task.get("pages"):
                task["template_reference"] = decision["matched_template"]
            task["template_reference"] = decision["matched_template"]
        elif d == DEC_SUGGEST:
            task["suggested_template"] = decision["matched_template"]
            task["await_confirm"] = True          # do NOT build until the user confirms

        # complete-funnel handoff: attach the linked follow-up automations for Skill 44
        funnel_id = task.get("funnel_template_id") or (
            decision["matched_template"] if d in (DEC_USE, DEC_SUGGEST, DEC_HONOR_USER) else None)
        if funnel_id:
            # Stamp the funnel identity onto the task so it SURVIVES the P4->P5
            # department handoff (SKILL.md "Full-Funnel Pipeline Integration").
            task["funnel_template_id"] = funnel_id
            decision["funnel_template_id"] = funnel_id
        lm = link_map_path or os.environ.get("GHL_FUNNEL_AUTOMATION_LINKS")
        if funnel_id and lm and os.path.isfile(lm):
            la = linked_automations(funnel_id, lm, overrides=task.get("automation_overrides"))
            decision["linked_automations"] = la
            task["linked_automations"] = la       # consumed by Skill 44 step 0
        # Compact, normalised match-decision receipt for the QC gate (FAB-QC reads this).
        try:
            routing_dir = os.path.join(evidence_root, "routing")
            os.makedirs(routing_dir, exist_ok=True)
            _mkey = decision.get("matched_template_key") or ""
            _mgroup = _mkey.split("/", 1)[0] if "/" in _mkey else None
            _mt = catalog.get(decision.get("matched_template"), group=_mgroup)
            receipt = {
                "skill": "06-ghl-install-pages",
                "matched_template_id": decision.get("matched_template"),
                "matched_template_key": decision.get("matched_template_key"),
                "template_path": (_mt.get("sourcePath") if _mt else None),
                "intent_mode": decision.get("intent_mode"),
                "flex_decision": decision.get("decision"),
                "confident_match": bool(decision.get("confidence", 0) >= threshold),
                "funnel_template_id": funnel_id,
                "linked_automations": task.get("linked_automations"),
                "ts": _ts(),
            }
            json.dump(receipt, open(os.path.join(routing_dir, "match-decision.json"),
                                    "w", encoding="utf-8"), indent=2)
        except Exception:  # noqa: BLE001 — receipt is advisory, never blocks
            pass
        return decision
    except Exception as exc:  # noqa: BLE001 — matching must never block a build
        return {"decision": "SKIPPED", "reason": f"matcher error: {type(exc).__name__}: {exc}"}


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
