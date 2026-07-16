#!/usr/bin/env python3
"""persona_for_job.py — the ONE shared persona entry point for the content engines (F4.3).

WHY THIS EXISTS
---------------
Before this, content-engine skills 49/50/52/53/54/56/57 each carried their OWN
local notion of "persona": static kanban labels, a self-contained email tone
library, a prompt-level "pick a well-known person" instruction, per-variant baked
copywriter strings, and a fail-closed deferred stub. None of them consulted the
canonical 5-layer matcher, so their output never joined the persona
learning/adherence loop and could not be governed by the library's craft
specialists.

This module is the single adoption seam. Every engine calls ``persona_for_job``
(``job_text, department, sop_slug -> selection JSON``) instead of inventing its
own persona logic. It delegates the actual match to the canonical selector
(``23-ai-workforce-blueprint/scripts/persona-selector-v2.py``), which owns the
funnel, stickiness, variety, Layer-5 semantics and — critically — the write to
``persona_selection_log`` (so engine selections finally feed the learning loop).

FAIL-CLOSED CONSUMER CONTRACT (modeled on Skill-23 SOP-07's
``funnel_rubrics.assert_persona_grounded``)
-----------------------------------------------------------------------------
The returned selection is NEVER "naked":

  * A normal job  -> ``persona_id`` is a real, usable persona id.
  * A mechanical/operational job -> ``persona_id`` is ``None`` **but**
    ``no_persona_required`` is ``True`` AND ``governance_persona_id`` carries the
    governance fallback (``covey-7-habits``, decision Q1) so a governance frame
    still exists for every job.
  * A degraded box (empty persona universe, selector missing/timeout, selector
    returned null) -> the module's own 4-tier fallback attaches a usable id and
    tags ``source`` = ``fallback:*``. This is defense-in-depth on top of the
    FDN-1 selector-side never-null guarantee; either layer alone makes null
    impossible, both together make it un-reachable.

ENGINE SCOPE (F4.3)
-------------------
Consumers wired to this entry point: 49 (signature-funnel, brief stage), 50
(email-engine, style→canonical crosswalk), 52/53/54 (tone-core N/A auto-pick),
56 (sales-page-assets, brief stage), 57 (social-media, C10 persona adapter).
Skill 55 (product-bio) is **explicitly OUT OF SCOPE**: all 24 signature-close
styles are required every time BY DESIGN (gate ``AF-PB-CLOSES``), so there is no
runtime persona selection to adopt. Library-coverage decisions (new CODE/IMAGE
craft personas, vocabulary tags — analysis Q3/F3.8) ship through the Skill-22
pipeline in a separate train, not here.

CLIENT SOVEREIGNTY IS ABSOLUTE
------------------------------
If the caller passes an express client choice
(``persona_source in CLIENT_FINAL_SOURCES`` with a ``client_persona_id``), that
choice is returned verbatim and the selector is NEVER consulted and NEVER
overridden — the client's stated persona is FINAL, never judged
(feedback-never-change-client-sovereignty). This is how skill 57's
``personaSource: client-choice`` and the tone-core client-named tone slots stay
untouched.

stdlib-only, deterministic, no network of its own (the selector may embed, but
this module never does). Importable as a library and runnable as a CLI.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Decision constants (Persona-Matching-Overhaul, ratified answers Q1/Q2)
# --------------------------------------------------------------------------- #
# Q1 — a mechanical/operational task carries no_persona_required=True, but a
#      governance persona is still attached so nothing runs ungoverned.
GOVERNANCE_PERSONA_FALLBACK = "covey-7-habits"
# Q2 — the default competition fallback is a dedicated house-voice persona
#      (fallback:true, excluded from normal competition; added to the library by
#      the FDN-1 train, triad 81->82). We reference it by id and guard for the
#      case where a box has not yet received it (older asset) by degrading to the
#      governance fallback, which every box has had since the 81-persona set.
DEFAULT_PERSONA_FALLBACK = "blackceo-house-voice"

# persona_source values that mean "the client named this persona explicitly" —
# FINAL, never overridden, selector never consulted.
CLIENT_FINAL_SOURCES = frozenset({
    "client-choice", "client", "locked", "config-named", "express",
})

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent

# Where the canonical selector lives, most-specific first. Env override wins so a
# box with a non-standard layout (or a test) can point at the real script.
_SELECTOR_CANDIDATES = [
    os.environ.get("PERSONA_SELECTOR_PATH", "").strip(),
    str(_REPO / "23-ai-workforce-blueprint" / "scripts" / "persona-selector-v2.py"),
    str(Path.home() / ".openclaw" / "skills" / "23-ai-workforce-blueprint"
        / "scripts" / "persona-selector-v2.py"),
    "/data/.openclaw/skills/23-ai-workforce-blueprint/scripts/persona-selector-v2.py",
    str(Path.home() / "clawd" / "skills" / "23-ai-workforce-blueprint"
        / "scripts" / "persona-selector-v2.py"),
]

# Seed persona library shipped in this repo (used to resolve the persona universe
# and blueprints when a live OpenClaw workspace is not present — e.g. CI/tests).
_SEED_SKILL22 = _REPO / "22-book-to-persona-coaching-leadership-system"
_SEED_CATEGORIES = _SEED_SKILL22 / "persona-categories.json"
_SEED_PERSONA_ROOT = _SEED_SKILL22 / "personas"


# --------------------------------------------------------------------------- #
# persona universe + blueprints
# --------------------------------------------------------------------------- #
def _live_paths() -> "dict | None":
    """Best-effort resolve the live OpenClaw paths. Returns None off-platform."""
    try:
        sys.path.insert(0, str(_HERE))
        from detect_platform import get_openclaw_paths  # type: ignore
        return get_openclaw_paths()
    except Exception:
        return None


def available_personas() -> list:
    """The persona universe on this box. Live workspace categories win; the seed
    library shipped with skill 22 is the deterministic fallback (so this resolves
    even on a bare checkout / CI runner)."""
    paths = _live_paths()
    for cat in ([paths["persona_categories"]] if paths and paths.get("persona_categories") else []) + [_SEED_CATEGORIES]:
        try:
            cat = Path(cat)
            if not cat.exists():
                continue
            data = json.loads(cat.read_text(encoding="utf-8"))
            personas = data.get("personas") if isinstance(data, dict) else None
            if isinstance(personas, dict) and personas:
                return list(personas.keys())
            if isinstance(personas, list) and personas:
                return [d.get("id") or d.get("name") for d in personas if isinstance(d, dict)]
        except Exception:
            continue
    # last resort: scan a personas/ dir
    for root in ([paths["coaching_personas"] / "personas"] if paths and paths.get("coaching_personas") else []) + [_SEED_PERSONA_ROOT]:
        try:
            root = Path(root)
            if root.is_dir():
                dirs = sorted(p.name for p in root.iterdir() if p.is_dir())
                if dirs:
                    return dirs
        except Exception:
            continue
    return []


def _blueprint_path(persona_id: str) -> "Path | None":
    if not persona_id:
        return None
    paths = _live_paths()
    roots = []
    if paths and paths.get("coaching_personas"):
        roots.append(Path(paths["coaching_personas"]) / "personas")
    roots.append(_SEED_PERSONA_ROOT)
    for root in roots:
        bp = root / persona_id / "persona-blueprint.md"
        if bp.exists():
            return bp
    return None


_SECTION_HEAD_RE = re.compile(r"^##\s+Section\s+(\d+)\b", re.IGNORECASE)

# U14 (A-U14, D-A4 Option A) — the section-map crosswalk fixing the Section-4
# load-contract hazard (master-spec v2 §A.1.3): the Command Center dispatch
# contract orders "Internalize Section 4 (A-D) and §7B", but the section
# NUMBER that actually carries the Agent Governance Framework (the lettered
# A-D subsections) differs by template generation — Section 4 under Template
# B, Section 8 under Template A. This map is additive and OPTIONAL: its
# absence (older/back-compat checkout) degrades `section4_excerpt` to its
# pre-U14 behavior byte-for-byte (a literal "## Section 4" grab).
_SEED_SECTION_MAP = _SEED_PERSONA_ROOT / "_section-map.json"
_SECTION_MAP_CACHE: "dict | None" = None


def _load_section_map() -> dict:
    """Cached load of the section-map crosswalk. Returns {} (empty, honest)
    on any missing/unreadable/malformed file — callers treat that exactly
    like "no crosswalk entry for this persona" and fall back to literal
    Section 4, never raise."""
    global _SECTION_MAP_CACHE
    if _SECTION_MAP_CACHE is not None:
        return _SECTION_MAP_CACHE
    paths = _live_paths()
    candidates = []
    if paths and paths.get("coaching_personas"):
        candidates.append(Path(paths["coaching_personas"]) / "personas" / "_section-map.json")
    candidates.append(_SEED_SECTION_MAP)
    data: dict = {}
    for cand in candidates:
        try:
            if cand.exists():
                loaded = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and isinstance(loaded.get("personas"), dict):
                    data = loaded
                    break
        except Exception:
            continue
    _SECTION_MAP_CACHE = data
    return data


def _governance_section_number(persona_id: str) -> "int | None":
    """The section number carrying persona_id's Agent Governance Framework
    (A-D lettered subsections), per the section-map. None when the map is
    absent, the persona is not in it, or that persona's blueprint has no
    resolvable A-D governance section (documented edge case; see the map's
    _meta notes) — callers fall back to literal Section 4 in every None
    case, so behavior never regresses to a crash or an empty excerpt where
    the pre-U14 code would have found something."""
    entry = _load_section_map().get("personas", {}).get(persona_id)
    if not isinstance(entry, dict):
        return None
    num = entry.get("governance_section")
    return int(num) if isinstance(num, int) else None


def _extract_section(lines: list, section_num: int) -> str:
    """Return the raw body of ``## Section <section_num>`` (heading line
    through, but not including, the next ``## Section`` heading). Empty
    string if that section number is not present."""
    start = None
    for i, ln in enumerate(lines):
        m = _SECTION_HEAD_RE.match(ln.strip())
        if m and m.group(1) == str(section_num):
            start = i
            break
    if start is None:
        return ""
    body = [lines[start]]
    for ln in lines[start + 1:]:
        m = _SECTION_HEAD_RE.match(ln.strip())
        if m:  # next Section heading -> stop
            break
        body.append(ln)
    return "\n".join(body).strip()


def section4_excerpt(persona_id: str, max_chars: int = 1400) -> str:
    """Return the persona blueprint's GOVERNANCE excerpt (the dispatch
    contract's "Section 4 (A-D)" load target — the key-principles /
    Agent-Governance-Framework material), truncated. Empty string if the
    blueprint is not resolvable on this box.

    U14 fix (D-A4 Option A): the section NUMBER actually loaded is resolved
    per-persona via `_section-map.json` (Template A -> Section 8, Template B
    -> Section 4), not hardcoded to a literal "Section 4" — the field name
    stays `section4_excerpt` for consumer back-compat (every existing caller
    reads this key), but the CONTENT is now the real governance framework
    under BOTH template generations. A persona absent from the map, or the
    map itself absent, falls back to literal Section 4 — byte-identical to
    pre-U14 behavior."""
    bp = _blueprint_path(persona_id)
    if bp is None:
        return ""
    try:
        text = bp.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    lines = text.splitlines()

    target_section = _governance_section_number(persona_id)
    excerpt = _extract_section(lines, target_section) if target_section else ""
    if not excerpt:
        # No crosswalk entry, or that section wasn't actually present in the
        # file (defensive) — honest fallback to the pre-U14 literal grab.
        excerpt = _extract_section(lines, 4)

    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rstrip() + " …"
    return excerpt


def _persona_display_name(persona_id: str) -> str:
    """Human name from categories metadata if present, else a title-cased slug."""
    for cat in [_SEED_CATEGORIES]:
        try:
            data = json.loads(Path(cat).read_text(encoding="utf-8"))
            meta = (data.get("personas") or {}).get(persona_id)
            if isinstance(meta, dict):
                for k in ("name", "label", "title", "display_name"):
                    if meta.get(k):
                        return str(meta[k])
        except Exception:
            pass
    return (persona_id or "").replace("-", " ").title()


# --------------------------------------------------------------------------- #
# selector invocation
# --------------------------------------------------------------------------- #
def _find_selector() -> "str | None":
    for cand in _SELECTOR_CANDIDATES:
        if cand and Path(cand).exists():
            return cand
    return None


def _compose_query(job_text: str, sop_slug: "str | None", sop_hints) -> str:
    """Fold SOP context into the text the selector categorises + embeds, so the
    match is task+SOP aware even on boxes where the selector predates the native
    --sop-* inputs (F3.4). Bounded to keep the selector's single embed cheap."""
    parts = [job_text or ""]
    if sop_slug:
        parts.append("SOP: %s" % sop_slug.replace("-", " "))
    if sop_hints:
        if isinstance(sop_hints, str):
            hints = [sop_hints]
        else:
            hints = [str(h) for h in sop_hints if h]
        if hints:
            parts.append("SOP guidance: " + ", ".join(hints))
    return ". ".join(p.strip() for p in parts if p and p.strip())[:1800]


