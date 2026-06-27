#!/usr/bin/env python3
"""automation_matcher.py — Flexible automation template matcher for Skill 44
(44-convert-and-flow-operator).

FLEXIBILITY FIRST — THIS IS THE PRIME DIRECTIVE
------------------------------------------------
This matcher is a GUIDE and a RESOURCE, never a rule or a gate.

  Mode 1 — Explicit desire:   User has stated what they want -> do exactly that.
                               This matcher is an optional reference only.
                               NEVER impose a suggestion or override user choice.

  Mode 2 — User is unsure:    Surface the best-matching templates + explain why
                               (trigger fit, category alignment, source rationale).
                               Let the user decide; present options, not mandates.

  Mode 3 — Just do it:        User says 'handle it' / 'build it' -> build the
                               highest-scoring template from this matcher's result.

EXPLICIT DESIRE RULE: if the request dict carries ``explicit_template`` (or the text
contains an unambiguous template name / alias), the matcher returns HONORED_EXPLICIT
immediately — it does NOT run scoring.  The caller MUST build what was named.

The matcher NEVER raises into the build loop (matching is advisory glue — a matcher
failure must not block an automation build). All errors return ``decision=SKIPPED``.

DESIGN
------
* stdlib-only, deterministic, no network.
* Catalog loader: reads the JSON templates from ``automation-templates/``.
  Handles both the direct category path and the root path.
* Lexical scorer with configurable threshold (default 0.55).
* Funnel-link hint: if the request provides ``funnel_id``, the matcher loads
  ``_links/funnel-to-automation-link-map.json`` and boosts templates that are
  listed as primary/supporting for that funnel.
* Output shape mirrors the Skill-6 funnel_matcher for easy agent integration.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
DEFAULT_THRESHOLD = 0.50          # confidence (0..1) to SUGGEST_TEMPLATE vs SUGGEST_CREATE
_CONF_DENOM = 7.0                 # raw-score -> confidence normaliser
_EXPLICIT_CONFIDENCE = 1.0        # confidence when an explicit template is named

# raw-score weights
_W_NAME = 7.0                     # exact template name in the request
_W_ALIAS = 5.0                    # alias match
_W_ID = 4.0                       # template id match
_W_CATEGORY = 3.0                 # category token overlap
_W_KW = 2.5                       # keyword phrase match
_W_TRIGGER = 1.5                  # trigger-event overlap
_W_SOURCE = 0.8                   # source/book token overlap
_W_FUNNEL_PRIMARY = 5.0           # funnel-link: listed as primary for the given funnel
_W_FUNNEL_SUPPORTING = 2.0        # funnel-link: listed as supporting
_W_ANTI = -4.0                    # anti-signal penalty

_STOPWORDS = {
    "a", "an", "the", "to", "for", "of", "and", "or", "my", "me", "i", "we", "our",
    "your", "you", "with", "in", "on", "at", "is", "are", "be", "want", "need",
    "build", "make", "create", "get", "into", "that", "this", "it", "so", "can",
    "will", "do", "have", "has", "email", "sequence", "automation", "workflow",
    "new", "send", "set", "up", "use", "run", "start", "add",
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


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --------------------------------------------------------------------------- #
# Catalog loader
# --------------------------------------------------------------------------- #
_CATEGORY_DIRS = [
    "welcome-indoctrination",
    "sales-close-sequences",
    "engagement-broadcast",
    "funnel-specific-followups",
    "multichannel-automation",
]


def _flatten(val: Any) -> str:
    """Recursively stringify any JSON value to plain text."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (int, float, bool)):
        return str(val)
    if isinstance(val, list):
        return " ".join(_flatten(v) for v in val)
    if isinstance(val, dict):
        return " ".join(_flatten(v) for v in val.values())
    return str(val)


