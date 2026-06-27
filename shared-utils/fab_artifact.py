#!/usr/bin/env python3
"""fab_artifact.py — the PRODUCER that emits ``build/fab-artifact.json`` from a REAL build.

WHY THIS EXISTS (closes the D4 gap)
-----------------------------------
The FAB-QC build-quality gate (``shared-utils/fab_qc.py``) scores ``build/fab-artifact.json``.
Before this module, NOTHING on the real build path wrote that file — only test fixtures did —
so ``v2_dispatcher._fab_overlay`` (Skill 6) returned ``ran:False`` and the ``qc-built-workflow.sh
--fab`` overlay (Skill 44) had nothing to score: the >=8.5 gate was a silent NO-OP on every real
funnel/automation build.

This module closes that. It NORMALISES a real build result — the matched ``funnel_template_id`` /
matched template id, the built pages/steps, the ACTUAL copy text, the recorded flex decision, and
the attached ``linked_automations`` — into the exact artifact shape ``fab_qc`` reads. With it
wired into both build paths, the gate genuinely fires:

  * Funnel (Skill 6, in-process):   ``v2_dispatcher`` calls
        ``emit(evidence_root, build_funnel_artifact(task, build))`` right before ``_fab_overlay``.
  * Automation (Skill 44, CLI):     ``qc-built-workflow.sh --fab`` calls this module's CLI to
        convert the ``caf workflows export`` JSON into ``build/fab-artifact.json`` BEFORE
        ``fab_qc`` scores it.

CONTRACT (fail-closed by design)
--------------------------------
The artifact's copy IS the real copy that was built. A builder MUST echo the copy it wrote
(``build['pages'][i]['copy']`` for a funnel page; the email/SMS subject+body in the workflow
export for an automation step). A build that emits NO copy produces empty-copy slots and the
FAB-QC D2 (copy substance) dimension fails it — that is the intended fail-closed behaviour, not a
bug: an un-echoed build cannot be proven non-thin.

stdlib-only, deterministic, no network. NEVER raises into a build loop (emit returns a status
dict; the CLI exits 0 on a best-effort emit so it can never block QC by crashing).
"""
from __future__ import annotations

import json
import os
import sys

ARTIFACT_REL = os.path.join("build", "fab-artifact.json")

# Per-slot copy keys we harvest when a page/step does not carry an explicit ``copy`` field.
_PAGE_COPY_KEYS = ("headline", "subheadline", "subhead", "hero", "body", "subject",
                   "cta", "text", "content", "bullets", "sections", "paragraphs")
_STEP_COPY_KEYS = ("subject", "body", "message", "text", "html", "content",
                   "emailBody", "email_body", "smsBody", "sms_body", "caption")
# Where a workflow-export step may nest its copy.
_STEP_NEST_KEYS = ("attributes", "data", "meta", "settings", "params", "config")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _as_text(v) -> str:
    if isinstance(v, (list, tuple)):
        return " ".join(_as_text(x) for x in v if x is not None)
    if isinstance(v, dict):
        return " ".join(_as_text(x) for x in v.values() if x is not None)
    return str(v) if v is not None else ""


def _page_copy(page: dict | None) -> dict | str | None:
    """Extract a page's copy: an explicit ``copy`` field wins; else assemble from known copy
    keys + any text-bearing ``blocks``. Returns a dict (slot -> text), a str, or None."""
    if not isinstance(page, dict):
        return None
    copy = page.get("copy")
    if isinstance(copy, (dict, list, str)) and copy:
        return copy
    bag: dict[str, str] = {}
    for k in _PAGE_COPY_KEYS:
        v = page.get(k)
        t = _as_text(v).strip()
        if t:
            bag[k] = t
    for i, blk in enumerate(page.get("blocks", []) or []):
        if isinstance(blk, dict):
            t = _as_text(blk.get("text") or blk.get("copy") or blk.get("content") or "").strip()
            if t:
                bag[str(blk.get("type") or blk.get("name") or f"block{i}")] = t
    return bag or None


def _step_channel(step: dict) -> str:
    t = str(step.get("type") or step.get("channel") or step.get("action") or "").upper()
    if "SMS" in t:
        return "sms"
    if "EMAIL" in t or "MAIL" in t:
        return "email"
    if "WHATSAPP" in t or "WA" == t:
        return "whatsapp"
    if "WAIT" in t:
        return "wait"
    return (t.lower() or "step")


def _step_copy(step: dict) -> str | None:
    """Assemble the real copy of a built workflow step from its (possibly nested) fields."""
    parts: list[str] = []
    sources = [step]
    for nk in _STEP_NEST_KEYS:
        nv = step.get(nk)
        if isinstance(nv, dict):
            sources.append(nv)
    for src in sources:
        for k in _STEP_COPY_KEYS:
            t = _as_text(src.get(k)).strip()
            if t:
                parts.append(t)
    # de-dup while preserving order
    seen, out = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return " — ".join(out) if out else None


def _iter_export_steps(export: dict) -> list[dict]:
    """The caf/GHL workflow export keeps steps under a handful of keys depending on shape."""
    for key in ("steps", "actions", "nodes"):
        v = export.get(key)
        if isinstance(v, list) and v:
            return [s for s in v if isinstance(s, dict)]
    wd = export.get("workflowData")
    if isinstance(wd, dict) and isinstance(wd.get("templates"), list):
        return [s for s in wd["templates"] if isinstance(s, dict)]
    return []