def _run_selector(query: str, department: str, record: bool, timeout: int, *,
                  blend: bool = False, topic_hint: "str | None" = None) -> "dict | None":
    """Spawn the canonical selector and parse its JSON. A ``PERSONA_FOR_JOB_FIXTURE``
    env var (path to a JSON file, or inline JSON) short-circuits the spawn so the
    consumer contract can be exercised in CI without an OpenClaw install — same
    escape-hatch pattern as the Command Center's PERSONA_FIXTURE_JSON.

    ``blend`` (A-U1) appends ``--blend`` (+ ``--topic`` when a topic hint is
    supplied) so the selector emits the voice-first persona-bundle SUPERSET
    (``persona-selector-v2.py``'s W7 branch, ``persona_blend.build_bundle``)
    instead of the single-persona selection. Audience confirmation and any
    other goal/context signalling travel as ENV (``OPENCLAW_AUDIENCE`` etc.) —
    ``subprocess.run`` inherits the parent process environment unmodified, so
    that passthrough needs no code here; this function only adds the argv
    flags the blend branch itself requires."""
    fixture = os.environ.get("PERSONA_FOR_JOB_FIXTURE", "").strip()
    if fixture:
        try:
            if os.path.exists(fixture):
                return json.loads(Path(fixture).read_text(encoding="utf-8"))
            return json.loads(fixture)
        except Exception:
            return None
    selector = _find_selector()
    if selector is None:
        return None
    cmd = [sys.executable or "python3", selector,
           "--task", query, "--department", department, "--format", "json"]
    if blend:
        cmd.append("--blend")
        if topic_hint:
            cmd += ["--topic", topic_hint]
    if not record:
        cmd.append("--no-record")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return None
    out = (proc.stdout or "").strip()
    if not out:
        return None
    # selector prints diagnostics to stderr and the JSON object to stdout; be
    # tolerant of a leading banner by grabbing the first {...} block.
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        i, j = out.find("{"), out.rfind("}")
        if 0 <= i < j:
            try:
                return json.loads(out[i:j + 1])
            except json.JSONDecodeError:
                return None
    return None


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def _fallback_persona(universe: list) -> "tuple[str, str]":
    """Resolve the guaranteed default persona and the reason tag. Never null."""
    uni = set(universe or [])
    if DEFAULT_PERSONA_FALLBACK in uni:
        return DEFAULT_PERSONA_FALLBACK, "fallback:default"
    if GOVERNANCE_PERSONA_FALLBACK in uni:
        return GOVERNANCE_PERSONA_FALLBACK, "fallback:governance"
    if universe:
        return sorted(universe)[0], "fallback:first-available"
    # Truly empty universe (broken box): still emit a stable constant id so the
    # doer is never naked; the blueprint excerpt will simply be empty.
    return DEFAULT_PERSONA_FALLBACK, "fallback:constant"