def _norm_template(raw: dict) -> dict:
    """Normalize a raw JSON template to a common internal shape.

    Handles both schema dialects (camelCase and snake_case) and extracts
    as much descriptive text as possible for keyword scoring.
    """
    aliases = raw.get("aliases") or raw.get("alias") or []
    if isinstance(aliases, str):
        aliases = [aliases]

    # source text: string, or nested object with primary + supporting
    src = raw.get("source", raw.get("source_books", ""))
    if isinstance(src, dict):
        parts = [src.get("primary", "")]
        supporting = src.get("supporting", [])
        if isinstance(supporting, list):
            parts += supporting
        src = " ".join(str(p) for p in parts)
    elif isinstance(src, list):
        src = " ".join(str(p) for p in src)

    # trigger text from dict values
    trigger = raw.get("trigger", {})
    if isinstance(trigger, dict):
        trigger_text = " ".join(str(v) for v in trigger.values() if isinstance(v, (str, int)))
    else:
        trigger_text = str(trigger)

    # purpose / summary: try multiple field names (both schema dialects)
    # Use _flatten so dict values (like coreThesis being a dict) are safe
    purpose = _flatten(
        raw.get("purpose")
        or raw.get("summary")
        or raw.get("coreThesis")
        or raw.get("core_thesis")
        or ""
    )

    # Additional keyword text from cadence, rationale, kpis, framework
    extra_parts = []
    for key in ("cadence", "framework", "role_in_3_closes", "kpis",
                "integrity_guardrails", "faithfulness", "flexibility_principle",
                "differentFromSeinfeldEmail", "rotationStrategy",
                "subjectLineFamilies", "bodyFrameworkVariants"):
        val = raw.get(key)
        if val is not None:
            extra_parts.append(_flatten(val))

    # Also pull from copyPersona / copy_persona (name and description)
    cp = raw.get("copyPersona", raw.get("copy_persona", {}))
    if isinstance(cp, dict):
        extra_parts.append(_flatten(cp.get("primary", cp.get("persona", ""))))
    elif isinstance(cp, str):
        extra_parts.append(cp)

    # Alias text is also good keyword signal
    alias_text = " ".join(str(a) for a in aliases)

    desc_text = " ".join(s for s in [purpose, alias_text, _flatten(src), trigger_text]
                         + extra_parts if s)

    # Flexibility / faithfulness note
    flexibility = raw.get("flexibility", raw.get("faithfulness", {}))
    if isinstance(flexibility, dict):
        flex_note = flexibility.get("core_principle",
                    flexibility.get("guide_not_rule", str(flexibility)[:200]))
    else:
        flex_note = str(flexibility)[:300]

    return {
        "id": raw.get("id", ""),
        "name": raw.get("name", ""),
        "aliases": [str(a).lower().strip() for a in aliases],
        "category": raw.get("category", ""),
        "source_text": src,
        "trigger_text": trigger_text,
        "purpose": purpose,
        "desc_text": desc_text,
        "flexibility_note": flex_note,
        "_raw": raw,
    }


class AutomationCatalog:
    """Loads all automation templates from the library root."""

    def __init__(self) -> None:
        self.templates: list[dict] = []
        self.by_id: dict[str, dict] = {}

    @classmethod
    def load(cls, library_root: str) -> "AutomationCatalog":
        cat = cls()
        for cat_dir in _CATEGORY_DIRS:
            dirpath = os.path.join(library_root, cat_dir)
            if not os.path.isdir(dirpath):
                continue
            for fname in sorted(os.listdir(dirpath)):
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(dirpath, fname)
                try:
                    with open(fpath, encoding="utf-8") as f:
                        raw = json.load(f)
                    tmpl = _norm_template(raw)
                    if tmpl["id"]:
                        cat.templates.append(tmpl)
                        cat.by_id[tmpl["id"]] = tmpl
                except Exception:
                    pass
        return cat

    def load_links(self, links_path: str) -> dict:
        """Load the funnel-to-automation link map; return {} on any error."""
        try:
            with open(links_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}


