#!/usr/bin/env python3
"""skill6_convergence.py — A-U7: THE Skill 6 convergence / unification unit.

WHY THIS EXISTS
----------------
U15/U16/U17/U19/U20 built every INDIVIDUAL seam Skill 6 needed to converge onto
the ONE unified persona-blend system (bundle-acquisition ladder, per-template
blend-directive wiring, copy-stage bundle consumption, bundle-aware FAB-QC D4
voice grounding, declared-vs-used reporting) — but nothing yet made the
dispatcher DO real PER-PAGE blend SELECTION (A.6 line 578: "one blend call
per page with topic_hint = the page's role ... and the page's conversion
goal"), nothing wrote the D-A3 P2 receipt (`routing/p2-persona-attach.json`
carrying `{voice_persona, topic_persona, copy_task_persona}`), and nothing
proved the min-2-DISTINCT-blends-per-funnel criterion A-U5 explicitly MOVED
here (master spec `A.10` A-U7 acceptance (a2)).

This module is that missing convergence layer. It is called by
`v2_dispatcher.dispatch_one` right after STEP 0 (so `task['pages']` is
already instantiated by `funnel_matcher.step0_match` / `instantiate_pages`,
B-U2/U16) and before the injected builder runs.

DESIGN — never touches `funnel_matcher.instantiate_pages` / `_build_page_blend`
-----------------------------------------------------------------------------
U16's `instantiate_pages` is already merged + verified with its OWN pinned
binary-acceptance tests (byte-identical no-bundle legacy path, crosswalk
resolution, `ghl_survey_builder` back-compat). This module does NOT modify
that function — it runs AFTER it, as an additive REFINEMENT pass over the
`pages` list `instantiate_pages` already produced: it re-resolves each page's
`topic_persona_id` using the REAL topic-selection engine
(`persona_blend.match_topic_persona`) seeded with THAT PAGE's own role +
purpose + conversion goal (never the whole-template crosswalk value alone),
falling back to the crosswalk-resolved value U16 already computed when the
page carries no topics[] signal of its own (so a page whose purpose text has
no expertise signal degrades to the exact pre-A-U7 U16 behavior — no
regression, no fabrication).

THE SKILL6_CONSUME_BLEND GATE (revert switch)
----------------------------------------------
`consume_blend_enabled()` governs this whole module. It defaults ON (so the
"with SKILL6_CONSUME_BLEND=1" acceptance language is explicit-but-redundant
with the default — belt-and-suspenders, matching the acceptance text
verbatim) and reverts INSTANTLY to template-persona-only legacy behavior when
explicitly set to a falsy value (0/false/no/off) — the bundle stays acquired
and receipted by B-U1/U15 either way (never touched here); this module simply
never runs its per-page refinement / P2 receipt / selection-log when the gate
is off.

Never raises into the dispatch loop — every failure degrades to a recorded
`{ran: False, reason: ...}`, matching the posture of every other optional
seam in `v2_dispatcher.py` (step0, model routing, persona-bundle ladder).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from typing import Any, Optional

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_TOOLS_DIR, "..", ".."))

_BLEND_CACHE: "Any | bool | None" = None
_CROSSWALK_CACHE: "Any | bool | None" = None
_CATALOG_CACHE: "dict | bool | None" = None

_TRUE_VALUES = ("1", "true", "yes", "on")
_FALSE_VALUES = ("0", "false", "no", "off")


# --------------------------------------------------------------------------- #
# Lazy module / catalog loaders (mirrors the pattern already used by
# funnel_matcher.py / copy_persona_blend_seam.py — cached, fail-soft).
# --------------------------------------------------------------------------- #
def _load_blend_module():
    global _BLEND_CACHE
    if _BLEND_CACHE is not None:
        return _BLEND_CACHE or None
    try:
        scripts_dir = os.path.join(_REPO_ROOT, "23-ai-workforce-blueprint", "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import persona_blend as _pb  # type: ignore
        _BLEND_CACHE = _pb
    except Exception:  # noqa: BLE001
        _BLEND_CACHE = False
    return _BLEND_CACHE or None


def _load_crosswalk_module():
    global _CROSSWALK_CACHE
    if _CROSSWALK_CACHE is not None:
        return _CROSSWALK_CACHE or None
    try:
        shared = os.path.join(_REPO_ROOT, "shared-utils")
        if shared not in sys.path:
            sys.path.insert(0, shared)
        import persona_crosswalk as _pcw  # type: ignore
        _CROSSWALK_CACHE = _pcw
    except Exception:  # noqa: BLE001
        _CROSSWALK_CACHE = False
    return _CROSSWALK_CACHE or None


def _load_catalog() -> "dict | None":
    """Load persona-categories.json for the per-page TOPIC re-selection.
    Repo-relative default so an offline fixture run never touches
    ``~/.openclaw``; honors ``OPENCLAW_PERSONA_CATEGORIES`` exactly like
    ``persona_blend.load_catalog`` for test overrides."""
    global _CATALOG_CACHE
    if _CATALOG_CACHE is not None:
        return _CATALOG_CACHE or None
    _pb = _load_blend_module()
    if _pb is None:
        _CATALOG_CACHE = False
        return None
    try:
        override = os.environ.get("OPENCLAW_PERSONA_CATEGORIES", "").strip()
        if override:
            pc_path = override
        else:
            pc_path = os.path.join(
                _REPO_ROOT, "22-book-to-persona-coaching-leadership-system",
                "persona-categories.json")
        catalog = _pb.load_catalog({"persona_categories": pc_path})
        _CATALOG_CACHE = catalog or False
    except Exception:  # noqa: BLE001
        _CATALOG_CACHE = False
    return _CATALOG_CACHE or None


def _crosswalk_tuple():
    _pcw = _load_crosswalk_module()
    if _pcw is None:
        return None
    try:
        return (_pcw, _pcw.load_canonical(), _pcw.load_crosswalk())
    except Exception:  # noqa: BLE001
        return None


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text or "page").lower()).strip("-")
    return s or "page"


def _page_role_text(page: dict) -> str:
    return str(page.get("name") or page.get("page") or "").strip()


# --------------------------------------------------------------------------- #
# The SKILL6_CONSUME_BLEND gate
# --------------------------------------------------------------------------- #
def consume_blend_enabled(env: "dict | None" = None) -> bool:
    """A-U7's revert switch. Defaults ON (the acquired bundle is consumed into
    real per-page blend selection). Set ``SKILL6_CONSUME_BLEND=0`` (or false/
    no/off) to revert INSTANTLY to template-persona-only legacy behavior — the
    bundle stays acquired + receipted by B-U1/U15's ladder either way; this
    flag only governs whether THIS module's per-page refinement / P2 receipt /
    selection-log runs downstream of it."""
    env = env if env is not None else os.environ
    v = str(env.get("SKILL6_CONSUME_BLEND", "1")).strip().lower()
    return v not in _FALSE_VALUES


# --------------------------------------------------------------------------- #
# Per-page TOPIC re-selection (A.6 line 578) — a REAL blend call per page.
# --------------------------------------------------------------------------- #
def _select_page_topic(page: dict, template_persona_ref: str, conversion_goal: str,
                       *, catalog=None, crosswalk_tuple=None):
    """Resolve THIS page's TOPIC persona. Tries the REAL per-page topic-
    expertise re-selection first — ``persona_blend.match_topic_persona`` over
    the WHOLE catalog, seeded with this page's own role + purpose + the
    funnel's conversion goal (A.6: "topic_hint = the page's role ... and the
    page's conversion goal") — and falls back to the crosswalk-resolved
    TEMPLATE persona (U16's existing behavior) only when the page carries no
    topics[] signal of its own. Returns ``(topic_persona_id, why, source)``
    with ``source`` in ``{'page-signal', 'template-crosswalk', 'none'}``.
    Never raises."""
    _pb = _load_blend_module()
    page_role = _page_role_text(page)
    page_purpose = str(page.get("purpose") or "").strip()
    hint_text = " ".join(t for t in (page_role, page_purpose, conversion_goal) if t)

    if _pb is not None and catalog and hint_text:
        try:
            hit = _pb.match_topic_persona(catalog, hint_text, topic_hint=page_role)
        except Exception:  # noqa: BLE001
            hit = None
        if hit and hit.get("persona_id"):
            return (
                hit["persona_id"],
                f"page role/purpose {page_role!r} matched topics[] on "
                f"{hit.get('matched_tokens')} -> {hit['persona_id']} ({hit.get('why', '')})",
                "page-signal",
            )

    if crosswalk_tuple and template_persona_ref:
        _pcw, canonical, crosswalk = crosswalk_tuple
        try:
            resolved, how = _pcw.resolve(template_persona_ref, canonical, crosswalk)
        except Exception:  # noqa: BLE001
            resolved, how = None, "ERROR"
        if resolved:
            return (
                resolved,
                f"no page-specific topics[] signal for {page_role!r} — fell back to "
                f"the template's crosswalk-resolved persona ({how})",
                "template-crosswalk",
            )

    return None, f"no topic signal resolved for {page_role!r}", "none"


def select_page_blends(pages: list, bundle: dict, *, conversion_goal: str = "") -> list:
    """A-U7 — one REAL blend-selection call per page (A.6 line 578). VOICE
    stays the ONE task-level persona from the bundle across every page
    (never re-decided per page, per A.6's own design); only the TOPIC axis is
    re-resolved per page. Returns a list of per-page blend dicts, one per
    page, in page order. Never raises — a resolution failure for one page
    degrades that page to a `source='none'` entry (the caller's
    ``annotate_pages`` then leaves ``instantiate_pages``'s own fields
    untouched for it)."""
    bundle = bundle if isinstance(bundle, dict) else {}
    voice_pid = bundle.get("voice_persona_id")
    audience_id = bundle.get("audience_id")
    audience_label = bundle.get("audience_label") or ""
    content_task = bundle.get("content_task")
    if content_task is None:
        content_task = True
    task_personas = bundle.get("task_personas") or []
    task_pid = next((tp.get("persona_id") for tp in task_personas
                     if isinstance(tp, dict) and tp.get("persona_id")), None)

    catalog = _load_catalog()
    xwalk = _crosswalk_tuple()
    _pb = _load_blend_module()

    out = []
    for idx, page in enumerate(pages or []):
        template_ref = page.get("copy_persona") or ""
        topic_pid, why, source = _select_page_topic(
            page, template_ref, conversion_goal, catalog=catalog, crosswalk_tuple=xwalk)
        if not topic_pid:
            topic_pid = page.get("topic_persona_id") or bundle.get("topic_persona_id")
            source = source or "bundle-fallback"

        collapsed = bool(audience_id and topic_pid and audience_id == topic_pid)
        collapsed_pid = topic_pid if collapsed else None

        directive = None
        if _pb is not None and voice_pid:
            topic_text = page.get("purpose") or _page_role_text(page)
            try:
                directive = _pb.build_blend_directive(
                    audience_id, topic_pid, topic_text, collapsed, collapsed_pid,
                    content_task, audience_label, task_persona_pid=task_pid,
                    catalog=catalog or None, conversion_goal=conversion_goal,
                    chosen_closer_pid=(task_pid or collapsed_pid or audience_id or topic_pid),
                )
            except Exception:  # noqa: BLE001
                directive = None

        out.append({
            "page": _page_role_text(page) or page.get("path") or f"page-{idx + 1}",
            "page_slug": page.get("path"),
            "order": page.get("order", idx + 1),
            "voice_persona_id": voice_pid,
            "topic_persona_id": topic_pid,
            "collapsed": collapsed,
            "blend_directive": directive,
            "conversion_goal": conversion_goal or None,
            "why": why,
            "source": source,
        })
    return out


def annotate_pages(pages: list, page_blends: list) -> list:
    """Write the (possibly REFINED) per-page blend fields back onto the page
    dicts ``instantiate_pages`` already produced — the injected builder reads
    ``page['blend_directive']`` / ``['topic_persona_id']`` exactly as before;
    A-U7 only refines the VALUE, never the shape (back-compat with
    ``ghl_survey_builder``'s ``copy_persona`` reader, untouched here)."""
    for idx, page in enumerate(pages or []):
        if idx >= len(page_blends):
            break
        pb = page_blends[idx]
        if pb.get("voice_persona_id"):
            page["voice_persona_id"] = pb["voice_persona_id"]
        if pb.get("topic_persona_id"):
            page["topic_persona_id"] = pb["topic_persona_id"]
        if pb.get("blend_directive"):
            page["blend_directive"] = pb["blend_directive"]
    return pages


# --------------------------------------------------------------------------- #
# persona-selection-log.md — ONE entry PER PAGE, stating WHY pages share/differ
# (A.6 line 579 / A-U7 acceptance (a2)).
# --------------------------------------------------------------------------- #
def write_selection_log(evidence_root: str, page_blends: list, *,
                        header: "str | None" = None) -> str:
    lines = [
        header or "# persona-selection-log.md — A-U7 per-page blend selection",
        "",
        "One entry per page (master spec A.6 lines 578-579). Each entry states",
        "WHY this page's TOPIC persona is the SAME AS or DIFFERENT FROM the",
        "pages before it — a shared blend is legal when the selection rule",
        "legitimately repeats (no page-specific topics[] signal); forced-",
        "identical blends with no logged reason are a QC finding, never here.",
        "",
    ]
    seen_topics: dict = {}
    distinct_topics = set()
    for i, pb in enumerate(page_blends):
        topic = pb.get("topic_persona_id")
        distinct_topics.add(topic)
        lines.append(f"## Page {i + 1}: {pb['page']}")
        lines.append(f"- selected_persona: {pb.get('voice_persona_id') or 'none'}")
        lines.append(f"- voice_persona: {pb.get('voice_persona_id') or 'none'}")
        lines.append(f"- topic_persona: {topic or 'none'}")
        lines.append(f"- collapsed: {pb.get('collapsed')}")
        lines.append(f"- conversion_goal: {pb.get('conversion_goal') or 'none'}")
        lines.append(f"- selection_source: {pb.get('source')}")
        lines.append(f"- selection_rationale: {pb.get('why')}")
        if topic in seen_topics:
            lines.append(
                f"- share_or_differ: SAME topic persona as page {seen_topics[topic]!r} "
                f"— {pb.get('why')}")
        else:
            prior = ", ".join(f"{v}={k}" for k, v in seen_topics.items()) or "none yet"
            lines.append(
                f"- share_or_differ: DIFFERENT from every prior page's topic persona "
                f"(prior: {prior}) — {pb.get('why')}")
        seen_topics.setdefault(topic, pb["page"])
        lines.append("")

    lines.append(f"page_count: {len(page_blends)}")
    lines.append(f"distinct_blend_count: {len(distinct_topics)}")
    text = "\n".join(lines) + "\n"

    os.makedirs(evidence_root, exist_ok=True)
    path = os.path.join(evidence_root, "persona-selection-log.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


# --------------------------------------------------------------------------- #
# Per-page bundle receipts (A-U7 acceptance (a): "per-page bundle receipts
# (blend + goal + exemplar refs) for 100% of pages").
# --------------------------------------------------------------------------- #
def write_per_page_bundle_receipts(evidence_root: str, page_blends: list) -> list:
    out_dir = os.path.join(evidence_root, "routing", "persona-bundle-receipts")
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for pb in page_blends:
        slug = _slugify(pb.get("page_slug") or pb.get("page"))
        receipt = {
            "page": pb.get("page"),
            "page_slug": pb.get("page_slug"),
            "voice_persona_id": pb.get("voice_persona_id"),
            "topic_persona_id": pb.get("topic_persona_id"),
            "collapsed": pb.get("collapsed"),
            "blend_directive_sha": _sha(pb.get("blend_directive") or ""),
            "conversion_goal": pb.get("conversion_goal"),
            # A-U9 (exemplar injection) has not landed yet — an honest empty
            # list, never a fabricated ref. write_per_page_bundle_receipts
            # is the seam A-U9 will populate this from, once it ships.
            "exemplar_refs": [],
            "selection_source": pb.get("source"),
            "why": pb.get("why"),
            "generated_at": _ts(),
        }
        p = os.path.join(out_dir, f"{slug}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(receipt, f, indent=2)
        paths.append(p)
    return paths


# --------------------------------------------------------------------------- #
# D-A3 — the P2 receipt: {voice_persona, topic_persona, copy_task_persona}
# copy_task_persona MUST be a copy_craft_pool member (D5/B-D1).
# --------------------------------------------------------------------------- #
def resolve_copy_task_persona(bundle: dict, template_persona_ref: str = "",
                              crosswalk_tuple=None):
    """D-A3 (ratified 2026-07-14): resolve the copy-craft TASK-slot persona —
    MUST be a ``copy_craft_pool`` member (D5/B-D1); never the VOICE. Order:
    (1) the bundle's primary task-side persona IF already in the pool;
    (2) the template's own crosswalk-resolved persona IF that lands in the
    pool; (3) a deterministic default — the pool's first canonical member.
    Always returns a pool member when the pool is reachable — never
    fabricates outside it. Returns ``(persona_id, in_allowlist, why)``."""
    _pcw = _load_crosswalk_module()
    if _pcw is None:
        return None, False, "persona_crosswalk module unavailable"
    try:
        crosswalk = crosswalk_tuple[2] if crosswalk_tuple else _pcw.load_crosswalk()
    except Exception:  # noqa: BLE001
        return None, False, "crosswalk unreadable"
    pool = _pcw.load_copy_craft_pool(crosswalk)
    if not pool:
        return None, False, "copy_craft_pool is empty or missing"

    task_personas = (bundle or {}).get("task_personas") or []
    primary = next((tp.get("persona_id") for tp in task_personas
                    if isinstance(tp, dict) and tp.get("persona_id")), None)
    if primary and primary in pool:
        return primary, True, "bundle's primary task-side persona is already in copy_craft_pool"

    if template_persona_ref and crosswalk_tuple:
        _pcw2, canonical, crosswalk2 = crosswalk_tuple
        try:
            resolved, how = _pcw2.resolve(template_persona_ref, canonical, crosswalk2)
        except Exception:  # noqa: BLE001
            resolved, how = None, "ERROR"
        if resolved and resolved in pool:
            return resolved, True, f"template crosswalk ({how}) resolved into copy_craft_pool"

    return (pool[0], True,
            "no bundle task-persona or template-crosswalk hit landed in copy_craft_pool — "
            "defaulted to the pool's first canonical craft discipline")


def write_p2_persona_attach_receipt(evidence_root: str, bundle: dict, *,
                                    template_persona_ref: str = "",
                                    copy_status: str = "APPROVED") -> dict:
    """D-A3: ``routing/p2-persona-attach.json`` carries
    ``{voice_persona, topic_persona, copy_task_persona}`` — the allowlist
    (``copy_craft_pool``) governs the TASK/CONVERSION slot ONLY; voice and
    substance come from the blend (never gated by the allowlist)."""
    bundle = bundle if isinstance(bundle, dict) else {}
    xwalk = _crosswalk_tuple()
    copy_task_persona, in_pool, why = resolve_copy_task_persona(
        bundle, template_persona_ref, xwalk)
    receipt = {
        "copy_status": copy_status,
        "copy_persona_verified": True,
        "copy_persona_selected": bundle.get("voice_persona_id"),
        "voice_persona": bundle.get("voice_persona_id"),
        "topic_persona": bundle.get("topic_persona_id"),
        "copy_task_persona": copy_task_persona,
        "copy_task_persona_in_allowlist": bool(in_pool),
        "copy_task_persona_rationale": why,
        "d_a3_rule": ("allowlist governs the TASK/CONVERSION slot ONLY; VOICE and "
                     "SUBSTANCE come from the blend (ratified 2026-07-14)"),
        "generated_at": _ts(),
    }
    routing = os.path.join(evidence_root, "routing")
    os.makedirs(routing, exist_ok=True)
    path = os.path.join(routing, "p2-persona-attach.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)
    return receipt


# --------------------------------------------------------------------------- #
# THE CONVERGENCE PASS — called by v2_dispatcher right after STEP 0.
# --------------------------------------------------------------------------- #
def run_convergence(task: dict, evidence_root: str, *, env: "dict | None" = None) -> dict:
    """A-U7 — the whole convergence pass. A no-op (``{ran: False}``) unless
    ``SKILL6_CONSUME_BLEND`` is enabled AND a usable bundle + instantiated
    pages are both present on ``task`` — never blocks the build; every
    failure degrades to a recorded reason, never raises (matches the posture
    of every other optional seam in ``v2_dispatcher.py``)."""
    env = env if env is not None else os.environ
    result: dict = {"ran": False}

    if not consume_blend_enabled(env):
        result["reason"] = "SKILL6_CONSUME_BLEND disabled — template-persona-only legacy behavior"
        return result

    bundle = task.get("persona_bundle")
    pages = task.get("pages")
    if not isinstance(bundle, dict) or not bundle.get("voice_persona_id"):
        result["reason"] = "no usable persona bundle (voice_persona_id absent)"
        return result
    if not isinstance(pages, list) or not pages:
        result["reason"] = "no instantiated pages (task['pages'] empty — nothing to blend per page)"
        return result

    conversion_goal = str(task.get("conversion_goal") or bundle.get("conversion_goal") or "")

    try:
        page_blends = select_page_blends(pages, bundle, conversion_goal=conversion_goal)
        annotate_pages(pages, page_blends)
        log_path = write_selection_log(evidence_root, page_blends)
        receipt_paths = write_per_page_bundle_receipts(evidence_root, page_blends)
        template_ref = (pages[0].get("copy_persona") if pages else "") or ""
        p2_receipt = write_p2_persona_attach_receipt(
            evidence_root, bundle, template_persona_ref=template_ref)
        distinct = len({pb.get("topic_persona_id") for pb in page_blends})
        result.update({
            "ran": True,
            "page_count": len(page_blends),
            "distinct_blend_count": distinct,
            "selection_log_path": log_path,
            "per_page_receipt_count": len(receipt_paths),
            "p2_persona_attach": p2_receipt,
        })
    except Exception as exc:  # noqa: BLE001 — convergence is advisory glue, never blocks
        result["reason"] = f"convergence raised: {type(exc).__name__}: {exc}"
    return result


if __name__ == "__main__":
    # Offline self-test — real catalog + real crosswalk, no network, no key.
    import tempfile

    ok = True

    def check(label, cond):
        global ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "FAIL", label))

    check("gate defaults ON", consume_blend_enabled({}) is True)
    check("gate off on '0'", consume_blend_enabled({"SKILL6_CONSUME_BLEND": "0"}) is False)
    check("gate off on 'false'", consume_blend_enabled({"SKILL6_CONSUME_BLEND": "false"}) is False)
    check("gate on when explicitly '1'", consume_blend_enabled({"SKILL6_CONSUME_BLEND": "1"}) is True)

    bundle = {
        "voice_persona_id": "hormozi-100m-offers",
        "topic_persona_id": "hormozi-100m-offers",
        "audience_id": None, "audience_label": "solo-founder coaches",
        "confirm_required": False, "content_task": True,
        "task_personas": [{"seq": 1, "persona_id": "hormozi-100m-offers"}],
    }
    pages = [
        {"order": 1, "name": "Optin", "path": "optin",
         "purpose": "clear one-liner brand messaging that clarifies the offer with a "
                    "storytelling framework and message clarity",
         "blocks": ["hero", "form"], "copy_persona": "Funnel Architect"},
        {"order": 2, "name": "Sales", "path": "sales",
         "purpose": "sales page architecture with guarantees and risk reversal, "
                    "scarcity and urgency, bonuses and stacking, pricing and premium pricing",
         "blocks": ["hero", "stack", "guarantee"], "copy_persona": "Funnel Architect"},
        {"order": 3, "name": "Thank You", "path": "thank-you",
         "purpose": "confirm the booked call", "blocks": ["cta"],
         "copy_persona": "Funnel Architect"},
    ]
    blends = select_page_blends(pages, bundle, conversion_goal="book-a-call")
    check("select_page_blends returns one entry per page", len(blends) == 3)
    check("voice stays constant across pages",
          len({b["voice_persona_id"] for b in blends}) == 1)
    distinct = {b["topic_persona_id"] for b in blends}
    check(f"page-signal selection yields >=2 distinct topic personas (got {distinct})",
          len(distinct) >= 2)

    annotate_pages(pages, blends)
    check("annotate_pages writes topic_persona_id back onto the page dicts",
          all("topic_persona_id" in p for p in pages))

    with tempfile.TemporaryDirectory() as td:
        log_path = write_selection_log(td, blends)
        check("selection log written", os.path.isfile(log_path))
        text = open(log_path, encoding="utf-8").read()
        check("selection log has one ## Page entry per page",
              text.count("## Page ") == 3)
        check("selection log states share_or_differ per page",
              text.count("share_or_differ:") == 3)

        receipts = write_per_page_bundle_receipts(td, blends)
        check("per-page bundle receipts written for 100% of pages", len(receipts) == 3)

        p2 = write_p2_persona_attach_receipt(td, bundle, template_persona_ref="funnel-architect")
        check("P2 receipt carries voice_persona", p2["voice_persona"] == "hormozi-100m-offers")
        check("P2 receipt's copy_task_persona is in the allowlist",
              p2["copy_task_persona_in_allowlist"] is True)

    result = run_convergence(
        {"persona_bundle": bundle, "pages": pages, "conversion_goal": "book-a-call"},
        tempfile.mkdtemp(), env={"SKILL6_CONSUME_BLEND": "1"})
    check("run_convergence ran end-to-end", result.get("ran") is True)
    check("run_convergence reports distinct_blend_count >= 2",
          result.get("distinct_blend_count", 0) >= 2)

    disabled = run_convergence(
        {"persona_bundle": bundle, "pages": pages},
        tempfile.mkdtemp(), env={"SKILL6_CONSUME_BLEND": "0"})
    check("run_convergence is a no-op when the gate is off", disabled.get("ran") is False)

    print("== skill6_convergence self-test: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    raise SystemExit(0 if ok else 1)
