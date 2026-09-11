#!/usr/bin/env python3
"""
decompose-task.py — COMBINED / PER-SUBTASK PERSONAS (spec §6, build plan W6.1/W6.2).

THE BIGGEST GAP this closes
---------------------------
The existing selector (`persona-selector-v2.py`) picks exactly ONE persona per
task. The spec's "key build" is the opposite: a big task DECOMPOSES into ordered
sub-tasks and EACH sub-task gets its OWN best-fit persona — and the system
records which persona guided which sub-task so §5 can report it.

Worked examples this must support (verbatim from spec §6):
  • A leadership email →
        - John Maxwell persona for the leadership-message body,
        - a different (sales) persona for the sales section,
        - a third (mechanical) for the send/sequencing step.
  • A landing page for Black women →
        - Michelle Obama for the copy / message / voice,
        - Russell Brunson for the funnel structure / build.

This file is NET-NEW and STANDALONE. It does NOT reimplement persona matching.
It REUSES the canonical selector's matching engine (`select_persona`) once per
sub-task, plus its mode/category/weight/record helpers, loaded by path (the
selector filename is hyphenated and cannot be `import`-ed by name — same
importlib-by-path trick the selector itself uses for `infer-task-category.py`).

================================================================================
INTEGRATION POINTS (where this gets wired in at integration time — file:line)
================================================================================
1. persona-selector-v2.py:1890-2039  (main(), select-mode)
   W6.1 wires a `--decompose` / `--combined` flag into this argparse block. When
   set, main() shells out to (or imports) `combined_select()` below INSTEAD of
   the single-persona `select_persona(...)` path at 2031-2038. DO NOT edit the
   selector here — this module imports it read-only.
2. persona-selector-v2.py:1651  select_persona(task, department, mode, weights,
   paths, db_path, variety=True)  → the matching engine we call once per subtask.
   We pass weights through `apply_specialist_surfacing()` (the W6 re-weighting
   tweak) BEFORE calling it; select_persona is unchanged.
3. persona-selector-v2.py:1159  record_selection(selection, task_text,
   department, db_path)  → called per sub-task so the selection log +
   persona_assignment reflect each part (and so the NEXT sub-task's variety
   penalty sees the prior pick — intra-decomposition variety, W6 edge case).
4. shared-utils/adaptive_weights.py  get_weights_for_task() / _apply_craft_emphasis
   → the W6 "surface the SPECIALIST not the obvious one" re-weighting tweak in
   `apply_specialist_surfacing()` below is the proposal to fold in here at
   integration time (it generalises CRAFT_TASK_FIT_FLOOR to every craft/execution
   sub-task). Standalone it lives in this file.
5. W6.3 migration `task_subtask_persona` (command-center/app/src/lib/db/
   migrations.ts, after id 021) → the `plan[]` / `subtask_personas[]` array this
   emits is the row source: {task_id, seq, subtask_text, persona_id,
   persona_name, score, department, task_category}.
6. W6.4 command-center/app/src/lib/persona-selector.ts:182-204 → parses the
   `subtask_personas` array from this script's stdout JSON, persists to the
   W6.3 table, renders one persona chip per sub-task.
7. W5 reporting (command-center/app/src/lib/owner-reports.ts) → consumes
   `personas_by_subtask` so the START / DONE messages name persona-per-part.

Token-furnace guard (W6.2): the whole-decomposition LLM budget is bounded by
DECOMP_MAX_SUBTASKS (default 6) and the selector's own per-call
STAGE_D_LLM_FINALIST_CAP (default 12). LLM-backed decomposition is a SINGLE
extra call, gated, with a deterministic heuristic fallback — a fresh box can
never fan out.

Usage:
    python3 decompose-task.py --task "<task>" [--department <dept>] \
        [--format json|human] [--no-llm] [--no-record] [--max-subtasks N]

Exit: 0 on success (incl. single-part collapse), non-zero only on bad args.
"""
import argparse
import importlib.util
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent.parent / "shared-utils"))


# ───────────────────────────────────────────────────────────────────────────
# Load the canonical selector by path (hyphenated filename → importlib).
# This is the SAME by-path loader pattern persona-selector-v2.py uses for
# infer-task-category.py. We reuse the selector's matching engine + helpers;
# we never reimplement matching and never edit the selector.
# ───────────────────────────────────────────────────────────────────────────
def _load_selector():
    """Load persona-selector-v2.py as a module and return it.

    Looks beside this file first (both ship in 23-ai-workforce-blueprint/scripts).
    Honors PERSONA_SELECTOR_PATH override for tests / relocation.
    """
    override = os.environ.get("PERSONA_SELECTOR_PATH")
    candidates = []
    if override:
        candidates.append(Path(override))
    candidates += [
        _HERE / "persona-selector-v2.py",
        _HERE.parent / "scripts" / "persona-selector-v2.py",
    ]
    for c in candidates:
        if c.is_file():
            spec = importlib.util.spec_from_file_location("persona_selector_v2", str(c))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod
    raise FileNotFoundError(
        "persona-selector-v2.py not found next to decompose-task.py "
        "(set PERSONA_SELECTOR_PATH to override)."
    )


_SEL = _load_selector()

# Bind the exact callables we reuse (all live on the selector module namespace).
select_persona = _SEL.select_persona                 # 1651 — the matching engine
detect_interaction_mode = _SEL.detect_interaction_mode
infer_task_category = _SEL.infer_task_category
get_weights_for_task = _SEL.get_weights_for_task
record_selection = _SEL.record_selection             # 1159 — per-subtask record
get_openclaw_paths = _SEL.get_openclaw_paths
find_dashboard_db = _SEL.find_dashboard_db
is_db_found = _SEL.is_db_found
canonical_dept_slug = _SEL.canonical_dept_slug


# ───────────────────────────────────────────────────────────────────────────
# Token-furnace / budget constants (W6.2 whole-decomposition budget)
# ───────────────────────────────────────────────────────────────────────────
def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


