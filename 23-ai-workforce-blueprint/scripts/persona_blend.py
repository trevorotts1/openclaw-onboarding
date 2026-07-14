#!/usr/bin/env python3
"""
persona_blend.py — voice-first AUDIENCE+TOPIC blend matcher (Skill 23, W7).

THE APPROVED DESIGN (operator-confirmed 2026-07-08)
---------------------------------------------------
For ANY content / communication job (email, social, podcast, blog, newsletter,
landing page, video, ad copy, …) the matcher decides the VOICE **first**:

  VOICE = an AUDIENCE persona blended with a TOPIC persona.
      • write in the AUDIENCE persona's voice (style-inspired only),
      • carrying the TOPIC persona's expertise on the job's subject.
  If ONE persona covers BOTH the audience and the topic → COLLAPSE to that one.
  The job is then decomposed into UP TO 10 TASK personas (one per distinct
  part); the topic persona may double as task guidance.

There is NO static "voice library". EVERY persona is characterised in the Skill
22 catalog (persona-categories.json) by additive fields — audiences[], topics[],
voice_style{}, usable_as[] (subset of [audience, topic, task]; DEFAULT when
absent = [topic, task] — serving as an AUDIENCE voice must be explicit) — and
this module reasons over the WHOLE catalog via those tags, emitting a stated
*why* per pick. The catalog grows constantly; the matcher never hard-codes ids.

AUDIENCE is resolved from the client's onboarding ICP (company-config.json via
ENV OPENCLAW_COMPANY_CONFIG / OPENCLAW_COMPANY_SLUG + SOUL.md), but we ALWAYS
confirm the audience before writing (clients have multiple audiences) and ASK
"What audience are we dealing with?" when unsure. `confirm_required` gates the
downstream write; on an operator change (OPENCLAW_AUDIENCE) we re-score the
voice and re-emit the bundle. We never fabricate an audience.

Voices are STYLE-INSPIRED, NEVER impersonation — a MANDATORY, non-removable
guardrail clause rides on every blend_directive (GUARDRAIL_CLAUSE below).

OUTPUT — the persona-bundle SUPERSET (see build_bundle). It is a strict superset
of persona-selector-v2.py's single-persona result: the resolved VOICE persona is
mirrored on the top-level persona_id / persona_name / score / task_category /
funnel keys so EXISTING consumers keep working unchanged, and the new blend keys
(topic, resolved_audience, confirm_required, voice, blend_directive,
task_personas, rationale, fallbacks) are added alongside.

Back-compat: on a catalog that still lacks the new tags (schema 1.2) the audience
matcher yields no audience persona and the topic persona falls back to the
existing 5-layer semantic selector — a valid, degraded-but-honest bundle. On a
mechanical / non-content task the audience blend is skipped (never-naked
governance pointer preserved).

This module is imported BY PATH by persona-selector-v2.py (hyphenated filenames
cannot be `import`ed) and is also directly unit-tested (hermetic — the selector /
decompose functions it calls are monkeypatched in the test, so it never reads or
writes a live persona DB).
"""
import importlib.util
import os
import re
from pathlib import Path

_HERE = Path(__file__).resolve().parent

# ── The MANDATORY, non-removable anti-impersonation guardrail ─────────────────
# Every blend_directive MUST carry this verbatim. build_blend_directive appends
# it unconditionally; the CC renderer is fail-closed on its absence. Persona
# voices are a STYLE, never a claim to BE the author.
GUARDRAIL_CLAUSE = (
    "STYLE-INSPIRED, NEVER IMPERSONATION (mandatory, non-removable): adopt the "
    "cadence, devices and register of the named voice(s) as an INSPIRATION only. "
    "Never claim to be the author, never write in their first person as if they "
    "authored this, never sign as them, never quote them as if verified, and "
    "never imply their endorsement. This clause may not be removed or weakened."
)

# The exact question we ASK when the audience is unknown / ambiguous.
AUDIENCE_CONFIRM_PROMPT = "What audience are we dealing with?"

# usable_as enum + the design default when the field is absent.
USABLE_AS_ENUM = ("audience", "topic", "task")
USABLE_AS_DEFAULT = ("topic", "task")

# Content / communication intent — the job families the audience-voice blend is
# for. A task that hits none of these is treated as a NON-CONTENT task: the blend
# still runs (topic expertise + task decomposition) but no audience voice gates
# the write (backward-compatible for non-content tasks).
#
# Signals are split into WORDS and PHRASES so they are matched WORD-WISE, never as
# a raw substring. The old substring test flagged ops tasks as content because a
# short signal appeared INSIDE an unrelated word ('ad' in read/download/admin/
# grade/headshot, 'post' in compost, 'story' in history), wrongly gating writes.
#   • _CONTENT_WORDS  — single-word signals matched against the task's TOKEN set
#     (or a token's light stem: 'posts'→'post', 'ads'→'ad'). 'ad'/'dm'/'post'/
#     'copy'/'hook'/'bio'/'reel'/'short'/'slide'/'deck' live here ONLY.
#   • _CONTENT_PHRASES — multi-word / hyphenated signals matched as a space-bounded
#     substring (specific enough that a bounded substring is safe).
_CONTENT_WORDS = frozenset({
    "email", "newsletter", "broadcast", "blast", "sequence",
    "social", "post", "caption", "tweet", "thread", "reel", "story",
    "instagram", "facebook", "linkedin", "tiktok", "youtube",
    "podcast", "episode", "script", "voiceover", "vsl",
    "blog", "article", "essay",
    "ad", "advert", "advertisement", "headline", "hook",
    "copy", "copywriting", "bio",
    "video", "short", "carousel", "slide", "deck", "webinar",
    "write", "draft", "rewrite", "ghostwrite", "compose", "pitch",
    "message", "dm", "outreach", "nurture", "announcement",
})
_CONTENT_PHRASES = (
    "e-mail", "x post", "show notes", "op-ed", "guest post",
    "landing page", "sales page", "sales letter", "opt-in", "lead magnet",
    "ad copy", "web copy", "about page",
)

# Stopwords stripped before tag/query token overlap.
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "at",
    "by", "from", "as", "is", "are", "be", "was", "were", "this", "that", "these",
    "those", "it", "its", "our", "your", "their", "we", "you", "they", "i", "me",
    "my", "us", "them", "who", "what", "which", "how", "write", "create", "make",
    "build", "draft", "please", "help", "need", "want", "about", "into", "out",
    "up", "new", "one", "get", "got", "will", "can", "do", "does", "some", "any",
    "more", "most", "each", "per", "via", "using", "use", "should", "could",
}


# ── module loaders (hyphenated selector/decompose filenames) ──────────────────
_SEL = None
_DT = None


