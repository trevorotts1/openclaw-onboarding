#!/usr/bin/env python3
"""persona_brief.py — brief-stage canonical persona resolution (F4.3) and the
launch task-mode persona adapter (F10).

TWO JOBS, ONE PERSONA LIBRARY
-----------------------------
1. ``resolve`` / ``cert_block`` resolve the funnel's governing persona through
   the ONE shared entry point ``shared-utils/persona_for_job.py`` (canonical
   5-layer selector) and write ``persona-selection.json`` so the copy/asset
   prompts are grounded in a real library persona and the signed
   PROCESS-CERTIFICATE names the canonical persona id.

2. ``apply_launch_personas`` is the launch-specific Task Mode adapter over the
   Skill 22 blueprints. A launch takes the blueprints' TASK reasoning and none
   of their coaching machinery:

   * ``hormozi-100m-offers`` governs offer value, the promise, scope, price
     logic and deliverability (one avatar and one specific outcome; value
     architecture before copy; real scarcity only where the client recorded it;
     guarantee conditions; first-week deliverability).
   * ``russell-brunson-the-funnel-hackers-cookbook`` governs the lead magnet,
     the page sequence, the order bump, the one-click upsell/downsell and the
     conversion path (right recipe first, full sequence, every ingredient,
     follow-up wired).
   * ``sinek-start-with-why`` governs WHY, audience alignment, the brand
     promise and voice (WHY before WHAT, HOW as verbs, WHAT as proof,
     belief-fit audience).

   What is deliberately NOT imported: the blueprints' quotas, coaching arcs and
   extra persona gates. No 32-64 obstacle map, no 16-objection minimum, no
   completeness quota over the 22 recipes / 37 page recipes, no 4-8 session
   coaching arc, and no persona QC gate beyond the launcher's existing checks.
   ``SUPPRESSED`` records that in the output. The client's approved promotion,
   idea-development needs and the friendly interview stay exactly as the
   launcher already runs them.

   ``copy_persona_blend_seam.render_blend_directive_variable`` is the ONE seam
   that renders the directive, so it always ends in the mandatory
   style-inspired / NEVER-impersonation clause. Nothing here renders a
   quotation, claims an author wrote anything, or implies a real person's
   endorsement: the blueprints' direct quotes stay unused, and only the task
   reasoning is applied.

Never naked, never crashes the run: an unreachable selector / bare box degrades
to the shared helper's own fail-closed fallback (see persona_for_job). The
launch adapter degrades to its own honest record when Skill 22 is not
installed (``blueprint_present: false``, never an invented blueprint).
stdlib-only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_SKILL_DIR = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
# Funnel copy is marketing work — the department the selector scores against.
DEPARTMENT = "marketing"
# brief.answers fields folded into the selector query (offer + audience + voice).
_QUERY_FIELDS = ("q1_offer", "q4_people", "q9_voice", "q3_pains")


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
        bits.append("signature funnel sales copy")
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


# --------------------------------------------------------------------------- #
# F10 — launch task-mode adapter over the Skill 22 blueprints
# --------------------------------------------------------------------------- #
PERSONA_SKILL_SLUG = "book-to-persona-coaching-leadership-system"
BLUEPRINT_FILE = "persona-blueprint.md"
LAUNCH_ADAPTER_ID = "skill49-launch-task-personas/v1"

# One launch task -> the ONE blueprint the Skill 22 router names for it.
TASK_PERSONAS = (
    {
        "task": "offer_architecture",
        "persona_id": "hormozi-100m-offers",
        "governs": "offer value, promise, scope, price logic and deliverability",
        "sections_applied": ("4A",),
        "preserves": (
            "value architecture before copy",
            "one avatar and one specific outcome",
            "the real price and scope logic the client supplied",
            "scarcity and urgency only where the client recorded them",
            "a deliverable first-week promise",
        ),
        "task_mode": (
            "Build the offer from the client's own supplied value, price, scope and delivery "
            "facts. Name one avatar and one specific outcome, make the promise measurable, and "
            "keep the price logic the client recorded. Use scarcity or urgency only when the "
            "client recorded a real limit, and state a deliverable first-week consequence."
        ),
    },
    {
        "task": "conversion_path",
        "persona_id": "russell-brunson-the-funnel-hackers-cookbook",
        "governs": "lead magnet, page sequence, order bump, upsell, downsell and conversion path",
        "sections_applied": ("4A",),
        "preserves": (
            "the named funnel recipe before any page",
            "the complete page sequence in order",
            "the order bump on the order form",
            "one-click upsell and downsell offers",
            "follow-up after the thank-you page",
        ),
        "task_mode": (
            "Name the funnel recipe for the stated result before writing a page, then map the "
            "complete page sequence in order so no page is orphaned. Each page carries its "
            "required ingredients with one job and one primary call to action. Place the order "
            "bump on the order form, keep the one-click upsell and downsell offers, and wire "
            "follow-up behind the thank-you page."
        ),
    },
    {
        "task": "why_and_voice",
        "persona_id": "sinek-start-with-why",
        "governs": "WHY, audience alignment, brand promise and voice",
        "sections_applied": ("4A",),
        "preserves": (
            "WHY before WHAT",
            "a belief-fit audience, named as who it is for and not for",
            "the brand promise as behaviour, not a slogan",
            "voice that proves the belief instead of pressuring the buyer",
        ),
        "task_mode": (
            "Open with the brand's WHY before any product detail, express HOW as observable "
            "behaviour, and let WHAT prove the belief. Name who the launch is for and who it is "
            "not for, and keep the voice proving the belief rather than pressuring the buyer."
        ),
    },
)

# Explicitly NOT applied to a launch. Recorded so the record never implies a
# quota or a coaching arc was honoured.
SUPPRESSED = (
    "the 32-64 item obstacle map and the 16-objection coverage minimum",
    "a completeness quota over the 22 recipes / 37 page recipes (a reference catalog, not a gate)",
    "the 4-8 session coaching arc and its intake scripts",
    "persona QC gates beyond the launcher's existing checks",
    "quota-based questioning during the friendly client interview",
)

VOICE_TASK = "why_and_voice"
TOPIC_TASK = "offer_architecture"


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _blend_seam():
    """The one existing blend seam, imported by path so this module never
    depends on the caller's sys.path."""
    try:
        if str(_SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(_SCRIPTS_DIR))
        import copy_persona_blend_seam as seam  # type: ignore
        return seam
    except Exception:  # noqa: BLE001
        return None