DECOMP_MAX_SUBTASKS = _int_env("DECOMP_MAX_SUBTASKS", 6)  # hard cap on parts

# Mechanical-task gate — SINGLE SOURCE: shared-utils/mechanical-gate.py.
# The selector (whole-task) and this decomposer (per-subtask) import the SAME
# classifier (F3.7 sub-gap 3) so the "no persona required" shell-command
# contract can never diverge again. Decomposition additionally treats genuine
# delivery/plumbing verbs ("send it"/"deploy"/... — the spec's sending/
# sequencing step) as mechanical via the gate's DELIVERY_VERBS extension. Loaded
# BY PATH (hyphenated filename); a tiny inline fallback mirrors the BASE rule +
# DELIVERY_VERBS so a box missing the shared file still gates identically.
def _load_shared_mechanical_gate():
    """Load shared-utils/mechanical-gate.py as a module (hyphenated → by path)."""
    candidates = [
        _HERE.parent.parent / "shared-utils" / "mechanical-gate.py",
        _HERE.parent.parent.parent / "shared-utils" / "mechanical-gate.py",
        Path("/data/.openclaw/skills/shared-utils/mechanical-gate.py"),
        Path.home() / ".openclaw" / "skills" / "shared-utils" / "mechanical-gate.py",
    ]
    for c in candidates:
        try:
            if c.is_file():
                spec = importlib.util.spec_from_file_location("mechanical_gate_mod", str(c))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                return mod
        except Exception:
            continue
    return None


_MECH_GATE = _load_shared_mechanical_gate()
if _MECH_GATE is not None:
    _is_mechanical_base = _MECH_GATE.is_mechanical
    DELIVERY_VERBS = _MECH_GATE.DELIVERY_VERBS
    GOVERNANCE_PERSONA_FALLBACK = _MECH_GATE.GOVERNANCE_PERSONA_FALLBACK
    DEFAULT_PERSONA_FALLBACK = _MECH_GATE.DEFAULT_PERSONA_FALLBACK
else:
    # Inline mirror of shared-utils/mechanical-gate.py (BASE rule + extension).
    DELIVERY_VERBS = ("send it", "send the", "schedule the send", "deploy",
                      "publish to", "push to", "upload", "queue the",
                      "sequence the send", "blast")
    GOVERNANCE_PERSONA_FALLBACK = "covey-7-habits"
    DEFAULT_PERSONA_FALLBACK = "blackceo-house-voice"

    def _is_mechanical_base(text, *, delivery_verbs=()):
        if not text:
            return False
        t = text.lower()
        if any(m in t for m in ("check disk", "check memory")):
            return True
        if any(re.search(r"\b" + re.escape(m) + r"\b", t)
               for m in ("restart", "reboot", "ping", "ls", "chmod", "chown")):
            return True
        if delivery_verbs and any(m in t for m in delivery_verbs):
            return True
        return False


def _is_mechanical(text: str) -> bool:
    """Per-subtask mechanical gate: BASE shell-command rule + delivery verbs."""
    return _is_mechanical_base(text, delivery_verbs=DELIVERY_VERBS)


# ───────────────────────────────────────────────────────────────────────────
# Specialist labelling — category/department → the AI specialist ROLE that
# carries this sub-task. Feeds the `specialist` field of the plan and §5
# START/DONE reports ("...the AI specialist..."). Coarse + deterministic;
# the persona is the WHO, the specialist is the ROLE.
# ───────────────────────────────────────────────────────────────────────────
SPECIALIST_BY_CATEGORY = {
    "email-outreach":   "Email & Outreach Specialist",
    "social-post":      "Social Media Specialist",
    "content-write":    "Copywriter",
    "video-script":     "Scriptwriter",
    "video-edit":       "Video Editor",
    "research":         "Researcher / Analyst",
    "strategy":         "Strategist",
    "design":           "Designer",
    "ops":              "Operations Specialist",
    "finance":          "Finance Specialist",
    "legal":            "Legal Specialist",
    "hr":               "People / HR Specialist",
    "customer-service": "Customer Support Specialist",
    "coaching-prompt":  "Coach",
    "review-feedback":  "Editor / Reviewer",
    "general":          "Generalist Specialist",
}
# A few intent words → a sharper specialist than the coarse category gives,
# so "funnel" → Funnel Architect (the Brunson lane) even though it categorises
# as strategy/general. Pure labelling; does NOT change persona matching.
# Short tokens ("ad", "paid") MUST be word-boundary matched so they don't fire
# on substrings ("ad" inside "leadership", "read").
SPECIALIST_INTENT = [
    (("funnel", "opt-in", "checkout flow", "upsell", "order form", "tripwire"), "Funnel Architect"),
    (("landing page", "sales page", "vsl page"), "Landing-Page Builder"),
    (("ad", "ads", "campaign", "creative", "paid"), "Paid-Ads Specialist"),
    (("subject line", "cold email", "newsletter"), "Email & Outreach Specialist"),
]


def _kw_hit(text: str, kw: str) -> bool:
    """Substring for multi-word phrases; word-boundary for single tokens."""
    if " " in kw or "-" in kw:
        return kw in text
    return re.search(r"\b" + re.escape(kw) + r"\b", text) is not None


def specialist_for(subtask_text: str, category: str, department: str) -> str:
    t = (subtask_text or "").lower()
    for kws, label in SPECIALIST_INTENT:
        if any(_kw_hit(t, k) for k in kws):
            return label
    return SPECIALIST_BY_CATEGORY.get(category, SPECIALIST_BY_CATEGORY["general"])