# --------------------------------------------------------------------------- #
# funnel producer (Skill 6 — in-process from the dispatcher)
# --------------------------------------------------------------------------- #
def build_funnel_artifact(task: dict, build: dict) -> dict:
    """Normalise a real funnel build (``task`` + injected-builder ``build`` result) into the
    artifact shape ``fab_qc`` reads. Copy is taken from the build pages first (the source of
    truth the builder wrote/pushed), falling back to the instantiated plan pages."""
    task = task or {}
    build = build or {}
    tm = task.get("template_match") or {}
    build_pages = [p for p in (build.get("pages") or []) if isinstance(p, dict)]
    plan_pages = [p for p in (task.get("pages") or []) if isinstance(p, dict)]
    n = max(len(build_pages), len(plan_pages))
    pages: list[dict] = []
    for i in range(n):
        bp = build_pages[i] if i < len(build_pages) else {}
        pp = plan_pages[i] if i < len(plan_pages) else {}
        name = (bp.get("name") or bp.get("page") or bp.get("step")
                or pp.get("name") or pp.get("page") or f"page-{i + 1}")
        copy = _page_copy(bp)
        if not copy:
            copy = _page_copy(pp)
        pages.append({"name": name, "copy": copy if copy is not None else {}})
    return {
        "kind": "funnel",
        "funnel_template_id": task.get("funnel_template_id") or task.get("instantiated_from_template"),
        "matched_template_id": tm.get("matched_template") or task.get("instantiated_from_template"),
        "flex_decision": tm.get("decision"),
        "linked_automations": task.get("linked_automations"),
        "pages": pages,
        "generated_by": "fab_artifact.build_funnel_artifact",
    }


# --------------------------------------------------------------------------- #
# automation producer (Skill 44 — from the workflow export)
# --------------------------------------------------------------------------- #
def build_automation_artifact(export: dict, match_decision: dict | None = None) -> dict:
    """Normalise a real automation build (the ``caf workflows export`` JSON) into the artifact
    shape ``fab_qc`` reads — each built step's channel + the ACTUAL copy that was pushed."""
    export = export or {}
    md = match_decision or {}
    steps_out: list[dict] = []
    for s in _iter_export_steps(export):
        ch = _step_channel(s)
        if ch == "wait":
            continue  # wait/delay nodes carry no copy — not a message step
        copy = _step_copy(s)
        steps_out.append({"channel": ch, "copy": copy if copy is not None else ""})
    return {
        "kind": "automation",
        "matched_template_id": md.get("matched_template_id"),
        "flex_decision": md.get("flex_decision"),
        "funnel_template_id": md.get("funnel_template_id"),
        "steps": steps_out,
        "generated_by": "fab_artifact.build_automation_artifact",
    }


# --------------------------------------------------------------------------- #
# emit
# --------------------------------------------------------------------------- #
def emit(evidence_root: str, artifact: dict, *, overwrite: bool = False) -> dict:
    """Write ``<evidence_root>/build/fab-artifact.json``. By default does NOT clobber an existing
    artifact (an explicit upstream emitter / fixture wins). Best-effort: never raises."""
    try:
        out_path = os.path.join(evidence_root, ARTIFACT_REL)
        if os.path.isfile(out_path) and not overwrite:
            return {"emitted": False, "reason": "fab-artifact already present", "path": out_path}
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=2)
        return {"emitted": True, "path": out_path,
                "pages": len(artifact.get("pages", []) or []),
                "steps": len(artifact.get("steps", []) or [])}
    except Exception as exc:  # noqa: BLE001 — emit must never crash a build/QC loop
        return {"emitted": False, "reason": f"{type(exc).__name__}: {exc}"}


def _load_json(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


# --------------------------------------------------------------------------- #
# CLI (the automation path: qc-built-workflow.sh --fab calls this)
# --------------------------------------------------------------------------- #
def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Emit build/fab-artifact.json from a real build so FAB-QC can score it.")
    ap.add_argument("--evidence", required=True, help="evidence root dir (writes build/fab-artifact.json)")
    ap.add_argument("--kind", choices=["funnel", "automation"], default="automation")
    ap.add_argument("--workflow", help="path to the caf workflows export JSON (automation kind)")
    ap.add_argument("--build", help="path to a funnel build-result JSON (funnel kind)")
    ap.add_argument("--task", help="path to a funnel task JSON (funnel kind)")
    ap.add_argument("--overwrite", action="store_true", help="clobber an existing artifact")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)

    md = _load_json(os.path.join(a.evidence, "routing", "match-decision.json")) or {}
    if a.kind == "automation":
        export = _load_json(a.workflow) if a.workflow else {}
        if export is None:
            if not a.quiet:
                print(f"fab_artifact: could not read workflow export {a.workflow!r}", file=sys.stderr)
            return 0  # best-effort: never block QC
        artifact = build_automation_artifact(export or {}, md)
    else:
        task = _load_json(a.task) if a.task else {}
        build = _load_json(a.build) if a.build else {}
        artifact = build_funnel_artifact(task or {}, build or {})

    res = emit(a.evidence, artifact, overwrite=a.overwrite)
    if not a.quiet:
        print(json.dumps(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