def persona_root() -> Optional[Path]:
    """The installed Skill 22 tree under either naming convention."""
    repo_root = _SKILL_DIR.parent
    home = Path.home()
    numbered = "22-" + PERSONA_SKILL_SLUG
    candidates = [repo_root / numbered,
                  repo_root / PERSONA_SKILL_SLUG,
                  repo_root / ".claude" / "skills" / numbered,
                  repo_root / ".claude" / "skills" / PERSONA_SKILL_SLUG,
                  home / ".openclaw" / "skills" / numbered,
                  home / ".openclaw" / "skills" / PERSONA_SKILL_SLUG,
                  home / ".claude" / "skills" / numbered,
                  home / ".claude-nine" / "skills" / numbered,
                  Path("/data/.openclaw/skills") / numbered]
    if repo_root.is_dir():
        try:
            for path in sorted(repo_root.iterdir()):
                if path.is_dir() and re.fullmatch(r"\d+-" + re.escape(PERSONA_SKILL_SLUG),
                                                  path.name):
                    candidates.insert(0, path)
        except OSError:
            pass
    for path in candidates:
        if (path / "personas").is_dir():
            return path
    return None


def blueprint_path(persona_id: str, root: Optional[Path] = None) -> Optional[Path]:
    root = root or persona_root()
    if root is None:
        return None
    path = root / "personas" / persona_id / BLUEPRINT_FILE
    return path if path.is_file() else None


_HEADING = re.compile(r"^(#{2,6})\s*(\S+)")