def _load_by_path(filename: str, modname: str):
    path = _HERE / filename
    spec = importlib.util.spec_from_file_location(modname, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def _selector():
    """Lazily load persona-selector-v2.py as a module (cached)."""
    global _SEL
    if _SEL is None:
        _SEL = _load_by_path("persona-selector-v2.py", "persona_selector_v2_blend")
    return _SEL


def _decompose():
    """Lazily load decompose-task.py as a module (cached)."""
    global _DT
    if _DT is None:
        _DT = _load_by_path("decompose-task.py", "decompose_task_blend")
    return _DT


# ── tag / query tokenisation + overlap ────────────────────────────────────────
def _tokens(text) -> set:
    """Lowercase content-token set (drops stopwords + <3-char noise)."""
    if not text:
        return set()
    raw = re.split(r"[^a-z0-9]+", str(text).lower())
    return {t for t in raw if len(t) >= 3 and t not in _STOP}


def _stem(tok: str) -> str:
    """Light singular/gerund stemmer so budget/budgeting, funnel/funnels,
    entrepreneur/entrepreneurs, market/marketing all match. Deterministic."""
    if len(tok) > 5 and tok.endswith("ing"):
        return tok[:-3]
    if len(tok) > 4 and tok.endswith("es"):
        return tok[:-2]
    if len(tok) > 3 and tok.endswith("s"):
        return tok[:-1]
    return tok


# Stemmed content-word signals, so a plural/gerund token still matches its base
# ('posts'→'post', 'reels'→'reel', 'ads'→'ad'). Computed once _stem is defined.
_CONTENT_WORD_STEMS = frozenset(_stem(w) for w in _CONTENT_WORDS)


def _tag_hit(query_tokens: set, tags) -> tuple:
    """Overlap of a query-token set against a persona's list of hyphenated tags.

    Matches on shared STEMS (budget↔budgeting, funnel↔funnels) and on substring
    containment for long tokens (>=5 chars), so plural/gerund/compound drift does
    not silently miss a real signal.

    Returns (hit_count, matched_tags_sorted, matched_tokens_sorted):
      hit_count    = number of DISTINCT query tokens matched somewhere in the tags
      matched_tags = the tags that matched at least one query token
    Deterministic; no external state.
    """
    if not query_tokens or not tags:
        return 0, [], []
    # stem -> original query token (first wins for a stable label)
    qstems = {}
    for q in query_tokens:
        qstems.setdefault(_stem(q), q)
    matched_orig = set()
    matched_tags = []
    for t in tags:
        toks = [x for x in re.split(r"[^a-z0-9]+", str(t).lower()) if x]
        hit = False
        for x in toks:
            xs = _stem(x)
            if xs in qstems:
                matched_orig.add(qstems[xs])
                hit = True
                continue
            # P4-01 fix: the substring-containment nudge is documented (and
            # intended) as a "long tokens (>=5 chars)" fallback for compound/
            # drift matches (e.g. 'copywriting' <-> 'copywriter'). Before this
            # fix only the QUERY-side stem (`st`) was length-gated — a SHORT
            # tag-side token (`xs`), e.g. 'a'/'b' from the tag 'a-b-testing' or
            # 'hr' from 'hr-leaders', is a trivial substring of almost any long
            # query stem ('a' in 'persuasive', 'hr' in 'other'), so those tags
            # silently won matches against semantically-unrelated queries across
            # the whole catalog (measured: 84 of 99 personas' audience/topic tags
            # carry a <=2-char hyphen-split token). Gating BOTH sides at >=5
            # restores the documented "long tokens" contract with no loss of the
            # legitimate compound-drift matches (those are exact-length stems on
            # both sides already, e.g. 'copywriting'/'copywriter' are len>=10).
            if len(xs) < 5:
                continue
            for st, orig in qstems.items():
                if len(st) >= 5 and (st in xs or xs in st):
                    matched_orig.add(orig)
                    hit = True
        if hit:
            matched_tags.append(t)
    return len(matched_orig), sorted(set(matched_tags)), sorted(matched_orig)


# ── catalog load + validation ─────────────────────────────────────────────────
def load_catalog(paths: dict) -> dict:
    """Load persona-categories.json. Returns {} when absent/unreadable.

    Honors ENV OPENCLAW_PERSONA_CATEGORIES as an explicit path override (used by
    tests and by callers that point at an enriched catalog directly); otherwise
    reads paths['persona_categories'].
    """
    import json
    override = os.environ.get("OPENCLAW_PERSONA_CATEGORIES", "").strip()
    if override:
        pc = Path(override)
    else:
        pc = paths.get("persona_categories") if paths else None
        pc = Path(pc) if pc else None
    if not pc or not pc.exists():
        return {}
    try:
        data = json.loads(pc.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _persona_meta(catalog: dict) -> dict:
    p = catalog.get("personas") if isinstance(catalog, dict) else None
    if isinstance(p, dict):
        return p
    if isinstance(p, list):
        out = {}
        for d in p:
            if isinstance(d, dict) and (d.get("id") or d.get("name")):
                out[d.get("id") or d.get("name")] = d
        return out
    return {}


def _usable_as(pinfo: dict) -> tuple:
    ua = pinfo.get("usable_as")
    if isinstance(ua, list) and ua:
        return tuple(x for x in ua if x in USABLE_AS_ENUM)
    return USABLE_AS_DEFAULT


def validate_catalog_tags(catalog: dict) -> dict:
    """Validate the additive tag layer of an enriched (schema >=1.3) catalog.

    Checks, per persona:
      • audiences[] ⊆ top-level audienceTags vocab (when that vocab is present)
      • topics[]    ⊆ top-level topicTags vocab   (when that vocab is present)
      • usable_as[] ⊆ USABLE_AS_ENUM
      • voice_style has the required `summary` when voice_style is present
      • emotional_register ⊆ top-level emotionalRegisterTags vocab (schema 1.4,
        A-U3 — when that vocab is present; same subset-of-controlled-vocab
        pattern as audiences ⊆ audienceTags above, one string per persona)
      • audience_resonance ⊆ top-level audienceResonanceTags vocab (schema 1.4,
        A-U3 — same pattern)
      • conversion_style   ⊆ top-level conversionStyleTags vocab (schema 1.4,
        A-U3 — same pattern; the operator-pinned canonical set is
        story-close/stack-close/logic-close/invitation-close/challenge-close,
        shipped as DATA in the catalog's conversionStyleTags, never hard-coded
        here, so the vocab stays a one-place edit like every other tag family)

    On a pre-enrichment catalog (schema 1.2 — no audienceTags/topicTags/enriched
    personas) this is a NO-OP that returns ok=True with note='pre-enrichment', so
    wiring it into a gate never turns a 1.2 box RED. A schema-1.3 catalog that
    predates the A-U3 fields is likewise unaffected — the three new checks below
    degrade to no-ops exactly like audiences/topics do when their vocab is absent
    AND no persona carries the field yet. The integrator that lands the 1.3/1.4
    catalog (and the CC) call this to keep the vocab honest.

    Returns {ok, schema, errors[], checked}.
    """
    schema = str(catalog.get("schemaVersion", "")) if isinstance(catalog, dict) else ""
    personas = _persona_meta(catalog)
    aud_vocab = set(catalog.get("audienceTags") or []) if isinstance(catalog, dict) else set()
    top_vocab = set(catalog.get("topicTags") or []) if isinstance(catalog, dict) else set()
    # A-U3 / schema-1.4: three additive scalar (single-string) fields, each
    # validated against its own top-level controlled vocabulary — the exact
    # same subset-of-vocab pattern audiences[]/topics[] already use above,
    # just scalar instead of list-valued (persona_blend.py:317-324 pattern).
    reg_vocab = set(catalog.get("emotionalRegisterTags") or []) if isinstance(catalog, dict) else set()
    res_vocab = set(catalog.get("audienceResonanceTags") or []) if isinstance(catalog, dict) else set()
    close_vocab = set(catalog.get("conversionStyleTags") or []) if isinstance(catalog, dict) else set()

    enriched = any(
        isinstance(v, dict) and (
            v.get("audiences") or v.get("topics") or v.get("voice_style")
            or v.get("emotional_register") or v.get("audience_resonance")
            or v.get("conversion_style")
        )
        for v in personas.values()
    )
    if not enriched and not aud_vocab and not top_vocab and not reg_vocab and not res_vocab and not close_vocab:
        return {"ok": True, "schema": schema or "1.2", "errors": [],
                "checked": 0, "note": "pre-enrichment (no additive tags present)"}

    errors = []
    checked = 0
    for pid, pinfo in personas.items():
        if not isinstance(pinfo, dict):
            continue
        checked += 1
        ua = pinfo.get("usable_as")
        if ua is not None:
            if not isinstance(ua, list):
                errors.append(f"{pid}: usable_as must be a list")
            else:
                bad = [x for x in ua if x not in USABLE_AS_ENUM]
                if bad:
                    errors.append(f"{pid}: usable_as has non-enum value(s) {bad}")
        if aud_vocab:
            for a in (pinfo.get("audiences") or []):
                if a not in aud_vocab:
                    errors.append(f"{pid}: audience {a!r} not in audienceTags vocab")
        if top_vocab:
            for t in (pinfo.get("topics") or []):
                if t not in top_vocab:
                    errors.append(f"{pid}: topic {t!r} not in topicTags vocab")
        vs = pinfo.get("voice_style")
        if isinstance(vs, dict) and not str(vs.get("summary", "")).strip():
            errors.append(f"{pid}: voice_style.summary is required and missing")

        # A-U3 / schema-1.4 scalar fields — each a required-non-empty-string
        # when present, additionally vocab-checked when that vocab is populated.
        er = pinfo.get("emotional_register")
        if er is not None:
            if not isinstance(er, str) or not er.strip():
                errors.append(f"{pid}: emotional_register must be a non-empty string")
            elif reg_vocab and er not in reg_vocab:
                errors.append(f"{pid}: emotional_register {er!r} not in emotionalRegisterTags vocab")
        ar = pinfo.get("audience_resonance")
        if ar is not None:
            if not isinstance(ar, str) or not ar.strip():
                errors.append(f"{pid}: audience_resonance must be a non-empty string")
            elif res_vocab and ar not in res_vocab:
                errors.append(f"{pid}: audience_resonance {ar!r} not in audienceResonanceTags vocab")
        cs = pinfo.get("conversion_style")
        if cs is not None:
            if not isinstance(cs, str) or not cs.strip():
                errors.append(f"{pid}: conversion_style must be a non-empty string")
            elif close_vocab and cs not in close_vocab:
                errors.append(f"{pid}: conversion_style {cs!r} not in conversionStyleTags vocab")
    return {"ok": not errors, "schema": schema or "1.3", "errors": errors,
            "checked": checked}


# ── content-intent detection ──────────────────────────────────────────────────
def is_content_task(task_text: str) -> bool:
    """True when the task is a content / communication job (audience voice matters).

    Single-word signals are matched against the task's TOKEN set (or a token's light
    stem), NEVER as a raw substring — so 'ad' matches the token 'ad'/'ads' but not
    'read'/'download'/'admin'/'grade', and 'post' matches 'post'/'posts' but not
    'compost'. Multi-word / hyphenated signals are matched as a space-bounded phrase.
    This keeps ops tasks with an incidental content substring correctly non-content
    (the module's back-compatibility guarantee) while genuine content still matches.
    """
    if not task_text:
        return False
    text = str(task_text).lower()
    words = {w for w in re.split(r"[^a-z0-9]+", text) if w}
    if words & _CONTENT_WORDS:
        return True
    if any(_stem(w) in _CONTENT_WORD_STEMS for w in words):
        return True
    padded = " " + text + " "
    return any(ph in padded for ph in _CONTENT_PHRASES)


# ── audience resolution from ICP ──────────────────────────────────────────────
# ICP-holding keys observed across live company-config.json schemas (single
# free-text descriptor first; explicit LISTS signal MULTIPLE known audiences).
_ICP_SINGLE_KEYS = (
    "ideal_customer", "idealCustomer", "target_audience", "primary_audience",
    "audience", "customer_avatar", "target_customer", "who_we_serve", "niche",
)
_ICP_LIST_KEYS = (
    "audiences", "audience_segments", "target_audiences", "icp_segments",
    "customer_segments", "segments",
)


def _cfg_scopes(company_cfg: dict) -> list:
    """The dicts we scan for ICP fields: top level + a nested 'company' object
    (the interview stores idealCustomer at company.ideal_customer)."""
    scopes = []
    if isinstance(company_cfg, dict):
        scopes.append(company_cfg)
        for nest in ("company", "brand", "icp", "profile"):
            v = company_cfg.get(nest)
            if isinstance(v, dict):
                scopes.append(v)
    return scopes


def _clean_descriptor(s) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()


def _extract_icp_descriptors(company_cfg: dict, soul_text: str = "") -> list:
    """Extract distinct human-readable audience descriptors from the ICP.

    Order: explicit LIST fields (each element = one known audience) first, then a
    single free-text descriptor. De-duplicated, order-preserving. SOUL.md is a
    low-priority backstop ("we serve …" / "our customers are …") used ONLY when
    the config yields nothing — we never invent an audience.
    """
    descriptors = []

    def _add(v):
        d = _clean_descriptor(v)
        if d and d.lower() not in {x.lower() for x in descriptors}:
            descriptors.append(d)

    for scope in _cfg_scopes(company_cfg):
        for k in _ICP_LIST_KEYS:
            v = scope.get(k)
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, str):
                        _add(item)
                    elif isinstance(item, dict):
                        _add(item.get("label") or item.get("name") or item.get("audience") or "")
    for scope in _cfg_scopes(company_cfg):
        for k in _ICP_SINGLE_KEYS:
            v = scope.get(k)
            if isinstance(v, str) and v.strip():
                _add(v)

    if not descriptors and soul_text:
        for m in re.finditer(
            r"(?:we serve|our (?:customers|clients|audience)(?:\s+are)?|"
            r"target(?:\s+audience)?|ideal (?:customer|client))\s*[:\-]?\s*([^\n.]{4,120})",
            soul_text, flags=re.I,
        ):
            _add(m.group(1))
    return descriptors


def resolve_audience(catalog: dict, company_cfg: dict, soul_text: str = "",
                     audience_override: str = "") -> dict:
    """Resolve the audience + whether the operator must confirm before writing.

    ALWAYS-confirm doctrine:
      • operator_confirmed (OPENCLAW_AUDIENCE / explicit override) → confirm_required=False.
      • single ICP descriptor → source 'onboarding_icp', confidence 'high',
        confirm_required=True (a confirm PROMPT — clients have >1 audience).
      • multiple ICP descriptors → source 'asked', confirm_required=True,
        ask = "What audience are we dealing with?" enumerating the known ones.
      • none → source 'asked', confidence 'none', confirm_required=True, same ASK.

    Returns {source, candidates[], confidence, label, ask, confirm_required}.
    Candidates carry the proposed audience persona per known audience. Never
    fabricates an audience (candidates=[] when the ICP yields nothing).
    """
    if audience_override and str(audience_override).strip():
        label = _clean_descriptor(audience_override)
        ap = match_audience_persona(catalog, label)
        return {
            "source": "operator_confirmed",
            "candidates": [_candidate(label, ap)],
            "confidence": "high",
            "label": label,
            "ask": None,
            "confirm_required": False,
        }

    descriptors = _extract_icp_descriptors(company_cfg, soul_text)
    candidates = [_candidate(d, match_audience_persona(catalog, d)) for d in descriptors]

    if len(descriptors) == 1:
        return {
            "source": "onboarding_icp",
            "candidates": candidates,
            "confidence": "high",
            "label": descriptors[0],
            "ask": (f'Onboarding ICP says the audience is "{descriptors[0]}". '
                    f"Confirm this audience before I write, or tell me the audience."),
            "confirm_required": True,
        }
    if len(descriptors) > 1:
        enum = "; ".join(f'"{d}"' for d in descriptors)
        return {
            "source": "asked",
            "candidates": candidates,
            "confidence": "medium",
            "label": descriptors[0],  # top proposal; ASK still required
            "ask": f"{AUDIENCE_CONFIRM_PROMPT} Known from onboarding: {enum}.",
            "confirm_required": True,
        }
    return {
        "source": "asked",
        "candidates": [],
        "confidence": "none",
        "label": None,
        "ask": (f"{AUDIENCE_CONFIRM_PROMPT} No audience is on file in the "
                f"onboarding ICP — name the audience so I can pick the voice."),
        "confirm_required": True,
    }


def _candidate(label: str, ap) -> dict:
    d = {"label": label, "audience_persona_id": None, "matched_tags": []}
    if ap:
        d["audience_persona_id"] = ap["persona_id"]
        d["matched_tags"] = ap.get("matched_tags", [])
        d["why"] = ap.get("why")
    return d


# ── whole-catalog tag matchers ────────────────────────────────────────────────
def match_audience_persona(catalog: dict, audience_label: str):
    """Pick the AUDIENCE-voice persona for an audience label, over the WHOLE catalog.

    Candidate universe = personas whose usable_as INCLUDES 'audience' (serving as
    an audience voice must be explicit) AND whose audiences[] is non-empty. Ranked
    by audience-tag overlap with the label. Returns None when nothing matches (a
    1.2 catalog, or an audience no persona speaks to) — the caller then keeps the
    audience unconfirmed / falls back to the topic voice; we never force a match.
    """
    personas = _persona_meta(catalog)
    if not audience_label or not personas:
        return None
    q = _tokens(audience_label)
    ranked = []
    for pid, pinfo in personas.items():
        if not isinstance(pinfo, dict) or pinfo.get("fallback"):
            continue
        if "audience" not in _usable_as(pinfo):
            continue
        auds = pinfo.get("audiences") or []
        if not auds:
            continue
        hits, mtags, mtoks = _tag_hit(q, auds)
        if hits > 0:
            ranked.append((hits, len(mtags), pid, mtags, mtoks))
    if not ranked:
        return None
    ranked.sort(key=lambda r: (-r[0], -r[1], r[2]))
    hits, _n, pid, mtags, mtoks = ranked[0]
    vs = (personas[pid].get("voice_style") or {})
    summary = vs.get("summary") if isinstance(vs, dict) else None
    why = (f"Audience voice for '{audience_label}': its audiences[] match on "
           f"{mtoks} ({hits} signal(s)); usable_as includes 'audience'"
           + (f"; voice: {summary}" if summary else "") + ".")
    return {"persona_id": pid, "why": why, "matched_tags": mtags,
            "matched_tokens": mtoks, "score": hits}


def match_topic_persona(catalog: dict, task_text: str, topic_hint: str = "",
                        semantic_pick: str = ""):
    """Pick the TOPIC-expertise persona for the job, over the WHOLE catalog.

    Ranked by topics[] overlap with the task (+ optional topic_hint) tokens. A
    small nudge is given to `semantic_pick` (the existing 5-layer selector's pick)
    so the tag pass and the semantic engine agree when they can, without letting
    an all-ties semantic stub override a clear tag winner. Returns None only when
    NO persona carries topics[] (a 1.2 catalog) — the caller then falls back to
    the semantic selector's pick.
    """
    personas = _persona_meta(catalog)
    if not personas:
        return None
    q = _tokens(task_text) | _tokens(topic_hint)
    ranked = []
    any_topics = False
    for pid, pinfo in personas.items():
        if not isinstance(pinfo, dict) or pinfo.get("fallback"):
            continue
        ua = _usable_as(pinfo)
        if "topic" not in ua:
            continue
        tops = pinfo.get("topics") or []
        if tops:
            any_topics = True
        hits, mtags, mtoks = _tag_hit(q, tops)
        nudge = 1 if (semantic_pick and pid == semantic_pick) else 0
        score = hits + 0.25 * nudge
        if hits > 0 or nudge:
            ranked.append((score, hits, len(mtags), pid, mtags, mtoks))
    if not any_topics and not ranked:
        return None
    if not ranked:
        return None
    ranked.sort(key=lambda r: (-r[0], -r[1], -r[2], r[3]))
    score, hits, _n, pid, mtags, mtoks = ranked[0]
    if hits == 0:
        # Pure semantic-NUDGE winner: no topics[] tag actually matched the job (a
        # 1.2 catalog, or a job with zero topic overlap). Return None so the caller
        # falls back to the semantic pick with an HONEST rationale — never emit a
        # 'topics[] match the job on [] (0 signal(s))' claim that did not happen.
        return None
    vs = (personas[pid].get("voice_style") or {})
    summary = vs.get("summary") if isinstance(vs, dict) else None
    why = (f"Topic expertise: its topics[] match the job on {mtoks} "
           f"({hits} signal(s))"
           + ("; agrees with the semantic selector" if semantic_pick == pid else "")
           + (f"; voice: {summary}" if summary else "") + ".")
    return {"persona_id": pid, "why": why, "matched_tags": mtags,
            "matched_tokens": mtoks, "score": score}


# ── collapse rule ─────────────────────────────────────────────────────────────
def decide_collapse(catalog: dict, audience_pid, topic_pid,
                    audience_label: str, task_text: str, topic_hint: str = "") -> tuple:
    """Decide whether ONE persona covers BOTH the audience and the topic.

    Rules (first match wins):
      1. audience_pid == topic_pid            → collapse onto it.
      2. the TOPIC persona also qualifies as the audience voice (usable_as has
         'audience' AND its audiences[] match the audience label) → collapse onto
         the topic persona (it carries expertise AND speaks to the audience,
         e.g. a finance-for-women voice covering a personal-finance job).
      3. the AUDIENCE persona also strongly covers the topic (its topics[] match
         the job) → collapse onto the audience persona.
    Returns (collapsed: bool, collapsed_pid or None).
    """
    if audience_pid and topic_pid and audience_pid == topic_pid:
        return True, audience_pid
    personas = _persona_meta(catalog)
    q_topic = _tokens(task_text) | _tokens(topic_hint)
    q_aud = _tokens(audience_label)

    if topic_pid and audience_label:
        tinfo = personas.get(topic_pid, {})
        if isinstance(tinfo, dict) and "audience" in _usable_as(tinfo):
            hits, _mt, _mk = _tag_hit(q_aud, tinfo.get("audiences") or [])
            if hits > 0:
                return True, topic_pid
    if audience_pid:
        ainfo = personas.get(audience_pid, {})
        if isinstance(ainfo, dict):
            hits, _mt, _mk = _tag_hit(q_topic, ainfo.get("topics") or [])
            if hits >= 2:  # a genuine dual-competence, not a single incidental tag
                return True, audience_pid
    return False, None


# ── A-U2: v2 structured voice-attribute block (additive, catalog-sourced) ─────
# Attributes come ONLY from the catalog's voice_style{} — never model-invented.
# Renders nothing (returns None) when the pid is absent, the catalog wasn't
# passed, or the persona simply has no voice_style — that is exactly how a
# schema-1.2 (pre-enrichment) catalog degrades to v1's prose-only directive,
# byte-identical.
def _vs_join(value, limit=None):
    """Join a voice_style list field (or pass through a string field) into one
    line fragment. Never fabricates: absent/empty input yields "" and the
    caller omits that fragment entirely rather than printing a placeholder."""
    if isinstance(value, list):
        items = value[:limit] if limit else value
        return ", ".join(str(x) for x in items if x)
    return str(value) if value else ""


def _voice_attr_block(label: str, pid, personas: dict):
    """Render the SLOT's structured attribute block (A.3):
        <LABEL> — <persona name> (<persona id>)
          tone: <tone> | cadence: <cadence>
          devices: <top 3 devices> | signature move: <1 signature move>
          avoid: <avoid[]>
    Returns a list of lines, or None when voice_style is unavailable for pid
    (graceful degradation — no block, no fabricated attributes)."""
    if not pid or not isinstance(personas, dict):
        return None
    info = personas.get(pid)
    vs = info.get("voice_style") if isinstance(info, dict) else None
    if not isinstance(vs, dict) or not vs:
        return None

    tone = _vs_join(vs.get("tone"))
    cadence = _vs_join(vs.get("cadence"))
    devices = _vs_join(vs.get("devices"), limit=3)
    signature_move = _vs_join(vs.get("signature_moves"), limit=1)
    avoid = _vs_join(vs.get("avoid"))

    lines = [f"{label} — {pid.replace('-', ' ').title()} ({pid})"]
    tone_cadence = " | ".join(
        p for p in (f"tone: {tone}" if tone else "",
                    f"cadence: {cadence}" if cadence else "") if p)
    if tone_cadence:
        lines.append("  " + tone_cadence)
    devices_sig = " | ".join(
        p for p in (f"devices: {devices}" if devices else "",
                    f"signature move: {signature_move}" if signature_move else "")
        if p)
    if devices_sig:
        lines.append("  " + devices_sig)
    if avoid:
        lines.append(f"  avoid: {avoid}")
    return lines


# ── blend directive (carries the mandatory guardrail) ─────────────────────────
def build_blend_directive(audience_pid, topic_pid, topic: str, collapsed: bool,
                          collapsed_pid, content_task: bool,
                          audience_label: str = "", task_persona_pid=None,
                          catalog: dict = None) -> str:
    """Compose the writer's SYNERGY instruction — up to FOUR slots working
    together (P4-02 step 7):

        1. VOICE     — the audience persona's cadence/devices/register.
        2. AUDIENCE  — who the content is FOR (the resolved audience label).
        3. SUBSTANCE — the topic persona's expertise/frameworks.
        4. TASK      — the task-side persona (DEP-5), an INDEPENDENT dimension
                       guiding HOW the work is executed (its process/method).

    Every slot populates when available and DEGRADES GRACEFULLY when not
    (voice-only, topic-only, task-only, or the neutral house voice). The
    GUARDRAIL_CLAUSE is ALWAYS appended and can never be omitted (fail-closed).

    A-U2 (Blend Directive v2): when `catalog` is supplied and a populated
    slot's persona carries voice_style{} (schema >=1.3), a structured
    voice-attribute block (tone/cadence/devices/signature move/avoid — sourced
    ONLY from the catalog, never invented) is appended per populated slot,
    followed by a one-line VOICE CONTRACT echo instruction. This is PURELY
    ADDITIVE: `catalog=None` (the default), a schema-1.2 catalog, or a persona
    with no voice_style all degrade to the identical v1 prose-only directive —
    the guardrail remains the trailing, non-removable clause in every case.
    """
    def _name(pid):
        return pid.replace("-", " ").title() if pid else None

    # voice_slots: [(LABEL, pid), ...] — the same populated-slot set the v1
    # prose body already expresses, tracked in parallel so the v2 attribute
    # block can never drift from what the directive's own prose claims.
    voice_slots = []

    if not content_task:
        body = (f"Non-content task — no audience-voice blend. Execute with "
                f"{_name(topic_pid)}'s expert judgement on {topic!r}.")
        voice_slots.append(("SUBSTANCE", topic_pid))
    elif collapsed and collapsed_pid:
        aud = f" for the '{audience_label}' audience" if audience_label else ""
        body = (f"Write in {_name(collapsed_pid)}'s voice{aud}: one persona covers "
                f"both the audience register and the {topic!r} expertise.")
        voice_slots.append(("VOICE", collapsed_pid))
    elif audience_pid and topic_pid:
        aud = f" ({audience_label})" if audience_label else ""
        body = (f"Write in {_name(audience_pid)}'s VOICE{aud} — its cadence, "
                f"devices and register — while carrying {_name(topic_pid)}'s "
                f"EXPERTISE on {topic!r}. Audience voice leads; topic expertise "
                f"informs substance.")
        voice_slots.append(("VOICE", audience_pid))
        voice_slots.append(("SUBSTANCE", topic_pid))
    elif topic_pid:
        body = (f"Audience not yet confirmed — draft with {_name(topic_pid)}'s "
                f"expertise on {topic!r} in a neutral house voice; the audience "
                f"voice is applied once confirmed.")
        voice_slots.append(("SUBSTANCE", topic_pid))
    else:
        body = f"Proceed in the default house voice on {topic!r}."

    # Slot 4 — the TASK-side persona. An independent dimension (DEP-5): it governs
    # the work PROCESS, not the voice or substance. Appended only for content
    # tasks and only when it is a GENUINELY DISTINCT persona (not already the
    # voice or the topic persona, which already doubles as task guidance) so the
    # composed directive never repeats itself — graceful degradation to
    # three/two/one slot when the task persona is absent or redundant.
    if content_task and task_persona_pid and task_persona_pid not in (
            audience_pid, topic_pid, collapsed_pid):
        body += (f" The task-side persona is {_name(task_persona_pid)} — apply "
                 f"ITS process and decision method to execute the work.")
        voice_slots.append(("TASK", task_persona_pid))

    # ── A-U2 v2 block — additive only; see docstring for the degrade contract ──
    personas = _persona_meta(catalog) if catalog else {}
    attr_blocks = []
    for label, pid in voice_slots:
        block = _voice_attr_block(label, pid, personas)
        if block:
            attr_blocks.append("\n".join(block))
    if attr_blocks:
        body = body + "\n\n" + "\n".join(attr_blocks) + (
            "\nVOICE CONTRACT: echo one line into persona-selection-log "
            "confirming the register you wrote in.")

    return body + " " + GUARDRAIL_CLAUSE


# ── task decomposition → up to 10 task personas ───────────────────────────────
def build_task_personas(task_text: str, department: str, *, max_task_personas: int = 10,
                        use_llm: bool = True, record: bool = True,
                        variety: bool = True) -> tuple:
    """Decompose the job into UP TO `max_task_personas` (<=10) parts, each with its
    own best-fit persona, by REUSING decompose-task.combined_select (the existing
    per-sub-task matcher). Returns (task_personas[], combined_raw).

    task_personas rows: {seq, part, persona_id, why} (the bundle shape). The
    combined engine's default DECOMP_MAX_SUBTASKS ceiling (6) is raised to the
    blend cap for this call only, then restored (raise-only, never lowered below
    the operator's configured value).
    """
    dt = _decompose()
    cap = max(1, min(int(max_task_personas or 10), 10))
    orig = getattr(dt, "DECOMP_MAX_SUBTASKS", 6)
    try:
        if cap > orig:
            dt.DECOMP_MAX_SUBTASKS = cap
        combined = dt.combined_select(
            task_text, department, use_llm=use_llm, record=record,
            max_subtasks=cap, variety=variety,
        )
    finally:
        dt.DECOMP_MAX_SUBTASKS = orig

    task_personas = []
    for p in combined.get("plan", [])[:cap]:
        task_personas.append({
            "seq": p.get("seq"),
            "part": p.get("subtask"),
            "persona_id": p.get("persona_id"),
            "why": p.get("why"),
            "no_persona_required": p.get("no_persona_required", False),
            "governance_persona_id": p.get("governance_persona_id"),
            "task_category": p.get("task_category"),
        })
    return task_personas, combined


# ── P4-01 step 2: match-score-distribution logging (drift observability) ──────
# "log match score distributions so drift is observable" (P4-01 spec (c)2).
# Best-effort, append-only JSONL — one record per audience/topic decision made
# inside build_bundle(). Logging failures (unwritable dir, disk full, a client
# box with a read-only workspace mount, ...) NEVER raise and NEVER block a
# persona match: this is pure observability riding alongside the real
# decision, never a dependency of it.
MATCH_SCORE_LOG_FILENAME = "match-score-log.jsonl"


def _match_score_log_path(paths: dict):
    """Resolve the match-score log path. OPENCLAW_PERSONA_MATCH_SCORE_LOG
    overrides (same override pattern as OPENCLAW_PERSONA_CATEGORIES — used by
    tests so this never touches a live workspace); otherwise
    paths['coaching_personas']/match-score-log.jsonl, alongside the persona
    catalog and gemini index this module already reads/writes near. Returns
    None when neither is resolvable (e.g. a paths dict with no
    coaching_personas key) — the caller treats that as "logging unavailable".
    """
    override = os.environ.get("OPENCLAW_PERSONA_MATCH_SCORE_LOG", "").strip()
    if override:
        return Path(override)
    cp = paths.get("coaching_personas") if isinstance(paths, dict) else None
    return Path(cp) / MATCH_SCORE_LOG_FILENAME if cp else None


def log_match_score(paths: dict, *, dimension: str, persona_id, score,
                     task_category=None, content_task=None) -> bool:
    """Append ONE match-score record. dimension in {"audience","topic"}.

    Returns True on a successful write, False on ANY failure (never raises —
    see module note above). Records are plain JSON lines:
      {ts, dimension, persona_id, score, task_category, content_task}
    """
    import json as _json
    from datetime import datetime, timezone
    try:
        log_path = _match_score_log_path(paths)
        if not log_path:
            return False
        log_path.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "dimension": dimension,
            "persona_id": persona_id,
            "score": score,
            "task_category": task_category,
            "content_task": content_task,
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(_json.dumps(rec) + "\n")
        return True
    except Exception:
        return False


def match_score_distribution(paths: dict, *, dimension: str = None,
                             tail: int = 2000) -> dict:
    """Summarize the match-score log for drift observability.

    Reads at most the last `tail` lines (bounded — this is a log-tail summary,
    never an unbounded full-file load) and returns:
      {count, mean, min, max, buckets: {low: n (<0.3), mid: n (0.3-0.6),
       high: n (>0.6)}}
    Filters to a single `dimension` when given. Returns count=0 (never raises,
    never fabricates a distribution) when the log is absent/unreadable/empty —
    an honest "no data yet" is what a fresh box or a logging-path failure
    looks like, and callers (health probes) must be able to tell that apart
    from "the matcher is genuinely producing low scores".
    """
    import json as _json
    empty = {"count": 0, "mean": None, "min": None, "max": None,
             "buckets": {"low": 0, "mid": 0, "high": 0}}
    log_path = _match_score_log_path(paths)
    if not log_path or not log_path.exists():
        return empty
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return empty
    scores = []
    for line in lines[-tail:]:
        line = line.strip()
        if not line:
            continue
        try:
            rec = _json.loads(line)
        except Exception:
            continue
        if dimension and rec.get("dimension") != dimension:
            continue
        s = rec.get("score")
        if isinstance(s, (int, float)):
            scores.append(float(s))
    if not scores:
        return empty
    buckets = {"low": 0, "mid": 0, "high": 0}
    for s in scores:
        if s < 0.3:
            buckets["low"] += 1
        elif s <= 0.6:
            buckets["mid"] += 1
        else:
            buckets["high"] += 1
    return {"count": len(scores), "mean": sum(scores) / len(scores),
            "min": min(scores), "max": max(scores), "buckets": buckets}


# ── A-U5 — per-page / per-scope blends ─────────────────────────────────────────
# Per-page blends are structurally impossible before this unit: build_bundle ran
# once per TASK and the Command Center persisted ONE bundle per task
# (`task_persona_bundle.task_id TEXT NOT NULL UNIQUE`). A 5-page funnel wrote its
# opt-in, sales, and thank-you pages under one blend. The fix is additive: the
# CALLER (Skill 6's per-page loop, A-U7) now MAY pass a `scope_hint` describing
# the page it is about to write, and build_bundle folds it into topic matching +
# echoes a stable `scope` key back for the Command Center's NEW
# `task_persona_bundle_scope` table (keyed `(task_id, scope)` — migration 090's
# unscoped `task_persona_bundle` table is never altered). Every existing
# single-bundle caller (scope_hint omitted/None/empty) gets a bundle with NO
# `scope`/`scope_hint` keys at all — byte-identical to pre-A-U5 output.
#
# scope_hint shape (all keys optional): {page_role, page_slug, conversion_goal,
# part_id}. `part_id` is forward-compatible with U115's per-part / long-horizon
# generalization of this same mechanism (Section E6) — this unit does not use it,
# it only avoids colliding with it.
def _resolve_scope_key(scope_hint: dict):
    """The `(task_id, scope)` composite key's non-task-id half. Preference order:
    an explicit `page_slug` (the stablest, URL-shaped identifier) > `page_role`
    (e.g. 'opt-in', 'sales', 'thank-you') > `part_id` (U115's per-part id). None
    when scope_hint is falsy/empty or names none of these — the caller then has
    nothing scope-able and build_bundle behaves exactly as the unscoped path.
    """
    if not scope_hint or not isinstance(scope_hint, dict):
        return None
    for key in ("page_slug", "page_role", "part_id"):
        v = scope_hint.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _scope_reason(scope_key: str, scope_hint: dict, *, shared_with: str = None) -> str:
    """The different-blends-allowed invariant (A.6 build step 3): the per-page
    log must state WHY pages share or differ a blend — a shared blend is legal
    when the collapse rule fires per page; forced-identical with no logged
    reason is a Quality-Control finding for the Section-B judge (A-U7's job to
    enforce across a real funnel run). This unit emits the honest per-call
    statement build_bundle already has evidence for; A-U7 threads it across
    pages to detect the "forced-identical, no reason" case.
    """
    goal = (scope_hint or {}).get("conversion_goal") if isinstance(scope_hint, dict) else None
    role = (scope_hint or {}).get("page_role") if isinstance(scope_hint, dict) else None
    parts = [f"scope={scope_key}"]
    if role:
        parts.append(f"page_role={role}")
    if goal:
        parts.append(f"conversion_goal={goal}")
    if shared_with:
        parts.append(f"blend shared with scope={shared_with} (collapse/topic-match fired identically)")
    return ", ".join(parts)


def write_persona_selection_log_entry(run_dir, scope_key: str, bundle: dict, *,
                                       reason: str = None) -> bool:
    """Append ONE per-page entry to `persona-selection-log.md` in `run_dir`,
    reusing the exact `- selected_persona: <slug>` line convention every other
    Skill 6/49/56 build script already writes (see `run_sales_page_assets.py`,
    the golden-momentum builder) so downstream readers (funnel_rubrics.py,
    prove_sp_intake.py) parse it unchanged. One call per page; A-U7 is the real
    per-page-loop caller in production, this unit only ships the writer +
    proves it with a fixture funnel (its own binary acceptance criterion (a)).

    Best-effort / non-fatal: a write failure returns False and never raises —
    same observability-never-blocks posture as log_match_score above.
    """
    try:
        rd = Path(run_dir)
        rd.mkdir(parents=True, exist_ok=True)
        log_path = rd / "persona-selection-log.md"
        pid = bundle.get("persona_id") or "none"
        lines = [f"- scope: {scope_key}", f"- selected_persona: {pid}"]
        if reason:
            lines.append(f"- reason: {reason}")
        entry = "## page: " + scope_key + "\n" + "\n".join(lines) + "\n\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)
        return True
    except Exception:
        return False


# ── the bundle assembler ──────────────────────────────────────────────────────
def build_bundle(task: str, department: str, *, paths: dict = None, db_path=None,
                 use_llm: bool = True, record: bool = True,
                 max_task_personas: int = 10, variety: bool = True,
                 topic_hint: str = "", audience_override: str = "",
                 scope_hint: dict = None) -> dict:
    """Assemble the voice-first persona BLEND bundle (the SUPERSET output).

    paths/db_path default to the live resolution when omitted; tests pass a
    hermetic paths dict and monkeypatch the selector/decompose functions.
    """
    sel = _selector()
    if paths is None:
        paths = sel.get_openclaw_paths()
    if db_path is None:
        db_path = sel.find_dashboard_db()
    db_field = str(db_path) if sel.is_db_found(db_path) else "none"

    catalog = load_catalog(paths)
    company_cfg = sel.load_company_config(paths) or {}
    soul_text = ""
    try:
        soul_p = paths.get("soul_md")
        if soul_p and Path(soul_p).exists():
            soul_text = Path(soul_p).read_text(encoding="utf-8", errors="replace")
    except Exception:
        soul_text = ""

    task_category = sel.infer_task_category(task)
    default_pid, default_src = sel._resolve_default_persona_id(paths)
    gov_pid, gov_src = sel._resolve_governance_persona_id(paths)
    fallbacks = {"default_persona": default_pid, "default_persona_source": default_src,
                 "governance": gov_pid, "governance_source": gov_src}

    # ── Mechanical / no-persona task — never-naked governance pointer, no blend ──
    if sel.is_mechanical_task(task):
        return {
            "mode": "blend",
            "persona_id": None,
            "no_persona_required": True,
            "content_task": False,
            "governance_persona_id": gov_pid,
            "governance_persona_source": gov_src,
            "confirm_required": False,
            "task_category": task_category,
            "topic": topic_hint or task_category,
            "resolved_audience": {"source": "n/a", "candidates": [],
                                  "confidence": "none", "label": None, "ask": None,
                                  "confirm_required": False},
            "voice": {"audience_persona": None, "topic_persona": None,
                      "collapsed": False, "collapsed_persona_id": None,
                      "topic_as_task_guidance": False},
            "blend_directive": ("Operational/mechanical task — no persona voice "
                                "required. " + GUARDRAIL_CLAUSE),
            "task_personas": [],
            "rationale": {"note": "mechanical task — governance persona attached, "
                                  "no audience/topic blend."},
            "funnel": {"pool": 0, "category": 0, "semantic": 0, "mechanical": True},
            "fallbacks": fallbacks,
            "catalog_version": str(catalog.get("schemaVersion", "")) or "unknown",
            "db": db_field,
            "message": (f"Operational/mechanical task — no persona required "
                        f"(governance persona '{gov_pid}' attached for oversight)."),
        }

    content_task = is_content_task(task)

    # ── A-U5 scope_hint — bounded tie-breaker, additive-only ────────────────────
    # A page's role (opt-in / sales / thank-you / ...) is a legitimate topic
    # signal when the caller supplied no explicit topic_hint of its own. Never
    # overrides an explicit topic_hint (explicit beats inferred, same precedence
    # every other hint in this module already follows). scope_hint=None (the
    # default) touches nothing here — topic_hint is used exactly as before.
    scope_key = _resolve_scope_key(scope_hint)
    if scope_key and not topic_hint and isinstance(scope_hint, dict):
        _page_role = scope_hint.get("page_role")
        if isinstance(_page_role, str) and _page_role.strip():
            topic_hint = _page_role.strip()

    # ── AUDIENCE (voice decided first) ──────────────────────────────────────────
    ra = resolve_audience(catalog, company_cfg, soul_text, audience_override)
    audience_label = ra.get("label") or ""

    # ── semantic topic pick from the existing 5-layer selector (best-effort) ────
    semantic_pick = ""
    semantic_funnel = None
    semantic_score = None
    try:
        mode = sel.detect_interaction_mode(task)
        weights = sel.get_weights_for_task(task, mode)
        _sr = sel.select_persona(task, department, mode, weights, paths, db_path,
                                 variety=False)
        if isinstance(_sr, dict):
            semantic_pick = _sr.get("persona_id") or ""
            semantic_funnel = _sr.get("funnel")
            semantic_score = _sr.get("score")
    except Exception:
        semantic_pick = ""

    # ── TOPIC persona (whole-catalog tags, semantic nudge) ──────────────────────
    tp = match_topic_persona(catalog, task, topic_hint, semantic_pick)
    if tp is None and semantic_pick:
        # No topics[] tag matched the job — inherit the 5-layer semantic pick. Keep
        # the rationale honest: distinguish an un-enriched catalog (no topics[]
        # ANYWHERE) from an enriched one where nothing matched THIS job.
        _catalog_has_topics = any(
            isinstance(v, dict) and v.get("topics")
            for v in _persona_meta(catalog).values())
        if _catalog_has_topics:
            _fallback_why = ("Topic expertise inherited from the 5-layer semantic "
                             "selector — no topics[] tag in the catalog matched this job.")
        else:
            _fallback_why = ("Topic expertise from the 5-layer semantic selector "
                             "(catalog has no topics[] tags to reason over).")
        tp = {"persona_id": semantic_pick,
              "why": _fallback_why,
              "matched_tags": [], "matched_tokens": [],
              "score": semantic_score if semantic_score is not None else 0.0}
    if tp is None:
        # No catalog at all — fall back to the guaranteed default persona.
        tp = {"persona_id": default_pid,
              "why": f"No topic candidates in the catalog — default fallback "
                     f"persona ({default_src}).",
              "matched_tags": [], "matched_tokens": [], "score": 0.0}
    topic_pid = tp["persona_id"]
    if topic_pid:
        log_match_score(paths, dimension="topic", persona_id=topic_pid,
                         score=tp.get("score"), task_category=task_category,
                         content_task=content_task)

    # topic string: prefer explicit hint, else the matched topic tags, else category.
    if topic_hint:
        topic = topic_hint
    elif tp.get("matched_tags"):
        topic = ", ".join(tp["matched_tags"][:3])
    else:
        topic = task_category

    # ── AUDIENCE persona (only for content tasks with a CONFIRMED-ENOUGH label) ──
    # When the ICP holds MULTIPLE known audiences and the operator has NOT chosen
    # yet (source == 'asked'), audience_label is only the arbitrary FIRST descriptor
    # — do NOT pre-commit its voice, neither directly nor via an audience-matching
    # collapse. The write stays gated (confirm_required=True) and the ASK enumerates
    # every candidate; the voice falls to the neutral house branch until confirmed.
    _audience_unconfirmed_multi = (
        ra.get("source") == "asked" and len(ra.get("candidates", [])) > 1)
    voice_audience_label = "" if _audience_unconfirmed_multi else audience_label
    ap = None
    if content_task and voice_audience_label:
        ap = match_audience_persona(catalog, voice_audience_label)
    audience_pid = ap["persona_id"] if ap else None
    if ap and audience_pid:
        log_match_score(paths, dimension="audience", persona_id=audience_pid,
                         score=ap.get("score"), task_category=task_category,
                         content_task=content_task)

    # ── COLLAPSE decision ───────────────────────────────────────────────────────
    if content_task:
        collapsed, collapsed_pid = decide_collapse(
            catalog, audience_pid, topic_pid, voice_audience_label, task, topic_hint)
    else:
        # Non-content: no audience voice — the topic persona carries the voice.
        collapsed, collapsed_pid = True, topic_pid

    # ── resolved VOICE persona (back-compat mirror) ─────────────────────────────
    if collapsed and collapsed_pid:
        voice_pid = collapsed_pid
    elif audience_pid:
        voice_pid = audience_pid
    else:
        voice_pid = topic_pid  # audience pending/none → interim voice = topic
    voice_score = tp.get("score") if voice_pid == topic_pid else (ap or {}).get("score", 0.0)

    # ── confirm_required (gates the write) ──────────────────────────────────────
    # Top-level confirm_required is authoritative. A non-content task never gates
    # on an audience voice (there is none), so it is False; keep the nested
    # resolved_audience.confirm_required in lockstep so consumers see one truth.
    if not content_task:
        confirm_required = False
    else:
        confirm_required = bool(ra.get("confirm_required", True))
    ra["confirm_required"] = confirm_required

    # ── TASK personas (up to 10) ────────────────────────────────────────────────
    # Computed BEFORE the directive (P4-02 step 7) so the primary task-side
    # persona can populate the directive's fourth synergy slot.
    task_personas, combined = build_task_personas(
        task, department, max_task_personas=max_task_personas,
        use_llm=use_llm, record=record, variety=variety)

    # The PRIMARY task-side persona (DEP-5): the first non-mechanical part's
    # persona. None when the plan is empty or all-mechanical — the directive then
    # simply omits slot 4 (graceful degradation).
    primary_task_pid = next(
        (tp.get("persona_id") for tp in task_personas
         if tp.get("persona_id") and not tp.get("no_persona_required")),
        None,
    )

    blend_directive = build_blend_directive(
        audience_pid, topic_pid, topic, collapsed, collapsed_pid, content_task,
        voice_audience_label, task_persona_pid=primary_task_pid, catalog=catalog)

    funnel = semantic_funnel if isinstance(semantic_funnel, dict) else {
        "pool": len(_persona_meta(catalog)),
        "category": len([p for p in _persona_meta(catalog).values()
                         if isinstance(p, dict) and (p.get("topics") or p.get("audiences"))]),
        "semantic": len(tp.get("matched_tags", [])),
    }

    voice = {
        "audience_persona": ({"id": audience_pid, "why": ap["why"]} if ap else None),
        "topic_persona": {"id": topic_pid, "why": tp["why"]},
        "collapsed": collapsed,
        "collapsed_persona_id": collapsed_pid if collapsed else None,
        "topic_as_task_guidance": True,
    }

    rationale = {
        "audience_resolution": (
            f"source={ra['source']}, confidence={ra['confidence']}, "
            f"candidates={[c['label'] for c in ra.get('candidates', [])]}"
            + ("" if not ra.get('ask') else f" — ASK: {ra['ask']}")),
        "audience_persona": (ap["why"] if ap else
                             ("no audience persona: " + (
                                 "audience not yet confirmed" if content_task
                                 else "non-content task (no audience voice)"))),
        "topic_persona": tp["why"],
        "collapse": (f"collapsed onto {collapsed_pid}" if collapsed
                     else "distinct audience + topic personas (blend)"),
        "voice_persona_mirror": f"back-compat persona_id mirrors the voice persona {voice_pid}",
        "task_decomposition": (
            f"{combined.get('subtask_count', len(task_personas))} part(s), "
            f"{combined.get('distinct_persona_count', 0)} distinct persona(s) "
            f"[{combined.get('decomposition_method', 'n/a')}] — topic persona "
            f"doubles as task guidance"),
    }

    bundle = {
        # ── back-compat single-persona mirror (existing consumers) ──
        "persona_id": voice_pid,
        "persona_name": voice_pid.replace("-", " ").title() if voice_pid else None,
        "persona_version": 1,
        "score": voice_score,
        "interaction_mode": sel.detect_interaction_mode(task),
        "task_category": task_category,
        "funnel": funnel,
        # ── blend superset ──
        "mode": "blend",
        "content_task": content_task,
        "topic": topic,
        "resolved_audience": ra,
        "confirm_required": confirm_required,
        "voice": voice,
        "blend_directive": blend_directive,
        "task_personas": task_personas[:10],
        "rationale": rationale,
        "fallbacks": fallbacks,
        "catalog_version": str(catalog.get("schemaVersion", "")) or "unknown",
        "task_id": combined.get("task_id"),
        "db": db_field,
    }
    if not catalog:
        bundle["warning"] = "NO_CATALOG"
        bundle.setdefault("message",
                          "persona-categories.json not found — blend ran on the "
                          "semantic selector + fallbacks only.")

    # ── A-U5 — echo the scope key + WHY back to the caller (additive-only) ──────
    # Only present when the caller supplied a resolvable scope_hint; every
    # existing single-bundle consumer (scope_hint omitted) gets a bundle dict
    # with NEITHER key at all — byte-identical to the pre-A-U5 shape.
    if scope_key:
        bundle["scope"] = scope_key
        bundle["scope_hint"] = dict(scope_hint)
        rationale["scope"] = _scope_reason(scope_key, scope_hint) + f" — {rationale['collapse']}"

    return bundle
