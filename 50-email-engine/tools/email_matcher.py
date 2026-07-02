#!/usr/bin/env python3
"""email_matcher.py — TAGS-FIRST library matcher for the Email Engine (Skill 50).

PURPOSE
-------
Route an email/sequence request to the right Superlibrary entry (framework /
buyer-type / objective / persona-style / sequence) BEFORE any copy is authored.
Mirrors Skill 6's ``funnel_matcher.py``: a stdlib-only, deterministic lexical
scorer over the committed ``email-library/catalog-index.json`` (id/type/name/
tags/length/best_for/file), with an OPTIONAL semantic ``EmbeddingReranker`` hook
for the shared prebuilt Gemini index. The lexical path is the wired + proven one.

FLEXIBILITY MODEL (identical doctrine to funnel_matcher)
--------------------------------------------------------
Every entry is a GUIDE and a RESOURCE, never a rule or a gate. Three modes:
  EXPLICIT_USER_SPEC      -> HONOR_USER      (build the user's spec; entry = optional ref)
  UNSURE_WANTS_SUGGESTION -> SUGGEST_ENTRY   (recommend + why, await confirm) | CREATE_NEW
  HANDS_OFF_DO_IT_ALL     -> USE_ENTRY       (build it all from the entry)    | CREATE_NEW
The matcher NEVER blocks and NEVER imposes an entry onto an explicit desire.

This module is GLUE for selection; it authors no copy and calls no provider. The
SACRED gates live in prove-email.py — the matcher only recommends what to write.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable

# --------------------------------------------------------------------------- #
# Config / weights
# --------------------------------------------------------------------------- #
DEFAULT_THRESHOLD = 0.55
_CONF_DENOM = 8.0

_W_NAME = 6.0            # entry name appears in the request
_W_ID = 5.0             # entry id (as words) appears in the request
_W_TAG_FULL = 2.0       # a whole tag phrase matched
_W_TAG_PART = 0.5       # a tag phrase partially matched (>=60% tokens)
_W_BEST = 0.4           # per best_for token overlap (capped)
_W_TYPE = 3.0           # request type filter matches the entry type
_CAP_TAG = 8.0
_CAP_BEST = 2.0

# --------------------------------------------------------------------------- #
# Flexibility — intent-mode detection (kept inline; mirrors funnel_matcher)
# --------------------------------------------------------------------------- #
MODE_EXPLICIT = "EXPLICIT_USER_SPEC"
MODE_UNSURE = "UNSURE_WANTS_SUGGESTION"
MODE_HANDSOFF = "HANDS_OFF_DO_IT_ALL"
MODES = (MODE_EXPLICIT, MODE_UNSURE, MODE_HANDSOFF)

DEC_HONOR_USER = "HONOR_USER"
DEC_SUGGEST = "SUGGEST_ENTRY"
DEC_USE = "USE_ENTRY"
DEC_CREATE_NEW = "CREATE_NEW"

_HANDSOFF_CUES = [
    "just do it", "just write", "just build", "handle it", "you handle", "do it all",
    "write them all", "the whole sequence", "full sequence", "done for me", "done-for-you",
    "dfy", "you decide", "you choose", "whatever you think", "whatever's best", "best practice",
    "make it happen", "i trust you", "up to you", "write the rest", "all of them",
]
_UNSURE_CUES = [
    "not sure", "unsure", "no idea", "don't know", "dont know", "what do you recommend",
    "what would you recommend", "which framework", "which one", "help me decide",
    "help me pick", "what are my options", "options", "maybe", "considering", "torn between",
    "should i use", "what's best", "what is best", "advice", "guidance",
]
_EXPLICIT_CUES = [
    "exactly", "specifically", "use the", "use pas", "write a pas", "must be", "must use",
    "i want the", "use my", "follow this", "build this:", "verbatim", "strictly",
]


def _flex_text(request: Any) -> str:
    if isinstance(request, str):
        return request.lower()
    if isinstance(request, dict):
        parts = [str(request.get(k, "")) for k in
                 ("text", "brief", "goal", "intent", "description", "ask", "message")]
        return " ".join(p for p in parts if p).lower()
    return str(request or "").lower()


def _flex_any(text: str, cues: list[str]) -> str | None:
    for c in cues:
        if c in text:
            return c
    return None


def detect_mode(request: Any, override: str | None = None) -> dict:
    if override in MODES:
        return {"mode": override, "reason": "explicit caller/user override", "cue": override}
    if isinstance(request, dict) and request.get("explicit_entry"):
        return {"mode": MODE_EXPLICIT, "reason": "explicit_entry field set", "cue": "explicit_entry"}
    text = _flex_text(request)
    cue = _flex_any(text, _EXPLICIT_CUES)
    if cue:
        return {"mode": MODE_EXPLICIT, "reason": f"explicit-spec cue: '{cue}'", "cue": cue}
    cue = _flex_any(text, _HANDSOFF_CUES)
    if cue:
        return {"mode": MODE_HANDSOFF, "reason": f"hands-off cue: '{cue}'", "cue": cue}
    cue = _flex_any(text, _UNSURE_CUES)
    if cue:
        return {"mode": MODE_UNSURE, "reason": f"unsure cue: '{cue}'", "cue": cue}
    return {"mode": MODE_UNSURE, "reason": "no strong cue -> default to suggest (never impose)", "cue": None}


def flex_decide(mode: str, *, has_confident: bool, has_any: bool = False) -> dict:
    base = {"imposes_on_user": False, "override_allowed": True}
    if mode == MODE_EXPLICIT:
        return {**base, "decision": DEC_HONOR_USER, "await_confirm": False, "build_from_entry": False,
                "entry_role": ("optional_reference" if has_any else "none"),
                "note": "User has an explicit desire — build exactly that; the entry is an optional reference."}
    if mode == MODE_HANDSOFF:
        if has_confident:
            return {**base, "decision": DEC_USE, "await_confirm": False, "build_from_entry": True,
                    "entry_role": "build_source",
                    "note": "User wants it handled and a proven entry fits — build from it (still overridable)."}
        return {**base, "decision": DEC_CREATE_NEW, "await_confirm": False, "build_from_entry": False,
                "entry_role": "none", "note": "User wants it handled but nothing fits — create net-new."}
    if has_confident:
        return {**base, "decision": DEC_SUGGEST, "await_confirm": True, "build_from_entry": False,
                "entry_role": "suggested", "note": "User is unsure — suggest the entry + why, then let them decide."}
    return {**base, "decision": DEC_CREATE_NEW, "await_confirm": True, "build_from_entry": False,
            "entry_role": "none", "note": "User is unsure and nothing fits — propose net-new; await confirm."}


def flex_principle() -> dict:
    return {
        "core": "Every library entry is a GUIDE and a RESOURCE, never a rule. It assists; it never "
                "dominates the user's desire.",
        "always": "Overridable, mixable, customizable, ignorable. Never blocks authoring.",
    }


# --------------------------------------------------------------------------- #
# Tokenisation
# --------------------------------------------------------------------------- #
_STOPWORDS = {
    "a", "an", "the", "to", "for", "of", "and", "or", "my", "me", "i", "we", "our",
    "your", "you", "with", "in", "on", "at", "is", "are", "be", "want", "need", "write",
    "make", "create", "get", "into", "that", "this", "it", "so", "can", "will", "do",
    "have", "has", "email", "emails", "new", "please",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _tokens(text: str) -> list[str]:
    raw = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [t for t in raw if t not in _STOPWORDS and len(t) > 1]


def _tokset(text: str) -> set[str]:
    return set(_tokens(text))


def _dehyphen(text: str) -> str:
    return (text or "").replace("-", " ").replace("_", " ")


# Skill root (…/50-email-engine). Used to record a PORTABLE, repo-relative
# `source` in the built index so the committed artifact never leaks an operator
# absolute path (e.g. /Users/<name>/…). Fleet-wide repo rule: no machine paths.
_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _portable_source(catalog_index_path: str) -> str:
    """Repo-relative path to the catalog (falls back to basename if outside)."""
    ap = os.path.abspath(catalog_index_path)
    rel = os.path.relpath(ap, _SKILL_DIR)
    return rel if not rel.startswith("..") else os.path.basename(ap)


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #
class Catalog:
    """In-memory searchable index over the list-shaped catalog-index.json."""

    def __init__(self, entries: list[dict], source: str = ""):
        self.entries = entries
        self.source = source
        self.by_id = {e["id"]: e for e in entries}
        self.types = sorted({e["type"] for e in entries})

    @classmethod
    def load(cls, catalog_index_path: str) -> "Catalog":
        raw = json.load(open(catalog_index_path, encoding="utf-8"))
        rows = raw["entries"] if isinstance(raw, dict) and "entries" in raw else raw
        entries = [cls._normalise(r) for r in rows if isinstance(r, dict) and r.get("id")]
        entries.sort(key=lambda e: (e["type"], e["id"]))
        return cls(entries, source=_portable_source(catalog_index_path))

    @staticmethod
    def _normalise(r: dict) -> dict:
        tags = [str(t) for t in (r.get("tags") or [])]
        best = [str(b) for b in (r.get("best_for") or [])]
        name = r.get("name", "")
        bag = " ".join([name, _dehyphen(" ".join(tags)), _dehyphen(" ".join(best)),
                        _dehyphen(r.get("type", "")), _dehyphen(r.get("id", ""))])
        return {
            "id": r["id"], "type": r.get("type", ""), "name": name,
            "tags": tags, "length": r.get("length", ""), "best_for": best,
            "file": r.get("file", ""),
            "searchText": _norm(bag), "searchTokens": sorted(_tokset(bag)),
            "idWords": _norm(_dehyphen(r["id"])),
        }

    def to_index(self) -> dict:
        return {"generated_at": _ts(), "source": self.source, "entryCount": len(self.entries),
                "types": self.types, "entries": self.entries}

    def save_index(self, out_path: str) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        json.dump(self.to_index(), open(out_path, "w", encoding="utf-8"), indent=2)
        return out_path


# --------------------------------------------------------------------------- #
# Classify + score
# --------------------------------------------------------------------------- #
def classify(request: dict | str) -> dict:
    if isinstance(request, str):
        request = {"text": request}
    text_parts = [str(request.get(k, "")) for k in
                  ("text", "brief", "goal", "intent", "description", "ask")]
    text = _norm(_dehyphen(" ".join(p for p in text_parts if p)))
    return {
        "text": text,
        "tokens": _tokset(text),
        "type": _norm(str(request.get("type", ""))),
        "raw": request,
    }


def _phrase_hit(phrase: str, req_text: str, req_tokens: set[str]) -> float:
    phrase_n = _norm(_dehyphen(phrase))
    if not phrase_n:
        return 0.0
    if phrase_n in req_text:
        return 1.0
    ptoks = _tokset(phrase_n)
    if not ptoks:
        return 0.0
    if len(ptoks & req_tokens) / len(ptoks) >= 0.6:
        return 0.5
    return 0.0


def score_entry(e: dict, feats: dict) -> dict:
    req_text, req_tokens = feats["text"], feats["tokens"]
    parts: dict[str, float] = {}

    name_n = _norm(_dehyphen(e["name"]))
    if name_n and name_n in req_text:
        parts["name"] = _W_NAME
    # distinctive name tokens (e.g. "tony robbins", "before after bridge") — lets a
    # request that names the entry win even when the full parenthetical name differs.
    name_toks = _tokset(_dehyphen(e["name"])) - {"style", "version", "the", "plan"}
    nt = min(3.0, 1.5 * len(name_toks & req_tokens))
    if nt:
        parts["nametok"] = round(nt, 3)
    if e["idWords"] and e["idWords"] in req_text:
        parts["id"] = _W_ID

    tag_score = 0.0
    for tag in e["tags"]:
        h = _phrase_hit(tag, req_text, req_tokens)
        tag_score += _W_TAG_FULL if h == 1.0 else (_W_TAG_PART if h else 0.0)
    tag_score = min(_CAP_TAG, tag_score)
    if tag_score:
        parts["tags"] = round(tag_score, 3)

    best_tokens = _tokset(_dehyphen(" ".join(e["best_for"])))
    b = min(_CAP_BEST, _W_BEST * len(best_tokens & req_tokens))
    if b:
        parts["best_for"] = round(b, 3)

    if feats["type"] and feats["type"] == e["type"]:
        parts["type"] = _W_TYPE

    raw = sum(parts.values())
    return {"id": e["id"], "type": e["type"], "name": e["name"], "raw": round(raw, 3), "parts": parts}


def _confidence(raw: float) -> float:
    return max(0.0, min(1.0, raw / _CONF_DENOM))


# --------------------------------------------------------------------------- #
# Optional embedding reranker (SCAFFOLD — lexical path is the wired one)
# --------------------------------------------------------------------------- #
class EmbeddingReranker:
    """Semantic re-rank hook. Supply ``embed_fn(text)->vector`` (the shared prebuilt
    Gemini email index on the client's own key). Absent -> no-op; lexical stands alone."""

    def __init__(self, embed_fn: Callable[[str], list[float]] | None = None):
        self.embed_fn = embed_fn

    def available(self) -> bool:
        return self.embed_fn is not None

    def rerank(self, request_text: str, catalog: Catalog, candidates: list[dict],
               blend: float = 0.35) -> list[dict]:
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
            e = catalog.by_id[c["id"]]
            sem = cos(qv, self.embed_fn(e["searchText"]))
            c["semantic"] = round(sem, 4)
            c["confidence"] = round((1 - blend) * c["confidence"] + blend * sem, 4)
        candidates.sort(key=lambda c: (-c["confidence"], c["id"]))
        return candidates


# --------------------------------------------------------------------------- #
# Match
# --------------------------------------------------------------------------- #
def match_email(request: dict | str, catalog: Catalog, *,
                threshold: float = DEFAULT_THRESHOLD, top_k: int = 5,
                reranker: "EmbeddingReranker | None" = None,
                intent_mode: str | None = None) -> dict:
    if isinstance(request, str):
        request = {"text": request}

    explicit_id = request.get("explicit_entry") or ""
    mode_info = detect_mode(request, override=(MODE_EXPLICIT if explicit_id else intent_mode))
    mode = mode_info["mode"]

    feats = classify(request)
    # An explicit type is the caller's declared narrowing — a HARD filter (the user's
    # explicit desire wins). Absent, every entry is scored.
    candidates = catalog.entries
    if feats["type"] and feats["type"] in set(catalog.types):
        candidates = [e for e in catalog.entries if e["type"] == feats["type"]]
    scored = [score_entry(e, feats) for e in candidates]
    for s in scored:
        s["confidence"] = round(_confidence(s["raw"]), 4)
    scored.sort(key=lambda s: (-s["confidence"], -s["raw"], s["id"]))
    if reranker and reranker.available():
        scored = reranker.rerank(feats["text"], catalog, scored)

    ranked = scored[:top_k]
    best = ranked[0] if ranked else None
    has_any = bool(best and best["raw"] > 0)
    has_confident = bool(best and best["confidence"] >= threshold and best["raw"] > 0)

    if mode == MODE_EXPLICIT and explicit_id and explicit_id in catalog.by_id:
        matched_id = explicit_id
        has_any = has_confident = True
    else:
        matched_id = best["id"] if has_any else None

    flex = flex_decide(mode, has_confident=has_confident, has_any=has_any)
    entry = catalog.by_id.get(matched_id) if matched_id else None
    return {
        "decision": flex["decision"],
        "intent_mode": mode,
        "mode_reason": mode_info["reason"],
        "imposes_on_user": flex["imposes_on_user"],   # always False
        "override_allowed": flex["override_allowed"], # always True
        "await_confirm": flex["await_confirm"],
        "build_from_entry": flex["build_from_entry"],
        "entry_role": flex["entry_role"],
        "flex_note": flex["note"],
        "flex_principle": flex_principle(),
        "matched_id": matched_id,
        "matched_type": entry["type"] if entry else None,
        "matched_name": entry["name"] if entry else None,
        "matched_file": entry["file"] if entry else None,
        "confidence": (1.0 if (mode == MODE_EXPLICIT and explicit_id) else (best["confidence"] if best else 0.0)),
        "threshold": threshold,
        "score_parts": best["parts"] if best else {},
        "ranked": [{"id": r["id"], "type": r["type"], "name": r["name"],
                    "confidence": r["confidence"], "raw": r["raw"], "parts": r["parts"]} for r in ranked],
        "rationale": _rationale(mode, flex["decision"], best, threshold, flex),
        "request": request,
        "ts": _ts(),
    }


def _rationale(mode: str, decision: str, best: dict | None, threshold: float, flex: dict) -> str:
    bm = (f"best='{best['name']}' ({best['id']}) confidence={best['confidence']} (threshold {threshold})"
          if best else "no candidate scored")
    return f"mode={mode} -> decision={decision}. {bm}. {flex['note']}"


def log_decision(decision: dict, log_path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
    line = json.dumps({
        "ts": decision.get("ts", _ts()), "intent_mode": decision.get("intent_mode"),
        "decision": decision["decision"], "matched_id": decision.get("matched_id"),
        "confidence": decision.get("confidence"), "threshold": decision.get("threshold"),
        "request": decision.get("request"),
        "ranked": [(r["id"], r["confidence"]) for r in decision.get("ranked", [])[:3]],
    }, ensure_ascii=False)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    return log_path


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