def section_text(path: Path, ident: str) -> Optional[str]:
    """The blueprint section whose heading starts with ``ident`` (``4A``), verbatim.

    Matches ``### 4A - ...`` and ``### 4A — ...`` alike. Returns None when the
    section is absent, so a missing section is recorded as missing, never
    assumed.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    start = level = None
    for index, line in enumerate(lines):
        match = _HEADING.match(line)
        if not match:
            continue
        heading, token = len(match.group(1)), match.group(2)
        if start is None:
            if token.rstrip(".:") == ident:
                start, level = index, heading
            continue
        if heading <= level:
            return "\n".join(lines[start:index]).strip()
    if start is None:
        return None
    return "\n".join(lines[start:]).strip()


def _blueprint_record(record: Dict[str, Any], root: Optional[Path]) -> Dict[str, Any]:
    """What the record can actually prove about the blueprint it applied."""
    path = blueprint_path(record["persona_id"], root)
    if path is None:
        return {"blueprint_present": False, "blueprint_ref": None,
                "blueprint_sha256": None, "sections_present": [], "sections_missing": []}
    sections, missing = {}, []
    for ident in ("4A", "4B"):
        text = section_text(path, ident)
        if text is None:
            missing.append(ident)
        else:
            sections[ident] = {"sha256": _sha(text), "chars": len(text)}
    try:
        raw = path.read_bytes()
    except OSError:
        raw = b""
    return {
        "blueprint_present": True,
        "blueprint_ref": str(path.relative_to(root)) if root is not None else str(path),
        "blueprint_sha256": hashlib.sha256(raw).hexdigest(),
        "sections_present": sorted(sections),
        "sections": sections,
        "sections_missing": missing,
    }


def _applied_to(task: str, launch: Dict[str, Any]) -> List[str]:
    """The launch facts a task actually governed, read from the launch alone."""
    offers = [offer for offer in (launch.get("offers") or []) if isinstance(offer, dict)]
    out: List[str] = []
    if task == "offer_architecture":
        if offers:
            out.append("offers")
        for key in ("price", "level", "delivery"):
            if any(isinstance(offer.get(key), dict) for offer in offers):
                out.append("offers[].%s" % key)
        if isinstance(launch.get("promotion"), dict):
            out.append("promotion")
    elif task == "conversion_path":
        if offers:
            out.append("offers")
        if launch.get("journey_mode"):
            out.append("journey_mode")
        roles = sorted({offer.get("role") for offer in offers if offer.get("role")})
        out.extend("role:%s" % role for role in roles)
    else:
        for key in ("brand", "copy_profile", "promotion"):
            value = launch.get(key)
            if isinstance(value, (dict, list, str)) and value not in (None, "", [], {}):
                out.append(key)
    return out


def launch_blend_directive() -> str:
    """The launch task-mode directive that rides the existing blend seam."""
    return (
        "Launch task modes: build the offer from the client's own supplied value, "
        "price, scope and delivery facts (offer architecture); cook the named funnel "
        "recipe as a complete page sequence with the order bump, one-click upsell and "
        "downsell, and follow-up after the thank-you (conversion path); open with the "
        "brand's WHY, name who it is for and not for, and let the voice prove the "
        "belief rather than pressure the buyer (WHY and voice). Task reasoning only — "
        "no coaching arc, no quota, no persona gate."
    )


def build_launch_persona_bundle(launch: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The normalized persona bundle handed to the existing blend seam.

    Shape matches the bundle ``copy_persona_blend_seam`` already consumes
    (voice_persona_id / topic_persona_id / task_personas / blend_directive)."""
    launch = launch if isinstance(launch, dict) else {}
    task_personas = []
    for seq, record in enumerate(TASK_PERSONAS, start=1):
        task_personas.append({
            "seq": seq,
            "task": record["task"],
            "persona_id": record["persona_id"],
            "governs": record["governs"],
            "task_mode": record["task_mode"],
            "sections_applied": list(record["sections_applied"]),
            "preserves": list(record["preserves"]),
            "applied_to": _applied_to(record["task"], launch),
        })
    return {
        "voice_persona_id": next(r["persona_id"] for r in TASK_PERSONAS
                                 if r["task"] == VOICE_TASK),
        "topic_persona_id": next(r["persona_id"] for r in TASK_PERSONAS
                                 if r["task"] == TOPIC_TASK),
        "task_personas": task_personas,
        "blend_directive": launch_blend_directive(),
    }