# --------------------------------------------------------------------------- #
# Explicit-desire detection
# --------------------------------------------------------------------------- #
def _detect_explicit(text: str, catalog: AutomationCatalog) -> str | None:
    """Return a template id if the user has named a specific template explicitly.

    Checks (in order):
    1. Template id with hyphens replaced by spaces ("soap-opera-sequence" -> "soap opera sequence")
    2. Template id as-is (handles copy-paste of the literal id)
    3. Core template name tokens (first 3-4 significant words, ignoring parenthetical)
    4. Alias match — all aliases checked; short all-caps aliases (like 'SOS') allowed
    """
    norm_text = _norm(text)
    # 1. ID as space-separated words
    for tmpl in catalog.templates:
        id_as_words = tmpl["id"].replace("-", " ")
        if id_as_words in norm_text:
            return tmpl["id"]
    # 2. ID with hyphens as-is (less common in natural language but handle it)
    for tmpl in catalog.templates:
        if tmpl["id"] in norm_text:
            return tmpl["id"]
    # 3. Core name match: strip parenthetical, take first N tokens
    for tmpl in catalog.templates:
        raw_name = re.sub(r"\(.*?\)", "", tmpl["name"])
        core_tokens = [t for t in _tokens(raw_name) if len(t) > 2][:5]
        if len(core_tokens) >= 2:
            core_phrase = " ".join(core_tokens)
            if core_phrase in norm_text:
                return tmpl["id"]
    # 4. Alias match — allow all-caps short aliases (SOS, VSL, etc.)
    for tmpl in catalog.templates:
        for alias in tmpl["aliases"]:
            # Accept short aliases only if they were ALL-CAPS in the original JSON
            # (the loader already lowercases them, so we check the original raw alias)
            original_aliases = tmpl["_raw"].get("aliases", [])
            is_short_caps = any(
                a.strip() == a.strip().upper() and len(a.strip()) >= 2
                for a in original_aliases
                if _norm(a) == alias
            )
            if (len(alias) > 5 or is_short_caps) and alias in norm_text:
                return tmpl["id"]
    return None


# --------------------------------------------------------------------------- #
# Scorer
# --------------------------------------------------------------------------- #
def _score_one(tmpl: dict, req: dict, funnel_primaries: set[str],
               funnel_supporting: set[str]) -> dict:
    text_tokens = req["tokens"]
    parts: dict[str, float] = {}

    # Name match
    name_tokens = _content_tokens(tmpl["name"])
    overlap = len(text_tokens & name_tokens)
    if overlap:
        w = _W_NAME * (overlap / max(len(name_tokens), 1))
        parts["name"] = round(w, 3)

    # Alias match
    for alias in tmpl["aliases"]:
        if alias in req["norm_text"]:
            parts["alias"] = parts.get("alias", 0) + _W_ALIAS
            break

    # ID match
    if tmpl["id"].replace("-", " ") in req["norm_text"] or tmpl["id"] in req["norm_text"]:
        parts["id_match"] = _W_ID

    # Category match
    cat_tokens = _content_tokens(tmpl["category"])
    cat_overlap = len(text_tokens & cat_tokens)
    if cat_overlap:
        parts["category"] = round(_W_CATEGORY * (cat_overlap / max(len(cat_tokens), 1)), 3)

    # Keyword / desc match — use the richer desc_text (purpose + aliases + cadence + etc.)
    desc_tokens = _content_tokens(tmpl.get("desc_text", "") or tmpl["purpose"])
    kw_overlap = len(text_tokens & desc_tokens)
    if kw_overlap:
        score = min(_W_KW * kw_overlap / max(len(desc_tokens), 1), _W_KW * 1.5)
        parts["keyword"] = round(score, 3)

    # Alias token overlap (aliases are often the most discriminating signal)
    alias_blob = " ".join(tmpl["aliases"])
    alias_tokens = _content_tokens(alias_blob)
    alias_overlap = len(text_tokens & alias_tokens)
    if alias_overlap:
        score = min(_W_ALIAS * alias_overlap / max(len(alias_tokens), 1), _W_ALIAS)
        parts["alias_overlap"] = round(score, 3)

    # Trigger text match
    trigger_tokens = _content_tokens(tmpl["trigger_text"])
    tr_overlap = len(text_tokens & trigger_tokens)
    if tr_overlap:
        score = min(_W_TRIGGER * tr_overlap / max(len(trigger_tokens), 1), _W_TRIGGER)
        parts["trigger"] = round(score, 3)

    # Source book match
    source_tokens = _content_tokens(tmpl["source_text"])
    src_overlap = len(text_tokens & source_tokens)
    if src_overlap:
        score = min(_W_SOURCE * src_overlap / max(len(source_tokens), 1), _W_SOURCE)
        parts["source"] = round(score, 3)

    # Funnel-link boost
    tid = tmpl["id"]
    cat_key = f"{tmpl['category']}/{tid}"
    if cat_key in funnel_primaries or tid in funnel_primaries:
        parts["funnel_link_primary"] = _W_FUNNEL_PRIMARY
    elif cat_key in funnel_supporting or tid in funnel_supporting:
        parts["funnel_link_supporting"] = _W_FUNNEL_SUPPORTING

    raw = sum(parts.values())
    confidence = min(raw / _CONF_DENOM, 1.0)
    return {"id": tid, "name": tmpl["name"], "category": tmpl["category"],
            "raw": raw, "confidence": round(confidence, 4), "parts": parts}