def _finalize(persona_id, name, mode, version, score, source, *,
              department, sop_slug, job_text, no_persona_required=False,
              governance_persona_id=None, raw=None, warnings=None,
              secondary_persona_id=None, secondary_persona_name=None,
              section4_chars=1400) -> dict:
    excerpt = section4_excerpt(persona_id, section4_chars) if persona_id else ""
    return {
        "persona_id": persona_id,
        "persona_name": name or (_persona_display_name(persona_id) if persona_id else None),
        "persona_mode": mode,
        "persona_version": int(version) if version is not None else 1,
        "score": score,
        "source": source,
        "no_persona_required": bool(no_persona_required),
        "governance_persona_id": governance_persona_id,
        "secondary_persona_id": secondary_persona_id,
        "secondary_persona_name": secondary_persona_name,
        "section4_excerpt": excerpt,
        "department": department,
        "sop_slug": sop_slug,
        "job_text": (job_text or "")[:400],
        "selector": raw,
        "warnings": warnings or [],
    }


def persona_for_job(job_text: str, department: str, *,
                    sop_slug: "str | None" = None, sop_hints=None,
                    client_persona_id: "str | None" = None,
                    persona_source: "str | None" = None,
                    record: bool = True, timeout: int = 60,
                    section4_chars: int = 1400,
                    blend: bool = False,
                    topic_hint: "str | None" = None) -> dict:
    """Resolve the best persona for a content-engine job. See module docstring.

    Returns a normalized selection dict that is NEVER naked (see contract).

    ``blend`` (A-U1, default-off): when True, resolve through the canonical
    selector's ``--blend`` (voice-first AUDIENCE+TOPIC) branch and return the
    persona-bundle SUPERSET verbatim — the dict carries ``blend_directive``,
    ``voice``, ``resolved_audience``, ``task_personas``, ``rationale`` etc. as
    TOP-LEVEL keys, plus a back-compat ``persona_id``/``persona_name`` mirror,
    so every consumer can adopt it without a shape migration. ``topic_hint``
    optionally names the topic explicitly (otherwise inferred from the job
    text). Single-persona mode (``blend=False``, the default) is completely
    untouched — same code path, same return shape, as before this parameter
    existed.
    """
    department = (department or "general").strip() or "general"
    warnings: list = []

    # 1) CLIENT SOVEREIGNTY — an express choice is FINAL; selector never runs,
    #    blend or not (a client-named voice is never blended or judged).
    if client_persona_id and (persona_source or "").strip().lower() in CLIENT_FINAL_SOURCES:
        uni = available_personas()
        if client_persona_id not in uni:
            warnings.append(
                "client-choice persona %r is not a canonical library id; honored "
                "verbatim (client sovereignty), adherence loop will not score it"
                % client_persona_id)
        return _finalize(client_persona_id, _persona_display_name(client_persona_id),
                         None, 1, None, "client-choice",
                         department=department, sop_slug=sop_slug, job_text=job_text,
                         warnings=warnings, section4_chars=section4_chars)

    # 2) BLEND mode (A-U1) — ask the canonical selector for the bundle
    #    superset instead of a single persona.
    if blend:
        query = _compose_query(job_text, sop_slug, sop_hints)
        raw = _run_selector(query, department, record, timeout,
                            blend=True, topic_hint=topic_hint)
        if raw is not None and not raw.get("error") and raw.get("blend_directive"):
            # Bundle superset, returned VERBATIM to the consumer (top-level
            # blend_directive / voice / resolved_audience / task_personas /
            # rationale / fallbacks / persona_id back-compat mirror — all as
            # shipped by persona_blend.build_bundle). Only the job/department/
            # sop context is normalized on top so it matches the single-
            # persona shape's context fields.
            bundle = dict(raw)
            bundle.setdefault("department", department)
            bundle.setdefault("sop_slug", sop_slug)
            bundle["job_text"] = (job_text or "")[:400]
            bundle.setdefault("warnings", [])
            return bundle
        # Selector unreachable / errored / degraded while blend was requested
        # — fail closed the SAME way single-persona mode does (defense in
        # depth atop FDN-1): never return a naked result, just be honest that
        # the blend itself degraded to the single-persona fallback.
        warnings.append(
            "blend requested but selector unavailable/errored/returned no "
            "bundle (%s); degrading to single-persona fallback"
            % ((raw or {}).get("error") if raw else "no selector / no output"))
        fid, source = _fallback_persona(available_personas())
        return _finalize(fid, _persona_display_name(fid), None, 1, None, source,
                         department=department, sop_slug=sop_slug, job_text=job_text,
                         raw=raw, warnings=warnings, section4_chars=section4_chars)

    # 3) Ask the canonical selector (single-persona mode — unchanged).
    query = _compose_query(job_text, sop_slug, sop_hints)
    raw = _run_selector(query, department, record, timeout)

    if raw is not None and not raw.get("error"):
        # 3a) mechanical / operational — truthful null persona + governance frame (Q1)
        if raw.get("no_persona_required"):
            return _finalize(None, None, None, 1, None, "no-persona-required",
                             department=department, sop_slug=sop_slug, job_text=job_text,
                             no_persona_required=True,
                             governance_persona_id=GOVERNANCE_PERSONA_FALLBACK,
                             raw=raw, warnings=warnings, section4_chars=section4_chars)
        pid = raw.get("persona_id")
        if pid:
            return _finalize(
                pid, raw.get("persona_name"),
                raw.get("interaction_mode") or raw.get("mode"),
                raw.get("persona_version", 1), raw.get("score"),
                "sticky" if raw.get("sticky") else "selector",
                department=department, sop_slug=sop_slug, job_text=job_text,
                secondary_persona_id=raw.get("secondary_persona_id"),
                secondary_persona_name=raw.get("secondary_persona_name"),
                raw=raw, warnings=warnings, section4_chars=section4_chars)
        # selector reachable but returned a null persona (e.g. NO_PERSONAS_AVAILABLE)
        warnings.append("selector returned a null persona (%s); applying fallback"
                        % (raw.get("warning") or raw.get("message") or "no reason given"))
    else:
        warnings.append("selector unavailable or errored (%s); applying fallback"
                        % ((raw or {}).get("error") if raw else "no selector / no output"))

    # 4) Fail-closed fallback — never naked (defense in depth atop FDN-1).
    fid, source = _fallback_persona(available_personas())
    return _finalize(fid, _persona_display_name(fid), None, 1, None, source,
                     department=department, sop_slug=sop_slug, job_text=job_text,
                     raw=raw, warnings=warnings, section4_chars=section4_chars)