# ───────────────────────────────────────────────────────────────────────────
# THE RE-WEIGHTING TWEAK (W6 §6a — "surface the best-fit SPECIALIST persona,
# not the obvious one").  PROPOSAL — folds into adaptive_weights at integration.
#
# WHY the obvious persona wins today: the 5 layers are
#   mission · owner_values · company_kpis · dept_kpis · task_fit.
# The first four are COMPANY-FIT layers — a broad, on-brand leadership/strategy
# persona scores high on all of them. task_fit (Layer 5) is the SPECIALIST
# signal (semantic + craft + perspective fit to THIS concrete step). On a whole
# task that blend is right. But once a task is DECOMPOSED, every sub-task is a
# single concrete craft step ("write the funnel", "write the copy", "send it"),
# so the specialist signal SHOULD dominate that step. adaptive_weights already
# does this for 6 CRAFT_CATEGORIES via CRAFT_TASK_FIT_FLOOR=0.40; the tweak is
# to GENERALISE that floor to every craft/execution sub-task in a decomposition,
# at a slightly higher per-subtask floor, so e.g. Russell-Brunson's funnel
# task_fit edge beats a generic on-brand persona's company_kpis edge, and
# Michelle-Obama's voice/craft fit wins the copy step over the dept head.
#
# Mechanics: raise task_fit to DECOMP_SUBTASK_TASK_FIT_FLOOR (default 0.45),
# pulling the shortfall proportionally OUT of the four company-fit layers
# (preserving their relative shape), then re-normalise. NO-OP for sub-tasks
# where the company lens SHOULD lead (strategy / coaching), so it never
# over-rotates a "decide the positioning" step onto a craft persona. Provably
# neutral when the floor is already met or set to 0 (env-disable).
# ───────────────────────────────────────────────────────────────────────────
def _subtask_task_fit_floor() -> float:
    try:
        v = float(os.environ.get("DECOMP_SUBTASK_TASK_FIT_FLOOR", "0.45"))
    except (TypeError, ValueError):
        v = 0.45
    return max(0.0, min(v, 0.85))


# Categories where the COMPANY/mission lens should keep leading even as a
# sub-task — surfacing is suppressed for these (no over-rotation).
_SURFACING_SUPPRESS = {"strategy", "coaching-prompt"}


def apply_specialist_surfacing(weights: dict, category: str, subtask_text: str) -> tuple:
    """Return (reweighted_weights, applied: bool). Pure; never raises.

    Generalises adaptive_weights._apply_craft_emphasis to every craft/execution
    sub-task so the SPECIALIST persona (Layer-5 task_fit) outranks the obvious
    company-fit persona. Suppressed for strategy/coaching steps.
    """
    if not isinstance(weights, dict) or "task_fit" not in weights:
        return weights, False
    if category in _SURFACING_SUPPRESS:
        return weights, False
    floor = _subtask_task_fit_floor()
    cur = float(weights.get("task_fit", 0.0))
    if floor <= 0.0 or cur >= floor:
        return weights, False
    others = {k: float(v) for k, v in weights.items() if k != "task_fit"}
    others_sum = sum(others.values())
    remainder = 1.0 - floor
    if others_sum <= 0:
        n = max(len(others), 1)
        scaled = {k: remainder / n for k in others}
    else:
        scaled = {k: v / others_sum * remainder for k, v in others.items()}
    scaled["task_fit"] = floor
    # Re-normalise defensively (mirror adaptive_weights._normalize behaviour).
    total = sum(scaled.values())
    if total > 0 and abs(total - 1.0) > 0.01:
        scaled = {k: v / total for k, v in scaled.items()}
    return scaled, True


# ───────────────────────────────────────────────────────────────────────────
# DECOMPOSITION — ordered sub-tasks. LLM-backed (single gated call) with a
# robust deterministic heuristic fallback. Single-part task → 1-element list
# (collapses to today's exact single-persona behaviour, no regression).
# ───────────────────────────────────────────────────────────────────────────
# Department hint keywords for a sub-task (best-effort; the CEO/router may
# override). Maps a sub-task's intent to a LIVE canonical floor department slug.
#
# DEAD-SLUG RECONCILIATION (F3.7 sub-gap 2): the four legacy targets
# `creative`, `billing`, `hr`, `operations` were NOT live DEPT_DOMAIN_TAGS keys
# — routing a sub-task to them would have landed on raw_dept_tags=[] (Stage B
# loses dept pre-qualification). They are remapped to the live canonical slug
# whose domain tags actually pre-qualify the right persona pool:
#   creative   → marketing            (copywriting/communication domains — copy work)
#   billing    → billing-finance      (finance/operations domains; also the canonical
#                                       alias of "billing", so canonical_dept_slug fixes it)
#   hr         → account-management    (communication/coaching domains — people work)
#   operations → logistics-fulfillment (operations/productivity-systems domains — process work)
# EVERY value is ALSO routed through canonical_dept_slug() at module load
# (below) so a hint can never again be a non-canonical / dead slug, and
# scripts/test-decompose-dept-hints.py LOCKS that every hint target is a live
# canonical DEPT_DOMAIN_TAGS key (mirrors test-dept-domain-mirror.py).
_DEPT_HINT_KEYWORDS_RAW = [
    (("funnel", "landing page", "sales page", "opt-in", "checkout", "upsell", "lead magnet"), "marketing"),
    (("ad", "paid", "campaign creative", "google ads", "meta ads"), "paid-advertisement"),
    (("sales", "pitch", "proposal", "close the", "objection", "discovery call"), "sales"),
    (("email", "outreach", "newsletter", "follow-up", "follow up", "sequence"), "marketing"),
    (("copy", "headline", "write the", "messaging", "voice", "story", "blog", "article"), "marketing"),
    (("design", "logo", "graphic", "mockup", "layout", "visual", "sketchnote"), "graphics"),
    (("video", "reel", "montage", "footage", "edit the cut"), "video"),
    (("research", "analyze", "investigate", "compile", "study"), "research"),
    (("contract", "nda", "policy", "compliance", "agreement", "terms"), "legal"),
    (("invoice", "budget", "pricing", "forecast", "cashflow", "p&l"), "billing-finance"),
    (("hire", "onboard", "recruit", "performance review"), "account-management"),
    (("refund", "ticket", "support", "complaint"), "customer-support"),
    (("sop", "workflow", "automation", "process", "procedure"), "logistics-fulfillment"),
]