# --------------------------------------------------------------------------- #
# Main match function
# --------------------------------------------------------------------------- #
def match_automation(
    request: dict | str,
    catalog: AutomationCatalog,
    *,
    links: dict | None = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict:
    """Match a request against the automation catalog.

    FLEXIBILITY: If the request carries ``explicit_template`` or the free-text
    unambiguously names a template, returns ``decision=HONORED_EXPLICIT`` without
    scoring — the caller MUST build what was named.

    Args:
        request: dict with keys ``text``, ``category``, ``funnel_id``,
                 ``explicit_template`` (all optional); OR a plain string.
        catalog:  loaded AutomationCatalog.
        links:    loaded funnel-to-automation link map (from _links/ dir).
        threshold: confidence floor for SUGGEST_TEMPLATE vs SUGGEST_CREATE.

    Returns a dict with:
        decision:              HONORED_EXPLICIT | SUGGEST_TEMPLATE | SUGGEST_CREATE | SKIPPED
        flexibility_mode:      1 | 2 | 3 (which flexibility mode drove the result)
        matched_template:      id or None
        matched_name:          str or None
        confidence:            float
        threshold:             float
        score_parts:           dict
        ranked:                list of top candidates
        rationale:             human-readable explanation
        funnel_link:           the funnel's primary/supporting automations from the link map
        ts:                    ISO timestamp
    """
    if not catalog.templates:
        return {"decision": "SKIPPED", "reason": "catalog is empty", "ts": _ts()}

    if isinstance(request, str):
        request = {"text": request}

    # EXPLICIT DESIRE CHECK (Mode 1 / flexibility gate)
    explicit_id = request.get("explicit_template") or ""
    if not explicit_id:
        explicit_id = _detect_explicit(request.get("text", ""), catalog) or ""

    if explicit_id:
        tmpl = catalog.by_id.get(explicit_id)
        if tmpl:
            return {
                "decision": "HONORED_EXPLICIT",
                "flexibility_mode": 1,
                "matched_template": explicit_id,
                "matched_name": tmpl["name"],
                "confidence": _EXPLICIT_CONFIDENCE,
                "threshold": threshold,
                "score_parts": {},
                "ranked": [{"id": explicit_id, "name": tmpl["name"],
                             "confidence": _EXPLICIT_CONFIDENCE, "raw": 999, "parts": {}}],
                "rationale": (
                    f"User explicitly named '{tmpl['name']}' — building exactly that. "
                    "This matcher honors explicit user desire above all scoring. "
                    "No template suggestion overrides this choice."
                ),
                "funnel_link": None,
                "request": request if isinstance(request, dict) else {"text": request},
                "ts": _ts(),
            }

    # Build feature dict
    text = request.get("text", "")
    norm_text = _norm(text)
    tokens = _content_tokens(text)
    funnel_id = request.get("funnel_id", "")

    req_feats = {
        "norm_text": norm_text,
        "tokens": tokens,
        "category_hint": _norm(request.get("category", "")),
        "funnel_id": funnel_id,
    }

    # Funnel-link hints
    funnel_link_data = None
    funnel_primaries: set[str] = set()
    funnel_supporting: set[str] = set()

    if funnel_id and links:
        for group_data in links.values():
            if isinstance(group_data, dict) and not group_data.get("_meta"):
                entry = group_data.get(funnel_id)
                if entry:
                    funnel_link_data = entry
                    funnel_primaries = set(entry.get("primary_automations", []))
                    funnel_supporting = set(entry.get("supporting_automations", []))
                    break

    # Score all templates
    scored = [_score_one(t, req_feats, funnel_primaries, funnel_supporting)
              for t in catalog.templates]
    scored.sort(key=lambda x: (-x["confidence"], -x["raw"], x["id"]))

    best = scored[0] if scored else None
    decision = "SUGGEST_CREATE"
    matched_id = None
    just_do_it = bool(request.get("just_do_it"))
    flex_mode = 2  # unsure by default

    if best and best["confidence"] >= threshold:
        decision = "SUGGEST_TEMPLATE"
        matched_id = best["id"]
        flex_mode = 3 if just_do_it else 2

    # Mode-3 shortcut: if just_do_it + funnel link primary exists, use the first primary
    # even if the general scorer chose something else (funnel architect knows the canonical chain)
    if just_do_it and funnel_link_data and decision == "SUGGEST_TEMPLATE":
        primaries = funnel_link_data.get("primary_automations", [])
        if primaries:
            # Resolve the first primary template id (strip category/ prefix)
            first_primary = primaries[0].split("/")[-1]
            if first_primary in catalog.by_id:
                matched_id = first_primary
                # Find and promote that score entry
                for s in scored:
                    if s["id"] == first_primary:
                        best = s
                        break

    rationale = _build_rationale(best, threshold, decision, flex_mode)

    return {
        "decision": decision,
        "flexibility_mode": flex_mode,
        "matched_template": matched_id,
        "matched_name": catalog.by_id[matched_id]["name"] if matched_id else None,
        "confidence": best["confidence"] if best else 0.0,
        "threshold": threshold,
        "score_parts": best["parts"] if best else {},
        "ranked": [{"id": r["id"], "name": r["name"], "category": r["category"],
                    "confidence": r["confidence"], "raw": r["raw"],
                    "parts": r["parts"]} for r in scored[:5]],
        "rationale": rationale,
        "funnel_link": funnel_link_data,
        "request": request if isinstance(request, dict) else {"text": request},
        "ts": _ts(),
    }


def _build_rationale(best: dict | None, threshold: float, decision: str,
                     flex_mode: int) -> str:
    flex_preamble = (
        "This matcher is a GUIDE and a RESOURCE, never a rule. "
        "Every suggestion is overridable — the user's explicit desire always wins."
    )
    if not best or best["raw"] <= 0:
        return (
            f"{flex_preamble} No template scored above zero — SUGGEST_CREATE: "
            "a new automation can be built from scratch and optionally saved to the library."
        )
    drivers = ", ".join(
        f"{k}(+{v:.2f})" if v >= 0 else f"{k}({v:.2f})"
        for k, v in sorted(best["parts"].items(), key=lambda kv: -abs(kv[1]))
    )
    if decision == "SUGGEST_TEMPLATE":
        return (
            f"{flex_preamble} Best match: '{best['name']}' "
            f"(confidence={best['confidence']:.2f} >= threshold {threshold}). "
            f"Score drivers: {drivers}. "
            "If the user prefers a different template or wants a custom automation, "
            "do exactly what they say — this is a suggestion, not a requirement."
        )
    return (
        f"{flex_preamble} Best candidate: '{best['name']}' "
        f"(confidence={best['confidence']:.2f} < threshold {threshold}) -> SUGGEST_CREATE. "
        f"Score drivers: {drivers}. "
        "A custom automation can be built and optionally saved back to the library."
    )


# --------------------------------------------------------------------------- #
# Step 0 wiring (called before Skill-44 builds an automation)
# --------------------------------------------------------------------------- #
def step0_match(
    task: dict,
    evidence_root: str,
    *,
    library_root: str | None = None,
    links_path: str | None = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict:
    """STEP 0 of the automation build flow.

    Build a request from the board task, match it against the catalog, LOG the
    decision, write ``routing/automation-match.json``, and MUTATE the task so the
    builder is template-first:

      HONORED_EXPLICIT   -> task['automation_template'] = the named template id;
                            task['automation_match'] records the decision.
      SUGGEST_TEMPLATE   -> task['automation_template'] = matched id (caller
                            presents to user for confirmation unless just_do_it).
      SUGGEST_CREATE     -> task['automation_match'] records SUGGEST_CREATE;
                            builder generates custom; caller can save_new_automation.

    Returns the decision record. Never raises into the build loop.

    FLEXIBILITY NOTE: this function is ADVISORY GLUE. A failure here MUST NOT
    block an automation build. The task is mutated only with a ``suggestion`` —
    the agent MUST present this to the user (Mode 2) or execute it as-is only
    when the user has said 'just do it' (Mode 3) or named the template (Mode 1).
    """
    try:
        # Resolve library root
        root = library_root or os.environ.get("CAF_AUTOMATION_LIBRARY", "")
        if not root:
            # Heuristic: look relative to this file
            here = os.path.dirname(os.path.abspath(__file__))
            candidate = os.path.normpath(os.path.join(here, ".."))
            if os.path.isdir(os.path.join(candidate, "welcome-indoctrination")):
                root = candidate
            else:
                return {"decision": "SKIPPED",
                        "reason": "no library root (set CAF_AUTOMATION_LIBRARY)",
                        "ts": _ts()}

        catalog = AutomationCatalog.load(root)
        if not catalog.templates:
            return {"decision": "SKIPPED", "reason": "catalog loaded but empty", "ts": _ts()}

        # Load links
        lp = links_path or os.path.join(root, "_links", "funnel-to-automation-link-map.json")
        links = catalog.load_links(lp)

        request = {
            "text": task.get("brief", "") or task.get("text", "") or task.get("description", ""),
            "category": task.get("automation_category", task.get("category", "")),
            "funnel_id": task.get("funnel_id", task.get("funnel_template_id", "")),
            "explicit_template": task.get("automation_template", ""),
            "just_do_it": bool(task.get("just_do_it")),
        }

        decision = match_automation(request, catalog, links=links, threshold=threshold)

        # Persist
        routing = os.path.join(evidence_root, "routing")
        os.makedirs(routing, exist_ok=True)
        with open(os.path.join(routing, "automation-match.json"), "w", encoding="utf-8") as f:
            json.dump(decision, f, indent=2, ensure_ascii=False)
        _log_decision(decision, os.path.join(routing, "automation-decisions.jsonl"))

        # Mutate task (advisory only)
        task["automation_match"] = {
            "decision": decision["decision"],
            "flexibility_mode": decision["flexibility_mode"],
            "matched_template": decision["matched_template"],
            "confidence": decision["confidence"],
            "rationale": decision["rationale"],
        }
        if decision["decision"] in ("HONORED_EXPLICIT", "SUGGEST_TEMPLATE"):
            task.setdefault("automation_template_suggestion", decision["matched_template"])

        return decision
    except Exception as exc:  # noqa: BLE001 — matching must never block a build
        return {"decision": "SKIPPED",
                "reason": f"matcher error: {type(exc).__name__}: {exc}",
                "ts": _ts()}


def _log_decision(decision: dict, log_path: str) -> None:
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        line = json.dumps({
            "ts": decision.get("ts", _ts()),
            "decision": decision["decision"],
            "flexibility_mode": decision.get("flexibility_mode"),
            "matched_template": decision.get("matched_template"),
            "confidence": decision.get("confidence"),
            "threshold": decision.get("threshold"),
            "rationale": decision.get("rationale"),
            "request": decision.get("request"),
            "ranked": [(r["id"], r["confidence"])
                       for r in decision.get("ranked", [])[:3]],
        }, ensure_ascii=False)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Save-back (grow the library after SUGGEST_CREATE)
# --------------------------------------------------------------------------- #
def save_new_automation(spec: dict, library_root: str, *,
                        category: str | None = None) -> dict:
    """Persist a custom automation as a new template in the library.

    ``spec`` must contain at minimum ``name`` and ``id``. Everything else is
    optional but should follow the template schema for compatibility with the
    matcher and the Skill-44 builder.

    Returns ``{path, id, category}``.
    """
    name = spec.get("name") or "New Automation"
    aid = spec.get("id") or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    cat = category or spec.get("category") or "_generated"
    cat_dir = os.path.join(library_root, cat)
    os.makedirs(cat_dir, exist_ok=True)

    out = {
        "id": aid,
        "name": name,
        "aliases": spec.get("aliases", []),
        "category": cat,
        "summary": spec.get("summary", spec.get("purpose", "")),
        "trigger": spec.get("trigger", {}),
        "channels": spec.get("channels", []),
        "sequence": spec.get("sequence", []),
        "source": spec.get("source", "custom — saved back by automation_matcher"),
        "flexibility": {
            "core_principle": (
                "This template is a GUIDE and a RESOURCE, never a rule or requirement. "
                "It must not dominate the user's desire."
            ),
            "usage_modes": {
                "mode_1_explicit_desire": "User has an explicit desire: do exactly what the user wants.",
                "mode_2_unsure": "User is unsure: suggest this template and explain why; let the user decide.",
                "mode_3_just_do_it": "User wants it handled: build from this template.",
            },
            "always": (
                "Overridable, mixable, customizable, ignorable at every level. "
                "The template assists; it never dominates."
            ),
        },
        "ghl_build": spec.get("ghl_build", {}),
        "origin": "SUGGEST_CREATE (saved back by automation_matcher)",
        "generated_at": _ts(),
    }

    path = os.path.join(cat_dir, f"{aid}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    return {"path": path, "id": aid, "category": cat}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _cli() -> None:
    import argparse

    ap = argparse.ArgumentParser(
        description="automation_matcher — Skill-44 flexible automation template matcher"
    )
    ap.add_argument("--library", default=os.environ.get("CAF_AUTOMATION_LIBRARY", ""),
                    help="Path to automation-templates/ directory")
    ap.add_argument("--links", default="",
                    help="Path to funnel-to-automation-link-map.json")
    ap.add_argument("--match", metavar="TEXT",
                    help="Match a request text against the catalog")
    ap.add_argument("--funnel-id", default="",
                    help="Funnel template id to include link-map hints")
    ap.add_argument("--explicit", default="",
                    help="Explicitly name a template (tests Mode 1 honored-explicit path)")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                    help=f"Confidence threshold (default {DEFAULT_THRESHOLD})")
    ap.add_argument("--list", action="store_true",
                    help="List all templates in the catalog")
    ap.add_argument("--selftest", action="store_true",
                    help="Run built-in self-test cases")
    args = ap.parse_args()

    root = args.library
    if not root:
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.normpath(os.path.join(here, ".."))

    catalog = AutomationCatalog.load(root)

    lp = args.links or os.path.join(root, "_links", "funnel-to-automation-link-map.json")
    links = catalog.load_links(lp)

    if args.list:
        for t in catalog.templates:
            print(f"  {t['category']}/{t['id']}")
            print(f"    {t['name']}")
        print(f"\nTotal: {len(catalog.templates)} templates")
        return

    if args.selftest:
        _selftest(catalog, links, args.threshold)
        return

    if args.match:
        req = {"text": args.match, "funnel_id": args.funnel_id,
               "explicit_template": args.explicit}
        result = match_automation(req, catalog, links=links, threshold=args.threshold)
        print(json.dumps({
            "decision": result["decision"],
            "flexibility_mode": result.get("flexibility_mode"),
            "matched_template": result["matched_template"],
            "matched_name": result["matched_name"],
            "confidence": result["confidence"],
            "rationale": result["rationale"],
            "top3": [(r["id"], r["confidence"]) for r in result["ranked"][:3]],
        }, indent=2, ensure_ascii=False))
        return

    ap.print_help()


# --------------------------------------------------------------------------- #
# Self-test
# --------------------------------------------------------------------------- #
_SELFTEST_CASES = [
    # (description, request, expected_decision, expected_template_contains)
    ("Explicit soap opera sequence by name",
     {"text": "build me a soap opera sequence", "funnel_id": ""},
     "HONORED_EXPLICIT", "soap-opera-sequence"),

    ("Explicit by alias SOS",
     {"text": "I want the SOS bonding emails", "funnel_id": ""},
     "HONORED_EXPLICIT", "soap-opera"),

    ("Webinar follow-up from funnel link (webinar-funnel)",
     {"text": "follow up emails after the webinar", "funnel_id": "webinar-funnel"},
     "SUGGEST_TEMPLATE", "webinar"),

    ("Cart abandon recovery for buyer funnel",
     {"text": "recover abandoned carts with multichannel messages", "funnel_id": ""},
     "SUGGEST_TEMPLATE", "abandoned-cart"),

    ("Application booking nurture",
     {"text": "nurture leads after they apply for my coaching program and get them to book a call", "funnel_id": "application"},
     "SUGGEST_TEMPLATE", "application"),

    ("Seinfeld daily broadcast",
     {"text": "daily entertainment emails about nothing that sell at the end", "funnel_id": ""},
     "SUGGEST_TEMPLATE", "seinfeld"),

    ("Membership stick and retention",
     {"text": "keep my membership members from cancelling", "funnel_id": "membership-continuity"},
     "SUGGEST_TEMPLATE", "membership"),

    ("Cold traffic — behavioral retargeting",
     {"text": "retarget page visitors who did not opt in with SMS and desktop push", "funnel_id": "cold-traffic-article-preframe"},
     "SUGGEST_TEMPLATE", "retargeting"),

    ("Explicit override — user names non-default template",
     {"text": "I want the scarcity deadline close emails for my webinar", "funnel_id": "webinar-funnel"},
     "HONORED_EXPLICIT", "scarcity-deadline-close"),

    ("Vague request — no strong match",
     {"text": "emails", "funnel_id": ""},
     None, None),  # any decision acceptable — just must not crash

    ("Mode 3 just_do_it flag",
     {"text": "welcome new subscribers", "funnel_id": "squeeze-page", "just_do_it": True},
     "SUGGEST_TEMPLATE", "soap-opera"),

    ("Funnel link primary boost — application funnel",
     {"text": "follow up automation for application funnel", "funnel_id": "application"},
     "SUGGEST_TEMPLATE", "application"),
]


def _selftest(catalog: AutomationCatalog, links: dict, threshold: float) -> None:
    print(f"Running {len(_SELFTEST_CASES)} self-test cases...")
    passed = 0
    failed = 0
    for desc, req, expected_decision, expected_id_fragment in _SELFTEST_CASES:
        result = match_automation(req, catalog, links=links, threshold=threshold)
        decision = result["decision"]
        matched = result.get("matched_template") or ""

        ok_decision = (expected_decision is None or decision == expected_decision)
        ok_match = (expected_id_fragment is None or
                    (matched and expected_id_fragment in matched))
        ok = ok_decision and ok_match and decision != "SKIPPED"

        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"  [{status}] {desc}")
        if not ok:
            print(f"         expected decision={expected_decision!r} id_contains={expected_id_fragment!r}")
            print(f"         got     decision={decision!r} matched={matched!r}")

    print(f"\n{passed}/{len(_SELFTEST_CASES)} PASS, {failed} FAIL")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    _cli()