def persona_for_jobs(jobs: list) -> list:
    """Batch resolver for multi-slot / multi-persona jobs (e.g. tone-core's
    four tone slots, or an SOP that declares several persona slots). Each item is
    a dict of kwargs for ``persona_for_job``. Client-named slots stay FINAL; N/A
    slots route through the selector. Returns one selection per input, order
    preserved. Never returns a naked slot."""
    out = []
    for spec in jobs:
        if not isinstance(spec, dict):
            spec = {"job_text": str(spec), "department": "general"}
        out.append(persona_for_job(
            spec.get("job_text", ""), spec.get("department", "general"),
            sop_slug=spec.get("sop_slug"), sop_hints=spec.get("sop_hints"),
            client_persona_id=spec.get("client_persona_id"),
            persona_source=spec.get("persona_source"),
            record=spec.get("record", True), timeout=spec.get("timeout", 60),
            section4_chars=spec.get("section4_chars", 1400),
            blend=spec.get("blend", False), topic_hint=spec.get("topic_hint")))
    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Resolve the canonical persona for a content-engine job "
                    "(shared entry point for skills 49/50/52/53/54/56/57).")
    ap.add_argument("--job", "--task", dest="job", help="the job/task text")
    ap.add_argument("--department", default="general")
    ap.add_argument("--sop-slug", dest="sop_slug", default=None)
    ap.add_argument("--sop-hints", dest="sop_hints", default=None,
                    help="comma-separated SOP persona hints")
    ap.add_argument("--client-persona-id", dest="client_persona_id", default=None)
    ap.add_argument("--persona-source", dest="persona_source", default=None,
                    help="config|adapter|client-choice|locked (client-* is FINAL)")
    ap.add_argument("--no-record", dest="record", action="store_false")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--blend", dest="blend", action="store_true",
                    help="(A-U1) resolve the voice-first persona-BUNDLE "
                         "superset instead of a single persona (default off; "
                         "single-persona callers are completely unaffected).")
    ap.add_argument("--topic-hint", dest="topic_hint", default=None,
                    help="(--blend) optional explicit topic hint for the job.")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run the fail-closed consumer contract self-test")
    a = ap.parse_args(argv)

    if a.self_test:
        return _self_test()

    if not a.job:
        ap.error("--job is required (or use --self-test)")
    hints = [h.strip() for h in a.sop_hints.split(",")] if a.sop_hints else None
    sel = persona_for_job(a.job, a.department, sop_slug=a.sop_slug, sop_hints=hints,
                          client_persona_id=a.client_persona_id,
                          persona_source=a.persona_source, record=a.record,
                          timeout=a.timeout, blend=a.blend, topic_hint=a.topic_hint)
    print(json.dumps(sel, indent=2))
    # exit 0 always; the selection is guaranteed usable. Callers inspect JSON.
    return 0