# Route every hint target through canonical_dept_slug() at module load so a hint
# is ALWAYS a canonical slug (belt-and-suspenders on top of the explicit remap).
_DEPT_HINT_KEYWORDS = [
    (kws, canonical_dept_slug(dept) or dept) for kws, dept in _DEPT_HINT_KEYWORDS_RAW
]


def _infer_dept_hint(subtask_text: str, default_dept: str) -> str:
    """Return the LIVE canonical dept slug this sub-task hints at, else default.

    Values are pre-canonicalised at module load, so the return is always a
    canonical slug (assuming `default_dept` is already canonical — callers pass
    canonical_dept_slug(caller_dept)).
    """
    t = (subtask_text or "").lower()
    for kws, dept in _DEPT_HINT_KEYWORDS:
        if any(k in t for k in kws):
            return dept
    return default_dept


# ── Heuristic splitter ──────────────────────────────────────────────────────
# Ordered sequence markers + numbered/bulleted lists + "and then" + clause-level
# coordination between distinct action verbs / "for the X section".
_ACTION_VERBS = (
    "write", "create", "build", "design", "draft", "compose", "produce",
    "send", "schedule", "publish", "post", "edit", "research", "analyze",
    "plan", "structure", "set up", "configure", "review", "format", "generate",
    "map", "outline", "sketch", "record", "compile", "summarize", "sequence",
)
_SEQ_SPLIT_RE = re.compile(
    r"(?:\b(?:then|after that|afterwards|next|followed by|and then|finally|"
    r"once that(?:'s| is) done)\b|;|→|->|\n\s*[-*•]\s+|\n\s*\d+[.)]\s+)",
    re.IGNORECASE,
)


def _looks_listy(task_text: str) -> bool:
    return bool(re.search(r"(?:^|\n)\s*(?:\d+[.)]|[-*•])\s+", task_text))


def _split_on_for_sections(chunk: str) -> list:
    """Split a chunk that names multiple deliverable sections.

    e.g. "John Maxwell for the leadership message, a different persona for the
    sales section" → ["...leadership message", "...sales section"]. We split on
    ", ... for the <section>" boundaries while keeping the action verb context.
    """
    # Only split when there are >=2 'for the <noun> (section|part|portion|body)'
    # cues — that is the spec's "one persona for this part, another for that".
    cues = re.findall(r"\bfor the\b", chunk, flags=re.IGNORECASE)
    if len(cues) < 2:
        return [chunk]
    parts = re.split(r"\s*,\s*(?=(?:a |an |another |the )?[\w\- ]{0,40}?\bfor the\b)",
                     chunk, flags=re.IGNORECASE)
    parts = [p.strip() for p in parts if p and p.strip()]
    return parts if len(parts) >= 2 else [chunk]


def _coordination_split(chunk: str) -> list:
    """Split 'X and Y' when both halves start a distinct action verb.

    "write the copy and build the funnel" → two parts. Conservative: requires an
    action verb on BOTH sides so "fast and clean copy" is NOT split.
    """
    pieces = re.split(r"\s+\band\b\s+", chunk, flags=re.IGNORECASE)
    if len(pieces) < 2:
        return [chunk]
    out, buf = [], pieces[0]
    for nxt in pieces[1:]:
        nxt_l = nxt.lower().lstrip()
        starts_action = any(nxt_l.startswith(v) for v in _ACTION_VERBS)
        buf_has_action = any(re.search(r"\b" + re.escape(v) + r"\b", buf.lower()) for v in _ACTION_VERBS)
        if starts_action and buf_has_action:
            out.append(buf.strip())
            buf = nxt
        else:
            buf = buf + " and " + nxt
    out.append(buf.strip())
    return [p for p in out if p]


def heuristic_decompose(task_text: str, max_subtasks: int) -> list:
    """Deterministic decomposition. Returns ordered list of raw sub-task strings.
    Single-part → 1-element list (no regression)."""
    raw = (task_text or "").strip()
    if not raw:
        return []
    # 1) sequence markers / lists
    chunks = [c.strip(" \t,.;") for c in _SEQ_SPLIT_RE.split(raw) if c and c.strip(" \t,.;")]
    if not chunks:
        chunks = [raw]
    # 2) within each chunk, split named sections then coordinated actions
    expanded = []
    for ch in chunks:
        for seg in _split_on_for_sections(ch):
            expanded.extend(_coordination_split(seg))
    # de-dup preserving order, drop trivially short fragments, strip dangling
    # leading/trailing conjunctions left by splitting on a marker mid-clause
    # (e.g. "...our new offer, and" when the split hit "finally" not "and finally").
    seen, ordered = set(), []
    for s in expanded:
        s2 = s.strip(" \t,.;")
        s2 = re.sub(r"^\s*(?:and|then|next|also)\b\s+", "", s2, flags=re.IGNORECASE)
        s2 = re.sub(r"\s*[,;]?\s*(?:and|then)\s*$", "", s2, flags=re.IGNORECASE)
        s2 = s2.strip(" \t,.;")
        key = s2.lower()
        if len(s2) >= 3 and key not in seen:
            seen.add(key)
            ordered.append(s2)
    if not ordered:
        ordered = [raw]
    return ordered[:max_subtasks]


# ── LLM splitter (single gated call) ────────────────────────────────────────
_DECOMP_PROMPT = """You are a project decomposer for an AI workforce. Break the task below into the SMALLEST set of ORDERED, independently-executable sub-tasks, where each sub-task is ONE concrete deliverable that a single specialist persona would own (e.g. "write the leadership message", "write the sales section", "build the funnel", "send the sequence"). Do not invent work. If the task is already a single deliverable, return ONE sub-task.

Return ONLY a JSON array of objects, no prose, max {max} items:
[{{"seq": 1, "subtask": "<imperative phrase>"}}]

TASK:
{task}
"""


