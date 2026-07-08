#!/usr/bin/env python3
"""persona_brief.py — brief-stage canonical persona resolution for Sales Page
Assets (F4.3).

At the brief stage the sales-page build now resolves its governing persona through the ONE
shared entry point ``shared-utils/persona_for_job.py`` (canonical 5-layer
selector) instead of the old static kanban label. The resolved persona id +
Section-4 governance excerpt are written to ``persona-selection.json`` so (a) the
copy/asset prompts can be grounded in a real library persona and (b) the signed
PROCESS-CERTIFICATE names the canonical persona id.

Never naked, never crashes the run: an unreachable selector / bare box degrades
to the shared helper's own fail-closed fallback (see persona_for_job). stdlib-only.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parent.parent
# Skill 56's authoritative PRIMARY owning department (skill-department-map.json) —
# the seeded canonical slug the selector scores against. Must match the board
# routing in run_sales_page_assets._mc_board_begin; the prior "funnels" literal was
# never a seeded department and silently misrouted (SK2-06).
DEPARTMENT = "marketing"
# brief.answers fields folded into the selector query (brand + product + offers).
_QUERY_FIELDS = ("brand_info", "product_info", "upsell_desc", "high_ticket_desc")


def _shared_utils_dir() -> "Path | None":
    for c in (os.environ.get("SHARED_UTILS_DIR", "").strip(),
              str(_SKILL_DIR.parent / "shared-utils"),
              str(Path.home() / ".openclaw" / "skills" / "shared-utils"),
              "/data/.openclaw/skills/shared-utils",
              str(Path.home() / "clawd" / "skills" / "shared-utils")):
        if c and (Path(c) / "persona_for_job.py").exists():
            return Path(c)
    return None


def _load_pfj():
    d = _shared_utils_dir()
    if d is None:
        return None
    try:
        sys.path.insert(0, str(d))
        import persona_for_job as pfj  # type: ignore
        return pfj
    except Exception:
        return None


def _brief_query(brief: dict) -> str:
    answers = brief.get("answers") if isinstance(brief, dict) else None
    answers = answers if isinstance(answers, dict) else (brief or {})
    bits = []
    for f in _QUERY_FIELDS:
        v = answers.get(f)
        if isinstance(v, str) and v.strip():
            bits.append(v.strip())
    ledger = (brief or {}).get("offer_token_ledger")
    if isinstance(ledger, (list, tuple)):
        bits.extend(str(x) for x in ledger if x)
    if not bits:
        bits.append("sales page assets copy")
    return " | ".join(bits)[:1400]


def resolve(run_dir: Path, *, client_persona_id: "str | None" = None,
            persona_source: "str | None" = None, record: bool = True) -> "dict | None":
    """Resolve the funnel's persona from brief.json and write persona-selection.json.
    Returns the selection dict, or None if the shared helper is unreachable."""
    brief = {}
    bp = run_dir / "brief.json"
    if bp.exists():
        try:
            brief = json.loads(bp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            brief = {}
    # brief-declared client persona choice wins (client sovereignty) if present.
    if not client_persona_id and isinstance(brief, dict):
        for k in ("client_persona_id", "personaId", "persona_id"):
            if isinstance(brief.get(k), str) and brief[k].strip():
                client_persona_id = brief[k].strip()
                persona_source = persona_source or "client-choice"
                break
    pfj = _load_pfj()
    if pfj is None:
        return None
    sel = pfj.persona_for_job(_brief_query(brief), DEPARTMENT,
                             client_persona_id=client_persona_id,
                             persona_source=persona_source, record=record)
    out = run_dir / "persona-selection.json"
    try:
        out.write_text(json.dumps(sel, indent=2), encoding="utf-8")
    except OSError:
        pass
    return sel


def cert_block(run_dir: Path) -> "dict | None":
    """Compact persona block for the PROCESS-CERTIFICATE, read from persona-selection.json."""
    sel_p = run_dir / "persona-selection.json"
    if not sel_p.exists():
        return None
    try:
        sel = json.loads(sel_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(sel, dict):
        return None
    if not sel.get("persona_id") and not sel.get("governance_persona_id"):
        return None
    return {
        "persona_id": sel.get("persona_id"),
        "persona_name": sel.get("persona_name"),
        "persona_source": sel.get("source"),
        "no_persona_required": bool(sel.get("no_persona_required")),
        "governance_persona_id": sel.get("governance_persona_id"),
        "section4_present": bool(sel.get("section4_excerpt")),
    }


def _self_test() -> int:
    import tempfile
    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "FAIL", label))

    if _shared_utils_dir() is None:
        print("  [SKIP] shared-utils not reachable")
        print("== persona_brief self-test: SKIPPED ==")
        return 0

    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        (rd / "brief.json").write_text(json.dumps({
            "answers": {"brand_info": "The Glow Method skincare brand",
                        "product_info": "The Glow Method course $97",
                        "upsell_desc": "Glow Accelerator $197"}}), encoding="utf-8")
        os.environ["PERSONA_FOR_JOB_FIXTURE"] = json.dumps(
            {"persona_id": "edwards-copywriting-secrets", "persona_name": "Edwards", "score": 0.9})
        sel = resolve(rd, record=False)
        check("brief resolved to selector persona", sel and sel.get("persona_id") == "edwards-copywriting-secrets")
        check("persona-selection.json written", (rd / "persona-selection.json").exists())
        cb = cert_block(rd)
        check("cert_block names canonical id", cb and cb["persona_id"] == "edwards-copywriting-secrets")

        # brief-declared client choice is FINAL
        (rd / "brief.json").write_text(json.dumps({
            "client_persona_id": "jakes-instinct",
            "answers": {"q1_offer": "x"}}), encoding="utf-8")
        sel = resolve(rd, record=False)
        check("brief client choice honored (FINAL)",
              sel and sel.get("persona_id") == "jakes-instinct" and sel.get("source") == "client-choice")
        os.environ.pop("PERSONA_FOR_JOB_FIXTURE", None)

    print("== persona_brief self-test: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Brief-stage canonical persona resolution (Sales Page Assets, F4.3).")
    ap.add_argument("--run-dir")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        raise SystemExit(_self_test())
    if not a.run_dir:
        ap.error("--run-dir is required (or use --self-test)")
    sel = resolve(Path(a.run_dir).resolve())
    print(json.dumps(sel or {"error": "shared-utils/persona_for_job.py not reachable"}, indent=2))
