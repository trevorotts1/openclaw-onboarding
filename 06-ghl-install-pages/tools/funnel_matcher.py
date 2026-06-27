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
# Catalog index
# --------------------------------------------------------------------------- #
class Catalog:
    """In-memory searchable index of every funnel template + persona registry."""

    def __init__(self, root: str, templates: list[dict], personas: dict):
        self.root = root
        self.templates = templates
        self.personas = personas          # persona-id -> persona record (cross-group)
        self.by_id = {t["id"]: t for t in templates}

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
        json.dump(self.to_index(), open(out_path, "w", encoding="utf-8"), indent=2)
        return out_path

    @classmethod
    def from_index(cls, index_path: str) -> "Catalog":
        idx = json.load(open(index_path, encoding="utf-8"))
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
                 reranker: "EmbeddingReranker | None" = None) -> dict:
    """Classify -> score every template -> decide USE_TEMPLATE or CREATE_NEW.

    FLEXIBILITY MODEL:
    ------------------
    Mode 1 — Explicit desire: if ``request["explicit_funnel"]`` is set OR the
    request text unambiguously names a template, returns ``HONORED_EXPLICIT``
    immediately (no scoring). The caller MUST build what was named.

    Mode 2 — Unsure (default): normal scoring path. Result is a SUGGESTION.
    The caller presents it to the user for confirmation.

    Mode 3 — Just do it: ``request["just_do_it"]=True`` — the caller builds the
    top match without asking.

    Returns a decision record (also what gets logged).
    """
    if isinstance(request, str):
        request = {"text": request}

    _EXPLICIT_CONFIDENCE = 1.0

    # Mode 1 — explicit desire check (fast path, no scoring needed)
    explicit_id = request.get("explicit_funnel") or ""
    if not explicit_id:
        explicit_id = _detect_funnel_explicit(request.get("text", ""), catalog) or ""

    if explicit_id and explicit_id in catalog.by_id:
        tmpl = catalog.by_id[explicit_id]
        persona = catalog.resolve_persona(tmpl["persona"])
        pages = instantiate_pages(tmpl)
        return {
            "decision": "HONORED_EXPLICIT",
            "flexibility_mode": 1,
            "matched_template": explicit_id,
            "matched_name": tmpl["name"],
            "confidence": _EXPLICIT_CONFIDENCE,
            "threshold": threshold,
            "score_parts": {},
            "copy_persona": persona,
            "pages": pages,
            "ranked": [{"id": explicit_id, "name": tmpl["name"],
                        "group": tmpl["group"], "confidence": _EXPLICIT_CONFIDENCE,
                        "raw": 999, "parts": {}}],
            "classified": {},
            "rationale": (
                "FLEXIBILITY MODE 1 — HONORED EXPLICIT: "
                f"User explicitly named '{tmpl['name']}' — building exactly that. "
                "This matcher honors explicit user desire above all scoring. "
                "No template suggestion overrides this choice."
            ),
            "request": request,
            "ts": _ts(),
        }

    # Mode 2/3 — scoring path
    feats = classify(request)
    scored = [score_template(t, feats) for t in catalog.templates]
    for s in scored:
        s["confidence"] = round(_confidence(s["raw"]), 4)
    scored.sort(key=lambda s: (-s["confidence"], -s["raw"], s["id"]))

    if reranker and reranker.available():
        scored = reranker.rerank(feats["text"], catalog, scored)

    ranked = scored[:top_k]
    best = ranked[0] if ranked else None
    decision = "CREATE_NEW"
    matched_id = None
    persona = None
    pages = None
    just_do_it = bool(request.get("just_do_it"))
    flex_mode = 3 if just_do_it else 2

    if best and best["confidence"] >= threshold and best["raw"] > 0:
        decision = "USE_TEMPLATE"
        matched_id = best["id"]
        tmpl = catalog.by_id[matched_id]
        persona = catalog.resolve_persona(tmpl["persona"])
        pages = instantiate_pages(tmpl)

    rationale = _rationale(best, threshold, decision, flex_mode)
    return {
        "decision": decision,
        "flexibility_mode": flex_mode,
        "matched_template": matched_id,
        "matched_name": catalog.by_id[matched_id]["name"] if matched_id else None,
        "confidence": best["confidence"] if best else 0.0,
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
# Instantiate (template -> ghl_builder page plan)
# --------------------------------------------------------------------------- #
def instantiate_pages(tmpl: dict) -> list[dict]:
    """Turn a matched template's pageStructure into a build plan ready for
    ``ghl_builder.build_manifest`` (the persona that writes each page's copy is
    attached so the copy step pulls from the right swipe-file voice)."""
    persona_label = tmpl["persona"].get("label", "")
    pages = []
    for p in tmpl["pageStructure"]:
        path = _slug(p["page"]) or f"step-{p['order']}"
        pages.append({
            "order": p["order"],
            "name": p["page"],
            "path": path,
            "mode": "direct",
            "purpose": p["purpose"],
            "blocks": p["blocks"],
            "skill44Widgets": p.get("skill44Widgets", []),
            "copy_persona": persona_label,
            "copy_scripts": tmpl.get("scripts", ""),
        })
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
        "decision": decision["decision"],
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
# STEP 0 wiring (called by v2_dispatcher before the builder runs)
# --------------------------------------------------------------------------- #
def step0_match(task: dict, evidence_root: str, *,
                catalog_root: str | None = None,
                index_path: str | None = None,
                threshold: float = DEFAULT_THRESHOLD,
                reranker: "EmbeddingReranker | None" = None) -> dict:
    """STEP 0 of the funnel build flow.

    Build a request from the board ``task`` (free text + structured intent), match
    it against the catalog, LOG the decision, write ``routing/funnel-match.json``,
    and MUTATE the task so the builder is template-first:

      * USE_TEMPLATE -> task['pages'] = instantiated plan, task['copy_persona'] set,
                        task['template_match'] records the decision.
      * CREATE_NEW   -> task['template_match'] records the decision; the builder
                        generates net-new, then the caller calls save_new_template.

    Returns the decision record. Never raises into the build loop (matching is
    advisory glue — a matcher failure must not block a build)."""
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
            # Flexibility model inputs (v14.6.0 retrofit)
            "explicit_funnel": task.get("explicit_funnel", ""),
            "just_do_it": bool(task.get("just_do_it")),
        }
        decision = match_funnel(request, catalog, threshold=threshold, reranker=reranker)

        # persist
        routing = os.path.join(evidence_root, "routing")
        os.makedirs(routing, exist_ok=True)
        json.dump(decision, open(os.path.join(routing, "funnel-match.json"), "w",
                                 encoding="utf-8"), indent=2)
        log_decision(decision, os.path.join(routing, "funnel-decisions.jsonl"))

        # mutate task (advisory — callers should present the suggestion to the user
        # unless decision=HONORED_EXPLICIT or just_do_it=True)
        task["template_match"] = {
            "decision": decision["decision"],
            "flexibility_mode": decision.get("flexibility_mode"),
            "matched_template": decision["matched_template"],
            "confidence": decision["confidence"],
            "rationale": decision.get("rationale", ""),
        }
        if decision["decision"] in ("USE_TEMPLATE", "HONORED_EXPLICIT"):
            task.setdefault("pages", decision["pages"])
            task["copy_persona"] = decision["copy_persona"]
            task["instantiated_from_template"] = decision["matched_template"]
        return decision
    except Exception as exc:  # noqa: BLE001 — matching must never block a build
        return {"decision": "SKIPPED", "reason": f"matcher error: {type(exc).__name__}: {exc}"}


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