def llm_decompose(task_text: str, max_subtasks: int) -> "list | None":
    """Single bounded LLM call to decompose. Returns list of strings or None on
    any failure (caller falls back to heuristic). Reuses llm_score provider
    plumbing (env + OpenAI-compatible chat) — NOT the score-only public API."""
    try:
        import llm_score as _llm  # shared-utils on path
    except Exception:
        return None
    prompt = _DECOMP_PROMPT.format(max=max_subtasks, task=task_text.strip())

    def _try_openrouter():
        api_key = _llm._env("OPENROUTER_API_KEY")
        if not api_key:
            return None
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/trevorotts1/openclaw-onboarding",
            "X-Title": "OpenClaw decompose-task",
        }
        body = {
            "model": "google/gemini-3.1-flash-lite",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 400,
            "reasoning": {"exclude": True},
        }
        payload = _llm._post_chat(url, headers, body)
        return _llm._extract_message(payload)

    def _try_ollama():
        api_key = _llm._env("OLLAMA_CLOUD_API_KEY")
        if not api_key:
            return None
        base = _llm._env("OLLAMA_CLOUD_URL", "https://ollama.com/api").rstrip("/")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body = {
            "model": "deepseek-v4-pro:cloud",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 400,
        }
        payload = _llm._post_chat(base + "/chat/completions", headers, body)
        return _llm._extract_message(payload)

    text = None
    for attempt in (_try_ollama, _try_openrouter):
        try:
            text = attempt()
            if text:
                break
        except Exception:
            text = None
    if not text:
        return None
    parsed = _parse_subtask_json(text)
    if not parsed:
        return None
    return parsed[:max_subtasks]


def _parse_subtask_json(text: str) -> "list | None":
    """Pull an ordered list of sub-task strings out of an LLM response.
    Resilient to code fences / prose around the JSON array."""
    if not text:
        return None
    candidates = [text]
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        candidates.insert(0, m.group(0))
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(obj, list) and obj:
            out = []
            for i, item in enumerate(obj):
                if isinstance(item, dict):
                    st = item.get("subtask") or item.get("task") or item.get("text")
                elif isinstance(item, str):
                    st = item
                else:
                    st = None
                if st and str(st).strip():
                    out.append(str(st).strip())
            if out:
                return out
    return None


def decompose_task(task_text: str, max_subtasks: int = DECOMP_MAX_SUBTASKS,
                   use_llm: bool = True) -> tuple:
    """Return (ordered_subtask_strings, method). method ∈ {'llm','heuristic'}.
    Single-part collapses to a 1-element list. Never raises."""
    max_subtasks = max(1, min(int(max_subtasks), DECOMP_MAX_SUBTASKS))
    if use_llm:
        llm = llm_decompose(task_text, max_subtasks)
        if llm and len(llm) >= 1:
            # If the LLM returned a single part, double-check the heuristic didn't
            # find an obvious multi-part split (belt-and-suspenders, no extra cost).
            if len(llm) == 1:
                h = heuristic_decompose(task_text, max_subtasks)
                if len(h) > 1:
                    return h, "heuristic"
            return llm, "llm"
    return heuristic_decompose(task_text, max_subtasks), "heuristic"


# ───────────────────────────────────────────────────────────────────────────
# Per-sub-task selection — REUSES select_persona (the matching engine).
# Mirrors persona-selector-v2.py main() select-mode for ONE sub-task:
# mode → category → mechanical gate → weights → (surfacing tweak) → match.
# Stickiness is intentionally bypassed (we call select_persona directly, which
# never reads persona_assignment) so two sub-tasks in the SAME category get
# independent fresh fits — the W6 "stickiness collision" edge case is avoided
# by construction.
# ───────────────────────────────────────────────────────────────────────────
def select_for_subtask(subtask_text: str, department: str, paths: dict,
                       db_path, variety: bool = True, *,
                       force_category: "str | None" = None,
                       dept_hint: bool = True) -> dict:
    """Pick the best-fit persona for ONE sub-task.

    department: the caller's default dept (canonicalised here). When
        `dept_hint` is True (default), a per-sub-task department hint refines it
        (F3.7): dept = _infer_dept_hint(subtask_text) || caller_dept — so e.g. a
        "build the funnel" step inside a marketing task scores under `marketing`
        and an "invoice" step under `billing-finance`, each with the right
        Stage-B domain pre-qualification. Hint values are live canonical slugs.
    force_category: when an SOP persona_slot supplies it (F3.9), the task
        category is PINNED to this value instead of inferred from text — this
        deterministically pins the craft floor + primary-domain bonus for the
        slot's craft.
    """
    caller_dept = canonical_dept_slug(department) or department
    # F3.7: per-sub-task department hint refines the caller's default dept.
    dept = _infer_dept_hint(subtask_text, caller_dept) if dept_hint else caller_dept
    # F3.9: an SOP slot forces the category; otherwise infer it from the text.
    category = force_category or infer_task_category(subtask_text)
    mode = detect_interaction_mode(subtask_text)
    specialist = specialist_for(subtask_text, category, dept)

    # Mechanical sub-task (e.g. the send/deploy step) → no persona required,
    # PER sub-task (W6 edge case). The copy part still gets a persona. A slot
    # with a forced category is an explicit CRAFT slot and is never gated as
    # mechanical (a "deploy the funnel" CONTENT slot must still get a persona).
    if force_category is None and _is_mechanical(subtask_text):
        return {
            "persona_id": None,
            "persona_name": None,
            "no_persona_required": True,
            # Q1: a mechanical step keeps the truthful no_persona_required flag
            # but carries a governance persona id so the dispatch gate has a
            # persona for EVERY part (never a naked sub-task).
            "governance_persona_id": GOVERNANCE_PERSONA_FALLBACK,
            "why": "Operational/mechanical step (dispatch/plumbing) — no persona required.",
            "department": dept,
            "specialist": specialist,
            "score": None,
            "task_category": category,
            "interaction_mode": mode,
            "weights_used": None,
            "specialist_surfacing_applied": False,
        }

    base_weights = get_weights_for_task(subtask_text, mode)
    weights, surfaced = apply_specialist_surfacing(base_weights, category, subtask_text)

    sel = select_persona(subtask_text, dept, mode, weights, paths, db_path, variety=variety)

    if not sel.get("persona_id"):
        # NO_PERSONAS_AVAILABLE / empty pool short-circuit (identical to selector).
        return {
            "persona_id": None,
            "persona_name": None,
            "no_persona_required": False,
            "why": sel.get("message") or sel.get("warning") or "no persona available",
            "department": dept,
            "specialist": specialist,
            "score": sel.get("score", 0.0),
            "task_category": category,
            "interaction_mode": mode,
            "warning": sel.get("warning"),
            "weights_used": weights,
            "specialist_surfacing_applied": surfaced,
        }

    why = _explain_pick(sel, category, surfaced)
    return {
        "persona_id": sel["persona_id"],
        "persona_name": sel.get("persona_name") or sel["persona_id"].replace("-", " ").title(),
        "no_persona_required": False,
        "why": why,
        "department": dept,
        "specialist": specialist,
        "score": sel.get("score", 0.0),
        "task_category": category,
        "interaction_mode": sel.get("interaction_mode") or mode,
        "weights_used": weights,
        "specialist_surfacing_applied": surfaced,
        # carry the raw selection so callers (W6.4) and record_selection see layers
        "_selection": sel,
    }