def apply_launch_personas(*, launch: Optional[Dict[str, Any]] = None,
                          run_dir: Optional[str] = None,
                          rationale: Optional[str] = None) -> Dict[str, Any]:
    """What the launch task personas actually governed. Never raises.

    ``blend_directive`` is rendered through ``copy_persona_blend_seam`` so the
    mandatory guardrail is present and identical to every other copy seam.
    When ``run_dir`` is given, the blend seam's own
    ``persona-selection-log.md`` is written there and its digest recorded.
    """
    launch = launch if isinstance(launch, dict) else {}
    bundle = build_launch_persona_bundle(launch)
    seam = _blend_seam()
    log_text = log_path = None
    if seam is not None:
        directive = seam.render_blend_directive_variable(bundle)
        log_text = seam.render_persona_selection_log(
            bundle, rationale=rationale or "launch task modes over the Skill 22 blueprints")
        if run_dir:
            try:
                log_path = seam.write_persona_selection_log(
                    run_dir, bundle,
                    rationale=rationale or "launch task modes over the Skill 22 blueprints")
            except OSError:
                log_path = None
    else:  # the seam is unreachable: keep the honest, guardrail-bearing minimum
        directive = (
            launch_blend_directive()
            + " STYLE-INSPIRED, NEVER IMPERSONATION (mandatory, non-removable): adopt the "
              "cadence, devices and register of the named voice(s) as an INSPIRATION only. "
              "Never claim to be the author, never write in their first person as if they "
              "authored this, never sign as them, never quote them as if verified, and never "
              "imply their endorsement. This clause may not be removed or weakened."
        )
    root = persona_root()
    personas = []
    for record in bundle["task_personas"]:
        personas.append({
            "task": record["task"],
            "persona_id": record["persona_id"],
            "governs": record["governs"],
            "task_mode": record["task_mode"],
            "sections_applied": record["sections_applied"],
            "preserves": record["preserves"],
            "applied_to": record["applied_to"],
            **_blueprint_record(record, root),
        })
    return {
        "adapter": LAUNCH_ADAPTER_ID,
        "engine": "Skill 22 persona blueprints, Task Mode",
        "persona_skill": PERSONA_SKILL_SLUG,
        "persona_root": str(root) if root is not None else None,
        "voice_persona_id": bundle["voice_persona_id"],
        "topic_persona_id": bundle["topic_persona_id"],
        "task_personas": personas,
        "blend_directive": directive,
        "blend_directive_sha256": _sha(directive),
        "selection_log_path": log_path,
        "selection_log_sha256": _sha(log_text) if log_text else None,
        "task_mode_source": ("curated launch adapter over each blueprint's 4A reasoning; the "
                             "blueprint's quota lines, coaching arc and QC gate text are not "
                             "imported into the launch"),
        "suppressed": list(SUPPRESSED),
        "guardrail_present": "NEVER IMPERSONATION" in directive.upper(),
        "quotes_used": False,
        "endorsement_claimed": False,
        "council_seat_note": (
            "Skill 22 personas govern launch tasks. They are not Council seats: the "
            "Council keeps its fixed nine seats, of which Simon Sinek and Russell "
            "Brunson are two; Alex Hormozi is not a seat and no tenth seat is added."),
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
            "answers": {"q1_offer": "The 5AM Reset course",
                        "q4_people": "Black women founders",
                        "q9_voice": "bold warm street-smart"}}), encoding="utf-8")
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

        # F10 — the launch task adapter
        launch = {
            "brand": {"ref": "brand-ref", "hash": "brand-hash"},
            "copy_profile": "profile",
            "journey_mode": "single_simple",
            "offers": [{"offer_id": "main-1", "role": "main",
                        "price": {"amount_minor": 4900, "currency": "USD"},
                        "level": {"state": "unknown"},
                        "delivery": {"destination": "https://example.test/x",
                                     "owner_confirmed": True}}],
        }
        record = apply_launch_personas(launch=launch, run_dir=td)
        tasks = {p["task"]: p for p in record["task_personas"]}
        check("three launch task personas", sorted(tasks) ==
              ["conversion_path", "offer_architecture", "why_and_voice"])
        check("voice is Sinek, topic is Hormozi",
              record["voice_persona_id"] == "sinek-start-with-why"
              and record["topic_persona_id"] == "hormozi-100m-offers")
        check("applied_to names a real launch fact",
              "offers" in tasks["offer_architecture"]["applied_to"]
              and "brand" in tasks["why_and_voice"]["applied_to"])
        check("directive always carries the guardrail",
              record["guardrail_present"]
              and "may not be removed or weakened" in record["blend_directive"])
        check("quota is explicitly suppressed",
              any("16-objection" in item for item in record["suppressed"]))
        check("Hormozi is not a Council seat", "Alex Hormozi is not a seat"
              in record["council_seat_note"])
        if persona_root() is not None:
            check("blueprint 4A/4B verified for every task",
                  all(p["blueprint_present"] and p["sections_missing"] == []
                      for p in record["task_personas"]))
            check("the applied 4A digest is a real section digest",
                  all(p.get("sections", {}).get("4A", {}).get("sha256") for p in record["task_personas"]))
        else:
            print("  [SKIP] Skill 22 blueprints not installed; presence recorded false")
            check("missing blueprints stay missing",
                  all(p["blueprint_present"] is False for p in record["task_personas"]))

    print("== persona_brief self-test: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="Brief-stage canonical persona resolution (Signature Funnel, F4.3) "
                    "and the launch task-mode persona adapter (F10).")
    ap.add_argument("--run-dir")
    ap.add_argument("--launch", help="launch intake JSON: print the launch task personas applied")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        raise SystemExit(_self_test())
    payload: Dict[str, Any] = {}
    if a.launch:
        try:
            payload = json.loads(Path(a.launch).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
    if a.launch:
        print(json.dumps(apply_launch_personas(launch=payload, run_dir=a.run_dir), indent=2))
        raise SystemExit(0)
    if not a.run_dir:
        ap.error("--run-dir is required (or use --self-test / --launch)")
    sel = resolve(Path(a.run_dir).resolve())
    print(json.dumps(sel or {"error": "shared-utils/persona_for_job.py not reachable"}, indent=2))