def _self_test() -> int:
    """Prove the never-naked contract with the fixture escape hatch (no OpenClaw
    install required). Every branch must yield a governed job."""
    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "FAIL", label))

    def governed(sel):
        # never naked: either a usable persona_id, or no_persona_required with a
        # governance persona attached.
        if sel.get("persona_id"):
            return True
        return sel.get("no_persona_required") and sel.get("governance_persona_id")

    # normal job — selector returns a real persona (fixture)
    os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(
        {"persona_id": "covey-7-habits", "persona_name": "Covey", "score": 0.9})
    s = persona_for_job("write a leadership email", "sales")
    check("normal job -> selector persona", s["persona_id"] == "covey-7-habits" and s["source"] == "selector")
    check("normal job -> governed", governed(s))

    # mechanical job — no_persona_required + governance fallback (Q1)
    os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(
        {"persona_id": None, "no_persona_required": True})
    s = persona_for_job("restart the server", "engineering")
    check("mechanical -> no_persona_required", s["no_persona_required"])
    check("mechanical -> governance persona attached", s["governance_persona_id"] == GOVERNANCE_PERSONA_FALLBACK)
    check("mechanical -> governed", governed(s))

    # selector returned null persona (NO_PERSONAS_AVAILABLE) — fallback
    os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(
        {"persona_id": None, "warning": "NO_PERSONAS_AVAILABLE"})
    s = persona_for_job("write sales copy", "marketing")
    check("null persona -> fallback source", str(s["source"]).startswith("fallback"))
    check("null persona -> governed (non-null id)", governed(s))

    # selector unavailable entirely — fallback
    os.environ["PERSONA_FOR_JOB_FIXTURE"] = "not-json{{"
    s = persona_for_job("write sales copy", "marketing")
    check("selector unavailable -> governed", governed(s))
    os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)

    # client sovereignty — express choice returned verbatim, selector never runs
    os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(
        {"persona_id": "should-not-be-used", "persona_name": "WRONG"})
    s = persona_for_job("anything", "content",
                        client_persona_id="td-jakes-instinct",
                        persona_source="client-choice")
    check("client-choice -> honored verbatim", s["persona_id"] == "td-jakes-instinct")
    check("client-choice -> source client-choice", s["source"] == "client-choice")
    os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)

    # ---- A-U1: blend=True bundle-superset mode ---------------------------- #

    # blend job — selector returns the full bundle superset (fixture shaped
    # exactly like persona_blend.build_bundle's real output).
    _blend_fixture = {
        "persona_id": "brunson-marketing-secrets-blackbook",
        "persona_name": "Brunson Marketing Secrets Blackbook",
        "mode": "blend",
        "content_task": True,
        "topic": "offers",
        "resolved_audience": {"source": "confirmed", "candidates": [], "confidence": "high",
                              "label": "founders", "ask": None, "confirm_required": False},
        "confirm_required": False,
        "voice": {"audience_persona": {"id": "brunson-marketing-secrets-blackbook", "why": "x"},
                  "topic_persona": {"id": "brunson-marketing-secrets-blackbook", "why": "x"},
                  "collapsed": True, "collapsed_persona_id": "brunson-marketing-secrets-blackbook",
                  "topic_as_task_guidance": True},
        "blend_directive": "Write as Brunson Marketing Secrets Blackbook. STYLE-INSPIRED, NEVER IMPERSONATION.",
        "task_personas": [],
        "rationale": {"collapse": "collapsed onto brunson-marketing-secrets-blackbook"},
        "fallbacks": {"default_persona": "acuff-miner-new-model-of-selling",
                      "governance": "covey-7-habits"},
        "catalog_version": "1.3",
    }
    os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(_blend_fixture)
    s = persona_for_job("write sales page copy", "marketing", blend=True)
    check("blend -> non-empty blend_directive", bool(s.get("blend_directive")))
    check("blend -> non-empty voice", bool(s.get("voice")))
    check("blend -> non-empty resolved_audience", bool(s.get("resolved_audience")))
    check("blend -> persona_id back-compat mirror present", s.get("persona_id") == "brunson-marketing-secrets-blackbook")
    check("blend -> governed", governed(s))

    # blend requested but the selector is unavailable/errored — fail closed
    # to the SAME never-naked fallback as single-persona mode, never a crash.
    os.environ["PERSONA_FOR_JOB_FIXTURE"] = "not-json{{"
    s = persona_for_job("write sales page copy", "marketing", blend=True)
    check("blend degraded -> governed (never naked)", governed(s))
    check("blend degraded -> honest warning recorded", any("blend" in w for w in s.get("warnings", [])))
    os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)

    # default (blend omitted) — byte-identical to the pre-A-U1 single-persona
    # path; same fixture, same assertions as the very first case above proves
    # the parameter is additive and default-off.
    os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(
        {"persona_id": "covey-7-habits", "persona_name": "Covey", "score": 0.9})
    s = persona_for_job("write a leadership email", "sales")
    check("blend omitted -> unchanged single-persona shape", s["persona_id"] == "covey-7-habits" and s["source"] == "selector" and "blend_directive" not in s)
    os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)

    print("== persona_for_job self-test: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