def _explain_pick(sel: dict, category: str, surfaced: bool) -> str:
    """Human 'why this persona for this part' string for the plan + §5 report."""
    name = sel.get("persona_name") or sel.get("persona_id")
    score = sel.get("score", 0.0)
    bits = [f"Best fit for the '{category}' step (score {score:.2f})"]
    layers = sel.get("layers") if isinstance(sel.get("layers"), dict) else {}
    tf = layers.get("task_fit")
    if isinstance(tf, (int, float)):
        bits.append(f"task-fit {tf:.2f}")
    if surfaced:
        bits.append("specialist-surfacing re-weight applied (task_fit floored so the "
                    "specialist outranks the obvious on-brand persona)")
    if sel.get("warning") == "LOW_CONFIDENCE_SELECTION":
        bits.append("LOW CONFIDENCE — consider adding personas via Skill 22")
    return f"{name}: " + "; ".join(bits)


# ───────────────────────────────────────────────────────────────────────────
# task_subtask_persona record path (W6.3 row source / W5 reporting source).
#
# WHY a DEDICATED table — and not record_selection() alone: record_selection
# upserts persona_assignment keyed (department, task_category). Two sub-tasks of
# ONE task that share a category would COLLIDE on that key (the second overwrites
# the first's sticky row), so the per-part history is lost. This table keys on
# (task_id, seq) so EVERY part's persona is recorded faithfully — including the
# mechanical / no-persona parts (persona_id NULL) — which is exactly the
# "which-persona-did-which-subtask" record §5 reporting reads.
#
# Schema mirrors build-plan W6.3 so the Command-Center migration (the canonical
# owner of this table) and this defensive CREATE TABLE IF NOT EXISTS converge:
# columns {task_id, seq, subtask_text, persona_id, persona_name, score,
# department, task_category, created_at}. INSERT names columns explicitly, so a
# CC-created table with extra columns (e.g. a different id default) still works.
# Best-effort, idempotent per task_id (delete-then-insert), never raises.
# Backward-compatible: single-persona (non-combined) selection never calls this.
# ───────────────────────────────────────────────────────────────────────────
_SUBTASK_PERSONA_DDL = """
CREATE TABLE IF NOT EXISTS task_subtask_persona (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    task_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    subtask_text TEXT,
    persona_id TEXT,
    persona_name TEXT,
    score REAL,
    department TEXT,
    task_category TEXT,
    slot TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def record_subtask_personas(task_id: str, subtask_personas: list, db_path) -> int:
    """Persist one row PER sub-task into task_subtask_persona.

    Returns the number of rows written (0 if the DB isn't present or on any
    failure). Never raises — a log-write must never fail the plan.
    """
    if not subtask_personas:
        return 0
    if not is_db_found(db_path):
        return 0
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(_SUBTASK_PERSONA_DDL)
            # F3.9 slot column is additive — a table CREATED by an OLDER CC
            # migration (or an older run of this script) may lack it. Add it
            # idempotently so the INSERT below always has a target column; ignore
            # the "duplicate column" error when it already exists. Never raises.
            try:
                conn.execute("ALTER TABLE task_subtask_persona ADD COLUMN slot TEXT")
            except sqlite3.OperationalError:
                pass
            # Idempotent per task_id: re-running a decomposition for the same
            # task replaces its prior plan rather than appending duplicates.
            conn.execute("DELETE FROM task_subtask_persona WHERE task_id = ?", (task_id,))
            written = 0
            for r in subtask_personas:
                score = r.get("score")
                conn.execute(
                    "INSERT INTO task_subtask_persona "
                    "(task_id, seq, subtask_text, persona_id, persona_name, "
                    " score, department, task_category, slot) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        task_id,
                        int(r.get("seq", 0) or 0),
                        r.get("subtask_text"),
                        r.get("persona_id"),
                        r.get("persona_name"),
                        (float(score) if isinstance(score, (int, float)) else None),
                        r.get("department"),
                        r.get("task_category"),
                        r.get("slot"),
                    ),
                )
                written += 1
            conn.commit()
            return written
        finally:
            conn.close()
    except Exception as e:  # best-effort: never fail the plan on a log write
        print(f"[decompose-task] WARN: task_subtask_persona insert failed: {e}",
              file=sys.stderr)
        return 0


# ───────────────────────────────────────────────────────────────────────────
# SOP persona_slot support (F3.9) — a slot is an SOP-declared sub-task contract:
#   {"slot": "content", "task_category": "content-write",
#    "domains": ["copywriting"], "audience_from": "task", "required": true}
# When slots are supplied, they are the AUTHORITATIVE sub-task list (text
# decomposition is skipped); each slot's task_category is forced so the craft
# floor + primary-domain bonus are pinned deterministically.
# ───────────────────────────────────────────────────────────────────────────
def _slot_subtask_text(slot: dict, task_text: str) -> str:
    """Compose the sub-task text for a slot = step label + (task audience context).

    `audience_from: "task"` (the default) folds the PARENT task text into the
    slot's sub-task text so the audience (e.g. "for an audience of Black women")
    reaches the content slot's Layer-5 semantic query (F3.9 QC requirement). An
    explicit `subtask`/`text` on the slot overrides the composed label.
    """
    label = (slot.get("subtask") or slot.get("text") or slot.get("slot")
             or slot.get("name") or slot.get("task_category") or "work")
    label = str(label).strip()
    parts = [label]
    if str(slot.get("audience_from", "task")).lower() == "task" and (task_text or "").strip():
        parts.append(f"— for this task: {task_text.strip()}")
    return " ".join(p for p in parts if p).strip()


def _apply_required_slot_fallback(entry: dict, slot_label: str) -> dict:
    """Guarantee a REQUIRED slot is never empty (F3.9 → F3.1 fallback).

    When a `required: true` slot's selection returns no persona (empty universe
    / low pool), attach DEFAULT_PERSONA_FALLBACK so the required slot always
    carries a persona. A non-required empty slot is left as-is (the plan records
    the gap truthfully). A client-configured default is resolved UPSTREAM (CC);
    this constant is the last resort.
    """
    entry = dict(entry)
    entry["persona_id"] = DEFAULT_PERSONA_FALLBACK
    entry["persona_name"] = (entry.get("persona_name")
                             or DEFAULT_PERSONA_FALLBACK.replace("-", " ").title())
    entry["no_persona_required"] = False
    entry["fallback"] = "default_persona"
    entry["why"] = (f"{entry['persona_name']}: required SOP slot "
                    f"'{slot_label or entry.get('task_category')}' had no confident "
                    f"match — attached default fallback persona (a required slot "
                    f"may never be empty).")
    return entry


def _work_items_from_slots(slots: list, task_text: str) -> list:
    """Normalise SOP slots → the internal work-item shape used by combined_select."""
    items = []
    for i, slot in enumerate(slots, start=1):
        if not isinstance(slot, dict):
            continue
        items.append({
            "seq": i,
            "text": _slot_subtask_text(slot, task_text),
            "force_category": (slot.get("task_category") or None),
            "required": bool(slot.get("required", False)),
            "slot": (slot.get("slot") or slot.get("name") or None),
        })
    return items


# ───────────────────────────────────────────────────────────────────────────
# Combined entry point — the function W6.1 wires main()'s --decompose flag to.
# ───────────────────────────────────────────────────────────────────────────
def combined_select(task_text: str, department: str, *, use_llm: bool = True,
                    record: bool = True, max_subtasks: int = DECOMP_MAX_SUBTASKS,
                    variety: bool = True, slots: "list | None" = None) -> dict:
    """Decompose → per-sub-task best-fit persona → structured plan.

    Records which persona guided which sub-task (W5 done-report source) and
    returns both the `plan` (rich) and `subtask_personas` (W6.3 row shape).

    slots (F3.9): when a governing SOP declares persona_slots, pass them here.
        Text decomposition is SKIPPED and the slots become the authoritative
        sub-task list — one select_for_subtask per slot, task_category forced to
        the slot's category (pins craft floor + primary-domain bonus), and
        `required: true` slots are guaranteed non-empty via the default fallback.
    """
    paths = get_openclaw_paths()
    db_path = find_dashboard_db()
    db_field = str(db_path) if is_db_found(db_path) else "none"

    # Group every sub-task's persona under ONE task_id (the W5 reporting + W6.3
    # row key). Honor the orchestrator's task id; synthesize a unique-per-run id
    # otherwise so independent runs never collide and re-fires stay idempotent.
    task_id = os.environ.get("OPENCLAW_TASK_ID") or f"decomp-{os.urandom(6).hex()}"

    # F3.9: SOP slots are authoritative when supplied — skip text decomposition.
    slot_items = _work_items_from_slots(slots, task_text) if slots else []
    if slot_items:
        work_items = slot_items[:max_subtasks]
        method = "sop-slots"
    else:
        subtasks, method = decompose_task(task_text, max_subtasks=max_subtasks, use_llm=use_llm)
        if not subtasks:
            subtasks, method = [task_text], "heuristic"
        work_items = [{"seq": i, "text": st, "force_category": None,
                       "required": False, "slot": None}
                      for i, st in enumerate(subtasks, start=1)]

    plan = []
    subtask_personas = []        # W6.3 task_subtask_persona row shape
    personas_by_subtask = []     # compact W5 reporting feed
    llm_select_calls = 0

    for item in work_items:
        seq = item["seq"]
        st = item["text"]
        entry = select_for_subtask(st, department, paths, db_path, variety=variety,
                                   force_category=item["force_category"])
        # F3.9: a REQUIRED slot with no confident match is backfilled with the
        # default fallback persona so the slot is never empty.
        if (item["required"] and not entry.get("persona_id")
                and not entry.get("no_persona_required")):
            entry = _apply_required_slot_fallback(entry, item["slot"])
        entry["slot"] = item["slot"]
        sel = entry.pop("_selection", None)

        # Record per-sub-task so the selection log + persona_assignment reflect
        # each part AND so the NEXT sub-task's variety penalty sees this pick
        # (intra-decomposition variety — W6 edge case). Bypassed for mechanical /
        # no-persona parts (record_selection no-ops on persona_id=None anyway).
        if record and sel and sel.get("persona_id"):
            try:
                record_selection(sel, st, entry["department"], db_path)
            except Exception as e:  # best-effort: never fail the plan on a log write
                entry.setdefault("warnings", []).append(f"record_selection: {e}")
        if entry["score"] is not None and not entry["no_persona_required"]:
            llm_select_calls += 1

        plan.append({
            "seq": seq,
            "subtask": st,
            "slot": entry.get("slot"),
            "persona": entry["persona_name"],
            "persona_id": entry["persona_id"],
            "why": entry["why"],
            "department": entry["department"],
            "specialist": entry["specialist"],
            "score": entry["score"],
            "task_category": entry["task_category"],
            "no_persona_required": entry["no_persona_required"],
            "fallback": entry.get("fallback"),
            "governance_persona_id": entry.get("governance_persona_id"),
            "specialist_surfacing_applied": entry["specialist_surfacing_applied"],
            "weights_used": entry["weights_used"],
        })
        subtask_personas.append({
            "seq": seq,
            "subtask_text": st,
            "slot": entry.get("slot"),
            "persona_id": entry["persona_id"],
            "persona_name": entry["persona_name"],
            "score": entry["score"],
            "department": entry["department"],
            "task_category": entry["task_category"],
        })
        personas_by_subtask.append({
            "seq": seq,
            "subtask": st,
            "slot": entry.get("slot"),
            "persona": entry["persona_name"],
            "specialist": entry["specialist"],
            "department": entry["department"],
        })

    # Persist which-persona-did-which-subtask (W6.3 table / W5 reporting source).
    # Gated on `record`; per-part record_selection rows above feed stickiness &
    # variety, this dedicated table feeds the per-part report without collision.
    subtask_persona_rows_written = 0
    if record:
        subtask_persona_rows_written = record_subtask_personas(task_id, subtask_personas, db_path)

    distinct = {p["persona_id"] for p in plan if p["persona_id"]}
    return {
        "mode": "combined",
        "task": task_text,
        "task_id": task_id,
        "department": canonical_dept_slug(department) or department,
        "decomposition_method": method,
        "slot_driven": bool(slot_items),  # F3.9: SOP slots were authoritative
        "subtask_count": len(plan),
        "distinct_persona_count": len(distinct),
        "subtask_persona_rows_written": subtask_persona_rows_written,
        "weighting_tweak": {
            "name": "specialist-surfacing-v1",
            "what": "Per sub-task, floor task_fit (Layer 5, the specialist signal) "
                    "so the best-fit SPECIALIST persona outranks the obvious "
                    "on-brand company-fit persona; generalises adaptive_weights "
                    "CRAFT_TASK_FIT_FLOOR to every craft/execution sub-task; "
                    "suppressed for strategy/coaching steps.",
            "floor": _subtask_task_fit_floor(),
            "env": "DECOMP_SUBTASK_TASK_FIT_FLOOR (0 disables); "
                   "DECOMP_MAX_SUBTASKS (budget cap)",
            "integration": "fold into shared-utils/adaptive_weights.py "
                           "(_apply_craft_emphasis / get_weights_for_task)",
        },
        "plan": plan,                          # rich — for humans + W6.4 cards
        "subtask_personas": subtask_personas,  # W6.3 task_subtask_persona rows
        "personas_by_subtask": personas_by_subtask,  # W5 START/DONE report feed
        "budget": {
            "max_subtasks": max_subtasks,
            "stage_d_llm_finalist_cap": getattr(_SEL, "STAGE_D_LLM_FINALIST_CAP", None),
            "persona_select_calls": llm_select_calls,
        },
        "db": db_field,
    }


# ───────────────────────────────────────────────────────────────────────────
# CLI
# ───────────────────────────────────────────────────────────────────────────
def _format_human(result: dict) -> str:
    lines = [
        f"COMBINED PLAN — {result['subtask_count']} sub-task(s), "
        f"{result['distinct_persona_count']} distinct persona(s) "
        f"[decomp: {result['decomposition_method']}]",
        f"task: {result['task']}",
        "",
    ]
    for p in result["plan"]:
        persona = p["persona"] or ("(no persona — mechanical)" if p["no_persona_required"] else "(none)")
        slot_tag = f" {{{p['slot']}}}" if p.get("slot") else ""
        lines.append(f"  {p['seq']}.{slot_tag} [{p['department']}/{p['specialist']}] {p['subtask']}")
        lines.append(f"       → {persona}")
        lines.append(f"         {p['why']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Decompose a task into ordered sub-tasks and pick a best-fit "
                    "persona PER sub-task (combined / per-subtask personas, spec §6)."
    )
    parser.add_argument("--task", required=True, help="The task description to decompose.")
    parser.add_argument("--department", default="general-task",
                        help="Default/hint department slug (per-subtask hints may refine).")
    parser.add_argument("--format", default="json", choices=["json", "human"])
    parser.add_argument("--no-llm", action="store_true",
                        help="Force deterministic heuristic decomposition (no LLM call).")
    parser.add_argument("--no-record", action="store_true",
                        help="Do not write per-subtask selections to the log / assignment DB.")
    parser.add_argument("--no-variety", action="store_true",
                        help="Disable anti-repetition variety in per-subtask selection.")
    parser.add_argument("--max-subtasks", type=int, default=DECOMP_MAX_SUBTASKS,
                        help=f"Hard cap on sub-tasks (token-furnace budget; default {DECOMP_MAX_SUBTASKS}).")
    parser.add_argument("--slots", default=None,
                        help="F3.9: JSON array of SOP persona_slot objects "
                             "({slot, task_category, domains, audience_from, "
                             "required}). When supplied, decomposition is SKIPPED "
                             "and slots are the authoritative sub-task list. "
                             "Accepts an inline JSON string or a @path to a file.")
    args = parser.parse_args()

    slots = None
    if args.slots:
        raw = args.slots
        if raw.startswith("@"):
            raw = Path(raw[1:]).read_text(encoding="utf-8")
        slots = json.loads(raw)
        if not isinstance(slots, list):
            parser.error("--slots must be a JSON array of slot objects")

    result = combined_select(
        args.task,
        args.department,
        use_llm=not args.no_llm,
        record=not args.no_record,
        max_subtasks=args.max_subtasks,
        variety=not args.no_variety,
        slots=slots,
    )
    if args.format == "human":
        print(_format_human(result))
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
